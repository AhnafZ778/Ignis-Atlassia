from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import shapefile

from fireatlas.core import calendar, connect
from fireatlas.hms import harvest_month
from fireatlas.bootstrap import populate_showcase


class HmsArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = connect(self.root / "real.sqlite3")
        self.addCleanup(self.db.close)
        self.directory = self.root / "downloads"
        self.directory.mkdir()

    def make_day(self, day: date):
        shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
        writer = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POINT)
        writer.field("Lon", "N", 11, 6)
        writer.field("Lat", "N", 10, 6)
        writer.field("YearDay", "N", 8, 0)
        writer.field("Time", "C", 5)
        writer.field("Satellite", "C", 20)
        writer.field("Method", "C", 21)
        writer.field("Ecosystem", "N", 4, 0)
        writer.field("FRP", "N", 8, 3)
        writer.point(-121.7, 39.9)
        writer.record(-121.7, 39.9, int(day.strftime("%Y%j")), "1025", "NOAA 21", "VIIRS", 43, 12.5)
        writer.close()
        stem = f"hms_fire{day:%Y%m%d}"
        with zipfile.ZipFile(self.directory / f"{stem}.zip", "w") as archive:
            for suffix, stream in (("shp", shp), ("shx", shx), ("dbf", dbf)):
                archive.writestr(f"{stem}.{suffix}", stream.getvalue())
            archive.writestr(f"{stem}.prj", "GEOGCS[\"WGS 84\"]")

    def test_complete_month_is_imported_and_repeat_is_idempotent(self):
        for offset in range(31):
            self.make_day(date(2024, 7, 1) + timedelta(days=offset))
        arguments = dict(month="2024-07", bbox=(-122, 39, -120, 41), directory=self.directory)
        first = harvest_month(self.db, **arguments)
        self.assertEqual(first["days_verified"], 31)
        self.assertEqual(first["rows_inserted"], 31)
        summary = calendar(self.db, bbox=arguments["bbox"], year=2024, series="hms-viirs")
        self.assertTrue(summary["monthly"][6]["export_window_complete"])
        self.assertEqual(summary["monthly"][6]["detected_cell_days"], 31)
        self.assertEqual(summary["daily"][0]["detected_cell_days"], None)
        self.assertEqual(harvest_month(self.db, **arguments)["rows_inserted"], 0)
        row = self.db.execute("SELECT raw_json FROM observations LIMIT 1").fetchone()
        self.assertIn("hms_archive_sha256", row["raw_json"])
        self.assertIn("nominal VIIRS", row["raw_json"])

    def test_missing_daily_archive_does_not_mark_month_complete(self):
        self.make_day(date(2024, 7, 1))
        with patch("fireatlas.hms.urlopen", side_effect=TimeoutError()):
            with self.assertRaisesRegex(ValueError, "archive unavailable"):
                harvest_month(self.db, month="2024-07", bbox=(-122, 39, -120, 41), directory=self.directory)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM export_windows").fetchone()[0], 0)

    def test_bundled_authentic_showcase_reproduces_baseline(self):
        database = self.root / "showcase.sqlite3"
        first = populate_showcase(database)
        self.assertTrue(first["loaded"])
        self.assertEqual([month["rows"] for month in first["months"]], [33024, 76, 177, 16143])
        self.assertFalse(populate_showcase(database)["loaded"])
        with connect(database) as db:
            result = calendar(db, bbox=(-122, 39, -120, 41), year=2024, series="hms-viirs")
            july = result["monthly"][6]
            self.assertFalse(result["demo_data"])
            self.assertEqual(july["baseline_years"], [2021, 2022, 2023])
            self.assertEqual(july["baseline_median"], 109)
            self.assertEqual(july["detected_cell_days"], 2197)


if __name__ == "__main__":
    unittest.main()
