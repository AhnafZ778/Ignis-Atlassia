# Run the scientific assistant

The real page is **http://127.0.0.1:8000/assistant.html**. A compact assistant also appears on the existing pages. Stored-data investigations work without an AI key. Conversational AI and speech are separate optional capabilities.

## Recommended local startup

```bash
bash scripts/run_website.sh
```

This starts the existing website with `.venv-assistant` and the private `.env.assistant` when that configuration exists. Starting the base environment without that file leaves Ask JARVIS unavailable. The launcher does not download datasets, install packages, or print keys. Pass `--host`, `--port`, or `--db` after the script name as needed.

## 1. Existing local app

```bash
uv run python -m fireatlas.web --no-showcase
```

The page opens a real observation map automatically. Select Park, Camp or Grove in the archive rail, or use **Region & dates** for a custom boundary. The default **Detection heatmap** smooths occupied 1 km observation cells with an approximately 1 km Gaussian kernel. **Show → Original detections** restores MODIS circles and VIIRS diamonds. Both preserve separate source readings. **Compare side by side** synchronizes the two map views. The UTC timeline shows actual per-source daily counts and labels incomplete exports.

Use **Earlier readings** to search authentic imported records inside the current boundary, from 2006 onward. Results are monthly detection windows, not confirmed incidents. Large windows open their peak UTC day to respect the replay record limit. **Evidence → Browse this day’s exact records** provides a keyboard-accessible alternative to clicking the map. Sample details include acquisition time, native confidence, source-specific FRP, product version and file hashes.

**Place note** creates a geographic annotation. **Select area → Finish area** retrieves original detections whose centers fall inside a drawn polygon. A selected cell or record can be annotated with its actual geometry and acquisition date; annotations are redrawn only in their matching study and date. The **Sources** tab traces imported records, calculation evidence, selected samples and annotations.

**Refine question** is a local rule-based editor: it shows an editable suggestion with scope, selected evidence and scientific interpretation rules. It does not send an AI request or silently change studies. Conversation uses the configured tool-capable provider; map, archive and prompt tools do not consume inference quota. Figure attachments are schematics of the selected display metric; streamed terrain imagery is omitted and the caption states the limitation.

No new datasets are downloaded. Custom replay supports up to 31 UTC days and 10,000 imported rows. Research/candidate windows stay within one UTC month; use the explicit **UTC month → Compare sensors in this month** action. Its evidence records the intersection with the study interval; the daily map keeps the full study window. Static exports load bundled named-case maps and clearly require the local service for custom analysis, private annotations and AI.

## Replay controls and alignment

- **Selected UTC day** displays that day only. **Accumulate through selected day** retains cells previously recorded in this study and weights heat by their distinct observed dates, without using future records.
- Heat normalization stays fixed for the study and is shared between MODIS and VIIRS panes. It does not automatically brighten quiet days. Kernel width stays fixed in geographic distance when zooming.
- **Outline newly observed cells** marks cells first recorded in this study and source. It does not establish ignition, continuous burning, or a fire perimeter.
- Playback offers three speeds, pause/resume, previous/next and First day. Every calendar date is visited; empty/unknown dates are not skipped. An investigation, figure attachment, manual frame change or hidden tab pauses playback.
- Daily readouts retain both sensors and their distinct cell union. The map source filter and cumulative progression summary are labeled separately. CSV export follows the selected source and daily/cumulative interval; selecting a cell limits export to its actual source-frame records.
- Questions about the displayed day receive the exact selected frame and evidence paths, including when it falls outside the compact preview. Checked answer cards identify sensor, UTC date and unit. Answers stay visible in Ask; opening a calculation explicitly opens Evidence.
- Static mode uses the same display aggregation with bundled named studies. Custom queries, AI and private annotations still require the local service. Missing results never become zero-fire claims.

## 2. Optional AI dependencies

The isolated environment avoids changing the base application.

```bash
uv venv --python 3.12 .venv-assistant
uv pip install --python .venv-assistant/bin/python -r requirements/assistant.lock -e .
```

Create `.env.assistant` locally (ignored by Git), using the template below. Supply one conversational provider key and current verified token prices. Do not put any key in website JavaScript or commit it.

