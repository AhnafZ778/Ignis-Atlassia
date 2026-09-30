# Import the longer NASA FIRMS archive

The committed sample covers July 2022–June 2026. In this workspace, 34
sidecar-backed owner-supplied standard archive exports have been imported
locally, including older MODIS and Suomi NPP detections. Eight files retain
request metadata; 26 older files use locally generated row-only sidecars
because original request forms were not supplied. Six of those files add MODIS
rows from July 2006 and the nominal 2019–2020 and 2021–2022 windows. One
additional S-NPP file (814833) supplies row-level data for July 2021–July 2022. The
original annual files and the local database remain in ignored `NASA_data/` and
`data/` folders, outside Git. The older sidecars are marked
`reconstructed-rows-only`, because their original FIRMS request forms were not
supplied. Their positive detections appear in the calendar as partial evidence;
empty dates remain unknown. Never select the
neighboring `fire_nrt_*.csv` or 7-day snapshot files for the historical
calendar.

## Current supplied archive inventory

The 26 reconstructed CSVs were processed on 2026-09-30. Their nominal date
spans are reconstructed from the supplied file periods and do not prove request
completeness. The six newly added MODIS files contribute 154,660 clipped rows;
the local database now contains 1,994,162 unique MODIS/S-NPP source records
across both boxes.

| Product | Older nominal archive windows supplied | Missing nominal window |
|---|---|---|
| MODIS Terra + Aqua | July 2006–June 2022, including reconstructed 2019–2020 and 2021–2022 files | Original request metadata are absent for the reconstructed windows; no complete-month claim |
| VIIRS Suomi NPP | July 2012–July 2022, with 814833 row-only provenance | Original request metadata are absent; no complete-month claim |

The newer request-backed records still provide 48 complete MODIS months and
47 complete S-NPP months per region from July 2022 through June 2026. S-NPP
May 2026 remains unknown because the supplied worldwide export contained no
rows for that month. No additional data are needed to demonstrate the FIRMS
detection calendar with honest unknown states. The reconstructed S-NPP window is now present as positive row evidence, but its
original request metadata are still missing; those metadata and the other
reconstructed windows are needed for a more continuous, completeness-verified
historical baseline.

## Newly supplied S-NPP row-only archive

`NASA_data/DL_FIRE_SV-C2_814833/fire_archive_SV-C2_814833.csv` covers rows
dated 2021-07-01 through 2022-07-01. Its parent SHA-256 is
`11148a105d2465d51c0f79c77fdadfb48d8f17f8f31f0d29e4bc6f3e5b24792a`, and its
explicit sidecar SHA-256 is
`e2bc6b36fc419a2fa82e7de32c831474f1414409ae7f163c633d86da234d0afe`. Because
the original FIRMS request JSON was not retained, its sidecar uses
`coverage_basis: reconstructed-rows-only`. The importer added 204,694 unique
clipped records and records 26 partial month slices (13 per region). Empty
dates stay unknown; the verified July 2022 request-backed export remains the
complete source where the files overlap.

## Target archive window

The calendar and daily history are configured for these target start dates in
both study areas. The supplied local files include detections from these start
dates, but older files do not include original request metadata and have the
gaps shown above. The target dates are scientific goals, not a claim of
complete imported coverage.

| Product | Northern California | Punjab–Haryana |
|---|---|---|
| MODIS Terra + Aqua standard | 2010-07-01 through latest complete FIRMS archive date | 2010-07-01 through latest complete FIRMS archive date |
| VIIRS Suomi NPP standard | 2012-07-01 through latest complete FIRMS archive date | 2012-07-01 through latest complete FIRMS archive date |

For easiest coverage of both analysis boxes, the importer can clip a world-area
export into both regions. Use adjacent, non-overlapping July-to-June requests
where the download form limits the request to one year; start MODIS with
2010-07-01 and S-NPP with 2012-07-01. Set each end date to the last date
actually included in that CSV. The exact requested dates and area are required
to decide whether a source-month is complete. Missing months stay unknown; the
importer never fills them with detections.

## Prepare one sidecar for each downloaded CSV

Keep the NASA CSV outside Git. Put one `request.json` beside each CSV in its own subfolder:

```text
NASA_data/
  MODIS_2010_part1/
    request.json
    fire_archive.csv
  SNPP_2012_part1/
    request.json
    fire_archive.csv
```

Example sidecar; enter the dates, exact bounding box, and product version that match that particular FIRMS request:

```json
{
  "product": "MODIS_SP",
  "start_date": "2010-07-01",
  "end_date": "2010-12-31",
  "bbox": [-180, -90, 180, 90],
  "csv_filename": "fire_archive_M-C61_2010.csv"
}
```

Use `MODIS_SP` for MODIS Terra/Aqua standard records or `VIIRS_SNPP_SP` for Suomi NPP standard records. Dates are inclusive. `bbox` is west, south, east, north, exactly as requested from FIRMS. `csv_filename` is optional when there is just one CSV beside the sidecar; name it when the folder also contains an NRT file. The importer uses only this named file and rejects NRT/URT rows. `product_version` is optional when the CSV contains rows from which the version can be read; do not guess a version for an empty file.

If downloads are divided into one-year windows, create one sidecar per file.
Record the exact inclusive dates returned by FIRMS. Overlapping or partial
windows are safe to import, but a month is marked complete only when a request
covers every day of that month and the full study region. Preserve each row's
source `version`; do not combine different MODIS collections into one
calibration or historical comparison.

Some supplied older annual CSVs have no saved request form. To import their
positive records without claiming complete coverage, create explicit
row-only sidecars with:

```json
"coverage_basis": "reconstructed-rows-only"
```

Run `uv run python scripts/prepare_legacy_firms_sidecars.py NASA_data` for the
recognized supplied files. Their month rows remain partial even if the
reconstructed date interval spans a full month. Do not remove that field or
replace it with request metadata unless the original FIRMS request details are
confirmed. The calendar marks detected days from these files as partial and
keeps all absent days unknown.

## Import locally

From the repository root, run:

```bash
uv run python -m fireatlas.archive import-requests NASA_data --db data/fireatlas.sqlite3
```

The command streams the archive CSVs, clips detections to Northern California and Punjab–Haryana, preserves the input file and request hashes, stores monthly version metadata, and can be rerun without duplicating rows. It prints imported rows, complete source-months, and duplicate slices. Keep the original files and sidecars: they are the source needed to reproduce the derived calendar.

The normal browser CSV uploader has a 25 MB limit and can mark only a single exact full month and box. Use the command above for multi-year exports.

## What the app says about coverage

- Complete source export with eligible rows: detections are counted; satellite pass and cloud exposure remain unknown.
- Complete source export with zero eligible rows: zero exported detections; pass, cloud, and no-fire status remain unknown.
- A world-area month with no rows anywhere is left incomplete; without any source record, it cannot safely be promoted to a zero-activity observation. The supplied S-NPP May 2026 month is this case.
- Incomplete or reconstructed row-only source export: positive source records are retained and shown as partial detections; absent dates and zero activity remain unknown. MODIS estimates are used only where export completeness, version match, and the calibration checks support them.
- FIRMS type 0 or missing enters the selected calendar variant. Other detection types remain inspectable in original rows but are excluded from that variant.

Source: [NASA FIRMS Archive Download](https://firms.modaps.eosdis.nasa.gov/download/). The local [data ledger](DATA.md) documents the sample that is currently bundled; the live region status shows what has actually been imported.
