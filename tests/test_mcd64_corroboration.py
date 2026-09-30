from __future__ import annotations

import unittest

from scripts.build_mcd64_corroboration import (
    classify_burn_date_pixel,
    decode_qa_value,
    same_day_spatial_comparison,
)
from fireatlas.calendar_v2 import _mcd64_corroboration


class MCD64QualityTests(unittest.TestCase):
    def test_qa_supported_burn_and_strict_full_period_unburned_rules(self):
        qa_supported = decode_qa_value(3)
        self.assertEqual(classify_burn_date_pixel(201, qa_supported),
                         ("qa-supported-burned", None))
        self.assertEqual(classify_burn_date_pixel(0, qa_supported),
                         ("qa-supported-full-period-unburned", None))

        # Burned dates remain supported when land/data are valid; the flags
        # remain separately visible. A zero Burn Date with those flags is not
        # counted as a full-month unburned observation.
        shortened_and_relabelled = decode_qa_value(15)
        self.assertEqual(classify_burn_date_pixel(201, shortened_and_relabelled),
                         ("qa-supported-burned", None))
        self.assertEqual(classify_burn_date_pixel(0, shortened_and_relabelled),
                         ("excluded-unburned", "shortened-mapping-period"))

    def test_invalid_burned_pixels_are_excluded_with_an_explicit_reason(self):
        self.assertEqual(classify_burn_date_pixel(12, decode_qa_value(1)),
                         ("excluded-burned", "qa-insufficient-valid-data"))
        self.assertEqual(classify_burn_date_pixel(12, decode_qa_value(0)),
                         ("excluded-burned", "qa-not-land-and-insufficient-data"))

    def test_same_utc_date_intersection_uses_source_specific_common_grid_cells(self):
        # 2024 day 200 is July 18. Only the shared MODIS cell contributes.
        result = same_day_spatial_comparison(
            2024,
            {"200": {(10, 20), (11, 21)}},
            {"2024-07-18": {
                "MODIS_SP": {(11, 21), (12, 22)},
                "VIIRS_SNPP_SP": {(13, 23)},
            }},
        )
        self.assertEqual(result["per_burn_date"][0]["burn_date_utc"], "2024-07-18")
        self.assertEqual(result["shared_1km_cell_days_by_source"],
                         {"MODIS_SP": 1, "VIIRS_SNPP_SP": 0})
        self.assertIn("not pixel-level agreement", result["interpretation_limit"])

    def test_day_366_is_not_mapped_into_the_next_year_for_non_leap_year(self):
        result = same_day_spatial_comparison(2025, {"366": {(1, 2)}}, {})
        self.assertEqual(result["per_burn_date"], [])
        self.assertEqual(result["burn_days_without_a_calendar_date"], [366])

    def test_calendar_exposes_qa_and_same_day_context_from_the_bound_report(self):
        result = _mcd64_corroboration("norcal", 2024, 7)
        self.assertEqual(result["status"], "loaded")
        self.assertGreater(result["qa_supported_burned_pixels"], 0)
        self.assertIn("same_day_spatial_comparison", result)
        interpretation = result["same_day_spatial_comparison"]["interpretation_limit"]
        self.assertIn("independent validation", interpretation)
        self.assertIn("MCD64A1 uses cumulative MODIS active-fire maps", interpretation)


if __name__ == "__main__":
    unittest.main()
