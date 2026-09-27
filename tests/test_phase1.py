from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fireatlas.core import calendar, connect, ingest
from fireatlas.demo import BBOX, FIELDS, make_demo
from fireatlas.fetch import fetch_month


def row(**changes):
    result = {
        "latitude": "40.12345", "longitude": "-121.12345",
        "acq_date": "2024-07-01", "acq_time": "1234", "satellite": "T",
        "instrument": "MODIS", "confidence": "80", "version": "6.1",
        "scan": "1.0", "track": "1.0", "frp": "12.4", "daynight": "D",
    }
    result.update(changes)
    return result


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


class Phase1Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = connect(self.root / "test.sqlite3")
        self.addCleanup(lambda: self.db.close())

    def test_joint_cell_day_retains_raw_sensor_counts_and_native_confidence(self):
        modis = self.root / "modis.csv"
        viirs = self.root / "viirs.csv"
        write_csv(modis, [row()])
        write_csv(viirs, [row(instrument="VIIRS", satellite="N", confidence="n", scan="0.38", track="0.38"),
                          row(instrument="VIIRS", satellite="N", confidence="h", longitude="-121.12346", scan="0.38", track="0.38")])
        ingest(self.db, modis, "MODIS_SP", complete_month="2024-07", bbox=BBOX)
        ingest(self.db, viirs, "VIIRS_SNPP_SP", complete_month="2024-07", bbox=BBOX)
        output = calendar(self.db, bbox=BBOX, year=2024)
        july_1 = next(day for day in output["daily"] if day["date_utc"] == "2024-07-01")
        self.assertEqual(july_1["detected_cell_days"], 1)
        self.assertEqual(july_1["raw_pixels_by_sensor"], {"MODIS": 1, "VIIRS": 2})
        self.assertEqual(output["monthly"][6]["detected_cell_days"], 1)
        self.assertEqual(output["monthly"][6]["satellite_observation_coverage"], "unknown")
        self.assertEqual(
            set(r["confidence_raw"] for r in self.db.execute("SELECT confidence_raw FROM observations")),
            {"80", "n", "h"},
        )

    def test_reimport_is_idempotent_and_invalid_csv_rolls_back(self):
        path = self.root / "modis.csv"
        write_csv(path, [row()])
        first = ingest(self.db, path, "MODIS_SP", complete_month="2024-07", bbox=BBOX)
        again = ingest(self.db, path, "MODIS_SP", complete_month="2024-07", bbox=BBOX)
        self.assertEqual(first["rows_inserted"], 1)
        self.assertTrue(again["already_imported"])
        self.assertEqual(self.db.execute("SELECT count(*) FROM observations").fetchone()[0], 1)
        write_csv(path, [row(acq_date="2024-07-02"), row(acq_date="2024-08-01")])
        with self.assertRaisesRegex(ValueError, "outside declared complete export window"):
            ingest(self.db, path, "MODIS_SP", complete_month="2024-07", bbox=BBOX)
        self.assertEqual(self.db.execute("SELECT count(*) FROM observations").fetchone()[0], 1)

    def test_source_uri_does_not_store_firms_key(self):
        path = self.root / "modis.csv"
        write_csv(path, [row()])
        ingest(self.db, path, "MODIS_SP", source_uri="https://firms.modaps.eosdis.nasa.gov/api/area/csv/secret-key/MODIS_SP/-122,39,-120,41/1?token=another-secret")
        uri = self.db.execute("SELECT source_uri FROM batches").fetchone()[0]
        self.assertIn("[MAP_KEY]", uri)
        self.assertNotIn("secret", uri)

    def test_incomplete_month_is_not_a_zero_and_has_no_baseline(self):
        path = self.root / "partial.csv"
        write_csv(path, [row()])
        ingest(self.db, path, "MODIS_SP")
        output = calendar(self.db, bbox=BBOX, year=2024, series="modis")
        july = output["monthly"][6]
        self.assertIsNone(july["detected_cell_days"])
        self.assertEqual(july["partial_import_detected_cell_days"], 1)
        self.assertIsNone(july["baseline_median"])

    def test_baseline_uses_prior_same_cohort_years_only(self):
        self.db.close()
        demo_db_path = self.root / "demo.sqlite3"
        make_demo(self.root / "demo", demo_db_path)
        self.db = connect(demo_db_path)
        joint = calendar(self.db, bbox=BBOX, year=2015, series="joint")
        july = joint["monthly"][6]
        self.assertEqual(july["detected_cell_days"], 4)
        self.assertEqual(july["baseline_median"], 2)
        self.assertEqual(july["baseline_years"], [2012, 2013, 2014])
        self.assertEqual(july["anomaly_cell_days"], 2)
        self.assertTrue(joint["demo_data"])
        early = calendar(self.db, bbox=BBOX, year=2004, series="modis")
        self.assertEqual(early["monthly"][6]["baseline_years"], [2001, 2002, 2003])
        self.assertEqual(early["monthly"][6]["baseline_median"], 3)
        self.assertIsNone(calendar(self.db, bbox=BBOX, year=2004, series="joint")["monthly"][6]["detected_cell_days"])

    def test_firms_month_fetch_uses_five_day_windows_and_redacts_key(self):
        class Response:
            def __init__(self, body): self.body = body
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self): return self.body

        urls = []

        def fake_open(url, timeout):
            urls.append(url)
            if "data_availability" in url:
                return Response(b"data_id,min_date,max_date\nMODIS_SP,2000-11-01,2024-12-31\n")
            return Response((",".join(FIELDS) + "\n").encode())

        with patch.dict(os.environ, {"FIRMS_MAP_KEY": "private-test-key"}), patch("fireatlas.fetch.urlopen", side_effect=fake_open):
            result = fetch_month(self.db, month="2024-02", source_id="MODIS_SP", bbox=BBOX, directory=self.root / "downloads")
        self.assertEqual(result["rows_read"], 0)
        self.assertEqual(len(urls), 7)
        self.assertTrue(urls[-1].endswith("/4/2024-02-26"))
        self.assertNotIn("private-test-key", self.db.execute("SELECT source_uri FROM batches").fetchone()[0])
        february = calendar(self.db, bbox=BBOX, year=2024, series="modis")["monthly"][1]
        self.assertEqual(february["detected_cell_days"], 0)
        self.assertEqual(february["satellite_observation_coverage"], "unknown")


