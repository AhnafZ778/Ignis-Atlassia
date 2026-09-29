# Appendix A — Schemas (implement these field names exactly)

All JSON files are UTF-8, dates are ISO 8601 (`YYYY-MM-DD`, times with `Z`), numbers are plain JSON numbers (no strings), missing values are `null`. Every file has `schema` and `method_version` at the top level. Add a JSON Schema file for each under `fireatlas/schemas/` and validate in tests (a small hand-written validator is fine; do not add a large dependency).

## A.1 `fireatlas-daily-aggregates-v1` (`fireatlas/samples/aggregates/<region>.json.gz`)

```json
{
  "schema": "fireatlas-daily-aggregates-v1",
  "method_version": "cell-days-1km-epsg6933-v2",
  "region": {"id": "norcal", "bbox": [-122.2, 38.8, -120.0, 41.0]},
  "generated_utc": "2026-10-10T12:00:00Z",
  "inputs": [{"bundle": "nasa_firms_norcal_2000_2025.zip", "sha256": "…", "source_id": "MODIS_SP"}],
  "series": ["MODIS_SP", "VIIRS_SNPP_SP", "VIIRS_NOAA20_SP"],
  "variants": ["utc|veg|all", "utc|veg|no-low", "utc|all|all", "utc|all|no-low",
               "solar|veg|all", "solar|veg|no-low", "solar|all|all", "solar|all|no-low"],
  "complete_months": {"MODIS_SP": ["2000-11", "…"], "VIIRS_SNPP_SP": ["2012-02", "…"]},
  "days": [
    {"date": "2024-07-25",
     "v": {"utc|veg|all": {
             "MODIS_SP":      {"cells": 415, "raw": 603, "frp_sum": 12345.6},
             "VIIRS_SNPP_SP": {"cells": 0,   "raw": 0,   "frp_sum": 0.0},
             "VIIRS_NOAA20_SP": {"cells": 0, "raw": 0, "frp_sum": 0.0},
             "union_modis_snpp": 415, "intersection_modis_snpp": 0}}}
  ]
}
```

Rules: a day appears only if at least one series has a complete export for that month; the example numbers other than the Park MODIS values (603 / 415, measured) are placeholders — tests must use real computed values. Days with zero everywhere may be omitted **only** if `complete_months` covers them (readers then treat them as observed zero).

## A.2 `fireatlas-calibration-v1` (`fireatlas/samples/calibration/<region>.json`)

```json
{
  "schema": "fireatlas-calibration-v1",
  "method_version": "overlap-ratio-moy-v1",
  "region": "norcal",
  "pair": {"reference": "VIIRS_SNPP_SP", "scaled": "MODIS_SP"},
  "variant": "utc|veg|all",
  "overlap": {"start": "2012-02", "end": "2025-12", "years": [2012, 2013], "excluded_days": 37},
  "bootstrap": {"replicates": 1000, "seed": 20261114},
  "ratio_by_month": [
    {"month": 1, "r": 0.0, "r_lo": 0.0, "r_hi": 0.0, "sum_modis": 0, "sum_viirs": 0, "basis": "month-of-year"}
  ],
  "r_all": {"r": 0.0, "r_lo": 0.0, "r_hi": 0.0},
  "stability": {"spearman_rho": 0.0, "p_value": 0.0, "permutations": 5000, "ratio_trend_flag": false},
  "loyo": {
    "month_of_year":  {"median_abs_log_error": 0.0, "annual_abs_pct_error": 0.0, "interval_coverage_pct": 0.0},
    "single_ratio":   {"median_abs_log_error": 0.0, "annual_abs_pct_error": 0.0, "interval_coverage_pct": null},
    "no_harmonization": {"median_abs_log_error": 0.0, "annual_abs_pct_error": 0.0, "interval_coverage_pct": null},
    "selected_model": "month_of_year",
    "per_year": [{"year": 2013, "month_of_year": 0.0, "single_ratio": 0.0, "no_harmonization": 0.0}]
  },
  "successor": {"pair": {"reference": "VIIRS_SNPP_SP", "scaled": "VIIRS_NOAA20_SP"}, "ratio_by_month": [], "r_all": {}}
}
```

