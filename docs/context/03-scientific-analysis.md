# 03 — Scientific analysis, calendars, research, and replay

[Context entry point](../../CODEBASE_CONTEXT.md) · reviewed 2026-10-27

## Contracts that look similar but are different

| Product | Authority | Unit/filter and completeness |
| --- | --- | --- |
| Original rows | core observations; Science.observations | Imported authentic records; native fields; no replay alias deduplication |
| Raw calendar | core.calendar | Distinct occupied common-grid cell-days for selected series; type 0 or missing; official incomplete totals withheld |
| Daily regional aggregates | aggregates.daily_aggregates | Authentic MODIS_SP/S-NPP_SP, type 0 or missing; source-specific cells, bridge union/intersection, FRP |
| Harmonized calendar | calendar_v2.calendar_v2 | VIIRS-equivalent cell-days; observed S-NPP or explicitly permitted calibrated MODIS estimates |
| Replay | replay.build_case | Authentic standard vegetation observations; alias-aware exact-repeat deduplication; daily occupied cells |
| Research | research.report | Its own row eligibility; overlap/Jaccard/bootstrap and candidate groups; does not inherit replay filtering |
| Landing globe | globe.snapshot/detail/static_bundle | Bounded visual aggregates for the globe; not scientific 1 km harmonization |

A unit/method label is part of a result's meaning. Similar-looking totals are not interchangeable.

## Monthly comparability research surface

`comparability.py` is the authority for the new `fireatlas-monthly-comparability-v1` experiment. It captures authentic standard MODIS/S-NPP rows and request-backed export ledgers read-only, requires every UTC date in a full month, excludes any processing-gap date, and keeps product-version pairs separate. Its raw baseline and adjusted predictions use exactly the same held-out complete months. Nested year holdout refits and selects only inside training years; forward evaluation uses earlier years only. Full-year errors require all twelve complete months. This does not estimate ground-truth fires or equalize observation opportunities.

The declared screening policy admits a bounded retrospective monthly comparison only after minimum month/year evidence and relative log-error improvement. It keeps daily imputation, cross-collection historical transfer, prospective monitoring, prediction intervals and independent review separate and closed. A counterfactual overlap-era source-switch experiment is not proof of the historical 2012 seam. Legacy `calibration.py`/`calendar_v2.py` calculations and evidence schemas below remain available for reproducibility; the new page and assistant comparison path do not offer their daily substitution as a current product.

`comparison_evidence.py` derives Park/Grove confusion tables, positive Jaccard, 30/60/90-minute subsets of original native matches, exact FIRMS acquisition groups, source-specific sampled FRP and granule intervals from the unchanged frozen parent ZIPs. No rematching, missing-pass reconstruction, between-pass activity or mismatch cause attribution is performed. Case diagnostics and regional monthly fits answer different questions. Use `test_comparability` for eligibility, leakage, unknown/zero states, claim units and frozen publication recount regressions.

## Legacy regional harmonization pipeline

1. aggregates.daily_aggregates reads eligible rows and complete source export ledgers. It retains original/excluded counts, versions and provenance; per-source unique cells; common-cell bridge counts; and separate native-resolution/FRP context.
2. calibration.calibrate chooses a version-matched MODIS/S-NPP pair. It fits monthly ratios, annual ratio, or no_harmonization. A monthly factor uses an annual fallback when that month's MODIS denominator is too small.
3. Model selection uses year-grouped validation inside outer held-out years. The held-out selected pipeline and fixed-model scores remain separate. The factor interval uses 1,000 seeded year-resampling bootstraps; the daily gap benchmark and 2012 step diagnostic answer separate questions.
4. prepare_calendar_v2 loads history and calibration once per region, with source/dependency identities. calendar_v2 computes day/month states, baselines, seasons and selected-month metadata.
5. result_identity.identify_calendar binds result_sha256 and release_id to scientific inputs, calibration, horizon and dependencies; presentation verdict wording is excluded from scientific_material.

Key fixed dates: MODIS supported history begins 2006-07-01; S-NPP begins 2012-07-01. The production regional UI/API explicitly supports **2006–2026**, even if input history extends later. Do not silently broaden this by changing a date label.

