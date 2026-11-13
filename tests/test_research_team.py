"""Billing, isolation and failure behavior for the actual specialist runner."""
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fireatlas.assistant.contracts import normalize_context
from fireatlas.assistant.store import Store
from fireatlas.assistant.research_team import configuration, review

MODEL={'model':'test-cheap','input_price':.1,'output_price':.3,'reasoning_effort':'low'}
VALID=json.dumps({'insight':'The checked values support a descriptive comparison.','next_test':'Match acquisition times before testing the weather hypothesis.','source_ids':[]})

class ResearchTeamTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'assistant.sqlite3')
        self.owner=self.store.create_session(normalize_context({}))
        self.service=SimpleNamespace(store=self.store)

    def run_review(self,answer=None,cancel=None):
        with patch('fireatlas.assistant.research_team.configuration',return_value=MODEL),patch('fireatlas.assistant.agent.provider_config',return_value={'provider':'aiand'}):
            return review(self.service,self.owner,'Explain the wildfire study.',answer or {'claims':[]},{},cancel or threading.Event(),time.monotonic()+30,lambda _:None)

    def test_three_roles_use_one_prior_reservation_and_known_usage_reconciles(self):
        def call(*args):
            with self.store.connection() as db:
                rows=db.execute('SELECT state FROM reservations').fetchall()
            self.assertEqual([r['state'] for r in rows],['reserved'])
            self.assertLessEqual(len(json.dumps(args[1],ensure_ascii=False).encode()),6000)
            return VALID,{'prompt_tokens':100,'completion_tokens':100}
        with patch('fireatlas.assistant.research_team._call',side_effect=call) as model:
            result=self.run_review()
        self.assertEqual(model.call_count,3)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(len({r['role'] for r in result['specialists']}),3)
        self.assertAlmostEqual(result['estimated_cost_usd'],.00012)
        self.assertLessEqual(result['reserved_usd'],.02)
        other=self.store.create_session(normalize_context({}))
        with self.assertRaises(PermissionError):self.store.get_artifact(other,result['receipt_id'])

    def test_unknown_billed_call_is_not_retried_or_refunded(self):
        with patch('fireatlas.assistant.research_team._call',side_effect=TimeoutError) as model:
            result=self.run_review()
        self.assertEqual(model.call_count,3)
        self.assertEqual(result['status'],'unavailable')
        self.assertIsNone(result['estimated_cost_usd'])
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT state FROM reservations').fetchone()['state'],'reserved')

    def test_unsupported_numbers_and_invented_citations_are_withheld(self):
        invalid=json.dumps({'insight':'There were 999 fires.','next_test':'Check records.','source_ids':['R99']})
        with patch('fireatlas.assistant.research_team._call',return_value=(invalid,{'prompt_tokens':100,'completion_tokens':100})):
            result=self.run_review()
        self.assertEqual(result['status'],'unavailable')
        self.assertTrue(all('insight' not in r for r in result['specialists']))

    def test_retrieved_product_names_and_actual_citations_do_not_become_count_permissions(self):
        source={'title':'VIIRS 375m active fire product','url':'https://doi.org/10.1234/viirs'}
        for text,ids,status in (
            ('Review the VIIRS 375 m product methods (R1).',['R1'],'completed'),
            ('There were 375 thermal records.',['R1'],'unavailable'),
            ('Review another reference (R9).',['R1'],'unavailable'),
            ('Review the VIIRS 750 m product methods.',['R1'],'unavailable'),
        ):
            raw=json.dumps({'insight':text,'next_test':'Match acquisition times before testing the weather hypothesis.','source_ids':ids})
            with self.subTest(text=text),patch('fireatlas.assistant.research_team._call',return_value=(raw,{'prompt_tokens':100,'completion_tokens':100})):
                self.assertEqual(self.run_review({'claims':[],'web_sources':[source]})['status'],status)

    def test_truncated_outputs_are_withheld_and_reported_usage_is_settled(self):
        with patch('fireatlas.assistant.research_team._call',return_value=(VALID,{'prompt_tokens':100,'completion_tokens':420,'finish_reason':'length'})) as call:
            result=self.run_review()
        self.assertEqual(call.call_count,3)
        self.assertTrue(all(r['reason_code']=='output_limit' for r in result['specialists']))
        self.assertIsNotNone(result['estimated_cost_usd'])

    def test_cancel_before_start_and_insufficient_allowance_send_no_inference(self):
        cancel=threading.Event();cancel.set()
        with patch('fireatlas.assistant.research_team._call') as model:
            with self.assertRaises(InterruptedError):self.run_review(cancel=cancel)
            self.store.session_limit=1
            with self.assertRaisesRegex(ValueError,'allowance'):self.run_review()
        model.assert_not_called()

    def test_oversized_context_sends_no_inference_and_reserves_nothing(self):
        with patch('fireatlas.assistant.research_team._call') as model:
            with self.assertRaisesRegex(ValueError,'too large'):
                self.run_review({'claims':[{'label':'🌋'*1500,'value':'🌋'*1500} for _ in range(12)]})
        model.assert_not_called()
        with self.store.connection() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM reservations').fetchone()[0],0)

    def test_current_provider_and_high_prices_cannot_trigger_paid_fallback(self):
        with patch('fireatlas.assistant.aiand.verified_model') as verify:
            with self.assertRaisesRegex(ValueError,'current provider'):configuration('local')
            verify.assert_not_called()
        with patch('fireatlas.assistant.aiand.verified_model',return_value={**MODEL,'output_price':5}):
            with self.assertRaisesRegex(ValueError,'prices'):configuration('aiand')


if __name__=='__main__':unittest.main()
