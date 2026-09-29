# 5. Gate 1 — Repository integrity (C12-T1 to C12-T3)

Do these before any feature work. They take under two hours.

### C12-T1 — Commit and push the uncommitted work

- **Goal:** GitHub contains everything the local app uses.
- **Steps:**
  1. `git status --short` and save the output to the task report.
  2. Confirm no secrets: `rg -n "MAP_KEY=|api_key|token" --hidden -g '!**/.venv/**'` must show no real keys.
  3. Stage code, tests, docs and small samples: `git add fireatlas tests docs scripts pyproject.toml uv.lock README.md PRD.md .gitignore`.
  4. Check sample sizes: `du -h fireatlas/samples/*` — each file must be < 50 MB (GitHub hard limit is 100 MB).
  5. Commit: `C12-T1: commit authentic MODIS/VIIRS pipeline, validity cases and method page`. Push to `origin/main`.
- **Acceptance checks:**
  - [ ] `git status` shows no modified tracked files and no untracked files under `fireatlas/` or `tests/`.
  - [ ] `git log origin/main -1` equals local `HEAD`.
  - [ ] Repository is **public** on GitHub (Settings → General → Danger zone → visibility). Record the URL in SCORECARD.

### C12-T2 — Fresh-clone smoke test and Linux launcher

- **Files:** `scripts/launch_demo.sh` (new), `scripts/smoke_test.sh` (new), `.github/workflows/ci.yml` (new).
- **Steps:**
  1. `scripts/launch_demo.sh`: `#!/usr/bin/env bash`, `set -euo pipefail`, `uv sync`, then `uv run python -m fireatlas.web --db data/fireatlas.sqlite3 --port "${PORT:-8000}"`.
  2. `scripts/smoke_test.sh`: clones the repo into a temp directory, runs `uv sync`, starts the server on port 8799 in the background, waits for `/api/meta` to return HTTP 200 (max 60 s), then checks: `/` returns 200; `/api/calendar?year=2024&series=joint&bbox=-122,39.5,-121.3,40.5` returns JSON whose July `detected_cell_days` equals the value recorded in SCORECARD "Ground truth"; kills the server; exits non-zero on any failure.
  3. CI workflow on `ubuntu-latest`: checkout, install uv (`astral-sh/setup-uv`), `uv sync`, `uv run python -m unittest discover -s tests`, `node --check` on every `fireatlas/static/*.js`.
- **Acceptance checks:**
  - [ ] `bash scripts/smoke_test.sh` exits 0 on a machine that never had the repo.
  - [ ] CI badge green on GitHub; badge added to README.

### C12-T3 — Declare every dependency

- **Steps:**
  1. Add to `pyproject.toml` an optional extra: `[project.optional-dependencies] masks = ["numpy>=1.24,<3"]` and document that GDAL (with HDF4 and netCDF drivers) must come from the system (`apt install gdal-bin python3-gdal` or conda-forge). Do not pip-install GDAL in CI.
  2. `fireatlas/masks.py` must fail with a clear message if `osgeo` is missing: "Native mask processing needs GDAL with HDF4 support; see docs/DATA.md".
  3. Pin upper bounds already present; run `uv lock` and commit `uv.lock`.
- **Acceptance checks:**
  - [ ] `uv sync` on a clean machine works without GDAL; core tests pass.
  - [ ] Mask tests are skipped (not failed) when GDAL is missing (`unittest.skipUnless`).

**Master prompt (Gate 1):**

```text
TASK C12-T1..T3. Follow docs/winning-plan/src/04-gate1-and-data.md section 5 exactly.
Do not change application behaviour. Paste git status before and after, the push result,
the smoke-test output, and the CI run URL. Output the REPORT block.
```

---

# 6. Tier 1 — Challenge core

## C2 — Authentic NASA data, provenance and scientifically defensible harmonization (weight 12, now 3, target 5)

**Why it matters:** Validity and Relevance are 40 of the 100 headline judge points. This category is where FireAtlas can be clearly better than competitors.

