"""Exercise the exported two-region calendar without loading the globe."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from functools import partial

try:
    from playwright.sync_api import sync_playwright
except ModuleNotFoundError:
    sync_playwright = None

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
<small id="harm-frp-unit"></small>
<span id="harm-history-range"></span><div id="harm-history-grid"></div><p id="harm-history-note"></p>
<span id="harm-bridge-state"></span><p id="harm-bridge-method"></p><section><span id="harm-bridge-modis"></span><small id="harm-bridge-modis-note"></small><i id="harm-bridge-modis-bar"></i><span id="harm-bridge-viirs"></span><small id="harm-bridge-viirs-note"></small><i id="harm-bridge-viirs-bar"></i><span id="harm-bridge-result"></span><small id="harm-bridge-result-note"></small><i id="harm-bridge-result-bar"></i><span id="harm-bridge-days"></span><i id="harm-mismatch-modis-bar"></i><i id="harm-mismatch-both-bar"></i><i id="harm-mismatch-viirs-bar"></i><i id="harm-mismatch-gap-bar"></i><span id="harm-mismatch-modis"></span><span id="harm-mismatch-both"></span><span id="harm-mismatch-viirs"></span><span id="harm-mismatch-gap"></span><p id="harm-bridge-note"></p><strong id="harm-frp-value"></strong><p id="harm-frp-note"></p><small id="harm-corroboration-state"></small><p id="harm-corroboration-note"></p></section>
<section id="harm-share-card" hidden><span id="harm-share-card-case"></span><strong id="harm-share-card-title"></strong><small id="harm-share-card-subtitle"></small><dd id="harm-share-card-value"></dd><dd id="harm-share-card-state"></dd><dd id="harm-share-card-quality"></dd><dd id="harm-share-card-inputs"></dd><dd id="harm-share-card-limit"></dd><a id="harm-share-card-url"></a></section>
</main><script>history.replaceState(null,'','?year=2024&month=7')</script><script src="/workspace-context.js"></script><script src="/workspace.js"></script><script src="/harmonized.js"></script></body></html>"""


class CalendarFixtureHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/__calendar_fixture__":
            body = FIXTURE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def matched_month_expectations(calendar: dict, month_key: str) -> dict:
    """Independently sum both sensors only where the bundled UTC records are paired."""
    availability = {item["date"]: item.get("sources", {})
                    for item in calendar.get("availability", [])
                    if item["date"].startswith(month_key)}
    days = [item for item in calendar.get("days", [])
            if item["date"].startswith(month_key)]
    paired = []
    for day in days:
        sources = availability.get(day["date"], {})
        if day.get("sensor_bridge", {}).get("status") != "complete":
            continue
        if day.get("viirs_status") == "documented_processing_gap":
            continue
        if not all(sources.get(source, {}).get("export_complete")
                   and sources[source].get("availability", {}).get("status")
                   != "documented_processing_gap"
                   for source in ("MODIS_SP", "VIIRS_SNPP_SP")):
            continue
        paired.append(day["date"])
    totals = {}
    for source in ("MODIS_SP", "VIIRS_SNPP_SP"):
        records = [availability[day][source] for day in paired]
        totals[source] = {
            "rows": sum(int(item.get("raw_pixel_count") or 0) for item in records),
            "cells": sum(int(item.get("detected_cell_days") or 0) for item in records),
        }
    frp_pairs = []
    for day in paired:
        sources = availability[day]
        values = (sources["MODIS_SP"].get("frp_sum_mw"),
                  sources["VIIRS_SNPP_SP"].get("frp_sum_mw"))
        if all(value is not None for value in values):
            frp_pairs.append(tuple(float(value) for value in values))
    return {
        "paired_days": len(paired),
        "day_count": len(days),
        "totals": totals,
        "frp_days": len(frp_pairs),
        "frp_means": ([sum(pair[index] for pair in frp_pairs) / len(frp_pairs)
                       for index in (0, 1)] if frp_pairs else [None, None]),
    }


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
    calendars = {}
    july_verdicts = {}
    for region in ("norcal", "punjab-haryana"):
        for year in range(start_year, end_year + 1):
            if not (site / "data/v2/calendar" / region / f"{year}.json").is_file():
                raise SystemExit(f"calendar is missing {region}/{year}")
        calendar = json.loads((site / "data/v2/calendar" / region / "2024.json")
                              .read_text(encoding="utf-8"))
        calendars[region] = calendar
        july_verdicts[region] = next(
            item["verdict"] for item in calendar["months"] if item["month"] == "2024-07")
    for item in manifest["files"]:
        path = site / item["path"]
        if not path.is_file():
            raise SystemExit(f"manifest file is missing: {item['path']}")
        content = path.read_bytes()
        if len(content) != item["bytes"] or hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise SystemExit(f"manifest checksum or size mismatch: {item['path']}")
    norcal_2006 = json.loads((site / "data/v2/calendar/norcal/2006.json")
                             .read_text(encoding="utf-8"))
    norcal_july = next(item for item in calendars["norcal"]["months"]
                       if item["month"] == "2024-07")
    norcal_august = next(item for item in calendars["norcal"]["months"]
                         if item["month"] == "2024-08")
    norcal_paired = matched_month_expectations(calendars["norcal"], "2024-07")

    handler = partial(CalendarFixtureHandler, directory=str(site))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    api_requests: list[str] = []
    try:
        if sync_playwright is None:
            verifier = ROOT / "scripts" / "verify_static_calendar.mjs"
            result = subprocess.run(
                ["node", str(verifier), "--base", base, "--site", str(site)],
                capture_output=True, text=True, check=False)
            if result.stdout:
                print(result.stdout, end="")
            if result.returncode:
                raise SystemExit(result.stderr or
                                 f"dependency-free browser verifier exited {result.returncode}")
            return
        with sync_playwright() as playwright:
            system_browser = next((shutil.which(name) for name in
                                   ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
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
            page.wait_for_function("document.querySelector('#harm-bridge-days').textContent.includes('days')")
            norcal = page.evaluate("""() => ({
              verdict: document.querySelector('#harm-verdict').textContent,
              status: document.querySelector('#harm-status').textContent,
              build: document.querySelector('#harm-build-meta').textContent,
              days: document.querySelectorAll('#harm-day-grid [data-date]').length,
              value: document.querySelector('#harm-value').textContent,
              valueNote: document.querySelector('#harm-value-note').textContent,
              years: document.querySelector('#harm-years').textContent,
              percentile: document.querySelector('#harm-percentile').textContent,
              download: document.querySelector('#harm-download').getAttribute('href'),
              bridge: document.querySelector('#harm-bridge-state').textContent,
              modis: document.querySelector('#harm-bridge-modis').textContent,
              modisNote: document.querySelector('#harm-bridge-modis-note').textContent,
              viirs: document.querySelector('#harm-bridge-viirs').textContent,
              viirsNote: document.querySelector('#harm-bridge-viirs-note').textContent,
              resultNote: document.querySelector('#harm-bridge-result-note').textContent,
              frp: document.querySelector('#harm-frp-value').textContent,
              frpUnit: document.querySelector('#harm-frp-unit').textContent,
              frpNote: document.querySelector('#harm-frp-note').textContent,
              corroboration: document.querySelector('#harm-corroboration-state').textContent,
              shareQuality: document.querySelector('#harm-share-card-quality').textContent,
              shareLimit: document.querySelector('#harm-share-card-limit').textContent,
              shareUrl: document.querySelector('#harm-share-card-url').href
            })""")
            if ("Northern California" not in norcal["verdict"] or norcal["download"] != "#"
                    or not norcal["bridge"] or not norcal["frp"] or not norcal["build"]
                    or "SHA-256" not in norcal["build"] or norcal["corroboration"] != "MCD64A1 LAGGED"
                    or norcal["verdict"] != july_verdicts["norcal"]):
                raise SystemExit(f"Northern California static calendar did not render correctly: {norcal}")
            expected_composition = (
                f"{norcal_july['observed_days']} VIIRS-observed days · "
                f"{norcal_july['estimated_days']} MODIS-estimated days · "
                f"{norcal_july['unknown_days']} unknown UTC dates")
            if (expected_composition not in norcal["valueNote"]
                    or "prediction intervals" not in norcal["valueNote"].lower()
                    or norcal["years"] != str(norcal_july["n_years"])
                    or norcal["percentile"] != "Percentile withheld"
                    or "Observed + estimated days" not in norcal["resultNote"]):
                raise SystemExit(f"Mixed-month composition, uncertainty, or insufficient-history state is wrong: {norcal}")

            if (norcal_paired["paired_days"] <= 0
                    or f"{norcal_paired['paired_days']} matched UTC dates" not in norcal["modisNote"]
                    or f"{norcal_paired['paired_days']} matched UTC dates" not in norcal["viirsNote"]
                    or not norcal["bridge"].startswith(
                        f"{norcal_paired['paired_days']}/{norcal_paired['day_count']} paired UTC dates")):
                raise SystemExit(f"Sensor summaries do not expose the same matched-date set: {norcal}; {norcal_paired}")
            displayed_cells = page.evaluate("""() => ["#harm-bridge-modis", "#harm-bridge-viirs"]
              .map(selector => Number(document.querySelector(selector).textContent.replace(/[^\\d.-]/g, "")))""")
            expected_cells = [norcal_paired["totals"][source]["cells"]
                              for source in ("MODIS_SP", "VIIRS_SNPP_SP")]
            if displayed_cells != expected_cells:
                raise SystemExit(f"Sensor cell totals include unmatched dates or differ from the bundle: {displayed_cells}; expected {expected_cells}")
            for note, source in ((norcal["modisNote"], "MODIS_SP"),
                                 (norcal["viirsNote"], "VIIRS_SNPP_SP")):
                if f"{norcal_paired['totals'][source]['rows']:,} eligible rows" not in note:
                    raise SystemExit(f"Matched-date row count is wrong for {source}: {note!r}")
            if ("mean MW" not in norcal["frpUnit"]
                    or f"{norcal_paired['frp_days']} matched dates" not in norcal["frpNote"]):
                raise SystemExit(f"FRP aggregate or units are unclear: {norcal['frpUnit']!r}; {norcal['frpNote']!r}")
            displayed_frp = [float(value.replace(",", "")) for value in norcal["frp"].split(" / ")]
            if any(abs(actual - expected) > 0.051
                   for actual, expected in zip(displayed_frp, norcal_paired["frp_means"])):
                raise SystemExit(f"FRP values differ from mean daily source sums on the matched dates: {displayed_frp}; expected {norcal_paired['frp_means']}")

            source_order = page.evaluate("""() => {
              const verdict = document.querySelector('#harm-verdict');
              const links = document.querySelector('#harm-official-links');
              return verdict.parentElement.firstElementChild === verdict
                && verdict.nextElementSibling === links;
            }""")
            if not source_order:
                raise SystemExit("verdict is not first in the calendar panel with official sources directly beneath it")
            norcal_sources = page.locator("#harm-official-links a").evaluate_all(
                "nodes => nodes.map(node => node.href)")
            if norcal_sources != ["https://www.fire.ca.gov/incidents", "https://inciweb.wildfire.gov/"]:
                raise SystemExit(f"Northern California official links are incorrect or missing: {norcal_sources}")
            if "not a fire perimeter" not in page.locator("#harm-official-links").inner_text().lower():
                raise SystemExit("Northern California verdict is missing the fire-perimeter limitation")

            gap_label = page.locator('#harm-day-grid [data-date="2024-07-25"]').get_attribute("aria-label") or ""
            if "gap" not in gap_label.lower() or "scaled" not in gap_label.lower():
                raise SystemExit(f"documented gap day was not visibly labelled: {gap_label!r}")

            page.locator('#harm-day-grid [data-date="2024-07-25"]').click()
            page.wait_for_function("document.querySelector('#harm-records details') !== null")
            drawer_note = page.locator("#harm-day-summary").inner_text().lower()
            if "prediction interval is withheld" not in drawer_note or "not prediction uncertainty" not in drawer_note:
                raise SystemExit(f"Documented-gap drawer is missing the estimate uncertainty limit: {drawer_note!r}")
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
                    or "region=norcal" not in share_url or "month=7" not in share_url):
                raise SystemExit(f"static evidence share card did not render its trace fields: {share_title!r}; {share_inputs!r}; {share_quality!r}; {share_limit!r}; {share_url!r}")
            if "EASE-Grid" not in bridge_method:
                raise SystemExit(f"static bridge method label is missing its grid transform: {bridge_method!r}")

            page.select_option("#harm-month", "8")
            page.wait_for_function("document.querySelector('#harm-bridge-result-note').textContent.includes('Observed VIIRS')")
            august_note = page.locator("#harm-value-note").inner_text()
            expected_august = (
                f"{norcal_august['observed_days']} VIIRS-observed days · "
                f"{norcal_august['estimated_days']} MODIS-estimated days · "
                f"{norcal_august['unknown_days']} unknown UTC dates")
            if (norcal_august["estimate_type"] != "observed"
                    or august_note != expected_august
                    or page.locator("#harm-years").inner_text() != str(norcal_august["n_years"])
                    or page.locator("#harm-percentile").inner_text() != "Percentile withheld"):
                raise SystemExit(f"Fully observed month or insufficient-history display is wrong: {august_note!r}; {norcal_august}")
            page.wait_for_function("document.querySelector('#harm-corroboration-note').textContent.includes('906')")
            if page.locator("#harm-corroboration-state").inner_text() != "MCD64A1 LAGGED":
                raise SystemExit("August 2024 did not render its separate dated MCD64A1 check")
            page.select_option("#harm-month", "9")
            page.wait_for_function("document.querySelector('#harm-corroboration-state').textContent === 'ACTIVE FIRE ONLY'")
            page.select_option("#harm-month", "7")
            page.select_option("#harm-year", "2006")
            page.wait_for_function("document.querySelector('#harm-value').textContent === 'Unknown'")
            unknown_2006_july = next(item for item in norcal_2006["months"]
                                     if item["month"] == "2006-07")
            unknown_note = page.locator("#harm-value-note").inner_text()
            if (unknown_2006_july["value"] is not None
                    or str(unknown_2006_july["unknown_days"]) + " unknown UTC dates" not in unknown_note
                    or "not included in the month total" not in unknown_note
                    or "total unknown, not zero" not in unknown_note):
                raise SystemExit(f"Partial historical detections were not kept separate from the unknown month total: {unknown_note!r}; {unknown_2006_july}")

            page.select_option("#harm-region", "punjab-haryana")
            page.wait_for_function("document.querySelector('#harm-verdict').textContent.includes('Punjab')")
            page.wait_for_function("document.querySelectorAll('#harm-day-grid [data-date]').length === 31")
            punjab = page.locator("#harm-verdict").inner_text()
            if punjab != july_verdicts["punjab-haryana"]:
                raise SystemExit(f"Punjab–Haryana visible verdict differs from its calendar data: {punjab!r}")
            punjab_sources = page.locator("#harm-official-links").inner_text()
            punjab_urls = page.locator("#harm-official-links a").evaluate_all(
                "nodes => nodes.map(node => node.href)")
            if (punjab_urls != ["https://firms.modaps.eosdis.nasa.gov/"]
                    or "No verified official local source listed." not in punjab_sources
                    or "do not identify crop-burning cause" not in punjab_sources):
                raise SystemExit(f"Punjab–Haryana source or cause limitation is incorrect: {punjab_sources!r}; {punjab_urls!r}")
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
