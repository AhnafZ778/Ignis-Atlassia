# Reliable JARVIS prompts and curated Canvas presentations

Implemented 5 October 2026. These additions extend the existing command runner, receipts, board storage, Story and Workflow. The protected landing remains unchanged.

## Use the shortcuts

Open Investigate, apply a study and choose a UTC frame. Use **Reliable JARVIS prompts**, or open **JARVIS · this investigation** in the Studio inspector. Presentation shortcuts fill the editable question in Studio; submit **Ask JARVIS**. On analytical pages, clicking the shortcut submits it directly.

Copyable prompts:

- `Create a curated Park Fire 2024 presentation on Canvas with paired heat maps, charts, evidence, an editable story and a runnable workflow.`
- `Create a curated Camp Fire 2018 presentation on Canvas with paired heat maps, charts, evidence, an editable story and a runnable workflow.`
- `Create a curated Grove Fire 2025 presentation on Canvas with paired heat maps, charts, evidence, an editable story and a runnable workflow.`
- `Create a comprehensive presentation on Canvas from this study, with paired sensor heat maps, daily charts, an availability timeline, checked findings, original records, connected groups, an editable story and a runnable workflow.`
- `Add the supported daily activity charts and availability timeline from this study to Canvas.`
- `Check the source export states and processing gaps for this study.`
- `Inspect the original satellite records for this study.`

Clear imperative requests such as `Send this data to the canvas` also use the curated presentation recipe. The named presets explicitly change to the named authentic study. The current-study prompt preserves the submitted selection. Questions, negations, export requests and ambiguous multi-study requests retain the existing conversational tool path.

## Destination and representation

Before a supported Canvas recipe inserts anything, JARVIS asks **Which Canvas should receive this investigation?** Choose a new investigation or an existing editable board, then confirm. Cancel leaves the board unchanged. Viewer-only and other owners’ boards are unavailable as destinations.

Replay presentations include the captured visualization, separate MODIS and S-NPP heat maps, joint and source-specific daily charts, collected-export availability, checked findings, original records, an evidence question and a chapter frame. Four named groups and context links arrange the eleven objects. A six-chapter editable Story and runnable registered Workflow are saved with the package. Context links explain evidence relationships; they do not claim an unrecorded execution.

Frozen lightweight visual previews prepare automatically; live map interaction remains optional. Paired supplementary heat maps use a fixed study scale. The primary captured frame retains its renderer descriptor and available image. The selected UTC date wins; a named presentation without a selected date opens its highest joint-cell activity frame. Other calculation contracts receive compatible views rather than invented replay heat maps.

Append inserts below existing content, keeps existing notes and the board study, and pins the new cards to the captured source study. Successful persistence opens the actual destination in the same tab. Existing command acknowledgment, cancellation, resume, return-to-source, export and affected-object undo remain available. Retrying the same request key reuses its command and cards.

## Availability

The catalog and shortcuts call the same owned backend recipe through `/api/studio/prompt-presets` and `/api/studio/prompt-commands`. They require the local scientific/private service and suitable authentic inputs, but no model key. Custom questions continue to use configured inference and existing tool validation. This change does not establish that every provider key or external API is functional.

Static pages retain frozen evidence and existing preview/download capabilities. They explicitly report that new Canvas persistence needs the local service. Scientific limits, calibration contracts, eligibility, deduplication, privacy, ownership and accounting are unchanged. Independent native review and complete exposure validation remain pending.

## Verification

- 69 focused Python tests passed across prompt composition, assistant integration, HTTP boundaries, portability and workflow/collaboration. The final automatic-preview change also passed all six prompt tests.
- 60 frontend tests passed across 14 files; TypeScript checking and the production build passed.
- Named-study URL checks cover real cross-month scopes, explicit overrides, invalid days and round trips.
- Real Chromium acceptance verifies destination choice before mutation, Grove append preserving an existing note, eleven cards/four groups/six resolved chapters, valid registered Workflow, actual destination acknowledgment, and Park capture of 30 July 2024. Heat-map previews render for both source panes with a shared scale; pointer-anchored zoom and keyboard card movement remain functional after packaging.
- Authentic results remain Grove: seven eligible records/four joint cell-days; Park: 6,224 eligible records/2,228 joint cell-days.
- Browser acceptance recorded zero page errors and zero inference requests. Loading a study may call the deterministic assistant `replay` operation; this is distinct from a model request.
- The supported asset refresh was used. Landing protection and source/static asset verification are recorded alongside the browser report.

Artifacts: [verification summary](jarvis-preset-checks/verification-summary.json), [browser report](jarvis-preset-checks/browser-report.json), [Canvas choice](jarvis-preset-checks/canvas-choice.png), [Grove presentation](jarvis-preset-checks/grove-composed-canvas.png), [Park presentation](jarvis-preset-checks/park-composed-canvas.png).

Repeat the focused checks:

```bash
.venv-assistant/bin/python -m unittest tests.test_studio_prompts tests.test_studio_assistant tests.test_studio_portability tests.test_studio_http tests.test_studio_workflow_rooms
(cd studio-app && npm test && npm run build)
node tests/test_workspace_named_context.cjs
.venv-assistant/bin/python scripts/verify_jarvis_presets.py --base http://127.0.0.1:8000
uv run python scripts/refresh_static_assets.py --site site
uv run python scripts/check_landing_preservation.py
uv run python scripts/check_jarvis_release.py
```
