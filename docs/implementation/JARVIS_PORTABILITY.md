# JARVIS orchestration and editable whiteboard portability

Implementation record: 5 October 2026, Asia/Dhaka. This extends the existing Research Studio, assistant, workflows and private stores. Existing uncommitted work and the Park/Camp/Grove presentation collection were retained. The protected landing scripts, assets, outside-header HTML and frozen globe release were not changed.

## Presenting the complete operation

1. Restart the local Python service after installing this build. Open **Investigate → Park**, select a UTC date and the MODIS or VIIRS pane. Playback pauses during capture.
2. Select **Prepare native and editable exports**, then **Send to Canvas**. Leave the destination as a new investigation, or use **Choose canvas** to append to a specific accessible board. The selected frame is frozen; it does not start following another board's timeline.
3. The command captures the actual display, reuses matching owned receipts, prepares compatible checked charts, creates a registered workflow, saves arranged objects and prepares both downloads. It opens the saved Canvas in the same tab. A failed browser acknowledgment leaves **Saved; open board to continue**, rather than claiming the board was opened.
4. Inspect a frozen map, its numerical data, checked findings and the recorded operation trace. Select the saved workflow to inspect node inputs and outputs. **Run captured workflow** creates a new run and new output cards; it does not rewrite the captured investigation.
5. Select a card and use **Arrange selected card**. **Undo this JARVIS change** reverses that command while preserving unrelated later work. A later edit to an affected object produces a conflict instead of being overwritten.
6. Download the prepared native archive or choose another output under **Export or restore the editable whiteboard**. Restore the archive into a new board. Open its companion in [the Excalidraw continuation editor](../../fireatlas/static/studio-excalidraw.html), move a map, edit captions or node text, reconnect an arrow, annotate, save and reopen.
7. **Return to captured source** restores the originating selection. The existing Studio presentation presets remain another convenient starting point; their authentic evidence, saved stories, paired heat images and workflows are unchanged.

The deterministic capture, persistence and export path works without inference. For a conversational request, use **Attach this view to JARVIS**, choose the source pane if necessary, and ask JARVIS to package it with `export_formats` of `native` and `excalidraw`. This explicit attachment binds the tool to the submitted instance/frame. The existing provider, cancellation and accounting mechanisms remain authoritative. Conversational tool routing was tested with mocks; no paid or live provider verification was performed.

## Supported entry points

| Entry | Captured scope and behavior |
| --- | --- |
| Explore / Atlas | Regional calendar, exact bounds/month/day and displayed result hash. Captures a bounded text evidence guide from the actual calendar and saves its full checked result separately. The guide is labeled as truncated text, rather than a map screenshot. |
| Investigate | Actual selected sensor pane/frame, daily or cumulative state, visible sources, kernel, weighting, normalization/domain, palette/opacity and available layers. Existing optional terrain capture remains renderer-dependent. |
| Research / Evidence | The registered active calculation, chart/table or validity section. Missing compatible results, coverage masks or unsupported selections produce an explicit error/omission. A source-only section is not silently converted into a Park investigation. |
| Canvas | Selected object and its effective pinned study, frozen receipt, board/object revision and intended destination. |
| Story | Saved story/chapter identity and revision, cited evidence and scene selection. Historical imported scenes are retained for inspection and re-export; an edited story resolves a new revision. |
| Workflow | Selected saved definition/node, normalized inputs, recorded outputs and rerun availability. Unsaved editor drafts are not advertised as executed workflows. |
| Assistant | Attached analytical source or owned selected Studio object, using the same runner and private session. |
| Private MCP | `studio_register_context`, `studio_command`, status/action tools and revision-bound export/status/chunk tools. Context is private to the MCP process and does not rely on website cookies. External MCP UI host acceptance remains unverified. |
| Protected landing | Existing limited legacy context and navigation, with server-side normalization. No analytical packaging module was added to the landing page. |

Applied scientific context remains under `FireAtlasContext`. The additive `fireatlas-jarvis-context-v1` envelope stores instance/tab/pane, exact study/geometry, selected objects, receipts, actual display settings, source revisions, destination and public return selection. Tab identifiers identify context; ownership, room roles and spending allowances remain independent. Conflicting sensor panes require a focused choice. A source change while a preview is being captured requires recapture.

