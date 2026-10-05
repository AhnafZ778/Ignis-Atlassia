# Canvas vegetation backgrounds

Implemented locally on 6 October 2026.

Canvas map cards have a persisted, text-free dot toggle for the map background. Green means on; gray means off. Click or keyboard Space changes it, with an accessible switch name and checked state. Off shows the original dark heatmap, and on restores the previous landscape. Park automatically displays its authentic supplied MOD13Q1 NDVI image and NASADEM terrain beneath the existing occupied-cell heat. Camp and Grove use their own supplied terrain. A matching exact footprint is required for these prepared images. Other footprints can request online vegetation through NASA GIBS. Existing supplied vegetation, online vegetation and terrain choices are retained when toggling off and back on.

Local images are checked against their recorded SHA-256 and exact bounding box before delivery through the owned snapshot landscape endpoint. Park's label names the 16-day composite beginning 11 July 2024. Online WMS requests retain the actual selected bounds in west/south/east/north order and align the requested date to the UTC 16-day period. They use the existing MODIS NDVI visualization, with anonymous CORS for Canvas rendering and PNG download. Online imagery is dated display context, separate from the frozen scientific receipt. It is never presented as fire-day vegetation measurements or an exposure denominator.

Canvas previews use the existing geographic Gaussian kernel and full-study domain. Background images are drawn beneath the heat; they do not change cell eligibility, deduplication, source count, selected day or concentration scale. Supplied layers work without terrain/imagery services. Missing or failed imagery retains the heat and source evidence, with an explicit status. Downloaded Canvas PNGs include the displayed landscape. Existing scientific result and reader export contracts are retained.

The online integration follows [NASA GIBS WMS access documentation](https://nasa-gibs.github.io/gibs-api-docs/access-basics/). A live Northern California request returned a valid PNG with anonymous CORS support (249,951 bytes). This verifies image retrieval, not independent scientific interpretation.

Validation artifacts and actual test outcomes are recorded alongside this document. The browser check uses a separate private workspace, opens the authentic Park preset, compares background-only pixel changes against unchanged sensor/day/domain, saves a PNG, checks refresh and opens the interactive map.

- 49 Python landscape/store/HTTP tests passed.
- 73 frontend tests passed; TypeScript and production build passed.
- Browser acceptance passed with zero JavaScript errors. Both sensor panes retained the full-study maximum `6.240770107354527` and the selected UTC date `2024-07-30` when switching backgrounds.
- Background selection persisted after refresh; the interactive map displayed the same supplied vegetation layers.
- Landing preservation passed: 75 protected asset hashes and both outside-header HTML boundaries match.

See the [browser report](browser-report.json), [Canvas screenshot](vegetation-canvas.png) and [downloaded vegetation heatmap PNG](park-vegetation-heat.png).

Run the checks against the local service with:

```bash
.venv-assistant/bin/python scripts/verify_canvas_vegetation.py
.venv-assistant/bin/python -m unittest tests.test_studio_landscape tests.test_studio_store tests.test_studio_http
```
