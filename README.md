# Ignis-Atlassia — NASA MODIS and VIIRS burning activity calendar

**Challenge:** NASA Space Apps 2026 · Harmonization of MODIS and VIIRS Hot Spots

Ignis-Atlassia is a research prototype for inspecting dated NASA FIRMS active-fire detections and counting distinct 1 km equal-area grid cell-days in UTC. The calendar variant includes FIRMS type 0 or missing, across confidence levels; other rows remain inspectable but are excluded from totals. The home page retains its existing globe. Four analytical destinations share the applied study: **Explore** (`atlas.html`), **Investigate** (`investigate.html`), **Research Lab** (`research.html?tab=…`) and **Evidence** (`evidence.html?tab=…`). Explore opens the regional harmonized calendar; Investigate opens synchronized 2D MODIS/VIIRS panes, with optional 3D. Legacy page URLs forward with their queries and fragments. A hotspot is a satellite thermal observation, not a fire perimeter, burned area, or proof that no fire occurred.

**GitHub Pages demo:** https://AhnafZ778.github.io/Ignis-Atlassia/ — bundled, read-only scientific evidence. JARVIS commands and private Studio authoring require the Python service. [Deployment setup and checks](docs/GITHUB_PAGES.md). Run the full app locally at http://127.0.0.1:8000/.
**Repository:** https://github.com/AhnafZ778/Ignis-Atlassia
**Project handoff:** [FireAtlas Project Brief](docs/FireAtlas_Project_Brief.pdf) · [HTML source](docs/FireAtlas_Project_Brief.html)

## Run

```bash
bash scripts/run_website.sh
```

For the tests:

```bash
uv run python -m unittest discover -s tests
```

## Website design and visual review

The analytical workspaces use a light interface: warm ivory, white work surfaces, dark ink, and cobalt actions. MODIS is amber/circle, VIIRS is cyan/diamond, and shared cells are green/square. Unknown and partial records retain explicit status labels. The landing keeps its dark globe shell, layout and protected assets; only its header/navigation changes.

See the [implemented redesign and screenshot review](docs/UI_Review/README.md) and [page-by-page audit](docs/UI_UX_AUDIT_AND_LIGHT_REDESIGN.md).

Production UI sources are in `fireatlas/static/`. To refresh `site/` after a UI edit while preserving its existing observation data and snapshot date:

```bash
uv run python scripts/refresh_static_assets.py --site site
```

A new data export still uses `scripts/export_static.py`. Static hosting supports bundled evidence; live research calculations and assistant tools require the local service. Map imagery and streamed terrain need network access.

Investigate map loading, historical search and JARVIS requests have no daily turn-count ceiling. The former shared 20-run cap has been removed; existing workspaces retain saved results without a reset. See the [archive search regression report](docs/implementation/archive-run-admission/README.md).

## Exact harmonized downloads

“Harmonized activity” means VIIRS-equivalent active-fire cell-days. Its matching download uses `fireatlas-regional-study-v1`; the separate “Combined detections” view retains the generic union-calendar `fireatlas-study-v2` bundle and its 50,000-row limit.

```bash
uv run python -m fireatlas.regional_study build --db data/fireatlas.sqlite3 \
  --region norcal --year 2026 --month 6 --output june-2026.zip
uv run python -m fireatlas.regional_study verify june-2026.zip
```

The regional verifier needs the ZIP and installed core dependencies. It freezes full required standard-source regional history, the actual calendar calibration, notices, ledgers, baselines and states, then recounts them. Changed results fail even after their checksums are updated. Limits are 2,000,000 rows, 3 GiB expanded and 512 MiB compressed. `/api/v2/study` accepts the displayed `expected_result_sha256`; changed inputs return HTTP 409.

The committed analytical namespace is `site/data/analysis/`, separate from the unchanged October 1 globe/evidence release. Exact static bundles exist for June 2026 and July 2024 in both regions. Other selections explicitly show bundle unavailability. Build a fresh namespace from a captured authentic database, then refresh analytical UI assets:

```bash
uv run python scripts/export_analytical.py --db data/fireatlas.sqlite3 --site fresh-release
uv run python scripts/refresh_static_assets.py --site site
python3 scripts/check_landing_preservation.py
uv run --offline --with playwright python scripts/verify_workspaces.py
```

A fresh analytical export needs the existing frozen evidence/UI scaffold to be served as a full site; it refuses to overwrite an existing analytical namespace. Refreshing UI does not rebuild the globe or scientific evidence. [Implementation report, checks and screenshots](docs/implementation/REPORT.md) records the shipped scope and remaining human/data gates.

