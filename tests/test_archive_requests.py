from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from fireatlas.archive import import_requests
from fireatlas.aggregates import daily_aggregates
from fireatlas.calendar_v2 import calendar_v2, region_status
from fireatlas.core import _complete_month, connect
from fireatlas.regions import REGIONS


FIELDS = ["latitude", "longitude", "brightness", "scan", "track", "acq_date", "acq_time",
          "satellite", "instrument", "confidence", "version", "bright_t31", "frp", "daynight", "type"]


class ArchiveRequestImportTests(unittest.TestCase):
    def _request(self, folder: Path, source: str, *, full_month=True, empty=False):
        folder.mkdir(parents=True)
        bbox = REGIONS["norcal"]["bbox"]
        request = {"product": source,
                   "start_date": "2024-07-01" if full_month else "2024-07-01",
                   "end_date": "2024-07-31" if full_month else "2024-07-15",
                   "bbox": list(bbox), "product_version": "2.0" if source == "VIIRS_SNPP_SP" else "61.03"}
        (folder / "request.json").write_text(json.dumps(request), encoding="utf-8")
        with (folder / "download.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(FIELDS)
            if not empty:
                row = [40, -121, 300, .4, .4, "2024-07-25" if full_month else "2024-07-10", "1200",
                       "Terra" if source == "MODIS_SP" else "SNPP",
                       "MODIS" if source == "MODIS_SP" else "SNPP", "n",
                       "61.03" if source == "MODIS_SP" else "2.0", 280, 2, "D", 0]
                writer.writerow(row)

    def test_import_tracks_empty_full_month_and_reimport_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            downloads = root / "NASA_data"
            self._request(downloads / "modis", "MODIS_SP")
            self._request(downloads / "viirs", "VIIRS_SNPP_SP", empty=True)
            database = root / "atlas.sqlite3"
            result = import_requests(database, downloads)
            self.assertEqual(result["complete_month_slices"], 2)
            self.assertEqual(result["imported_rows"], 1)
            second = import_requests(database, downloads)
            self.assertEqual(second["imported_rows"], 0)
            self.assertEqual(second["already_imported_slices"], 2)
            with connect(database) as db:
                bbox = REGIONS["norcal"]["bbox"]
                self.assertTrue(_complete_month(db, "2024-07", ("MODIS_SP",), bbox))
                self.assertTrue(_complete_month(db, "2024-07", ("VIIRS_SNPP_SP",), bbox))
                empty_version = db.execute("SELECT product_versions_json FROM source_exports WHERE source_id='VIIRS_SNPP_SP'").fetchone()[0]
                self.assertEqual(json.loads(empty_version), ["2.0"])
                empty_rows = db.execute("SELECT count(*) FROM observations WHERE source_id='VIIRS_SNPP_SP'").fetchone()[0]
                self.assertEqual(empty_rows, 0)

    def test_partial_date_request_cannot_create_complete_export_window(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            downloads = root / "NASA_data"
            self._request(downloads / "modis", "MODIS_SP", full_month=False)
            result = import_requests(root / "atlas.sqlite3", downloads)
            self.assertEqual(result["complete_month_slices"], 0)
            with connect(root / "atlas.sqlite3") as db:
                self.assertFalse(_complete_month(db, "2024-07", ("MODIS_SP",), REGIONS["norcal"]["bbox"]))

    def test_named_standard_csv_is_selected_when_nrt_sibling_exists(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "NASA_data" / "modis"
            self._request(folder, "MODIS_SP")
            sidecar = json.loads((folder / "request.json").read_text(encoding="utf-8"))
            sidecar["csv_filename"] = "download.csv"
            (folder / "request.json").write_text(json.dumps(sidecar), encoding="utf-8")
            (folder / "nrt.csv").write_text("not a FIRMS archive", encoding="utf-8")
            result = import_requests(root / "atlas.sqlite3", root / "NASA_data")
            self.assertEqual(result["requests"], 1)
            self.assertEqual(result["complete_month_slices"], 1)

    def test_named_csv_cannot_escape_its_request_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "NASA_data" / "modis"
            self._request(folder, "MODIS_SP")
            sidecar = json.loads((folder / "request.json").read_text(encoding="utf-8"))
            sidecar["csv_filename"] = "../download.csv"
            (folder / "request.json").write_text(json.dumps(sidecar), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "local CSV basename"):
                import_requests(root / "atlas.sqlite3", root / "NASA_data")

    def test_empty_world_month_stays_unknown_instead_of_becoming_zero_activity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "NASA_data" / "viirs"
            self._request(folder, "VIIRS_SNPP_SP", empty=True)
            sidecar_path = folder / "request.json"
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            sidecar["bbox"] = [-180, -90, 180, 90]
            sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
            result = import_requests(root / "atlas.sqlite3", root / "NASA_data")
            self.assertEqual(result["complete_month_slices"], 0)
            with connect(root / "atlas.sqlite3") as db:
                self.assertFalse(_complete_month(db, "2024-07", ("VIIRS_SNPP_SP",), REGIONS["norcal"]["bbox"]))

    def test_reconstructed_file_dates_import_positive_rows_without_claiming_complete_coverage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            downloads = root / "NASA_data"
            self._request(downloads / "modis", "MODIS_SP")
            sidecar = downloads / "modis" / "request.json"
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
            metadata["coverage_basis"] = "reconstructed-rows-only"
            sidecar.write_text(json.dumps(metadata), encoding="utf-8")

            database = root / "atlas.sqlite3"
            result = import_requests(database, downloads)
            self.assertEqual(result["complete_month_slices"], 0)
            self.assertEqual(result["reconstructed_row_only_month_slices"], 1)
            with connect(database) as db:
                bbox = REGIONS["norcal"]["bbox"]
                self.assertFalse(_complete_month(db, "2024-07", ("MODIS_SP",), bbox))
                export = db.execute("SELECT coverage_basis,complete_export FROM source_exports WHERE region_id='norcal'").fetchone()
                self.assertEqual(export["coverage_basis"], "reconstructed-rows-only")
                self.assertEqual(export["complete_export"], 0)
                daily = daily_aggregates(db, "norcal", "2024-07-01", "2024-07-31")
                day = next(item for item in daily["days"] if item["date_utc"] == "2024-07-25")
                source = day["sources"]["MODIS_SP"]
                self.assertFalse(source["export_complete"])
                self.assertEqual(source["partial_detected_cell_days"], 1)
                status = region_status(db)["regions"]
                norcal = next(item for item in status if item["id"] == "norcal")
                self.assertEqual(norcal["products"]["MODIS_SP"]["reconstructed_row_only_months"], ["2024-07"])
                calendar = calendar_v2(db, region="norcal", year=2024, month=7, include_history=True)
                day = next(item for item in calendar["days"] if item["date"] == "2024-07-25")
                self.assertEqual(day["partial_modis_cell_days"], 1)
                month = next(item for item in calendar["months"] if item["month"] == "2024-07")
                self.assertEqual(month["partial_detection_days"], 1)
                historic = next(item for item in calendar["history"]["days"] if item["date"] == "2024-07-25")
                self.assertEqual(historic["partial_modis_cell_days"], 1)


if __name__ == "__main__":
    unittest.main()
