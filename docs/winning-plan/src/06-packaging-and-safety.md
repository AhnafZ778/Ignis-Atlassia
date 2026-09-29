## C12 (rest) — Build, documentation, data access and reproducibility (weight 4, now 2, target 5)

C12-T1 to C12-T3 are in Gate 1 (section 5). These tasks finish the category.

### C12-T4 — Open-source licence

- **Files:** `LICENSE` (new, repository root), `pyproject.toml` (`license = "Apache-2.0"`), README badge.
- **Steps:**
  1. Copy the full, unmodified Apache License 2.0 text from https://www.apache.org/licenses/LICENSE-2.0.txt into `LICENSE`. Do not retype it.
  2. Add `NOTICE` listing: "FireAtlas © 2026 the FireAtlas team (names)". Third-party data are **not** covered by the code licence; state that in README → "Data licences" and link `/data.html`.
  3. Check that every bundled third-party file (Leaflet, fonts, images in `incident-media/`) has a licence allowing redistribution. For each image record source URL, author/agency and licence in `fireatlas/static/incident-media/SOURCES.md`. Remove any image whose licence is unknown.
- **Acceptance checks:** [ ] GitHub shows "Apache-2.0" in the repo sidebar. [ ] `SOURCES.md` has a row for every file in `incident-media/`, or the file is deleted.

### C12-T5 — README and PRD rewrite

- **Files:** `README.md` (≤ 120 lines), `PRD.md` (fix or move to `docs/archive/`).
- **README outline (exact headings, this order):**
  1. `# FireAtlas` + one line: `A harmonized MODIS + VIIRS burning-activity calendar built on NASA FIRMS.` + badges (CI, licence, live demo).
  2. `## Live demo` — public URL (C12-T6) + one screenshot of the calendar heatmap (`docs/img/calendar.png`, < 400 KB).
  3. `## What it does` — 4 bullets: multi-year calendar; harmonized S-NPP-equivalent unit with intervals; missing-sensor days marked; every number traceable to NASA pixels.
  4. `## Why it matters` — 3 sentences on sensor retirements (Terra, Aqua, S-NPP) and the need for a continuous record. Cite sources.
  5. `## Quick start` — `git clone …`, `uv sync`, `bash scripts/launch_demo.sh`, open `http://127.0.0.1:8000`. Nothing else is needed for the preset regions.
  6. `## Data` — table: dataset, product/version, DOI or URL, licence. Link `docs/DATA.md` (C2-T6).
  7. `## Method` — 5 lines + link `docs/HARMONIZATION_METHOD.md`.
  8. `## Validation results` — a small table copied from SCORECARD with the date of the run.
  9. `## Limits` — hotspot ≠ burned area; not tactical; confidence not comparable; complete export ≠ clear pass.
  10. `## Reproduce everything` — commands to rebuild aggregates and calibration from raw FIRMS archives (C2-T2, C2-T5).
  11. `## Team, AI use and credits` — names and roles, link `docs/AI_USE.md`, NASA/FIRMS acknowledgement text.
- **Delete from README:** all mentions of training lab, PWA, synthetic demo, casebook, `--judge-demo`, Windows PowerShell launcher (unless still shipped), and duplicated install sections.
- **PRD:** fix the contradictory line (`PRD.md:130`) or move `PRD.md` to `docs/archive/PRD-2026-09.md` with a one-line note "superseded by docs/winning-plan".
- **Acceptance checks:** [ ] `wc -l README.md` ≤ 120. [ ] `rg -n -i "training|pwa|judge-demo|casebook" README.md` returns nothing. [ ] A new person follows Quick start successfully (record name/initials in SCORECARD).

### C12-T6 — Public static site (no server needed by judges)

