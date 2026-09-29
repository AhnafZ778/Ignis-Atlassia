# FireAtlas SCORECARD — live accountability tracker

**Plan:** `docs/winning-plan/FireAtlas_Winning_Plan.pdf` (source `docs/winning-plan/src/`).
**Rules:** see plan section 9.1. Executors update **task rows** with evidence; only the **Auditor** (plan 9.2) changes **scores**. Every change adds a Changelog line.
**Status words:** `NOT STARTED` · `IN PROGRESS` · `BLOCKED (reason)` · `DONE (evidence: …)` · `DROPPED (reason)`

| Field | Value |
|---|---|
| Last audit | 2026-09-29 (numeric baseline; implementation checked through R6) |
| Audit score (100) | **31.8** · Tier 1 target 54.2 · Tier 1 + 2 target 88.0 |
| Local rubric (118) | **≈65** · target ≈106 |
| Post-R6 score delta | **0 points assigned** · R5 exposes existing records and R6 removes an unrelated event feed; neither adds calibration or independent validation |
| Branch | UNDECIDED (Gate 0 pending) |
| Tier 1 freeze date | 2026-11-08 (Branch A) |
| Deadline risk | RED (user deadline 2026-10-01; repository checks remain open) |
| Public repo URL | — |
| Public demo URL | — |

## 1. Gates

| Gate | Status | Evidence |
|---|---|---|
| G0-T1 Written ruling from Local Lead | NOT STARTED | |
| G0-T2 Branch chosen (A/B) | NOT STARTED | |
| G0-T3 Official statement copied (28 Oct) | NOT STARTED | |
| Gate 1 (C12-T1…T3) repo integrity | IN PROGRESS | `d43c602` on `origin/main`; clean-clone smoke and local suite pass; GitHub CI and public access not verified |
| Tier 1 complete (all C1, C2, C10-T1…T7 DONE) | NOT STARTED | |

## 2. Requirement trace (fill after G0-T3)

| # | Requirement sentence (verbatim from the 2026 statement) | Feature / task that satisfies it | Status |
|---|---|---|---|
| 1 | | | |

## 3. Category scores (Auditor only)

`points = weight × score ÷ 5`. Hard caps: synthetic-only ≤ 2 · not pushed ≤ 2 · no method + test ≤ 2 · forecast without held-out evaluation ≤ 3 · operational instruction ⇒ 0.

| # | Category | Wt | Score (0–5) | Points | Target T1 | Target T1+2 | Evidence (file:line / command) |
|---|---|---:|---:|---:|---:|---:|---|
| C1 | Challenge fit and working calendar | 12 | 3 | 7.2 | 5 | 5 | Calendar works for one bbox, 2022–2026 authentic data; UTC only; no multi-year heatmap (`core.py:328-418`) |
| C2 | Authentic NASA data, provenance, harmonization | 12 | 3 | 7.2 | 5 | 5 | 30,823 FIRMS standard rows with hashes; no calibration; type filter missing (`core.py:310-325`); pipeline uncommitted |
| C3 | Terrain, fuels, vegetation, dated weather | 8 | 1 | 1.6 | 2 | 4 | Visual-only elevation layer (`terrain-earth.html:32`) |
| C4 | Explainable sector ranking | 14 | 0 | 0.0 | 0 | 4 | Absent |
| C5 | UAS feasibility and airspace/command boundaries | 7 | 1 | 1.4 | 2 | 4 | Documentation mentions only |
| C6 | Dated aerial observations and state update | 8 | 0 | 0.0 | 0 | 4 | Absent |
| C7 | Spread scenarios, uncertainty, freshness | 10 | 1 | 2.0 | 1 | 4 | `research.py:266` states spread unavailable |
| C8 | Containment boundaries and operational safety | 7 | 2 | 2.8 | 3 | 4 | Limits text exists; no banned-phrase test |
| C9 | Responder workflow, resident info, alert separation | 6 | 2 | 2.4 | 3 | 4 | Briefing card with fixed label (`briefing.py:42-45`) |
| C10 | Validation, replay, leakage, baselines | 8 | 2 | 3.2 | 4 | 5 | Recount verifier + CAL FIRE association 7/25; MODIS masks 0/17 |
| C11 | Interface clarity and demo reliability | 4 | 3 | 2.4 | 5 | 5 | Works locally; cluttered; ArcGIS globe failed to load |
| C12 | Build, docs, reproducibility | 4 | 2 | 1.6 | 5 | 5 | 78 tests pass; code changes are pushed and worktree is clean; license and public/CI verification remain open |
| | **Total** | 100 | | **31.8** | 54.2 | 88.0 | Arithmetic: 7.2+7.2+1.6+0+1.4+0+2.0+2.8+2.4+3.2+2.4+1.6 = 31.8 |

