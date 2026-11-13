# 10 — Static delivery, builds, configuration, and verification

## Render/Vercel submission delivery

If Render checks out legacy `3ce3224` and reports a missing Dockerfile, the new
files have not reached the selected Git branch. The isolated
`codex/free-render-demo` deployment branch contains the authored runtime and
root configs; select that branch on Render (and Vercel) after it is pushed.
Keep Root Directory empty and Dockerfile Path `./Dockerfile`. This preserves
the dirty working branch and its generated deletions. Build the isolated
checkout to detect accidental dependence on uncommitted local files. Docker
and Vercel ignore rules explicitly re-exclude parent directory contents before
allowlisting nested public files, preventing broad parent reinclusion.

`docs/DEPLOYMENT.md` is the deployment runbook. The root multi-stage Dockerfile
builds authored Studio source in a fresh Node22 image (including the audience
template and camera module imported outside `studio-app`), then runs pinned
Python3.12 assistant dependencies with Node/native export helpers. `.dockerignore`
excludes prebuilt Studio output, secrets, local databases and large `site/` data.
It includes curated public reference documents and only the small public Park
platform/replay files used by the existing welcome example.
`render.yaml` selects the Free instance with no persistent disk or paid resource.
`hosted.py` uses ephemeral `/tmp/fireatlas` storage and initializes a new store
from authentic bundled inputs. `vercel.json` builds only an origin-validated
entry HTML via `scripts/build_vercel.mjs`; `.vercelignore` limits CLI inputs.
Vercel's `FIREATLAS_RENDER_URL` is public; provider secrets belong only on Render.

Focused checks: `.venv-assistant/bin/python -m unittest tests.test_hosted -q`,
the two gateway regressions below, and `docker build -t fireatlas-submission:local .`.
Real image startup, owned save/reload, native export/restore and package recovery
after a fresh instance are separate from mocked HTTP tests. Free Render does
not retain server-side boards/assets across redeploy/restart/idle spin-down;
downloaded native packages provide sharing and recovery. Prior 2GB/disk tests
do not establish free-tier resource or persistence behavior.
Actual hosted integration and provider availability remain post-deploy checks.
`scripts/prepare_submission_demo.py` strips conversation/discussion from an
inspected native starter and regenerates integrity hashes; scientific result
and drawing bytes are preserved. Its checked ZIP and provenance are intentional
versioned public demo assets; generated Vercel output/runtime stores are ignored.

[Context entry point](../../CODEBASE_CONTEXT.md) · reviewed 2026-10-27

## Authored versus generated

