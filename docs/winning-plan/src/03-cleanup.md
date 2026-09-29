# 3. Target product shape (what the finished site looks like)

## 3.1 Information architecture (final)

| Page | Path | Purpose | Status |
|---|---|---|---|
| Calendar (home) | `/` | Hero + area picker + multi-year calendar + day evidence | Rebuild from existing `index.html` |
| Method & validation | `/method.html` | How harmonization works, calibration results, sensor timeline, recount, limits | Extend existing |
| Sources & citations | `/data.html` | Every dataset, version, URL, licence, retrieval date, hashes; AI-use disclosure | Rewrite existing |
| Fire replay (beta) | `/replay.html` | Tier 2 Scout: Park Fire uncertainty replay | New, only if Tier 1 done |

**Top navigation (exact labels, left to right):** `Calendar` · `Method & validation` · `Fire replay (beta)` (hidden until C4–C7 pass) · `Sources`. Remove the "Labs & sources" dropdown.

## 3.2 Visual rules (apply everywhere)

- Keep the existing design system in `fireatlas/static/design.css` (graphite surfaces, ember accent, DM Sans + Space Grotesk). Do not add a new CSS framework.
- **Sensor colours (fixed, colour-blind safe, use CSS variables in `design.css`):** `--modis: #E69F00` (orange), `--viirs-snpp: #56B4E9` (sky blue), `--viirs-noaa20: #009E73` (green), `--viirs-noaa21: #CC79A7` (pink), `--harmonized: #F0E442` (yellow), `--degraded: repeating hatch #7a8a93`, `--unknown: #3b4a52`.
- Every number on screen shows its **unit** ("cell-days", "detections", "MW") and its **scope** (area, date range, series, UTC or local solar day).
- Every chart has a one-line caption beginning with **"What this shows:"** and one line beginning with **"What this does not show:"**.
- Synthetic content is never visible in the default site. If any remains (tests only), it must have a red `SYNTHETIC` badge.
- Performance budget: first meaningful paint < 2.5 s on a 4G profile; calendar API < 800 ms for preset areas; no request to a third-party service is required for the calendar to render.
- Accessibility: all controls keyboard-operable; colour is never the only signal (use hatch/icons for degraded/unknown); WCAG AA contrast.

---

# 4. Cleanup — things to remove, demote or keep (section R)

Each row is one task. Execute in order. Run the full test suite after each row; fix or delete tests that only covered removed features.

