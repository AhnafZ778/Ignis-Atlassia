"""Verify the static landing shell without loading or interacting with the globe."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=ROOT / "site",
                        help="static export directory to inspect")
    args = parser.parse_args()
    app = (args.site / "app.js").resolve()
    css = (args.site / "landing.css").read_text(encoding="utf-8")
    if not app.is_file() or ".static-calendar-note" not in css:
        raise SystemExit("static app assets are missing or out of sync")

    errors: list[str] = []
    with sync_playwright() as playwright:
        system_browser = next((shutil.which(name) for name in
                               ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")
                               if shutil.which(name)), None)
        browser = playwright.chromium.launch(headless=True, executable_path=system_browser)
        page = browser.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.set_content("""<!doctype html><html><head>
          <meta name="fireatlas-static-data" content="./data/v2/">
          </head><body>
          <div id="earth-frame-host" aria-label="Existing Earth"></div>
          <input id="globe-markers" type="checkbox" aria-label="Existing satellite toggle">
          <button id="start-calendar-tour">Preparing data tour…</button>
          <section id="harmonized-calendar">Bundled calendar</section>
          <section id="study-workspace">Server-backed map workspace</section>
          </body></html>""")
        page.evaluate("""() => {
          window.__staticShellFetches = [];
          window.fetch = (...args) => {
            window.__staticShellFetches.push(String(args[0]));
            return Promise.reject(new Error('static shell must not call an API'));
          };
        }""")
        page.add_script_tag(path=str(app))
        page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))")
        result = page.evaluate("""() => ({
          workspaceHidden: document.querySelector('#study-workspace').hidden,
          tourHidden: document.querySelector('#start-calendar-tour').hidden,
          note: document.querySelector('.static-calendar-note')?.textContent.trim(),
          calendarPresent: Boolean(document.querySelector('#harmonized-calendar')),
          earthPresent: Boolean(document.querySelector('#earth-frame-host')),
          satelliteToggleChecked: document.querySelector('#globe-markers').checked,
          requests: window.__staticShellFetches
        })""")
        browser.close()

    expected = {
        "workspaceHidden": True,
        "tourHidden": True,
        "calendarPresent": True,
        "earthPresent": True,
        "satelliteToggleChecked": False,
        "requests": [],
    }
    for key, value in expected.items():
        if result.get(key) != value:
            raise SystemExit(f"static shell {key}: expected {value!r}, got {result.get(key)!r}")
    if not result.get("note") or errors:
        raise SystemExit(f"static shell note or browser errors: note={result.get('note')!r}; errors={errors}")
    print("Static shell verified: calendar retained; server-only workspace omitted; no API fetch; Earth host and toggle state unchanged.")


if __name__ == "__main__":
    main()
