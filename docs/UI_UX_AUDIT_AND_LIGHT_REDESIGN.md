# Website UI audit and light redesign specification

**Date:** 3 October 2026 · **Project:** Ignis-Atlassia / FireAtlas

**Deliverable:** audit of the actual website and an implementation-ready visual redesign specification. The companion [visual proposal](UI_UX_LIGHT_DIRECTION.html) shows the proposed colors, hierarchy, legends, and page personalities with explicitly synthetic illustrations. The redesign is now implemented in the actual website. See the [implementation and screenshot review](UI_Review/README.md); the earlier proposal remains a synthetic design reference.

**Visual references:** [desktop Atlas proposal](UI_UX_LIGHT_DIRECTION.png), [mobile proposal](UI_UX_LIGHT_DIRECTION_MOBILE.png), and [Assistant proposal](UI_UX_LIGHT_ASSISTANT.png). The HTML includes Atlas, Replay, Assistant, and Palette views in one file. Its sketch controls only illustrate layout and state changes. Desktop/mobile checks found no document-wide overflow, script errors, or network requests; unknown sample days display dashes rather than invented zero counts.

## 1. Audit scope and evidence

Reviewed the live local website, its HTML/CSS, and the JavaScript that renders its maps, charts, calendars, evidence, and assistant overlays. Primary source files are in `fireatlas/static/`; `site/` is the generated static export. The earlier UI handoff files are not the target of this redesign.

The audit covers Overview, Atlas, Replay, Research, Candidates, Exposure, Validation, Data, Method, Review, Assistant, and the standalone terrain viewer. The legacy `earth.html` and `Globe.html` interfaces were also checked in source. Desktop and mobile captures on 2 October used 1440 × 1000 and 390 × 844 viewports; source verification continued on 3 October. Loaded observation views were inspected where available; several API sections were still loading during the capture window, so their loading appearance and rendering code were reviewed. That does not establish that their APIs are broken. The captured primary pages showed no document-wide horizontal overflow or JavaScript page errors; that does not cover every interaction or hidden state. The local preview service later changed its route behavior; earlier computed-style findings were therefore checked against the unchanged source rather than represented as a new live capture.

### The most consequential findings

| Finding | Evidence | Consequence |
| --- | --- | --- |
| Maps are buried below setup and explanations | Atlas map starts approximately 1,976 px down the mobile document; Candidates approximately 1,663 px. Research comparison chart approximately 2,077 px. | Users must scroll through several screens before reaching the reason they opened the page. |
| Essential labels are extremely small | Globe source labels include 7–9 px text; many captions, statuses, and diagram labels are 8–11 px. | Dates, units, and source distinctions become harder to read than decorative headings. |
| At least one actual text contrast failure is severe | The Data page NOAA link computes to cyan text on an orange surface, approximately 1.28:1, despite the ink color in its page stylesheet. | Competing shared styles override a locally sensible button design. |
| Legends do not consistently match their graphics | Method's generated VIIRS dots are gold while VIIRS elsewhere is cyan. Candidates use neutral markers and green selection beside a sensor legend. | Users cannot carry an interpretation safely between pages. |
| The assistant workflow is poorly ordered on mobile | The archive appears before the map; the study map heading is around 971 px down and the conversation heading around 2,761 px. | Asking a question and seeing its mapped evidence feel disconnected. |
| Scientific scopes are easy to confuse | Atlas has selected-area and regional-history controls; Validation has a study context plus an independently selected named evidence case. | A result or evidence download can be assumed to describe the wrong study. |

These are problems in hierarchy, interaction, and scientific communication as well as color. The redesign needs to address all four.

## 2. Chosen visual direction

Use **warm ivory, white work surfaces, deep ink, and strong cobalt actions**. Keep the existing dark Earth and satellite scene as the landing page's visual centerpiece. Maps and real terrain can remain dark or photographic within a light surrounding interface.

Use saturated accents selectively: actions, active navigation, headings, small section markers, and restrained tinted panels. Large reading areas remain calm. Page personality comes mainly from composition and task layout.

### Core tokens

| Role | Color | Usage |
| --- | --- | --- |
| Page canvas | `#F7F5EF` | Warm ivory background |
| Work surface | `#FFFFFF` | Maps' surrounding controls, tables, forms, conversation |
| Main text | `#142C3E` | Headings, body copy, values |
| Secondary text | `#4D6575` | Explanations, metadata, labels |
| Primary / focus / selection | `#2457D6` | Primary buttons, active navigation, focus and selection outline |
| Primary hover | `#1C46B3` | Hover or pressed primary buttons |
| Teal accent | `#006D77` | Atlas and assistant section accents |
| Coral accent | `#C13D29` | Replay section accents |
| Violet accent | `#6650BE` | Method diagrams and editorial markers |
| Sunflower decoration | `#FDBE4C` | Small decorative fills with ink text |
| Decorative separator | `#D8DED8` | Nonessential dividers between already distinct surfaces |
| Interactive boundary | `#7A8E9E` | Input boundaries or controls that need a visible outline |
| Pale cobalt | `#EAF0FF` | Selected controls and compact study panels |
| Pale coral | `#FFF0E8` | Replay explanatory highlights |
| Pale mint | `#E7F5EE` | Positive status surfaces |
| Pale violet | `#F1EDFF` | Method and evidence details |

