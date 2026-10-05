# Ignis-Atlassia analytical implementation report

Implemented and checked on 5 October 2026. Reference checkout: `9e9f682307be01a340d80b98d05b1ed78fe638c8`. Changes remain in the working tree; no deployment, push, external messages or paid provider calls were performed.

## Delivered routes

| Destination | Canonical route | Retained compatibility files |
| --- | --- | --- |
| Earth overview | `/` | `/index.html`; logo destination |
| Explore | `/atlas.html` | Atlas links and recognized landing calendar fragments |
| Investigate | `/investigate.html` | `/replay.html`, `/assistant.html` |
| Research Lab | `/research.html?tab=comparison` | Candidate and exposure pages infer their corresponding tabs |
| Evidence | `/evidence.html?tab=sources` | Data → Sources; Method → Method; Review → Reproduce/Review |
| Research validation | `/evidence.html?tab=method#research-validation` | `/research-validation.html` |

Research has Comparison, Candidate Groups, Sensitivity and Exposure tabs. Evidence has Sources, Method, Calibration, Validity and Reproduce/Review tabs. Compatibility files preserve query parameters, fragments, explicit tabs and project-subpath hosting. The header has four primary destinations. Analytical pages use scoped, lazy-mounted controllers; the landing keeps its original initialization and shared assets.

Investigate uses the existing assistant desk with one study selector, UTC playback controller, source filters, row inspection, notebook and contextual conversation. Synchronized 2D sensor panes are the default. Optional 3D mounts a separate renderer, uses the applied frame and scale, frames the exact study bounds and disposes its scene when returning to comparison. It does not start the old complete replay controller alongside the assistant controller.

## Landing boundary

[The recorded baseline](landing-baseline.json) protects 75 source/release asset hashes and both landing HTML documents with their header removed. `scripts/check_landing_preservation.py` passes. UI refresh checks the source boundary before writing and checks the target's protected assets and outside-header HTML afterward. Fresh static export also checks the recorded boundary before using the authoritative source assets.

The header retains its original dimensions/classes, mobile button and accessibility attributes. Its compatibility helper handles only the four recognized calendar fragments: `atlas-section`, `calendar-section`, `harmonized-calendar` and `study-workspace`. Ordinary visits retain the original globe behavior and dates.

The original landing was reconstructed from the recorded Git commit and captured under the same browser conditions as the changed page. With the navbar excluded, [original](artifacts/landing-original-restored.png) and [current](artifacts/landing-current.png) images have **zero changed pixels**. External imagery was blocked in this visual comparison to remove network variability. The separate static globe check exercised the frozen source/date filters, location evidence drawer and mobile controls under a project subpath. This is a software regression check, not a claim about current satellite coverage.

## Scientific results and downloads

The calculation definitions remain distinct:

- **Harmonized activity:** observed S-NPP occupied common cells or permitted MODIS-scaled estimates, in VIIRS-equivalent active-fire cell-days. The matching download is `fireatlas-regional-study-v1`.
- **Combined detections:** the eligible daily MODIS/VIIRS common-cell union. Its existing `fireatlas-study-v2` bundle, verifier and 50,000-row limit remain unchanged.
- Replay additionally removes source aliases; Research retains its broader selected standard-source row scope. Raw records, eligible unique detections, occupied cells, candidate groups and native FRP retain their separate contracts.

Regional bundles freeze the exact calibration used by the displayed calendar, complete required standard-source history, original/stored row identifiers and fields, empty export windows, batch/source ledgers, notices, fitting inputs, daily/monthly states, baselines, seasonal outputs, contextual scope and release inventory. Standalone calibration files are not substituted for the calendar's calibration identity. A read transaction and frozen artifact copies prevent combining a cached result with newer inputs. Requested identities that no longer match return a stale-result response; concurrent builds are rejected while one export is active.

