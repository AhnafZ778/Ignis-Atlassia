# 4. Data and harmonization

Build this only for `norcal` and `punjab-haryana`, using the boxes and dates in section "The goal". One variant only: UTC day, FIRMS type 0 or missing (`veg`), all confidence values.

## Perfected-plan measurement contract

The primary published value is **VIIRS-equivalent active-fire cell-days on a common 1 km
grid**. Native VIIRS 375 m detections remain available as a detail layer. A raw MODIS pixel
count and a raw VIIRS pixel count are never compared as if they were the same unit. The current
FIRMS implementation assigns detection centroids to the versioned equal-area grid; it must not
be described as native fire-mask resampling until standard mask products have been decoded and
checked.

For every source and UTC day:

1. retain the original row, native pixel scale, product version, confidence, acquisition time,
   FRP, request metadata, retrieval date, file hash, and row count;
2. exclude type values outside `0` or missing from the calendar and count the exclusions;
3. deduplicate within that sensor and UTC day before aggregation;
4. aggregate VIIRS 375 m to the common 1 km cell for the shared comparison while retaining the
   375 m source rows;
5. store source-specific cell-days, raw pixel counts, and raw FRP sums separately;
6. choose one reference observation for the harmonized value and expose the other sensor for
   comparison; never add both sensors into one activity count.

The visible quality vocabulary is `observed`, `scaled`, `unknown`,
`documented_processing_gap`, and `zero_detections_exported`. A complete zero export means zero
eligible rows in that export; it does not establish a clear pass, cloud-free observation, or no
fire. Missing or incomplete windows remain unknown. FRP is secondary context in MW/day and is
never added to the activity measure.

## C2-T1 — Import the archives

- **Files:** `fireatlas/regions.py` (new), `fireatlas/archive.py`, `tests/test_archive.py`.
- **Steps:**
  1. `regions.py` holds the two regions: id, name, bbox, and one sentence on the fire regime.
  2. Import a FIRMS CSV from a folder that contains `request.json` with `product` (`MODIS_SP` or `VIIRS_SNPP_SP`), `start_date`, `end_date`, and `bbox`. Reject near-real-time files.
  3. A month is complete only when the request covers that whole month and the region box. Keep the existing hash and row-count checks.
  4. Remove the rule that a file must start on 1 July (`archive.py` around the July-1 check).
- **Checks:**
  - [x] Re-importing the existing Northern California 2022–2025 files still yields 30,823 rows (`tests/test_archive.py::test_packaged_nasa_pair_loads_on_fresh_database`).
  - [x] A month that sticks out of the request is stored as partial, not complete (`tests/test_archive_requests.py::test_partial_date_request_cannot_create_complete_export_window`).
  - [x] When an older CSV lacks its original FIRMS request form, its sidecar is `reconstructed-rows-only`; inferred dates never create complete export windows (`tests/test_archive_requests.py::test_reconstructed_file_dates_import_positive_rows_without_claiming_complete_coverage`).
  - [x] Missing annual windows are listed separately from supplied row-only archives in `docs/NASA_DATA_IMPORT.md`; missing dates remain unknown.

## C2-T2 — Daily cell-days

- **Files:** `fireatlas/aggregates.py`, `tests/test_aggregates.py`, output `fireatlas/samples/aggregates/<region>.json.gz`.
- **Steps:** For each UTC day and each series, store cell count, raw pixel count, and FRP sum. Schema `fireatlas-daily-aggregates-v1` in the appendix. Include the input file SHA-256 and `method_version`.
- **Checks:**
  - [x] For Northern California, all 31 July 2024 MODIS daily cell counts match the existing calendar using the authentic bundled NASA rows (`tests/test_archive.py::test_packaged_nasa_pair_loads_on_fresh_database`).
  - [x] A row with FIRMS `type` 2 is excluded (`tests/test_aggregates.py::test_daily_aggregate_excludes_type_two_and_preserves_zero_day`).

## C2-T3 — Missing-satellite days

- **Files:** `fireatlas/availability.py`, `fireatlas/samples/sensor_notices.json`, `tests/test_availability.py`.
- **Steps:**
  1. Seed `sensor_notices.json` with a dated, sourced S-NPP product notice. The verified 2024 interval is 2024-07-24 05:24 UTC through 2024-07-29 15:18 UTC, inclusive. The source labels a product-processing outage; it does not establish a no-fire condition or cloud mask. Preserve the exact interval, source URL, retrieval date, and a quote of 25 words or fewer.
  2. Never infer satellite unavailability from a zero FIRMS count. A complete export with zero rows is `zero_detections_exported`; its pass, cloud and observation opportunity remain `unknown`. An incomplete export is `unknown_export`. A source notice intersecting a day is `documented_processing_gap`, even if the export contains some points.
  3. Remove hardcoded Park Fire date checks from `app.js`. A date hatch and explanation must come from the source-notice ledger; no-pass and cloud states stay unknown unless native coverage inputs establish them.
