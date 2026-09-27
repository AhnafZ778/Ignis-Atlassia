"""Exploratory source comparison, candidate groups and explicit mask denominators."""
from __future__ import annotations

import calendar as civil_calendar
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from datetime import date, timedelta
from statistics import quantiles

from pyproj import Transformer

from .core import GRID_VERSION, SERIES, TO_GRID, _complete_month, validate_bbox

METHOD = "fireatlas-research-v1"
SOURCES = SERIES["joint"]
FROM_GRID = Transformer.from_crs("EPSG:6933", "EPSG:4326", always_xy=True)
MAX_RECORDS = 10000
MAX_NODES = 3000
MAX_MASK_ROWS = 20000


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def context(year, month, bbox, as_of=None, distance_km=2, gap_days=1):
    if type(year) is not int or not 2000 <= year <= 2100:
        raise ValueError("year must be an integer from 2000 to 2100")
    if type(month) is not int or not 1 <= month <= 12:
        raise ValueError("month must be an integer from 1 to 12")
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        raise ValueError("bbox needs four coordinates")
    bbox = tuple(float(v) for v in bbox)
    validate_bbox(bbox)
    if bbox[1] < -86 or bbox[3] > 86:
        raise ValueError("research grid supports latitudes from -86 to 86")
    if isinstance(distance_km, bool) or not isinstance(distance_km, (int, float)) or not math.isfinite(distance_km) or not .5 <= distance_km <= 10:
        raise ValueError("distance_km must be between 0.5 and 10")
    if type(gap_days) is not int or not 0 <= gap_days <= 7:
        raise ValueError("gap_days must be an integer from 0 to 7")
    start = date(year, month, 1)
    last = date(year, month, civil_calendar.monthrange(year, month)[1])
    cutoff = date.fromisoformat(as_of) if as_of else last
    if not start <= cutoff <= last:
        raise ValueError("as_of must be a UTC date within the selected month")
    return {"year": year, "month": month, "bbox": bbox, "as_of": cutoff.isoformat(),
            "distance_km": float(distance_km), "gap_days": gap_days}, start, cutoff


def load_records(db, config, start, cutoff):
    w, s, e, n = config["bbox"]
    rows = db.execute("""
        SELECT o.*, b.demo, b.file_sha256 FROM observations o
        JOIN batches b ON b.id=o.batch_id
        WHERE o.source_id IN (?,?) AND o.acquisition_utc>=? AND o.acquisition_utc<?
          AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=?
        ORDER BY o.acquisition_utc,o.detection_id LIMIT ?
    """, (*SOURCES, start.isoformat(), (cutoff + timedelta(days=1)).isoformat(), w, e, s, n, MAX_RECORDS + 1)).fetchall()
    if len(rows) > MAX_RECORDS:
        raise ValueError("research selection exceeds 10,000 pixels; narrow the AOI or cutoff")
    return [dict(row) for row in rows]


