# FireAtlas presentation and visual polish guide

> Historical snapshot from 27 September 2026. Its screenshots and routes predate
> the R1/R2 cleanup on `main`; the disaster casebook and fictional Training Lab
> described below are archived and are not available from the current site. Do
> not use this guide as a current demonstration script. R13 will replace it after
> updated presentation assets are ready.

[Open the 22-page PDF](FireAtlas_Feature_Polish_Guide.pdf).

The archived guide contains 16 prioritized feature pages, screenshots,
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
Screenshots document the application as it existed on 27 September 2026; they
are not screenshots of the current `main` branch.

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

Before the R1/R2 cleanup and after adding the mobile web app:

- `uv run python -m unittest discover -s tests -v`: **56 tests passed**.
- `uv build`: source distribution and wheel built successfully.
- Changed JavaScript files passed `node --check`.
- `uv run --with playwright python scripts/verify_mobile_app.py`: **passed**.
  The persistent Chrome profile reported zero manifest or installability errors.
  The earlier version also checked the now-archived Training Lab offline flow.
  No JavaScript exceptions were observed in that historical check.
- PDF: 22 A4 landscape pages; all source images loaded; no detected footer
  overlaps. Cover, calendar and mobile-status rendered pages were visually reviewed.
- Authentic database SHA-256 remained unchanged:
  `c124dd85c3846631ddbf1f237ff3bd9d51aa7c4e78f7493e39e02c9e50412839`.

These are application checks. No physical-phone install, public HTTPS deployment,
native APK or iOS build was completed. The new install page is `/install.html`.
See [mobile setup](../MOBILE_APP.md) for the remaining presentation setup.
