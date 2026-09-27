import csv
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

from fireatlas.core import connect, ingest
from fireatlas.demo import FIELDS
from fireatlas.globe import snapshot, detail
from fireatlas.web import handler_factory


class GlobeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "authentic.sqlite3"
        self.db = connect(self.path)
        self.addCleanup(self.db.close)
        rows = [self.row(20.1, -2.3, "2026-09-20", "10"),
                self.row(20.6, -2.8, "2026-09-27", "20"),
                self.row(-179.9, 45, "2026-09-27", "nan"),
                self.row(180, 45, "2026-09-27", "unknown"),
                self.row(1, 2, "2026-09-19", "999")]
        self.import_rows(rows, "MODIS_NRT")
        self.import_rows([self.row(20.2, -2.6, "2026-09-27", "25", "VIIRS", "1")], "VIIRS_NOAA20_NRT")
        self.import_rows([self.row(25, 2, "2030-01-01", "500")], "MODIS_NRT", demo=True)

    def row(self, lon, lat, day, frp, instrument="MODIS", satellite="T"):
        return dict(latitude=lat, longitude=lon, acq_date=day, acq_time="1234", satellite=satellite,
                    instrument=instrument, confidence="n" if instrument=="VIIRS" else "80",
                    version="2.0NRT", scan="1", track="1", frp=frp, daynight="D")

    def import_rows(self, rows, source, demo=False):
        path = self.root / f"{source}-{demo}.csv"
        with path.open("w", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=FIELDS)
            writer.writeheader();writer.writerows(rows)
        ingest(self.db, path, source, demo=demo)

    def test_totals_window_authentic_only_and_date_source_filters(self):
        data = snapshot(self.db)
        self.assertEqual(data["total"], 5)
        self.assertEqual(data["latest_observation"], "2026-09-27T12:34:00Z")
        self.assertEqual(data["window_start"], "2026-09-20")
        self.assertEqual(sum(c["count"] for c in data["clusters"]), 5)
        self.assertEqual(sum(d["count"] for d in data["daily"]), 5)
        self.assertEqual(sum(s["count"] for s in data["sources"]), 5)
        self.assertEqual(snapshot(self.db, day="2026-09-27")["total"], 4)
        self.assertEqual(snapshot(self.db, source="VIIRS_NOAA20_NRT")["total"], 1)
        self.assertEqual(snapshot(self.db, day="2026-09-26")["total"], 0)

    def test_cluster_detail_uses_matching_cell_and_preserves_original_coordinates(self):
        data = snapshot(self.db)
        cluster = next(c for c in data["clusters"] if c["id"] == "200:87")
        result = detail(self.db, cell=cluster["id"])
        self.assertEqual(result["total"], cluster["count"])
        self.assertEqual(result["total"], 3)
        self.assertEqual(cluster["max_frp_mw"], 25)
        self.assertEqual(result["bbox"], [20, -3, 21, -2])
        self.assertEqual({(r["lon"], r["lat"]) for r in result["observations"]}, {(20.1,-2.3),(20.6,-2.8),(20.2,-2.6)})
        self.assertTrue(all(len(r["file_sha256"]) == 64 for r in result["observations"]))
        self.assertEqual(detail(self.db, cell="200:87", day="2026-09-20")["total"], 1)
        self.assertEqual(detail(self.db, cell="200:87", source="MODIS_NRT")["total"], 2)
        self.assertEqual(detail(self.db, cell="359:135")["observations"][0]["lon"], 180)
        self.assertIsNone(detail(self.db, cell="0:135")["observations"][0]["frp_mw"])

    def test_invalid_requests_and_empty_dataset(self):
        for args in ({"source":"NOAA_HMS_VIIRS"},{"day":"2026-09-19"},{"day":"2026-09-99"}):
            with self.assertRaises(ValueError): snapshot(self.db, **args)
        for cell in ("bad","-1:30","360:0","0:180"):
            with self.assertRaises(ValueError): detail(self.db, cell=cell)
        with connect(self.root / "empty.sqlite3") as db:
            result = snapshot(db)
            self.assertEqual(result["total"], 0)
            self.assertEqual(result["clusters"], [])
            self.assertIsNone(result["latest_observation"])

    def test_http_synthetic_gate_and_cache_invalidation(self):
        server = ThreadingHTTPServer(("127.0.0.1",0), handler_factory(self.path))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        def get(path):
            with urlopen(f"http://127.0.0.1:{server.server_port}{path}") as response: return json.load(response)
        self.assertEqual(get("/api/globe")["total"], 5)
        self.assertEqual(get("/api/globe")["total"], 5)
        with self.assertRaises(HTTPError) as error:get("/api/globe?demo=1")
        self.assertEqual(error.exception.code,400)
        self.import_rows([self.row(30,10,"2026-09-27","30","VIIRS","2")],"VIIRS_NOAA21_NRT")
        self.assertEqual(get("/api/globe")["total"],6)
        self.assertEqual(get("/api/globe/detail?cell=200:87")["total"],3)

    def test_projection_matches_camera_axes_and_hides_back_hemisphere(self):
        module = str(Path("fireatlas/static/globe-math.js").resolve())
        script = """
const assert=require('node:assert/strict'),m=require(process.argv[1]);
const v={width:1000,height:800,rotation:[1,0,0,0,1,0,0,0,1],distance:3,framing:0,vertical:0};
assert.deepEqual(m.project(m.vector(0,0),v),{x:500,y:400});
assert.equal(m.project(m.vector(180,0),v),null);
assert.equal(m.project(m.vector(90,0),v),null);
assert.ok(m.project(m.vector(20,0),v).x>500);
assert.ok(m.project(m.vector(-20,0),v).x<500);
assert.ok(m.project(m.vector(0,20),v).y<400);
const yaw=112*Math.PI/180,pitch=-3*Math.PI/180,cy=Math.cos(yaw),sy=Math.sin(yaw),cx=Math.cos(pitch),sx=Math.sin(pitch);
v.rotation=[cy,0,-sy,-sy*sx,cx,-cy*sx,sy*cx,sx,cy*cx];
const p=m.project(m.vector(112,-3),v);assert.ok(Math.abs(p.x-500)<1e-8&&Math.abs(p.y-400)<1e-8);
assert.equal(m.project(m.vector(-68,3),v),null);
"""
        subprocess.run(["node","-e",script,module],check=True,capture_output=True,text=True)
