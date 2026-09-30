# Data readiness and implementation status

**Updated:** 30 September 2026 after regenerating the compact static evidence bundle, checking the completed fire-mask checklist, and running the full regression suite. Older presentation guides and screenshots may show historical or removed features.

## Data presently available

| Source | Current scope | Status and limit |
| --- | --- | --- |
| NASA FIRMS MODIS + VIIRS S-NPP standard archives | Local database: 1,994,162 unique standard rows in two regions, with positive detections as early as July 2006 MODIS / July 2012 S-NPP and row-level S-NPP through July 2022; 48 MODIS and 47 S-NPP request-verified months per region from July 2022 through June 2026 | Eight exports retain request metadata. Twenty-six exports use reconstructed row-only sidecars; missing dates remain unknown and are not valid full-month zeros. Complete exports do not establish clear passes or cloud-free observation. |
| NOAA HMS VIIRS | 49,420 historical Northern California detections, July 2021–2024 | Authentic, separate NOAA product cohort; not merged into the NASA pair. |
| Recent global NASA FIRMS files | Present only in the local ignored database/data files | Not bundled in a clean clone and not reproducible without copying or reimporting the source files. |
| MODIS/VIIRS pass and cloud masks | No processed pilot coverage bundle | Missing observation opportunities remain unknown. The web app does not derive “no pass” from absent detections. |
| NASA GIBS NDVI and land-cover imagery | Requested by date through NASA GIBS | Visual context only; no local vegetation/fuel calculation. Measured fire weather is unavailable. |

Archive row counts, original-file hashes and missing windows are documented in [the NASA data ledger](DATA.md) and [NASA archive import](NASA_ARCHIVE_IMPORT.md). The 2022–2026 matched export months remain the only complete comparison window. Hotspot rows represent thermal detections, not a perimeter, burned area, or proof that no fire occurred in blank areas. Product-version changes limit historical comparisons; see the archive and method notes.

## Synthetic data boundary

The website no longer has a synthetic data selector, synthetic tour, generated context endpoint, generated coverage-mask endpoint, or `--judge-demo` launcher. API requests with a `demo` query parameter return HTTP 400. The retired `/api/presentation`, `/api/context`, and `/api/research/coverage-example` endpoints return HTTP 404. The server refuses to start with a database containing generated demonstration batches. The generator modules are imported by automated tests only and have no command-line entry point.

A user may upload an observation mask to the Research Lab. The app checks its structure and consistency but cannot certify how the mask was produced. No mask is supplied by default.

## Verification record

- Automated suite: `uv run --offline python -m unittest discover -s tests -q`; the current run is recorded in the [scorecard](winning-plan/SCORECARD.md) after the 2006 history and native evidence refresh. The suite covers the static evidence, Data Sources and native review checks.
- JavaScript syntax: `node --check` on the edited app, study, research, method, data and validity scripts.
- HTTP behavior: tests verify retired API routes return 404 and `demo` query parameters return 400. The main launcher also rejects a generated database.
- Browser screenshot review and external NASA/GIBS availability were not part of the R4 checks. Do not infer visual QA or live service availability from unit tests.
- The static bundle is 2006–2026 and is prepared for GitHub Pages, but the workflow has not been deployed or opened at a public URL.

## Remaining scientific work

The Grove case has 20/20 native fire-mask granules and 15,495 clipped pixels;
Park has 114/114 and 1,372,872 pixels. FIRMS-to-native reconciliation is 7/7
for Grove and 3,137/3,137 for Park. Both ledgers are still
`processed-unreviewed`: they provide descriptive 90-minute pairs, not a
complete dated observed/cloud/no-pass/unknown grid. Independent specialist
review and per-cell pass/cloud coverage remain open. The harmonized calendar
remains a descriptive shared-grid count of imported detection-centroid
cell-days.
