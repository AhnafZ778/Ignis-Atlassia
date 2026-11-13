"""Isolated synthetic records test the descriptive ranking; they are never published."""
import sqlite3
import threading
import unittest
from datetime import date,timedelta
from fireatlas.historical_similarity import match_imported_profiles
from fireatlas.assistant.contracts import normalize_context
from fireatlas.regions import REGIONS

class ProfileCandidateTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript('CREATE TABLE batches(id INTEGER,demo INTEGER); CREATE TABLE observations(batch_id INTEGER,source_id TEXT,processing_level TEXT,acquisition_utc TEXT,lon REAL,lat REAL); INSERT INTO batches VALUES(1,0),(2,1);')
        self.cfg=normalize_context({'case':'park-2024','start':'2024-07-25','end':'2024-07-28','source':'MODIS_SP','series':'modis'})
        self.add([-121.7,40.0],'2024-07-25',[2,4,8,16])
        for region,counts in [('norcal',[8,4,2,1]),('punjab-haryana',[1,2,4,8])]:
            w,s,e,n=REGIONS[region]['bbox'];self.add([(w+e)/2,(s+n)/2],'2015-07-01',counts)
        w,s,e,n=REGIONS['punjab-haryana']['bbox']
        self.add([(w+e)/2,(s+n)/2],'2010-07-01',[2,4,8,16],batch=2)
        self.add([(w+e)/2,(s+n)/2],'2011-07-01',[2,4,8,16],source='VIIRS_SNPP_SP')
    def add(self,point,start,counts,batch=1,source='MODIS_SP'):
        for offset,count in enumerate(counts):
            day=(date.fromisoformat(start)+timedelta(days=offset)).isoformat()
            self.db.executemany('INSERT INTO observations VALUES(?,?,?,?,?,?)',[(batch,source,'SP',day+'T12:00:00Z',*point)]*count)
    def test_ranks_same_source_profiles_and_excludes_demo_other_source_and_reference(self):
        result=match_imported_profiles(self.db,self.cfg,{'first_year':2006,'last_year':2026})
        first=result['candidates'][0]
        self.assertEqual(first['region'],'punjab-haryana')
        self.assertEqual(first['counts'],[1,2,4,8])
        self.assertEqual(first['distance'],0)
        self.assertEqual(result['reference']['counts'],[2,4,8,16])
        self.assertFalse(any(row['start'].startswith(('2010','2011','2024')) for row in result['candidates']))
        self.assertEqual(result['unit'],'imported thermal records before alias deduplication')
    def test_a_missing_reference_date_is_unknown_and_not_zero_filled(self):
        self.db.execute("DELETE FROM observations WHERE acquisition_utc LIKE '2024-07-27%'")
        with self.assertRaisesRegex(ValueError,'cannot be filled with zero'):
            match_imported_profiles(self.db,self.cfg,{})
    def test_sensor_union_and_invalid_reference_windows_are_refused(self):
        with self.assertRaises(ValueError):match_imported_profiles(self.db,{**self.cfg,'source':'joint'},{})
        with self.assertRaises(ValueError):match_imported_profiles(self.db,{**self.cfg,'end':'2024-07-25'},{})
