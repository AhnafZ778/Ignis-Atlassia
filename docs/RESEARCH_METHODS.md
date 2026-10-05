# FireAtlas research methods, version 1

The Research Lab is a reproducible exploratory workspace. It does not yet supply calibrated sensor sensitivity, validated fire-event identities or a regional spread model. Synthetic FIRMS-shaped records and generated observation exposure are test fixtures only; the website has no generated-data mode.

## Consolidated workspace

`/research.html` hosts Comparison, Candidate Groups, Sensitivity and Exposure. Candidate/exposure legacy pages are query-preserving aliases. Sensitivity reuses the bounded deterministic assistant operation and does not require conversational inference. A cross-month incoming study keeps its full interval and requires an explicit UTC month intersection. Form edits remain drafts until a calculation succeeds. Late responses from an inactive tab are aborted and cannot commit a newer study’s context. Static hosting provides evidence alternatives and disables new calculations that require the local service.

## Study scope and provenance

Each study selects an AOI, UTC month, inclusive acquisition-date cutoff, candidate distance and date-gap threshold. Only `MODIS_SP` and `VIIRS_SNPP_SP` records are included. NRT and other VIIRS platforms are excluded. Synthetic and authentic source batches cannot be mixed in a study.

The cutoff filters acquisition times, not retrieval/publication history. A later reprocessed record acquired before the cutoff can be included. This is a retrospective study. The implemented historical replay also filters acquisition dates; it does not reconstruct past publication availability.

The report includes method `fireatlas-research-v1`, grid version, parameters, completeness per source, original product versions, source URIs and file hashes. Its SHA-256 identifier hashes the canonical JSON before the `report_id` field is added: sorted keys, compact separators, Python `json.dumps` default ASCII encoding. It identifies content, not scientific approval or a digital signature. The browser export wraps this report and the supplied mask; the hash identifies the report only.

## Sensor overlap

For each source and UTC date, construct a set of existing 1 km EPSG:6933 detection-centroid cells. Multiple pixels in a source/cell/day contribute one element. The daily intersection is shared co-occurrence; the union is total distinct detected cell-days. The source ratio is summed VIIRS cell-days / summed MODIS cell-days. The co-occurrence fraction is summed intersections / summed unions. Zero denominators produce null results.

