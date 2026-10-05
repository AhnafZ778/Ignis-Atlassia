"""Contract tests for the frozen regional bundle, distinct from generic studies."""
import csv
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fireatlas.core import connect, ingest
from fireatlas.regional_study import build_bundle, verify_bundle, StaleResult
from fireatlas.calendar_v2 import _verdict

BBOX=(-122.2,38.8,-120.,41.)
FIELDS=['latitude','longitude','acq_date','acq_time','satellite','instrument','confidence','version','scan','track','frp','daynight','type']


def fixture(db, directory):
    for year in [2023,2024,2025]:
        for source in ['MODIS_SP','VIIRS_SNPP_SP']:
            path=directory/f'{source}-{year}.csv'
            with path.open('w',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(FIELDS)
                for i in range(2 if source=='MODIS_SP' else 4):
                    writer.writerow([39.8,-121.8+i*.02,f'{year}-07-25','1200','Terra' if source=='MODIS_SP' else 'N',
                        'MODIS' if source=='MODIS_SP' else 'VIIRS','90' if source=='MODIS_SP' else 'h',
                        '61.03' if source=='MODIS_SP' else '2','1','1','10','D','0'])
            r=ingest(db,path,source,source_uri='user-supplied:test',complete_month=f'{year}-07',bbox=BBOX)
            batch=db.execute('SELECT id,file_sha256 FROM batches WHERE source_id=? ORDER BY id DESC',(source,)).fetchone()
            db.execute('INSERT INTO source_exports VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (batch['id'],'norcal',source,f'{year}-07',f'{year}-07-01',f'{year}-07-31',*BBOX,1,'request-metadata',
                        json.dumps(['61.03' if source=='MODIS_SP' else '2']),batch['file_sha256'],'a'*64))
    db.commit()


class RegionalStudyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.db=connect(self.root/'science.sqlite3');fixture(self.db,self.root)

    def tearDown(self):
        self.db.close();self.temp.cleanup()

    def build(self,year=2024,month=7):
        target=self.root/'result.zip'
        build_bundle(self.db,target,region='norcal',year=year,month=month)
        return target

    def test_mixed_gap_and_observed_zero_reproduce_without_live_inputs(self):
        target=self.build()
        with zipfile.ZipFile(target) as archive:
            result=json.loads(archive.read('calendar-v2.json'))
        july=result['months'][6]
        self.assertEqual((july['observed_days'],july['estimated_days'],july['unknown_days']),(25,6,0))
        self.assertEqual(result['days'][0]['value'],None)
        with patch('fireatlas.calendar_v2.MCD64_REPORT',self.root/'missing.json'),patch('fireatlas.availability.NOTICE_FILE',self.root/'missing.json'):
            checked=verify_bundle(target)
        self.assertEqual(checked['status'],'verified')
        self.assertEqual(checked['rows'],18)

    def test_unknown_and_observed_months_keep_their_states(self):
        for year,month,kind in [(2025,7,'observed'),(2025,6,'unknown')]:
            target=self.build(year,month)
            self.assertEqual(verify_bundle(target)['status'],'verified')
            with zipfile.ZipFile(target) as archive:
                item=json.loads(archive.read('calendar-v2.json'))['months'][month-1]
            self.assertEqual(item['estimate_type'],kind)
            if kind=='unknown':self.assertIsNone(item['value'])

    def test_numeric_tampering_fails_even_with_new_checksum(self):
        original=self.build();tampered=self.root/'tampered.zip'
        with zipfile.ZipFile(original) as source:
            files={name:source.read(name) for name in source.namelist()}
        value=json.loads(files['calendar-v2.json']);value['months'][6]['value']+=1
        files['calendar-v2.json']=json.dumps(value).encode()
        manifest=json.loads(files['manifest.json']);manifest['files']['calendar-v2.json']={'sha256':hashlib.sha256(files['calendar-v2.json']).hexdigest(),'bytes':len(files['calendar-v2.json'])}
        files['manifest.json']=json.dumps(manifest).encode()
        with zipfile.ZipFile(tampered,'w',zipfile.ZIP_DEFLATED) as target:
            for name,body in files.items():target.writestr(name,body)
        with self.assertRaisesRegex(ValueError,'Scientific recount'):verify_bundle(tampered)

    def test_grid_tampering_is_detected_after_rehash(self):
        original=self.build();tampered=self.root/'grid.zip'
        with zipfile.ZipFile(original) as source:files={name:source.read(name) for name in source.namelist()}
        name='observations/0001.jsonl';lines=files[name].splitlines();row=json.loads(lines[0]);row['grid_x']+=1
        lines[0]=json.dumps(row).encode();files[name]=b'\n'.join(lines)+b'\n';manifest=json.loads(files['manifest.json'])
        manifest['files'][name].update(sha256=hashlib.sha256(files[name]).hexdigest(),bytes=len(files[name]));files['manifest.json']=json.dumps(manifest).encode()
        with zipfile.ZipFile(tampered,'w',zipfile.ZIP_DEFLATED) as target:
            for name,body in files.items():target.writestr(name,body)
        with self.assertRaisesRegex(ValueError,'grid differs'):verify_bundle(tampered)

    def test_limits_and_stale_selection_never_publish_an_archive(self):
        with patch('fireatlas.regional_study.MAX_ROWS',1):
            with self.assertRaisesRegex(ValueError,'no sampled'):self.build()
        path=self.root/'stale.zip'
        with self.assertRaises(StaleResult):build_bundle(self.db,path,region='norcal',year=2024,month=7,expected_result_sha256='wrong')
        self.assertFalse(path.exists())

    def test_supported_median_is_not_hidden_by_missing_percentile(self):
        text=_verdict('Northern California',2026,{'month':'2026-06','value':113.,'n_years':3,'baseline_median':109.,'anomaly_cell_days':4.})
        self.assertIn('4 above the median',text);self.assertIn('Percentile unavailable',text)

    def test_wholly_scaled_pre_viirs_month_reproduces(self):
        source=self.root/'MODIS_SP-2023.csv'
        earlier=self.root/'MODIS_SP-2011.csv'
        earlier.write_text(source.read_text().replace('2023-07-25','2011-07-25'))
        imported=ingest(self.db,earlier,'MODIS_SP',source_uri='user-supplied:test',complete_month='2011-07',bbox=BBOX)
        batch=self.db.execute('SELECT id,file_sha256 FROM batches WHERE source_id=? ORDER BY id DESC',('MODIS_SP',)).fetchall()
        actual=self.db.execute('SELECT batch_id FROM observations WHERE acquisition_utc LIKE ?',('2011-%',)).fetchone()[0]
        sha=self.db.execute('SELECT file_sha256 FROM batches WHERE id=?',(actual,)).fetchone()[0]
        self.db.execute('INSERT INTO source_exports VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (actual,'norcal','MODIS_SP','2011-07','2011-07-01','2011-07-31',*BBOX,1,'request-metadata',json.dumps(['61.03']),sha,'a'*64))
        self.db.commit()
        target=self.build(2011,7)
        self.assertEqual(verify_bundle(target)['status'],'verified')
        with zipfile.ZipFile(target) as archive:item=json.loads(archive.read('calendar-v2.json'))['months'][6]
        self.assertEqual(item['estimate_type'],'scaled')
        self.assertEqual((item['observed_days'],item['estimated_days'],item['unknown_days']),(0,31,0))

    def test_regional_http_download_identity_stale_and_busy(self):
        import threading
        from http.server import ThreadingHTTPServer
        from urllib.request import urlopen
        from urllib.error import HTTPError
        from fireatlas.web import handler_factory
        from fireatlas.regional_study import BUILD_LOCK
        server=ThreadingHTTPServer(('127.0.0.1',0),handler_factory(self.root/'science.sqlite3'))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base+'/api/v2/calendar?region=norcal&year=2024&month=7') as response:result=json.load(response)
            sha=result['meta']['result_sha256']
            path=f'/api/v2/study?region=norcal&year=2024&month=7&expected_result_sha256={sha}'
            with urlopen(base+path) as response:
                self.assertIn('application/zip',response.headers['Content-Type']);body=response.read()
            target=self.root/'http-result.zip';target.write_bytes(body)
            self.assertEqual(verify_bundle(target)['result_sha256'],sha)
            with self.assertRaises(HTTPError) as caught:urlopen(base+path.replace(sha,'stale'))
            self.assertEqual(caught.exception.code,409)
            with BUILD_LOCK:
                with self.assertRaises(HTTPError) as caught:urlopen(base+path)
                self.assertEqual(caught.exception.code,503)
        finally:server.shutdown();server.server_close()

    def test_sensor_notice_cache_follows_changed_file(self):
        from fireatlas.availability import NOTICE_FILE, notices
        path=self.root/'notices.json';path.write_bytes(NOTICE_FILE.read_bytes())
        before=notices(path)[0]['start_utc']
        value=json.loads(path.read_text());value['notices'][0]['start_utc']='2024-07-24T06:24:00Z';path.write_text(json.dumps(value))
        self.assertNotEqual(notices(path)[0]['start_utc'],before)


if __name__=='__main__':unittest.main()
