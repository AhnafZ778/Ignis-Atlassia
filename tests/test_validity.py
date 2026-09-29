from __future__ import annotations

import hashlib
import io
import json
import tempfile
import threading
import unittest
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from fireatlas.archive import import_bundle
from fireatlas.core import connect
from fireatlas.granules import load as load_granules
from fireatlas.incidents import candidate_rows, evaluate as evaluate_incidents, load as load_incidents
from fireatlas.validity import build_evidence, report, verify_evidence
from fireatlas.web import handler_factory


class HistoricalValidityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.database = Path(cls.temp.name) / "authentic.sqlite3"
        import_bundle(cls.database)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_case_totals_trace_to_authentic_rows_and_keep_coverage_unknown(self):
        with connect(self.database) as db:
            park = report(db, case_id="park-2024", selected_date="2024-07-25")
            grove = report(db, case_id="grove-2025")
        self.assertEqual(park["data_class"], "authentic-imported")
        self.assertEqual(park["days"][8]["joint_detected_cell_days"], len(park["selected_day_cells"]))
        self.assertEqual(park["coverage"]["status"], "unknown")
        self.assertIsNone(park["coverage"]["clear_observed_cell_days"])
        self.assertEqual(park["paired_observation_status"], "unavailable-without-authentic-fire-masks")
        self.assertTrue(all(source["full_month_export"] for source in park["sources"]))
        self.assertTrue(park["first_detection_within_5km_after_reported_start"])
        self.assertTrue(grove["first_detection_within_5km_after_reported_start"])
        self.assertEqual(park["days"][7]["documented_source_notice"], "partial-day")
        self.assertEqual(park["days"][8]["documented_source_notice"], "processing-outage")
        self.assertEqual(park["days"][12]["documented_source_notice"], None)
        self.assertEqual(park["days"][8]["raw_pixels"]["VIIRS_SNPP_SP"], 0)
        self.assertEqual(park["cmr_inventory"]["status"], "metadata-only")
        self.assertEqual({item["product"]: item["cmr_hits"] for item in park["cmr_inventory"]["products"] if item["role"] == "fire-mask"},
                         {"MOD14": 42, "MYD14": 40, "VNP14IMG": 32})
        self.assertEqual([item["companion_geolocation_time_matches"] for item in park["cmr_inventory"]["products"] if item["role"] == "fire-mask"],
                         [42, 40, 32])
        sensitivity = {(item["grid_metres"], item["exclude_low_confidence"]): item
                       for item in park["detection_sensitivity"]}
        self.assertEqual(sensitivity[1000, False]["joint_detected_cell_days"],
                         sum(day["joint_detected_cell_days"] for day in park["days"]))
        self.assertLessEqual(sensitivity[1000, True]["retained_raw_pixels"],
                             sensitivity[1000, False]["retained_raw_pixels"])
        self.assertEqual(park["independent_incidents"]["eligible_additional_incidents"], 25)
        self.assertEqual(park["independent_incidents"]["nearby_detections"], 7)
        self.assertEqual(park["independent_incidents"]["misses"], 18)

    def test_registered_incident_cohort_is_complete_and_recomputed(self):
        cohort = load_incidents()
        self.assertEqual(len(cohort["incidents"]), 288)
        self.assertEqual(sum(row["status"] == "eligible" for row in cohort["incidents"]), 25)
        self.assertTrue(cohort["pages_complete"])
        with connect(self.database) as db:
            candidates = candidate_rows(cohort, db)
        outcome = evaluate_incidents(cohort, candidates=candidates)
        self.assertEqual((outcome["eligible_additional_incidents"], outcome["nearby_detections"], outcome["misses"]), (25, 7, 18))
        self.assertEqual(sum(len(rows) for rows in candidates.values()), 481)

    def test_cmr_inventory_exposes_park_snpp_gap_without_claiming_clear_passes(self):
        inventory = load_granules()
        viirs = next(item for item in inventory["cases"]["park-2024"]["products"]
                     if item["product"] == "VNP14IMG")
        self.assertFalse(any("2024-07-25" <= item["start_utc"][:10] <= "2024-07-28"
                             for item in viirs["granules"]))
        self.assertIn("not been downloaded", inventory["interpretation"])

    def test_verifiable_export_recounts_and_detects_tampering(self):
        with connect(self.database) as db:
            bundle = build_evidence(db, "park-2024")
        result = verify_evidence(io.BytesIO(bundle))
        self.assertTrue(result["valid"])
        self.assertEqual(result["case_id"], "park-2024")
        with zipfile.ZipFile(io.BytesIO(bundle)) as original:
            entries = {name: original.read(name) for name in original.namelist()}
        rows = json.loads(entries["observations.json"])
        rows[0]["grid_x"] += 1
        entries["observations.json"] = json.dumps(rows).encode()
        damaged = io.BytesIO()
        with zipfile.ZipFile(damaged, "w") as output:
            for name, body in entries.items():
                output.writestr(name, body)
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            verify_evidence(io.BytesIO(damaged.getvalue()))
        manifest = json.loads(entries["manifest.json"])
        manifest["files"]["observations.json"] = hashlib.sha256(entries["observations.json"]).hexdigest()
        entries["manifest.json"] = json.dumps(manifest).encode()
        regrouped = io.BytesIO()
        with zipfile.ZipFile(regrouped, "w") as output:
            for name, body in entries.items():
                output.writestr(name, body)
        with self.assertRaisesRegex(ValueError, "grid assignment"):
            verify_evidence(io.BytesIO(regrouped.getvalue()))

    def test_http_case_day_and_download(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(self.database))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"
        with urlopen(base + "/api/validity?case=grove-2025&date=2025-07-05") as response:
            selected = json.load(response)
        self.assertEqual(selected["selected_date_utc"], "2025-07-05")
        with urlopen(base + "/api/validity/export?case=grove-2025") as response:
            self.assertEqual(response.headers["Content-Type"], "application/zip")
            self.assertTrue(verify_evidence(io.BytesIO(response.read()))["valid"])
        for path in ("/api/validity?case=park-2024&date=2025-07-04",
                     "/api/validity?case=park-2024&demo=1",
                     "/api/validity?case=unknown"):
            with self.assertRaises(HTTPError):
                urlopen(base + path)

    def test_method_page_recounts_real_exports_and_preserves_scope(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(self.database))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"
        for case_id, expected in (("park-2024", (3137, 1606)), ("grove-2025", (7, 4))):
            with urlopen(base + f"/api/validity/check?case={case_id}") as response:
                result = json.load(response)
            self.assertTrue(result["calculations_reproduce"])
            self.assertFalse(result["independent_scientific_review"])
            self.assertEqual((result["original_pixels"], result["joint_cell_days"]), expected)
            with urlopen(base + f"/api/validity/export?case={case_id}") as response:
                with zipfile.ZipFile(io.BytesIO(response.read())) as exported:
                    digest = hashlib.sha256(exported.read("manifest.json")).hexdigest()
            self.assertEqual(result["manifest_sha256"], digest)
        for query in ("case=park-2024&demo=1", "case=unknown"):
            with self.assertRaises(HTTPError) as failure:
                urlopen(base + "/api/validity/check?" + query)
            self.assertEqual(failure.exception.code, 400)
        with urlopen(base + "/") as response:
            landing = response.read()
        self.assertIn(b'/method.html', landing)
        self.assertNotIn(b'id="challenge-fit"', landing)
        self.assertNotIn(b'id="evidence-section"', landing)
        with urlopen(base + "/method.html") as response:
            method = response.read()
        self.assertIn(b'id="challenge-fit"', method)
        self.assertIn(b'id="source-records"', method)
        for path, content_type in (("/method.css", "text/css"), ("/method.js", "text/javascript")):
            with urlopen(base + path) as response:
                self.assertIn(content_type, response.headers["Content-Type"])
