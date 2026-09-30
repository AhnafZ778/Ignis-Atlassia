# Perfected plan authority and delta

**Authoritative plan:** `docs/winning-plan/FireAtlas_Updated_Perfected_Winning_Plan.pdf`  
**Superseded planning snapshot:** `docs/winning-plan/FireAtlas_Winning_Plan.pdf`  
**Received:** 30 September 2026

This source file makes the supplied perfected plan the working specification. The earlier
PDF remains useful as a record of decisions already made, but its score ceiling and task order
must not be treated as a promise. A score changes only when the evidence gate below is passed.

## What the perfected plan changes

| New requirement | What the repository can claim today | Gate still open |
|---|---|---|
| Primary unit is **VIIRS-equivalent active-fire cell-days on a common 1 km grid**; native VIIRS 375 m remains detail. | The calendar and Sensor Bridge label the common-grid unit; imported rows retain native source fields. The current transform is detection-centroid binning, not a native fire-mask resampling. | Native-mask/common-grid agreement and an independent review. |
| Show MODIS-only, VIIRS-only, both, and gap/unknown states. | The Sensor Bridge and calendar states expose these categories for the imported source-export window. | Complete archive windows and pass/cloud evidence for stronger coverage claims. |
| Show raw Fire Radiative Power separately in MW/day. | Raw FRP is shown per source and is never added to cell-days or combined across sensors. | Check every displayed total against the current export after any data refresh. |
| Add MCD64A1 Collection 6.1 as lagged burned-area corroboration. | Dated Burn Date and QA rasters are hash-bound in the evidence report; the UI shows counts only for matching months and keeps this context separate from active-fire detections. | Independently review the dated checks before claiming a passed corroboration gate. |
| Distinguish observed, scaled, unknown, documented processing gap, and complete zero export. | Existing calendar and evidence views preserve documented gaps, scaled values, unknown partial exports, and zero-export limitations. A scaled outage day carries `evidence_state=scaled` plus `coverage_state=documented_processing_gap`, and is written as “gap · scaled estimate”. | Verify the state on every complete/partial window and keep pass/cloud opportunity unknown without masks. |
| Provide a shareable evidence card. | The local calendar can create a card and a parameterized link from the same API/static JSON as the selected result. | Verify the link and card on the public host. |
| Keep Rapid Pulse separate from historical science. | The historical calendar does not silently mix near-real-time records; a separate rapid product is deferred. | Build only after P0/P1 and give it a separate mode, calibration, and limits. |
| Demonstrate See → Compare → Verify → Share, with a 30-second cut and a 90-second narrated cut. | The local storyboard and browser checks cover the existing globe, calendar, evidence drawer, method audit, and local card. | Capture the new bridge/card sequence and rehearse it on the public URL. |

## Non-negotiable scientific rules

1. Never compare raw MODIS 1 km pixels directly with raw VIIRS 375 m pixels.
2. Deduplicate within each sensor and UTC day before aggregation.
3. Never add both sensors into one activity count. Use one selected reference observation and
   show the other sensor for comparison.
4. Keep FRP as a separate source-context measure. It is not burned area or fire severity.
5. A complete zero export means zero eligible rows in that export. It does not prove a clear
   pass, cloud-free observation, or no fire.
6. Missing, incomplete, or documented-outage inputs remain unknown or gap-marked.
7. MCD64A1 is lagged burned-area context, never active-fire ground truth for the same day.
8. Historical claims must show product version, request coverage, retrieval/hash provenance,
   and the uncertainty interval. A weak held-out interval stays labelled weak.
9. The existing globe, its controls, its overlays, and its handoff remain unchanged.

## Release gates under the perfected plan

### P0 — required before a broader historical claim

- Recover missing standard archive windows for both study regions.
- Preserve request metadata, product version, UTC range, bounding box, retrieval date, SHA-256,
  row count, and excluded type counts.
- Reproduce common-grid daily and monthly totals from the source rows after deduplication.
- Keep all partial and undocumented windows unknown; do not fill gaps with generated values.

### P1 — highest-value judge path

- Sensor Bridge with MODIS-only / VIIRS-only / both / gap states.
- Separate raw FRP context card.
- Visible state badges and patterns for observed, scaled, unknown, documented gap, and complete
  zero export.
- MCD64A1 context only after authentic input and independent review; otherwise keep the explicit
  active-fire-only state.
- Shareable evidence card with selected value, state, versions, source hashes, and limits.
- One external usability check and a public no-credential demo.

### P2 — deferred until P0 and P1 pass

FIRMS Recent Pulse, NOAA-20 supplemental data, custom AOI, multilingual labels, and any new
operational workflow. No spread model, evacuation recommendation, drone route, wind guidance,
causal classification, or second globe belongs in this challenge path.

## Score discipline

The current weighted implementation score remains **41.6 / 100**. The previous **44.8 / 100**
claim ceiling and **93 / 118** local-rubric claim came from the earlier plan and are withdrawn until
the perfected-plan P0/P1 gates, public URL, and eligibility ruling are complete. The perfected PDF
is a blueprint, not evidence of a NASA judge score. Recalculate only from checked files, test output,
or a public URL that was actually opened.
