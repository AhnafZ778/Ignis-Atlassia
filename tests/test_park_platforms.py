import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from fireatlas.park_platforms import read_park_day

class ParkPlatformsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name)/'source.sqlite'
        conn=sqlite3.connect(self.db)
        conn.executescript('''CREATE TABLE batches(id INTEGER, file_sha256 TEXT, retrieved_utc TEXT, demo INTEGER);
        CREATE TABLE source_exports(batch_id INTEGER, source_id TEXT, complete_export INTEGER, request_start TEXT, request_end TEXT, west REAL, south REAL, east REAL, north REAL, product_versions_json TEXT, parent_sha256 TEXT, request_sha256 TEXT);
        CREATE TABLE observations(detection_id TEXT, batch_id INTEGER, source_id TEXT, platform TEXT, product_version TEXT, processing_level TEXT, acquisition_utc TEXT, lon REAL, lat REAL, grid_x INTEGER, grid_y INTEGER, frp_raw TEXT, confidence_raw TEXT, daynight TEXT, scan_m REAL, track_m REAL, raw_json TEXT);''')
        conn.execute("INSERT INTO batches VALUES(1,'hash','time',0)")
        conn.execute('INSERT INTO source_exports VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(1,'VIIRS_NOAA20_SP',1,'2024-07-01','2024-07-31',-123,39,-120,41,json.dumps(['2']),'parent','request'))
        for id,lon,raw in [('valid',-121.7,{'type':'0'}),('out',-123,{'type':'0'}),('nonfire',-121.7,{'type':'2'})]:
            conn.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(id,1,'VIIRS_NOAA20_SP','NOAA-20','2','SP','2024-07-25T01:00:00Z',lon,40,1,2,'4','n','N',375,375,json.dumps(raw)))
        conn.execute("INSERT INTO batches VALUES(2,'olderhash','time',0)")
        conn.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',('earlier-batch',2,'VIIRS_NOAA20_SP','NOAA-20','2','SP','2024-07-25T02:00:00Z',-121.8,40,1,2,'4','n','N',375,375,json.dumps({'type':'0'})))
        conn.commit();conn.close()

    def tearDown(self): self.temp.cleanup()

    def test_bounded_verified_data_and_missing_source(self):
        result=read_park_day('2024-07-25',self.db)
        self.assertEqual([r['id'] for r in result['sources']['VIIRS_NOAA20_SP']['observations']], ['valid', 'earlier-batch'])
        self.assertEqual(result['sources']['VIIRS_NOAA21_SP']['state'],'unavailable')
        self.assertEqual(result['sources']['VIIRS_NOAA20_SP']['exports'][0]['file_sha256'],'hash')
        self.assertEqual(read_park_day('2024-07-26',self.db)['sources']['VIIRS_NOAA20_SP']['state'],'complete_export')
        with self.assertRaises(ValueError): read_park_day('2024-08-01',self.db)
        with self.assertRaises(FileNotFoundError): read_park_day('2024-07-25',self.db.with_suffix('.missing'))
