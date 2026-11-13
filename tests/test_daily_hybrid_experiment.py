"""Engineering fixtures only; these do not establish scientific performance."""
import copy
import gzip
import json
import unittest
from unittest.mock import patch

from fireatlas import daily_hybrid_experiment as hybrid
from tests.test_qualification import fixture


def mock_fit(train, target):
    return {'expected': [3 * r['modis'] + 0.5 for r in target],
            'parameters': [3.0], 'environment': {'kind': 'synthetic-only'}}


def platform_counts(inputs):
    return {d['date']: {'terra': d['sources']['MODIS_SP']['cells'], 'aqua': 0}
            for d in inputs['days']}


class DailyHybridTests(unittest.TestCase):
    def test_fixed_hybrids_chronology_strata_and_recount(self):
        inputs = fixture()
        with patch.object(hybrid.daily, 'fit_predict', mock_fit):
            result = hybrid.analyze(inputs, platform_counts(inputs), synthetic=True)
            self.assertEqual(3, len(result['folds']))
            self.assertFalse(result['estimates_admitted'])
            self.assertFalse(result['scientific_admission'])
            for fold in result['folds']:
                self.assertLess(max(fold['training_years']), min(fold['calibration_years']))
                self.assertLess(max(fold['calibration_years']), fold['test_year'])
                self.assertTrue(all(n >= 30 for n in fold['calibration_counts'].values()))
            for row in result['rows']:
                for suffix in ('annual', 'monthly'):
                    expected = row['fixed']['hurdle_poisson' if row['modis'] == 0 else suffix + '_ratio']
                    self.assertEqual(expected, row['fixed']['zero_hurdle_' + suffix])
            self.assertTrue(hybrid.verify(result)['verified'])
            altered = copy.deepcopy(result)
            altered['rows'][0]['fixed_intervals']['zero_hurdle_annual'][1] += 1
            with self.assertRaisesRegex(ValueError, 'recount'):
                hybrid.verify(altered)

    def test_later_targets_do_not_change_prior_fit_or_point_prediction(self):
        before = fixture()
        after = copy.deepcopy(before)
        for day in after['days']:
            if day['date'] >= '2015-01-01':
                target = day['sources']['VIIRS_SNPP_SP']
                target['cells'] *= 7
                target['raw'] *= 7
        with patch.object(hybrid.daily, 'fit_predict', mock_fit):
            a = hybrid.analyze(before, platform_counts(before), synthetic=True)
            b = hybrid.analyze(after, platform_counts(after), synthetic=True)
        self.assertEqual(a['rows'][0]['fixed'], b['rows'][0]['fixed'])
        self.assertEqual(a['folds'][0]['training_dates'], b['folds'][0]['training_dates'])
        self.assertNotEqual(a['folds'][0]['radii'], b['folds'][0]['radii'])

    def test_sparse_zero_calibration_fails_closed_and_no_identity_mix(self):
        inputs = fixture()
        for day in inputs['days']:
            modis = day['sources']['MODIS_SP']
            if modis['cells'] == 0:
                modis['cells'] = modis['raw'] = 1
        with patch.object(hybrid.daily, 'fit_predict', mock_fit):
            result = hybrid.analyze(inputs, platform_counts(inputs), synthetic=True)
        self.assertEqual([], result['rows'])
        self.assertTrue(any(s['reason'] == 'calibration-stratum-insufficient' for s in result['skipped']))
        with self.assertRaises(ValueError):
            hybrid.analyze(inputs, platform_counts(inputs), experimental=True)
        with self.assertRaises(ValueError):
            hybrid.analyze({**inputs, 'synthetic': False}, platform_counts(inputs))

    def test_experimental_policy_binds_protocol_and_never_admits(self):
        inputs = {**fixture(), 'synthetic': False}  # in-memory engineering fixture
        review = hybrid.experimental_review()
        with patch.object(hybrid.daily, 'fit_predict', mock_fit):
            result = hybrid.analyze(inputs, platform_counts(inputs), experimental=review)
            self.assertFalse(result['scientific_admission'])
            self.assertFalse(result['estimates_admitted'])
            self.assertTrue(hybrid.verify(result)['verified'])
            forged = copy.deepcopy(review)
            forged['independent_scientific_approval'] = True
            with self.assertRaises(ValueError):
                hybrid.analyze(inputs, platform_counts(inputs), experimental=forged)

    def test_runner_rejects_mismatched_nested_region_before_fitting(self):
        from fireatlas import qualification
        from scripts import evaluate_daily_hybrid as runner
        original = {'schema': 'fireatlas-daily-estimate-research-v2', 'region': 'norcal',
                    'versions': ['61.03', '2'], 'synthetic': False,
                    'experimental_review': qualification.experimental_review('daily'),
                    'inputs': {'region': 'punjab-haryana', 'versions': ['61.03', '2']}}
        original['result_sha256'] = qualification.digest(original)
        entry = {'id': '0123456789abcdef', 'region': 'norcal', 'versions': ['61.03', '2'],
                 'reproduction_artifact': 'cohort-daily/0123456789abcdef.json.gz',
                 'result_sha256': original['result_sha256']}
        def read(_root, name, _release):
            return json.dumps({'entries': [entry]}).encode() if name.startswith('daily-cohorts/') else gzip.compress(json.dumps(original).encode())
        with patch.object(runner.qualification_publication, 'read', side_effect=read), \
             patch.object(runner.daily_estimates, 'verify') as verify, \
             patch.object(runner.hybrid, 'analyze') as fit, \
             patch('sys.argv', ['evaluate_daily_hybrid.py', 'norcal', '--versions', '61.03', '2', '--release', 'a' * 64]):
            with self.assertRaisesRegex(ValueError, 'identity'):
                runner.main()
        verify.assert_not_called()
        fit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
