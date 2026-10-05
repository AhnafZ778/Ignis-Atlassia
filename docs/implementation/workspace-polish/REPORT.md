# AI& integration and analytical workspace polish

Prepared 6 October 2026. Published on the existing `r7-work` branch.

Three privately configured AI& credentials authenticated successfully against the real provider's `/v1/models` endpoint (HTTP 200, 13 models each). Credentials remain in the ignored, mode-0600 `.env.assistant`. JARVIS and the dedicated story director share the authenticated integration. Catalog authentication can select another configured credential after a 401/403; uncertain paid inference is never automatically repeated. The separately recorded [story acceptance](../aiand-story/REPORT.md) includes real authoring and a 95-second captioned infographic film. Authentication does not establish every future model or external service's availability.

## Investigate

The study map is now the main visual surface. The heading, archive chooser, geographic context, readouts and timeline use whitespace and section rules instead of nested containers. **Create in Studio** remains a visible primary action. **Send to Canvas** sits after the timeline and the matching record controls; destination selection, presentation presets and export preferences live in a keyboard-accessible disclosure. Source selection, timeline playback, geographic selection, optional 3D, scientific receipts and JARVIS actions retain their existing controllers.

The design uses consistent spacing, limited paragraph width and small-screen layouts informed by [GOV.UK layout guidance](https://design-system.service.gov.uk/styles/layout/), with explicit units, labels and source identification informed by [Carbon's visualization legend guidance](https://www.carbondesignsystem.com/building-blocks/data-visualization/legends). These sources informed presentation decisions; no new design framework or scientific method was added.

## Evidence → Validity

The native audit now leads with its actual case, UTC window, exact bounds, grid identity and recorded status. Inventory, FIRMS/native reconciliation, raw-sample review and independent sign-off are separate visible checks. Whole-area observation opportunity has its own unavailable gate. Native sample counts, descriptive pair counts and confidence disagreements are read from the report, including explicit unavailable states.

Direct actions open the case-specific review form, download its evidence ZIP and reach the separate recount. The counting explanation is optional; the dated interactive evidence walkthrough, original records, hashes, official references and numerical sensitivity evidence remain available. Pending human review is never presented as a passed scientific validation.

The owner's current Park audit contains **3,431 reconciled rows**; the older October 1 static audit contains **3,137**. Both values already existed before this UI change (see before screenshots). This work preserves that distinction rather than rewriting either scientific source to match the other. Park retains 114 processed granules, 1,372,872 native centroid samples, zero of 30 independently reviewed samples and zero of one sign-offs. Grove retains 20 granules and seven reconciled rows. No calibration, counting, eligibility, alias, UTC or completeness rule changed.

## Scope and verification

New styling is loaded only by Investigate and Evidence. The local HTTP server explicitly serves the new stylesheet. The static site was refreshed through `scripts/refresh_static_assets.py`, preserving the original globe/evidence snapshot and analytical namespace. The landing guard still verifies 75 protected asset hashes and both outside-header HTML boundaries.

The browser report records local and `/demo/` project-subpath static checks: case switching, all four native gates, the separate exposure boundary, exact audit scope, case-bound downloads, native recount, Studio visibility, destination chooser, preserved presets, keyboard disclosure and fixed scale across source/day changes. Both pages fit 360, 390 and 768 pixels with no horizontal overflow or browser exceptions. A real Grove **Send to Canvas** handoff requested a destination, persisted the exact July 4 frame, navigated to the arranged board and restored its cards on refresh. The acceptance script removed only its isolated test board. Static Park/Grove method verifiers additionally check incident context, blank review templates and independent analytical recounts without a scientific API.

Screenshots and `browser-report.json` are saved alongside this report. The final machine-readable test inventory is `test-results.json`. Public export, provider availability and paid-call claims are limited to the recorded checks. Independent native review and complete exposure validation remain pending.

## GitHub delivery

Work is delivered in focused commits on `r7-work`: AI&/server integration (`06caf08`), Studio and built assets (`7b73c3e`), analytical layout/validity (`78e1244`), followed by documentation and acceptance evidence. Private credentials, original owner archives, scientific/private databases and runtime intermediates remain ignored. The final remote branch is verified against the local HEAD after pushing; no merge or separate deployment is performed.

Final checks: the complete optional-runtime Python discovery suite passed **370 tests**; Studio passed **76 frontend tests across 17 files**; TypeScript passed; the renderer passed **8 tests**; all **4 map/visual/lifecycle/context test files** passed; **49 JavaScript files** passed syntax checks. Both static native-case verifiers and the local/static responsive browser checks passed. Credentials were checked against 2,670 public candidate files with **zero leaks**, and no candidate exceeded GitHub's 100 MB file limit.
