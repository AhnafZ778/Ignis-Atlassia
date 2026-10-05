# Workflow blank-screen fix

Verified 5 October 2026 against the local scientific service, without model or speech calls.

## Reproduction and change

A fresh Studio session and a completed Park preset initially opened Workflow successfully. Blocking the lazy `WorkflowPanel` JavaScript download reproduced the reported empty page: the browser reported `Failed to fetch dynamically imported module`, React removed every child of `#studio-root`, and all Studio tabs disappeared. No saved workflow in the inspected local store had malformed node types, labels or coordinates.

Workflow now has a dedicated error boundary. A failed module download or editor render preserves the Studio shell, tabs and board. Recovery offers an explicit retry, return to Canvas, and refresh into the current board's Workflow tab. Refresh retains the incoming scientific selection and application subpath and explicitly names the current board, preventing a preset from reverting to the earlier analytical handoff. A rejected React lazy promise is replaced on retry; retries are never automatic.

The diagram has its own boundary, leaving the workflow table, parameter editor, saving and execution available if the renderer cannot initialize. Diagram retries keep the current draft. Controlled diagram nodes are memoized across unrelated renders.

Source and published Studio assets were regenerated with the supported build and static refresh tools. The landing page, scientific calculations and frozen data were unchanged.

## Checks actually run

- `npm --prefix studio-app run test`: **57 tests passed in 14 files**, including four new recovery regressions. Unit tests cover rejected module retry, render failure without automatic retry loops, diagram failure with continued editing/saving, and board/scope/subpath preservation in the refresh URL.
- `npm --prefix studio-app run build`: TypeScript and production build passed.
- `.venv-assistant/bin/python scripts/verify_workflow_browser.py`: real Park, Camp and Grove preset diagrams and tables each loaded seven nodes and passed backend graph validation. A Park label edit persisted and its saved workflow executed to completion with **seven checked node receipts**.
- The browser test deliberately interrupted the Workflow module download. Studio navigation remained available, Return to Board retained the selected investigation, and refreshing opened the same saved seven-node workflow with the edited label. **No uncaught page errors** occurred, including this failure scenario.
- Browser layout checks at **360, 390 and 768 pixels** reported document widths equal to their viewport widths.
- `python3 scripts/check_landing_preservation.py`: **75 protected hashes and both outside-header HTML boundaries matched**.
- `python3 scripts/check_jarvis_release.py`: **382 manifest assets**, source/static parity and **177 JavaScript syntax checks** passed.

See [browser-report.json](browser-report.json), [the working diagram](workflow-park.png), [contained download failure](workflow-download-recovery.png), and [the restored workflow](workflow-refreshed.png). Narrow-layout screenshots are included alongside them. `workflow-loading-failure-before.png` records the reproduced empty Studio before the fix.

## Operating note

An already-open tab can still be executing the old application JavaScript. Reload that tab once to receive the fix. Future editor loading failures remain contained; refresh loads the current asset manifest without deleting saved workflows or browser drafts. No provider availability, external transfer or deployment was tested or changed by this fix.
