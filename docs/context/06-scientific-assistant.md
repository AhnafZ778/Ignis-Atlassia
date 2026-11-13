# 06 — Scientific assistant / JARVIS / MCP

[Context entry point](../../CODEBASE_CONTEXT.md) · reviewed 2026-10-27

## Authority chain

Scientific modules → Science.call → owned hash-bound evidence receipt → fact/guided_answer → validated UI claims/actions.

Models choose tools and prose; they do not supply authoritative scientific values. Deterministic operation buttons and registered prompt recipes can work without a model key.

The Investigation assistant can read selected note, labeled-shape or frame IDs after resolving their text from the owned saved board. The bounded `read_selected_board_notes` tool treats text as untrusted authored context; a note-only response is an AI interpretation with no checked scientific claims. See the Studio frontend guide for the selection workflow.

| Module under fireatlas/assistant/ | Responsibility |
| --- | --- |
| contracts.py | normalize_context, METHODS, digest, JSON pointer, semantic DESTINATIONS |
| science.py | Read-only bounded scientific operations and release identity |
| service.py | AssistantService; sessions, run start/cancel, tool/model execution, navigation acknowledgement, notebook export |
| store.py | Owner-checked expiring sessions, artifacts/runs/events, throttling and atomic budget reservations |
| agent.py | Provider configuration, model tools, output validation, fact and deterministic guided answers |
| http.py | Same-origin cookie HTTP routes |
| gateway.py | Optional restricted ASGI proxy/event stream |
| mcp_server.py | Trusted private stdio tools and optional owned MCP Apps views |
| presentation.py | Allowlisted figure kinds, navigation targets and display action options |
| prompts.py | Local transparent question preparation |
| places.py / geometry.py | Explicit cached place lookup and polygon inclusion |
| references.py | Curated local documentation retrieval |
| annotations.py / figures.py | Bounded annotation geometry and selected-figure callouts |
| voice.py | Bounded transcription and checked-answer speech |
| connectors.py | Operator-approved MCP connections; no arbitrary supplied URL/command |
| aiand.py / free_models.py | Authenticated verified provider routing/pricing; verified free-only routing |
| system.md | Model behavior contract; load only with the relevant code |

## Normalized scientific context

normalize_context allowlists year/month/bbox, explicit UTC start/end/as_of/day, case/region, source/series, metric, layer/view/scale, distance/gap, mask_id and revision. Unknown keys fail. Core context can span up to one year; a detailed replay remains at most 31 dates. Research must stay inside one UTC month unless an explicit study_month argument selects a valid intersection.

bbox is west/south/east/north, finite, non-dateline-crossing and within the grid latitude domain. Source/metric choices are explicit; joint FRP fails. Named case defaults are applied without overriding explicit values. Context revision must match the registered browser view when a run starts.

## Science.call lifecycle

Science opens SQLite with mode=ro and PRAGMA query_only. Heavy operations share a semaphore; a SQLite progress handler observes cancellation/deadline. release() hashes the source ledger, schema/export inventory and supporting artifacts and tracks DB/WAL/supporting file changes. A mid-computation release change invalidates the result.

Operations are archive_search, availability, observations, replay, research, calendar, comparability, harmonized, persistence, missingness, compare, sensitivity, exposure, validation, method and sources. Each returns its existing authoritative method rather than a model-written computation.

Evidence schema fireatlas-assistant-evidence-v1 includes operation, method/unit, normalized context, grid, release_id, payload, limitations and SHA-256, saved under the requesting owner's artifact namespace. Detailed observations use stable pagination with 1–200 rows/page. Polygon selection is bounded and uses centroid inclusion; it does not create a coverage denominator. `comparability` requires the exact fixed regional bounds and returns the full available monthly overlap experiment, explicitly outside a selected-day value. The compatibility `harmonized` operation now invokes this same method; legacy calendar APIs remain separately reproducible. `fact` resolves month counts, dimensionless log error, fractional errors, ratios and original-row counts distinctly. Native validation is limited to supported Park/Grove cases.

fact(evidence, path) resolves a JSON-pointer scalar and derives operation-specific units; null, bool, objects and nonfinite numbers are not concrete measurement claims. guided_answer produces deterministic claims. Model validation checks receipt ownership, pointers, values/units, study context, figure kind, navigation/display options, and numeric wording. If final wording fails, saved checked results can remain available.

## Runs, costs, and recovery

AssistantService uses two worker threads. start validates session context/view, message length, operation and idempotent nonce; it saves a run before dispatch. Events record stages and terminal state. cancel signals work and propagates to related Studio commands.

Store persists sessions, artifacts, runs, events and reservations separately from science. Sessions expire; restart marks interrupted model runs failed instead of reissuing potentially billed calls. Budget reservation/reconciliation is atomic. Throttling is not the removed historical blanket 20-run ceiling; archive/map browsing must continue in long-lived sessions.

Provider modes are OpenAI, Google, OpenRouter free-only, and AI&. OpenAI/Google admission requires server keys, verified positive input/output prices and installed optional dependencies. AI& has authenticated route/price verification. OpenRouter only permits verified free routes. The repository's default model labels are configuration defaults, not recommendations about current public models.

Scalar claims and guided answers resolve the same operation-specific units before Studio preserves them. For example, a replay study's aggregate union is in cell-days; its individual daily frame is in cells. Snapshot verification continues to check the saved value and unit against the receipt.

Invalid scalar paths in assistant output trigger a model retry even for imported-source and grouped-table results that do not have a full guided answer. Candidate paths come from the bounded claims and selected-frame preview; this recovery does not invent a value.

For an unselected whiteboard question, Studio resolves at most 20 saved board text elements as untrusted context, labels their scope `board`, and exposes them through the existing board-note tool. It selects text without an assistant-placement marker first, preserving scene order within each category; explicitly selecting an assistant object still reads it directly. Explicit selection keeps the narrower `selection` scope. Text from a saved assistant-placed object, including a label bound to such a shape, is marked `assistant_placed` so the model does not assume it was written by the researcher; other origin is not established by the absence of that marker. Metadata is a context cue, not evidence of authorship or scientific truth. Blank boards supply no notes. The document owner and revision are checked before reading either scope.

Those same bounded notes are already included in the assistant request's Studio context, so the model may answer directly without repeating a note-tool call. The tool remains available. Note content is still untrusted, and numerical claims require checked evidence as before.

For a selected whiteboard visual without a supported note or evidence binding, or when the question explicitly asks to inspect the selected visual, the local client renders the selection as a bounded PNG and submits it with saved element IDs. Studio checks ownership, revision, selected object existence, PNG size and dimensions before attaching it to the existing assistant image path. The image is client-rendered untrusted context, not a scientific receipt; visual-only responses cannot publish checked measurement claims. The client rejects a late answer if the selected content or its image bytes change. Structured evidence remains available alongside an explicitly requested visual inspection.

