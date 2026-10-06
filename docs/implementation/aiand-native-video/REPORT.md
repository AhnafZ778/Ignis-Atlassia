# Actual AI& video generation

Implemented and exercised on 6 October 2026, following the explicit request to use AI& video models.

The earlier delivery used AI& for story text and Chromium/ffmpeg for pictures. It did not call the native video endpoint. Checking only the primary chat key also missed the second configured credential's video access. All three credentials were subsequently checked read-only: the second has accepted the current video terms and exposes MiniMax-H3. No terms were accepted by the application. The configured default now uses that enabled credential with `FIREATLAS_STUDIO_VIDEO_PROVIDER=aiand` and `FIREATLAS_AIAND_VIDEO_MODEL=minimaxai/minimax-h3`.

## Delivered behavior

Create story authors and grounds the storyboard, then invokes the actual native video integration. Refresh film & voice uses an existing saved storyboard. The backend:

1. Checks personal video acceptance and authenticated model pricing independently of the chat route.
2. Prepares the selected chapter's authentic image reference and uploads it to `/v1/files` with `purpose=vision`.
3. Submits `/v1/videos` with the actual video model, first-frame reference, 16:9 aspect ratio and 4–15 second duration.
4. Persists returned job identities before polling. Statuses such as moderation and in-progress appear in the Story view with the current chapter.
5. Downloads the provider's MP4 and records its hash, model and cost. Matching completed clips are reused; interrupted jobs reconnect by their saved ID.
6. Composes the native motion and sound with exact frozen evidence overlays, checked narration and embedded subtitles. Light text panels maintain contrast as the generated background changes.

AI-generated motion is illustrative. Exact measurement marks, source labels, values, UTC dates and heat domains come from the frozen graphical overlay, rather than trusting model-generated lettering. Native output is 768p; final composition upscales to 1080p. Chapters longer than 15 seconds retain the last generated frame for the remainder so narration is not clipped. The existing local renderer is an explicit alternate setting, not a silent fallback after a provider failure.

The video prompt lives in `fireatlas/studio/aiand_video.py`, separate from the grounded writing instructions. It calls for restrained editorial styling, continuous motion, quiet instrumental atmosphere and stationary evidence regions; it prohibits invented readings, perimeters, ignition or physical spread. Original calculations and scientific review/exposure gates remain unchanged.

## Actual provider acceptance

Five real image-conditioned MiniMax-H3 jobs completed successfully. Each requested 15 seconds and was quoted at $1.20, totaling **$6.00** for native generation. The returned clips contained H.264 video at 1344×768 and AAC sound. The initial assembled film was 87.187696 seconds with video, sound, checked neural narration and embedded subtitles. A later text-contrast correction reused all five downloaded clips, with **$0.00 in new native submissions**. The current assembled media details and reuse evidence are in [acceptance.json](acceptance.json).

Real browser checks verified the native model label, actual film playback with sound enabled, download controls, completed progress at 100%, reload retaining the native export, and 360/390/768 layouts with no horizontal overflow. No generation POST occurred during browser verification. See [the native Story view](native-story-desktop.png) and [a final film frame](native-film-frame.png).

The live run reused the existing owned acceptance story; it did not spend another writing request or alter the user's investigations. Private identity files, keys, full videos, uploaded-reference IDs and provider job IDs are excluded from the public report. Their owned receipts and clip caches remain in the ignored local Studio store.

## Failure and recovery behavior

An admitted AI& job cannot be aborted part-way. Cancel stops local delivery and retains its remote identity; the provider may still bill a successfully completed job. This limitation is reported explicitly. Unknown intermediate statuses remain running. Polling occurs every ten seconds; each provider wait can last up to one hour, separately from the local encoder's 15-minute limit.

Timeout during paid creation does not trigger a second POST. Recovery searches the account's recent jobs for one exact signed prompt/model/duration match; only a unique match is resumed. Ambiguity remains an explicit error. Known rejected or failed jobs can be retried through an explicit user refresh. Insufficient credits, acceptance requirements and provider failures are shown directly. The captured study is never replaced with another case.

Native video charges have exact per-second quotes and provider receipts independent of chat token accounting. The cached-clip count and new-submission amount distinguish reuse from another purchase. Download limits retain the existing 512 MiB output boundary; prepared scenes retain their existing input limits. Credentials never reach the browser.

## Checks run

- 71 Python native transport, authoring, story and voice tests passed; two additional native-manager branch/failure tests passed. The focused native-manager/transport rerun passed 22 tests.
- 62 assistant and Studio HTTP tests passed with mocked inference transports.
- All 81 frontend tests across 17 files passed, including native provider status and restoring a new native export after an older writing job.
- Eleven renderer tests passed, including actual native-clip composition with audio/subtitles and changed-clip rejection. TypeScript and production build passed.
- Supported static refresh and the landing guard passed: 75 protected asset hashes and both outside-header HTML boundaries match. Private configuration remains ignored with mode 0600.

Live verification covers the recorded key access, five completed jobs and assembled sample. It does not certify every prompt or future provider capacity. Static hosting cannot submit jobs or save private films; frozen readers remain usable. No public deployment or external publication occurred.

The provider documents native job creation, first-frame uploads, polling, pricing, audio and person-specific acceptance in its [official video API reference](https://docs.aiand.com/api/videos/).