def overlap(rows, start, cutoff, complete):
    sets = {source: defaultdict(set) for source in SOURCES}
    raw = Counter()
    versions = {source: set() for source in SOURCES}
    for row in rows:
        sets[row["source_id"]][row["acquisition_utc"][:10]].add((row["grid_x"], row["grid_y"]))
        raw[row["source_id"]] += 1
        versions[row["source_id"]].add(row["product_version"])
    daily = []
    for offset in range((cutoff - start).days + 1):
        stamp = (start + timedelta(days=offset)).isoformat()
        m, v = (sets[source][stamp] for source in SOURCES)
        daily.append({"date": stamp, "modis": len(m), "viirs": len(v), "both": len(m & v),
                      "modis_only": len(m - v), "viirs_only": len(v - m), "union": len(m | v)})
    total = {key: sum(d[key] for d in daily) for key in ("modis", "viirs", "both", "modis_only", "viirs_only", "union")}
    active_days = sum(d["union"] > 0 for d in daily)
    mixed = any(len(v) > 1 for v in versions.values())
    interval = None
    band_status = "insufficient_active_days"
    if not all(complete.values()):
        band_status = "incomplete_exports"
    elif mixed:
        band_status = "mixed_product_versions"
    elif not total["modis"]:
        band_status = "zero_modis_denominator"
    elif active_days >= 10:
        # Paired day resampling preserves the two source counts within each day.
        # Serial dependence is not modeled: this is an exploratory percentile band.
        rng = random.Random(42)
        ratios = []
        for _ in range(1000):
            sample = [daily[rng.randrange(len(daily))] for _ in daily]
            denominator = sum(d["modis"] for d in sample)
            if denominator:
                ratios.append(sum(d["viirs"] for d in sample) / denominator)
        if len(ratios) >= 950:
            q = quantiles(ratios, n=40, method="inclusive")
            interval = [round(q[0], 4), round(q[-1], 4)]
            band_status = "exploratory"
        else:
            band_status = "unstable_denominator"
    return {"totals": total, "daily": daily, "active_days": active_days,
            "raw_pixels": dict(raw), "product_versions": {s: sorted(v) for s, v in versions.items()},
            "ratio": total["viirs"] / total["modis"] if total["modis"] else None,
            "jaccard": total["both"] / total["union"] if total["union"] else None,
            "ratio_band": interval, "band_status": band_status,
            "band_method": "Paired UTC-day percentile bootstrap, 1000 resamples, seed 42; 2.5–97.5 percentiles; minimum 10 active days. Temporal dependence is not modeled.",
            "calibration_status": "not_calibrated",
            "note": "Same-cell, same-day co-occurrence is descriptive; it does not establish paired overpasses, equal exposure or sensor sensitivity."}


