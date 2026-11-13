# 02 — Acquisition, normalization, and provenance

[Context entry point](../../CODEBASE_CONTEXT.md) · reviewed 2026-10-27

## Source owners

| Module | Responsibility / useful symbols |
| --- | --- |
| core.py | connect, _normalized_row, ingest, _complete_month, calendar_row_included; scientific schema and grid |
| archive.py | build_bundle, import_bundle, import_requests; original archive CSVs, metadata sidecars, region/month slicing |
| fetch.py | availability, fetch_month; authenticated FIRMS area requests in 1–5-day windows |
| hms.py | harvest_month; separate NOAA HMS complete daily archives |
| bootstrap.py | populate_showcase; verify and seed bundled HMS history into an empty DB |
| pilots.py | PilotSync; resumable authentic import, status files, ledger reconciliation and reproducibility checks |
| settings.py | firms_key; environment credential or owner-managed key file |
| regions.py | REGIONS, PRODUCTS, bbox containment/intersection |
| provenance.py | public_source_reference, sanitize_public_payload; safe outward source references |
| demo.py | make_demo; synthetic fixtures for tests only |
| presentation.py | Deterministic presentation fixtures in their separate store |
| scripts/prepare_legacy_firms_sidecars.py | Explicit reconstructed row-only metadata, never fake request coverage |

All paths in this table are under fireatlas/ unless prefixed scripts/.

## Scientific SQLite contract

connect creates five tables and lookup indexes. batches records source ID, sanitized source URI, file SHA-256, retrieval time, demo flag, row count, and window identity. observations stores detection_id, batch reference, native source/platform/sensor/version/processing level, acquisition/retrieval UTC, coordinates, scan/track meters, raw confidence, raw FRP, day/night, anomaly type, grid indexes, and raw_json.

excluded_rows preserves explicitly excluded polar rows and reasons. export_windows establishes a complete monthly bbox export. source_exports additionally records region, request dates/bounds, complete_export, coverage_basis, product versions, original archive hash, and request hash. An observation row alone is insufficient proof of completeness.

## Normalization and idempotency

- Input CSV uses the original FIRMS column contract. instrument may be absent for ingestion; other required fields are checked.
- Source/platform/instrument combinations are validated. S-NPP archive instrument=SNPP normalizes to VIIRS while original spelling remains in raw_json.
- NRT/URT version labels cannot be relabeled standard processing.
- acq_date + zero-padded acq_time becomes UTC. Scan/track kilometers become positive finite meters.
- Supported scientific grid latitude is ±86°. Grid indexes are floor(projected coordinate / 1000), with EPSG:4326 → EPSG:6933 and always_xy=True.
- Detection IDs hash normalized observation identity fields; batch IDs separately identify file/source/window. Reimporting a batch is a no-op; INSERT OR IGNORE avoids duplicate detection IDs.
- An invalid row aborts the transaction. Explicit polar exclusion cannot simultaneously assert a complete monthly export.
- complete_month and bbox must appear together, and every included row must belong to that month and box.
- Source URI sanitization redacts FIRMS MAP_KEY path segments, query/fragment credentials, and personal absolute local-file locations.

Read ingest and _normalized_row before changing a column, hash, alias, or importer. A hash change can alter duplicate identity and downstream provenance.

## Archive completeness

import_requests consumes owner-supplied archive directories and request.json sidecars. It streams and slices input by fixed study region and month. A month becomes complete only when **original request metadata** covers the entire month and full regional box. A reconstructed-rows-only sidecar can preserve positive rows but cannot turn absent dates into complete zero exports.

World-spanning empty exports have a special conservative completeness guard. Requested dates/bbox/product and parent/request hashes survive in the ledger. Do not convert reconstructed metadata into original evidence simply to remove partial-state labels.

The fixed regional boxes are Northern California (-122.2, 38.8, -120.0, 41.0) and Punjab–Haryana (73.8, 29.5, 77.6, 32.6), ordered west/south/east/north. Named incident replay boxes are different; a smaller incident selection is not the regional calibration domain.

