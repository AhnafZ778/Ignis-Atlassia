# 04 — Validation, native masks, and scientific evidence bundles

[Context entry point](../../CODEBASE_CONTEXT.md) · reviewed 2026-10-27

## Evidence ladder

Authentic imported rows, reproducible aggregation, native file reconciliation, external incident context, and independent human review are separate gates. A checksum verifies content integrity; a recount verifies a stated computation. Neither authenticates a provider independently nor signs off scientific validity.

| Module/script | Role |
| --- | --- |
| fireatlas/granules.py | Public NASA CMR metadata inventory for fixed cases; query/refresh/load/summary |
| scripts/build_fire_mask_inventory.py | Inventory local native file/geolocation assets |
| fireatlas/mask_download.py | Frozen exact download checklist; optional authenticated Earthdata acquisition |
| fireatlas/masks.py | Pair/decode authentic fire mask + geolocation, store native samples, reconcile rows and summarize passes |
| fireatlas/mask_review.py | Deterministic human sample queue, blank review, hash checks and review validation |
| fireatlas/incidents.py | CAL FIRE incident cohort used as explicitly external context |
| fireatlas/validity.py | Park/Grove case reports, sensitivity checks, gates and evidence archives |
| fireatlas/validation_check.py | Independent analytic projection/grid recount of frozen evidence |
| scripts/build_mcd64_corroboration.py | Hash-bound lagged burned-area/QA contextual checks |
| scripts/build_replay_layers.py | Prepared georeferenced display context from already local rasters |

## Native processing

masks.PRODUCTS pairs MOD14→MOD03, MYD14→MYD03, and VNP14IMG→VNP03IMG. Native decoding and geolocation are optional heavy requirements (NumPy plus appropriate GDAL/HDF/netCDF support); core row/calendar operation does not imply those libraries are installed.

decode_file streams bounded strips and rejects shape mismatch. Native class labels retain missing, not-processed/bowtie, unusable, water/land, cloud, unknown, and low/nominal/high fire distinctions. Processing records file identities, product/date/case provenance, and native pixel location. Native pixel centroids are mapped onto the same common grid for the stated comparison, not used to invent full footprint coverage.

Inventory absence is not proof of no satellite pass. passes_from_pixels, paired_observations, reconcile, and summarize have distinct responsibilities. Review native method metadata and source/geolocation hashes when a gate changes.

Native evidence defaults to data/validity_masks.sqlite3. Downloaded files stay under NASA_data/fire_masks/. The HTTP server only exposes inventory-backed native filenames. No arbitrary path is accepted.

## Human review

mask_review.REQUIRED_SAMPLES is 30. make_template emits a blank hash-bound review tied to current native evidence. validate_review checks identity, required samples, outcomes and reviewer information; accepted outcomes include agree/disagree/unresolved. Installing a form is explicit CLI work. A model must not impersonate a qualified independent reviewer or mark a scientific signoff completed just because automated recounts pass.

Park/Grove validity configurations differ from replay windows. Selected-day reports include native/source state, sensitivity results, incident context and review gates. External incident coordinates/dates do not assign every nearby hotspot to that incident.

MCD64A1 is lagged contextual burned-area evidence with its own Burn Date/QA interpretation and hashes. It is not active-fire ground truth, a perimeter or a coverage denominator. calendar_v2 only reports a matching dated check when one exists; missing corroboration stays not-loaded.

## Scientific export contracts

| Contract | Owner | Contents / limits |
| --- | --- | --- |
| fireatlas-study-v2 (legacy v1 accepted) | study.py | Generic selected-series raw union calendar, normalized inputs and month audit; 50,000 rows |
| fireatlas-regional-study-v1 | regional_study.py | Exact harmonized region/month result plus full required regional history, ledgers, notices, calibration and dependencies; 2,000,000 rows |
| fireatlas-validity-evidence-v1 | validity.py | Case evidence, input rows, audit and checksums |
| fireatlas-studio-evidence-snapshot-v1 | studio/evidence.py | Owned immutable receipt-backed facts; not a scientific source-data ZIP |
| fireatlas-board-v1 | studio/portability.py | Saved authoring board and frozen provenance; not a replacement for the regional science bundle |

regional_study.build_bundle uses one consistent read transaction and freezes external JSON dependencies. It checks expected_result_sha256 against the displayed result. Changed inputs cause StaleResult and HTTP 409 rather than silently exporting another calculation. It uses the production 2026 preparation horizon and includes full required standard-source history, not only the selected month's visible rows.

