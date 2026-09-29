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

Park's 25 July result is **603 MODIS pixels, zero S-NPP pixels, and 415 detected 1 km cells**. This is a period of high *observed detection activity*, not a calibrated increase in burning. NASA's [FIRMS outage notice](https://firms.modaps.eosdis.nasa.gov/notifications/firms/outages.html) says S-NPP processing stopped at 05:28 UTC on 24 July and remained unresolved through 28 July. The calendar marks 24 July as a partial-day notice and 25–28 July as processing-gap days. It does not infer a ground-cell pass or cloud state from the notice. Zero VIIRS detections on those days must not be read as zero fire.

The fixed additional-incident check follows every **288** July links in the 2024 and 2025 CAL FIRE year archives. After excluding the two illustrated cases and retaining published start coordinates inside the archive area, **25 incidents** remain: **7** have a first imported standard FIRMS point within 5 km and 48 hours after the interpreted start, while **18** have no nearby point. These are temporal-spatial associations, not sensitivity, recall, or miss-rate measurements because the archive does not yet contain usable pass and cloud masks. Every eligible incident, result, official URL, and rectangular candidate-row prefilter is included in the evidence ZIP.

The pixel-count sensitivity audit recomputes Park at 500 m, 1 km, and 2 km centroid grids: **2,400 / 1,606 / 685** detected cell-days with all confidence classes, and **2,313 / 1,565 / 675** after omitting VIIRS `l` and MODIS confidence below 30. These are counts on different grids, not estimates of fire area or sensor agreement. Grove's corresponding all-class counts are **5 / 4 / 2**. Same-cell, same-day co-detection is a descriptive count; matched overpasses within 90 minutes require usable mask observations that are not yet available.

A public [NASA CMR](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html) metadata snapshot made on 29 September 2026 lists **42 Terra MOD14, 40 Aqua MYD14, and 32 S-NPP VNP14IMG** candidate Park fire-mask granules intersecting the case box and window. The Grove window lists **9 / 8 / 3**. Each has a same-start-time geolocation product in the metadata inventory, but the files have not been retrieved or checked. The clipped inventory, CMR query URLs, product identifiers, and protected download URLs are in `fireatlas/samples/validity_cmr_inventory.json` and the case ZIP. Refresh the public metadata with `uv run python -m fireatlas.granules`. CMR search results are an acquisition list, **not** evidence of valid ground-cell observation or complete swath processing.

## Reproduce and inspect

Start the local site with `uv run python -m fireatlas.web --db data/fireatlas.sqlite3 --port 8000`. A clean database loads the bundled compact NASA archive. Open `/method.html`, choose Park or Grove, scrub a UTC day, and select a detection circle. **Inspect the underlying evidence** shows acquisition time, platform, version, confidence, coordinates, source file hash, and row identifier. Download the case ZIP and run:

```bash
uv run python -m fireatlas.validity path/to/fireatlas_validity_park-2024.zip
```

The ZIP contains clipped original CSV fields, source request identifiers and hashes, the displayed case audit, public CMR granule metadata, method, contextual incident citation, NASA outage citation where applicable, and a manifest. The verifier checks checksums, independently recomputes each row's EPSG:6933 grid assignment from coordinates, and recounts the displayed figures using the repository method. It does **not** authenticate the original NASA download, inspect raw swath masks, or constitute independent scientific review. Original worldwide archives stay outside Git; the [archive inventory](NASA_ARCHIVE_IMPORT.md) describes the compact derivative.

## Open scientific gates

1. Obtain standard MOD14/MYD14 and VNP14IMG fire-mask granules plus geolocation for both windows with a valid Earthdata/LAADS account. Inventory every expected granule, verify hashes, decode valid clear/fire/cloud/unusable cells, and keep any absent swath unknown. A processing outage is not automatically a no-pass classification.
2. Compare FIRMS rows with mask fire detections, publish all mismatches, check at least 30 sampled mask cells against raw products, and then calculate a **usable-observation** paired comparison within 90 minutes. The present CSV export alone cannot meet these gates.
3. The predeclared additional-incident rule is: follow every July 2024 and July 2025 link in CAL FIRE's published year archive, retain incidents with a published start coordinate inside `[-122.2,38.8,-120,41]`, and exclude the selected Park and Grove examples from evaluation. For each remaining incident with a published start time, report the first imported standard FIRMS detection within 5 km and within 48 hours **after** that time, or a miss. Keep inaccessible pages, missing coordinates/times, and outside-area incidents in an exclusion ledger. This tests temporal and spatial association only; unknown pass/cloud coverage prevents an unbiased detection-rate claim.
4. Ask a reviewer outside the coverage implementation to inspect the raw-mask samples, source availability, and interpretation. Run uncoached desktop and phone comprehension checks before claiming a near-full validity result.

The published [MODIS](https://lpdaac.usgs.gov/documents/1005/MOD14_User_Guide_V61.pdf) and [VIIRS Collection 2](https://www.earthdata.nasa.gov/s3fs-public/2024-07/VIIRS_C2_AF-375m_User_Guide_1.0.pdf) guides define native mask classes and geolocation requirements. The site currently renders pass and cloud coverage as **unknown** throughout these cases.

## Native-mask tooling update

The native-mask processor and exact download helper are now implemented. See
[NASA native-mask acquisition and validation](NATIVE_MASK_VALIDATION.md) for
terminal commands, the conservative centroid-sampling method, and remaining
footprint and human-review gates. The case ZIP now includes `native_masks.json`
with all frozen input-file statuses, clipped native samples when available, and
a reproducible native summary. A separate analytical `fireatlas.validation_check`
recounts the detection figures without importing the calendar transform. No raw
mask was available in this workspace at implementation time; neither selected
case has passed the raw-mask review or 98% reconciliation gate.
