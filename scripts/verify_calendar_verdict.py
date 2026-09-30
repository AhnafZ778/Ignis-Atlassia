"""Verify both live calendar verdicts and their immediately adjacent sources."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import sys
import threading
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_static_calendar import FIXTURE


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    args = parser.parse_args()
    site = args.site.resolve()
    if not (site / "harmonized.js").is_file():
        raise SystemExit(f"calendar client is missing from {site}")

    fixture = FIXTURE.replace(
        '<meta name="fireatlas-static-data" content="./data/v2/">\n'
        '<meta name="fireatlas-static-snapshot" content="verification">\n', "")
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(site)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    checks = []
    try:
        with sync_playwright() as playwright:
            browser_path = next((shutil.which(name) for name in
                                 ("chromium", "chromium-browser", "google-chrome",
                                  "google-chrome-stable") if shutil.which(name)), None)
            browser = playwright.chromium.launch(headless=True, executable_path=browser_path)
            page = browser.new_page()

            def proxy_api(route) -> None:
                request_url = urlsplit(route.request.url)
                upstream_url = args.api_base.rstrip("/") + request_url.path
                if request_url.query:
                    upstream_url += "?" + request_url.query
                response = route.fetch(url=upstream_url, timeout=120_000)
                route.fulfill(response=response)

            page.route("**/api/**", proxy_api)
            page.route("**/__calendar_fixture__", lambda route: route.fulfill(
                status=200, content_type="text/html; charset=utf-8", body=fixture))
            page.goto(f"{base}/__calendar_fixture__", wait_until="domcontentloaded")
            page.wait_for_function(
                "document.querySelector('#harm-status').textContent.includes('Imported FIRMS archive')",
                timeout=120_000)

            for region, label in (("norcal", "Northern California"),
                                  ("punjab-haryana", "Punjab")):
                page.locator("#harm-region").select_option(region)
                page.wait_for_function(
                    "label => document.querySelector('#harm-verdict').textContent.includes(label)",
                    arg=label, timeout=120_000)
                result = page.evaluate("""async region => {
                  const response = await fetch(`/api/v2/calendar?region=${region}&year=2024&month=7`);
                  if (!response.ok) throw new Error(`calendar API returned ${response.status}`);
                  const data = await response.json();
                  const monthVerdict = data.months.find(item => item.month === '2024-07').verdict;
                  const verdict = document.querySelector('#harm-verdict');
                  const links = document.querySelector('#harm-official-links');
                  return {actual: verdict.textContent, monthVerdict, apiVerdict: data.meta.verdict,
                    urls: [...links.querySelectorAll('a')].map(node => node.href),
                    sourceText: links.textContent,
                    ordered: verdict.parentElement.firstElementChild === verdict
                      && verdict.nextElementSibling === links};
                }""", region)
                if not (result["actual"] == result["monthVerdict"] == result["apiVerdict"]):
                    raise SystemExit(f"{region} visible verdict differs from its live API result: {result}")
                if not result["ordered"]:
                    raise SystemExit(f"{region} verdict is not first with sources directly beneath it")
                if region == "norcal":
                    if result["urls"] != ["https://www.fire.ca.gov/incidents",
                                           "https://inciweb.wildfire.gov/"]:
                        raise SystemExit(f"Northern California official links are missing: {result}")
                    if "not a fire perimeter" not in result["sourceText"].lower():
                        raise SystemExit(f"Northern California fire-perimeter limit is missing: {result}")
                else:
                    if result["urls"] != ["https://firms.modaps.eosdis.nasa.gov/"]:
                        raise SystemExit(f"Punjab–Haryana NASA FIRMS source is missing: {result}")
                    if "No verified official local source listed." not in result["sourceText"]:
                        raise SystemExit(f"Punjab–Haryana local-source fallback is missing: {result}")
                    if "do not identify crop-burning cause" not in result["sourceText"]:
                        raise SystemExit(f"Punjab–Haryana cause limitation is missing: {result}")
                checks.append(region)
            browser.close()
    finally:
        server.shutdown()
        server.server_close()

    print("Live verdict gate passed: " + ", ".join(checks)
          + "; exact API text, order, official links, and limitations verified.")


if __name__ == "__main__":
    main()
