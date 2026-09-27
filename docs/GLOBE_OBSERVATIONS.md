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

## Documented wildfire layer — 27 September 2026

The “Documented wildfires” toggle loads six curated historical cases from
`/documented-fires.json`: Jasper, Valparaíso, Evros, Lahaina, Mallacoota and the
Camp Fire. Blue diamond markers and a case picker open a dated summary with
direct news reports in new tabs. Camp Fire also links to NASA imagery.

This layer works independently of the thermal-detection toggle and NASA API
availability. These are selected historical examples, not a current incident
feed. Coordinates represent approximate affected communities, not ignition
points or fire boundaries. Cases are not inferred from or matched to the
current satellite snapshot; satellite date and source filters do not filter
the historical collection. Source publication dates appear beside each link.

Verification: all 56 existing automated tests passed. Browser checks covered
the six-case picker, globe marker selection, external report tabs, independent
layer visibility and mobile layout at 390×844. No JavaScript exceptions or
horizontal overflow were observed. Desktop was checked at 1366×768.

### Casebook navigation polish

The documented wildfire toggle now sits at the top of the information panel.
Numbered cards separate the event, location and date; a desktop scroll hint
exposes the rest of the collection. Report details have a prominent sticky
“Back to all wildfires” button and Previous/Next controls with a case counter.
Returning restores focus to the selected card. Larger blue globe markers have
a wider hit area. The satellite detail view also has an explicit back button.

Browser checks passed for marker selection, source links, Previous/Next limits,
back navigation, focus restoration and showing/hiding the layer. Layout checks
at 1366, 1024, 820 and 390 px found no horizontal overflow or JavaScript errors.

## Worldwide 2D and 3D browsing — 28 September 2026

The former EONET-only map now defaults to `/api/globe?source=all&date=all`,
using the same authentic global FIRMS snapshot as Earth: 866,956 imported
observations in 7,307 one-degree groups, dated September 20–27, 2026. The
existing data already included worldwide locations; no synthetic observations
or new claims of live activity were added. The previous 200-event EONET sample
contained only IRWIN reports and was unsuitable as a global coverage map.

The 2D layer selector separates satellite groups, six documented historical
cases, and the existing EONET report sample. Every layer exposes its provenance
and date limitations. Regional navigation and worldwide reset cover Africa,
Asia, Europe, North America, South America and Oceania. These regional views
use broad rectangular geographic windows, not administrative boundaries.
All groups are drawn; the list pages through 30 at a time. At global zoom,
marker sizes shrink to preserve geographic readability. Orange/gold satellite
colors follow the globe's earlier/latest observation-day convention.

Satellite and historical popups link to the matching 3D selection. A satellite
handoff restores the full snapshot's date and source selection so its evidence
matches the 2D point. The globe now has World/Europe controls and a location
picker scoped to the chosen regional window. The 2D map loads as it approaches
the viewport, retaining lazy loading on the landing page.

Browser verification passed: exact global totals/group counts; nonempty data
in all six regional windows; satellite and historical handoff to 3D; historical
source links; EONET sample labelling; pagination; worldwide reset; and layouts
at 1440, 1024, 820 and 390 px without horizontal overflow or JavaScript errors.
