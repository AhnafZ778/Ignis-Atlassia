"""Verify the static Data & Method evidence story without a Python API."""

from __future__ import annotations

import argparse
import shutil
import threading
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    parser.add_argument("--case", choices=("park-2024", "grove-2025"), default="park-2024")
    args = parser.parse_args()
    site = args.site.resolve()
    required = [
        site / "method.html",
        site / "method.js",
        site / "validity.js",
        site / "data/v2/validity" / f"{args.case}.json",
        site / "data/v2/validity" / f"{args.case}-check.json",
        site / "data/v2/validity" / f"{args.case}.zip",
        site / "data/v2/validity" / f"{args.case}-review-template.json",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("static method bundle is incomplete: " + ", ".join(missing))
    evidence_zip_path = site / "data/v2/validity" / f"{args.case}.zip"
    with zipfile.ZipFile(evidence_zip_path) as evidence_zip:
        if "native_review_template.json" not in evidence_zip.namelist():
            raise SystemExit("static evidence ZIP is missing native_review_template.json")

    handler = partial(SimpleHTTPRequestHandler, directory=str(site))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    api_requests: list[str] = []
    evidence_check = "incident media loaded" if args.case == "park-2024" else "official context rendered without substitute media"
    try:
        with sync_playwright() as playwright:
            executable = next((shutil.which(name) for name in
                               ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")
                               if shutil.which(name)), None)
            browser = playwright.chromium.launch(headless=True, executable_path=executable)
            page = browser.new_page(viewport={"width": 1440, "height": 1200})
            page.on("request", lambda request: api_requests.append(request.url)
                    if "/api/" in request.url else None)
            page.goto(f"{base}/method.html?case={args.case}", wait_until="domcontentloaded")
            page.wait_for_function("document.querySelector('#validity-status') && "
                                   "!document.querySelector('#validity-status').textContent.includes('Checking')")
            page.wait_for_function("document.querySelectorAll('#validity-day-buttons button').length > 0")
            if page.locator("#validity-day-buttons button").count() == 0:
                raise SystemExit("historical case did not render any UTC day controls")
            page.locator("#validity-inspect summary").click()
            gate_text = page.locator("#validity-validation").inner_text().replace(",", "")
            expected_gates = {
                "park-2024": ("114 / 114", "3137 / 3137", "0 / 30", "0 / 1"),
                "grove-2025": ("20 / 20", "7 / 7", "0 / 30", "0 / 1"),
            }[args.case]
            for expected in expected_gates:
                if expected not in gate_text:
                    raise SystemExit(f"static native validation gate is stale for {args.case}: missing {expected!r}")
            if args.case == "park-2024":
                page.wait_for_function("document.querySelectorAll('#validity-evidence-media img').length > 0")
                images = page.locator("#validity-evidence-media img").evaluate_all(
                    "els => els.map(image => ({complete:image.complete, width:image.naturalWidth, height:image.naturalHeight}))")
                if any(not item["complete"] or item["width"] == 0 or item["height"] == 0 for item in images):
                    raise SystemExit(f"disclosed incident media did not load: {images}")
            else:
                page.wait_for_function("document.querySelector('#validity-incident-context').textContent.includes('GROVE FIRE')")
                if page.locator("#validity-evidence-media img").count():
                    raise SystemExit("Grove case substituted an unrelated incident image")
            page.locator("#run-recount").click()
            page.wait_for_function("document.querySelector('#proof-state').textContent.includes('Recomputed')")
            state = page.locator("#proof-state").inner_text()
            label = page.locator("#proof-label").inner_text()
            if state != "Recomputed from source rows" or label != "All plotted totals reproduce":
                raise SystemExit(f"static recount did not pass: {state}; {label}")
            download = page.locator("#method-download").get_attribute("href") or ""
            if f"data/v2/validity/{args.case}.zip" not in download:
                raise SystemExit(f"static evidence download did not resolve to the bundled ZIP: {download}")
            review_template = page.locator("#validity-review-template").get_attribute("href") or ""
            expected_template = f"data/v2/validity/{args.case}-review-template.json"
            if expected_template not in review_template:
                raise SystemExit(f"static review template did not resolve to the bundled JSON: {review_template}")
            template = page.evaluate("""async href => await (await fetch(href)).json()""", review_template)
            if template.get("schema") != "fireatlas-native-mask-review-v1" or template.get("case_id") != args.case:
                raise SystemExit("static review template has the wrong schema or case")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()

    if api_requests:
        raise SystemExit(f"static method issued API requests: {api_requests}")
    print(f"Static method verified: {args.case}; {evidence_check}; recount passed; no API calls.")


if __name__ == "__main__":
    main()
