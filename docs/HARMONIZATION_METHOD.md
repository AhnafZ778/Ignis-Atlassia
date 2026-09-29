# MODIS–VIIRS harmonization method

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

## Interpretation limits

This is not a burned-area product, fire perimeter, fire count, or sensor
sensitivity calibration. Same-cell same-day overlap does not prove matched
overpasses or the same physical fire. FIRMS point exports alone do not provide
the pass and cloud masks needed to say that a zero-detection day was observed
fire-free. MODIS and VIIRS era changes must therefore be interpreted with the
source cohort and processing level visible in the audit.

NASA advises scientific users to use standard processing when available; the
importer rejects rows labelled NRT/RT/URT under a standard source. NRT products
remain available as separate, explicitly labelled series for recent browsing.

## Reproduce an audit

```bash
curl 'http://127.0.0.1:8000/api/harmonization?demo=1&year=2015&month=7&series=joint&bbox=-122,39,-120,41'
```

The UI’s **Method audit JSON** button downloads the same response used to render
the panel. Synthetic output is labelled and remains separate from authentic
imports.
