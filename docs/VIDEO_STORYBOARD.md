# FireAtlas — perfected-plan video storyboard

**Status:** The local 30-second silent cut at
`docs/winning-plan/evidence/FireAtlas_30s_demo.mp4` and the local 90-second silent cut at
`docs/winning-plan/evidence/FireAtlas_90s_perfected_demo.mp4` are verified against the same static
bundle. The 90-second cut has a hash-bound WebVTT sidecar at
`docs/winning-plan/evidence/FireAtlas_90s_perfected_demo.vtt`; it remains a local rehearsal, not proof
of public deployment, external usability, eligibility, or independent scientific review. Neither cut
is submitted or publicly hosted. The existing globe remains the opening view and was not replaced.

## 30-second captioned cut (available locally)

| Time | Scene | On-screen caption |
|---|---|---|
| 0–4 s | Existing FireAtlas landing capture | **One daily calendar for researchers and local planners.** Compare dated MODIS + VIIRS detections on a shared UTC cell-day grid. |
| 4–12 s | Northern California · July 2024 calendar | **Comparison not usable.** Only 1 comparable year; the result is shown as insufficient history. |
| 12–15 s | Selected 25 July calendar day | **925.3 estimated cell-days.** MODIS-based estimate during a documented S-NPP processing gap; pass and cloud status remain unknown. |
| 15–18 s | Original source-row page | **Inspect the original records.** Acquisition time, native confidence, and product version. |
| 18–24 s | Punjab–Haryana · October 2024 calendar | **A harvest-window view for local planners.** Official 2024 monitoring context · heat detections do not confirm crop-residue fires. |
| 24–27 s | Northern California held-out calibration | **The current uncertainty is under-calibrated.** Nominal 95% intervals cover 41.5% / 39.0% of 41 held-out pairs each. |
| 27–30 s | End card | **See the dates. Inspect the evidence.** Local demo; public URL not verified; independent scientific review pending. |

The displayed counts and status phrases come from captured local screens. The October Punjab–Haryana
frame shows 5,174 observed cell-days, one comparable year, and the dated Government of India
[monitoring deployment release](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2060764&lang=2&reg=48).
The opening globe is a still capture and must not be described as a fresh renderer check.

## 90-second perfected-plan cut (local rehearsal captured)

This sequence follows **See → Compare → Verify → Share**. Every value must be read from the same
public build that the judge opens. If a scene is not present or a value cannot be checked, mark it
`NOT CAPTURED` instead of filling the frame with a placeholder.

| Time | Visual | Narration / caption |
|---|---|---|
| 0–5 s | Existing globe and controls | “NASA satellites watched fire activity for decades, but the record changes when the sensor changes.” |
| 5–15 s | Sensor Bridge | “Raw MODIS and VIIRS pixels are different units. FireAtlas deduplicates them on a common 1 km grid and keeps native VIIRS 375 m detail.” |
| 15–35 s | Northern California calendar | Read the live verdict, comparable-year count, evidence state, and one critical date exactly as shown. |
| 35–50 s | Selected day drawer | Show MODIS and VIIRS source values, native scale, FRP in MW/day per source, UTC time, product version, notice, and hash. |
| 50–65 s | Punjab–Haryana calendar | “The same controls show a different fire regime. Official context is separate; hotspots do not identify cause.” |
| 65–80 s | Native-mask method audit | Show 20/20 decoded Grove granules, 7/7 FIRMS rows matched, the common-grid method, weak interval coverage, and pending independent review. Park's 114/114 processing is available in the evidence drawer. |
| 80–90 s | Share evidence card and URL | Show value, state, versions, source inputs/hashes, limitations, and the share URL. “Every claim remains traceable.” |

The captured local rehearsal uses the seven frames in `docs/winning-plan/evidence/video-frames/` and
is rendered by `scripts/render_perfected_plan_video.py`. It is a silent H.264 file at 1600×900, 30 fps,
and approximately 90 seconds. `FireAtlas_90s_perfected_demo.manifest.json` binds the video, WebVTT
sidecar, source frames, and the current static bundle manifest to SHA-256 values and records the scene
durations. The captions identify the local static bundle and the remaining public and review gates; they
do not present the local capture as a deployed product.

### Required capture labels

- `ACTIVE FIRE ONLY` must remain visible when MCD64A1 is not bundled. Never show an invented
  burned-area overlay.
- `observed`, `scaled`, `unknown`, `documented processing gap`, and `complete zero export` must
  remain text or pattern labels, not color-only signals.
- FRP is source context, not burned area, severity, or a second activity count.
- A documented processing gap is not a proof of no fire or no satellite pass.
- The globe, its controls, and the globe-to-calendar handoff must remain unchanged.

## Capture and verification gate

Before describing the 90-second cut as a submission asset:

1. Capture the globe, bridge, verdict, drawer, method audit, and share card from one public build.
2. Recheck every visible number against the API/static JSON and source hash.
3. Run the static calendar, method, data, and shell verifiers with API requests blocked.
4. Repeat at approximately 1440, 768, and 390 px; test keyboard focus and reduced motion.
5. Rehearse the same path on the public URL with no credentials or localhost dependency; the local
   rehearsal currently does not satisfy this step.
6. Record whether an outside viewer can identify the two sensors, a hatched unknown/gap day, and
   the official context marker without prompting.

## Rebuild the current local 30-second cut

```bash
python3 scripts/render_winning_plan_video.py
```

The script uses the active local PNG captures, project-local fonts, and FFmpeg. It verifies a
silent H.264 stream at 1600×900, 30 fps, and 30 seconds. Do not submit or publish the clip until
the eligibility ruling, public URL, and perfected 90-second capture gate are recorded.

To rebuild the local perfected sequence after recapturing its frames:

```bash
python3 scripts/render_perfected_plan_video.py
```

That command verifies one silent 1600×900 H.264 stream at 30 fps and approximately 90 seconds.
