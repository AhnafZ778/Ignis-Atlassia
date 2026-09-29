# 8. Submission package

Everything here is judged directly. Draft it early (week 6 in Branch A), finalise it at the event.

### SUB-T1 — Project page (Space Apps site)

Fill every field; the local rubric gives 1 point just for a complete page. Field names below follow the 2025 project-page form — **VERIFY against the 2026 form** and adapt the mapping, not the content.

| Field | What to write (exact guidance) |
|---|---|
| Project name | `FireAtlas — one fire calendar across MODIS and VIIRS` |
| Challenge | `Harmonization of MODIS and VIIRS Hot Spots` (exact 2026 title from G0-T3) |
| High-level summary (≤ 150 words) | Problem (sensor handover, retirements) → what FireAtlas does (harmonized calendar, missing-sensor days, uncertainty, trace to pixel) → one result with your measured numbers → who it helps. Use the winning story (2.4). |
| Link to final project | Public static site URL (C12-T6) |
| Link to repository | GitHub URL (public) |
| Presentation / video | 30-second video link (SUB-T2) or 7-slide deck (SUB-T3) |
| Detailed description | Sections: What it does · How it works (method in 6 bullets) · Validation (tables from SCORECARD with run dates) · Limits · Future work (Tier 2 replay, more regions, NOAA-21) |
| Use of NASA data | Name every NASA product with version and DOI/URL: FIRMS MODIS C6.1 (MCD14ML), FIRMS VIIRS S-NPP (VNP14IMGML), NOAA-20 (VJ114IMGML), CMR granule metadata (MOD14/MYD14/VNP14IMG/VJ114IMG), MCD64A1 C6.1, NASADEM (if Tier 2), FEDS (if Tier 2). Say what each is used for. |
| Other data | NOAA HMS, LANDFIRE, HRRR, CAL FIRE incidents, building footprints — with licences. |
| Use of AI | Copy the summary of `docs/AI_USE.md`. |
| References | All citations (C2-T6 list, papers used in C7). |
| Prior work disclosure (Branch A only) | `Parts of this project (data pipeline and prototype interface) were developed between 27 Sep and 13 Nov 2026, before the hackathon, with the Local Lead's written approval on <date>. During the hackathon we built: <list with commit range>.` Use the exact ruling wording. |
| Team | Names, roles, countries; no personal contact details. |

- **Acceptance checks:** [ ] Every field filled. [ ] Every number matches SCORECARD (same run date). [ ] Links open in a private browser window.

### SUB-T2 — 30-second video (storyboard, exact timing)

Record at 1920×1080, 30 fps, screen capture of the public site. Voice-over (VO) ≤ 75 words total; burn-in captions; no music with lyrics; end card ≥ 2 s.

| Time | Screen | VO (exact draft; replace bracketed values with SCORECARD numbers) |
|---|---|---|
| 0:00–0:04 | Sensor timeline animating; Terra, Aqua, S-NPP lanes end | "NASA's fire satellites are retiring. Twenty-five years of fire records are split across sensors that see fire differently." |
| 0:04–0:11 | Heatmap for Northern California, 2003–2025, scrolling | "FireAtlas joins MODIS and VIIRS into one burning-activity calendar—in a single unit, with uncertainty." |
| 0:11–0:17 | Hover the 2024 July row; hatched outage days; tooltip | "Missing-sensor days are marked, not hidden—like the Park Fire, when Suomi NPP went dark." |
| 0:17–0:23 | Method page: held-out error table, scatter | "On years we held out, it predicts VIIRS activity within [X] percent." |
| 0:23–0:27 | Day drawer → raw NASA rows | "Every number traces back to the original NASA pixel." |
| 0:27–0:30 | End card: logo, URL, challenge name, "Data: NASA FIRMS" | (silence) |

- **Checks:** [ ] ≤ 30.0 s (check file duration with `ffprobe`). [ ] Captions readable on a phone. [ ] No synthetic data on screen. [ ] Shown to 2 people who have not seen the project; both can say what it does.

### SUB-T3 — 7 slides (if slides instead of or in addition to video)

