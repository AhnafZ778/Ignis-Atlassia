# Data readiness and implementation status

**Updated:** 29 September 2026. This file describes the repository after cleanup segment R4. Older presentation guides and screenshots are historical artifacts and show removed features.

## Data presently available

| Source | Current scope | Status and limit |
| --- | --- | --- |
| NASA FIRMS MODIS + VIIRS S-NPP standard archives | 30,823 Northern California detections; 84 complete source-month exports from July 2022 through December 2025; partial 2026 rows | Authentic user-supplied archive derivatives with source request IDs and hashes. Complete exports do not establish clear passes or cloud-free observation. |
| NOAA HMS VIIRS | 49,420 historical Northern California detections, July 2021–2024 | Authentic, separate NOAA product cohort; not merged into the NASA pair. |
| Recent global NASA FIRMS files | Present only in the local ignored database/data files | Not bundled in a clean clone and not reproducible without copying or reimporting the source files. |
| MODIS/VIIRS pass and cloud masks | No processed pilot coverage bundle | Missing observation opportunities remain unknown. The web app does not derive “no pass” from absent detections. |
| NASA GIBS NDVI and land-cover imagery | Requested by date through NASA GIBS | Visual context only; no local vegetation/fuel calculation. Measured fire weather is unavailable. |

Archive row counts and provenance are documented in [NASA archive import](NASA_ARCHIVE_IMPORT.md). Hotspot rows represent thermal detections, not a perimeter, burned area, or proof that no fire occurred in blank areas. Product-version changes limit historical comparisons; see the archive and method notes.

## Synthetic data boundary

The website no longer has a synthetic data selector, synthetic tour, generated context endpoint, generated coverage-mask endpoint, or `--judge-demo` launcher. API requests with a `demo` query parameter return HTTP 400. The retired `/api/presentation`, `/api/context`, and `/api/research/coverage-example` endpoints return HTTP 404. The server refuses to start with a database containing generated demonstration batches. The generator modules are imported by automated tests only and have no command-line entry point.

A user may upload an observation mask to the Research Lab. The app checks its structure and consistency but cannot certify how the mask was produced. No mask is supplied by default.

## Verification record

- Automated suite: run `uv run python -m unittest discover -s tests -v`; latest result is recorded in the R4 row in [the scorecard](winning-plan/SCORECARD.md).
- JavaScript syntax: `node --check` on the edited app, study, research, method, data and validity scripts.
- HTTP behavior: tests verify retired API routes return 404 and `demo` query parameters return 400. The main launcher also rejects a generated database.
- Browser screenshot review and external NASA/GIBS availability were not part of the R4 checks. Do not infer visual QA or live service availability from unit tests.

## Remaining scientific work

Native MOD14/MYD14 and VNP14IMG fire masks with geolocation have not been decoded into dated observed/cloud/no-pass/unknown grid states. No 90-minute matched-overpass validation, held-out sensitivity evaluation, independent specialist review, or calibration is established by the source archive alone. The harmonized calendar remains a descriptive shared-grid count of imported detection-centroid cell-days.