Regional ZIP limits include 512 MiB compressed, 3 GiB expanded, 100,000-row/128 MiB chunks, 64 KiB per source record and 32 MiB metadata. verify_bundle checks safe archive inventory and sizes/hashes, reconstructs temporary scientific SQLite, recounts/refits the result, and compares scientific content. Tampering still fails after a malicious checksum refresh because values are recomputed.

study.verify_bundle similarly reconstructs raw counts/audit from frozen normalized inputs. validation_check implements an independent analytic EPSG:6933 formula instead of calling the application calendar to agree with itself. Preserve that separation.

## Useful verification commands

```bash
uv run python -m fireatlas.regional_study verify path/to/regional.zip
uv run python -m fireatlas.mask_review --case park-2024 --template /tmp/native-review.json
uv run python -m unittest tests.test_study tests.test_regional_study tests.test_validity tests.test_validation_check tests.test_masks
```

The template command writes a blank form; it does not complete human review. Verify current CLI help before preparing optional native downloads. Tests also include test_mcd64_corroboration.py. UI checks include verify_native_mask_status.py and verify_workspace_polish.py; existing reports are dated evidence, not current acceptance.

## Qualification pilot successors

`opportunity.py` follows CMR SearchAfter pagination, records page identities/hit counts/geometry/orbit/companion candidates and marks changing, duplicate or incomplete inventories incomplete. Candidate acquisitions include those without positive FIRMS rows. Ledgers separate export completeness, native centroid state and validated opportunity; full-cell opportunity unknown and no-pass disabled until supported geometry and independently checked examples exist. `rematch` independently reruns deterministic1:1 matching for30/60/90 minutes; native grid/confidence sensitivity reaggregates class counts and rematches. Confusion/positive Jaccard/directional denominators are explicit. Connected shared-granule bootstrap groups avoid treating adjacent cells as independent. Timing conditions link evidence; no physical causes assigned. `research_review.py` validates raw native documents against actual evidence with the existing30sample validator, plus method/conclusion and five-person task-study gates. No synthetic tests or model-generated signatures count as human review. Day/night and full-opportunity subsets remain unassessed.

## Polygon and all-state successors

`coverage.py` intersects complete candidate CMR inventories with fully interior pilot cells; envelopes freeze their inventory and are self-contained recounts. Pixel-boundary mode requires explicit boundary origin, original native class/file/geolocation/centre binding and quality; STRtree queries and cell/pixel/vertex/contact caps bound work. Unknown quality/classes 0 and 6, partial coverage and conflicting masks stay unknown. Calculated states do not admit validated opportunity or no-pass. Actual local files currently supply centres, so provider-boundary and independent geometry review remain unresolved.

`disagreement.py` independently rematches all sampled states at30/60/90 minutes and records cloud/quality/timing conditions around positives with original hashes. Its state matrix is distinct from usable-only confusion counts. Mask states are recounted from class counts; UTC intervals and file hashes are required. Physical causes stay unresolved. Immutable gzip evidence and compact summaries are exposed through the existing qualification reader/API and integrated acquisition tools. `tests/test_transfer_coverage.py` covers synthetic geometry, authentic-sample binding, unknown/partial/overlap states, recount tampering and matching boundaries.

`group_uncertainty` sums integer category totals per connected group for identical seeded draws; it reproduces expanded-cell bootstrap fractions without repeatedly materializing the cells. `interval_distance` caches exact datetime differences across repeated cell samples; every threshold still independently recomputes matching assignments. Synthetic tests and an independent authentic-input comparison check equivalence. This does not change dependent-group or acquisition-time limitations.

## Native angle/quality sidecar

`native_context.py` and `scripts/native_context_pipeline.py` add exact, original-hash-checked solar/sensor zenith and raw geolocation flags at stored native line/sample positions. Required SDS scale/range/fill metadata, dimension equality and original coordinate/class agreement prevent inferred alignment. The original store remains read-only; native offset zero is required. Missing originals retain unavailable support, and invalid/fill/boundary/unsupported flags remain unknown. The85degree day/night split is a common diagnostic, not a native product flag; MODIS nonzero flags are not decoded without a supported definition. Raw flag-zero and40degree viewing subsets are diagnostic filters, not validated quality or opportunity.

