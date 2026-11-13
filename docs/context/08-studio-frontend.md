# 08 — Studio React frontend and editor state

[Context entry point](../../CODEBASE_CONTEXT.md) · reviewed 2026-10-27

## Boot and build

studio-app is a React 19 + TypeScript + Vite island mounted at #studio-root by src/main.tsx. fireatlas/static/studio.html supplies the shell, Leaflet and shared assistant-map.js. main.tsx loads capabilities, creates/reuses the principal, reads saved document lists, interprets analytical study handoff/explicit board URLs, and opens board/outline/story/workflow/room tabs.

An explicit incoming study must not be replaced by an unrelated saved board's study. sessionStorage remembers current board/handoff; the server remains authoritative. A missing/deleted requested board shows a usable recovery state. Manual creation asks for an investigation name; rename is set_title through the same undoable transaction system. Deleting the final board leaves an empty collection.

vite.config.ts has relative base URLs, two entries (Studio and Excalidraw), no source maps, a Vite manifest and emptyOutDir=true. npm run build typechecks, builds into fireatlas/static/studio-assets/, creates the export SDK, then runs postbuild. This is an output-replacing operation, not a harmless orientation command.

## Source owners

| File(s) under studio-app/src/ | Role |
| --- | --- |
| main.tsx, styles.css | Identity/collection boot, tabs, naming/deletion, shell |
| api.ts | Owned HTTP client, path/URL encoding, idempotency, ApiError/conflicts, render event subscription |
| types.ts | Cross-language study/card/document/snapshot/story/workflow/render contracts |
| store.ts | StudioProvider, transaction queue, current document epoch, conflict recovery, snapshot/report indexes |
| components/Board.tsx, BoardTools.tsx | Built-in card board, pan/zoom, transforms, groups and saved viewport |
| components/CardBody.tsx | Frozen fact/table/chart previews, bounded live maps, expansion and source state |
| components/Inspector.tsx, StudyPanel.tsx | Bindings, evidence verification, card edits, effective study and linked context |
| components/Outline.tsx | Accessible linear counterpart to canvas |
| components/HeatPreview.tsx, FrozenHeatTable.tsx, MapBackgroundControls.tsx | Frozen paired sensor graphics, numeric table, persisted landscape control |
| components/StoryDirector.tsx, StoryPlayer.tsx | Draft/save/resolve/generate/render/recovery and frozen scene playback |
| components/WorkflowWorkspace.tsx, WorkflowPanel.tsx, WorkflowBoundary.tsx | Lazy React Flow composer and module-load/error recovery |
| components/RoomPanel.tsx | Room roles, comments/presenter, presence/layout bridge |
| components/JarvisPanel.tsx, InvestigationActions.tsx | Context-bound assistant commands, board exports/imports and actions |
| components/PresentationPresets.tsx | Curated Park/Camp/Grove creation through lib/presentation.ts |
| components/InvestigationName.tsx, DeleteInvestigationDialog.tsx | Accessible named creation/rename and explicit deletion confirmation |
| components/TldrawBoard.tsx | Optional lazy licensed adapter over the same evidence card state |
| excalidraw.tsx | Independent editable-scene continuation editor |

## State and concurrency invariants

store.ts keeps docRef alongside React state. open() increments an epoch and clears context-dependent reports/conflicts. Async handlers compare that epoch/document/context revision before accepting results. This prevents a response for board A from changing board B after navigation.

Transactions run through one promise queue. Failed operations are retained for reload/retry. A 409 is a conflict to resolve, not a reason to drop edits. Retry explicitly reloads current state and requests a permitted merge. mergeDocument preserves accumulated snapshot indexes and room metadata when transaction responses omit them.

Display selections (day/start/end/cell) propagate only over compatible links and only for the current context revision. They do not mutate frozen measurements. canvasCards overlays shared geometry drafts onto saved cards for display. Room layout edits may go through a registered LayoutBridge; persistent science still goes through the server.

api.ts derives its base from the document base URL for subpath hosting, uses credentialed same-origin fetch, and centralizes machine-readable server errors. subscribeRender consumes events and closes on terminal state/error/timeout; recovery can use persisted job records. Do not duplicate API behavior inside components.

## Domain helpers and paired backend contracts

| Frontend helper | Paired authority / invariant |
| --- | --- |
| lib/graph.ts | studio/graph.py; shared compatibility/topology/selection behavior and test vectors |
| lib/workflow.ts | studio/workflow.py; typed ports and draft parsing; backend validates independently |
| lib/scenes.ts | studio/story.py resolved scenes; reading/question-paused/exploring/returning state machine |
| lib/audience.ts | studio/audience_templates.json and story.adapt_narration; preserve manual authored text |
| lib/chartValues.ts | Exact CSV/table export from frozen prepared values; preserve null/state/unit |
| lib/presentation.ts | Curated frozen evidence layouts, story/workflow preparation |
| lib/mapLandscape.ts | studio landscape endpoint, dated context and background request/cache |
| lib/collaboration.ts, lib/sharedLayout.ts | Liveblocks field-level geometry drafts, server revisions and role-checked auth |
| lib/outline.ts | Human-readable link/follow summary |

