"""Isolated provenance fixtures: no NASA or human review is asserted."""
import copy
import json
import sqlite3
import tempfile
import unittest
import weakref
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fireatlas import acquisition, transfer, transfer_provenance as provenance
from fireatlas.core import connect, ingest
from fireatlas.regions import REGIONS
from tests.test_qualification import HEADER, Response


class TransferProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        products = [{'data_id':s,'min_date':'2010-01-01','max_date':'2026-12-31'} for s in ('MODIS_SP','VIIRS_SNPP_SP')]
        self.discovery = {'schema':'fireatlas-source-availability-v1','retrieved_utc':datetime.now(timezone.utc).isoformat(),'products':products}
        self.cohorts = [{'source':'MODIS_SP','version':'6.03'}, {'source':'VIIRS_SNPP_SP','version':'2'}]

    def populate(self, *, prior=False, empty=False):
        for source,sat,instrument,version in [('MODIS_SP','T','MODIS','6.03'),('VIIRS_SNPP_SP','N','VIIRS','2')]:
            row=f'40,-121,2012-02-01,1200,{sat},{instrument},90,{version},1,1,2,D\n'
            if prior and source=='MODIS_SP':
                path=self.root/'earlier.csv';path.write_text(HEADER+row)
                with connect(self.root/'observations.sqlite3') as db:
                    ingest(db,path,source,batch_key='earlier-owner')
            plan=acquisition.plan('norcal',['2012-02'],[source],self.discovery)
            calls=iter([HEADER+(row if not empty else '')]+[HEADER]*(len(plan['requests'])-1))
            with patch.object(acquisition,'firms_key',return_value='fixture'),patch.object(acquisition.time,'sleep'):
                acquisition.acquire(self.root,plan,opener=lambda *a,**k: Response(next(calls).encode()))
            acquisition.import_month(self.root,plan,source,'2012-02')
        with connect(self.root/'observations.sqlite3') as db:
            return transfer.capture(db,'norcal',*self.cohorts)

    def verify(self, inputs):
        return provenance.verify_capture(inputs,self.root/'observations.sqlite3',self.root)

    def test_verified_capture_and_idempotent_reimport(self):
        inputs=self.populate()
        result=self.verify(inputs)
        self.assertEqual('verified',result['status'])
        self.assertFalse(result['scientific_admission'])
        plan=json.loads(next((self.root/'plans').glob('*.json')).read_text())
        acquisition.import_month(self.root,plan,plan['requests'][0]['source'],'2012-02')
        self.assertEqual(result,self.verify(inputs))

    def test_aggregate_memory_budget_rejects_oversized_capture(self):
        inputs=self.populate()
        with patch.object(provenance,'MAX_CAPTURE_DETECTIONS',0):
            with self.assertRaisesRegex(ValueError,'Aggregate capture'):
                self.verify(inputs)

    def test_role_memory_and_combined_work_are_bounded_separately(self):
        inputs=self.populate()
        # One detection per role fits the resident bound even though the
        # combined input contains two detections. The global work bound stays.
        with patch.object(provenance,'MAX_ROLE_DETECTIONS',1),patch.object(provenance,'MAX_CAPTURE_DETECTIONS',2):
            self.assertEqual('verified',self.verify(inputs)['status'])
        with patch.object(provenance,'MAX_ROLE_DETECTIONS',0):
            with self.assertRaisesRegex(ValueError,'Per-role capture'):
                self.verify(inputs)
        with patch.object(provenance,'MAX_ROLE_DETECTIONS',1),patch.object(provenance,'MAX_CAPTURE_DETECTIONS',1):
            with self.assertRaisesRegex(ValueError,'Aggregate capture'):
                self.verify(inputs)

    def test_previous_role_batches_do_not_survive_into_next_role(self):
        inputs=self.populate()
        original=provenance._month;references=[]
        class WeakDict(dict):pass
        def tracked(root,batch,requests,version,**kwargs):
            if batch['source_id']=='VIIRS_SNPP_SP':
                self.assertTrue(references)
                self.assertIsNone(references[-1](), 'Previous role retained its batch while the next began')
            value,reason,processed=original(root,batch,requests,version,**kwargs)
            if value is not None:
                value=WeakDict(value)
                if batch['source_id']=='MODIS_SP':references.append(weakref.ref(value))
            return value,reason,processed
        with patch.object(provenance,'_month',side_effect=tracked):
            self.assertEqual('verified',self.verify(inputs)['status'])

    def test_partial_month_rows_count_towards_combined_work_bound(self):
        inputs=self.populate()
        (self.root/'months/norcal-MODIS_SP-2012-02.csv').unlink()
        with patch.object(provenance,'MAX_CAPTURE_DETECTIONS',1):
            with self.assertRaisesRegex(ValueError,'Aggregate capture'):
                self.verify(inputs)

    def test_prior_first_owner_is_partial(self):
        inputs=self.populate(prior=True)
        result=self.verify(inputs)
        self.assertEqual('partial',result['status'])
        self.assertIn('source:first-owner-not-verified',result['reasons'])

    def test_missing_request_and_plan_remain_partial(self):
        inputs=self.populate()
        next((self.root/'requests').glob('*.csv')).unlink()
        self.assertEqual('partial',self.verify(inputs)['status'])
        for plan in (self.root/'plans').glob('*.json'): plan.unlink()
        self.assertEqual('partial',self.verify(inputs)['status'])

    def test_earlier_role_files_changed_during_later_role_fail(self):
        for kind in ('request','receipt','merged','plan'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as td:
                self.root=Path(td);inputs=self.populate()
                plan_path=next(p for p in (self.root/'plans').glob('*.json')
                               if json.loads(p.read_text())['requests'][0]['source']=='MODIS_SP')
                request_id=json.loads(plan_path.read_text())['requests'][0]['id']
                paths={'request':self.root/'requests'/(request_id+'.csv'),
                       'receipt':self.root/'requests'/(request_id+'.json'),
                       'merged':self.root/'months'/'norcal-MODIS_SP-2012-02.csv',
                       'plan':plan_path}
                original=provenance._verify_role
                def alter_later(db,root,plans,material,role,cohort,total,fingerprints):
                    if role=='target':
                        with paths[kind].open('a') as stream:stream.write('\n')
                    return original(db,root,plans,material,role,cohort,total,fingerprints)
                with patch.object(provenance,'_verify_role',side_effect=alter_later):
                    with self.assertRaisesRegex(ValueError,'changed before verification completed'):
                        self.verify(inputs)
    def test_changed_original_or_capture_fails(self):
        inputs=self.populate()
        p=next((self.root/'requests').glob('*.csv'));p.write_text(p.read_text()+'\n')
        with self.assertRaises(ValueError): self.verify(inputs)
        changed=copy.deepcopy(inputs);changed['daily_cells'][0]['cells'][0][0]+=1
        changed['input_sha256']=__import__('fireatlas.qualification',fromlist=['digest']).digest({k:v for k,v in changed.items() if k!='input_sha256'})
        with self.assertRaises(ValueError): self.verify(changed)

    def test_empty_exports_do_not_prove_product_version(self):
        inputs=self.populate(empty=True)
        self.assertEqual([],inputs['export_ledger'])
        result=self.verify(inputs)
        self.assertEqual('partial',result['status'])
        self.assertFalse(result['original_sources_reopened'])

    def test_duplicate_and_version_guards(self):
        inputs=self.populate()
        altered=copy.deepcopy(inputs);altered['daily_cells'].append(copy.deepcopy(altered['daily_cells'][0]))
        from fireatlas.qualification import digest
        altered['input_sha256']=digest({k:v for k,v in altered.items() if k!='input_sha256'})
        with self.assertRaises(ValueError):self.verify(altered)
        altered=copy.deepcopy(inputs);altered['source_cohort']['version']='wrong'
        altered['input_sha256']=digest({k:v for k,v in altered.items() if k!='input_sha256'})
        with self.assertRaises(ValueError):self.verify(altered)

    def test_resealed_notice_snapshot_cannot_change_evidence_provenance(self):
        import hashlib
        from fireatlas.qualification import digest
        inputs=self.populate();altered=copy.deepcopy(inputs)
        text=json.dumps({'schema':'fireatlas-sensor-notices-v1','notices':[]})
        altered['notice_snapshot']={'source_utf8':text,'sha256':hashlib.sha256(text.encode()).hexdigest()}
        altered['input_sha256']=digest({k:v for k,v in altered.items() if k!='input_sha256'})
        transfer.validate(altered,False)
        with self.assertRaisesRegex(ValueError,'notice_snapshot'):self.verify(altered)

    def test_omitted_or_altered_original_detection_fails(self):
        for action in ('delete', 'alter'):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as td:
                self.root=Path(td)
                inputs=self.populate()
                with sqlite3.connect(self.root/'observations.sqlite3') as db:
                    if action=='delete':
                        db.execute("DELETE FROM observations WHERE source_id='MODIS_SP'")
                    else:
                        db.execute("UPDATE observations SET raw_json='{}' WHERE source_id='MODIS_SP'")
                with self.assertRaises(ValueError):self.verify(inputs)


if __name__=='__main__':unittest.main()
