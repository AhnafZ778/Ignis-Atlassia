# 07 — Studio backend: durable documents, commands, workflows, rooms, exports

[Context entry point](../../CODEBASE_CONTEXT.md) · reviewed 2026-10-27

## Composition and ownership

StudioService in fireatlas/studio/service.py composes StudioStore, Science, Rooms, RenderManager, Commands, Portability, Miro and StoryGeneration. It may bridge to the existing AssistantService. Its Science instance writes receipts into Studio's durable science_results namespace, not the expiring assistant notebook.

Studio root defaults to the scientific DB's parent / studio; the durable database is studio.sqlite3. STORE_VERSION is 11. A newer-than-supported store fails closed; sequential migrations preserve old documents. Never reset the author's DB to make a schema change pass.

Studio identity is a pseudonymous principal with hashed session tokens and explicit recovery tokens. The HTTP cookie is fireatlas_studio, separate from assistant ownership. Role order is viewer < editor < owner. Rooms grant bounded access; instance IDs/context IDs are not credentials.

## Module map

| Module under fireatlas/studio/ | Responsibility |
| --- | --- |
| service.py / http.py / errors.py | Application service, HTTP dispatch, structured status/code errors |
| store.py | Migrations, owned durable records, revisioned atomic edits, idempotency, undo/redo |
| graph.py | Pure card/group/view/connection validation, compatible scopes, acyclic propagation |
| evidence.py | Snapshot construction, scalar/unit verification and scale contract |
| composition.py | Curated layouts/decorated frozen evidence |
| orchestration.py / prompts.py | Versioned captured contexts, registered JARVIS recipes and supported prompt shortcuts |
| workflow.py | Typed bounded DAG validation and execution |
| rooms.py | Role-checked rooms/invites/comments/presenter state and adapter authorization |
| portability.py / miro.py | Frozen board export/import; separately explicit configured remote transfer |
| assets.py / capabilities.py | Build manifest allowlist and truthful runtime capabilities |
| heat.py / visuals.py / context_layers.py | Frozen occupied-cell images, prepared scientific graphics and existing map context |
| story.py / narrative.py / story_generation.py | Immutable stories and grounded narration; see story guide |
| render.py / narration.py / local_voice.py / aiand_video.py / resources.py | Optional media lifecycle; see story guide |

## Durable state and transactions

Document state contains schema/title/study, card dictionary + order, connections, groups, saved viewport, and story/workflow references. Cards retain binding, immutable snapshot_id, display, provenance, transform, follow mode, and optional pinned study. Fourteen card types are declared in graph.CARD_TYPES.

Important limits: 100 cards, 300 connections, 1,000,000-byte document state, two live maps. Small arbitrary presentation JSON is still bounded. graph.py rejects invalid values, mismatched follow relationships and cycles. A context/scale/compare connection has a compatibility contract; propagation is one topological pass, not a repeated feedback loop.

Store writes use BEGIN IMMEDIATE with foreign keys and atomic rollback. apply_transaction checks role, base document revision, touched object revisions, idempotency and allowed operations before applying changes and recording the inverse. Explicit non-conflicting merges are distinct from blindly accepting stale state.

Undo appends the inverse as a new revision; it does not rewrite history. It checks touched objects so later conflicting edits survive. Redo has the corresponding constraints. Selection/display state is not a substitute for the document's saved scientific study.

Deletion is owner/revision checked and tombstones the authoring document while stopping related queued/running work. Scientific inputs remain independent. Deleting the last investigation must leave an empty Studio, rather than silently creating another document.

## Binding → receipt → snapshot → card

resolve_binding derives effective board/card study plus allowed binding overrides, invokes Science.call, builds a snapshot and saves it under the owning document. Attaching the snapshot is a document transaction.

A snapshot includes result and receipt hashes, release identity, method/unit/grid, facts with observed/unknown/unavailable state, context/scope, dependency hashes and limitations. Up to 40 facts resolve per binding. verify_snapshot checks hashes and re-resolves values/states/units from the stored receipt; merely editing hashes does not legitimize a changed value.

