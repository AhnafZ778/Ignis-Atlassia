# 5. Calendar, proof, and the home page

## Perfected-plan judge path

Keep the existing globe and controls at the top. Under it, follow **See → Compare → Verify →
Share**. The calendar must communicate the result before the user opens the method text:

1. **Verdict:** percentile/comparable years, estimated days, unknown days, and official links.
2. **Sensor Bridge:** MODIS raw source values → common 1 km transformation → VIIRS-equivalent
   value, with MODIS-only, VIIRS-only, both, and gap/unknown states visible.
3. **Heatmap:** years by UTC day, with observed solid, scaled amber hatch, unknown crosshatch,
   documented gap purple hatch, and complete zero export labelled. Every pattern has a text
   label and keyboard-readable description.
4. **Evidence drawer:** source values, native scales, FRP in MW/day per sensor, quality state,
   notice, source rows, version, hash, and a download action.
5. **Share card:** selected value, state, versions, source inputs/hashes, limits, and a URL
   generated from the same API/static JSON. It is a briefing artifact, not a new result.

The MCD64A1 panel is shown when an authentic dated, hash-bound check exists. It labels the
result as lagged, analytical context and keeps the active-fire limits visible while independent
review is pending. Without a dated check the page says **ACTIVE FIRE ONLY** and links to NASA's
product record. Do not show a fire perimeter, fire-free area, or validity percentage based on
the absence of that product.

## C1-T1 — Calendar API

- **File:** `fireatlas/calendar_v2.py`. Route `GET /api/v2/calendar`.
- **Parameters:** `region` (`norcal` or `punjab-haryana` only), `year`. Reject anything else with HTTP 400.
- **Response:** schema `fireatlas-calendar-v2` in the appendix. For each day: harmonized value, low, high, `estimate_type`, `source_used`, `quality` (`good` for complete S-NPP exports, `degraded` for a MODIS estimate outside the downloaded S-NPP window or within a documented product gap, `unknown` for incomplete exports or unvalidated scaling), `evidence_state`, `coverage_state`, `sensor_bridge`, and source-separated `frp_mw_day`. A scaled value during a documented gap has `evidence_state=scaled` and `coverage_state=documented_processing_gap`; the UI says “gap · scaled estimate”. A complete export with zero records is an observed zero-detection day; pass/cloud coverage stays unknown. For each month: value, percentile among baseline years, rank, `n_years`, and `flag` (`unusually-high` at or above the 90th percentile, `unusually-low` at or below the 10th, `typical`, or `insufficient-history` when `n_years` < 10).
- **Baseline:** years from 2010 through the year before the selected year, and only years whose MODIS collection matches the selected year. List excluded years.
- **Checks:**
  - [x] Northern California 2024 returns 12 months from authentic bundled NASA records through `/api/v2/calendar` (`tests/test_validity.py::test_real_calendar_api_and_day_drawer_keep_nasa_source_evidence`).
  - [x] A third region id returns 400 (`tests/test_web.py::test_region_calendar_api_is_named_scoped_and_never_fabricates_empty_data`).

## C1-T2 — Heatmap

Under the globe, years as rows and days as columns, 2010 through the latest complete year. An incomplete export, a documented product-gap interval, and a complete zero-detection export have distinct patterns and labels. A daily outage hatch means the UTC day intersects the notice; it does not mean the whole day had no S-NPP data. Hover or keyboard focus reads the date, the value, the unit "VIIRS-equivalent active-fire cell-days", and whether the value is observed, scaled, unknown, a documented processing gap, or a complete zero export.

- [x] Screenshot `docs/winning-plan/evidence/C1-T2-norcal.png` shows the 2010s, unknown export months, and the documented S-NPP outage interval intersecting 24–29 July 2024 with partial endpoint days marked distinctly. Captured from the live local archive on 2026-09-29 at 1440 CSS px / DPR 2; includes the July 2024 daily grid and full historical legend.

## C1-T3 — The verdict sentence

First text in the calendar panel. Templates, filled only from the API:

