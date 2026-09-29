## C1 — Direct challenge fit and a working burning-activity calendar (weight 12, now 3, target 5)

**Goal state:** for any preset region (and custom boxes inside it when running locally), a user sees 20+ years of harmonized activity as a calendar, can tell which periods were unusual and which days had missing sensors, and can open the pixels behind any day.

### C1-T1 — Calendar API v2

- **Files:** new `fireatlas/calendar_v2.py`; route `/api/v2/calendar` in `web.py`; `tests/test_calendar_v2.py`.
- **Request parameters (validate each; reject unknown values with HTTP 400):**
  - `region` (id from `regions.py`) **or** `bbox` (must lie inside a loaded region; otherwise 400 "Area outside loaded historical record").
  - `series`: `harmonized` (default) | `modis` | `viirs-snpp` | `viirs-noaa20`.
  - `metric`: `cell_days` (default) | `detections` | `frp_sum`. `harmonized` supports `cell_days` only (the calibration is fitted on cell-days).
  - `day`: `utc` (default) | `solar`. `types`: `veg` (default) | `all`. `confidence`: `all` (default) | `no-low`.
  - `baseline`: `YYYY-YYYY` (default `2003-2022`), minimum 10 years.
  - `years`: `YYYY-YYYY` range to return (default: all loaded).
- **Response (`fireatlas-calendar-v2`; full field list in Appendix A.3):** `meta` (series, metric, day, filters, region, bbox, method versions, calibration id, data class `authentic`); `years[]` each with `days[]` = `{date, value, low, high, estimate_type, source_used, quality, availability: {source: state}}`; `monthly[]` with `value, low, high, climatology: {p10, p50, p90, n_years}, percentile_rank, rank, flag`; `season` per year (C1-T4); `provenance[]`; `limits[]`.
- **Rules:**
  1. Days with no complete export → `value: null`, `quality: "unknown"`.
  2. Zero on a complete, available day → `value: 0`, `quality: "observed-zero"`, and the UI text "no detections recorded — not proof of no fire".
  3. Percentiles use only baseline years that pass version and availability rules (C2-T4, C2-T3); list the years used.
  4. `flag` values: `unusually-high` (≥ 90th percentile), `unusually-low` (≤ 10th), `typical`, `insufficient-history` (< 10 baseline years), `not-comparable`.
- **Acceptance checks:**
  - [ ] Contract test: response validates against Appendix A.3 for `norcal`, every series and variant.
  - [ ] Test: bbox outside loaded regions → 400 with the exact message.
  - [ ] Performance: preset-region response < 800 ms on the dev laptop (log the timing in SCORECARD).

### C1-T2 — Multi-year calendar heatmap (the signature visual)

- **Files:** `fireatlas/static/index.html` (replace the current monthly/day panels inside `#calendar-section`), new `fireatlas/static/calendar-heatmap.js`, `fireatlas/static/calendar.css`.
- **Layout (desktop ≥ 1100 px):**
  - Rows = years (newest at top), columns = day of year (1–366). Each cell 3 px wide × 14 px tall with 1 px gap; year label (Space Grotesk 12 px) at left; month ticks (Jan…Dec) on top.
  - Right of each row: a 120 px horizontal bar showing the **season window** (C1-T4) against the climatological window (thin outline).
  - Colour: sequential log scale from `--unknown`-adjacent dark to ember `#FFB163` (reuse `calendarHeat` in `app.js:374-379`); legend with 5 ticks and the unit.
  - `quality = degraded` → diagonal hatch overlay; `unknown` → flat `--unknown`; `estimate_type = scaled` → small dot in the cell's corner (legend: "estimated from another sensor").
  - Hover tooltip (and keyboard focus): `25 Jul 2024 (UTC) · 415 S-NPP-equivalent cell-days (estimated from MODIS; 95% 350–480) · S-NPP: missing (NASA notice) · MODIS: available`. Numbers come from the API.
  - Click / Enter → opens the **day drawer** (C1-T6).
- **Mobile (< 760 px):** show one year at a time as a 7-column month-grid calendar (reuse the existing `#day-grid` rendering), with a year picker; same colours and states.
- **Render with `<canvas>`** for the grid (≈ 9,000 cells) and an invisible, focusable roving `<button>` for keyboard/screen readers that announces the tooltip text.
- **Acceptance checks:**
  - [ ] Screenshot `evidence/C1-T2-heatmap-norcal.png` shows ≥ 20 years; Park 2024 late July visibly hatched as degraded.
  - [ ] Keyboard: arrows move day/year, Enter opens drawer (manual test noted in SCORECARD).
  - [ ] Renders in < 300 ms after data arrive (performance.now() log).

