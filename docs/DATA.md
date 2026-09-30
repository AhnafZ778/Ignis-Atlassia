# NASA data ledger

## What is in this checkout

The bundled regional sample contains 30,823 original MODIS and Suomi NPP FIRMS detections clipped to the Northern California study box `[-122.2, 38.8, -120.0, 41.0]`. In this workspace, 34 sidecar-backed worldwide standard archive exports have been processed into Northern California and Punjab–Haryana: eight retain original request metadata, and 26 use locally reconstructed row-only sidecars. The local folder additionally contains duplicate CSV copies without request sidecars; they are not treated as extra exports. The local database contains 1,994,162 unique standard regional source records: 456,202 MODIS and 1,537,960 S-NPP detections. Parent exports were supplied by the project owner; original request metadata and exact NASA download dates are not available for the 26 reconstructed exports. Those rows are imported as positive evidence only, with no complete-month claim. The verified target begins in **July 2010** for MODIS and **July 2012** for S-NPP; reconstructed MODIS detections extend the displayed positive history to July 2006, and reconstructed S-NPP rows now extend through July 2022 without creating complete-month evidence. Files were inventoried and imported in this workspace on 2026-09-30; this date is not when NASA generated or delivered them.

| Product | Parent archive and request | Coverage (UTC dates) | Parent file SHA-256 |
|---|---|---|---|
| MODIS Terra + Aqua · Collection 6.1 standard | `fire_archive_M-C61_814042.csv` · request 814042 | 2022-07-01 through 2023-07-01 (end exclusive) | `79311ac9ef6aa2c76caf850985c98c2b9d4fc3a9b1f6dbeb0bc8beb4c2a5b3fc` |
| MODIS Terra + Aqua · Collection 6.1 standard | `fire_archive_M-C61_814040.csv` · request 814040 | 2023-07-01 through 2024-07-01 (end exclusive) | `1b20952ad260b42521502217829c52b7231b12634b696e734fdade40d9e642e4` |
| MODIS Terra + Aqua · Collection 6.1 standard | `fire_archive_M-C61_814038.csv` · request 814038 | 2024-07-01 through 2025-07-01 (end exclusive) | `df89cff5b3a6d78122f98b59bab2aee1caac2b202ed7263f776c0a571c4f577b` |
| MODIS Terra + Aqua · Collection 6.1 standard | `fire_archive_M-C61_814031.csv` · request 814031 | 2025-07-01 through 2026-07-01 (end exclusive) | `b65a9565bf3473abe26701b9a53c896ad540163d1af31180f0654b5010702165` |
| VIIRS Suomi NPP · Collection 2 standard, 375 m | `fire_archive_SV-C2_814043.csv` · request 814043 | 2022-07-01 through 2023-07-01 (end exclusive) | `339067de2db9cf136fa1da1acabac5410c5e45e2719351744bbd438f9982bcde` |
| VIIRS Suomi NPP · Collection 2 standard, 375 m | `fire_archive_SV-C2_814041.csv` · request 814041 | 2023-07-01 through 2024-07-01 (end exclusive) | `7c2804b73b4a1698c82f6d5f3eb99e95acecce654b346456c9e2b2f7198469fe` |
| VIIRS Suomi NPP · Collection 2 standard, 375 m | `fire_archive_SV-C2_814039.csv` · request 814039 | 2024-07-01 through 2025-07-01 (end exclusive) | `4e0ad98372415621a0dd6f50c5dfbf68c8e3d18ddf1cef814484edd91dcc1478` |
| VIIRS Suomi NPP · Collection 2 standard, 375 m | `fire_archive_SV-C2_814034.csv` · request 814034 | 2025-07-01 through 2026-07-01 (end exclusive) | `f71c07d37d8537ed4a4fc4424639be323b517719e3bd155ca0d6b9eaa37b91ab` |

The input product records include MODIS versions `6.03` and `61.03`; VIIRS records use version `2`. Do not interpret their cross-year differences as calibrated sensor change. In each region, the database has 48 request-verified MODIS source-months and 47 request-verified S-NPP source-months from July 2022 through June 2026. The worldwide S-NPP export has no May 2026 rows, so that month remains unknown rather than becoming a zero.

