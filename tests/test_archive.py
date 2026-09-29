import csv
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from fireatlas.archive import BBOX, SAMPLE, build_bundle, import_bundle
from fireatlas.bootstrap import populate_showcase
from fireatlas.core import calendar, connect
from fireatlas.harmonization import month_audit
from fireatlas.pilots import PilotSync


class ArchiveTests(unittest.TestCase):
    def test_packaged_nasa_pair_loads_on_fresh_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "fireatlas.sqlite3"
            self.assertTrue(SAMPLE.exists())
            self.assertTrue(populate_showcase(database)["loaded"])
            imported = import_bundle(database)
            self.assertEqual(imported["imported_rows"], 30823)
            status = PilotSync(database).reconcile_imports()
            self.assertEqual((status["sync"]["completed"], status["sync"]["status"]), (16, "complete"))
            with connect(database) as db:
                audit = month_audit(db, bbox=BBOX, year=2025, month=7, series="joint")
                self.assertEqual((audit["raw_pixels_total"], audit["detected_cell_days"]), (1467, 474))

    def test_world_archives_become_verified_regional_months(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "NASA_data"
            header = ["latitude", "longitude", "brightness", "scan", "track", "acq_date",
                      "acq_time", "satellite", "instrument", "confidence", "version",
                      "bright_t31", "frp", "daynight", "type"]
            for year in (2022, 2023, 2024, 2025):
                for code, platform, instrument, version in (("M-C61", "Terra", "MODIS", "61.03"),
                                                            ("SV-C2", "SNPP", "SNPP", "2")):
                    if year == 2022 and code == "M-C61":
                        version = "6.03"
                    request = f"{code}_{year}"
                    directory = archive / f"DL_FIRE_{request}"
                    directory.mkdir(parents=True)
                    path = directory / f"fire_archive_{request}.csv"
                    with path.open("w", newline="") as stream:
                        writer = csv.writer(stream)
                        writer.writerow(header)
                        for step in range(12):
                            month = (7 + step - 1) % 12 + 1
                            stamp_year = year + (7 + step > 12)
                            writer.writerow([40, -121, 300, 0.4, 0.4, f"{stamp_year}-{month:02d}-01",
                                             "1200", platform, instrument, "n", version, 280, 2, "D", 0])
                        writer.writerow([0, 0, 300, 0.4, 0.4, f"{year + 1}-07-01",
                                         "1200", platform, instrument, "n", version, 280, 2, "D", 0])
            bundle = root / "slices.zip"
            result = build_bundle(archive, bundle)
            self.assertEqual((result["sources"], result["slices"], result["complete_month_slices"]),
                             (8, 96, 84))
            with zipfile.ZipFile(bundle) as zipped:
                manifest = json.loads(zipped.read("manifest.json"))
                self.assertEqual(len(manifest["source_files"]), 8)
                self.assertTrue(all(len(item["original_sha256"]) == 64 for item in manifest["source_files"]))
            database = root / "atlas.sqlite3"
            self.assertEqual(import_bundle(database, bundle)["imported_rows"], 96)
            self.assertEqual(import_bundle(database, bundle)["already_imported_slices"], 96)
            with connect(database) as db:
                july = calendar(db, bbox=BBOX, year=2025, series="joint")["monthly"][6]
                self.assertEqual(july["detected_cell_days"], 1)
                self.assertEqual(july["baseline_years"], [2022, 2023, 2024])
                self.assertEqual(month_audit(db, bbox=BBOX, year=2025, month=7, series="joint")["baseline_version_status"],
                                 "mixed-product-versions-across-years")
                self.assertIsNone(calendar(db, bbox=BBOX, year=2026, series="joint")["monthly"][0]["detected_cell_days"])


if __name__ == "__main__":
    unittest.main()