When a model reads only board notes, a valid interpretation/question diagram can accompany its answer and be placed by the whiteboard. Evidence nodes are omitted from that note-only path because it has not retrieved their scientific receipts; invalid diagrams are discarded.

Diagram interpretation nodes use the answer's validated interpretation as their label, avoiding a mismatch when a model paraphrases the same answer in its node. Labels and interpretations may be up to 1,200 characters; the model is still prompted to keep interpretations concise. Note-only results include bounded diagnostic categories for omitted, malformed or semantically rejected diagrams, without raw model output.

Diagrams may also contain short AI context nodes for distinct ideas. They cannot carry an evidence ID, and the whiteboard labels them as AI context. They remain subject to the existing limits on numerical and causal assertions; source-linked evidence nodes remain separate.

If a notes-only diagram request fails before producing an answer, whether before or after the model reads the saved notes, it reports that the assistant could not finish and offers a retry. It does not ask for an unrelated study or invent a diagram. Provider API errors still use the normal error path.

Secrets stay in private environment/configuration. Use provider_config/capabilities as the current truth; do not copy environment values into docs. Key-name examples include FIREATLAS_AI_PROVIDER, FIREATLAS_AI_MODEL, OPENAI_API_KEY, GOOGLE_API_KEY, OPENROUTER_API_KEY and AIAND_API_KEY. Full statically found names are indexed without values in source-manifest.json.

## HTTP surface

All routes below have prefix /api/assistant/. capabilities is public GET; owned routes require the fireatlas_workspace session cookie. Mutations check exact Origin and bounded JSON; public deployment needs an explicitly configured origin.

| Route family | Behavior |
| --- | --- |
| sessions | POST initialize/reuse, GET context/budget, DELETE private workspace |
| views | Register applied context and browser instance |
| runs, runs/{id}, /cancel, /events | Start, inspect, cancel, poll events |
| prompts | Prepare question locally |
| notebook, annotations | Store/read notes and linked geometry |
| evidence/{id}, artifacts/{id} | Read owned evidence; delete owned artifacts |
| places, images, figures/annotate, masks | Explicit bounded contextual inputs, not authoritative new measurements |
| actions, actions/{id}/ack | Semantic navigation/display action with instance/revision/expiry checks |
| exports | JSON or HTML notebook |
| voice/{operation} | Capability/budget-gated speech |

The gateway adds a separate /runs/{id}/stream event route and does not permit Studio authoring writes.

## Studio and desktop bridge

studio/assistant.py explicitly links the Studio principal to an ordinary private assistant session. Cross-store IDs are validated; knowledge of an ID is not permission. Attached analytical view context carries origin instance/revision and owned references.

Whiteboard assistant answers record their originating document ID. A bounded conversation of up to 30 questions, answer summaries and scalar claim labels/values/units is retained privately in the Studio store for the originating principal and document. Follow-up requests include its latest six turns, including after the assistant session expires; other investigations and older unscoped answers are excluded. Deleting a board removes its retained conversation. The provider receives it as context, not new evidence; retained conversational claims do not replace source receipts. Whole-board native investigation packages include the exporting principal's conversation; restore imports it under the new board and principal. Packages made before this addition restore with empty history.

For a whole-board question without an explicit selection, the bounded set of 20 text elements prioritizes authored notes, then known generated data-display labels, then previous assistant output. This prevents a large chart's labels from displacing a research question. The matching client ordering supports source focus; explicit selections retain their existing behavior. If all live board table references point to one owned, hash-matching table, it is also made available as board context without assuming a selected row. Multiple tables or inconsistent hashes do not trigger automatic selection. The model may read the table when relevant; chart labels alone do not establish data values.

When model wording fails after a table read and the question contains one explicit ISO or English month/day/year date, the deterministic fallback shows claims only from a unique row containing that exact ISO date in the retrieved page. If no unique match is present it offers no row claims and directs the user to the table. It does not search beyond the retrieved page or infer dates for ambiguous/multiple-date questions.

The table-diagram fallback follows the same requested-date rule, including when the retrieved page lacks a unique match. A diagram's interpretation node may repeat the final interpretation with numbers only after the same output validator checks those numbers against claims; other diagram labels still reject unverified numeric values. If the selected source is a grouped bar, its diagram fallback uses the recomputed selected aggregate rather than an arbitrary raw row.

The interpretation validator permits the platform identifiers NOAA-20 and NOAA-21. For whiteboard responses, it also permits numerical values and dates that exactly match independently resolved scalar claims in the same response (including comma-formatted integers and English month/day dates). It rejects other digits and the existing disallowed causal/forecast terms. Numeric matching checks values, not whether the prose assigns a value to the correct source or unit; the linked claim remains the authoritative record.

For grouped tables whose categories are strictly ordered ISO dates and whose means are all present, the grouping tool provides deterministic consecutive changes. A bounded validation rejects common claims that all values steadily rise or fall when a step contradicts that claim, and checks ordinal statements such as a steepest decline after the third date. It does not verify arbitrary descriptions, causes, or trends outside that limited vocabulary.

When a user selects a group-specific chart element, Studio recomputes its saved table grouping and passes the selected category and its index to the assistant. Multiple selected categories remain unscoped. The assistant must retrieve that grouping before interpreting the bar; an aggregate may represent many rows. If model wording fails, the fallback recalculates the selected grouping when necessary and returns its checked mean and counts with group-level source bindings. Group labels can also be cited as checked scalar claims when nonblank.

The owned `GET /api/studio/documents/{id}/assistant/conversation` route returns the latest six bounded turns for the current principal. The whiteboard panel can display them without exposing another principal's history.

If a diagram request for a saved two-period comparison cannot obtain model wording, the deterministic fallback matches any selected comparison view to its exact saved snapshot, describes the selected series' observed direction when both values exist, and returns its available checked values with their saved source binding. Missing values remain unavailable. This is a fallback from the saved comparison, not an independently generated scientific explanation.

For an optional diagram field returned as a string, the assistant accepts a bounded JSON object string through the same diagram validation; non-JSON prose is omitted so a valid model explanation can still be used with the ordinary evidence-linked fallback diagram. Unsupported structured diagrams are still validated. Diagram fallback reports the exception class in `fallback_reason`, without provider response text. A live comparison still reached the fallback after this change; real model output remains provider-dependent.