1. **Title** — name, one-line promise, challenge name, team.
2. **Problem** — sensor timeline graphic; "A single sensor can't tell 25 years of fire history anymore."
3. **What we built** — screenshot of the heatmap with 3 callouts (harmonized unit · degraded days · trace to pixel).
4. **How it works** — 5-box flow: FIRMS archives → 1 km cell-days → availability ledger → overlap calibration → calendar + intervals.
5. **Does it work?** — held-out error table (vs no harmonization and single-ratio baselines) + burned-area correlation; one sentence of limits.
6. **Who it helps** — land manager question answered in 60 s (usability test result); second region example (crop or savanna burning).
7. **What's next + credits** — Tier 2 replay (if built: one screenshot, "beta"), NOAA-21 continuity, data credits, AI use, links/QR code.

Rules: ≥ 24 pt font, ≤ 25 words per slide except slide 5 table, every chart captioned with source.

### SUB-T4 — Live demo run sheet (for local judging, 3–5 minutes)

1. Open the public URL (not localhost) in a fresh browser profile; have the local server running as backup and a 60 s screen recording as a last resort.
2. Say the one question (2.4). Pick `Northern California` chip.
3. Point at the heatmap; hover a 2024 hatched day; open the day drawer; show raw rows.
4. Switch to `Punjab–Haryana` to show crop-burning seasons (global relevance).
5. Open Method → "Does harmonization work?"; read one number.
6. (If Tier 2 done) Open Fire replay: step two times, reveal outcome, show accuracy vs persistence.
7. Close with limits and the challenge name.

- **Checks:** [ ] Rehearsed 3 times with a timer; each run ≤ 5 min. [ ] Offline fallback tested (Wi-Fi off → local server + static site folder).

**Master prompt (submission drafting):**

```text
TASK SUB-T<n>. Read docs/winning-plan/src/08-submission-tracker-timeline.md "SUB-T<n>"
and docs/winning-plan/SCORECARD.md. Draft the text exactly to the structure given.
Take every number, date and URL from SCORECARD or the repository; if a value is missing,
write [MISSING: what] instead of guessing. No superlatives ("revolutionary",
"first-ever", "real-time") and no operational claims. Output the draft and a list of
every number used with its SCORECARD row.
```

**Submission checklist:** [ ] SUB-T1 · [ ] SUB-T2 · [ ] SUB-T3 · [ ] SUB-T4 · [ ] submitted before 15 Nov 18:00 local (6 h buffer before the 23:59 deadline) · [ ] confirmation screenshot saved

---

# 9. The live accountability tracker

`docs/winning-plan/SCORECARD.md` is the single source of truth for progress. The PDF is the plan; the SCORECARD is the state.

## 9.1 Update rules

1. After **every** task, the executor's REPORT block says which SCORECARD rows change. You (or the Auditor) apply them.
2. A task row may be set to `DONE` only with evidence (commit hash + test line + screenshot/JSON path).
3. **Category scores are never set by the executor.** They are recomputed by the Auditor (9.2) at least every 2 days and after each block of section 0.1.
4. Every change adds one line to the SCORECARD **Changelog**: `YYYY-MM-DD HH:MM · who · what changed · evidence`.
5. Numbers in "Ground truth & measured results" are replaced only by values from a command run in the same session; keep the old value in the changelog.

## 9.2 Auditor master prompt (paste into a strong LLM with repository access)

```text
You are the FireAtlas AUDITOR. You do not write features. You measure.
Inputs: the repository, docs/winning-plan/SCORECARD.md, and the scoring rules in
docs/winning-plan/src/02-gates-and-scoring.md section 2.1 (scores 0-5, weights, hard caps).

Do, in order:
1. git status; git log -5 --oneline; git log origin/main -1. Note uncommitted work.
2. uv run python -m unittest discover -s tests  -> paste the final line.
3. For each task marked DONE in SCORECARD: check that its evidence exists (file path,
   commit, test name). If any is missing, change the status to IN PROGRESS and say why.
4. Start the server; request /, /method.html, /data.html and the calendar v2 API for each
   preset region; record status codes and response times.
5. For each category C1..C12: choose the score 0-5 using the evidence table in 2.1; then
   apply every hard cap (synthetic-only <=2; not pushed <=2; no method+test <=2;
   forecast without held-out evaluation <=3; operational instruction => 0).
   Write one line of evidence per category with file:line or command output.
6. Compute points = weight x score / 5 for each category and the total. Show the arithmetic.
7. Estimate the local-rubric scores (section 2.2) with one sentence of justification each.
8. Output:
   a) the updated "Category scores" and "Local rubric" tables for SCORECARD,
   b) "Change since last audit" (per category: old -> new, reason),
   c) "Top 3 blockers" and "Next 3 tasks" (task IDs from the plan),
   d) a changelog line.
Rules: never raise a score without new evidence; when unsure, choose the lower score;
never invent measurements.
```