## 4. Local rubric estimate (Auditor only)

| # | Criterion | Max | Now | Target | Justification (one sentence) |
|---|---|---:|---:|---:|---|
| 1 | Impact | 20 | 10 | 17 | Clear problem, one region only, no user evidence |
| 2 | Creativity | 20 | 11 | 16 | Evidence tracing is distinctive; calendar view conventional |
| 3 | Validity | 20 | 11 | 18 | Authentic data; no calibration or held-out test yet |
| 4 | Relevance | 20 | 11 | 19 | Harmonization not implemented; off-topic features present |
| 5 | Presentation | 20 | 12 | 18 | Polished visuals; no video/slides; story diluted |
| 6 | Teamwork | 5 | 2 | 5 | Two committers; no PR/review evidence |
| 7 | User experience | 5 | 3 | 5 | Usable but crowded |
| 8 | NASA data usage | 5 | 4 | 5 | FIRMS central; versions not surfaced in UI |
| 9 | Challenge category named | 1 | 1 | 1 | |
| 10 | Repository access | 1 | 0 | 1 | Latest work not pushed |
| 11 | Project page complete | 1 | 0 | 1 | Not submitted |
| | **Total** | 118 | **≈65** | **≈106** | |

## 5. Task status

| ID | Task | Status | Evidence (commit · test line · screenshot/JSON) | Updated |
|---|---|---|---|---|
| G0-T1 | Written ruling | NOT STARTED | | |
| G0-T2 | Choose branch | NOT STARTED | | |
| G0-T3 | Re-read statement 28 Oct | NOT STARTED | | |
| C12-T1 | Commit + push, repo public | IN PROGRESS | R4/R5 changes pushed to `origin/main`; repository visibility not verified | 2026-09-29 |
| C12-T2 | Launcher, smoke test, CI | IN PROGRESS | `scripts/smoke_test.sh "$PWD"` passes; GitHub CI run pending | 2026-09-29 |
| C12-T3 | Declare dependencies | DONE (evidence: locked optional NumPy extra; core installs without GDAL) | Local `uv sync --frozen`; 82-test suite; missing GDAL guidance check | 2026-09-29 |
| R1 | Delete disaster casebook | DONE (evidence: JSON asset/route, 3D toggle and animated fire effects removed; landing/browser check confirms no casebook controls, satellite details and EONET layer work with 0 page errors; 82 tests pass; `/`, `/method.html`, `/data.html` return 200 and retired JSON returns 404) | local checks, 2026-09-29 | 2026-09-29 |
| R2 | Archive + remove training lab | DONE (evidence: preserved on `origin/archive/training-lab`; page, API routes, assets, imports, service-worker, styles, navigation, and feature-only tests removed from `main`; retired page/API paths return 404; 78 tests pass) | local checks, 2026-09-29 | 2026-09-29 |
| R3 | Remove PWA | DONE (evidence: PWA routes/assets/metadata removed; legacy root-worker registrations and `fireatlas-app-shell-*` caches are cleared on the next secure visit; retired paths return 404; 78 tests pass) | local checks, 2026-09-29 | 2026-09-29 |
| R4 | Remove synthetic demo UI | DONE (evidence: removed data selector, synthetic tour, generated context/exposure controls and judge launcher; server returns 400 for `demo` query parameters, 404 for retired generator endpoints, and refuses synthetic databases; 78 tests pass; edited JavaScript syntax checks pass) | local checks, 2026-09-29 | 2026-09-29 |
| R5 | Replace synthetic tour | DONE (evidence: four-step walkthrough reads the active calendar, highlights area/sensor/calendar controls, selects a positive date from `/api/calendar`, and opens the existing method-page source inspector; no-data and row-mismatch states are explicit) | local checks, 2026-09-29 | 2026-09-29 |
| R6 | Remove EONET from home | DONE (evidence: removed landing section/navigation, Data page status widget, feed JS/module, API route, CLI command, styles, and feature-only tests; `/api/events` and `/events.js` return 404; pages contain no EONET UI) | full tests + local route/page checks, 2026-09-29 | 2026-09-29 |
| R7 | Demote NRT globe | NOT STARTED | | |
| R8 | Remove ArcGIS globe from home | NOT STARTED | | |
| R9 | Delete earth.html + terrain HTML | NOT STARTED | | |
| R10 | Merge Research Lab into method | NOT STARTED | | |
| R11 | HMS out of calendar switch | NOT STARTED | | |
| R12 | Move NRT dropdown | NOT STARTED | | |
| R13 | Delete stale presentation docs | NOT STARTED | | |
| R14 | Move rubric JPGs | NOT STARTED | | |
| R15 | Move plan PDF | NOT STARTED | | |
| R16 | Replace hardcoded S-NPP gap | NOT STARTED | | |
| R17 | README/PRD rewrite trigger | NOT STARTED | | |
| C2-T1 | Multi-region importer | NOT STARTED | | |
| C2-T2 | Daily aggregates (8 variants) | NOT STARTED | | |
| C2-T3 | Availability ledger | NOT STARTED | | |
| C2-T4 | Filters + version rules | NOT STARTED | | |
| C2-T5 | Calibration + LOYO | NOT STARTED | | |
| C2-T6 | Provenance + citations | NOT STARTED | | |
| C1-T1 | Calendar API v2 | NOT STARTED | | |
| C1-T2 | Multi-year heatmap | NOT STARTED | | |
| C1-T3 | Climatology panel | NOT STARTED | | |
| C1-T4 | Seasons + critical periods | NOT STARTED | | |
| C1-T5 | Area selection | NOT STARTED | | |
| C1-T6 | Day drawer | NOT STARTED | | |
| C1-T7 | Insight templates | NOT STARTED | | |
| C1-T8 | Exports | NOT STARTED | | |
| C10-T1 | Publish LOYO validation | NOT STARTED | | |
| C10-T2 | 2012 step test | NOT STARTED | | |
| C10-T3 | MCD64A1 comparison | NOT STARTED | | |
| C10-T4 | HMS cross-check | NOT STARTED | | |
| C10-T5 | MODIS mask fix + review | NOT STARTED | | |
| C10-T6 | Recount verifier v2 | NOT STARTED | | |
| C10-T7 | Leakage rules | NOT STARTED | | |
| C11-T1 | Home structure | NOT STARTED | | |
| C11-T2 | Remove visual noise | NOT STARTED | | |
| C11-T3 | Sensor timeline | NOT STARTED | | |
| C11-T4 | Method page sections | NOT STARTED | | |
| C11-T5 | 4-step tour | DONE (uses current interface and live imported records; the proposed region chips, 25-year heatmap, and percentile badge are not implemented and are not claimed by the tour) | local checks, browser interaction, 2026-09-29 | 2026-09-29 |
| C11-T6 | Empty/error states | NOT STARTED | | |
| C11-T7 | Reliability + Lighthouse | NOT STARTED | | |
| C11-T8 | 5-person usability test | NOT STARTED | | |
| C12-T4 | Licence + image sources | NOT STARTED | | |
| C12-T5 | README + PRD | NOT STARTED | | |
| C12-T6 | Static site + Release asset | NOT STARTED | | |
| C12-T7 | Sources page + AI use | NOT STARTED | | |
| C12-T8 | Teamwork evidence | NOT STARTED | | |
| C12-T9 | Release tag + hash check | NOT STARTED | | |
| C8-T1 | Safety wording + banned-phrase test | NOT STARTED | | |
| C9-T1 | Season context + official links | NOT STARTED | | |
| C5-T1 | Aerial-observation scope text | NOT STARTED | | |
| S-T0 | Replay clock + leakage guard | NOT STARTED | | |
| C3-T1 | Terrain | NOT STARTED | | |
| C3-T2 | Fuels | NOT STARTED | | |
| C3-T3 | Dated weather | NOT STARTED | | |
| C7-T1 | Spread model | NOT STARTED | | |
| C7-T2 | 50-member ensemble | NOT STARTED | | |
| C7-T3 | Freshness + uncertainty display | NOT STARTED | | |
| C4-T1 | Sectors | NOT STARTED | | |
| C4-T2 | Score components | NOT STARTED | | |
| C4-T3 | Explanation UI | NOT STARTED | | |
| C4-T4 | Retrospective hit rate | NOT STARTED | | |
| C6-T1 | Aerial perimeter ingest | NOT STARTED | | |
| C6-T2 | Assimilation | NOT STARTED | | |
| C6-T3 | Replay metrics | NOT STARTED | | |
| C5-T2 | Airspace boundaries panel | NOT STARTED | | |
| C5-T3 | Feasibility numbers | NOT STARTED | | |
| C8-T2 | Replay safety design | NOT STARTED | | |
| C9-T2 | After-action workflow | NOT STARTED | | |
| C9-T3 | Resident separation | NOT STARTED | | |
| SUB-T1 | Project page | NOT STARTED | | |
| SUB-T2 | 30-second video | NOT STARTED | | |
| SUB-T3 | 7 slides | NOT STARTED | | |
| SUB-T4 | Demo run sheet + rehearsals | NOT STARTED | | |