`0.0` values above are placeholders showing type only. `basis` ∈ {`month-of-year`, `annual-fallback`}. `selected_model` is the model with the lowest LOYO median absolute log error; the UI uses it.

## A.3 `fireatlas-calendar-v2` (`GET /api/v2/calendar`)

```json
{
  "schema": "fireatlas-calendar-v2",
  "meta": {
    "region": "norcal", "bbox": [-122.2, 38.8, -120.0, 41.0],
    "series": "harmonized", "unit": "S-NPP-equivalent cell-days", "metric": "cell_days",
    "day": "utc", "types": "veg", "confidence": "all",
    "baseline": {"requested": "2003-2022", "years_used": [2003, 2004], "excluded": [{"year": 2012, "reason": "mixed-collection"}]},
    "calibration_id": "norcal:overlap-ratio-moy-v1:utc|veg|all",
    "method_versions": {"aggregates": "cell-days-1km-epsg6933-v2", "calibration": "overlap-ratio-moy-v1", "availability": "cmr-ledger-v1"},
    "data_class": "authentic", "generated_utc": "…"
  },
  "years": [
    {"year": 2024,
     "days": [{"date": "2024-07-25", "value": 0.0, "low": 0.0, "high": 0.0,
               "estimate_type": "scaled", "source_used": "MODIS_SP", "quality": "degraded",
               "availability": {"MODIS_SP": "available", "VIIRS_SNPP_SP": "missing", "VIIRS_NOAA20_SP": "available"},
               "notice_ids": ["snpp-2024-07-processing-stop"]}],
     "monthly": [{"month": 7, "value": 0.0, "low": 0.0, "high": 0.0,
                  "climatology": {"p10": 0.0, "p50": 0.0, "p90": 0.0, "n_years": 20},
                  "percentile_rank": 0.0, "rank": 1, "n_ranked": 21, "flag": "unusually-high",
                  "degraded_days": 5}],
     "season": {"status": "ok", "start": "2024-06-30", "peak": "2024-07-28", "end": "2024-09-20",
                "length_days": 83, "start_shift_days": -12,
                "critical_periods": [{"start": "2024-07-24", "end": "2024-08-06", "peak_value": 0.0}]}}
  ],
  "provenance": [{"source_id": "MODIS_SP", "bundle_sha256": "…", "doi_or_url": "…"}],
  "limits": ["Detections show where satellites recorded heat; they are not burned area.",
             "A zero on an available day means no detections were recorded, not proof of no fire."]
}
```

Enumerations: `estimate_type` ∈ {`observed`, `scaled`}; `quality` ∈ {`good`, `degraded`, `unknown`, `observed-zero`}; availability state ∈ {`available`, `degraded`, `missing`, `ended`}; `flag` ∈ {`unusually-high`, `unusually-low`, `typical`, `insufficient-history`, `not-comparable`}; `season.status` ∈ {`ok`, `unavailable`}. Dates and numbers in the example are illustrative, not measured.

## A.4 `fireatlas-sensor-notices-v1` (`fireatlas/samples/sensor_notices.json`)

```json
{"schema": "fireatlas-sensor-notices-v1", "method_version": "1",
 "notices": [{"id": "snpp-2024-07-processing-stop", "source_id": "VIIRS_SNPP_SP",
              "start_utc": "2024-07-24T05:28:00Z", "end_utc": "2024-07-28T00:00:00Z",
              "type": "outage", "url": "…", "retrieved_utc": "…", "quote": "…"}]}
```

## A.5 `fireatlas-replay-step-v1` (Tier 2, `GET /api/replay/park-2024/step?as_of=…`)

