# Repository orientation for coding agents

Read [CODEBASE_CONTEXT.md](CODEBASE_CONTEXT.md) first, then the relevant guide under [docs/context/](docs/context/). Read current source and tests before editing; historical plans and acceptance reports are not current implementation proof.

## Working boundaries

- Check Git status and preserve unrelated work, including pre-existing generated-asset deletions.
- Keep scientific calculations in the authoritative Python modules. Preserve UTC, method/unit/scope/provenance contracts, source-specific FRP, and unknown/null states.
- Keep authentic observations separate from synthetic fixtures and private authoring stores.
- Preserve ownership, origin, idempotency, revision, cancellation, and optional-capability checks.
- Edit authored frontend source, then use the documented build/refresh path when generated output is part of the task. Studio builds replace their output directory; static exports can be large and change frozen evidence.
- Do not inspect or copy credentials into context, logs, browser responses, or exported artifacts.
- Use tests appropriate to the changed segment; distinguish mocked/local checks from actual provider, hosted integration, and human scientific review.

## Maintain LLM context

For changes to architecture, schemas, APIs, scientific meaning, state/lifecycle, configuration, build steps, or verification commands, update the corresponding curated segment guide in the same change. Update CODEBASE_CONTEXT.md if navigation or cross-cutting contracts change.

Regenerate the static index with:

```bash
python3 scripts/update_codebase_context.py
python3 scripts/update_codebase_context.py --check
```

The generator uses the Git inventory and source bytes without importing the app. Generated files are docs/context/SOURCE_INDEX.md and docs/context/source-manifest.json. Do not hand-edit them. A fresh inventory does not replace review of the prose.

Keep context.md and .harness/ as their existing harness-managed records; the repository-owned context starts at CODEBASE_CONTEXT.md.
