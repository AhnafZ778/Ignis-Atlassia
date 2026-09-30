# Native-mask acquisition and validation

## Current result

The supplied `NASA_data/fire_masks/` folder now contains complete local
inventories for both fixed cases. The processor decoded **20 of 20 Grove**
fire-mask granules and retained **15,495 native pixel samples** inside its
study box. It decoded **114 of 114 Park** granules and retained **1,372,872
native pixel samples**. The CMR candidate inventory is 42 MOD14 + 40 MYD14 +
32 VNP14IMG for Park and 9 + 8 + 3 for Grove, with the same counts of
geolocation companions. CMR metadata is an acquisition list, not a pass map.

This is real native-product processing, but it is **centroid sampling only**.
The selected-cell evidence is unreviewed; both cases have a 30-sample raw-cell
review queue with zero human sign-offs, and no-pass or full-cell footprint
coverage remains unknown. FIRMS reconciliation matched 7/7 Grove rows and
3,137/3,137 Park rows within the declared time and distance tolerances (100%,
target ≥98%). Both ledgers are `processed-unreviewed`; neither establishes a
fire perimeter or a complete observation denominator.

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
uv run --with earthaccess==0.19.0 python -m fireatlas.mask_download \
  --case park-2024 --download --clean-partials
```

The download command is resumable: it skips non-empty files already in the
output directory, downloads each missing file through its own temporary file,
and applies a connection/read timeout and retries per URL. This prevents one
stalled LAADS request from holding the whole batch open. A few historical
LAADS rows also get a filename-equivalent Earthdata Cloud fallback. If the
command exits with a failure report, rerun the same command; only the files
still absent are attempted.

If the login fails with `Temporary failure in name resolution` or
`NameResolutionError` for `urs.earthdata.nasa.gov`, no NASA request was made and
the password is not the cause. Restore the workstation's internet, VPN or
proxy DNS first, then check the hostname before rerunning:

```bash
getent hosts urs.earthdata.nasa.gov
curl -I --connect-timeout 10 https://urs.earthdata.nasa.gov
```

The password prompt is intentionally blank. Do not paste credentials into the
terminal transcript or into this repository.

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
require that native stack for displaying the calendar. In this workspace, run
the processor with:

```bash
PYTHONPATH="$PWD:$PWD/.venv/lib/python3.12/site-packages" /usr/bin/python3 -m fireatlas.masks --case grove-2025
PYTHONPATH="$PWD:$PWD/.venv/lib/python3.12/site-packages" /usr/bin/python3 -m fireatlas.masks --case park-2024
```

On another computer, first install a compatible GDAL Python environment with
HDF4, HDF5/netCDF, numpy, and pyproj. Check `gdalinfo --formats`; do not assume an
unqualified pip GDAL package includes HDF4. A missing reader or shape mismatch is
recorded as a failed granule. The MOD03 reader uses the native EOS swath names
for Latitude and Longitude, which GDAL does not list among the root HDF
subdatasets. The commands produce a local SQLite store at
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
  Reported grid-cell centre coordinates are rounded to six decimal degrees for
  cross-environment reproducibility; native sample coordinates remain exact.
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
  are exported individually. This rule matched 7/7 Grove records and 3,137/3,137
  Park records (100%), passing the declared ≥98% target. That result does not
  waive the human review gate or establish a full pass/cloud denominator.

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

For a quick release consistency check across both fixed cases, run:

```bash
PYTHONPATH="$PWD" /usr/bin/python3 scripts/verify_native_mask_status.py \
  --db data/fireatlas.sqlite3