Python and TypeScript graph/workflow implementations must change together where the contract is shared. The renderer camera helper is imported by StoryPlayer, so animation changes can affect both browser and video.

## Interaction contracts

Wheel input zooms around the pointer, including over cards; it must not scroll nested content or the page. Empty-canvas/explicit pan, Space-drag and middle-button drag coexist with card-header movement. Keyboard actions and the linear outline must remain available.

Live map slots are capped at two. Prepared/frozen previews remain usable without a live-map slot or optional map service. Background toggles affect displayed context and exported appearance, not counts or common study domain.

React Flow and tldraw are optional editor capabilities with explicit fallbacks. A usable built-in board/outline should survive a missing licensed canvas. Workflow module loading must not strand navigation or lose the saved board. Static hosting truthfully refuses private Studio authoring.

## Verify

From repository root:

```bash
npm --prefix studio-app run typecheck
npm --prefix studio-app test
```

Tests are colocated *.test.ts/tsx (graph, workflow, store concurrency, shared layout, scene exploration, naming/deletion, render recovery, map landscape, heat/chart values and orchestration). Real-browser scripts cover navigation/panning/wheel zoom, workflows, named investigations, deletion, presets and handoff. See scripts/verify_studio_*.py, verify_workflow_browser.py, verify_investigation_*.py and verify_canvas_*.py. Browser acceptance can write test documents; review its arguments first.


## Board-first layout and comparison tables

Studio keeps the saved board first; presentation presets, portability tools, board creation and the card library are grouped behind native disclosures, and the inspector appears when a card is selected. Existing story, workflow, room, template and export paths remain available. A captured monthly comparison can render and export a table of the selected experiment's frozen monthly values through `chartValues.ts`; numerical series come from its saved receipt, not the screenshot. The Studio entry URL carries a cache revision so rebuilt entry bundles replace old layouts.

## Investigation whiteboard

Assistant search matches offer Open original: CSV matches open their exact highlighted record, and PDF matches open their original page. Source hashes and board ownership are rechecked before display.

Selecting exactly one source-linked table, PDF item or frozen evidence item exposes Open source in the action bar. It uses the existing checked inspector; mixed or unlinked selections do not offer an ambiguous target.

The Ask AI companion lives in its own centered dock above the canvas, outside the horizontally scrolling action bar. It is visible even before a named board exists. The first-use panel explains the evidence → ask/draw → challenge flow and offers Start an investigation or a saved-board picker. Entering a board through that guide expands the real companion; its Add evidence action opens the existing source picker without sending an AI request. Ctrl/Cmd+Enter submits a typed question. The canvas fills the remaining viewport height beneath the navigation, actions and companion dock. Escape or the close button dismisses the companion and returns focus to its launcher. Showing a selected source closes the assistant before fitting the source to the resized canvas; an intervening board switch or source edit cancels the delayed focus.

An unavailable assistant response remains visible as a retry message and cannot be added to the board as an explanation. Checked fallback results retain their existing source-linked actions.

The PDF reader renders fonts through the browser while PDF.js script evaluation remains disabled. This allows pages using unembedded standard fonts to render in the reader and in newly placed page images; existing saved page images are not rewritten.

Before a named board is open, board creation errors are shown in the investigation status instead of being hidden behind the scratch-canvas message.

Add evidence → Add cell map renders a saved map card’s verified snapshot using its selected day and sensor as a portable image. The server-prepared schematic retains geographic bounds, labels and available local background; the canvas object retains its snapshot identity and can be inspected or restored through native packages. For saved replay maps, Add heatmap uses the existing Python heat calculation and a study-fixed scale to create a labeled portable image with the selected day, sensor and geographic bounds. Small dots mark the recorded common-cell centers, while the background is dimmed for contrast. It is a static heat image with the existing auto-selected verified local landscape or NASA GIBS vegetation context when available, and a dark geographic frame otherwise; its context label is saved with the image. Inspect selected evidence offers Open current interactive map in a separate tab, retaining the saved bounds, date and source after checking that the date exists in the frozen replay. The interactive page uses the current archive; it is not a replay of the frozen receipt.

