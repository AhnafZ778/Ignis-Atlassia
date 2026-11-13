"""Bounded diagnostics derived from frozen native-mask evidence, never ground truth."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import zipfile

from pyproj import Transformer

from .comparability import digest

ROOT = Path(__file__).resolve().parents[1]
CASES = ("park-2024", "grove-2025")
FROM_GRID = Transformer.from_crs("EPSG:6933", "EPSG:4326", always_xy=True)


def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def confusion(pairs):
    counts = Counter()
    for p in pairs:
        if p["modis_state"] not in ("detected", "observed-without-detection") or p["viirs_state"] not in ("detected", "observed-without-detection"):
            raise ValueError("Confusion table requires usable sampled states.")
        counts[("both_detected" if p["viirs_state"] == "detected" else "modis_only")
               if p["modis_state"] == "detected" else
               ("viirs_only" if p["viirs_state"] == "detected" else "both_without_detection")] += 1
    cells = {k: counts[k] for k in ("both_detected", "modis_only", "viirs_only", "both_without_detection")}
    total, positive = sum(cells.values()), sum(cells[k] for k in ("both_detected", "modis_only", "viirs_only"))
    return {**cells, "n_pairs": total, "positive_union_pairs": positive,
            "overall_agreement": (cells["both_detected"] + cells["both_without_detection"]) / total if total else None,
            "positive_jaccard": cells["both_detected"] / positive if positive else None,
            "modis_positive_overlap": cells["both_detected"] / (cells["both_detected"] + cells["modis_only"]) if cells["both_detected"] + cells["modis_only"] else None,
            "viirs_positive_overlap": cells["both_detected"] / (cells["both_detected"] + cells["viirs_only"]) if cells["both_detected"] + cells["viirs_only"] else None}


def derive(case, observations, inventory):
    case_id = case["case_id"]
    native = case["native_masks"]
    granules = {}
    processed = {g["producer_id"]: g for g in native["ledger"] if g["status"] == "processed"}
    for product in inventory["cases"][case_id]["products"]:
        for item in product["granules"]:
            if item["producer_id"] in processed:
                granules[item["producer_id"]] = {**item, **processed[item["producer_id"]]}
    pairs = native["paired_observations"]["pairs"]
    thresholds, enriched = {}, []
    for p in pairs:
        m, v = (granules.get(p[k]) for k in ("modis_granule", "viirs_granule"))
        if m is None or v is None:
            raise ValueError("A paired native sample lacks a processed granule interval.")
        # Use the original matching rule: all endpoints must be within the limit.
        gap = max(abs((stamp(m[a]) - stamp(v[b])).total_seconds()) / 60
                  for a in ("start_utc", "end_utc") for b in ("start_utc", "end_utc"))
        enriched.append({**p, "maximum_endpoint_gap_minutes": round(gap, 6)})
    for limit in (30, 60, 90):
        subset = [p for p in enriched if p["maximum_endpoint_gap_minutes"] <= limit]
        thresholds[str(limit)] = confusion(subset)
    positives = []
    for p in enriched:
        if p["modis_state"] != "detected" and p["viirs_state"] != "detected":
            continue
        lon, lat = FROM_GRID.transform((p["grid_x"] + .5) * 1000, (p["grid_y"] + .5) * 1000)
        positives.append({**p, "lon": round(lon, 6), "lat": round(lat, 6),
                          "category": "both_detected" if p["modis_state"] == p["viirs_state"] else
                          ("modis_only" if p["modis_state"] == "detected" else "viirs_only"),
                          "cause": "undetermined"})
    groups = defaultdict(list)
    for o in observations:
        if o.get("demo") or o["source_id"] not in ("MODIS_SP", "VIIRS_SNPP_SP"):
            raise ValueError("Only authentic standard rows belong in this evidence.")
        groups[(o["acquisition_utc"], o["source_id"], o["platform"], o["product_version"])].append(o)
    acquisitions = []
    for (when, source, platform, version), rows in sorted(groups.items()):
        frp = []
        for o in rows:
            try:
                value = float(o["frp_raw"])
                if math.isfinite(value) and value >= 0:
                    frp.append(value)
            except (ValueError, TypeError):
                pass
        acquisitions.append({"acquisition_utc": when, "source_id": source, "platform": platform,
                             "product_version": version, "rows": len(rows),
                             "occupied_cells": len({(o["grid_x"], o["grid_y"]) for o in rows}),
                             "sampled_frp_sum_mw": sum(frp) if frp else None,
                             "frp_rows": len(frp), "frp_missing_rows": len(rows) - len(frp),
                             "daynight": sorted({o["daynight"] for o in rows}),
                             "source_file_sha256": sorted({o["file_sha256"] for o in rows}),
                             "points": [{"lon": o["lon"], "lat": o["lat"], "confidence_raw": o["confidence_raw"], "frp_raw": o["frp_raw"], "detection_id": o["detection_id"]} for o in rows]})
    review = native["raw_mask_review"]
    result = {
        "schema": "fireatlas-comparison-case-v1", "case_id": case_id, "title": case["title"],
        "bbox": case["bbox"], "start_utc": case["start_utc"], "end_utc": case["end_utc"],
        "source_notice": case.get("source_notice"),
        "source_provenance": case["provenance"],
        "native_mask_method": native["method"],
        "threshold_metrics": thresholds,
        "grid_confidence_sensitivity": case["detection_sensitivity"],
        "threshold_interpretation": "30/60/90 minute subsets of the original 90-minute greedy one-to-one matches, using maximum endpoint separation; matches are not recomputed. These are sampled cell/pass pairs, not independent fires.",
        "positive_pairs": positives,
        "acquisitions": acquisitions,
        "acquisition_interpretation": "Groups preserve exact FIRMS UTC acquisition minutes, platform, source and version. Adjacent minutes are not assumed to be separate orbital overpasses. No missing pass or hourly activity is reconstructed.",
        "granules": sorted(granules.values(), key=lambda g: (g["start_utc"], g["producer_id"])),
        "review": {"status": review["status"], "reviewed": review["reviewed_samples"],
                   "required": review["required_samples"], "independent_signoff": False},
        "reconciliation": {k: native["reconciliation"].get(k) for k in ("matched", "total_firms_pixels", "fraction", "confidence_disagreements")},
        "sampled_daily_states": native["daily_sampled_state_counts"],
        "limits": [
            "High overall agreement is dominated by pairs without detection. Positive Jaccard uses only the union of positive pairs.",
            "Neither sensor is ground truth. Sensor overlap is not fire detection accuracy, precision, recall or sensitivity.",
            "Only native centroids are sampled; full-footprint cloud exposure and no-pass denominators remain unknown.",
            "A VIIRS-only sample does not establish a small fire. Timing, cloud, geometry, algorithm and sensitivity can all contribute.",
            "The Park outage affects source availability. Its case window differs from the regional monthly comparison.",
            "FRP sums are sampled MW values in one acquisition group, not energy, hourly heat release or a harmonized total.",
            "The two named cases are case studies, not representative independent validation."
        ],
    }
    result["result_sha256"] = digest(result)
    return result


def build_case(case_id, archive_root=None):
    if case_id not in CASES:
        raise ValueError("Choose park-2024 or grove-2025.")
    path = Path(archive_root or ROOT / "site/data/v2/validity") / (case_id + ".zip")
    with zipfile.ZipFile(path) as archive:
        needed = ("case.json", "observations.json", "cmr_inventory.json")
        for name in needed:
            if archive.getinfo(name).file_size > 50_000_000:
                raise ValueError("Frozen case evidence is too large.")
        raw = {name: archive.read(name) for name in needed}
    result = derive(*(json.loads(raw[name]) for name in needed))
    result["frozen_parent_members"] = {name: hashlib.sha256(body).hexdigest() for name, body in raw.items()}
    result.pop("result_sha256")
    result["result_sha256"] = digest(result)
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify",))
    parser.add_argument("file", type=Path)
    parser.add_argument("--parent-root", type=Path, default=ROOT / "site/data/v2/validity")
    args = parser.parse_args()
    if args.file.stat().st_size > 8_000_000:
        raise ValueError("Case diagnostics exceed the bounded input size.")
    value = json.loads(args.file.read_text())
    expected = build_case(value.get("case_id"), args.parent_root)
    if digest(value) != digest(expected):
        raise ValueError("Case recount differs from the frozen parent evidence.")
    print(json.dumps({"verified": True, "result_sha256": expected["result_sha256"],
                      "scope": "Recounts the fixed frozen parent ZIP members; not independent scientific review."}))


if __name__ == "__main__":
    main()
