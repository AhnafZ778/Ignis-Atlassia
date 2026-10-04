# JARVIS scientific assistant: architecture and delivery plan

## Purpose and placement

Make the scientist's question a reproducible investigation: requested area and UTC interval → stored observations → a named calculation → inspected evidence → map/table → notebook. The assistant describes recorded observations in third person. It never roleplays as an eyewitness or converts thermal detections into a spread simulation.

The dedicated `/assistant.html` is the investigation desk. It has space for a study form, conversation, a changing evidence workspace and a notebook. Existing pages get a compact assistant dock and contextual handoff. The existing Earth, satellite, orbit layers and controls remain the landing experience.

### Workspace arrangement

1. Plain-language introduction and permanent interpretation boundary.
2. Study setup: named case or custom bbox, ordered UTC dates, source, heat metric, candidate distance and gap.
3. Quick investigations that use stored data even without a model key.
4. Map and evidence tables beside the conversation on desktop; stacked on mobile.
5. Selected-frame controls next to the figure, exact date and source export status.
6. Notebook with scientist notes, evidence-linked map pins, saved findings, JSON export and a printable report.

Visual vocabulary: amber MODIS, cyan VIIRS, muted green shared cells; one light-to-dark magnitude ramp; white selection/annotation outlines. Text accompanies every sensor and status. Unknown/partial exports stay visible. The assistant workspace uses actual cell footprints and a study-wide scale; existing replay retains its explicitly labelled frame-relative smoothing, which must not be compared by brightness across dates.

## Data and calculations

The observed archive, original source rows, replay cells, research cell-days and calibrated VIIRS-equivalent values have different meanings. Tools wrap existing Python calculations rather than reimplementing them in a language model.

| Tool | Scientific purpose | Boundary |
|---|---|---|
| availability | Inventory supplied sources, intervals and local context | Imported rows do not prove completeness |
| observations | Original source rows with exact full matching count and pagination | Not replay-deduplicated totals |
| replay | Daily observation distribution | Standard MODIS / S-NPP; up to 31 days / 10,000 rows |
| research | Source overlap and connected candidates | One UTC month; existing eligibility and limits |
| persistence | Distinct observed dates per returned grid cell | Does not establish uninterrupted burning |
| missingness | Product/export status by source and UTC date | Missing records never establish no fire |
| compare | Newly observed, repeated and not observed again locations | Does not establish spread or extinction |
| sensitivity | Bounded distance/day-gap experiment | Compare membership, not unstable candidate labels |
| exposure | Mask-based source denominators | No percentage without denominator and mask status |
| calendar | Existing raw observed-cell calendar | Incomplete totals remain withheld |
| harmonized | Existing regional calibration | Exact calibrated bounds; no invented custom calibration |
| validation | Existing evidence gates | No AI human-review signature |
| method / sources | Calculation explanations and curated references | References do not become local measurements |

Named cases resolve through the existing catalog. Unknown places require coordinates or an approved geocoding connector. Requests are not silently narrowed; oversized or cross-month analyses explain the applicable limit. Original observations remain inspectable regardless of replay eligibility.

## Evidence and model contracts

An evidence result includes a private result ID, operation, method/version, study context, grid, release fingerprint, payload, limitations and SHA-256 receipt. The language model returns a typed draft with references to exact JSON pointers, not invented numerical text. The renderer resolves the values and units. Rate claims also carry their denominator and mask status. Free-form interpretation and checked facts are visibly distinct.

Selected figures are explicit attachments, not a continuous screen feed. Registered page adapters supply view state and selected records. Terrain screenshots or heat overlays can be attached from Replay; the assistant desk can capture an explicitly labelled geographic cell schematic. All numerical statements still come from tool results. MCP output and attachments are untrusted reference content, never instructions.

Recent investigations and their evidence IDs support follow-up questions. Saved evidence must match the current release before use in a new calculation/answer. Full results remain available in the evidence inspector and exports, even when model previews are truncated.

## Useful agentic workflows

- “Show Park on the globe, then replay July 25.” Resolve catalog, retrieve evidence and navigate using registered destinations.
- “Why are VIIRS observations missing here?” Inspect export metadata and the documented processing-gap ledger; distinguish product gaps from fire absence.
- “Which cells were observed on more days?” Count distinct UTC dates, map cell footprints and attach an interpretation to an actual returned cell.
- “What changed between these dates?” Compare observed location sets and preserve the status of both frames.
- “Are these candidate groups stable?” Run the bounded threshold experiment and compare membership receipts.
- “Explain this sensor difference.” Compare existing overlap totals, expose eligibility differences and separate source counts.
- “Can I infer a detection rate?” Inspect coverage-mask status, denominator and numerator; explain unavailable or unvalidated exposure.
- “Prepare my investigation for another researcher.” Export parameters, checked findings, complete evidence, annotations and source/release hashes.
- “Explain this figure.” Attach only the selected visualization plus structured view state; avoid inferring temperature, burned area or perimeters.

