from __future__ import annotations

import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fireatlas.core import connect
from fireatlas.calendar_v2 import calendar_v2, prepare_calendar_v2
from scripts.export_static import compact_static_validity_report, export_static, _rebase_local_asset_urls


class StaticCalendarExportTests(unittest.TestCase):
    def test_asset_rebasing_preserves_json_pointer_separators(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'assistant-map.js').write_text('window.mapReady=true;')
            page='<a href="/">Home</a><script src="/assistant-map.js"></script><script>const parts=path.split("/");</script>'
            (root/'assistant.html').write_text(page)
            script='const pointer="/frames/6/products/MODIS_SP/detections"; const keys=pointer.slice(1).split("/").map(k=>k.replaceAll("~1","/"));'
            (root/'assistant.js').write_text(script)
            _rebase_local_asset_urls(root)
            self.assertEqual((root/'assistant.js').read_text(),script)
            self.assertIn('href="./"',(root/'assistant.html').read_text())
            self.assertIn('src="./assistant-map.js"',(root/'assistant.html').read_text())
            self.assertIn('path.split("/")',(root/'assistant.html').read_text())
    def test_static_validity_summary_keeps_ui_fields_and_leaves_full_evidence_explicit(self):
        source = {
            "case_id": "park-2024",
            "selected_day_cells": [{"records": [{"source_id": "MODIS_SP"}]}],
            "native_masks": {
                "paired_observations": {"sample_size": 2, "pairs": [{"id": 1}]},
                "reconciliation": {"matched": 3, "results": [{"id": 1}]},
                "raw_mask_review": {"status": "pending", "samples": [{"id": 1}]},
                "selected_day_cells": [{"source_id": "MODIS_SP"}],
            },
        }
        compact = compact_static_validity_report(source)
        self.assertEqual(len(compact["selected_day_cells"]), 1)
        self.assertEqual(compact["native_masks"]["paired_observations"]["sample_size"], 2)
        self.assertNotIn("pairs", compact["native_masks"]["paired_observations"])
        self.assertNotIn("results", compact["native_masks"]["reconciliation"])
        self.assertNotIn("samples", compact["native_masks"]["raw_mask_review"])
        self.assertEqual(compact["static_export"]["schema"], "fireatlas-validity-static-summary-v1")
        self.assertIn("pairs", source["native_masks"]["paired_observations"])

    def test_evidence_card_exposes_traceable_quality_limit_and_link(self):
        html = (Path(__file__).parents[1] / "fireatlas/static/atlas.html").read_text(encoding="utf-8")
        script = (Path(__file__).parents[1] / "fireatlas/static/harmonized.js").read_text(encoding="utf-8")
        for element in ("harm-share-card-quality", "harm-share-card-limit", "harm-share-card-url"):
            self.assertIn(element, html)
        self.assertIn("coverage ${coverageStates.map(readable)", script)
        self.assertIn("ACTIVE FIRE ONLY · pass/cloud coverage unknown", script)
        self.assertIn("function evidenceHref()", script)
        self.assertIn('month.estimate_type === "mixed"', script)
        self.assertIn("paired UTC dates", script)
        self.assertIn("prediction interval withheld", script)
        self.assertIn('id="harm-frp-unit"', html)

    def test_release_shell_exposes_persona_paths_and_pages_artifact(self):
        root = Path(__file__).parents[1]
        home = (root / "fireatlas/static/index.html").read_text(encoding="utf-8")
        atlas = (root / "fireatlas/static/atlas.html").read_text(encoding="utf-8")
        css = (root / "fireatlas/static/harmonized.css").read_text(encoding="utf-8")
        workflow = (root / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        # The landing page stays globe-led; atlas-specific journeys and calendar
        # evidence live with the analytical workflow.
        self.assertIn('id="earth-frame-host"', home)
        self.assertIn('id="decision-paths"', atlas)
        # The earlier redesign replaced persona captions with scientific
        # workflow links. Check that each destination still preserves context.
        for route in ("replay.html", "research.html", "method.html"):
            self.assertIn(f'href="./{route}"', atlas)
        self.assertIn(".harm-persona-panel", css)
        self.assertIn("path: site", workflow)
        self.assertTrue((root / "fireatlas/static/.nojekyll").is_file())
        self.assertIn("!site/**", (root / ".gitignore").read_text(encoding="utf-8"))

    def test_prepared_region_data_reuses_the_same_calendar_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "empty.sqlite3"
            with connect(db_path) as db:
                prepared = prepare_calendar_v2(db, region="norcal", fallback_year=2024)
                reused = calendar_v2(db, region="norcal", year=2024, month=7,
                                     include_history=True, prepared=prepared)
                direct = calendar_v2(db, region="norcal", year=2024, month=7,
                                     include_history=True)
            self.assertEqual(reused, direct)

    def test_export_has_both_region_calendars_history_and_compressed_day_rows(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            db_path, static_source, output = root / "empty.sqlite3", root / "assets", root / "site"
            static_source.mkdir()
            (static_source / "index.html").write_text(
                '<!doctype html><html><head></head><body><a href="/">Home</a>'
                '<a href="/data/v2/calendar/norcal/2010.json">Calendar evidence</a>'
                '<link rel="stylesheet" href="/styles.css"><script src="/harmonized.js"></script>'
                '</body></html>', encoding="utf-8")
            (static_source / "styles.css").write_text(".earth{background:url('/earth.svg')}", encoding="utf-8")
            (static_source / "harmonized.js").write_text("fetch('/api/v2/regions')", encoding="utf-8")
            (static_source / "earth.svg").write_text("<svg/>", encoding="utf-8")
            with connect(db_path):
                pass

            result = export_static(db_path, output, static_source=static_source,
                                   first_year=2010, last_year=2010)
            self.assertEqual(result["calendar_count"], 2)
            self.assertEqual(result["regions"], 2)
            self.assertTrue((output / "data/v2/calendar/norcal/2010.json").is_file())
            self.assertTrue((output / "data/v2/calendar/punjab-haryana/2010.json").is_file())
            self.assertTrue((output / "data/v2/history/norcal.json").is_file())
            globe = json.loads(gzip.decompress(
                (output / "data/v2/globe/recent.json.gz").read_bytes()))
            self.assertEqual(globe["schema"], "fireatlas-globe-static-v1")
            self.assertEqual(globe["aggregates"], [])
            self.assertIsNone(globe["latest_observation"])
            observations = json.loads(gzip.decompress(
                (output / "data/v2/observations/norcal/2010.json.gz").read_bytes()))
            self.assertEqual(observations["schema"], "fireatlas-static-observations-v1")
            self.assertEqual(observations["days"], {})
            html = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn('name="fireatlas-static-data"', html)
            self.assertIn('href="./"', html)
            self.assertIn('href="./data/v2/calendar/norcal/2010.json"', html)
            self.assertIn('href="./styles.css"', html)
            self.assertIn('src="./harmonized.js"', html)
            self.assertNotIn(".sqlite3", " ".join(str(path) for path in output.rglob("*")))
            manifest = json.loads((output / "data/v2/manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], "fireatlas-static-site-v1")
            self.assertIn("Older reconstructed-row periods remain partial; missing dates are unknown.",
                          manifest["limitations"])
            self.assertIn("The static globe is a checksummed eight-day imported snapshot, not a live FIRMS feed.",
                          manifest["limitations"])
            self.assertIn("data/v2/globe/recent.json.gz", {entry["path"] for entry in manifest["files"]})
            for entry in manifest["files"]:
                content = (output / entry["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(content).hexdigest(), entry["sha256"], entry["path"])
                self.assertEqual(len(content), entry["bytes"], entry["path"])


if __name__ == "__main__":
    unittest.main()