### C1-T3 — Monthly climatology and anomaly panel

- **Files:** `index.html` (panel under the heatmap), `calendar-heatmap.js` or new `climatology.js`.
- **UI:**
  - 12 monthly bars for the selected year, over a shaded p10–p90 band and a median line from the baseline years.
  - Bars coloured by `flag`: `unusually-high` ember with ▲ icon, `unusually-low` blue with ▼, `typical` neutral, `insufficient-history` hatched gray.
  - Under each flagged month a badge: `Aug 2024 · 97th percentile · rank 1 of 21 years (2003–2022 baseline)`.
  - Caption lines "What this shows: monthly S-NPP-equivalent cell-days compared with the same month in the baseline years." / "What this does not show: burned area, fire counts, or risk."
- **Acceptance checks:**
  - [ ] Badge text is generated only from API fields (test: DOM text equals API values).
  - [ ] With < 10 baseline years the panel shows "Not enough comparable years for an 'unusual' label".

### C1-T4 — Critical periods and season metrics

- **Files:** `fireatlas/calendar_v2.py` (season computation), UI in the heatmap right column + a "Season summary" card.
- **Method (write into `docs/HARMONIZATION_METHOD.md`):**
  1. For each year, daily harmonized values `x_d`. Cumulative share `C_d = Σ_{≤d} x / Σ_year x` (skip null days; if > 10 % of days are null, season metrics are `unavailable`).
  2. `season_start` = first day with `C_d ≥ 0.10`; `season_peak` = centre of the 15-day window with the largest sum; `season_end` = first day with `C_d ≥ 0.90`; `season_length` = end − start + 1.
  3. Climatological season = median start/peak/end over baseline years; report the shift of the selected year in days ("started 12 days earlier than usual").
  4. **Critical period** = runs of ≥ 5 consecutive days where the 15-day centred moving sum exceeds that day-of-year's baseline 90th percentile. List them with start/end dates and peak value.
  5. Regions spanning the southern-hemisphere season: compute the season on a **fire year** starting at the month of lowest climatological activity (store `fire_year_start_month` per region).
- **Acceptance checks:**
  - [ ] Unit test on a synthetic series with a known triangle-shaped season returns the exact start/peak/end.
  - [ ] Southern region test uses the rotated fire year.
  - [ ] UI lists critical periods with dates; clicking one scrolls the heatmap to it.

### C1-T5 — Area selection

- **Files:** `index.html`, `app.js` (AOI controls), `fireatlas/regions.py`.
- **UI:**
  - Region chips above the calendar (one per preset; label + fire regime, e.g., "Punjab–Haryana · crop-residue burning"). The selected chip is highlighted.
  - "Draw a custom box" button (local server only): two clicks on the Leaflet map set the corners; the box must lie inside a loaded region; otherwise show "Outside the loaded historical record. Loaded areas: …".
  - Keep the text field `west,south,east,north` for power users; validate live.
  - The static public site (C12-T6) shows presets only, with the note "Custom areas need the local install (see README)".
- **Acceptance checks:**
  - [ ] Every chip loads a calendar in < 2 s on the public site.
  - [ ] Custom box inside `norcal` works locally; outside shows the message.

### C1-T6 — Day drawer (evidence for one day)

- **Files:** reuse `#evidence-section` logic in `app.js`; update copy.
- **Content, top to bottom:**
  1. Date + day definition (UTC or local solar) + region.
  2. Harmonized value with interval and `source_used`.
  3. Per-source rows: availability state (with notice link), raw pixels, cell-days, product versions.
  4. Small Leaflet map with the day's detections coloured by sensor (MODIS orange squares sized 1 km, VIIRS blue squares 375 m — drawn as approximate nadir squares with the note "approximate nadir size; real footprints grow toward swath edges").
  5. Table of up to 200 original records (existing `/api/observations`), each with a "raw row" expander showing the untouched CSV fields.
  6. Buttons: "Download this day (CSV)", "Recount this day" (calls the verifier, C10-T6).
- **Acceptance checks:**
  - [ ] For Park 2024-07-25 the drawer shows MODIS 603 pixels / 415 cells and S-NPP "missing (NASA notice)".

### C1-T7 — Auto-generated insight text (no free-form LLM text)

