# 09 — Stories, readers, narration, video, and resource recovery

[Context entry point](../../CODEBASE_CONTEXT.md) · reviewed 2026-10-27

## Shared story authority

studio/story.py validates authored story bodies and resolves them into fireatlas-resolved-story-v1. The browser player, exported reader and video consume this prepared scene contract. Do not independently reinterpret card numbers or chapter timing in a renderer.

A story has a title/profile/audience/target duration, bounded chapters and optional style. Chapters reference selected cards and frozen evidence plus caption, narration/structured narration segments, timing, transition, question, study/selection, camera, layers, visible gallery and source filter.

Limits: 24 chapters, ten minutes total, 2–300 seconds per chapter; the default profile is landscape 1920×1080 at 30 fps with 120-second target. Audience profiles control visible evidence detail; manually authored text is preserved when adapting default prose.

resolve_story checks snapshot/receipt/scale/scope, constructs visuals and schematic fallbacks, resolves checked narration fields and freezes scene timing. Resolved identity binds the prepared content. A saved story revision records its source document revision, so later board edits do not silently replace old exported evidence.

| Module | Responsibility |
| --- | --- |
| studio/story.py | clean_story/default_story/resolve_story, captions/transcript, export_reader/verify_reader |
| studio/narrative.py | Validate structured text/checked-field segments; resolve cited fields from frozen receipts |
| studio/evidence.py | Ground scalar values/units; check narration numbers |
| studio/visuals.py | Prepare figures, selected intervals/cells, gallery and camera display |
| studio/heat.py | Frozen occupied-cell heat image and common scale |
| studio/context_layers.py | Freeze/verify existing prepared context images; no new scientific inference |
| studio/story_generation.py | Capture revision, request a structured storyboard, validate and save it durably |
| studio/narration.py / local_voice.py | Speech preflight, splitting, caching, duration/hash checks, optional offline Piper |
| studio/render.py / resources.py | Persistent media jobs, admission, worker monitoring, cancellation/restart recovery |
| studio/aiand_video.py | Authenticated native video capability, durable clip checkpoints and reuse |

## Checked narration versus authored interpretation

Numerical fields resolve through snapshot_id + receipt pointer; the model cannot set a replacement unit or number. Narration segments distinguish plain authored explanation from checked fields. Invalid/missing values remain unavailable. Exporting the recipe and its receipts allows verify_reader to reconstruct checked figures/captions/text. Authored explanation remains interpretation, even when its numeric tokens pass a grounding check.

story_generation.compose accepts a narrowly structured four-to-six-chapter storyboard over captured selected cards. It validates card IDs, checked-field references and numbers; preserves matched paired sensor heat maps; and keeps the frozen card's actual display selection ahead of model directions. Generated film duration is additionally bounded 45–120 seconds.

Generation captures document revision before provider work. A completed storyboard survives later render-admission failure as partial work. Do not repeat a paid writing request just because video preparation failed. Restart/recovery status must be distinguished from fresh generation.

## Reader path

export_reader writes a portable reader with frozen scene data, figures, evidence receipts, captions/transcript and manifest. The static studio-reader controller runs without the authoring service. Player states are reading, question-paused, exploring and returning. Frozen evidence exploration can resume at the saved chapter/position without recalculating the study.

```bash
python -m fireatlas.studio.story verify-reader path/to/extracted/reader
```

Reader reproduction is an integrity/check-field guarantee, not independent endorsement of interpretation.

## Render engines

| Engine | Entry/runtime | Boundary |
| --- | --- | --- |
| Local prepared documentary | studio-render/render-local.mjs; Node + Chromium + ffmpeg | Explicit FIREATLAS_STUDIO_LOCAL_RENDER opt-in; frozen SVG scenes |
| Remotion | render.mjs + entry.jsx; pinned Remotion | Requires installed packages and operator license acknowledgement |
| AI& native video | Python aiand_video + prepare-aiand.mjs / compose-aiand.mjs | Image-conditioned provider clips/sound composed with exact evidence overlays; separately charged remote generation |

capabilities.py reports actual configuration, binary/module presence and fallback reason. A provider chat key does not establish native-video access. Runtime model names and fees must be checked through provider admission, not hardcoded as current external facts in this guide.

Native provider footage is illustrative generated media; authentic charts/counts still come from frozen evidence. Local preparation, paid remote clip creation, speech and final assembly are separate phases and can fail independently. Completed native clips can be reused; uncertain paid requests must not be blindly resubmitted.

studio-render/input.mjs rejects unbounded scene count/timing, unsupported profile, remote URLs, executable SVG, malformed camera bounds and unverified/locality-violating audio references. Rendering consumes prepared data rather than user code. camera.mjs supports bounded figure motion without moving fixed labels/legends.

audio.mjs, subtitles.mjs, film-frame.mjs and compose-aiand.mjs have local fixture tests. Timed VTT and an embedded subtitle track retain checked text; player subtitle visibility varies. Audio is hash-checked and measured before assembly. Missing/failed/overlong provider speech can yield a complete captioned film without a paid retry. Offline local timing adjustments are recorded separately from the immutable saved story.

## Persistent jobs and cancellation

Render states: queued, running, completed, failed, canceled. Phases additionally include preparing-assets, narrating, generating-video, rendering, encoding and finalizing. Other subsystems sometimes use cancelled with two l's; preserve the subsystem's actual wire contract.

A render binds story_id + immutable story_revision. It saves progress/manifest/artifact paths and exposes video, manifest, transcript, captions and evidence hashes. StoryDirector restores recent exports by saved revision. SSE updates have polling/reload recovery paths.

One render runs at a time. Local worker resources are sampled using Linux /proc identities, process-tree accounting and explicit storage admission. The local watcher checks approximately every 0.2 seconds, with 2 GiB summed resident-memory, CPU and 15-minute execution/1 GiB working-output gates. This is sampled enforcement, not a hard kernel allocation quota.

Cancellation checks gate final publication and stop the owned worker/process group; restart verifies process identity before recovery and discards unfinished media. Completed exports are not automatically deleted to free storage. Never kill a process solely from an unverified recycled PID.

## Verification and limitations

Tests: test_studio_story.py, test_story_generation.py, test_aiand_video.py, test_studio_local_voice.py, test_studio_resources.py; frontend scenes/storyExplore/renderRecovery; npm --prefix studio-render test. Browser scripts: verify_studio_browser.py, verify_story_progress.py, verify_native_video.py. The native-video verifier inspects an existing saved film and should not create another paid request.

Historical media acceptance reports live under docs/implementation/. Passing local tone fixtures or provider mocks does not verify live speech quality, word-level alignment, hosted renderer licensing, or an actual new paid video job. No provider job was submitted while creating this context.