For a whiteboard request with a selected CSV card or scatter plot, Studio resolves the selected saved element against the owned board, verifies its dataset hash, and grants the run access to that one table. The model's `read_selected_table` tool reads at most ten rows and eight named columns per call, with a 500-character cell limit; it returns exact text and checked claim paths, not aggregate statistics. Imported contents are untrusted data, and the user explicitly selects the table before asking. Provider-backed interpretation requires a configured model; the tool is exercised with a fake model in automated tests.

`summarize_selected_table` uses the owned selected CSV and Python's deterministic numeric parser to summarize up to eight selected columns across all stored rows. It records finite binary64 counts, minimum, maximum, mean and median, with separate missing and nonnumeric counts; empty numeric columns return null statistics and units are not inferred. Checked claim labels retain the column name and indicate that source units are unspecified. `compare_selected_groups` calculates exact-category means and support counts using the same owned table; checked labels identify the group, and challenge claims retain the group, statistic and source for recomputation after restoration. It can prepare a `csv-groups` visual intent, whose Add grouped chart action recalculates the source before rendering. `prepare_selected_scatter` validates two selected column names, prepares the bounded deterministic pairs and supplies a source-bound chart intent; the whiteboard re-reads the source before rendering it. Ambiguous axes require clarification. Correlation and automatic grouped-chart placement are not implemented. Other assistant-only receipts may still be unavailable after package restoration.

When a saved PDF page or excerpt is selected, the assistant may call `read_selected_document_page`: the server verifies the owned board element, source hash and page number, then runs local `pdftotext` for that page with a ten-second timeout and 12,000-byte output bound. This extracts the entire selected page, not only the selected excerpt; scanned pages may have no text. Missing Poppler fails with an explicit availability error. Extracted text is untrusted document content, not a scientific verification or instruction. A resulting whiteboard explanation retains its source and page reference; native packages still mark assistant-only claim receipts unavailable after restoration.

For a selected side-by-side finding view, the client sends saved whiteboard element IDs, not numerical claims. Studio verifies the owned scene, card, snapshot hash, finding receipt and named series before providing the assistant with the selected sensor or estimate alongside the existing frozen receipt. This makes the selection meaningful in an assistant question; it does not automatically search other evidence or generate a new finding.

Whiteboard runs can call `search_investigation_sources` for case-insensitive literal matches across owned CSV tables and PDF pages. Each call visits at most four sources, reads at most twelve PDF pages and returns at most eight matches; a continuation cursor resumes at the exact CSV cell or PDF page and is invalidated if the query or source membership changes. PDFs are limited to twenty pages, matching the reader limit. The result reports scanned scope, unavailable pages, truncation and any continuation; an empty or incomplete result is not evidence of absence. Source bytes are hash-checked, extracted content is untrusted, and matched snippets include a source hash plus a CSV row or PDF page. The client can add a match to the board after rechecking the referenced source, then reopen that row or page. The answer offers at most the latest 24 matched excerpts. These snippets are not scientific causal findings, and literal search is not a semantic index.

New blank Studio investigations may have no study context. Assistant runs for these boards can use imported material, but are marked unscoped unless selected/available frozen evidence provides a study. Internal normalization defaults do not authorize satellite calculations: those requests require a study, and the agent's normal tool and automatic fallback paths enforce that boundary.

Challenge runs use the selected frozen evidence and attached sources; their normal preset, `investigate` tool and deterministic fallback do not substitute a newly calculated satellite study. On an unscoped board, a selected frozen card supplies its own snapshot context if its effective board study is empty.

When an explicit chart request has produced a validated grouped-table result, the output validator supplies the corresponding grouped visual intent if the model omitted it. This does not invent columns or retry a provider request. The whiteboard may automatically place the chart for an explicit creation request after rechecking the selected source; general comparison requests retain an Add grouped chart action.

Explicit creation requests can also automatically place a single prepared scatter plot from the selected table. The client repeats the scoped data read, checks source hash and columns and verifies the captured selection before applying the reversible addition; other requests retain a manual action.

For a whiteboard diagram request with saved evidence, if the provider omits a valid diagram but returns an interpretation that passes diagram validation, a deterministic fallback links the source to that complete AI interpretation. If the interpretation is empty or fails validation, it links the source to an open question. A provider failure without usable wording retains the source/question fallback. Unavailable evidence or cancellation does not create a diagram.

For checked claims citing a frozen board evidence result, the assistant response includes the server-resolved card and snapshot binding. Challenge placement rechecks that binding and stores it on the individual claim element; the whiteboard inspector can resolve its exact payload path. Claims citing a CSV row, PDF page text or a specific source-search excerpt receive an owned source binding with the exact row or page; challenge placement checks that source and the existing table/document inspector can reopen it. CSV column summary claims retain their source hash, column and statistic, and are recalculated from the owned dataset before placement and on inspection, including after restoration. Other assistant-only result receipts remain unavailable after native import.

mcp_server creates a private owner/session per trusted desktop process, exposing bounded investigate/get_evidence/capabilities plus owned Studio build/story/command/export operations. It does not expose shell execution, arbitrary files, source-data imports or human signoff. Export chunks are at most 1 MiB. HTTP download links do not authenticate an MCP client.

studio-mcp-app/src/app.ts uses the MCP Apps SDK for compact board/card/story inspection, selection context and packaging acknowledgements. Its self-contained build goes to fireatlas/static/studio-mcp/. A browser resource existing is not evidence that an external host negotiated the extension.

## Verify and extend

Primary tests: test_assistant.py, test_studio_assistant.py, test_studio_mcp.py, test_studio_prompts.py. Browser checks: verify_jarvis_tool_routing.py, verify_jarvis_presets.py, verify_canvas_handoff.py, verify_archive_run_admission.py.

For a new operation, update science.OPERATIONS and dispatch, contracts.METHODS, fact/guided claims, model tools/validation, display allowlists, frontend affordances and tests together. Inspect release identity if its new inputs differ. Never implement a new scientific algorithm solely in model prompts.


## Raw calendar finding

A raw calendar guided result includes the selected month's observed occupied cell-days, or its explicitly labelled partial imported count when complete totals are unavailable. The scalar is resolved from the scientific receipt and keeps its existing units and provenance.

## Finding-comparison receipt

`Science.call('finding_comparison')` resolves the requested two-period pair through `published_pair`, checks the fixed region/bounds and comparison identity, and stores the full published values, model details and parent hashes as an owned receipt. The selected interpretation is metadata; it does not replace any series.

`environment_analogues` resolves the immutable Park pilot, verifies its hash and scope (MODIS, 2024-07-25–28), calculates the chosen matches in Python, and saves them as an owned evidence receipt.

