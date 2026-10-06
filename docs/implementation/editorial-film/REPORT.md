# Editorial infographic films and narration

Implemented and exercised locally on 6 October 2026. Landing assets, scientific calculations and private owner documents remain preserved.

The first film adapter sampled very few visual states, inherited crowded figure headings, and supplied no audio unless separately requested. The story preview also inherited white text over its light surface. Story persistence was prematurely terminal at 65%, before the associated film finished. These issues have separate renderer, styling, voice and durable-progress corrections.

Create story now uses a dedicated `zai-org/glm-5.3` AI& route with high reasoning and the revised `fireatlas/studio/story_system.md`. The prompt specifies an evidence-led arc, distinct chapter questions, concise headlines/captions, paced narration and a single main visual per chapter. Numerical claims still resolve from owned receipts. The selected model was authenticated against the provider catalog and exercised in one real writing request; conversational JARVIS's model configuration is unchanged. Existing reservations and price checks apply. No uncertain paid request is automatically retried.

The film renderer uses restrained cream/navy/cobalt typography, a large prepared figure, clearly separated captions and up to two checked fact fields. Duplicate internal headings and small UI badges are removed from presentation; measured marks, values, axes, dates and legends are retained. Smooth entrances and exits are sampled at 30 fps in persistent local Chromium. Frozen heat normalization and source scope remain unchanged. Explicit camera transitions move map geometry without moving its labels. The optional Remotion adapter shares the frame design, but a live licensed Remotion render was not exercised.

Piper supplies local neural narration from the saved checked text, with consistent loudness and full chapter audio. This is AI-generated narration, not a new measurement. Each chapter's presentation time can extend to fit its complete audio and a pause. The export manifest records original and actual durations plus adjustments; saved stories and scientific receipts are immutable. Existing paid speech fallback retains its accounting and failure rules. If narration cannot be prepared, the result explicitly says captions-only. `Refresh film & voice` uses the saved story without another writing request.

Story progress remains running after storyboard persistence, follows real narration/render phases and completes only when the film does. Refresh restores the saved render. Legacy completed/65% records reconnect to their actual associated render. Cancellation and checkpoint updates cannot revive cancelled delivery. See the [progress regression report](../story-progress-fix/REPORT.md).

## Actual acceptance

One real AI& authoring request produced five distinct evidence-grounded chapters. The installed neural voice and local renderer produced an 87.167-second film containing H.264 1920×1080 video at 30 fps, AAC audio and a `mov_text` subtitle track. The MP4 is 2,706,814 bytes. Saved story timing was 81 seconds; the manifest records the three extensions needed to retain full narration. ffmpeg measured mean audio volume at −18.6 dB. See [media metadata](media-report.json), [opening frame](opening-frame.png) and [activity frame](activity-frame.png). These frame captures were visually inspected for legible figure marks and clean typography.

Real browser acceptance restored the owned film after a simulated legacy 65% checkpoint, reached 100%, played with sound enabled, displayed download and saved-story refresh actions, and restored after reload without another generation POST. Layouts at 360, 390 and 768 pixels had no horizontal overflow or page errors. See [browser results](browser-report.json) and [completed desktop](story-completed-desktop.png). Browser playback and codec checks establish functional audio; subjective listener assessment and word-level forced alignment were not performed.

Automated checks run for this change:

- 66 Python story-generation, story and offline-voice tests, including actual local neural MP3 preparation.
- 62 Python assistant and Studio HTTP tests, using mocked inference transports.
- 79 frontend tests across 17 files; TypeScript and production build passed.
- Ten renderer tests, including smooth adjacent frame motion and actual MP4 audio/subtitle muxing.
- Supported static refresh and landing guard: 75 asset hashes and both outside-header HTML boundaries match.

The full repository suite was not rerun. Core scientific inputs, counts, filtering, version/completeness rules and pending independent review/exposure gates were not changed.

## Voice and provider provenance

The optional voice runtime is pinned in `requirements/studio-voice.txt`: Piper 1.4.1 and ONNX Runtime 1.30.0. The installed voice is `en_US-ljspeech-high`. Its model SHA-256 is `5d4f08ba6a2a48c44592eed3ce56bf85e9de3dd4e20df90541ae68a8310c029a`; configuration SHA-256 is `7e1f4634af596d83cca997fb7a931ba80b70f8a316a2655ee69c55365e0ace14`. Voice files remain ignored local assets. Piper is a GPL-3.0 optional runtime; the published voice model card lists MIT weights and the public-domain LJSpeech dataset. The filename's `high` suffix is not an independent quality certification. [Piper Python API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md), [pinned voice card](https://huggingface.co/rhasspy/piper-voices/blob/5512791644e2148e4be301d4c7fc2a4bf51a5057/en/en_US/ljspeech/high/MODEL_CARD).

Read-only authenticated checks returned the story model in AI&'s catalog. Its separately listed native video model was `minimaxai/minimax-h3`, with video-terms acceptance false for this account. No acceptance or native video generation call was made. This implementation authors with AI& and renders verified scientific visuals locally. A native generative video service is not asserted as working. [AI& model catalog](https://docs.aiand.com/api/models/), [AI& video API](https://docs.aiand.com/api/videos/).

Static hosting retains frozen reader/preview support; new story generation, private persistence and rendering require the local service and installed capabilities. Missing local voice files do not trigger a fabricated audio result. Credentials, owned acceptance identifiers and private full films are excluded from the report. No public deployment or external publication was performed.

Correction and subsequent delivery: the initial video-access statement above described the primary chat key. A later check of all three configured credentials found the second credential has accepted video terms. The [native video integration](../aiand-native-video/REPORT.md) now uses that enabled credential and AI&'s actual MiniMax-H3 video endpoint; it supersedes the local-only engine described in this historical report.