**Definitions used everywhere (write them into `docs/HARMONIZATION_METHOD.md`):**

- **Source series:** `MODIS_SP` (Terra + Aqua, Collection 6.1 standard, MCD14ML), `VIIRS_SNPP_SP` (VNP14IMGML, Collection 2 standard), `VIIRS_NOAA20_SP` (VJ114IMGML, standard). NRT series never enter baselines.
- **Cell-day:** a 1 km EPSG:6933 grid cell with at least one detection centroid of the given series on that day (existing definition, `core.py:175-212`).
- **Harmonized unit:** **"S-NPP-equivalent cell-days"**. S-NPP is the middle of the record (2012–2026) and bridges MODIS (past) and NOAA-20 (future).
  - 2012-01-20 → 2026-10-31: observed `VIIRS_SNPP_SP` cell-days when S-NPP is available that day.
  - Before 2012-01-20: `MODIS_SP cell-days × r(m)` where `r(m)` is the month-of-year VIIRS/MODIS ratio (C2-T5).
  - S-NPP missing day in 2012–2019: `MODIS × r(m)`, flagged `fallback-modis`.
  - S-NPP missing day in 2020+ or after 2026-11-01: `NOAA-20 cell-days × q(m)` where `q(m)` is the S-NPP/NOAA-20 ratio from their overlap, flagged `fallback-noaa20` / `successor-noaa20`.
  - Every harmonized value carries `source_used`, `estimate_type` (`observed` | `scaled`), and a 95 % interval (equal to the value when observed).

### C2-T1 — Generalize the FIRMS archive importer (multi-region, multi-year)

- **Files:** `fireatlas/archive.py`, new `fireatlas/regions.py`, `tests/test_archive.py`.
- **Steps:**
  1. Create `fireatlas/regions.py` with a `REGIONS` dict. Each region: `id`, `name`, `bbox` (west, south, east, north), `fire_regime` (text), `why` (one sentence). Start with these five; the executor must **VERIFY each bbox on a map** (e.g., open the bbox in geojson.io) and adjust only if it clearly misses the intended area:
     - `norcal` — Northern California (Park Fire 2024): `-122.2, 38.8, -120.0, 41.0` (existing bundle area).
     - `punjab-haryana` — crop-residue burning, India: `73.8, 29.5, 77.6, 32.6`.
     - `rondonia` — Amazon deforestation fires, Brazil: `-66.8, -13.7, -59.8, -7.9`.
     - `top-end-au` — tropical savanna, Northern Territory, Australia: `129.0, -17.0, 138.0, -11.0`.
     - `california` — whole state (optional, large): `-124.5, 32.5, -114.1, 42.0`.
  2. Replace the fixed constants `BBOX` and `EXPECTED_YEARS` (`archive.py:26-28`) with arguments `--region <id>` and a `request.json` file inside each downloaded `DL_FIRE_*` folder. `request.json` fields (typed by the human from the FIRMS request e-mail): `request_id`, `product` (`MODIS_SP` | `VIIRS_SNPP_SP` | `VIIRS_NOAA20_SP`), `start_date`, `end_date`, `area` (bbox or "country:XXX").
  3. A month is `complete_export = true` only if the whole month lies inside `[start_date, end_date]` **and** the region bbox lies inside the requested area. Otherwise import as partial.
  4. Keep all existing checks (NRT rejection, hashes, row counts). Remove the "file must start on July 1" rule (`archive.py:50-51`).
  5. Output bundle name: `fireatlas/samples/nasa_firms_<region>_<start>_<end>.zip` **only if < 50 MB**; otherwise write to `data/bundles/` (git-ignored) and publish as a GitHub Release asset (C12-T6).
- **Human data acquisition (cannot be done by the LLM):**
  1. Open `https://firms.modaps.eosdis.nasa.gov/download/` → "Create New Request".
  2. Area: draw or enter the region bbox (or choose the country for large regions).
  3. Date range and source, one request per product: MODIS Collection 6.1 **2000-11-01 → 2025-12-31**; VIIRS S-NPP 375 m **2012-01-20 → latest standard month**; VIIRS NOAA-20 375 m **2020-01-01 → latest standard month**. VERIFY on the form whether a date-range length limit exists; if so, split by year.
  4. Format CSV. Submit; download from the e-mail link; unzip into `NASA_data/<region>/DL_FIRE_*`; create `request.json` in each folder.