## Shared recipes and persistence

The deterministic `Commands` runner implements five recipes: `visualization_to_investigation`, `selection_to_chart_set`, `findings_to_workflow`, `board_to_portable_exports` and `continue_investigation`. Website controls, the conversational tool and private MCP wrappers call these implementations. They use the existing scientific operation registry, receipts, workflow DAG runner, assets and document transactions.

Studio schema migrations 5/6 add owned contexts, commands, checkpoints, investigation packages, export jobs, remote mappings and imported historical annotations/projects. Schema 6 remains separate from the scientific database and assistant notebook. Stable identities derive from command/step/artifact role. Board insertion and its checkpoint commit atomically. Safe appends retain current collaboration/lock rules; updates and undo check affected object revisions.

Commands report the actual phase through accepted, capturing, preparing results, building workflow, applying board, saved, awaiting view acknowledgment and completed. Optional archive preparation reports its separate preparation phase. Partial, failed and cancelled records retain recovery information. Restart marks unfinished deterministic work for explicit resume. Saved outputs/checkpoints are reused; an uncertain paid request is not automatically repeated. Cancelled commands cannot deliver late mutations or acknowledge navigation.

Acknowledgment validates the owned registered destination instance, actual board revision and affected object set after the destination DOM has mounted. A pending navigation request does not close the acknowledgment gate. Repeated command submissions reuse the saved command; repeated revision-bound export keys return the same saved export even after later board edits. Reusing an export key for another format/scope/revision is rejected.

| Interface | Behavior |
| --- | --- |
| `POST /api/studio/contexts` | Register/update the owned submitting instance. |
| `POST /api/studio/assistant-contexts` | Explicitly attach captured context/preview using both owned Studio and assistant identities. |
| `GET /api/studio/contexts/{instance}/commands` | Owned instance command lookup for durable delivery. |
| `POST /api/studio/commands` | Submit a typed recipe and idempotency key. |
| `GET /api/studio/commands/{id}` | Durable phase, status, outputs and omissions. |
| `POST /api/studio/commands/{id}/{cancel,resume,ack,undo}` | Command-specific recovery/acknowledgment/undo. |
| `GET /api/studio/packages/{id}` | Frozen source, view, receipts, cards, workflow and actual trace. |
| `POST /api/studio/documents/{id}/exports` | Prepare a saved-revision whole-board, frame or selection export. |
| `GET /api/studio/exports/{id}` and `/download` | Preparation status and owned disk-backed completed archive. |
| `POST /api/studio/imports` | Bounded streaming native archive upload and restoration. |
| `POST /api/studio/documents/{id}/miro-transfers` | Explicit transfer to an operator-allowed destination. |

Mutations retain origin validation and ownership/room-role checks. The ordinary 3 MB JSON request limit is unchanged; native upload uses its own bounded streaming route. Completed exports are retained. Failed temporary preparations are cleaned up.

## Scientific contracts

Scientific calculations, filters, version matching, replay alias removal, limits, release identities, UTC binning and missingness remain unchanged. Charts are selected deterministically from compatible receipts, with at most four compatible chart cards. Unsupported daily series are omitted with a reason. Availability has its own source-state contract and is not represented as fire activity or a cloud/pass denominator.

The captured harmonized result hash must still match the displayed calendar. Its finding card now explicitly references the selected month's total, observed/estimated/unknown dates, available median/difference, qualifying years and recorded comparison wording. It does not fill a null percentile or select another month. This is a checked presentation change, not a numerical change.

| Preservation target | Recorded result |
| --- | --- |
| Northern California, June 2026 | 113 harmonized cell-days; 30 observed dates; median 109; difference +4; unavailable percentile. |
| Northern California, July 2024 | Approximately 3450.715794898222; 25 observed/six estimated dates. |
| Punjab–Haryana, July 2024 | Approximately 221.195876288660; 25 observed/six estimated dates. |
| Northern California, July 2025 | 415; two qualifying prior years; unavailable median/anomaly/percentile. |
| Park replay | 6,224 eligible unique detections; 2,228 joint cell-days. |
| Camp replay | 5,644 eligible detections; 1,375 joint cell-days; partial exports. |
| Grove replay | Seven detections; four joint cell-days. |

