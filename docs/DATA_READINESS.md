# Data readiness — 27 September 2026

**Historical snapshot:** The authentic NASA MODIS/Suomi NPP archive was added
on 29 September 2026. For the current data inventory and reproduction commands,
see [NASA archive import](NASA_ARCHIVE_IMPORT.md) and the root README. Counts
and verification results below describe the repository before that import.

**Ready to proceed with presentation UI, navigation and interaction improvements.**
The current local backend serves authentic imports alongside a separate, clearly
labelled synthetic showcase. NASA API availability does not block these workflows.
This is readiness for the demonstration, not scientific or operational validation.

## Available data

| Segment | Data available | Classification |
| --- | --- | --- |
| Recent global atlas | 72,776 MODIS + 394,527 NOAA-20 + 399,653 NOAA-21 detections, September 20–27, 2026 | Authentic rolling CSV snapshot; partial monthly coverage |
| Historical atlas | 49,420 NOAA HMS VIIRS detections, Northern California, July 2021–2024 | Authentic historical source |
| Full-year calendar | 11,322 generated detections, 96 source-months, January–December 2023–2026 | Synthetic; includes hypothetical future months |
| Monthly baselines | Three comparable prior scenario years for every 2026 month | Synthetic; excludes the separate legacy guided tour |
| Research comparison | September 2026: 562 pixels, 250 union cell-days, 125 shared cell-days, three candidate groups and an exploratory ratio band | Synthetic inputs, real application calculations |
| Exposure demonstration | 720 source/cell/day mask entries; 360 assumed observed cell-days per sensor | Explicitly fabricated mask; real coverage remains unknown |
| Vegetation / cover / weather controls | 100 local GeoJSON cells per layer, restricted to the showcase AOI | Illustrative synthetic values; weather is an arbitrary index, not FWI |
| Training Lab | Preserved on `archive/training-lab`; not served from `main` after 29 September 2026 | Archived fictional exercise |
| Event reports | Existing NASA EONET feed/cache, kept separate from synthetic data | Reported events; availability depends on feed/cache |

The 866,956 accepted NASA detections and 49,420 NOAA observations total **916,376
authentic records**. One additional NASA polar row is preserved in the exclusion
ledger outside the atlas grid. No synthetic rows were added to this database.

## Verification performed

- **51 automated tests passed:** ingestion, exclusions, harvester behavior,
  calendars, research, portable evidence, web endpoints, training behavior and
  six new presentation tests (before the training feature was archived).
- **Build passed:** Python wheel and source distribution.
- **JavaScript syntax checks and `git diff --check` passed.**
- **Desktop (1440 px) and mobile (390 px) browser checks passed:** presentation
  links, all three local context layers, sensor changes, switching back to
  authentic data, ZIP export and independent verification, research JSON export,
  exposure-mask clearing after cutoff changes, and training replay advancement
  (before the training feature was archived).
  No JavaScript page errors occurred. External browser requests were blocked
  during these checks; the large Earth embed was omitted from this focused test.
  The local application server remained connected. This does not claim that the
  whole site works without its server or that remote imagery was verified.
- **Data isolation passed:** the authentic database's SHA-256 remained unchanged;
  all three original CSV hashes and all 36 seed-row samples matched; the synthetic
  database passed SQLite integrity checking and contains no authentic batches.
- **Reproducibility passed:** repeat generation is idempotent, authentic databases
  reject fixture insertion, synthetic requests require explicit demo mode, and
  downloaded study counts reproduce from the bundled inputs.

Re-run the automated gate with:

```bash
uv run python -m unittest discover -s tests -v
uv build
```

## Entry points

- `/data.html`: authentic sources and demonstration links.
- `/?demo=1&year=2026&month=9&series=joint#calendar-section`: full-year showcase.
- `/research.html?demo=1&year=2026&month=9&exposure=synthetic`: populated research
  comparison with the fabricated mask explicitly selected.
- The former `/training.html` exercise is preserved on `archive/training-lab`.
- `/api/presentation`: versioned generation method and original CSV hashes.

## Boundaries for the next phase

No additional download is needed for the UI work. Genuine observation masks,
measured weather, SAR change analysis, calibrated sensitivity and validated spread
forecasts remain outside the verified feature set. The interface keeps those
scientific requirements visible rather than treating synthetic inputs as evidence.

Remote base maps and authentic GIBS imagery still need connectivity. Recent NASA
CSVs are snapshots and do not update automatically while FIRMS is unavailable.
The ignored `NASA_data/` files and local database are not pushed to GitHub; a new
deployment gets the bundled NOAA slice and synthetic seeds, and needs the local
database copied or the CSVs imported to show the full recent authentic snapshot.
