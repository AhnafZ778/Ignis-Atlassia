import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from fireatlas.core import connect
from fireatlas.demo import make_demo
from fireatlas.study import build_bundle, verify_bundle


class StudyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        with contextlib.redirect_stdout(io.StringIO()):
            make_demo(root / "demo", root / "demo.sqlite3")
        self.db = connect(root / "demo.sqlite3")
        self.addCleanup(self.db.close)
        self.config = dict(year=2015, month=7, series="joint", bbox=(-122,39,-120,41))

    def bundle(self, **changes):
        return build_bundle(self.db, **(self.config | changes))

    def test_roundtrip_includes_baseline_inputs_and_raw_provenance(self):
        body = self.bundle(day="2015-07-02", layer="ndvi")
        result = verify_bundle(io.BytesIO(body))
        self.assertTrue(result["verified"])
        self.assertEqual(result["data_class"], "synthetic")
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            rows = json.loads(z.read("observations.json"))
            self.assertEqual({r["acquisition_utc"][:4] for r in rows}, {"2012", "2013", "2014", "2015"})
            self.assertIn("confidence", rows[0]["raw"])
            self.assertEqual(len(rows[0]["file_sha256"]), 64)
            self.assertEqual(json.loads(z.read("selection.json"))["day"], "2015-07-02")
            self.assertEqual(len(json.loads(z.read("batches.json"))), 8)

    def test_empty_scope_and_incomplete_windows(self):
        self.assertTrue(verify_bundle(io.BytesIO(self.bundle(bbox=(10,10,11,11))))["verified"])
        self.db.execute("DELETE FROM export_windows WHERE month='2015-07'")
        result = verify_bundle(io.BytesIO(self.bundle()))
        self.assertTrue(result["verified"])

    def test_rejects_corruption_and_recomputed_hash_with_wrong_counts(self):
        original = self.bundle()
        for rehash in (False, True):
            with zipfile.ZipFile(io.BytesIO(original)) as z:
                files = {name: z.read(name) for name in z.namelist()}
            summary = json.loads(files["calendar.json"])
            summary["monthly"][6]["baseline_median"] = 999
            files["calendar.json"] = json.dumps(summary).encode()
            if rehash:
                manifest = json.loads(files["manifest.json"])
                manifest["files"]["calendar.json"] = hashlib.sha256(files["calendar.json"]).hexdigest()
                files["manifest.json"] = json.dumps(manifest).encode()
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as z:
                for name, body in files.items(): z.writestr(name, body)
            with self.assertRaisesRegex(ValueError, "does not reproduce" if rehash else "checksum mismatch"):
                verify_bundle(io.BytesIO(output.getvalue()))

    def test_invalid_selection_and_oversize_never_silently_truncate(self):
        for config in [dict(day="2015-02-30"), dict(day="2014-07-01"), dict(month=13), dict(layer="bogus")]:
            with self.assertRaises(ValueError): self.bundle(**config)
        with patch("fireatlas.study.MAX_ROWS", 2):
            with self.assertRaisesRegex(ValueError, "Narrow the AOI"):
                self.bundle()
