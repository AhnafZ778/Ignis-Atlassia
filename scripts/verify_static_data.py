"""Verify the static Data Sources ledger without server endpoints."""

from __future__ import annotations

import argparse
import shutil
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    args = parser.parse_args()
    site = args.site.resolve()
    required = [site / "data.html", site / "data.js", site / "data/v2/regions.json", site / "data/v2/manifest.json"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("static data page is incomplete: " + ", ".join(missing))

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(site)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    requests: list[str] = []
    errors: list[str] = []
    try:
        with sync_playwright() as playwright:
            executable = next((shutil.which(name) for name in
                               ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")
                               if shutil.which(name)), None)
            browser = playwright.chromium.launch(headless=True, executable_path=executable)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("request", lambda request: requests.append(request.url) if "/api/" in request.url else None)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}/data.html", wait_until="domcontentloaded")
            page.wait_for_function("document.querySelector('#archive-coverage-status').textContent.includes('complete region-product-month')")
            if page.locator("#pilot-list .pilot-card").count() != 2:
                raise SystemExit("static data page did not render both study-area cards")
            if page.locator("#source-list .source-card").count() < 2:
                raise SystemExit("static data page did not render both NASA source cards")
            if page.locator("#import-submit").is_enabled() or page.locator("#sync-pilots").is_enabled():
                raise SystemExit("static data page exposed a server-only import or sync control")
            status = page.locator("#archive-coverage-status").inner_text()
            badge = page.locator("#credential-state").inner_text()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    if requests or errors:
        raise SystemExit(f"static data page requests/errors: {requests}; {errors}")
    print(f"Static data page verified: {status}; badge={badge}; no API calls or browser errors.")


if __name__ == "__main__":
    main()
