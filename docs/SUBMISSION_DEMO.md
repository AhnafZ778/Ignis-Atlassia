# Submission-day priorities

The deadline is today. Ship a convincing, recoverable scientific whiteboard demo;
defer feature expansion. The full scientific-agent objective remains longer-term.

## Three required outcomes, in order

1. **The hosted whiteboard works.** Open it, create/open a board, save an edit,
   reload, ask the configured hosted model and download an export. Keep the board
   and API on the same origin. For the shortest initial deployment, the Render
   Python service serves the frontend and API together; Vercel's small entry
   page opens the matching Render URL. Follow [deployment steps](DEPLOYMENT.md).
   A later reverse proxy is
   optional, not required for today's first working demo.
2. **One strong scientific workflow works.** Start from the authentic saved
   Rajshahi 2023–2025 peak-day comparison with shared heat scales, editable
   annotations, Python-derived counts/deltas and separate weather context. Use
   its retained evidence instead of downloading three years during the pitch.
   The figures must remain usable if model wording is unavailable. AI hypotheses
   are proposals; do not present them as established causal findings.
3. **The investigation is shareable and recoverable.** Export the native package,
   restore it into a new board and inspect its evidence and conversation. Keep a
   local copy of the checked comparison package and a short screen recording as
   backups. A recording is not evidence that the hosted app works.

## Demo sequence

- Open the saved three-year comparison and explain the common scale and exact
  counts. Move an annotation to show the board is editable.
- Ask a short question about the selected evidence. Inspect the cited values and
  source scope; if narration is unavailable, keep the source figures visible.
- Find a relevant paper and inspect original passages if available. An abstract
  is labeled as an abstract; paper wording is separate from local measurements.
- Export the investigation, reload the board and show that it is saved.

Keep Solo investigation as the default. The three-specialist research team is an
optional extra with its existing price/token limits; the core demo must not depend
on every specialist completing.

## Hosting checks before submitting the URL

- Configure the public origin to the actual whiteboard origin and keep provider
  credentials only on the server. Do not use a localhost-only model on the host.
- Use free hosting only, per the user's budget. `render.yaml` selects Free with
  no disk; Vercel uses Hobby. SQLite/assets are temporary and can disappear on
  restart, redeploy or idle spin-down. Download the native package before leaving
  and restore it after a cold start; do not promise permanent board URLs.
- The public gateway's aggregate request ceiling is3MB. The checked comparison
  package is below that ceiling; do not promise large CSV/PDF imports today.
- Test the submitted URL in a fresh browser session: open, create, save, reload,
  one short AI question, source inspection, export and restore. Then keep the
  service ready before presenting and retain a downloaded backup.

References: [Render free services](https://render.com/docs/free),
[Render persistent disks](https://render.com/docs/disks),
[Vercel rewrites](https://vercel.com/docs/routing/rewrites).

## Deferred for after submission

Broader NASA observation acquisition, exhaustive variable discovery, more visual
redesign, new connectors, general model/scientific qualification and a larger
swarm. Existing code for NASA catalog expansion is work in progress and has no
completed independent review. Do not expand it while stabilizing this demo.

## Current evidence and limits

Authentic comparison figures and native portability were exercised locally.
The gateway regression exercises real local HTTP save/retry, owner/origin
isolation, export/download/restore and DELETE bodies. Hosted checks are pending;
the user confirmed that neither service is deployed yet. Scientific narration
is unqualified, runtime zoom/motion gates remain open, and the unrelated existing
landing-preservation failure remains. No deployment has been performed.
