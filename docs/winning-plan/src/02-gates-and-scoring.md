# 1. Gate 0 — Eligibility and timeline (do this before any code)

**Problem.** The official Space Apps FAQ says: *"Teams are not allowed to begin working on the challenges prior to the hackathon."* At submission, teams confirm *"all of your work is original."* This repository's first commit is 27 Sep 2026; the hackathon is 14–15 Nov 2026.

### G0-T1 — Get a written ruling

- **Goal:** know, in writing, whether existing code may be reused.
- **Steps:**
  1. Find your Local Event page on spaceappschallenge.org and the Local Lead's contact.
  2. Send the message produced by the prompt below. Also post the question in the official Space Apps help channel if your event uses one.
  3. Save the reply as `docs/winning-plan/evidence/G0-ruling.txt` (do not commit personal emails; redact addresses).
- **Acceptance checks:**
  - [ ] A written reply exists and is saved.
  - [ ] `SCORECARD.md` → "Gate 0" row set to `Branch A (reuse allowed)` or `Branch B (rebuild at event)`.

**Master prompt (for any LLM, to draft the message):**

```text
Draft a short, polite email (under 180 words) to my NASA Space Apps 2026 Local Lead.
Facts: our team explored NASA FIRMS MODIS/VIIRS data and built a prototype web app in
late September 2026, before the challenge statements (28 Oct) and the hackathon
(14-15 Nov). The FAQ says teams may not begin working on challenges before the hackathon.
Ask: (1) May we reuse this prior code, data-processing scripts, or only ideas/notes?
(2) If reuse is allowed, must we disclose it on the project page, and how?
(3) If not allowed, may we keep the public datasets we downloaded?
Do not claim anything else about the project. Neutral tone. No marketing language.
```

### G0-T2 — Choose the branch

| Ruling | Branch | What it means for this plan |
|---|---|---|
| Reuse allowed (with disclosure) | **Branch A** | Execute sections 3–8 on this repository. Disclose prior work on the project page (section 8). |
| Reuse not allowed | **Branch B** | Freeze this repository as a private research notebook. Until 14 Nov, only write **design notes, data-download lists and this plan** (ideas are not code). At the event, create a new repository and rebuild Tier 1 from sections 6–7 using the master prompts. Budget: 36 working hours for Tier 1 only; skip Tier 2. |
| No answer by 25 Oct | Branch B by default | Safer option. |

### G0-T3 — Re-read the official statement on 28 Oct

- [ ] Copy the official challenge statement text into `docs/winning-plan/evidence/challenge-statement-2026.md` (with URL and retrieval date).
- [ ] For each requirement sentence, add a row to `SCORECARD.md → Requirement trace` with the feature that satisfies it.
- [ ] If the statement adds or removes a requirement (for example "global AOI", "fire weather", "download"), update section 6 tasks before continuing.

---

# 2. The two scoring systems

You are graded twice: by the **audit implementation score** (my 100-point system, which measures what actually works) and by **Space Apps judges**. Track both in `SCORECARD.md`.

## 2.1 Audit implementation score (100 points)

Score each category 0–5, then `points = weight × score ÷ 5`.

| Score | Meaning | Evidence required before you may claim it |
|---|---|---|
| 0 | No artifact | — |
| 1 | Idea or documentation only | A document describing it |
| 2 | Mockup, hardcoded output, isolated experiment | Screenshot or script |
| 3 | Functional component; integration, authentic data or verification missing | Working code + unit tests |
| 4 | End-to-end on real historical data with reproducible checks | Authentic-data run + reproducible command + tests + screenshot |
| 5 | Plus independent validation, clear limits, reliable demo | Validation report file with metrics vs a baseline + public demo link + limits text |

**Hard caps (the auditor LLM must apply these):**

- Any category using only synthetic data: **max 2**.
- Any category whose code is not committed and pushed: **max 2**.
- Any model/ranking without a stated method and a test: **max 2**.
- Any forecast without evaluation against held-out observations: **max 3**.
- Any output that could be read as an operational instruction (flight path, ignition line, evacuation zone): **category = 0** until removed.

| # | Category | Wt | Now | Target (Tier 1 only) | Target (Tier 1 + 2) |
|---|---|---:|---:|---:|---:|
| C1 | Challenge fit and working calendar | 12 | 3 | 5 | 5 |
| C2 | Authentic NASA data, provenance, harmonization | 12 | 3 | 5 | 5 |
| C3 | Terrain, fuels, vegetation, dated weather | 8 | 1 | 2 | 4 |
| C4 | Explainable ranking of observation sectors | 14 | 0 | 0 | 4 |
| C5 | UAS feasibility framing and airspace/command boundaries | 7 | 1 | 2 | 4 |
| C6 | Dated aerial-observation analysis and state update | 8 | 0 | 0 | 4 |
| C7 | Spread scenarios, uncertainty, input freshness | 10 | 1 | 1 | 4 |
| C8 | Containment boundaries and operational safety | 7 | 2 | 3 | 4 |
| C9 | Responder workflow, resident info, official-alert separation | 6 | 2 | 3 | 4 |
| C10 | Validation, replay, leakage control, baselines | 8 | 2 | 4 | 5 |
| C11 | Interface clarity and judge-demo reliability | 4 | 3 | 5 | 5 |
| C12 | Build, docs, data access, reproducibility | 4 | 2 | 5 | 5 |
| | **Total points** | 100 | **31.8** | **54.2** | **88.0** |

