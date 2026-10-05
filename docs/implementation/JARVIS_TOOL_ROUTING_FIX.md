# JARVIS tool selection and Canvas handoff fix

Recorded 5 October 2026. This change addresses conversational requests failing with “The AI could not verify its answer” despite usable scientific results or saved Canvas operations.

JARVIS receives descriptions and typed arguments for its registered scientific, source-selection, geographic, annotation and Studio tools. The model selects the tools according to the request. Final answers require actual evidence, a validated action, a saved operation or a focused clarification. Numerical claims still resolve through owned receipts and exact JSON pointers.

The old failure path discarded valid tool results when the model's final references or wording failed validation. The new path returns the checked calculation with an explicit wording-unavailable flag. Saved Canvas commands and typed drafts are returned as operation outputs, independently of scientific scalar claims. A command being saved is distinct from its board being opened and acknowledged.

Conversational Canvas requests on analytical pages capture the current applied study/frame automatically before submitting. Explicit sensor names select the corresponding pane; otherwise the current joint view is retained. Manual attachment still permits a pane choice. Capture checks the source revision; late results cannot repaint a newer selection. The existing Studio runner performs persistence, recovery and browser acknowledgment. The protected landing assistant script remains unchanged.

If no usable output exists, JARVIS gives a focused clarification. Conservative deterministic recovery applies only to the submitted study; explicit places, dates and selected geometries are not silently replaced by the old selection. Provider failures without completed output remain errors and do not trigger another uncertain paid request.

## Executed checks

| Check | Result |
| --- | --- |
| Assistant, Studio assistant and Studio HTTP Python suites | 66 tests passed |
| Studio frontend suite | 53 tests across 13 files passed |
| TypeScript and production build | Passed |
| Analytical static refresh | Passed through supported tooling |
| Landing guard | 75 protected asset hashes and both outside-header HTML boundaries match |
| Release consistency and JavaScript syntax | 382 manifest files match; 177 JavaScript files checked |
| Browser with mocked inference and authentic read-only inputs | AI-selected tool, invalid-reference fallback, automatic capture, real board/workflow, acknowledgment and refresh without duplicates passed |
| Live configured AI& scientific request | Completed using checked MODIS/VIIRS readings; one inference call, no wording fallback |
| Live configured AI& Canvas request | Chose `run_studio_recipe`; saved seven cards and a workflow, preserved the source frame, opened and acknowledged the board; no browser errors |

The live scientific example retained 25 July 2024: 603 MODIS detections in 415 occupied cells; zero imported S-NPP detections, explicitly labeled as a documented product gap. These describe imported evidence, not fire absence or satellite observation opportunity.

Artifacts are in [jarvis-tool-routing](jarvis-tool-routing/): browser [report](jarvis-tool-routing/report.json), [checked-output screenshot](jarvis-tool-routing/checked-tool-fallback.png), [mocked Canvas screenshot](jarvis-tool-routing/automatic-canvas-handoff.png), [live scientific result](jarvis-tool-routing/live-provider-smoke.json), [live Canvas result](jarvis-tool-routing/live-canvas-smoke.json) and [live Canvas screenshot](jarvis-tool-routing/live-canvas-handoff.png). The browser check can be rerun with `.venv-assistant/bin/python scripts/verify_jarvis_tool_routing.py`; its inference transport is mocked and its private stores are temporary.

## Operating scope

Repository publication also checks large static archives: six storage tests pass, covering exact reconstruction, corruption, changed transport identities, traversal and safe cleanup. Both authentic Punjab–Haryana ZIPs were independently reconstructed from their parts and matched the frozen release hashes. CI and Pages perform this assembly before using the release; Pages removes only redundant transport copies from its ephemeral checkout after verifying the full archives. The published site remains approximately 905 MiB rather than carrying another 314 MiB of duplicate parts. No Git LFS service is required.

Refresh an already-open analytical page after restarting the local service. Try “Compare MODIS and VIIRS detections for the selected UTC day” or “Package this heatmap on my canvas with the relevant charts and a rerunnable workflow.” Studio command progress reports actual persistence, and board navigation is acknowledged after destination registration.

Static hosting cannot persist private boards or run custom calculations. Deterministic actions remain independent of inference where a scientific backend is available. Only the configured AI& route was exercised live here; these results do not certify every provider key, speech API, Miro destination or hosted collaboration service. Independent scientific review and exposure-validation gates remain pending. No deployment, external messages or repository push was performed.
