# Archive search and map run admission

Verified locally on 6 October 2026.

The shared daily 20-run admission check counted automatic map loads, historical searches, conversations, failed requests and cancellations together. Once reached, it blocked stored-data browsing with “Temporary workspace turn limit reached.” The check has been removed from `Store.create_run`, including conversational admission. Existing history remains intact; saturated workspaces require no cookie, notebook or database reset. The running local service was restarted to activate the change.

Scientific calculations, selection, eligibility, concurrency handling, ownership, idempotency, HTTP throttles and paid inference accounting retain their existing behavior. No scientific data or protected landing asset was changed by this fix.

Verification:

- All 45 tests in `tests.test_assistant` passed, including new regressions covering previously saturated workspaces, failed/cancelled history, conversational admission, nonce reuse and the active-run guard.
- Actual archive and replay operations completed after 21 prior requests with inference mocked to fail if invoked.
- A real browser completed 21 deterministic requests in one workspace, then used the visible historical-search button. It returned 218 monthly windows and 46,344 authentic imported rows before replay filtering.
- Refresh preserved saved answers and restored the selected Park frame: 159 MODIS and 558 VIIRS detections. No JavaScript errors or conversational inference requests occurred.

The [browser report](browser-report.json) and [screenshot](historical-search-restored.png) record the result. Reproduce against the local service with:

```bash
.venv-assistant/bin/python -m unittest tests.test_assistant
.venv-assistant/bin/python scripts/verify_archive_run_admission.py
```

The browser check creates its own private workspace and uses actual deterministic API calls; it does not modify the user's existing workspace or scientific database.
