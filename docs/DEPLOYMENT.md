# Deploy the submission demo on free hosting

The application runs entirely on **Render**: pages, whiteboard, AI API, saved
boards and downloads share one origin. **Vercel is a small entry page** that
opens the matching Render URL, including its path, query and fragment. The
browser address changes to Render. This keeps private session cookies and saves
on the same host. Vercel is optional; the Render URL works directly.

## 1. Render first

1. Put the intended source changes in your Git repository, including the files
   below. Do not add `.env*`, local databases, `data/` or `NASA_data/`.
2. Create a **Blueprint** from the repository root using `render.yaml`. It uses
   the root `Dockerfile`; there is no separate build/start command to configure.
3. Keep the selected **Free** instance. The Blueprint has `plan: free`, no
   persistent disk, no paid database and no additional service. Runtime stores
   use `/tmp/fireatlas` and are temporary. Local saves, uploads, sessions and
   generated download links can be lost on a restart, redeploy or idle spin-down.
   Export investigation packages to your computer before leaving the demo.
   No hosting has been created by these files.
   For a strict $0 hosting budget, keep the Render account without a payment
   method and do not enable paid add-ons. Render can charge usage overages when
   a payment method is present; without one, limits can suspend the service.
4. Enter `AIAND_API_KEY` privately when prompted. The Blueprint selects the
   existing AI& provider. Never put this key in Vercel or frontend code. A local
   Ollama endpoint will not be available on the hosted machine. Model access,
   credits, pricing checks and existing budget limits still apply. Free hosting
   does not provide free AI inference; use your existing provider key/credits.
   Set a spending limit in that provider account: local usage counters are also
   temporary and reset when the server store is lost.
5. Optionally add `FIRMS_MAP_KEY` privately for new FIRMS data retrieval. The
   retained comparison starter does not need a new data download. Other public
   research services can fail or rate limit independently.
6. Deploy. Render supplies `RENDER_EXTERNAL_URL`; startup uses it as the exact
   public origin for both Studio and assistant writes. If using a custom domain,
   set `FIREATLAS_PUBLIC_ORIGIN` to its exact HTTPS origin and use that host
   consistently. Run one instance/worker with this temporary SQLite setup.
7. Open `/healthz` on the Render URL. HTTP 200 checks Studio and native-export
   helpers; it does **not** test a paid AI request or certify scientific answers.

The Docker build installs locked frontend dependencies, builds authored Studio
source in isolation and installs the pinned assistant runtime. Local generated
assets, private stores and environment files are excluded. First startup loads
the bundled, hash-checked authentic NOAA HMS/FIRMS Northern California sample;
each fresh instance can rebuild that starter. It does not copy your local boards or complete
historical archive. The separate Rajshahi starter retains its frozen receipts.

## 2. Vercel entry page

1. Import the same repository with the **repository root** as Root Directory.
   Use Vercel's free **Hobby** plan; no paid Vercel feature is required.
   Use Framework Preset **Other**. `vercel.json` specifies the commands and
   output directory; do not select `studio-app` or upload the large `site/` tree.
2. Set the public build variable `FIREATLAS_RENDER_URL` to the actual Render
   HTTPS origin, for example `https://your-service.onrender.com`. Use no path,
   query or fragment. Set it for each Vercel environment you intend to use.
3. Deploy. An unset/invalid target fails the build clearly. Only the entry page
   is built; `.vercelignore` limits CLI uploads. Git-based integration still
   needs the source committed to the selected branch.
4. Test both `/` and `/studio-excalidraw.html` through the Vercel URL. Both must
   open Render. API calls, downloads and sessions then stay on Render.

Render is the interactive frontend host in this arrangement. This configuration
does not independently host the whiteboard on Vercel or use a cross-site API.

## 3. Dependable demo and sharing

1. Download `/demo/rajshahi-peak-days.fireatlas.zip` from Render. In Investigation,
   use **More → Restore investigation** and choose that package. Each restore
   creates a new board owned by the current browser session.
2. Inspect the three-year comparison, common heat scale, editable annotations
   and retained evidence. The public starter excludes private AI conversation
   and board discussion. Its provenance file is in `deployment/demo/`.
3. Make an edit, wait for Saved, reload, and confirm it remains. Close/reopen the
   browser using the same profile to retain the private session. Clearing cookies
   loses that browser's access; retain the account recovery information privately.