For a combined whiteboard diagram and chart request, a compatible saved monthly comparison can be offered with the diagram. When the model supplies a diagram, the automatic comparison chart uses its single matching evidence receipt; when the model omits the diagram, the fallback diagram uses the selected chart receipt. The provider-failure fallback offers a comparison chart only for a compatible saved comparison and does not substitute it for a scatter or grouped chart. The interface places the diagram and offers a separate chart action. Explicit simple negations are respected by backend routing; frontend automatic placement remains conservative when any negation appears.

A malformed or semantically invalid optional model diagram is discarded before output; the explanation and claims still pass their existing checks. A replacement evidence diagram is generated only when the saved source is unambiguous or a single associated comparison chart identifies it. Diagram fallbacks can include `observed_retry_categories`, fixed labels derived from retries before another model request; interpretation schema retries distinguish a small allowlist of missing, wrong-type and overlong errors. These labels omit raw model/source content and do not establish the terminal cause.

Selected CSV reads and summaries can bind a model diagram to the owned table. A diagram-only request can use a table-linked question diagram if the model omits one or fails after reading it; the table source takes priority over saved comparisons for that selected-table request.

After validation and source binding, repeated evidence nodes for the same retrieved evidence ID and identical interpretation nodes are coalesced. Edges are redirected to the retained node; duplicate edges and self-connections created by the merge are removed. Different evidence IDs and distinct questions remain separate. The interpretation merge also applies to note-only and visual-only answers.

Table evidence nodes use the owned table name and up to three actual field names from the returned table page (or the selected table metadata when appropriate). Labels are bounded and whitespace-normalized, with an ellipsis for omitted or shortened metadata; they are source identifiers, not model-generated measurements. The same labeling is used for a table-read fallback.

When an AI response fails after a board source search has completed, the checked fallback retains the search matches and their source identities so the user can still inspect the matched files.

If a whiteboard request fails before a checked result or action exists, the response identifies the assistant as unavailable and offers a retry instead of asking the user to select an unrelated study. Model API failures retain their existing error path; cancellation remains cancellation.

If the scientific archive cannot be opened, assistant capability discovery reports a null release and an unavailable FireAtlas data connector. This does not prevent Studio from creating and opening private boards; scientific operations still require their source archive.

Source-search prompts ask the model to summarize without constructing passage claims; matched excerpts and source links are supplied from the search result. A checked fallback presents found matches even when wording fails.

Satellite-specific limitations are attached when satellite evidence is involved; source-only PDF, CSV and literal search responses retain their own source context.

For a selected table or chart linked to one, the assistant is directed to read that table before asking for a separate satellite study context.

For a source-linked table object with an unambiguous valid row offset, Studio supplies that row as the starting point for the assistant's selected-table read. Comparison instructions ask for checked representative values alongside dates and statuses, while blank cells remain unavailable. Multiple selected rows do not imply one preferred row. The provider can still omit requested claims; this instruction is not a guarantee of answer completeness.

If a challenge fails after both a selected-table read and a source search, the checked fallback prioritizes the selected table and retains source-search excerpts. The Park challenge can display table-bound values alongside an open question; the fallback does not present them as AI interpretation.

When a checked fallback is caused by a framework usage limit, its internal answer metadata records only an allowlisted limit category (or `other`), never the exception text or source material. It does not increase quotas or spending limits.

For a selected-table challenge with retrieved evidence and no unresolved location or requested action, a model response may combine a follow-up question with checked claims and a separately validated visualization. The question is retained in the interpretation and all ordinary claim, visualization and wording validators still apply. Other clarification paths keep their existing no-claims rule. The prompt asks the model to inspect source-state fields before describing a blank satellite value; this instruction does not itself verify the interpretation.

Blank and whitespace-only imported table cells cannot be returned as scalar claims. Selected-table answers without a diagram request must include a nonempty interpretation or retry; if wording remains unavailable, checked source-linked table values remain available through the bounded fallback.

Table comparison instructions distinguish a shared date from spatial overlap or equal coverage and prohibit relabeling detection counts as cell-days or individual fires. This instruction does not automatically verify the model's interpretation; a live response has incorrectly inferred common cell-days from daily source totals.

If diagram wording fails after reading a selected table, the fallback retains up to eight exact nonempty table values with row-specific source bindings, alongside the editable question diagram.

Selected-table reads return up to 32 checked nonempty cell claim candidates with exact payload paths; invalid-claim retries can reference the same candidates.

A selected-table read accepts up to twelve exact column names and ten rows, and returns bounded checked cell candidates.

Paid whiteboard requests have a bounded cumulative input allowance of 45,000 tokens for multi-call source reads; per-call cost reservations and existing spending caps still apply. Free routes retain their 20,000-token allowance. Mixed search and selected-source requests instruct the model to address each source; an incomplete model response still uses the checked fallback.

Checked imported-table cell claims display their source column and one-based data-row number; their unit is the generic reported value because the assistant cannot infer source units from CSV text.

CSV cell claim labels use logical CSV record numbers including the header, matching the table and scatter inspectors; stored row offsets remain zero-based data-row offsets.

## Source-backed whiteboard views

Whiteboard-only `prepare_board_view` requests heatmap, original coordinates, source-separated satellites, raw calendar, archive, measured factors, environmental analogues or similar imported profiles. `board_views.py` validates case/date/boundary/source intent and shares unresolved/resolved place checks with ordinary investigations. An unscoped board requires a named supported case or explicit custom boundary/dates. Changed selected boundaries and narrowed intervals require the request to authorize them. Source-qualified calendar/map requests cannot silently substitute another sensor. Coordinates are bounded to 200 original rows on the selected UTC day. Park satellite views can use the existing hash-verified four-platform publication; factors use only the fixed Park NDVI/elevation pilot. No model supplies plotted numbers.

`show_related_candidate` derives a candidate view's source, boundary and UTC interval from an owned `similar_patterns` receipt; coordinate previews narrow to the requested candidate day. A request may prepare at most four views and cannot fetch replacement studies during a challenge. Completed tool results attach as `data_views` even when checked wording falls back; cancellations and unavailable calculations are not successful views. Invalid requests expose bounded diagnostic categories rather than raw provider failures. New scientific operations are `similar_patterns`, `environment_context`, and `park_platforms`; existing saved-operation unit contracts remain intact.

## Local Ollama mode (2026-11-08)

`FIREATLAS_AI_PROVIDER=local` uses the loopback OpenAI-compatible Ollama endpoint and `FIREATLAS_LOCAL_MODEL` (default `ignis-scientist:latest`). `local.py` validates loopback configuration, checks installed-profile readiness, filters/shortens tool definitions and classifies unselected general concept questions. Local requests bypass paid price admission/reservations, record local inference receipts, and never fall back to a hosted provider. Raw selected-image interpretation and hosted speech are unavailable in this text profile.

