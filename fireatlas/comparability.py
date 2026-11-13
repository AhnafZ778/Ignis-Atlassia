"""Versioned, complete-month MODIS/VIIRS comparability experiments.

This module never imputes daily observations. It evaluates a regional monthly
count mapping against S-NPP observations, not ground-truth fire occurrence.
Legacy calendar/study algorithms stay reproducible under their original schemas.
"""
from __future__ import annotations

import argparse
from calendar import monthrange
from collections import Counter, defaultdict
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import sqlite3

from .aggregates import daily_aggregates
from .calibration import MODELS, _point_factors, _factor_for, _percentile
from .core import GRID_VERSION
from .regions import REGIONS

SCHEMA = "fireatlas-monthly-comparability-v1"
METHOD = "complete-month-nested-and-past-only-v1"
SOURCES = ("MODIS_SP", "VIIRS_SNPP_SP")
POLICY = {
    "minimum_complete_months": 24,
    "minimum_outer_years": 3,
    "minimum_relative_log_error_improvement": 0.10,
    "minimum_forward_test_years": 3,
    "prediction_interval_required_for_imputation": True,
}
LIMITS = {"days": 36600, "months": 1200, "json_bytes": 16_000_000}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def metric(predictions):
    """Reference is VIIRS observed activity, never true fire occurrence."""
    if not predictions:
        return {"n_months": 0, "median_absolute_log_error": None,
                "median_absolute_percentage_error_nonzero": None,
                "weighted_absolute_percentage_error": None, "relative_bias": None}
    errors = [abs(math.log((p["prediction"] + 1) / (p["reference"] + 1))) for p in predictions]
    nonzero = [abs(p["prediction"] - p["reference"]) / p["reference"]
               for p in predictions if p["reference"] > 0]
    total = sum(p["reference"] for p in predictions)
    return {"n_months": len(predictions),
            "median_absolute_log_error": _percentile(errors, .5),
            "median_absolute_percentage_error_nonzero": _percentile(nonzero, .5),
            "weighted_absolute_percentage_error": sum(abs(p["prediction"] - p["reference"]) for p in predictions) / total if total else None,
            "relative_bias": sum(p["prediction"] - p["reference"] for p in predictions) / total if total else None}


def choose(rows):
    """Inner year holdout uses only the supplied outer-training observations."""
    years = sorted({r["year"] for r in rows})
    predictions = {name: [] for name in MODELS}
    for held in years:
        train = [r for r in rows if r["year"] != held]
        annual, monthly = _point_factors(train)
        if annual is None:
            continue
        for row in rows:
            if row["year"] != held:
                continue
            for name in MODELS:
                predictions[name].append({"prediction": row["modis"] * _factor_for(name, annual, monthly, row["month"]),
                                          "reference": row["viirs"]})
    scores = {name: metric(values) for name, values in predictions.items()}
    available = [(m["median_absolute_log_error"], name) for name, m in scores.items()
                 if m["median_absolute_log_error"] is not None]
    return (min(available)[1] if available else None), scores


