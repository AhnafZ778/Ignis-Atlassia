"""Reproducible UTC daily FIRMS aggregates for the two study regions."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import re
import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .availability import source_status
from .core import GRID_VERSION, calendar_row_included
from .regions import REGIONS

SCHEMA = "fireatlas-daily-aggregates-v1"
METHOD_VERSION = "utc-1km-centroid-type0-or-missing-v1"
BRIDGE_METHOD_VERSION = "common-1km-bridge-frp-v1"
SOURCES = ("MODIS_SP", "VIIRS_SNPP_SP")
NATIVE_PIXEL_METERS = {"MODIS_SP": 1000, "VIIRS_SNPP_SP": 375}


def _include(row: dict) -> bool:
    return calendar_row_included(row["raw_json"])


def daily_aggregates(db, region: str, start: str | date, end: str | date) -> dict:
    if region not in REGIONS:
        raise ValueError(f"region must be one of {', '.join(REGIONS)}")
    first = date.fromisoformat(start) if isinstance(start, str) else start
    last = date.fromisoformat(end) if isinstance(end, str) else end
    if last < first:
        raise ValueError("end date precedes start date")
    bbox = REGIONS[region]["bbox"]
    complete_months = {(row["source_id"], row["month"]) for row in db.execute("""
        SELECT DISTINCT source_id,month FROM export_windows
        WHERE source_id IN (?,?) AND west<=? AND south<=? AND east>=? AND north>=?
          AND month>=? AND month<=?
    """, (*SOURCES, bbox[0], bbox[1], bbox[2], bbox[3], first.strftime("%Y-%m"), last.strftime("%Y-%m")))}
    rows = db.execute("""
        SELECT o.source_id,o.acquisition_utc,o.grid_x,o.grid_y,o.frp_raw,
               o.product_version,o.raw_json,b.file_sha256,b.source_uri
        FROM observations o JOIN batches b ON b.id=o.batch_id
        WHERE o.source_id IN (?,?) AND o.acquisition_utc>=? AND o.acquisition_utc<?
          AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=?
          AND b.demo=0
        ORDER BY o.acquisition_utc,o.source_id,o.grid_y,o.grid_x
    """, (*SOURCES, first.isoformat(), (last + timedelta(days=1)).isoformat(),
          bbox[0], bbox[2], bbox[1], bbox[3])).fetchall()
    month_meta = defaultdict(lambda: {"versions": set(), "hashes": set(), "parents": set(), "requests": set(), "coverage_bases": set()})
    for row in db.execute("""
        SELECT e.source_id,e.month,e.coverage_basis,e.product_versions_json,
               e.parent_sha256,e.request_sha256,b.file_sha256
        FROM source_exports e JOIN batches b ON b.id=e.batch_id
        WHERE e.region_id=? AND e.source_id IN (?,?) AND e.month>=? AND e.month<=?
    """, (region, *SOURCES, first.strftime("%Y-%m"), last.strftime("%Y-%m"))):
        meta = month_meta[(row["month"], row["source_id"])]
        meta["versions"].update(json.loads(row["product_versions_json"]))
        meta["hashes"].add(row["file_sha256"])
        meta["parents"].add(row["parent_sha256"])
        meta["requests"].add(row["request_sha256"])
        meta["coverage_bases"].add(row["coverage_basis"])
    by_day_source = defaultdict(lambda: {
        "cells": set(), "raw": 0, "excluded": 0, "excluded_types": defaultdict(int),
        "frp": 0.0, "frp_valid": 0,
        "versions": set(), "hashes": set(), "parents": set(),
    })
    for row in rows:
        item = dict(row)
        if not _include(item):
            # Keep excluded FIRMS rows visible in the derived artifact.  The
            # calendar still uses only type 0 (or missing type), but a reviewer
            # can now see exactly how many rows were filtered and why.
            aggregate = by_day_source[(item["acquisition_utc"][:10], item["source_id"])]
            aggregate["excluded"] += 1
            excluded_type = str(json.loads(item["raw_json"]).get("type") or "missing")
            aggregate["excluded_types"][excluded_type] += 1
            continue
        day = item["acquisition_utc"][:10]
        aggregate = by_day_source[(day, item["source_id"])]
        aggregate["cells"].add((item["grid_x"], item["grid_y"]))
        aggregate["raw"] += 1
        aggregate["versions"].add(item["product_version"])
        aggregate["hashes"].add(item["file_sha256"])
        if ":parent-sha256:" in item["source_uri"]:
            aggregate["parents"].add(item["source_uri"].split(":parent-sha256:", 1)[1].split(":", 1)[0])
        try:
            frp = float(item["frp_raw"])
            if math.isfinite(frp) and frp >= 0:
                aggregate["frp"] += frp
                aggregate["frp_valid"] += 1
        except (TypeError, ValueError):
            pass
    days = []
    current = first
    while current <= last:
        stamp, month = current.isoformat(), current.strftime("%Y-%m")
        by_source = {}
        for source in SOURCES:
            complete = (source, month) in complete_months
            aggregate = by_day_source[(stamp, source)]
            metadata = month_meta[(month, source)]
            versions = sorted(aggregate["versions"] | metadata["versions"])
            raw = aggregate["raw"]
            records = {
                "source_id": source,
                "export_complete": complete,
                "native_pixel_resolution_m": NATIVE_PIXEL_METERS[source],
                "common_grid_method": "centroid-to-EASE-Grid-1km",
                "raw_pixel_count": raw if complete else None,
                "partial_raw_pixel_count": raw if not complete else None,
                "excluded_row_count": aggregate["excluded"] if complete else None,
                "partial_excluded_row_count": aggregate["excluded"] if not complete else None,
                "excluded_type_counts": dict(sorted(aggregate["excluded_types"].items())) if complete else {},
                "partial_excluded_type_counts": dict(sorted(aggregate["excluded_types"].items())) if not complete else {},
                "detected_cell_days": len(aggregate["cells"]) if complete else None,
                "partial_detected_cell_days": len(aggregate["cells"]) if not complete else None,
                "unique_common_grid_cells": len(aggregate["cells"]) if complete else None,
                "partial_unique_common_grid_cells": len(aggregate["cells"]) if not complete else None,
                "rows_collapsed_to_common_grid_cells": max(0, raw - len(aggregate["cells"])) if complete else None,
                "partial_rows_collapsed_to_common_grid_cells": max(0, raw - len(aggregate["cells"])) if not complete else None,
                "frp_sum_mw": round(aggregate["frp"], 6) if complete and (raw == 0 or aggregate["frp_valid"]) else None,
                "partial_frp_sum_mw": round(aggregate["frp"], 6) if not complete and aggregate["frp_valid"] else None,
                "frp_valid_rows": aggregate["frp_valid"],
                "frp_missing_rows": raw - aggregate["frp_valid"],
                "product_versions": versions,
                "product_version_status": "known" if len(versions) == 1 else "mixed" if len(versions) > 1 else "unknown",
                "slice_sha256": sorted(aggregate["hashes"] | metadata["hashes"]),
                "parent_sha256": sorted(aggregate["parents"] | metadata["parents"]),
                "request_sha256": sorted(metadata["requests"]),
                "coverage_basis": sorted(metadata["coverage_bases"]),
            }
            records["availability"] = source_status(
                current, source, complete_export=complete,
                detection_count=records["raw_pixel_count"])
            # A documented product outage is not a zero-FRP observation. Keep
            # the context value unknown for that UTC day even when the export
            # contains no rows.
            if records["availability"]["status"] == "documented_processing_gap":
                records["frp_sum_mw"] = None
            by_source[source] = records
        modis_cells = by_day_source[(stamp, "MODIS_SP")]["cells"]
        viirs_cells = by_day_source[(stamp, "VIIRS_SNPP_SP")]["cells"]
        modis_complete = by_source["MODIS_SP"]["export_complete"]
        viirs_complete = by_source["VIIRS_SNPP_SP"]["export_complete"]
        gap_sensors = [source for source in SOURCES
                       if by_source[source]["availability"]["status"] == "documented_processing_gap"]
        bridge_complete = modis_complete and viirs_complete and not gap_sensors
        bridge = {
            "method_version": BRIDGE_METHOD_VERSION,
            "status": "documented-processing-gap" if gap_sensors else "complete" if bridge_complete else "partial",
            "unit": "common-grid cell-days; each sensor retained separately",
            "modis_common_grid_cells": len(modis_cells) if bridge_complete else None,
            "viirs_common_grid_cells": len(viirs_cells) if bridge_complete else None,
            "co_detected_cell_days": len(modis_cells & viirs_cells) if bridge_complete else None,
            "modis_only_cell_days": len(modis_cells - viirs_cells) if bridge_complete else None,
            "viirs_only_cell_days": len(viirs_cells - modis_cells) if bridge_complete else None,
            "partial_modis_common_grid_cells": len(modis_cells) if not modis_complete else None,
            "partial_viirs_common_grid_cells": len(viirs_cells) if not viirs_complete else None,
            "partial_co_detected_cell_days": None,
            "partial_modis_only_cell_days": None,
            "partial_viirs_only_cell_days": None,
            "missing_sensor": [source for source, complete in (("MODIS_SP", modis_complete), ("VIIRS_SNPP_SP", viirs_complete)) if not complete],
            "gap_sensor": gap_sensors,
        }
        days.append({"date_utc": stamp, "sources": by_source, "sensor_bridge": bridge})
        current += timedelta(days=1)
    provenance = db.execute("""
        SELECT DISTINCT b.source_id,b.file_sha256,b.source_uri,b.retrieved_utc
        FROM batches b LEFT JOIN export_windows w ON w.batch_id=b.id
        WHERE b.source_id IN (?,?) AND b.demo=0 AND (
          (w.month>=? AND w.month<=? AND w.west<=? AND w.south<=? AND w.east>=? AND w.north>=?)
          OR EXISTS (SELECT 1 FROM observations o WHERE o.batch_id=b.id
            AND o.acquisition_utc>=? AND o.acquisition_utc<? AND o.lon>=? AND o.lon<=?
            AND o.lat>=? AND o.lat<=?)
        ) ORDER BY b.source_id,b.file_sha256
    """, (*SOURCES, first.strftime("%Y-%m"), last.strftime("%Y-%m"), *bbox,
          first.isoformat(), (last + timedelta(days=1)).isoformat(), bbox[0], bbox[2], bbox[1], bbox[3])).fetchall()
    inputs = [dict(row) for row in provenance]
    for row in db.execute("""
        SELECT DISTINCT e.source_id,e.month,e.request_start,e.request_end,e.west,e.south,e.east,e.north,
               e.complete_export,e.coverage_basis,e.product_versions_json,e.parent_sha256,e.request_sha256,
               b.file_sha256,b.retrieved_utc
        FROM source_exports e JOIN batches b ON b.id=e.batch_id
        WHERE e.region_id=? AND e.source_id IN (?,?) AND e.month>=? AND e.month<=?
        ORDER BY e.source_id,e.month
    """, (region, *SOURCES, first.strftime("%Y-%m"), last.strftime("%Y-%m"))):
        inputs.append({**dict(row), "product_versions": json.loads(row["product_versions_json"])})
    inputs = sorted(inputs, key=lambda item: (item.get("source_id", ""), item.get("month", ""), item.get("file_sha256", "")))
    manifest_material = json.dumps({"region": region, "start": first.isoformat(), "end": last.isoformat(),
                                    "method": METHOD_VERSION, "inputs": inputs}, sort_keys=True).encode()
    return {
        "schema": SCHEMA,
        "region": {"id": region, "name": REGIONS[region]["name"], "bbox": bbox},
        "period": {"start": first.isoformat(), "end": last.isoformat()},
        "unit": "distinct 1 km EASE-Grid centroid cell-days",
        "primary_measure": "VIIRS-equivalent active-fire cell-days on a common 1 km grid",
        "native_detail": {
            "MODIS_SP": {"pixel_size_m": 1000, "label": "MODIS native ~1 km source pixels"},
            "VIIRS_SNPP_SP": {"pixel_size_m": 375, "label": "VIIRS S-NPP native 375 m source pixels"},
        },
        "bridge_method_version": BRIDGE_METHOD_VERSION,
        "frp_context": "Raw FIRMS Fire Radiative Power (MW) summed by UTC day and source; missing FRP rows are reported separately. FRP is context and is not harmonized into cell-days.",
        "grid": GRID_VERSION,
        "method_version": METHOD_VERSION,
        "detection_filter": "FIRMS type 0 or missing; all confidence values",
        "coverage_statement": "Export completeness does not establish satellite pass, cloud-free conditions, or no-fire conditions.",
        "input_manifest_sha256": hashlib.sha256(manifest_material).hexdigest(),
        "inputs": inputs,
        "days": days,
    }


def write_daily_aggregates(db, region: str, start: str | date, end: str | date,
                          output: str | Path) -> dict:
    payload = daily_aggregates(db, region, start, end)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            compressed.write(encoded)
    payload["output"] = str(path)
    payload["output_sha256"] = hashlib.sha256(encoded).hexdigest()
    payload["day_count"] = len(payload["days"])
    return payload


def paired_complete_months(db, region: str) -> list[str]:
    """Return only months with request-verified exports from both sensors."""
    complete = defaultdict(set)
    for row in db.execute("""
        SELECT source_id,month FROM source_exports
        WHERE region_id=? AND source_id IN (?,?) AND complete_export=1
    """, (region, *SOURCES)):
        complete[row["source_id"]].add(row["month"])
    return sorted(complete[SOURCES[0]] & complete[SOURCES[1]])


def _parent_inputs(db, region: str, months: list[str]) -> list[dict]:
    if not months:
        return []
    marks = ",".join("?" for _ in months)
    rows = db.execute(f"""
        SELECT DISTINCT e.source_id,e.parent_sha256,b.source_uri
        FROM source_exports e JOIN batches b ON b.id=e.batch_id
        WHERE e.region_id=? AND e.source_id IN (?,?) AND e.complete_export=1
          AND e.month IN ({marks})
        ORDER BY e.source_id,e.parent_sha256
    """, (region, *SOURCES, *months))
    found = {}
    products = {"MODIS_SP": "M-C61", "VIIRS_SNPP_SP": "SV-C2"}
    for row in rows:
        source, digest, uri = row["source_id"], row["parent_sha256"], row["source_uri"]
        if not digest or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"Missing valid parent SHA-256 for {source}; refusing an unattributed bundle")
        request = re.search(r":request-id:([^:]+)", uri or "")
        if request:
            filename = f"fire_archive_{products[source]}_{request.group(1)}.csv"
        else:
            filename = Path(urlsplit(uri or "").path).name
            if not filename:
                raise ValueError(f"Cannot identify input file for {source} parent {digest}")
        identity = (filename, digest)
        found[identity] = {"filename": filename, "sha256": digest}
    if not found:
        raise ValueError("No provenance-linked source files found for complete paired months")
    return [found[key] for key in sorted(found)]


def paired_daily_bundle(db, region: str) -> dict:
    """Build the frozen C2-T2 artifact from complete paired source months only."""
    if region not in REGIONS:
        raise ValueError(f"region must be one of {', '.join(REGIONS)}")
    months = paired_complete_months(db, region)
    if not months:
        raise ValueError(f"No complete paired MODIS/S-NPP months for {region}")
    start = date.fromisoformat(months[0] + "-01")
    last_month = date.fromisoformat(months[-1] + "-01")
    next_month = (last_month.replace(day=28) + timedelta(days=4)).replace(day=1)
    end = next_month - timedelta(days=1)
    detail = daily_aggregates(db, region, start, end)
    month_set = set(months)
    days = []
    for item in detail["days"]:
        if item["date_utc"][:7] not in month_set:
            continue
        values = {}
        for source in SOURCES:
            record = item["sources"][source]
            if not record["export_complete"]:
                raise ValueError(f"Paired month {item['date_utc'][:7]} is incomplete for {source}")
            values[source] = {
                "cells": record["detected_cell_days"],
                "raw": record["raw_pixel_count"],
                "frp_sum": record["frp_sum_mw"],
                "excluded": record["excluded_row_count"],
                "excluded_type_counts": record["excluded_type_counts"],
            }
        days.append({"date": item["date_utc"], **values, "sensor_bridge": item["sensor_bridge"]})
    return {
        "schema": SCHEMA,
        "method_version": METHOD_VERSION,
        "region": {"id": region, "bbox": list(REGIONS[region]["bbox"])},
        "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "inputs": _parent_inputs(db, region, months),
        "days": days,
    }


def write_paired_daily_bundle(db, region: str, output: str | Path) -> dict:
    payload = paired_daily_bundle(db, region)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            compressed.write(encoded)
    return {
        "region": region,
        "path": str(path),
        "months": len({item["date"][:7] for item in payload["days"]}),
        "days": len(payload["days"]),
        "inputs": len(payload["inputs"]),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description="Build reproducible paired daily FIRMS aggregate bundles")
    parser.add_argument("--db", type=Path, default=Path("data/fireatlas.sqlite3"))
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).with_name("samples") / "aggregates")
    parser.add_argument("--region", choices=tuple(REGIONS), action="append")
    args = parser.parse_args()
    from .core import connect

    results = []
    with connect(args.db) as db:
        for region in args.region or list(REGIONS):
            results.append(write_paired_daily_bundle(db, region, args.output_dir / f"{region}.json.gz"))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