4. Ask one short question with the hosted AI key configured; inspect the cited
   evidence. Provider failure must leave existing figures and exports usable.
5. Export the **native investigation package** from More. Download it locally,
   then restore it in a separate browser profile. Check figures, source receipts
   and any included conversation. This is the dependable handoff to another
   person; a private `?board=...` URL alone does not grant them access.
6. Keep the downloaded package on your computer. After a Render restart or
   redeploy, restore it into a new board; old board URLs, server-side downloads
   and recovery tokens may no longer work. The bundled comparison starter is
   always included in the image and can be downloaded again after a cold start.

Free Render services sleep after 15 minutes without inbound traffic. Waking
the service plus rebuilding its authentic starter can take several minutes
on the free CPU allowance. Open the demo in advance of presenting. There is
no automatic durable cloud save in this free configuration. Package download
and restore are the recovery and sharing workflow; do not promise permanent
shared board URLs. A browser's local drawing draft is not a complete evidence
backup. Stay within the hosts' included usage limits; no upgrade is configured.

Whole-board native exports can include AI conversation and board discussion;
review the contents before sharing. Packages retain frozen evidence without the
original scientific database. Rerunning calculations can require additional
source data, credentials and compatible methods. Integrity hashes do not prove
source authenticity or scientific approval.

The public gateway accepts at most **3,000,000 bytes per request**; the starter
fits. Large CSV/PDF/native imports can exceed that limit. Native board export
includes the saved whiteboard. Browser drawing export remains available through
its own UI. Server PNG/PDF, film rendering, speech, local raster tools and the
large frozen analytical evidence release are not installed by this image.
The small public Park platform publication and replay case are included for the
welcome example and its source links.
Some historical analytical pages therefore lack their separate data namespaces.
New NASA catalog work and fully qualified causal/scientific narration remain
outside today's submission scope.

This is a small submission service. Existing abuse controls admit at most 30
new Studio identities and 30 new assistant sessions per hour through the gateway;
visitors share that allowance. Existing owner sessions remain usable. Keep the
presentation browser profile and downloaded package available; this setup is
not qualified for an unrestricted high-traffic public launch.
Free Render also has a small memory allowance. Keep the demo to the retained
comparison and small imports/exports; large investigations or concurrent heavy
AI/export work can exceed it. Native export does not imply unlimited capacity.

## If Render says it cannot find Dockerfile

Render builds a Git commit, not your local working folder. Commit `3ce3224`
predates the deployment files. A local Dockerfile does not fix a deployment
until its source branch is committed and pushed.

The prepared deployment branch is **`codex/free-render-demo`**. In the existing
Render service, set **Settings → Build & Deploy → Branch** to that branch,
leave Root Directory blank, and use Dockerfile Path `./Dockerfile`. Keep the
instance on **Free**, then choose **Manual Deploy → Deploy latest commit**.
Confirm the deploy log checks out the new commit rather than `3ce3224`.

For Vercel, use the same deployment branch in the project's Git settings so
the root `vercel.json` and entry builder are available there too. This branch
contains selected source/public demo files; your original working branch and
private stores remain separate. It does not update `main` automatically.

## Delivery files and local verification

Keep `Dockerfile`, `.dockerignore`, `render.yaml`, `vercel.json`, `.vercelignore`,
`fireatlas/hosted.py`, `scripts/build_vercel.mjs`, the public starter under
`deployment/demo/`, and their source dependencies in Git. Generated Vercel output,
deployment test results, secrets and runtime stores stay ignored. Existing
intentional public static evidence remains versionable. Nothing was committed
or pushed automatically.

```bash
docker build -t fireatlas-submission:local .
docker run --rm --memory=512m --cpus=0.1 -p 127.0.0.1:8173:10000 \
  -e FIREATLAS_PUBLIC_ORIGIN=http://127.0.0.1:8173 \
  fireatlas-submission:local
# A separately configured server-side provider key is needed for real AI calls.
.venv-assistant/bin/python -m unittest tests.test_hosted -q
FIREATLAS_RENDER_URL=https://your-service.onrender.com node scripts/build_vercel.mjs
```

Hosted integration remains a separate gate: send the final Render and Vercel
URLs after deploying so the actual submitted route can be checked.

References: [Render Blueprint specification](https://render.com/docs/blueprint-spec),
[Render free services and filesystem limits](https://render.com/docs/free),
[Vercel configuration](https://vercel.com/docs/project-configuration/vercel-json).