`local_system.md` requests brief, answer-first plain language and permits labelled hypotheses/opinions. The local agent accepts natural text as well as checked structured drafts; text passes the same source/action and numeric-wording checks. General conceptual explanations may have no measurement receipt, clearly labelled AI general explanation. Requests for maps or selected-source measurements still require actual tools. Automatic repeated limitation text is omitted from local conversation; scientific caveats remain in immutable receipts/figures. This is prompt/inference configuration, not trained weights or verified scientific judgement.

`scripts/setup_local_assistant.py --activate` downloads Qwen2.5 1.5B by default and builds a non-thinking CPU profile through Ollama. `--base-model` selects an explicit alternative. `scripts/run_website.sh` gives the ignored local env file precedence without loading the private cloud file. Existing providers and boards remain available. See the setup guide and `tests/test_local_assistant.py`, plus local natural-text/tool tests in `tests/test_assistant_board_views.py`.

Board view preparation now fills omitted case/date/source fields only from explicit unambiguous user intent. A model-supplied conflicting source still fails; this reduces avoidable small-model retries without changing evidence scope.

## Helpful communication and scoped previews — 2026-11-08

The local and shared system prompts now lead with the requested answer/action, allow reasoned hypotheses/opinions and discourage mechanical disclaimer lists. The local prompt includes short positive examples instead of an exact two-sentence rule. Default whiteboard Explain now asks for the main pattern and a useful next investigation. Routine answer-level limitation footers are omitted; scientific method/scope notes remain in immutable receipts and UI source inspectors. Returned legacy notes are collapsed under Source notes in the companion. Existing board objects and source receipts are unchanged.

Calendar model previews now select the requested UTC interval from the original year receipt instead of exposing the first months/days through generic list truncation. Previews contain up to 31 matching days with exact original receipt paths and checked daily candidates. They do not present full-month totals as a selected sub-month result. Longer intervals are explicitly marked truncated. This changes model context, not the scientific calendar or stored receipt.

Local unselected concept questions use plain text without unused tool/output schemas or unrelated board-table reads. General technical explanations and authored board-note discussions can use ordinary numeric specifications/numbered steps without publishing measurement claims. Selected scientific measurements still resolve exact owned values and units; unsupported numerical measurements still fail. The wording validator accepts natural month/day forms of checked ISO dates, list numbering, negation and explicitly qualified hypotheses instead of rejecting all uses of causal vocabulary.

Observed timings before this change: 3 successful stored local requests averaged 59.23 s (39.18–79.80 s); some earlier attempts timed out. A fresh 3-product one-day Dhaka-area FIRMS test averaged 1.271 s per direct provider request (1.246–1.287 s). These small samples distinguish data acquisition from CPU inference, not a service-level guarantee. Live post-change answer timings and quality checks are recorded in the prototype checkpoint.

For small local selected tables (at most 10 rows and 12 relevant columns), the owned/hash-checked reader now supplies the data before inference. Hash columns stay in provenance rather than the language-model data preview. The bounded CSV preview retains all requested sensor/state columns; if one row matches the question date, the prompt focuses that row with original receipt paths. Normal source explanations use natural text and auto-bind matching source values/dates; structured output is reserved for requested chart/diagram plans. The selected-table tool menu no longer offers unrelated satellite calculations or unrequested grouped charts. Larger tables and explicit aggregation/scatter requests keep their existing readers/calculators.

Small-table plain explanations now receive only the question and named source records, with readable sensor labels and explicit unavailable labels. The model no longer gets positional arrays, provenance IDs, claim-candidate JSON or unrelated tool schemas for this path. The server still binds mentioned values and natural dates to the original requested-row receipt paths. This addresses an observed local-model error that shifted NOAA readings across the blank S-NPP column; mere digit matching was insufficient to establish a correct interpretation. Source-aware quality checks remain separate from HTTP completion and unit-test success.

Final measured local app checks were 7.75 s for a short explanation and 7.85 s for the actual selected Park table (one inference each), after earlier misassociation/fallback attempts were rejected as quality passes. Source explanations now preserve sensor/value association across missing cells. The small warm-runtime sample is not a guarantee for larger evidence or cold starts.

The model-facing missing-value label is unavailable, rather than internal JSON null; original CSV blanks and receipt bytes remain unchanged. Source prompts translate status codes into ordinary wording.

Selected CSV candidates are bounded after focusing the requested row, preserving original receipt indices even for later rows. Local natural-text claim binding accepts sentence punctuation and checked comma-formatted integers, while rejecting digit substrings and unsupported values. A regression replays the exact public Park response previously rejected when its final count ended a sentence.

## Showcase continuation — 2026-11-09

The active local alias now uses Qwen2.5 1.5B after public Park-data trials. The earlier abliterated Qwen3, a 4B instruction trial, standard Qwen3 and an installed Mistral trial were not accepted as better defaults: some misread trends/units, and Mistral was slower. No model training or cloud fallback occurred. The setup script reproduces the selected profile and retains an explicit base-model option.

Selected CSVs no longer hide scientific-view tools. Unambiguous single named-study display requests are prepared through the existing checked tool before one compact wording request. Explicit ISO days and English study ranges are preserved together; custom geographic/ambiguous requests keep normal tool selection. Scope/source/ownership/cancellation checks remain in the existing prepare path. Prepared prompts contain source labels/values rather than geometry and unrelated board text; unavailable sensors are not described as agreeing. Native scientist quantities remain in the original receipt.

Small selected-table explanations receive the focused record and checked same-column directions against the nearest earlier uniquely dated row. Missing numeric cells and duplicate dates stay unavailable/ambiguous; original cell paths bind neighboring values. Ordinary comparisons focus on available readings; explicit missing/status questions retain that metadata and partial-export status stays visible. Local prompt JSON uses readable UTF-8 so copied Unicode label escapes cannot masquerade as unsupported numbers. Date-wording validation recognizes compact ranges only when both endpoints are checked.

Local challenges reuse loaded frozen receipts in a compact single-inference path. A single-day replay is described as one dated view, with its actual acquisition/grid field names available for an executable test. Analysis-note sourceBindings are verified against the owned document and frozen hash just like direct snapshot references; a changed or foreign hash is rejected. The qualitative model alternative remains an interpretation, not a new measurement or calculation.

A local prepared heatmap prompt asks for the dated detection count, occupied grid cells and one next check using record times or matching grid locations. The output check rejects claims about the extent of affected land or fire severity based on detection-only results. Checked values and source scope remain authoritative.

