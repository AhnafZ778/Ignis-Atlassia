import hashlib,json,unittest
from pathlib import Path
from fireatlas.environment_analogues import matches,resolve_publication

class EnvironmentAnalogueTests(unittest.TestCase):
    def test_published_ranking_reproduces_and_excludes_neighbors(self):
        p=Path(__file__).resolve().parents[1]/'site/data/environment-analogues/v1'
        manifest=json.loads((p/'manifest.json').read_text());raw=(p/'park.json').read_bytes();digest=hashlib.sha256(raw).hexdigest();self.assertEqual(digest,manifest['files']['park.json']['sha256'])
        data=json.loads(raw); rankings=json.loads((p/'matches.json').read_text());self.assertEqual(rankings['input_sha256'],digest)
        for cell in data['cells']:
            result=matches(data,cell['id']);self.assertEqual(result,rankings['results'][cell['id']]);r,c=map(int,cell['id'].split('-'))
            for m in result['matches']:
                y,x=map(int,m['cell_id'].split('-'));self.assertTrue(abs(r-y)>1 or abs(c-x)>1)
        result=resolve_publication(p,'1-0',digest);self.assertEqual(result['target']['modis_recorded_detections'],31);self.assertEqual(len(result['matches']),5)
        with self.assertRaises(ValueError):resolve_publication(p,'1-0','bad')
        with self.assertRaises(ValueError):matches(data,'missing')