Calculated foreground/background pairs: ink on white **14.39:1**, secondary text on white **6.12:1**, white on cobalt **6.16:1**, cobalt on ivory **5.65:1**, teal on ivory **5.58:1**, coral on ivory **4.86:1**. The interactive boundary is approximately **3.39:1** against white and **3.11:1** against ivory. These ratios apply to the listed pairs, not every possible opacity, hover state, raster background, or tint.

Target at least 4.5:1 for ordinary text and 3:1 for qualifying large text, following [W3C's text contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html). Meaningful control and graphic boundaries need suitable 3:1 contrast against adjacent colors; decorative borders do not replace an accessible interactive boundary. See [W3C's non-text contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html).

### Scientific meaning remains consistent

| Meaning | Color | Additional encoding |
| --- | --- | --- |
| MODIS | `#A75500` | Circle + explicit MODIS text |
| VIIRS | `#006E86` | Diamond + explicit VIIRS/platform text |
| Shared observed cell | `#287446` | Square + “Shared cell” text |
| Complete export | `#166448` on pale mint | Check icon + “Complete export” |
| Partial export | `#9B5F09` on `#FFF3D6` | One restrained hatch + “Partial export” |
| Unknown/unavailable | `#53697A` on `#EEF1F5` | Dashed outline + explicit status |
| Error | `#B73538` on `#FDEBEB` | Error icon + actionable message |
| Selected candidate/sample | Cobalt outline + white halo | Label and selected state; retain its underlying source meaning |
| Heat magnitude | `#FFF2B2 → #FEC44F → #FC8D3C → #E34A33 → #B30000` | Continuous ramp + metric name, unit, and actual scale explanation |

Page accents never recolor source identities. Real NDVI, satellite imagery, land-cover classes, and terrain textures retain their scientific or geographic colors. The heat ramp does not represent temperature unless a supported temperature product is actually being displayed.

## 3. Shared interface specification

### Navigation and study context

- One user-facing brand: **Ignis-Atlassia**. Preserve FireAtlas in software/schema names and technical provenance.
- Shared navigation: Overview, Atlas, Fire replay, Research lab, Data sources, Assistant, and a clearly active Methods menu containing Method and Review.
- Research tabs use task names consistently: Sensor overlap, Candidates, Exposure, Validation. Remove decorative numbering; keep numbers for the genuine Exposure steps.
- Each analytical page has one compact study strip showing location/AOI, UTC dates, and selected source. Show the currently applied settings; edits go into an adjacent disclosure or mobile sheet.
- Preserve canonical study URL parameters and existing context handoff. Evidence-case selectors must state their own scope when they are independent of the selected study.
- Use one fixed Assistant launcher that opens the expanded assistant workspace directly, retaining the earlier one-click request. Compact chat can be a mode inside that workspace. Preserve the active study, conversation, and draft question.

### Typography, controls, and spacing

- Load the existing local DM Sans body and Space Grotesk heading fonts through one shared font definition.
- Body: 16 px. Control labels: 14 px. Secondary captions: 12–13 px. Tables: 13–14 px. Avoid meaningful labels below 12 px.
- Task page titles: approximately 40–44 px desktop and 30–32 px mobile. One introductory sentence is normally enough.
- Use a spacing scale of 4, 8, 12, 16, 24, 32, and 48 px. Analytical layouts can use a 1440 px maximum; long reading pages should have a narrower text column.
- Primary actions: cobalt with white text. Secondary actions: white with visible boundaries. Tertiary actions: readable text links. Selected and unavailable states must remain distinguishable.
- Design normal action controls for 44 px touch height. This is a design target; WCAG 2.2 AA's minimum target rule is 24 px with specified spacing and other exceptions, not a blanket 44 px requirement. See [W3C's target size guidance](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html).
- Mobile gutters: 16 px. Forms and tables must not force whole-page horizontal scrolling. Large exact-data tables may have a labeled local scroll area.
- Give disclosure summaries, map tools, tabs, dialogs, and menus clear focus indicators. Restoring focus and supporting Escape are part of the assistant/modal behavior.

### Legend hierarchy

Place a compact legend beside the visualization on desktop and immediately above it on mobile:

1. **What is plotted:** actual sources or classes present in that view, with text and shape.
2. **Magnitude, when applicable:** a single ramp, metric name, unit, and scale definition.
3. **Data status:** complete, partial, or unknown at the scope actually supported by the data.

Keep one short reading rule near the visualization. Put extended scientific limitations and calculation detail in an expandable panel. Do not add legend entries for encodings that the visualization does not use.

**Scale distinction to preserve:** Replay currently uses frame-relative heat, while the Assistant map fixes its heat normalization across the selected study for each source/scope. Use a coherent visual language while labeling each actual scale honestly. This visual redesign must not silently change kernels, normalizations, scientific counts, or denominators.

### Loading, empty results, and failure states

- Show a compact loading state in the affected result area, with the applied study context still readable.
- If a request is delayed, explain that it is still pending; offer Retry after a bounded timeout. Cancel superseded requests or ignore their late results.
- Distinguish “no records in a complete export” from “export incomplete,” “coverage unknown,” “service unavailable,” and “dataset unavailable.”
- Never replace a failed or missing response with zero.
- Static pages use bundled results where supported and show a clear local-service requirement for unavailable analytical APIs.
- A source-export status is not a claim that the satellite observed every location. Keep the source-specific status beside the result.

### Source references for consequential findings

