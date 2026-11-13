# 11 — Maintaining context and choosing a change path

[Context entry point](../../CODEBASE_CONTEXT.md) · reviewed 2026-10-27

## Progressive reading for an outside LLM

1. Read CODEBASE_CONTEXT.md for product meaning, architecture, invariants and snapshot limitations.
2. Read only the relevant numbered segment guide(s).
3. Locate actual symbols with SOURCE_INDEX.md or source-manifest.json; then read the implementation and nearby tests.
4. Check Git status and current capabilities/configuration where relevant. Do not assume private data, generated assets or external services exist.
5. Implement the requested change, verify the affected behavior, and update the context in the same change.

Avoid loading all historical docs, the full generated symbol index and every source file for a narrow task. The segment pages explain relationships; the index supplies exact files, line locations, imports, hashes and Python environment key names.

## What to update

| Change | Curated context to review |
| --- | --- |
| Entrypoints, runtime, routes, stores or deployment boundary | 01, 10 and root map |
| CSV/source formats, normalization, identity, completeness | 02; downstream 03/04/06 |
| Metrics, scientific filters, calibration or baselines | 03, 04; affected UI/assistant claims |
| Native evidence/review/bundle verification | 04 and affected delivery checks |
| Analytical pages, selection URLs, tabs/maps, static mode | 05, 06, 10 |
| Assistant operations, providers, ownership or claims | 06; affected 01/07 |
| Studio schema/cards/revisions, workflows, commands, room roles, board export | 07; paired 08/09 |
| React state, interactions, API types or SDK build | 08; paired backend contract |
| Stories, media, captions, narration, renderer recovery | 09; corresponding frontend/backend notes |
| Static exporters, scripts, CI, setup or test commands | 10 |
| New subsystem, guide structure or changed maintenance tooling | Root guide, this page, AGENTS.md, generator scope |

State what source changed, why it changes behavior, how it is verified, and any unresolved limitations. Prefer repository-relative paths and symbols in curated prose; reserve line numbers for the generated index. Keep measured results with dates and commands. Remove superseded snapshot-specific caveats after actual verification.

context.md and .harness/ already contain harness-managed orientation records. Do not overwrite them with this index. The durable repository-owned entry point is CODEBASE_CONTEXT.md, with discovery/maintenance instructions in AGENTS.md and README.md.

## Generate and check

```bash
python3 scripts/update_codebase_context.py
python3 scripts/update_codebase_context.py --check
```

The generator requires Python 3.10+ and Git, uses the repository path derived from its own file, and runs from any working directory. It imports no application modules, runs no science, reads no credential files, writes no private databases, and does not start servers.

Inputs come from Git's tracked + nonignored untracked inventory, filtered to source/config/test roots and selected root references. It hashes existing selected files, parses Python with AST (including class methods), lexically scans JS/TS exports/imports, and records HTML external scripts. It skips generated Studio/MCP assets, vendor fonts/imagery, samples, private data/env files, build outputs and symlinks.

Outputs:
- SOURCE_INDEX.md: grouped, clickable source/symbol navigation.
- source-manifest.json: complete source hashes, byte/line counts, symbols, import names, Python environment **key names** and base commit.

--check writes nothing and exits 1 if either generated file differs from the current source inventory/base commit. New/deleted/changed selected files therefore stale the inventory. Regenerate after a commit if the recorded base commit changes. A source index refresh does not automatically rewrite or validate the meaning of the segment pages.

Changes to excluded sample data, historical reports, private input files, generated assets, and the curated guide text are **not** certified by inventory freshness. Review their owners/manifests/tests explicitly. If adding a new source root or file type, update the generator's scope rather than assuming it discovers all files automatically.

## Common change paths

| Request | Trace before editing |
| --- | --- |
| Add a scientific field | core/aggregate computation → method/unit contract → receipt fact → snapshot/figure → browser/story/export → verifier |
| Add a scientific operation | Scientific function → Science dispatch/registry → METHODS/fact/guided claims → model tool/output allowlists → HTTP/MCP/frontend → tests |
| Fix a wrong displayed total | Confirm method/scope/source state → direct authoritative result → receipt → frozen snapshot → prepared chart → UI; do not just patch displayed text |
| Fix stale results after navigation | Context URL/revision → view registration → request identity → async guard/cancellation → state acceptance |
| Add a Studio card field | graph validation/state → store transaction/inverse → service/API → TypeScript type/editor → snapshots/portability/story compatibility |
| Change card links/workflows | Python and TypeScript graph/port schemas → shared vectors → revision/cache semantics → editor and runner |
| Fix a failed video/export | Capability/admission → immutable source revision → persisted job phase → saved provider receipt/clip/audio → worker/output validation → publication gate |
| Change an analytical page | Authored HTML/controller/CSS → lifecycle + URL context → optional refreshed site derivative → subpath/static/landing checks |

Do not recalculate a frozen receipt to match an edited claim, change unknown to zero for rendering convenience, hide a conflict, repeat an uncertain paid call, or report a saved command as visible before acknowledgement.

## Evidence and handoff

When handing work to another LLM, provide the root guide, affected segment pages, current task, inspected revision/status, changed files and actual verification results. Explicitly separate source facts, historical acceptance, local mocks/fixtures, live integration evidence, independent review, and unresolved inference.

Keep secrets, raw personal paths, full observation dumps and huge embedded Earth assets out of context. Describe their interface/role and point to their controlled source instead.
