# Park and Grove historical evidence protocol

The two fixed examples use imported NASA FIRMS **standard-product detection exports**. They are an inspectable burning-activity calendar, not a measured fire perimeter, burned area, or satellite observation-coverage map. The definitions below are frozen in `fireatlas/validity.py`. These cases were chosen for the visual study; they are **not** an independently selected evaluation cohort.

| Case | UTC days | Area, west/south/east/north | Independent contextual record |
| --- | --- | --- | --- |
| Park Fire | 17–31 July 2024 | `-122.0,39.5,-121.3,40.5` | [CAL FIRE Park Fire](https://www.fire.ca.gov/incidents/2024/7/24/park-fire/) |
| Grove Fire | 4–6 July 2025 | `-121.55,39.25,-121.28,39.48` | [CAL FIRE Grove Fire](https://www.fire.ca.gov/incidents/2025/7/4/grove-fire) |

Acquisition dates use UTC. The reported local incident start is interpreted in `America/Los_Angeles` only to calculate the first imported detection within 5 km **after** that time. CAL FIRE supplies contextual event timing and location; it does not generate NASA counts. The association does not prove that a specific hotspot belongs to the incident.

## Working result from the bundled archive

| Case | Original detection pixels | Joint detected 1 km cell-days | First nearby post-report detection |
| --- | ---: | ---: | --- |
| Park | 3,137 | 1,606 | MODIS, 24 July 2024 22:33 UTC, 1.23 km from reported start |
| Grove | 7 | 4 | VIIRS S-NPP, 4 July 2025 22:10 UTC, 0.29 km from reported start |

Park's 25 July result is **603 MODIS pixels, zero S-NPP pixels, and 415 detected 1 km cells**. This is a period of high *observed detection activity*, not a calibrated increase in burning. NASA LDOPE's [final outage record](https://landweb.modaps.eosdis.nasa.gov/displayissue?id=716) gives the S-NPP science-product outage as 24 July 2024 05:24 UTC through 29 July 2024 15:18 UTC, inclusive. The first and last UTC dates are partial; the days between are within the documented interval. The notice does not establish a ground-cell pass or cloud state. Zero VIIRS detections must not be read as zero fire.

The fixed additional-incident check follows every **288** July links in the 2024 and 2025 CAL FIRE year archives. After excluding the two illustrated cases and retaining published start coordinates inside the archive area, **25 incidents** remain: **7** have a first imported standard FIRMS point within 5 km and 48 hours after the interpreted start, while **18** have no nearby point. These are temporal-spatial associations, not sensitivity, recall, or miss-rate measurements because the archive does not yet contain usable pass and cloud masks. Every eligible incident, result, official URL, and rectangular candidate-row prefilter is included in the evidence ZIP.

The pixel-count sensitivity audit recomputes Park at 500 m, 1 km, and 2 km centroid grids: **2,400 / 1,606 / 685** detected cell-days with all confidence classes, and **2,313 / 1,565 / 675** after omitting VIIRS `l` and MODIS confidence below 30. These are counts on different grids, not estimates of fire area or sensor agreement. Grove's corresponding all-class counts are **5 / 4 / 2**. Same-cell, same-day co-detection is a descriptive count; matched overpasses within 90 minutes require usable mask observations that are not yet available.

A public [NASA CMR](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html) metadata snapshot made on 29 September 2026 lists **42 Terra MOD14, 40 Aqua MYD14, and 32 S-NPP VNP14IMG** candidate Park fire-mask granules. The Grove window lists **9 / 8 / 3**. Local processing decoded **20 of 20 Grove** fire-mask granules and **114 of 114 Park** granules, paired with same-time geolocation files, and retained 15,495 and 1,372,872 clipped native pixel samples respectively. FIRMS reconciliation is 7/7 for Grove and 3,137/3,137 for Park. The CMR inventory and identifiers show expected products only, not valid ground-cell observation or complete swath coverage; both native ledgers remain unreviewed.

## Reproduce and inspect

Start the local site with `uv run python -m fireatlas.web --db data/fireatlas.sqlite3 --port 8000`. A clean database loads the bundled compact NASA archive. Open `/method.html`, choose Park or Grove, scrub a UTC day, and select a detection circle. **Inspect the underlying evidence** shows acquisition time, platform, version, confidence, coordinates, source file hash, and row identifier. Download the case ZIP and run:

```bash
uv run python -m fireatlas.validity path/to/fireatlas_validity_park-2024.zip
```

The ZIP contains clipped original CSV fields, source request identifiers and hashes, the displayed case audit, public CMR granule metadata, method, contextual incident citation, NASA outage citation where applicable, and a manifest. The verifier checks checksums, independently recomputes each row's EPSG:6933 grid assignment from coordinates, and recounts the displayed figures using the repository method. It does **not** authenticate the original NASA download, inspect raw swath masks, or constitute independent scientific review. Original worldwide archives stay outside Git; the [archive inventory](NASA_ARCHIVE_IMPORT.md) describes the compact derivative.

## Open scientific gates

1. Have an independent reviewer inspect the Park and Grove native samples, verify hashes and class interpretation, and then extend the centroid evidence with independently verified swath footprints. Inventory and decode valid clear/fire/cloud/unusable cells while keeping any absent swath unknown. A processing outage is not automatically a no-pass classification.
2. Compare FIRMS rows with mask fire detections, publish all mismatches, check at least 30 sampled mask cells against raw products, and then calculate a **usable-observation** paired comparison within 90 minutes. The present CSV export alone cannot meet these gates.
3. The predeclared additional-incident rule is: follow every July 2024 and July 2025 link in CAL FIRE's published year archive, retain incidents with a published start coordinate inside `[-122.2,38.8,-120,41]`, and exclude the selected Park and Grove examples from evaluation. For each remaining incident with a published start time, report the first imported standard FIRMS detection within 5 km and within 48 hours **after** that time, or a miss. Keep inaccessible pages, missing coordinates/times, and outside-area incidents in an exclusion ledger. This tests temporal and spatial association only; unknown pass/cloud coverage prevents an unbiased detection-rate claim.
4. Ask a reviewer outside the coverage implementation to inspect the raw-mask samples, source availability, and interpretation. Run uncoached desktop and phone comprehension checks before claiming a near-full validity result.

The published [MODIS](https://lpdaac.usgs.gov/documents/1005/MOD14_User_Guide_V61.pdf) and [VIIRS Collection 2](https://www.earthdata.nasa.gov/s3fs-public/2024-07/VIIRS_C2_AF-375m_User_Guide_1.0.pdf) guides define native mask classes and geolocation requirements. The top-level case coverage remains **unknown**. Grove and Park display sampled native fire, clear, or cloud classes for processed centroids; pending human review and missing full-footprint accounting do not establish full-cell exposure.

## Native-mask tooling update

The native-mask processor and exact download helper are now implemented. See
[NASA native-mask acquisition and validation](NATIVE_MASK_VALIDATION.md) for
terminal commands, the conservative centroid-sampling method, and remaining
footprint and human-review gates. The case ZIP now includes `native_masks.json`
with all frozen input-file statuses, clipped native samples when available, and
a reproducible native summary. A separate analytical `fireatlas.validation_check`
recounts the detection figures without importing the calendar transform. Grove's
native files are available and its reconciliation gate passes for 7/7 FIRMS
rows; Park's passes for 3,137/3,137. Raw-mask review and full-footprint
coverage gates remain open for both cases.
