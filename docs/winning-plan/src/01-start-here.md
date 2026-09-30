# FireAtlas — Perfected Winning Plan and Accountability Tracker

**Challenge:** NASA Space Apps 2026 · Harmonization of MODIS and VIIRS Hot Spots
**Document version:** Perfected plan alignment · 30 September 2026
**Authoritative delta:** `docs/winning-plan/src/00-perfect-plan-authority.md`

The supplied `FireAtlas_Updated_Perfected_Winning_Plan.pdf` supersedes the earlier plan's
claim ceiling. The current weighted implementation score is **41.6 / 100**. The earlier
**44.8 / 100** implementation claim and **93 / 118** local-rubric claim are withdrawn until
the perfected-plan P0/P1 gates, eligibility ruling, and public demo are actually evidenced.
Do not claim 54, 88, 93, 106, or 20/20 from documentation alone.

---

## The goal

Upgrade the existing website. Keep the 3D globe and every control it has: drag to rotate, pause, zoom, reset, Satellite signals, Wildfires, the details dialog, the detections-by-day chart, and the terrain Earth link. If any of those are missing, put them back. Do not replace the globe with a diagram.

Under the globe, add the result the challenge asks for. For Northern California and for Punjab–Haryana, the calendar shows one comparable record from the years below, whether the selected season is unusual, the critical dates, and which days Suomi NPP was missing.

The perfected scientific unit is **VIIRS-equivalent active-fire cell-days on a common 1 km
grid**. Native VIIRS 375 m pixels remain a detail channel. Raw FRP is shown separately in
MW/day. The Sensor Bridge must make MODIS-only, VIIRS-only, both, and gap/unknown states
visible without adding the two sensors into one count. These are evidence states, not a claim
that the sensors have equal detection probability.

**Data targets and current local archive status** (do not invent rows or mark reconstructed periods complete):

| Area | Box (west, south, east, north) | MODIS Collection 6.1 target start | Suomi NPP 375 m target start |
|---|---|---|---|
| Northern California | −122.2, 38.8, −120.0, 41.0 | 2010-07-01 | 2012-07-01 |
| Punjab–Haryana | 73.8, 29.5, 77.6, 32.6 | 2010-07-01 | 2012-07-01 |

Local status (2026-09-30): 34 sidecar-backed standard archive exports are imported. Eight newer exports retain request metadata and monthly completeness from July 2022 through June 2026 (48 MODIS and 47 S-NPP months per region; S-NPP May 2026 is unknown). Twenty-six reconstructed exports add authentic detection rows as early as July 2006 MODIS, and request 814833 adds S-NPP rows through July 2022, but their original request metadata were not supplied; they are labeled `reconstructed-rows-only`, displayed as partial detections, and never used to infer zero activity. The reconstructed MODIS inventory now includes the nominal 2019→2020 and 2021→2022 windows; the S-NPP July 2021→July 2022 window is present only as row-level evidence. The Sensor Bridge now exposes source-specific counts, `excluded_type_counts`, `evidence_state`, `coverage_state`, bridge status, and source-separated FRP for the imported paired window. It is therefore not a continuous verified historical baseline.

Download page: https://firms.modaps.eosdis.nasa.gov/download/ · CSV · standard archive, not near-real-time. Split by year if the form requires it. No more data are necessary for the current detection-calendar demo; exact request metadata and missing archive windows are needed before the longer series can be called complete.

## What "done" must look like

A judge opens the public link and, without help, sees:

1. The globe, working.
2. Two area choices: Northern California and Punjab–Haryana.
3. This sentence, filled only from the API: `{Area}, {Month Year}: {percentile}th percentile of {n} comparable years. {k} days are estimates because Suomi NPP was missing.` If fewer than 10 years are comparable, the sentence is: `{Area}, {Month Year}: comparison not usable. Only {n} comparable years.` It must not say "unusual".
4. The season start, peak, and end for that year.
5. A hatched day that opens the original NASA rows.
6. A method page with the held-out error of the harmonization, compared with "no harmonization" and with one single ratio.

That screen is what earns the scores in section 2. A finished code task that is not visible there does not raise the score.

## 0. How to use this document

Implement the required tasks in P0/P1 order, one at a time. P2 and the operational ideas in
section 7 remain deferred. The full change table and score discipline are in
`src/00-perfect-plan-authority.md`.

| Order | Task | Where |
|---|---|---|
| 1 | G0-T1, the human asks the Local Lead before relying on this repo at the event | Section 1 |
| 2 | C2-T1, C2-T2, C2-T3, C2-T5, C2-T6, plus common-grid/FRP/state evidence | Section 4 |
| 3 | C1-T1, C1-T2, C1-T3, C1-T4, C1-T6 | Section 5 |
| 4 | C10-T1, C10-T2 | Section 5 |
| 5 | C11-T1, keep the globe and put the calendar under it | Section 5 |
| 6 | C8-T1, C12-T4, C12-T5, C12-T6, C12-T7 | Section 6 |
| 7 | P1 share card, SUB-T1, SUB-T2 (30 s), SUB-T4, and the 90 s rehearsal | Section 8 |

### Executor system prompt

```text
You are the executor for the FireAtlas repository (NASA Space Apps 2026).
Python 3.10+. Tests: uv run python -m unittest discover -s tests

RULES
1. Implement only the task id you were given. The required ids are listed in
   docs/winning-plan/src/01-start-here.md and the perfected-plan authority file. Do not build
   the replay, spread model, sector ranking, drones, wind display, chat box, extra regions,
   Recent Pulse, or new globe until P0/P1 pass.
2. Never remove or hide the home-page 3D globe or these controls: rotate, pause,
   zoom in, zoom out, reset, Satellite signals, Wildfires, details dialog,
   detections-by-day chart, terrain Earth link. Restore any that are missing.
3. Never invent data, dates, URLs, or results. If a download is not on disk, stop
   and mark the task BLOCKED.
4. Read a file before editing it. Do not refactor unrelated code.
5. Add a unit test for the new behaviour. Run the full suite. Paste the final
   "Ran N tests ... OK" line.
6. Hotspots are not burned area, fire perimeters, or proof of no fire. FRP is source context,
   not burned area or severity. Do not say the app predicts, dispatches, or recommends a response.
7. Never commit FIRMS keys or Earthdata tokens.
8. End with:
   TASK: <id>
   STATUS: DONE | BLOCKED (reason)
   FILES CHANGED: <paths>
   TESTS: <command> -> <result line>
   EVIDENCE: <command output or screenshot path>
   SCORECARD UPDATE: <rows>
```
