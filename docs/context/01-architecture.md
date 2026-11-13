# 01 — Runtime, architecture, APIs, and storage

[Context entry point](../../CODEBASE_CONTEXT.md) · reviewed 2026-10-27

## Executables and composition

| Entry | Role |
| --- | --- |
| scripts/run_website.sh | Normal launcher; chooses default core or existing .venv-assistant runtime and private environment file |
| python -m fireatlas.web | stdlib ThreadingHTTPServer; default host 127.0.0.1, port 8000, DB data/fireatlas.sqlite3 |
| fireatlas / python -m fireatlas.cli | init, ingest, calendar, research, fetch-month, firms-status, harvest-hms, sync-pilots |
| python -m fireatlas.assistant.gateway | Optional Starlette/Uvicorn proxy plus AG-UI run event stream |
| python -m fireatlas.hosted | Render entry: temporary free-tier store, authentic bootstrap, exact public origin, single ASGI worker |
| python -m fireatlas.assistant.mcp_server | Private stdio tools and optional MCP Apps UI resource |
| studio-app/ | React/TypeScript authoring island, built into the Python static directory |
| studio-render/ | Server-prepared film rendering helpers |
| studio-mcp-app/ | Compact owned-board/story viewer for compatible MCP hosts |

This is not a FastAPI backend or a single React application. Scientific and analytical routes are implemented directly in fireatlas/web.py. Python core has few external dependencies; assistant/model, native raster, browser, speech, and video dependencies are optional.

handler_factory(database) constructs AssistantService, optional StudioService, StudioAssets, PilotSync, and scientific caches. The Handler delegates Studio and assistant paths before science/static routes. Studio initialization failure yields an unavailable response for that feature while scientific pages continue. Asset serving uses explicit allowlists, not unrestricted filesystem browsing.

main() may seed an empty **default** DB from bundled verified HMS/FIRMS samples unless --no-showcase is used. A custom DB path is not automatically seeded. Serving a DB with synthetic batches is refused. Server shutdown closes assistant and Studio services.

## Stores and identities

| Store/default path | Authority and lifetime | Main contents |
| --- | --- | --- |
| data/fireatlas.sqlite3 | Authentic scientific input | batches, observations, excluded_rows, export_windows, source_exports |
| data/validity_masks.sqlite3 | Derived native-mask evidence | granules, native pixels; associated human reviews remain separate |
| data/assistant/workspace.sqlite3 | Expiring assistant sessions | sessions, runs, artifacts, events, cost reservations, throttles |
| data/studio/studio.sqlite3 | Durable owned authoring | principals, documents/revisions/transactions, snapshots, science_results, stories, workflows, renders, rooms, commands, exports |
| data/assistant/mcp-workspace.sqlite3 and data/assistant/mcp-studio/ | Private MCP-process workspace | Separate desktop session and Studio identity |
| site/data/ | Published frozen artifacts | Read-only JSON/gzip/ZIP inputs and evidence manifests |

Paths are defaults, not a requirement that local stores exist. Constructors accept alternate roots, especially for tests. data/ and NASA_data/ are ignored and must not be treated as clone contents.

Assistant uses the fireatlas_workspace cookie. Studio uses fireatlas_studio and hashed persistent session tokens. Browser instance/context revisions coordinate a selected view; they do not grant document ownership. Public share URLs serialize study/display context, not private notebook access.

## Scientific HTTP surface

Paths are relative to the application root. Inspect Handler.do_GET/do_POST for exact arguments and response shapes.

