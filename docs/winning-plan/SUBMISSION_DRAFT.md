# NASA Space Apps project-page draft

**Status: draft only. Do not submit until Gate G0 has a written ruling and the required public links are verified.** The repository contains substantial work started before the 14–15 November 2026 event; local-event rules may prohibit submitting pre-developed work.

## Project details

- **Project:** FireAtlas
- **Challenge:** Harmonization of MODIS and VIIRS Hot Spots
- **Public project/demo URL:** `[MISSING — deploy and verify]`
- **Public source repository:** `[MISSING — verify that the configured repository is public and matches the submitted source]`
- **Eligibility / reuse ruling:** `[MISSING — written Local Lead ruling required; see evidence/G0-ruling-request.md]`

## Summary (150 words)

FireAtlas turns NASA MODIS and VIIRS records into a burning-activity calendar for Northern California and Punjab–Haryana. The primary unit is VIIRS-equivalent cell-days on a common 1 km grid; VIIRS 375 m detections remain inspectable. A Sensor Bridge exposes MODIS-only, VIIRS-only, shared, and gap/unknown states. Fire Radiative Power is shown separately in MW/day and never added to activity counts. Each UTC day retains rows, product versions, confidence, excluded types, hashes, and processing state. Verified exports cover 2022–2026; older rows are partial because the original request metadata are missing, including the reconstructed S-NPP 2021–2022 archive. July 2024 has one comparable year, so no unusual-activity conclusion is made. Pass and cloud opportunity remain unknown; a hotspot is not burned area, a perimeter, or proof of no fire. Dated MCD64A1 Burn Date checks are shown only as lagged, analytical context with source hashes; active-fire limits remain explicit. FireAtlas is a research and learning tool, not operational guidance. AI assisted code and text; it did not generate NASA values.

## Numbers and evidence to preserve

| Region · month | API verdict | Comparable baseline | Documented S-NPP gap | Interpretation |
|---|---|---:|---:|---|
| Northern California · July 2024 | Comparison not usable | 1 year | 6 estimated days | MODIS-based estimates on six dates; no unusual-activity conclusion |
| Punjab–Haryana · July 2024 | Comparison not usable | 1 year | 6 estimated days | MODIS-based estimates on six dates; no unusual-activity conclusion |

The two calibration artifacts use 41 complete, version-matched 2023–2026 month pairs per region: MODIS `61.03` with VIIRS S-NPP Collection 2. Nominal 95% interval coverage is 41.5% for Northern California and 39.0% for Punjab–Haryana. These intervals are under-calibrated. Older MODIS `6.03` rows are not mixed into this fit. The July 2024 verdicts and figures above were read from `calendar_v2` using the local imported database on 2026-09-29; each verdict is also visible in the app.

## Products, limitations, and AI use

- **NASA inputs:** FIRMS standard active-fire archive exports: MODIS Terra/Aqua Collection 6.1 (including `61.03` in the version-matched calibration; older `6.03` records are separately identified) and VIIRS Suomi NPP Collection 2.
- **Coverage caveat:** The six dates overlap the dated NASA S-NPP processing-gap notice. FireAtlas uses MODIS estimates for those dates; the export does not establish pass, cloud, or clear-sky coverage. Historical row-only files are not complete-month evidence.
- **Exact safety statement:** “FireAtlas is a research and learning tool. It is not an operational fire-management, evacuation, or flight-planning tool.”
- **AI use:** OpenAI Codex/ChatGPT helped draft and edit code, documentation, and interface text. AI did not create or alter NASA FIRMS detection rows, raw coordinates, or product counts. No trained AI model produces satellite values or fire forecasts. No independent scientific review is documented.
- **Sources:** [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/); [NASA Space Apps challenge](https://www.spaceappschallenge.org/2026/challenges/harmonization-of-modis-and-viirs-hot-spots/); [project data ledger](../DATA.md); [AI-use disclosure](../AI_USE.md).

## Perfected-plan evidence status

- **P0:** Common-grid bridge, UTC/type filtering, excluded-type counts, source hashes, and
  explicit evidence states are implemented for the imported paired window. Older request
  metadata are missing; the S-NPP 2021–2022 rows are present only as reconstructed partial evidence; native fire-mask coverage and independent
  review are incomplete.
- **P1:** Sensor Bridge, source-separated FRP, static evidence exports, a local share card, and
  month-specific MCD64A1 lagged corroboration are visible. Independent review, a public URL,
  outside-user check, and 90-second narrated rehearsal are still required.
- **P2:** Recent Pulse, NOAA-20, custom AOI, and multilingual labels are deferred until P0/P1
  pass. They must never alter the historical calendar.

The perfected plan supersedes the earlier planning snapshot. The current internal implementation
score is **41.6 / 100**; no claim of a higher NASA score is made from this draft.

## Submit only after

1. A written Local Lead ruling resolves whether and how this pre-existing repository may be used.
2. The public repository and demo URLs are reachable and match the reviewed files.
3. The project-page facts are copied from the current API and checked against the currently deployed version.
4. The perfected 90-second sequence shows the globe, Sensor Bridge, verdict, evidence drawer,
   method uncertainty, and share card from the same public build.
5. The independent scientific review is recorded, or the submission explicitly says it has not occurred.