The original [scientific baseline](scientific-baseline.json), current preset report and static calendar checks retain the relevant evidence. Regional harmonized activity, combined occupied-cell detections, replay records, research rows, source FRP and candidate groups remain distinct. A stored display sample keeps its matching-count/truncation metadata. No observation opportunity, incident membership, ignition, perimeter or spread claim is inferred.

Workflow exports distinguish **Runnable workflow**, **Recorded execution**, and **Explanatory dependency**. Frozen input references are explanatory unless an intermediate call actually occurred. Registered `board_insert` and `portable_export` nodes perform real effects and checkpoint their outputs. Applying a workflow to another explicit supported study creates another definition/run/result scope; it does not relabel an old receipt.

## Local portability

The authoritative document remains the Studio store. A `fireatlas-board-export-v1` representation freezes one saved board revision, with layout/stacking, groups/frames, styles/text, view descriptors, assets, connectors, saved workflows/stories and permitted metadata. Whole-board output includes offscreen objects. A frame or selection export closes its selected card/evidence references and explicitly omits whole-board stories, workflows and investigation histories.

| Format | Editability and restoration |
| --- | --- |
| `.fireatlas.zip`, `fireatlas-board-v1` | Restores a new owned board with fresh remapped object/result/workflow/chapter/connector IDs, exact frozen receipt content, bounded display inputs, assets, saved definitions, recorded history and attributed board discussion. Includes the Excalidraw companion, object map, conversion report and checksummed inventory. |
| `.excalidraw` | Individual editable text, findings, workflow node shapes, frames and bound arrows. Maps/complex charts are separate embedded visual objects with editable captions. Scientific recomputation remains in FireAtlas. |
| SVG | Prepared vector output where available, with embedded map/chart figures. |
| PNG | Frozen prepared output within explicit bitmap dimensions/area; excessive whole-board output requests a frame/selection. |
| PDF | Overview, readable groups/workflows, spatial tiles for large unframed content and readable object pages, within the page limit. |

Native limits: 512 MiB compressed, 1 GiB expanded, 4,096 entries and 32 MiB per JSON entry/chunk. Existing 100-card/300-connector/40-asset limits remain; each imported raster asset is bounded by the existing 1.5 MB limit. PNG output is limited to 16,000 pixels per edge and 64 million pixels; PDF to 128 pages. Export preparation is serialized within the process. JSON scientific payloads exceeding a permitted entry size use indexed chunks. Actual sizes/hashes are accumulated during writing and streaming verification. Restoration retains bounded decoded contents in memory; it is not an unbounded-memory importer.

Restoration checks schemas, hashes/actual expansion, duplicate/traversal/symlink paths, allowed entries, MIME/magic, asset metadata, graphs, identities/references and frozen scientific facts. Rehashed semantic and asset tampering tests reject forged content. It neither fetches external assets nor imports executable content. Archives exclude tokens, room membership/invitations/presence, unrelated conversations/notebooks, private endpoints and the scientific SQLite database. Imported evidence is labeled **imported frozen provenance**, rather than a newly authenticated measurement.