For Investigation only, the assistant worker dispatches explicit heatmap-catalog questions and recent country-reading requests before invoking the language model. The catalog comes from the registered replay cases; its exact Add requests calculate a normal owned replay receipt. Country reading requests resolve one country from the packaged Natural Earth name and boundary reference. The server uses the private FIRMS key to query one near-real-time product over 1–5 recent days (default NOAA-20 VIIRS and three days), then filters area rows to the simplified country boundary. The receipt carries acquisition UTC, original coordinates, channel brightness in K, FRP in MW where available, product, query bounds, response digest and boundary digest. This does not import observations into the main scientific archive. A model explanation, deterministic answer and tool failure remain separate outcomes.

General local MODIS/VIIRS questions receive the NASA FIRMS reference facts on nominal active-fire pixel sizes and observation differences. The model still writes the response. Source: https://firms.modaps.eosdis.nasa.gov/alerts/notes.php .

Natural map wording including “provide”, “make” and “generate” uses the scientific-view route. A failed view request without a matching receipt does not substitute selected-table evidence. Explicit numeric before/after wording is checked for reversed increases and decreases before publishing model prose.

An open-choice California wildfire heatmap request can select the archived Park Fire case directly. The route explicitly identifies its MODIS product, UTC day and query bounds; a close-up uses the smaller box around the incident reference. Explicit dates, sensors, cases and other regions stay with the normal scope handling. The view and displayed counts come from the standard owned replay receipt.

The open-choice heatmap parser accepts optional articles and named regional aliases. For an open Sundarbans fire request, the server queries four standard-processing FIRMS area products in the fixed Amurbunia-area box for May 4–6, 2024 UTC. The case refers to the incident reported by BSS on May 4. The owned receipt retains each product’s returned rows, count and digest, plus the incident and locality references. An empty successful query yields a source-linked search map. Transport and invalid-response errors are surfaced separately.

Named local-area map requests use the GeoNames-backed Open-Meteo lookup once for an explicit place. The prototype uses a roughly 40 km search box around the returned coordinate, with no claim about municipal boundaries. It defaults to the latest three UTC dates and supports a one-to-five-day date window. Same-name choices remain explicit when the resolver returns multiple equivalent candidates. After a map request, a place-only follow-up can use the last question from the same owned board. Country and documented incident routes still use their own evidence contracts. GeoNames and Open-Meteo supply place context only; measurements come from NASA FIRMS.

Board reading requests now parse the requested figure kinds separately from their place, sensor and dates. A live FIRMS request can project heatmaps, UTC calendars, coordinate plots, original reading tables and product comparisons from one frozen area receipt. Each product retains its own observations. A place-only follow-up can carry forward compatible view types. Named or attached studies reuse the registered archive calculations. The fixed Northern California and Punjab–Haryana scopes remain required for evaluated monthly comparability. An unsupported daily or custom-area harmonized request yields specific scope guidance.

A view requested from a selected saved FIRMS map or reading uses its verified board-owned receipt, including the original dates, products and rows. A saved single-product receipt supports a map, calendar and readings. A comparison needs at least two products. An open California wildfire request can produce a heatmap and calendar using the same Park Fire close-up bounds and MODIS day.

A plain question about one selected, dated replay heatmap gives the local model a compact set of verified source values in one inference. This path leaves geographic retrieval, explicit date or sensor changes, new views, and diagram requests with their existing tools.

Locality and country reading requests accept calendar years, months and explicit UTC ranges. The assistant separates dates from place lookup, checks NASA FIRMS standard-processing availability, and freezes one bounded year of observations from nonoverlapping one-to-five-day area responses, including per-response digests and product date coverage. Longer ranges and all-history prompts list the covered years as actionable queries. Historical incident requests also check NASA EONET’s wildfire catalog for the same dates and bounding box, with its own status and source link. Detection counts and incident reports remain separate.

Investigation’s area request parser accepts singular reading, spaced and commonly mistyped view names, punctuation and shorthand, location-first phrasing, and qualified localities. Chart exclusions and conflicting places are checked before data retrieval. Same-board follow-ups can keep the previous chart types, dates and product when the user changes only the place, or keep the place when the user changes only the date. Conceptual questions remain with the configured model. Historical date parsing also accepts year-first slashes, calendar weeks and calendar months.

In the Investigation area routes, a plain request for readings now means the monthly observation calendar. Explicit raw/record/table requests still bring a table, and explicit dates still set the exact query interval. A calendar with no dates defaults to the current UTC month through today. Bundled maps and calendars retain the same receipt. The month grid shows the site’s occupied 1 km cell count beside raw returned detections. The map uses the same Gaussian as replay, applied to distinct occupied cells over the queried interval.

Peak-month Investigation requests query one standard-processing FIRMS product with listed dates covering the full search. The search defaults to the previous calendar year when the prompt supplies no dates and ranks complete UTC months by summed occupied 1 km cell-days, or returned detections if explicitly requested. The heatmap and calendar bind to the same selected month. The receipt retains all ranked month totals and the original window hashes, including ties. An all-zero result does not select an arbitrary peak. Explicit Sundarbans landscape requests use the joint Wildlife Institute of India and Bangladesh Forest Department report's rounded search rectangles; the previously documented May 2024 incident retains its own narrower bounds.

## Regional and annual heatmap comparisons (2026-11-12)

`comparison_research.py` exposes `prepare_heatmap_comparison` to the reasoning agent. Compound region/year research is admitted to the model rather than the older single-area dispatcher; this admission does not extract a scientific plan from prompt keywords. The model supplies typed places, mode, dates/years, product and metric. Local comparison requests receive a compact tool/prompt context; selected CSV/PDF questions keep their source-specific path. An alternate model JSON envelope is flattened only when it has one unambiguous recognized mode; its unchanged values still undergo normal tool validation.

Defaults are one peak UTC day per completed year, the last three completed years, distinct occupied EPSG:6933 1 km cells, and NOAA-20 standard processing. Explicit distinct completed years and detections ranking are supported. Up to six panels are retained. Localities use an explicitly labeled approximately 40 km rectangle (or the existing Sundarbans scope), not a general administrative boundary resolver. Each annual query must cover the full calendar year with contiguous hashed five-day acquisition windows; truncation refuses a peak claim. Successful queries describe returned observations, not clear-sky observation opportunity. All-zero years retain no invented winning date; ties retain every equal-scoring date.

`fireatlas/heatmap_comparison.py` owns ranking/counts/deltas. Frozen `regional_comparison` receipts retain complete daily rankings, original returned rows, query hashes, selected panels and a common Gaussian display domain. Saved comparison currently admits two or three single-product FIRMS area/country receipts; replay or arbitrary raster images need a new scoped acquisition. Optional ERA5/Open-Meteo seven-day point context retains original returned JSON, request/returned coordinates, units and response hash; any invalid/unavailable response remains unavailable. Neither weather association nor annotations establish causation. Acquisition needs server FIRMS access; model planning needs a functioning configured provider. Whiteboard research deadlines are 480 seconds and client polling allows 600 seconds. Actual provider, acquisition and hosted checks remain separate from mocked integration.

