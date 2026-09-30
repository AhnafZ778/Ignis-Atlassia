# 7. Do not build this in the challenge path

Do not build a fire-spread replay, terrain analysis, fuels, weather, wind display, sector ranking, drone or airspace guidance, chat with the data, or a "most effective response" view.

Those features are not required by the challenge statement, they are not in the score claimed in section 2, and a model that builds them instead of section 4 and section 5 will miss the claimed score. If a pull request adds them, reject it.

The perfected plan also defers FIRMS Recent Pulse, NOAA-20 supplemental data, custom AOI, and
multilingual labels until P0/P1 are complete. If a rapid product is added later, it must be a
separate data mode with its own freshness, calibration, and limits; it may not alter the
historical calendar. The existing globe remains the only globe.
