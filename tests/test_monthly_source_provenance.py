"""Synthetic local fixtures for monthly original-file binding, never science approval."""
import copy
import unittest
from unittest.mock import patch

from fireatlas import comparability, comparability_v2, monthly_source_provenance, qualification
from fireatlas.core import connect
from tests.test_transfer_provenance import TransferProvenanceTests


class MonthlySourceTests(unittest.TestCase):
    def setUp(self):
        self.source_fixture=TransferProvenanceTests('test_verified_capture_and_idempotent_reimport')
        self.source_fixture.setUp()
        self.addCleanup(self.source_fixture.doCleanups)
        self.root=self.source_fixture.root

    def evidence(self, *, prior=False):
        capture=self.source_fixture.populate(prior=prior)
        with connect(self.root/'observations.sqlite3') as db:
            inputs=comparability.capture(db,'norcal')
        inputs['versions']=['6.03','2']
        bundle=comparability_v2.analyze(inputs,experimental=qualification.experimental_review('monthly'))
        return bundle,capture

    def verify(self,bundle,capture):
        return monthly_source_provenance.verify(bundle,capture,self.root/'observations.sqlite3',self.root)

    def test_eligible_source_counts_reproduce_without_scientific_admission(self):
        bundle,capture=self.evidence();proof=self.verify(bundle,capture)
        self.assertEqual(proof['status'],'verified')
        self.assertEqual(proof['eligible_months'],1)
        self.assertEqual(proof['eligible_utc_days_checked'],29)
        self.assertTrue(proof['original_sources_reopened'])
        self.assertFalse(proof['scientific_admission'])
        self.assertIn('Raw detection totals',proof['scope'])

    def test_daily_mismatch_cannot_hide_in_equal_monthly_total(self):
        bundle,capture=self.evidence();inputs=copy.deepcopy(bundle['inputs'])
        first,second=inputs['days'][:2]
        first['sources']['MODIS_SP']['cells']=0
        second['sources']['MODIS_SP']['cells']=1;second['sources']['MODIS_SP']['raw']=1
        altered=comparability_v2.analyze(inputs,experimental=qualification.experimental_review('monthly'))
        with self.assertRaisesRegex(ValueError,'daily cell count differs'):
            self.verify(altered,capture)

    def test_wrong_cohort_synthetic_and_tampered_result_rejected(self):
        bundle,capture=self.evidence();wrong=copy.deepcopy(capture);wrong['target_cohort']['version']='other'
        with self.assertRaisesRegex(ValueError,'exact cohort differs'):self.verify(bundle,wrong)
        forged=copy.deepcopy(bundle);forged['result']['eligible_months']=999
        with self.assertRaises(ValueError):self.verify(forged,capture)
        synthetic=copy.deepcopy(bundle);synthetic['result']['synthetic']=True
        with patch.object(comparability_v2,'verify',return_value={'synthetic':True}):
            with self.assertRaisesRegex(ValueError,'synthetic'):self.verify(synthetic,capture)

    def test_missing_original_and_unverified_first_owner_remain_partial(self):
        bundle,capture=self.evidence(prior=True)
        proof=self.verify(bundle,capture)
        self.assertEqual(proof['status'],'partial')
        self.assertFalse(proof['original_sources_reopened'])
        self.assertIn('source:first-owner-not-verified',proof['source_verification']['reasons'])

    def test_missing_original_receipt_remains_partial(self):
        bundle,capture=self.evidence()
        next((self.root/'requests').glob('*.csv')).unlink()
        proof=self.verify(bundle,capture)
        self.assertEqual(proof['status'],'partial')
        self.assertFalse(proof['original_sources_reopened'])

    def test_acquisition_lock_prevents_a_concurrent_source_check(self):
        import fcntl
        bundle,capture=self.evidence()
        with (self.root/'.acquisition.lock').open('a') as guard:
            fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'Campaign acquisition is active'):
                self.verify(bundle,capture)
            with patch.object(monthly_source_provenance,'capture_for_bundle') as capture_call:
                with self.assertRaisesRegex(ValueError,'Campaign acquisition is active'):
                    monthly_source_provenance.verify_bundle(bundle,self.root/'observations.sqlite3',self.root)
                capture_call.assert_not_called()

    def test_capture_and_recount_share_the_campaign_lock(self):
        import fcntl
        bundle,_=self.evidence()
        original=monthly_source_provenance.capture_for_bundle
        def capture_while_locked(*args):
            with (self.root/'.acquisition.lock').open('a') as guard:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
            return original(*args)
        with patch.object(monthly_source_provenance,'capture_for_bundle',side_effect=capture_while_locked):
            proof=monthly_source_provenance.verify_bundle(bundle,self.root/'observations.sqlite3',self.root)
        self.assertEqual(proof['status'],'verified')

    def test_zero_eligible_months_cannot_be_verified(self):
        bundle,capture=self.evidence();inputs=copy.deepcopy(bundle['inputs'])
        for day in inputs['days']:day['sources']['MODIS_SP']['processing_gap']=True
        empty=comparability_v2.analyze(inputs,experimental=qualification.experimental_review('monthly'))
        proof=self.verify(empty,capture)
        self.assertEqual(proof['eligible_months'],0)
        self.assertEqual(proof['status'],'partial')
        self.assertFalse(proof['original_sources_reopened'])


if __name__=='__main__':unittest.main()