def complete_months(inputs):
    """Require every expected UTC date, both verified exports, one version pair, and no outage."""
    days = inputs.get("days")
    if not isinstance(days, list) or len(days) > LIMITS["days"]:
        raise ValueError("Bounded daily input is required.")
    grouped, dates = defaultdict(list), set()
    for day in days:
        stamp = date.fromisoformat(day["date"]).isoformat()
        if stamp != day["date"]:
            raise ValueError("Use canonical YYYY-MM-DD UTC dates.")
        if stamp in dates:
            raise ValueError("Duplicate UTC input date.")
        dates.add(stamp)
        for source in SOURCES:
            item = day["sources"][source]
            for field in ("cells", "raw"):
                v = item.get(field)
                if v is not None and (type(v) is not int or v < 0):
                    raise ValueError("Input counts must be nonnegative integers or unknown.")
            if item["cells"] is not None and item["raw"] is not None and item["cells"] > item["raw"]:
                raise ValueError("Occupied cells cannot exceed source rows.")
            if not isinstance(item.get("versions"), list) or not all(isinstance(v, str) and 0 < len(v) <= 40 for v in item["versions"]):
                raise ValueError("Declare bounded string product versions explicitly.")
            if type(item.get("processing_gap")) is not bool:
                raise ValueError("Processing-gap state must be explicit.")
            if type(item.get("verified_export")) is not bool:
                raise ValueError("Export evidence must be explicit.")
        grouped[stamp[:7]].append(day)
    if len(grouped) > LIMITS["months"]:
        raise ValueError("Too many source months.")
    rows, excluded = [], []
    for ym, items in sorted(grouped.items()):
        year, month = map(int, ym.split("-"))
        expected = monthrange(year, month)[1]
        reasons = set()
        if len(items) != expected:
            reasons.add("missing-utc-dates")
        versions = {}
        for source in SOURCES:
            values = [d["sources"][source] for d in items]
            if any(not v["verified_export"] for v in values):
                reasons.add("unverified-or-incomplete-source-export")
            if any(v.get("processing_gap") for v in values):
                reasons.add("documented-processing-gap")
            if any(v["cells"] is None or v["raw"] is None for v in values):
                reasons.add("unknown-source-total")
            found = {version for v in values for version in v.get("versions", [])}
            if len(found) != 1 or any(len(v.get("versions", [])) != 1 for v in values):
                reasons.add("unknown-or-mixed-product-version")
            versions[source] = sorted(found)
        if reasons:
            excluded.append({"month": ym, "reasons": sorted(reasons), "utc_days": len(items)})
            continue
        pair = [versions[s][0] for s in SOURCES]
        rows.append({"date": ym, "year": year, "month": month, "days": expected, "versions": pair,
                     "modis": sum(d["sources"][SOURCES[0]]["cells"] for d in items),
                     "viirs": sum(d["sources"][SOURCES[1]]["cells"] for d in items),
                     "raw_modis": sum(d["sources"][SOURCES[0]]["raw"] for d in items),
                     "raw_viirs": sum(d["sources"][SOURCES[1]]["raw"] for d in items)})
    return rows, excluded


def evaluate(rows, protocol):
    """Persist each held-out prediction with the exact training years and method."""
    if protocol not in ("nested", "forward"):
        raise ValueError("Unknown evaluation protocol.")
    results, folds, skipped = [], [], []
    for year in sorted({r["year"] for r in rows}):
        train = [r for r in rows if (r["year"] < year if protocol == "forward" else r["year"] != year)]
        years = sorted({r["year"] for r in train})
        # Two years are needed to select by an inner year split.
        if len(years) < 2:
            skipped.append({"year": year, "reason": "fewer-than-two-training-years"})
            continue
        name, scores = choose(train)
        annual, monthly = _point_factors(train)
        if name is None or annual is None:
            skipped.append({"year": year, "reason": "no-training-factor-or-inner-selection"})
            continue
        folds.append({"test_year": year, "training_years": years, "selected_model": name,
                      "inner_scores": scores})
        for row in rows:
            if row["year"] != year:
                continue
            factor = _factor_for(name, annual, monthly, row["month"])
            fixed = {m: row["modis"] * _factor_for(m, annual, monthly, row["month"]) for m in MODELS}
            results.append({**row, "reference": row["viirs"], "prediction": fixed[name],
                            "factor": factor, "model": name, "training_years": years, "fixed": fixed})
    scores = metric(results)
    baseline = metric([{**r, "prediction": r["modis"]} for r in results])
    base, adjusted = baseline["median_absolute_log_error"], scores["median_absolute_log_error"]
    improvement = (base - adjusted) / base if base and adjusted is not None else None
    fixed = {m: metric([{**r, "prediction": r["fixed"][m]} for r in results]) for m in MODELS}
    annuals = []
    for year in sorted({r["year"] for r in results}):
        items = [r for r in results if r["year"] == year]
        # Twelve genuinely complete months, not twelve partially paired month entries.
        if len(items) == 12 and {r["month"] for r in items} == set(range(1, 13)):
            actual = sum(r["reference"] for r in items)
            annuals.append({"year": year, "reference": actual, "prediction": sum(r["prediction"] for r in items),
                            "absolute_percentage_error": abs(sum(r["prediction"] for r in items) - actual) / actual if actual else None})
    seasonal = {season: metric([r for r in results if r["month"] in months])
                for season, months in {"DJF": (12, 1, 2), "MAM": (3, 4, 5), "JJA": (6, 7, 8), "SON": (9, 10, 11)}.items()}
    return {"protocol": protocol, "folds": folds, "skipped": skipped, "rows": results,
            "adjusted": scores, "raw": baseline, "relative_log_error_improvement": improvement,
            "fixed_models": fixed, "complete_year_results": annuals, "seasonal": seasonal}