Each pixel subset is reaggregated and independently rematched at30/60/90minutes, retaining actual confusion/directional/positive-union and connected-group support. `verify` recounts all statistics from frozen raw values; publication additionally binds every original store sample and refuses synthetic cases. Bounded deterministic gzip artifacts share the10GB/20GBfree campaign budget and atomic writer lock. Original native methods and releases are unchanged. `tests/test_native_context.py` checks subset reaggregation, scaling/fill/boundary/unknown flags, missing originals, dependence support, exact endpoints and tampering. Authentic Park/Grove extraction is separate from synthetic engineering tests. Full-cell coverage, no-pass and independent scientific processing approval remain open.

## Tiled native opportunity successor

`opportunity_frames.py`, `opportunity_review.py`, `protocols/native-opportunity-v2.0.1.json` and `scripts/opportunity_pipeline.py` add an isolated bounded fixed-region/pilot frame contract. Raw CMR page bytes and pagination/hit counts are recounted; provider boundary transcriptions bind originals and require independent source/completeness review. Actual original SDS coordinates/classes/raw flags/fill/dimensions must reproduce before authentic qualification. Candidate envelopes or native centres never become full-cell coverage. Partial, conflicting, missing-quality and UTC-ambiguous states remain unknown. A separately checked no-pass example is required in addition to complete inventory and adequate geometry. Regional date/tile coverage rejects overlaps and adds missing ROI area to unknown; a pilot cannot qualify a region. Synthetic/AI review cannot admit opportunity. No current UI/API/publication changes or historical bridge admission are claimed for this successor. See [the execution guide](../qualification/OPPORTUNITY.md) and `tests/test_opportunity_frames.py`.

The source-bound `transfer_opportunity.py` successor rebuilds regional reports from exact campaigns and requires original re-extraction for qualified file-bound evidence. It restricts native platform support to the requested region/cohorts, retains missing geometry groups, and separates dependent acquisition-cell samples from regional day-area coverage. An unsigned/AI/synthetic review cannot satisfy either protocol or bound conclusions. `tests/test_transfer_opportunity.py` includes absent-platform, foreign-pilot, unknown/missing/date, tamper and streaming/path cases. No new published opportunity/transfer family is enabled yet.

The successor publisher now verifies a counted `successor-evidence.json` index and all registered opportunity campaign parts and transfer dependencies. Pilot summaries preserve missing date/cells as validated unknown, with separate candidate groups, native granules and boundary-pixel counts. Exact original campaign/packet gzip bytes are streamed into the manifest rather than recompressing or assembling a giant case object. Pending count captures may be renewed when the count hash changes; prior reviewed support or signed conclusions cannot silently inherit a new count result. Symlinked namespace escapes and overlapping campaign parts are rejected. This exposes evidence and closed gates; it supplies no new scientific approval.

`experimental_pixel_geometry.py` is an isolated, bounded 3×3 geolocation-center midpoint model for research. It checks native product/time/version identities, scan-seam/array edges, flags/fill and invalid or folded geometries, and keeps every result marked modeled, not provider boundary, validated opportunity or no-pass. Optional `verify_original_files` checks hashes before and after rereading the supplied nine centers, mask/flag arrays, dimensions and fill; it does not establish scan topology or physical footprints. The method and library environment are not yet frozen for persistent public artifacts. `scripts/experimental_geometry_sample.py` produces one local JSON sample with original binding and requires system GDAL/NumPy plus pyproj/Shapely. A real MODIS sample modeled and rebound; a real VIIRS sample remained unresolved because quality fill metadata was absent. Reference geometry, uncertainty validation and independent scientific review remain missing.

Transfer-original verification is available with `scripts/verify_transfer_provenance.py`; it accepts an exact frozen input or count experiment, JSON or gzip, and produces a hash-bound local receipt. It reopens source bytes and rejects changed notices/month eligibility, tampering, omitted rows, mixed versions and invalid request chains. Positive results cover only the exact captured scope and current database snapshot; original source records and local receipts are not provider-origin signatures, observation opportunity or scientific approval. Historical readiness remains separately non-deployed and currently does not automatically consume these receipts.

The qualification publisher can register exact-input transfer-provenance receipts. It reopens the stored receipt, verifies its hash and identity, independently reruns the original-file chain against the captured input and only then includes the receipt and source status in a new release. Changed input identities remain pending; corrupt or nonreproducible registered receipts fail publication. The Research selector switches its own status and receipt link together. Local source-chain verification is not NASA-origin authentication or scientific qualification.
