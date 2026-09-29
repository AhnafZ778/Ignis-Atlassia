# 7. Tier 2 — FireAtlas Scout: Park Fire 2024 uncertainty replay (beta)

**Start condition:** every Tier 1 acceptance check for C1, C2 and C10-T1…T7 is `DONE` in SCORECARD. If the hackathon is less than 10 days away (Branch A) or less than 14 hours remain (Branch B) and Tier 1 is not done, mark all of section 7 `DROPPED (time)` and polish Tier 1 instead. A strong Tier 1 beats a weak Tier 1 plus a weak Tier 2.

**What Scout is (one sentence, use it everywhere):** *A replay of a past fire that shows, hour by hour, which areas the fire-spread scenarios disagreed about most—and how new observations reduced that uncertainty.*

**What Scout is not:** a forecast, a flight planner, an evacuation tool, or anything usable on an active fire.

**Case:** Park Fire, Butte/Tehama counties, California, ignited 24 July 2024 (VERIFY ignition time on the CAL FIRE incident page and record it). Replay window: ignition → 31 July 2024, time step 6 hours. This case is chosen because (a) S-NPP VIIRS was out 24–28 July, so the replay shows how the system copes with a missing sensor using MODIS and NOAA-20 VIIRS; (b) it is already the flagship example in the bundle.

## 7.0 Shared foundations

### S-T0 — Replay clock and leakage guard (C10 Tier 2)

- **Files:** `fireatlas/replay.py` (new), `tests/test_replay.py`.
- **Design:**
  1. Every replay input is a record with `valid_at` (time the value describes, UTC) and `available_at` (earliest time a person could have had it, UTC). Rules for `available_at`: FIRMS NRT detections = acquisition time + 3 h (FIRMS NRT latency target; VERIFY on the FIRMS FAQ and record); standard-product detections are **not allowed** in replay (they arrived months later) — use the NRT archive files for July 2024 (VERIFY that FIRMS archive download offers NRT for that date; if not, use standard detections with `available_at = acquisition + 3 h` and write the limitation on the page); HRRR analysis = valid time + 1 h; aerial perimeters = file timestamp; terrain and fuels = static (`available_at = 1970-01-01`), with the fuels product year ≤ 2024.
  2. `class ReplayClock(now_utc)` with `inputs(kind) -> list` that returns only records with `available_at <= now_utc`. All model code receives inputs **only** through the clock.
  3. Every output file stores `as_of_utc` and the list of input IDs used.
  4. **Active-fire block:** the replay endpoint refuses any event whose last detection is within 30 days of the server's current date (HTTP 403, message "Replay is only for past fires"). Test it.
- **Acceptance checks:**
  - [ ] Test: a record with `available_at` one second after `now_utc` is never returned.
  - [ ] Test: output files list only input IDs with `available_at <= as_of_utc` (property test over 100 random clocks).
  - [ ] Test: active-fire block works.

## C3 — Terrain, fuels, vegetation and dated weather (weight 8, now 1, target 4)

### C3-T1 — Terrain

- **Data:** NASADEM 1 arc-second (≈30 m), NASA LP DAAC, Earthdata Login (VERIFY product short name `NASADEM_HGT` v001). Fallback: Copernicus GLO-30 DEM (licence attribution required).
- **Files:** `fireatlas/terrain.py`, `data/replay/park-2024/dem.tif` (not committed; add to Release asset), `tests/test_terrain.py`.
- **Steps:** download tiles covering bbox `-122.3, 39.6, -121.4, 40.4` (VERIFY it covers the final Park perimeter plus 10 km); mosaic and reproject to EPSG:32610 (UTM 10N), 30 m; compute slope (degrees), aspect (degrees from north), TPI (elevation minus mean in 300 m radius). Use GDAL (`gdaldem slope/aspect`) or numpy; record the commands.
- **Acceptance checks:** [ ] Unit test on a synthetic tilted plane gives the known slope/aspect. [ ] Summary stats written to SCORECARD.

### C3-T2 — Fuels

- **Data:** LANDFIRE 13 Anderson / 40 Scott-Burgan fuel models (FBFM40), product version dated **before** 24 Jul 2024 (VERIFY: LF 2022 "LF 2.3.0" or LF2023 "LF 2.4.0" release date). Download via the LANDFIRE Product Service (LFPS) or the map viewer.
- **Steps:** clip to bbox, resample (nearest) to the 30 m DEM grid, map codes to the Scott & Burgan parameter table used by the spread model; codes 91–99 (non-burnable) set to non-burnable.
- **Acceptance checks:** [ ] Code histogram in SCORECARD. [ ] Test: non-burnable codes never ignite in the spread model.

