import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen
import zipfile

from fireatlas.core import calendar, connect, ingest
from fireatlas.presentation import BBOX, PREFIX, SEEDS, context_fixture, ensure_presentation
from fireatlas.research import coverage_example, report
from fireatlas.study import build_bundle, verify_bundle
from fireatlas.web import handler_factory, main


class PresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.database = cls.root / "demo.sqlite3"
        ensure_presentation(cls.root / "csv", cls.database)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_full_year_baselines_and_idempotent_seed_provenance(self):
        with connect(self.database) as db:
            count = db.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
            hashes = list(db.execute("SELECT file_sha256 FROM batches ORDER BY id"))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM batches").fetchone()[0], 96)
            self.assertFalse(db.execute("SELECT 1 FROM batches WHERE demo=0").fetchone())
            cal = calendar(db, year=2026, series="joint", bbox=BBOX)
            self.assertTrue(cal["demo_data"])
            for month in cal["monthly"]:
                self.assertTrue(month["export_window_complete"])
                self.assertEqual(month["baseline_years"], [2023, 2024, 2025])
                self.assertGreater(month["detected_cell_days"], 0)
            self.assertGreater(cal["monthly"][8]["detected_cell_days"], cal["monthly"][0]["detected_cell_days"])
            seeds = {f["sha256"] for f in json.loads(SEEDS.read_text())["files"]}
            for row in db.execute("SELECT raw_json,source_uri FROM observations"):
                raw = json.loads(row[0])
                self.assertEqual(raw["synthetic"], "true")
                self.assertIn(raw["seed_file_sha256"], seeds)
                self.assertTrue(row[1].startswith(PREFIX))
        ensure_presentation(self.root / "csv", self.database)
        with connect(self.database) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM observations").fetchone()[0], count)
            self.assertEqual(list(db.execute("SELECT file_sha256 FROM batches ORDER BY id")), hashes)

    def test_research_has_overlap_band_groups_and_explicit_exposure(self):
        with connect(self.database) as db:
            study = report(db, year=2026, month=9)
            self.assertTrue(study["demo_data"])
            self.assertTrue(study["presentation"]["synthetic"])
            self.assertEqual(len(study["presentation"]["seed_files"]), 3)
            self.assertEqual(study["overlap"]["band_status"], "exploratory")
            self.assertEqual(study["candidates"]["count"], 3)
            self.assertEqual(study["coverage"]["status"], "unavailable")
            mask = coverage_example(db, year=2026, month=9, bbox=BBOX)
            exposed = report(db, year=2026, month=9, mask=mask)
            self.assertEqual(exposed["coverage"]["status"], "synthetic")
            for source in exposed["coverage"]["sources"]:
                self.assertEqual(source["detections_without_mask"], 0)
                self.assertGreater(source["per_100_observed_cell_days"], 0)
                self.assertLessEqual(source["per_100_observed_cell_days"], 100)
            cutoff = report(db, year=2026, month=9, as_of="2026-09-07")
            self.assertLess(cutoff["raw_pixels"], study["raw_pixels"])
            self.assertTrue(all(d["date"] <= "2026-09-07" for d in cutoff["overlap"]["daily"]))

    def test_context_is_bounded_labelled_and_reproducible(self):
        for layer in ("ndvi", "landcover", "fwi"):
            args = dict(year=2026, month=9, bbox=BBOX, layer=layer)
            data = context_fixture(**args)
            self.assertTrue(data["synthetic"])
            self.assertEqual(len(data["features"]), 100)
            self.assertEqual(data, context_fixture(**args))
            self.assertEqual(context_fixture(**(args | {"bbox": (0, 0, 1, 1)}))["features"], [])
            for f in data["features"]:
                self.assertTrue(f["properties"]["synthetic"])
                if layer == "ndvi": self.assertTrue(-1 <= f["properties"]["value"] <= 1)
        with self.assertRaises(ValueError):
            context_fixture(year=2015, month=7, bbox=BBOX, layer="fwi")

    def test_bundle_reproduces_and_carries_synthetic_context(self):
        with connect(self.database) as db:
            body = build_bundle(db, year=2026, month=9, series="joint", bbox=BBOX, layer="fwi")
        result = verify_bundle(io.BytesIO(body))
        self.assertTrue(result["verified"])
        self.assertEqual(result["data_class"], "synthetic")
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertTrue(json.loads(archive.read("presentation-provenance.json"))["synthetic"])
            self.assertTrue(json.loads(archive.read("synthetic-context.geojson"))["synthetic"])

    def test_refuses_authentic_database_without_modifying_it(self):
        real = self.root / "guard.sqlite3"
        with connect(real) as db:
            ingest(db, self.root / "csv" / "MODIS_SP_2023_01.csv", "MODIS_SP", demo=False)
        before = hashlib.sha256(real.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "dedicated synthetic"):
            ensure_presentation(self.root / "guard", real)
        self.assertEqual(hashlib.sha256(real.read_bytes()).hexdigest(), before)

    def test_synthetic_http_mode_and_showcase_routes_are_retired(self):
        # Isolated path avoids mutating the shared fixture or any user database.
        real = self.root / "http" / "real.sqlite3"
        with connect(real): pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(real))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(f"http://127.0.0.1:{server.server_port}/") as response:
                home = response.read()
            self.assertNotIn(b"data-demo", home)
            self.assertNotIn(b"story.js", home)
            self.assertIn(b'id="start-calendar-tour"', home)
            self.assertIn(b'id="calendar-tour"', home)
            with urlopen(f"http://127.0.0.1:{server.server_port}/tour.js") as response:
                tour_js = response.read()
            self.assertIn(b"/api/calendar", tour_js)
            self.assertIn(b"#calendar-day-summary", tour_js)
            self.assertIn(b"/api/observations", tour_js)
            self.assertNotIn(b"synthetic", tour_js.lower())
            with urlopen(f"http://127.0.0.1:{server.server_port}/tour.css") as response:
                self.assertIn(b".calendar-tour", response.read())
            with urlopen(f"http://127.0.0.1:{server.server_port}/data.html") as response:
                self.assertNotIn(b"presentation-data", response.read())
            with urlopen(f"http://127.0.0.1:{server.server_port}/research.html") as response:
                self.assertNotIn(b"example-mask", response.read())
            def read(path):
                with urlopen(f"http://127.0.0.1:{server.server_port}{path}") as response:
                    return json.load(response)
            self.assertEqual(read("/api/meta")["years"], [])
            self.assertIsNone(read("/api/calendar?year=2015&series=joint")["monthly"][6]["detected_cell_days"])
            for path in ("/api/meta?demo=1", "/api/calendar?demo=0"):
                with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                    read(path)
                self.assertEqual(error.exception.code, 400)
            for path in ("/api/presentation", "/api/context?year=2026&month=9&layer=ndvi", "/api/research/coverage-example"):
                with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                    read(path)
                self.assertEqual(error.exception.code, 404)
            with patch("sys.argv", ["fireatlas.web", "--db", str(self.database), "--no-showcase"]):
                with self.assertRaisesRegex(SystemExit, "Refusing to serve a database containing synthetic"):
                    main()
        finally:
            server.shutdown()
            server.server_close()
