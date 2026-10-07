# GitHub Pages publication

The static demo's URL is https://AhnafZ778.github.io/NASA-Spaceapps/.
In repository **Settings → Pages**, select **GitHub Actions** as the publishing source.
GitHub must allow Pages for the repository's visibility and account plan.

Push to `main` to publish, or manually run **Publish the verified static FireAtlas bundle**
from the repository's Actions tab. The workflow first calls CI: it installs the locked
core, mask and assistant dependencies, runs Python tests, checks JavaScript syntax and
smoke-tests a clean clone. Publication requires that job to succeed.

The deployment job reconstructs the two large regional ZIPs from their checksummed
transport parts, then removes only those redundant transport copies. It records the
published commit in `deployment.json` and checks all frozen evidence file sizes and
SHA-256 hashes in the two release manifests. It rejects symlinks, private credential
or database files, and a publication larger than 1,000,000,000 bytes. The current
bundle is about 949 MB, leaving about 51 MB before that conservative limit.

Chromium then exercises the analytical pages under a project subpath, desktop and
mobile navigation, supported calendar selections, downloads, legacy redirects and
the static limitations. Both historical evidence cases must recount successfully,
and the landing globe is checked under `/NASA-Spaceapps/`. Only then does the workflow
upload `site/` and deploy it to the `github-pages` environment.

After deployment, open the homepage and its Explore, Investigate and Evidence links.
`deployment.json` identifies the commit actually served. Check the two Punjab–Haryana
ZIP download links as well: their assembled files are intentionally larger than
GitHub's individual repository file limit, while their transport parts remain below it.

## Updating the demo

Production UI sources live in `fireatlas/static/`. Refresh the published derivative
after UI changes without changing the frozen observation data:

```bash
uv run python scripts/refresh_static_assets.py --site site
python3 scripts/check_landing_preservation.py
uv run --with playwright python scripts/verify_workspaces.py --output /tmp/fireatlas-pages-checks
```

Commit the intended source and `site/` changes, then push to `main`. Browser checks
require a Playwright Chromium installation (`uv run --with playwright python -m
playwright install chromium`). The workflow installs it automatically on GitHub.

Run archive pruning only in a disposable publication copy: the transport parts in the
working repository need to stay tracked. The workflow's checkout is disposable.

## Static capabilities

The globe, bundled calendars, supplied investigation replays, historical evidence
recounts, existing downloads and portable readers work with the exported data.
JARVIS model conversations, saving private Studio boards, importing data, new custom
calculations and server-generated exports require the Python service. Publishing to
Pages does not make those services available. External map imagery and terrain still
require their providers and a network connection.
