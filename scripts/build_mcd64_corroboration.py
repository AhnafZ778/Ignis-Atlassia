"""Build a compact, hash-bound MCD64A1 corroboration report.

The report is deliberately a lagged burned-area check. It never merges burned
area into the active-fire calendar and never treats an empty Burn Date raster
as evidence that a satellite passed or that no fire occurred.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from itertools import zip_longest
import calendar
from pathlib import Path

from fireatlas.core import GRID_METERS, TO_GRID, calendar_row_included

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "fireatlas.sqlite3"
QA_GUIDE_URL = "https://lpdaac.usgs.gov/documents/1006/MCD64_User_Guide_V61.pdf"
QA_SPECIAL_CONDITIONS = {
    0: "none-or-not-applicable",
    1: "too-few-valid-observations",
    2: "low-separability-or-too-few-training-samples",
    3: "burn-date-at-time-series-limit",
    4: "water-contamination",
    5: "persistent-hotspot",
    6: "reserved",
    7: "reserved",
}

CASES = {
    "park-2024": {
        "region": "norcal", "bbox": (-122.0, 39.5, -121.3, 40.5),
        "active_start": "2024-07-17", "active_end": "2024-07-31",
        "months": [("2024-07", "Win03", "A2024183"), ("2024-08", "Win03", "A2024214")],
    },
    "grove-2025": {
        "region": "norcal", "bbox": (-121.55, 39.25, -121.28, 39.48),
        "active_start": "2025-07-04", "active_end": "2025-07-06",
        "months": [("2025-07", "Win03", "A2025182"), ("2025-08", "Win03", "A2025213")],
    },
}

REGIONAL_CHECKS = {
    "punjab-haryana": {
        "bbox": (73.8, 29.5, 77.6, 32.6),
        "months": [("2024-07", "Win18", "A2024183"), ("2025-07", "Win18", "A2025182")],
    }
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def raster_counts(path: Path, bbox: tuple[float, float, float, float]) -> dict:
    west, south, east, north = bbox
    command = [
        "gdal_translate", "-q", "-projwin", str(west), str(north), str(east), str(south),
        "-of", "XYZ", str(path), "/vsistdout/",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True, bufsize=1)
    counts = Counter()
    for line in process.stdout or ():
        fields = line.split()
        if len(fields) == 3:
            try:
                counts[int(float(fields[2]))] += 1
            except ValueError:
                continue
    if process.wait() != 0:
        raise RuntimeError(f"gdal_translate failed for {path}")
    valid = {str(day): count for day, count in sorted(counts.items()) if 1 <= day <= 366}
    return {
        "pixel_count": sum(counts.values()),
        "burned_pixels": sum(valid.values()),
        "burn_date_counts": valid,
        "unburned_pixels": counts.get(0, 0),
        "unmapped_pixels": counts.get(-1, 0),
        "water_or_invalid_pixels": counts.get(-2, 0),
        "other_values": {str(value): count for value, count in sorted(counts.items())
                         if value not in {-2, -1, 0} and not 1 <= value <= 366},
        "burn_date_min": min((int(day) for day in valid), default=None),
        "burn_date_max": max((int(day) for day in valid), default=None),
    }


def _xyz_process(path: Path, bbox: tuple[float, float, float, float]):
    west, south, east, north = bbox
    command = [
        "gdal_translate", "-q", "-projwin", str(west), str(north), str(east), str(south),
        "-of", "XYZ", str(path), "/vsistdout/",
    ]
    return subprocess.Popen(command, stdout=subprocess.PIPE, text=True, bufsize=1)


def decode_qa_value(value: int) -> dict:
    """Decode the documented MCD64A1 Collection 6.1 QA byte."""
    if not 0 <= value <= 255:
        raise ValueError("MCD64A1 QA values must be unsigned bytes")
    special_code = (value >> 5) & 0b111
    return {
        "land": bool(value & 0b00000001),
        "valid_data": bool(value & 0b00000010),
        "mapping_period_shortened": bool(value & 0b00000100),
        "contextual_relabeling": bool(value & 0b00001000),
        "spare_bit_4_set": bool(value & 0b00010000),
        "special_condition_code": special_code,
        "special_condition": QA_SPECIAL_CONDITIONS[special_code],
    }


def classify_burn_date_pixel(burn_date: int, qa_flags: dict) -> tuple[str, str | None]:
    """Return the supported QA disposition and an exclusive exclusion reason."""
    if 1 <= burn_date <= 366:
        if not qa_flags["land"] and not qa_flags["valid_data"]:
            return "excluded-burned", "qa-not-land-and-insufficient-data"
        if not qa_flags["land"]:
            return "excluded-burned", "qa-not-land"
        if not qa_flags["valid_data"]:
            return "excluded-burned", "qa-insufficient-valid-data"
        return "qa-supported-burned", None
    if burn_date == 0:
        if not qa_flags["land"]:
            return "excluded-unburned", "qa-not-land"
        if not qa_flags["valid_data"]:
            return "excluded-unburned", "qa-insufficient-valid-data"
        if qa_flags["mapping_period_shortened"]:
            return "excluded-unburned", "shortened-mapping-period"
        if qa_flags["contextual_relabeling"]:
            return "excluded-unburned", "contextual-relabeling"
        if qa_flags["special_condition_code"]:
            return "excluded-unburned", f"special-condition-{qa_flags['special_condition_code']}"
        return "qa-supported-full-period-unburned", None
    return "not-burned-or-unburned", None


def qa_value_cross_tab(burn_path: Path, qa_path: Path,
                       bbox: tuple[float, float, float, float],
                       year: int | None = None) -> tuple[dict, dict[str, set[tuple[int, int]]]]:
    """Decode QA bits, apply the land/valid-data test, and retain a raw cross-tab."""
    year = year or int(burn_path.parent.name[:4])
    burn_process = _xyz_process(burn_path, bbox)
    qa_process = _xyz_process(qa_path, bbox)
    qa_values, categories = Counter(), defaultdict(Counter)
    bit_counts = Counter()
    special_conditions = Counter()
    disposition_counts = Counter()
    burned_exclusions, unburned_exclusions = Counter(), Counter()
    burned_flags = Counter()
    burn_date_counts, supported_doy_counts = Counter(), Counter()
    supported_burned_cells_by_doy = defaultdict(set)
    strict_unburned = pixel_count = coordinate_mismatches = unpaired_pixels = unparsed_values = 0
    outside_bbox_centers = 0
    west, south, east, north = bbox
    try:
        burn_stream = burn_process.stdout or ()
        qa_stream = qa_process.stdout or ()
        for burn_line, qa_line in zip_longest(burn_stream, qa_stream):
            if burn_line is None or qa_line is None:
                unpaired_pixels += 1
                continue
            burn_fields, qa_fields = burn_line.split(), qa_line.split()
            if len(burn_fields) != 3 or len(qa_fields) != 3:
                unparsed_values += 1
                continue
            try:
                burn_xy = tuple(float(value) for value in burn_fields[:2])
                qa_xy = tuple(float(value) for value in qa_fields[:2])
                burn_value, qa_value = int(float(burn_fields[2])), int(float(qa_fields[2]))
            except ValueError:
                unparsed_values += 1
                continue
            if any(abs(a - b) > 1e-8 for a, b in zip(burn_xy, qa_xy)):
                coordinate_mismatches += 1
                continue
            lon, lat = burn_xy
            if not (west <= lon <= east and south <= lat <= north):
                outside_bbox_centers += 1
                continue
            pixel_count += 1
            qa_key = str(qa_value)
            qa_values[qa_key] += 1
            flags = decode_qa_value(qa_value)
            for key in ("land", "valid_data", "mapping_period_shortened",
                        "contextual_relabeling", "spare_bit_4_set"):
                if flags[key]:
                    bit_counts[key] += 1
            if burn_value == 0:
                special_conditions[str(flags["special_condition_code"])] += 1
            disposition, reason = classify_burn_date_pixel(burn_value, flags)
            disposition_counts[disposition] += 1
            if reason:
                (burned_exclusions if disposition == "excluded-burned" else
                 unburned_exclusions)[reason] += 1
            if 1 <= burn_value <= 366:
                burn_date_counts[burn_value] += 1
                if disposition == "qa-supported-burned":
                    supported_doy_counts[burn_value] += 1
                    grid_x, grid_y = TO_GRID.transform(lon, lat)
                    supported_burned_cells_by_doy[burn_value].add(
                        (int(grid_x // GRID_METERS), int(grid_y // GRID_METERS)))
                    for flag in ("mapping_period_shortened", "contextual_relabeling"):
                        if flags[flag]:
                            burned_flags[flag] += 1
            elif burn_value == 0 and disposition == "qa-supported-full-period-unburned":
                strict_unburned += 1
            if 1 <= burn_value <= 366:
                category = "burn_date_1_to_366"
            elif burn_value == 0:
                category = "burn_date_0"
            elif burn_value == -1:
                category = "burn_date_minus_1"
            elif burn_value == -2:
                category = "burn_date_minus_2"
            else:
                category = "other_burn_date_value"
            categories[category][qa_key] += 1
    finally:
        burn_code = burn_process.wait()
        qa_code = qa_process.wait()
    if burn_code != 0 or qa_code != 0:
        raise RuntimeError(f"gdal_translate failed for paired Burn Date / QA crop: {burn_path.name}")
    raw_burned_pixels = sum(count for day, count in burn_date_counts.items())
    supported_burned_pixels = sum(supported_doy_counts.values())
    report = {
        "status": "decoded-and-filtered-using-collection-6.1-guide",
        "pixel_count": pixel_count,
        "qa_raw_value_counts": dict(sorted(qa_values.items(), key=lambda item: int(item[0]))),
        "burn_date_category_by_qa_raw_value": {
            category: dict(sorted(counts.items(), key=lambda item: int(item[0])))
            for category, counts in sorted(categories.items())
        },
        "burned_pixels_by_qa_raw_value": dict(sorted(
            categories["burn_date_1_to_366"].items(), key=lambda item: int(item[0]))),
        "decoded_qa_bit_counts": dict(sorted(bit_counts.items())),
        "unburned_special_condition_code_counts": dict(sorted(special_conditions.items(), key=lambda item: int(item[0]))),
        "burn_date_positive_pixels": raw_burned_pixels,
        "qa_disposition_pixel_counts": dict(sorted(disposition_counts.items())),
        "qa_supported_burned_pixels": supported_burned_pixels,
        "qa_excluded_burned_pixels": raw_burned_pixels - supported_burned_pixels,
        "qa_excluded_burned_pixels_by_reason": dict(sorted(burned_exclusions.items())),
        "qa_supported_burned_pixels_with_flags": dict(sorted(burned_flags.items())),
        "qa_supported_burn_date_min": min(supported_doy_counts, default=None),
        "qa_supported_burn_date_max": max(supported_doy_counts, default=None),
        "burn_date_zero_pixels": sum(categories["burn_date_0"].values()),
        "qa_supported_full_period_unburned_pixels": strict_unburned,
        "qa_excluded_burn_date_zero_pixels_by_reason": dict(sorted(unburned_exclusions.items())),
        "qa_supported_burned_doy_counts": {str(day): count for day, count in sorted(supported_doy_counts.items())},
        "burn_date_positive_doy_counts": {str(day): count for day, count in sorted(burn_date_counts.items())},
        "coordinate_mismatches": coordinate_mismatches,
        "unpaired_pixels": unpaired_pixels,
        "unparsed_values": unparsed_values,
        "outside_bbox_pixel_centers": outside_bbox_centers,
        "filter_applied": True,
        "burned_pixel_filter": "retain Burn Date 1–366 only when QA bit 0 (land) and bit 1 (valid data) are both set; shortened-period and contextual-relabel flags remain counted and visible",
        "full_period_unburned_filter": "count Burn Date 0 only when land and valid-data bits are set, the mapping period is not shortened, contextual relabeling is not set, and special-condition code is 0",
        "source_guide_url": QA_GUIDE_URL,
        "interpretation_limit": "The conservative unburned subset describes mapped MCD64A1 output only; it is not an overpass, clear-sky, or fire-free mask.",
    }
    return report, {str(day): cells for day, cells in sorted(supported_burned_cells_by_doy.items())}


def active_fire_details(db: Path, bbox: tuple[float, float, float, float],
                        start: str, end: str) -> tuple[dict, dict[str, dict[str, set[tuple[int, int]]]]]:
    west, south, east, north = bbox
    end_exclusive = (date.fromisoformat(end) + timedelta(days=1)).isoformat() + "T00:00:00Z"
    with sqlite3.connect(db) as connection:
        rows = connection.execute(
            """SELECT o.source_id,o.acquisition_utc,o.grid_x,o.grid_y,o.raw_json
               FROM observations o JOIN batches b ON b.id=o.batch_id
               WHERE b.demo=0 AND o.source_id IN ('MODIS_SP','VIIRS_SNPP_SP')
                 AND o.acquisition_utc>=? AND o.acquisition_utc<?
                 AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=?
               ORDER BY o.source_id,o.acquisition_utc""",
            (start + "T00:00:00Z", end_exclusive, west, east, south, north),
        ).fetchall()
    rows_by_source, cells_by_source = Counter(), defaultdict(set)
    cells_by_date_source = defaultdict(set)
    excluded_types = defaultdict(Counter)
    for source, acquired, grid_x, grid_y, raw_json in rows:
        try:
            raw = json.loads(raw_json)
        except (TypeError, json.JSONDecodeError):
            raw = None
        if not calendar_row_included(raw):
            code = str((raw or {}).get("type") or "missing") if isinstance(raw, dict) else "unparseable"
            excluded_types[source][code] += 1
            continue
        rows_by_source[source] += 1
        cells_by_source[source].add((grid_x, grid_y))
        cells_by_date_source[(acquired[:10], source)].add((grid_x, grid_y))
    summary = {
        "utc_start": start, "utc_end": end,
        "detection_filter": "FIRMS type 0 or missing, matching the harmonized calendar",
        "rows_by_source": dict(sorted(rows_by_source.items())),
        "unique_common_grid_cells_by_source": {
            source: len(cells) for source, cells in sorted(cells_by_source.items())},
        "excluded_type_counts": {source: dict(sorted(counts.items()))
                                 for source, counts in sorted(excluded_types.items())},
    }
    by_date = defaultdict(dict)
    for (stamp, source), cells in cells_by_date_source.items():
        by_date[stamp][source] = cells
    return summary, by_date


def active_fire_summary(db: Path, bbox: tuple[float, float, float, float], start: str, end: str) -> dict:
    """Return a concise source summary using the harmonized calendar filter."""
    return active_fire_details(db, bbox, start, end)[0]


def same_day_spatial_comparison(
        year: int,
        burned_cells_by_doy: dict[str, set[tuple[int, int]]],
        active_cells_by_date: dict[str, dict[str, set[tuple[int, int]]]]) -> dict:
    """Compare exact UTC burn dates on the common centroid-assigned 1 km grid."""
    day_results = []
    shared_cell_days = Counter()
    dates_with_shared_cells = Counter()
    unmatchable_doys = []
    days_in_year = 366 if calendar.isleap(year) else 365
    sources = ("MODIS_SP", "VIIRS_SNPP_SP")
    for doy_text, burned_cells in sorted(burned_cells_by_doy.items(), key=lambda item: int(item[0])):
        doy = int(doy_text)
        if not 1 <= doy <= days_in_year:
            unmatchable_doys.append(doy)
            continue
        burn_date = (date(year, 1, 1) + timedelta(days=doy - 1)).isoformat()
        active_for_date = active_cells_by_date.get(burn_date, {})
        overlaps = {}
        for source in sources:
            shared = burned_cells & active_for_date.get(source, set())
            overlaps[source] = len(shared)
            shared_cell_days[source] += len(shared)
            dates_with_shared_cells[source] += bool(shared)
        day_results.append({
            "burn_date_utc": burn_date,
            "burn_day_of_year": doy,
            "qa_supported_mcd64_1km_cells": len(burned_cells),
            "active_fire_cells_by_source": {
                source: len(active_for_date.get(source, set())) for source in sources},
            "shared_1km_cells_by_source": overlaps,
        })
    return {
        "method": "Same UTC date; QA-supported 500 m MCD64A1 cell centers and FIRMS detection centroids assigned to the common 1 km EPSG:6933 grid.",
        "shared_1km_cell_days_by_source": dict(sorted(shared_cell_days.items())),
        "burn_dates_with_any_shared_1km_cell_by_source": dict(sorted(dates_with_shared_cells.items())),
        "burn_days_without_a_calendar_date": unmatchable_doys,
        "per_burn_date": day_results,
        "interpretation_limit": (
            "Descriptive same-date spatial co-location only. A shared cell is not pixel-level agreement and is not independent validation; "
            "MCD64A1 uses cumulative MODIS active-fire maps to guide training-sample selection and prior probabilities. "
            "No same-day co-location does not establish absence of fire because overpass timing, cloud, and detection conditions differ."),
        "source_guide_url": QA_GUIDE_URL,
    }


def one_check(*, label: str, bbox: tuple[float, float, float, float], month: str,
              window: str, doy: str, db: Path, active_fire: dict | None = None,
              active_cells_by_date: dict[str, dict[str, set[tuple[int, int]]]] | None = None) -> dict:
    folder = ROOT / "NASA_data" / "mcd64a1" / month
    path = folder / f"MCD64monthly.{doy}.{window}.061.burndate.tif"
    qa_path = folder / f"MCD64monthly.{doy}.{window}.061.ba_qa.tif"
    if not path.exists():
        raise FileNotFoundError(path)
    if not qa_path.exists():
        raise FileNotFoundError(qa_path)
    qa, burned_cells_by_doy = qa_value_cross_tab(path, qa_path, bbox, year=int(month[:4]))
    return {
        "label": label, "month": month, "product": "MCD64A1", "collection": "6.1",
        "window": window, "source_filename": path.name, "source_sha256": sha256(path),
        "qa_source_filename": qa_path.name, "qa_source_sha256": sha256(qa_path),
        "bbox": list(bbox), "burn_date": raster_counts(path, bbox),
        "qa": qa,
        "same_day_spatial_comparison": same_day_spatial_comparison(
            int(month[:4]), burned_cells_by_doy, active_cells_by_date or {}),
        "active_fire": active_fire or {},
    }


def _raster_bbox(path: Path) -> list[float]:
    info = json.loads(subprocess.check_output(["gdalinfo", "-json", str(path)], text=True))
    corners = info["cornerCoordinates"]
    points = [corners[key] for key in ("upperLeft", "lowerLeft", "lowerRight", "upperRight")]
    return [min(point[0] for point in points), min(point[1] for point in points),
            max(point[0] for point in points), max(point[1] for point in points)]


def _bbox_overlaps(left: list[float] | tuple[float, ...],
                   right: list[float] | tuple[float, ...]) -> bool:
    return left[0] < right[2] and right[0] < left[2] and left[1] < right[3] and right[1] < left[3]


def source_inventory() -> list[dict]:
    """Account for every supplied raster pair against the current case areas."""
    case_specs = {**CASES, **REGIONAL_CHECKS}
    check_lookup = defaultdict(list)
    for label, spec in case_specs.items():
        for month, window, doy in spec["months"]:
            check_lookup[(month, window, doy)].append(label)
    footprints = {label: spec["bbox"] for label, spec in case_specs.items()}
    inventory = []
    for burn_path in sorted((ROOT / "NASA_data" / "mcd64a1").glob("*/*.burndate.tif")):
        fields = burn_path.name.split(".")
        month, doy, window = burn_path.parent.name, fields[1], fields[2]
        qa_path = burn_path.with_name(burn_path.name.replace(".burndate.tif", ".ba_qa.tif"))
        if not qa_path.is_file():
            inventory.append({"month": month, "window": window, "burn_date_file": burn_path.name,
                              "burn_date_sha256": sha256(burn_path), "qa_file": None,
                              "status": "missing-qa-companion"})
            continue
        key = (month, window, doy)
        used_by = check_lookup.get(key, [])
        coverage = _raster_bbox(burn_path)
        overlapping_areas = [label for label, bbox in footprints.items()
                             if _bbox_overlaps(coverage, bbox)]
        if used_by:
            status = "used-in-dated-corroboration"
            reason = "This raster pair is clipped and summarized for the listed regional case-month check."
        elif not overlapping_areas:
            status = "outside-current-demo-footprints"
            reason = "The raster footprint does not intersect either current demo area, so it cannot support those dated case checks."
        else:
            status = "not-selected-for-current-case-months"
            reason = "The raster overlaps a demo area but has no matching dated case-month check in the current evidence set."
        inventory.append({
            "month": month, "window": window, "doy_token": doy,
            "burn_date_file": burn_path.name, "burn_date_sha256": sha256(burn_path),
            "qa_file": qa_path.name, "qa_sha256": sha256(qa_path),
            "raster_bbox_wsen": coverage, "demo_areas_overlapped": overlapping_areas,
            "status": status, "used_by_checks": used_by, "scope_reason": reason,
        })
    return inventory


def build(db: Path) -> dict:
    cases = {}
    for case_id, spec in CASES.items():
        checks = []
        for month, window, doy in spec["months"]:
            year, month_number = (int(part) for part in month.split("-"))
            start = f"{month}-01"
            end = f"{month}-{calendar.monthrange(year, month_number)[1]:02d}"
            active_summary, active_cells = active_fire_details(db, spec["bbox"], start, end)
            checks.append(one_check(label=case_id, bbox=spec["bbox"], month=month,
                                    window=window, doy=doy, db=db, active_fire=active_summary,
                                    active_cells_by_date=active_cells))
        cases[case_id] = {
            "region": spec["region"], "bbox": list(spec["bbox"]),
            "active_fire": active_fire_summary(db, spec["bbox"], spec["active_start"], spec["active_end"]),
            "checks": checks,
        }
    regional = {}
    for region, spec in REGIONAL_CHECKS.items():
        checks = []
        for month, window, doy in spec["months"]:
            year, month_number = (int(part) for part in month.split("-"))
            start = f"{month}-01"
            end = f"{month}-{calendar.monthrange(year, month_number)[1]:02d}"
            active_summary, active_cells = active_fire_details(db, spec["bbox"], start, end)
            checks.append(one_check(label=region, bbox=spec["bbox"], month=month,
                                    window=window, doy=doy, db=db, active_fire=active_summary,
                                    active_cells_by_date=active_cells))
        regional[region] = {"bbox": list(spec["bbox"]), "checks": checks}
    inventory = source_inventory()
    used_pairs = sum(item["status"] == "used-in-dated-corroboration" for item in inventory)
    out_of_scope_pairs = sum(item["status"] == "outside-current-demo-footprints" for item in inventory)
    return {
        "schema": "fireatlas-mcd64-corroboration-v2",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "loaded",
        "product": "MCD64A1 Collection 6.1 monthly burned area",
        "product_url": "https://doi.org/10.5067/MODIS/MCD64A1.061",
        "archive_url": "https://modis-fire.umd.edu/files/MODIS_C61_BA_User_Guide_1.1.pdf",
        "distribution": "University of Maryland fuoco SFTP; official guide section 4",
        "interpretation": "Lagged burned-area context only. Burn Date values 1–366 are mapped burned pixels; 0 is unburned, -1 unmapped, and -2 water/invalid. This is not active-fire truth, an overpass mask, cloud mask, or a fire perimeter.",
        "qa_interpretation": "QA bits are decoded using the official Collection 6.1 guide. Burn Date 1–366 pixels count as QA-supported burned only when land and valid-data bits are set. Burn Date 0 counts as full-period unburned only when land and valid-data are set, the mapping period is not shortened, contextual relabeling is not set, and the special-condition code is zero. Other categories remain separately counted; this is product QA support, not ground truth.",
        "qa_specification": {
            "guide_url": QA_GUIDE_URL,
            "bits": {
                "0": "1=land grid cell; 0=water grid cell",
                "1": "1=sufficient valid reflectance data; 0=insufficient",
                "2": "1=reliable mapping period is shorter than the full month",
                "3": "1=cell was relabeled during contextual relabeling",
                "4": "spare; guide states it is set to 0",
                "5-7": "special-condition code for unburned grid cells",
            },
            "special_condition_codes": {str(code): meaning for code, meaning in QA_SPECIAL_CONDITIONS.items()},
        },
        "same_day_comparison_interpretation": "A descriptive same-UTC-date spatial co-location on the common 1 km centroid-assigned grid; this is not pixel agreement and is not independent validation. MCD64A1 uses cumulative MODIS active-fire maps to guide training samples and prior probabilities. No co-location does not establish fire absence.",
        "dataset_accounting": {
            "raster_pair_count": len(inventory), "input_tiff_count": 2 * len(inventory),
            "used_pair_count": used_pairs, "outside_demo_pair_count": out_of_scope_pairs,
            "scope_note": "All supplied pairs are inventoried. Pairs outside the California and Punjab–Haryana case footprints remain available in the source archive but are not mixed into these case summaries.",
        },
        "source_inventory": inventory,
        "cases": cases,
        "regional_checks": regional,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--output", type=Path, default=ROOT / "fireatlas" / "samples" / "mcd64_corroboration.json")
    args = parser.parse_args()
    report = build(args.db)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "status": report["status"], "cases": list(report["cases"])}))


if __name__ == "__main__":
    main()