scope is scientific; display is presentation. A day/cell/interval selection can inspect compatible frozen evidence without rewriting totals. An incompatible new scope requires refreezing. A common study scale uses the full applicable receipt statistic, not each day's visible maximum. Context backgrounds are frozen/verified separately from measurements.

## Captured-view commands

orchestration.CONTEXT_SCHEMA is fireatlas-jarvis-context-v1. The envelope contains surface, origin_instance_id, origin_tab_id, context_revision, study_selection, active_view, selected object IDs, owned result refs, destination, source document revision and return route.

normalize allowlists and bounds all fields, rejects private/external return routes, and validates the scientific selection. Commands.context checks monotonic instance revision and destination edit access.

Registered recipes are visualization_to_investigation, selection_to_chart_set, findings_to_workflow, board_to_portable_exports and continue_investigation. Follow-up actions are typed/allowlisted, not arbitrary code.

Submission requires an idempotency key tied to a request hash. Stable command-derived object IDs and durable step input/output checkpoints prevent duplicate insertion on retries. A saved board can await destination-view acknowledgement; that state is distinct from failure and from completed visible delivery. Restart turns interrupted deterministic commands into resumable partial work. Cancel/resume/undo act on the saved command and preserve unrelated later edits.

The browser bridge is static/jarvis-orchestration.js; Studio's conversational attachment/proposal bridge is studio/assistant.py. Scientific receipts are resolved by their actual owner before worker admission. Captured image pixels never become numerical evidence.

Whiteboard assistant requests can return a bounded diagram intent. `assistant/board_diagram.py` validates node IDs, saved-evidence membership, question wording and restricted relationships; evidence node labels and document/card/snapshot bindings are supplied by the server. Interpretation labels repeat the assistant's existing validated interpretation. This is an AI-generated explanation, not a verified scientific relationship. It does not apply board mutations itself.
Whiteboard assistant answers can also nominate an owned saved `comparability` or `finding_comparison` snapshot as a `monthly-comparison` visual. The server supplies its board/card/snapshot binding; the client obtains chart values through the verified snapshot preview. Assistant artifact IDs take precedence over any original result ID embedded in retrieved receipts, keeping the session-owned reference consistent with frozen board bindings.

## Workflows

workflow.validate checks node IDs/types, port compatibility, acyclicity, parameters and bounded input. Nodes include operation, evidence_input, pick, filter, compare, visualize, card_output, board_insert, portable_export, export_prep and story_output.

Limits are 40 nodes, 5,000 workflow records, eight scientific tool calls and 120 seconds. A concrete pick yields a scalar; wildcard pick yields a series. The runner calls existing Science operations. Deterministic node caching binds inputs/context/release identity; board insertion and export are explicit revision-aware effects. Stale source revisions fail; model-generated executable code is never accepted.

## Rooms and board portability

Rooms store server-owned membership, hashed invite tokens, comments and presenter epochs. Limits include 25 members and 500 comments. Loopback presence is process-local and intended for explicit development/testing. Liveblocks authorization requires server credentials and role checks; presence/shared layout does not replace the scientific document authority.

Portability captures whole-board, frame, or selection into a frozen intermediate representation, including offscreen owned objects as appropriate. Formats: native .fireatlas.zip, editable .excalidraw, SVG, PNG, PDF. Import validates archive paths/duplicates/symlinks, sizes, inventory and hashes, then creates a **new owned board**. Limits: 512 MiB compressed, 1 GiB expanded, 4,096 entries, 32 MiB JSON entry.

Native/Excalidraw need pinned Node helpers and the generated SDK; PNG/PDF need local Chromium. SVG can remain available separately. Miro is an explicit configured remote action with durable local/remote mapping and reconciliation; preparing an archive does not imply publishing a board remotely.

## API groups and verification

HTTP prefix /api/studio/ covers principals/recovery/session; documents with transactions/undo/redo/revisions/snapshots/bindings; stories/generation/renders; workflows/runs; contexts/commands/packages; exports/imports; rooms/invites/comments/presenter; assets and optional Miro transfers. Read http._dispatch for methods and exact request fields, plus studio-app/src/api.ts for callers. Mutations enforce Origin, JSON/body bounds, role and revision; native imports have separate ZIP bounds.

