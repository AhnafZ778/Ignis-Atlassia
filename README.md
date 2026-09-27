# FireAtlas — atlas, training and research labs

The [PRD](PRD.md) defines the full NASA Space Apps project. The local web MVP runs on the Phase 1 data pipeline: NASA FIRMS CSV import, original-row provenance, 1 km common-cell assignment, and a UTC burning activity calendar with comparable prior-year monthly baselines.

## Launch the website

```bash
uv sync
uv run python -m fireatlas.web --db data/fireatlas.sqlite3 --port 8000
```

Open **http://127.0.0.1:8000/**. On first launch, the default authentic database loads a compact, verified NOAA HMS VIIRS pilot slice from July 2021–2024 in Northern California. The landing page opens on its real July 2024 atlas and calendar. Switch to **Explore demo** for the separately labelled synthetic MODIS/VIIRS comparison. A separate NASA EONET map shows recent reported fire events. Open **http://127.0.0.1:8000/data.html** to inspect both authentic source paths and FIRMS connectivity. The maps, source switch, daily calendar, dated NASA GIBS NDVI/land-cover overlays, evidence records, and CSV exports are interactive. The site binds to localhost by default. It uses OpenStreetMap tiles and NASA GIBS imagery over the network; the event feed, calendar and imported points still work if those external tiles fail.

**Guided tour:** Use **Start the guided tour** on the landing page. Five interactive stops move through the AOI map, monthly activity, sensor switch, original evidence, and the Training Lab. The example shows four MODIS raw pixels, twelve VIIRS raw pixels, and four joint cell-days in July 2015; the measures and synthetic source are labelled. This tour uses the normal controls and queries. Shared atlas links, CSV exports and study bundles retain the selected demo/authentic context. The Research Lab also opens the same mode from the atlas.

The homepage uses the interactive WebGL Earth from the supplied `earth.html` file in a full-width landing scene on desktop and mobile. The landing mode centers the globe, adapts its framing to the screen, and allows normal page scrolling. “Explore full Earth” opens the standalone page with all its controls and asset credits. A lightweight still from the same renderer appears while the model loads or when WebGL is unavailable. The scene is self-contained and approximately 14 MB; it needs WebGL 2. Its composite imagery and lighting are illustrative, not live fire or weather information.

The atlas, Training Lab, and Research Lab share the visual system in `fireatlas/static/design.css`: graphite surfaces, ember accents, responsive layouts, and locally served DM Sans and Space Grotesk fonts. Font licenses are included in `fireatlas/static/fonts/`. Shared navigation behavior lives in `fireatlas/static/ui.js`, including the mobile menu and keyboard dismissal. Reduced-motion preferences are supported by the interface transitions.

The sensor atlas map only shows **imported** records; the independent EONET map shows reported events. Empty or incomplete source exports remain unknown. The bundled NOAA pilot covers one Northern California bounding box and four July months, not global satellite coverage. The app does not provide live hotspot monitoring, measured fire-weather risk, a verified vegetation mask, or a safety service. The Fire weather layer explicitly says no GFWED data are loaded. To run the synthetic demonstration separately, use `uv run python -m fireatlas.web --db data/demo.sqlite3 --port 8001`; it creates the demo database if needed. Synthetic and authentic observations remain in separate databases.

### Authentic NOAA satellite showcase

The bundled [`NOAA HMS historical fire-point archive`](https://www.ospo.noaa.gov/products/land/hms.html) slice contains 49,420 VIIRS point records inside `-122,39,-120,41`. The importer verified all 31 daily archives in each July 2021–2024 month before declaring that **AOI/month export** complete. The package includes the derived CSVs, source ZIP URLs and SHA-256 hashes in `fireatlas/samples/`; the much larger original ZIPs and SQLite database remain local and ignored by Git. The 2024 view has 2,197 detected 1 km cell-days and a 2021–2023 median of 109. These are detection centroid counts, not fire incidents, burned area, or scientific anomaly calibration. Pass/cloud coverage remains unknown. The HMS `scan` and `track` values use the nominal 375 m VIIRS I-band resolution because the archive does not provide an individual pixel footprint; confidence and day/night are labelled unavailable.

To refresh any historical month directly from NOAA, run:

```bash
uv run python -m fireatlas.cli --db data/fireatlas.sqlite3 harvest-hms --month 2024-07 --bbox -122 39 -120 41
```

The harvester caches the daily ZIPs in ignored `data/downloads/`, validates the point schema, records the original ZIP hashes in a manifest and in each selected row, and imports only the VIIRS method on Suomi NPP, NOAA-20 and NOAA-21. A failed or missing daily download never marks the month complete. Repeating the command is idempotent. On first default launch the bundled slice loads automatically into an empty authentic database; pass `--no-showcase` to start without it. HMS covers North America and remains a separate source cohort from NASA FIRMS MODIS/VIIRS.

The atlas map's **Replay the archive** control steps through actual acquisition dates. Select a daily bar to focus the map on that day's imported points, drag the slider, or play the month. The same dates appear in the calendar and lead to original source rows. Large monthly point sets are sampled across the entire month for display; the calendar and exports use all imported observations.

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

**Development environment note (27 September 2026):** FIRMS connections timed out during local checks, including a check against NASA's documented secondary host. A key's presence does not verify its validity or source availability. No authentic **FIRMS** pilot observations or scientific calibration results are claimed; the independent NOAA HMS pilot above is real satellite data. Retry FIRMS from the Data sources page when connectivity is restored. NASA documents its secondary service in the [FIRMS system update](https://firms.modaps.eosdis.nasa.gov/notifications/firms/update.html).

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
- Set the acquisition cutoff, distance threshold and date gap to explore candidate detection groups. The default July 2015 demo has one four-day group; choosing **Same day only** splits it into four groups.
- Import a prepared observation-mask JSON file to calculate rates within supplied observed exposure. **Load synthetic example** demonstrates the calculation: four detected cell-days / 31 assumed observed cell-days for each sensor, or about 12.9 per 100. These denominators are fabricated and labeled.
- Export the study, input mask, parameters, source hashes, candidate membership and report identifier as JSON. Uploaded masks are evaluated for the request and are not saved to the database. Download them before leaving the page if needed.

The exploratory ratio band requires at least ten active days, complete source exports and one product version per source. The small default demo correctly withholds that band. Calibrated sensitivity, verified masks, SAR change evidence and regional spread ensembles require external datasets and scientific validation; the lab exposes their status without fabricating results.

The same study is reproducible from the CLI:

```bash
uv run python -m fireatlas.cli --db data/demo.sqlite3 research \
  --year 2015 --month 7 --bbox -122 39 -120 41 \
  --distance-km 2 --gap-days 1 --output data/research-study.json
```

Add `--as-of 2015-07-02` to limit acquisition dates, or `--mask path/to/coverage.json` to use a prepared coverage mask. [Research methods and mask format](docs/RESEARCH_METHODS.md) describe the calculations, limits, data requirements and reference documentation.