def candidates(rows, distance_km, gap_days):
    nodes = defaultdict(list)
    for row in rows:
        nodes[(row["acquisition_utc"][:10], row["grid_x"], row["grid_y"])].append(row)
    if len(nodes) > MAX_NODES:
        raise ValueError("candidate tracking exceeds 3,000 cell-days; narrow the selection")
    keys = sorted(nodes)
    parent = list(range(len(keys)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # Distances measured geodesically between fixed grid cell centers. EPSG:6933
    # is equal-area, not equidistant; its x/y spacing must not be used as ground km.
    from pyproj import Geod
    geod = Geod(ellps="WGS84")
    centers = [FROM_GRID.transform((x + .5) * 1000, (y + .5) * 1000) for _, x, y in keys]
    ordinals = [date.fromisoformat(k[0]).toordinal() for k in keys]
    for i in range(len(keys)):
        for j in range(i - 1, -1, -1):
            if ordinals[i] - ordinals[j] > gap_days:
                break
            _, _, meters = geod.inv(*centers[i], *centers[j])
            if meters <= distance_km * 1000:
                parent[find(i)] = find(j)
    components = defaultdict(list)
    for i, key in enumerate(keys):
        components[find(i)].append(key)
    groups = []
    for component in components.values():
        records = [r for key in component for r in nodes[key]]
        dates = sorted({key[0] for key in component})
        identity = digest(sorted(r["detection_id"] for r in records))[:12]
        groups.append({"id": f"candidate-{identity}", "first_utc": min(r["acquisition_utc"] for r in records),
                       "last_utc": max(r["acquisition_utc"] for r in records), "days": len(dates),
                       "cell_days": len(component), "raw_pixels": len(records),
                       "sources": sorted({r["source_id"] for r in records}),
                       "centroid": [sum(r["lon"] for r in records) / len(records), sum(r["lat"] for r in records) / len(records)],
                       "detection_ids": sorted(r["detection_id"] for r in records),
                       "points": [{"date": d, "grid_x": x, "grid_y": y,
                                   "coordinates": list(FROM_GRID.transform((x + .5) * 1000, (y + .5) * 1000))}
                                  for d, x, y in component]})
    groups.sort(key=lambda g: (g["first_utc"], g["id"]))
    return {"count": len(groups), "groups": groups, "distance_km": distance_km, "gap_days": gap_days,
            "method": "Connected components of daily detection cells; geodesic center distance and UTC-date gap.",
            "note": "Candidates are connected samples, not confirmed incidents. Chaining can merge separate events; gaps can split one event. IDs change when membership changes."}


def validate_mask(mask, config, start, cutoff):
    if not isinstance(mask, dict) or mask.get("format") != "fireatlas-coverage-v1":
        raise ValueError("coverage format must be fireatlas-coverage-v1")
    if mask.get("grid") != GRID_VERSION or mask.get("bbox") != list(config["bbox"]):
        raise ValueError("coverage grid and bbox must exactly match this study")
    if mask.get("start_date") != start.isoformat() or mask.get("end_date") != cutoff.isoformat():
        raise ValueError("coverage dates must exactly match the study start and cutoff")
    if type(mask.get("synthetic")) is not bool:
        raise ValueError("coverage must declare synthetic as true or false")
    if not isinstance(mask.get("provenance"), str) or not mask["provenance"].strip() or len(mask["provenance"]) > 2000:
        raise ValueError("coverage requires a provenance description (up to 2000 characters)")
    if not isinstance(mask.get("method"), str) or not mask["method"].strip() or len(mask["method"]) > 2000:
        raise ValueError("coverage requires a mask derivation method")
    cells = mask.get("cells")
    if not isinstance(cells, list) or not 1 <= len(cells) <= MAX_MASK_ROWS:
        raise ValueError("coverage requires 1–20,000 source/cell/day rows")
    statuses = {}
    w, s, e, n = config["bbox"]
    west, south = TO_GRID.transform(w, s)
    east, north = TO_GRID.transform(e, n)
    for cell in cells:
        if not isinstance(cell, dict) or cell.get("source_id") not in SOURCES:
            raise ValueError("coverage source must be MODIS_SP or VIIRS_SNPP_SP")
        x, y = cell.get("grid_x"), cell.get("grid_y")
        if type(x) is not int or type(y) is not int:
            raise ValueError("coverage grid_x and grid_y must be integers")
        if not (x * 1000 < east and (x + 1) * 1000 > west and y * 1000 < north and (y + 1) * 1000 > south):
            raise ValueError("coverage cell does not intersect the AOI")
        try:
            day = date.fromisoformat(cell.get("date", ""))
        except (TypeError, ValueError):
            raise ValueError("coverage date must be YYYY-MM-DD") from None
        if not start <= day <= cutoff:
            raise ValueError("coverage row outside study dates")
        status = cell.get("status")
        if status not in ("observed", "cloud", "no_pass", "unknown"):
            raise ValueError("coverage status must be observed, cloud, no_pass or unknown")
        key = (cell["source_id"], day.isoformat(), x, y)
        if key in statuses:
            raise ValueError("duplicate coverage source/cell/day")
        statuses[key] = status
    return statuses


def coverage(rows, mask, config, start, cutoff, complete):
    if mask is None:
        return {"status": "unavailable", "sources": [], "note": "Import explicit observation-mask cell-days to calculate exposure. FIRMS detections alone cannot supply the denominator."}
    statuses = validate_mask(mask, config, start, cutoff)
    demo = any(r["demo"] for r in rows)
    if rows and mask["synthetic"] != demo:
        raise ValueError("synthetic coverage cannot be mixed with authentic detections, or vice versa")
    output = []
    for source in SOURCES:
        detected = {(r["acquisition_utc"][:10], r["grid_x"], r["grid_y"]) for r in rows if r["source_id"] == source}
        exposed = {(d, x, y) for (src, d, x, y), status in statuses.items() if src == source and status == "observed"}
        matched = detected & exposed
        conflicts = [cell for cell in detected if (source, *cell) in statuses and statuses[(source, *cell)] != "observed"]
        missing = [cell for cell in detected if (source, *cell) not in statuses]
        if conflicts:
            raise ValueError(f"{source}: a detected cell-day is marked cloud, no_pass or unknown; reconcile the mask with the detections")
        status = "available" if exposed and complete[source] else "no_observed_exposure" if not exposed else "incomplete_export"
        output.append({"source_id": source, "status": status, "observed_cell_days": len(exposed),
                       "detected_in_mask": len(matched), "detections_without_mask": len(missing),
                       "per_100_observed_cell_days": 100 * len(matched) / len(exposed) if status == "available" else None,
                       "mask_counts": dict(Counter(v for (src, *_), v in statuses.items() if src == source))})
    return {"status": "synthetic" if mask["synthetic"] else "user_supplied_unvalidated", "sources": output,
            "sha256": digest(mask), "provenance": mask["provenance"], "method": mask["method"],
            "note": "Rates apply only to supplied observed cell-days, not the full AOI. Missing mask rows remain unknown. No joint exposure is inferred."}


def report(db, *, year=2015, month=7, bbox=(-122, 39, -120, 41), as_of=None, distance_km=2, gap_days=1, mask=None):
    config, start, cutoff = context(year, month, bbox, as_of, distance_km, gap_days)
    rows = load_records(db, config, start, cutoff)
    complete = {source: _complete_month(db, start.isoformat()[:7], (source,), config["bbox"]) for source in SOURCES}
    batches = db.execute("""SELECT DISTINCT b.source_id,b.file_sha256,b.source_uri,b.demo FROM batches b
        JOIN export_windows w ON w.batch_id=b.id WHERE w.month=? AND w.source_id IN (?,?)
        AND w.west<=? AND w.south<=? AND w.east>=? AND w.north>=?""",
        (start.isoformat()[:7], *SOURCES, *config["bbox"])).fetchall()
    provenance = {(r["source_id"], r["file_sha256"]): {k: r[k] for k in ("source_id", "file_sha256", "source_uri", "demo")} for r in rows}
    for row in batches:
        provenance[(row["source_id"], row["file_sha256"])] = dict(row)
    demo_flags = {bool(r["demo"]) for r in provenance.values()}
    if len(demo_flags) > 1:
        raise ValueError("research selection mixes synthetic and authentic data; use a dedicated database or AOI")
    if mask is not None and isinstance(mask, dict) and demo_flags and mask.get("synthetic") != (True in demo_flags):
        raise ValueError("coverage and source exports must use the same synthetic/authentic data class")
    result = {"method_version": METHOD, "grid": GRID_VERSION, "config": config,
              "sources": list(SOURCES), "demo_data": True in demo_flags,
              "data_status": "synthetic" if True in demo_flags else "imported" if provenance else "empty",
              "raw_pixels": len(rows), "complete_exports": complete,
              "overlap": overlap(rows, start, cutoff, complete),
              "candidates": candidates(rows, config["distance_km"], config["gap_days"]),
              "coverage": coverage(rows, mask, config, start, cutoff, complete),
              "provenance": sorted(provenance.values(), key=lambda p: (p["source_id"], p["file_sha256"])),
              "temporal_scope": "Retrospective acquisition-date cutoff. Publication/processing histories are not reconstructed; this is not a causal incident replay.",
              "gates": {"calibration": "Requires matched overpasses, observation masks, reference labels and independent holdout validation.",
                        "radar": "Requires co-registered SAR before/after scenes, quality masks and a dated optical cross-check.",
                        "spread": "Requires a validated regional fuel/terrain model, weather ensemble and held-out arrival observations."}}
    from .presentation import PREFIX, provenance as presentation_provenance
    if result["demo_data"] and any(p["source_uri"].startswith(PREFIX) for p in result["provenance"]):
        result["presentation"] = presentation_provenance()
    result["report_id"] = digest(result)
    return result


def coverage_example(db, **kwargs):
    config, start, cutoff = context(**kwargs)
    rows = load_records(db, config, start, cutoff)
    if not rows or not all(r["demo"] for r in rows):
        raise ValueError("the synthetic mask example requires a selection containing only synthetic detections")
    cells = sorted({(r["grid_x"], r["grid_y"]) for r in rows})
    if len(cells) * 2 * ((cutoff - start).days + 1) > MAX_MASK_ROWS:
        raise ValueError("synthetic mask example exceeds 20,000 rows; narrow the selection")
    return {"format": "fireatlas-coverage-v1", "grid": GRID_VERSION, "bbox": list(config["bbox"]),
            "start_date": start.isoformat(), "end_date": cutoff.isoformat(), "synthetic": True,
            "provenance": "synthetic://fireatlas/coverage-example-v1",
            "method": "Demonstration only: assume every selected detection cell has daily observation coverage from both sources. This fabricated denominator cannot calibrate sensors.",
            "cells": [{"source_id": source, "date": (start + timedelta(days=offset)).isoformat(),
                       "grid_x": x, "grid_y": y, "status": "observed"}
                      for offset in range((cutoff - start).days + 1) for source in SOURCES for x, y in cells]}