## Data and study areas

The committed authentic NASA sample contains 30,823 Northern California MODIS Terra/Aqua and Suomi NPP VIIRS standard-product rows for July 2022–June 2026. In this workspace, 34 sidecar-backed standard FIRMS archive exports have been imported into Northern California and Punjab–Haryana: eight retain original request metadata, while 26 use explicitly reconstructed, row-only sidecars. The local database now retains 1,995,759 stored standard source records across those two study areas (456,202 MODIS and 1,539,557 Suomi NPP), with positive detections as early as July 2006 for MODIS and July 2012 for Suomi NPP. The six newly supplied MODIS archives fill the earlier 2006–2010 history and the nominal 2019–2020 and 2021–2022 MODIS windows. The newly supplied S-NPP 814833 archive adds row-level detections from July 2021 through July 2022. Their request forms are absent, so every reconstructed month remains partial and absent dates remain unknown. This is not a verified continuous archive. The two regions still have 48 complete MODIS source-months and 47 complete S-NPP source-months each from July 2022 through June 2026; S-NPP May 2026 remains unknown.

The calendar is an authentic regional FIRMS detection view, not a fire-perimeter or observation-coverage product. `NASA_data/` and the local database are ignored by Git; a clean clone gets only the committed Northern California sample until the owner-supplied files are imported. See [the data ledger](docs/DATA.md) and [archive import instructions](docs/NASA_DATA_IMPORT.md) for file provenance, missing windows, and the import command. NASA data are not covered by the repository's Apache-2.0 code license.

## Build a static calendar snapshot

After importing the local archive, create a fresh static bundle and serve it locally:

```bash
uv run python scripts/export_static.py --db data/fireatlas.sqlite3 --output site-release
python3 -m http.server 8000 --directory site-release
```

The bundle includes precomputed 2006–2026 calendars, dated history, compressed source-row samples for both regions, complete row-level observation archives split into deterministic sub-100 MB gzip parts, and the Park/Grove validity reports with their checksum manifests, recount results, evidence ZIPs and blank native-review templates. The Data & Method page uses those files directly, so a judge can open the historical case, scrub UTC days, inspect source rows, run the displayed recount, and download the hash-bound reviewer form without credentials or a Python API. It does not copy the SQLite database or the raw `NASA_data/` archive. It is a dated, read-only evidence demo; data imports, new research calculations and private assistant actions require the Python server. The existing frozen globe overlays work in static mode. The GitHub Pages workflow publishes the committed `site/` bundle only after CI, publication integrity and browser checks pass. See [GitHub Pages setup](docs/GITHUB_PAGES.md).

The release checks are reproducible:

```bash
uv run --offline --with playwright python scripts/verify_static_calendar.py --site site-release
uv run --offline --with playwright python scripts/verify_static_method.py --site site-release --case park-2024
uv run --offline --with playwright python scripts/verify_static_method.py --site site-release --case grove-2025
uv run --offline --with playwright python scripts/verify_static_data.py --site site-release

# Optional human review workflow (requires native files and a qualified reviewer)
uv run python -m fireatlas.mask_review --case grove-2025 --template /tmp/grove-native-review.json
uv run python -m fireatlas.mask_review --case grove-2025 --review /tmp/grove-native-review.json --install
```

The static bundle is still a dated snapshot. Its source rows preserve NASA FIRMS provenance and hashes, while pass, cloud, and no-pass coverage remain unknown unless standard fire-mask products have been processed and reviewed.

## What works and what remains uncertain

The local app imports original FIRMS fields, preserves source provenance, assigns detection centroids to a shared 1 km grid, and renders UTC monthly/daily activity and source records. The primary calendar unit is VIIRS-equivalent active-fire cell-days; native MODIS (~1 km) and VIIRS (375 m) rows remain inspectable in the visible Sensor Bridge. Raw FRP is shown separately in MW/day and is not added across sensors. The region calendar can fit and hold out a transparent count ratio when version-matched overlap records are present; this is not a calibrated sensor-sensitivity model. Satellite pass and cloud coverage remain unknown; an empty detection day is not treated as proof of no fire. MCD64A1 corroboration is a documented pending input, not an invented overlay. The project has no validated spread forecast.

Ignis-Atlassia is a research and learning tool. It is not an operational fire-management, evacuation, or flight-planning tool.

See [data and methods](docs/NASA_ARCHIVE_IMPORT.md), [the Winning Plan and live scorecard](docs/winning-plan/SCORECARD.md), [AI use and numerical review status](docs/AI_USE.md), and [current validation limits](docs/VALIDITY_CASES.md).

## Scientific assistant