`studio-excalidraw.html` mounts `src/excalidraw.tsx` as the canvas-first Investigation page. Drawing, shapes, text, image insertion, undo/redo and pan/zoom use Excalidraw. The original browser-local draft under `fireatlas-investigation-whiteboard-v1` remains available; users can copy it into an empty named investigation. Local Studio now provides a board selector, creation/rename, per-object scene saves and recovery drafts via `lib/useInvestigationBoard.ts` and `lib/whiteboard.ts`. A conflict offers a drawing-only copy; it does not copy the original evidence cards. More → Create recovery token lets the current principal issue a recovery token, showing that issuance replaces any previous token; the token is displayed once and is not saved by the client. More → Recover Studio access accepts an existing recovery token privately through the existing recovery API; it cannot recover an account without that token. On successful identity change it preserves pending work as a local draft and clears the previous canvas before listing recovered boards; an invalid token leaves the current board visible. Saved evidence can be placed as an editable textual summary linking back to its Studio board. Saved finding-comparison and monthly-comparison chart cards can also be added as editable bar shapes and an exact table using the verified Python-prepared snapshot preview. Shapes retain the snapshot identity; editing a shape does not change the source receipt. `WhiteboardAssistant.tsx` connects the existing Studio assistant to the current document; selected evidence previews must still match the card's snapshot ID and hash. It can add its answer as editable text, with each checked claim separately selectable and retaining its own source binding. Frozen-card claims open through Inspect selected evidence; imported-source claims open through the table or document inspector. It can read bounded rows from an explicitly selected CSV, text from a selected PDF page, and selected saved board text or labels inside selected shapes or frames. The server resolves selected IDs against the owned saved scene, limits context to 20 notes of 2,000 characters each, and treats their text as untrusted authored material rather than verified evidence. Static hosting retains the browser-local canvas. Preserve the existing Studio bundle and generated-asset deletions when staging this entry.

## Planned Investigation integration

The [Investigation whiteboard prototype context](12-investigation-whiteboard-prototype.md) records the 2026-11-04 source review, public Clicky reverse engineering, dependency choices, proposed scene/agent/import contracts and a bounded demonstration plan. Investigation's More menu offers native package export and restore into a new owned board, plus local PNG/SVG figure export of the current selection (including frame contents and bound labels), or the whole drawing when nothing is selected. PNG is capped at 4096 pixels on its longer side. Its ordinary Export button downloads the editable drawing alone. A validated assistant diagram may be added as editable nodes and bound arrows using `whiteboardDiagram.ts`. Assistant-selected saved monthly comparison charts are assembled from rechecked snapshot previews; broader chart types, imports and unified history remain planned. In Ask AI, an explicit imperative such as “Organize these notes” arranges two to twenty selected items or groups into a grid locally, after saving the current board and checking that its selection and scene have not changed. Bound text moves with its container, and complete groups, selected frames with their contents, and fully selected connected diagrams move as rigid units. An item inside a frame requires the whole frame to be selected; selecting only one end of a connector is refused. Locked or rotated objects and overlapping destinations are refused. The move is a single undoable scene update and does not require a model call.

An explicit “Organize the board” or “Arrange everything” uses all unlocked top-level objects, regardless of the current selection. Free lines and arrows move as independent objects without altering their points. Locked objects remain obstacles; locked members of an included frame or group, partial connections, unsupported objects, and collisions refuse the operation rather than moving them. The same size limits and single-step undo apply.

With two unlocked, unrotated shapes, notes or images selected, an explicit “Connect these objects” adds an editable native arrow labeled “related” with bindings to both objects. Selected bound labels and the existing contained CSV-card caption count as part of their source card. The drawing library's converter uses a same-sized rectangle only to calculate an image endpoint's binding; the original image and its data reference stay in the scene. It is a neutral visual relationship; the assistant does not infer evidential support or causation. Overlapping objects and unsupported selections are refused. The addition is one undoable scene update, and the connector retains endpoint IDs for source navigation and package remapping.

More → Import CSV or dropping a CSV onto the canvas adds a dataset preview to a named local board; its inspector pages ten original rows at a time and offers an exact CSV download. Two user-selected columns can produce a bounded scatter plot, with plotted and skipped counts. The movable PNG carries its dataset identity, hash and column names; select it and use More → Inspect selected table to reopen the source rows and the saved axes. A paged Plotted values table recalculates the exact numeric pairs used by the current plot, including CSV record numbers and skipped-row counts. Show record navigates to and highlights the matching original CSV record. Add these values to board places the current page as editable, source-linked text beside the chart; each value row can reopen its original record, and the page is an explicit snapshot of the chart axes at placement. Changing the axis controls does not change that table until the chart is updated. Changing the axes and selecting Update scatter plot recalculates from the same checked dataset and replaces the selected image in one undoable board edit, preserving its position and size. A locked or changed chart is not replaced. Select the table or plot before asking AI to let the assistant read bounded original rows; a placed explanation retains its dataset reference. Whole-board packages preserve the image and remap its dataset link. More → Saved tables can re-add a table if its upload finished after the board was switched or before a drawing was saved. CSV sources are private board data. Static mode does not expose CSV upload.

