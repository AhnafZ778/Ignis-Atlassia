# Studio navigation and canvas panning

Implemented 6 October 2026 (Asia/Dhaka).

- Added Studio to all six canonical navigation headers, with an active-page marker in Studio. The landing change is restricted to its permitted navigation block.
- Styled Investigate's Create in Studio link as a prominent filled action with a minimum 44-pixel target, keyboard focus indication and its existing context-preserving destination.
- Empty-space dragging now pans without selecting a mode. Pan canvas also works over frozen previews. Space-drag with canvas focus and middle-button drag pan over cards. Selection-mode card dragging, buttons, fields and interactive Leaflet maps retain their gestures.
- Pointer capture keeps panning reliable outside the canvas boundary; cancellation, lost capture and window blur end the gesture. Panning changes the viewport rather than writing card transformations. Save canvas view remains explicit.

Verification: production TypeScript/build passed; 60 frontend tests passed; Chromium checks passed for default panning, Space-drag, middle-button panning, preview panning, saved card dragging, detail controls, pointer zoom and five-link headers. The Investigate action is visible at 360/390/768 pixels without page overflow. The landing guard matches 75 protected asset hashes and both outside-header boundaries. Supported static refresh and source/static asset checks passed.

See [browser report](browser-report.json), [Investigate button](investigate-studio-button.png) and [canvas controls](studio-panning-controls.png).

Run ` .venv-assistant/bin/python scripts/verify_studio_navigation_pan.py --base http://127.0.0.1:8000 ` against the local service to repeat acceptance. It creates an isolated browser identity and a small private test board; it does not call a model provider.