### C3-T3 — Dated weather

- **Data:** NOAA HRRR analysis (f00) hourly, from the NOAA Open Data Dissemination bucket `noaa-hrrr-bdp-pds` on AWS (VERIFY bucket name and file naming). Variables: 10 m U/V wind, 2 m temperature, 2 m RH. Fallback: gridMET daily (lower resolution; label it).
- **Steps:** for each hour in the replay window, extract the variables on the replay grid (bilinear), store as `data/replay/park-2024/weather/<valid_utc>.npz` with `available_at = valid + 1 h`. Compute dead fuel moisture (1-h, 10-h) with a documented simple method (e.g., Fosberg/Nelson table — VERIFY source and cite).
- **Acceptance checks:** [ ] Freshness panel (C7-T3) shows the age of weather at each step. [ ] Test: weather interpolation reproduces a constant field exactly.

## C7 — Spread scenarios, uncertainty and input freshness (weight 10, now 1, target 4)

### C7-T1 — Spread model

- **Preferred:** `pyretechnics` (Rothermel surface spread + elliptical growth; VERIFY the package exists on PyPI, its licence is OSI-compatible, and its API) — pin the version.
- **Fallback (only if preferred fails in < 4 h of effort):** a cellular automaton on the 30 m grid where the spread probability to a neighbour = `p0 × f_fuel × exp(a·wind_along) × exp(b·slope_along)`, with `p0, a, b` from a cited paper (e.g., Alexandridis et al. 2008 — VERIFY values). Label it on screen as **"simplified, uncalibrated spread model"**.
- **Files:** `fireatlas/spread.py`, `tests/test_spread.py`.
- **Acceptance checks:** [ ] Test: no wind and flat terrain → roughly circular spread (aspect ratio < 1.2). [ ] Test: wind from west → spread further east. [ ] Test: non-burnable cells never burn.

### C7-T2 — Ensemble (50 members)

- **Perturbations per member (seeded, `seed = 20261114 + member`):** wind speed × U(0.8, 1.2); wind direction + N(0°, 15°); dead fuel moisture × U(0.85, 1.15); ignition = observed hotspot cells as of `as_of_utc` (from the clock) with each cell kept with probability 0.9.
- **Output per step:** burn-probability grid `p(x)` for horizons +6 h, +12 h, +24 h = fraction of members that burned cell x.
- **Acceptance checks:** [ ] Same seed → identical output (test). [ ] Runtime per step < 60 s on the dev laptop (record).

### C7-T3 — Freshness and uncertainty display

- For each step show a **freshness table**: input · valid time · available time · age at `as_of` (e.g., "NOAA-20 VIIRS detections · 25 Jul 09:48 UTC · 12:48 UTC · 2 h 12 min old"). Rows: MODIS, S-NPP (shows "missing — NASA notice"), NOAA-20, weather, fuels, terrain, aerial perimeter.
- Map layers: `p(x)` as a sequential colour ramp with a legend "share of 50 scenarios that burned this cell"; the **uncertainty band** = cells with 0.1 < p < 0.9 outlined.
- **Acceptance checks:** [ ] Screenshot at three clocks. [ ] Legend text exactly as above.

## C4 — Explainable ranking of observation sectors (weight 14, now 0, target 4)

**Question answered:** *Which parts of the fire edge were the scenarios most unsure about at this time, and why?* This is where an extra observation would have reduced uncertainty the most.

### C4-T1 — Sectors

- Divide the area within 10 km of the current observed fire extent into 2 km × 2 km sectors on the UTM grid (`fireatlas/sectors.py`). Keep only sectors with at least one cell where 0.05 < p < 0.95 at +12 h.

### C4-T2 — Score and components (all in [0, 1])

