"""Synthetic diagnostic examples; no scientific approval is implied."""
import copy
import gzip
import json
import unittest
from unittest.mock import patch
from fireatlas import daily_diagnostics as diagnostics


def row(stamp,modis,reference,expected,probability,interval):
    year,month,_=map(int,stamp.split('-'))
    return {'date':stamp,'year':year,'month':month,'modis':modis,'reference':reference,
            'expected_count':expected,'probability_positive':probability,'interval':interval}


def fixture():
    return {'schema':'fireatlas-daily-estimate-research-v2','rows':[
        row('2020-01-01',0,0,1.0,0.25,[0.0,2.0]),
        row('2020-07-01',0,4,2.0,0.75,[0.0,3.0]),
        row('2021-07-01',2,2,2.0,0.5,None)]}


class DailyDiagnosticsTests(unittest.TestCase):
    def test_exact_denominators_and_distinct_year_groups(self):
        report=diagnostics.analyze(fixture());overall=report['overall']
        self.assertEqual(3,overall['n_utc_days']);self.assertEqual(2,overall['test_year_groups'])
        self.assertAlmostEqual((.25**2+.25**2+.5**2)/3,overall['occurrence_brier'])
        self.assertEqual(.5,overall['interval_coverage']);self.assertEqual(2,overall['interval_days']);self.assertEqual(1,overall['interval_covered_days'])
        self.assertEqual(2,report['by_season']['JJA']['test_year_groups'])
        self.assertEqual(1,report['by_modis_state']['zero_modis_positive_viirs']['n_utc_days'])
        self.assertFalse(report['scientific_admission']);self.assertFalse(report['daily_estimates_admitted'])

    def test_empty_and_unsupported_are_explicit(self):
        report=diagnostics.analyze({'schema':'fireatlas-daily-estimate-research-v2','rows':[]})
        self.assertIsNone(report['overall']['occurrence_brier'])
        self.assertIsNone(report['by_season']['JJA']['interval_coverage'])
        self.assertEqual(0,report['by_season']['JJA']['interval_covered_days'])
        self.assertEqual(0,report['n_test_year_groups'])

    def test_duplicate_dates_invalid_probabilities_and_intervals_fail(self):
        for mutation in (lambda r:r['rows'].append(copy.deepcopy(r['rows'][0])),
                         lambda r:r['rows'][0].update(probability_positive=float('nan')),
                         lambda r:r['rows'][0].update(probability_positive=1.1),
                         lambda r:r['rows'][0].update(interval=[4,3]),
                         lambda r:r['rows'][0].update(reference=True),
                         lambda r:r['rows'][0].update(month=2)):
            report=fixture();mutation(report)
            with self.assertRaises(ValueError):diagnostics.analyze(report)

    def test_unpinned_release_is_rejected_before_reads(self):
        from scripts import diagnose_daily_holdouts as runner
        with patch.object(runner.qualification_publication,'read') as read:
            for release in ('',None,'bad'):
                with self.assertRaisesRegex(ValueError,'explicit immutable'):
                    runner.run('norcal',['6.03','2'],release)
            read.assert_not_called()

    def test_tampered_input_cannot_reach_source_refit(self):
        from fireatlas import qualification
        from scripts import diagnose_daily_holdouts as runner
        original=fixture();original.update(synthetic=False,region='norcal',versions=['6.03','2'],
                                          inputs={'region':'norcal','versions':['6.03','2']},
                                          platform_counts={},input_sha256='wrong')
        original['result_sha256']=qualification.digest(original)
        entry={'id':'a'*16,'region':'norcal','versions':['6.03','2'],
               'reproduction_artifact':'cohort-daily/'+'a'*16+'.json.gz',
               'result_sha256':original['result_sha256']}
        def read(_root,name,_release):
            if name.startswith('daily-cohorts/'):
                return json.dumps({'region':'norcal','entries':[entry]}).encode()
            return gzip.compress(json.dumps(original).encode())
        with patch.object(runner.qualification_publication,'read',side_effect=read), \
             patch.object(runner.daily_estimates,'verify') as verify:
            with self.assertRaisesRegex(ValueError,'input identity'):
                runner.run('norcal',['6.03','2'],'b'*64)
            verify.assert_not_called()
