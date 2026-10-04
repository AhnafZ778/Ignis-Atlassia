# Website theme and assistant location update

Implemented in the actual website sources and refreshed in `site/`. The UI handoff pages were not edited. The exported observation snapshot remains **2026-10-01**.

## Changes

- Restored the complete dark overview shell: navigation, Earth hero, lower overview, destination cards, evidence dialog and assistant overlays. Removed the white pseudo-element behind the lower overview.
- Kept scientific workspaces light, with shared ink, surface, divider, control and action tokens. Primary actions are solid cobalt, selected controls have a visible underline or outline, and status labels distinguish complete, partial and unavailable data.
- Preserved sensor meanings: MODIS amber circles, VIIRS cyan diamonds and shared cells green squares. Heat ramps and numerical normalization retain their existing values. Calendar text chooses black or white for contrast against its heat value.
- Highlighted the fire-study/archive chooser. It opens on a first visit, remembers subsequent open/closed choices, and keeps the map accessible when collapsed. Saved cards and historical results have separate open and location-toggle buttons.
- Added areas, date ranges, counts and a selected indicator to saved fire cards. Incident reference coordinates are explicitly distinguished from study boundaries. Historical results show the geographic area and returned observation boundary; their display uses each result's bounds rather than the current edited study.
- Added signed decimal coordinates and Copy beside the assistant location search. Exact observations use five decimals; cell centers and geographic bounds use four. Changing dates, sensors or studies clears stale sample coordinates. Selecting a sample does not overwrite the place query.
- Added a selectable-text copy fallback, keyboard-operable location toggles, polite selection/copy feedback and contrasting map-selection outlines. Annotation locations are labeled separately from satellite observations.
- Updated expanded assistant diagrams and schematic captures to use the host page's palette. Standalone terrain controls share the light interface tokens; the Earth scene retains its original background and renderer.

## Verification

- **36 responsive captures**: 12 pages at 1440, 1024 and 390 px. All routes loaded with no document-wide horizontal overflow or JavaScript page errors. See `results.json`.
- Checked first-visit archive visibility, remembered collapse after reload, keyboard coordinate toggle, exact observation coordinates, clipboard copy, selectable-text fallback, unchanged study context on toggles, stale-selection clearing and historical boundary labels.
- Checked all 12 flat routes in the static export, including the bundled assistant replay and honest local-service notices on research pages.
- Six static-export unit tests passed. Existing observation-map and evidence-visualization checks passed, including source separation, shared-cell union, chronology, fixed scales, missing values and evidence paths.
- A targeted computed-color audit found no low-contrast plain-background text in the checked headings, labels, controls and supporting text after remediation. This is a targeted check, not a full WCAG conformance certification; geographic imagery and gradient backgrounds require visual inspection.
- Connected Earth verification passed: zoom-in moved the camera closer, zoom-out moved it farther away, reset and rotation controls responded, the historical browser contained 16 options, satellite signals could be enabled, and the evidence dialog retained a dark background. The original renderer remains `arcgis-terrain`.
- Clipboard fallback and coordinate toggles were also exercised through their actual browser controls, including an Enter-key activation.
- The page gallery deliberately blocks the external terrain SDK to check its fallback layout. The separate live-globe capture uses the connected renderer. External imagery remains a network-dependent resource.

## Review files

Open `index.html` in this folder for desktop, tablet and phone screenshots. The selected-observation screenshots show the coordinate strip with real returned records; no synthetic observations were inserted into the project archive.
