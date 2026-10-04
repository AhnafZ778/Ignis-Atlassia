# Ignis-Atlassia — NASA MODIS and VIIRS burning activity calendar

**Challenge:** NASA Space Apps 2026 · Harmonization of MODIS and VIIRS Hot Spots

Ignis-Atlassia is a research prototype for inspecting dated NASA FIRMS active-fire detections and counting distinct 1 km equal-area grid cell-days in UTC. The calendar variant includes FIRMS type 0 or missing, across confidence levels; other rows remain inspectable but are excluded from totals. The home page opens on the existing 3D globe. Atlas, Fire replay, Research lab, Data sources, Method, Review, and the scientific assistant are separate focused workspaces. A hotspot is a satellite thermal observation, not a fire perimeter, burned area, or proof that no fire occurred.

**Public demo:** Not deployed from this checkout. Run locally at http://127.0.0.1:8000/.
**Repository:** https://github.com/AhnafZ778/NASA-Spaceapps
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

The actual website uses a shared light interface: warm ivory, white work surfaces, dark ink, and cobalt actions. MODIS is amber/circle, VIIRS is cyan/diamond, and shared cells are green/square. Unknown and partial records retain explicit status labels. The landing globe and its interactions are preserved.

See the [implemented redesign and screenshot review](docs/UI_Review/README.md) and [page-by-page audit](docs/UI_UX_AUDIT_AND_LIGHT_REDESIGN.md).

Production UI sources are in `fireatlas/static/`. To refresh `site/` after a UI edit while preserving its existing observation data and snapshot date:

```bash
uv run python scripts/refresh_static_assets.py --site site
```

A new data export still uses `scripts/export_static.py`. Static hosting supports bundled evidence; live research calculations and assistant tools require the local service. Map imagery and streamed terrain need network access.

## Data and study areas

The committed authentic NASA sample contains 30,823 Northern California MODIS Terra/Aqua and Suomi NPP VIIRS standard-product rows for July 2022–June 2026. In this workspace, 34 sidecar-backed standard FIRMS archive exports have been imported into Northern California and Punjab–Haryana: eight retain original request metadata, while 26 use explicitly reconstructed, row-only sidecars. The local database now retains 1,994,162 unique standard source records across those two study areas (456,202 MODIS and 1,537,960 Suomi NPP), with positive detections as early as July 2006 for MODIS and July 2012 for Suomi NPP. The six newly supplied MODIS archives fill the earlier 2006–2010 history and the nominal 2019–2020 and 2021–2022 MODIS windows. The newly supplied S-NPP 814833 archive adds row-level detections from July 2021 through July 2022. Their request forms are absent, so every reconstructed month remains partial and absent dates remain unknown. This is not a verified continuous archive. The two regions still have 48 complete MODIS source-months and 47 complete S-NPP source-months each from July 2022 through June 2026; S-NPP May 2026 remains unknown.

The calendar is an authentic regional FIRMS detection view, not a fire-perimeter or observation-coverage product. `NASA_data/` and the local database are ignored by Git; a clean clone gets only the committed Northern California sample until the owner-supplied files are imported. See [the data ledger](docs/DATA.md) and [archive import instructions](docs/NASA_DATA_IMPORT.md) for file provenance, missing windows, and the import command. NASA data are not covered by the repository's Apache-2.0 code license.

## Build a static calendar snapshot

After importing the local archive, create a fresh static bundle and serve it locally:

```bash
uv run python scripts/export_static.py --db data/fireatlas.sqlite3 --output site-release
python3 -m http.server 8000 --directory site-release
```

The bundle includes precomputed 2006–2026 calendars, dated history, compressed source-row samples for both regions, complete row-level observation archives split into deterministic sub-100 MB gzip parts, and the Park/Grove validity reports with their checksum manifests, recount results, evidence ZIPs and blank native-review templates. The Data & Method page uses those files directly, so a judge can open the historical case, scrub UTC days, inspect source rows, run the displayed recount, and download the hash-bound reviewer form without credentials or a Python API. It does not copy the SQLite database or the raw `NASA_data/` archive. It is a dated, read-only evidence demo; data imports, the research API, and globe observation overlays still require the Python server. A GitHub Pages workflow is configured for the committed `site/` bundle, but no public deployment has been run or verified from this checkout.

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

Open `/assistant.html` for stored-data investigations, linked replay maps, source-status tables and a private reproducible notebook. The existing pages also include a contextual assistant. Scientific action buttons work without an AI key; optional OpenAI/Google conversation, selected-figure vision, narration and MCP connections are configured on the server.

See [the architecture and delivery plan](docs/SCIENTIFIC_ASSISTANT_PLAN.md) and [setup instructions](docs/SCIENTIFIC_ASSISTANT_SETUP.md). The assistant reuses the existing calculations and preserves the globe and satellite. It does not download datasets, predict spread or turn missing observations into zero activity.