- Data link cascade: `fireatlas/static/data.css:2` and `fireatlas/static/workspace.css:80`.
- Validation gate labels and unused validity response: `fireatlas/static/research-deep.js:104` and `fireatlas/static/research-deep.js:134`; independent study/case selectors in `research-validation.html`.
- Reviewer-attested JSON rather than cryptographic signing: `fireatlas/static/review.js:144` and the module description in `fireatlas/mask_review.py`.
- Frame-relative Replay normalization: `fireatlas/static/replay.js:159` and its metric explanation. Study-wide Assistant maxima: `fireatlas/static/assistant-map.js:18`.
- The global layering and literal generated colors require inspecting the shared CSS and the corresponding page renderers together.

## 4. Global inconsistency register

**Priority:** P0 = meaning/accessibility or scope risk; P1 = major workflow/readability; P2 = coherence and finishing.

| ID | Priority | Current finding | Required change |
| --- | --- | --- | --- |
| G01 | P1 | `styles.css`, `design.css`, page CSS, `lab.css`, `workspace.css`, and `assistant.css` overlap with conflicting tokens and literal colors. | Define one shared token/component system and migrate each page into it. Retire superseded rules instead of appending another blanket override layer. |
| G02 | P1 | Text and controls inherit different fonts; Method font aliases and Review fallback typography differ. | Load shared local fonts once and apply the same body, heading, and numeric styles. |
| G03 | P0 | Essential metadata and visual labels are often 8–11 px. | Establish readable minimums; shorten labels rather than shrinking them. |
| G04 | P1 | Panels and controls blend together. Existing panel/control boundary pairs include approximately 1.55:1 and 2.45:1 contrast. | White surfaces, visible control boundaries, and stronger text hierarchy. Audit the actual computed styles after migration. |
| G05 | P1 | Primary actions and active states alternate among cyan, peach, orange, sage, and white. | Cobalt primary action and outline selection across pages; page accents remain decorative. |
| G06 | P0 | Sensor colors vary between charts, diagrams, maps, and legends. | One source token and symbol contract, including JavaScript-generated SVG and map renderers. |
| G07 | P0 | Partial and unknown states use unrelated hatch colors and border styles. | One status component with consistent text, icon, and pattern; preserve meaningful distinctions. |
| G08 | P1 | Oversized introductions, workflow rails, and context cards stack before results. | Compact title and study strip, then the primary map/chart. |
| G09 | P1 | All analytical pages repeat the same dark hero and card arrangement. | Task-specific compositions with shared components. |
| G10 | P1 | Some mobile research tabs hide the active destination outside the initial horizontal viewport. | Keep the current task visible and support keyboard navigation. Use a compact task selector when needed. |
| G11 | P1 | Two fixed assistant buttons compete for attention and mobile map space. | One launcher, expanded workspace first, secondary modes inside it. |
| G12 | P2 | Methods dropdown has no clear parent active state when Method/Review is current. | Active parent and active child states, keyboard and screen-reader support. |
| G13 | P2 | Ignis-Atlassia, FireAtlas, and Jarvis naming appears at different hierarchy levels. | Consistent product name; label the assistant by function and technical provenance separately. |
| G14 | P1 | Similar caveats appear in introductions, legends, result panels, and footers. | One local reading rule plus one deeper limitation/provenance disclosure per workflow. |
| G15 | P1 | SDK and map controls have their own dark or tiny visual styles. | Apply readable shared white map chrome and focus styles; use a neutral light base map where geographic imagery is absent. |

## 5. Page-by-page audit and redesign

### Overview — `/`

**Personality:** an immersive dark globe within a bright, confident website shell; a concise ivory section below it. Preserve the existing Earth model, satellite orbit, layers, controls, location search, dates, signals, wildfire toggle, and evidence interactions.

**Proposed order:** shared header → existing globe hero → short reading rule → three compact archive/context readouts → workspace destinations → one limitations disclosure.

| ID | Priority | Finding | Change / content treatment |
| --- | --- | --- | --- |
| L01 | P0 | Globe source captions and orbital labels are exceptionally small. | Raise meaningful captions to 12 px or more; keep decorative orbital text subordinate. |
| L02 | P1 | Observation caveats recur in hero copy, scope text, globe caption, lower introduction, reading rule, limitation card, and footer. | Keep the globe's short interpretation rule and one full limitation disclosure; remove the repeated paraphrases. |
| L03 | P1 | The lower section repeats a large marketing-style heading instead of giving a quick next action. | Use compact readouts and a clear workspace chooser. |
| L04 | P2 | Card footer labels repeat titles; “Each page has one purpose” explains the site architecture instead of helping the visitor. | Remove generic filler; use concrete actions such as “Compare daily sensor counts.” |
| L05 | P1 | Light redesign could accidentally affect the iframe/canvas, reveal styles, or controls. | Scope light shell changes explicitly; verify first-load globe, orbit, zoom, reset, search, and overlays independently. |

Keep real data notices and NASA attribution. A loading capture alone is not evidence of a globe regression.

### Atlas — `/atlas.html`

**Personality:** a cartographic workspace. Teal section accents, a large geographic canvas, compact white controls, and a day-detail inspector.

**Desktop order:** title + study strip → map/layer toolbar → map and date inspector → adjacent daily playback → selected-study calendar → exports/evidence.

**Mobile order:** title + compact study selector → map legend → map → selected-day/playback strip → date detail → calendar. Advanced settings open in a sheet.

