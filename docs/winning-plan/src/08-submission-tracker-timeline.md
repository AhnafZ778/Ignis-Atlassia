# 8. Submission

## SUB-T1 — Project page

Fill the Space Apps project page with: the challenge name, the public URL, the public repo, a
150-word summary that states the verdict and comparable-year count for both regions using
numbers copied from the method page, the NASA products and versions, the common-grid unit,
the separate FRP context, the limits sentence, and AI use from `docs/AI_USE.md`. If a number
is not in `SCORECARD.md` or the current API, write `[MISSING]` rather than guessing. If MCD64A1
is not present, say `ACTIVE FIRE ONLY` rather than implying corroboration.

## SUB-T2 — 30-second video

| Seconds | On screen | Words |
|---|---|---|
| 0–4 | The globe | "MODIS and VIIRS both detect fires, but their counts are not the same record." |
| 4–12 | Northern California heatmap and the verdict sentence | Read the sentence exactly as the page shows it. |
| 12–18 | A hatched July 2024 day and its NASA rows | "Days a satellite was missing stay marked." |
| 18–24 | Punjab–Haryana · October 2024 | "Local planners can inspect detections during the official harvest-monitoring window; one comparable year is not enough for a trend claim, and hotspots do not identify cause." |
| 24–30 | Method-page error line, then the URL | "On years we held out, the error is {the figure on the page}." |

The perfected plan also requires a separate 90-second narrated rehearsal:

| Seconds | On screen | Narration |
|---|---|---|
| 0–5 | Existing globe | “The record changes when the sensor changes.” |
| 5–15 | Sensor Bridge | “Raw MODIS and VIIRS pixels are different units; the calendar uses a common 1 km grid.” |
| 15–35 | Northern California calendar | Read the live verdict and one state badge exactly as shown. |
| 35–50 | Evidence drawer | Show source values, native scale, FRP per source, notice, version, and hash. |
| 50–65 | Punjab–Haryana calendar | Explain the official context and that hotspots do not establish cause. |
| 65–80 | Method page | Show held-out errors, baseline comparison, and interval coverage. |
| 80–90 | Share card | Show the selected value, state, sources, limits, and share URL. |

The 90-second sequence is a target until it is captured from the current build and checked on the
public URL. The local silent 30-second cut is evidence of the earlier path only; do not describe
it as proof that the perfected sequence has been rehearsed.

## SUB-T4 — Demo

Open the public URL. Show the globe for five seconds. Switch to Northern California, read the verdict, open one hatched day. Switch to Punjab–Haryana and read that verdict. Open the method page and read one error number. Stop. Do not open a spread model, a wind map, or a chat box.

# 9. How to confirm the score

After SUB-T4 and the perfected 90-second sequence have been rehearsed on the public URL, update
the SCORECARD only if every P0/P1 check in sections 4–6 is ticked. The old 44.8 and 93 figures
are withdrawn; calculate any new value from the evidence actually available. If a gate is open,
leave that category at its current score. Do not average, round up, or copy a planning target.

**Auditor prompt:**

```text
Open `docs/winning-plan/SCORECARD.md` and section 2 of
`docs/winning-plan/src/02-gates-and-scoring.md`. For each perfected gate, pass the
check only if the evidence column cites a command output, a file, or a public
URL you opened. Keep the current score while a gate is open; calculate a new
score only after all required P0/P1 evidence is present and the auditor records
the arithmetic. Do not raise a score for work outside sections 4–8 or for an
unbundled MCD64A1 claim.
```
