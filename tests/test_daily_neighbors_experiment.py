"""Synthetic engineering checks; these are not scientific validation."""
import copy
import unittest
from unittest.mock import patch

from fireatlas import daily_neighbors_experiment as neighbors
from tests.test_daily_hybrid_experiment import mock_fit, platform_counts
from tests.test_qualification import fixture


class SimilarDayTests(unittest.TestCase):
    def test_prediction_uses_only_training_reference_and_stable_ties(self):
        base = {'modis': 0, 'terra': 0, 'aqua': 0}
        train = [{**base, 'date': '2012-01-01', 'viirs': 0},
                 {**base, 'date': '2013-01-01', 'viirs': 8}]
        target = [{**base, 'date': '2014-01-01', 'viirs': 1}]
        first = neighbors.predict(train, target, k=2)
        self.assertEqual(first, {'expected': [4.0], 'probability_positive': [0.5]})
        target[0]['viirs'] = 999
        self.assertEqual(first, neighbors.predict(list(reversed(train)), target, k=2))
        with self.assertRaisesRegex(ValueError, 'Insufficient'):
            neighbors.predict(train, target, k=3)

    def test_chronology_recount_and_tampering(self):
        inputs = fixture()
        with patch.object(neighbors.daily, 'fit_predict', mock_fit):
            result = neighbors.analyze(inputs, platform_counts(inputs), synthetic=True)
            self.assertEqual(len(result['folds']), 3)
            self.assertFalse(result['scientific_admission'])
            self.assertFalse(result['estimates_admitted'])
            self.assertEqual(sum(b['n'] for b in result['occurrence_calibration']), len(result['rows']))
            self.assertGreaterEqual(result['occurrence_brier'], 0)
            self.assertLessEqual(result['occurrence_brier'], 1)
            self.assertIn('statsmodels', result['environment'])
            self.assertEqual(result['baseline_protocol']['id'], 'daily-hybrid-v1.0.0')
            for fold in result['folds']:
                self.assertLess(max(fold['training_dates']), min(fold['calibration_dates']))
                self.assertLess(max(fold['calibration_dates']), min(fold['test_dates']))
            self.assertEqual(len(result['rows']), sum(len(f['test_dates']) for f in result['folds']))
            self.assertTrue(neighbors.verify(result)['verified'])
            tampered = copy.deepcopy(result)
            tampered['rows'][0]['fixed'][neighbors.MODEL] += 1
            with self.assertRaisesRegex(ValueError, 'recount'):
                neighbors.verify(tampered)

    def test_heldout_viirs_does_not_affect_its_prediction_or_interval(self):
        before = fixture();after = copy.deepcopy(before)
        for day in after['days']:
            if day['date'] >= '2017-01-01':
                source = day['sources']['VIIRS_SNPP_SP']
                source['cells'] *= 7;source['raw'] *= 7
        with patch.object(neighbors.daily, 'fit_predict', mock_fit):
            a = neighbors.analyze(before, platform_counts(before), synthetic=True)
            b = neighbors.analyze(after, platform_counts(after), synthetic=True)
        x = next(r for r in a['rows'] if r['year'] == 2017)
        y = next(r for r in b['rows'] if r['year'] == 2017)
        self.assertEqual(x['fixed'][neighbors.MODEL], y['fixed'][neighbors.MODEL])
        self.assertEqual(x['fixed_intervals'][neighbors.MODEL], y['fixed_intervals'][neighbors.MODEL])


if __name__ == '__main__':
    unittest.main()
