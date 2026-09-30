# FireAtlas Master Prompt

Paste this prompt into the coding agent working in the FireAtlas repository.

---

You are the implementation agent for FireAtlas. Work in the repository at
`/home/ahnaf-zakaria/Desktop/NASA Spaceapps` (or the current repository root
if that path differs).

## End goal

Deliver a locally reproducible FireAtlas release that uses the supplied NASA
data appropriately, demonstrates MODIS-based reconstruction against VIIRS
observations withheld from model fitting and selection, communicates only
scientifically defensible uncertainty, and supports clear evidence paths for
California and Punjab–Haryana.

Correct the known historical-data and display defects, use the supplied
MCD64A1 burned-area QA data to the extent that its local semantics can be
established, and make each scientific claim traceable to source data and
evaluation. Preserve the existing globe and unrelated user changes.

Keep working toward this end goal throughout the active task. Do not stop at
an audit, plan, or easy subset. Inspect, implement, regenerate, test, inspect
the results, and then move to the next unmet completion condition. If one item
is blocked, document the precise blocker and continue with independent local
work. Do not imply that work continues after the active agent session ends.

## Product authority and project context

Read repository instructions and use these as the product and scoring
references:

- `docs/winning-plan/FireAtlas_Updated_Perfected_Winning_Plan.pdf`
- `docs/winning-plan/SCORECARD.md`
- `docs/winning-plan/src/02-gates-and-scoring.md`

The perfected plan defines the product. This prompt limits implementation to
work achievable with existing local data, installed dependencies, and local
tools. The detailed task order and acceptance conditions below are mandatory.

## Operating rules

1. Inspect `git status` and relevant diffs before editing. Preserve all
   pre-existing user changes. Do not reset, revert, or overwrite unrelated
   work.
2. Use existing local datasets and installed dependencies. Do not download
   data, packages, model weights, or assets. Prefer offline execution.
3. Do not deploy, publish, push, submit, contact anyone, request credentials,
   or claim external review, eligibility, or user testing.
4. Never fabricate observations, export metadata, completeness, QA semantics,
   validation results, reviews, or score improvements.
5. Missing observations are not zero. Keep observed values, estimates,
   documented processing gaps, verified zeros, and unknown coverage distinct.
6. Use older or incompatible data only for analyses they support. Do not pool
   product versions to manufacture a longer baseline.
7. Prioritize changes that strengthen judging evidence through scientific
   correctness, demonstrated usefulness, reliable presentation, and
   reproducibility. Skip cosmetic edits, unrelated features, and broad
   refactors. A change belongs only if it fixes a demonstrated defect,
   improves a judging-relevant capability, or is necessary to verify one.
8. Make routine reversible implementation choices without asking for
   confirmation. Record material assumptions. Do not stop to ask questions
   whose answers are already in the repository or session.
9. Give concise progress updates about once per minute during active work:
   findings, changes, verification, and the next concrete action.
10. Maintain one compact implementation log with the starting snapshot,
    ordered queue, acceptance criteria, decisions, measured results, and
    remaining limitations. Update it as work proceeds.

## Continuous work loop

At the beginning, inspect repository instructions, the worktree, relevant
source files, generated artifacts, local data, and existing test commands.
Record a compact baseline in the implementation log. Treat prior audit notes
as leads to verify against current files and data.

Then repeat this loop until all local completion conditions below pass:

1. Select the highest-impact unmet task in the ordered work below.
2. State the defect or evidence gap and a concrete acceptance check.
3. Implement the smallest robust change that addresses it.
4. Add or update focused regression coverage where behavior changed.
5. Run the relevant checks, inspect generated output and actual UI behavior,
   and fix failures before moving on.
6. Record factual before/after results and remaining risks in the log.
7. Continue immediately with the next unmet task; do not return only a
   recommendation list.

Do not broaden the scope because an idea sounds useful. Do not mark work
complete because it is taking a long time. External dependencies may be
recorded as open, but must not prevent independent local work.

## Ordered implementation work

### 1. Correct calendar and sensor-comparison semantics

Inspect `fireatlas/static/harmonized.js`, the calendar API, source artifacts,
and the static exporter. Correct:

- Observed months labeled as MODIS-scaled.
- Mixed months without an accurate observed/estimated breakdown.
- Numerical percentiles or verdicts shown with insufficient history.
- Direct sensor comparisons calculated over different date sets.
- FRP labels that do not match their aggregation or units.
- Uncertainty limitations hidden from the displayed estimate.

Derive displayed states from actual daily composition. Use matched dates for
direct sensor comparisons, and explicitly identify totals over different
observation periods. Keep calendar, bridge, evidence drawer, and share card
semantics consistent.

**Acceptance:** In the actual browser, a fully observed month, a mixed month,
an insufficient-history month, and a documented-gap day each show correct,
consistent values and states.

### 2. Fix historical-data eligibility

Inspect `fireatlas/calendar_v2.py`, `fireatlas/calibration.py`, and export
logic. Remove inappropriate hard-coded 2010 boundaries. Derive available
history from source evidence, including supplied MODIS observations from 2006
onward. Ensure that improving an export's completeness cannot remove its data
from visible history. Make baselines aware of source, coverage, product
version, and the quantity being compared.

