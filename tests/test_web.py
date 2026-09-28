from __future__ import annotations

import contextlib
import io
import json
import tempfile
import threading
import unittest
import zipfile
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen, Request

from fireatlas.demo import make_demo
from fireatlas.core import connect
from fireatlas.web import handler_factory


class WebMvpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        database = root / "demo.sqlite3"
        with contextlib.redirect_stdout(io.StringIO()):
            make_demo(root / "demo", database)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(database))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def get(self, path):
        with urlopen(self.base + path) as response:
            return response.headers, response.read()

    def test_calendar_map_observations_and_exports(self):
        _, home = self.get("/")
        self.assertIn(b"Burning activity calendar", home)
        self.assertIn(b"earth-frame-host", home)
        _, earth = self.get("/earth.html")
        self.assertIn(b"Earth \xe2\x80\x94 An orbital portrait", earth)
        self.assertGreater(len(earth), 10_000_000)
        _, terrain = self.get("/terrain-earth.html")
        self.assertIn(b"world-elevation", terrain)
        self.assertIn(b"window.fireAtlasEarth", terrain)
        _, embed = self.get("/earth-embed.js")
        self.assertIn(b"/terrain-earth.html?embed=landing", embed)
        query = "year=2015&series=joint&bbox=-122,39,-120,41"
        _, body = self.get("/api/calendar?" + query)
        result = json.loads(body)
        self.assertEqual(result["monthly"][6]["detected_cell_days"], 4)
        self.assertTrue(result["demo_data"])
        _, body = self.get("/api/map?" + query + "&month=7&zoom=3")
        self.assertEqual(json.loads(body)["mode"], "aggregates")
        _, body = self.get("/api/map?" + query + "&month=7&zoom=8")
        self.assertEqual(len(json.loads(body)["features"]), 16)
        _, body = self.get("/api/map?" + query + "&month=7&day=1&zoom=8")
        daily_map = json.loads(body)
        self.assertEqual(daily_map["scope_date"], "2015-07-01")
        self.assertEqual(len(daily_map["features"]), 4)
        with self.assertRaises(HTTPError):
            self.get("/api/map?" + query + "&month=7&day=32&zoom=8")
        _, body = self.get("/api/observations?date=2015-07-01&series=joint&bbox=-122,39,-120,41")
        self.assertEqual(len(json.loads(body)["observations"]), 4)
        headers, body = self.get("/api/export?kind=calendar&" + query)
        self.assertIn("text/csv", headers["Content-Type"])
        self.assertIn(b"baseline_median", body)
        _, body = self.get("/api/export?kind=observations&" + query)
        self.assertEqual(body.count(b"2015-07-01T12:34:00Z"), 4)

    def test_invalid_aoi_returns_error(self):
        with self.assertRaises(HTTPError) as caught:
            self.get("/api/calendar?year=2015&bbox=bad")
        self.assertEqual(caught.exception.code, 400)

    def test_data_status_and_cross_origin_sync_rejection(self):
        _, page = self.get("/data.html")
        self.assertIn(b"NASA FIRMS", page)
        _, body = self.get("/api/data/status")
        status = json.loads(body)
        self.assertTrue(status["synthetic"])
        self.assertEqual(len(status["pilots"]), 2)
        request = Request(self.base + "/api/data/sync", data=b"{}", headers={"Content-Type":"application/json", "Origin":"https://other.example"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(caught.exception.code, 403)

    def test_cached_eonet_feed_is_separate_from_firms_data(self):
        cache = Path(self.temp.name) / "demo.events.json"
        cache.write_text(json.dumps({"kind": "reported-wildfire-events", "fetched_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                                     "count": 1, "events": [{"id": "EONET_123", "title": "Wildfire report"}]}))
        _, body = self.get("/api/events")
        feed = json.loads(body)
        self.assertEqual(feed["count"], 1)
        self.assertEqual(feed["kind"], "reported-wildfire-events")
        _, body = self.get("/api/calendar?year=2015&series=joint&bbox=-122,39,-120,41")
        self.assertEqual(json.loads(body)["monthly"][6]["detected_cell_days"], 4)

    def test_demo_mode_is_explicit_and_separate_from_authentic_dataset(self):
        real = Path(self.temp.name) / "authentic.sqlite3"
        with connect(real):
            pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(real))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"
        def read(path):
            with urlopen(base + path) as response:
                return json.load(response)
        self.assertEqual(read("/api/meta?demo=0")["years"], [])
        self.assertIn(2015, read("/api/meta?demo=1")["years"])
        query = "year=2015&series=joint&bbox=-122,39,-120,41"
        real_calendar = read(f"/api/calendar?demo=0&{query}")
        demo_calendar = read(f"/api/calendar?demo=1&{query}")
        self.assertIsNone(real_calendar["monthly"][6]["detected_cell_days"])
        self.assertEqual(demo_calendar["monthly"][6]["detected_cell_days"], 4)
        self.assertEqual(read(f"/api/observations?demo=0&date=2015-07-01&series=joint&bbox=-122,39,-120,41")["observations"], [])
        self.assertEqual(len(read(f"/api/observations?demo=1&date=2015-07-01&series=joint&bbox=-122,39,-120,41")["observations"]), 4)
        self.assertEqual(read("/api/research?demo=0")["raw_pixels"], 0)
        self.assertEqual(read("/api/research?demo=1")["raw_pixels"], 16)
        self.assertEqual(read("/api/data/status")["synthetic"], False)
        with self.assertRaises(HTTPError) as caught:
            read("/api/meta?demo=maybe")
        self.assertEqual(caught.exception.code, 400)

    def test_study_download_and_invalid_day(self):
        headers, body = self.get("/api/study?year=2015&month=7&day=2015-07-01")
        self.assertEqual(headers["Content-Type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            self.assertIn("observations.json", z.namelist())
        with self.assertRaises(HTTPError) as caught:
            self.get("/api/study?year=2015&month=7&day=2014-07-01")
        self.assertEqual(caught.exception.code, 400)

    def test_training_routes_and_causal_snapshots(self):
        _, page = self.get("/training.html")
        self.assertIn(b"SIMULATED EXERCISE", page)
        _, body = self.get("/api/training/scenario")
        self.assertTrue(json.loads(body)["synthetic"])
        _, body = self.get("/api/training/snapshot?elapsed=1199")
        data = json.loads(body)
        self.assertEqual(data["zone"]["id"], "zone-1")
        self.assertEqual(len(data["observations"]), 1)
        for invalid in ["-1", "3601", "nan", "1.5"]:
            with self.assertRaises(HTTPError) as caught:
                self.get("/api/training/snapshot?elapsed=" + invalid)
            self.assertEqual(caught.exception.code, 400)

    def test_research_report_mask_import_and_input_validation(self):
        _, page = self.get("/research.html")
        self.assertIn(b"EXPLORATORY RESEARCH", page)
        _, body = self.get("/api/research")
        report = json.loads(body)
        self.assertEqual(report["raw_pixels"], 16)
        self.assertEqual(report["coverage"]["status"], "unavailable")
        _, body = self.get("/api/research/coverage-example")
        mask = json.loads(body)
        request = Request(self.base + "/api/research", data=json.dumps({"config": report["config"], "mask": mask}).encode(), headers={"Content-Type": "application/json"})
        with urlopen(request) as response:
            imported = json.load(response)
        self.assertEqual(imported["coverage"]["sources"][0]["observed_cell_days"], 31)
        for payload in [[], {"config": {"month": 50}}, {"config": {}, "mask": {}}]:
            request = Request(self.base + "/api/research", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
            with self.assertRaises(HTTPError) as caught:
                urlopen(request)
            self.assertEqual(caught.exception.code, 400)


if __name__ == "__main__":
    unittest.main()

class CsvImportTests(unittest.TestCase):
    def test_local_import_is_atomic_idempotent_and_preserves_partial_state(self):
        from test_phase1 import row, write_csv
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / 'real.sqlite3'
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler_factory(database))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            file = root / 'input.csv'
            try:
                def upload(source='VIIRS_NOAA20_NRT', suffix='', origin=base):
                    request = Request(base + '/api/data/import?source=' + source + suffix, data=file.read_bytes(),
                                      headers={'Content-Type':'text/csv', 'Origin':origin})
                    with urlopen(request) as response:
                        return json.load(response)
                write_csv(file, [row(instrument='VIIRS', satellite='N20', version='2.0NRT')])
                self.assertEqual(upload()['import']['rows_inserted'], 1)
                self.assertTrue(upload()['import']['already_imported'])
                with urlopen(base + '/api/calendar?year=2024&series=viirs-noaa20-nrt&bbox=-122,39,-120,41') as response:
                    self.assertIsNone(json.load(response)['monthly'][6]['detected_cell_days'])
                for source in ('VIIRS_SNPP_NRT', 'VIIRS_NOAA20_SP'):
                    with self.assertRaises(HTTPError) as caught:
                        upload(source)
                    self.assertEqual(caught.exception.code, 400)
                with self.assertRaises(HTTPError) as caught:
                    upload(origin='https://other.example')
                self.assertEqual(caught.exception.code, 403)
                write_csv(file, [row(instrument='VIIRS', satellite='N20', version='2.0NRT'), row(instrument='VIIRS', satellite='N20', acq_date='2024-08-01')])
                with self.assertRaises(HTTPError):
                    upload(suffix='&complete_month=2024-07&bbox=-122,39,-120,41')
                with connect(database) as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM observations').fetchone()[0], 1)
                    self.assertEqual(db.execute('SELECT count(*) FROM export_windows').fetchone()[0], 0)
                write_csv(file, [row()])
                upload('MODIS_SP', '&complete_month=2024-07&bbox=-122,39,-120,41')
                with urlopen(base + '/api/data/status') as response:
                    status = json.load(response)
                self.assertEqual(status['sync']['completed'], 1)
                self.assertEqual(status['sources'][0]['latest_window']['month'], '2024-07')
            finally:
                server.shutdown()
                server.server_close()
