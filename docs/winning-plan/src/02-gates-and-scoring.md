# 1. Gate 0 — Eligibility (human step, before the event)

The Space Apps FAQ says teams may not begin working on the challenges before the hackathon (14–15 Nov 2026). This repo started on 27 Sep 2026. Ask the Local Lead, in writing, whether this code may be reused and whether that reuse must be disclosed. Save the reply, with email addresses removed, in `docs/winning-plan/evidence/G0-ruling.txt`. If reuse is not allowed, do not submit this repository. The scores below apply only to an eligible submission.

On 28 Oct 2026, copy the official challenge statement into `docs/winning-plan/evidence/challenge-statement-2026.md`. If it adds a requirement this plan does not cover, stop and tell the owner. Do not invent extra features to cover it.

# 2. The scores these tasks earn

The supplied `FireAtlas_Updated_Perfected_Winning_Plan.pdf` is now authoritative. Its NASA
judging alignment is Impact, Creativity, Validity, Relevance, and Presentation. The weighted
100-point table below remains an internal engineering tracker, not a NASA judge score. The
earlier plan's claim numbers are retained only as a historical arithmetic record and are
explicitly withdrawn until the perfected P0/P1 gates pass.

`points = weight × score ÷ 5`. A category stays at the "Now" score until its check passes. Do
not raise a category because a diagram or a plan exists. The old targets of 54.2, 88.0, 93,
and ≈106 are withdrawn.

## 2.1 Implementation score — current **41.6 / 100** · no perfected-plan claim yet

| # | Category | Wt | Now | Earlier claim (withdrawn) | Points | Perfected-plan evidence gate |
|---|---|---:|---:|---:|---:|---|
| C1 | Calendar | 12 | 4 | 4 | 9.6 | P0 archive completeness plus visible verdict, critical dates, heatmap state patterns, Sensor Bridge, and evidence drawer; older row-only history stays partial |
| C2 | Harmonized NASA data | 12 | 4 | 4 | 9.6 | P0 common 1 km aggregation, within-sensor/day deduplication, raw 375 m detail, FRP separation, source hashes, and reproducible state classification |
| C3 | Terrain, fuels, weather | 8 | 1 | 1 | 1.6 | No work. Do not raise |
| C4 | Sector ranking | 14 | 0 | 0 | 0 | No work |
| C5 | Aerial framing | 7 | 1 | 1 | 1.4 | No work |
| C6 | Aerial observations | 8 | 0 | 0 | 0 | No work |
| C7 | Spread scenarios | 10 | 1 | 1 | 2.0 | No work |
| C8 | Safety wording | 7 | 3 | 3 | 4.2 | The limits sentence in section 6 is on the home page and the method page |
| C9 | Season verdict for a manager | 6 | 3 | 3 | 3.6 | Live verdict matches the API, appears first in the calendar panel, and official sources are directly beneath it; no unsupported unusual-fire claim |
| C10 | Held-out test | 8 | 3 | 4 | 4.8 | Held-out comparison includes common-grid, ratio/no-correction baselines, interval coverage, and the 2012 step only when complete request metadata exist |
| C11 | Interface | 4 | 3 | 4 | 2.4 | Globe and controls remain unchanged; public URL opens the calendar and preserves See → Compare → Verify → Share |
| C12 | Repo and demo access | 4 | 3 | 4 | 2.4 | Local static bundle plus evidence card, source ledger, hash-bound exports, and public no-credential demo |
| | **Total** | 100 | **41.6** | **44.8 (withdrawn)** | **41.6** | Current: 9.6+9.6+1.6+0+1.4+0+2.0+4.2+3.6+4.8+2.4+2.4 = 41.6. No perfected-plan claim is set. |

C1 and C2 remain at 4. Dated MCD64A1 corroboration is now hash-bound, but archive completeness, native-mask independent review, and outside-user checks remain open. A UI card cannot substitute for those gates.

### Perfected-plan gates (status at 30 September 2026)

| Gate | Required evidence | Current status |
|---|---|---|
| P0 archive and provenance | Complete requested windows, metadata, hashes, UTC/type rules, and no fabricated rows | **OPEN** — 26 older exports are reconstructed row-only inputs; the S-NPP 2021–2022 rows are present, but their original request metadata and complete-window evidence are absent |
| P0 common-grid reproducibility | VIIRS 375 m aggregated to the common 1 km grid, native detail retained, deduplicated daily totals reproduced independently | **PARTIAL** — imported FIRMS centroid transform is documented; native mask resampling and independent review are absent |
| P1 Sensor Bridge and FRP | MODIS-only / VIIRS-only / both / gap states plus source-separated FRP MW/day | **LOCAL UI PRESENT** — counts are tied to imported exports; complete historical coverage is not established |
| P1 independent corroboration | MCD64A1 Collection 6.1 or separately documented official context, with dates and limits | **PARTIAL** — dated MCD64A1 Burn Date + QA rasters are hash-bound in `fireatlas/samples/mcd64_corroboration.json`; independent review is pending |
| P1 share card | Value, state, versions, hashes, limitations, and public URL all reproduce the selected result | **LOCAL ONLY** — public host not verified |
| P1 usability and deployment | Outside-user check, public no-credential URL, globe and mobile rehearsal | **OPEN** |
| P2 rapid mode | Separate Recent Pulse data mode, calibration, and limits | **DEFERRED** |

## 2.2 Local rubric — current **≈70 / 118** · earlier **93 / 118 withdrawn**

| Criterion | Max | Now | Earlier claim (withdrawn) | Perfected-plan evidence gate |
|---|---:|---:|---:|---|
| Impact | 20 | 15 | 15 | The video shows the same one-year-limited verdict in a California fire-season case and Punjab–Haryana's official [2024 paddy-harvest monitoring window](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2060764&lang=2&reg=48), names local planners, and states hotspots do not establish crop-burning cause |
| Creativity | 20 | 11 | 14 | Visible common-grid Sensor Bridge, mismatch categories, uncertainty hatching, and retained 375 m detail |
| Validity | 20 | 11 | 16 | Held-out error, baseline comparison, interval coverage, archive hashes, and MCD64A1 context or explicit active-fire-only state |
| Relevance | 20 | 11 | 18 | The calendar is the feature the challenge names. Training lab, synthetic demo, and EONET are not on the judged path |
| Presentation | 20 | 12 | 16 | Globe remains, public link works, and both 30-second and 90-second evidence paths are rehearsed |
| Teamwork | 5 | 2 | 2 | This plan adds no teamwork tasks, so this box stays 2 |
| User experience | 5 | 3 | 4 | Pick an area, read the sentence, open one hatched day, inspect the bridge, and share the evidence card; outside-user check required for 4 |
| NASA data usage | 5 | 4 | 5 | Sources page lists MODIS C6.1, VIIRS S-NPP, FIRMS acknowledgement, and any MCD64A1 input with version, retrieval, and hash |
| Category named | 1 | 1 | 1 | Challenge name is on the home page |
| Repository access | 1 | 0 | 1 | Public repo matches the running site |
| Project page | 1 | 0 | 1 | Space Apps project page submitted |
| **Total** | **118** | **≈70** | **93 (withdrawn)** | Current: 15+11+11+11+12+2+3+4+1+0+0 = **70**; no perfected-plan claim is set |

A judge can still score a box lower if the sentence is buried or the demo fails. The earlier
93-point row is a withdrawn planning ceiling, not a prediction. Re-score only after the perfected
gates are independently evidenced.