- **Acceptance checks:**
  - [ ] `uv run python -m fireatlas.archive build --region norcal NASA_data/norcal` reproduces the existing 30,823 rows for 2022-07→2026-06 when given the same inputs (regression test).
  - [ ] Test: a month partially outside the request dates is imported as partial.
  - [ ] Test: a region bbox outside the requested area raises `ValueError`.
  - [ ] SCORECARD "Data inventory" table lists, per region and product: years, rows, complete months, file SHA-256.

### C2-T2 — Precomputed daily aggregates (fast, small, publishable)

- **Files:** new `fireatlas/aggregates.py`, `tests/test_aggregates.py`.
- **Steps:**
  1. For each region, series and UTC day compute: `cells_<series>` (count), `raw_<series>` (pixels), `frp_sum_<series>` (MW, sum of numeric `frp`), plus union/intersection counts for MODIS∪S-NPP and MODIS∩S-NPP.
  2. Compute each value in **8 variants**: day definition {`utc`, `solar`} × types {`veg` (type 0 or missing), `all`} × confidence {`all`, `no-low`}. `solar` day = UTC date of `acquisition_utc + longitude/15 hours` (local solar time; no time-zone library needed). `no-low` removes VIIRS `l` and MODIS confidence < 30.
  3. Write `fireatlas/samples/aggregates/<region>.json.gz` with schema `fireatlas-daily-aggregates-v1` (fields listed in Appendix A.1). Target size < 10 MB per region.
  4. Aggregates must be reproducible: include input bundle hashes and the method version.
- **Acceptance checks:**
  - [ ] For `norcal` July 2024 UTC/all/all, aggregate union cells equal `/api/calendar` joint values day by day (test).
  - [ ] Solar-day test: a detection at 2024-07-25T06:30Z at lon −121.5 goes to solar date 2024-07-24 (06:30 − 8.1 h).
  - [ ] Type test: a row with `type=2` is excluded under `veg` and included under `all`.

### C2-T3 — Sensor-availability ledger (replaces the hardcoded outage)