def source_switch(evaluation, year, month):
    """Counterfactual handoff error relative to the same month's VIIRS reference."""
    rows = sorted((r for r in evaluation["rows"] if r["year"] == year), key=lambda r: r["month"])
    if not rows or type(month) is not int or not 2 <= month <= 12:
        return None
    before = next((r for r in rows if r["month"] == month - 1), None)
    after = next((r for r in rows if r["month"] == month), None)
    points = [{**r, "raw_switch": r["modis"] if r["month"] < month else r["reference"],
               "adjusted_switch": r["prediction"] if r["month"] < month else r["reference"],
               "selected_source": "MODIS estimate" if r["month"] < month else "VIIRS observation"}
              for r in rows]
    return {"year": year, "switch_month": month, "protocol": evaluation["protocol"],
            "kind": "counterfactual-held-out-source-switch-not-historical-2012",
            "seam_evaluable": bool(before and after), "rows": points,
            "raw_seam_error": abs(before["reference"] - before["modis"]) if before and after else None,
            "adjusted_seam_error": abs(before["reference"] - before["prediction"]) if before and after else None,
            "definition": "Absolute difference between the joined-series month-to-month change and the same change in the observed VIIRS reference. A real VIIRS change is preserved, not forced to zero."}


def analyze(inputs):
    if inputs.get("schema") != "fireatlas-comparability-input-v1" or inputs.get("region") not in REGIONS:
        raise ValueError("Use a versioned fixed-region comparability input.")
    all_rows, excluded = complete_months(inputs)
    pairs = Counter(tuple(r["versions"]) for r in all_rows)
    requested = inputs.get("versions")
    if requested is not None and (not isinstance(requested, list) or len(requested) != 2 or not all(isinstance(v, str) for v in requested)):
        raise ValueError("Choose an exact MODIS/VIIRS product-version pair.")
    pair = tuple(requested) if requested else (max(pairs, key=lambda p: (pairs[p], p)) if pairs else None)
    rows = [r for r in all_rows if tuple(r["versions"]) == pair]
    nested, forward = evaluate(rows, "nested"), evaluate(rows, "forward")
    checks = {
        "enough_complete_months": len(rows) >= POLICY["minimum_complete_months"],
        "enough_outer_years": len(nested["folds"]) >= POLICY["minimum_outer_years"],
        "improves_held_out_log_error": nested["relative_log_error_improvement"] is not None
            and nested["relative_log_error_improvement"] >= POLICY["minimum_relative_log_error_improvement"],
    }
    admitted = all(checks.values())
    selected, selection = choose(rows)
    factors = None
    if rows:
        a, m = _point_factors(rows)
        if a is not None:
            factors = {"annual_ratio": a, "monthly_ratios": {str(k): v for k, v in m.items()}}
    eligible_months = {r["date"] for r in rows}
    experiments = {}
    for evaluation in (nested, forward):
        for year in sorted({r["year"] for r in evaluation["rows"]}):
            for month in range(2, 13):
                item = source_switch(evaluation, year, month)
                if item and item["seam_evaluable"]:
                    experiments[f'{evaluation["protocol"]}/{year}/{month}'] = item
    default_keys = [k for k in experiments if k.startswith("forward/") and k.endswith("/7")]
    default_key = default_keys[0] if default_keys else next(iter(experiments), None)
    zero = Counter()
    for d in inputs["days"]:
        if d["date"][:7] not in eligible_months:
            continue
        m, v = (d["sources"][s]["cells"] for s in SOURCES)
        if v is not None and v > 0:
            zero["viirs_positive_days"] += 1
            zero["modis_zero_viirs_positive_days"] += int(m == 0)
    continuity = [{"versions": list(p), "complete_months": pairs[p],
                   "years": sorted({r["year"] for r in all_rows if tuple(r["versions"]) == p}),
                   "transfer_to_selected_pair": "same-pair" if p == pair else "not-established"}
                  for p in sorted(pairs)]
    # Fit availability, evaluated comparison, daily imputation and external review are distinct gates.
    result = {
        "schema": SCHEMA, "method_version": METHOD, "region": {**REGIONS[inputs["region"]], "bbox": list(REGIONS[inputs["region"]]["bbox"])},
        "unit": "monthly occupied 1 km centroid cell-days; VIIRS-equivalent only for adjusted estimates",
        "target": "Observed standard S-NPP monthly activity, not ground-truth fires, burned area or sensor sensitivity.",
        "grid": GRID_VERSION, "versions": list(pair) if pair else None,
        "period": {"first_eligible_month": rows[0]["date"] if rows else None,
                   "last_eligible_month": rows[-1]["date"] if rows else None,
                   "latest_imported_standard_utc": inputs.get("latest_standard_utc")},
        "admission": {"status": "evaluated-retrospective-comparison" if admitted else "insufficient-comparison-evidence",
                      "monthly_comparison": admitted, "screening_checks": checks, "policy": POLICY,
                      "daily_imputation": False, "historical_collection_transfer": False,
                      "prospective_monitoring": False,
                       "forward_evidence_sufficient": len(forward["folds"]) >= POLICY["minimum_forward_test_years"], "independent_review": "pending",
                      "prediction_intervals": "withheld-not-calibrated",
                      "note": "Declared screening gates govern this research interface; passing them is not independent scientific certification."},
        "eligibility": {"complete_matched_months": len(rows), "years": sorted({r["year"] for r in rows}),
                        "excluded_months": excluded, "version_cohorts": continuity,
                        "rule": "Every UTC date, both request-metadata-verified exports, no processing-gap date, one declared version per source. Partial months never enter full-year metrics."},
        "model_definition": {"candidates": list(MODELS),
                             "selection": "Inner leave-one-year-out median absolute log error; lexical tie break. Test-year values never select or fit their prediction.",
                             "factor": "Sum VIIRS / sum MODIS in training months. Month-specific factor requires at least 30 MODIS training cell-days in that calendar month; otherwise pooled annual factor.",
                             "log_error": "abs(log((predicted + 1)/(VIIRS + 1)))",
                             "raw_baseline": "Unscaled MODIS on exactly the same held-out months.",
                             "uncertainty": "Errors are observed cross-validation residuals, not confidence or prediction intervals. Only four distinct overlap years; months are temporally dependent."},
        "production_fit": {"selected_model": selected, "inner_scores": selection, "factors": factors,
                           "use": "Descriptive monthly fit only; held-out proof uses separately refitted training data."},
        "evaluation": {"nested": nested, "forward": forward},
        "experiments": experiments, "default_experiment": default_key,
        "zero_recovery_limit": dict(zero),
        "coverage": {"export_completeness": "checked-per-source-month",
                     "usable_footprint": "unknown", "cloud_and_no_pass": "not-inferred",
                     "independent_ground_truth": "not-provided"},
        "diagnostics": inputs.get("diagnostics", {}),
        "limitations": [
            "Common-grid aggregation does not equalize detection sensitivity or satellite observation opportunity.",
            "Ratios cannot recover a VIIRS-positive observation when MODIS reports zero.",
            "Daily gap substitution is not admitted. Missing observations remain unknown.",
            "No continuous 2000-to-present record or cross-collection transfer is established.",
            "Only the fixed selected region and product versions were evaluated.",
            "Four overlap years do not support a general climate baseline or a guaranteed prediction interval.",
            "Source-specific FRP is a sampled context statistic, not integrated energy or a harmonized total.",
        ],
        "input_sha256": digest(inputs),
    }
    result["result_sha256"] = digest(result)
    return result