The table inspector's Compare groups control calculates a mean for one numeric column by exact categories in another, and displays numeric/total and missing/nonnumeric counts. Add grouped table places editable text; Add grouped chart places editable horizontal bars sharing a zero baseline, with source-specific counts and unavailable values. Long category labels wrap into rows of appropriate height, with separate room for negative bars and values. Both carry the dataset identity and selected columns. Selecting either and inspecting the table recalculates and reopens its grouping, including after native package restoration. The board objects are saved snapshots and can be edited independently.

New grouped charts retain group identity on each label, bar and value. Selecting one of these elements and opening its source recalculates the grouped table and highlights that category; it may aggregate multiple source rows. Selecting the frame opens the general grouped table. Existing charts can be recreated for per-group focus.

When opening a selected table, grouped value or summary, the inspector checks the selected object and its source metadata after asynchronous reads. If selection or source changes while loading, the old table response is not opened. Paging an already open inspector and assistant source links retain their own navigation behavior.

When a challenge on a selected table or grouped-chart value falls back without AI wording, the challenge frame retains checked claims tied to that selected table alongside an open question. Group-level claims are recalculated and checked before placement. The fallback is a question with evidence rather than an AI-written critique.

When that challenge returns one grouped-table visualization, the whiteboard recalculates it for the selected table and places the source-linked chart alongside the challenge in the same undoable update. A mismatched source or changed selection prevents placement. Other visualization kinds are not automatically placed by this challenge path.

The investigation's More menu links to `park-example.html`, a read-only, standalone example available with or without the local Studio service. It shows the published four-day platform table, an embedded chart and coordinate plots of the actual July 27 detections, with an exact downloadable table. Coordinate plots have labeled axes rather than a basemap. They do not modify the scratch canvas or a saved board.

When the assistant prepares a scatter plot from the selected CSV, an explicit chart-creation request automatically places one validated plot; otherwise the response offers Add scatter plot. Placement repeats the scoped Python calculation, checks the selected source and requested axes, and flushes pending edits before adding the source-linked chart image. An automatic action refuses a changed selected table or cancelled/switched board; a completed addition is undoable.

When the assistant prepares a grouped comparison, Add grouped chart rechecks the selected table hash and grouping columns, flushes pending board edits and places the same editable native chart used by the table inspector. An explicit request to create, make, draw, add, plot or build a chart automatically places one validated grouped result; negated requests and general comparisons retain the manual button. The selected table must remain unchanged, and board switching or cancellation prevents late placement. The table inspector closes so the chart remains visible.

An explicit request to draw, create, make, add or build a diagram automatically places a returned validated diagram. The diagram action flushes prior edits, rechecks each bound evidence card and snapshot, and refuses a changed selection or cancelled run. Other requests retain an Add diagram action. Native arrows connect at the facing node edges and remain bound to editable nodes.

An explicit combined request such as “Explain and diagram this” places the source-linked explanation and the editable diagram together in a single board update. Claim bindings are checked before placement, and the manual explanation action is disabled while placement is in progress. If no diagram is returned, the assistant offers the explanation separately and reports that the diagram is unavailable.

Saved evidence previews wrap their text within the card and expand vertically for longer facts; long uninterrupted values are split across lines without dropping characters.

Add evidence → Add Park Fire satellite comparison places an editable daily line-and-point chart and exact table in a native frame for the bounded four-day Park case. The frame lets board organization move the chart as a unit while individual points and values retain their source links. Lines connect only consecutive available daily observations; missing days break the line. MODIS, S-NPP, NOAA-20 and NOAA-21 remain distinct; the S-NPP processing gap appears unavailable. Each chart object points to the saved derived CSV. Selecting a plotted point, day label or daily table value and opening its source highlights that day's CSV record, including source states and hashes. This is a static case comparison rather than a synchronized interactive map. Existing saved charts retain their original appearance; add the comparison again for the updated chart.

Named investigations route the top Undo/Redo buttons and canvas keyboard shortcuts through Studio transactions after flushing pending edits. Native Excalidraw history controls are hidden on named boards; browser text-field undo remains local while editing text. A history response with an uncertain result or failed refresh locks the canvas and presents Reload board. The restored Excalidraw scene is normalized before accepting subsequent edits to avoid creating a spurious history entry. Native browser-local boards retain Excalidraw history. Backend redo supports new multi-step sequences when intervening transactions are paired undos and redos. Completed pointer gestures are queued as separate snapshots, including while an earlier save is in flight; switching boards flushes that queue. Text edits are grouped until the editing session ends, including pauses while typing; draft recovery continues during the session. Other non-pointer actions still use the debounced path, so complete action grouping remains pending.