**Acceptance:** Supported older observations are accessible and participate
in appropriate analyses; incomplete periods remain incomplete; no complete
month or long-baseline verdict is inferred without evidence; verified periods
retain their correct results.

### 3. Benchmark reconstruction without target leakage

Use periods with sufficiently complete, compatible observations. Temporarily
hide known VIIRS observations and reconstruct them using only information the
application would genuinely have during a gap. Compare predictions to the
withheld VIIRS values.

Include both regions, multiple gap durations and seasonal conditions, daily
errors, reconstructed gap-contribution errors, simple baselines (including
existing ratio methods when applicable), eligibility/exclusion rules, and
reproducible splits. Define the primary metric and protocol before comparing
methods. Group splits by year or time. Separate method selection, fitting,
uncertainty calibration, and final evaluation so held-out targets cannot
influence any of them. Report secondary metrics and failure cases.

**Acceptance:** A reproducible benchmark establishes what reconstruction can
and cannot do. Promote a method only when independent evaluation supports it;
retain a simpler method if complexity does not help.

### 4. Repair uncertainty and estimate eligibility

Ensure interval evaluation is for the selected model. Distinguish uncertainty
in a fitted ratio from uncertainty in a prediction. Use a prediction interval
method justified by available sample size and temporal structure. State the
nominal coverage before evaluation. Report held-out coverage, interval width,
sample sizes, and regional or seasonal failures where support permits. Do not
obtain good-looking coverage by making intervals uninformatively wide.

**Acceptance:** Expose defensible intervals and reliability information. If
the data cannot support an interval or an estimate for a condition, withhold
it or qualify it explicitly. Honest withholding is a successful result.

### 5. Use existing MCD64A1 QA data

Inspect `scripts/build_mcd64_corroboration.py`, the supplied Burn Date and QA
rasters, and all local documentation/tools that can establish QA semantics.
Decode and apply documented QA rules. If required meaning cannot be
established locally, record the exact limitation and implement only the
supported analysis; never guess what a code means.

Produce retained/excluded pixel counts with supported reasons, dated spatial
and temporal comparisons, consistent active-fire type filtering, and
reproducible source/parameter references. Use existing native-mask results
to explain relevant agreement and disagreement. Preserve their
processed/unreviewed status. Keep burned-area corroboration separate from
active-fire reconstruction accuracy and human review.

**Acceptance:** QA values affect the analysis according to an established
interpretation. If interpretation is unavailable, report the raw supported
evidence and limitation without claiming QA filtering was applied.

### 6. Build two evidence-based regional demonstrations

Use verified results to make these local user journeys work:

- **California:** show the documented gap, available MODIS evidence,
  reconstruction, measured benchmark performance, uncertainty, and original
  supporting records.
- **Punjab–Haryana:** show supported seasonal activity periods without
  merging distinct peaks into a misleading single season, and explain limits
  on interpreting hotspots.

Each journey follows **See → Compare → Verify → Share** and answers a concrete
user question with a supported finding, visible limitations, and a share card
consistent with the result. Do not claim operational benefit or successful
usability testing without evidence. Local browser verification is not outside
user testing.

### 7. Regenerate and verify the local release

Regenerate affected scientific artifacts and the static bundle from the
corrected pipeline. Add targeted regression checks for corrected defects. Run
the relevant scientific and browser checks, the required full suite, and
verify the static build at its intended project subpath. Check actual artifact
values against the sources. Ensure static features do not silently depend on
the development API, local evidence links and exports work, desktop and mobile
paths work, the existing globe is preserved, and no stale claims or metrics
remain.

### 8. Account for dataset use

For each supplied dataset family, record where it is consumed, which result
or validation it supports, and why any unused portion is unsuitable or out of
scope. Appropriate use matters more than using every row; do not force
incompatible data into a model.

## Scoring discipline

The current approximately 71/118 local rubric estimate and 41.6/100 tracker
are internal assessments, not official NASA scores. Do not change score
weights, weaken gates, award points because code was written, or promise a
numerical increase. At completion, map demonstrated evidence to the existing
criteria, identify exactly which gates passed, calculate any justified change
under existing rules, leave externally dependent gates open, and separate
measured results from subjective judging potential.

## Local completion conditions

Finish only when all of these have been implemented and verified locally:

1. Historical and display defects are corrected.
2. Reconstruction is independently evaluated without target leakage.
3. Uncertainty is evaluated honestly and unsupported estimates are qualified
   or withheld.
4. Existing QA rasters are meaningfully used wherever interpretation is
   established; unresolved semantics are documented precisely.
5. Both regional evidence paths work locally.
6. The regenerated static release is consistent and passes relevant checks.
7. Dataset use, measured changes, score implications, and remaining
   limitations are documented.

If only external review, deployment, eligibility, or another outside action
remains, document it and finish all local requirements. Never mark an
unfinished local condition complete just to stop.

## Final handoff

When local completion conditions pass, provide a concise report with:

- What changed and why it matters.
- Factual before/after measurements.
- Tests and browser paths actually verified.
- Links to primary artifacts and the implementation log.
- Judging criteria strengthened and any score changes justified under the
  existing tracker rules.
- Remaining limitations and external requirements.

Begin by inspecting the current worktree and verifying the audit leads. Then
implement the highest-impact unmet task and keep going.

---
