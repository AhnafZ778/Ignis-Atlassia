"""Region-based harmonized calendar built from imported FIRMS records only."""

from __future__ import annotations

import calendar
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import median

from .aggregates import daily_aggregates
from .calibration import calibrate
from .regions import REGIONS

MODIS_ARCHIVE_START = date(2010, 7, 1)
MODIS_EARLIEST_SUPPORTED_HISTORY = date(2006, 7, 1)
SNPP_ARCHIVE_START = date(2012, 7, 1)
MCD64_REPORT = Path(__file__).resolve().parent / "samples" / "mcd64_corroboration.json"


def _mcd64_corroboration(region: str, year: int, month: int) -> dict:
    """Return only a hash-bound check that exists for this region/month."""
    base = {
        "product": "MCD64A1 Collection 6.1 burned area",
        "status": "not-loaded",
        "source_url": "https://doi.org/10.5067/MODIS/MCD64A1.061",
        "note": "No dated MCD64A1 check is bundled for this selection; active-fire detections remain the only displayed evidence.",
    }
    try:
        report = json.loads(MCD64_REPORT.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return base
    if report.get("schema") != "fireatlas-mcd64-corroboration-v1" or report.get("status") != "loaded":
        return base
    key = f"{year:04d}-{month:02d}"
    case_records = [item for item in report.get("cases", {}).values()
                    if item.get("region") == region]
    checks = [check for item in case_records for check in item.get("checks", [])]
    if not checks:
        checks = report.get("regional_checks", {}).get(region, {}).get("checks", [])
    selected = next((item for item in checks if item.get("month") == key), None)
    if selected is None:
        return base
    burned = selected.get("burn_date", {})
    active = selected.get("active_fire", {})
    return {
        **base,
        "status": "loaded",
        "month": key,
        "case_id": selected.get("label"),
        "bbox": selected.get("bbox"),
        "source_filename": selected.get("source_filename"),
        "source_sha256": selected.get("source_sha256"),
        "qa_source_filename": selected.get("qa_source_filename"),
        "qa_source_sha256": selected.get("qa_source_sha256"),
        "burned_pixels_in_bbox": burned.get("burned_pixels", 0),
        "burn_date_min": burned.get("burn_date_min"),
        "burn_date_max": burned.get("burn_date_max"),
        "active_fire_rows": active.get("rows_by_source", {}),
        "active_fire_cells": active.get("unique_common_grid_cells_by_source", {}),
        "review_status": "analytical-only-independent-review-pending",
        "note": "Lagged burned-area context for the selected month. Burn Date pixels are not active-fire truth, an overpass mask, a cloud mask, or a fire perimeter.",
    }


def _mcd64_checks_for_year(region: str, year: int) -> dict:
    """Keep dated checks available when a static annual export changes month."""
    checks = (_mcd64_corroboration(region, year, month) for month in range(1, 13))
    return {check["month"]: check for check in checks if check["status"] == "loaded"}


def _selected_modis_version(days: list[dict], year: int) -> str | None:
    counts = defaultdict(int)
    for item in days:
        if int(item["date_utc"][:4]) != year:
            continue
        source = item["sources"]["MODIS_SP"]
        versions = source["product_versions"]
        if source["export_complete"] and len(versions) == 1:
            counts[versions[0]] += 1
    return max(counts, key=lambda version: (counts[version], version)) if counts else None


def _percentile_rank(value: float, baseline: list[float]) -> tuple[float | None, int | None]:
    if not baseline:
        return None, None
    rank = 1 + sum(item < value for item in baseline)
    percentile = 100 * sum(item <= value for item in baseline) / len(baseline)
    return percentile, rank


def _ordinal(value: float) -> str:
    number = int(round(value))
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def _verdict(region_name: str, year: int, item: dict) -> str:
    label = date(year, int(item["month"][5:7]), 1).strftime("%B %Y")
    if item["value"] is None:
        partial_days = item.get("partial_detection_days", 0)
        if partial_days:
            modis = item.get("partial_modis_cell_days", 0)
            viirs = item.get("partial_viirs_cell_days", 0)
            return (f"{region_name}, {label}: partial archive rows show {modis:,} MODIS and "
                    f"{viirs:,} S-NPP source cell-days across {partial_days} UTC dates. "
                    "The full-month total is unknown; other dates are not zeros.")
        return (f"{region_name}, {label}: monthly activity is unknown because the imported "
                "source exports are incomplete; missing dates are not zeros.")
    if item["n_years"] < 10:
        return f"{region_name}, {label}: comparison not usable. Only {item['n_years']} comparable years."
    estimated_days = (item["outside_downloaded_snpp_period_days"]
                      + item["documented_gap_estimate_days"])
    pre = item["outside_downloaded_snpp_period_days"]
    outage = item["documented_gap_estimate_days"]
    estimate_note = (f" {estimated_days} days are MODIS estimates: {pre} before the downloaded "
                     f"S-NPP period and {outage} during a documented product gap."
                     if estimated_days else "")
    return (f"{region_name}, {label}: {_ordinal(item['percentile_rank'])} percentile of "
            f"{item['n_years']} comparable years.{estimate_note}")


def _season(days: list[dict]) -> dict:
    values = [item["value"] for item in days]
    missing = sum(value is None for value in values)
    if not values or missing / len(values) > .10:
        return {"season_start": None, "season_peak": None, "season_end": None,
                "season_status": "unavailable", "missing_days": missing}
    known = [float(value) for value in values if value is not None]
    total = sum(known)
    if total <= 0:
        return {"season_start": None, "season_peak": None, "season_end": None,
                "season_status": "no-detected-activity", "missing_days": missing}
    running = 0.0
    start = end = None
    for item in days:
        if item["value"] is not None:
            running += float(item["value"])
            if start is None and running / total >= .10:
                start = item["date"]
            if end is None and running / total >= .90:
                end = item["date"]
    windows = []
    for index in range(max(0, len(days) - 14)):
        window = days[index:index + 15]
        if all(item["value"] is not None for item in window):
            windows.append((sum(float(item["value"]) for item in window), index + 7))
    peak = days[max(windows, key=lambda item: (item[0], -item[1]))[1]]["date"] if windows else None
    status = "available" if start and end and peak else "unavailable"
    return {"season_start": start, "season_peak": peak, "season_end": end,
            "season_status": status, "missing_days": missing}


def prepare_calendar_v2(db, *, region: str, fallback_year: int = 2024) -> dict:
    """Load and calibrate a region once so multiple year views reuse the same rows."""
    if region not in REGIONS:
        raise ValueError(f"region must be one of {', '.join(REGIONS)}")
    bbox = REGIONS[region]["bbox"]
    earliest_row_only_month = db.execute("""
        SELECT min(e.month) FROM source_exports e
        JOIN batches b ON b.id=e.batch_id
        WHERE e.region_id=? AND e.source_id='MODIS_SP'
          AND e.coverage_basis='reconstructed-rows-only' AND e.complete_export=0
          AND b.demo=0 AND b.row_count>0
    """, (region,)).fetchone()[0]
    history_start = MODIS_ARCHIVE_START
    if earliest_row_only_month:
        row_start = date.fromisoformat(earliest_row_only_month + "-01")
        history_start = max(MODIS_EARLIEST_SUPPORTED_HISTORY,
                            min(MODIS_ARCHIVE_START, row_start))
    latest = db.execute("""
        SELECT max(substr(o.acquisition_utc,1,10)) FROM observations o
        JOIN batches b ON b.id=o.batch_id
        WHERE o.source_id IN ('MODIS_SP','VIIRS_SNPP_SP') AND b.demo=0
          AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=?
    """, (bbox[0], bbox[2], bbox[1], bbox[3])).fetchone()[0]
    latest_date = date.fromisoformat(latest) if latest else date(fallback_year, 12, 31)
    history_end = max(date(fallback_year, 12, 31), latest_date)
    raw = daily_aggregates(db, region, history_start, history_end)
    versions = {target_year: _selected_modis_version(raw["days"], target_year)
                for target_year in range(history_start.year, history_end.year + 1)}
    fallback = {"schema": "fireatlas-calibration-v1", "status": "insufficient-version-matched-overlap",
                "selected_model": None, "versions": {"MODIS_SP": None, "VIIRS_SNPP_SP": None}}
    calibrations = {}
    for version in set(versions.values()):
        calibration = calibrate(raw, modis_version=version) if raw["days"] else {
            **fallback, "versions": {"MODIS_SP": version, "VIIRS_SNPP_SP": None}}
        calibrations[version] = calibration
    return {"region": region, "latest": latest, "history_end": history_end,
            "history_start": history_start,
            "raw": raw, "versions": versions, "calibrations": calibrations}


def calendar_v2(db, *, region: str, year: int, month: int = 7,
                include_history: bool = False, prepared: dict | None = None) -> dict:
    if region not in REGIONS:
        raise ValueError(f"region must be one of {', '.join(REGIONS)}")
    if not MODIS_EARLIEST_SUPPORTED_HISTORY.year <= year <= 2026:
        raise ValueError("year must be between 2006 and 2026")
    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    selected_month_number = month

    prepared = prepared or prepare_calendar_v2(db, region=region, fallback_year=year)
    if prepared.get("region") != region:
        raise ValueError("prepared calendar data do not match selected region")
    bbox = REGIONS[region]["bbox"]
    latest = prepared["latest"]
    history_end = prepared["history_end"]
    raw = prepared["raw"]
    selected_modis = prepared["versions"].get(year, _selected_modis_version(raw["days"], year))
    fitted = prepared["calibrations"].get(selected_modis)
    if fitted is None:
        fitted = calibrate(raw, modis_version=selected_modis) if raw["days"] else {
            "schema": "fireatlas-calibration-v1", "status": "insufficient-version-matched-overlap",
            "selected_model": None, "months": [], "versions": {"MODIS_SP": selected_modis,
                                                                      "VIIRS_SNPP_SP": None}}
    model = fitted.get("selected_model") if fitted.get("status") == "calibrated" else None
    fit_months = {item["month"]: item for item in fitted.get("months", [])}
    annual_interval = fitted.get("annual_ratio_95_interval", [None, None])
    ratio_ready = model in ("monthly_ratio", "annual_ratio", "no_harmonization")
    by_date = {}
    for item in raw["days"]:
        stamp = item["date_utc"]
        by_date[stamp] = item

    harmonized = []
    current = prepared["history_start"]
    while current <= history_end:
        stamp = current.isoformat()
        row = by_date.get(stamp)
        value = low = high = None
        scale_factor = None
        scale_interval = None
        estimate_type = source_used = "unknown"
        quality, reason = "unknown", "incomplete_source_export"
        viirs_state = "unknown_export"
        viirs_gap_partial_day = False
        modis_value = None
        partial_modis = partial_viirs = 0
        if row:
            modis = row["sources"]["MODIS_SP"]
            viirs = row["sources"]["VIIRS_SNPP_SP"]
            modis_value = modis["detected_cell_days"]
            partial_modis = int(modis["partial_detected_cell_days"] or 0)
            partial_viirs = int(viirs["partial_detected_cell_days"] or 0)
            viirs_state = viirs["availability"]["status"]
            viirs_gap_partial_day = viirs["availability"]["notice_day_scope"] == "partial-utc-day"
            ratio_month = fit_months.get(current.month, {})
            if current < SNPP_ARCHIVE_START or viirs_state == "documented_processing_gap":
                calibrated_modis_version = fitted.get("versions", {}).get("MODIS_SP")
                matching_modis_version = modis["product_versions"] == [calibrated_modis_version]
                if modis["export_complete"] and modis_value is not None and ratio_ready and matching_modis_version:
                    if model == "monthly_ratio":
                        factor, factor_low, factor_high = ratio_month.get("ratio"), ratio_month.get("low"), ratio_month.get("high")
                    elif model == "annual_ratio":
                        factor, factor_low, factor_high = fitted.get("annual_ratio"), *annual_interval
                    else:
                        factor, factor_low, factor_high = 1.0, 1.0, 1.0
                    if factor is not None:
                        value = modis_value * factor
                        low = modis_value * factor_low if factor_low is not None else None
                        high = modis_value * factor_high if factor_high is not None else None
                        scale_factor = factor
                        scale_interval = [factor_low, factor_high]
                        estimate_type, source_used, quality = "scaled", "MODIS_SP", "degraded"
                        reason = "outside-downloaded-SNPP-period" if current < SNPP_ARCHIVE_START else "documented-processing-gap"
                else:
                    reason = ("MODIS-export-incomplete" if not modis["export_complete"] else
                              "MODIS-product-version-mismatch" if not matching_modis_version else
                              "calibration-not-validated")
            elif viirs["export_complete"] and viirs["detected_cell_days"] is not None:
                value = float(viirs["detected_cell_days"])
                low = high = value
                estimate_type, source_used, quality = "observed", "VIIRS_SNPP_SP", "good"
                reason = viirs_state
            else:
                reason = "VIIRS-export-incomplete"
        evidence_state = (
            "complete_zero_export" if value == 0 and quality == "good"
            else "observed" if estimate_type == "observed"
            else "scaled" if estimate_type == "scaled"
            else "unknown"
        )
        coverage_state = (
            "documented_processing_gap" if reason == "documented-processing-gap"
            else "complete_zero_export" if evidence_state == "complete_zero_export"
            else "observed" if evidence_state == "observed"
            else "unknown"
        )
        harmonized.append({"date": stamp, "value": value, "low": low, "high": high,
                           "estimate_type": estimate_type, "source_used": source_used,
                           "quality": quality, "reason": reason,
                           "modis_cell_days": modis_value, "scale_factor": scale_factor,
                           "scale_interval": scale_interval, "viirs_status": viirs_state,
                           "viirs_gap_partial_day": viirs_gap_partial_day,
                           "partial_modis_cell_days": partial_modis,
                           "partial_viirs_cell_days": partial_viirs,
                           "sensor_bridge": row.get("sensor_bridge") if row else None,
                           "frp_mw_day": {
                               "MODIS_SP": (row["sources"]["MODIS_SP"].get("frp_sum_mw") if row else None),
                               "VIIRS_SNPP_SP": (row["sources"]["VIIRS_SNPP_SP"].get("frp_sum_mw") if row else None),
                           } if row else None,
                           "evidence_state": evidence_state,
                           "coverage_state": coverage_state})
        current += timedelta(days=1)

    by_harmonized_date = {item["date"]: item for item in harmonized}
    year_days = [item for item in harmonized if int(item["date"][:4]) == year]
    season = _season(year_days)
    monthly = []
    years_used, excluded = set(), []
    for month in range(1, 13):
        first = date(year, month, 1)
        last = date(year, month, calendar.monthrange(year, month)[1])
        target_days = [by_harmonized_date.get((first + timedelta(days=offset)).isoformat())
                       for offset in range((last - first).days + 1)]
        target_days = [item for item in target_days if item]
        total = sum(float(item["value"]) for item in target_days) if target_days and all(item["value"] is not None for item in target_days) else None
        degraded = sum(item["quality"] == "degraded" for item in target_days)
        partial_detection_days = sum(
            item["partial_modis_cell_days"] > 0 or item["partial_viirs_cell_days"] > 0
            for item in target_days)
        partial_modis_cell_days = sum(item["partial_modis_cell_days"] for item in target_days)
        partial_viirs_cell_days = sum(item["partial_viirs_cell_days"] for item in target_days)
        pre_overlap = sum(item["reason"] == "outside-downloaded-SNPP-period" for item in target_days)
        outage_estimates = sum(item["reason"] == "documented-processing-gap" for item in target_days)
        target_versions = set()
        for day in raw["days"]:
            if day["date_utc"].startswith(f"{year}-{month:02d}"):
                source = day["sources"]["MODIS_SP"]
                if source["export_complete"]:
                    target_versions.update(source["product_versions"])
        baseline, excluded_for_month = [], []
        if len(target_versions) == 1:
            target_version = next(iter(target_versions))
            for prior_year in range(2010, year):
                key = f"{prior_year}-{month:02d}"
                prior_days = [item for item in harmonized if item["date"].startswith(key)]
                versions = set()
                for day in raw["days"]:
                    if day["date_utc"].startswith(key):
                        source = day["sources"]["MODIS_SP"]
                        if source["export_complete"]:
                            versions.update(source["product_versions"])
                if not prior_days or any(item["value"] is None for item in prior_days):
                    excluded_for_month.append({"year": prior_year, "reason": "incomplete-or-unknown-month"})
                elif versions != {target_version}:
                    excluded_for_month.append({"year": prior_year, "reason": "MODIS-product-version-mismatch"})
                else:
                    baseline.append({"year": prior_year, "value": sum(float(item["value"]) for item in prior_days)})
        else:
            excluded_for_month.append({"year": year, "reason": "selected-MODIS-product-version-unknown-or-mixed"})
        if total is not None:
            values = [item["value"] for item in baseline]
            percentile, rank = _percentile_rank(total, values)
            n = len(values)
            baseline_median = median(values) if values else None
            flag = ("insufficient-history" if n < 10 else "unusually-high" if percentile >= 90
                    else "unusually-low" if percentile <= 10 else "typical")
        else:
            percentile = rank = None
            baseline_median = median(item["value"] for item in baseline) if baseline else None
            n, flag = len(baseline), "unknown-month"
        if baseline:
            years_used.update(item["year"] for item in baseline)
        excluded.append({"month": f"{year}-{month:02d}", "years": excluded_for_month})
        month_item = {"month": f"{year}-{month:02d}", "value": total,
                        "percentile_rank": percentile, "rank": rank, "n_years": n,
                        "flag": flag, "degraded_days": degraded,
                        "partial_detection_days": partial_detection_days,
                        "partial_modis_cell_days": partial_modis_cell_days,
                        "partial_viirs_cell_days": partial_viirs_cell_days,
                        "outside_downloaded_snpp_period_days": pre_overlap,
                        "documented_gap_estimate_days": outage_estimates,
                        "baseline_median": baseline_median,
                        "anomaly_cell_days": total - baseline_median if total is not None and baseline_median is not None else None,
                        "modis_product_version": next(iter(target_versions)) if len(target_versions) == 1 else None,
                        "baseline_years": [item["year"] for item in baseline]}
        month_item["verdict"] = _verdict(REGIONS[region]["name"], year, month_item)
        monthly.append(month_item)

    selected_month = monthly[selected_month_number - 1]
    verdict = selected_month["verdict"]

    result = {
        "schema": "fireatlas-calendar-v2",
        "meta": {
            "region": {"id": region, "name": REGIONS[region]["name"]},
            "bbox": list(bbox),
            "unit": "VIIRS-equivalent active-fire cell-days on a common 1 km grid",
            "primary_measure": "VIIRS-equivalent active-fire cell-days on a common 1 km grid",
            "native_detail": raw.get("native_detail", {}),
            "bridge_method_version": raw.get("bridge_method_version"),
            "frp_context": raw.get("frp_context"),
            "corroboration": (_mcd64_corroboration(region, year, selected_month_number)
                              if raw.get("inputs") else {"status": "not-loaded",
                              "note": "No authentic active-fire inputs are imported for this calendar."}),
            "corroboration_by_month": (_mcd64_checks_for_year(region, year)
                                       if raw.get("inputs") else {}),
            "baseline": {"years_used": sorted(years_used), "excluded": excluded},
            "calibration_id": fitted.get("calibration_id"),
            "calibration_status": fitted.get("status", "insufficient-version-matched-overlap"),
            "calibration_model": model,
            "calibration_validation": fitted.get("validation"),
            "data_class": "authentic-imported" if raw.get("inputs") else "no-authentic-imports",
            "period": {"requested_start": MODIS_ARCHIVE_START.isoformat(),
                       "history_start": prepared["history_start"].isoformat(),
                       "actual_latest_detection": latest,
                       "selected_year": year, "selected_month": selected_month_number,
                       "downloaded_snpp_period_starts": SNPP_ARCHIVE_START.isoformat()},
            "verdict": verdict,
            "season": season,
            "coverage_limit": "FIRMS export completeness is not pass, cloud, or observation-opportunity coverage.",
            "inputs": raw.get("inputs", []),
        },
        "days": [item for item in harmonized if int(item["date"][:4]) == year],
        "months": monthly,
        "calibration": fitted,
        "availability": [{"date": item["date"], "sources": by_date.get(item["date"], {}).get("sources", {})}
                          for item in harmonized if int(item["date"][:4]) == year],
    }
    if include_history:
        result["history"] = {
            "unit": "VIIRS-equivalent active-fire cell-days on a common 1 km grid",
            "start": harmonized[0]["date"] if harmonized else None,
            "end": harmonized[-1]["date"] if harmonized else None,
            "days": [{"date": item["date"], "value": item["value"],
                      "quality": item["quality"], "estimate_type": item["estimate_type"],
                      "reason": item["reason"], "viirs_status": item["viirs_status"],
                      "evidence_state": item["evidence_state"],
                      "coverage_state": item["coverage_state"],
                      "partial_gap_day": item["viirs_gap_partial_day"],
                      "partial_modis_cell_days": item["partial_modis_cell_days"],
                      "partial_viirs_cell_days": item["partial_viirs_cell_days"]}
                     for item in harmonized],
        }
    return result


def region_status(db) -> dict:
    """Actual imported monthly export coverage, separate from the planned span."""
    regions = []
    for key, region in REGIONS.items():
        sources = {}
        w, south, east, north = region["bbox"]
        history_start = MODIS_ARCHIVE_START
        for source, planned_start in (("MODIS_SP", MODIS_ARCHIVE_START.isoformat()),
                                      ("VIIRS_SNPP_SP", SNPP_ARCHIVE_START.isoformat())):
            rows = db.execute("""
                SELECT w.month,b.file_sha256 FROM export_windows w
                JOIN batches b ON b.id=w.batch_id
                WHERE w.source_id=? AND b.demo=0
                  AND w.west<=? AND w.south<=? AND w.east>=? AND w.north>=?
                ORDER BY w.month,b.file_sha256
            """, (source, w, south, east, north)).fetchall()
            months = sorted({row["month"] for row in rows})
            missing_months = []
            if months:
                cursor = date.fromisoformat(planned_start).replace(day=1)
                last_month = date.fromisoformat(months[-1] + "-01")
                while cursor <= last_month:
                    key_month = cursor.strftime("%Y-%m")
                    if key_month not in months:
                        missing_months.append(key_month)
                    cursor = (date(cursor.year + 1, 1, 1) if cursor.month == 12
                              else date(cursor.year, cursor.month + 1, 1))
            count = db.execute("""
                SELECT count(*) FROM observations o JOIN batches b ON b.id=o.batch_id
                WHERE o.source_id=? AND b.demo=0 AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=?
            """, (source, w, east, south, north)).fetchone()[0]
            row_only_months = [row[0] for row in db.execute("""
                SELECT DISTINCT e.month FROM source_exports e
                JOIN batches b ON b.id=e.batch_id
                WHERE e.region_id=? AND e.source_id=?
                  AND e.coverage_basis='reconstructed-rows-only'
                  AND e.complete_export=0 AND b.row_count>0
                ORDER BY e.month
            """, (key, source)).fetchall()]
            first_detection = db.execute("""
                SELECT min(o.acquisition_utc) FROM observations o
                JOIN batches b ON b.id=o.batch_id
                WHERE o.source_id=? AND b.demo=0 AND o.lon>=? AND o.lon<=?
                  AND o.lat>=? AND o.lat<=?
            """, (source, w, east, south, north)).fetchone()[0]
            if source == "MODIS_SP" and row_only_months:
                row_start = date.fromisoformat(min(row_only_months) + "-01")
                history_start = max(MODIS_EARLIEST_SUPPORTED_HISTORY,
                                    min(MODIS_ARCHIVE_START, row_start))
            sources[source] = {"planned_start": planned_start,
                               "complete_month_count": len(months),
                               "first_complete_month": months[0] if months else None,
                               "last_complete_month": months[-1] if months else None,
                               "complete_months": months,
                               "missing_months": missing_months,
                               "reconstructed_row_only_months": row_only_months,
                               "reconstructed_row_only_month_count": len(row_only_months),
                               "first_detection_utc": first_detection,
                               "file_hashes": sorted({row["file_sha256"] for row in rows}),
                               "imported_detection_rows": count}
        regions.append({"id": key, "name": region["name"], "bbox": region["bbox"],
                        "description": region["description"],
                        "history_start": history_start.isoformat(), "products": sources})
    return {"schema": "fireatlas-region-status-v1", "regions": regions,
            "coverage_note": "Monthly export completeness describes the supplied request window and region. It is not satellite pass, clear-sky, or no-fire evidence."}