## 9.3 Daily improvement report (what you ask for each day)

Prompt: `Using the Auditor results and SCORECARD, write today's improvement report: score now vs yesterday vs target (both systems), tasks finished today with evidence, tasks slipped and why, risk level for the deadline (green/amber/red with reason), and tomorrow's 3 tasks.`

Risk level rule: **red** if the Tier 1 freeze date will be missed at the current pace (remaining Tier 1 tasks ÷ tasks done per day > days until freeze); **amber** if within 2 days of that; otherwise **green**.

---

# 10. Timelines

## 10.1 Branch A — reuse allowed (29 Sep → 15 Nov 2026)

| Week | Dates | Work (task IDs) | Exit check |
|---|---|---|---|
| 1 | 29 Sep – 4 Oct | G0-T1 email; Gate 1 (C12-T1…T3); cleanup R1–R17 | Repo public, CI green, cleanup checklist done |
| 2 | 5 – 11 Oct | C2-T1 regions + downloads (start downloads day 1; they are slow); C2-T2 aggregates; C2-T3 availability ledger | Aggregates for norcal + 1 other region |
| 3 | 12 – 18 Oct | C2-T4 filters/versions; C2-T5 calibration + LOYO; C2-T6 docs; C1-T1 API v2 | Calibration JSON for all regions; API contract tests |
| 4 | 19 – 25 Oct | C1-T2…T5 (heatmap, climatology, seasons, area picker); C10-T1, C10-T2 | Heatmap screenshot; Gate 0 answer (default Branch B if none by 25 Oct) |
| 5 | 26 Oct – 1 Nov | **28 Oct: G0-T3** (re-plan if needed); C1-T6…T8; C10-T3…T7; C11-T1…T4 | Method page shows validation |
| 6 | 2 – 8 Nov | C11-T5…T8 (tour, states, reliability, usability test); C12-T4…T8; C8-T1, C9-T1, C5-T1; submission drafts | **Tier 1 freeze 8 Nov**; Auditor run; target ≥ 50/100 |
| 7 | 9 – 13 Nov | If Tier 1 all DONE: S-T0, C3-T1…T3, C7-T1…T3, C4-T1…T3 (core replay). Otherwise: Tier 1 fixes only. Record video draft; rehearse | Replay beta or DROPPED; video draft ≤ 30 s |
| Event | 14 – 15 Nov | Final data refresh check; C4-T4, C6 if time; SUB-T1…T4; C12-T9 tag | Submitted by 15 Nov 18:00 local |

## 10.2 Branch B — rebuild at the event (36 working hours, Tier 1 only)

Before 14 Nov you may prepare **only** non-code material (if the ruling allows): this plan, data-source lists, and download instructions. Confirm whether pre-downloading public datasets is allowed; if not, start downloads at hour 0.

| Hours | Work |
|---|---|
| 0–2 | New repo, licence, README skeleton, CI; start FIRMS archive downloads for 2 regions (norcal + one contrasting region) |
| 2–8 | Ingest + 1 km cell-day aggregates (C2-T2 simplified: vegetation filter, all confidences); availability ledger from CMR for the 2 regions (C2-T3) |
| 8–14 | Calibration r(m) + LOYO vs no-harmonization baseline (C2-T5); method doc |
| 14–22 | Calendar API + heatmap + climatology badges + day drawer with raw rows (C1-T1…T3, T6) |
| 22–26 | Method page with sensor timeline, validation table, limits (C11-T3, T4 parts; C10-T1) |
| 26–29 | Static site deploy (C12-T6), safety wording (C8-T1), sources + AI use (C12-T7) |
| 29–33 | Usability test with 3 people at the venue; fix top problem; video + slides |
| 33–35 | Project page (SUB-T1), rehearsal |
| 35–36 | Submit; buffer |

Take regular breaks and sleep at least one block; tired teams make validity mistakes that judges notice.