| ID | Priority | Finding | Change / content treatment |
| --- | --- | --- | --- |
| A01 | P1 | Map begins around 1,211 px on desktop and 1,976 px on mobile. | Move map directly after the compact context strip. |
| A02 | P1 | A prominent Replay invitation precedes the Atlas task, while introductory and navigation panels duplicate explanation. | Make Replay a contextual action after the user selects a study/day; shorten the introduction. |
| A03 | P0 | Selected-AOI results and broader regional history have separate controls and scopes. | Use clearly labeled **Selected study / Regional history** tabs; keep each applied scope visible. |
| A04 | P0 | Legend combines sources, magnitude, estimate provenance, completeness, and outages into one dense block. | Split observation meaning/magnitude from data status; show only entries used by the active view. |
| A05 | P1 | Thirty-one small day buttons, a slider, playback, and repeated instructions compete. | Use one primary timeline and accessible date picker; open exact date detail on selection. |
| A06 | P0 | Regional history has up to 366 columns in a roughly 900 px overview; daily targets are too narrow. | Make the annual strip an overview. Selecting a month opens readable date cells and a table alternative. |
| A07 | P1 | Expanded source tables duplicate the comparison workflow on Research. | Compact sensor summary with an expandable exact table and contextual Research link. |
| A08 | P1 | Unknown coverage cards and four mixed-purpose metrics compete with the map. | Put status beside the current result; separate calibration/timing context from headline counts. |
| A09 | P1 | Multiple export groups use differing names and scopes. | One export menu per active scope, with content and file type named. |
| A10 | P2 | “Critical dates,” responder wording, repeated source cards, and defensive fabrication statements distract. | Use “Peak observed window” and “Historical study summary”; move methods/provenance into one disclosure. |

Retain default NDVI context, land-cover/hotspot layers, unavailable weather labeling, AOI selection, daily observations, calendar completeness, and study handoff. Do not use a lighter UI to recolor the NDVI raster.

### Fire replay — `/replay.html`

**Personality:** a focused landscape viewer with coral section markers, large terrain/imagery, and an integrated playback rail. White controls frame the scene.

**Proposed order:** named case/date/source strip → context and view controls → map + immediate playback rail → three source/count summaries → records and status tabs → method details.

| ID | Priority | Finding | Change / content treatment |
| --- | --- | --- | --- |
| R01 | P1 | Large setup and interpretation panels precede the actual scene. | Compact case strip and grouped settings; keep one observation/heat interpretation sentence. |
| R02 | P1 | Three legend blocks occupy space before the map; headings and helpers are very small. | Compact legible map-edge legend with actual metric and scale. |
| R03 | P1 | Timeline is below a tall map rather than at its edge. | Dock selected UTC date, play/pause, scrubber, and export at the map's bottom edge; keep it usable in flat and relief modes. |
| R04 | P0 | Heat colors are frame-relative; changing metrics can be misread as comparing absolute intensity. | Keep the frame-relative scale label visible and change the unit/help with the metric. Do not alter normalization in a visual refactor. |
| R05 | P1 | Sensor, heat, context, perspective, fit, and explanatory controls are scattered. | Group **Observations / Landscape / View**; use a mobile settings sheet instead of a long first screen. |
| R06 | P1 | Sensor counts, union cell totals, records, and source-status caveats repeat. | One labeled count strip; distinct **Records / Data status** panels with traceable details. |

Keep source-specific FRP restrictions, record counts versus union cells, unknown/partial dates, real terrain availability, fallback behavior, and CSV export. Real relief remains a geographic surface; the overlay remains observations.

### Scientific assistant — `/assistant.html` and expanded chat

**Personality:** a bright investigation workspace. A geographic canvas and conversation form the primary pair; evidence appears where the question needs it.

**Desktop:** compact study bar → map (about two-thirds of the main width) + conversation → optional evidence drawer. Archive selection is a drawer, not a permanently competing third pane.

**Mobile:** compact study selector → **Map / Chat / Evidence** tabs. Keep the query composer reachable within Chat and make “Show on map” switch directly to the mapped evidence.

| ID | Priority | Finding | Change / content treatment |
| --- | --- | --- | --- |
| J01 | P1 | Three desktop panes squeeze labels and controls; mobile archive comes before the map/chat. | Use two primary panes and a collapsible archive; use mobile task tabs. |
| J02 | P1 | Source, mode, split, locate, inspect, pin, polygon, landscape, month, speed, and export tools are all similarly prominent. | Keep current-study selection, question, and map inspection primary. Group annotation tools; put advanced replay/query controls behind a labeled disclosure. |
| J03 | P1 | Legend and source explanation recur on map, timeline, and count cards. | One map legend; compact source chips elsewhere with exact evidence accessible on demand. |
| J04 | P1 | Charcoal/sage styling and smaller headings differ from the shared app; expanded chat has its own styles again. | Apply the same fonts, surface tokens, status vocabulary, figure cards, and action hierarchy to both presentations. |
| J05 | P0 | Model/service readiness and archive availability can appear as one overall readiness impression. | Show **AI connection** and **Observation archive** as distinct statuses with specific failure messages. |
| J06 | P1 | Questions, explanatory examples, network descriptions, and task suggestions compete with active work. | Show two or three useful starters when empty; hide them after a conversation begins. Describe capabilities through named actions and evidence. |
| J07 | P0 | Heat scaling differs from Replay and can be misread if the redesign standardizes only the ramp. | Label study-wide source/scope scale; show date, metric, sources, units, and caveat on generated figures and annotations. |

Preserve evidence-backed answers, map observations, sensor separation, annotation tools, page navigation, graphs/diagrams, figure capture, and conversation state. Surface source links or evidence details beneath the claim they support. A failed tool call needs a useful recovery action, not internal JSON-pointer wording in the conversation.