Each named board remembers its latest pan and zoom in browser-local storage; reopening the board restores that view without changing the shared scene or creating a board transaction. A first visit or invalid/unavailable stored viewport fits the scene with a minimum readable zoom, so very large boards may extend beyond the viewport. Browser storage is optional and viewport positions do not transfer with packages.

Undo and redo reload the updated scene while retaining the current pan and zoom rather than resetting the view.

More → Export HTML report captures the selected objects (or the whole drawing), a sanitized SVG figure, text notes, and source files tied to selected objects. CSV and PDF originals are embedded as downloads after hash checks; CSVs render as tables, with a 100-row preview and full download when a table exceeds 30,000 cells. Selected frozen snapshots contribute a verified metadata-and-receipt JSON containing the saved result; an expandable preview is capped at 100,000 characters while the download contains the complete embedded JSON. The JSON is serialized for the report, not a byte-identical original download. The report allows at most 30 linked sources and 15 MiB of source bytes; larger selections should use the native package. The report is self-contained HTML without script execution. Its SVG sanitizer normalizes exporter-created namespace attributes before safety filtering so the embedded figure serializes as valid standalone XML and retains frame clipping in independent renderers. Reports are readable exports, not editable investigation packages.

More → Import PDF or dropping a PDF onto the canvas uses pinned PDF.js with evaluation disabled to validate a PDF of at most 10 MiB and 20 pages before saving its original bytes. The reader renders one bounded page and extracted selectable text at a time; users can place the page image or a selected excerpt, each retaining document hash and page number. More → Inspect selected document reopens the associated page; Saved documents recovers uploaded sources. PDF originals and references survive native package restoration. Selecting a page or excerpt allows the assistant to read the selected page's locally extracted text; it requires `pdftotext` on the server and a configured model. Scanned pages display as images without extracted text. The PDF reader worker is included in the staged whiteboard asset refresh.

More → Challenge selected comparison accepts an evidence object linked to an owned, frozen `finding_comparison` snapshot. After checking its card and snapshot identity, it presents an alternate MODIS, S-NPP or adjusted series and places two editable frames using the receipt's same periods and shared scale. Values and changes come from the saved comparison; frame objects retain the source reference and series identity. The source is checked again before placement, and the frames are one undoable addition. When a view is selected, Ask AI sends the saved element ID; the server verifies its source and series and supplies that selection with the frozen evidence. This is a manual comparison of available series, not an assistant-generated interpretation or a search of attached evidence.

More → Inspect selected evidence resolves a selected source-linked canvas object against its current owned card, snapshot and hash and shows its saved facts, method and date scope in place. For a two-period finding it reads both months from the saved receipt. Challenge claims backed by a frozen board card retain that specific card/snapshot binding; the inspector resolves the claim's JSON pointer against that receipt and displays the selected value only if it matches. Claims bound to imported CSV rows and PDF pages can use More → Inspect selected table/document, including after native restoration. CSV summary claims recalculate the selected column and statistic on inspection. Unbound claims from supported scientific assistant calculations are preserved as owned snapshots and can be opened through the same inspector or selected for follow-up questions without a card; source-specific assistant results outside supported scientific operations still need durable receipt navigation.

Ask AI can search bounded portions of the board's saved CSV and PDF sources and offer matching excerpts. Add source excerpt creates editable text with the source hash and exact CSV row or PDF page; More → Inspect selected table/document reopens that location. The table excerpt is checked against the current source before placement. Search limits and unavailable content are returned to the assistant; see the assistant guide. Source inspection and placement remain available through the local authoring service.

Ask AI → Challenge selection asks the assistant to examine a selected source-linked finding and adds an editable Challenge frame in one canvas update. A selected frozen two-period finding also produces side-by-side views from its actual saved values, using the selected sensor or estimate and an alternate on a common scale. The response distinguishes AI interpretation, checked claims and retrieved source context; without checked claims or retrieved sources, or when AI wording falls back, it places an open question. Before placement, the action rechecks the selected elements, owned source bindings and matched source hashes, and flushes pending edits. Source excerpt children retain their own CSV row or PDF page. A changed selection, cancellation, board switch or unavailable source prevents placement. Native restore remaps original element references and marks missing targets and unavailable assistant claim receipts. Further work is needed for complete action history grouping and source-specific navigation from every checked claim.

Challenge frames retain the complete bounded assistant interpretation instead of cutting it mid-sentence. Their initial viewport fit reserves space around the frame; long frames can still require zooming for comfortable reading.