The SDK is pinned to `@excalidraw/excalidraw` **0.18.1**. Creation, restoration and serialization use its actual exported helpers; the installed declaration is `serializeAsJSON(elements, appState, files, type)`. Files embed images in the supported `files` map. The independent editor opens/saves the scene and checks bindings. [Excalidraw's scene schema](https://docs.excalidraw.com/docs/codebase/json-schema/) documents the elements/appState/files representation. General import of external diagram edits back into scientific results remains outside this implementation.

## Installation and operation

The checked-in frontend build is refreshed through supported tooling. Native/Excalidraw backend preparation additionally needs the local pinned Node dependencies, including JSDOM and native text metrics:

```bash
npm --prefix studio-app ci
npm --prefix studio-app run build
uv run python scripts/refresh_static_assets.py --site site
bash scripts/run_website.sh
```

PNG/PDF require an installed local Chromium executable. Missing runtimes produce capability errors. Excalidraw's optional editor and font assets load separately; the ordinary Studio entry does not eagerly fetch the full editor. Static serving supports existing frozen evidence/readers and the editable companion. Custom capture calculations, private board persistence/native restoration and command execution require the local service; static controls do not simulate successful persistence. Source/static Studio inventories are compared against generated hashes, and refresh enforces the landing guard.

## Miro adapter and external dependencies

Only **Send to Miro** performs a transfer. Configure server-side `FIREATLAS_MIRO_ACCESS_TOKEN` and comma-separated `FIREATLAS_MIRO_BOARD_IDS`. Public-origin deployments also require approved owned principal IDs in `FIREATLAS_MIRO_PUBLISHER_IDS`. Tokens never appear in capability responses or exported archives. The operator must configure/maintain authorization; this implementation adds no multi-user OAuth flow.

Frames/items are created before connectors, images upload embedded bytes, and returned identities/content fingerprints are persisted. First transfer, repeat-as-new and update-existing are distinct. Participant edits are preserved. Changing mapped image content requires an explicit new transfer, rather than overwriting a changed image. Uncertain creation is reconciled using a bounded remote search; zero/multiple matches or an incomplete search stop with ambiguity. Network-uncertain writes are not automatically repeated. Rate-limit retries are bounded.

[Miro's service-account setup](https://developers.miro.com/docs/rest-api-build-your-first-hello-world-app), [image upload endpoint/6 MB limit](https://developers.miro.com/reference/create-image-item-using-local-file), and [read/write scopes](https://developers.miro.com/reference/scopes) were checked against primary documentation. Mock tests cover request construction, endpoints/bound connector identities, rate limits, size limits, uncertain outcomes and changed remote objects. **No live Miro transfer or credential/scope verification was performed.** A supplied token and explicitly selected authorized test destination remain necessary for that acceptance gate.

External MCP UI hosts, licensed tldraw/hosted collaboration and configured live inference remain separate existing integration gates. Local built-in Canvas and the actual Excalidraw continuation editor were exercised. Independent native-mask human review, validated observation exposure and source authentication remain pending scientific gates.

## Acceptance evidence

Executed validation: **329 Python tests** in 460.781 seconds; **51 frontend tests across 13 files**; TypeScript/Vite build; **177 JavaScript syntax checks**; all **382 source/static indexed assets**; existing heat/visual/terrain checks; static calendar/source/Park/Grove checks; and **11 real browser acceptance checks**, with zero page errors. The runtime dependency audit reported zero known vulnerabilities. Logs are retained rather than treating warnings from deliberate malformed-ZIP fixtures as failed assertions.

| Final cold static entry | Requests | Decoded response bytes |
| --- | ---: | ---: |
| Explore | 29 | 3,182,152 |
| Investigate | 29 | 1,698,340 |
| Evidence | 26 | 1,103,582 |

The machine-readable [verification summary](jarvis-checks/verification-summary.json) records exact final counts, commands and reports. [Browser report](jarvis-checks/browser-report.json), [interruption trace](jarvis-checks/interruption-trace.json), [restoration comparison](jarvis-checks/restoration-comparison.json), [preset report](jarvis-checks/presets/report.json) and [static loading report](jarvis-checks/static-loading-report.json) retain actual execution evidence.

Browser acceptance covers authentic Park capture and same-tab acknowledgment, lost acknowledgment/refresh without duplicate insertion, actual workflow rerun/effects, command-specific undo preserving a later note, all five output formats, empty-science-backend restoration with original receipt hashes, actual Excalidraw move/text/arrow edit and save/reopen, pointer zoom/pan/card drag and 360/390/768 layouts. Atlas acceptance additionally checks exact region bounds, displayed result identity and selected-month harmonized value. Existing presentation checks retain all three presets and their shared heat domains. Provider failure/stale action/ownership scenarios use mocked transports or isolated fixtures, not paid providers.

Cold entries were measured in fresh browser contexts under `/project/`, with external imagery blocked, after the requested summary became ready plus 1.5 seconds. The report counts decoded response bodies, including capability/error responses. It does not claim a before/after loading improvement. Summary rendering downloaded no full regional row archive or result ZIP. The handoff report separately measures the entire acceptance scenario and uses response Content-Length headers; it is not a cold-load measurement.

Screenshots, sample native/edited scenes, SVG/PNG/PDF, logs and canonical restoration comparison are in [jarvis-checks/](jarvis-checks/). Protected landing checks still match all 75 assets and both HTML boundaries. No public deployment, messages, repository push, live Miro publication or paid provider calls were part of this implementation.
