from __future__ import annotations

import unittest
from datetime import date, timedelta

from fireatlas.calendar_v2 import (_baseline_mismatch_reason, _baseline_signature,
                                   _baseline_median, _history_start, _month_composition,
                                   _percentile_rank, _season, _verdict)
from fireatlas.core import connect
from pathlib import Path
import tempfile


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

    def test_percentile_values_are_withheld_below_ten_comparable_years(self):
        self.assertEqual(_percentile_rank(8.0, list(range(9))), (None, None))
        self.assertEqual(_percentile_rank(8.0, list(range(10))), (90.0, 9))

    def test_prior_year_median_is_withheld_below_three_eligible_years(self):
        self.assertIsNone(_baseline_median([8.0, 10.0]))
        self.assertEqual(_baseline_median([8.0, 10.0, 12.0]), 10.0)

    def test_month_state_distinguishes_observed_mixed_and_unknown_days(self):
        observed = [{"value": 2, "estimate_type": "observed"} for _ in range(31)]
        self.assertEqual(_month_composition(observed, 31), {
            "value": 62.0, "estimate_type": "observed", "observed_days": 31,
            "estimated_days": 0, "unknown_days": 0, "day_count": 31})
        mixed = observed[:25] + [{"value": 3, "estimate_type": "scaled"} for _ in range(6)]
        result = _month_composition(mixed, 31)
        self.assertEqual(result["estimate_type"], "mixed")
        self.assertEqual(result["value"], 68.0)
        self.assertEqual((result["observed_days"], result["estimated_days"], result["unknown_days"]), (25, 6, 0))
        incomplete = _month_composition(mixed[:-1], 31)
        self.assertIsNone(incomplete["value"])
        self.assertEqual(incomplete["estimate_type"], "unknown")
        self.assertEqual(incomplete["unknown_days"], 1)

    def test_baseline_requires_matching_daily_source_composition_and_versions(self):
        def make_month(composition, modis_versions=("61.03",)):
            daily, raw_by_date = [], {}
            for index, (estimate_type, source_id, version) in enumerate(composition):
                stamp = f"2024-07-{index + 1:02d}"
                daily.append({"date": stamp, "value": 2, "estimate_type": estimate_type,
                              "source_used": source_id})
                raw_by_date[stamp] = {"sources": {
                    "MODIS_SP": {"export_complete": True, "product_versions": list(modis_versions)},
                    "VIIRS_SNPP_SP": {"export_complete": True, "product_versions": ["2"]},
                }}
                if source_id == "MODIS_SP":
                    raw_by_date[stamp]["sources"][source_id]["product_versions"] = [version]
            return _baseline_signature(daily, raw_by_date)

        mixed = ([ ("observed", "VIIRS_SNPP_SP", "2") ] * 25
                 + [("scaled", "MODIS_SP", "61.03")] * 6)
        fully_observed = [("observed", "VIIRS_SNPP_SP", "2")] * 31
        target, error = make_month(mixed)
        observed, error_observed = make_month(fully_observed, modis_versions=("6.1", "61.03"))
        wrong_source_mix, _ = make_month(fully_observed)
        wrong_product, _ = make_month(
            [("observed", "VIIRS_SNPP_SP", "2")] * 25
            + [("scaled", "MODIS_SP", "61.02")] * 6)

        self.assertIsNone(error)
        self.assertIsNone(error_observed)
        self.assertNotEqual(target["quantity"], observed["quantity"])
        self.assertEqual(_baseline_mismatch_reason(target, observed), "source-composition-mismatch")
        self.assertIsNone(_baseline_mismatch_reason(observed, wrong_source_mix))
        self.assertNotEqual(target["products"], wrong_product["products"])
        self.assertEqual(target["quantity"], wrong_product["quantity"])
        self.assertEqual(_baseline_mismatch_reason(target, wrong_product), "product-version-mismatch")
        self.assertIsNone(_baseline_mismatch_reason(target, make_month(mixed)[0]))

    def test_history_start_uses_rows_and_survives_export_completeness_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            with connect(Path(temporary) / "history.sqlite3") as db:
                batch_id = db.execute("""
                    INSERT INTO batches(source_id,source_uri,file_sha256,retrieved_utc,demo,row_count,window_key)
                    VALUES('MODIS_SP','local:test',?,'2026-09-30T00:00:00Z',0,8,'test-window')
                """, ("a" * 64,)).lastrowid
                db.execute("""
                    INSERT INTO source_exports(batch_id,region_id,source_id,month,request_start,request_end,
                      west,south,east,north,complete_export,product_versions_json,parent_sha256,request_sha256)
                    VALUES(?,?,? ,?,?,?, ?,?,?,?, ?,?,?,?)
                """, (batch_id, "norcal", "MODIS_SP", "2007-03", "2007-03-01", "2007-03-31",
                      -123, 38, -119, 42, 0, '["61.03"]', "b" * 64, "c" * 64))
                self.assertEqual(_history_start(db, "norcal", 2024).isoformat(), "2007-03-01")
                db.execute("UPDATE source_exports SET complete_export=1 WHERE batch_id=?", (batch_id,))
                db.execute("UPDATE batches SET row_count=0 WHERE id=?", (batch_id,))
                self.assertEqual(_history_start(db, "norcal", 2024).isoformat(), "2007-03-01")


if __name__ == "__main__":
    unittest.main()