## Daily and monthly state rules

Observed S-NPP is the primary regional series when its export is complete. Calibrated MODIS is allowed only before the downloaded S-NPP period or for a documented S-NPP processing gap, with complete MODIS export, matching product version, and a ready calibration/model. An ordinary missing S-NPP export is not automatically filled.

Days retain value, estimate_type, source_used, quality, reason, evidence_state, coverage_state, partial source cell-days, sensor bridge, and FRP fields. Unknown values remain null. Scaled days expose scale_factor and scale_interval; low/high prediction bounds are withheld because factor uncertainty is not a validated daily prediction interval.

Monthly totals require every UTC day to have a known value. Composition distinguishes observed/scaled/mixed/unknown and records partial data separately. Comparable historic months must match daily source/estimate composition and product versions. Median baseline needs three comparable earlier years; percentile needs ten. Anomaly is meaningful only when the current total and comparable baseline exist.

Season context uses cumulative 10%/90% activity dates and a 15-day peak window, subject to missingness gating. These are descriptive activity timing measures, not ignition or operational season forecasts. briefing.py and harmonization.py turn the existing calendar into derived explanatory products; neither is a second numerical authority.

## Replay versus validity cases

replay.py defines Park, Camp, Grove, plus bounded custom studies. build_case produces daily frames, cell geometry, source statuses, original observations and audit totals. Detailed replay spans at most 31 UTC dates; assistant replay additionally refuses more than 10,000 raw rows. It does not substitute a sampled total when the requested scope is too large.

A named replay box/window collects observations around an incident, without assigning them to a validated perimeter. validity.py has a separate Park/Grove case catalog and different windows. Do not unify these dictionaries just because case IDs overlap.

Replay persistence counts distinct observed dates at cells. Comparison labels are newly_observed, repeated, and not_observed_again. None establishes physical spread or extinction. FRP requires a single sensor; joint FRP is disallowed by normalized assistant context.

## Exploratory research

research.context bounds month, dates, area, distance and day gap. load_records caps input at 10,000. overlap computes same-cell/same-UTC-date co-occurrence, a descriptive VIIRS/MODIS ratio and Jaccard. Its paired-day 1,000-resample bootstrap requires at least ten active days, complete exports and stable product versions; it does not model temporal dependence and is explicitly not sensitivity calibration.

candidates forms connected components of cell-days, capped at 3,000 nodes. Center-to-center distances are geodesic WGS84 distances: EPSG:6933 is equal-area, not equidistant. Transitive chaining can merge distinct events; missing dates can split one event. IDs hash group membership, not an enduring incident identity.

Coverage rates require a compatible fireatlas-coverage-v1 mask: exact grid, bbox, date range, declared synthetic flag, provenance/method, and 1–20,000 unique source/cell/day rows. Status is observed/cloud/no_pass/unknown. A detected cell cannot be labeled non-observed in the supplied mask. Missing mask rows remain unknown; no joint exposure denominator is invented. Authentic and synthetic classes cannot mix. User masks remain labeled unvalidated.

## Module and test map

| Change | Read | Verify |
| --- | --- | --- |
| Grid, raw counts, eligibility | core.py, aggregates.py | test_phase1, test_aggregates |
| Ratios/holdout/baseline/season | calibration.py, calendar_v2.py | test_calibration, test_calendar_v2 |
| Audit/briefing/verdict | harmonization.py, briefing.py, result_identity.py | test_calendar_v2, test_regional_study, verify_calendar_verdict.py |
| Case maps/persistence/alias rules | replay.py, assistant/science.py | test_replay, test_assistant |
| Candidates/overlap/exposure | research.py | test_research |
| Globe-specific display | globe.py, archive_overview.py | test_globe, test_archive_overview |

Test modules live under tests/; verify scripts under scripts/. For a scientific change, review exports, hash identities, static artifacts and assistant facts in addition to the direct algorithm test.

## Qualification successors (2026-10-27)