def capture(db, region):
    if region not in REGIONS:
        raise ValueError("Choose a supported fixed study region.")
    bbox = REGIONS[region]["bbox"]
    verified = {(r["source_id"], r["month"]) for r in db.execute("""
        SELECT e.source_id,e.month FROM source_exports e JOIN batches b ON b.id=e.batch_id
        WHERE e.region_id=? AND b.demo=0 AND e.complete_export=1 AND e.coverage_basis='request-metadata'
          AND e.west<=? AND e.south<=? AND e.east>=? AND e.north>=?
    """, (region, *bbox))}
    months = sorted(m for s, m in verified if s in SOURCES)
    days = []
    if months:
        first = date.fromisoformat(months[0] + "-01")
        last = date.fromisoformat(months[-1] + "-01")
        last = last.replace(day=monthrange(last.year, last.month)[1])
        raw = daily_aggregates(db, region, first, last)
        for day in raw["days"]:
            sources = {}
            for s in SOURCES:
                item = day["sources"][s]
                sources[s] = {"cells": item["detected_cell_days"], "raw": item["raw_pixel_count"],
                              "versions": item["product_versions"],
                              "verified_export": item["export_complete"] and (s, day["date_utc"][:7]) in verified,
                              "processing_gap": item["availability"]["status"] == "documented_processing_gap"}
            days.append({"date": day["date_utc"], "sources": sources})
    w, south, e, north = bbox
    diagnostics = [dict(r) for r in db.execute("""
        SELECT o.source_id,o.platform,o.daynight,o.product_version,COUNT(*) AS imported_rows
        FROM observations o JOIN batches b ON b.id=o.batch_id
        WHERE b.demo=0 AND o.source_id IN ('MODIS_SP','VIIRS_SNPP_SP')
          AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=?
        GROUP BY o.source_id,o.platform,o.daynight,o.product_version
        ORDER BY o.source_id,o.platform,o.daynight,o.product_version
    """, (w, e, south, north))]
    latest = db.execute("""
        SELECT MAX(o.acquisition_utc) FROM observations o JOIN batches b ON b.id=o.batch_id
        WHERE b.demo=0 AND o.source_id IN ('MODIS_SP','VIIRS_SNPP_SP')
          AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=?
    """, (w, e, south, north)).fetchone()[0]
    ledgers = [dict(r) for r in db.execute("""
        SELECT e.region_id,e.source_id,e.month,e.complete_export,e.coverage_basis,
               e.product_versions_json,e.parent_sha256,e.request_sha256,b.file_sha256
        FROM source_exports e JOIN batches b ON b.id=e.batch_id
        WHERE e.region_id=? AND b.demo=0 AND e.source_id IN ('MODIS_SP','VIIRS_SNPP_SP')
        ORDER BY e.source_id,e.month,b.file_sha256,e.request_sha256
    """, (region,))]
    return {"schema": "fireatlas-comparability-input-v1", "region": region, "days": days,
            "latest_standard_utc": latest, "source_ledger": ledgers,
            "diagnostics": {"platform_daynight_inventory": diagnostics,
                            "note": "Inventory counts, not exposure-normalized comparison; the monthly mapping pools Terra/Aqua and is not a sensitivity model."}}


