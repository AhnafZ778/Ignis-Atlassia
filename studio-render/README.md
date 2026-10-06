# Prepared Studio documentary renderer

`npm ci` installs the pinned Remotion 4.0.532 renderer. `npm test` checks bounded prepared inputs. `node render.mjs /absolute/job/folder` reads the server-prepared `input.json`; arbitrary URLs, scripts, SVG event handlers and nonlocal narration files are rejected.

The operator must establish current Remotion license eligibility or hold an applicable license and set `FIREATLAS_REMOTION_LICENSE_ACK=free-eligible` or `company-license`. The application does not purchase a license or assume eligibility. Actual Remotion rendering remains unverified until that setting is supplied. It consumes the same saved resolved chapter timing, SVG figures, captions and checked narration as the web story.

The explicitly opt-in `FIREATLAS_STUDIO_LOCAL_RENDER=1` adapter uses Node.js, Chromium/Google Chrome and `ffmpeg`, and is identified as `local-svg-ffmpeg` in its export manifest. A silent 12-second 1080p/30fps QA video has been encoded and checked. Both adapters embed the saved resolved narration as a default English `mov_text` subtitle track, retaining `captions.vtt` as a separate artifact. Video-player subtitle support varies; enable captions in the player when needed. Version-2 captions split complete narration into shorter timed cues without changing its words. Older reader caption versions remain reproducible. Muxing copies the picture/audio streams rather than re-encoding them. `ffmpeg` is required for both adapters, including silent Remotion export. It needs no provider credentials; optional speech uses the existing assistant cost ledger.

See [implementation and test record](../docs/implementation/STUDIO.md) for startup, artifacts, remaining gates and exact configuration boundaries.

The current local renderer uses a cream/navy editorial layout, one large frozen figure per chapter, editable story captions and 30 fps entrances/exits. A persistent local Chromium process captures smooth motion; neither animation nor voice changes the scientific values or heat domain. Offline narration extends video presentation timing when needed to retain every spoken word; the manifest records these adjustments separately from the immutable saved story.

For optional local neural narration in the existing assistant environment:

```bash
uv pip install --python .venv-assistant/bin/python -r requirements/studio-voice.txt
.venv-assistant/bin/python -m piper.download_voices --data-dir data/voices en_US-ljspeech-high
```

Run these commands from the repository root. Set `FIREATLAS_STUDIO_VOICE_PROVIDER=piper` in private configuration and restart the service. `FIREATLAS_STUDIO_VOICE_MODEL` can select another installed compatible ONNX voice. Voice files remain local ignored assets. Piper is a GPL-3.0 optional runtime; the selected published voice weights carry MIT licensing and use the public-domain LJSpeech dataset. Its provenance and verified model/configuration hashes are in the [film acceptance report](../docs/implementation/editorial-film/REPORT.md). Offline speech needs no API key or paid speech reservation. Missing narration remains an explicitly labeled caption-only result.

With `FIREATLAS_STUDIO_VIDEO_PROVIDER=aiand`, `prepare-aiand.mjs` prepares authentic first-frame images; the Python backend uses AI&'s native video API and persists remote jobs/downloaded clips. `compose-aiand.mjs` combines the returned video/sound with transparent exact-evidence overlays and checked narration. The local renderer remains an explicit alternative. Native generation is charged by AI& per second, independently of the local encoder. [Native setup and acceptance](../docs/implementation/aiand-native-video/REPORT.md).
