"""Case bundles for an observation-first historical fire replay.

The replay groups authentic, standard-processing FIRMS detections into daily
1 km EASE-Grid cell observations.  It is a visualization of reported samples,
not a fire perimeter, a spread model, or an observation-opportunity mask.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from pyproj import Transformer

from .core import GRID_METERS, GRID_VERSION, TO_GRID, calendar_row_included
from .provenance import public_source_reference

FROM_GRID = Transformer.from_crs("EPSG:6933", "EPSG:4326", always_xy=True)
SOURCES = ("MODIS_SP", "VIIRS_SNPP_SP")
SCHEMA = "fireatlas-observation-replay-v1"

# The event names and incident coordinates come from the CAL FIRE pages. The
# AOI/time window only selects FIRMS records; it does not assign every point to
# the named incident.
CASES = {
    "park-2024": {
        "title": "Park Fire · California · 2024",
        "subtitle": "A large, fast-growing Northern California fire",
        "start": "2024-07-24", "end": "2024-08-14", "selected_day": "2024-07-25",
        "bbox": [-122.0, 39.5, -121.3, 40.5],
        "incident": {"name": "CAL FIRE Park Fire incident record",
                     "url": "https://www.fire.ca.gov/incidents/2024/7/24/park-fire/",
                     "longitude": -121.76168, "latitude": 39.7789},
        "notes": [
            "The selected window and AOI collect observations around the incident; detections are not assigned to an official fire perimeter.",
            "NASA documented a Suomi-NPP standard-product processing gap from 2024-07-24 05:24 UTC through 2024-07-29 15:18 UTC. Endpoint days are partial.",
        ],
        "gaps": [{"source_id": "VIIRS_SNPP_SP", "start": "2024-07-24", "end": "2024-07-29",
                  "kind": "documented-product-gap", "partial_first": True, "partial_last": True,
                  "url": "https://landweb.modaps.eosdis.nasa.gov/displayissue?id=716"}],
    },
    "camp-2018": {
        "title": "Camp Fire · California · 2018",
        "subtitle": "A historic Butte County fire · candidate detections in a frozen study box",
        "start": "2018-11-08", "end": "2018-11-21", "selected_day": "2018-11-09",
        "bbox": [-121.85, 39.6, -121.3, 40.0],
        "incident": {"name": "CAL FIRE Camp Fire incident record",
                     "url": "https://www.fire.ca.gov/incidents/2018/11/8/camp-fire/",
                     "longitude": -121.4347, "latitude": 39.7596},
        "notes": [
            "The frozen AOI and dates select nearby standard-processing detections. FIRMS points are not validated Camp Fire membership or a fire boundary.",
            "This case uses local MODIS and Suomi-NPP records. A missing day remains unknown without a matching complete export and an observation mask.",
        ],
        "gaps": [],
    },
    "grove-2025": {
        "title": "Grove Fire · California · 2025",
        "subtitle": "A sparse-data example · only a few imported detections",
        "start": "2025-07-04", "end": "2025-07-06", "selected_day": "2025-07-04",
        "bbox": [-121.55, 39.25, -121.28, 39.48],
        "incident": {"name": "CAL FIRE Grove Fire incident record",
                     "url": "https://www.fire.ca.gov/incidents/2025/7/4/grove-fire",
                     "longitude": -121.4139814, "latitude": 39.3742124},
        "notes": [
            "The local archive contains only a few detections for this case. Empty frames are unknown and must not be read as fire-free conditions.",
            "The nearby incident location is a reference point, not a perimeter or a map-matched fire label.",
        ],
        "gaps": [],
    },
}


def _case_spec(case_id: str) -> dict:
    if case_id not in CASES:
        raise ValueError("case must be park-2024, camp-2018, or grove-2025")
    return CASES[case_id]


def _dedup_key(row: dict) -> tuple:
    """Collapse duplicate Suomi-NPP platform spellings while keeping versions."""
    platform = str(row["platform"]).strip().upper()
    if row["source_id"] == "VIIRS_SNPP_SP":
        platform = "SNPP"
    elif row["source_id"] == "MODIS_SP":
        platform = "TERRA" if platform in ("T", "TERRA") else "AQUA"
    return (row["source_id"], platform, row["product_version"], row["acquisition_utc"],
            row["lon"], row["lat"], row["scan_m"], row["track_m"],
            row["confidence_raw"], row["frp_raw"])


def _source_export_status(db, case: dict, source_id: str, stamp: str) -> dict:
    month = stamp[:7]
    bbox = case["bbox"]
    rows = db.execute("""
        SELECT complete_export,west,south,east,north,coverage_basis,product_versions_json,
               parent_sha256,request_sha256
        FROM source_exports
        WHERE source_id=? AND month=?
    """, (source_id, month)).fetchall()
    covering = [row for row in rows if row["west"] <= bbox[0] and row["south"] <= bbox[1]
                and row["east"] >= bbox[2] and row["north"] >= bbox[3]]
    if any(row["complete_export"] for row in covering):
        state = "complete_export"
    elif covering:
        state = "partial_export"
    else:
        state = "unknown"
    gap = next((item for item in case["gaps"]
                if item["source_id"] == source_id and item["start"] <= stamp <= item["end"]), None)
    if gap:
        state = "partial_product_gap" if ((stamp == gap["start"] and gap["partial_first"])
                                           or (stamp == gap["end"] and gap["partial_last"])) else "documented_product_gap"
    versions = set()
    hashes = set()
    for row in covering:
        try:
            value = json.loads(row["product_versions_json"] or "[]")
            versions.update(value if isinstance(value, list) else value.values() if isinstance(value, dict) else [])
        except (TypeError, json.JSONDecodeError):
            pass
        for key in ("parent_sha256", "request_sha256"):
            if row[key]:
                hashes.add(row[key])
    return {"state": state, "label": {
        "complete_export": "Complete export request", "partial_export": "Partial export",
        "unknown": "Export completeness unknown", "documented_product_gap": "Documented product gap",
        "partial_product_gap": "Partial day · documented product gap",
    }[state], "request_coverage_basis": sorted({row["coverage_basis"] for row in covering}),
        "product_versions": sorted(str(value) for value in versions),
        "request_hashes": sorted(hashes),
        "pass_cloud_opportunity": "unknown"}


def build_case(db, case_id: str) -> dict:
    case = _case_spec(case_id)
    end_exclusive = (date.fromisoformat(case["end"]) + timedelta(days=1)).isoformat()
    west, south, east, north = case["bbox"]
    raw_rows = db.execute("""
        SELECT o.detection_id,o.source_id,o.platform,o.product_version,o.acquisition_utc,
               o.lon,o.lat,o.scan_m,o.track_m,o.grid_x,o.grid_y,o.confidence_raw,
               o.frp_raw,o.daynight,o.source_uri,o.raw_json,b.file_sha256,
               b.source_uri AS batch_source_uri,b.retrieved_utc
        FROM observations o JOIN batches b ON b.id=o.batch_id
        WHERE b.demo=0 AND o.source_id IN (?,?)
          AND o.processing_level='SP' AND o.acquisition_utc>=? AND o.acquisition_utc<?
          AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=?
        ORDER BY o.acquisition_utc,o.detection_id
    """, (*SOURCES, case["start"], end_exclusive, west, east, south, north)).fetchall()

    unique = {}
    duplicate_count = 0
    excluded_types = 0
    for sql_row in raw_rows:
        row = dict(sql_row)
        if not calendar_row_included(row["raw_json"]):
            excluded_types += 1
            continue
        key = _dedup_key(row)
        if key in unique:
            duplicate_count += 1
            continue
        unique[key] = row

    by_day = defaultdict(lambda: defaultdict(list))
    provenance_by_source = defaultdict(lambda: {"hashes": set(), "uris": set(), "versions": set(), "retrieved": set()})
    observations = []
    for row in unique.values():
        stamp = row["acquisition_utc"][:10]
        source = row["source_id"]
        frp = None
        try:
            frp = float(row["frp_raw"]) if row["frp_raw"] not in (None, "") else None
            if frp is not None and not math.isfinite(frp):
                frp = None
        except (TypeError, ValueError):
            frp = None
        record = {"id": row["detection_id"], "date": stamp,
                  "acquisition_utc": row["acquisition_utc"], "source_id": source,
                  "platform": row["platform"], "product_version": row["product_version"],
                  "longitude": row["lon"], "latitude": row["lat"],
                  "grid_x": row["grid_x"], "grid_y": row["grid_y"],
                  "frp_mw": frp, "confidence": row["confidence_raw"],
                  "daynight": row["daynight"], "scan_m": row["scan_m"],
                  "track_m": row["track_m"], "source_uri": public_source_reference(row["source_uri"]),
                  "source_file_sha256": row["file_sha256"],
                  "retrieved_utc": row["retrieved_utc"]}
        observations.append(record)
        by_day[stamp][source].append(record)
        prov = provenance_by_source[source]
        if row["file_sha256"]:
            prov["hashes"].add(row["file_sha256"])
        if row["source_uri"]:
            prov["uris"].add(public_source_reference(row["source_uri"]))
        if row["batch_source_uri"]:
            prov["uris"].add(public_source_reference(row["batch_source_uri"]))
        prov["versions"].add(row["product_version"])
        prov["retrieved"].add(row["retrieved_utc"])

    frames = []
    current, last = date.fromisoformat(case["start"]), date.fromisoformat(case["end"])
    while current <= last:
        stamp = current.isoformat()
        sensor_cells = {source: defaultdict(list) for source in SOURCES}
        for source in SOURCES:
            for record in by_day[stamp][source]:
                sensor_cells[source][(record["grid_x"], record["grid_y"])].append(record)
        keys = set(sensor_cells[SOURCES[0]]) | set(sensor_cells[SOURCES[1]])
        cells = []
        for gx, gy in sorted(keys):
            lon, lat = FROM_GRID.transform((gx + .5) * GRID_METERS, (gy + .5) * GRID_METERS)
            # Store the actual equal-area grid-cell footprint for the 3D view.
            # Projecting the four corners here keeps the ground drape aligned
            # with the same EPSG:6933 cells used for all counts.
            ring = [list(FROM_GRID.transform(x, y)) for x, y in (
                (gx * GRID_METERS, gy * GRID_METERS),
                ((gx + 1) * GRID_METERS, gy * GRID_METERS),
                ((gx + 1) * GRID_METERS, (gy + 1) * GRID_METERS),
                (gx * GRID_METERS, (gy + 1) * GRID_METERS),
                (gx * GRID_METERS, gy * GRID_METERS),
            )]
            modis_rows = sensor_cells["MODIS_SP"].get((gx, gy), [])
            viirs_rows = sensor_cells["VIIRS_SNPP_SP"].get((gx, gy), [])
            modis_frp = [record["frp_mw"] for record in modis_rows if record["frp_mw"] is not None]
            viirs_frp = [record["frp_mw"] for record in viirs_rows if record["frp_mw"] is not None]
            cells.append({"grid_x": gx, "grid_y": gy, "longitude": lon, "latitude": lat,
                          "ring": ring,
                          "modis_detections": len(modis_rows), "viirs_detections": len(viirs_rows),
                          "modis_frp_max_mw": max(modis_frp) if modis_frp else None,
                          "viirs_frp_max_mw": max(viirs_frp) if viirs_frp else None,
                          "sources": (["MODIS_SP"] if modis_rows else []) + (["VIIRS_SNPP_SP"] if viirs_rows else [])})
        products = {}
        for source in SOURCES:
            rows = by_day[stamp][source]
            cell_count = len(sensor_cells[source])
            statuses = _source_export_status(db, case, source, stamp)
            products[source] = {**statuses, "detections": len(rows), "cell_days": cell_count,
                                "frp_sum_mw": round(sum(record["frp_mw"] for record in rows
                                                        if record["frp_mw"] is not None), 3),
                                "frp_max_mw": max((record["frp_mw"] for record in rows
                                                    if record["frp_mw"] is not None), default=None),
                                "product_versions": sorted({record["product_version"] for record in rows})
                                or statuses["product_versions"]}
        frames.append({"date_utc": stamp, "products": products, "joint_cell_days": len(keys),
                       "observed": bool(keys), "cells": cells})
        current += timedelta(days=1)

    source_summary = {}
    for source in SOURCES:
        records = [record for record in observations if record["source_id"] == source]
        provenance = provenance_by_source[source]
        source_summary[source] = {
            "detections": len(records),
            "cell_days": sum(frame["products"][source]["cell_days"] for frame in frames),
            "detected_days": sum(frame["products"][source]["detections"] > 0 for frame in frames),
            "product_versions": sorted(provenance["versions"]),
            "source_file_hashes": sorted(provenance["hashes"]),
            "source_uris": sorted(provenance["uris"]),
            "retrieved_utc": sorted(provenance["retrieved"]),
        }
    joint_cell_days = sum(frame["joint_cell_days"] for frame in frames)
    return {
        "schema": SCHEMA, "case_id": case_id,
        "case": {key: value for key, value in case.items() if key != "gaps"},
        "grid": {"id": GRID_VERSION, "crs": "EPSG:6933", "cell_size_m": GRID_METERS,
                 "assignment": "Detection centroid assigned to a common 1 km equal-area grid cell."},
        "method": {
            "primary_metric": "Unique detected cell-days per selected sensor; joint counts each grid cell once per UTC date if either sensor reports it.",
            "heatmap": "Fixed-kernel smoothing of detected 1 km cell-days. Relative visual concentration only; it is not temperature, fire intensity, burned area, or severity.",
            "frp": "Maximum and summed reported FRP are kept separately for each source and date, in MW. FRP is not temperature or a severity score.",
            "persistence": "Distinct observed UTC days per grid cell up to the selected date, within the selected source mode.",
            "missing_data": "A frame without rows stays unknown unless a source export explicitly covers the case AOI and UTC month. Export completeness does not establish a clear satellite pass.",
            "deduplication": "Standard-processing records only; vegetation-fire type 0 or missing type; exact imported repeats collapsed; Suomi-NPP N/SNPP aliases canonicalized within source, version, acquisition, position, scan, track, confidence and FRP.",
        },
        "summary": {"raw_rows_in_aoi": len(raw_rows), "eligible_unique_detections": len(observations),
                    "duplicate_alias_rows_removed": duplicate_count, "excluded_non_vegetation_rows": excluded_types,
                    "joint_cell_days": joint_cell_days,
                    "detected_days": sum(frame["observed"] for frame in frames),
                    "sources": source_summary},
        "frames": frames, "observations": sorted(observations,
                                                   key=lambda row: (row["acquisition_utc"], row["source_id"], row["id"])),
        "limitations": [
            "FIRMS detections are thermal-anomaly observations, not fire perimeters or confirmed incident membership.",
            "The daily sequence is not a physical fire-spread simulation and makes no forecast.",
            "No detection can mean no detection was imported; satellite pass, cloud, and cell-level observation opportunity stay unknown without validated masks.",
            "MODIS and VIIRS remain separate sensor products. Joint mode counts their union on a common UTC-day grid and never adds raw sensor counts.",
            "MCD64A1 is a later, MODIS-dependent burn-date context layer. It is not independent validation or same-day active-fire truth.",
        ],
    }


def build_catalog(db, built_cases: dict | None = None) -> dict:
    cases = []
    for case_id, spec in CASES.items():
        bundle = (built_cases or {}).get(case_id) or build_case(db, case_id)
        source_status = {source: sorted({frame["products"][source]["state"] for frame in bundle["frames"]})
                         for source in SOURCES}
        cases.append({"id": case_id, "title": spec["title"], "subtitle": spec["subtitle"],
                      "start": spec["start"], "end": spec["end"],
                      "selected_day": spec["selected_day"], "bbox": spec["bbox"],
                      "incident": spec["incident"], "notes": spec["notes"],
                      "summary": bundle["summary"], "source_status": source_status,
                      "bundle": f"cases/{case_id}.json.gz"})
    return {"schema": "fireatlas-observation-replay-catalog-v1",
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "cases": cases,
            "context_layers": {
                "terrain": {"available_cases": ["park-2024", "camp-2018", "grove-2025"],
                            "source": "Locally supplied NASADEM HGT; hillshade context. 3D elevation surface is streamed from the same World Elevation service as the existing globe."},
                "ndvi": {"available_cases": ["park-2024"], "source": "Local Terra MOD13Q1 Version 061, 16-day NDVI composite A2024193 (2024-07-11)."},
                "landcover": {"available_cases": ["park-2024"], "source": "Local MCD12Q1 Version 061 annual 2024 IGBP land-cover classification."},
                "burned_area": {"available_cases": ["park-2024"], "source": "Local MCD64A1 Version 061 Burn Date for July and August 2024; lagged MODIS-derived context, not independent validation."},
                "power": {"available_cases": [], "source": "NASA POWER is local point data at 39.9°N, 121.1°W in local solar time; outside the frozen Park AOI, so it is not drawn over the selected case."},
            },
            "provenance": {"local_database": "data/fireatlas.sqlite3", "products": ["MODIS active fire standard processing", "VIIRS Suomi-NPP active fire standard processing"], "no_new_downloads": True}}
