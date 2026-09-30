"""Version-matched descriptive scaling and held-out checks for FIRMS cell-days."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

METHOD_VERSION = "nested-year-selection-factor-bootstrap-1000-step2012-v3"
BOOTSTRAPS = 1000
SEED = 20261114
MODELS = ("monthly_ratio", "annual_ratio", "no_harmonization")


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _rows(daily: dict) -> tuple[list[dict], dict[str, int]]:
    by_month = defaultdict(lambda: {"modis": 0, "viirs": 0, "modis_versions": set(), "viirs_versions": set(), "days": 0})
    excluded = defaultdict(int)
    for day in daily["days"]:
        date_text = day["date_utc"]
        modis = day["sources"]["MODIS_SP"]
        viirs = day["sources"]["VIIRS_SNPP_SP"]
        if not modis["export_complete"] or not viirs["export_complete"]:
            excluded["incomplete_source_export"] += 1
            continue
        if viirs["availability"]["status"] == "documented_processing_gap":
            excluded["documented_viirs_processing_gap"] += 1
            continue
        item = by_month[date_text[:7]]
        item["modis"] += modis["detected_cell_days"] or 0
        item["viirs"] += viirs["detected_cell_days"] or 0
        item["modis_versions"].update(modis["product_versions"])
        item["viirs_versions"].update(viirs["product_versions"])
        item["days"] += 1
    output = []
    for key, value in sorted(by_month.items()):
        year, month = map(int, key.split("-"))
        output.append({"year": year, "month": month, **value,
                       "modis_versions": sorted(value["modis_versions"]),
                       "viirs_versions": sorted(value["viirs_versions"])})
    return output, dict(excluded)


def _ratio(rows: list[dict]) -> float | None:
    denominator = sum(row["modis"] for row in rows)
    return sum(row["viirs"] for row in rows) / denominator if denominator > 0 else None


def _monthly_factor(rows: list[dict], month: int, annual: float) -> tuple[float, str]:
    candidates = [row for row in rows if row["month"] == month]
    denominator = sum(row["modis"] for row in candidates)
    if denominator >= 30:
        return sum(row["viirs"] for row in candidates) / denominator, "month-of-year"
    return annual, "annual-fallback"


def _bootstrap_interval(rows: list[dict], *, month: int | None, annual_fallback: bool) -> list[float | None]:
    years = sorted({row["year"] for row in rows})
    if not years:
        return [None, None]
    # Use the protocol's single declared seed for each interval. The sampled
    # years are therefore reproducible from the frozen method specification.
    rng = random.Random(SEED)
    estimates = []
    by_year = {year: [row for row in rows if row["year"] == year] for year in years}
    for _ in range(BOOTSTRAPS):
        sampled = [rng.choice(years) for _ in years]
        sample_rows = [row for year in sampled for row in by_year[year]
                       if month is None or row["month"] == month]
        if month is not None and annual_fallback:
            sample_rows = [row for year in sampled for row in by_year[year]]
        ratio = _ratio(sample_rows)
        if ratio is not None and math.isfinite(ratio):
            estimates.append(ratio)
    return [_percentile(estimates, .025), _percentile(estimates, .975)]


def _fit(rows: list[dict]) -> tuple[float | None, dict[int, dict]]:
    annual = _ratio(rows)
    if annual is None:
        return None, {}
    fits = {}
    for month in range(1, 13):
        value, basis = _monthly_factor(rows, month, annual)
        fallback = basis == "annual-fallback"
        interval = _bootstrap_interval(rows, month=month, annual_fallback=fallback)
        fits[month] = {"ratio": value, "low": interval[0], "high": interval[1], "basis": basis}
    return annual, fits


def _point_factors(rows: list[dict]) -> tuple[float | None, dict[int, float]]:
    """Fit point factors without bootstrap work for nested model selection."""
    annual = _ratio(rows)
    if annual is None:
        return None, {}
    return annual, {month: _monthly_factor(rows, month, annual)[0]
                    for month in range(1, 13)}


def _factor_for(model: str, annual: float, monthly: dict[int, float], month: int) -> float:
    if model == "monthly_ratio":
        return monthly[month]
    if model == "annual_ratio":
        return annual
    return 1.0


def _inner_selection(rows: list[dict]) -> dict:
    """Select a method by year-grouped CV inside the supplied training years."""
    years = sorted({row["year"] for row in rows})
    errors = {name: [] for name in MODELS}
    folds = []
    for validation_year in years:
        fit_rows = [row for row in rows if row["year"] != validation_year]
        held_out = [row for row in rows if row["year"] == validation_year]
        if not fit_rows or not held_out:
            continue
        annual, monthly = _point_factors(fit_rows)
        if annual is None:
            continue
        fold_errors = {name: [] for name in MODELS}
        for row in held_out:
            for name in MODELS:
                predicted = row["modis"] * _factor_for(name, annual, monthly, row["month"])
                error = abs(math.log((predicted + 1) / (row["viirs"] + 1)))
                errors[name].append(error)
                fold_errors[name].append(error)
        folds.append({"validation_year": validation_year,
                      "fit_years": sorted({row["year"] for row in fit_rows}),
                      "median_absolute_log_error": {
                          name: _percentile(values, .5)
                          for name, values in fold_errors.items()}})
    summaries = {name: _percentile(values, .5) for name, values in errors.items()}
    candidates = [(score, name) for name, score in summaries.items() if score is not None]
    selected = min(candidates)[1] if candidates else None
    return {"selected_model": selected, "scores": summaries, "folds": folds,
            "years": years, "selection_rule": "lowest median absolute log error; lexical tie-break"}


def _held_out(rows: list[dict]) -> dict:
    """Nested year-grouped evaluation: selection occurs inside each outer fold."""
    all_years = sorted({row["year"] for row in rows})
    errors = {name: [] for name in MODELS}
    annual_errors = {name: [] for name in errors}
    annual_error_years = {name: [] for name in errors}
    partial_years = []
    selected_errors = []
    selected_annual_errors = []
    selected_annual_years = []
    selection_folds = []
    for held_out_year in all_years:
        train = [row for row in rows if row["year"] != held_out_year]
        test = [row for row in rows if row["year"] == held_out_year]
        if not train:
            continue
        selection = _inner_selection(train)
        annual, monthly = _point_factors(train)
        if annual is None:
            continue
        predicted_year = {name: defaultdict(float) for name in (*MODELS, "selected_pipeline")}
        actual_year = {name: defaultdict(float) for name in (*MODELS, "selected_pipeline")}
        fold_errors = {name: [] for name in (*MODELS, "selected_pipeline")}
        for row in test:
            for name in MODELS:
                factor = _factor_for(name, annual, monthly, row["month"])
                predicted = row["modis"] * factor
                actual = row["viirs"]
                error = abs(math.log((predicted + 1) / (actual + 1)))
                errors[name].append(error)
                fold_errors[name].append(error)
                predicted_year[name]["all"] += predicted
                actual_year[name]["all"] += actual
            if selection["selected_model"]:
                name = selection["selected_model"]
                predicted = row["modis"] * _factor_for(name, annual, monthly, row["month"])
                error = abs(math.log((predicted + 1) / (row["viirs"] + 1)))
                selected_errors.append(error)
                fold_errors["selected_pipeline"].append(error)
                predicted_year["selected_pipeline"]["all"] += predicted
                actual_year["selected_pipeline"]["all"] += row["viirs"]
        for name in (*MODELS, "selected_pipeline"):
            actual = actual_year[name]["all"]
            if len(test) == 12:
                if actual:
                    annual_error = abs(predicted_year[name]["all"] - actual) / actual
                    if name == "selected_pipeline":
                        selected_annual_errors.append(annual_error)
                        selected_annual_years.append(held_out_year)
                    else:
                        annual_errors[name].append(annual_error)
                        annual_error_years[name].append(held_out_year)
                else:
                    if name != "selected_pipeline":
                        annual_errors[name].append(None)
        if len(test) != 12:
            partial_years.append({"year": held_out_year,
                                  "eligible_months": len(test),
                                  "annual_error_used": False})
        selection_folds.append({"outer_test_year": held_out_year,
                                "outer_train_years": sorted({row["year"] for row in train}),
                                "selected_model": selection["selected_model"],
                                "selection_status": "nested" if selection["selected_model"] else "insufficient-inner-training",
                                "inner_selection": selection})
    summaries = {}
    for name in errors:
        annual_values = [value for value in annual_errors[name] if value is not None]
        summaries[name] = {
            "median_absolute_log_error": _percentile(errors[name], .5),
            "median_annual_absolute_percent_error": _percentile(annual_values, .5),
            "annual_error_years": annual_error_years[name],
        }
    selected_summary = {
        "median_absolute_log_error": _percentile(selected_errors, .5),
        "median_annual_absolute_percent_error": _percentile(selected_annual_errors, .5),
        "annual_error_years": selected_annual_years,
        "outer_evaluation_folds": len(selected_errors) and sum(
            fold["selected_model"] is not None for fold in selection_folds),
    }
    production_selection = _inner_selection(rows)
    return {"years_held_out": all_years,
            "partial_years_excluded_from_annual_error": partial_years,
            "models": summaries,
            "nested_selected_pipeline": selected_summary,
            "outer_folds": selection_folds,
            "selected_model": production_selection["selected_model"],
            "production_model_selection": production_selection,
            "prediction_interval": {
                "status": "withheld-not-independently-calibrated",
                "nominal_coverage": 0.95,
                "held_out_coverage": None,
                "median_width": None,
                "evaluated_pairs": 0,
                "reason": "The available short paired record does not yet support independently calibrated prediction intervals.",
            },
            "selection_rule": production_selection["selection_rule"],
            "evaluation_protocol": "Nested leave-one-year-out. Candidate selection uses only outer-training years; reported fixed-model and selected-pipeline errors use outer-test years."}


def _season(month: int) -> str:
    return {12: "DJF", 1: "DJF", 2: "DJF",
            3: "MAM", 4: "MAM", 5: "MAM",
            6: "JJA", 7: "JJA", 8: "JJA",
            9: "SON", 10: "SON", 11: "SON"}[month]


def _summary(values: list[float]) -> dict:
    return {"sample_size": len(values), "median": _percentile(values, .5),
            "p90": _percentile(values, .9)}


def _daily_gap_benchmark(daily: dict, *, modis_version: str, viirs_version: str) -> dict:
    """Evaluate daily predictions and contiguous artificial gaps with nested year splits."""
    monthly_rows, _ = _rows(daily)
    eligible_months = {(row["year"], row["month"]): row for row in monthly_rows
                       if row["modis_versions"] == [modis_version]
                       and row["viirs_versions"] == [viirs_version]}
    excluded = defaultdict(int)
    by_year_month = defaultdict(list)
    for day in daily["days"]:
        stamp = day["date_utc"]
        modis = day["sources"]["MODIS_SP"]
        viirs = day["sources"]["VIIRS_SNPP_SP"]
        if not modis["export_complete"] or not viirs["export_complete"]:
            excluded["incomplete_source_export"] += 1
            continue
        if viirs.get("availability", {}).get("status") == "documented_processing_gap":
            excluded["documented_viirs_processing_gap"] += 1
            continue
        year, month = int(stamp[:4]), int(stamp[5:7])
        if (year, month) not in eligible_months:
            excluded["incompatible_or_ineligible_month"] += 1
            continue
        if modis["product_versions"] != [modis_version] or viirs["product_versions"] != [viirs_version]:
            excluded["product_version_mismatch"] += 1
            continue
        if modis["detected_cell_days"] is None or viirs["detected_cell_days"] is None:
            excluded["unknown_daily_total"] += 1
            continue
        by_year_month[(year, month)].append({
            "date": stamp, "day": date.fromisoformat(stamp), "year": year, "month": month,
            "modis": float(modis["detected_cell_days"]),
            "viirs": float(viirs["detected_cell_days"]),
        })

    years = sorted({year for year, _ in eligible_months})
    daily_errors = {name: [] for name in (*MODELS, "selected_pipeline")}
    daily_ape = {name: [] for name in daily_errors}
    daily_nonzero = defaultdict(int)
    windows = defaultdict(lambda: {"log_error": [], "ape": [], "years": set(), "nonzero": 0})
    folds = []
    for held_out_year in years:
        train_rows = [row for row in monthly_rows if row["year"] != held_out_year
                      and row["modis_versions"] == [modis_version]
                      and row["viirs_versions"] == [viirs_version]]
        test_keys = sorted(key for key in by_year_month if key[0] == held_out_year)
        selection = _inner_selection(train_rows)
        annual, monthly = _point_factors(train_rows)
        if annual is None:
            folds.append({"held_out_year": held_out_year, "status": "no-training-factor"})
            continue
        folds.append({"held_out_year": held_out_year,
                      "training_years": sorted({row["year"] for row in train_rows}),
                      "selected_model": selection["selected_model"],
                      "selection_status": "nested" if selection["selected_model"] else "insufficient-inner-training"})
        for key in test_keys:
            days = sorted(by_year_month[key], key=lambda item: item["date"])
            for day in days:
                model_factors = {name: _factor_for(name, annual, monthly, day["month"])
                                 for name in MODELS}
                if selection["selected_model"]:
                    model_factors["selected_pipeline"] = _factor_for(
                        selection["selected_model"], annual, monthly, day["month"])
                for name, factor in model_factors.items():
                    predicted = day["modis"] * factor
                    actual = day["viirs"]
                    daily_errors[name].append(abs(math.log((predicted + 1) / (actual + 1))))
                    if actual > 0:
                        daily_nonzero[name] += 1
                        daily_ape[name].append(abs(predicted - actual) / actual)

            for duration in (1, 3, 7, 14):
                if len(days) < duration:
                    continue
                for start in range(len(days) - duration + 1):
                    block = days[start:start + duration]
                    if any((block[index]["day"] - block[index - 1]["day"]).days != 1
                           for index in range(1, len(block))):
                        continue
                    actual = sum(item["viirs"] for item in block)
                    season = _season(block[0]["month"])
                    models = dict((name, _factor_for(name, annual, monthly, block[0]["month"]))
                                  for name in MODELS)
                    if selection["selected_model"]:
                        name = selection["selected_model"]
                        models["selected_pipeline"] = _factor_for(name, annual, monthly, block[0]["month"])
                    for name, factor in models.items():
                        predicted = sum(item["modis"] for item in block) * factor
                        key = (duration, season, name)
                        result = windows[key]
                        result["years"].add(held_out_year)
                        result["log_error"].append(abs(math.log((predicted + 1) / (actual + 1))))
                        if actual > 0:
                            result["nonzero"] += 1
                            result["ape"].append(abs(predicted - actual) / actual)

    window_results = []
    for (duration, season, model), values in sorted(windows.items()):
        window_results.append({"gap_duration_days": duration, "season": season, "model": model,
                               "window_count": len(values["log_error"]),
                               "nonzero_actual_windows": values["nonzero"],
                               "outer_test_years": sorted(values["years"]),
                               "median_absolute_log_error": _percentile(values["log_error"], .5),
                               "median_absolute_percent_error_nonzero": _percentile(values["ape"], .5)})
    daily_results = {}
    for name in daily_errors:
        daily_results[name] = {"n_days": len(daily_errors[name]),
                               "n_nonzero_viirs_days": daily_nonzero[name],
                               "median_absolute_log_error": _percentile(daily_errors[name], .5),
                               "median_absolute_percent_error_nonzero": _percentile(daily_ape[name], .5)}
    return {
        "schema": "fireatlas-gap-benchmark-v1",
        "status": "evaluated" if any(item["n_days"] for item in daily_results.values()) else "insufficient-compatible-daily-data",
        "versions": {"MODIS_SP": modis_version, "VIIRS_SNPP_SP": viirs_version},
        "eligible_complete_months": [f"{year}-{month:02d}" for year, month in sorted(eligible_months)],
        "eligible_days": sum(len(items) for items in by_year_month.values()),
        "outer_years": years,
        "outer_folds": folds,
        "gap_durations_days": [1, 3, 7, 14],
        "season_definition": {"DJF": "December–February", "MAM": "March–May",
                              "JJA": "June–August", "SON": "September–November"},
        "primary_metric": "median absolute log error abs(log((prediction+1)/(VIIRS+1)))",
        "secondary_metrics": ["median absolute percentage error on nonzero VIIRS totals",
                              "sample counts and outer test years"],
        "daily_metrics": daily_results,
        "contiguous_gap_contribution_metrics": window_results,
        "window_protocol": "Evaluate every rolling contiguous window wholly inside each compatible complete UTC month in the outer held-out year. Windows overlap and are clustered by outer test year; window count is not an independent sample size.",
        "model_selection_protocol": "For each outer test year, select among monthly ratio, annual ratio, and no harmonization using leave-one-year-out validation within outer-training years only. Fit the selected method on all outer-training months, then evaluate only on the held-out year.",
        "excluded_daily_dates": dict(sorted(excluded.items())),
    }


def _step_2012(rows: list[dict]) -> dict:
    """Hold out the first VIIRS year and compare its ratio with later years."""
    observed = [row for row in rows if row["year"] == 2012]
    reference = [row for row in rows if row["year"] != 2012]
    reference_years = sorted({row["year"] for row in reference})
    if not observed:
        return {"status": "awaiting-2012-standard-exports", "ratio": None,
                "interval_95": [None, None], "within_interval": None,
                "months_used": [], "reference_years": reference_years}
    months = sorted({row["month"] for row in observed})
    ratio = _ratio(observed)
    if ratio is None or len(reference_years) < 2:
        return {"status": "insufficient-reference-years", "ratio": ratio,
                "interval_95": [None, None], "within_interval": None,
                "months_used": months, "reference_years": reference_years}
    interval = _bootstrap_interval(reference, month=None, annual_fallback=False)
    lower, upper = interval
    within = lower <= ratio <= upper if lower is not None and upper is not None else None
    return {"status": "evaluated", "ratio": ratio, "interval_95": interval,
            "within_interval": within, "months_used": months,
            "reference_years": reference_years}


def calibrate(daily: dict, *, modis_version: str | None = None,
              viirs_version: str | None = None) -> dict:
    """Fit a transparent ratio for one explicitly matched pair of product versions."""
    all_rows, excluded = _rows(daily)
    version_pairs = defaultdict(int)
    for row in all_rows:
        if len(row["modis_versions"]) == len(row["viirs_versions"]) == 1:
            version_pairs[(row["modis_versions"][0], row["viirs_versions"][0])] += 1
    candidates = [pair for pair in version_pairs
                  if (modis_version is None or pair[0] == modis_version)
                  and (viirs_version is None or pair[1] == viirs_version)]
    if candidates:
        selected_pair = max(candidates, key=lambda key: (version_pairs[key], key))
        modis_version, viirs_version = selected_pair
    eligible = [row for row in all_rows if row["modis_versions"] == [modis_version]
                and row["viirs_versions"] == [viirs_version]] if modis_version and viirs_version else []
    if not eligible:
        return {"schema": "fireatlas-calibration-v1", "status": "insufficient-version-matched-overlap",
                "region": daily["region"], "versions": {"MODIS_SP": modis_version, "VIIRS_SNPP_SP": viirs_version},
                "overlap_months": [], "excluded_days": excluded,
                "eligible_months": [],
                "step_2012": _step_2012([]),
                "method_version": METHOD_VERSION, "data_class": "authentic-imported"}
    years = sorted({row["year"] for row in eligible})
    annual, monthly_fits = _fit(eligible)
    if annual is None:
        return {"schema": "fireatlas-calibration-v1", "status": "zero-MODIS-denominator",
                "region": daily["region"], "versions": {"MODIS_SP": modis_version, "VIIRS_SNPP_SP": viirs_version},
                "overlap_months": [f"{row['year']}-{row['month']:02d}" for row in eligible],
                "excluded_days": excluded,
                "eligible_months": _month_inputs(eligible),
                "step_2012": _step_2012(eligible),
                "method_version": METHOD_VERSION,
                "data_class": "authentic-imported"}
    validation = _held_out(eligible)
    validation["daily_gap_benchmark"] = _daily_gap_benchmark(
        daily, modis_version=modis_version, viirs_version=viirs_version)
    months = [{"month": month, **monthly_fits[month],
               "n_years": sum(1 for row in eligible if row["month"] == month)}
              for month in range(1, 13)]
    result = {
        "schema": "fireatlas-calibration-v1",
        "status": "calibrated" if len(years) >= 2 else "insufficient-held-out-years",
        "region": daily["region"],
        "unit": "VIIRS-equivalent active-fire distinct 1 km centroid cell-days",
        "versions": {"MODIS_SP": modis_version, "VIIRS_SNPP_SP": viirs_version},
        "overlap_months": [f"{row['year']}-{row['month']:02d}" for row in eligible],
        "eligible_months": _month_inputs(eligible),
        "years_used": years,
        "excluded_days": excluded,
        "annual_ratio": annual,
        "annual_ratio_95_interval": _bootstrap_interval(eligible, month=None, annual_fallback=False),
        "months": months,
        "validation": validation,
        "step_2012": _step_2012(eligible),
        "method_version": METHOD_VERSION,
        "bootstrap_replicates": BOOTSTRAPS,
        "random_seed": SEED,
        "data_class": "authentic-imported",
    }
    material = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    result["calibration_id"] = hashlib.sha256(material).hexdigest()
    if validation["selected_model"]:
        result["selected_model"] = validation["selected_model"]
    return result


def _month_inputs(rows: list[dict]) -> list[dict]:
    """Compact, auditable month totals that are actually used by the fit."""
    return [{"year": row["year"], "month": row["month"],
             "modis_cell_days": row["modis"], "viirs_cell_days": row["viirs"],
             "modis_versions": row["modis_versions"],
             "viirs_versions": row["viirs_versions"],
             "eligible_utc_days": row["days"]}
            for row in rows]


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


def build_artifact(*, region: dict, calibration: dict, paired_months: list[str],
                   parent_files: list[dict], daily_bundle_sha256: str) -> dict:
    """Bind calibration results to the exact paired source files and daily bundle."""
    stable_inputs = {"region": region, "paired_months": paired_months,
                     "parent_files": parent_files,
                     "daily_bundle_sha256": daily_bundle_sha256,
                     "method_version": calibration["method_version"]}
    manifest = json.dumps(stable_inputs, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema": "fireatlas-calibration-artifact-v1",
        "region": region,
        "calibration": calibration,
        "provenance": {
            "input_manifest_sha256": hashlib.sha256(manifest).hexdigest(),
            "paired_complete_months": paired_months,
            "parent_files": parent_files,
            "daily_bundle": f"/samples/aggregates/{region['id']}.json.gz",
            "daily_bundle_sha256": daily_bundle_sha256,
            "reproduction": "Recompute from the listed paired daily bundle with the method version recorded in the calibration object.",
        },
    }


def write_artifacts(database: str | Path, output_dir: str | Path,
                    daily_bundle_dir: str | Path | None = None) -> list[dict]:
    """Create deterministic per-region calibration JSON from complete pairs only."""
    from .aggregates import _parent_inputs, daily_aggregates, paired_complete_months
    from .core import connect
    from .regions import REGIONS

    root = Path(__file__).resolve().parent.parent
    bundle_dir = Path(daily_bundle_dir) if daily_bundle_dir else root / "fireatlas" / "samples" / "aggregates"
    output = Path(output_dir)
    artifacts = []
    with connect(database) as db:
        for region_id, region in REGIONS.items():
            months = paired_complete_months(db, region_id)
            if not months:
                raise ValueError(f"No complete paired months are available for {region_id}")
            # Match the calendar API's frozen archive horizon. The ratio fit
            # still admits only complete paired months, but its exclusion
            # ledger then agrees exactly with the visible calendar result.
            first = date.fromisoformat(months[0] + "-01")
            month_end = date.fromisoformat(months[-1] + "-01")
            next_month = (month_end.replace(day=28) + timedelta(days=4)).replace(day=1)
            last = next_month - timedelta(days=1)
            daily = daily_aggregates(db, region_id, first, last)
            modis_version = _selected_modis_version(daily["days"], 2024)
            calibration = calibrate(daily, modis_version=modis_version)
            files = _parent_inputs(db, region_id, months)
            bundle_path = bundle_dir / f"{region_id}.json.gz"
            if not bundle_path.is_file():
                raise ValueError(f"Paired daily bundle is missing: {bundle_path}")
            with bundle_path.open("rb") as stream:
                bundle_hash = hashlib.file_digest(stream, "sha256").hexdigest()
            document = build_artifact(
                region={"id": region_id, "name": region["name"], "bbox": list(region["bbox"])},
                calibration=calibration, paired_months=months,
                parent_files=files, daily_bundle_sha256=bundle_hash)
            output.mkdir(parents=True, exist_ok=True)
            path = output / f"{region_id}.json"
            path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            artifacts.append({"region": region_id, "path": str(path),
                              "paired_months": len(months),
                              "parent_files": len(files),
                              "calibration_id": calibration.get("calibration_id"),
                              "status": calibration["status"],
                              "step_2012": calibration["step_2012"]["status"]})
    return artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description="Build source-attributed FireAtlas calibration JSON artifacts")
    parser.add_argument("--db", default="data/fireatlas.sqlite3", help="Imported FireAtlas SQLite database")
    parser.add_argument("--output", default="fireatlas/samples/calibration", help="Artifact output directory")
    parser.add_argument("--daily-bundles", default=None, help="Directory containing paired daily JSON.GZ bundles")
    args = parser.parse_args()
    for item in write_artifacts(args.db, args.output, args.daily_bundles):
        print(json.dumps(item, sort_keys=True))


if __name__ == "__main__":
    main()