def build(db, region="norcal"):
    inputs = capture(db, region)
    return {"schema": "fireatlas-comparability-bundle-v1", "inputs": inputs, "result": analyze(inputs),
            "verification_scope": "Recomputes the statistical experiment from frozen aggregate inputs. It does not authenticate NASA source files or provide independent review."}


def verify(bundle):
    if bundle.get("schema") != "fireatlas-comparability-bundle-v1":
        raise ValueError("Unsupported comparability evidence.")
    actual = analyze(bundle["inputs"])
    if digest(actual) != digest(bundle.get("result")):
        raise ValueError("Statistical recount differs from the frozen result.")
    return {"verified": True, "result_sha256": actual["result_sha256"], "input_sha256": actual["input_sha256"],
            "scope": "Aggregate statistical reproduction only; source authentication and independent review are separate."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    generate = sub.add_parser("build")
    generate.add_argument("--db", type=Path, default=Path("data/fireatlas.sqlite3"))
    generate.add_argument("--region", choices=REGIONS, default="norcal")
    generate.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("verify")
    check.add_argument("file", type=Path)
    args = parser.parse_args()
    if args.command == "verify":
        if args.file.stat().st_size > LIMITS["json_bytes"]:
            raise ValueError("Comparability JSON exceeds 16 MB.")
        print(json.dumps(verify(json.loads(args.file.read_text()))))
    else:
        with sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            bundle = build(db, args.region)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(bundle, sort_keys=True, separators=(",", ":")) + "\n")
        print(json.dumps({"file": str(args.output), **verify(bundle)}))


if __name__ == "__main__":
    main()