More → Find original finding follows the original element IDs stored on a selected challenge or its source and claim children, selects the surviving original elements and brings them into view. It reports when referenced elements are missing and does not substitute another finding. Native package restoration remaps those IDs; this navigation changes the selection and viewport rather than adding a board history entry.

For a question submitted with a selection, the assistant answer offers Show selected source to select and focus those original objects. Explanations and their individual claims retain the same original element IDs, so More → Find original finding can return to them after saving or native package restoration. If those objects were deleted, the action reports that they are unavailable; the selection cue is not a scientific citation or a saved drawing.

Ask AI has an expandable Recent conversation containing the latest six saved questions, short answers and scalar claim values for the current principal and investigation. It loads when the panel opens and refreshes after a completed answer; a failed load offers retry. Whole-board native exports include the exporting principal's bounded conversation and restore it to the new board. These are conversation summaries, not restored source citations.

Only one CSV or PDF can be dropped at a time, and a saved investigation must be open; mixed source drops are rejected before import. Image and native Excalidraw drops remain handled by Excalidraw. Status messages persist for five seconds rather than disappearing on canvas refresh.

When an explicit whiteboard request asks for both a diagram and a saved monthly-comparison chart, a single compatible chart preview is rechecked against the current board and added with the diagram and optional explanation in one undoable scene edit. A failed or stale chart preview leaves the diagram available and retains the chart retry action. Board switching, cancellation and busy transitions prevent late placement.

For a single saved monthly comparison, an explicit request to create a chart automatically adds the validated chart. If the request also asks for an explanation, both are placed in one undoable edit; ordinary questions retain the optional chart action. Placement flushes pending work and checks the current card, snapshot and preview before applying.

When an explicit request asks for an explanation and a grouped CSV chart or scatter plot, the assistant rechecks the selected dataset and claim sources, then places both in one undoable scene update. An explicit diagram-and-CSV-chart request adds a predefined, table-linked diagram naming the selected columns and asking a question, with the chart and optional explanation in one undoable update. A validated model diagram tied to the exact table and chart columns is used when available; otherwise the predefined diagram is used. New assistant requests are disabled while chart placement is pending.

When a selected Park timeline challenge falls back without AI wording, the board asks how satellite observations compare and which records are unavailable. Mixed selections retain a general question. Questions with attached sources are labeled as open questions.

When an AI challenge falls back without model wording, the board places a source-linked open question. A selected Park table may additionally show checked values bound to that same table; unrelated fallback claims are omitted. Ordinary fallback claim preservation remains separate.

When no item is selected, an Investigation question can read up to 20 saved board text elements (2,000 characters each); the assistant receives them as user-authored, unverified context. Selected items retain the narrower selection behavior. The client rejects a pending answer if board text changes while that whole-board question is running. Images and unselected attached file contents are not automatically interpreted as text.

Assistant diagrams and explanations retain the selected source element IDs, or the same bounded note IDs selected by the server for a whole-board question, prioritizing text without an assistant-placement marker. The source IDs are fixed at submission so subsequent assistant additions do not replace the original context. More → Find original material selects the surviving source items. Native package restoration remaps those references; missing originals remain unavailable rather than being replaced. `boardNoteIds.ts` mirrors the server's selection and must stay in sync with it.

When a selected object has no supported note, table, document or frozen-evidence binding, or the question explicitly asks to inspect a selected visual, Ask AI renders the selected objects as a PNG of at most 1536 pixels per edge and sends it to the configured vision route. The visual is context rather than a measurement. Source changes, image-file changes, cancellation and board switches prevent a late result from being placed. Supported evidence selections continue using their structured sources as well.

Diagram nodes wrap labels and use individual heights; each new row begins below its tallest predecessor. An interpretation longer than 120 characters occupies a full-width row with wider text wrapping, preserving its full text while reducing diagram height. Arrows remain bound to the facing node edges. The assistant opens from a compact top-bar control into a scrollable floating panel, leaving the canvas at full size. A transient cursor marks the selected source while the assistant is reading or pointing. For a real scene edit, `assistantPlacement.ts` fits the camera to the intended objects, approaches their bounds and sweeps a clipped preview rendered from the actual Excalidraw elements and files. A straight connector follows its native endpoints. The companion collapses during this sequence and leaves Stop in the island. The overlay is excluded from autosave, undo and exports. The client commits files and the native edit together after checking the board generation and scene; a cancellation, switch or concurrent edit cannot commit the preview. Reduced-motion and hidden tabs use immediate placement.

Assistant polling reconnects to the same run after a network error or HTTP 502, 503 or 504; it does not issue a second model request. Each status check has a ten-second abort deadline bounded by the remaining three-minute run limit. Stop and board switching abort an in-flight status check and attempt to cancel the run. Other polling errors stop tracking and attempt cancellation. These checks do not guarantee that a provider can cancel an already dispatched request; the initial submission and other unrelated requests do not share the status-check deadline.

