import copy
import unittest
from fireatlas.finding_comparison import derive, _measure

class FindingComparisonTest(unittest.TestCase):
    def test_direction_and_zero_denominator(self):
        self.assertEqual(_measure(0, 4), {'first': 0, 'second': 4, 'difference': 4, 'percent': None, 'direction': 'increase'})
        self.assertEqual(_measure(3, 3)['direction'], 'unchanged')
        self.assertEqual(_measure(None, 1)['direction'], 'unavailable')
        with self.assertRaises(ValueError): _measure(float('nan'), 2)

    def test_same_cohort_pairs_and_each_years_estimate(self):
        def row(year, modis, viirs, estimate, version='2'):
            return {'year':year, 'month':6, 'date':str(year)+'-06', 'versions':['61.03', version],
                    'modis':modis, 'reference':viirs, 'prediction':estimate,
                    'model':'annual_ratio', 'training_years':[year-1]}
        rows=[row(2023,10,30,20),row(2024,12,20,25),row(2025,14,40,30,'3')]
        bundle={'schema':'fireatlas-comparability-bundle-v1','result':{
          'schema':'fireatlas-monthly-comparability-v1','region':{'id':'x'},'unit':'cell-days',
          'result_sha256':'a','input_sha256':'b','method_version':'m',
          'evaluation':{'forward':{'rows':rows},'nested':{'rows':[]}}}}
        original=copy.deepcopy(bundle); out=derive(bundle)
        self.assertEqual(len(out['pairs']),1)
        self.assertEqual(out['pairs'][0]['years'],[2023,2024])
        self.assertTrue(out['pairs'][0]['direction_differs'])
        self.assertEqual(out['pairs'][0]['series']['viirs']['difference'],-10)
        self.assertEqual(out['pairs'][0]['training_years'],[[2022],[2023]])
        self.assertEqual(bundle,original)
        self.assertEqual(out,derive(bundle))

if __name__ == '__main__': unittest.main()

class PublishedFindingTest(unittest.TestCase):
    def test_public_pair_identity_and_values(self):
        import json
        from pathlib import Path
        from fireatlas.finding_comparison import published_pair
        from fireatlas.studio.visuals import prepared
        directory = Path(__file__).resolve().parents[1]/'site/data/finding-comparisons/v1'
        doc = json.loads((directory/'norcal.json').read_text())
        pair = next(p for p in doc['pairs'] if p['protocol']=='forward')
        result = published_pair(directory,'norcal',pair['month'],*pair['years'],doc['result_sha256'],'viirs')
        self.assertEqual(result['comparison'],pair)
        with self.assertRaises(ValueError): published_pair(directory,'norcal',pair['month'],*pair['years'],'bad-hash')
        snap={'id':'s','scope':{'bbox':doc['region']['bbox'],'start':pair['dates'][0]+'-01','end':pair['dates'][1]+'-28','day':None},'method':{'unit':doc['unit']}}
        visual=prepared({'type':'chart'},[snap],{'s':{'operation':'finding_comparison','payload':result}}, {})
        self.assertEqual([r['reference'] for r in visual['rows']],[pair['series']['viirs']['first'],pair['series']['viirs']['second']])
