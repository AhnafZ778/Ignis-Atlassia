# AI use and numerical review

## AI assistance

OpenAI Codex/ChatGPT has been used to help draft and edit code, documentation, and interface text. AI assistance did not create or alter the NASA FIRMS detection rows, the raw coordinates, or NASA product counts. The application derives its calendar values from imported CSV rows using the versioned Python pipeline; no trained AI model produces satellite values or fire forecasts in this project.

AI-generated text is not a source of incident truth. Historical incident descriptions and linked reports must be checked against their cited sources before submission.

## Optional scientific assistant

The `/assistant.html` workspace and contextual assistant can use a server-side OpenAI, Google or OpenRouter model to select scientific tools, discuss retrieved evidence, interpret explicitly selected figures, and request page navigation. Conversational inference requires owner-supplied credentials; the stored-data investigation buttons work without them. The OpenRouter adapter only permits verified free models and free fallbacks, blocks paid speech/plugins, and displays the returned model. Availability depends on provider capacity and account quotas.

The model references exact values in authoritative calculation results. The server resolves those references into numerical cards, units, method identifiers and source-release receipts. Free-form interpretation is labelled AI-assisted and is separate from checked values. AI annotations are interpretations, never independent measurements or human review signatures. Selected figures cannot supply burned-area, temperature, perimeter or spread measurements.

Temporary private notebooks retain findings, notes and annotations; users can export or delete them. Speech is labelled AI-generated narration, never an eyewitness account. No assistant tool imports additional datasets, edits observations or forecasts fire spread. See [the architecture plan](SCIENTIFIC_ASSISTANT_PLAN.md) and [configuration instructions](SCIENTIFIC_ASSISTANT_SETUP.md).

## Human review of numerical claims

No independent scientific review of the NASA counts or methods is documented in this repository as of 2026-09-29. Reviewer names: none recorded. The reproducibility scripts and tests check code consistency; they do not replace an independent review of source rows, product interpretation, or the scientific conclusions. Keep this gate open until a named reviewer records the date, files or hashes inspected, discrepancies, and conclusion.