```

This checks that native counts are within their frozen inventory, the 98% reconciliation
flag agrees with its numerator and denominator, all four validation gates are present, and
the CMR metadata still distinguishes candidate metadata from native observations. A passing
result is an integrity check; it does not mark the pending inventory, raw-cell review, or
independent-review gates complete.

## Human review gates

The ZIP's `case.json → native_masks.raw_mask_review.samples` provides up to 30
deterministically selected native samples stratified by sensor and mask class.
`native_review_template.json` is the matching blank form with the source hashes
and immutable expected sample context.
The Data & Method page exposes the same blank form as **Download blank
native-mask review form** for each case. In a running local server it is also
available at `/api/validity/review-template?case=grove-2025` (or
`park-2024`); a static export places it at
`data/v2/validity/grove-2025-review-template.json` beside the ZIP. These are
review inputs only, never a completed sign-off.
A reviewer must open the original named files, locate the row/sample, inspect the
class and coordinates, compare the resulting grid, and record discrepancies.
The software does **not** auto-sign that review. The repository now provides a
hash-bound review form and validator. For reviewers who do not want to edit JSON
by hand, open **Review native masks** from the Data & Method evidence drawer (or
`/review.html?case=grove-2025`). The browser form loads the same hash-bound
template, shows the immutable source pixel, class, coordinate and grid context
for all 30 samples in each processed case, requires an observed class/coordinate/grid assignment and an
outcome for each sample, and downloads the completed JSON. The browser never marks a sample as reviewed
from the expected value. Run the CLI validator below before installing a real
reviewer record:

```bash
# Write a blank form containing the exact native sample keys and input hashes.
uv run python -m fireatlas.mask_review --case grove-2025 \
  --template /tmp/grove-native-review.json

# After a qualified reviewer fills every sample and the interpretation:
uv run python -m fireatlas.mask_review --case grove-2025 \
  --review /tmp/grove-native-review.json --install
```

Validation requires all 30 outcomes, an observed native class, coordinates and
grid assignment for each sample, notes for disagreements or unresolved cells,
matching source/geolocation hashes, reviewer identity and an ISO timestamp.
`--install` writes only to the
ignored local review store; it does not edit raw NASA files or claim scientific
independence. Set `reviewer.independent` to `true` only when the reviewer is
actually independent of the processor. Until a real reviewer supplies this
record, the UI and ZIP keep both review gates pending. The additional CAL FIRE
association cohort remains a separate check, not a calibrated sensitivity
evaluation.

## Sources and remaining limits

Class definitions follow the [MODIS C6/C6.1 guide](https://modis-fire.umd.edu/files/MODIS_C6_C6.1_Fire_User_Guide_1.0.pdf)
and [VIIRS Collection 2 guide](https://www.earthdata.nasa.gov/s3fs-public/2024-07/VIIRS_C2_AF-375m_User_Guide_1.0.pdf).
The original LP DAAC MODIS guide URL timed out and the Earthdata VIIRS PDF
returned 403 during this session; the MODIS team's guide and NASA LAADS native
filespec were accessible as additional implementation references. The current
run decoded authentic HDF4 MODIS and netCDF VIIRS masks from both cases. This
verifies that the adapters ran on those supplied files, not that every class or
pixel has been independently validated. No independent reviewer or full-footprint
observation denominator is claimed. The Grove and Park reconciliations are
100% for their imported FIRMS rows; they are not a completeness claim for
satellite opportunity.

## Checks performed on this implementation

- Full regression suite: the current count is recorded in the scorecard after the 2006 history and native evidence refresh (including the browser-review route contract).
- Additional MODIS confidence-boundary checks: 29/30/79/80 handled according to the product guide; mask boundary suite passed.
- Both authentic case ZIPs pass the application verifier and the separate analytical recount across the project and system Python environments: Park **3,137 pixels / 1,606 cell-days**, Grove **7 pixels / 4 cell-days**. Each ZIP includes `native_review_template.json`; neither has a completed human review.
- Native HDF4 and netCDF readers decoded all supplied Park and Grove masks and geolocation companions; the four fabricated netCDF samples remain a separate boundary smoke test.
- Chrome at 1440, 768 and 390 px with remote browser requests blocked and reduced motion: gallery open/close, six image assets, actual pending gate counts, source selection and Grove switch passed. No JavaScript page errors or horizontal overflow occurred. Screenshots were inspected. This is not the five-viewer comprehension study.
- Wheel/source distribution build, JavaScript syntax and diff whitespace checks passed. Incident image assets are now included in the package.
- Grove was reprocessed from the supplied native files: **20 of 20** fire-mask granules and **15,495** clipped native samples. Park was reprocessed at **114 of 114** and **1,372,872** clipped native samples. No login credentials were supplied or saved during this run.