## Network acquisition boundaries

fetch_month verifies product availability for the full requested month, downloads bounded day windows, validates CSV field continuity, atomically installs a temporary CSV, and ingests it. refresh explicitly replaces previous matching exports transactionally. Primary/secondary hosts are fallbacks for transport/server failures, not repeated attempts at rejected credentials or rate limits.

HMS rows retain NOAA provenance and their own processing/source label. They are not substitute standard FIRMS S-NPP rows for harmonization. PilotSync tracks running/admission state and reconciles already imported data.

The web Data page's import/sync mutation endpoints are loopback/same-origin restricted. The assistant and MCP interfaces do not import arbitrary datasets.

## Data availability is not observation coverage

availability.py overlays the dated sensor_notices.json ledger. source_status returns documented_processing_gap, unknown_export, detections_in_export, or zero_detections_exported, plus notice-day scope. observation_opportunity stays unknown. Even a full-month request cannot establish satellite pass, clear sky, or absence of fire.

The committed samples and local archive are different: fireatlas/samples/ supplies small authentic and supporting frozen artifacts; NASA_data/ and the large live DB remain ignored. Read docs/DATA.md and docs/NASA_DATA_IMPORT.md for dated local ledgers; do not copy historic row counts into claims about the current DB without querying it.

## Verify and change safely

Relevant tests: test_phase1.py, test_archive.py, test_archive_requests.py, test_hms.py, test_pilots.py, test_aggregates.py. Use temporary DBs and fixture inputs when testing. After schema/source changes, also inspect release fingerprints, aggregate/calibration outputs, study exports, and public provenance serialization. Update this guide and the source index.

## Isolated qualification acquisition

`acquisition.py` discovers current FIRMS availability and writes bounded5-day exact original request CSVs and hash-bound receipts under `data/qualification/campaign/`. It enforces a10decimalGB campaign+processing+qualification-publication budget and20decimalGB free floor, uses an interprocess lock, checks response completeness and CSV bounds, validates receipts by recount and resumes without duplicate provider requests. Complete-month merged imports use a single outer transaction for batches, observations, export_windows and source_exports in a separate shadow database; original scientific DB is unchanged. SQLite page ceilings, journal headroom, timed progress checks and pre-reserved64KiB streamed CSV blocks bound expansion. The overlap runner records each completed month and retries both acquisition/import busy-lock states briefly; other failures retain receipts and stop the batch. Empty verified exports retain unknown collection if undocumented. `VIIRS_NOAA21_SP` and `viirs-noaa21` are separate from NRT, confirmed by live provider availability; no platform calibration follows from importing them. Use explicit `scripts/qualification_pipeline.py`, never provider actions on GET.

## Full bounded campaign continuation

`scripts/complete_mentor_campaign.py` sequences overlap, NOAA-20, NOAA-21 and early MODIS regional standard archives under one original10GB/20 GB free gate. Provider availability controls actual start/end; partial edge months and unavailable standard products are excluded, never replaced with NRT. The overlap runner now accepts source/from-year bounds, two rate-limited workers and a persisted one-day fallback after a five-day request exceeds the unchanged2 MB ceiling. Replacement plans reserve their larger worst-case volume before acquisition; original receipts remain. Verified idempotent imports skip unnecessary full-history inventory scans. Fitting occurs only in the explicit AI-only assessment phase after frozen input read locks close. Interrupted phases retain incomplete progress and supported research remains separately scoped.

The overlap runner retries only SQLite BUSY/LOCKED and explicit shared acquisition-lock contention for a bounded600second deadline, allowing concurrent read captures and full publication to finish. Atomic/idempotent imports make rolled-back commit retries safe; schema, provider, corruption and storage errors still stop acquisition. Focused tests: `tests.test_campaign_locks`.