The owned `documents/{id}/whiteboard` GET returns the current Excalidraw elements and embedded PNG/JPEG/WebP files. `patch_whiteboard` uses ordinary document transactions with per-object conflict keys and inverse patches. The current increment stores bounded drawing objects in `whiteboard_objects` (10 MB per board, at most 500 changes per transaction and existing 3 MB request limit). Whole-board native archives include a versioned whiteboard payload and an editable Excalidraw scene; restoration validates and remaps objects and Studio evidence references inside the import transaction. Legacy archives without a whiteboard remain readable. Assistant-only claim result IDs absent from the archive are marked unavailable after import. Other Studio export formats currently refuse to silently omit an attached whiteboard; the editor's direct Excalidraw export remains available. Historical revision reconstruction remains separate. Existing snapshots remain separate. Studio undo ignores later edits paired with their recorded inverses but refuses independent conflicts. Schema 11 records redo-to-undo lineage atomically with each new redo; redo permits a chain of paired undo/redo operations but refuses unrelated later changes. Old redo entries lacking lineage remain conservatively blocked where applicable.

Challenge frames may retain `originalElementIds` and multiple `sourceBindings` in their FireAtlas metadata. For snapshot-linked notes, the assistant resolves all selected owned source bindings and verifies their snapshot hashes before using them. Native restoration remaps existing whiteboard element IDs and marks missing targets unavailable rather than leaving links to objects from the original board.

Schema 9 adds board-owned immutable CSV datasets in the separate Studio database. `datasets.py` accepts UTF-8 CSV up to 5 MiB, 50,000 rows, 100 unique columns and 50 MiB per board; exact original bytes are retained, duplicate content is reused, and access is role checked. The scoped raw-upload route has a dedicated size limit; read returns at most 100 rows and download returns original bytes. The scoped scatter endpoint selects two distinct columns and returns finite numeric pairs, logical CSV record numbers, and a skipped-row count; it rejects more than 5,000 pairs. Whiteboard assistant runs can access one selected saved table through bounded, hash-verified reads; see the assistant guide. Whole-board native packages retain all uploaded tables and remap whiteboard references. Dataset membership is independent of document revision, so exports bind a separate dataset-manifest hash and reject retries after membership changes. CSV tables do not enter the NASA observation database.

The owned dataset `summary` GET route recalculates bounded numeric summaries for up to eight explicitly named columns using `datasets.summarize`. It is used to recheck source-linked whiteboard summary claims without relying on expiring assistant results.

The owned dataset `group-summary` GET route uses `datasets.group_summary` to compare numeric means across at most 30 exact categories in an imported CSV. It includes every row and reports numeric, missing and nonnumeric counts; blank categories stay null. Units and causes are not inferred. More than 30 groups or invalid columns fail explicitly rather than truncating results.

`datasets.summarize` calculates descriptive statistics across the entire owned CSV using the same finite binary64 parser as scatter plots, for up to eight explicit columns. It records numeric, missing and nonnumeric row counts separately and leaves statistics null where no numeric values exist. This operation does not infer units or imply a causal relationship.

`park_chart.py` builds the July 25–28 Park study's four-platform daily recorded-detection table from the existing published replay and NOAA files. It verifies each NOAA file against its publication manifest, records the primary replay and daily NOAA byte hashes, retains source states, and writes unavailable zero-row gaps as empty cells. The owned same-origin `park-timeline` action saves that derived table as a private dataset for the whiteboard and its native package. The result counts records within the case boundary; it does not imply a perimeter or continuous satellite coverage.

Schema 10 introduces `source_documents` and `source_documents.py` for private PDFs. These functions store opaque original bytes with a 10 MiB per-file limit, 50 MiB per-board limit, ownership checks, content deduplication and hash verification; the signature check is not structural PDF validation. Scoped same-origin HTTP routes upload, list and download the original bytes. The client parses the PDF and enforces its page limit before uploading. Whole-board native exports include all original PDFs with a separate source manifest, validate references, and restore them under remapped document IDs; retry rejects changed source membership. Older archives without PDF entries remain readable.

