"""Manufactured fixtures exercise engineering guards, not scientific review."""
import copy
import unittest

from fireatlas import historical_successor as historical, transfer_opportunity
from fireatlas.qualification import digest
from tests.test_transfer_opportunity import count_evidence


class HistoricalSuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = transfer_opportunity.build(count_evidence())
        cls.output = historical.build(cls.evidence)

    def test_recounts_original_cohort_observations_and_keeps_historical_closed(self):
        result = self.output
        self.assertEqual(192, len(result['observations']))
        self.assertEqual([], result['estimates'])
        self.assertFalse(result['historical_deployment_admitted'])
        self.assertFalse(result['original_source_files_verified'])
        self.assertEqual('asserted-fingerprints-not-reopened',result['source_provenance_status'])
        self.assertFalse(result['overlap_admission']['admitted'])
        self.assertTrue(historical.verify(result, self.evidence)['verified'])
        for row in result['observations']:
            self.assertEqual('observation', row['kind'])
            self.assertEqual(self.evidence['count_evidence']['input_sha256'], row['input_sha256'])

    def test_raw_and_summary_tampering_rejected_even_if_rehashed(self):
        evidence = copy.deepcopy(self.evidence)
        evidence['count_evidence']['inputs']['months'][0]['source_count'] += 1
        evidence['count_evidence']['inputs']['input_sha256'] = digest({k:v for k,v in evidence['count_evidence']['inputs'].items() if k != 'input_sha256'})
        evidence['result_sha256'] = digest({k:v for k,v in evidence.items() if k != 'result_sha256'})
        with self.assertRaises(ValueError): historical.build(evidence)
        value = copy.deepcopy(self.output)
        value['observations'][0]['count'] += 1
        value['result_sha256'] = digest({k:v for k,v in value.items() if k != 'result_sha256'})
        with self.assertRaisesRegex(ValueError, 'recount'): historical.verify(value, self.evidence)
        with self.assertRaises(ValueError): historical.build({'admitted': True})

    def test_compact_iso_daily_dates_are_counted_in_their_canonical_month(self):
        from fireatlas import transfer
        inputs=copy.deepcopy(self.evidence['count_evidence']['inputs'])
        inputs['daily_cells'][0]['date']=inputs['daily_cells'][0]['date'].replace('-','')
        inputs['input_sha256']=digest({k:v for k,v in inputs.items() if k!='input_sha256'})
        transfer.validate(inputs,True)
        evidence=transfer_opportunity.build(transfer.analyze(inputs,synthetic=True))
        result=historical.build(evidence)
        month=next(row for row in result['observations'] if row['cohort']==evidence['source_cohort'] and row['month']=='2012-01')
        self.assertEqual(2,month['count'])

    def test_candidates_require_bound_source_scope_unique_dates_and_finite_intervals(self):
        evidence = self.evidence
        observation = next(r for r in self.output['observations'] if r['cohort'] == evidence['source_cohort'])
        model = {'transfer_evidence_sha256': evidence['result_sha256'], 'region': evidence['region'],
                 'source_cohort': evidence['source_cohort'], 'target_cohort': evidence['target_cohort']}
        row = {'kind': 'counterfactual-estimate', 'month': observation['month'], 'region': evidence['region'],
               'source_cohort': evidence['source_cohort'], 'target_cohort': evidence['target_cohort'],
               'model': model, 'model_sha256': digest(model), 'input_sha256': digest(observation),
               'value': 2., 'interval': [0., 4.]}
        # A manufactured non-overlap subset tests validation only. No candidate is admitted.
        historical._validate_candidates([row], [observation], evidence)
        with self.assertRaisesRegex(ValueError, 'overwrite'): historical._validate_candidates([row], self.output['observations'], evidence)
        with self.assertRaisesRegex(ValueError, 'Duplicate'): historical._validate_candidates([row, row], [observation], evidence)
        for key, val in [('interval', [4, 1]), ('interval', [0, float('inf')]), ('value', float('nan')),
                         ('model_sha256', 'm'), ('input_sha256', 'i'), ('region', 'another')]:
            changed = copy.deepcopy(row); changed[key] = val
            with self.subTest(key=key, val=val), self.assertRaises(ValueError):
                historical._validate_candidates([changed], [observation], evidence)

    def test_approval_flags_and_changed_conclusions_cannot_bypass_recount(self):
        evidence = copy.deepcopy(self.evidence)
        evidence['ready_for_conclusions'] = True
        evidence['checks'] = {key: True for key in evidence['checks']}
        evidence['result_sha256'] = digest({k:v for k,v in evidence.items() if k != 'result_sha256'})
        with self.assertRaises(ValueError): historical.build(evidence, conclusions={'admitted':True})


if __name__ == '__main__': unittest.main()