`qualification.py` loads immutable monthly-v2.0.4/daily-v2.0.5 proposals and validates imported human protocol/conclusion attestations. `comparability_v2.py` keeps exact cohorts, whole UTC months, chronological training before Y-2, calibration Y-2/Y-1, test Y, training-only nested or forward selection, nominal90% absolute-log1p residual intervals, fair calibrated baselines, support/season/zero metrics and full recount. Qualified evaluation requires human protocol approval. The owner-authorized explicit AI-experimental mode binds a separate frozen audit/policy receipt and permits authentic exploratory calculations while top-level performance qualification and release admission remain false. Synthetic inputs cannot enter authentic admission. `daily_estimates.py` separately evaluates identity, annual/monthly ratios and pinned optional statsmodels 0.15.0 hurdle Poisson using only MODIS/platform/season inputs; requires separate support/performance/review. `continuity.py` withholds direct collection/platform transfer and never lets estimates replace observations. Direct bridge evaluation/recount and native footprint opportunity implementation remain unfinished. See `docs/qualification/IMPLEMENTATION.md`; interface presence is not scientific acceptance.

## Direct transfer successor

`transfer.py` and the frozen `direct-transfer-v1.0.0` proposal define a separate exact-source/version collection/platform experiment. Read-only capture preserves original cell unions, platform identities, full-month request ledgers and sensor-notice bytes. Recount rejects changed counts/units/grid/platform/ledger/hash scope. Core deduplication means a verified export establishes completeness rather than exclusive import-batch ownership; stored same-version snapshots may contribute to the union. Forward folds use earlier training and two intervening calibration years; backward folds explicitly use later training/calibration as retrospective transfer. Proposed numerical screens remain separate from human review and regional opportunity-change qualification. `continuity.direct_bridge_check` recounts the evidence and keeps unsupported bridges closed. First real collection checks have no verified direct overlap; no historical bridge is admitted.

The full regional campaign controller can separately assess acquired exact cohorts, preserving each monthly/daily bundle and an index. It never pools old/new collections. Research exposes these as separately selected experimental results. A successful calculation or independent engineering review cannot satisfy scientific review, supported opportunity changes or historical truth.

The campaign controller also invokes direct transfer capture/evaluation for actual standard collection changes and S-NPP→NOAA-20/21 version pairs, with separate first-inspection records and `cohort-transfer` reproduction files. Missing platform cohorts remain unknown rather than assigned assumed versions. No result is inherited from the regional MODIS/S-NPP model.

The acquired 6.03/2 assessment now has 131 complete months and five chronological monthly test-year groups (60 test months) in each region; both proposed numerical screens pass, while AI-only scientific admission remains closed. Daily experiments have six groups/2,191 dates per region but fail performance checks. Read current hash-bound cohort artifacts for exact metrics; these inspected historical results are retrospective. Research exposes actual monthly raw/adjusted errors, coverage/width/interval score and gate outcomes separately from qualification.

`monthly_source_provenance.py` and `scripts/verify_monthly_source.py` independently recount a frozen monthly bundle, match its eligible exact-cohort daily centroid-cell counts to a separate MODIS/S-NPP transfer capture, and reopen the original request chain using `transfer_provenance.py` under a shared campaign lock. Missing original chains or no eligible months remain partial; mismatched cell counts, cohorts and tampered results fail. Original plan, receipt and file fingerprints are rechecked at the end, but the check cannot make files immutable against a process that ignores the lock. It covers eligible model cell-day counts only, not raw detection totals, excluded months, provider signatures, observation opportunity or scientific review. The command refits the existing frozen historical statistical experiment for recount; it is not a new blind evaluation. Verify the actual output and provenance before claiming real archives pass this check.

The qualification publisher can register a monthly source receipt against the exact monthly input and result hashes. It rebuilds the source capture and recounts the receipt while holding the campaign lock; changed source captures or monthly inputs leave the selected cohort pending. A receipt checks source reproducibility, and does not promote scientific admission.

`daily_reproduction.py` provides a separate numerical comparison for a refitted frozen daily cohort. Inputs, protocol, reviews, integer counts, partitions and gate outcomes compare exactly; finite floating model results use fixed exploratory absolute and relative tolerances. Changed gates, nonfinite numbers and structural differences fail the comparison. Runtime/fold environments are reported separately, and unsupported folds remain inconclusive. This does not weaken frozen result hashes, establish threshold robustness or an independent-machine result, change failed daily gates, or admit estimates.