### Research overview — `/research.html`

**Personality:** a clear comparison report: aligned source columns, a large overlap chart, and exact values available underneath.

**Proposed order:** compact study form → three headline values → source legend + overlap chart → daily data disclosure → related workflows.

| ID | Priority | Finding | Change / content treatment |
| --- | --- | --- | --- |
| O01 | P1 | Mobile chart starts around 2,077 px down the document. | Put the chart immediately after a compact study strip and values. |
| O02 | P1 | Candidate distance/gap settings consume the overlap form although their role belongs mainly to grouping. | Move them to **Candidate settings** while preserving context handoff. |
| O03 | P0 | Daily completeness legend may imply detail when only an aggregated month status is available. | Label the supported status scope; do not manufacture daily complete/partial states. |
| O04 | P1 | Hardcoded SVG colors and small labels bypass shared design styles. | Render through shared source/ink tokens; keep numeric labels readable and expose a data table. |
| O05 | P1 | Exact table, candidate totals, workflow rail, and destination cards repeat competing paths. | Three meaningful headline values, expandable exact table, and a single compact related-actions row. |

Keep API overlap results authoritative. Shared cells and the distinct union need different wording; candidate groups are not confirmed incidents.

### Candidate tracking — `/research-candidates.html`

**Personality:** a geographic explorer with a readable result list and a selected-group inspector. Teal layout accents; neutral group markers with cobalt selection.

**Proposed order:** compact applied study → map/list workspace → selected-group evidence → accessible membership table.

| ID | Priority | Finding | Change / content treatment |
| --- | --- | --- | --- |
| C01 | P1 | Mobile map starts around 1,663 px; horizontal 245 px candidate cards hide list context. | Map first; compact candidate picker and visible selected-position/count on mobile. |
| C02 | P0 | Neutral points and green selected markers do not match the sensor legend. | Neutral candidate identity; cobalt selected halo; source symbols/chips only where sensor identity is actually shown. |
| C03 | P1 | Group rerendering/sorting can repeatedly fit the map and move the camera. | Preserve viewport while sorting; fit on explicit action or deliberate group selection. |
| C04 | P1 | Raw group identifiers lead while date range, detected days, cell-days, and sources are harder to scan. | Human-readable group label and date range first; aligned useful columns; raw IDs in evidence details. |
| C05 | P0 | Buttons use `role=listitem`, obscuring native button semantics. | A semantic list/table containing ordinary focusable buttons; announce selection and updated evidence. |
| C06 | P0 | NDVI requested date/effective composite, availability, and loading are not equally clear. | Show the actual composite note and layer status close to the layer control; no promise of instantaneous vegetation. |

Retain grouping algorithm and exact membership, sortable list, NDVI, map-to-evidence selection, and the connected-samples limitation.

### Observation exposure — `/research-exposure.html`

**Personality:** a genuine three-step form with a readable result preview. Distinct stages rather than an entire page of equivalent cards.

**Steps:** 1. Match study → 2. Add coverage mask → 3. Review source rates.

| ID | Priority | Finding | Change / content treatment |
| --- | --- | --- | --- |
| E01 | P1 | Step headings repeat and all stages appear equally active before a mask exists. | One step indicator and a dominant current action. |
| E02 | P0 | Legend covers fewer states than the mask workflow supports. | Explicit **Unavailable / Synthetic demo / User supplied, unvalidated / Validated** states with text and distinct treatment. |
| E03 | P0 | Green detected-in-mask meaning conflicts with shared-cell green. | Use counts/text to show mask inclusion; reserve source tokens for source meaning. |
| E04 | P1 | Upload, example, template, unavailable download, and schema instructions compete. | Upload primary; example/template secondary; accepted-mask download appears after a mask exists. Schema in a detail panel. |
| E05 | P1 | Several no-mask notices and result placeholders repeat the same state. | One actionable empty state: add a matching mask to obtain a denominator. |
| E06 | P0 | Mask context, validation, numerator/denominator, and reupload instruction need a clear relationship. | Keep source, numerator, denominator, unit, and mask status beside every displayed rate. Show reupload guidance near the upload when context handoff requires it. |

Keep `fireatlas-coverage-v1` validation, synthetic labeling, and user-supplied status rules. FIRMS detections alone cannot establish observation coverage.

### Validation and limits — `/research-validation.html`

**Personality:** an evidence register. Clear status rows, supported claims, remaining evidence requirements, and named downloadable artifacts.

**Proposed order:** study gate context → gate register → independent named evidence-case selector → check/result/download actions → full limitations.

| ID | Priority | Finding | Change / content treatment |
| --- | --- | --- | --- |
| V01 | P0 | AOI/month gates and named Park/Grove evidence bundle can describe different scopes without a strong separation. | Explicit labels for **Selected study gates** and **Named case evidence**, or intentionally match them with a visible confirmation. |
| V02 | P0 | Named evidence selector comes after its action cards. | Put the selector and applied case before check, ZIP, and Review actions. |
| V03 | P1 | Gate cards share gray/dashed treatment despite different readiness meanings. | Available, partial, not available, and external evidence needed each get clear text/icon/status treatment. |
| V04 | P1 | Check and refresh duplicate their apparent job; JSON/ZIP/review cards look equally primary. | One gate refresh action; named evidence action group showing result type and scope. |
| V05 | P2 | API-preservation prose is visible to scientists, while supported claims are repeated elsewhere. | Remove implementation prose; concise supported-claim list with expandable requirements and Method links. |
| V06 | P0 | `research-deep.js` parses the validity response but does not use its body to present the evidence-case gate outcomes; “Evidence loaded” reflects HTTP success. | Render the actual report outcomes and missing evidence. Distinguish a successful fetch from an analytical check or passed validation. |
| V07 | P0 | Broad unavailable cards can be read as case-specific findings; “Calibration” conflates physical sensor sensitivity with descriptive count scaling. | Qualify the gate as **Sensor sensitivity calibration**; identify requirement cards as general requirements and descriptive scaling as a separate capability. |
| V08 | P1 | “Run analytical check” opens raw JSON as the main result experience. | Show an in-page case-scoped result summary with exact JSON available as a secondary inspect/download action. |

