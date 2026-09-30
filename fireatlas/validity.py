"""Frozen, inspectable historical cases for the MODIS–VIIRS calendar.

FIRMS detection rows establish where heat was reported.  They do not establish
clear passes, cloud cover, fire boundaries, or a reference fire truth set.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import sqlite3
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .core import GRID_METERS, GRID_VERSION, SERIES, TO_GRID, _complete_month

SCHEMA = "fireatlas-validity-case-v1"
BUNDLE_SCHEMA = "fireatlas-validity-evidence-v1"
SOURCES = SERIES["joint"]
CASES = {
    "park-2024": {
        "title": "Park Fire · July 2024", "year": 2024, "month": 7,
        "start": "2024-07-17", "end": "2024-07-31", "selected_day": "2024-07-25",
        "bbox": [-122.0, 39.5, -121.3, 40.5],
        "official": {"name": "CAL FIRE Park Fire incident record",
                     "url": "https://www.fire.ca.gov/incidents/2024/7/24/park-fire/",
                     "start_local": "2024-07-24T14:52:00", "timezone": "America/Los_Angeles",
                     "lon": -121.76168, "lat": 39.7789},
        "source_notice": {"source_id": "VIIRS_SNPP_SP", "start_utc": "2024-07-24",
                          "end_utc": "2024-07-29", "partial_first_day": True,
                          "partial_last_day": True, "start_time_utc": "05:24", "end_time_utc": "15:18",
                          "type": "documented-product-processing-gap",
                          "url": "https://landweb.modaps.eosdis.nasa.gov/displayissue?id=716",
                          "description": "NASA's LDOPE record gives the final S-NPP science-product outage as 24 July 05:24 UTC through 29 July 15:18 UTC, inclusive. The two endpoint days are partial; this does not establish a cell-level pass or cloud mask."},
    },
    "grove-2025": {
        "title": "Grove Fire · July 2025", "year": 2025, "month": 7,
        "start": "2025-07-04", "end": "2025-07-06", "selected_day": "2025-07-04",
        "bbox": [-121.55, 39.25, -121.28, 39.48],
        "official": {"name": "CAL FIRE Grove Fire incident record",
                     "url": "https://www.fire.ca.gov/incidents/2025/7/4/grove-fire",
                     "start_local": "2025-07-04T14:50:00", "timezone": "America/Los_Angeles",
                     "lon": -121.4139814, "lat": 39.3742124},
    },
}


def _case(case_id: str) -> dict:
    if case_id not in CASES:
        raise ValueError("case must be park-2024 or grove-2025")
    return CASES[case_id]


def _rows(db: sqlite3.Connection, case: dict) -> list[dict]:
    bbox = case["bbox"]
    end_exclusive = (date.fromisoformat(case["end"]) + timedelta(days=1)).isoformat()
    rows = db.execute("""
        SELECT o.detection_id,o.source_id,o.platform,o.product_version,o.processing_level,
               o.acquisition_utc,o.lon,o.lat,o.grid_x,o.grid_y,o.confidence_raw,
               o.frp_raw,o.daynight,o.source_uri,o.raw_json,b.file_sha256,b.demo
        FROM observations o JOIN batches b ON b.id=o.batch_id
        WHERE o.source_id IN (?,?) AND o.acquisition_utc>=? AND o.acquisition_utc<?
          AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=?
        ORDER BY o.acquisition_utc,o.detection_id
    """, (*SOURCES, case["start"], end_exclusive, bbox[0], bbox[2], bbox[1], bbox[3])).fetchall()
    return [dict(row) for row in rows]


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(a)))


def _sensitivity(rows: list[dict]) -> list[dict]:
    """Recount detection-centroid cell-days under declared grid/confidence choices.

    This is a method sensitivity check, not a satellite-observation comparison.
    """
    result = []
    for metres in (500, 1000, 2000):
        for exclude_low in (False, True):
            cells = set()
            retained = 0
            for row in rows:
                confidence = str(row["confidence_raw"]).strip().lower()
                low = confidence == "l" or (row["source_id"] == "MODIS_SP"
                                              and confidence.isdigit() and int(confidence) < 30)
                if exclude_low and low:
                    continue
                x, y = TO_GRID.transform(row["lon"], row["lat"])
                cells.add((row["acquisition_utc"][:10], math.floor(x / metres), math.floor(y / metres)))
                retained += 1
            result.append({"grid_metres": metres, "exclude_low_confidence": exclude_low,
                           "retained_raw_pixels": retained, "joint_detected_cell_days": len(cells)})
    return result


def _summarize(case_id: str, rows: list[dict], *, selected_date: str | None = None,
               complete: dict[str, bool] | None = None) -> dict:
    case = _case(case_id)
    selected = selected_date or case["selected_day"]
    if not case["start"] <= selected <= case["end"] or date.fromisoformat(selected).isoformat() != selected:
        raise ValueError("date must be a UTC day in the selected case")
    marks = {source: defaultdict(set) for source in SOURCES}
    raw = Counter()
    versions = {source: set() for source in SOURCES}
    provenance = {}
    map_cells = {}
    first_near = None
    official = case["official"]
    official_start = (datetime.fromisoformat(official["start_local"])
                      .replace(tzinfo=ZoneInfo(official["timezone"]))
                      .astimezone(timezone.utc).isoformat().replace("+00:00", "Z"))
    for row in rows:
        if row["source_id"] not in SOURCES or row["demo"] or row["processing_level"] != "SP":
            raise ValueError("validity cases require authentic standard MODIS and VIIRS rows")
        day = row["acquisition_utc"][:10]
        if not case["start"] <= day <= case["end"]:
            raise ValueError("row outside the frozen case period")
        if not (case["bbox"][0] <= row["lon"] <= case["bbox"][2]
                and case["bbox"][1] <= row["lat"] <= case["bbox"][3]):
            raise ValueError("row outside the frozen case area")
        source = row["source_id"]
        projected_x, projected_y = TO_GRID.transform(row["lon"], row["lat"])
        expected_grid = (math.floor(projected_x / GRID_METERS),
                         math.floor(projected_y / GRID_METERS))
        grid = (row["grid_x"], row["grid_y"])
        if grid != expected_grid:
            raise ValueError("frozen row grid assignment does not match its coordinates")
        raw[(day, source)] += 1
        marks[source][day].add(grid)
        versions[source].add(row["product_version"])
        provenance[(source, row["file_sha256"], row["source_uri"])] = True
        distance = _km(official["lat"], official["lon"], row["lat"], row["lon"])
        if distance <= 5 and row["acquisition_utc"] >= official_start:
            if first_near is None or row["acquisition_utc"] < first_near["acquisition_utc"]:
                first_near = {"acquisition_utc": row["acquisition_utc"],
                              "source_id": source, "distance_km": round(distance, 2)}
        if day == selected:
            key = grid
            cell = map_cells.setdefault(key, {"grid_x": grid[0], "grid_y": grid[1],
                                             "lon": row["lon"], "lat": row["lat"],
                                             "sources": set(), "raw_pixels": 0,
                                             "records": []})
            cell["sources"].add(source)
            cell["raw_pixels"] += 1
            cell["records"].append({"detection_id": row["detection_id"],
                                    "source_id": source, "platform": row["platform"],
                                    "acquisition_utc": row["acquisition_utc"],
                                    "lat": row["lat"], "lon": row["lon"],
                                    "confidence_raw": row["confidence_raw"],
                                    "product_version": row["product_version"],
                                    "file_sha256": row["file_sha256"],
                                    "source_uri": row["source_uri"]})
    days = []
    current = date.fromisoformat(case["start"])
    last = date.fromisoformat(case["end"])
    while current <= last:
        day = current.isoformat()
        modis, viirs = marks[SOURCES[0]][day], marks[SOURCES[1]][day]
        days.append({"date_utc": day,
                     "raw_pixels": {source: raw[(day, source)] for source in SOURCES},
                     "detected_cell_days": {SOURCES[0]: len(modis), SOURCES[1]: len(viirs)},
                     "joint_detected_cell_days": len(modis | viirs),
                     "co_detected_cell_days": len(modis & viirs),
                     "documented_source_notice": ("partial-day-notice" if (
                                                   (day == case.get("source_notice", {}).get("start_utc") and case["source_notice"].get("partial_first_day"))
                                                   or (day == case.get("source_notice", {}).get("end_utc") and case["source_notice"].get("partial_last_day")))
                                                   else "documented-processing-gap")
                         if case.get("source_notice") and case["source_notice"]["start_utc"] <= day <= case["source_notice"]["end_utc"]
                         else None,
                     "satellite_observation_coverage": "unknown"})
        current += timedelta(days=1)
    for cell in map_cells.values():
        cell["sources"] = sorted(cell["sources"])
    return {"schema": SCHEMA, "case_id": case_id, "title": case["title"],
            "data_class": "authentic-imported" if rows else "no-detections-in-selected-area",
            "bbox": case["bbox"], "start_utc": case["start"], "end_utc": case["end"],
            "selected_date_utc": selected, "grid": GRID_VERSION,
            "sources": [{"source_id": source, "product_versions": sorted(versions[source]),
                         "full_month_export": (complete or {}).get(source, False)} for source in SOURCES],
            "days": days, "selected_day_cells": sorted(map_cells.values(), key=lambda c: (c["grid_x"], c["grid_y"])),
            "official_reference": {**official, "start_utc_interpreted": official_start,
                                   "interpretation": "California local civil time interpreted in America/Los_Angeles; the official record does not supply an explicit UTC offset."},
            "source_notice": case.get("source_notice"),
            "first_detection_within_5km_after_reported_start": first_near,
            "provenance": [{"source_id": source, "file_sha256": digest, "source_uri": uri}
                           for source, digest, uri in sorted(provenance)],
            "coverage": {"status": "unknown", "reason": "Standard FIRMS point exports do not include verified pass/cloud fire masks.",
                         "clear_observed_cell_days": None, "cloud_cell_days": None,
                         "no_pass_cell_days": None, "unknown_cell_days": None},
            "paired_observation_status": "unavailable-without-authentic-fire-masks",
            "detection_sensitivity": _sensitivity(rows),
            "limitations": ["Hotspot centroids are not a fire perimeter or burned area.",
                            "A complete detection export is not a clear satellite observation.",
                            "Same-cell, same-day overlap is not a matched overpass.",
                            "FIRMS CSV rows do not provide source fire-mask granule identifiers.",
                            "Official incident timing corroborates a case; it is not a complete reference inventory."]}


def _add_native_evidence(result: dict, rows: list[dict], inventory: dict, native: dict) -> None:
    from .masks import summarize
    result["native_masks"] = summarize(result["case_id"], rows, native, inventory,
                                       result["selected_date_utc"])
    masks = result["native_masks"]
    review = masks["raw_mask_review"]
    samples_complete = review["reviewed_samples"] >= review["required_samples"] and review["status"] == "complete"
    result["validation_gates"] = [
        {"id": "inventory", "label": "Native masks", "status": "passed" if masks["inventory_complete"] else "pending",
         "actual": masks["processed_fire_granules"], "required": masks["expected_fire_granules"], "unit": "granules"},
        {"id": "reconciliation", "label": "Match NASA rows", "status": "passed" if masks["reconciliation"]["passes_target"] else "pending",
         "actual": masks["reconciliation"]["matched"], "required": masks["reconciliation"]["total_firms_pixels"],
         "unit": "rows", "target_fraction": .98},
        {"id": "samples", "label": "Inspect raw cells", "status": "passed" if samples_complete else "pending",
         "actual": review["reviewed_samples"], "required": review["required_samples"], "unit": "reviewed samples"},
        {"id": "review", "label": "Independent review", "status": "passed" if samples_complete and review.get("independent_signoff") else "pending",
         "actual": 1 if samples_complete and review.get("independent_signoff") else 0, "required": 1, "unit": "reviewer sign-offs"},
    ]


def report(db: sqlite3.Connection, *, case_id: str, selected_date: str | None = None) -> dict:
    case = _case(case_id)
    if selected_date is not None:
        try:
            if not case["start"] <= selected_date <= case["end"] or date.fromisoformat(selected_date).isoformat() != selected_date:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError("date must be a UTC day in the selected case") from None
    complete = {source: _complete_month(db, f'{case["year"]}-{case["month"]:02d}', (source,), tuple(case["bbox"]))
                for source in SOURCES}
    rows = _rows(db, case)
    result = _summarize(case_id, rows, selected_date=selected_date, complete=complete)
    from .granules import load, summary
    inventory = load()
    result["cmr_inventory"] = summary(inventory, case_id)
    from .masks import read_evidence
    _add_native_evidence(result, rows, inventory, read_evidence(case_id))
    from .incidents import load as load_incidents, evaluate
    result["independent_incidents"] = evaluate(load_incidents(), db)
    return result


def build_evidence(db: sqlite3.Connection, case_id: str) -> bytes:
    case = _case(case_id)
    rows = _rows(db, case)
    if not rows:
        raise ValueError("authentic case rows are unavailable")
    audit = report(db, case_id=case_id)
    from .granules import SAMPLE as CMR_SAMPLE
    from .incidents import SAMPLE as INCIDENT_SAMPLE, candidate_rows, load as load_incidents
    payloads = {
        "case.json": json.dumps(audit, sort_keys=True, indent=2).encode(),
        "observations.json": json.dumps(rows, sort_keys=True, indent=2).encode(),
        "cmr_inventory.json": CMR_SAMPLE.read_bytes(),
        "incident_cohort.json": INCIDENT_SAMPLE.read_bytes(),
        "incident_candidates.json": json.dumps(candidate_rows(load_incidents(), db), sort_keys=True, indent=2).encode(),
        "method.json": json.dumps({
            "grid": GRID_VERSION, "coordinate_reference_system": "EPSG:6933",
            "assignment": "floor(projected centroid x / 1000 m), floor(projected centroid y / 1000 m)",
            "day": "UTC acquisition date", "joint_count": "distinct (UTC day, grid_x, grid_y)",
            "co_detection": "same UTC day and grid cell has both source identifiers",
            "sensitivity_grid_metres": [500, 1000, 2000],
            "low_confidence_exclusion": "VIIRS confidence l; MODIS confidence <30",
            "official_nearby_rule": "first imported detection within 5 km after reported local start, interpreted in America/Los_Angeles",
            "mask_coverage": "not derived; all pass and cloud states unknown",
            "recount_limit": "Verifier uses this repository's method code; the manifest is a consistency checksum, not a NASA signature or independent review.",
        }, sort_keys=True, indent=2).encode(),
        "README.txt": ("FireAtlas historical detection evidence v1. Run: uv run python -m fireatlas.validity FILE.zip\n"
                       "This ZIP reproduces FIRMS detection cell-day counts and a dated CAL FIRE nearby-point association check."
                       " It does not contain fire-mask coverage, an independently validated fire truth set,"
                       " or proof of no fire on blank days. native_review_template.json is a blank"
                       " hash-bound form; it is not a completed scientific review."
                       " source_uri records the original archive request and parent hash; file_sha256 identifies the clipped source slice.\n").encode(),
    }
    from .masks import read_evidence
    from .mask_review import make_template
    native = read_evidence(case_id)
    payloads["native_masks.json"] = json.dumps(native, sort_keys=True).encode()
    payloads["native_review_template.json"] = json.dumps(
        make_template(case_id, native), sort_keys=True, indent=2
    ).encode()
    manifest = {"schema": BUNDLE_SCHEMA, "case_id": case_id,
                "files": {name: hashlib.sha256(body).hexdigest() for name, body in payloads.items()}}
    payloads["manifest.json"] = json.dumps(manifest, sort_keys=True, indent=2).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in payloads.items():
            archive.writestr(name, body)
    return buffer.getvalue()


def verify_evidence(path: str | Path | io.BytesIO) -> dict:
    with zipfile.ZipFile(path) as archive:
        expected = {"case.json", "observations.json", "cmr_inventory.json", "incident_cohort.json",
                    "incident_candidates.json", "method.json", "README.txt", "manifest.json",
                    "native_review_template.json"}
        if "native_masks.json" in archive.namelist():
            expected.add("native_masks.json")
        if set(archive.namelist()) != expected:
            raise ValueError("unexpected validity bundle files")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("schema") != BUNDLE_SCHEMA or set(manifest.get("files", {})) != expected - {"manifest.json"}:
            raise ValueError("invalid validity bundle manifest")
        for name, checksum in manifest["files"].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != checksum:
                raise ValueError(f"validity bundle checksum mismatch: {name}")
        audit = json.loads(archive.read("case.json"))
        rows = json.loads(archive.read("observations.json"))
        cmr_inventory = json.loads(archive.read("cmr_inventory.json"))
        incident_cohort = json.loads(archive.read("incident_cohort.json"))
        incident_candidates = json.loads(archive.read("incident_candidates.json"))
        native = json.loads(archive.read("native_masks.json")) if "native_masks.json" in expected else None
        review_template = json.loads(archive.read("native_review_template.json"))
    if audit.get("case_id") != manifest["case_id"] or audit.get("schema") != SCHEMA:
        raise ValueError("validity case identity mismatch")
    reproduced = _summarize(manifest["case_id"], rows, selected_date=audit["selected_date_utc"],
                            complete={item["source_id"]: item["full_month_export"] for item in audit["sources"]})
    from .granules import summary
    reproduced["cmr_inventory"] = summary(cmr_inventory, manifest["case_id"])
    if native is not None:
        _add_native_evidence(reproduced, rows, cmr_inventory, native)
        from .mask_review import make_template
        if review_template != make_template(manifest["case_id"], native):
            raise ValueError("Native review template does not reproduce from frozen samples")
    from .incidents import evaluate
    reproduced["independent_incidents"] = evaluate(incident_cohort, candidates=incident_candidates)
    if reproduced != audit:
        raise ValueError("validity case does not reproduce from frozen rows")
    return {"valid": True, "case_id": manifest["case_id"], "observations": len(rows),
            "detected_cell_days": sum(day["joint_detected_cell_days"] for day in audit["days"]),
            "coverage": audit["coverage"]["status"]}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Verify a FireAtlas historical validity evidence ZIP")
    parser.add_argument("bundle")
    print(json.dumps(verify_evidence(parser.parse_args().bundle), indent=2))
