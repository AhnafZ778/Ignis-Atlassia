from __future__ import annotations

import contextlib
import gzip
import io
import json
import tempfile
import threading
import unittest
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen, Request

from fireatlas.demo import make_demo
from fireatlas.core import connect
from fireatlas.research import coverage_example
from fireatlas.web import handler_factory


class WebMvpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        database = root / "demo.sqlite3"
        self.database = database
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

    def test_winning_plan_safety_and_data_disclosures(self):
        limit = b"Ignis-Atlassia is a research and learning tool. It is not an operational fire-management, evacuation, or flight-planning tool."
        _, home = self.get("/")
        self.assertIn(limit, home)
        _, method = self.get("/method.html")
        self.assertIn(limit, method)
        _, sources = self.get("/data.html")
        self.assertIn(b"archive-coverage", sources)
        self.assertIn(b"Source versions, request dates and file fingerprints", sources)
        self.assertIn(b"/docs/DATA.md", sources)
        self.assertIn(b"AI assistance helped with code and documentation", sources)
        self.assertIn(b"No independent scientific reviewer is recorded yet", sources)

    def test_native_review_form_is_served_and_hash_bound_template_is_available(self):
        _, page = self.get("/review.html?case=grove-2025")
        self.assertIn(b"id=\"review-samples\"", page)
        self.assertIn(b"Download review JSON", page)
        _, script = self.get("/review.js")
        self.assertIn(b"input_hashes", script)
        _, template_body = self.get("/api/validity/review-template?case=grove-2025")
        template = json.loads(template_body)
        self.assertEqual(template["schema"], "fireatlas-native-mask-review-v1")
        self.assertEqual(template["case_id"], "grove-2025")
        self.assertIn("input_hashes", template)

    def test_live_region_archive_ledger_is_served(self):
        _, body = self.get("/api/v2/regions")
        status = json.loads(body)
        self.assertEqual([item["id"] for item in status["regions"]], ["norcal", "punjab-haryana"])
        for region in status["regions"]:
            for product in region["products"].values():
                self.assertIn("complete_months", product)
                self.assertIn("missing_months", product)
        _, page = self.get("/data.html")
        self.assertIn(b'id="archive-region-list"', page)
        self.assertIn(b"Which months are actually loaded?", page)

    def test_paired_daily_evidence_bundles_download_from_data_page(self):
        _, page = self.get("/data.html")
        self.assertIn(b"Reproducible daily bundles", page)
        for region in ("norcal", "punjab-haryana"):
            headers, compressed = self.get(f"/samples/aggregates/{region}.json.gz")
            self.assertEqual(headers["Content-Type"], "application/gzip")
            evidence = json.loads(gzip.decompress(compressed))
            self.assertEqual(evidence["schema"], "fireatlas-daily-aggregates-v1")
            self.assertEqual(evidence["region"]["id"], region)
            self.assertEqual(len(evidence["days"]), 1430)
            self.assertEqual(len(evidence["inputs"]), 8)

    def test_calibration_artifacts_are_downloadable_and_method_page_uses_them(self):
        _, page = self.get("/method.html")
        self.assertIn(b'id="calibration-download"', page)
        self.assertIn(b'id="calibration-provenance"', page)
        _, script = self.get("/calibration-validation.js")
        self.assertIn(b"new URL(`samples/calibration/", script)
        self.assertIn(b"document.baseURI", script)
        self.assertNotIn(b"/api/v2/calendar?", script)
        for region in ("norcal", "punjab-haryana"):
            headers, body = self.get(f"/samples/calibration/{region}.json")
            self.assertIn("application/json", headers["Content-Type"])
            artifact = json.loads(body)
            self.assertEqual(artifact["schema"], "fireatlas-calibration-artifact-v1")
            self.assertEqual(artifact["region"]["id"], region)
            self.assertEqual(len(artifact["provenance"]["paired_complete_months"]), 47)

    def test_calendar_map_observations_and_exports(self):
        _, home = self.get("/")
        self.assertIn(b"Burning activity calendar", home)
        self.assertIn(b"NASA SPACE APPS 2026", home)
        self.assertIn(b'id="harm-official-links"', home)
        _, calendar_script = self.get("/harmonized.js")
        self.assertIn(b"state?.availability?.notices", calendar_script)
        self.assertIn(b"Open NASA product notice", calendar_script)
        self.assertIn(b"harm-season-context", home)
        self.assertIn(b"2024 paddy-harvest monitoring", calendar_script)
        self.assertIn(b"PRID=2060764", calendar_script)
        self.assertIn(b"do not confirm crop-residue fires", calendar_script)
        self.assertIn(b"VISIBLE SENSOR BRIDGE", home)
        self.assertIn(b"RAW FRP CONTEXT", home)
        self.assertIn(b"MCD64A1", home)
        self.assertIn(b'id="harm-share-card"', home)
        self.assertIn(b'id="harm-build-meta"', home)
        self.assertIn(b'id="harm-bridge-method"', home)
        self.assertIn(b"INPUTS + HASH", home)
        self.assertIn(b"cyan solid", home)
        self.assertIn(b"purple hatch", home)
        self.assertIn(b"gray crosshatch", home)
        _, validity_script = self.get("/validity.js")
        self.assertIn(b"validity-unknown", validity_script)
        _, validity_style = self.get("/validity.css")
        self.assertIn(b"same state grammar", validity_style)
        calendar_panel = home.split(b'<section id="harmonized-calendar"', 1)[1]
        verdict_index = calendar_panel.index(b'id="harm-verdict"')
        links_index = calendar_panel.index(b'id="harm-official-links"')
        heading_index = calendar_panel.index(b'class="harmonized-heading"')
        self.assertLess(verdict_index, links_index)
        self.assertLess(links_index, heading_index)
        self.assertNotIn(b"archive-timeline", home)
        self.assertIn(b"earth-frame-host", home)
        self.assertIn(b'id="globe-markers"', home)
        self.assertIn(b'id="globe-wildfires"', home)
        self.assertIn(b"/globe.js", home)
        headers, wildfire_data = self.get("/documented-fires.json")
        self.assertIn("application/json", headers["Content-Type"])
        casebook = json.loads(wildfire_data)
        embedded_casebook = json.loads(home.split(b'<script id="globe-wildfire-data" type="application/json">', 1)[1].split(b'</script>', 1)[0])
        self.assertEqual(embedded_casebook, casebook)
        self.assertEqual(casebook["kind"], "selected-global-wildfire-casebook")
        self.assertEqual(len(casebook["events"]), 15)
        self.assertTrue(all(-90 <= event["lat"] <= 90 and -180 <= event["lon"] <= 180 for event in casebook["events"]))
        self.assertTrue(all(event["id"] and event["name"] and event["place"] and event["period"] and event["summary"] and event["sources"] for event in casebook["events"]))
        _, earth = self.get("/earth.html")
        self.assertIn(b"Earth \xe2\x80\x94 An orbital portrait", earth)
        self.assertIn(b"window.fireAtlasEarth", earth)
        self.assertGreater(len(earth), 10_000_000)
        _, terrain = self.get("/terrain-earth.html")
        self.assertIn(b"world-elevation", terrain)
        self.assertIn(b"window.fireAtlasEarth", terrain)
        _, embed = self.get("/earth-embed.js")
        self.assertIn(b"/terrain-earth.html?embed=landing", embed)
        self.assertNotIn(b"/earth.html?embed=landing", embed)
        self.assertIn(b"native projection bridge", embed)
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

    def test_historical_responder_brief_is_bounded_and_evidence_linked(self):
        _, body = self.get("/api/briefing?year=2015&month=7&series=joint&bbox=-122,39,-120,41")
        brief = json.loads(body)
        self.assertEqual(brief["schema"], "fireatlas-responder-briefing-v1")
        self.assertEqual(brief["classification"], "synthetic")
        self.assertTrue(brief["historical_only"])
        self.assertFalse(brief["operational"])
        self.assertEqual(brief["selected_month"]["detected_cell_days"], 4)
        self.assertEqual(brief["active_days_count"], 4)
        self.assertEqual(brief["observed_days"], 31)
        self.assertEqual(brief["unknown_days"], 0)
        self.assertEqual(len(brief["active_days"]), 4)
        self.assertIn("not integrated", brief["context"]["terrain"])
        self.assertTrue(any("perimeter" in item for item in brief["limitations"]))

    def test_harmonization_audit_exposes_common_grid_and_source_limits(self):
        _, body = self.get("/api/harmonization?year=2015&month=7&series=joint&bbox=-122,39,-120,41")
        audit = json.loads(body)
        self.assertEqual(audit["schema"], "fireatlas-harmonization-audit-v1")
        self.assertEqual(audit["status"], "descriptive-pair-available")
        self.assertEqual(audit["raw_pixels_total"], 16)
        self.assertEqual(audit["detected_cell_days"], 4)
        self.assertEqual(audit["co_detected_cell_days"], 4)
        self.assertEqual([item["raw_pixels"] for item in audit["sources"]], [4, 12])
        self.assertTrue(all("unknown" in item for item in audit["limits"] if "coverage" in item))

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

    def test_region_calendar_api_is_named_scoped_and_never_fabricates_empty_data(self):
        _, body = self.get("/api/v2/regions")
        status = json.loads(body)
        self.assertEqual({item["id"] for item in status["regions"]}, {"norcal", "punjab-haryana"})
        _, body = self.get("/api/v2/calendar?region=norcal&year=2024&month=7")
        data = json.loads(body)
        self.assertEqual(data["schema"], "fireatlas-calendar-v2")
        self.assertEqual(data["meta"]["data_class"], "no-authentic-imports")
        self.assertEqual(data["meta"]["period"]["selected_month"], 7)
        self.assertIn("common 1 km grid", data["meta"]["primary_measure"])
        self.assertEqual(data["meta"]["corroboration"]["status"], "not-loaded")
        self.assertEqual(data["days"][0]["sensor_bridge"]["status"], "partial")
        self.assertIn("July 2024", data["meta"]["verdict"])
        self.assertEqual(len(data["days"]), 366)
        self.assertEqual(len(data["months"]), 12)
        self.assertTrue(all(item["value"] is None for item in data["days"]))
        _, body = self.get("/api/v2/calendar?region=norcal&year=2024&month=7&history=1")
        history = json.loads(body)["history"]
        self.assertEqual(history["start"], "2006-07-01")
        self.assertEqual(history["days"][0]["date"], "2006-07-01")
        self.assertIsNone(history["days"][0]["value"])
        with self.assertRaises(HTTPError) as caught:
            self.get("/api/v2/calendar?region=world&year=2024")
        self.assertEqual(caught.exception.code, 400)

    def test_linked_data_import_documents_are_served(self):
        for route, expected in (("/docs/NASA_DATA_IMPORT.md", b"Import the longer NASA FIRMS archive"),
                                ("/docs/DATA.md", b"July 2010"),
                                ("/docs/AI_USE.md", b"AI")):
            headers, body = self.get(route)
            self.assertEqual(headers.get_content_type(), "text/markdown")
            self.assertIn(expected, body)

    def test_synthetic_mode_and_showcase_routes_are_retired(self):
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
        self.assertEqual(read("/api/meta")["years"], [])
        query = "year=2015&series=joint&bbox=-122,39,-120,41"
        real_calendar = read(f"/api/calendar?{query}")
        self.assertIsNone(real_calendar["monthly"][6]["detected_cell_days"])
        authentic_brief = read(f"/api/briefing?{query}&month=7")
        self.assertEqual(authentic_brief["classification"], "authentic-imported")
        self.assertEqual(authentic_brief["status"], "insufficient-evidence")
        self.assertTrue(authentic_brief["historical_only"])
        authentic_audit = read(f"/api/harmonization?{query}&month=7")
        self.assertEqual(authentic_audit["status"], "missing-complete-source-export")
        self.assertEqual(authentic_audit["data_class"], "authentic-imported")
        self.assertEqual(read("/api/observations?date=2015-07-01&series=joint&bbox=-122,39,-120,41")["observations"], [])
        self.assertEqual(read("/api/research")["raw_pixels"], 0)
        self.assertEqual(read("/api/data/status")["synthetic"], False)
        for path in ("/api/meta?demo=1", "/api/calendar?demo=0", "/api/research?demo=1"):
            with self.subTest(path=path), self.assertRaises(HTTPError) as caught:
                read(path)
            self.assertEqual(caught.exception.code, 400)
        for path in ("/api/presentation", "/api/context?year=2026", "/api/research/coverage-example"):
            with self.subTest(path=path), self.assertRaises(HTTPError) as caught:
                read(path)
            self.assertEqual(caught.exception.code, 404)

    def test_study_download_and_invalid_day(self):
        headers, body = self.get("/api/study?year=2015&month=7&day=2015-07-01")
        self.assertEqual(headers["Content-Type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            self.assertIn("observations.json", z.namelist())
        with self.assertRaises(HTTPError) as caught:
            self.get("/api/study?year=2015&month=7&day=2014-07-01")
        self.assertEqual(caught.exception.code, 400)

    def test_archived_training_page_and_api_are_not_served(self):
        for path in ("/training.html", "/api/training/scenario", "/api/training/snapshot"):
            with self.subTest(path=path), self.assertRaises(HTTPError) as caught:
                self.get(path)
            self.assertEqual(caught.exception.code, 404)

    def test_removed_pwa_assets_are_not_served(self):
        for path in ("/install.html", "/install.js", "/manifest.webmanifest",
                     "/app-sw.js", "/offline.html", "/app-icon-192.png"):
            with self.subTest(path=path), self.assertRaises(HTTPError) as caught:
                self.get(path)
            self.assertEqual(caught.exception.code, 404)

    def test_eonet_world_snapshot_and_feed_are_retired(self):
        for path in ("/api/events", "/events.js"):
            with self.subTest(path=path), self.assertRaises(HTTPError) as caught:
                self.get(path)
            self.assertEqual(caught.exception.code, 404)
        _, home = self.get("/")
        _, data = self.get("/data.html")
        for page in (home, data):
            self.assertNotIn(b"live-events", page)
            self.assertNotIn(b"NASA EONET", page)

    def test_research_report_mask_import_and_input_validation(self):
        _, page = self.get("/research.html")
        self.assertIn(b"EXPLORATORY RESEARCH", page)
        _, body = self.get("/api/research")
        report = json.loads(body)
        self.assertEqual(report["raw_pixels"], 16)
        self.assertEqual(report["coverage"]["status"], "unavailable")
        with connect(self.database) as db:
            mask = coverage_example(db, year=2015, month=7, bbox=[-122,39,-120,41])
        with self.assertRaises(HTTPError) as caught:
            self.get("/api/research/coverage-example")
        self.assertEqual(caught.exception.code, 404)
        request = Request(self.base + "/api/research", data=json.dumps({"config": report["config"], "mask": mask}).encode(), headers={"Content-Type": "application/json"})
        with urlopen(request) as response:
            imported = json.load(response)
        self.assertEqual(imported["coverage"]["sources"][0]["observed_cell_days"], 31)
        request = Request(self.base + "/api/research?demo=1", data=json.dumps({"config": report["config"], "mask": mask}).encode(), headers={"Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(caught.exception.code, 400)
        for payload in [[], {"config": {"month": 50}}, {"config": {}, "mask": {}}]:
            request = Request(self.base + "/api/research", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
            with self.assertRaises(HTTPError) as caught:
                urlopen(request)
            self.assertEqual(caught.exception.code, 400)


if __name__ == "__main__":
    unittest.main()

class CsvImportTests(unittest.TestCase):
    def test_local_import_is_atomic_idempotent_and_preserves_partial_state(self):
        try:
            from .test_phase1 import row, write_csv
        except ImportError:
            from tests.test_phase1 import row, write_csv
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
