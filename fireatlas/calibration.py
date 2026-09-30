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

METHOD_VERSION = "monthly-ratio-loyo-bootstrap-1000-step2012-v2"
BOOTSTRAPS = 1000
SEED = 20261114


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


def _held_out(rows: list[dict]) -> dict:
    all_years = sorted({row["year"] for row in rows})
    errors = {name: [] for name in ("monthly_ratio", "annual_ratio", "no_harmonization")}
    annual_errors = {name: [] for name in errors}
    annual_error_years = {name: [] for name in errors}
    partial_years = []
    interval_hits = total = 0
    for held_out_year in all_years:
        train = [row for row in rows if row["year"] != held_out_year]
        test = [row for row in rows if row["year"] == held_out_year]
        if not train:
            continue
        annual, monthly = _fit(train)
        if annual is None:
            continue
        predicted_year = defaultdict(float)
        actual_year = defaultdict(float)
        for row in test:
            for name, factor in (("monthly_ratio", monthly[row["month"]]["ratio"]),
                                 ("annual_ratio", annual), ("no_harmonization", 1.0)):
                predicted = row["modis"] * factor
                actual = row["viirs"]
                errors[name].append(abs(math.log((predicted + 1) / (actual + 1))))
                predicted_year[name] += predicted
                actual_year[name] += actual
            lower, upper = monthly[row["month"]]["low"], monthly[row["month"]]["high"]
            if lower is not None and upper is not None:
                interval_hits += int(row["modis"] * lower <= row["viirs"] <= row["modis"] * upper)
                total += 1
        for name in errors:
            actual = actual_year[name]
            if len(test) == 12:
                if actual:
                    annual_errors[name].append(abs(predicted_year[name] - actual) / actual)
                    annual_error_years[name].append(held_out_year)
                else:
                    annual_errors[name].append(None)
            elif name == "monthly_ratio":
                partial_years.append({"year": held_out_year,
                                      "eligible_months": len(test),
                                      "annual_error_used": False})
    summaries = {}
    for name in errors:
        annual_values = [value for value in annual_errors[name] if value is not None]
        summaries[name] = {
            "median_absolute_log_error": _percentile(errors[name], .5),
            "median_annual_absolute_percent_error": _percentile(annual_values, .5),
            "annual_error_years": annual_error_years[name],
        }
    fitted = summaries["monthly_ratio"]["median_absolute_log_error"]
    candidates = [(summary["median_absolute_log_error"], name) for name, summary in summaries.items()
                  if summary["median_absolute_log_error"] is not None]
    selected = min(candidates)[1] if candidates else None
    return {"years_held_out": all_years,
            "partial_years_excluded_from_annual_error": partial_years,
            "models": summaries,
            "monthly_interval_coverage": interval_hits / total if total else None,
            "monthly_interval_pairs": total, "selected_model": selected,
            "selection_rule": "lowest median absolute log error; lexical tie-break"}


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
            first = date(2010, 7, 1)
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
