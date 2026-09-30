"""Reproducible, descriptive audit of a selected satellite calendar month.

This compares source records on the existing UTC/1 km centroid grid.  It does
not estimate relative detection probability or infer fire area or severity.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from .core import GRID_VERSION, SERIES, SOURCES, calendar, calendar_row_included, validate_bbox


def month_audit(db, *, year: int, month: int, series: str,
                bbox: tuple[float, float, float, float]) -> dict:
    if series not in SERIES or not 2000 <= year <= 2100 or not 1 <= month <= 12:
        raise ValueError("invalid year, month, or series")
    validate_bbox(bbox)
    summary = calendar(db, bbox=bbox, year=year, series=series)
    selected = summary["monthly"][month - 1]
    stamp = f"{year}-{month:02d}"
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    sources = SERIES[series]
    marks = {source: defaultdict(set) for source in sources}
    raw = Counter()
    raw_by_day = Counter()
    versions = {source: set() for source in sources}
    placeholders = ",".join("?" for _ in sources)
    records = db.execute(f"""
        SELECT source_id, acquisition_utc, grid_x, grid_y, product_version, raw_json
        FROM observations
        WHERE source_id IN ({placeholders}) AND acquisition_utc>=? AND acquisition_utc<?
          AND lon>=? AND lon<=? AND lat>=? AND lat<=?
    """, (*sources, start.isoformat(), end.isoformat(), bbox[0], bbox[2], bbox[1], bbox[3]))
    for row in records:
        source = row["source_id"]
        versions[source].add(row["product_version"])
        if not calendar_row_included(row["raw_json"]):
            continue
        raw[source] += 1
        stamp_day = row["acquisition_utc"][:10]
        raw_by_day[(source, stamp_day)] += 1
        marks[source][stamp_day].add((row["grid_x"], row["grid_y"]))

    rows = []
    day = start
    while day < end:
        stamp_day = day.isoformat()
        source_cells = {source: marks[source][stamp_day] for source in sources}
        union = set().union(*source_cells.values())
        overlap = len(set.intersection(*source_cells.values())) if len(sources) == 2 else None
        rows.append({"date_utc": stamp_day, "raw_pixels_by_source": {
            source: raw_by_day[(source, stamp_day)] for source in sources},
            "cell_days_by_source": {source: len(cells) for source, cells in source_cells.items()},
            "joint_cell_days": len(union) if selected["export_window_complete"] else None,
            "partial_joint_cell_days": None if selected["export_window_complete"] else len(union),
            "co_detected_cell_days": overlap,
            "export_window_complete": bool(selected["export_window_complete"]),
            "satellite_observation_coverage": "unknown"})
        day += timedelta(days=1)

    by_source = [{"source_id": source, "sensor": SOURCES[source][0],
                  "processing_level": SOURCES[source][1],
                  "raw_pixels": raw[source],
                  "detected_cell_days": sum(len(cells) for cells in marks[source].values()),
                  "product_versions": sorted(versions[source]),
                  "full_month_export": bool(db.execute("""
                      SELECT 1 FROM export_windows WHERE source_id=? AND month=?
                        AND west<=? AND south<=? AND east>=? AND north>=? LIMIT 1
                  """, (source, stamp, *bbox)).fetchone())}
                 for source in sources]
    baseline_versions = {}
    for prior in selected["baseline_years"]:
        prior_month = f"{prior}-{month:02d}"
        prior_rows = db.execute(f"""
            SELECT DISTINCT source_id,product_version FROM observations
            WHERE source_id IN ({placeholders}) AND acquisition_utc>=? AND acquisition_utc<?
              AND lon>=? AND lon<=? AND lat>=? AND lat<=?
        """, (*sources, prior_month + "-01",
              date(prior + (month == 12), month % 12 + 1, 1).isoformat(),
              bbox[0], bbox[2], bbox[1], bbox[3]))
        by_prior_source = {source: set() for source in sources}
        for row in prior_rows:
            by_prior_source[row["source_id"]].add(row["product_version"])
        baseline_versions[str(prior)] = {source: sorted(by_prior_source[source]) for source in sources}
    if not baseline_versions:
        baseline_version_status = "no-qualifying-baseline-years"
    elif any(not values[source] for values in baseline_versions.values() for source in sources):
        baseline_version_status = "unknown-where-source-has-no-detections"
    elif all(values[source] == sorted(versions[source])
             for values in baseline_versions.values() for source in sources):
        baseline_version_status = "same-observed-product-versions"
    else:
        baseline_version_status = "mixed-product-versions-across-years"
    joint = sum(row["joint_cell_days"] or 0 for row in rows) if selected["export_window_complete"] else None
    partial_joint = sum(row["partial_joint_cell_days"] or 0 for row in rows) if not selected["export_window_complete"] else None
    both = sum(row["co_detected_cell_days"] or 0 for row in rows) if len(sources) == 2 else None
    standard_pair = sources == SERIES["joint"]
    complete_pair = standard_pair and all(item["full_month_export"] for item in by_source)
    if not standard_pair:
        status = "outside-standard-modis-viirs-pair"
    elif not complete_pair:
        status = "missing-complete-source-export"
    elif any(len(item["product_versions"]) > 1 for item in by_source):
        status = "mixed-product-versions"
    elif not all(item["raw_pixels"] for item in by_source):
        status = "complete-export-with-zero-detections-in-one-source"
    else:
        status = "descriptive-pair-available"
    return {
        "schema": "fireatlas-harmonization-audit-v1",
        "status": status,
        "data_class": "synthetic" if summary["demo_data"] else "authentic-imported",
        "year": year, "month": month, "series": series, "bbox": list(bbox),
        "calendar_timezone": "UTC", "grid": GRID_VERSION,
        "sources": by_source,
        "raw_pixels_total": sum(raw.values()),
        "detected_cell_days": joint,
        "partial_detected_cell_days": partial_joint,
        "co_detected_cell_days": both,
        "days": rows,
        "baseline_median": selected["baseline_median"],
        "baseline_years": selected["baseline_years"],
        "baseline_product_versions": baseline_versions,
        "baseline_version_status": baseline_version_status,
        "provenance": summary["provenance"],
        "limits": [
            "Common-grid centroid grouping removes repeated detections within a UTC cell-day but does not calibrate sensor sensitivity.",
            "Same-cell same-day co-detection does not establish matched overpasses or the same physical fire.",
            "A complete CSV export does not prove a clear satellite pass; observation and cloud coverage are unknown.",
            "Hotspot centroids are not a fire perimeter, burned area, or proof of no fire on zero-detection days.",
            "Historical baselines are only within the selected source cohort; a MODIS-only era and joint MODIS/VIIRS era are not directly compared.",
            "Even within a source cohort, different product versions across years can affect a historical comparison.",
        ],
    }
