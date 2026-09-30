# NASA FIRMS Archive Download import

The user supplied 34 sidecar-backed standard FIRMS archive exports in `NASA_data/`: eight
July 2022–June 2026 files with saved request metadata, plus 26 older MODIS
Collection 6.1 and VIIRS Suomi NPP Collection 2 files. Original request forms
were not supplied for those older files, so locally generated sidecars mark
them `reconstructed-rows-only`. Six reconstructed MODIS exports (requests
814851, 814850, 814849, 814847, 814831 and 814832) add positive rows from July
2006 onward but do not create complete-month evidence. The original files and database are ignored
by Git. The reproducible, compact modern Northern California derivative is bundled as
`fireatlas/samples/nasa_firms_northern_california_2022_2026.zip` (about 576 KB).

The folder also contains two duplicate physical CSV copies for request IDs
814362 and 814364 without an additional request sidecar. They are not counted
as new exports or imported as separate batches; the importer uses the
sidecar-backed request inventory above.

The local application database imports the standard files into both
Northern California and Punjab–Haryana. It contains 1,994,162 unique standard
source records across those boxes (456,202 MODIS and 1,537,960 S-NPP). The six
new reconstructed MODIS exports contribute 154,660 clipped rows, and S-NPP
request 814833 contributes 204,694 unique clipped rows; none of the 26
reconstructed exports can establish complete monthly coverage. In each region MODIS has 48 and S-NPP has 47 request-verified
source-months from 2022-07 through 2026-06; May 2026 stays unknown because the
worldwide S-NPP export had no rows. Older positive records display as partial,
while empty dates remain unknown.

The supplied reconstructed inventory now includes the nominal MODIS annual
windows 2006-07→2007-07, 2007-07→2008-07, 2008-07→2009-07,
2009-07→2010-07, 2019-07→2020-07 and 2021-07→2022-07. The S-NPP
2021-07→2022-07 window is now present as row-only evidence from request 814833.
These boundaries are reconstructed;
without the original requests they are not verified exact coverage windows.

The new 814833 archive is represented by an explicit sidecar at
`NASA_data/DL_FIRE_SV-C2_814833/request.json`. It records the parent hash
`11148a105d2465d51c0f79c77fdadfb48d8f17f8f31f0d29e4bc6f3e5b24792a`, the
sidecar hash `e2bc6b36fc419a2fa82e7de32c831474f1414409ae7f163c633d86da234d0afe`,
and `coverage_basis: reconstructed-rows-only`. This preserves traceability
without turning the missing request metadata into a complete-window claim.

The bundle contains 30,823 original detection rows inside
`west=-122.2,south=38.8,east=-120,north=41`, split by UTC month and source.
Its manifest records each FIRMS request ID, original filename and SHA-256,
worldwide month counts, slice SHA-256 and selected row counts. The original
worldwide CSVs contain more than 93 million records and are not packaged.
Every field of a selected NASA row is retained in its derived CSV and in the
database's `raw_json`. FIRMS Archive Download uses `instrument=SNPP` for its
Suomi NPP files; the importer normalizes this to `sensor=VIIRS` without
altering the raw field.

## Completeness and limits

- The 84 source-month slices from July 2022 through December 2025 are marked
  as complete *exports* for the selected box. Both standard products are
  available for July 2022–2025, including the three prior July years used by
  the 2025 baseline. Complete export does not establish clear satellite passes
  or continuous observation.
- The 11 nonempty January–June 2026 slices are imported as partial evidence.
  The bundled Northern California sample keeps 2026 slices partial. In the
  local database, complete requested MODIS months are recorded as complete;
  the S-NPP May 2026 month remains unknown because the worldwide source file
  has no rows. The separate July 2026 NRT CSVs are excluded from the standard
  series.
- Some prior-year MODIS detections use version `6.03`, whereas July 2025 uses
  `61.03`. The method audit flags this version change across baseline years.
  Its cell-day difference is descriptive; it is not a calibrated trend or a
  measured change in wildfire incidence.
- The request scope comes from the user's FIRMS Archive Download files and
  screenshots. This pipeline verifies local file hashes, CSV fields, dates and
  derived counts; it cannot independently authenticate NASA's request system
  or establish satellite pass and cloud coverage.
- Hotspots are thermal detections, not fire perimeters, burned area, or proof
  that no fire occurred where no point appears. Agricultural and other heat
  sources have not been removed using a validated mask.

The July 1 spillover rows at the end of the 2022–2024 year files are skipped;
the next archive owns each full July month. Original parent hashes and skipped
row counts remain in `manifest.json`. The imported batch source identifier is
an `urn:fireatlas:nasa-firms-archive:...` containing the request ID and the
original file hash. It is an identifier, not a live download URL.

## Reproduce locally

```bash
uv run python -m fireatlas.archive build NASA_data
uv run python -m fireatlas.archive import --db data/fireatlas.sqlite3
uv run python -m fireatlas.web --db data/fireatlas.sqlite3 --port 8000
```

The import is idempotent. A fresh default server loads this compact NASA
bundle and the separate NOAA HMS sample without a FIRMS MAP_KEY. Open
`/method.html?context=calendar&series=joint&year=2025&month=7&bbox=-122.2,38.8,-120,41#harmonization-audit`
to inspect the authentic paired month; use **Download study** to verify its
calendar and source audit from frozen input rows.

To import the owner-supplied worldwide standard CSVs into both study regions,
put an exact `request.json` beside each file (including `csv_filename` when an
NRT companion is in the same folder), then run:

```bash
uv run python -m fireatlas.archive import-requests NASA_data --db data/fireatlas.sqlite3
```

Each sidecar records the product, inclusive dates, request bounding box,
request ID, and selected standard filename. The importer stores hashes, clips
the file to the two region boxes, and does not infer pass, cloud, or no-fire
status from an empty regional slice.

Two additional world NRT files from the same July 2025–June 2026 requests
contain July 1, 2026 detections. They were imported into the **local database
only** as `MODIS_NRT` (10,300 rows) and `VIIRS_SNPP_NRT` (58,564 rows), with
their original file hashes recorded by the importer. They are absent from the
bundled regional standard-product sample and remain partial, separate series.
Reproduce that optional local import from the original files with:

```bash
uv run python -m fireatlas.cli ingest NASA_data/DL_FIRE_M-C61_814031/fire_nrt_M-C61_814031.csv --source MODIS_NRT --source-uri urn:fireatlas:nasa-firms-archive:814031:nrt-2026-07-01
uv run python -m fireatlas.cli ingest NASA_data/DL_FIRE_SV-C2_814034/fire_nrt_SV-C2_814034.csv --source VIIRS_SNPP_NRT --source-uri urn:fireatlas:nasa-firms-archive:814034:nrt-2026-07-01
```

Source: [NASA FIRMS Archive Download](https://firms.modaps.eosdis.nasa.gov/download/).
NASA asks users of its open Earth science data to
[cite the datasets they use](https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy).