- **Files:** `app.js` → replace `#insight-card` generator.
- **Templates (fill only from API fields; if a field is null, drop the sentence):**
  - `"{month} {year} in {region}: {value} S-NPP-equivalent cell-days ({percentile}th percentile of {n} baseline years, {baseline})."`
  - `"{k} day(s) this month had a missing or degraded sensor; their values are estimates."`
  - `"Season started {abs(shift)} days {earlier|later} than the {baseline} median."`
  - Always end with: `"Detections show where satellites recorded heat; they are not burned area or proof that no fire occurred elsewhere."`
- **Acceptance checks:** [ ] Unit test (Node) renders templates from a fixture and drops sentences with null fields.

### C1-T8 — Exports

- CSV and JSON download of the current calendar view with a header block (`# series=…, region=…, method=…, calibration_id=…, generated_utc=…, citation=…`). Keep the study ZIP (`/api/study`) and add `calibration.json` + `availability.json` to it; extend `fireatlas/study.py` verifier to check them.
- **Acceptance checks:** [ ] `uv run python -m fireatlas.study <zip>` verifies a v3 bundle including calibration and availability files.

**Master prompt (C1):**

```text
TASK C1-T<n>. Read docs/winning-plan/src/05-calendar-validation.md "C1-T<n>" and
Appendix A.3 (API schema) in docs/winning-plan/src/09-appendix.md. Read the existing
files listed before editing. Build exactly the described API/UI. All on-screen numbers
must come from API responses; never hardcode dates, counts or region-specific cases.
Keep the existing design system (fireatlas/static/design.css). Add tests (Python for API,
Node for pure JS functions). Run the full test suite. Start the server and capture a
screenshot of the new UI at 1440x900 and 390x844 into docs/winning-plan/evidence/.
Output the REPORT block.
```

**C1 checklist:** [ ] T1 API v2 · [ ] T2 heatmap · [ ] T3 climatology · [ ] T4 seasons/critical periods · [ ] T5 area selection · [ ] T6 day drawer · [ ] T7 insight text · [ ] T8 exports · [ ] a first-time user answers "Was August 2024 unusual here?" in < 60 s (user test, C11-T8)

---

## C10 — Independent validation, retrospective replay, leakage control and baselines (weight 8, now 2, target 4 Tier 1 / 5 Tier 2)

### C10-T1 — Publish the calibration validation

- Show the LOYO results (C2-T5) on `/method.html` → section "Does harmonization work?": a table per region (median abs log error, annual % error, interval coverage) for **month-of-year ratio vs single ratio vs no harmonization**, and a scatter plot (log–log) of predicted vs observed monthly S-NPP cell-days for held-out years with the 1:1 line.
- [ ] Numbers on the page equal `samples/calibration/<region>.json` (test).

### C10-T2 — Sensor-transition step test

- **Question:** does the harmonized series jump at 2012 when S-NPP enters?
- **Method:** for each region, compare the observed annual ratio `ΣV_y/ΣM_y` for 2012–2014 against the bootstrap 95 % interval of `r_all` fitted on 2015–2025 only. Report `step_ok = inside interval`. Also plot MODIS-only, naive stitched series (MODIS before 2012, S-NPP after), and harmonized series together for 2005–2020; the naive series will show the artificial jump.
- [ ] Figure `evidence/C10-T2-<region>.png` and table in SCORECARD.

### C10-T3 — Independent reference: NASA MCD64A1 burned area

- **Data (human + script):** MODIS/Terra+Aqua Burned Area Monthly L3 Global 500 m, **MCD64A1 Collection 6.1**, from LP DAAC (Earthdata Login required). VERIFY the product page and version before download. Tools: NASA AppEEARS area request (region polygon, 2003–2025, band `Burn Date`) or direct HDF tiles.
- **Method:** monthly burned area km² inside each region (count pixels with Burn Date > 0 × pixel area). Spearman correlation across all months 2003–2025 between burned area and (a) harmonized cell-days, (b) naive stitched series, (c) MODIS-only. Also correlation of **year-over-year changes** across the 2011→2012 boundary.
- **Honest interpretation text:** "Burned area is an independent product with different sensitivity (small fires and crop burns are often missed). Agreement supports, but does not prove, the harmonized record."
- [ ] Results table in SCORECARD and on `/method.html`. [ ] Script `fireatlas/reference_mcd64.py` + test on a tiny synthetic raster.

### C10-T4 — Cross-check with NOAA HMS (existing data)

