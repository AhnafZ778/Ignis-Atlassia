# Perfected winning plan — implementation delta

The authoritative planning document supplied on 30 September 2026 is
`FireAtlas_Updated_Perfected_Winning_Plan.pdf`. The earlier `FireAtlas_Winning_Plan.pdf`
remains a historical implementation record. This note records what changed and what the
repository can honestly support.

## Differences from the earlier plan

| Change in the perfected plan | Current implementation response | Evidence state |
|---|---|---|
| Make **VIIRS-equivalent active-fire cell-days on a common 1 km grid** the primary measure; keep native VIIRS 375 m detail separate. | Calendar metadata now names the primary measure; daily bundles expose native pixel size, common-grid method, and source-specific counts. | Implemented from imported FIRMS rows; centroid binning is not a native mask resampling. |
| Use authentic standard fire masks to test the bridge, rather than treating point exports as coverage. | Grove's local native ledger now decodes 20/20 supplied MOD14/MYD14/VNP14IMG granules into 15,495 clipped pixels; Park decodes 114/114 into 1,372,872 pixels. Reconciliation is 7/7 and 3,137/3,137, and the method page retains descriptive usable pairs within 90 minutes. | Raw-cell review and the full-footprint pass/cloud denominator remain open for both cases. |
| Make the MODIS → common grid → VIIRS bridge visible, including MODIS-only, VIIRS-only, both, and gap/unknown states. | The landing calendar now renders a Sensor Bridge panel with three source/result stages, mismatch bars, and explicit gap state. | Implemented for complete source-export days; incomplete days remain unknown. |
| Show raw Fire Radiative Power separately from activity counts. | The bridge panel shows MODIS and VIIRS raw FRP sums in MW/day, separately from cell-days. | Implemented from the imported FIRMS `frp` field; FRP is not calibrated or added across sensors. |
| Add independent MCD64A1 Collection 6.1 burned-area corroboration. | Dated Burn Date + QA rasters are hash-bound in `fireatlas/samples/mcd64_corroboration.json`; the UI shows month-specific mapped counts as lagged context and keeps active-fire-only limits. | Analytical corroboration is present; independent review and public deployment remain open. |
| Add a shareable evidence card containing value, state, versions, inputs, and limits. | “Share evidence” creates a visible card and copies a parameterized calendar URL when browser sharing/clipboard is available. | Implemented locally; the URL still depends on the host serving the static/API data. |
| Separate Rapid Pulse from the historical science calendar. | The existing NRT controls remain a separate legacy workspace. The harmonized calendar is labelled historical; no NRT records are silently mixed into it. | Boundary documented; a new pulse product remains P2 and is not claimed as complete. |
| Align the visible journey to See → Compare → Verify → Share. | Globe remains first, the bridge sits above the daily calendar, source rows remain inspectable, and the share card is adjacent to the bridge. | Implemented without changing the globe. |
| Make the release identity inspectable at the point of use. | The calendar shows the static bundle date, bridge method version, source-hash count/sample, and the share card labels its input versions and SHA-256 sample. | Implemented locally; the displayed snapshot is not a public deployment proof. |
| Apply the prescribed color-independent state grammar. | Calendar, history, and the validity evidence map now use cyan solid for observed, amber hatch for estimates, purple hatch for documented gaps, gray crosshatch for unknown exports, and blue-gray zero-export cells; source colors remain distinct where they identify MODIS versus VIIRS. | Implemented locally; the palette communicates state but does not add missing pass/cloud evidence. |
| Add independent corroboration, external usability, deployment, and eligibility gates. | These remain explicit open gates; no score is raised merely because a UI card exists. | Not complete: MCD64A1 input, independent review, Local Lead ruling, and public deployment are still absent. |

## Scientific boundary kept from the perfected plan

- A raw MODIS count and raw VIIRS count are never presented as the same quantity.
- The calendar selects one reference observation per day; it never sums both sensors into one
  “fire count.”
- Raw FRP is source context, not a harmonized activity measure.
- A complete zero export is labelled a zero in the export, not a clear pass or fire-free area.
- Missing, incomplete, or documented-outage days remain unknown or gap-marked.
- A scaled value during a documented outage carries both labels in the API: `evidence_state=scaled`
  and `coverage_state=documented_processing_gap`; the calendar text says “gap · scaled estimate”.
- MCD64A1 is a lagged burned-area corroboration product, not active-fire ground truth.
- No globe controls or globe renderer were changed for this delta.

## Verification target

The bridge and card are generated from the same API/static JSON used by the calendar. They do
not contain Park, Grove, FRP, mismatch, or version values baked into graphics. After rebuilding
the static bundle, run:

```bash
uv run --offline python -m unittest discover -s tests -q
uv run --with playwright python scripts/verify_static_calendar.py --site site
uv run --with playwright python scripts/verify_static_method.py --site site --case park-2024
uv run --with playwright python scripts/verify_static_method.py --site site --case grove-2025
uv run --with playwright python scripts/verify_static_data.py --site site
uv run --with playwright python scripts/verify_static_shell.py --site site
```

The calendar check also verifies a documented-gap day is visibly labelled “gap · scaled
estimate”, opens bundled NASA source rows, and reveals the share card. These checks establish
local reproducibility and browser behavior. They do not establish a NASA judge score,
authentic MCD64A1 coverage, pass/cloud masks, or public-host availability.
