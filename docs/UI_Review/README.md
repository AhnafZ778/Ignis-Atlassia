# Implemented website redesign and visual review

The production UI is in `fireatlas/static/`, with the published copy in `site/`. These screenshots show the actual website with supplied records, rather than the earlier synthetic UI handoff. They were reviewed at desktop, tablet, and mobile sizes, and the discrepancies found during review were corrected.

Open the [screenshot gallery](index.html). Full-page captures are included for analytical workspaces. The landing captures show the preserved Earth hero. The review record will include the final browser results alongside the screenshots.

## What changed

| Page | Implemented design and workflow |
| --- | --- |
| Overview | Existing globe and orbit controls retained; light navigation, compact explanation, archive readouts, and clear destinations below the hero. |
| Atlas | Compact applied study, separate selected-study and regional-history scopes, NDVI context, readable calendar intensity, dated evidence, and daily replay. The static explorer follows the same hierarchy. |
| Fire replay | Case/source/metric setup, dominant terrain map, continuous magnitude ramp, coordinated UTC timeline and source records. Display settings collapse on mobile. |
| Research | Three useful headline values, immediate sensor chart, keyboard-accessible date inspection, exact table, and expandable study settings. |
| Candidates | Neutral candidate map with selection outlines, stable candidate numbering after sorting, readable list and exact evidence. |
| Exposure | Coverage workflow and mask state kept beside the denominator; unsupported percentages remain withheld. |
| Validation | Named-case evidence distinguished from study settings; status gates and evidence artifacts show their scope. |
| Data | Searchable source catalog, region filter, archive completeness, and clear empty/loading states. |
| Method | Readable calculation flow, real worked example and recount, optional model/validation details. |
| Review | Usable sample queue, locally saved drafts, blank independent measurements, and explicit attestation requirements. |
| Assistant | Map-first investigation workspace, distinct sensor filters, timeline, annotations, evidence tabs, expanded conversation and evidence diagrams; mobile Map/Conversation/Evidence navigation. |
| Terrain Earth | Preserved 3D scene with readable standalone controls and a compact interpretation guide. |

## Shared scientific language

Warm ivory canvas, white work surfaces, deep ink, and cobalt actions. MODIS uses amber/circle, VIIRS cyan/diamond, and shared cells green/square. Partial data have patterned status; unavailable data have explicit labels. Heat uses one continuous magnitude ramp. Replay uses a frame-relative scale; the assistant uses a fixed study scale. Neither represents a perimeter, temperature field, or forecast.

## Fixes found through screenshots and interactions

- The assistant’s mobile map tools created an oversized grid row and squeezed the map. Explicit map/tool rows now preserve the viewport.
- The static Atlas legend clipped on desktop. A single-column sidebar fixes its text flow; mobile legends sit above the map.
- Repeated setup copy pushed static maps downward. Study/display settings now collapse, and context/completeness detail sits below the map.
- Replay’s previous/next controls were unbound, and play remained disabled after loading. Both now track the selected frame.
- Method foreground colors were inherited from pale surface tokens. Explicit ink colors restore the worked values and diagram labels.
- Sensor colors in generated charts and map symbols differed between pages. The shared palette now applies to those generated elements.
- Candidate labels changed after sorting. Labels now retain original identity and selection.
- Unknown/partial calendar states and unavailable API results needed clearer presentation. They remain distinct from zero observations.

## Practical limits

A visual review and the recorded workflows do not establish every possible browser or network condition. Streamed imagery/elevation requires a connection and may be unavailable. Static research calculations require the local analysis service and show this requirement explicitly. AI responses were not purchased during verification; the assistant’s stored-data workflows and provider-unavailable UI were exercised. Scientific coverage and independent-validation gaps are retained as gaps.

`site/` retains its existing **2026-10-01** observation snapshot. UI asset refresh does not relabel or regenerate those observations.