- Use the bundled NOAA HMS July 2021–2024 slice: daily Spearman correlation between HMS VIIRS cell-days and FIRMS S-NPP cell-days in the overlapping box. Present as "independent processing chain check".
- [ ] Table on `/method.html` "Advanced analysis".

### C10-T5 — Fix native MODIS mask reading and finish the reconciliation

- **Observed failure:** 16/17 MODIS granules fail with "Expected one ('Latitude','latitude') layer, found 0" (`masks.py:97-99`).
- **Steps:**
  1. Run `gdalinfo NASA_data/fire_masks/MOD03.A2025185.0510.061.*.hdf | grep -i subdataset` and paste the output. Check `gdalinfo --formats | grep -i hdf4` to confirm the HDF4 driver exists.
  2. Adapt `native_layer` matching to the real subdataset names printed (do not guess). If HDF4 is missing, document the install and mark BLOCKED.
  3. Reprocess Park and Grove into `data/validity_masks.sqlite3`; reach the ≥ 98 % reconciliation target or report the actual rate.
  4. Human review: two team members independently review the 30 deterministic samples (existing queue) and record decisions in `docs/winning-plan/evidence/C10-T5-review.csv` (`sample_id, reviewer, decision, note`). Report agreement.
- [ ] Validation gates on `/method.html` show real statuses, not "pending".

### C10-T6 — Recount verifier for calendar v2

- Extend `fireatlas/validation_check.py` to recompute, from exported aggregates + calibration + availability files, every harmonized daily value and interval (independent implementation of the formula in C2-T5 step 5). Expose a "Recount" button in the day drawer.
- [ ] Test: tampering with one aggregate value makes the recount fail with a clear message.

### C10-T7 — Leakage rules (needed for C1 anomalies and Tier 2)

- Baselines only use years **before** the target year (already enforced for monthly baselines; enforce for percentiles and season climatology too).
- Calibration used for a pre-2012 estimate may use the full overlap period (it is a fixed method parameter, disclosed as such). Document this.
- [ ] Test: requesting 2015 with baseline `2003-2022` returns 400 or automatically restricts to `2003-2014` (choose one and document it; recommended: restrict and state it).

**Master prompt (C10):**

```text
TASK C10-T<n>. Read docs/winning-plan/src/05-calendar-validation.md "C10-T<n>".
Implement the method exactly. Report metrics only from your own runs, with the command
used. If a metric is bad, report it and show it in the UI honestly; do not tune the
method on the held-out years. Add tests. Output the REPORT block.
```

**C10 checklist (Tier 1):** [ ] T1 · [ ] T2 · [ ] T3 · [ ] T4 · [ ] T5 · [ ] T6 · [ ] T7

---

## C11 — Interface clarity and reliability of the judge demonstration (weight 4, now 3, target 5)

### C11-T1 — Home page structure (final order, top to bottom)

1. **Header**: logo "fireatlas" (keep), nav from section 3.1, right side: GitHub link icon.
2. **Hero** (max 80 vh):
   - Eyebrow: `NASA SPACE APPS 2026 · HARMONIZATION OF MODIS AND VIIRS HOT SPOTS` (names the challenge category — rubric item 9).
   - H1: `25 years of NASA fire detections. One calendar.` (replace the year count with the real span once data are loaded).
   - Sub (≤ 30 words): `MODIS and VIIRS see fire differently, and both are retiring. FireAtlas joins them into one burning-activity calendar—with missing days, uncertainty, and the original pixels in view.`
   - Primary button `Open the calendar` → scrolls to calendar; secondary link `How harmonization works` → `/method.html`.
   - Right side: **sensor timeline graphic** (C11-T3) instead of the heavy globe. The globe may stay only if it loads in < 2 s and shows the preset regions (clicking a region selects it); otherwise remove it (R7/R8).
3. **Region chips + calendar heatmap** (C1-T2, C1-T5).
4. **Selected-year panel**: climatology bars (C1-T3) + season summary + critical periods (C1-T4) + insight text (C1-T7).
5. **Day drawer** (C1-T6), opens inline.
6. **"Can I trust this?" strip**: three cards linking to `/method.html` anchors — "Missing sensors are marked" · "Held-out error: X %" (from calibration file) · "Every number traces to a NASA pixel".
7. **Footer**: data citations (short), licence, AI-use note link, team names, "Not an operational fire-management tool".

### C11-T2 — Remove visual noise

- Delete the floating globe console (`.console-tabs`, wildfire toggle, satellite-signals switch) with R1/R7.
- Max two font sizes per card; no more than one animated element on screen at a time; respect `prefers-reduced-motion` (already supported in `design.css`).

