# JARVIS infographic story creation

Implemented 6 October 2026. The landing remains protected.

The primary **Create story** action now submits an owned, revision-bound job instead of creating an empty six-chapter template. It freezes the selected board, resolves missing supported scientific bindings using their captured scope, calls AI& once with a dedicated director prompt, checks references, composes scenes, saves the resolved story and starts the existing local video renderer. Editing is under **Edit story & export settings**. A live progress bar, cancellation, film player and download actions replace the default editor-heavy screen.

The director's instructions live in `fireatlas/studio/story_system.md` and are included in Python package data. AI& writes structured narration and chooses existing visual cards; it does not generate observations, axes, image URLs or numerical chart series. The checked receipt resolver supplies values and units. Known UTC date lists and selected acquisition dates support readable prose. Valid cross-card citations attach their actual owned receipts without changing the visible selection. Frozen scenes retain the existing scientific preparation and recount contract.

AI& credentials remain in the ignored, mode-0600 `.env.assistant`. `AIAND_API_KEY` selects the primary credential; optional `AIAND_API_KEYS` supplies an ordered server-only pool. Only an authentication rejection during the read-only model-catalog check permits trying the next credential. An inference failure or uncertain timeout never triggers another paid request. Catalog prices and model capabilities are checked before existing assistant reservations are made. Cost, usage and model receipts are recorded in the same private accounting store; keys are absent from capabilities, documents, job receipts and generated assets.

New interfaces:

- `POST /api/studio/documents/{id}/story-generations`: `expected_revision`, optional selected card IDs and `render` Boolean.
- `GET /api/studio/story-generations/{id}`: durable stage, progress, saved story/render references, provider receipt and omissions/errors.
- `POST /api/studio/story-generations/{id}/cancel`: prevents late story insertion and stops the associated render.
- `POST /api/studio/story-generations/{id}/resume`: explicitly finishes a retained storyboard without another AI call. An uncertain call with no saved storyboard cannot be automatically repeated.

Migration 7 adds owned story-generation checkpoints. Source revision and scene saving happen together. Later board changes do not replace the captured source. Refresh reconnects to the saved job. A renderer failure retains the interactive story and reader export. A service interruption fails visibly and does not repeat inference. Existing JARVIS `create_story_draft` proposals use this director when configured; applying a proposal opens the Story view and its real progress. Manual drafts remain available when AI& is unavailable.

AI& is the storyboard author, not a claimed native video-generation API. Chromium/ffmpeg locally builds the MP4 from verified prepared SVG scenes with infographic framing, bounded chapter transitions and embedded subtitles. The optional Remotion renderer shares the same frame layout. Voice remains the existing separately configured speech integration; the default film has captions and transcript. Static hosting supports frozen readers and previews; new AI generation and saved jobs require the service. The selected local renderer does not require a new Remotion licensing assertion.

Verification artifacts and results are recorded alongside this report. Three supplied credentials authenticated successfully against `/models`. Real authenticated AI& authoring was exercised on authentic Park evidence; initial validation defects were corrected and its retained response was recovered without another paid request. The completed six-chapter film contains H.264 1920×1080 video and embedded `mov_text` subtitles, lasts 95 seconds, and retains the checked 6,224 eligible detections / 2,228 joint cell-days. This validates the recorded requests and sample, not future provider capacity or every possible user question.

Scientific counts, filtering, alias rules, grid, release identities, missingness and scientific gates remain unchanged. Pending independent scientific review and exposure validation remain pending. No deployment or external publication was performed.

## Recorded checks

- Python regression suite: 154 tests passed in the optional assistant environment, including existing Studio stories, store, HTTP, JARVIS and assistant contracts.
- Focused authoring/recovery/date suite: 10 tests passed; transport mocks verify authentication fallback, billing receipts and no inference retry.
- Frontend: 76 tests across 17 files passed, including applied-revision submission, progress, refresh recovery and cancellation blocking a late response. TypeScript and production build passed.
- Renderer: eight checks passed, including actual subtitle muxing and bounded infographic framing.
- Browser: saved AI& story, actual MP4 download, refresh and 360/390/768 layouts passed with no page errors. See `live-report.json` and screenshots.
- Landing: 75 protected asset hashes and both outside-header HTML boundaries match after the supported static refresh.
- Credentials: zero supplied keys found in tracked files. Private configuration remains Git-ignored.

The browser's successful final export was recovered from its earlier actual AI& response and rerendered after framing corrections. No paid retries occurred during recovery. The representative MP4 is retained privately at `/tmp/ignis-infographic-film.mp4`; source scientific data and private stores are not published with the report.