For whole-board questions, the client recognizes a single unambiguous linked dataset as board context; source-linked explanations and chart requests can retain its identity. It checks that the set of linked datasets has not changed while the answer is in flight. The server independently resolves ownership and hashes. Explicit selections and boards with multiple datasets retain their selection behavior.

New diagram nodes retain their semantic node kind. The response offers a separate Read key idea action when an interpretation node exists; it closes the companion and fits that node so its complete text can be read. View diagram retains the overview and uses more of the available viewport.

Diagram connections spanning rows route around the outside of intervening cards when their direct path would cross one. Separate edges receive distinct lanes; the geometry remains editable as native bound arrows.

During an assistant request, Watch on board collapses the panel and returns keyboard focus to the top control while work continues. The control says Working until the request finishes, then View update until opened; reopening while running still exposes Stop. Switching documents clears this transient watch state.

More → Add web link places an editable native card with the user-provided title, domain and HTTP(S) link. Creating it does not fetch the destination. Embedded credentials and non-web schemes are rejected; the card is a reference rather than an extracted or independently verified source. It can be used on a saved investigation or a browser-only scratch board.

More → Add drawing imports a bounded `.excalidraw` scene beside existing objects as one scene update. Object, group, frame, connector and embedded-file identifiers are remapped; a scene without an existing frame gets an Imported drawing frame. Missing references or images are rejected before the board changes. Imported FireAtlas-specific bindings are removed because a plain Excalidraw file does not carry the owned evidence package; ordinary external web links remain. Existing imported frames are retained rather than nested inside another frame. Saved boards retain their existing file and object limits, and board switches during file reading cancel the addition.

Assistant explanations use a locked decorative background sized to their wrapped content, a distinct editable title and interpretation, and a source-values label above separately editable, source-linked claims. Long uninterrupted words wrap within the card. The background and label do not carry scientific claims.

Assistant claim displays omit the generic CSV unit placeholder “reported value” for readability while preserving it in saved claim metadata. Actual units remain visible in the assistant, explanation and challenge views.

After an automatically placed assistant diagram, View diagram closes the panel and focuses only its diagram nodes, excluding the potentially lengthy explanation and other results. Below 600 pixels it focuses the first node for legibility; users can pan to the other nodes. When an explanation was added with the diagram, View explanation focuses its main editable text separately. Reopening the assistant retains the current answer. Deleted elements and board switches are checked before focusing.

## Scientific views and ideation on Investigation

The always-visible top Ask AI dock works before a named board exists through `WhiteboardAssistantWelcome`. Its welcome opens board creation or the saved-board picker; entering this way opens the companion and focuses the question. The expanded companion offers evidence guidance and real-view starters. Ctrl/Cmd+Enter submits; Escape returns focus to the launcher.

Completed scientific data views are verified against durable snapshot hashes, rendered from server figures, and embedded as portable images with source references and caption dates. Figures can be moved/resized; scientific values stay frozen in the linked evidence. Each result has its own focus control. Requested relationships create neutral native bound arrows, and requested pins create editable amber notes retaining the view bindings. Placement reads the latest scene after asynchronous rendering so concurrent manual drawings/movements survive. Additions use one undoable scene update and an actual placement cue. A hash change or board switch prevents late placement. Real maps are not replaced by prose diagrams; notes and conceptual diagrams remain native editable elements. Current automated UI checks mock network/rasterization and do not establish on-screen acceptance.

Default Explain asks for the main pattern and next investigation rather than a list of limitations. Companion source notes use a closed details control; scientific receipts and saved evidence retain their full metadata. Map/factor starters ask for useful comparisons rather than boilerplate caveats. Existing board text is not rewritten by this communication pass.

Heatmap catalog answers expose each dated saved study as a separate Add heatmap button. The normal assistant request, native placement animation and verified receipt pipeline handles the selected action. Live country responses render a source-linked coordinate plot colored by measured channel brightness. The answer card distinguishes the model name, saved data, live FIRMS data and the fallback state where model wording is unavailable.

A country heatmap request places the `firms-country-heatmap` preview from its verified live receipt. The figure outlines the requested country and colors occupied display cells by their recorded detection counts. The coordinate reading map remains a separate figure, colored by channel brightness.

An archived heatmap may provide a case title in the assistant view response. The title is painted above the source and date on the saved board image and carried into its editable caption.

A historical regional FIRMS preview plots the verified search window, its locality reference and returned counts for each queried product. When every product returns an empty CSV, the map has no heat cells and still remains editable and source-linked. Its editable caption links to the incident report.

