# Story progress recovery — 6 October 2026

The storyboard save published `completed` at 65% before admitting the requested video render. Story Director therefore stopped polling during that short interval. The reported film nevertheless completed in about 27 seconds. Read-only inspection and ffprobe confirmed its saved 100-second H.264 1920×1080 video, embedded subtitle stream and 2,078,222-byte MP4.

The storyboard checkpoint now remains `running / preparing-video` at 65%. Story-only requests complete atomically at 100%. Linked renderer stages update the generation record in the same database transaction; completed films report 100%. Reading an older generation reconciles it with its actual render using a revision check, without overwriting newer updates or cancellation. Existing authoring admission remains separate from the existing single-render admission.

The frontend continues polling legacy premature completion responses, accurately labels storyboard-versus-film readiness, resets progress on board changes and retains its existing cancellation and stale-response guards. A completed saved film restores its player and download on refresh. No saved story or scientific result was regenerated.

Verification performed:

- 62 Python authoring/story/render tests passed, including blocked render admission, durable completion without a browser, cancellation and storyboard-only completion.
- All 78 frontend tests across 17 files passed, including the exact 65% response sequence, completed film restoration and cancellation. Existing unrelated JARVIS tests emitted React `act` warnings.
- TypeScript and the production build passed. Supported static refresh copied the generated assets; 75 protected landing asset hashes and both HTML boundaries match.
- Chromium exercised an existing owned acceptance film through a simulated legacy checkpoint, advanced to 100%, read real video metadata, restored after refresh and checked 360/390/768 layouts. No page errors or generation POSTs occurred. See `browser-report.json` and the screenshot.
- Python compilation, generated entry JavaScript syntax and `git diff --check` passed.

The local website was restarted with the updated backend after confirming no active authoring, render or assistant runs. Private identity files, videos, credentials and scientific/private databases remain outside version control. No paid AI or speech request was made for this fix.