The regional verifier requires no live database or current notice/calibration artifacts. It checks the inventory and expansion limits, reconstructs the database, recomputes EPSG:6933 grid assignments, refits the frozen calibration and recounts completeness, daily/monthly composition, baselines and seasonal outputs. Counts, identifiers, nulls and states compare exactly; floating-point comparisons use relative tolerance `1e-12` and absolute tolerance `1e-9`. A changed numeric result with refreshed checksums is rejected by the scientific recount.

Regional limits are 2,000,000 observations, 3 GiB expanded payload, 512 MiB compressed ZIP, JSONL chunks of at most 100,000 rows or 128 MiB, 64 KiB per record and 32 MiB per metadata entry. Serialization checks accumulated sizes and cleans failed temporary output. Downloads are served from completed files; oversized selections are rejected without sampling.

```bash
uv run python -m fireatlas.regional_study build --db data/fireatlas.sqlite3 \
  --region norcal --year 2026 --month 6 --output /tmp/norcal-june.zip
uv run python -m fireatlas.regional_study verify /tmp/norcal-june.zip
```

`GET /api/v2/study` accepts region, year, month, optional day and optional `expected_result_sha256`. The calendar response supplies additive result identity and bundle availability.

| Preserved target | Checked result |
| --- | --- |
| Northern California, June 2026 | 113; 30 observed dates; prior median 109; difference +4; percentile null |
| Northern California, July 2024 | 3450.715794898222; 25 observed and six estimated dates |
| Punjab–Haryana, July 2024 | 221.1958762886598; 25 observed and six estimated dates |
| Northern California, July 2025 | 415; two qualifying prior years; median/anomaly/percentile null |
| Northern California, May 2026 | Unknown harmonized month; no official total inferred |
| Park | 6,224 eligible unique detections; 2,228 joint cell-days; 988 aliases and eight non-vegetation rows removed |
| Camp | 5,644 eligible detections; 1,375 joint cell-days; partial export |
| Grove | Seven eligible detections; four joint cell-days; complete empty dates remain distinguishable from unknown dates |

[Scientific preservation](artifacts/scientific-preservation.json) compared the original and changed calculation code on one captured database scope. Both regions' 2024/2026 daily calendars, calibrations, compositions and baselines, all three named replay frames/summaries, the Grove generic union calendar and Grove research report matched by exact structured equality. Only presentation verdicts and additive identity metadata were excluded from that comparison. The original structured outputs are retained in [the compressed reference](artifacts/scientific-reference.json.gz).

**No numerical method change was introduced.** June 2026's verdict now reports the supported median and difference even though the percentile needs ten comparable years. July 24, 2024 at 05:24 UTC through July 29 at 15:18 UTC remains the documented processing interruption, with all six intersecting UTC dates and partial-day endpoints retained. Eligibility, version matching, null monthly totals, baseline thresholds and withheld prediction intervals remain unchanged. The casebook documentation was corrected to the actual 15 records; the protected casebook file was not changed.

## Applied context, scales and stale work

The analytical `FireAtlasContext` module extends the existing namespace without loading the landing's old `lab.js` initializer. It carries the applied AOI/interval/day/cohort/metric, polygon selection, display settings, method/unit/release/result identity and navigation origin. Public serializers exclude ownership tokens, notebook text and private artifact identifiers. Calendar handoff retains its originating contract while replay reports its own calculation identity.

Form edits remain drafts until applied. Malformed inputs and unrecognized region/case identifiers produce visible selection errors. Camera focus changes display only. Cross-month studies keep their full interval; Research asks for an explicit supported month intersection. Unsupported regional/polygon/cohort selections retain the original scope and show a useful error. Study/tab changes push history; scrubbing and display changes replace it. Back/Forward uses validated restoration.

Heat normalization is fixed over the full selected study and shared between sensor panes. Day changes and source hiding do not rescale it. Geographic Gaussian kernel dimensions remain fixed with zoom. Persistence and single-source native peak FRP retain their own domains/units; joint FRP stays unavailable. Frame-relative contrast requires the explicit “brightness not comparable across dates” setting. Both unit checks and browser checks exercise scale stability.