Tests: test_studio_store.py, test_studio_http.py, test_studio_workflow_rooms.py, test_studio_portability.py, test_studio_prompts.py, test_studio_landscape.py, test_studio_miro.py, test_studio_assistant.py. Shared graph vectors live in studio-app/test-vectors/graph.json. Do not equate mocked integration tests with a hosted destination/provider acceptance.


## Calendar and comparison captures

A Research monthly-comparison capture retains the selected held-out year, fixed regional bounds, chart settings and original comparison result identity. The Studio runner recomputes the comparison and rejects a changed result hash before binding it. Return links may carry the public `cmp_*` chart controls. Multi-year summary metrics are not presented on a card scoped to a single held-out year. Raw calendar receipts render their frozen daily occupied-cell values in calendar/chart previews; unknown totals remain unknown. Curated composition omits groups with fewer than two cards.


## Compact evidence saves

The ordinary analytical “Save to Studio” prompt uses the `minimal` composition and saves the selected chart/calendar and, for a raw calendar, its finding without automatically adding presentation/question cards. Curated presentation presets remain separate. Comparison snapshots store the validated experiment key and display mode; previews and table exports read the corresponding rows from the immutable comparison receipt and retain observed/estimated columns. The snapshot hash binds this selection.

## Finding-comparison snapshots

The compact visualization command can capture a `finding_comparison` receipt as a chart card plus an editable finding note. Each command creates a separate immutable snapshot retaining both selected month dates and the chosen series. The selected months are stored as disjoint periods rather than a continuous multi-year observation interval. A later alternative is positioned alongside the earlier finding if that placement does not overlap existing cards; otherwise it is appended safely. The workflow retains the original calculation arguments. `visuals.prepared` renders the two captured rows, and the existing portable archive retains receipt, note and snapshot.

Explicit map record, cell or polygon selections may be included in Studio capture via Save options. The server binds selection and UTC day to the frozen replay; portable native exports include an observations CSV for that selected evidence and verify it against the receipt on export. No selection means no selected-record CSV.


## Assistant calculation snapshots

The Investigation assistant can preserve unbound claims from a completed owned run via `POST documents/{id}/assistant/runs/{run}/preserve-claims`. The server resolves the run and owned assistant evidence, verifies receipt hashes and scalar claims, and atomically stores an idempotent scientific receipt and snapshot for supported scientific operations. Client-supplied claim values are never accepted. Whole-board native exports retain these snapshots and remap their references on restore. A selected snapshot-only whiteboard claim is resolved against its owned saved scene element, hash and verified receipt before a later assistant run; the selected snapshot supplies its own study context. Other assistant-only results are not automatically promoted into scientific evidence.


Saved replay snapshots expose a scoped, read-only `GET documents/{id}/snapshots/{snapshot}/heat` view using the existing `heat.prepare` kernel after receipt verification. It accepts one UTC day and a standard sensor selection, preserving the frozen boundary and full-study scale. It also returns the selected frozen common-cell centers for display markers; it does not modify observations.

Source search uses optional `pdfinfo` to identify the end of a PDF before extracting pages; if page count is unavailable, failures remain explicitly unresolved. Searches remain limited to 20 pages per document, with later pages reported as unsearched.

## Portable scientific board figures

Completed owned runs may preserve supported `data_views` without scalar claims through the same idempotent `preserve-claims` endpoint. The server verifies each view kind against its receipt operation and digest before storing a durable snapshot; client numbers are not trusted. `studio/board_views.py` renders portable SVG coordinate, satellite, Park four-platform, archive-window, environmental, analogue and candidate-profile figures. Existing calendar and heat renderers remain authoritative. Unknown satellite values display as unavailable, not zero. Archive headings/visual scope show actual query years, separately retaining reference scope. Figures retain source boundaries, dates, methods and hashes; existing native packages retain the snapshots and remap references on restore. Tests: `tests/test_assistant_board_views.py`.

