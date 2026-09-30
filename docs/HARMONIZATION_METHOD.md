# MODIS–VIIRS harmonization method

The perfected plan names the primary unit **VIIRS-equivalent active-fire cell-days on a
common 1 km grid**. “VIIRS-equivalent” identifies the selected reference scale; it is not a
claim that the two instruments have equal detection probability. Native source detail remains
available: MODIS is represented as approximately 1 km source pixels and the imported Suomi NPP
record as 375 m VIIRS source pixels. The landing page’s Sensor Bridge shows the transformation
and keeps sensor-only, shared, and gap days separate.

FireAtlas exposes a month-level method audit at `/api/harmonization` and on the
Data & Method page (`/method.html#harmonization-audit`). The audit is intentionally descriptive: it makes the
comparison reproducible without claiming that the two instruments have equal
detection probability.

## Input contract

- Each imported row keeps its source ID, platform, product version, processing
  level, acquisition timestamp, native confidence, FRP, original row JSON,
  source URI and file SHA-256.
- Acquisition timestamps are parsed as UTC. The calendar and daily replay use
  UTC dates, so a local-time conversion cannot move a record between days.
- MODIS and VIIRS are assigned to the common 1 km EPSG:6933 equal-area grid by
  detection centroid. The grid implementation is versioned as
  `ease6933-centroid-1km-v1`.
- The calendar variant includes FIRMS `type` 0 or a missing type value, at all
  source confidence levels. Other types remain in inspectable source rows but
  do not contribute to the displayed calendar, harmonization audit, or daily
  aggregate bundle.

## Calculation

For each UTC day, the joint series takes the union of the selected source grid
cells. A grid cell contributes at most one detected cell-day, even when several
pixels or both sensors report it. The audit also retains per-source raw pixel
counts and per-source cell-day counts, plus the intersection of MODIS and VIIRS
cell sets on each day.

The audit flags mixed product versions within a source for review. A single
version in each source is still insufficient for a calibrated sensitivity
comparison; matched overpasses and observation masks are separate requirements.
It also checks product versions in the same-month prior years used by the
baseline. The supplied July 2022 MODIS archive has version `6.03` in the
Northern California box, while July 2025 uses `61.03`; the audit marks the
2025 historical comparison as mixed-version and the interface treats its
cell-day difference as descriptive.

Monthly totals are the sum of complete daily cell-day counts. A month without a
verified complete export remains unknown; partial records are shown as a lower
bound. Prior-year medians require at least three complete same-month exports for
the same source cohort and AOI.

The local archive now contains positive records from older annual files back
to July 2006 MODIS and July 2012 S-NPP. Their original FIRMS request metadata
were unavailable, so those inputs are marked `reconstructed-rows-only`: their
detection days are visible as partial, and their non-detection days cannot
enter a monthly harmonized value or baseline. The request-verified joint
monthly comparison starts in July 2022; S-NPP May 2026 remains unknown because
the supplied worldwide S-NPP export had no rows for that month.

## Interpretation limits

This is not a burned-area product, fire perimeter, fire count, or sensor
sensitivity calibration. Same-cell same-day overlap does not prove matched
overpasses or the same physical fire. FIRMS point exports alone do not provide
the pass and cloud masks needed to say that a zero-detection day was observed
fire-free. MODIS and VIIRS era changes must therefore be interpreted with the
source cohort and processing level visible in the audit.

## Raw FRP and independent corroboration

Daily aggregates retain each source’s raw FIRMS Fire Radiative Power sum in MW/day as
secondary context. FRP is displayed per sensor and is never added to the harmonized
cell-day measure. The perfected plan calls for MCD64A1 Collection 6.1 burned-area context
as a lagged, independent product. Dated Burn Date and QA rasters are now hash-bound in
`fireatlas/samples/mcd64_corroboration.json`; the UI shows mapped counts for matching months
as separate context. It does not treat them as active-fire truth, a pass/cloud mask, or a
perimeter, and independent review remains pending.

NASA advises scientific users to use standard processing when available; the
importer rejects rows labelled NRT/RT/URT under a standard source. NRT products
remain available as separate, explicitly labelled series for recent browsing.

## Reproduce an audit

```bash
curl 'http://127.0.0.1:8000/api/harmonization?year=2025&month=7&series=joint&bbox=-122.2,38.8,-120,41'
```

The UI’s **Method audit JSON** button downloads the same response used to render
the panel. The browser now queries the configured import database only; the
retired synthetic showcase cannot be selected from a page or API parameter.