| Method/path | Implementation or purpose |
| --- | --- |
| GET /api/meta | Available sources, bounds, limits and default UI metadata |
| GET /api/archive-overview | Historic archive hero metadata |
| GET /api/calendar | Raw union calendar; year/series/bbox |
| GET /api/comparability | Complete-month fixed-region comparison; region=norcal or punjab-haryana; read-only DB transaction, bounded cache |
| GET /api/comparability/case | Native diagnostics derived from original Park/Grove evidence ZIP; case=park-2024 or grove-2025 |
| GET /api/v2/regions | Fixed calibrated regions and source state |
| GET /api/v2/calendar | Harmonized regional calendar; region/year/month/history |
| GET /api/v2/study | Exact harmonized ZIP; optional expected_result_sha256, stale result returns 409 |
| GET /api/v2/monthly-provenance | Exact immutable monthly source receipt by cohort ID, optionally pinned to a release; absent or invalid evidence remains unavailable |
| GET /api/harmonization | Descriptive selected-month audit |
| GET /api/briefing | Evidence-first calendar briefing |
| GET /api/research; POST /api/research | Exploratory overlap/candidates; POST accepts config and optional mask |
| GET /api/replay, /api/replay/catalog | Named Park/Camp/Grove replay and catalog |
| GET /api/observations, /api/map, /api/export | Source rows, bounded map representations, CSV output |
| GET /api/study | Generic raw-union evidence ZIP |
| GET /api/validity, /check, /export, /review-template | Historical native evidence/recount/download; append suffix to /api/validity |
| GET /api/native-masks and /api/native-masks/{filename} | Local inventory and allowlisted authentic native files |
| GET /api/globe, /api/globe/detail | Landing-specific bounded source/date display |
| GET /api/data/status | Ingestion and pilot status |
| POST /api/data/import, /api/data/sync | Local-only mutation, strict loopback host + Origin + content-type checks |

General science errors become JSON 400 for bad selections and 500 for DB errors. Output sanitization removes personal local-file URI details. CSV import is capped at 25 MB; research JSON at 3 MB.

## Consistency and concurrency

The scientific connection wrapper closes after context exit; use its transaction() for an inner transaction that must not close the outer connection. Source records and completeness ledgers are distinct.

Calendar/replay/globe caches track database and WAL stamps. Calendar caches additionally account for notices/corroboration. Regional export uses a nonblocking build lock and a read transaction. The assistant's Science.call additionally checks its release identity before and after bounded calculation. Do not cache results solely by visible year or selected case.

## Gateway is not an equivalent Studio deployment

assistant/gateway.py allows science GETs, assistant POST/DELETE operations and Studio POST/PATCH/DELETE operations. Studio retains exact-origin, cookie-principal, ownership and revision checks; scientific archive ingestion and human-review writes remain blocked. The proxy forwards idempotency keys, Range headers and mutation bodies, retaining its aggregate 3 MB request ceiling. Large Studio uploads can exceed this gateway ceiling even when the direct Studio route permits them. It internally proxies to a loopback threaded server. Its special /api/assistant/runs/{run_id}/stream route adapts stored events into a stream. Adding a local route does not automatically make it writeable through this gateway.

Public origin settings are FIREATLAS_ASSISTANT_ORIGIN and FIREATLAS_STUDIO_ORIGIN. Inspect current boundary code before exposing a service; no deployment was performed during the context study.

The submission Docker entry `hosted.py` sets both origins from
`FIREATLAS_PUBLIC_ORIGIN` or Render's `RENDER_EXTERNAL_URL`, refuses invalid
origins and synthetic science stores, and preserves all science/assistant/Studio
stores under `FIREATLAS_DATA_DIR` (default `/tmp/fireatlas`, ephemeral on free
Render). Native package download/restore provides recovery after server loss;
cookies/recovery tokens alone cannot restore a deleted store. A marker and
temporary database make the first bundled bootstrap retryable: publish the
database only after both imports complete. Existing completed stores are
not reseeded. `/healthz` checks Studio/native export helpers, not provider access.
The explicit public download `/demo/rajshahi-peak-days.fireatlas.zip` serves a
conversation-free starter; restore creates a private owned board. Vercel only
redirects the browser to Render, preserving deep links. See `docs/DEPLOYMENT.md`.

## Change and verify

For route changes, inspect web.py plus assistant/http.py or studio/http.py as appropriate; update corresponding browser clients. Tests: test_web.py, test_studio_http.py, test_assistant.py, test_studio_mcp.py. The generated index locates nested methods but is not a complete HTTP schema.

The qualification exact-byte API also serves `/api/v2/daily-neighbors` for a 16-hex cohort identity, optionally bound to an immutable release. It uses the same publication manifest reader and static gzip bytes as the Research similar-day panel; it does not fit a model or approve daily estimates.

The local asset allowlist includes `clean-workflow.css`; the static publication copies the same stylesheet.


The local `/api/mask-map` endpoint uses `fireatlas/mask_map.py` to read the processed native mask SQLite store in read-only mode for an explicitly requested UTC day and geographic bounds. It returns original sample centers, class/source counts and a bounded deterministic per-class sample; it does not infer continuous coverage. No private mask database is published in the static site.