The local comparison tool returns a bounded numeric brief to the small model while keeping the complete receipt for source inspection. After its successful acquisition, local tool schemas are omitted for the explanation step. Exact panel years/dates remain checked scalar candidates. Natural-language date matching preserves an explicit year instead of consuming the same month/day from a different year; this matters when comparing repeated seasonal dates across years. Numerical wording is still validated and can fall back to checked source results when the model cannot finish reliably.

Regional comparison wording cannot assert statistical significance: no inferential test is part of this count/ranking method. The validator requests a descriptive rewrite and retains checked results if it fails. The local detection-versus-coverage guard also applies to this operation. A model choosing the acquisition correctly does not establish reliable wording; actual local-model probes and fallback cases must be reported separately.

`heatmap_comparison.narrative_issue` checks explicit count equality and increase/decrease statements against the cited frozen panels/years; a contradiction requests a rewrite, never a silent replacement of model wording. Comparative adjective order and hedged hypotheses are outside this narrow predicate checker. It is not a general semantic fact checker or proof of provider reliability.

Comparison prompts and tool schemas are focused for both local and hosted providers. Returned previews include Python-derived successive directions and minimum/maximum panel indices for occupied cells and available weather summaries. They do not add new measurements. Baseline `cell_delta`/`record_delta` bind `delta_reference` to the first panel; `previous_cell_delta` binds `previous_reference` to the adjacent panel. Claim captions for this operation are assigned from the receipt, overriding model-authored labels that could name the wrong reference year. A narrow wording check also rejects an explicit wrong-reference cell difference. An explicit statement that no significance test was performed is allowed; claims of significant or insignificant differences are not.

Actual installed local-model trials selected acquisition successfully but repeatedly confused thermal cells with human activity. Local comparison narration is therefore withheld after acquisition (including frozen-receipt follow-ups); source figures, all panels, weather and exports remain usable with `ai_wording_unavailable` and `local-comparison-narration-unqualified`. General local conversations and other existing operations retain their paths. Dependency-injected test models exercise the narration validators without qualifying a deployed model. A hosted-model failure similarly retains balanced checked values from every panel and explicitly reports an unverified explanation.

Verification on 2026-11-12: authentic Rajshahi annual NOAA-20 SP acquisition completed for 2023–2025, with 73/74/73 contiguous five-day request windows. Independently recounted peak dates/cells were 2023-03-27/14, 2024-04-06/13 and 2025-04-01/19; all three seven-day ERA5 weather requests returned data. A new immutable receipt derived from those retained rows adds the explicit delta references (the original receipt remains unchanged). One configured AI& hosted-model probe over this verified cached receipt completed with a checked scientific interpretation after correction; earlier failed probes remain failures. This is a bounded observed provider run, not general model qualification, provider-origin attestation, human scientific approval or Render/Vercel runtime validation.

Frozen-comparison follow-ups use the owned prepared receipt directly. The legacy single-view rule that required preparing a new map whenever “heatmap” appeared no longer applies to comparison-agent requests; the ordinary no-evidence/tool-required guard still applies. Failed wording on a frozen comparison also returns that checked evidence instead of the single-view “could not prepare” error. Selected CSV/PDF behavior retains its separate routing and validation.

Explicit weather superlatives tied to a year or ordinal panel (for example “the latest year was hottest”) are checked against the actual finite seven-day summaries; an unavailable value cannot establish an extremum. This is a narrow relation validator, not general semantic verification. A real browser follow-up initially exposed this contradiction and was not counted as a scientifically valid explanation.

## Public research and bounded specialist team (2026-11-13)

`web_references.py` repairs explicit public-search parsing and retrieves metadata from fixed Crossref, NASA CMR collection and Wikipedia endpoints, with an optional configured web-search provider. Each provider has bounded response/time limits, cancellation/deadline checks and returned/unavailable status. Searches retain query, retrieval time, exact returned source URLs, scope and digest in an owned `public_research` artifact. Collection discovery is not data acquisition; snippets are not full-paper findings. Bare searches of saved sources keep their existing local path.

Reasoning context keeps six prior turns, compact public references and completed specialist proposals; it excludes raw search receipts/provider accounting and sends Studio context once. Full originals remain in the owned board history/export. The existing cumulative input and USD limits remain unchanged. If wording reaches a limit after retrieval, the exact sources remain available with a truthful explanation-unavailable state.

The coordinator's `search_public_research` tool permits at most two attempts per turn, uses concise public terms and supplies exact retrieved source cards. Frozen challenges cannot invoke it. A model-authored URL anywhere in the final draft, including a clarification, is rejected after retrieval. Hosted comparison planning keeps search available after preparing evidence; local comparison tool compaction remains unchanged. Repeated identical comparison arguments in one run reuse their receipt.

`research_team.py` adds an opt-in observation analyst, scientific skeptic and experiment designer. Each makes one actual model call on compact checked scalar cards and public metadata, without recursive agents or tools. It requires the existing authenticated AI& route and verified positive prices no higher than $0.50 input/$1.50 output per million tokens. Maximum serialized input is 6,000 UTF-8 bytes plus a framing allowance per role; output is capped at 420 tokens per role. A single conservative aggregate reservation precedes all inference, with an immutable $0.02 additional ceiling and normal session/day limits. The coordinator's cost is separate. No automatic inference retry or paid-provider fallback occurs. Reported usage is settled; any uncertain usage retains the reservation.

Specialist outputs are authored proposals, not independent scientific review. Unsupported counts, invented citations, malformed/truncated output or contradictory comparison relations are withheld. Exact cited source identifiers and whole VIIRS-resolution product names present in retrieved metadata can appear without admitting that number as a measured count. Fixed diagnostic categories reveal no raw rejected prose or provider errors. Cancellation and partial failure preserve existing evidence; an optional team failure preserves the main answer.

Focused checks: `uv run --python .venv-assistant/bin/python --no-project python -m unittest tests.test_public_research_agent tests.test_research_team tests.test_assistant_web_references tests.test_studio_assistant tests.test_studio_portability -q`. Mocked tests are distinct from actual public API/provider/browser verification. General scientific narration, full-paper review, all NASA products and Render/Vercel integration remain separate acceptance work. The bounded original-passage reader is described below.

### Structured public research answers (2026-11-13)

