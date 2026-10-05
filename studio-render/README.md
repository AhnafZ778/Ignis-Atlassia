# Prepared Studio documentary renderer

`npm ci` installs the pinned Remotion 4.0.532 renderer. `npm test` checks bounded prepared inputs. `node render.mjs /absolute/job/folder` reads the server-prepared `input.json`; arbitrary URLs, scripts, SVG event handlers and nonlocal narration files are rejected.

The operator must establish current Remotion license eligibility or hold an applicable license and set `FIREATLAS_REMOTION_LICENSE_ACK=free-eligible` or `company-license`. The application does not purchase a license or assume eligibility. Actual Remotion rendering remains unverified until that setting is supplied. It consumes the same saved resolved chapter timing, SVG figures, captions and checked narration as the web story.

The explicitly opt-in `FIREATLAS_STUDIO_LOCAL_RENDER=1` adapter uses Node.js, Chromium/Google Chrome and `ffmpeg`, and is identified as `local-svg-ffmpeg` in its export manifest. A silent 12-second 1080p/30fps QA video has been encoded and checked. Both adapters embed the saved resolved narration as a default English `mov_text` subtitle track, retaining `captions.vtt` as a separate artifact. Video-player subtitle support varies; enable captions in the player when needed. Version-2 captions split complete narration into shorter timed cues without changing its words. Older reader caption versions remain reproducible. Muxing copies the picture/audio streams rather than re-encoding them. `ffmpeg` is required for both adapters, including silent Remotion export. It needs no provider credentials; optional speech uses the existing assistant cost ledger.

See [implementation and test record](../docs/implementation/STUDIO.md) for startup, artifacts, remaining gates and exact configuration boundaries.
