# FireAtlas — 60-second visual data journey

Capture `/method.html` using its actual historical data. Keep date, sensor and units visible. The diagrams marked schematic explain processing; they do not represent actual orbits or satellite footprints.

| Time | Capture | Short on-screen words |
| --- | --- | --- |
| 0–10 s | Five-stage workflow across the page | **NASA → CSV → UTC + source → shared grid → calendar** |
| 10–20 s | Park selected; choose 25 July in the workflow's UTC selector | **603 original pixels → 415 detected cells** |
| 20–29 s | Click a source row in the real-cell example, then show the daily union equation | **Same cell. Same day. Count once.** |
| 29–39 s | Migrated “Observation gaps” scene; NASA outage notice | **No detection ≠ no fire.** S-NPP processing interruption. Pass/cloud unknown. |
| 39–49 s | “What changed” scene and “Open this case in the calendar” | **Dated observations → daily calendar.** The official incident marker is separate. |
| 49–60 s | Click “Run the recount”; capture the returned result and ZIP link | **Recomputed from source rows.** Human scientific review pending. |

The sample Park numbers describe the bundled case at the time this script was written. Capture displayed results; never insert these numbers into graphics if inputs change. The recount covers the whole 17–31 July case: 3,137 original pixels / 1,606 detected cell-days. It checks file consistency, grid assignments, daily totals, union/overlap and sensitivity trials. It does not authenticate NASA, verify native-mask coverage or provide external scientific sign-off.

For a timeline-only 16:9 frame, use `/method.html?frame=1&case=park-2024`. The older [Park capture](presentation/park-fire-2024-evidence.png) predates this page migration; recapture before use.

## Recording controls

- Top case and UTC controls update the workflow, the actual-cell example, the union equation and the migrated case scenes together.
- The source inspector receives the exact AOI, series and date from an authentic calendar link. Its monthly audit is explicitly **whole-month**, while the historical example workflow uses the **fixed case window**.
- Incident photos appear only with the evidence section expanded; they are context, not calculation inputs.
- Recount success is shown only after the current server calculation. Capture errors and missing states honestly.
- Keep unavailable pass/cloud coverage in view; do not invent perimeters, forecast spread, sensor equivalence or a judging score.

Build plan and acceptance criteria: [DATA_METHOD_PAGE_PLAN.md](DATA_METHOD_PAGE_PLAN.md). Scientific case definitions: [VALIDITY_CASES.md](VALIDITY_CASES.md).
