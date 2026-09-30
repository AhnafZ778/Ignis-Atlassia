from __future__ import annotations

import unittest
from datetime import date, timedelta

from fireatlas.calibration import build_artifact, calibrate


def synthetic_daily(*, step_ratio: float = 4.0) -> dict:
    days = []
    current, end = date(2012, 7, 1), date(2016, 12, 31)
    while current <= end:
        first = current.day == 1
        modis = 100 if first else 0
        ratio = step_ratio if current.year == 2012 else 4.0
        viirs = round(modis * ratio)
        days.append({
            "date_utc": current.isoformat(),
            "sources": {
                "MODIS_SP": {"export_complete": True,
                             "detected_cell_days": modis,
                             "product_versions": ["61.03"]},
                "VIIRS_SNPP_SP": {"export_complete": True,
                                  "detected_cell_days": viirs,
                                  "product_versions": ["2"],
                                  "availability": {"status": "detections_in_export"}},
            },
        })
        current += timedelta(days=1)
    return {"region": {"id": "synthetic-test"}, "days": days}


class CalibrationTests(unittest.TestCase):
    def test_fixed_ratio_has_zero_held_out_error_and_reproducible_seed(self):
        first = calibrate(synthetic_daily())
        second = calibrate(synthetic_daily())
        self.assertEqual(first["months"][0]["ratio"], 4.0)
        self.assertEqual(first["validation"]["models"]["monthly_ratio"]["median_absolute_log_error"], 0.0)
        self.assertEqual(first["validation"]["models"]["annual_ratio"]["median_absolute_log_error"], 0.0)
        self.assertEqual(first["step_2012"]["status"], "evaluated")
        self.assertTrue(first["step_2012"]["within_interval"])
        self.assertEqual(first["months"], second["months"])
        self.assertEqual(first["step_2012"], second["step_2012"])
        self.assertEqual(first["eligible_months"], second["eligible_months"])
        self.assertEqual(first["eligible_months"][0]["modis_cell_days"], 100)
        self.assertEqual(first["eligible_months"][0]["viirs_cell_days"], 400)
        self.assertEqual(first["eligible_months"][0]["eligible_utc_days"], 31)
        self.assertEqual(first["validation"]["models"]["monthly_ratio"]["annual_error_years"],
                         [2013, 2014, 2015, 2016])
        self.assertEqual(first["validation"]["partial_years_excluded_from_annual_error"],
                         [{"year": 2012, "eligible_months": 6, "annual_error_used": False}])

    def test_calibration_artifact_hashes_exact_paired_inputs(self):
        report = calibrate(synthetic_daily())
        region = {"id": "norcal", "name": "Northern California", "bbox": [-122.2, 38.8, -120.0, 41.0]}
        months = ["2022-07", "2022-08"]
        files = [{"filename": "fire_archive_M-C61_1.csv", "sha256": "a" * 64},
                 {"filename": "fire_archive_SV-C2_2.csv", "sha256": "b" * 64}]
        first = build_artifact(region=region, calibration=report, paired_months=months,
                               parent_files=files, daily_bundle_sha256="c" * 64)
        again = build_artifact(region=region, calibration=report, paired_months=months,
                               parent_files=files, daily_bundle_sha256="c" * 64)
        changed = build_artifact(region=region, calibration=report, paired_months=months,
                                 parent_files=files, daily_bundle_sha256="d" * 64)
        self.assertEqual(first, again)
        self.assertEqual(first["schema"], "fireatlas-calibration-artifact-v1")
        self.assertNotEqual(first["provenance"]["input_manifest_sha256"],
                            changed["provenance"]["input_manifest_sha256"])
        self.assertEqual(first["calibration"]["calibration_id"], report["calibration_id"])

    def test_step_test_detects_a_2012_ratio_outside_later_year_interval(self):
        result = calibrate(synthetic_daily(step_ratio=10.0))
        self.assertEqual(result["step_2012"]["ratio"], 10.0)
        self.assertFalse(result["step_2012"]["within_interval"])
        self.assertEqual(result["step_2012"]["reference_years"], [2013, 2014, 2015, 2016])

    def test_step_test_is_explicitly_pending_without_2012_rows(self):
        rows = [day for day in synthetic_daily()["days"] if not day["date_utc"].startswith("2012-")]
        from fireatlas.calibration import _rows, _step_2012
        monthly, _ = _rows({"region": {"id": "synthetic-test"}, "days": rows})
        step = _step_2012(monthly)
        self.assertEqual(step["status"], "awaiting-2012-standard-exports")
        self.assertIsNone(step["within_interval"])


if __name__ == "__main__":
    unittest.main()