Arithmetic. Tier 1 only: 12 + 12 + 3.2 + 0 + 2.8 + 0 + 2.0 + 4.2 + 3.6 + 6.4 + 4 + 4 = **54.2**. Tier 1 + 2: 12 + 12 + 6.4 + 11.2 + 5.6 + 6.4 + 8.0 + 5.6 + 4.8 + 8.0 + 4 + 4 = **88.0**.

**Important:** the audit score weights FireAtlas Scout heavily (C3–C9 = 60 points), but Space Apps judges weight **challenge relevance**. A Tier-1-only project scoring 54/100 here can still win the challenge; a project with half-built Scout features and a weak calendar cannot. Never trade Tier 1 quality for Tier 2 breadth.

## 2.2 Space Apps judging (what actually wins)

**Official criteria (2025 wording; 2026 guide due 13 Nov):** Impact, Creativity, Validity, Relevance, Presentation, each scored 1–5 by local judges. **Global awards** are chosen later by NASA subject-matter experts (Best Use of Science, Best Use of Data, Best Use of Technology, Galactic Impact, Best Mission Concept, Most Inspirational, Best Use of Storytelling, Global Connection, Art & Technology, Local Impact).

**Local-event rubric supplied by the team (screenshots in the repo root, source unverified — confirm with your Local Lead):**

| # | Criterion | Points | What it measures | Estimate now | Target |
|---|---|---:|---|---:|---:|
| 1 | Impact | 1–20 | Scale/significance of problem, reach | 10 | 17 |
| 2 | Creativity | 1–20 | Originality of idea and execution | 11 | 16 |
| 3 | Validity | 1–20 | Scientific soundness, feasibility, usability | 11 | 18 |
| 4 | Relevance | 1–20 | Alignment to challenge; NASA data at the core | 11 | 19 |
| 5 | Presentation | 1–20 | Clarity, structure, storytelling, reach | 12 | 18 |
| 6 | Teamwork | 1–5 | Evidence of collaboration | 2 | 5 |
| 7 | User experience | 1–5 | 5 = anyone can use it | 3 | 5 |
| 8 | NASA data usage | 1–5 | NASA open data + other sources clearly shown | 4 | 5 |
| 9 | Challenge category identified | 0/1 | 2026 category named | 1 | 1 |
| 10 | Repository access | 0/1 | Public working link | 0 | 1 |
| 11 | Project page complete | 0/1 | NASA project page submitted | 0 | 1 |
| — | Women participation bonus | +5 % | Team composition | — | — |
| | **Total** | **118** | | **≈65** | **≈106** |

## 2.3 What past winners had in common (use as a checklist)

Sources: Space Apps awards pages 2019–2025, NASA winner announcements, winning teams' repositories.

- [ ] **Named NASA data at the centre** (for example FIRMS MCD14ML / VNP14IMGML, not "satellite data").
- [ ] **A working public demo link** plus a public repository (c.a.w.s.t.o.n. 2019, Team I.O. GROW 2024).
- [ ] **One clearly defined user and one plain question** the tool answers (farmers, fire authorities, event planners).
- [ ] **Evidence of validity:** statistical test, expert interview or real user test (Starflock 2022 used 20 million FIREX-AQ rows and a statistical finding; GROW 2024 tested with a fire-affected farm owner).
- [ ] **Explanatory visuals** instead of raw maps.
- [ ] **Honest limits** (c.a.w.s.t.o.n. labelled their mockups as mockups).
- [ ] **Competitor awareness:** another 2026 team (IGNIS) already published a 26-year, 9-region harmonized calendar using an overlap-ratio method. FireAtlas must beat it on **validity** (sensor-availability accounting, held-out validation, uncertainty, evidence tracing) and **presentation**, not just match it.

## 2.4 The winning story (memorize this; every screen must support it)

> **"MODIS is ending and Suomi NPP stopped delivering on 1 November 2026. Twenty-five years of NASA fire records are split across sensors that see fire differently. FireAtlas harmonizes MODIS and VIIRS into one burning-activity calendar for any study area, shows which days a sensor was missing, puts every number next to its uncertainty, and lets anyone trace a result back to the original NASA pixel."**

**Primary user:** a land manager or fire-season planner comparing this season to the historical record.
**Secondary users:** researchers and educators (method + evidence); responders (historical review brief, Tier 2 replay).
**The one question:** *"Is this period unusual for this place, and can I trust the comparison across sensors?"*

## 2.5 Things to highlight in every demo, slide and page

1. The **multi-year calendar heatmap** (years × days) for one area (C1).
2. **Sensor timeline with outages and mission ends** (C2): Terra 2000–, Aqua 2002–Aug 2026, S-NPP 2012–Nov 2026, NOAA-20 2020–, NOAA-21 2024–.
3. **The calibration and its held-out error** (C2/C10): "VIIRS sees about N× more 1 km cell-days than MODIS here; predicted within X % on years we held out" (N and X come from your own run — never from this document).
4. **"No detection ≠ no fire"** and **"degraded day"** markers (C2).
5. **Trace a day to its original pixels** (existing evidence drawer and recount) (C10).
6. Park Fire 2024 as the concrete story, and one contrasting area (crop burning or savanna) for global impact.