| ID | Item | Location | Action | Why |
|---|---|---|---|---|
| R1 | Global disaster casebook (15 disasters with death tolls, flame textures) | `fireatlas/static/documented-fires.json`; `#globe-documented`, `#globe-documented-toggle` in `index.html` (lines ~67, ~99–100); casebook code in `globe.js`; route in `web.py` ASSETS | **Delete** | Not NASA data, not related to harmonization, emotionally loaded death counts invite judge skepticism. |
| R2 | Training Lab (fictional Alder Creek crew exercise) | `training.html/js/css`, `training-state.js`, `training-store.js`, `training-offline.js`, `training-sw.js`, `fireatlas/training.py`, `/api/training/*` in `web.py`, `tests/test_training.py`, `tests/test_web.py::test_training_routes_and_causal_snapshots` | **Move to branch `archive/training-lab`, then delete from `main`** | Off-challenge and synthetic; dilutes Relevance and Validity. |
| R3 | Installable PWA / offline shell | `install.html`, `install.js`, `manifest.webmanifest`, `app-sw.js`, `offline.html`, icons, `tests/test_app_sw.py`, `docs/MOBILE_APP.md`, `scripts/verify_mobile_app.py` | **Delete** (keep icons only if used as favicon) | Service-worker caching can serve stale data during judging; no rubric value. |
| R4 | Synthetic "Explore demo" mode in the UI | Demo toggle and `demo=1` links in `index.html`/`app.js`/`study-ui.js`/`story.js`; `--judge-demo` in `web.py:531-534`; `scripts/launch_judge_demo.ps1` | **Remove from UI and launcher.** Keep `fireatlas/demo.py` and `presentation.py` **only for tests** | Authentic data exist; synthetic mode is a validity liability. |
| R5 | Guided tour built on synthetic July 2015 | `story.js`, `#story-dock` | **Replace** with a 4-step tour on authentic data (C11-T5) | Current tour uses fabricated data. |
| R6 | EONET "World snapshot" section | `#live-events` in `index.html` (~line 228), `events.js`, `fireatlas/events.py`, `/api/events` | **Remove from home.** Optionally list EONET on `/data.html` as a separate reported-events source | Not part of the harmonized record; live network dependency. |
| R7 | 7-day NRT global globe as the hero | `globe.js`, `earth-embed.js`, `/api/globe*`, NRT database rows | **Demote:** hero shows the sensor timeline and harmonized-archive coverage areas (C11-T1, C11-T3). Keep NRT import code for the "recent season" extension only | NRT data are rolling snapshots, not the historical record; 866,956 local rows are not reproducible from a clone. |
| R8 | ArcGIS terrain globe | `terrain-earth.html`, `earth-embed.js` ArcGIS path | **Remove from home.** Reuse only on `/replay.html` if Tier 2 needs terrain visuals | Third-party network dependency; failed to load in audit; not analysis. |
| R9 | 14.5 MB `earth.html` and `fireatlas_terrain_fixed.html` at repo root | root; `/earth.html` route (`web.py` `EARTH_MODEL`); `tests/test_web.py:44-51` | **Delete files, route and tests** | Heavy, unused by the core story. |
| R10 | Research Lab as a separate page | `research.html/js/css`, `fireatlas/research.py` | **Merge** the overlap table and candidate groups into `/method.html` → "Advanced analysis" collapsible; delete the standalone page and nav link | Fewer pages, one story. |
| R11 | NOAA HMS in the calendar sensor switch | `data-series="hms-viirs"` button in `index.html`; `SERIES["hms-viirs"]` stays in `core.py` | **Remove from the main switch.** Use HMS only as an independent cross-check in validation (C10-T4) | It is NOAA, not the MODIS/VIIRS pair; confuses the story. |
| R12 | "Imported product" dropdown with NRT series | `index.html` sensor view row | **Move** to `/data.html` | Keeps the calendar focused on harmonized series. |
| R13 | Stale presentation guide and screenshots (synthetic era) | `docs/presentation/*` | **Delete** after the new video/slides exist (section 8) | Screenshots show removed features. |
| R14 | Root-level phone screenshots of the rubric | `825258880_….jpg`, `825260014_….jpg` | **Move** to `docs/winning-plan/evidence/local-rubric-*.jpg` (or keep out of Git) | Clutter; keep as evidence of the rubric source. |
| R15 | Project plan PDF at root | `NASA_Space_Apps_Fire_Atlas_Project_Plan.pdf` | **Move** to `docs/archive/` | Clutter. |
| R16 | Hardcoded S-NPP gap | `app.js:383-417,456`; `validity.py:34-38` `source_notice` | **Replace** by the data-driven availability ledger (C2-T3) | Only one outage is known to the app. |
| R17 | Overlong README (281 lines, three datasets mixed) and contradictory PRD line 130 | `README.md`, `PRD.md` | **Rewrite** (C12-T5) | Judges read the first screen only. |

**Master prompt for any R-row:**

```text
TASK R<n>. Read docs/winning-plan/src/03-cleanup.md row R<n>. Then:
1. List every file, route, test and HTML element that references the item
   (use ripgrep; paste the matches with path:line).
2. If the action is "Move to branch", create branch archive/<name> from main first
   and push it; then return to main.
3. Remove or change exactly those references. Do not touch unrelated code.
4. Delete tests that only exercised the removed feature; keep all other tests.
5. Run: uv run python -m unittest discover -s tests  (must pass)
6. Start the server (uv run python -m fireatlas.web --port 8000), load /, /method.html,
   /data.html, and confirm there are no 404s or console errors
   (report the browser console output or curl status codes).
Output the REPORT block from the Executor System Prompt.
```

**Checklist (all R rows):**

- [ ] R1 · [ ] R2 · [ ] R3 · [ ] R4 · [ ] R5 · [ ] R6 · [ ] R7 · [ ] R8 · [ ] R9 · [ ] R10 · [ ] R11 · [ ] R12 · [ ] R13 · [ ] R14 · [ ] R15 · [ ] R16 · [ ] R17
- [ ] After all rows: `rg -n "training|documented-fires|earth.html|install.html|demo=1" fireatlas/static` returns only intentional matches (list them in the SCORECARD).