Fields: `as_of_utc`, `inputs_used[]` (`id`, `kind`, `valid_at`, `available_at`, `age_minutes`), `ensemble` (`members`, `seed_base`, `horizons_h: [6,12,24]`, `burn_probability_tiles` URL template), `sectors[]` (`id`, `rank`, `score`, `U`, `E`, `S`, `V`, `reason`, `geometry`), `assimilation` (`applied`, `perimeter_id`, `ess`), `outcome` (present only when `reveal=true`: `next_perimeter_id`, `jaccard`, `brier`, `hit_rate_top5`), `limits[]`, `banner`.

# Appendix B — Glossary (plain words)

| Term | Meaning |
|---|---|
| Active-fire detection / hotspot | A satellite pixel flagged as containing heat from a fire. Not the fire's size or edge. |
| MODIS | Sensor on NASA's Terra (2000–) and Aqua (2002–) satellites; ~1 km fire pixels. |
| VIIRS | Sensor on Suomi NPP (2012–2026), NOAA-20 (2018–) and NOAA-21 (2022–); 375 m fire pixels, sees more small fires. |
| FIRMS | NASA's Fire Information for Resource Management System, which distributes both. |
| Standard vs NRT | Standard (science-quality, weeks–months later) vs near-real-time (hours). Only standard products build baselines. |
| Cell-day | One 1 km grid cell with ≥ 1 detection on one day. Makes pixel sizes more comparable. |
| Harmonized value | The activity a day would show in S-NPP VIIRS terms, estimated when S-NPP was not flying or missing. |
| r(m) | The ratio of VIIRS to MODIS cell-days in calendar month m during the years both flew. |
| LOYO | Leave-one-year-out: hide a year, fit on the rest, test on the hidden year. |
| Bootstrap interval | Range from recomputing the ratio on many resampled sets of years; shows uncertainty. |
| Degraded / missing day | A day when a sensor was partly or fully unavailable according to NASA notices or granule counts. |
| Critical period | ≥ 5 days in a row when the 15-day activity was above the normal 90th percentile. |
| Burn probability | Share of simulated scenarios in which a place burned. Not a forecast. |
| Entropy (U) | How much the scenarios disagree about a place: 0 = all agree, 1 = split 50/50. |
| TFR | FAA Temporary Flight Restriction over an incident. |

# Appendix C — File map after Tier 1 (target)

| Path | Role |
|---|---|
| `fireatlas/regions.py` | Preset regions, bboxes, fire regime, official links |
| `fireatlas/archive.py` | FIRMS archive import (multi-region) |
| `fireatlas/aggregates.py` | Daily cell-day aggregates (8 variants) |
| `fireatlas/availability.py` + `granules.py` | CMR overpass ledger + notices |
| `fireatlas/calibration.py` | r(m), q(m), bootstrap, LOYO, stability |
| `fireatlas/calendar_v2.py` | Calendar v2 API logic (harmonized series, climatology, seasons) |
| `fireatlas/reference_mcd64.py` | MCD64A1 burned-area comparison |
| `fireatlas/validation_check.py` | Independent recount of harmonized values |
| `fireatlas/briefing.py` | Season context card |
| `fireatlas/sources.py` | Single list of datasets for the Sources page and tests |
| `fireatlas/web.py` | HTTP server and routes |
| `fireatlas/static/index.html`, `app.js`, `calendar-heatmap.js`, `calendar.css` | Home calendar |
| `fireatlas/static/method.html/js/css` | Method & validation |
| `fireatlas/static/data.html/js` | Sources page |
| `fireatlas/samples/aggregates/`, `calibration/`, `availability/`, `sensor_notices.json` | Published data products |
| `scripts/launch_demo.sh`, `smoke_test.sh`, `export_static.py` | Run, verify, publish |
| `docs/HARMONIZATION_METHOD.md`, `DATA.md`, `AI_USE.md`, `TEAM.md` | Documentation |
| `docs/winning-plan/SCORECARD.md` | Live tracker |

Tier 2 adds: `fireatlas/replay.py`, `terrain.py`, `spread.py`, `sectors.py`, `observations_aerial.py`, `assimilate.py`, `fireatlas/static/replay.html/js/css`.