### C11-T3 — Sensor timeline graphic (reused on home and method page)

- Horizontal timeline 2000 → 2027 with one lane per platform: Terra MODIS (2000-02 → ~2027-01), Aqua MODIS (2002-07 → ~2026-08), S-NPP VIIRS (2012-01-20 → delivery end 2026-11-01), NOAA-20 VIIRS (2020-01-01 → ), NOAA-21 VIIRS (2024-01-17 → ). For NOAA-20 and NOAA-21 these are FIRMS record start dates, not launch dates; label the lanes "in FIRMS since". Dates: FIRMS FAQ and NASA/NOAA notices (VERIFY each and cite in a tooltip).
- Outage ticks from `sensor_notices.json`; the overlap window used for calibration shaded; "harmonized unit: S-NPP-equivalent" label.
- [ ] Generated from `sensor_notices.json` + a `platforms.json` file; no hardcoded dates in JS.

### C11-T4 — Method & validation page (`/method.html`) sections

1. "An observation becomes a day" (keep existing workflow visual).
2. "Two sensors, different eyes" — pixel size comparison (keep `validity.js` drawSensors), plus the calibration ratio per region as a bar chart.
3. "Missing sensors are marked" — sensor timeline + Park 2024 outage example from the ledger.
4. "Does harmonization work?" — C10-T1 table + scatter; C10-T2 step figure; C10-T3 burned-area correlation.
5. "Trace any number" — existing recount (keep) + calendar v2 recount.
6. "Advanced analysis" (collapsed) — merged Research Lab content (R10), HMS cross-check.
7. "Limits" — bullet list (hotspot ≠ perimeter/burned area; complete export ≠ clear pass; confidence not comparable across sensors; not for tactical use — quote FIRMS/ARSET "not recommended for use at a tactical level").

### C11-T5 — New 4-step guided tour (authentic data)

1. "Pick a place" → highlights region chips (auto-selects `norcal`).
2. "Read 25 years at once" → highlights the heatmap, points at 2024.
3. "Was it unusual?" → highlights the August/July badge and percentile.
4. "Check the evidence" → opens Park 2024-07-25 drawer showing the S-NPP gap and raw pixels.
- Replace `story.js`; each step uses real API data; "Skip tour" always visible.

### C11-T6 — Empty, error and loading states (write every string)

| State | Text |
|---|---|
| Loading calendar | `Loading {region} · {years}…` (skeleton rows, no spinner longer than 1 s without text) |
| API error | `The calendar could not load. Check that the server is running, then retry.` + Retry button |
| Outside record | `No historical record is loaded for this area. Loaded areas: {list}.` |
| Insufficient history | `Fewer than 10 comparable years — no "unusual" label is given.` |
| Degraded day | `A sensor was missing or degraded on this day; the value is estimated from {source}.` |

### C11-T7 — Reliability for judging

- Public static site (C12-T6) must work with **no server and no third-party API** except map tiles; if tiles fail, the calendar still works.
- Test in Chrome, Firefox, Safari (or WebKit via Playwright) at 1440×900 and 390×844; record results in SCORECARD.
- Lighthouse (Chrome DevTools) on the public URL: Performance ≥ 80, Accessibility ≥ 95. Record scores.

### C11-T8 — Five-person usability test (counts for UX and Impact)

- Ask 5 people who never saw the app (at least one land-management, geography or environmental-science person if possible) to do three tasks without help: (1) "Find the most active month of 2024 in Northern California." (2) "Was it unusual compared with earlier years?" (3) "Find a day where a satellite was missing." Record time, success, and one quote each in `evidence/C11-T8-usability.md` (first names or initials only, with consent; no minors' names or photos).
- [ ] ≥ 4/5 succeed on every task; fix the top problem and retest one person.

**Master prompt (C11):**

```text
TASK C11-T<n>. Read docs/winning-plan/src/05-calendar-validation.md "C11-T<n>" and
section 3.2 (visual rules) in 03-cleanup.md. Implement the exact structure and copy.
Use only data from the APIs. Keep accessibility (keyboard, contrast, reduced motion).
Capture before/after screenshots at 1440x900 and 390x844 into
docs/winning-plan/evidence/. Run tests. Output the REPORT block.
```

**C11 checklist:** [ ] T1 home · [ ] T2 noise removed · [ ] T3 timeline · [ ] T4 method page · [ ] T5 tour · [ ] T6 states · [ ] T7 reliability · [ ] T8 usability test