### Reconstructed MODIS history added locally

The following six owner-supplied MODIS files were added after the original ledger was written. Their `request.json` sidecars are explicit `reconstructed-rows-only` records: the dates and world-area box are inferred for row import, not evidence of a complete request. The sidecar-bounded windows are shown for traceability; all resulting months remain partial.

| Request ID | Local file | Reconstructed sidecar window |
|---|---|---|
| 814851 | `fire_archive_M-C61_814851.csv` | 2006-07-01 through 2007-07-02 |
| 814850 | `fire_archive_M-C61_814850.csv` | 2007-07-01 through 2008-07-02 |
| 814849 | `fire_archive_M-C61_814849.csv` | 2008-07-01 through 2009-07-02 |
| 814847 | `fire_archive_M-C61_814847.csv` | 2009-07-01 through 2010-07-02 |
| 814831 | `fire_archive_M-C61_814831.csv` | 2019-07-01 through 2020-07-02 |
| 814832 | `fire_archive_M-C61_814832.csv` | 2021-07-01 through 2022-07-02 |

Together these six files contribute 154,660 clipped rows. They extend positive MODIS history to July 2006 and close the previously noted nominal MODIS archive windows. Neither the reconstructed MODIS rows nor their inferred date windows can establish satellite pass, cloud, or no-fire coverage.

### Reconstructed S-NPP history added locally

The owner-supplied `fire_archive_SV-C2_814833.csv` adds the previously missing
July 2021–July 2022 Suomi NPP rows. Its exact parent SHA-256 is
`11148a105d2465d51c0f79c77fdadfb48d8f17f8f31f0d29e4bc6f3e5b24792a`; the
local sidecar SHA-256 is
`e2bc6b36fc419a2fa82e7de32c831474f1414409ae7f163c633d86da234d0afe`.
The file contains rows dated 2021-07-01 through 2022-07-01 and was imported
as 26 reconstructed month slices (13 per region), with 204,694 new clipped
records. The sidecar deliberately uses `coverage_basis: reconstructed-rows-only`:
the source rows are visible and hash-bound, but no month in this archive is
promoted to a complete export. The verified July 2022 request-backed slice
remains authoritative where both records overlap.

The reconstructed CSVs add detections but cannot establish continuous coverage because their original request forms are absent. Their sidecars are marked `reconstructed-rows-only`, and the calendar renders detections from them as partial while keeping non-detection dates unknown. The reconstructed MODIS inventory now nominally spans July 2006–June 2022, with the six additions listed above plus the earlier 19 exports. The reconstructed S-NPP inventory now nominally spans July 2012–July 2022: the new 814833 archive covers July 2021–July 2022 at row level, while its original request metadata are unavailable. These nominal boundaries do not certify exact coverage. The May 2026 S-NPP export is also incomplete. All row totals are observations, not counts of fires or fire days, and even a request-verified export does not prove a clear satellite pass.

For a partial historical month, the calendar verdict now gives MODIS and S-NPP
cell-day counts separately, names how many UTC dates contain imported detections,
and says the remaining dates are unknown rather than zero. It does not create a
joint monthly total from row-only archives.

| Local regional rows by area | MODIS standard | S-NPP standard |
|---|---:|---:|
| Northern California | 54,659 | 173,245 |
| Punjab–Haryana | 401,543 | 1,364,715 |

The committed modern bundle manifest and the ignored local database retain parent hashes, request IDs, dates, area, source versions, and completeness labels. The 26 reconstructed windows retain file and sidecar hashes in the local database, but they do not preserve authentic FIRMS request metadata.