- `U` (uncertainty) = mean over sector cells of binary entropy `H(p) = −p log2 p − (1−p) log2(1−p)` at +12 h.
- `E` (exposure) = sector building count / max building count across sectors. Data: Microsoft US Building Footprints (ODbL; VERIFY) or OpenStreetMap buildings (ODbL). Record the data date; buildings built after 2024 must not be used.
- `S` (staleness) = min(1, hours since the last satellite detection-capable overpass covering the sector (from the CMR availability ledger, C2-T3) / 12).
- `V` (terrain visibility, illustrative) = fraction of sector cells visible from a point 120 m above the sector's highest cell (viewshed on the DEM; `gdal_viewshed`). It shows how much of the sector a single elevated viewpoint could see; it is **not** a flight altitude recommendation.
- **Score** `= U × (0.5 + 0.5E) × (0.5 + 0.5S) × V`. Write the formula on screen.
- **Acceptance checks:** [ ] Unit tests for each component on hand-made grids. [ ] Test: a sector with p = 0 or 1 everywhere has U = 0 and score 0.

### C4-T3 — Explanation UI

- Right panel "Most uncertain sectors at 25 Jul 18:00 UTC": ranked list (top 5) with a stacked bar showing the four components and a one-line reason generated from the largest components, e.g., `"Scenarios split 48/52 here; 120 buildings; last satellite look 9 h ago."`
- Clicking a sector highlights it and shows the member-by-member burn outcome (small multiples of 10 members).
- **Ablation note** (below the list): rank correlation between the full score and `U` alone — shows what E, S and V change.
- **Acceptance checks:** [ ] Every number in the reason line comes from the component values (test). [ ] No text uses the words "fly", "deploy", "send" or "dispatch" (safety test from C8-T1 covers the page).

### C4-T4 — Does the ranking mean anything? (retrospective check)

- For each step, compare the top-5 sectors with where the fire actually grew in the next 12 h (from the next observed perimeter): **hit rate** = share of top-5 sectors that intersect new growth; compare with (a) 5 random edge sectors (1,000 draws; report mean and 95 % range) and (b) 5 sectors with the highest `p` (most likely to burn).
- Report honestly on the page, including if the ranking is no better than random.
- **Acceptance checks:** [ ] Table in SCORECARD with hit rates per step and baseline ranges.

## C6 — Dated aerial observations and state update (weight 8, now 0, target 4)

### C6-T1 — Observation ingest

- **Data (in order of preference, VERIFY each for the Park Fire):** (1) NASA FEDS (Fire Event Data Suite) VIIRS-derived 12-hourly fire perimeters (NASA Earth Information System; VERIFY access location and licence); (2) NIFC / FIRIS airborne infrared perimeters from the NIFC Open Data site (WFIGS or the interagency perimeter history). Record each perimeter's `observed_at` and `available_at`.
- **Files:** `fireatlas/observations_aerial.py`, `data/replay/park-2024/perimeters/*.geojson`, `tests/test_observations_aerial.py`.
- **Rules:** perimeters without a timestamp are rejected; geometry must be valid (fix with `buffer(0)` and log it); reproject to UTM 10N.
- **Acceptance checks:** [ ] ≥ 6 dated perimeters in the replay window, or a written reason why not. [ ] Ingest test with a tiny GeoJSON.

### C6-T2 — State update (assimilation)

- **Files:** `fireatlas/assimilate.py`, `tests/test_assimilate.py`.
- **Method:** when a new perimeter P arrives at time t: for each member k, compute Jaccard `J_k` between its burned area at t and P. Weight `w_k ∝ exp(−(1 − J_k)/0.1)`, normalise. Resample 50 members by systematic resampling using the weights. Re-seed all members from P (burned = inside P) while keeping each member's perturbation parameters. Record effective sample size `1/Σw²` per update.
- **Acceptance checks:** [ ] Test: identical member and perimeter → J = 1 and highest weight. [ ] Test: weights sum to 1. [ ] ESS plotted per update.

### C6-T3 — Replay metrics (C10 Tier 2)

- For each step with a next perimeter: Jaccard of the p ≥ 0.5 footprint vs next perimeter; Brier score of `p` vs observed burned/unburned cells within 10 km. Compare three versions: **persistence** (perimeter does not grow), **ensemble without assimilation**, **ensemble with assimilation**.
- **Acceptance checks:** [ ] Table and line chart on `/replay.html` → "How well did it do?" with all three. [ ] Numbers in SCORECARD.

## C5 (Tier 2) — Aerial-observation feasibility framing and airspace/command boundaries (target 4)

### C5-T2 — Boundaries panel (text and diagram, not map overlays)