Preserve validity/check/export APIs and independent-evidence requirements. A successful manifest check is not a validated spread model.

### Data sources — `/data.html`

**Personality:** a source catalog and archive ledger. Human-readable records, filters, status, and concise import actions.

**Proposed order:** source/region summary → archive coverage ledger → catalog/download table → import workflow → documentation/provenance details.

| ID | Priority | Finding | Change / content treatment |
| --- | --- | --- | --- |
| D01 | P0 | NOAA action link's computed cyan-on-orange text is approximately 1.28:1. | Use shared cobalt/white button or ink on a suitable pale surface; verify computed cascade, not only `data.css`. |
| D02 | P1 | Raw source IDs lead labels and counts repeat across banners, cards, and table rows. | Human-readable source/platform labels; IDs secondary; one count per applicable scope. |
| D03 | P0 | “Verified archives” can encompass reconstructed or unverified coverage. | Rename to **Archive coverage** and label each verification/export state honestly. |
| D04 | P1 | Loading can persist without a visible delay explanation, timeout, or retry action. | Bounded delayed/unavailable states and Retry; preserve unknown status. A short loading capture alone does not prove an API fault. |
| D05 | P1 | Long reference, recipe, calibration, native-bundle, and acknowledgment sections crowd the catalog. | Searchable catalog columns for purpose, format, region, dates, count, availability; supporting material in disclosures. |
| D06 | P2 | Marketing claims such as “The real fire season, ready to explore” add little operational information. | Precise source descriptions and a direct **Open July 2024 in Atlas** action. |

Keep all source hashes, provenance, verification states, original download links, import feedback, and attribution available. Avoid exposing private local paths as downloadable links.

### Method — `/method.html`

**Personality:** an editorial explanation with a worked example. Violet accents and legible diagrams, not an endless analytics dashboard.

**Proposed order:** what is counted → short pipeline → one worked cell/day union example → recount/exact records → optional detailed evidence tour → calibration and validation links.

| ID | Priority | Finding | Change / content treatment |
| --- | --- | --- | --- |
| M01 | P1 | Page is about 6,686 px tall on desktop and 10,789 px on mobile; five pipeline cards and five tour scenes repeat concepts. | One concise primary explanation and worked example; the long tour becomes optional. |
| M02 | P0 | Generated VIIRS sample dots are gold while the shared source convention is cyan. | Apply shared VIIRS token/symbol in JavaScript and the legend. |
| M03 | P0 | “Joint grid” does not clearly distinguish union from shared overlap. | Use **Distinct cell union** and **Shared cell** exactly where each applies. |
| M04 | P1 | Tiny calendar/provenance labels and dense pseudo-record graphics are hard to inspect. | Readable labels with an accessible exact-record table; retain the reproducibility affordance. |
| M05 | P2 | Jump numbering differs from actual section numbering; calendar link uses an old landing anchor. | Consistent section names and direct canonical Atlas links while retaining compatibility shims. |

Keep equal-area grid interpretation, cell-day deduplication, source-specific counting, recount behavior, exact evidence, and incomplete-source rules.

### Native-mask review — `/review.html`

**Personality:** a precise review workbench: selected sample, original references, measurement form, and progress. Fewer distractions during independent review.

**Proposed order:** evidence case + progress → reviewer details → selected sample and original-product references → blank measurement form → Next pending → review/export status.

| ID | Priority | Finding | Change / content treatment |
| --- | --- | --- | --- |
| Q01 | P0 | Opaque producer IDs and numeric classes are exposed without equally clear product/source/class context. | Human-readable product labels, known original-file references, product-specific class key, coordinate/grid units. |
| Q02 | P0 | “Signed record” implies signing; the workflow creates a reviewer name/time/attestation JSON. | Use **Review record** or **Reviewer attestation** unless cryptographic signatures are implemented and verified. |
| Q03 | P0 | “Ready” and a checkmark near 0/30 can resemble a passed review. | **Pending review**, explicit reviewed/total progress, and final validated status only after the actual gate. |
| Q04 | P1 | Thirty small queue targets overwhelm mobile. | Progress summary, Next pending, and expandable sample queue; preserve direct navigation. |
| Q05 | P1 | A long review form risks losing work on refresh or case changes. | Add explicit per-case draft save/restore and a clear leave/change-case warning when needed. Keep saved notes local and make clearing a draft explicit. |
| Q06 | P0 | Review lacks a skip link; field errors and instructions need stronger local association. | Skip link, semantic field labels, product-class help, error association, and predictable focus after queue navigation. |

Keep original measurement fields blank until the reviewer enters them. Do not prefill independent answers from the producer values. Preserve JSON validation, evidence hash linkage, required fields, and export contract. If a usable original-file link is absent, state that plainly rather than manufacturing a path.

### Terrain viewer and legacy Earth views