Portable restore also remaps pinned-note `sourceBindings` to the restored document and snapshot hashes. Missing, foreign or changed note bindings remain explicitly unavailable. This is covered by a native-package round-trip check.

A completed owned live country run can preserve a `firms_country` receipt via its matching `firms-country` view, with the same digest and claim verification as saved scientific views. The snapshot has the live source identity, rather than the local archive release. Its preview reads the frozen rows and can be reopened without calling NASA or using a model.

Completed owned historical regional FIRMS runs can preserve `firms_region` receipts through a matching `firms-region-heatmap` view. The same receipt digest and claim checks apply. Frozen previews read the captured product results without contacting NASA again.

A multi-view run may name the same FIRMS receipt for several figure kinds. Each preview is checked against the receipt operation and saved snapshot digest. Daily calendars count returned rows for each UTC day in the query window, including empty days. The count does not infer satellite coverage. Archive summaries preserve the distinct scientific operation and original facts for each requested view.

## Frozen regional comparisons (2026-11-12)

`regional_comparison` is an assistant-acquired frozen operation, admitted only through its matching registered data view. Preservation checks the owned receipt hash, scalar values/units and view-operation match. Frozen FIRMS area/country/comparison receipts carry external provenance and can be saved without a local imported archive; dependency manifests are explicitly unavailable, rather than manufactured from an unrelated science release. Selected native comparison elements resolve their `comparisonPanel` against the owned receipt and pass that exact panel scope to the agent.

`heat.prepare_comparison` prepares each panel with its own bounds and dates, verifies the frozen common Gaussian domain against all panels, and never normalizes panels independently. `board_views.render` returns the typed comparison visual. Existing package ownership/remapping preserves snapshot links, panel indexes and scalar paths. Saved display annotations do not mutate scientific evidence.

The owned `GET .../snapshots/{id}/receipt?download=1` response downloads server-serialized evidence JSON. It preserves Python floating-point representations used by the receipt digest; parsing and reserializing a receipt in browser JavaScript can collapse `2.0` to `2` and invalidate that hash. Ownership and snapshot verification precede both inspection and download.

## Durable public research (2026-11-13)

The whiteboard bridge accepts `research_team` only as a literal boolean, defaults it off and delegates all inference/accounting to the shared assistant service. Owned run polling exposes actual bounded stage-start events rather than simulated progress. Saved conversation turns retain bounded public sources, search receipts and validated specialist reports separately from scientific measurements. They are available after assistant-session expiry and remain principal/document scoped.

Whole-board native exports preserve these research fields and original public-research receipts inside the existing conversation digest. Restoration validates bounds, specialist structure, finite usage and HTTPS source links before rendering. Imported research remains authored/untrusted; retaining a digest does not independently verify scientific claims. Old packages without research fields remain compatible. Subset exports and another principal's conversation remain excluded by the existing scope/ownership rules.

Structured `research_answer` fields and their exact citation handles now accompany saved whiteboard research turns. Summaries are bounded to 2,400 characters; the proposal fields have separate 600/400/1,000-character limits. Native restore validates source structure before resolving handles, then requires each cited handle to exist in the turn's public source cards. This retains proposals after session expiry and keeps malformed imported IDs inside normal validation errors. It does not authenticate authored/imported prose as measured evidence.

Public source-reading reports are retained with owned conversation turns and native packages. `public_reading.validate_reports` checks bounded article/abstract/unavailable states, source-handle/DOI identity, fixed original-text links, UTC, passage shape/truncation and receipt hashes; unshortened paragraph hashes also recompute. These are publication provenance/integrity checks, not scientific admission. Original complete XML is not included in the conversation package; selected excerpts and the original response hash/link are preserved.

Owned conversation turns also retain bounded `nasa_discoveries`: exact UTC/bounds/query, collection/granule/associated-variable metadata, nullable unknowns and original-page/receipt hashes. Native restore checks source handles, fixed NASA concept/page URLs and query scope, metadata bounds, child states and report digests. These imported reports remain untrusted catalog context, not acquired measurements or verified coverage. Original raw CMR pages remain in separate owned assistant artifacts; native conversation exports carry normalized metadata and hashes/links only.
