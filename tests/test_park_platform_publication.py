import gzip, hashlib, json, unittest
from pathlib import Path
from fireatlas.park_platforms import DAYS,read_park_day

class ParkPublicationTests(unittest.TestCase):
    def test_manifest_and_local_recount(self):
        directory=Path(__file__).resolve().parents[1]/'site/data/park-platforms/v1'
        manifest=json.loads((directory/'manifest.json').read_text())
        self.assertEqual(manifest['schema'],'fireatlas-park-platform-publication-v1')
        for day in DAYS:
            name=day+'.json.gz';data=(directory/name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(),manifest['files'][name]['sha256'])
            actual=json.loads(gzip.decompress(data));self.assertEqual(actual['date_utc'],day)
            if not __import__('fireatlas.park_platforms',fromlist=['DEFAULT_DB']).DEFAULT_DB.exists():continue
            local=read_park_day(day)
            for source in actual['sources']:
                self.assertEqual([r['id'] for r in actual['sources'][source]['observations']],[r['id'] for r in local['sources'][source]['observations']])
