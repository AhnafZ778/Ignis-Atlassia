# Playback and Ask JARVIS fix

## Changes

- Atlas playback uses a solid cyan magnitude fill, cobalt selection/focus outlines, an explicit hatch for incomplete exports, and a themed range control. Zero imported counts do not receive a fabricated bar height.
- Expanded conversations inherit the hosting page palette: dark on the globe landing page, light on analytical pages. Toolbar, chat header, message area, composer and evidence stage share theme tokens.
- The local launcher loads the installed assistant environment and private configuration. The earlier base-environment server reported AI unavailable because it had neither loaded that configuration nor the assistant runtime.
- Questions about the displayed day reuse owned, release-matched map evidence. Exact date, per-source counts and export-status paths are supplied before inference, reducing unnecessary tool turns. Invalid source references still fail verification; cost limits remain enforced.

## Observed browser verification

Desktop at 1440 px and mobile at 390 px: no JavaScript errors or horizontal page overflow. Daily bar selection updates the selected UTC day. The actual July 2006 archive renders all 31 source-incomplete days with the hatch/dashed status treatment. Both expanded themes and evidence graphs were rendered and captured. The final live server also confirmed that Ask JARVIS is enabled and an unselected-cell question returns clear selection guidance rather than attempting to invent a reading.

A real Ask JARVIS request through the configured AI& Efficient route completed with checked evidence for Park Fire, July 25, 2024: MODIS 603 detection records and 415 occupied cells; VIIRS S-NPP zero eligible records with a documented product-gap label. The answer retained source links and explained that missing records do not establish no fire. The successful question cost an estimated $0.001592 in one inference call; the estimate is not a provider invoice. Earlier diagnostic calls also consumed a small amount of credit.

Screenshots and the browser result log are in this folder. Tests use isolated temporary assistant state; production source observations were not modified and no new datasets were downloaded.

## Start the website

```bash
bash scripts/run_website.sh
```

Open http://localhost:8000/assistant.html. The private `.env.assistant` stays outside the exported site and Git. Static hosting cannot execute conversational AI without the backend.