- Bundled derived file: `fireatlas/samples/nasa_firms_northern_california_2022_2026.zip`
- Derived bundle SHA-256: `1d11fe547f0b005ca9cd4ffc88d48c12f63a782b442719203609605712d60696`
- Processor: `fireatlas.archive.build_bundle`, method schema `fireatlas-firms-archive-slice-v1`
- Source page: https://firms.modaps.eosdis.nasa.gov/download/
- FIRMS acknowledgement: “We acknowledge the use of imagery from the NASA LANCE FIRMS (https://earthdata.nasa.gov/firms), part of the NASA Earth Science Data and Information System (ESDIS).”

## Reproducible paired daily aggregates

The Data Sources page links to a small compressed evidence bundle for each
region. Each contains **47 shared request-complete source months** and **1,430
UTC dates** from July 2022 through June 2026; May 2026 is omitted because the
S-NPP source export is incomplete. Dates with no eligible detections in a
complete paired month remain explicit zero rows. The series use FIRMS `type`
0 or missing, count distinct 1 km EASE-Grid centroid cells and eligible source
rows, and sum reported FRP. Type-2 rows do not enter the calendar. These are
detection summaries, not satellite pass coverage, fire counts, or burned area.

| Bundle | SHA-256 | Parent FIRMS inputs |
|---|---|---|
| `fireatlas/samples/aggregates/norcal.json.gz` | `6cc2d49eb7cb2b1deb803cfd68dcfa624231177c79c8b4c8580216a45f70982b` | 8 request-backed archive CSVs listed above |
| `fireatlas/samples/aggregates/punjab-haryana.json.gz` | `ecea89bc4e635429d53b315b7bd73ee5936d1545711cfe0e95ddd7c6b0b67629` | Same eight parent files and hashes listed above |

Build the bundles from the imported database with:

```bash
uv run python -m fireatlas.aggregates --db data/fireatlas.sqlite3
```

The compressed JSON includes its schema, method version, region bounds,
generation time, parent filenames and SHA-256 values. Re-running reproduces the
daily numeric values for unchanged inputs and method; `generated_utc` means the
compressed file hash changes on a later build. The full four-year local
database and original 34 CSVs are not committed; the compact paired bundles are
available in a clean checkout and through the Data Sources page.

## Reproducible sensor-ratio calibration

The Method page reads a region-specific calibration artifact rather than
recalculating the displayed fit in the browser. Each artifact records the
41 version-matched, complete MODIS 61.03 / VIIRS Collection 2 overlap months
(January 2023 through June 2026), monthly inputs, leave-one-year-out results,
the deterministic bootstrap seed, the source CSV hashes, and the paired daily
bundle hash. The public JSON files are:

- `fireatlas/samples/calibration/norcal.json`
- `fireatlas/samples/calibration/punjab-haryana.json`

Rebuild them from the imported database and paired daily bundles with:

```bash
uv run python -m fireatlas.calibration --db data/fireatlas.sqlite3
```

The values remain a descriptive scaling experiment, not proof that the sensors
are interchangeable. Fixed-candidate leave-one-year-out errors are retained as
reference baselines; the nested selected-pipeline result is the estimate that
accounts for model choice. Across four outer year folds, Northern California's
nested median absolute log error is 0.304 and its median full-year absolute
error is 25.2%. Punjab–Haryana's corresponding errors are 0.322 and 26.3%.
Daily and 1-, 3-, 7-, and 14-day seasonal gap results are included in the same
artifacts. The rolling gap windows overlap and are grouped by held-out year, so
their window counts are not independent sample sizes.

For the nested selected pipeline, held-out daily median absolute log error is
0.571 in Northern California and 0.926 in Punjab–Haryana. Median absolute
percentage error on nonzero VIIRS days is 100.0% and 93.0%, respectively. These
values describe this short paired sample and should be read alongside the
season-by-gap table in the Method page; they do not establish sensor detection
probability.

Prediction intervals are explicitly **withheld**: the artifacts contain zero
independently evaluated prediction-interval pairs and make no interval
coverage or width claim. The earlier 17/41 (41.5%) and 16/41 (39.0%) values
were coverage diagnostics for monthly-ratio factor intervals, not prediction
interval coverage, and are not presented as prediction reliability. The
production calendar's current method choice is fit using all available overlap
months; it is separate from the nested held-out estimate. The artifacts also
leave the 2012 sensor step pending: older detections are available as positive
rows, including the reconstructed S-NPP 2021–2022 window, but their original
request metadata do not establish complete observation windows. Independent
review is still required.

## Use and license

The code license in the repository does not apply to NASA data. NASA Earthdata’s [data use and citation guidance](https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy) says NASA ESDIS material is generally not copyrighted and NASA mission data are CC0 unless the product is marked with another restriction; it asks users to acknowledge NASA and cite the data. Check the specific FIRMS collection metadata before redistribution. No product DOI or per-file citation is recorded in the supplied archive request metadata.

## Known data gap for the Winning Plan

### MCD64A1 Collection 6.1 corroboration

Official University of Maryland MCD64A1 Collection 6.1 monthly Burn Date and
companion QA rasters are included for dated Park, Grove, and Punjab–Haryana
checks. `fireatlas/samples/mcd64_corroboration.json` records each clipped box,
QA-supported Burn Date counts, day-of-year range, same-date grid co-location,
active-fire context, and SHA-256 for both source files. Retrieved and imported
2026-09-30. Static exports copy the same report to
`data/v2/validity/mcd64-corroboration.json`.

The [Collection 6.1 guide](https://lpdaac.usgs.gov/documents/1006/MCD64_User_Guide_V61.pdf)
defines QA bit 0 as land, bit 1 as sufficient valid data, bit 2 as a shortened
reliable mapping period, bit 3 as contextual relabeling, and bits 5–7 as a
special-condition code for unburned cells. A Burn Date of 1–366 is counted as
QA-supported burned only when bits 0 and 1 are set. A Burn Date of 0 is counted
as full-period unburned only when bits 0 and 1 are set, bits 2 and 3 are clear,
and the special-condition code is zero. Other categories remain visible in the
evidence report. These are product QA rules, not ground-truth labels.

Sources: [MCD64A1 DOI](https://doi.org/10.5067/MODIS/MCD64A1.061) and the
[official Collection 6.1 guide](https://modis-fire.umd.edu/files/MODIS_C61_BA_User_Guide_1.1.pdf).
This is lagged burned-area context only; it does not establish active-fire
truth, satellite pass, cloud clearance, a fire perimeter, or fire-free area.
Same-date co-location assigns MCD64A1 pixel centers and FIRMS centroids to the
same 1 km EPSG:6933 cells. It is descriptive rather than independent validation:
the MCD64A1 algorithm uses cumulative MODIS active-fire maps to guide training
samples and prior probabilities. A lack of same-date co-location does not
establish fire absence. Independent review remains pending.

The local app can now display partial historical detections from July 2006 MODIS and July 2012 S-NPP, including reconstructed S-NPP rows through July 2022, but it still cannot produce a complete harmonized calendar or long-term baseline for those years. No rows have been synthesized. The monthly calendar keeps reconstructed months incomplete unless exact request dates and area establish a complete export.

No extra dataset is required for a truthful FIRMS detection calendar. Native MOD14/MYD14/VNP14IMG fire masks with matching MOD03/MYD03/VNP03IMG geolocation are needed only to classify sampled cells as fire, usable non-fire, or cloud. They are not sufficient for a claim that every cell had a satellite pass: the complete candidate granule inventory and appropriate footprint treatment are also required. The local processor now decoded Grove 20/20 expected fire-mask granules (15,495 clipped pixels) and Park 114/114 (1,372,872 clipped pixels). Both cases remain processed-unreviewed: the site still leaves cell-level pass/cloud coverage unknown until raw-cell review and full-footprint accounting are complete.

The dated S-NPP product notice ledger is `fireatlas/samples/sensor_notices.json`. NASA LDOPE reports a science-product outage from 2024-07-24 05:24 UTC through 2024-07-29 15:18 UTC, inclusive. Partial first and last UTC dates are shown distinctly. A zero-record export is never classified as a missing sensor or a fire-free day.

## Reproduce the bundled regional archive

With the owner-supplied `NASA_data/DL_FIRE_*` parent files available locally:

```bash
uv run python -m fireatlas.archive build NASA_data
uv run python -m fireatlas.archive import --db data/fireatlas.sqlite3
```

The parent CSVs are not checked into Git. The committed regional ZIP is the reproducible input for a clean checkout.
