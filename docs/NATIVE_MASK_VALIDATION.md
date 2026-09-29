# Native-mask acquisition and validation

## Current result

The supplied NASA files are **detection CSVs**, not native fire-mask swaths. On
29 September 2026 a request to the first protected Park MOD14 URL returned HTTP
403. No raw mask or geolocation files were available locally. The frozen CMR
inventory lists 228 Park files and 40 Grove files (134 fire masks and 134
geolocation companions in total). It is an acquisition list, not a pass map.

The project now has a processor, a portable native-evidence extension, a separate
analytical recount, and visual validation gates. These are implemented tooling;
they have not been validated on authentic native swaths in this workspace.
Human review and full footprint coverage are still open requirements.

## Download the exact files

Start with Grove: it requires only 40 files. Run these commands in the project
folder. Credentials are entered into your own terminal through NASA's supported
`earthaccess` client; the helper requests no persistent credential storage.

```bash
# Generate the exact filenames and NASA URLs without logging in:
uv run python -m fireatlas.mask_download --case grove-2025

# Retrieve those exact URLs; this prompts for your Earthdata Login:
uv run --with earthaccess==0.19.0 python -m fireatlas.mask_download --case grove-2025 --download

# Retrieve the larger Park case:
uv run --with earthaccess==0.19.0 python -m fireatlas.mask_download --case park-2024 --download
```

Create or recover your own account at <https://urs.earthdata.nasa.gov/>. A FIRMS
MAP_KEY is not an Earthdata Login. If NASA asks you to authorize the supplying
DAAC application, do that in your own browser and retry. Do not send account
passwords or tokens to the project team. If an account cannot access the frozen
URL, use Earthdata Search to locate that same filename/version; do not substitute
an NRT, tiled, burned-area, 750 m VIIRS, or unrelated later collection product.
The URLs span LP DAAC and LAADS storage. A failed download leaves that file missing.

The helper writes `NASA_data/fire_masks/download_checklist.csv`. Browser/manual
alternative: sign in at <https://search.earthdata.nasa.gov/> and retrieve the
listed `.hdf`/`.nc` files using the exact producer filename. Put files under
`NASA_data/fire_masks/` (nested folders are allowed). For a manual geographic
search, the frozen windows are:

| Case | UTC window | west,south,east,north | Products |
|---|---|---|---|
| Grove | 4–6 July 2025 | `-121.55,39.25,-121.28,39.48` | MOD14/MYD14 061, VNP14IMG 002; MOD03/MYD03 6.1, VNP03IMG 2 |
| Park | 17–31 July 2024 | `-122,39.5,-121.3,40.5` | Same six products |

## Decode after downloading

This workstation's `/usr/bin/python3` has GDAL 3.8.4, numpy and pyproj with native
HDF4 and netCDF support. The default `uv` environment intentionally does not
require that native stack for displaying the calendar. Run the processor with
that system interpreter here:

```bash
python3 -m fireatlas.masks --case grove-2025
python3 -m fireatlas.masks --case park-2024
```

On another computer, first install a compatible GDAL Python environment with
HDF4, HDF5/netCDF, numpy, and pyproj. Check `gdalinfo --formats`; do not assume an
unqualified pip GDAL package includes HDF4. A missing reader or shape mismatch is
recorded as a failed granule. The commands produce a local SQLite store at
`data/validity_masks.sqlite3`. Raw files, this store, and credentials stay outside
Git. Refresh the site after processing; derived evidence is included in the
case ZIP. The CLI reruns idempotently, replacing prior results for expected files.

## What the processor establishes

- It matches exact frozen filenames and a unique same-start-time geolocation
  companion. It hashes both native inputs and refuses ambiguous duplicates.
- It reads the native 2D mask and equal-shaped latitude/longitude arrays in
  bounded strips; geolocation is never guessed or resized. netCDF is read with
  bottom-up flipping disabled so source row/sample positions remain inspectable.
- It keeps native row/sample indices, original coordinates and class codes for
  every centroid inside the case box, and assigns the existing EPSG:6933 grid.
- Codes 7–9 establish sampled fire; codes 3 and 5 supply non-fire samples; code 4
  supplies cloud samples. Codes 0–2, 6, mixed clear/cloud cells and absent samples
  remain unknown. Native confidence classes stay separate.
