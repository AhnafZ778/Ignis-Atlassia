# FireAtlas product requirements document

**Project:** FireAtlas: A Harmonized Burning Calendar and Crew Awareness Lab  
**Status:** Phases 1–2 implemented with a real NOAA HMS VIIRS historical pilot slice and a separately labelled synthetic MODIS/VIIRS comparison. Phase 3 synthetic training prototype, Phase 4 exploratory Research Lab, and Phase 5 reproducibility workspace implemented. Phase 6 authentic-data integration is implemented through NOAA HMS; FIRMS connectivity and its MODIS/VIIRS pilot validation remain pending. A separate NASA EONET reported-event feed is live. Phase 7 offline training continuity is implemented. Scientific calibration and regional validation remain pending.
**Source:** `NASA_Space_Apps_Fire_Atlas_Project_Plan.pdf`, nine pages, dated 26 September 2026

## 1. Product decision

The [2026 NASA Space Apps challenge](https://www.spaceappschallenge.org/2026/challenges/harmonization-of-modis-and-viirs-hot-spots/) asks for a web application that harmonizes MODIS and VIIRS active-fire hotspots into a burning activity calendar for an area of interest (AOI). The calendar is the judged core. FireAtlas will explain seasonal patterns and unusual activity while exposing sensor differences and missing observations. The map helps select an AOI; a later crew exercise demonstrates how historical evidence might inform training.

**Promise:** A user can select an area, inspect a comparable burning calendar, see which sensor contributed each observation, and understand when a comparison is weak or unavailable.

**Scientific boundary:** A hotspot is a thermal anomaly at an overpass, not a confirmed wildfire, unique fire event, burned area, live perimeter, or safe route. Cropland burns and other heat sources may be present. Fire-weather potential, vegetation condition, and incident scenarios are separate products with separate clocks and uncertainty.

## 2. Users and jobs

| User | Job | Product response |
| --- | --- | --- |
| Land manager / scientist | Compare a region's season across years | MODIS historical and consistent VIIRS-era series, same-month baseline, provenance, export |
| Emergency planner | See unusually active periods without mistaking sensor growth for fire growth | Cell-day metric, source switch, overlap explanation, observation gaps |
| Educator / judge | Understand how observations become a calendar | Original FIRMS fields, common-grid method, duplicate example, reproducible demo |
| Incident trainer (later) | Rehearse alerts and route changes | Causal historical replay and simulated crew views, clearly labelled exercise |

## 3. Main journey

1. Open the global atlas and choose or draw an AOI.
2. Choose a year, land-cover stratum, and source series: MODIS, VIIRS S-NPP, or joint overlap-era sample.
3. Read daily detected cell-days and monthly seasonal comparison. Open a day to inspect original pixels and sensor counts.
4. Open the evidence drawer to see acquisition time, processing level, source file, missing-data status, metric definition, and export.
5. Optionally inspect dated vegetation/fire-weather context, then launch a **simulated** incident replay.

## 4. Functional requirements

| Priority | Requirement | Acceptance evidence |
| --- | --- | --- |
| P0 | AOI map with world aggregates at low zoom and original FIRMS detections at local zoom | Clicking a point shows acquisition UTC, platform, confidence in its native scale, FRP, version, and age |
| P0 | Harmonized calendar | Same-day MODIS and VIIRS pixels in one common cell yield one joint cell-day, with both sensors reported; source-specific raw pixel counts remain visible |
| P0 | Comparable seasonal baseline | Same-month prior years with an identical source cohort and verified complete export windows only; fewer than three comparable prior years yields no baseline |
| P0 | Evidence and export | Reproducible AOI JSON/CSV with raw provenance, method version, UTC/local calendar choice, and explicit unknown satellite coverage |
| P0 | Forest/vegetation context | Dated land cover and greenness condition, masked cloud/no-data; no claim that greenness alone establishes safety |
| P1 | Fire-weather context | NASA GFWED index, validity time and native coarse scale, separate from observed hotspots |
| P1 | Incident replay | At each replay timestamp, later detections and later perimeters remain hidden |
| P1 | Commander/crew exercise | Signed or versioned incident snapshot, approved polygon and routes, location accuracy/age, connection state, acknowledgments, local alert prototype; stale or disconnected is unknown |
| P2 | Radar change card | Dated before/after SAR evidence with optical cross-check and classification uncertainty |
| P2 | Spread ensemble | Multiple weather scenarios and arrival-time envelope, never labelled as measured fire boundary |

## 5. Calendar method and data rules

**Raw contract.** Store `source_id`, platform, sensor, product version, processing level, acquisition UTC, retrieval UTC, longitude/latitude, scan/track dimensions, raw confidence, raw FRP, day/night, optional thermal anomaly type, source URI, untouched source row, and file hash. MODIS numeric and VIIRS categorical confidence remain separate. FRP is not calibrated across sensors in the MVP.

**Common analysis unit.** Start with 1 km EPSG:6933 equal-area cells for local AOIs. Assign each detection centroid to one cell and count a cell at most once per UTC day in the joint series. This is **detected centroid cell-days**, a sampling proxy. Store original scan/track values; the centroid method does not prove full footprint overlap and will be replaced by a validated footprint/intersection study before claiming event deduplication. World tiles will use pre-aggregated coarser cells.

**Series.** Provide a stable MODIS standard-processing series from its available historical period, VIIRS S-NPP standard-processing from its available period, and an overlap-era joint series. Do not stitch early MODIS counts and later VIIRS counts into one falsely seamless trend. NOAA-20/21 may be added as separately labelled cohorts after an availability and overlap review. Standard and near-real-time processing cannot share a historical baseline.

**Calendar and anomaly.** Use UTC internally. The user interface may offer a local civil-date view with the AOI time zone recorded; date-line AOIs require explicit handling. Aggregate daily cell-days to a month; compare with the median of at least three previous complete-export years for the *same calendar month and source cohort*. In a replay, only prior years can contribute. A change from median is a count difference, not a forecast or a normalized exposure rate.

**Missingness.** “Complete export window” means the requested FIRMS CSV was fully collected for that AOI/month; it does **not** mean every satellite pass was clear or observed. FIRMS point records alone cannot establish cloud-free overpass coverage. Therefore satellite observation coverage remains `unknown` until mask/coverage products are ingested. An incomplete export has a null official count even if partial records exist. A complete export with zero detections means “zero detections in collected records,” not “observed fire-free.”

**Phase 1 comparison limit.** Source cohort and processing level are enforced, and original product versions are exposed. Automated collection-version equivalence and sensitivity adjustment await an overlap study; users should treat the baseline as a transparent exploratory comparison until those checks are complete.

**Classification.** Add land-cover strata and likely static-heat screening before users filter for forest/cropland. Keep an “other/uncertain” group. Candidate fire events, burned area, and physical wildfire counts need separate validated algorithms or products.

## 6. Data sources and constraints

| Input | Use | Constraint |
| --- | --- | --- |
| [NASA FIRMS area API](https://firms.modaps.eosdis.nasa.gov/api/area/) MODIS/VIIRS CSV | Core hotspot record | Free `MAP_KEY`, 1–5 day AOI requests, current source availability must be checked; long history should use standard products |
| [NASA EONET v3](https://eonet.gsfc.nasa.gov/docs/v3) wildfire events | Separate current-event map when FIRMS is inaccessible | Curated reported locations, including some prescribed fires; never substitute for sensor pixels or calendar coverage |
| [NOAA HMS daily historical fire points](https://www.ospo.noaa.gov/products/land/hms.html) | Independent North American VIIRS detection cohort for the authentic atlas | Verify every daily ZIP in an AOI/month; retain original ZIP hashes; do not merge with NASA FIRMS source series or infer pass/cloud coverage |
| MCD12Q1, MOD13Q1 / HLS | Land cover and dated vegetation condition | Land cover is broad; optical data can be cloud/smoke obscured |
| GFWED, GPM, SMAP | Regional fire-weather/moisture context | Scale is too coarse for a crew route |
| MCD64A1 / VNP64A1 | Retrospective burned-area check | Delayed, not live perimeter |
| FEDS / agency incident GIS | Replay reference and approved incident context | Coverage, latency and authority vary |
| SRTM/NASADEM, LANDFIRE, OSM | Later experimental terrain/fuel/path context | Trails and fuels require field review |
| OPERA RTC-S1 / NISAR | Later dated change evidence | SAR change is not live heat or trail passability |

NASA's [FIRMS documentation](https://firms.modaps.eosdis.nasa.gov/content/academy/data_api/firms_api_use.html) distinguishes standard processing from NRT and documents the CSV fields. The project must record collection versions and rerun affected aggregates when standard data replace NRT records.

## 7. Architecture and phase plan

**Target architecture:** Python ingestion/QA → PostGIS raw observations and spatial aggregates → FastAPI → React/MapLibre atlas and calendar. Prefetch global aggregates and historical partitions. Keep the FIRMS key on the server. An incident backend, WebSocket updates, and Android/Capacitor notification proof of concept follow only after the calendar works.

**Phase 1 — data foundation (started in this repository).** Build a local, reproducible vertical slice: FIRMS CSV schema and validation, file-hash provenance, common cells, UTC daily calendar, source-specific raw counts, joint cell-day counts, and prior-year same-source monthly baseline. A local SQLite store minimizes setup for the small AOI slice; migrate to PostGIS for world scale. A clearly synthetic demonstration is included. Real pilot results require a FIRMS key and selected AOIs.

**Phase 1 exit criteria:**

- Two FIRMS standard-product sources can be imported for the same complete AOI month without equating confidence classes.
- Reimporting the same export does not double count raw pixels.
- A MODIS pixel and several VIIRS pixels in one cell/day produce one joint cell-day and retain per-sensor raw counts.
- A complete month has a baseline only after three prior comparable, complete months; partial months and unknown satellite coverage are visible.
- Every output identifies grid method, source cohort, raw provenance, and whether it is demo data.
- Repeat the same checks with authentic standard-product AOI exports once a FIRMS key is available; choose a forest pilot and contrasting agricultural AOI, and document source availability.

**Phase 2 — judged web MVP.** AOI globe/map, daily and monthly charts, source toggle, evidence drawer, raw export, vegetation strata, dated weather layer, responsive layout. Run a user task: identify a seasonal peak and an unusual month, and explain why it is not a wildfire forecast.

**Current Phase 2 build:** interactive imported-record map with low-zoom grouping and local detection points, daily archive replay, map-to-AOI selection, daily/monthly calendar, source switch, raw evidence inspection, CSV exports, responsive layout, and dated NASA GIBS NDVI/annual land-cover overlays. The replay queries a selected acquisition date and can focus on its displayed points; large month views sample across all acquisition dates for display while the calendar uses all rows. The GIBS images are visual context; they do not provide a class mask or greenness anomaly calculation. No GFWED source has been imported, so the weather control reports unavailable. Authentic FIRMS AOI validation remains pending downloaded standard-product records; the independent NOAA HMS pilot is populated and reproducible.

**Phase 3 — training bridge.** Causal historical replay, scripted incident polygons, commander/crew simulated screens, stale/unknown state, route expiry and deterministic alerts. Test airplane mode and stale GPS. It is an exercise, not an authorized safety system.

**Current Phase 3 build:** `/training.html` provides a one-hour fictional Alder Creek replay. Server snapshots filter observations by acquisition and publication time, and zones/routes by publication time. Commander and crew views share the same replay clock. Local rules check GPS age, heartbeat age, accuracy, snapshot expiry, route expiry and zone intersection. Airplane-mode and stale-GPS drills exercise unknown states; an actual browser network disconnect uses the last received snapshot while the replay advances. Alert and route acknowledgments are retained in the current tab and exported with the received snapshot and local assessment. Snapshots include a scenario version and deterministic SHA-256 content identifier, not a cryptographic signature.

**Phase 3 validation:** automated checks cover causal release boundaries, deterministic snapshots, route intersection (including segments whose endpoints are outside the zone), route expiry, stale GPS and unknown offline state. Browser checks cover replay, rewind, acknowledgments, export, playback, real browser offline/reconnect behavior and mobile layouts. Rewinding discards later acknowledgments; restarting clears the exercise record.

**Phase 3 remaining field work:** authentic incident replay data, specialist-reviewed thresholds, shared authenticated commander/crew sessions, durable acknowledgment delivery, native/background device notifications, and physical-device airplane/GPS testing. The current implementation is a local browser exercise; Phase 7 adds offline reload for a prepared tab. No real incident or device position is used.

**Phase 4 — research extensions.** Calibrated source sensitivity bands from overlap studies; coverage-adjusted rates using proper masks; candidate event tracking; optional SAR evidence and ensemble spread for one validated region.

**Current Phase 4 build:** `/research.html` analyzes imported MODIS SP and VIIRS S-NPP SP observations for an AOI/month through an acquisition-date cutoff. Daily common-cell overlap, source-specific raw counts, co-occurrence fraction and the VIIRS/MODIS cell-day ratio are inspectable and exportable. An exploratory paired-day percentile band is enabled only for complete exports, one collection version per source and at least ten active days. It is not a calibrated sensitivity estimate. Candidate groups use adjustable geodesic distance and UTC-date gaps, with membership and source detection IDs exposed.

**Coverage adapter:** a prepared `fireatlas-coverage-v1` JSON mask supplies observed/cloud/no-pass/unknown source/cell/day statuses with grid, AOI, dates and provenance. Rates use only the intersection of detections and supplied observed exposure. Missing rows remain unknown; conflicts and synthetic/authentic mixtures are rejected; incomplete source exports suppress rates. The bundled synthetic example fabricates exposure solely to demonstrate the workflow. Direct satellite raster processing and mask validation are not implemented.

**Phase 4 validation and limits:** automated checks cover duplicate pixels, paired resampling, mixed collections, cutoff membership, geodesic clustering, missing exposure, conflicting masks, incomplete imports and malformed requests. Browser checks cover assumption changes, mask import/rejection, JSON exports, cutoff changes, empty states and responsive layouts. Research cutoffs are retrospective acquisition dates, not causal publication-time replay. Full calibration still requires authentic paired observations, validated masks, reference labels and held-out validation. SAR and spread extensions remain explicitly unavailable until suitable regional inputs and validation are supplied. See `docs/RESEARCH_METHODS.md` for the implemented methods and contracts.

**Phase 5 — reproducibility and sharing (added after Phase 4).** Let users return to an exact atlas selection and retain the evidence behind a comparison. Shared links restore AOI, year, month, source cohort, selected UTC day and context layer. Up to 20 named views can be saved in the current browser. Restoring a view preserves missing months rather than silently switching to an available month. A source ledger exposes selected-year import provenance and file hashes.

**Study bundle:** `/api/study` exports a versioned ZIP with selection, full-year calendar, normalized observations with original source rows, complete export windows, batch provenance, method instructions and a SHA-256 manifest. Inputs include every prior same-month year used in baseline comparisons. A single database read transaction keeps the export internally consistent. The bundle refuses requests exceeding 50,000 observations, including baseline inputs, rather than silently truncating them. `python -m fireatlas.study study.zip` verifies file hashes and recomputes daily/monthly cell-day totals, missingness, baseline medians and differences.

**Phase 5 validation and limits:** automated tests cover baseline input retention, raw provenance, empty/incomplete scopes, invalid selections, export limits, hash corruption, and mismatched calendar totals even after a checksum is recomputed. Browser checks cover saved-view creation/restoration/deletion, shared-day restoration, missing-month reloads, ZIP download and mobile layouts. Saved views remain local to one browser; links require access to the same server and reflect its current data. Bundles freeze the included inputs but do not embed full original import files, map tiles or context imagery. File hashes are integrity checks, not source authentication. This phase does not supply the authentic observations or specialist validation still required by Phase 4.

**Phase 6 — authentic-data integration and pilot validation.** A server-only FIRMS credential is loaded from the environment or an owner-only file outside the project. `/data.html` displays connection verification, source imports, pilot export completeness and validation status. The same-origin local sync action runs a background import of July 2021–2024 MODIS SP and VIIRS S-NPP SP for two geographic comparison areas. Successful full-month imports are resumable; failed requests never mark a month complete. The importer rejects a database containing synthetic data. A successful run checks both sources and three prior-year baselines, then reproduces calendar totals from exported study inputs. The default server now uses a separate authentic-data database; the synthetic demonstration remains available with an explicit database option.

**Phase 6 execution status (27 September 2026):** credential configured; primary and secondary FIRMS host connectivity checks timed out. FIRMS key activation and source availability could not be verified. NOAA HMS daily archives were reachable and provided 49,420 authentic VIIRS points in the Northern California pilot for July 2021–2024. All 124 daily ZIPs were present and schema checked; the four derived AOI/month CSVs and daily ZIP hashes are bundled for a reproducible first-launch view. The 2024 calendar has 2,197 detected cell-days and a 2021–2023 median of 109. This verifies the application's count pipeline, not scientific anomaly significance or complete satellite pass coverage. Regional classification, reference-label checks, validated masks and specialist review remain outstanding.

**Data-access workaround:** a NOAA HMS harvester reads its independent historical daily fire-point ZIPs, selects VIIRS detections, checks coordinates and UTC acquisition fields, and imports a complete AOI/month only after all daily files validate. The authentic atlas opens on this pilot cohort. A separate lightweight harvester caches recent NASA EONET wildfire-category events for the reported-event map; its cache refreshes hourly and survives connection failures. NASA's authenticated FIRMS Archive Download plus the existing local CSV importer remains the historical MODIS/VIIRS fallback. NOAA and FIRMS source cohorts remain separate, and EONET events never enter the sensor calendar or its baselines.

**Phase 7 — offline training continuity (implemented).** A versioned, training-scoped service worker caches the static exercise shell. Per-tab recovery retains only the received snapshot, public scenario, replay position, crew selection, drills and local acknowledgments. Reload resumes paused; cached evidence stays visibly disconnected until a fresh response arrives. An offline tab cannot rewind before its received snapshot or retrieve future evidence. New tabs without saved evidence withhold the briefing. Malformed, incompatible or causally inconsistent recovery records are rejected. Restart clears records after a successful new briefing; server scenario-version changes invalidate the old session.

**Phase 7 validation and limits:** automated recovery checks and real browser offline/reload checks cover acknowledgment retention, GPS drills, causal rewind, offline export, reconnect, restart and empty new tabs. The cache contains no API responses. Desktop/mobile layouts were checked. Recovery survives reloads of the same tab; users must export before closing it. There is no cross-device synchronization, remote acknowledgment delivery, background notification service or physical-device field validation. The replay clock remains paused across reloads.

**Presentation experience — visible demonstration path.** The website defaults to an explicitly labelled synthetic example while authentic imports are pending. A one-click source switch selects the isolated authentic database. A five-stop guided tour operates the actual map, calendar, source selection, evidence drawer, and Training Lab entry. A month-level comparison card exposes source-specific raw pixel counts next to joint cell-days and explains the different units. Links, downloads and Research Lab requests preserve the selected mode. Missing real exports show unknown values rather than synthetic numbers. This work improves the judged browser experience; it makes no additional scientific claims.

## 8. Product success and release gates

- **Science:** manual review of paired detections and the 2011–2014 transition shows the displayed series does not imply a sensor-change fire surge.
- **Comprehension:** a user can state what a hotspot, cell-day, event and burned area mean, and identify an incomplete or unknown-coverage month.
- **Reproducibility:** downloaded AOI rows reproduce the plotted calendar with published code and source version.
- **Replay integrity:** no information from later overpasses or final burned-area maps appears at earlier replay times.
- **Human safety:** disconnected crew is gray/unknown; an unvalidated route is never displayed as safe. Field claims require specialist validation and real-device tests.

## 9. Open decisions and external inputs

1. Select the exact pilot forest and agricultural AOIs, dates and validation incident. The PDF suggests California's 2024 Park Fire; that is a candidate, not yet a chosen dataset.
2. Obtain a free NASA FIRMS `MAP_KEY` and confirm source availability before real ingest. The key stays in a local environment variable and is never saved in the database.
3. Choose local-time display policy for AOIs spanning multiple time zones.
4. Obtain land-cover/observation masks and a documented overlap study before classifying forest-only activity or adjusting rates for sensor exposure.
5. Obtain incident specialist input before setting any distance, lead-time, alert or route threshold.

## 10. Demonstration narrative

Show a forest and cropland AOI; select one month; switch MODIS, VIIRS and joint cell-days; inspect the original rows behind a duplicate day; show a missing or incomplete month and a prior-year baseline. Then, only after the P0 experience is stable, open an explicitly simulated crew exercise. Acknowledge NASA FIRMS and Fire Event Explorer as existing systems; FireAtlas's contribution is transparent cross-sensor comparison and careful uncertainty communication.
