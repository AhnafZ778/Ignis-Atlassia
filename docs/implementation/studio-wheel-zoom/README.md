# Canvas wheel input only zooms

Implemented 6 October 2026 (Asia/Dhaka).

Every wheel gesture inside the built-in Studio canvas now zooms around the pointer, including gestures over cards, scrollable evidence, controls and embedded views. Native capture uses a non-passive listener to prevent default scrolling and to stop nested wheel handlers before they can scroll or apply their own zoom. Horizontal wheel input also zooms; limits remain 10%–400%. Wheel input outside the canvas retains ordinary page behavior.

Scrollbar offsets participate in the pointer anchor calculation. Dragging a scrollbar or panning the canvas remains available for repositioning; pointer handling leaves native scrollbar tracks alone. No scientific result or card position changes when zooming.

Production build and TypeScript checking passed; 60 frontend tests passed. Real Chromium acceptance checks wheel zoom in both directions over card content, controls and headings; unchanged card/board/page scroll positions; pointer anchoring after manual scrolling; suppression of nested wheel handlers; ordinary outside-canvas behavior; and unchanged stored card positions. No page errors or passive-listener warnings were recorded.

See [browser report](browser-report.json). Repeat with:

```bash
.venv-assistant/bin/python scripts/verify_studio_wheel_zoom.py --base http://127.0.0.1:8000
```

Source and generated static assets are refreshed through the supported exporter. The protected landing remains unchanged.
