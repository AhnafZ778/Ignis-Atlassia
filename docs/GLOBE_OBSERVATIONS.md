# NASA observations on the landing Earth

The landing page displays the user's imported NASA FIRMS MODIS, NOAA-20 and
NOAA-21 CSV detections on the existing `earth.html` renderer. The full atlas,
research and training workspaces remain reachable through the navigation.

## Data interpretation

- Authentic NRT NASA sources only. Synthetic batches and NOAA HMS observations
  are excluded, including when the atlas below is in demonstration mode.
- A snapshot spans the latest NASA acquisition date and seven preceding UTC
  dates. The date range and latest acquisition time are visible. It is a local
  import, not a live NASA connection.
- Global markers aggregate all qualifying records in 1° longitude/latitude
  cells. Coordinates are the mean detection location, marker size encodes count,
  and brighter markers include the latest observed day in the selected view.
  All counts are retained; no first-N truncation is applied.
- A selected cluster shows source-specific totals, first and last acquisition
  times, maximum valid individual-pixel FRP in MW and up to 12 latest records
  with exact coordinates, original confidence values and source-file hashes.
  Cyan marks display those latest records at their original coordinates.
- Dates identify observations, not ignition. A cluster is not a wildfire
  incident or perimeter. FRP is not a severity or containment score. Repeated
  passes and different satellites can observe the same event; an empty location
  does not prove absence of fire. Current conditions after the last observation
  are unknown.

NASA describes the distinction between vegetation fires and other heat sources
in its [static thermal anomalies explanation](https://wiki.earthdata.nasa.gov/spaces/FIRMS/blog/2025/02/28/425855667/FIRMS%2Bincorporates%2Bstatic%2Bthermal%2Banomalies%2Bdata%2Bto%2Bhelp%2Busers%2Bdifferentiate%2Bbetween%2Bvegetation%2Band%2Bnon%2Bvegetation%2Bfires.).

## Interaction and rendering

The 2D marker overlay uses the same camera rotation, projection, distance and
framing as the WebGL sphere. Perspective horizon rejection hides the far side.
It draws in the same animation callback as the surface, including while dragging
and zooming. Selecting a point pauses rotation and turns toward its coordinates.
Dragging and pinch gestures do not select points. Region buttons and an accessible
list of the 40 largest clusters provide alternatives to pointer selection.

The interface provides date and satellite filters, a marker visibility switch,
rotation control, zoom controls, and per-source links into the authentic atlas.
Filtering clears the previous selection and markers while loading. A failed
request exposes a retry control. The evidence list remains usable without WebGL.
The renderer stops drawing while its frame is outside the viewport and honors
the existing preference for reduced motion.

`GET /api/globe?source=all&date=all` supplies the snapshot.
`GET /api/globe/detail?cell=292:87&source=all&date=all` supplies matching evidence.
Dates may be one UTC day in the current snapshot. Sources may be `all` or one
supported NASA NRT source ID. Both endpoints reject synthetic mode. A bounded
five-minute cache is invalidated by changes to the database or WAL file.

## Verification — 27 September 2026

- 56 automated tests passed, including five new globe tests for totals, source
  and date filters, synthetic exclusion, snapshot boundaries, coordinate edges,
  missing FRP values, matching detail queries, cache invalidation and projection.
- Wheel and source build passed. JavaScript syntax checks passed.
- Desktop 1440 px, tablet 820 px and mobile 390 px rendered the real model and
  markers without JavaScript page errors or horizontal overflow.
- Real pointer click selected the expected 9,353-record cell. A drag did not
  select a cell; zoom and marker visibility changed the rendered globe.
- NOAA-21 filtering reproduced 399,653 detections. Selecting September 27
  reproduced 9,610 observations; every returned cluster belonged to that date.
- Atlas handoff retained authentic mode, satellite, year, month and area.
- Simulated snapshot failure and retry passed. Browsing evidence also passed
  with the Earth frame blocked.
- The existing authentic database remained unchanged; this feature reads it.

The 1° cells are a visual grouping chosen for the global view. Use the linked
atlas and original source records for closer inspection. Regional fire status,
fire boundaries, ignition attribution and operational response information
require additional data and are not derived by this feature.

## Landing-page polish and detection reveal — 27 September 2026

The globe starts with detections off. Observation data is fetched during idle
time after the Earth becomes ready (or on an explicit detection request).
Turning on detections shows the overlay immediately if its data is already
loaded, without a forced turn or change to the current rotation setting. When
data is still needed, the globe performs an eased full turn, then restores the
captured orientation and pauses before revealing the overlay. If data remains pending,
“Loading data…” stays visible at that original pose. Unchecking cancels the turn
and restores the pose without showing detections. Reduced-motion mode skips the
turn. Failed data requests leave detections off and expose Retry.

The compact right panel switches between the overview and selected group;
source records, atlas links and interpretation expand on demand. Legend buttons
and daily-count bars show explanatory tooltips on hover, keyboard focus or tap.
The daily chart retains the full date window for the selected satellite even
when the globe displays one date. Missing records are labelled coverage unknown.

Verification: 56 automated tests passed. Browser checks covered default-hidden
markers, background loading, exact rotation-matrix equality after a full turn,
cancellation, delayed data, reduced motion, request errors, tooltips and group
inspection. Desktop 1440×900, laptop 1366×768 and mobile-width 390×844 were checked;
no horizontal overflow or JavaScript exceptions were observed. The application
uses the existing Earth textures and shaders; the renderer bridge now exposes a
bounded turn and cancellation to support this interaction.

Repeat the delayed-data and pose checks against a populated server:

```bash
uv run --with playwright python scripts/verify_globe_reveal.py
```

## Worldwide 2D and 3D browsing — 29 September 2026

The former EONET-only map now defaults to `/api/globe?source=all&date=all`,
using the same authentic global FIRMS snapshot as Earth: 866,956 imported
observations in 7,307 one-degree groups, dated September 20–27, 2026. The
existing data already included worldwide locations; no synthetic observations
or new claims of live activity were added. The previous 200-event EONET sample
contained only IRWIN reports and was unsuitable as a global coverage map.

The landing 2D map now exposes the imported NASA satellite snapshot and a
separate NASA EONET reported-event sample. EONET remains a curated feed and is
not part of the MODIS–VIIRS calendar. Regional navigation and worldwide reset
cover Africa, Asia, Europe, North America, South America and Oceania; these are
broad rectangular windows rather than administrative boundaries. Satellite
groups retain their detection count and last-observed date in the map list.

The 3D Earth panel is now limited to satellite evidence. The historical
casebook endpoint, fire textures, picker, and death-count summaries have been
removed. The FIRMS snapshot remains an imported historical snapshot; it is not
labelled as a live observation stream. The map loads as it approaches the
viewport, preserving lazy loading on the landing page.

The R1 cleanup is implemented in code. Automated and served-page checks are
pending; earlier browser-verification statements above describe the prior
casebook version and have been removed with that feature.
