"""Synthetic comparisons only; these do not approve daily estimates."""
import copy
import gzip
import json
import unittest
from unittest.mock import patch
from fireatlas import daily_reproduction as reproduction


def fixture():
    return {'inputs':{'days':[{'date':'2020-01-01','reference':1.0}]},
            'platform_counts':{'2020-01-01':{'terra':1,'aqua':0}},
            'folds':[{'test_year':2020,'training_dates':['2017-01-01'],
                      'environment':{'numpy':'old'},'parameters':[1.0,0.0]},
                     {'test_year':2021,'training_dates':['2018-01-01'],
                      'environment':{'numpy':'old'},'parameters':[2.0,0.0]}],
            'rows':[{'date':'2020-01-01','reference':2,'prediction':1.0}],
            'checks':{'coverage':False},'result_sha256':'a'*64}


class DailyNumericalReproductionTests(unittest.TestCase):
    def test_tolerance_does_not_change_original_hash_or_environment(self):
        before=fixture();after=copy.deepcopy(before)
        after['folds'][0]['parameters'][0]+=1e-7
        after['folds'][0]['environment']={'numpy':'different'}
        after['result_sha256']='b'*64
        result=reproduction.compare(before,after)
        self.assertTrue(result['numerically_consistent'])
        self.assertGreater(result['max_absolute_difference'],0)

    def test_partitions_counts_and_gates_are_exact(self):
        before=fixture()
        for mutate in (lambda x:x['folds'].reverse(),
                       lambda x:x['rows'][0].update(reference=3),
                       lambda x:x['checks'].update(coverage=True),
                       lambda x:x['rows'][0].update(date='2020-01-02')):
            after=copy.deepcopy(before);mutate(after)
            self.assertFalse(reproduction.compare(before,after)['numerically_consistent'])

    def test_original_inputs_never_inherit_numeric_tolerance(self):
        before=fixture();after=copy.deepcopy(before)
        after['inputs']['days'][0]['reference']+=1e-12
        result=reproduction.compare(before,after)
        self.assertFalse(result['numerically_consistent'])
        self.assertIn('input identity differs',str(result['examples']))

    def test_large_nonfinite_and_type_changes_fail(self):
        before=fixture()
        for value in (1.1,float('nan'),float('inf'),1):
            after=copy.deepcopy(before);after['rows'][0]['prediction']=value
            self.assertFalse(reproduction.compare(before,after)['numerically_consistent'])

    def test_finite_overflow_fails_and_report_remains_serializable(self):
        before=fixture();after=copy.deepcopy(before)
        before['rows'][0]['prediction']=-1e308
        after['rows'][0]['prediction']=1e308
        result=reproduction.compare(before,after)
        self.assertFalse(result['numerically_consistent'])
        self.assertTrue(result['absolute_difference_overflow'])
        json.dumps(result,allow_nan=False)

    def test_protocol_and_review_numbers_are_exact(self):
        before=fixture();before['protocol']={'gate':0.85}
        after=copy.deepcopy(before);after['protocol']['gate']+=1e-12
        self.assertFalse(reproduction.compare(before,after)['numerically_consistent'])

    def test_missing_or_extra_fields_fail(self):
        before=fixture();after=copy.deepcopy(before)
        del after['folds'][0]['parameters']
        self.assertFalse(reproduction.compare(before,after)['numerically_consistent'])

    def test_runner_rejects_input_tampering_before_any_refit(self):
        from fireatlas import qualification
        from scripts import reproduce_daily_numerically as runner
        inputs={'region':'norcal','versions':['6.03','2']};platform_counts={}
        original={'schema':'fireatlas-daily-estimate-research-v2','synthetic':False,
                  'region':'norcal','versions':['6.03','2'],'inputs':inputs,
                  'platform_counts':platform_counts,'input_sha256':'incorrect','folds':[],'rows':[]}
        original['result_sha256']=qualification.digest(original)
        record={'id':'a'*16,'region':'norcal','versions':['6.03','2'],
                'reproduction_artifact':'cohort-daily/'+'a'*16+'.json.gz',
                'result_sha256':original['result_sha256']}
        def read(_root,name,_release):
            if name.startswith('daily-cohorts/'):
                return json.dumps({'region':'norcal','entries':[record]}).encode()
            return gzip.compress(json.dumps(original).encode())
        with patch.object(runner.qualification_publication,'read',side_effect=read), \
             patch.object(runner.daily_estimates,'analyze') as fit:
            with self.assertRaisesRegex(ValueError,'input identity'):
                runner.run('norcal',['6.03','2'],'b'*64)
            fit.assert_not_called()

    def test_runner_rejects_unpinned_release_before_reading(self):
        from scripts import reproduce_daily_numerically as runner
        with patch.object(runner.qualification_publication,'read') as read:
            for release in ('',None,'a'*63,'G'*64):
                with self.assertRaisesRegex(ValueError,'explicit immutable'):
                    runner.run('norcal',['6.03','2'],release)
            read.assert_not_called()

    def test_runner_uses_exact_frozen_result_and_reports_no_scientific_admission(self):
        from fireatlas import qualification
        from scripts import reproduce_daily_numerically as runner
        inputs={'region':'norcal','versions':['6.03','2']};platform_counts={}
        original={'schema':'fireatlas-daily-estimate-research-v2','synthetic':False,
                  'region':'norcal','versions':['6.03','2'],'inputs':inputs,
                  'platform_counts':platform_counts,'input_sha256':qualification.digest([inputs,platform_counts]),
                  'folds':[{'test_year':2020,'environment':{'numpy':'old'}}],
                  'rows':[{'date':'2020-01-01','prediction':1.0}],'review':None,'experimental_review':None}
        original['result_sha256']=qualification.digest(original)
        record={'id':'a'*16,'region':'norcal','versions':['6.03','2'],
                'reproduction_artifact':'cohort-daily/'+'a'*16+'.json.gz',
                'result_sha256':original['result_sha256']}
        def read(_root,name,_release):
            if name.startswith('daily-cohorts/'):
                return json.dumps({'region':'norcal','entries':[record]}).encode()
            return gzip.compress(json.dumps(original).encode())
        with patch.object(runner.qualification_publication,'read',side_effect=read), \
             patch.object(runner.daily_estimates,'analyze',return_value=copy.deepcopy(original)) as fit:
            report=runner.run('norcal',['6.03','2'],'b'*64)
        self.assertEqual('consistent-within-tolerance',report['status'])
        self.assertFalse(report['scientific_admission'])
        self.assertFalse(report['independent_machine_verified'])
        fit.assert_called_once_with(inputs,platform_counts,review=None,experimental=None)
        with patch.object(runner.qualification_publication,'read',side_effect=read), \
             patch.object(runner.daily_estimates,'analyze',return_value=copy.deepcopy(original)), \
             patch.object(runner,'source_hashes',side_effect=[{'method':'old'},{'method':'changed'}]):
            with self.assertRaisesRegex(ValueError,'changed during reproduction'):
                runner.run('norcal',['6.03','2'],'b'*64)


if __name__=='__main__':unittest.main()
