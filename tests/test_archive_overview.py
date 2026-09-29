from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fireatlas.archive import SAMPLE, import_bundle
from fireatlas.archive_overview import archive_overview
from fireatlas.core import connect


class ArchiveOverviewTests(unittest.TestCase):
    def test_only_complete_authentic_pair_windows_feed_the_hero(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "archive.sqlite3"
            self.assertEqual(import_bundle(database)["imported_rows"], 30823)
            with connect(database) as db:
                result = archive_overview(db)

        self.assertEqual(result["schema"], "fireatlas-archive-overview-v1")
        self.assertEqual(result["status"], "verified-pair-windows")
        self.assertEqual(result["paired_month_count"], 42)
        self.assertEqual(result["timeline"][0], {"month": "2022-07", "modis": True, "viirs_snpp": True, "paired": True})
        self.assertEqual(result["timeline"][-1]["month"], "2025-12")
        self.assertEqual(result["scope_bbox"], [-122.2, 38.8, -120.0, 41.0])
        self.assertEqual({item["observation_rows"] for item in result["sources"]}, {7793, 21431})
        self.assertEqual({item["archive_rows"] for item in result["sources"]}, {8151, 22672})

    def test_synthetic_or_empty_databases_do_not_look_like_archive_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            with connect(Path(temporary) / "empty.sqlite3") as db:
                result = archive_overview(db)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["data_class"], "unavailable")
        self.assertEqual(result["paired_months"], [])


if __name__ == "__main__":
    unittest.main()
