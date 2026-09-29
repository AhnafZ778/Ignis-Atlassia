# FireAtlas — Winning Plan and Accountability Tracker

**Challenge:** NASA Space Apps 2026 · *Harmonization of MODIS and VIIRS Hot Spots*
**Document version:** 1.0 · 29 September 2026 · Baseline audit score **31.8 / 100** (implementation) · **≈65 / 118** (local-event rubric estimate)
**Companion files (same folder):** `SCORECARD.md` (the live tracker an LLM updates) · `src/*.md` (this document's source) · `scripts/build_winning_plan.py` (rebuilds this PDF)

---

## 0. How to use this document

This document is written for two readers:

1. **You (the team lead).** Read sections 0–4 once. Then use `SCORECARD.md` every day.
2. **An executor LLM** (any coding model). Give it the **Executor System Prompt** in section 0.3, then one **Task Master Prompt** at a time from sections 4–8. Never give it the whole plan at once and say "do everything".

### 0.1 The order of work (never skip a gate)

| Order | Block | Section | Why it comes here |
|---|---|---|---|
| 1 | **Gate 0 — eligibility and timeline** | 1 | Space Apps rules may forbid work started before 14 Nov 2026. Nothing else matters if the project is ineligible. |
| 2 | **Gate 1 — repository integrity** | 5 (C12-T1…T3) | The best work is uncommitted. A judge who clones today sees an older product. |
| 3 | **Cleanup — remove what hurts** | 3 (target shape) and 4 (R1–R17) | Off-topic features lower Relevance and Validity scores. |
| 4 | **Challenge core (Tier 1)** | 6 (C2, C1, C10) | The judged challenge is harmonization + calendar. This is 70–80 % of the win. |
| 5 | **Interface, packaging and safety wording** | 6 (C11, C12-T4…T9, C5/C8/C9 Tier 1) | Judges see a 30-second video or 7 slides and a public link. |
| 6 | **FireAtlas Scout replay (Tier 2)** | 7 (C3, C4, C6, C7 and Tier 2 of C5, C8, C9, C10) | Only after Tier 1 acceptance tests pass. Clearly labelled extension. |
| 7 | **Submission package** | 8 | Project page, video, slides, citations, AI disclosure, licence. |
| 8 | **Tracking and re-scoring** | 9 (tracker, Auditor prompt) and 10 (timelines) | Keeps every claim tied to evidence. |

### 0.2 Status words (use exactly these words in `SCORECARD.md`)

- `NOT STARTED` · `IN PROGRESS` · `BLOCKED (reason)` · `DONE (evidence: …)` · `DROPPED (reason)`

A task is `DONE` only when **every** acceptance check in its checklist passes **and** the evidence (command output, test name, screenshot path, commit hash) is written next to it.

### 0.3 Executor System Prompt (paste this first into any coding LLM)

```text
You are the executor for the FireAtlas repository (NASA Space Apps 2026, challenge
"Harmonization of MODIS and VIIRS Hot Spots"). Repository root: the folder that contains
pyproject.toml and the fireatlas/ package. Python 3.10+, dependency manager: uv.
Run tests with: uv run python -m unittest discover -s tests

NON-NEGOTIABLE RULES
1. Never invent data, numbers, dates, URLs, API fields, dataset versions or results.
   If a value is not in a file you read or a command you ran, write "UNKNOWN" and stop to ask.
2. Before editing a file, read it. Quote the exact lines you will change (path:line).
3. Do only the task you were given. Do not refactor unrelated code. Do not rename public
   API fields unless the task says so.
4. Every new behaviour needs a unit test in tests/. Run the full test suite before you say
   you are done. Paste the final "Ran N tests ... OK" line.
5. Never mix synthetic and authentic data. Synthetic outputs must carry demo=true / a
   "SYNTHETIC" label. Authentic outputs must carry source IDs and file hashes.
6. Never state that the app predicts, validates, authorizes, dispatches, or guarantees
   anything unless a test and a validation file prove it. Hotspots are not perimeters,
   burned area, or proof of no fire.
7. Never produce flight routes, waypoints, drone altitudes, ignition lines, evacuation
   zones or "safe" areas. Link to official sources instead.
8. Never commit secrets (FIRMS MAP_KEY, Earthdata tokens). Keys stay in environment
   variables or ~/.config/fireatlas/.
9. If a step says "VERIFY", you must confirm it by running a command or reading the
   official page. If you cannot, mark the task BLOCKED and explain what is missing.
10. When finished, output a REPORT block exactly in this format:
    TASK: <id>
    STATUS: DONE | BLOCKED (reason)
    FILES CHANGED: <path list>
    TESTS: <command> -> <result line>
    EVIDENCE: <screenshots / JSON outputs / commit hash>
    SCORECARD UPDATE: <which rows in docs/winning-plan/SCORECARD.md to change and to what>
    RISKS / FOLLOW-UPS: <bullets>
```

### 0.4 How each task in this plan is written

Every task has the same parts. If a part is missing, treat the task as not ready.

- **ID** (for example `C2-T3`) — used in `SCORECARD.md` and commit messages (`C2-T3: add sensor availability ledger`).
- **Goal** — one sentence.
- **Files** — exact paths to create or edit.
- **Steps** — numbered, in order.
- **Acceptance checks** — the checklist that defines DONE.
- **Master prompt** — paste-ready text for the executor LLM.

### 0.5 Ground-truth facts (the executor must not contradict these)

These were measured during the 29 September 2026 audit. If code changes them, the SCORECARD must record the new value and the command that produced it.

| Fact | Value | How it was measured |
|---|---|---|
| Authentic FIRMS standard rows in bundle | 30,823 (MODIS_SP 8,151; VIIRS_SNPP_SP 22,672) | `archive.import_bundle` into an empty database |
| Bundle area and years | bbox `-122.2, 38.8, -120.0, 41.0`; July 2022 – June 2026 (84 complete months to Dec 2025) | `fireatlas/archive.py:26-28` |
| MODIS product versions | `6.03` (Jul–Dec 2022), `61.03` (2023+) | SQL on `observations.product_version` |
| FIRMS `type` values in bundle | 0: 30,620 · 2: 164 · 3: 39 (all currently counted) | SQL on `raw_json` |
| Park Fire case, 25 Jul 2024 | MODIS 603 pixels → 415 cells; VIIRS 0 rows (S-NPP outage 24–28 Jul) | `/api/harmonization` |
| July 2025 enclosing box | 474 cell-days vs median 152 (2022–2024), mixed MODIS versions | `/api/calendar` |
| CAL FIRE association | 25 eligible incidents: 7 nearby detection, 18 miss | `/api/validity` |
| Native mask processing (Grove 2025) | VIIRS 3/3 processed; MODIS 0/17 (16 fail "found 0 Latitude layer", 1 missing file) | `python3 -m fireatlas.masks --case grove-2025 --store /tmp/...` |
| Test suite | 81 tests pass | `uv run python -m unittest discover -s tests` |
| Committed state | Authentic pipeline (`archive.py`, `validity.py`, `harmonization.py`, `masks.py`, method page, NASA sample ZIP) is **uncommitted**; local branch 2 commits ahead of `origin/main` | `git status`, `git show HEAD:fireatlas/web.py` |
| Scout features | Terrain analysis, fuels, weather, spread, sector ranking, aerial ingest, assimilation: **absent** | grep over `fireatlas/` |
| Official dates | Challenge statements 28 Oct 2026; hackathon 14–15 Nov 2026; submission closes 15 Nov 23:59 local | Space Apps FAQ |
| Sensor continuity | S-NPP delivery ends 1 Nov 2026; Aqua MODIS science collection ends ~Aug 2026; Terra ~Jan 2027 | NASA/NOAA notices, LAADS transition PDF |