Assistant map previews use one portable figure with a title, date, map, metrics panel, legend and source line. Space Grotesk and DM Sans are loaded from the existing static fonts and painted into the PNG. New maps are a single board image with the saved receipt metadata and any reference link attached directly. The typed caption outside the figure is no longer needed for new placements.

The assistant accepts multiple typed reading figures in one response and places them in one undoable board edit. Two compatible views can fit together in the canvas. The reading catalog includes live maps, calendars, raw rows, source inventory, published satellite comparisons, export status, persistence, measured factors and evaluated monthly comparability.

Investigation places project navigation behind the disclosure in the board toolbar, leaving the full viewport height for the shell. New regional and country heat figures use the same portable heat compositor as archived fire cases. Supplied vegetation or terrain takes priority, followed by a NASA GIBS shaded-relief tile and Explore’s attributed reference basemap. Existing embedded board figures retain their original pixels.

## Comparison workbench (2026-11-12)

The companion's Peak days × 3 starter requests one peak UTC day in each of the last three completed years; Compare maps uses selected eligible saved FIRMS maps. `comparisonBoard.ts` places up to six heatmaps in aligned native frames with one shared scale, editable source-bound rings/arrows, exact baseline differences, seven-day weather rows and a clearly marked AI interpretation. Hypothesis prompts remain distinct from checked measurements. Each panel has a focus control. The entire composition is a single guarded reversible placement retaining pre-existing drawing content; late responses after a source/board change are rejected. Add scientific views retries from preserved evidence without repeating acquisition and retains the interpretation.

Open source resolves `comparisonPanel` through the owned checked receipt, shows that panel's date, full ranking search span, product, ties, weather point/window/source and corresponding facts. Download full evidence retains all panel/search/weather data as JSON. `comparisonEvidence.ts` refuses invalid panel identity and only exposes HTTPS Open-Meteo archive query links. Native packages and HTML reports retain frozen evidence and source references. Model interpretation and edited canvas labels remain authored text. Map backgrounds use each comparison panel's own geographic scope; missing background/weather has an explicit fallback.

Build the whiteboard into an isolated Vite directory and merge it using `scripts/refresh_whiteboard_assets.py`; retain Studio assets and pre-existing deletions. After a refresh, update the whiteboard entry URL revision in both `fireatlas/static/studio-excalidraw.html` and `site/studio-excalidraw.html`, because existing browser caches can retain the old entry. This does not publish a hosted deployment.

Annual comparison headers and the source inspector explicitly name the ranking metric (occupied 1 km cells or returned detection records). The map's occupied-cell quantity and baseline-cell differences retain their own units when the scientist chooses detection-ranked peak days. Headers wrap for single-column comparisons.

## Scientific field-lab companion (2026-11-13)

`WhiteboardAssistant.tsx` retains the cream/sage/forest language with a dark forest lab header and composer-first order. Solo investigation is the default; Research team explicitly opts into three additional specialist calls and discloses its $0.02 extra ceiling. The mode resets on board changes, and requests retain the existing run/source/revision/cancellation guards. Actual server stage events describe work; no fabricated percentage or completed specialist is shown. Current work and answers precede secondary starters.

`ResearchTeamPanel.tsx` shows completed, partial and unavailable outcomes, proposed tests, exact source links and reported/unknown usage. Recent conversation exposes saved public references and specialist reports after reopening. Reference pinning keeps source URLs attached to editable native board objects. Panel styles live in `investigation.css`; narrow screens retain the composer and scrollable controls, with reduced-motion CSS for status/canvas cues. Automated component checks do not establish complete keyboard, motion, zoom or hosted acceptance.

`ResearchBriefPanel.tsx` presents structured public research as Research context, Working hypothesis and Proposed test, with exact reference handles and original links. It labels the scope as AI proposals based on metadata. The same component appears in saved conversation; native exports retain its fields. Ordinary answers still use the existing view, and scientific measurement claims remain separate. Styles reuse the lab's cream/forest palette and numbered reading sequence, with narrow wrapping.

`PublicReadingPanel.tsx` exposes expandable original article passages, abstract-only and unavailable states with section/location, shortening and reported-license cues. Current and saved answers retain them; Read original methods submits the exact displayed DOI alongside its handle. Structured brief scope changes to selected original passages only when actual passages exist. React renders publication text as text.

`useInvestigationBoard` skips recovery-draft writes for unchanged scenes when no edit is queued/in flight and no text-edit transition is pending. Genuine unsaved edits still attempt recovery storage and server saving; existing drafts are preserved. A no-op retry clears only a stale draft-full warning, not a server/conflict error. `ToolbarMenu.tsx` positions the fixed More menu below its actual toggle and follows toolbar resizing/scrolling, including wrapped save statuses.
