import csv
import gzip
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from tests.studio_support import StudioCase
from fireatlas.studio.park_chart import DAYS, ROOT, SOURCES, published_timeline, save_timeline
from fireatlas.studio.datasets import read
from fireatlas.studio.errors import StudioError, NotFound

class ParkChartTests(StudioCase):
    def test_published_counts_and_gap_are_preserved_in_saved_table(self):
        board=self.board(); result=save_timeline(self.service.store,self.owner,board['id'])
        rows=result['rows'];self.assertEqual([row['date'] for row in rows],list(DAYS))
        replay=json.load(gzip.open(ROOT/'replay/cases/park-2024.json.gz','rt'))
        frames={row['date_utc']:row for row in replay['frames']}
        for row in rows:
            day=row['date'];noaa=json.load(gzip.open(ROOT/'park-platforms/v1'/f'{day}.json.gz','rt'))
            self.assertEqual(row['values']['MODIS_SP'],frames[day]['products']['MODIS_SP']['detections'])
            self.assertIsNone(row['values']['VIIRS_SNPP_SP'])
            for source in SOURCES[2:]:self.assertEqual(row['values'][source],len(noaa['sources'][source]['observations']))
        data=read(self.service.store,self.owner,board['id'],result['dataset']['id'])[1]
        saved=list(csv.DictReader(data.decode().splitlines()))
        self.assertEqual(saved[0]['MODIS_SP'],str(rows[0]['values']['MODIS_SP']))
        self.assertEqual(saved[0]['VIIRS_SNPP_SP'],'')
        self.assertEqual(saved[0]['VIIRS_SNPP_SP state'],'documented_product_gap')
        self.assertEqual(save_timeline(self.service.store,self.owner,board['id'])['dataset']['id'],result['dataset']['id'])
        with self.assertRaises(NotFound):save_timeline(self.service.store,self.other,board['id'])

    def test_changed_publication_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            shutil.copytree(ROOT/'replay',root/'replay')
            shutil.copytree(ROOT/'park-platforms/v1',root/'park-platforms/v1')
            path=root/'park-platforms/v1'/f'{DAYS[0]}.json.gz';path.write_bytes(path.read_bytes()+b'x')
            with self.assertRaises(StudioError):published_timeline(root)
