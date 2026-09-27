import csv
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from fireatlas.core import REQUIRED_COLUMNS, connect
from fireatlas.fetch import availability, fetch_month
from fireatlas.pilots import PILOTS, PilotSync
from fireatlas.settings import firms_key


class Response:
    def __init__(self, body): self.body = body.encode()
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def read(self): return self.body


class PilotTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.database = self.root / "real.sqlite3"
        self.env = patch.dict(os.environ, {"FIRMS_MAP_KEY": "test-secret", "FIRMS_KEY_FILE": str(self.root / "key")})
        self.env.start(); self.addCleanup(self.env.stop)

    def test_key_file_and_environment_precedence(self):
        key_path = self.root / "key"
        key_path.write_text("file-test-secret\n")
        self.assertEqual(firms_key(), "test-secret")
        with patch.dict(os.environ, {"FIRMS_MAP_KEY": ""}):
            self.assertEqual(firms_key(), "file-test-secret")
            key_path.unlink()
            self.assertIsNone(firms_key())

    def test_network_failure_never_exposes_key(self):
        sync = PilotSync(self.database)
        with patch("fireatlas.fetch.urlopen", side_effect=URLError("https://example/test-secret")):
            sync.run()
        status = sync.status()
        self.assertEqual(status["sync"]["status"], "failed")
        self.assertNotIn("test-secret", json.dumps(status))
        self.assertNotIn("test-secret", sync.status_path.read_text())
        self.assertEqual(status["sources"], [])

    def test_failed_month_has_no_complete_export_or_partial_cache(self):
        headers = ",".join(sorted(REQUIRED_COLUMNS)) + "\n"
        available = [{"data_id":"MODIS_SP", "min_date":"2000-01-01", "max_date":"2024-12-31"}]
        with connect(self.database) as db, patch("fireatlas.fetch.urlopen", side_effect=[Response(headers), URLError("test-secret"), URLError("test-secret")]):
            with self.assertRaises(ValueError):
                fetch_month(db, month="2024-07", source_id="MODIS_SP", bbox=tuple(PILOTS[0]["bbox"]), directory=self.root / "downloads", available_sources=available)
            self.assertEqual(db.execute("SELECT count(*) FROM export_windows").fetchone()[0], 0)
        self.assertEqual(list((self.root / "downloads").glob("*.csv")), [])

    def test_secondary_recovers_transport_failure_but_not_rate_limit(self):
        body = "data_id,min_date,max_date\nVIIRS_NOAA20_NRT,2026-09-01,2026-09-27\n"
        with patch("fireatlas.fetch.urlopen", side_effect=[URLError("offline"), Response(body)]) as download:
            self.assertEqual(availability()[0]["data_id"], "VIIRS_NOAA20_NRT")
            self.assertIn("firms2.modaps", download.call_args.args[0])
        with patch("fireatlas.fetch.urlopen", side_effect=HTTPError("secret", 429, "limit", {}, None)) as download:
            with self.assertRaisesRegex(ValueError, "HTTP 429"):
                availability()
            self.assertEqual(download.call_count, 1)

    def test_full_empty_pilots_reproduce_and_second_run_skips_completed_downloads(self):
        def fake_open(url, timeout):
            if "data_availability" in url:
                return Response("data_id,min_date,max_date\nMODIS_SP,2000-01-01,2025-12-31\nVIIRS_SNPP_SP,2012-01-01,2025-12-31\n")
            return Response(",".join(sorted(REQUIRED_COLUMNS)) + "\n")
        sync = PilotSync(self.database)
        with patch("fireatlas.fetch.urlopen", side_effect=fake_open) as download:
            sync.run()
            self.assertEqual(download.call_count, 113)  # availability + 16 months * 7 windows
            first = sync.status()
            self.assertEqual(first["sync"]["status"], "complete")
            self.assertEqual(first["sync"]["completed"], 16)
            self.assertEqual(first["sync"]["validation"]["pilots"][0]["baseline_median"], 0)
            self.assertNotIn("test-secret", json.dumps(first))
            download.reset_mock()
            sync.run()
            self.assertEqual(download.call_count, 0)
        with connect(self.database) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM batches").fetchone()[0], 16)

    def test_invalid_api_response_and_interrupted_status(self):
        with patch("fireatlas.fetch.urlopen", return_value=Response("Invalid MAP_KEY: test-secret")):
            with self.assertRaisesRegex(ValueError, "did not accept") as caught:
                availability()
            self.assertNotIn("test-secret", str(caught.exception))
        self.database.with_suffix(".sync.json").write_text('{"status":"downloading","completed":4}')
        sync = PilotSync(self.database)
        self.assertEqual(sync.state["status"], "interrupted")
        self.assertEqual(sync.state["completed"], 4)