## 6. Data inventory (fill from C2-T1)

| Region | Product | Years | Rows | Complete months | SHA-256 |
|---|---|---|---:|---:|---|
| norcal | MODIS_SP | 2022-07 → 2026-06 | 8,151 | — | (from bundle manifest) |
| norcal | VIIRS_SNPP_SP | 2022-07 → 2026-06 | 22,672 | — | (from bundle manifest) |

## 7. Ground truth and measured results

| Measure | Value | Command | Date |
|---|---|---|---|
| Test suite | 78 tests OK after R5 tour | `uv run python -m unittest discover -s tests` | 2026-09-29 |
| Park 2024-07-25 MODIS | 603 pixels → 415 cells; S-NPP 0 rows | `/api/harmonization` | 2026-09-29 |
| Smoke test calendar value (C12-T2) | 1,668 joint detected cell-days; authentic MODIS/S-NPP provenance; HTTP 200 | `bash scripts/smoke_test.sh "$PWD"` | 2026-09-29 |
| Calibration results (C2-T5): region · r_all · LOYO median abs log error (MoY / single / none) · coverage · beats baselines | — | `python -m fireatlas.calibration --region …` | |
| Step test 2012 (C10-T2) | — | | |
| MCD64A1 Spearman (harmonized / naive / MODIS-only) | — | | |
| HMS cross-check Spearman | — | | |
| MODIS mask reconciliation rate | 0/17 processed | `python3 -m fireatlas.masks --case grove-2025` | 2026-09-29 |
| Lighthouse (Perf / A11y) | — | | |
| Usability test (tasks passed / 5) | — | | |
| Replay: Jaccard / Brier vs persistence / no-assimilation | — | | |
| Replay: top-5 hit rate vs random range | — | | |