Inactive tab fetches are canceled and guarded through response-body consumption. A browser test held a returned body, switched tabs, then released it: the old result could neither increment the applied context revision nor repaint the new tab. A tab from one destination is not applied to a different workspace when following a navigation link. Existing assistant tests cover ownership, cancellation, receipts, provider failure and stale browser actions. No provider, voice, gateway or MCP expansion was made.

## Static and local release

The October 1 `site/data/v2/` release and its globe files remain unchanged. New analytical evidence is isolated under `site/data/analysis/`, with its own October 4 manifest and release identity:

`6236a3065af5c3091a0d15ee82bfcabe65abf63e1ab15b24a1f29bec7b9d5297`

Its 97 indexed files total 459,404,228 bytes. All indexed sizes and SHA-256 values were checked. Calendars cover 2006–2026; the namespace includes the exact calendar-used calibration artifacts and four prebuilt regional bundles:

| Bundle | Frozen standard rows | ZIP bytes |
| --- | ---: | ---: |
| Northern California, June 2026 | 229,501 | 20,864,529 |
| Northern California, July 2024 | 229,501 | 20,879,141 |
| Punjab–Haryana, June 2026 | 1,766,258 | 164,490,795 |
| Punjab–Haryana, July 2024 | 1,766,258 | 164,508,016 |

Each has a successful recount record in `site/data/analysis/checks/`. Other static selections clearly state that an exact regional bundle is unavailable. The old static release lacks the full preparation-input snapshot needed to certify exact frozen reconstruction, so matching old totals were not used to relabel its provenance. Legacy native-validity/context evidence retains its older snapshot and actual scope. Separately labeled static combined-calendar outputs live under `site/data/combined/`; they are output JSON, not a substitute for the generic input bundle.

The local service can calculate new bounded studies and generate exact bundles. Static mode retains calendars, named investigations and dated evidence, while custom research and private notebooks require the service. No-key mode retains deterministic calculations; unavailable providers, missing layers and terrain failure preserve useful selection/tables/evidence. Terrain SDK/view initialization is bounded and failure returns to 2D.

## Loading and accessibility checks

[Before](artifacts/before-loading.json) and [after](artifacts/after-loading.json) measurements record completed local response bodies with external imagery excluded. Bytes are measured response-body lengths, not a wire-compressed bandwidth estimate.

| Entry | Before requests / bytes | After requests / bytes |
| --- | ---: | ---: |
| Explore | 29 / 6,470,892 | 25 / 3,167,387 |
| Investigate | 22 / 752,542 | 26 / 1,148,054 |
| Evidence | 19 / 916,685 | 25 / 1,584,838 |

The original capture reused one browser context across old routes; the changed capture used a fresh context per canonical route and opened Evidence's Calibration tab. These are actual observations with different cache/content conditions, not a controlled percentage speedup claim. Explore's initial render does not fetch source archives, history or result ZIPs. Named replay loads only its selected bundle; Evidence loads the active tab's evidence. 3D code is deferred until requested, and result ZIPs are downloaded only on request.

Browser checks covered 360, 390 and 768 pixels, keyboard entry and tab arrows, drawer Escape/focus restoration, reduced motion, labeled sensor shapes, numeric table alternatives, readable legends and absence of horizontal overflow in the tested layouts. The connected terrain check loaded real imagery/common-cell marks, kept the domain through a day change and restored synchronized 2D without changing the study. External imagery failure was also tested separately.

## Executed checks

[The current machine-readable Studio verification summary](studio-checks/verification-summary.json) and the browser artifacts record actual execution. The older [baseline test record](artifacts/test-results.json) is retained for before/after comparison:

- Full Python regression after the resource segment: **305 tests passed** in 295.277 seconds (`docs/implementation/studio-checks/resource-full-python.log`), with no provider calls. Earlier smaller-suite logs remain as historical artifacts.
- Studio resource/lifecycle checks: **24 tests passed** in 13.582 seconds; Studio HTTP checks: **14 tests passed** in 12.728 seconds. These cover actual memory/CPU termination, detached-child handling, restart recovery, storage admission, low-disk rollback and truthful capability reporting.
- Core regional/calendar checks: **18 passed**, including observed/scaled/mixed/unknown states, tampering with refreshed hashes, stale identity, export limits, frozen dependencies and notice-cache invalidation.
- Static export checks after the tooling guard change: **six passed**.
- JavaScript syntax: **74 source/generated files passed**; existing map and checked-visual tests and the new terrain lifecycle test passed.
- Static calendar, data, globe and Park/Grove method verification scripts passed. The globe and aliases were exercised under project-subpath hosting.
- Canonical workspace browser verification passed: route/history/context, mixed and unknown calendars, malformed incoming selections, matching downloads, scales, lazy tabs, cross-workspace tab isolation and narrow layouts.
- Local no-provider browser verification passed: deterministic study loading, draft/applied Research state, candidate table, sensitivity, withheld unsupplied exposure and stale response body.
- Protected hashes/outside-header HTML, analytical manifest inventory and `git diff --check` passed.

Representative commands:

```bash
.venv-assistant/bin/python -m unittest discover -s tests
uv run python -m unittest tests.test_regional_study tests.test_calendar_v2
node tests/test_assistant_map.cjs
node tests/test_assistant_visuals.cjs
node tests/test_investigation_terrain.cjs
python3 scripts/check_landing_preservation.py
uv run --offline --with playwright python scripts/verify_workspaces.py
uv run --offline --with playwright python scripts/verify_local_workspaces.py --base http://127.0.0.1:8074/
uv run --offline --with playwright python scripts/verify_investigation_terrain.py --base http://127.0.0.1:8074/
```

The last two commands require a running local service; the terrain command also requires its external SDK/imagery. Offline `uv` requires installed packages/browser assets.

Live conversational providers and paid speech were intentionally not tested. Independent human mask review, complete validated per-cell exposure, outside-user comprehension studies, public deployment and authoritative 2026 competition eligibility were not performed or certified by these checks.

## Artifacts and demonstration

Representative screenshots are in [artifacts/](artifacts/): before/after calendar, Sensor Bridge, investigation, calibration/reproduction, local Research, connected 3D, terrain failure and 360/390/768 layouts. The landing comparison uses the reconstructed original pair described above. Browser checks and loading measurements are JSON beside the screenshots.

1. Open Explore with no selection: Northern California June 2026 shows 113 observed cell-days, median 109 and difference +4; explain the unavailable percentile.
2. Explicitly select July 2024: inspect the 25 observed/six estimated dates, gap endpoints and unavailable composition-matched baseline; open the Sensor Bridge.
3. Investigate the selected day, or explicitly choose the named Park preset. Compare sensor panes and UTC frames; explain the replay filtering contract and avoid assigning detections to an incident or perimeter.
4. Open Evidence → Calibration, then Reproduce/Review. Download the matching regional ZIP, run the verifier and retain its release/hash identity. Show processed native evidence and pending independent review as separate gates.

To see the new Python routes, restart any service process that was launched before these edits. Existing owner configuration, archives and notebooks were retained. Remaining scientific work requires new source metadata/validated exposure inputs and actual independent reviewer sign-offs; automated tests cannot supply those gates.

## JARVIS orchestration and editable whiteboard delivery — 5 October 2026

[JARVIS portability implementation and operation](JARVIS_PORTABILITY.md) describes the shared recipes, captured instance/pane context, durable checkpoints, real workflow effects, same-tab acknowledgment, command-specific undo, native restoration and editable Excalidraw companion. It also records SVG/PNG/PDF behavior, explicit mocked Miro transfer coverage, static/local differences and remaining external gates. Existing scientific baseline outputs and the protected landing/globe release remain unchanged.

[Final verification summary](jarvis-checks/verification-summary.json), browser/preset/static reports, interruption traces, canonical restoration comparison, screenshots and sample archives are retained under `jarvis-checks/`. Earlier records in this report remain dated evidence of their respective implementation segments.
