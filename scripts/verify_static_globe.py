"""Verify the exported landing-globe filters and detail drawer without its API."""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import tempfile
import threading
from collections import Counter
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    parser.add_argument("--prefix", default="/fireatlas/",
                        help="project subpath at which to serve the static site")
    args = parser.parse_args()
    site = args.site.resolve()
    bundle_path = site / "data/v2/globe/recent.json.gz"
    if not bundle_path.is_file():
        raise SystemExit(f"static globe bundle is missing: {bundle_path}")
    bundle = json.loads(gzip.decompress(bundle_path.read_bytes()))
    if bundle.get("schema") != "fireatlas-globe-static-v1":
        raise SystemExit("static globe bundle schema is invalid")
    source_totals: Counter[str] = Counter()
    daily_totals: Counter[tuple[str, str]] = Counter()
    for row in bundle.get("aggregates", []):
        source_totals[row["source_id"]] += row["count"]
        daily_totals[(row["source_id"], row["date"])] += row["count"]
    source_id = max(source_totals, key=source_totals.get, default=None)
    if not source_id:
        raise SystemExit("static globe snapshot contains no aggregate data")
    day = max((value for (source, value), count in daily_totals.items() if source == source_id),
              key=lambda value: daily_totals[(source_id, value)])
    expected_window_total = source_totals[source_id]
    expected_day_total = daily_totals[(source_id, day)]

    with tempfile.TemporaryDirectory(prefix="fireatlas-static-globe-") as temporary:
        host_root = Path(temporary)
        prefix = "/" + args.prefix.strip("/") + "/"
        (host_root / prefix.strip("/")).symlink_to(site, target_is_directory=True)
        server = ThreadingHTTPServer(("127.0.0.1", 0),
                                     partial(SimpleHTTPRequestHandler, directory=str(host_root)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        requests: list[str] = []
        api_requests: list[str] = []
        http_errors: list[str] = []
        errors: list[str] = []
        try:
            with sync_playwright() as playwright:
                executable = next((shutil.which(name) for name in
                                   ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
                                   if shutil.which(name)), None)
                browser = playwright.chromium.launch(headless=True, executable_path=executable)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.on("request", lambda request: requests.append(request.url))
                page.on("request", lambda request: api_requests.append(request.url)
                        if "/api/" in request.url and not request.url.endswith("/api/assistant/capabilities") else None)
                page.on("response", lambda response: http_errors.append(
                    f"{response.status} {response.url}") if response.status >= 400 and not response.url.endswith("/api/assistant/capabilities") else None)
                page.on("pageerror", lambda error: errors.append(str(error)))
                base = f"http://127.0.0.1:{server.server_port}{prefix}"
                page.goto(f"{base}?lite=1", wait_until="domcontentloaded")
                page.wait_for_function("document.querySelector('#globe-cell-count').textContent.includes('° cells')",
                                       timeout=90000)
                page.locator("#earth-details-open").click()
                page.wait_for_function("document.querySelector('#earth-details-dialog').open")
                if int(page.locator("#globe-total").inner_text().replace(",", "")) < expected_window_total:
                    raise SystemExit("static globe did not render the selected source's full eight-day count")
                page.locator("#globe-source").select_option(source_id)
                page.wait_for_function("document.querySelector('#globe-status').textContent.includes('Ready')",
                                       timeout=30000)
                window_total = int(page.locator("#globe-total").inner_text().replace(",", ""))
                if window_total != expected_window_total:
                    raise SystemExit(f"static source filter count {window_total} != {expected_window_total}")

                page.locator("#globe-date").select_option(day)
                page.wait_for_function("document.querySelector('#globe-status').textContent.includes('Ready')",
                                       timeout=30000)
                day_total = int(page.locator("#globe-total").inner_text().replace(",", ""))
                if day_total != expected_day_total:
                    raise SystemExit(f"static date filter count {day_total} != {expected_day_total}")

                location = page.locator("#globe-location option").nth(1).get_attribute("value")
                if not location:
                    raise SystemExit("static globe did not populate the evidence location selector")
                page.locator("#globe-location").select_option(location)
                page.wait_for_function("!document.querySelector('#globe-selection').hidden && "
                                       "!document.querySelector('#globe-selection').textContent.includes('Loading source evidence')")
                if page.locator("#globe-selection ol li").count() == 0:
                    raise SystemExit("static evidence drawer did not show original source records")
                page.set_viewport_size({"width": 390, "height": 844})
                if page.locator(".globe-console").evaluate("el => el.getBoundingClientRect().width") > 390:
                    raise SystemExit("static globe console overflows the mobile viewport")
                bundle_requests = [url for url in requests if "data/v2/globe/recent.json.gz" in url]
                browser.close()
        finally:
            server.shutdown()
            server.server_close()

    if not bundle_requests:
        raise SystemExit("static globe did not load its bundled data under the project prefix")
    if api_requests or errors or http_errors:
        raise SystemExit(f"static globe API requests/HTTP/browser errors: {api_requests}; {http_errors}; {errors}")
    print(f"Static globe verified at {prefix}: {source_id} window={window_total:,}, {day}={day_total:,}; "
          "evidence records rendered, mobile console fits, no API calls or HTTP/browser errors.")


if __name__ == "__main__":
    main()