- A source/cell/day with a fire sample is detected. A sampled non-fire/cloud day
  additionally requires every candidate granule for that source to be processed
  and all sampled pass states to agree. Missing files cannot create a clear day.
- It creates descriptive usable pairs in the same centroid grid cell, with all
  four granule interval endpoint differences at most 90 minutes. Each pass is
  used at most once per cell, including across UTC midnight.
- FIRMS reconciliation requires the same platform, a native fire centroid within
  100 metres, and a time within the granule interval plus a 60-second minute
  rounding allowance. Matches, unreconciled rows and confidence disagreements
  are exported individually. Matching tolerance must be evaluated on real files;
  the target of 98% is a gate, not an achieved result.

**Centroid samples do not establish complete observation of an entire 1 km cell.**
No-pass is deliberately never produced: it needs independently verified swath
footprints and a complete observation inventory. Invalid geolocation is counted
per input; missing or ambiguous geography is not filled. This processor therefore
provides inspectable sample evidence while full coverage validation remains open.
Hashes establish consistency, not an official NASA authenticity signature.

## Independent computational recount

Download the case ZIP from the website. Both commands run without the server:

```bash
uv run python -m fireatlas.validity ~/Downloads/fireatlas_validity_grove-2025.zip
python3 -m fireatlas.validation_check ~/Downloads/fireatlas_validity_grove-2025.zip
```

The second verifier is separate stdlib code and uses an analytical WGS84
EPSG:6933 transform, rather than importing the calendar/grid implementation. It
recounts source pixels, daily union/overlap, confidence/grid sensitivity, and
selected-day native class histograms from frozen inputs. Neither verifier is an
independent scientific review of raw NASA observations. Original native files
are identified by hashes and filename in the ZIP; the clipped samples reproduce
the sample-based figures.

## Human review gates

The ZIP's `case.json → native_masks.raw_mask_review.samples` provides up to 30
deterministically selected native samples stratified by sensor and mask class.
A reviewer must open the original named files, locate the row/sample, inspect the
class and coordinates, compare the resulting grid, and record discrepancies.
The software does **not** auto-sign that review. Collect reviewer name, date,
input hashes, each sample outcome, and interpretation before marking it completed.
The UI intentionally keeps review pending until that evidence exists and a
review-ingestion procedure is implemented. The additional CAL FIRE association
cohort remains a separate check, not a calibrated sensitivity evaluation.

## Sources and remaining limits

Class definitions follow the [MODIS C6/C6.1 guide](https://modis-fire.umd.edu/files/MODIS_C6_C6.1_Fire_User_Guide_1.0.pdf)
and [VIIRS Collection 2 guide](https://www.earthdata.nasa.gov/s3fs-public/2024-07/VIIRS_C2_AF-375m_User_Guide_1.0.pdf).
The original LP DAAC MODIS guide URL timed out and the Earthdata VIIRS PDF
returned 403 during this session; the MODIS team's guide and NASA LAADS native
filespec were accessible as additional implementation references. C2 native
adapter verification on actual files is still required. No independent reviewer,
98% native reconciliation result, or full footprint observation denominator is
claimed by this change.

## Checks performed on this implementation

- Full regression suite: **80 tests passed**.
- Additional MODIS confidence-boundary checks: 29/30/79/80 handled according to the product guide; mask boundary suite passed.
- Both authentic case ZIPs pass the separate analytical recount: Park **3,137 pixels / 1,606 cell-days**, Grove **7 pixels / 4 cell-days**.
- Native netCDF reader smoke check: four **fabricated** samples only, run with system GDAL; no authentic swath reader verification is claimed.
- Chrome at 1440, 768 and 390 px with remote browser requests blocked and reduced motion: gallery open/close, six image assets, actual pending gate counts, source selection and Grove switch passed. No JavaScript page errors or horizontal overflow occurred. Screenshots were inspected. This is not the five-viewer comprehension study.
- Wheel/source distribution build, JavaScript syntax and diff whitespace checks passed. Incident image assets are now included in the package.
- Authentication-dependent download was not run; no login credentials were supplied or saved. Both native processors ran with missing inputs and correctly reported **0 processed**.