`daily_diagnostics.py` separately derives descriptive held-out daily error, occurrence Brier score and interval support from a fully recounted original cohort, by test year, season and MODIS zero/positive state. Exact interval days and covered counts accompany coverage; empty groups remain null. The zero-MODIS/positive-VIIRS group is selected using the reference outcome, so its Brier score is descriptive rather than a calibration assessment. Counts represent observed sensor cell-days, not fire truth; year groups are not independent cells and no uncertainty interval is manufactured.

## Direct-transfer opportunity admission successor

`transfer_opportunity.py` / `protocols/direct-transfer-opportunity-v2.0.0.json` wrap the unchanged v1 count experiment. Full eligible-month UTC dates, exact ordered cohorts and fixed region require recounted source campaign/regional reports; missing/duplicate/foreign scope cannot become a passed flag. Seasonal regional area and per-platform acquisition-cell support remain separate; standard declared platforms stay required without positive detections, geometry failures remain explicit, and independent protocol/conclusion/original checks are separate. Named count-composition summaries aid review. Admission applies to recounted overlap only; historical deployment/forecasting stay closed. See [execution and remaining historical work](../qualification/TRANSFER_OPPORTUNITY.md).

`historical_successor.py` is a separate monthly historical-readiness recount. It rebuilds per-cohort counts from the exact transfer input and canonical UTC dates, rejects duplicate/colliding estimate candidates, malformed scope/hash/uncertainty and tampered overlap evidence. Original source CSVs are not reopened: row/result provenance explicitly reports asserted fingerprints, not verified authenticity. Candidates are always withheld; overlap review alone never admits historical deployment. The frozen `continuity.historical_record` helper accepts caller-provided flags and must not be used as a deployment gate. No current production caller is known. A separately frozen model, source-era opportunity, applicability and independent review remain required.

## Daily hybrid exploratory successor

`daily_hybrid_experiment.py` defines two fixed retrospective candidates: on MODIS-zero dates use the existing hurdle prediction; otherwise use the annual or month-specific ratio. All four prior methods remain comparators. Earlier training years, subsequent calibration years and later test years remain disjoint within each fold. Nominal 90% log-residual intervals are separately calibrated for MODIS-zero and positive strata, with insufficient strata excluded; intervals remain empirical under temporal dependence. `scripts/evaluate_daily_hybrid.py` accepts an exact manifest-verified frozen AI-experimental cohort, verifies nested scope and recounts it before fitting, then writes a new hash-named, globally budgeted bundle without changing existing results. This is a post-inspection exploratory proposal, has no human scientific approval or release admission, and produces no synthetic locations. Inspect its frozen protocol and source-bound AI policy for limits and actual gates.

`daily_neighbors_experiment.py` adds a separately frozen retrospective research candidate: the mean and positive fraction of 64 fixed-feature nearest earlier training dates. It reuses the hybrid experiment's exact chronological folds, eligible dates and independently calibrated baseline intervals. Candidate intervals use the same prior-year zero/positive strata. It evaluates the existing proposed gates against identity, ratio and hurdle baselines, retains hybrid comparisons, and never admits daily estimates. Previously inspected dates are development evidence, not blind confirmation. `scripts/evaluate_daily_neighbors.py` requires an exact frozen daily cohort and writes a separate budgeted bundle; `tests/test_daily_neighbors_experiment.py` exercises chronology, target leakage and statistical recount. The method's source hashes and fixed choices are in `protocols/daily-neighbors-v1.0.0.json`.

## MODIS collection overlap pilot

`fireatlas/modis_collection_pilot.py` compares the original January 2023 C6 and C61 global MCD14ML files as a descriptive one-month pilot. It filters type 0 rows to each fixed region, assigns centroids to the existing 1 km EPSG:6933 grid and reports per-UTC-day shared, collection-only and union-based Jaccard counts; platform-specific row counts remain separate. Empty unions have null Jaccard. The pilot does not qualify a collection bridge or establish observation opportunity. `scripts/compare_modis_collections.py` takes the campaign lock, rechecks original download receipts and source hashes before and after computation, enforces the shared storage gate, and writes a result-hash-named artifact. Synthetic tests are in `tests/test_modis_collection_pilot.py`.