if __name__ == "__main__":
    unittest.main()

class PublicCsvTests(unittest.TestCase):
    def test_public_header_preserved_and_polar_row_accounted_for(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'public.csv'
            values = [row(instrument='VIIRS', satellite='N21', version='2.0NRT'),
                      row(instrument='VIIRS', satellite='N21', version='2.0NRT', latitude='-86.2141')]
            for item in values: item.pop('instrument')
            with path.open('w') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(values[0]));writer.writeheader();writer.writerows(values)
            with connect(root / 'test.sqlite3') as db:
                with self.assertRaisesRegex(ValueError, 'coordinates outside'):
                    ingest(db, path, 'VIIRS_NOAA21_NRT')
                self.assertEqual(db.execute('SELECT count(*) FROM batches').fetchone()[0], 0)
                result = ingest(db, path, 'VIIRS_NOAA21_NRT', exclude_outside_grid=True)
                self.assertEqual((result['rows_read'],result['rows_inserted'],result['rows_excluded']), (2,1,1))
                raw = json.loads(db.execute('SELECT raw_json FROM observations').fetchone()[0])
                self.assertNotIn('instrument', raw)
                self.assertEqual(db.execute('SELECT sensor FROM observations').fetchone()[0], 'VIIRS')
                self.assertEqual(db.execute('SELECT line_number FROM excluded_rows').fetchone()[0], 3)
                self.assertEqual(ingest(db,path,'VIIRS_NOAA21_NRT',exclude_outside_grid=True)['rows_inserted'], 0)
                self.assertEqual(db.execute('SELECT count(*) FROM export_windows').fetchone()[0], 0)