Open `/investigate.html` (`/assistant.html` remains an alias) for stored-data investigations, linked replay maps, source-status tables and a private reproducible notebook. The existing pages also include a contextual assistant. Scientific action buttons work without an AI key; optional OpenAI/Google conversation, selected-figure vision, narration and MCP connections are configured on the server.

See [the architecture and delivery plan](docs/SCIENTIFIC_ASSISTANT_PLAN.md) and [setup instructions](docs/SCIENTIFIC_ASSISTANT_SETUP.md). The assistant reuses the existing calculations and preserves the globe and satellite. It does not download datasets, predict spread or turn missing observations into zero activity.

## Research Studio

Studio owners can remove a saved board with **Delete investigation** beside the selector. The confirmation dialog names the investigation and offers **Keep investigation** or **Delete investigation**. Deleting the last board leaves Studio empty; curated presets remain selectable. Scientific inputs are unaffected. [Deletion verification](docs/implementation/investigation-deletion/README.md).

Open **Studio** from the main navigation, or use the prominent **Create in Studio** button in Investigate to arrange checked evidence into a private, revisioned board. New manual investigations ask for a name. To rename any investigation, edit **Investigation name** at the top and press **Save name** or Enter; the saved name appears in the investigation selector and supports Undo/Redo. Drag empty canvas to pan the view; use **Pan canvas** to drag over card previews, Space-drag with canvas focus, or middle-button drag. Card headers still move cards in **Select cards** mode, and wheel scrolling anywhere inside the canvas—including over cards—only zooms around the pointer. Use scrollbar dragging or canvas panning to reposition the view.

The Studio keeps its durable SQLite store separate from the scientific and assistant stores, records the originating study context at board creation, and supports bounded evidence cards, durable groups and saved views, linked interval/cell inspection, an outline, Story Director chapters, checked static-reader export, workflow validation, optional collaboration rooms and conflict-safe undo. Stories use a 1080p/30fps, two-minute profile by default; narration and video rendering remain capability-gated, with captions and schematic fallbacks when optional services are unavailable.

For a presentation, select a curated **Park**, **Camp** or **Grove** preset in the Studio collection. Each prepares paired heat-map images, linked evidence, a saved seven-node workflow and a presenter story in its own board. Park/Camp run for 90 seconds; Grove uses a shorter 45-second walkthrough. Both heat images carry into the opening Story figure, portable reader and video, with source counts, UTC selection and one study-fixed scale. Heat PNGs and exact chart CSV/SVG/context downloads are available. Workflow execution and video export remain explicit actions. See the [preset screenshots and verification report](docs/implementation/studio-checks/lifecycle-presets/).

Canvas map cards have a small dot toggle: **green turns the map background on; gray restores the original dark heatmap**. Click it or focus it and press Space. Turning it back on restores the previous landscape choice. Park defaults to its supplied vegetation composite, Camp/Grove to terrain, and other footprints can request online vegetation. The toggle state persists and the heatmap PNG includes the displayed background; counts and the common study scale stay the same. Supplied and online context retain their dated labels. [Canvas vegetation verification](docs/implementation/canvas-vegetation/README.md).

New exported stories freeze the narration recipe alongside its cited receipts. Verify an extracted reader with `python -m fireatlas.studio.story verify-reader path/to/extracted/story`. The verifier reconstructs checked fields, figures, captions and transcript; authored explanation remains interpretation. New video exports embed the same resolved text in shorter timed subtitle cues and retain the VTT sidecar. Subtitle display depends on the video player.

Story Director restores saved video jobs and downloads through **Recent video exports**, labeled by their immutable story revision. Generated audio is hash-checked and measured before encoding. Partial failures or speech longer than its chapter produce a complete captioned video without a paid retry. Speech is cached per saved revision; explicitly changing the story can require new narration. Local tone fixtures verify chapter timing, while live provider speech quality and word-level alignment remain unverified.

Every Story chapter can open its own frozen evidence exploration and resume at the saved position. Video exports persist preparation/rendering/encoding phases; cancellation prevents late publication and interrupted-job recovery discards unfinished media. The latest local regression passes 305 Python tests, 48 frontend tests and seven renderer checks. See the [acceptance audit](docs/implementation/STUDIO_ACCEPTANCE_AUDIT.md) for the remaining external integration gates and the practical limits of local resource monitoring.