- **Files:** new `fireatlas/availability.py`, `fireatlas/samples/sensor_notices.json`, `fireatlas/samples/availability/<region>.json`, `tests/test_availability.py`; edit `core.py`, `harmonization.py`, `app.js` (delete `app.js:383-417,456` special case), `validity.py:34-38`.
- **Steps:**
  1. **Overpass inventory from NASA CMR** (public, no login for metadata). For each region and product short name (`MOD14` v`061`, `MYD14` v`061`, `VNP14IMG` v`002`, `VJ114IMG` v`002`) query `https://cmr.earthdata.nasa.gov/search/granules.json` with `short_name`, `version`, `bounding_box=<region bbox>`, `temporal=<month start>,<month end>`, `page_size=2000`. Paginate using the `CMR-Search-After` response header (VERIFY in CMR API docs; `fireatlas/granules.py:27-47` already queries CMR and can be reused). Record each granule's `time_start`.
  2. Count granules per UTC day and per solar day → `overpass_granules`. Store monthly JSON files so reruns resume.
  3. `sensor_notices.json`: curated list of official notices. Each entry: `source_id`, `start_utc`, `end_utc` (or null), `type` (`outage` | `partial-outage` | `mission-end` | `delivery-end`), `url`, `retrieved_utc`, `quote` (≤ 25 words copied from the notice). Seed entries (all VERIFY by opening the URL and copying the quote):
     - S-NPP processing stop 2024-07-24 05:28Z → 2024-07-28 (FIRMS outages page; already cited in `validity.py`).
     - S-NPP NRT and standard outage, Apr 28 → May 2026 (Earthdata alert "data-outage-alert-suomi-npp-near-real-time-nrt-standard-products").
     - S-NPP data excluded 2026-08-03 02:00Z → 2026-08-06 16:24Z (LAADS alert 193182).
     - S-NPP delivery ends 2026-11-01 13:00Z (Earthdata alert "suomi-npp-data-product-delivery-cease-november-1-2026").
     - Aqua MODIS science collection ends ~2026-08 and Terra ~2027-01 (LAADS MODIS–VIIRS transition PDF).
  4. Day state per source: `available` (≥ 1 granule, no notice) · `degraded` (partial-outage notice or granules < 50 % of that month's median daily count) · `missing` (0 granules or full outage notice) · `ended` (after mission/delivery end).
  5. Calendar and harmonized series read this ledger. A joint/harmonized day with any required source not `available` gets `quality = "degraded"` and the UI hatches it.
  6. Remove the hardcoded Park gap in `app.js` and `validity.py`; the Park 24–28 Jul flags must now come from the ledger.
- **Acceptance checks:**
  - [ ] Park 2024-07-24..28 shows `VIIRS_SNPP_SP` `degraded`/`missing` from data, with the notice URL, and **no** literal `2024` date check remains in `app.js` (`rg -n "snppGap" fireatlas/static` returns nothing).
  - [ ] Test with a synthetic ledger: a missing S-NPP day makes the harmonized value `scaled` with `source_used = MODIS_SP`.
  - [ ] Every notice has a URL and retrieved date (test validates schema).
  - [ ] Optional metric `cells_per_overpass` available in the API (value ÷ overpass granules), labelled "sampling-normalized, not cloud-corrected".

### C2-T4 — Filters and version rules

- **Files:** `core.py` (`_counts`, `calendar`), `harmonization.py`, tests.
- **Steps:**
  1. Add parameters `types="veg"|"all"` (default `veg`: `thermal_anomaly_flag` in (`'0'`, NULL)) and `confidence="all"|"no-low"` (default `all`) to `_counts` and every endpoint that calls it. `thermal_anomaly_flag` already stores FIRMS `type` (`core.py:198`).
  2. Baseline eligibility: a prior year is used only if each source's product versions belong to the same **collection** as the target year. Collection mapping (write as a table in code, VERIFY against FIRMS attribute docs): MODIS versions starting `6.1` or `61` → `C6.1`; starting `6.0`/`6.03`/`6` without `1` → `C6`; VIIRS `2`/`2.0` → `C2`. Mixed-collection years are **excluded from the baseline and listed** in `excluded_baseline_years` with the reason.
  3. `briefing.py:42-45`: status must be `baseline-not-comparable` when versions are mixed or fewer than 10 comparable baseline years exist for anomaly language (Tier-1 rule: "unusual" language needs ≥ 10 years).
- **Acceptance checks:**
  - [ ] July 2025 `norcal` with the current bundle: 2022 is excluded (`6.03`), the briefing says "baseline not comparable", not "322 above median".
  - [ ] The 203 type ≠ 0 rows no longer count under the default filter (test using the real bundle).

### C2-T5 — Overlap calibration with uncertainty (the scientific heart)

- **Files:** new `fireatlas/calibration.py`, `tests/test_calibration.py`, outputs `fireatlas/samples/calibration/<region>.json`.
- **Method (implement exactly; no other statistics libraries needed):**
  1. **Overlap window** for MODIS↔S-NPP: complete months from 2012-02 through the last complete month of both, excluding days where either source is not `available` in the ledger.
  2. For each overlap year `y` and month-of-year `m`: `M[y,m]` = sum of MODIS daily cell-days on available days; `V[y,m]` = the same for S-NPP on the same days (use variant `utc/veg/all`, plus repeat for others).
  3. **Month-of-year ratio:** `r(m) = Σ_y V[y,m] / Σ_y M[y,m]`. Valid only if `Σ_y M[y,m] ≥ 30`; otherwise use the pooled annual ratio `r_all = ΣV / ΣM` and set `ratio_basis = "annual-fallback"`. If `ΣM < 30` overall, harmonization for that region is `unavailable`.
  4. **Uncertainty:** bootstrap by year. Resample overlap years with replacement 1,000 times (Python `random.Random(20261114)`); recompute `r(m)`; the 95 % interval is the 2.5th and 97.5th percentiles.
  5. **Estimate for a MODIS-only month:** `Ṽ = M × r(m)`, interval `[M × r_lo(m), M × r_hi(m)]`. Daily estimates use the same monthly ratio.
  6. **Leave-one-year-out (LOYO) validation:** for each overlap year, refit `r(m)` without it, predict that year's `V[y,m]` from its `M[y,m]`, and report: (a) median absolute log error `median |ln((V̂+1)/(V+1))|` over months, (b) annual total absolute % error, (c) interval coverage (% of months where `V` falls inside the predicted interval).
  7. **Baselines to beat** (report the same metrics): (i) *no harmonization* (`r = 1`), (ii) *single pooled ratio* (`r_all`, no month-of-year).
  8. **Stability check:** Spearman rank correlation between year and annual ratio `ΣV_y/ΣM_y`, with a permutation p-value (5,000 permutations, same seed). If p < 0.05, set `ratio_trend_flag = true` and show a warning ("the MODIS/VIIRS relationship changed over time; older estimates carry extra uncertainty").
  9. Repeat steps 1–8 for **S-NPP ↔ NOAA-20** over 2020-01 → last common complete month to get `q(m)`.
  10. Save `fireatlas-calibration-v1` JSON (Appendix A.2).
- **Acceptance checks:**
  - [ ] Unit test with synthetic data where V = 4 × M exactly: `r(m) = 4`, interval width 0, LOYO error 0.
  - [ ] Unit test: months with ΣM < 30 use `annual-fallback`.
  - [ ] Real run for every region with overlap data; results table (region, r_all, LOYO median abs log error, coverage, beats-baselines yes/no) copied into SCORECARD.
  - [ ] If the month-of-year model does **not** beat both baselines for a region, the UI uses the better baseline model for that region and says so. Never hide a failure.

### C2-T6 — Provenance, citations and data licence text

- **Steps:**
  1. Every new dataset (FIRMS archives per region, CMR inventories, notices, MCD64A1 in C10) gets a row in `docs/DATA.md` and on `/data.html`: name, product short name + version, provider, URL, date range, retrieval date, licence/terms, citation text, file SHA-256.
  2. FIRMS acknowledgement text as published in the FIRMS FAQ (https://www.earthdata.nasa.gov/data/tools/firms/faq, read 29 Sep 2026): *"We acknowledge the use of imagery from the NASA LANCE FIRMS (https://earthdata.nasa.gov/firms), part of the NASA Earth Science Data and Information System (ESDIS)."* Re-check the FAQ before submission and copy any updated wording verbatim; image captions cite "NASA FIRMS".
- **Acceptance checks:**
  - [ ] Test: every `source_id` present in the database has a row in `docs/DATA.md` (parse the markdown table).

**Master prompt (use one task ID at a time):**

```text
TASK C2-T<n>. Read docs/winning-plan/src/04-gate1-and-data.md, section "C2-T<n>",
and the files it lists. Implement exactly the listed steps and method. Where the
text says VERIFY, verify by running a command or opening the official page, and
quote what you found. Do not change the statistical method; if the data make the
method impossible (for example too few overlap months), implement the documented
fallback and report it. Add the listed unit tests. Run the full test suite.
Then run the real-data command for region norcal and paste the key numbers.
Output the REPORT block. Numbers you report must come from your command output.
```

**C2 checklist:** [ ] T1 importer · [ ] T2 aggregates · [ ] T3 availability ledger · [ ] T4 filters/versions · [ ] T5 calibration · [ ] T6 provenance · [ ] ≥ 3 regions with ≥ 20 years MODIS and ≥ 10 years S-NPP · [ ] LOYO beats both baselines in ≥ 3 regions (or failure shown honestly)