- `{area}, {month} {year}: {percentile}th percentile of {n} comparable years. {k} days are MODIS estimates before the downloaded S-NPP period or during a documented product gap.`
- If `n` < 10: `{area}, {month} {year}: comparison not usable. Only {n} comparable years.`

Under the sentence, two links:

- Northern California: CAL FIRE incidents `https://www.fire.ca.gov/incidents` and InciWeb `https://inciweb.wildfire.gov`
- Punjab–Haryana: NASA FIRMS, plus a state source only if you loaded the page and got HTTP 200. Otherwise the line is `No verified official local source listed.`

- [x] `tests/test_calendar_v2.py::test_comparison_verdict_names_estimate_reason_and_omits_zero_estimate_clause` covers the percentile and insufficient-history templates, names the two MODIS-estimate reasons, and omits the estimate clause at zero.
- [x] Live API and browser check for July 2024, Northern California: the visible verdict exactly matches `meta.verdict`; CAL FIRE and InciWeb links sit directly beneath it. Screenshot: `docs/winning-plan/evidence/C9-T1-verdict.png`.

## C1-T4 — Critical dates

For each year, using harmonized daily values and skipping missing months: season start is the first day whose cumulative share reaches 10%, season end is the first day it reaches 90%, and the peak is the centre of the 15-day window with the largest sum. If more than 10% of days are missing, season status is `unavailable`. Show start, peak, and end next to the verdict.

- [x] A synthetic triangle-shaped year returns the known start, peak, and end (`tests/test_calendar_v2.py::test_triangle_returns_known_ten_percent_dates_and_fifteen_day_peak`).

## C1-T6 — Day drawer

Clicking a day opens the existing evidence drawer: the harmonized value, each sensor's availability, and up to 200 original rows. The button label remains a download of that day's CSV.

- [x] 25 July 2024 returns original MODIS source rows and a documented S-NPP processing gap; the drawer links to the NASA notice from the API and does not treat missing rows as proof of no fire or no pass (`tests/test_validity.py::test_real_calendar_api_and_day_drawer_keep_nasa_source_evidence`, `tests/test_aggregates.py::test_zero_exports_and_notices_are_not_called_sensor_pass_or_missing_fire`, `tests/test_web.py::test_calendar_map_observations_and_exports`).

## C10-T1 and C10-T2 — Method page

On `/method.html`, show one section, "Does the scale hold up?":

- The leave-one-year-out model comparison from the calibration JSON: monthly-ratio error, single-ratio error, no-harmonization error, and which one the app uses. The existing horizontal comparison graphic is the visual presentation of those values.
- One line for the 2012 step: the 2012 annual Suomi NPP / MODIS ratio, and whether it sits inside the 95% interval fitted on the other overlap years.

The perfected plan adds the compact Sensor Bridge and FRP audit to the existing method comparison;
it does not add a second globe, a spread forecast, or an operational recommendation. Any MCD64A1
context remains a lagged corroboration note with its own source and date.

- [x] The model errors, annual errors, selected model, and interval-coverage values displayed for both regions match the corresponding calibration JSON (`uv run --with playwright python scripts/verify_calibration_ui.py --base http://127.0.0.1:8765`; captures: `docs/winning-plan/evidence/C10-T1-calibration-norcal.png` and `C10-T1-calibration-punjab-haryana.png`).
- [ ] The 2012 step is still pending because row-only legacy imports do not establish complete monthly source exports; do not show a ratio as a measured complete-window result until that input gate passes.

## C11-T1 — Home page

Order, top to bottom: header, **existing globe with all of its controls**, verdict sentence and official links, Sensor Bridge, daily heatmap/calendar, critical dates and method context, source-row drawer, share card, link to the method page, and footer with the limits sentence from section 6. Add the challenge name `Harmonization of MODIS and VIIRS Hot Spots` in the eyebrow. Do not remove or edit globe controls to make room.

**Master prompt:** `TASK <id>. Follow docs/winning-plan/src/05-calendar-validation.md for that task only. Numbers on screen come from the API. Output the REPORT block.`
