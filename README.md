# FireAtlas — atlas, training and research labs

## Presentation guide and mobile app

[Download the 22-page feature polish guide](docs/presentation/FireAtlas_Feature_Polish_Guide.pdf) for 16 prioritized features, exact pages, actual screenshots and presentation checks.

FireAtlas now includes an installable mobile web app. Open `/install.html` for installation instructions; see [mobile setup and verification](docs/MOBILE_APP.md). The prepared Training Lab works offline. There is no native APK/iOS build, and the globe and analysis tools still require the server. A physical-phone rehearsal and reachable HTTPS host remain necessary.

The [PRD](PRD.md) defines the full NASA Space Apps project. The local web MVP runs on the Phase 1 data pipeline: NASA FIRMS CSV import, original-row provenance, 1 km common-cell assignment, and a UTC burning activity calendar with comparable prior-year monthly baselines.

## Launch the website

```bash
uv sync
uv run python -m fireatlas.web --db data/fireatlas.sqlite3 --port 8000
```

Open **http://127.0.0.1:8000/**. On first launch, the default authentic database loads a compact, verified NOAA HMS VIIRS pilot slice from July 2021–2024 in Northern California. The landing page opens on its real July 2024 atlas and calendar. Switch to **Explore demo** for the separately labelled synthetic MODIS/VIIRS comparison. A separate NASA EONET map shows recent reported fire events. Open **http://127.0.0.1:8000/data.html** to inspect both authentic source paths and FIRMS connectivity. The maps, source switch, daily calendar, dated NASA GIBS NDVI/land-cover overlays, evidence records, and CSV exports are interactive. The site binds to localhost by default. It uses OpenStreetMap tiles and NASA GIBS imagery over the network; the event feed, calendar and imported points still work if those external tiles fail.

**Guided tour:** Use **Start the guided tour** on the landing page. Five interactive stops move through the AOI map, monthly activity, sensor switch, original evidence, and the Training Lab. The example shows four MODIS raw pixels, twelve VIIRS raw pixels, and four joint cell-days in July 2015; the measures and synthetic source are labelled. This tour uses the normal controls and queries. Shared atlas links, CSV exports and study bundles retain the selected demo/authentic context. The Research Lab also opens the same mode from the atlas.

The homepage uses the satellite Earth and World Elevation terrain from the supplied `fireatlas_terrain_fixed.html` demo, integrated through `/terrain-earth.html`. Its native ArcGIS projection keeps the clickable NASA FIRMS detections, historical flame textures, region navigation, zoom, rotation and date/sensor filters aligned with the globe. Elevation is sampled from the displayed terrain at close zooms. An accessible case/evidence list supplies the same records when 3D is unavailable. “Explore terrain Earth” opens the terrain globe with California and reset controls; the original self-contained visual model remains available at `/earth.html`. The terrain view loads ArcGIS Maps SDK 4.32, Esri imagery and World Elevation over the network and retains their attribution. Surface imagery is separate from the dated NASA detection overlay.

The landing globe uses **authentic NASA NRT imports only**, independently of the atlas's synthetic/authentic selector. With the current CSVs, it represents all **866,956 detections** as **7,307 one-degree geographic clusters** over September 20–27, 2026. Each marker sits at its observations' mean coordinates; its size indicates detection count, and brighter points include observations from the latest day in the selected snapshot. Selecting a cell also displays up to 12 latest records at their original coordinates in cyan. These are detection groups, not fire incidents or perimeters. The panel identifies the first/last observations and maximum individual-pixel FRP; it does not infer ignition time, wildfire severity or current containment. Multiple satellites and repeat passes may observe the same fire.

The globe window includes the latest imported NASA observation date and seven preceding UTC dates. It follows the imported database rather than calling NASA APIs. Date/source filters and cluster details are cached briefly, with database changes invalidating the cache. Empty sources and failed requests are shown explicitly; neither NOAA HMS nor synthetic data substitutes for missing NASA globe data. A fresh checkout must import the recent NASA CSVs or receive the local database to reproduce this global overlay. [Globe implementation and verification](docs/GLOBE_OBSERVATIONS.md) records the supported behavior and interpretation.

