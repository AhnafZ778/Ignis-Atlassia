"""Exercise the exported two-region calendar without loading the globe."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from functools import partial

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = """<!doctype html><html><head>
<meta name="fireatlas-static-data" content="./data/v2/">
<meta name="fireatlas-static-snapshot" content="verification">
</head><body><main id="harmonized-calendar">
<p id="harm-verdict"></p><nav id="harm-official-links"></nav><div id="harm-season-context" hidden></div>
<select id="harm-region"><option value="norcal">Northern California</option><option value="punjab-haryana">Punjab–Haryana</option></select>
<select id="harm-year"></select><select id="harm-month"></select><span id="harm-status"></span>
<p id="harm-build-meta"></p>
<button id="harm-share" type="button"></button><span id="harm-share-status"></span><a id="harm-download"></a><strong id="harm-value"></strong><small id="harm-value-note"></small>
<strong id="harm-years"></strong><small id="harm-percentile"></small><strong id="harm-season"></strong>
<small id="harm-season-note"></small><strong id="harm-model"></strong><small id="harm-model-note"></small>
<span id="harm-month-total"></span><h3 id="harm-days-title"></h3><div id="harm-day-grid"></div>
<div id="harm-source-status"></div><p id="harm-day-title"></p><p id="harm-day-summary"></p>
<div id="harm-day-source-status"></div><div id="harm-records"></div>
<span id="harm-history-range"></span><div id="harm-history-grid"></div><p id="harm-history-note"></p>
<span id="harm-bridge-state"></span><p id="harm-bridge-method"></p><section><span id="harm-bridge-modis"></span><small id="harm-bridge-modis-note"></small><i id="harm-bridge-modis-bar"></i><span id="harm-bridge-viirs"></span><small id="harm-bridge-viirs-note"></small><i id="harm-bridge-viirs-bar"></i><span id="harm-bridge-result"></span><small id="harm-bridge-result-note"></small><i id="harm-bridge-result-bar"></i><span id="harm-bridge-days"></span><i id="harm-mismatch-modis-bar"></i><i id="harm-mismatch-both-bar"></i><i id="harm-mismatch-viirs-bar"></i><i id="harm-mismatch-gap-bar"></i><span id="harm-mismatch-modis"></span><span id="harm-mismatch-both"></span><span id="harm-mismatch-viirs"></span><span id="harm-mismatch-gap"></span><p id="harm-bridge-note"></p><strong id="harm-frp-value"></strong><p id="harm-frp-note"></p><small id="harm-corroboration-state"></small><p id="harm-corroboration-note"></p></section>
<section id="harm-share-card" hidden><span id="harm-share-card-case"></span><strong id="harm-share-card-title"></strong><small id="harm-share-card-subtitle"></small><dd id="harm-share-card-value"></dd><dd id="harm-share-card-state"></dd><dd id="harm-share-card-quality"></dd><dd id="harm-share-card-inputs"></dd><dd id="harm-share-card-limit"></dd><a id="harm-share-card-url"></a></section>
</main><script src="/harmonized.js"></script></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    args = parser.parse_args()
    site = args.site.resolve()
    required = [site / "harmonized.js", site / "data/v2/regions.json",
                site / "data/v2/calendar/norcal/2024.json",
                site / "data/v2/calendar/punjab-haryana/2024.json",
                site / "data/v2/observations/norcal/2024.json.gz"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("static calendar bundle is incomplete: " + ", ".join(missing))
    manifest = json.loads((site / "data/v2/manifest.json").read_text(encoding="utf-8"))
    start_year, end_year = manifest["calendar_start_year"], manifest["calendar_end_year"]
    for region in ("norcal", "punjab-haryana"):
        for year in range(start_year, end_year + 1):
            if not (site / "data/v2/calendar" / region / f"{year}.json").is_file():
                raise SystemExit(f"calendar is missing {region}/{year}")
    for item in manifest["files"]:
        path = site / item["path"]
        if not path.is_file():
            raise SystemExit(f"manifest file is missing: {item['path']}")
        content = path.read_bytes()
        if len(content) != item["bytes"] or hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise SystemExit(f"manifest checksum or size mismatch: {item['path']}")

    handler = partial(SimpleHTTPRequestHandler, directory=str(site))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    api_requests: list[str] = []
    try:
        with sync_playwright() as playwright:
            system_browser = next((shutil.which(name) for name in
                                   ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")
                                   if shutil.which(name)), None)
            browser = playwright.chromium.launch(headless=True, executable_path=system_browser)
            page = browser.new_page()
            page.on("request", lambda request: api_requests.append(request.url)
                    if "/api/" in request.url else None)
            page.route("**/__calendar_fixture__", lambda route: route.fulfill(
                status=200, content_type="text/html; charset=utf-8", body=FIXTURE))
            page.goto(f"{base}/__calendar_fixture__", wait_until="domcontentloaded")
            page.wait_for_function("document.querySelector('#harm-status').textContent.includes('static snapshot')")
            page.wait_for_function("document.querySelectorAll('#harm-day-grid [data-date]').length === 31")
            page.wait_for_function("document.querySelector('#harm-bridge-state').textContent.includes('days')")
            norcal = page.evaluate("""() => ({
              verdict: document.querySelector('#harm-verdict').textContent,
              status: document.querySelector('#harm-status').textContent,
              build: document.querySelector('#harm-build-meta').textContent,
              days: document.querySelectorAll('#harm-day-grid [data-date]').length,
              download: document.querySelector('#harm-download').getAttribute('href'),
              bridge: document.querySelector('#harm-bridge-state').textContent,
              frp: document.querySelector('#harm-frp-value').textContent,
              corroboration: document.querySelector('#harm-corroboration-state').textContent,
              shareQuality: document.querySelector('#harm-share-card-quality').textContent,
              shareLimit: document.querySelector('#harm-share-card-limit').textContent,
              shareUrl: document.querySelector('#harm-share-card-url').href
            })""")
            if ("Northern California" not in norcal["verdict"] or not norcal["download"].startswith("http")
                    or not norcal["bridge"] or not norcal["frp"] or not norcal["build"]
                    or "SHA-256" not in norcal["build"] or norcal["corroboration"] != "MCD64A1 LAGGED"):
                raise SystemExit(f"Northern California static calendar did not render correctly: {norcal}")

            gap_label = page.locator('#harm-day-grid [data-date="2024-07-25"]').get_attribute("aria-label") or ""
            if "gap" not in gap_label.lower() or "scaled" not in gap_label.lower():
                raise SystemExit(f"documented gap day was not visibly labelled: {gap_label!r}")

            page.locator('#harm-day-grid [data-date="2024-07-25"]').click()
            page.wait_for_function("document.querySelector('#harm-records details') !== null")
            source_rows = page.locator("#harm-records details").count()
            if source_rows < 1:
                raise SystemExit("static source-row drilldown returned no records")

            page.locator("#harm-share").click()
            page.wait_for_function("!document.querySelector('#harm-share-card').hidden")
            share_title = page.locator("#harm-share-card-title").inner_text()
            share_inputs = page.locator("#harm-share-card-inputs").inner_text()
            bridge_method = page.locator("#harm-bridge-method").inner_text()
            share_quality = page.locator("#harm-share-card-quality").inner_text()
            share_limit = page.locator("#harm-share-card-limit").inner_text()
            share_url = page.locator("#harm-share-card-url").get_attribute("href") or ""
            if (not share_title or "2024" not in share_title or "SHA-256" not in share_inputs
                    or not share_quality or "MCD64A1 lagged context" not in share_limit
                    or "harm_region=norcal" not in share_url or "harm_month=7" not in share_url):
                raise SystemExit(f"static evidence share card did not render its trace fields: {share_title!r}; {share_inputs!r}; {share_quality!r}; {share_limit!r}; {share_url!r}")
            if "EASE-Grid" not in bridge_method:
                raise SystemExit(f"static bridge method label is missing its grid transform: {bridge_method!r}")

            page.select_option("#harm-month", "8")
            page.wait_for_function("document.querySelector('#harm-corroboration-note').textContent.includes('906')")
            if page.locator("#harm-corroboration-state").inner_text() != "MCD64A1 LAGGED":
                raise SystemExit("August 2024 did not render its separate dated MCD64A1 check")
            page.select_option("#harm-month", "9")
            page.wait_for_function("document.querySelector('#harm-corroboration-state').textContent === 'ACTIVE FIRE ONLY'")
            page.select_option("#harm-month", "7")

            page.select_option("#harm-region", "punjab-haryana")
            page.wait_for_function("document.querySelector('#harm-verdict').textContent.includes('Punjab')")
            page.wait_for_function("document.querySelectorAll('#harm-day-grid [data-date]').length === 31")
            punjab = page.locator("#harm-verdict").inner_text()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()

    if api_requests:
        raise SystemExit(f"static calendar issued API requests: {api_requests}")
    print(f"Static calendar verified: {2 * (end_year - start_year + 1)} region-year calendars "
          f"({start_year}–{end_year}), {len(manifest['files'])} checksummed data files; "
          f"July 25 NorCal opened {source_rows} bundled source rows; no API calls were made.")
    print(f"NorCal verdict: {norcal['verdict']}")
    print(f"Punjab–Haryana verdict: {punjab}")


if __name__ == "__main__":
    main()