The optional `modis_collection_publication.py` preflight reopens both original archives and receipts, independently reconstructs the result, and retains exact provenance for a final source check before a release pointer may change. A source-bound artifact is not scientific or historical-transfer approval.

## Multi-month collection research (in development)

`modis_collection_series.py` provides a separate calendar-aware monthly recount for MODIS collections, retaining the frozen January pilot. It handles real month lengths, exact UTC month validation, type-0 cell-day sets, source-specific platform counts and null empty-union Jaccard. The separate `scripts/acquire_modis_collection_series.py` and `scripts/compare_modis_collection_series.py` add provider-file discovery, bounded downloads, resumable receipt checks and original-file recount under the campaign lock. The public SFTP client requires a Python environment with pexpect. Authentic multi-month acquisition, publication and independent engineering review are not yet complete for this successor. It does not qualify a collection bridge or establish observation opportunity.

## Two-period finding and experimental model

`fireatlas/finding_comparison.py` derives same-calendar-month, exact-version-cohort pairs from the existing comparability bundle. Differences, zero denominators and direction are computed in Python. The publication result hash covers canonical JSON before adding `result_sha256` and the parent file hash; the manifest separately hashes the final delivered bytes. `published_pair` resolves one forward pair and verifies both identities. The first and second adjusted values retain their respective model/training years.

`fireatlas/change_aware.py` is an isolated, synthetic-tested experimental log1p monthly fit with seasonal offsets, a shared MODIS slope and a consecutive-year same-month change term. It rejects training rows at or after the held-out year. Its explicitly marked synthetic-fixture fold checks chronological training/calibration/test separation and compares identity, annual and monthly ratios, and fixed log offset, but it has no real-data evaluation, published predictions or human protocol approval; do not treat it as an admitted product.

`fireatlas/park_platforms.py` reads the separate qualification campaign database in read-only mode, bounded to the Park box and July 25–28, 2024. It retains standard NOAA-20/21 identities, original record hashes and complete request evidence, and leaves missing requests unavailable. It does not import records into the scientific store.

## Environmental analogue pilot

`scripts/build_environment_analogues.py` reads two native MOD13Q1 A2024177 NDVI and reliability bands and NASADEM terrain zips, warps to a bounded 0.1° Park grid, and records medians on quality-filtered resampled raster pixels. MODIS standard replay detections are counted July 25–28, 2024, after the June 25–July 10 composite. `environment_analogues.matches` ranks non-neighboring cells by equal-weight IQR-scaled Euclidean distance of NDVI and elevation. It is same-period spatial matching, not historical event matching, fire/no-fire controls, cause attribution or forecasting. Zero detections leave observation opportunity unknown. `scripts/evaluate_environment_pilot.py` compares absolute detection-count differences with geographic neighbors; this single-event descriptive check is not independent validation.

## Imported-profile candidates for Investigation

`historical_similarity.match_imported_profiles` compares daily shares of authentic imported, standard-processing records from one sensor. A reference is 2–14 UTC days with records on every date. Candidate windows are contiguous, equal-length intervals in the existing NorCal and Punjab–Haryana regional archives (at most 26 search years). The calculation excludes demo batches, retains original record counts before alias deduplication, excludes windows overlapping the reference in an overlapping boundary, ranks Euclidean profile distances, and returns three non-overlapping candidates. Missing dates are excluded, never zero-filled. Dates, source, boundary, raw counts, search coverage and distance accompany the result. This is descriptive temporal-profile matching; differing regional areas, import coverage and processing can affect counts. It establishes neither incident identity nor shared environmental/human causes, and is not an exhaustive worldwide search. Tests: `tests/test_historical_similarity.py`.

The new `context_publication` adapter in `environment_analogues.py` verifies the existing Park publication against its manifest before exposing NDVI/elevation cells. It does not change the existing analogue pilot or scientific release.