- On `/replay.html` add a collapsible "Who controls the airspace" panel:
  1. Over a US wildfire, the FAA usually issues a Temporary Flight Restriction under 14 CFR 91.137; unauthorised drones are prohibited, and drone incursions have grounded firefighting aircraft (cite the US Forest Service / NIFC "If you fly, we can't" material — VERIFY the page).
  2. Incident aviation is coordinated by the incident's air operations organisation using NWCG procedures (Fire Traffic Area; cite the NWCG document — VERIFY title and number).
  3. FireAtlas outputs are **research questions** ("where was uncertainty highest?") that an authorised team *could* consider; the tool gives no routes, altitudes or targets.
- A simple static SVG diagram: "Satellites (FIRMS) → analysts → incident air operations (decides) → authorised aircraft/UAS" with the decision box clearly owned by the incident.
- **Acceptance checks:** [ ] No coordinates, rings or lines are drawn on the map for airspace. [ ] Citations on the Sources page.

### C5-T3 — Feasibility numbers (illustrative, clearly labelled)

- For the top-5 sectors, show only: sector area (km²), terrain visibility V, and "last satellite look" age. Do **not** compute flight times, battery, routes or altitudes.

## C8 (Tier 2) — Containment boundaries and operational safety (target 4)

### C8-T2 — Replay safety design

- Persistent top banner on `/replay.html` (not dismissible): `Replay of a past fire (Park Fire, July 2024). Scenarios, not forecasts. Not for operational use.`
- The observed perimeter is drawn as a solid line labelled "Observed perimeter (source, time)"; scenario output is only a probability raster. **Never** draw or label containment lines, control lines, dozer lines, "safe" areas or evacuation zones.
- The active-fire block from S-T0.
- **Acceptance checks:** [ ] Banner present on every replay screenshot. [ ] C8-T1 banned-phrase test covers `replay.html/js` and replay API text.

## C9 (Tier 2) — Responder workflow, resident information, official-alert separation (target 4)

### C9-T2 — After-action review workflow

- Replay controls: play/pause, step ± 6 h, time slider, "jump to next observation". At each step the right panel shows: what was known (freshness table), what scenarios said, what happened next (revealed only after pressing "Reveal outcome" — this keeps the leakage honest for viewers too).
- "Export review" button → Markdown/PDF with the step table, metrics and all source citations.

### C9-T3 — Resident separation

- A small "Live in this area?" box that contains **only** the official links from `regions.py` (C9-T1) and the sentence `This replay is about a past fire. For current conditions, use official sources.` No FireAtlas data inside the box.

## 7.x Replay page layout (`/replay.html`)

1. Banner (C8-T2).
2. Title `Park Fire 2024 — where was the fire's future most uncertain?` + one-line explanation.
3. Main: Leaflet map (satellite detections by sensor colour, observed perimeter, `p(x)` raster, sector outlines with rank numbers). Base map: a plain terrain/hillshade tile layer; the hillshade can be generated from the DEM so no third-party globe is needed.
4. Right panel tabs: `Now` (freshness + top sectors), `Why` (component bars, formula), `Outcome` (hidden until revealed), `Accuracy` (C6-T3 metrics).
5. Bottom: time slider with ticks for each observation (satellite overpasses coloured by sensor, perimeters as white ticks, S-NPP outage shaded).
6. Footer: methods summary, limits, citations, "Who controls the airspace" (C5-T2).

**Master prompt (Tier 2, one task at a time):**

```text
TASK <S-T0|C3-Tn|C7-Tn|C4-Tn|C6-Tn|C5-Tn|C8-T2|C9-Tn>. Read
docs/winning-plan/src/07-scout-replay.md for that task. Tier 2 may start only if
SCORECARD shows all Tier 1 checks DONE; if not, stop and say so.
All inputs must pass through fireatlas/replay.py ReplayClock. Every dataset marked VERIFY
must be confirmed from its official page (paste URL and version) before use; if it cannot
be confirmed, mark BLOCKED. Report metrics exactly as computed, including bad results.
Never output routes, waypoints, altitudes or containment lines. Add tests. Run the full
suite. Output the REPORT block.
```

**Tier 2 checklist:** [ ] S-T0 · [ ] C3-T1 · [ ] C3-T2 · [ ] C3-T3 · [ ] C7-T1 · [ ] C7-T2 · [ ] C7-T3 · [ ] C4-T1 · [ ] C4-T2 · [ ] C4-T3 · [ ] C4-T4 · [ ] C6-T1 · [ ] C6-T2 · [ ] C6-T3 · [ ] C5-T2 · [ ] C5-T3 · [ ] C8-T2 · [ ] C9-T2 · [ ] C9-T3 · [ ] `/replay.html` linked in nav only after all above are DONE