- **Goal:** a stable URL that works even if nobody's laptop is on.
- **Files:** `scripts/export_static.py` (new), `.github/workflows/pages.yml` (new), `tests/test_export_static.py`.
- **Steps:**
  1. `export_static.py --out site/` copies `fireatlas/static/` and writes pre-computed JSON for every preset region and every option combination the public UI exposes: `site/api/v2/calendar/<region>/<series>-<metric>-<day>-<types>-<confidence>.json` (use the same function as the live route; do not re-implement), plus `site/api/method/*.json` (calibration, availability, validation tables).
  2. In JS, add one switch: `const API_MODE = document.documentElement.dataset.apiMode || "live"`. In `static` mode, build file paths instead of query URLs. The exporter sets `data-api-mode="static"` in the copied HTML.
  3. Disable controls that need the server (custom bbox, CSV upload, recount) in static mode and show "Available in the local install".
  4. Pages workflow: on push to `main`, run tests, run `export_static.py`, upload `site/` with `actions/upload-pages-artifact`, deploy with `actions/deploy-pages`. Total size < 200 MB.
  5. Also attach the full aggregates + calibration + availability files as a **GitHub Release** asset `fireatlas-data-v1.zip` with SHA-256 in the release notes.
- **Acceptance checks:**
  - [ ] Public URL loads calendar for every preset region with the network panel showing no request to `127.0.0.1` and no failed request.
  - [ ] Test: exporter output for `norcal` equals the live API response byte-for-byte (after JSON normalisation).

### C12-T7 — Sources page and AI-use disclosure

- **Files:** `fireatlas/static/data.html` (rewrite as "Sources"), `docs/AI_USE.md` (new).
- **Sources page layout:** one card per dataset — name, provider, product/collection version, DOI/URL, licence/terms, date retrieved, file hashes, exact role in FireAtlas ("baseline input", "availability ledger", "independent check", "Tier 2 replay input"). Sections: "Harmonized record inputs" · "Validation references" · "Replay inputs (beta)" · "Map tiles and software".
- **`docs/AI_USE.md` template (fill truthfully):**

```markdown
# Use of AI tools
- Tools used: <list, e.g. Cursor with <model names>>
- Used for: code drafting, test drafting, documentation drafting, planning.
- Not used for: generating any data values, images of fires, or validation results.
- Human review: every merged change was read and run by <names>.
- Space Apps rule check: we follow the Space Apps AI guidance (link) and disclose here and on the project page.
```

- **Acceptance checks:** [ ] Every dataset used in code appears on the Sources page (test: a list in `fireatlas/sources.py` drives both the page and a unit test that greps the code for dataset IDs). [ ] AI_USE.md linked from footer and README.

### C12-T8 — Teamwork evidence (local rubric: Teamwork 5 points)

- **Steps:** each team member works on their own branch and merges through pull requests with a short review comment by another member; add `docs/TEAM.md` (name, role, what they built, with PR links). Use GitHub Issues with the task IDs from this plan (labels `tier1`, `tier2`, `submission`).
- **Acceptance checks:** [ ] ≥ 2 people have merged PRs. [ ] `docs/TEAM.md` lists roles.

### C12-T9 — Release and reproducibility check

- **Steps:** tag `v1.0-submission` after the final change; run `scripts/smoke_test.sh` against the tag; rebuild aggregates from raw archives for one region on a second machine and compare SHA-256 of the output with the release asset.
- **Acceptance checks:** [ ] Hashes match (paste both). [ ] Tag exists on GitHub.

**Master prompt (C12-T4…T9):**

```text
TASK C12-T<n>. Read docs/winning-plan/src/06-packaging-and-safety.md "C12-T<n>".
Follow the steps exactly; copy legal texts verbatim from their official source and paste
the source URL in the REPORT. Do not invent licences for images: if unknown, delete the
image and list it. Run the test suite. Output the REPORT block.
```

**C12 checklist:** [ ] T1 · [ ] T2 · [ ] T3 · [ ] T4 licence · [ ] T5 README · [ ] T6 static site · [ ] T7 sources + AI use · [ ] T8 teamwork · [ ] T9 release

---

## C5, C8, C9 — Tier 1 parts (safety wording and responder-facing information)

Tier 1 does **not** build Scout. It makes sure the current product says exactly what it is and never implies operational use. This lifts C5 to 2, C8 to 3 and C9 to 3.

### C8-T1 — Operational-safety wording and a banned-phrase test