The atlas, Training Lab, and Research Lab share the visual system in `fireatlas/static/design.css`: graphite surfaces, ember accents, responsive layouts, and locally served DM Sans and Space Grotesk fonts. Font licenses are included in `fireatlas/static/fonts/`. Shared navigation behavior lives in `fireatlas/static/ui.js`, including the mobile menu and keyboard dismissal. Reduced-motion preferences are supported by the interface transitions.

The sensor atlas map only shows **imported** records; the independent EONET map shows reported events. Empty or incomplete source exports remain unknown. The bundled NOAA pilot covers one Northern California bounding box and four July months, not global satellite coverage. The app does not provide live hotspot monitoring, measured fire-weather risk, a verified vegetation mask, or a safety service. In authentic mode, the Fire weather layer says no GFWED data are loaded. In demo mode, local synthetic context illustrations are available for the 2023–2026 Northern California scenario; the weather illustration uses arbitrary units, not computed FWI. To run the synthetic demonstration separately, use `uv run python -m fireatlas.web --db data/demo.sqlite3 --port 8001`; it creates the demo database if needed. Synthetic and authentic observations remain in separate databases.

### Authentic NOAA satellite showcase

The bundled [`NOAA HMS historical fire-point archive`](https://www.ospo.noaa.gov/products/land/hms.html) slice contains 49,420 VIIRS point records inside `-122,39,-120,41`. The importer verified all 31 daily archives in each July 2021–2024 month before declaring that **AOI/month export** complete. The package includes the derived CSVs, source ZIP URLs and SHA-256 hashes in `fireatlas/samples/`; the much larger original ZIPs and SQLite database remain local and ignored by Git. The 2024 view has 2,197 detected 1 km cell-days and a 2021–2023 median of 109. These are detection centroid counts, not fire incidents, burned area, or scientific anomaly calibration. Pass/cloud coverage remains unknown. The HMS `scan` and `track` values use the nominal 375 m VIIRS I-band resolution because the archive does not provide an individual pixel footprint; confidence and day/night are labelled unavailable.

To refresh any historical month directly from NOAA, run:

```bash
uv run python -m fireatlas.cli --db data/fireatlas.sqlite3 harvest-hms --month 2024-07 --bbox -122 39 -120 41
```

The harvester caches the daily ZIPs in ignored `data/downloads/`, validates the point schema, records the original ZIP hashes in a manifest and in each selected row, and imports only the VIIRS method on Suomi NPP, NOAA-20 and NOAA-21. A failed or missing daily download never marks the month complete. Repeating the command is idempotent. On first default launch the bundled slice loads automatically into an empty authentic database; pass `--no-showcase` to start without it. HMS covers North America and remains a separate source cohort from NASA FIRMS MODIS/VIIRS.

The atlas map's **Replay the archive** control steps through actual acquisition dates. Select a daily bar to focus the map on that day's imported points, drag the slider, or play the month. The same dates appear in the calendar and lead to original source rows. Large monthly point sets are sampled across the entire month for display; the calendar and exports use all imported observations.

The daily calendar shows exact distinct detected-cell counts on a year-wide logarithmic color scale, with UTC dates, source series and AOI bounds shown alongside it. A complete-export zero is separate from unknown activity; positive partial-import counts are shown as lower bounds (≥) and never treated as a complete month. Monthly values sum daily cells into cell-days. Peak labels apply only to loaded complete data. Select a date to trace its sensor pixels, or move between dates with arrow keys and activate with Enter. Common-grid aggregation does not calibrate sensor sensitivity or establish satellite pass/cloud coverage.

To launch with your own imported FIRMS data, pass `--db data/fireatlas.sqlite3`; the AOI field accepts `west,south,east,north`. The server reads the database and does not call FIRMS from browsers. Download authentic data with the instructions below, then restart or refresh the site.

## Save, share and reproduce an atlas study

The calendar includes a **Keep the evidence** panel:

- **Save view** stores a named AOI/year/month/sensor/day/context selection in this browser (up to 20). Choose it from the saved list to open or remove it.
- **Copy view link** creates a URL restoring the same selection. The recipient needs access to the same running server and dataset; a localhost link only works on your computer. Links use the server's current data.
- **Download study** freezes the selected-year calendar and its supporting observations, including prior-year baseline inputs, in a ZIP. It also contains complete export windows, original source rows, batch provenance and file checksums. More than 50,000 observations requires a smaller AOI.
- **Source ledger** shows selected-year import sources, retrieval times and original file hashes.

Verify a downloaded bundle without querying the database:

```bash
uv run python -m fireatlas.study ~/Downloads/fireatlas_study_joint_2015.zip
```

The verifier checks SHA-256 integrity and reproduces daily/monthly cell-day counts, completeness, baseline medians and differences using the included normalized grid assignments. It does not independently validate satellite observations or the grid transform. Bundles omit full original import files, map imagery and research masks; file hashes are not authenticity signatures. Synthetic data remain labelled throughout the bundle.

## Run the synthetic example

Python 3.10+ and `pyproj` are required. Install with `uv sync` and run the commands below. Alternatively, use `python3 -m pip install -e .` and replace `uv run python` with `python3`.

```bash
uv run python -m fireatlas.demo
uv run python -m fireatlas.cli --db data/demo.sqlite3 calendar \
  --bbox -122 39 -120 41 --year 2015 --series joint \
  --output data/demo-calendar.json
uv run python -m unittest discover -s tests -v
```

Everything in `data/demo/` is **synthetic** and labelled as such in JSON output. The July 2015 example has repeated pixels from two sensors in the same cell: joint cell-days remain deduplicated, while raw sensor pixel counts remain separate. The baseline uses only prior 2012–2014 July windows. This demonstrates behavior, not real fire history.

## Use authentic NASA FIRMS data

Request a free [FIRMS MAP_KEY](https://firms.modaps.eosdis.nasa.gov/api/map_key). Keep it in your shell environment or in `~/.config/fireatlas/firms.key` with owner-only permissions (`chmod 600`). `FIRMS_MAP_KEY` overrides the key file; `FIRMS_KEY_FILE` can select a different file. Do not commit credentials. The key is never returned by the website or included in downloaded studies. Select a modest AOI and a month offered by the chosen standard-processing source; verify availability with [NASA's availability endpoint](https://firms.modaps.eosdis.nasa.gov/api/data_availability/).

### Imported NASA snapshot: September 20–27, 2026

The three CSVs supplied in `NASA_data/` contain 866,957 rows. The local authentic database now holds 866,956 of these detections: MODIS NRT **72,776**, NOAA-20 VIIRS NRT **394,527**, and NOAA-21 VIIRS NRT **399,653**. One NOAA-21 row at latitude -86.2141 is outside the supported EPSG:6933 region; its original row, CSV line number and reason are retained in `excluded_rows`. Original files are unchanged and ignored by Git; their exact hashes and official download URLs are recorded in the database. These downloads are local and are not included in the bundled NOAA showcase or repository.

Open `/data.html` and use the NASA snapshot links to view each source globally, then select an acquisition day or zoom in. Low-zoom bins count all imported points in the viewport. High-zoom display samples at most 1,000 points across the entire selected period, with the full imported count reported. Sampling does not affect calendar counts or evidence. The files are rolling seven-day near-real-time snapshots touching eight UTC dates; they do not establish complete September exports or replace the historical 2021–2024 standard-product comparison.

The importer accepts NASA public CSVs without an `instrument` column, deriving the normalized sensor from the selected source and validating its satellite identifier. Original row JSON stays unchanged. Large CSVs stream through one transaction instead of being held in memory. To repeat an import (duplicates are ignored):

```bash
uv run python -m fireatlas.cli ingest NASA_data/J2_VIIRS_C2_Global_7d.csv \
  --source VIIRS_NOAA21_NRT --exclude-outside-grid \
  --source-uri https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-21-viirs-c2/csv/J2_VIIRS_C2_Global_7d.csv
```

The `--exclude-outside-grid` option preserves polar rows separately and is restricted to partial imports. Invalid records within the grid still roll back the new batch. Use the CLI for files above the browser upload limit of 25 MB. NASA's original recent files remain snapshots, not a continuously updating feed.

### September 2026 data continuity and manual downloads

The Data Sources page includes the FIRMS2 maintenance advisory captured on September 27 (disruption may extend through September 30), and NASA's planned November 1 Suomi NPP delivery cessation. The maintenance panel switches to historical wording after that window; it never declares recovery automatically. The S-NPP historical study remains separate from future NOAA-20/21 imports.

FIRMS downloads try the primary host, then the official secondary host for connection failures and HTTP 5xx responses. Authentication errors, malformed responses and rate limits are reported without trying to bypass them. Availability checks still gate full-month downloads. Neither host nor the nrt3/nrt4 daily archive could be reached from this machine during the September 27 checks; a configured key is not a verified key.

**Nothing must be downloaded to explore the bundled NOAA showcase.** To finish the real FIRMS historical comparison while the API is unreachable, request eight CSV exports from [NASA Archive Download](https://firms2.modaps.eosdis.nasa.gov/download/):

- Products: **MODIS Collection 6.1 standard** and **VIIRS Suomi NPP 375 m standard**.
- Dates: **July 1–31 in 2021, 2022, 2023 and 2024**, one file per product and month.
- Bounding box: **west -122.2, south 38.8, east -120, north 41**, covering both pilot areas.

On `/data.html`, select the downloaded CSV and exact product. Assert a complete month only for a verified full export and enter its month and exact bounding box. Eight full exports over this enclosing area satisfy the 16 individual pilot windows. The importer checks row dates, coordinates, instrument and satellite, preserves row provenance and file hashes, rejects NRT-labelled records under a standard product, and prevents duplicate detections. The full-export declaration comes from the user: CSV rows alone cannot prove missing days were observed. Partial files never establish complete export windows.

Recent 24-hour/48-hour/7-day CSVs can also be imported with the full-month checkbox unchecked. The source ledger links to their atlas view. NOAA-20 standard and NOAA-20/21 NRT, S-NPP NRT and MODIS NRT have separate series; they do not silently replace the historical MODIS/S-NPP comparison. The current CLI can fetch complete months for these sources when the availability API offers them; it does not yet harvest rolling recent windows automatically.

The daily HTTPS text archive in NASA's Active Fire page requires **Earthdata Login**, separate from MAP_KEY. That authenticated file route is **not automated** here. Archive Download may use an email verification code. WMS/KML/shapefiles and Landsat are not required for this pilot; the CSV importer supports MODIS and VIIRS, not Landsat. GIBS imagery is visual context and does not provide the observation masks or weather datasets needed for calibrated research.

Browser imports are limited to 25 MB, same-origin requests and the local app. Larger files can use the existing CLI. Run sync again after manual imports to reproduce all completed pilot totals; no NASA request is needed if every pilot window is already present.

### Authentic-data pilot workflow

The **Data sources** page shows credential configuration separately from successful NASA verification, import progress, a per-source/year completeness matrix, and reproducibility results. **Sync pilot data** runs a background import; **Retry pilot sync** resumes completed source-months after a failure. The action is limited to same-origin requests on the local app. Remote/public deployment needs a separately authenticated administrative workflow.

The pilot plan imports MODIS SP and VIIRS S-NPP SP for July 2021, 2022, 2023 and 2024 in Northern California and Sacramento Valley. These are geographic comparison areas, not validated forest/agricultural masks or incident boundaries. The last year is compared against the three prior years. Successful completion checks study checksums, daily/monthly cell-day totals, missingness and baseline medians. This is reproducibility verification, not scientific calibration.

The same workflow is available from the terminal:

```bash
uv run python -m fireatlas.cli firms-status
uv run python -m fireatlas.cli --db data/fireatlas.sqlite3 sync-pilots
```

The sync exits nonzero on failure. Status is retained in `data/fireatlas.sync.json`, and successful checks in `data/fireatlas.validation.json`. CSV downloads are cached under `data/downloads/`. Completed imports are retained and reused; incomplete monthly requests never receive a complete-export marker. A demo database is rejected before authentic imports can begin.

**Development environment note (27 September 2026):** FIRMS connections timed out during local checks, including a check against NASA's documented secondary host. A key's presence does not verify its validity or source availability. The recent user-downloaded FIRMS snapshots are imported, but the complete historical FIRMS pilot and scientific calibration remain pending; the independent NOAA HMS pilot above is also real satellite data. Retry FIRMS from the Data sources page when connectivity is restored. NASA documents its secondary service in the [FIRMS system update](https://firms.modaps.eosdis.nasa.gov/notifications/firms/update.html).

### Reachable NASA event-feed workaround

The [NASA EONET v3 wildfire-event feed](https://eonet.gsfc.nasa.gov/docs/v3) is reachable from this machine. `fireatlas.events` harvests up to 200 recent reported event points, validates their type, coordinates and timestamps, and atomically caches a snapshot in ignored `data/fireatlas.events.json`. The homepage displays the event map and a shortlist; the Data sources page shows the feed status. The cache refreshes after one hour or when **Refresh** is pressed. If NASA is temporarily unreachable, the last snapshot is labelled cached. To refresh it from the terminal:

```bash
uv run python -m fireatlas.cli --db data/fireatlas.sqlite3 harvest-events
```

EONET's wildfire category can include prescribed fires. Its reported event locations are **not** MODIS/VIIRS detections and never feed the sensor calendar, baselines or research calculations. The 200-point limit is a recent sample, not a complete global event count.

For historical sensor records while the area API is inaccessible, use the [NASA FIRMS Archive Download](https://firms.modaps.eosdis.nasa.gov/download/) from a connection that can reach it, then import the downloaded CSV with `fireatlas.cli ingest` below. The archive requires an Earthdata login or email verification. Declare `--complete-month` only for a verified full month and matching AOI export; otherwise import it as partial and leave official monthly counts unknown.

### Individual source-month imports

```bash
export FIRMS_MAP_KEY='your-private-key'
uv run python -m fireatlas.cli fetch-month --source MODIS_SP --month 2024-07 \
  --bbox -122 39 -120 41
uv run python -m fireatlas.cli fetch-month --source VIIRS_SNPP_SP --month 2024-07 \
  --bbox -122 39 -120 41
uv run python -m fireatlas.cli calendar --year 2024 --series joint \
  --bbox -122 39 -120 41 --output data/2024-calendar.json
```

`fetch-month` requests the NASA area API in at most five-day windows, writes one CSV in ignored `data/downloads/`, and imports it only when every window succeeds. It stores a source URL with `[MAP_KEY]` placeholder rather than the private key. For a local CSV export:

```bash
uv run python -m fireatlas.cli ingest path/to/MODIS.csv --source MODIS_SP \
  --complete-month 2024-07 --bbox -122 39 -120 41
```

Declare `--complete-month` only when the file contains the entire requested AOI/month export, including the possibility of an empty detection list. Without that declaration the file is ingested as partial and official daily/monthly counts remain null. A complete CSV export still does **not** establish cloud-free satellite coverage: the JSON reports that separately as `unknown`.

## What the number means

`detected_centroid_cell_days` counts distinct 1 km EPSG:6933 cell centroids on each UTC day. Two sensors detecting the same cell/day contribute one joint cell-day. It is a sampling proxy, not a fire-event count, burned area, or footprint-based co-detection. The imported `scan` and `track` dimensions are preserved, but this prototype does not intersect full sensor footprints. The `modis` and `viirs-snpp` series stay separate across the sensor transition; `joint` is for overlap years.

`baseline_median` requires at least three earlier same-month complete exports for the same source cohort and AOI. No baseline is fabricated when that evidence is absent. The current web MVP has no land-cover class mask, pass/cloud coverage denominator, GFWED import, or crew safety feature. NASA GIBS overlays are imagery context only.

The web interface vendors [Leaflet 1.9.4](https://leafletjs.com/download.html) under its BSD 2-Clause license in `fireatlas/static/vendor/`.

## Phase 3: Training Lab

Open **http://127.0.0.1:8000/training.html**, or select **Training** from the homepage. The fictional Alder Creek incident runs from 12:00 to 13:00 UTC with synthetic zones, routes, observations and three crews. It has no external map-tile dependency.

1. Play the replay, step five minutes, or scrub the timeline. New evidence appears only at its publication time.
2. At 12:20, inspect the zone revision, Crew Alpha's zone intersection, and the conflicting route. At 12:25, the first route expires; a revised route arrives at 12:30.
3. Switch to **Crew device**, choose a crew and acknowledge the route briefing or an alert. Acknowledging an alert does not clear its underlying condition.
4. Enable **Stale GPS** to hold an old location for the selected crew. Enable **Airplane mode** and advance time: cached evidence remains visible, crew status becomes unknown and routes still expire. Disable the drill to fetch the current snapshot. Actual browser offline events use the same path.
5. Export the JSON exercise record with the current received snapshot, local assessment, drills and acknowledgments. Rewinding removes later acknowledgments; restarting clears them all.

The snapshot includes a scenario version and deterministic SHA-256 identifier. It is not signed. Acknowledgments remain in the browser tab and are not sent to another user or device. The local alert prototype includes visual, screen-reader and optional sound cues while the page is open. It is not a background notification service. The loaded page can continue local checks after disconnection, and Phase 7 adds offline reload for a prepared tab. Physical-device airplane-mode and GPS tests remain pending.

### Phase 7: offline training recovery

1. Open `/training.html` while connected. Wait for **Offline page ready** and **Progress saved in this tab**.
2. Advance the replay, choose a crew and acknowledge a briefing or alert. Your replay position, selected view, GPS/offline drills and local acknowledgments are saved automatically in this tab.
3. Disconnect and reload the same tab. It restores the last received snapshot, pauses the replay, and marks crew status unknown until a fresh server response arrives. The exercise clock stays at its saved time; wall-clock time away does not advance this simulation.
4. Continue forward offline and export the exercise record. Rewinding earlier than the received snapshot requires reconnection. A new offline tab without a saved briefing cannot invent one.
5. Reconnect to receive evidence appropriate to the current replay time. A scenario-version change starts a new briefing. Restart clears the record only after the new briefing is successfully received.

The offline pack caches only the Training Lab page, scripts, styles, fonts and local map library. API responses, the atlas, credentials and future snapshots are excluded. Recovery uses per-tab `sessionStorage`: export your record before closing the tab. Browser storage can be cleared or unavailable; the page reports that condition. This does not add cross-device acknowledgment delivery or real incident operations.

The service worker requires localhost or HTTPS. Its scope is `/training.html`. When changing any asset in its pack, increment `CACHE` in `fireatlas/static/training-sw.js`; a new pack activates once existing Training Lab tabs close. The implementation follows browser [service-worker lifecycle](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers) and [sessionStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/sessionStorage) behavior.

Exercise rules use a 120-second GPS limit, 90-second heartbeat limit, 100-meter accuracy limit and 300-second snapshot validity. These are fictional exercise parameters, not operational thresholds. All aging follows the displayed replay clock; pausing or hiding the page pauses the exercise.

Run `uv run python -m unittest discover -s tests -v` to check the data pipeline, web endpoints and training behavior. The training tests also use **Node.js** to exercise the same local rule code used by the browser.

## Phase 4: Research Lab

Open **http://127.0.0.1:8000/research.html**, or select **Research** on the homepage. The research entry below the atlas carries the selected AOI, year and month into the lab.

- Compare daily MODIS and VIIRS common-cell overlap, raw pixel counts and descriptive ratios. Inspect the exact counts and source versions in the expandable table.
- Set the acquisition cutoff, distance threshold and date gap to explore candidate detection groups. The default September 2026 synthetic study has three spatial groups and 26 active days. The older guided-tour July 2015 scenario remains available with one four-day group; choosing **Same day only** splits that group into four.
- Import a prepared observation-mask JSON file to calculate rates within supplied observed exposure. **Load synthetic example** demonstrates the calculation within generated cells. The Data Sources research link opens with this fabricated mask already selected. Changing the period or AOI clears it; all denominators are explicitly labelled synthetic.
- Export the study, input mask, parameters, source hashes, candidate membership and report identifier as JSON. Uploaded masks are evaluated for the request and are not saved to the database. Download them before leaving the page if needed.

The exploratory ratio band requires at least ten active days, complete source exports and one product version per source. The richer September 2026 demonstration meets these requirements; the older July 2015 guided tour still correctly withholds that band. Calibrated sensitivity, verified masks, SAR change evidence and regional spread ensembles require external datasets and scientific validation; the lab exposes their status without fabricating results.

The same study is reproducible from the CLI:

```bash
uv run python -m fireatlas.cli --db data/demo.sqlite3 research \
  --year 2015 --month 7 --bbox -122 39 -120 41 \
  --distance-km 2 --gap-days 1 --output data/research-study.json
```

Add `--as-of 2015-07-02` to limit acquisition dates, or `--mask path/to/coverage.json` to use a prepared coverage mask. [Research methods and mask format](docs/RESEARCH_METHODS.md) describe the calculations, limits, data requirements and reference documentation.


## Presentation dataset and data readiness

Open [Data Sources](http://127.0.0.1:8000/data.html) for the authentic imports and three demonstration entry points. No further NASA download is required to work on navigation and interactivity.

- **Authentic database:** 866,956 accepted detections from the three downloaded September 2026 CSVs, plus 49,420 NOAA HMS historical records. A polar row remains preserved in the exclusion ledger. Rolling NASA exports remain partial; missing days are never filled in authentic mode.
- **Separate synthetic database:** 11,322 presentation detections across 96 source-months, covering every month in 2023–2026. Three prior years support each 2026 monthly baseline. The old guided tour remains available, with its scenario excluded from the new baseline.
- **Traceable generation:** the small bundled `fireatlas/samples/presentation_seeds.json` contains sampled measured attributes, original CSV line numbers and SHA-256 hashes. All dates, positions, seasonality and paired satellite scenarios are invented; synthetic S-NPP-shaped records are not real NOAA-to-S-NPP conversions. The fixture includes hypothetical months after the current date.
- **Local context:** NDVI-style values, land-cover classes and an arbitrary weather index illustrate the controls. They are not inferred from the CSVs or presented as actual imagery, weather observations or forecasts. Synthetic context is restricted to the showcase region and explicitly gated by `demo=1`.
- **Portable evidence:** synthetic study ZIPs include generation provenance and selected context GeoJSON; Research Lab JSON includes seed provenance and any supplied exposure mask. CSV rows retain their synthetic flag, source URI and seed references.

The server creates fixtures on the first demo request, resumes interrupted generation and refuses to add them to a database containing authentic batches. To prebuild them before a presentation:

```bash
uv run python -m fireatlas.presentation --db data/demo.sqlite3
```

The original files in `NASA_data/` and the populated databases remain ignored by Git. The bundled seed sample and NOAA historical slice work from a fresh checkout; deploying the full recent authentic snapshot requires copying the database or importing those original CSVs. Synthetic presentation data is reproducible without those full files or a NASA API connection.

See [Data readiness and verification](docs/DATA_READINESS.md) for the tested scope and remaining scientific limits.

### Judge-ready demonstration

For a deterministic presentation from a fresh checkout, run:

```powershell
.\scripts\launch_judge_demo.ps1
```

This creates `data/judge-demo.sqlite3` locally from the versioned synthetic generator and serves the complete guided study at `http://127.0.0.1:8000/?demo=1`. Open the page once while connected so the app shell and successful API responses are cached; the atlas and insight card can then be rehearsed if the network drops. Synthetic data are labelled throughout and are never mixed into the authentic database.