`transfer_provenance.py` is a separate read-only verifier for a frozen transfer capture. It uses a consistent SQLite read transaction and matches the capture, original request receipts, whole-month UTC windows, requested bounds/cohort, reconstructed merged CSV bytes and first-owner normalized observation rows, then checks exact daily cell/platform/file unions. Equivalent saved plans are deduplicated; missing originals or unverified earlier owners remain partial. It verifies stored acquisition records and bytes, not a NASA cryptographic signature or independent review. Immutable scientific transfer methods remain unchanged.

The transfer-source verifier confines retained normalized batches to a single role, then drops that role before processing the next. It bounds unique normalized detections at 2,000,000 per role and 4,000,000 parsed across the capture, including rows in later-partial months; per-month detection and original-file bounds remain. Partial reasons are deduplicated as they are recorded. These are detection-count guards, not limits on total process memory or CPU: the input and freshly captured cells can also occupy memory. This does not alter prior receipt schemas or scientific approval.

The verifier fingerprints the plans and completed original request CSVs, receipts and merged files it reads, then rechecks those bytes after both roles have finished. Standalone transfer and monthly commands take a shared campaign lock; the qualification publisher already holds the exclusive lock. Acquisition and import use the exclusive lock, so cooperating work cannot modify these files during verification. A process that ignores the lock can still modify files after an individual final recheck; the pass is not a filesystem snapshot or provider signature. A changed original fails instead of yielding a verified receipt, and lock contention leaves the check to be retried.

The campaign runner retries the two exact known provider transport failure messages at most twice after the initial attempt (3- and 6-second backoff), retaining the minimum provider request spacing across attempts. Each retry revalidates already retained receipts and resumes incomplete requests. Only failures opening or reading the provider response are classified as transport interruptions; local file and receipt failures propagate without retry. With concurrent workers, all started workers finish before failures are classified: a failure that must stop further requests takes precedence over size-limit fallback and transport retry. HTTP errors during response reads receive the same handling as errors opening the response. Rate limits, rejected access, invalid data, storage errors and other failures are not retried by this policy; incomplete work remains incomplete. Campaign lock and SQLite busy retries remain a separate bounded policy.

## Bangladesh live API check — 2026-11-08

The existing owner-managed FIRMS credential was already configured and was validated through `fetch.availability()`; its value was not displayed or copied. A new key was not requested. Current provider availability included MODIS NRT, NOAA-20 NRT and NOAA-21 NRT through November 8; S-NPP NRT ended November 2 in that response and must not be substituted for newer dates. Availability is dated provider metadata, not observation opportunity.

A bounded direct Area API check requested November 3–7, 2026 for bbox `[88.0,20.5,92.7,26.7]`. Returned records were checked against requested bounds and dates. Results were MODIS_NRT 0, VIIRS_NOAA20_NRT 59, VIIRS_NOAA21_NRT 53. This rectangle includes neighbouring territory, so these are not exact Bangladesh country totals. Filtering the returned coordinates to the interior Dhaka-area rectangle `[90.2,23.65,90.6,24.0]` yielded 0, 5 and 2 respectively. These are separate sensor records, not summed unique fires. Empty results do not establish no fire or clear-sky coverage.

The retained CSV text totals 9,628 bytes. Files and a safe request/hash receipt are in ignored `data/live-checks/bangladesh-2026-11-08/`. Their receipt hashes describe retained UTF-8 CSV text after the existing download decoder, not a NASA signature. No scientific database rows, saved boards or frozen releases were changed. NRT remains preliminary and distinct from SP.

The app's existing acquisition code supports authenticated server-side FIRMS access; `fetch_month` still downloads whole months. The assistant's science tools continue to read stored evidence. This key/data check does not implement or claim an automatic whiteboard-to-FIRMS on-demand fetch path. For small requests use the global Area API (1–5 days per call); NASA's country endpoints were marked unavailable when inspected. A new free MAP_KEY can be requested by email at https://firms.modaps.eosdis.nasa.gov/api/map_key/ if ever needed. Keep the key in the server environment or owner-managed key file, never browser/export payloads.