| Location | Meaning / edit policy |
| --- | --- |
| fireatlas/*.py, assistant/, studio/ | Python application and scientific source |
| fireatlas/static/ top-level HTML/JS/CSS | Authored analytical UI |
| studio-app/src/, scripts/ and package/lock/config files | Authoring editor and export-helper source |
| fireatlas/static/studio-assets/ | Generated versioned Vite/Excalidraw output; do not patch hashed chunks |
| studio-mcp-app/src/ → fireatlas/static/studio-mcp/ | MCP Apps source → self-contained generated resource |
| studio-render/ | Authored render adapters and fixtures |
| site/ | Committed frozen publication, including copied UI/assets and scientific namespaces |
| fireatlas/samples/ | Bundled authentic/synthetic-supporting artifacts with explicit provenance, notices, calibration and evidence metadata |
| NASA_data/, data/, .env.* | Ignored local input/state/private configuration |
| docs/implementation/, docs/UI_Review/ | Historical acceptance/reports/screenshots; evidence dates matter |
| docs/winning-plan/, PRD.md, PROJECT_DETAILS.md | Planning/project context, not automatic proof of implemented behavior |
| docs/Website_UI_Design_Handoff/ | Reference handoff copies, not live UI source |

Large binary imagery, source archives, dependency/vendor code, screenshots and published data are intentionally outside the symbol index. Their **role and owners** are documented here and in segment guides; do not paste them into an LLM context window.

## Runtime setup

pyproject.toml defines Python >=3.10, core pyproj/pyshp dependencies, optional masks and assistant extras, package data and the fireatlas CLI. uv.lock and requirements/assistant.lock pin runtime inputs; assistant extra markers require Python >=3.12. requirements/studio-voice.txt is a separate optional offline speech runtime.

The launcher uses .venv-assistant plus .env.assistant when present; otherwise uv's project environment. It passes --no-showcase for an existing default scientific DB. A clean clone can load its authentic bundled sample through normal startup; it does not contain the owner's complete NASA archive.

CI's install sequence includes Node 24, npm ci --prefix studio-app, Python 3.12 with uv sync --frozen --all-extras, then the assistant lock. These are repository configuration choices. Do not invent newer dependency recommendations when describing them.

Key settings are named in assistant/provider, Studio capability, rendering, room and settings modules. Secret values are private; the generated manifest records only source-referenced Python key names. Optional integrations include keys/pricing for AI/speech, FIREATLAS_STUDIO_ORIGIN/FIREATLAS_ASSISTANT_ORIGIN, tldraw public license configuration, Liveblocks server secret, local-render/video/voice selection, Remotion acknowledgement, and operator-configured Miro/MCP connections. Capability APIs are more reliable than assuming that a setting is active.

## Studio build chain

```bash
npm --prefix studio-app ci
npm --prefix studio-app run typecheck
npm --prefix studio-app test
npm --prefix studio-app run build
# Optional MCP Apps resource:
npm --prefix studio-mcp-app ci
npm --prefix studio-mcp-app run build
```

The Studio build replaces its output directory. postbuild copies fonts and writes stable studio-entry.js/excalidraw-entry.js, features.json and studio-manifest.json with per-file SHA-256. assets.StudioAssets serves only allowlisted files. An absent manifest empties the allowlist even when some hashed chunks still exist.

For an isolated whiteboard-only refresh, build from `studio-app/` with Vite's `--outDir` pointing to a new temporary directory, then run `python3 scripts/refresh_whiteboard_assets.py /path/to/stage`. The script traverses the Excalidraw entry's static/dynamic manifest dependencies, refuses differing existing hashed files, and merges the required assets and new whiteboard bootstrap into both local and static output manifests. It retains the Studio entry and existing generated-asset deletions. This is not a full Studio/SDK rebuild.

The read-only Park investigation is generated into local and static HTML/CSV files with `python3 scripts/build_park_whiteboard_example.py`; pass `--check` to verify both copies against the existing published Park case records. The builder checks NOAA publication hashes and recounts July 27 map points against the table. The separate example does not rewrite the frozen source bundles or private boards.

At the 2026-10-27 study, generated Studio files were already deleted in the worktree. This documentation task did not rebuild or restore them. Recheck Git status before deciding whether a build belongs in your task.

## Three scientific publication namespaces

| Namespace | Contract / lifecycle |
| --- | --- |
| site/data/v2/ | Original frozen evidence/globe/calendar ledger; inspected snapshot date 2026-10-01 |
| site/data/analysis/ | Separate harmonized analytical release; inspected snapshot date 2026-10-04 |
| site/data/combined/ | Separate generic-union calendar reference, fireatlas-combined-static-v1 |
| site/data/replay/ | Named replay snapshots for the static experience |

Data namespaces are not interchangeable based on directory name alone. Meta markers route analytical controllers to analysis and preserved evidence to v2. Frozen manifests preserve actual data dates; refreshing UI must not relabel observations as current.

export_static.py builds a complete fresh staged static output and refuses existing output. export_analytical.py uses SQLite backup, creates isolated analysis calendars/calibration/history/source rows/exact bundles, and refuses an existing target namespace. An isolated analytical export alone is not a complete served website; it needs the frozen evidence/UI scaffold. export_combined.py prepares the raw-union reference namespace.

refresh_static_assets.py copies current presentation assets while retaining frozen observation data/dates and the protected landing boundary. It can remove stale generated chunks, so it is not read-only. check_landing_preservation.py and the baseline file define protected landing assets/HTML outside the editable header.

The large Punjab–Haryana regional ZIPs are stored as checksummed transport parts. static_bundle_storage.py reconstructs exact ZIP bytes (and can prune redundant parts for publishing). Restored URLs and archive hashes stay stable. Do not commit a regenerated enormous archive over the transport mechanism.

## Explore raw archive publication

`python scripts/export_explore.py --db data/fireatlas.sqlite3 --site site` writes a new, separate `site/data/explore/` namespace and refuses overwrite. Defaults cover both fixed regions, joint/MODIS/S-NPP sources and 2006–2026 (126 calendars). It works from a temporary SQLite backup, rejects synthetic batches, calls `core.calendar`, and adds Python-derived per-month eligible raw-row summaries. Files retain source evidence and hashes; the manifest records byte hashes, supported years/sources and a release identity. Publication is staged before moving into place. Original `combined`, `analysis` and `v2` namespaces are preserved. If intentionally rebuilding this new namespace, retain or move the previous publication before rerunning; do not relabel old data dates.

The browser loads one raw year/source result plus its separate, capped analytical point bundle. Run `tests.test_explore_export` for schema/source/unknown-state checks, atomic failure/no-overwrite/synthetic boundaries, full inventory hashes and parity with the existing combined outputs. Browser acceptance must exercise real Explore, including visible map/month bars/day calendar, applied controls, source and date restoration, unsupported scopes, failed loads, optional imagery and responsive widths; testing the monthly comparison alone is insufficient.

## Monthly comparison publication

`python scripts/export_comparability.py --db data/fireatlas.sqlite3 --site site` writes only `site/data/comparability/`: both regional input/result bundles, both derived native cases and their byte/hash manifest. It uses a read-only transaction for regional capture and original frozen native ZIPs for cases. It can replace this new namespace; it does not rewrite the older evidence releases. Run the documented UI refresh after authored page changes, then use `python scripts/verify_comparability_ui.py` with the prepared assistant/browser runtime to exercise source fixture mode and the actual static website under `/site/`. The verifier follows the legacy bookmark into Research Comparison and tests native diagnostics separately in Evidence Validity. `tests/test_comparison_integration.cjs` checks subpath bookmark translation and independent experiment/native/observation identity round trips. The mentor status, original assessment and evidence JSON are published through the same allowlisted documentation copy path as AI disclosure.

Reproduction commands: `python -m fireatlas.comparability verify site/data/comparability/norcal.json` (repeat for punjab-haryana) and `python -m fireatlas.comparison_evidence verify site/data/comparability/cases/park-2024.json` (repeat for grove-2025). `tests.test_comparability` checks publication byte hashes and recounts against current derivation code, catching stale exports. Statistical recounts do not authenticate NASA downloads or establish independent scientific acceptance.

## Release workflow

.github/workflows/ci.yml runs on PR/manual/reusable calls: checkout, assemble archives, install locked runtimes/helpers, Python tests, top-level JS syntax, then fresh-clone smoke_test.sh.

pages.yml runs on main push/manual: requires CI, assembles archives, records deployment revision, checks release size/integrity, installs browser tools, verifies project-subpath workspaces, Park/Grove historical evidence and globe, then uploads site/ to Pages. A local test pass is separate from CI, publication, hosted integration and independent review.

Useful commands (choose for the change; do not run costly exports just to update prose):

```bash
# Core test entry point and CI runner:
uv run python -m unittest discover -s tests
uv run --no-sync python scripts/run_ci_tests.py
# Small browser-logic tests:
node --test tests/*.cjs
# Renderer fixture suite:
npm --prefix studio-render test
# Read-only source/static parity and protected-landing checks:
python3 scripts/check_jarvis_release.py
python3 scripts/check_landing_preservation.py
# Source-only context freshness:
python3 scripts/update_codebase_context.py --check
```

Full assistant tests need the configured optional runtime. The exact CI dependency installation is in the workflow; uv --no-sync intentionally uses an already prepared environment.

## Verification matrix

| Area | Automated source tests | Further acceptance scripts |
| --- | --- | --- |
| Import/scientific core | test_phase1, test_archive*, test_hms, test_pilots, test_aggregates | smoke_test, scientific preservation |
| Calibration/calendars | test_calibration, test_calendar_v2, test_regional_study | verify_calendar_verdict, verify_calibration_ui |
| Research/replay/globe | test_research, test_replay, test_globe, test_archive_overview | verify_workspaces, verify_globe_reveal |
| Native evidence | test_masks, test_validity, test_validation_check, test_mcd64_corroboration | verify_native_mask_status; separate human review |
| Assistant/MCP | test_assistant, test_studio_assistant, test_studio_mcp, test_studio_prompts | verify_jarvis_tool_routing, verify_jarvis_presets |
| Studio persistence/export | test_studio_store/http/portability/landscape/workflow_rooms/miro | verify_studio_browser, verify_canvas_handoff, verify_jarvis_portability |
| Media | test_studio_story/local_voice/resources, test_story_generation, test_aiand_video; renderer tests | verify_story_progress, verify_native_video |
| Static publishing | test_static_export, test_static_bundle_storage | check_pages_release, verify_static_calendar/data/method/globe/shell, verify_jarvis_static |
| UI interactions | Colocated Studio Vitest tests; tests/*.cjs | verify_investigation_names/deletion, verify_studio_navigation_pan/wheel_zoom, verify_canvas_vegetation, verify_workflow_browser, verify_workspace_polish |

Python test names above are relative to tests/ and omit .py; abbreviated script families refer to scripts/. Read each script's CLI before execution: browser checks can create fixture boards, outputs, temporary hosts and reports. Live provider work, hosted rooms/Miro, licensed SDKs and human mask review require their own evidence.

## Documentation-task verification record

Recorded on 2026-10-27: the source inventory indexes 368 source/configuration/test files; all 14 context Markdown files passed local link checks with zero missing destinations. The generator freshness check passed. Isolated temporary fixtures verified generation, Python class/method indexing, environment key names, source/private/generated exclusions, missing output, same-size source edits, additions and deletions. Only README.md changed among previously tracked non-generated files; existing Studio asset deletions and the pre-existing untracked PDF were preserved.

No fresh application/browser/media acceptance suite was run for this documentation change. Existing acceptance totals in README/reports describe their own recorded runs and must not be reported as tests executed by this context task.

## Immutable qualification publication

`scripts/export_qualification.py` writes a new content-derived `site/data/qualification/releases/HASH/` namespace, deterministic gzip for full native inputs/pairs, verifies a file-byte manifest, then atomically moves `current.json`. Prior releases remain for rollback; old v1/comparability/v2/analysis/explore namespaces unchanged. Approved monthly/daily research results are accepted only after statistical recount, authentic/scope guards and separately evaluated human release admission; absent approval publishes pending records without fitting. `qualification_publication.py` bounds allowlisted file/API reads and preserves exact bytes. The new `/api/v2/{comparability,comparability-inputs,daily,readiness,availability,campaign,acquisition,opportunity,native,native-summary,native-inputs}` routes must not intercept existing calendar/regions/study routes. Refresh authored UI with `scripts/refresh_static_assets.py`; preserve protected landing hashes. New focused tests: `tests.test_qualification`; original scientific/static/Explore/native/API and browser-context regressions remain applicable. See qualification execution/reviewer guides for explicit missing scientific gates.

AI experimental execution is explicit (`qualification_pipeline.py monthly|daily --ai-experimental`), mutually exclusive with human review, and exactly recounted during export. The frozen AI receipt is not independent scientific approval; publications use `experimental-ai-reviewed` and retain support exclusions. No fit runs through an HTTP GET.

The `research` extra pins statsmodels 0.15.0 and shapely 2.1.2, with `uv.lock` updated. New qualification publications include `coverage`, `disagreement`, `transfer`, their compact summaries, `monthly-cohorts`, and hash-named `cohort-monthly`/`cohort-daily`/`cohort-transfer` gzip bundles. Export recomputes summaries and statistically recounts frozen cohort/transfer inputs before an atomic pointer change. Old namespaces/releases remain intact. Coverage envelope exports include original CMR metadata for exact recount. `tests/test_transfer_coverage.py` adds leakage/identity/geometry/quality/concurrency/one-day-fallback checks; synthetic tests are explicitly not authentic accuracy or human review.

Native-context artifacts are optional per-case deterministic gzip sidecars created explicitly with `scripts/native_context_pipeline.py extract`; GDAL/HDF4/netCDF extraction runs under the documented system-Python native runtime. `verify` is available under the research runtime without GDAL. Export repeats raw-sample statistical recount and actual original-store binding before adding `native-context/{case}.json.gz` and `native-context-summary/{case}.json` to the manifest; original releases remain immutable. Exact-byte read-only APIs mirror those families. These files join the shared storage budget; unsupported native fields do not trigger new acquisition or automatic scientific admission. Focused checks add `tests.test_native_context` and the native context lifecycle case in `tests/test_qualification_ui.cjs`.

Each acquired daily bundle also gets a compact `daily-cohorts/{region}.json` index with the same cohort identity as monthly research, retaining model metrics, zero-recovery, seasons and checks. `/api/v2/daily-cohorts` mirrors the frozen bytes. Original native-file extraction is reverified through the system GDAL runtime before authentic sidecar publication; self-contained/store-only verification scopes are explicitly weaker.

Independent rendered review found that an existing static browser could retain an older dynamically loaded qualification.js despite fresh HTML. The authored three analytical pages now reference source-hash-versioned qualification assets, and Research/Evidence register the module before lazy panel mounting. Exact reference tests prevent stale revision strings after edits. Run the normal UI refresh after updating those authored references; protected landing assets and frozen releases remain unchanged.

## Transfer opportunity local evidence

`python scripts/transfer_opportunity_pipeline.py --help` exposes versioned protocol/template/evaluate/verify/admit. Packet indexes use relative paths inside the shared qualification root; gzip packets stream with bounded size, and output uses the common global storage gate/atomic lock. Current authentic pending results are local under `data/qualification/transfer-opportunity-v2/`, not new public API/static evidence. `tests/test_transfer_opportunity.py` is part of the configured science checks. Frozen original count releases stay intact; a future publication must recount the same exact packet/original dependencies before changing its pointer.

Qualification successor exports add `footprint-summary/{case}.json`, `footprint-campaign/{case}.json.gz` (part index), `footprint-part/{result_sha256}.json.gz` (original campaign bytes), `transfer-opportunity-summary/{region}.json`, `transfer-opportunity/{id}.json.gz`, and dependency `opportunity-packet/{sha256}.json.gz`. `qualification_successors.py` recounts registered sources and builds compact summaries; the publisher streams frozen source files through size/hash verification under the shared storage lock before switching the pointer. Read-only `/api/v2/` families match these names, taking `case`, `region`, `id` or `sha256` respectively. An optional `release` query selects a frozen version. Static immutable paths and API bytes share the same manifest and allowlist. Prior namespaces remain intact; missing source evidence stays pending.

Historical readiness successor tests: `.venv-assistant/bin/python -m unittest tests.test_historical_successor -q`. They include forged admission, content tampering, duplicate dates, observation collisions, accepted compact ISO dates and invalid intervals. This is a local fail-closed readiness contract, not a published historical estimate/API or scientific approval.

Experimental midpoint geometry uses `.venv-assistant/bin/python -m unittest tests.test_experimental_pixel_geometry -q` for synthetic checks. For authentic single-sample reads run `python3 scripts/experimental_geometry_sample.py --help`; system GDAL/NumPy must load before any alternate research site-packages. It writes only a bounded JSON response, downloads nothing and cannot qualify observation opportunity. Freeze method source and dependencies before persisting reproducibility claims.

Run `.venv-assistant/bin/python scripts/verify_transfer_provenance.py PATH_TO_FROZEN_COHORT_TRANSFER.json.gz` for a local original-file chain check; defaults point to the separate qualification campaign and its read-only SQLite database. Output is JSON on stdout; no archive writes or provider calls occur. Missing chains produce partial results and tampering fails. Tests: `.venv-assistant/bin/python -m unittest tests.test_transfer_provenance -q`. Snapshot-bound receipts may be retained under `data/qualification/provenance-v1`, but are included only when registered and freshly reverified by the publisher.

Registered source-provenance receipts are rechecked at qualification publication, then exposed as `transfer-provenance/{16hex}.json` and `/api/v2/transfer-provenance?id=...`, with optional frozen `release`. The Research transfer index binds status and exact receipt to its input hash. A new immutable release is required; older releases retain their original bytes and show pending when the field is absent.

Before rechecking a registered transfer receipt, the publisher captures the current exact-cohort database input under its acquisition lock. If the archive has changed, that old receipt is pending rather than attributed to a newer capture. Invalid receipt bytes, database failures and a failed source recount for an unchanged capture remain publication errors; no blanket exception is treated as staleness.

Monthly source receipts follow the same immutable-release pattern at `monthly-provenance/{16hex}.json` and `/api/v2/monthly-provenance?id=...`. Under the exclusive campaign lock the publisher rebuilds the source capture and reopens original evidence for each registered, exact-input receipt; changed inputs or capture leave that cohort pending and changed receipt bytes or a failed recount stop publication. The local API and static route return manifest-verified bytes. Focused checks include `tests.test_monthly_source_provenance`, `tests.test_monthly_source_publication`, `tests.test_qualification_successors` and `tests/test_qualification_ui.cjs`. Previous releases are never rewritten.

To bound peak memory, the publisher runs each registered monthly source recount in its own private worker before loading the full release. The parent holds the same exclusive campaign lock throughout; each worker exits before the next begins. The parent binds each worker result to the exact registered entry and monthly bundle hashes and rereads the registered receipt before publication. A failed worker, changed entry or changed bundle stops publication; missing matching evidence stays pending. `preflight_monthly_publication.py` is an internal worker and must not be used as standalone verification without the parent lock.

The worker records hashes of the original files read and the database and write-ahead log, plus the acquisition-plan filename inventory. Immediately before switching the release pointer, the parent rechecks these fingerprints and inventory. The lock coordinates cooperating writers; sequential checks cannot make the filesystem immutable against writers that ignore it.

Run `.venv-assistant/bin/python scripts/reproduce_daily_numerically.py REGION --versions MODIS_VERSION VIIRS_VERSION --release RELEASE_ID` to refit one exact manifest-verified daily cohort and print a compact exploratory numerical comparison. The fixed tolerances and source hashes appear in the report; on-disk method bytes must agree before and after fitting. It writes no data or scientific admission. Environment metadata is recorded, not assumed identical, and a second machine remains a separate evidence requirement. Check with `tests.test_daily_reproduction` plus the existing daily-model tests.

Run `.venv-assistant/bin/python scripts/diagnose_daily_holdouts.py REGION --versions MODIS_VERSION VIIRS_VERSION --release RELEASE_ID` for an exact-input, source-recounted descriptive report by test year, season and MODIS state. It prints no credentials, does not alter frozen data, and makes no scientific admission. Check with `tests.test_daily_diagnostics`; source hashes before/after the calculation and exact release/result identities are included in each report.

Registered daily diagnostic reports are admitted to a new release only after exact source-release bytes, cohort/result identities, method-source hashes and descriptive metrics are recounted. Changed results or method sources remain pending; tampered registered bytes and mismatched recounts stop publication. Exact original report bytes are available through `daily-diagnostics/{16hex}.json` and `/api/v2/daily-diagnostics?id=...`; prior releases remain intact.

Daily hybrid publication registrations are indexed by exact daily cohort. The publisher verifies the bundle hash, original immutable release bytes and exact input, then independently recounts the hybrid before adding its full gzip and compact summary. A changed daily result makes the prior experiment pending; invalid registration, source bytes or recount stops publication. `/api/v2/daily-hybrid?id=...` and the static release expose identical frozen bytes. The source release remains retained.

Static asset refresh includes the linked native opportunity and transfer-opportunity execution guides as well as the qualification implementation guide, so published documentation links resolve. Historical notes in these guides describe the current versioned pending evidence; they do not promote scientific admission.

Registered `daily-neighbors` bundles are bound to exact original daily publication bytes, region, versions and inputs, and are statistically recounted before a new release is switched. Matching cohort summaries expose screening outcomes, occurrence calibration and the frozen bundle; absent or changed inputs remain pending. `/api/v2/daily-neighbors?id=COHORT&release=RELEASE` and the corresponding static path serve manifest-verified identical gzip bytes. Existing releases and daily admission are unchanged.

Original native angle/flag re-extraction now runs for each case in a separate system-Python/GDAL preflight before the publisher holds the full release in memory. The worker binds the compressed context, original native file inventory and contents, and native store plus WAL before and after extraction; the worker also recounts the statistical result, and the parent streams the verified original compressed context into the new release and rechecks these fingerprints before switching the pointer. Missing contexts remain absent, new or changed inputs stop publication, and the campaign lock coordinates cooperating writers. Sequential fingerprints cannot make files immutable against writers that bypass that lock. `tests/test_native_publication_preflight.py` covers the handoff and source changes; authentic worker runs and complete publication remain separate evidence.

The optional January 2023 MODIS collection comparison enters a new release only after `modis_collection_publication.preflight` verifies the two retained originals and receipts and recounts the result. The publisher rechecks those source bindings before switching the pointer; absent results stay absent. The manifest-bound `collection-pilot.json` is available through the static release route and `/api/v2/collection-pilot`. It is descriptive evidence, not collection-transfer admission. Focused checks cover source tampering, absent/appearing inputs, exact-byte API parity, stale UI responses and source/static asset versions.

After a release containing the collection pilot, `scripts/verify_collection_release.py` takes the campaign lock, recounts retained original files, verifies the selected immutable artifact and manifest, compares exact bytes from the local static and API routes, and checks the release pointer remains unchanged. Its URL inputs are restricted to local HTTP origins. `tests/test_collection_release_verifier.py` exercises source/route mismatch, redirects, lock paths and pointer changes; `tests/test_modis_collection_pilot.py` also exercises synthetic originals through the exporter and real local static/API servers. Actual release verification remains a separate step.

`scripts/register_daily_research.py` registers an exact region/version daily hybrid, similar-day bundle and diagnostics against the current immutable release under the campaign lock. It checks the existing source release and cohort identity, invokes the same successor recounts as publication, binds artifact hashes, retains unrelated index entries and atomically replaces the registration index. The diagnostics copy is hash-named and budgeted. A changed pointer, stale cohort, invalid artifact or unavailable validation prevents registration; no daily estimates are admitted. `tests/test_register_daily_research.py` covers idempotence, index preservation and stale/escaped inputs with mocked scientific validators; real artifacts require their normal recount.

`scripts/refresh_daily_research.py REGION --versions MODIS VIIRS --release RELEASE` runs the existing hybrid, similar-day and diagnostic recounts sequentially for an exact current frozen cohort, then invokes the locked registration command. It limits captured subprocess output, keeps temporary files in the counted work tree with locked budget checks, and checks each scope and closed-admission state. The command does not publish or admit estimates; changing the release before registration rejects the update. `tests/test_refresh_daily_research.py` covers ordering, scope, stale pointers and bounded output using synthetic mocks.

After publishing refreshed daily registrations, `scripts/verify_daily_research_release.py` checks both fixed 6.03/2 cohorts against the manifest-bound daily source, reruns the registered successor validators, compares the exact hybrid, similar-day and diagnostic bytes with both local routes, and checks the pointer did not change. It keeps admission closed. The synthetic verifier test mocks source/recount/HTTP responses; actual release and local-service verification is separate.

## Finding-comparison publication

`python3 scripts/export_finding_comparisons.py` verifies the frozen parent bundles, prepares a complete versioned publication in a temporary sibling directory, and atomically installs a new namespace. Existing v1 bytes are immutable; a differing result requires a new namespace. `site/data/finding-comparisons/v1/manifest.json` hashes the actual region file bytes. The local server explicitly exposes those files and `/api/park-platforms?date=2024-07-25`. Authored and `site/` analytical files must remain in sync. The Studio board and detail view also display disjoint comparison months. Build the React island in a temporary Vite output directory, then merge new content-hashed assets and refresh the entry and manifest without recreating the pre-existing deleted files; retain existing asset files for rollback. Run the typecheck before switching.

Focused checks: `python3 -m unittest tests.test_finding_comparison tests.test_change_aware tests.test_park_platforms tests.test_studio_calendar_capture` and `.venv/bin/python -m unittest tests.test_studio_finding_capture`. These include synthetic tests; they do not constitute the remaining scientific review or new-model evaluation.

`python3 scripts/export_park_platforms.py` stages a separate static Park NOAA-20/21 standard-product publication for July 25–28 and verifies complete export receipts. It does not overwrite v1. The browser verifies compressed bytes against the publication manifest before decompression. NASA LAADS DAAC describes its data products as unrestricted for reuse and redistribution: https://ladsweb.modaps.eosdis.nasa.gov/learn . Focused tests: `tests.test_park_platform_publication` and `tests.test_studio_selected_rows`.

`python3 scripts/build_environment_analogues.py` uses existing native MOD13Q1/NASADEM and the frozen Park replay to stage `site/data/environment-analogues/v1`; it refuses overwriting an existing release. Requires system GDAL and numpy, but makes no network request. `python3 scripts/evaluate_environment_pilot.py` runs a descriptive geographic baseline comparison. Test with `python3 -m unittest tests.test_environment_analogues` and the local Studio test `tests.test_studio_environment_capture`.

Local assistant setup is reproducible with `python3 scripts/setup_local_assistant.py --activate`; the website launcher prefers `.env.assistant.local` and leaves `.env.assistant` untouched. This is a backend/prompt change and does not need a Studio asset rebuild. Run the local configuration and board-view assistant tests with `.venv-assistant/bin/python`. Model integration requires actual Ollama checks separately from mocked tests.

## Submission-day whiteboard scope

See `docs/SUBMISSION_DEMO.md` for the narrowed demo and hosted smoke checks. The public gateway now forwards owned Studio mutations while retaining Studio origin/owner/revision checks and the gateway3MB upload bound. Focused regression: `uv run --python .venv-assistant/bin/python --no-project python -m unittest tests.test_assistant.AssistantTests.test_gateway_ag_ui_stream_and_public_write_boundary tests.test_assistant.AssistantTests.test_gateway_owned_whiteboard_save_retry_export_and_cross_origin_boundary -q`. This exercises local Starlette→loopback HTTP, save/retry/isolation/export/restore, not a real Render/Vercel deployment. Existing built whiteboard assets can be served by the same Python service; a separate static site can link to that service. No deploy is implied by these checks.
