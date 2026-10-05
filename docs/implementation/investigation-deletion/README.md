# Investigation deletion

Implemented and verified locally on 6 October 2026.

All 284 previously active investigations in the local Studio store were cleared at the user's request. The [clear report](clear-report.json) records zero remaining active boards. Scientific inputs, assistant notebooks and curated presentation presets were preserved. Internal revisions are retained through soft deletion rather than purging database evidence.

A new investigation created after that cleanup was preserved; the cleanup did not continuously remove new work.

Studio now shows **Delete investigation** beside its saved-investigation selector. An accessible native modal uses the Studio palette, a trash icon, a blurred backdrop and explicit **Keep investigation** / **Delete investigation** actions. It names the targeted board, defaults keyboard focus to Keep, supports Escape, contains focus, retains errors for retry, and blocks duplicate submission while saving. Successful deletion selects a remaining board or shows an empty Studio. Reload and old deleted-board URLs do not recreate the deleted investigation. Empty Studio keeps creation and curated preset controls usable.

`DELETE /api/studio/documents/{id}` accepts `expected_revision` and the existing `Idempotency-Key` header. The existing owner and same-origin checks apply. A changed revision requires reloading before deletion. Repeated delivery of the same successful deletion is idempotent. Deleted boards disappear for owners and collaborators and reject subsequent reads and card mutations. Associated active workflow/render jobs receive cancellation flags. Scientific records and unrelated investigations are unchanged.

Verification completed:

- 42 Python Studio store and HTTP tests passed, covering ownership, same origin, revision conflicts, idempotency and deleted-board access.
- 69 frontend tests passed, including four confirmation-dialog tests for cancel, Escape, failure/retry and pending submission.
- TypeScript checking and production build passed.
- Real browser checks passed for keep/cancel, confirmed deletion, preservation of a second board, reload, final-board deletion and a stale board link. Dialog layouts passed at 360, 390 and 768 pixels with no horizontal overflow or JavaScript errors.
- Landing protection passed: all 75 protected asset hashes and both outside-header HTML boundaries match.

See the [browser report](browser-report.json), [desktop dialog](confirmation-desktop.png) and [narrow dialog](confirmation-narrow.png). Reproduce with:

```bash
.venv-assistant/bin/python -m unittest tests.test_studio_store tests.test_studio_http
cd studio-app
npm test
npm run build
```

From the repository root, run `.venv-assistant/bin/python scripts/verify_investigation_deletion.py` against the local service. It creates and deletes its own test investigations, leaving that browser workspace empty. The frontend was refreshed through the supported static tooling; static authoring still requires the local service.
