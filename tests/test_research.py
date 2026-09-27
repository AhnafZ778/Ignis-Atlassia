import contextlib
import copy
import io
import tempfile
import unittest
from datetime import date
from pathlib import Path

from fireatlas.core import connect, TO_GRID
from fireatlas.demo import make_demo, BBOX
from fireatlas.research import report, coverage_example, overlap, candidates, context


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        with contextlib.redirect_stdout(io.StringIO()):
            make_demo(root / "demo", root / "study.sqlite3")
        self.db = connect(root / "study.sqlite3")
        self.addCleanup(self.db.close)

    def mask(self):
        return coverage_example(self.db, year=2015, month=7, bbox=BBOX)

    def test_overlap_deduplicates_pixels_and_withholds_small_sample_band(self):
        result = report(self.db)
        self.assertEqual(result["raw_pixels"], 16)
        self.assertEqual(result["overlap"]["totals"]["both"], 4)
        self.assertEqual(result["overlap"]["raw_pixels"], {"MODIS_SP": 4, "VIIRS_SNPP_SP": 12})
        self.assertEqual(result["overlap"]["ratio"], 1)
        self.assertIsNone(result["overlap"]["ratio_band"])
        self.assertEqual(result["overlap"]["band_status"], "insufficient_active_days")
        self.assertEqual(result["coverage"]["status"], "unavailable")
        self.assertEqual(result["report_id"], report(self.db)["report_id"])

    def test_cutoff_and_linking_parameters_change_membership(self):
        result = report(self.db, as_of="2015-07-02")
        self.assertEqual(result["raw_pixels"], 8)
        self.assertEqual(result["candidates"]["count"], 1)
        self.assertEqual(result["candidates"]["groups"][0]["cell_days"], 2)
        self.assertTrue(all(p["date"] <= "2015-07-02" for p in result["candidates"]["groups"][0]["points"]))
        separated = report(self.db, gap_days=0)
        self.assertEqual(separated["candidates"]["count"], 4)
        self.assertEqual(len({g["id"] for g in separated["candidates"]["groups"]}), 4)
        self.assertEqual(report(self.db)["candidates"]["count"], 1)

    def test_supplied_exposure_uses_intersection_and_unknown_rows_are_not_zero(self):
        mask = self.mask()
        result = report(self.db, mask=mask)
        for source in result["coverage"]["sources"]:
            self.assertEqual(source["detected_in_mask"], 4)
            self.assertEqual(source["observed_cell_days"], 31)
            self.assertAlmostEqual(source["per_100_observed_cell_days"], 400 / 31)
        mask["cells"] = [cell for cell in mask["cells"] if cell["date"] != "2015-07-01"]
        for cell in mask["cells"]:
            if cell["date"] == "2015-07-05":
                cell["status"] = "cloud"
        for source in report(self.db, mask=mask)["coverage"]["sources"]:
            self.assertEqual(source["detected_in_mask"], 3)
            self.assertEqual(source["observed_cell_days"], 29)
            self.assertEqual(source["detections_without_mask"], 1)
            self.assertAlmostEqual(source["per_100_observed_cell_days"], 300 / 29)

    def test_mask_rejects_duplicates_conflicts_scope_and_data_class(self):
        original = self.mask()
        masks = []
        duplicate = copy.deepcopy(original)
        duplicate["cells"].append(duplicate["cells"][0]); masks.append(duplicate)
        conflict = copy.deepcopy(original); conflict["cells"][0]["status"] = "cloud"; masks.append(conflict)
        wrong_scope = copy.deepcopy(original); wrong_scope["bbox"][0] = -123; masks.append(wrong_scope)
        real = copy.deepcopy(original); real["synthetic"] = False; masks.append(real)
        invalid = copy.deepcopy(original); invalid["cells"][0]["grid_x"] = True; masks.append(invalid)
        for mask in masks:
            with self.subTest(mask=mask["synthetic"]), self.assertRaises(ValueError):
                report(self.db, mask=mask)

    def test_incomplete_exports_and_no_exposure_withhold_rates(self):
        mask = self.mask()
        self.db.execute("DELETE FROM export_windows WHERE month='2015-07' AND source_id='VIIRS_SNPP_SP'")
        result = report(self.db, mask=mask)
        self.assertIsNotNone(result["coverage"]["sources"][0]["per_100_observed_cell_days"])
        self.assertIsNone(result["coverage"]["sources"][1]["per_100_observed_cell_days"])
        self.assertEqual(result["overlap"]["band_status"], "incomplete_exports")
        mask["cells"] = [c for c in mask["cells"] if c["date"] > "2015-07-04"]
        for cell in mask["cells"]:
            cell["status"] = "unknown"
        self.assertTrue(all(s["per_100_observed_cell_days"] is None for s in report(self.db, mask=mask)["coverage"]["sources"]))

    def test_empty_and_invalid_selection(self):
        result = report(self.db, month=8)
        self.assertEqual(result["raw_pixels"], 0)
        self.assertEqual(result["candidates"]["count"], 0)
        self.assertIsNone(result["overlap"]["ratio"])
        for options in [{"distance_km": float("nan")}, {"gap_days": 1.5}, {"as_of": "2015-08-01"}, {"bbox": [0,89,1,90]}, {"month": 13}]:
            with self.assertRaises(ValueError):
                report(self.db, **options)

    def test_bootstrap_is_reproducible_and_mixed_versions_disable_band(self):
        rows = []
        for day in range(1, 16):
            for source in ["MODIS_SP", "VIIRS_SNPP_SP"]:
                for cell in range(1 if source == "MODIS_SP" else 1 + day % 3):
                    rows.append({"source_id": source, "acquisition_utc": f"2015-07-{day:02d}T12:00:00Z", "grid_x": cell, "grid_y": 0, "product_version": "1"})
        complete = {"MODIS_SP": True, "VIIRS_SNPP_SP": True}
        a = overlap(rows, date(2015,7,1), date(2015,7,31), complete)
        self.assertEqual(a["band_status"], "exploratory")
        self.assertLess(a["ratio_band"][0], a["ratio"])
        self.assertGreater(a["ratio_band"][1], a["ratio"])
        self.assertEqual(a, overlap(rows, date(2015,7,1), date(2015,7,31), complete))
        rows[0]["product_version"] = "2"
        self.assertEqual(overlap(rows, date(2015,7,1), date(2015,7,31), complete)["band_status"], "mixed_product_versions")

    def test_candidate_distance_uses_ground_distance_at_high_latitude(self):
        x, y = TO_GRID.transform(10, 80)
        gx, gy = int(x // 1000), int(y // 1000)
        rows = [{"grid_x": gx + i, "grid_y": gy, "acquisition_utc": "2015-07-01T12:00:00Z",
                 "detection_id": str(i), "source_id": "MODIS_SP", "lon": 10, "lat": 80} for i in (0, 2)]
        # Two kilometers in the projection are less than one kilometer on the ground here.
        self.assertEqual(candidates(rows, 1, 0)["count"], 1)


if __name__ == "__main__":
    unittest.main()