```bash
# Select openai or google.
FIREATLAS_AI_PROVIDER=openai
OPENAI_API_KEY=YOUR_PRIVATE_KEY
# For Google instead: GOOGLE_API_KEY=YOUR_PRIVATE_KEY
# Model defaults: gpt-6-luna / gemini-3.8-flash. An available tool/vision model can be overridden.
# FIREATLAS_AI_MODEL=YOUR_MODEL
FIREATLAS_AI_INPUT_USD_PER_MILLION=VERIFIED_INPUT_PRICE
FIREATLAS_AI_OUTPUT_USD_PER_MILLION=VERIFIED_OUTPUT_PRICE
PYDANTIC_AI_NO_BANNER=1
```

Obtain keys from [OpenAI project API keys](https://platform.openai.com/api-keys) or [Google AI Studio](https://aistudio.google.com/api-keys). Verify the selected model and current prices in [OpenAI pricing](https://openai.com/api/pricing/) or [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing). Enabling a key incurs provider costs; configured prices are mandatory for the application's reservation ledger.

The OpenAI adapter uses Responses with provider storage disabled. Gemini uses a supported low thinking level. Model capabilities were checked against the [GPT-6 Luna documentation](https://developers.openai.com/api/docs/models/gpt-6-luna) and [Gemini thinking documentation](https://ai.google.dev/gemini-api/docs/thinking). Questions, selected figures and relevant tool previews are sent to the configured provider; raw source archives are not uploaded wholesale. Provider processing and retention policies still apply.

```bash
uv run --python .venv-assistant/bin/python --no-project --env-file .env.assistant \
  python -m fireatlas.web --no-showcase
```

The app's executable global limit is $4.50/day within the requested $5/day envelope; it defaults to $0.25 per temporary session. Unknown billed usage is held, not automatically retried or assumed free. Set an independent provider project budget as well. A price/usage overrun pauses paid calls pending operator review. Stored-data buttons continue to work.

## AI&: efficient questions and deeper investigations

The current local installation selects AI&. Its key stays in ignored `.env.assistant`, with owner-only file permissions. Public website assets and capability responses contain no credentials.

```bash
FIREATLAS_AI_PROVIDER=aiand
AIAND_API_KEY=YOUR_PRIVATE_KEY
PYDANTIC_AI_NO_BANNER=1
```

Use the same isolated-environment startup command above. The question composer offers two modes; this choice does not change the scientific study:

| Mode | Text model | When a figure is attached |
| --- | --- | --- |
| Efficient (default) | GLM-5.3-Flash | DeepSeek-V4.1-Flash |
| Deep | DeepSeek-V4-Pro | DeepSeek-V4.1-Flash |

Efficient is the default for reading records, explaining sensor differences, annotating selected evidence, and interpreting figures. Deep adds reasoning for complex comparisons. These routes balance capability and cost; they are not a universal model ranking. The authenticated [AI& model catalog](https://docs.aiand.com/api/models/) is checked before inference and refreshed every five minutes. Tool support, image support when required, reasoning settings, and finite positive USD prices must all pass. Current per-million uncached input/output prices verified on 2026-10-02: GLM Flash $0.15/$0.50, DeepSeek Pro $1.00/$2.50, DeepSeek V4.1 Flash $0.30/$0.60. Cached input may cost less.

Routes can be overridden with `FIREATLAS_AIAND_MODEL`, `FIREATLAS_AIAND_VISION_MODEL`, `FIREATLAS_AIAND_DEEP_MODEL`, and `FIREATLAS_AIAND_DEEP_VISION_MODEL`. The default allowed price ceilings are $2 input / $5 output per million tokens, configurable using `FIREATLAS_AIAND_MAX_INPUT_PRICE` and `FIREATLAS_AIAND_MAX_OUTPUT_PRICE`. Unverified or unsupported routes fail before a paid inference request. A failed paid request is not automatically retried or switched to another paid model.

Per-call completion limits include reasoning tokens: 1,600 in Efficient (low reasoning for GLM; reasoning off for DeepSeek figures), 2,400 in Deep (high reasoning); each investigation is further bounded by eight requests, 20,000 text-only input tokens (30,000 with a figure), 6,000 output tokens and twelve tool calls. The existing $4.50 global daily limit and $0.25 temporary-session limit apply. Efficient figure requests use low-detail image input. Replay previews omit repeated geometry and request-file hashes; the full saved calculation and exact selected-record inspection retain those details. Map, archive, prompt refinement and explicit stored-data tasks remain independent of paid inference. The answer shows the actual returned model, mode and conservative cost estimate; private per-call receipts retain token usage. Estimates use uncached rates, not the provider's final invoice. Missing usage keeps the reservation held. Sending a question shares that question and compact relevant evidence with AI&; attaching a figure also shares that selected schematic.

Live checks on 2026-10-02: Efficient text and Deep text both retrieved the authoritative 3,125 detections / 1,599 joint cell-days for the Park July 24–31 study; Deep figure input also passed. The completed browser Efficient figure workflow retrieved 6,224 detections / 2,228 joint cell-days for the full named Park study in two calls, estimated at $0.003091 using uncached catalog prices. Desktop and 390 px mobile had no JavaScript errors or horizontal overflow. These are bounded integration checks, not a comprehensive model benchmark or a guarantee that every question will finish; invalid citations and exhausted limits still stop publication.

Scientific measurements still come from local calculation tools and checked evidence paths. Models cannot execute arbitrary code, invent coordinates for unknown regions, download data, or attest independent human validation. OpenRouter's free-only adapter remains available by changing the provider back to `openrouter`; no automatic billing fallback is enabled.

## 3. OpenRouter and speech

### OpenRouter with no paid inference

The OpenRouter adapter is **free-only**. Store one key in the ignored `.env.assistant` file:

```bash
FIREATLAS_AI_PROVIDER=openrouter
OPENROUTER_API_KEY=YOUR_PRIVATE_KEY
FIREATLAS_OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
FIREATLAS_OPENROUTER_VISION_MODEL=google/gemma-4-31b-it:free
PYDANTIC_AI_NO_BANNER=1
```

Start using the same `uv run --python .venv-assistant/bin/python --no-project --env-file .env.assistant python -m fireatlas.web --no-showcase` command. No token-price configuration is needed for this adapter. It validates every configured route against the current public model catalog: the model must have a `:free` entry, zero pricing, tool calling, and image input when a figure is attached. Verification expires after five minutes and fails closed when the catalog cannot be checked. Provider requests also enforce zero input/output price caps and disable paid plugins. Paid models and automatic routers are rejected. Available free fallback routes are explicitly listed in `fireatlas/assistant/free_models.py`.

The answer identifies the model actually returned by OpenRouter. Each provider call records its usage/cost receipt. Paid speech is blocked even if an OpenAI key exists. Free-model capacity and account quotas still apply; a multi-step question can consume several inference requests. Scientific action buttons work without consuming this quota. Extra keys are not rotated to bypass account limits.

Live verification on 2026-10-02: Nemotron Ultra and Gemma passed tool-call checks with reported cost zero. A complete Park-data question used Ultra followed by its free Super fallback and returned the authoritative 6,224 eligible detections and 2,228 joint cell-days; both calls reported zero cost. Qwen's free endpoint returned a capacity limit and remains a fallback candidate. The configured account reported a 50-request daily allowance at setup; OpenRouter's quota is authoritative, not this document. The focused regression suite now contains 34 passing tests, including the free-only transport, image routing and paid-speech block.

See [free variants](https://openrouter.ai/docs/guides/routing/model-variants/free), [provider controls](https://openrouter.ai/docs/guides/routing/provider-selection), and [account limits](https://openrouter.ai/docs/api_reference/limits). Availability and quality vary; these are tested candidates, not a claim of universally best performance.

### Paid speech when using a direct provider

Speech uses the OpenAI key, including when chat uses Google. The UI records valid mono WAV; no ffprobe installation is needed. Verify conservative maximum request costs for the configured models before enabling these variables:

```bash
FIREATLAS_STT_MAX_REQUEST_USD=YOUR_VERIFIED_CEILING_FOR_20_SECONDS
FIREATLAS_TTS_MAX_REQUEST_USD=YOUR_VERIFIED_CEILING_FOR_800_CHARACTERS
# Optional model overrides:
# FIREATLAS_STT_MODEL=gpt-transcribe
# FIREATLAS_TTS_MODEL=gpt-4o-mini-tts
```

The ledger debits these ceilings conservatively rather than guessing the provider's actual speech charge. Maximum microphone time is 180 seconds per workspace/day; narration is limited to 4,000 characters/day. The microphone needs localhost or HTTPS and browser permission. Transcript review comes before sending; narration is AI-generated speech of a saved, checked answer.

## 4. Public same-origin gateway

Serve the scientific site and assistant from one origin, or reverse-proxy both under the frontend origin. A static GitHub Pages deployment cannot run private analysis or hold provider keys.

```bash
uv run --python .venv-assistant/bin/python --no-project --env-file .env.assistant \
  python -m fireatlas.assistant.gateway \
  --db data/fireatlas.sqlite3 --host 0.0.0.0 --port 8000 \
  --origin https://YOUR_PUBLIC_HOST
```

Use one gateway worker with a persistent local disk for `data/assistant/`. Mount the supplied science database and context assets; do not run ingestion through this public endpoint. The gateway supports scientific reads and private assistant updates; it rejects existing data import/sync and human review writes. TLS is supplied by the host/reverse proxy. Deploying this service or spending on hosting is a separate action; this implementation does not publish it.

The optional SSE route is `/api/assistant/runs/RESULT_RUN_ID/stream`, authenticated with the same private cookie. It emits AG-UI run/step events without exposing chain-of-thought. The included frontend polls durable run receipts on both server modes.

## 5. MCP

Trusted desktop clients can launch the stored-data MCP server over stdio:

```json
{
  "mcpServers": {
    "fireatlas": {
      "command": "/ABSOLUTE/PROJECT/.venv-assistant/bin/python",
      "args": ["-m", "fireatlas.assistant.mcp_server", "--db", "/ABSOLUTE/PROJECT/data/fireatlas.sqlite3"],
      "cwd": "/ABSOLUTE/PROJECT"
    }
  }
}
```

Tools: `describe_capabilities`, `investigate`, `get_evidence`. Each launched desktop process has a separate private workspace. There is no public unauthenticated MCP listener.

To let the website AI use an external **reference or geocoding** MCP, create an operator-controlled JSON file and set `FIREATLAS_MCP_CONFIG` to its absolute path:

```json
[
  {
    "id": "approved-geocoder",
    "url": "https://YOUR_APPROVED_MCP_HOST/mcp",
    "scope": "geocoding",
    "tools": ["YOUR_READ_ONLY_PLACE_SEARCH_TOOL"],
    "token_env": "YOUR_CONNECTOR_TOKEN_ENV_NAME"
  }
]
```

Only explicitly listed tools are exposed. The server URL is configured by the operator, never accepted from a visitor. The connector provider determines whether a key is needed. Reference/geocoding output remains untrusted external context and is not imported as wildfire measurements. The local source references and named-case catalog need no additional API key.

## 6. Notebook and submission release

Save notes or select a cell and **Pin to map selection**. **Export evidence JSON** includes all saved calculations, parameters, references and annotations. **Open report / save PDF** downloads a self-contained report; open it and use Print → Save as PDF.

To record a source-file SHA-256 release after closing ingestion and using a checkpointed database:

```bash
uv run python scripts/fingerprint_assistant_release.py --db data/fireatlas.sqlite3
```

This reads existing data and writes a metadata receipt; it does not download datasets, write the scientific database or make a second database copy. Restart the analysis service after creating the receipt. Later source/manifest changes invalidate the fingerprint. Without this step, results honestly identify a live source-ledger release instead of claiming a frozen submission snapshot.

## Verification

```bash
.venv-assistant/bin/python -m unittest tests.test_assistant tests.test_research tests.test_replay tests.test_static_export
```

The initial delivery passed 34 focused tests, including the actual SDKs against mocked OpenAI Responses and OpenRouter transports, tool-result claims, ownership, cancellation, budget reservations, free-only model/image routing, the HTTP gateway and static export. Browser checks exercised named and custom Replay handoffs, selected figures, notebook notes, source navigation and the 390 px layout. The private MCP server was exercised in process. The Park study returned 6,224 eligible unique detections and 2,228 joint cell-days using the existing calculation pipeline.

OpenRouter conversation was exercised with owner credentials and reported zero-cost tool calls and checked Park-data claims. A browser figure question encountered a free-provider capacity error; the interface recovered with no JavaScript errors and kept paid speech disabled. Direct OpenAI/Google conversational and speech calls remain unverified. Offline tests use the actual installed provider framework with a function model and temporary source fixtures; they do not contact a paid provider.

The map workspace rebuild was checked in the browser against the actual database: on 2024-07-30 in Park’s study box it returned 159 eligible MODIS detections and 558 VIIRS detections. Historical search across 2006–2026 found 218 monthly windows and 46,344 raw imported rows inside that box at verification time. A large August 2021 window opened its peak day, 2021-08-18, with 270 MODIS and 1,068 VIIRS eligible replay detections. These are different filtering levels, not interchangeable fire counts. Browser checks covered source filters, comparison-map resizing, polygon queries, annotation provenance, prompt refinement, named-study switching and bundled static fallback. Conversational tool inspection and AI annotations were tested using an SDK mock; the rebuild did not make a new live inference request.

## Geographic navigation and visual evidence guides

The assistant supports an explicit **Locate a place** search on each page. Saved fire studies resolve locally. Other names use [Nominatim search](https://nominatim.org/release-docs/latest/api/Search/), with a persistent 30-day cache and a global request interval above one second. Several matches are presented as choices; the model cannot select an ambiguous result for you. No additional key is required for the default service. Configure `FIREATLAS_GEOCODER_URL` and `FIREATLAS_GEOCODER_USER_AGENT` to use an operator-approved endpoint and application identity. Public deployments must follow the [service usage policy](https://operations.osmfoundation.org/policies/nominatim/). This sends the typed place name to the geography provider; no observation dataset is downloaded or imported. If the service is unavailable, saved studies and explicit coordinates still work.

Camera actions focus the existing Earth globe, standalone terrain globe, Atlas, candidate map, Replay, or assistant map. A geographic marker is a reference location, never a fire detection. Camera movement leaves the scientific area and dates unchanged. Source, heat metric, UTC day, map context, comparison and history controls use allowlisted settings; actions are acknowledged by the actual browser. A date outside the selected interval is rejected. A different observation study requires matching replay evidence.

Ask to show a source, calendar, calculation method, coverage denominator or native file. The assistant opens and outlines the corresponding real page section. **Save annotated evidence guide** captures that section’s displayed text and draws an OpenCV callout. It is explicitly labeled a text evidence guide, not a screenshot or image-derived fire analysis. An attached map schematic has a registered observation-field region which can also be outlined. OpenCV does not extract temperature, spread, perimeters or measurements from these pixels.

The three published prompts have prepared, checked workflows: selected-sample inspection and annotation, historical archive-window search, and daily source availability. If model output fails validation or reaches its bounded tool allowance, these tasks return the already checked values and source paths, labeled **Checked … workflow**, instead of an unchecked narrative. Unknown, incomplete export and complete export with no imported records remain separate. Missingness shows all study dates, with dated product notices filtered to the study interval. Historical windows are retrieval shortcuts, not confirmed incidents; window cards open the monthly bundle or its peak UTC day when the month is too large.

Provider failures before a response, exhausted monetary allowances, unavailable geocoding and unsupported arbitrary questions can still stop an investigation. The bounded scientific task buttons remain available independently of model inference.

### Latest verification

The current implementation passed 50 focused Python tests and the browser map calculation checks. Live browser checks exercised all three published prompts against Grove, Park and Camp (nine investigations), actual selected-cell annotations, all study dates in the availability table, and historical windows opening their peak UTC day. Additional checks exercised ambiguous Dhaka lookup, actual 2D and 3D camera movement, the existing globe and satellite, cross-page source navigation, OpenCV evidence-guide downloads, bundled static observations, and 390 px layouts. Bounded live model checks consumed about $0.035 in total; checked-workflow fallbacks remained visibly distinguished from AI wording.

Research pages load a selected study independently of the optional full-archive year inventory. Narrow UTC intervals remain intact in both the scientific request and assistant context, even when the inventory times out.

## Expanded conversation and visual explanations

Select **Expand chat ↗** on the globe or any scientific page to open the main-screen assistant. The same conversation, draft and study remain active when returning to the page. On phones, switch between **Conversation** and **Visual explanation**.

Use **Daily sensor graph**, **Availability chart**, or **Overlap comparison** to calculate and plot existing archive data without a model request. Ask the AI to show a graph or diagram to open a checked visual automatically. Each visual identifies its study interval, calculation units, source values and receipt. Select a bar to inspect its exact value, expand the accessible table, or select **Save SVG**. **Method diagram** explains the calculation flow; overlap results additionally show source-only and shared cell-days. Detection records, daily occupied cells and study-wide cell-days are deliberately different units.

Visuals use the full saved calculation, never model-invented measurements or executable plotting code. If model wording fails scientific validation after the bounded retries, an explicitly labeled checked explanation can still display retrieved values. Provider outages remain visible; stored-data tasks and the last checked calculation remain usable independently of AI wording.

The Earth camera now fits geographic bounds using the current viewport. Zoom during an ongoing location move continues toward that location instead of cloning the previous camera position. The existing globe and satellite remain in place.

This upgrade passed 41 focused Python tests plus JavaScript evidence-unit checks. Browser checks verified conversation restoration, source-linked charts, SVG export, real overlap diagrams, 390 px layouts, region fitting, concurrent focus/zoom and the existing globe controls. A live AI visual request exercised validated rendering and the checked explanation fallback; another attempt encountered a provider error and was reported as unavailable.