- **Checks:**
- [x] 2024-07-25 in Northern California is flagged `documented_processing_gap` for Suomi NPP; the sourced notice ID and URL are retained (`tests/test_validity.py::test_real_calendar_api_and_day_drawer_keep_nasa_source_evidence`, `tests/test_aggregates.py::test_zero_exports_and_notices_are_not_called_sensor_pass_or_missing_fire`).
- [x] A complete day with zero Suomi NPP rows is `zero_detections_exported`, with observation opportunity unknown (`tests/test_aggregates.py::test_zero_exports_and_notices_are_not_called_sensor_pass_or_missing_fire`).
- [x] A complete day with Suomi NPP rows and no notice is `detections_in_export`, with observation opportunity still unknown (`tests/test_aggregates.py::test_zero_exports_and_notices_are_not_called_sensor_pass_or_missing_fire`).

## C2-T5 — The ratio that joins the sensors

- **Files:** `fireatlas/calibration.py`, `tests/test_calibration.py`, `fireatlas/samples/calibration/<region>.json`.
- **Method, implement exactly:**
  1. Overlap months are complete months from 2012-07 through the last month both products have, skipping only dates intersecting a documented S-NPP product-processing gap. Complete zero-detection exports remain observed zeros.
  2. For month-of-year `m`, `r(m) = (sum of Suomi NPP cell-days) / (sum of MODIS cell-days)` over those overlap years. If the MODIS sum for that month is under 30, use the all-year ratio instead and set `basis` to `annual-fallback`.
  3. Uncertainty: resample overlap years with replacement 1,000 times using `random.Random(20261114)`. The 95% interval is the 2.5th and 97.5th percentiles.
  4. For dates before the downloaded S-NPP archive starts (2024 plan: 2012-07-01), and on dates intersecting a documented S-NPP product outage: harmonized value = MODIS cell-days × `r(m)`, `estimate_type` = `scaled`, `source_used` = `MODIS_SP`. A complete S-NPP export with zero eligible records is an observed zero-detection record, not a missing sensor. An incomplete S-NPP export outside a documented outage is `unknown`, not an estimate.
  5. Leave-one-year-out: refit without each overlap year, predict that year's Suomi NPP monthly totals, and record median absolute log error `median(|ln((predicted+1)/(actual+1))|)`, annual absolute percent error, and how often the actual falls inside the interval. Compute the same error for `r = 1` and for one all-year ratio.
  6. The calendar uses whichever of the three has the lower leave-one-year-out log error. Say which one on the method page.
- **Checks:**
  - [x] Synthetic test where Suomi NPP = 4 × MODIS: `r(m)` is 4 and held-out error is 0 (`tests/test_calibration.py::test_fixed_ratio_has_zero_held_out_error_and_reproducible_seed`).
  - [x] Both regions have calibration JSON artifacts; the web test loads and schema-checks each (`tests/test_web.py::test_calibration_artifacts_are_downloadable_and_method_page_uses_them`).
  - [x] Method-page values are loaded from the selected calibration JSON; the HTML contains placeholders and the script reads model metrics from the JSON.

### Perfected validation additions

The ratio is not a license to call the sensors equally sensitive. Before a perfected-plan claim,
the reviewer must also check:

- daily and monthly common-grid totals against the retained source rows after deduplication;
- MODIS-only, VIIRS-only, both, gap, and unknown categories on complete and incomplete days;
- raw FRP sums per source against the same filtered rows, without cross-sensor addition;
- sensitivity to the common-grid rule and to confidence/type filters;
- leave-one-year-out performance against no correction, one annual ratio, and the selected
  model, with interval coverage shown even when it is weak;
- MCD64A1 Collection 6.1 only as lagged burned-area context, never active-fire ground truth.

The repository now contains dated MCD64A1 granules and a hash-bound report, but no independent
sign-off. The method page shows their mapped Burn Date counts only as lagged context and keeps
the limits sentence; it must not treat those values as active-fire truth or a burned-area overlay.

## C2-T6 — Sources

Add `docs/DATA.md` rows for both products: name, version, URL, date range, retrieval date, licence, SHA-256 of the imported files. Use this FIRMS acknowledgement, and re-check it before submission: *"We acknowledge the use of imagery from the NASA LANCE FIRMS (https://earthdata.nasa.gov/firms), part of the NASA Earth Science Data and Information System (ESDIS)."*

**Master prompt:** `TASK C2-T<n>. Follow docs/winning-plan/src/04-gate1-and-data.md for that task only. Use the method as written. Output the REPORT block.`