Daily counts are descriptive imported counts. Both monthly AOI source exports must be complete before the resampling band is considered. Complete CSV exports do not establish valid satellite exposure. Same-day, same-cell observations need not be from matched overpasses or the same physical fire. The [MODIS active-fire product guide](https://lpdaac.usgs.gov/documents/1005/MOD14_User_Guide_V61.pdf) documents fire-mask classes and product caveats; the point export does not carry a complete observation mask.

### Exploratory ratio band

The code resamples paired daily MODIS/VIIRS counts with replacement, using all dates from the study start through the cutoff. Both source counts retain the same selected day index. It draws 1,000 replicates with seed 42 and calculates the ratio of the resampled sums. Replicates with zero MODIS denominator are excluded; fewer than 950 valid replicates suppress the band. Inclusive 2.5th and 97.5th percentiles form the displayed range.

At least ten active union days, complete source exports and no mixed versions within either source are required. The ten-day threshold is a prototype guard, not an established statistical adequacy threshold. Distinct source versions across MODIS and VIIRS are expected; the check only rejects multiple versions *within* a source. The standard [paired bootstrap description](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html) explains resampling shared indices. FireAtlas implements a small deterministic percentile calculation with the Python standard library and does not use SciPy or claim BCa intervals.

This band ignores temporal dependence, unmatched overpasses, heterogeneous exposure and reference-label errors. It is not a calibrated confidence statement about sensor sensitivity. Scientific use needs an overlap-study design, dependence-aware uncertainty, version review and independent validation.

## Candidate detection groups

Nodes are distinct detection cell-days. Two nodes link if their WGS84 geodesic cell-center distance is within the chosen kilometer threshold and their UTC-date difference is within the selected gap. EPSG:6933 is equal-area, so projected x/y distances are not treated as ground kilometers. Connected components produce candidate groups, including singleton nodes. Zero-day gap creates same-day groups.

Membership includes original detection IDs, daily grid coordinates and center locations. IDs are hashes of sorted member detection IDs and change as membership changes. Transitive linking can merge multiple real events; missing detections can split one event. The method does not identify burned area, event perimeters or the number of physical fires. Displayed points are cell centers, not a geographic basemap or boundaries.

Requests are capped at 10,000 pixels and 3,000 unique cell-days. Exceeding a cap rejects the study rather than silently analyzing a truncated sample. Source and candidate settings remain in the exported report.

## Observation-mask contract

The mask adapter accepts a prepared JSON object. It does not read or classify satellite HDF/NetCDF rasters. An upstream pipeline must process pass/cloud/quality masks, geolocate them to the common grid and establish usable observation of each reported cell-day. Partial footprints must not be silently counted as full observed cells. Record those decisions in `method` and source granule identifiers in `provenance`.

```json
{
  "format": "fireatlas-coverage-v1",
  "grid": "ease6933-centroid-1km-v1",
  "bbox": [-122, 39, -120, 41],
  "start_date": "2015-07-01",
  "end_date": "2015-07-31",
  "synthetic": true,
  "provenance": "synthetic://example-only",
  "method": "Illustrative row only; replace with a documented mask derivation.",
  "cells": [
    {"source_id": "MODIS_SP", "date": "2015-07-01", "grid_x": -11686, "grid_y": 4720, "status": "observed"}
  ]
}
```

This one-row example describes the schema, not complete AOI coverage. The website no longer generates a mask; provide a prepared upstream mask file if you have one.

Rules:

- Grid, AOI and study dates must match exactly. Rows must lie within the date window and cells must intersect the AOI. Edge cells remain full analysis units, matching the centroid method; no area-weighted full-AOI rate is implied.
- Every source/cell/day key is unique. Grid indices are integers. Accepted sources are MODIS SP and VIIRS S-NPP SP.
- `observed` contributes one source-specific exposed cell-day. `cloud`, `no_pass` and `unknown` contribute none. Missing rows remain unknown.
- Source and mask synthetic/authentic classes must agree. A detection in an explicit unobserved cell is a conflict and rejects the mask; a detection with no mask row is reported as unmatched and excluded from the rate numerator.
- The import is limited to 20,000 rows and the HTTP request to 3 MB. Uploaded masks are stateless; the browser retains them until the selection changes or the page is closed. No database import or upstream scientific verification occurs.

For each source, let **O** be supplied observed cell-days and **D** be detected cell-days. The displayed rate is `100 × |D ∩ O| / |O|`. Empty exposure or an incomplete FIRMS source export produces a null rate. This is a rate within supplied observed exposure, not an estimate for the full AOI. No joint-sensor exposure is inferred. Source-specific masks can cover different locations; their rates are not automatically comparable.

The test-only synthetic mask fixture assumes daily observation of every selected detection cell by both sources, including non-detection days. This is invented exposure for tests, not a satellite mask. Its `synthetic` flag and method description are retained in test exports.

## API and reproduction

- `GET /api/research?year=2015&month=7&bbox=-122,39,-120,41&distance_km=2&gap_days=1` returns the unmasked study.
- `POST /api/research` accepts `{"config": {...}, "mask": {...}}`; omit or use null for the mask to leave coverage unknown.
- Observation masks must be supplied as a prepared JSON file. The former generated-mask route was retired; a mask upload is validated for scope and consistency but not scientifically certified.
- `fireatlas research` supports the same settings plus a local `--mask` file and `--output` report file.

## Remaining research gates

| Extension | Required evidence before validation |
| --- | --- |
| Calibrated sensitivity | Authentic matched overpasses, usable-observation masks, reference labels, reviewed collection equivalence and independent holdout performance |
| Verified adjusted rates | A documented, tested raster-mask derivation and selection/exposure design |
| Validated candidate events | Reference incident identities, merge/split review and parameter sensitivity across pilot AOIs |
| Optional SAR change | Co-registered before/after SAR, quality masks, processing metadata and a dated optical cross-check |
| Optional spread ensemble | Validated regional terrain/fuels, weather members, a physical spread method, observed arrival references and held-out validation |

The current UI explicitly lists these gates. It does not render synthetic SAR results or spread boundaries as measured evidence.
