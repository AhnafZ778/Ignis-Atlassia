"""Check that the Punjab–Haryana seasonal context stays dated and limited.

Run against the local static bundle:
  uv run --with playwright python scripts/verify_season_context.py --base http://127.0.0.1:8090
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


SOURCE = "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2060764&lang=2&reg=48"
EVIDENCE = Path("docs/winning-plan/evidence")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8090")
    parser.add_argument("--chrome", default="/usr/bin/google-chrome")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=args.chrome,
            headless=True,
            args=["--enable-unsafe-swiftshader", "--use-angle=swiftshader"],
        )
        page = await browser.new_page(viewport={"width": 1600, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        response = await page.goto(f"{base}/", wait_until="domcontentloaded")
        assert response and response.ok, "Landing page did not load"
        await page.wait_for_function(
            "document.querySelector('#harm-status')?.textContent.includes('Imported FIRMS archive')"
        )

        region = page.locator("#harm-region")
        year = page.locator("#harm-year")
        month = page.locator("#harm-month")
        context = page.locator("#harm-season-context")
        verdict = page.locator("#harm-verdict")

        await region.select_option("punjab-haryana")
        await page.wait_for_function(
            "document.querySelector('#harm-verdict')?.textContent.startsWith('Punjab–Haryana, July 2024:')"
        )
        assert await context.is_hidden(), "July must not receive the October–November context"

        await month.select_option("10")
        await page.wait_for_function(
            "!document.querySelector('#harm-season-context').hidden && "
            "document.querySelector('#harm-verdict').textContent.includes('October 2024')"
        )
        text = await context.inner_text()
        assert "1 Oct–30 Nov" in text and "do not confirm crop-residue fires" in text, text
        source = context.locator("a")
        assert await source.get_attribute("href") == SOURCE
        assert await source.get_attribute("target") == "_blank"
        assert await page.locator("#harm-value").inner_text() == "5,174"
        assert await page.locator("#harm-years").inner_text() == "1"
        assert "comparison not usable. Only 1 comparable years." in await verdict.inner_text()
        print("October 2024: 5,174 observed cell-days; one comparable year; official context and cause limitation visible. PASS")

        for width in (1440, 768, 390):
            await page.set_viewport_size({"width": width, "height": 900})
            section_top = await page.locator("#harmonized-calendar").evaluate(
                "element => element.getBoundingClientRect().top + window.scrollY"
            )
            await page.evaluate("top => window.scrollTo(0, top - 30)", section_top)
            await page.wait_for_timeout(150)
            dimensions = await context.evaluate(
                "element => ({width: element.clientWidth, scroll: element.scrollWidth, "
                "left: element.getBoundingClientRect().left, right: element.getBoundingClientRect().right})"
            )
            assert dimensions["scroll"] <= dimensions["width"] + 1, (width, dimensions)
            assert dimensions["left"] >= 0 and dimensions["right"] <= width + 1, (width, dimensions)
            await page.screenshot(path=str(EVIDENCE / f"season-context-{width}.png"))
        print("Season context fits desktop, tablet, and phone widths without horizontal clipping. PASS")

        await month.select_option("11")
        await page.wait_for_function(
            "!document.querySelector('#harm-season-context').hidden && "
            "document.querySelector('#harm-verdict').textContent.includes('November 2024')"
        )
        assert await page.locator("#harm-value").inner_text() == "7,648"
        assert await page.locator("#harm-years").inner_text() == "1"
        print("November 2024: 7,648 observed cell-days; the same dated source context is visible. PASS")

        await year.select_option("2023")
        await page.wait_for_function(
            "document.querySelector('#harm-verdict')?.textContent.includes('November 2023')"
        )
        assert await context.is_hidden(), "A 2024 government deployment window must not be implied for 2023"

        await region.select_option("norcal")
        await page.wait_for_function(
            "document.querySelector('#harm-verdict')?.textContent.startsWith('Northern California, November 2024:')"
        )
        assert await context.is_hidden(), "Punjab–Haryana context must not appear for Northern California"
        assert not errors, f"Browser JavaScript errors: {errors}"
        print("Out-of-window dates and Northern California: Punjab context hidden; browser has no JS errors. PASS")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
