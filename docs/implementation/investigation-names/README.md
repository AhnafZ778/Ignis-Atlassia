# Investigation naming

Implemented 6 October 2026 (Asia/Dhaka).

New manual investigations prompt for a name before creation. Cancel creates nothing and restores focus. Existing investigations have an explicit Investigation name field and Save name action; Enter submits and Escape cancels an unsaved rename. Names are trimmed, bounded to 1–120 characters, and read-only for viewers. Failed saves retain the draft and report failure rather than claiming success.

Renaming reuses the existing owned title transaction, preserving scientific selection, cards and frozen evidence. Undo/Redo applies through the existing revision history. The saved-investigation selector synchronizes renamed titles, and the current board URL follows manual creation, switching and preset creation so a refresh opens the actual investigation.

Verification: 65 frontend tests passed across 15 files; production TypeScript/build passed. Real Chromium checks creation, explicit rename, refresh, selector labels after switching, Undo/Redo, cancellation/focus restoration and layouts at 360/390/768 pixels. No page errors or horizontal page overflow were recorded. The supported static refresh and asset parity check passed; all 75 protected landing hashes and both outside-header boundaries match.

See [browser report](browser-report.json) and [name editor](investigation-name.png). Repeat acceptance with:

```bash
.venv-assistant/bin/python scripts/verify_investigation_names.py --base http://127.0.0.1:8000
```

Naming requires the local Studio service; static evidence releases do not simulate persistent authoring. No inference/provider calls are needed.
