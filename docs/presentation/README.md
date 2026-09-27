# FireAtlas presentation and visual polish guide

[Open the 22-page PDF](FireAtlas_Feature_Polish_Guide.pdf).

The guide contains 16 prioritized feature pages, actual application screenshots,
exact local URLs, presentation actions, visual improvement suggestions and a
ready-to-present check for each feature. It also documents the mobile app format,
phone setup, a five-minute presentation sequence and remaining limitations.

- Pages 3–7: globe, seasonal calendar, sensor comparison, date replay and evidence.
- Pages 8–13: research overlap, candidate groups, exposure, commander rehearsal,
  mobile crew view and offline recovery.
- Pages 14–18: environmental context, study exports, guided tour, EONET and provenance.
- Pages 19–22: mobile status, phone setup, presentation script and verification.

The [HTML source](FireAtlas_Feature_Polish_Guide.html) and 24 original captures in
[screenshots](screenshots/) accompany the PDF. [screenshots.json](screenshots.json)
records their source URLs, selectors and data labels. Interaction instructions
in the guide identify state changes that cannot be encoded in a page URL.
Screenshots are the current application, not future redesign mockups.

## Rebuild the PDF

From the repository root, with Playwright and Chrome available:

```bash
uv run --with playwright python scripts/build_presentation_guide.py
```

The generator reads the included PNG captures, checks all images load and checks
that content does not overlap footers. It prints A4 landscape using local Chrome
at `/usr/bin/google-chrome`; no running FireAtlas server is needed to rebuild.
Local page links require the running application. Replace `127.0.0.1:8000` with
the presentation host when showing the website on another device.

## Verification — 27 September 2026

After adding the mobile web app:

- `uv run python -m unittest discover -s tests -v`: **56 tests passed**.
- `uv build`: source distribution and wheel built successfully.
- Changed JavaScript files passed `node --check`.
- `uv run --with playwright python scripts/verify_mobile_app.py`: **passed**.
  The persistent Chrome profile reported zero manifest or installability errors.
  At 390 × 844 with touch emulation, the app's offline launch displayed the
  reconnect screen. The narrower Training Lab service worker took control;
  actual browser-offline reload restored 12:05 and Crew Bravo; exercise export
  worked offline. No JavaScript exceptions were observed.
- PDF: 22 A4 landscape pages; all source images loaded; no detected footer
  overlaps. Cover, calendar and mobile-status rendered pages were visually reviewed.
- Authentic database SHA-256 remained unchanged:
  `c124dd85c3846631ddbf1f237ff3bd9d51aa7c4e78f7493e39e02c9e50412839`.

These are application checks. No physical-phone install, public HTTPS deployment,
native APK or iOS build was completed. The new install page is `/install.html`.
See [mobile setup](../MOBILE_APP.md) for the remaining presentation setup.