## Navigation and annotations

Models request semantic destinations: globe, Atlas, calendar, harmonization, replay, timeline, records, overlap, candidates, exposure, validation, sources, method, review and assistant. No arbitrary selectors or browser code are offered.

A requested action contains owner, context revision, view instance and expiry. The browser applies it, records actual state, then acknowledges success or failure. Action buttons and automatic requested navigation share this contract. The assistant does not claim that navigation succeeded before acknowledgement. Custom Replay handoffs carry their authoritative result instead of silently opening the default named case. Pages that cannot honor a narrower study refuse the action and retain the result in the assistant workspace.

Annotations pin a scientist note or labelled AI interpretation to a real returned point/cell. AI text is not an independent measurement. Original observations are never edited. Native-mask human review remains a separate workflow.

## Runtime and open-source choices

- [Pydantic AI](https://github.com/pydantic/pydantic-ai): typed outputs, tool calling, multimodal input and provider-neutral OpenAI/Google adapters. [Agent documentation](https://pydantic.dev/docs/ai/core-concepts/agent/).
- [FastMCP](https://github.com/PrefectHQ/fastmcp) and the official [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk): a private stdio scientific server and operator-approved external reference/geocoding clients. [Tool contracts](https://gofastmcp.com/servers/tools).
- [AG-UI](https://github.com/ag-ui-protocol/ag-ui): compatible run/step events over the optional ASGI SSE endpoint. The existing vanilla frontend uses durable receipt polling so it also works with the current stdlib server.
- [Starlette](https://www.starlette.io/) / Uvicorn: an optional same-origin public gateway that keeps local import/sync/review writes private.
- Durable SQLite receipts and pessimistic cost reservations in the core runtime. A restart preserves evidence and refuses to automatically replay uncertain billed calls. This delivery uses that existing-app-compatible boundary rather than adding DBOS or an unrestricted autonomous browser/shell. DBOS and continuous Pipecat/WebRTC remain optional later integrations, not dependencies of this delivered workflow.

Library versions are pinned in `requirements/assistant.lock`, resolved for an isolated Python 3.12 environment. The base app can run scientific assistant tools without installing model/MCP packages.

OpenRouter is an additional free-only adapter. It verifies zero-priced `:free` catalog entries, requires tool support and image support for selected figures, limits routing to explicit free fallbacks, disables paid plugins and speech, and displays the returned model. Quota/capacity errors leave stored-data tools usable; extra keys are not rotated. The adapter uses the installed Pydantic AI OpenRouter integration and does not require another dependency.

## Voice

Explicit microphone recording captures one question, up to 20 seconds. The scientist reviews the transcription before sending. Narration is composed from a saved checked answer, labelled AI-generated voice. Recording files are temporary; raw audio is not stored. Stale narration is rejected after the context changes. Voice uses the same shared global cost ledger. OpenAI speech is optional even when conversational inference uses Google.

## Anonymous public demo and cost envelope

Private HttpOnly SameSite cookies identify temporary workspaces; no accounts are required. Sessions expire after a day idle or seven days total. Owner checks cover evidence, runs, masks, images, notes, actions and exports. Users can delete the workspace; global cost receipts remain for accounting.

The advertised allowance is $5/day. The executable reservation limit is $4.50/day, with a $0.25 session allowance, two active investigation slots, one heavy calculation slot per process, request throttles and bounded payloads. Each paid model call reserves a pessimistic input/output ceiling before sending; unknown usage stays reserved. A usage overrun trips the paid-call circuit breaker. Operator-verified pricing is required; the application cannot enforce a provider invoice if its configured prices are wrong. The provider should also have an independent account/project spend cap.

Keys remain server-side. No dataset download/import, arbitrary SQL, shell, communication or publishing tool exists. Curated external tools must be operator-approved read-only reference/geocoding services. No continuous browser recording or remote arbitrary URL is offered.

## Delivery and acceptance

Implemented modules: study/evidence contracts; source adapters; private store and cancellation; typed provider coordinator; shared dock and dedicated workspace; semantic page adapters; annotations; selected figures; voice; reproducible notebook; same-origin gateway; private MCP bridge; static page packaging and focused regressions.

Acceptance checks: compare totals with current calculations; preserve unknown/partial status; prohibit joint FRP; verify ownership/cancellation/idempotency/stale actions; check cost races and untrusted text escaping; load desktop/mobile workspace and existing pages; exercise custom/named Replay handoffs; exercise the MCP server and gateway; confirm static routes/assets and the existing globe/satellite remain intact.

Provider and speech calls need the owner's credentials for a live check. Offline function-model tests cover the typed tool/claim path without inventing an AI conversation or spending money.