After actual public retrieval, the hosted coordinator can return a `research_answer` with bounded synthesis (600 characters), hypothesis (400), proposed test (1,000) and exact server-assigned reference handles. Preferred prose is shorter than those hard bounds. The composed structured-research summary and durable conversation allow 2,400 characters so the separately bounded sections fit together. Ordinary model interpretation fields and diagram labels retain their existing 1,200-character limit. Measurement claims still require original scientific receipts and checks. Research proposals are authored AI text based on metadata, not verified findings. Existing numeric/causal wording checks cover specific patterns, not arbitrary semantic assertions or spelled-out numbers.

`PrepareOutputTools` reduces the final output schema to flat title/synthesis/hypothesis/proposed_test/source_ids/essential clarification fields only after public metadata exists and no scientific result or requested diagram/chart needs the full schema. Citation choices are constrained to the actually returned handles. Dynamic post-retrieval instructions ask for one concise qualitative sentence per section; they do not remove calculation tools. Detectability proposals are prompted to require independent fire-presence references and matched per-location overpass/cloud/geometry opportunity. That instruction is not a semantic proof that a model proposed a valid experiment. Flat fields normalize to the canonical stored `research_answer`. Every scientific function tool stays available; acquiring a scientific result restores the full checked-claim schema. Before public retrieval, the additional research schema is omitted. Search tools return compact reference handles and metadata rather than duplicating original URLs/provider receipts; exact links and hash-bound receipts remain server-owned and portable. Conceptual public-research diagrams remain authored context and cannot imply an uninspected scientific receipt.

Conversation context retains each structured proposal and its actually cited handles/URLs, including later references beyond the first three, without repeating its formatted summary. `model_diagnostic` records only safe field names/lengths, fixed retry categories and message/schema byte sizes; rejected model prose and private provider exceptions are not retained. Bounded JSON object strings in research_answer, or a hosted JSON-only final text object, pass through the same typed and semantic validation as objects; surrounding prose/Markdown is rejected. This accommodates observed provider formatting without changing field values. Schema retries retain field/type/message metadata with original input and exception context omitted, avoiding recursive exception serialization and repeated rejected content. Empty/whitespace-only proposal fields fail. Citation handles, specific Sentinel/Landsat platform identifiers and whole VIIRS-resolution product names present in retrieved metadata are excluded from numeric-wording checks, as in the specialist runner; their numbers alone are not admitted as measured values. Token/USD ceilings remain unchanged. Public-only titles pass the same metadata-aware digit/causal wording guard before clarification can return; unsupported heading measurements are rejected too. Schema, digit-pattern and citation checks do not independently qualify scientific truth.

### Original public source passages (2026-11-13)

`public_reading.py` resolves a server-owned DOI reference through fixed Europe PMC metadata and open-access XML endpoints. It refuses redirects and arbitrary URLs, bounds each response to 2 MB with cancellation/deadline checks, checks returned DOI identity, rejects entity/internal-DTD declarations and extracts at most four original paragraphs (1,500 characters each). Heading matches guide section selection; original order, section/location, complete-paragraph hashes, truncation, UTC retrieval time, original-response hash and reported license remain attached. Unavailable full text may expose only an available matching abstract; unavailable means unavailable. The entire article is not reviewed, and publication prose is not a checked local measurement. Portable excerpts retain original-source hashes and links, not the entire original XML file.

`read_public_reference` permits two attempts per turn and keeps the main 45,000-input-token/USD ceilings. Handles bind to the current source catalog or a frozen owned saved catalog; both saved references remain available across reads. A scientist-supplied DOI URL must match the chosen owned source; terminal prose punctuation resolves only against owned exact URLs. Explicit deterministic searches now assign handles after retaining their unchanged original receipt. Frozen challenges cannot read new sources. The model may choose reading; no keyword recipe invents article findings. Source-reading receipts and excerpts survive wording failure, private history and native export/restore. Main qualitative synthesis uses selected passages when available and retains ordinary scientific claim validation. Compact follow-up context includes limited original passages; full receipts remain owner-bound.

Exact DOI search terms (bare DOI or doi.org URL) use Crossref’s exact work endpoint and verify the returned DOI before creating a source card. Ordinary topic searches keep bibliographic discovery; an exact lookup failure never falls back to unrelated bibliographic matches.

A real passage-reading run retrieved both requested sections but exhausted the existing input ceiling while rewriting an overlong synthesis. Reading-tool and post-retrieval guidance now aim for shorter captions (220/160/320 characters) within unchanged hard schema limits. Safe diagnostics measure both flat and nested prose-field lengths without retaining rejected prose; this guidance does not guarantee provider compliance.

### Scoped NASA catalog discovery

`nasa_discovery.py` and the reasoning agent's `discover_nasa_data` add topic/region/UTC collection discovery, then exact-concept inspection of up to five granules and eight explicitly associated variables. A named locality reuses the existing labeled approximately40km rectangle resolver (Sundarbans retains its landscape scope); direct bounds must come from the scientist's bracketed array or the selected study. Granule inspection requires both bounds and inclusive UTC dates. The CMR inclusive next-day query boundary is retained in original query provenance; returned granules starting on that next day are omitted from the requested-day candidate list. The listing is conservative and bounded, not observation coverage.

The reader uses fixed public NASA CMR endpoints without credentials or redirects, bounds response reads at512KB, preserves original page bytes in owned server artifacts and normalized metadata/query/UTC/original-response hashes in reports. Public catalog availability is not file access authorization, downloaded observations, clear-sky opportunity or scientific measurement. Unknown units, dates and listing completeness stay null. Associated variable IDs come from the exact collection metadata or verified variable associations; optional variable-name patterns refine the bounded listing. Child endpoint failures retain other usable parts. No arbitrary returned file URL is fetched. Three attempts per turn and19000-byte serialized reports keep the existing main45000 input/USD ceilings and specialist limits unchanged.

A shared twelve-reference catalog keeps R handles stable across public searches, source reading and NASA discovery; omitted new citation cards are reported as limited instead of exceeding native source bounds. Original search receipts retain all returned references. NASA reports, exact collection citations and scope survive owned saved history and native restore; portable reports retain normalized metadata and response hashes/links, not complete raw catalog pages. Compact follow-up context retains exact concept IDs without resending original pages. This backend increment reuses existing source-card presentation; it does not reset the capped visual review or qualify scientific narration, actual observation acquisition or hosting.

Focused checks: `uv run --python .venv-assistant/bin/python --no-project python -m unittest tests.test_nasa_discovery tests.test_nasa_discovery_agent tests.test_assistant_web_references tests.test_public_research_agent tests.test_studio_portability -q`. Synthetic test evidence, actual public API acquisition of metadata, actual model execution and hosted checks remain separate.