**Personality:** a full geographic scene with restrained floating controls and compact back navigation.

| ID | Priority | Finding | Change / content treatment |
| --- | --- | --- | --- |
| T01 | P1 | Standalone terrain uses its own typography, dark controls, and very small attribution/credits. | Shared readable floating controls; legible attribution and acquisition notes. |
| T02 | P0 | Scene focus styling can suppress a visible keyboard indicator. | Restore focus on the scene and its controls; respect reduced motion and preserve SDK keyboard interaction. |
| T03 | P2 | Legacy Earth views use a separate brand/menu skin. | Align control typography and product naming while preserving Earth, atmosphere, city lights, stars, clouds, sun, rotation, and existing model behavior. |

The scene itself stays photographic/dark. The landing page globe and satellite remain protected from redesign.

## 6. Information cleanup inventory

### Remove from normal page flow

- Decorative workflow numbering that does not describe actual steps.
- Repeated observation/perimeter disclaimers after the nearby legend already supplies the rule.
- Repeated card footers that restate the card title.
- “Each page has one purpose,” API-preservation statements, and similar implementation narration.
- Defensive fabrication wording when a concise source/status label would communicate the actual state.
- Repeated large introductions immediately before the primary map/chart.
- Duplicate source legends on the same workspace and duplicate assistant launchers.
- Repeated no-mask notices and unavailable-download cards masquerading as normal actions.
- Marketing phrases on Data that do not tell a scientist what source, period, or record type is available.

### Move into details, an inspector, or a relevant specialist page

- Raw group IDs, source IDs, long hashes, and complete timestamps when the compact view only needs the UTC day.
- Extended calculation prose, schema specifications, import recipes, and native evidence manifests.
- Exact daily rows beneath summary charts; keep them reachable, keyboard usable, and exportable.
- Calibration requirements to Validation, with a concise status link elsewhere.
- Method's long evidence tour and provenance explanations after the worked example.
- Assistant service/tool-network implementation details to diagnostics; keep useful connection/archive status visible.
- Reviewer export contract and schema detail after the immediate review task.

### Keep visible where it changes interpretation or an action

- Applied region/AOI, UTC date range, selected sensor/platform, and cutoff.
- Metric name, unit, heat scale domain, count type, numerator/denominator.
- Export completeness and mask-validation state at the actual supported scope.
- Actual imagery/composite acquisition period and unavailable-layer status.
- A concise observation-versus-perimeter/forecast reading rule.
- Candidate connected-samples caveat, reviewer progress, and independent evidence requirements.
- Attribution and original-record/evidence links.
- Actionable errors and static/local-service limitations.

### Specific copy corrections

| Current wording or pattern | Replacement / placement |
| --- | --- |
| “Joint grid” | “Distinct cell union” or “Shared cell,” according to the actual quantity |
| “Critical dates” | “Peak observed window” |
| “Verified archives” over mixed states | “Archive coverage” + row-level verification/export state |
| “Signed record” | “Review record” / “Reviewer attestation” |
| Ready checkmark beside 0/30 | “Pending review · 0 of 30 reviewed” |
| “These links preserve the existing validity APIs” | Remove; name the evidence case and downloaded artifact instead |
| “No data is being fabricated for missing downloads” | “Select a UTC day to inspect its records and export status.” Missing data still receives its proper status. |
| Raw “Evidence value needs a JSON pointer” error | “The selected evidence could not be attached. Select a result or run the study again.” Keep technical detail in diagnostics. |
| “The real fire season, ready to explore” | “NOAA HMS archive · source coverage and daily records” |

## 7. Page personalities within one coherent system

| Page | Distinct composition | Accent role |
| --- | --- | --- |
| Overview | Existing immersive globe + concise bright destination section | Cobalt actions around the dark scene |
| Atlas | Large map + day inspector + compact calendar | Teal section markers |
| Replay | Landscape canvas + attached playback + exact-date evidence | Coral section markers |
| Research | Comparison report with aligned source values and chart | Cobalt structure; fixed source colors |
| Candidates | Map/list explorer with selected-group inspector | Teal section markers; cobalt selection |
| Exposure | Actual stepped form and result preview | Cobalt step/action; mask status colors |
| Validation | Evidence register and supported-claim rows | Violet editorial markers; fixed status colors |
| Data | Searchable catalog and archive ledger | Teal catalog markers; cobalt actions |
| Method | Narrow reading column + worked diagram/example | Violet editorial markers |
| Review | Focused sample workbench with progress | Cobalt active sample; neutral measurement form |
| Assistant | Map/conversation pair with evidence drawer and figure cards | Teal section markers; cobalt controls |
| Terrain/Earth | Full scene + readable floating chrome | Cobalt focus/actions, dark scene |

Do not give every page a separate sensor palette, font, button family, or navigation model. Personality comes from what the page helps the scientist do.

## 8. Implementation order and source ownership

### Phase 1 — Shared foundation and meaning fixes

1. Introduce shared color/type/spacing tokens and reusable button, status, input, legend, disclosure, navigation, and study-strip components.
2. Resolve the actual CSS cascade on each page. Update literal colors in generated SVG, Leaflet/canvas/ArcGIS chrome, and assistant figures.
3. Correct source meanings, union/shared wording, scope labels, unrendered validity-report outcomes, Data CTA contrast, Review readiness/signing language, and tiny essential labels.
4. Consolidate the assistant launcher and unify expanded chat with the shared shell.

### Phase 2 — Workspaces users interact with most