The browser bundle includes a lazy tldraw evidence-shape adapter (operator license key required), a working React Flow workflow composer and a Liveblocks room client backed by role-checked server authorization and field-level shared layout drafts. Story chapters resolve intervals, highlighted cells, visible evidence-card galleries, audience/duration profiles and bounded camera transitions into the same reader/video scene contract. The built-in board and outline remain available without a tldraw key. JARVIS workflow drafts load into the editable composer without automatically saving or running a recipe. The opt-in silent video adapter uses Chromium and ffmpeg; map camera motion preserves fixed labels and legends. Remotion and hosted rooms expose their actual configuration status; live SDK/host verification is distinct from fallback and mocked tests. Static readers contain frozen scene evidence and can be served by `studio-reader.html` without the authoring service. Studio routes and limits are documented in [Research Studio implementation notes](docs/implementation/STUDIO.md).

## JARVIS: captured view to editable whiteboard

The two large Punjab–Haryana regional ZIPs are stored in checksummed parts below GitHub's file limit. After cloning, run `python3 scripts/static_bundle_storage.py --site site` to reconstruct the exact archives before serving the static site. CI and Pages run that step automatically; download URLs and scientific archive hashes stay unchanged. Credentials, local databases, dependencies and repeated browser hosting fixtures remain ignored; source, lockfiles, published browser builds and curated verification evidence are versioned.

Open Investigate, choose an authentic study and UTC frame, optionally select **Prepare native and editable exports**, then **Send to Canvas**. JARVIS asks which Canvas should receive it: create a new investigation or choose an editable existing board. One saved command captures the view, arranges paired sensor maps, checked charts, an availability timeline, findings and original records into connected groups, and creates an editable story and runnable workflow. Selected exports are prepared from the saved board. It opens the persisted board in the same tab. **Return to captured source**, command-specific undo and explicit recovery preserve that selection and unrelated later work. Existing Park/Camp/Grove presentation presets remain available. **Reliable JARVIS prompts** also provides presentation, chart, source-state and original-record shortcuts in analytical workspaces and the Studio inspector. Supported shortcuts work without a model key; custom conversational questions retain the configured AI tool path. Copyable prompts, behavior and verification are documented in [JARVIS prompt presets](docs/implementation/JARVIS_PROMPTS.md).

Conversational Canvas requests on analytical pages automatically capture the current applied view before submission. **Attach this view to JARVIS** remains available for an explicit sensor-pane choice. JARVIS chooses from the registered scientific, navigation and Studio tools; checked calculations and saved commands remain usable if its final wording fails verification. Deterministic capture/export needs no model key. Whole-board, frame and selection exports support native `.fireatlas.zip`, editable `.excalidraw`, SVG, PNG and PDF. Restore native archives into new owned boards; imported receipts retain frozen provenance. [Implementation and export instructions](docs/implementation/JARVIS_PORTABILITY.md) and [tool-routing fix with live acceptance results](docs/implementation/JARVIS_TOOL_ROUTING_FIX.md) cover the actual scope. Restart an existing local service to load new backend routes.

Backend native/Excalidraw export needs the pinned local Node helpers (`npm --prefix studio-app ci`); rebuild with `npm --prefix studio-app run build`. PNG/PDF also need local Chromium. The independent [Excalidraw continuation editor](fireatlas/static/studio-excalidraw.html) works with embedded exported scenes on static hosting. Static hosting cannot save private boards or run new commands. Miro is an explicit operator-configured action; its live destination acceptance has not been performed.

**Infographic stories:** In Studio, open a prepared investigation, choose **Story**, then **Create story**. AI& GLM-5.3 authors the checked storyboard. With `FIREATLAS_STUDIO_VIDEO_PROVIDER=aiand`, AI&'s actual `minimaxai/minimax-h3` video-generation API creates image-conditioned clips with sound. The film composes those clips with exact scientific figures, checked narration and subtitles. Each provider clip is 4–15 seconds at 768p; the assembled film is upscaled to 1080p. Progress shows the actual provider chapter/status. **Refresh film & voice** generates a native film from a saved story without another writing request; completed native clips are reused. Configure private `AIAND_API_KEY` and optional ordered `AIAND_API_KEYS` in `.env.assistant`. Video access is verified per key, independently of chat access. See [setup](docs/SCIENTIFIC_ASSISTANT_SETUP.md#ai-infographic-stories-in-studio) and [native video acceptance](docs/implementation/aiand-native-video/REPORT.md).

The latest analytical UI puts Investigate's map and timeline first, with compact Canvas actions, and shows case-specific native validation/review gates at the top of Evidence → Validity. See the [implementation and acceptance report](docs/implementation/workspace-polish/REPORT.md). Recheck the local and static project-subpath presentation with:

```bash
.venv-assistant/bin/python scripts/verify_workspace_polish.py --base http://127.0.0.1:8000
```