- **Files:** `tests/test_safety_language.py` (new), all files in `fireatlas/static/*.html|*.js`, API text fields in `fireatlas/*.py`.
- **Banned phrases (case-insensitive) unless inside a sentence that negates them (list the allowed exact sentences in the test):** `predicts`, `prediction`, `forecast`, `safe zone`, `safe area`, `evacuat`, `dispatch`, `authoriz`, `guarantee`, `real-time`, `tactical`, `containment line`, `validated` (allowed only in "held-out validation" and when a validation file exists).
- **Required sentences (exact text, must appear on the home page footer and `/method.html` Limits):**
  - `FireAtlas is a research and learning tool. It is not an operational fire-management, evacuation or flight-planning tool.`
  - `For current fire information, warnings and orders, use the official sources listed for this region.` (the list comes from `official_links` in C9-T1). Never call a non-government app or website "official".
- **Test logic:** load every static file and a set of API responses (calendar, harmonization, briefing); fail if a banned phrase appears outside the allowlist.
- **Acceptance checks:** [ ] Test passes. [ ] Screenshot of footer with the required sentence.

### C9-T1 — Replace "responder briefing" with a "Season context" card and official links

- **Files:** `fireatlas/briefing.py`, `#responder-briefing` in `index.html`, `app.js`.
- **Changes:**
  1. Rename the card to **"Season context"**. Remove the label `historical-review-candidate` (`briefing.py:42-45`); instead output `record_status`: `comparable` (same product versions and all sources available), `mixed-versions`, `degraded-days` (k days listed), or `insufficient-history`.
  2. Content: selected period's value vs climatology (from C1-T3), season start shift (C1-T4), degraded days, and "What to check next" = links only.
  3. **Official links panel** per preset region, stored in `fireatlas/regions.py` as `official_links: [{label, url, kind}]` where `kind ∈ {agency, alerts, incidents, airspace}`. Seed (VERIFY every URL loads before commit):
     - `norcal` / `california`: CAL FIRE incidents (https://www.fire.ca.gov/incidents), InciWeb (https://inciweb.wildfire.gov), FAA TFR list (https://tfr.faa.gov).
     - `punjab-haryana`: VERIFY official state / national sources (e.g., Punjab Remote Sensing Centre, Indian Agricultural Research Institute CREAMS residue-burning bulletins); if none can be verified, show only NASA FIRMS and write "No verified official local source listed".
     - `rondonia`: INPE Queimadas (https://terrabrasilis.dpi.inpe.br/queimadas/portal/) — VERIFY.
     - `top-end-au`: North Australia and Rangelands Fire Information (https://firenorth.org.au) and NT Bushfires — VERIFY.
  4. Remove any "context not integrated" placeholder text (`briefing.py:76-81`); omit the section instead.
- **Acceptance checks:** [ ] API returns `record_status` values in tests for all four states. [ ] Each link was loaded (HTTP 200/301) — paste the curl results. [ ] No link is labelled "official" unless it is a government or agency site.

### C5-T1 — Scope statement for aerial observation (no Scout yet)

- Add to `/method.html` → "Where this could go" (3 short paragraphs, no promises):
  1. The harmonized calendar tells *when and where fires usually happen*; that helps plan **when** observation assets (satellite tasking, aerial surveys) are most useful.
  2. Any drone or aircraft use near wildfires is governed by the incident's aviation organisation and airspace rules (US: FAA TFRs under 14 CFR 91.137; NWCG Fire Traffic Area procedures in the NWCG Standards for Airspace Coordination / PMS 515 — VERIFY document titles). FireAtlas does not plan flights.
  3. The "Fire replay (beta)" extension (if shipped) studies, on a past fire, which areas were most uncertain — as a research question, not an operational tool.
- **Acceptance checks:** [ ] Text present; C8-T1 test passes on it; the citation URLs are on the Sources page.

**Master prompt (C5/C8/C9 Tier 1):**

```text
TASK <C8-T1|C9-T1|C5-T1>. Read docs/winning-plan/src/06-packaging-and-safety.md for the
task. Implement the exact wording given. For every URL, run curl -sI <url> and paste the
status line; do not add a URL you could not load. Do not add any feature that suggests
operational use. Run the test suite (including tests/test_safety_language.py). Output
the REPORT block.
```

**Checklist:** [ ] C8-T1 · [ ] C9-T1 · [ ] C5-T1