## 8. Changelog

| When (UTC) | Who | What changed | Evidence |
|---|---|---|---|
| 2026-09-29 | Lead engineer (audit) | Baseline scorecard created from audit | Audit report, 81 tests OK |
| 2026-09-29 | Lead engineer | Added Linux launcher, fresh-clone smoke test, CI workflow, optional NumPy mask extra and actionable GDAL errors | Commit `d43c602`; smoke pass; 82 tests; GitHub CI pending |
| 2026-09-29 | Lead engineer | Completed R1: removed the global historical disaster casebook and its map/3D presentation code | 82 tests OK; targeted local Playwright interaction check; required-page HTTP checks |
| 2026-09-29 | Lead engineer | Completed R2: archived the fictional Training Lab and removed it from the active application | `origin/archive/training-lab`; 78 tests OK; retired page/API paths return 404; PWA browser check passes |
| 2026-09-29 | Lead engineer | Completed R3: removed installable PWA metadata, routes and offline shell, including cleanup for existing browser registrations | 78 tests OK; browser page checks report no manifest, worker or JS exceptions; retired PWA paths return 404 |
| 2026-09-29 | Lead engineer | Completed R4: removed the user-facing synthetic showcase, generated context/mask endpoints, and demo launcher; left generators as test fixtures only | 78 tests OK; demo queries return 400, removed routes return 404, CLI refuses synthetic databases; edited JavaScript syntax checks pass |
| 2026-09-29 | Lead engineer | Completed R5/C11-T5: added a four-step authentic-data walkthrough tied to the current area controls, source comparison, calendar, and a real positive day when available | `/tour.js` reads `/api/calendar` and `/api/observations`, then hands off to the dated source inspector; 78 tests OK; local Chrome interaction verified |
| 2026-09-29 | Lead engineer | Completed R6: removed the off-challenge EONET reported-event map and feed while retaining the separate NASA FIRMS 3D globe | Feed route and asset return 404; landing and Data sources pages contain no EONET UI; 74 tests OK |