5. Rebuild Atlas hierarchy: map first, selected-study/regional-history scopes, readable calendars and exports.
6. Rebuild Replay hierarchy: map and playback together, concise settings, actual heat-scale label, records/status details.
7. Rebuild Assistant hierarchy: map/conversation pair, archive drawer, mobile task tabs, integrated annotations and figure evidence.

### Phase 3 — Research workflows

8. Research: compact applied context, three headline values, immediate comparison chart, expandable exact table.
9. Candidates: readable list, stable camera, cobalt selection, accessible evidence table, actual NDVI period/status.
10. Exposure: real steps, explicit mask states, visible denominator and status alongside rates.
11. Validation: explicit study/case scopes, selector before actions, gate register and named artifacts.

### Phase 4 — Evidence pages and landing finishing

12. Data: human-readable searchable catalog, archive coverage ledger, bounded loading/retry states.
13. Method: concise primary explanation, one worked example, optional deep tour.
14. Review: readable measurements, source/class context, progress, per-case drafts, blank independent fields.
15. Overview and standalone scenes: apply bright shell/readable chrome while retaining globe, satellite, scene, and interactions.
16. Remove superseded rules, update static asset registration/export, regenerate `site/`, and verify route/context integrity.

### Main files affected

| Area | Existing source |
| --- | --- |
| Shared style and navigation | `styles.css`, `design.css`, `lab.css`, `workspace.css`, `lab.js`, `workspace.js`, `study-ui.js`, `ui.js` |
| Overview | `index.html`, `landing.css`, `globe.css`, globe frame and viewer interfaces |
| Atlas/calendar | `atlas.html`, `app.js`, `harmonized.css`, calendar/harmonization renderers |
| Replay | `replay.html`, `replay.css`, `replay.js`, `terrain-earth.html` |
| Research | `research*.html`, `research.css`, `research-overview.js`, `research-deep.js` |
| Assistant | `assistant.html`, `assistant.css`, `assistant.js`, `assistant-workspace.js`, `assistant-map.js`, `assistant-views.js`, `assistant-visuals.js` |
| Data/Method/Review | Their HTML/CSS/JS controllers and dynamically generated diagrams |
| Serving/export | `fireatlas/web.py` asset registry and `scripts/export_static.py` |

This can use the existing datasets and credentials. It does not require a new data download or a new model provider. Scientific API response schemas, counts, grouping algorithms, grid definitions, kernels, and coverage rules remain authoritative. Visual changes that would affect a scientific calculation require a separately identified decision.

## 9. Completion checks

- Every primary route loads directly in the local service and is included in the static export.
- The landing globe, satellite, orbit, zoom/reset, location/date/source controls, and evidence interactions still work on first load.
- Shared navigation, fonts, primary actions, focus rings, and sensor meanings are coherent across all pages and assistant modes.
- Actual computed ordinary-text pairs meet the chosen 4.5:1 threshold; important controls/graphics have readable boundaries and non-color distinctions.
- At 1440 px, 1024 px, and 390 px widths, essential text is readable, controls are reachable, and there is no document-wide horizontal overflow.
- For Atlas, Replay, Research, Candidates, and Assistant, target the first main visualization near the top: approximately within 600 px desktop / 750 px mobile after default loaded context. Use the task layout rather than hiding required interpretation to meet the target.
- Map date/source/metric changes coordinate with timeline, records, values, and status. Selection, sorting, fit, and annotations have predictable camera behavior.
- Calendar unknown/partial states remain distinct from complete exports with zero listed records. Annual overview cells are not the only way to select a date.
- Rates show numerator, denominator, unit, mask status, and source completeness. No missing API or mask response becomes zero.
- Validation actions display the evidence case they actually operate on. Review export remains an attestation until actual signing exists.
- Review drafts survive the intended local save/restore path; independent measurements remain blank until entered.
- Expanded assistant opens in one click and retains conversation/study state; graphs and diagrams have readable axes, source labels, dates, units, and evidence context.
- Keyboard users can reach menus, tabs, map alternatives, forms, tables, disclosures, dialogs, and review queues; focus returns after closing a dialog.
- Delayed, timeout, empty, partial, missing-raster, unknown-mask, and static-service states explain the current limitation and useful next action.
- Regenerated `site/` has the same intended visual behavior, valid asset links, and context-preserving links. The original UI handoff folder is not used as the production source.

## 10. Expected improvement

The strongest improvement is reducing the distance between a scientist's question and the corresponding map, exact date, source distinction, and evidence. The new palette makes actions and text legible; the layout changes make the data easier to inspect; scope and status corrections make conclusions safer to interpret. A UI audit alone does not justify a numerical competition-score increase. Judge-visible value follows when these changes are implemented and the workflows can be demonstrated clearly.

## 11. Implementation and screenshot review record

The redesign described above is implemented in the production source under `fireatlas/static/`; the generated `site/` copy was refreshed without changing the existing observation snapshot. The page-by-page visual record is in [UI_Review](UI_Review/README.md), including the actual rendered screenshots and machine-readable results.

The final browser pass loaded Atlas, Research, Candidates, Exposure, Validation, Data, Method, Review, Replay, and Assistant at 1440, 1024, and 390 pixel widths with no page errors or document-wide overflow. Additional checks covered the preserved landing Earth controls, standalone terrain controls, actual 3D Replay, static subdirectory routes, keyboard chart inspection, candidate selection, exposure-mask rejection, review draft persistence, assistant graph rendering, and the static manifest hash. The static release remains dated 2026-10-01; no data was relabeled while refreshing the UI.
