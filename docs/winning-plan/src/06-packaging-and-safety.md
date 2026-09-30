# 6. Publish what the judge will open

The perfected release path is a no-credential evidence demo. The public copy must carry the
same static JSON used by the calendar, Sensor Bridge, method audit, day drawer, and share card.
It must not silently fall back to localhost or a synthetic fixture.

## C8-T1 — Limits sentence

Put this exact sentence in the home-page footer and on `/method.html`:

`FireAtlas is a research and learning tool. It is not an operational fire-management, evacuation, or flight-planning tool.`

- [x] Both pages contain that sentence (`tests/test_web.py::test_winning_plan_safety_and_data_disclosures`).

## C12-T4 — Licence

Put the Apache License 2.0 text from https://www.apache.org/licenses/LICENSE-2.0.txt into `LICENSE` without retyping it. State in the README that NASA data is not covered by that code licence.

## C12-T5 — README

Rewrite `README.md` to at most 120 lines: what the site does, the public link, how to run it (`uv sync` then `bash scripts/launch_demo.sh`), the two regions, the data versions, and the limits sentence. Say that the home page opens on the 3D globe.

## C12-T6 — Public site

`scripts/export_static.py` writes a `site/` folder that contains the globe assets and pre-built `/api/v2/calendar` JSON for both regions and each year from 2010 through the latest complete year. The calendar must render from those files when the page is opened as static files. Deploy that folder to GitHub Pages.

The export also includes dated Park/Grove validity reports, analytical recount results, evidence ZIPs, standalone blank native-review forms, and a read-only Data Sources ledger. Run `scripts/verify_static_calendar.py`, `scripts/verify_static_method.py` for both cases, and `scripts/verify_static_data.py` against the release folder; these checks must pass without `/api/` requests. The static copy disables CSV imports and NASA sync controls while preserving the dated provenance and limitations.

- [ ] The public URL loads both regions with no request to `127.0.0.1`.
- [ ] The globe still renders on that URL.

### Perfected-plan release checks

- The header names the challenge and current data status.
- The Sensor Bridge labels raw MODIS, common 1 km transformation, VIIRS-equivalent activity,
  and native 375 m detail without adding sensor counts.
- FRP is shown as source-separated MW/day context, never as the calendar unit.
- State badges and patterns distinguish observed, scaled, unknown, documented processing gap,
  and complete zero export.
- The shareable evidence card includes selected value, state, product versions, source hashes,
  limitations, and the public URL. Its values are generated from the selected JSON, not baked
  into an illustration.
- If MCD64A1 is unavailable, the page says `ACTIVE FIRE ONLY` and links the NASA product. When
  a dated check is available, the release shows its hash-bound mapped count as lagged context
  and keeps independent review and pass/cloud limits visible. A release must never imply that
  MCD64A1 is active-fire truth or a perimeter.
- Rapid Pulse, if added later, is a separate mode with its own freshness, calibration, and
  limits; it cannot change historical calendar values.

## C12-T7 — Sources page

`/data.html` lists MODIS Collection 6.1 and VIIRS Suomi NPP 375 m with version, URL, date range,
retrieval date, file SHA-256, and the FIRMS acknowledgement from C2-T6. If MCD64A1 is acquired,
list its Collection 6.1 DOI and retrieval/hash details beside its lagged corroboration role.
Link `docs/AI_USE.md`, which names the tools used, says they did not generate data values, and
names the people who reviewed the numbers. Until a reviewer signs off, say that independent
review is pending.

**Master prompt:** `TASK <id>. Follow docs/winning-plan/src/06-packaging-and-safety.md for that task only. Output the REPORT block.`
