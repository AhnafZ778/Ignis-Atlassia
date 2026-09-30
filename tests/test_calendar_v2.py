from __future__ import annotations

import unittest
from datetime import date, timedelta

from fireatlas.calendar_v2 import _season, _verdict


def triangular_year() -> list[dict]:
    start = date(2024, 1, 1)
    days = []
    for index in range(366):
        value = max(0, 11 - abs(index - 50))
        days.append({"date": (start + timedelta(days=index)).isoformat(), "value": value})
    return days


class CriticalDateTests(unittest.TestCase):
    def test_triangle_returns_known_ten_percent_dates_and_fifteen_day_peak(self):
        result = _season(triangular_year())
        self.assertEqual(result["season_status"], "available")
        self.assertEqual(result["season_start"], "2024-02-14")
        self.assertEqual(result["season_peak"], "2024-02-20")
        self.assertEqual(result["season_end"], "2024-02-26")

    def test_more_than_ten_percent_unknown_days_withholds_critical_dates(self):
        days = triangular_year()
        for item in days[:37]:
            item["value"] = None
        result = _season(days)
        self.assertEqual(result["season_status"], "unavailable")
        self.assertEqual(result["missing_days"], 37)
        self.assertIsNone(result["season_start"])
        self.assertIsNone(result["season_peak"])
        self.assertIsNone(result["season_end"])

    def test_comparison_verdict_names_estimate_reason_and_omits_zero_estimate_clause(self):
        item = {"month": "2024-07", "value": 120.0, "percentile_rank": 92,
                "n_years": 12, "outside_downloaded_snpp_period_days": 4,
                "documented_gap_estimate_days": 2}
        verdict = _verdict("Northern California", 2024, item)
        self.assertEqual(verdict,
                         "Northern California, July 2024: 92nd percentile of 12 comparable years. "
                         "6 days are MODIS estimates: 4 before the downloaded S-NPP period and "
                         "2 during a documented product gap.")
        item["outside_downloaded_snpp_period_days"] = 0
        item["documented_gap_estimate_days"] = 0
        verdict_without_estimate = _verdict("Northern California", 2024, item)
        self.assertEqual(verdict_without_estimate,
                         "Northern California, July 2024: 92nd percentile of 12 comparable years.")

    def test_fewer_than_ten_comparable_years_withholds_percentile(self):
        verdict = _verdict("Punjab–Haryana", 2024, {
            "month": "2024-07", "value": 120.0, "n_years": 9,
            "outside_downloaded_snpp_period_days": 0,
            "documented_gap_estimate_days": 0,
        })
        self.assertEqual(verdict,
                         "Punjab–Haryana, July 2024: comparison not usable. Only 9 comparable years.")


if __name__ == "__main__":
    unittest.main()
