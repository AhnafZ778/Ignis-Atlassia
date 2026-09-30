"""Verify that the method-page calibration graphics match the JSON artifacts.

Run a local FireAtlas server, then:
  uv run --with playwright python scripts/verify_calibration_ui.py --base http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


REGIONS = ("norcal", "punjab-haryana")
LABELS = {
    "Month-specific ratio": "monthly_ratio",
    "One annual ratio": "annual_ratio",
    "No scaling · factor 1": "no_harmonization",
}
EVIDENCE = Path("docs/winning-plan/evidence")


def fmt(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def pctfmt(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{fmt(100 * value, digits)}%"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
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
        page = await browser.new_page(viewport={"width": 1440, "height": 1200}, device_scale_factor=1)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(f"{base}/method.html", wait_until="domcontentloaded")
        selector = page.locator("#calibration-region")

        for region in REGIONS:
            await selector.select_option(region)
            response = await page.request.get(f"{base}/samples/calibration/{region}.json")
            assert response.ok, f"{region} artifact returned HTTP {response.status}"
            artifact = await response.json()
            calibration = artifact["calibration"]
            validation = calibration["validation"]
            await page.wait_for_function(
                "name => document.querySelector('#calibration-context')?.textContent.includes(name)",
                arg=artifact["region"]["name"],
            )

            actual_rows = await page.locator("#calibration-models .calibration-model").evaluate_all(
                """rows => rows.map(row => {
                  const stats = row.querySelectorAll('.calibration-model-stat strong');
                  return {
                    label: row.querySelector('.calibration-model-name strong').textContent,
                    badge: row.querySelector('.calibration-model-name span').textContent,
                    error: stats[0].textContent,
                    annual: stats[1].textContent,
                    nested: row.classList.contains('nested'),
                    selected: row.classList.contains('selected')
                  };
                })"""
            )
            assert len(actual_rows) == 4, f"{region}: expected nested result and three references"
            nested = validation["nested_selected_pipeline"]
            nested_row = actual_rows[0]
            assert nested_row["nested"] and not nested_row["selected"], (region, nested_row)
            assert nested_row["label"] == "Nested selected pipeline", (region, nested_row)
            assert nested_row["badge"] == "NESTED HELD-OUT ESTIMATE", (region, nested_row)
            assert nested_row["error"] == fmt(nested["median_absolute_log_error"]), (region, nested_row)
            annual = nested["median_annual_absolute_percent_error"]
            annual_expected = "—" if annual is None else f"{fmt(100 * annual, 1)}%"
            assert nested_row["annual"] == annual_expected, (region, nested_row)
            seen = set()
            for row in actual_rows[1:]:
                key = LABELS[row["label"]]
                seen.add(key)
                model = validation["models"][key]
                assert row["error"] == fmt(model["median_absolute_log_error"]), (region, key, row)
                annual = model["median_annual_absolute_percent_error"]
                annual_expected = "—" if annual is None else f"{fmt(100 * annual, 1)}%"
                assert row["annual"] == annual_expected, (region, key, row)
                assert not row["selected"], (region, "fixed reference styled as winner", row)
                assert row["badge"] == "FIXED CANDIDATE REFERENCE", (region, key, row)
            assert seen == set(validation["models"]), f"{region}: missing model from the graphic"
            context = await page.locator("#calibration-context").inner_text()
            production_label = next(label for label, key in LABELS.items()
                                    if key == calibration["selected_model"])
            assert f"production calendar choice: {production_label.lower()}" in context.lower(), (region, context)

            benchmark = validation["daily_gap_benchmark"]
            daily = benchmark["daily_metrics"]["selected_pipeline"]
            daily_expected = (
                f"{fmt(daily['median_absolute_log_error'])} median log error · "
                f"{pctfmt(daily['median_absolute_percent_error_nonzero'])} median nonzero-day absolute percentage error"
            )
            daily_actual = await page.locator("#calibration-daily-value").inner_text()
            assert daily_actual == daily_expected, (region, daily_actual, daily_expected)
            gap_groups: dict[tuple[int, str], dict] = {}
            for item in benchmark["contiguous_gap_contribution_metrics"]:
                if item["model"] not in {"selected_pipeline", *validation["models"].keys()}:
                    continue
                key = (item["gap_duration_days"], item["season"])
                gap_groups.setdefault(key, {})[item["model"]] = item
            expected_gaps = [
                {"gap_duration_days": key[0], "season": key[1], **value}
                for key, value in sorted(gap_groups.items())
            ]
            actual_gaps = await page.locator("#calibration-gap-table tbody tr").evaluate_all(
                "rows => rows.map(row => [...row.cells].map(cell => cell.textContent.trim()))"
            )
            assert len(actual_gaps) == len(expected_gaps) == 16, (region, len(actual_gaps), len(expected_gaps))
            for actual, expected in zip(actual_gaps, expected_gaps):
                gap_label = f"{expected['gap_duration_days']} day{'s' if expected['gap_duration_days'] != 1 else ''} · {expected['season']}"
                count_source = (expected.get("selected_pipeline") or expected.get("monthly_ratio")
                                or expected.get("annual_ratio") or expected.get("no_harmonization"))
                gap_values = [
                    gap_label,
                    f"{count_source['window_count']:,}",
                    fmt(expected["selected_pipeline"]["median_absolute_log_error"])
                    if expected.get("selected_pipeline") else "—",
                    fmt(expected["monthly_ratio"]["median_absolute_log_error"])
                    if expected.get("monthly_ratio") else "—",
                    fmt(expected["annual_ratio"]["median_absolute_log_error"])
                    if expected.get("annual_ratio") else "—",
                    fmt(expected["no_harmonization"]["median_absolute_log_error"])
                    if expected.get("no_harmonization") else "—",
                ]
                assert actual == gap_values, (region, actual, gap_values)

            interval = validation["prediction_interval"]
            assert interval["status"] == "withheld-not-independently-calibrated", (region, interval)
            assert interval["held_out_coverage"] is None and interval["median_width"] is None
            coverage_actual = await page.locator("#calibration-coverage-value").inner_text()
            assert coverage_actual == "Withheld", (region, coverage_actual)
            coverage_note = await page.locator("#calibration-coverage-note").inner_text()
            assert interval["reason"] in coverage_note and "No coverage or interval width is claimed." in coverage_note

            step = calibration.get("step_2012") or {}
            step_value = await page.locator("#calibration-step-value").inner_text()
            step_note = await page.locator("#calibration-step-note").inner_text()
            if step.get("status") == "evaluated":
                expected_value = "Inside reference interval" if step["within_interval"] else "Outside reference interval"
                expected_note = (
                    f"2012 ratio {fmt(step['ratio'])} from {len(step['months_used'])} complete months; "
                    f"later-year 95% interval {fmt(step['interval_95'][0])}–{fmt(step['interval_95'][1])} "
                    f"({len(step['reference_years'])} reference years)."
                )
                assert step_value == expected_value, (region, step_value, expected_value)
                assert step_note == expected_note, (region, step_note, expected_note)
            else:
                pending_notes = {
                    "insufficient-reference-years": (
                        "The 2012 rows exist, but fewer than two later complete overlap years are available "
                        "for the reference interval."
                    ),
                    "awaiting-2012-standard-exports": (
                        "2012 detections are present as partial evidence, but the saved request metadata "
                        "do not establish complete source exports."
                    ),
                }
                expected_note = pending_notes.get(step.get("status"))
                assert expected_note is not None, (region, "unexpected 2012 step status", step)
                assert step_value == "Not tested", (region, step_value)
                assert step_note == expected_note, (region, step_note, expected_note)
                assert step.get("ratio") is None and step.get("within_interval") is None, (region, step)
                result_attr = await page.locator("#calibration-step-value").get_attribute("data-result")
                assert result_attr is None, (region, "pending step has a result marker", result_attr)

            await page.locator("#calibration-validation").screenshot(
                path=str(EVIDENCE / f"C10-T1-calibration-{region}.png")
            )
            print(
                f"{region}: nested estimate, three fixed references, daily and seasonal-gap metrics, "
                f"withheld prediction interval, and 2012 step state match the source JSON. PASS",
                flush=True,
            )

        assert not errors, f"Browser JavaScript errors: {errors}"
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
