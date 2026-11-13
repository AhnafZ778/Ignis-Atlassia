"""Synthetic registration tests; scientific validators remain separate."""
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fireatlas.qualification import digest
from scripts import register_daily_research as reg


class DailyRegistrationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
  self.work=root/'work';self.pub=root/'pub';self.work.mkdir();self.pub.mkdir();(self.work/'campaign').mkdir();(self.work/'campaign/.acquisition.lock').touch()
  self.release='a'*64;self.cohort='b'*16;(self.pub/'current.json').write_text(json.dumps({'release_id':self.release}))
  self.original={'synthetic':False,'region':'norcal','versions':['6.03','2']};self.original['result_sha256']=digest(self.original)
  self.summary={'region':'norcal','entries':[{'region':'norcal','versions':['6.03','2'],'id':self.cohort,'reproduction_artifact':'cohort-daily/'+self.cohort+'.json.gz','result_sha256':self.original['result_sha256']}]}
  for prefix in ('daily-hybrid-v1','daily-neighbors-v1'):
   directory=self.work/prefix;directory.mkdir();(directory/'fixture.json.gz').write_bytes(gzip.compress(json.dumps({'original_release_id':self.release,'experiment':{'result_sha256':'c'*64}}).encode()))
  self.report=root/'diagnostic.json';self.report.write_text(json.dumps({'release_id':self.release,'result_sha256':self.original['result_sha256']}))
  (self.work/'successor-evidence.json').write_text(json.dumps({'schema':'fixture','other':{'preserve':True}}))
 def run_register(self):
  return reg.registration(self.work,self.pub,'norcal',['6.03','2'],self.release,'daily-hybrid-v1/fixture.json.gz','daily-neighbors-v1/fixture.json.gz',self.report)
 def read(self,_root,name,_release):
  return json.dumps(self.summary).encode() if name.startswith('daily-cohorts/') else gzip.compress(json.dumps(self.original).encode())
 def test_atomic_index_update_idempotency_and_changed_pointer(self):
  with patch.object(reg.qualification_publication,'read',side_effect=self.read),patch.object(reg.daily_estimates,'verify'),patch.object(reg.successors,'daily_hybrid_asset',return_value=True),patch.object(reg.successors,'daily_neighbors_asset',return_value=True),patch.object(reg.successors,'daily_diagnostics_asset',return_value=True),patch.object(reg.acquisition,'budget'):
   a=self.run_register();first=(self.work/'successor-evidence.json').read_bytes();b=self.run_register()
   self.assertEqual(a,b);self.assertEqual(first,(self.work/'successor-evidence.json').read_bytes())
   data=json.loads(first);self.assertTrue(data['other']['preserve']);self.assertEqual(len(a['registered']),3)
   def switch(*_args): (self.pub/'current.json').write_text(json.dumps({'release_id':'d'*64}));return True
   with patch.object(reg.successors,'daily_diagnostics_asset',side_effect=switch):
    with self.assertRaisesRegex(ValueError,'Release changed'):self.run_register()
   self.assertEqual(first,(self.work/'successor-evidence.json').read_bytes())
 def test_rejects_wrong_release_and_escaped_artifact(self):
  (self.pub/'current.json').write_text(json.dumps({'release_id':'d'*64}))
  with self.assertRaisesRegex(ValueError,'Current release changed'):self.run_register()
  (self.pub/'current.json').write_text(json.dumps({'release_id':self.release}))
  with patch.object(reg.qualification_publication,'read',side_effect=self.read),patch.object(reg.daily_estimates,'verify'):
   with self.assertRaises(ValueError):reg.registration(self.work,self.pub,'norcal',['6.03','2'],self.release,'../outside','daily-neighbors-v1/fixture.json.gz',self.report)
 def test_invalid_diagnostic_leaves_no_artifact_or_index_change(self):
  before=(self.work/'successor-evidence.json').read_bytes()
  with patch.object(reg.qualification_publication,'read',side_effect=self.read),patch.object(reg.daily_estimates,'verify'),patch.object(reg.successors,'daily_hybrid_asset',return_value=True),patch.object(reg.successors,'daily_neighbors_asset',return_value=True),patch.object(reg.successors,'daily_diagnostics_asset',return_value=None),patch.object(reg.acquisition,'budget'):
   with self.assertRaisesRegex(ValueError,'Diagnostics belong'):self.run_register()
  self.assertEqual(before,(self.work/'successor-evidence.json').read_bytes())
  self.assertEqual(list((self.work/'daily-diagnostics-v1').iterdir()),[])
 def test_real_successor_validators_bind_all_three_registrations(self):
  from fireatlas import daily_hybrid_experiment,daily_neighbors_experiment,daily_diagnostics
  from scripts import diagnose_daily_holdouts
  original={'synthetic':False,'region':'norcal','versions':['6.03','2'],'inputs':{'region':'norcal'},'platform_counts':{'date':1},'input_sha256':'e'*64,'checks':{}}
  original['result_sha256']=digest(original);self.original=original;self.summary['entries'][0]['result_sha256']=original['result_sha256']
  source=gzip.compress(json.dumps(original).encode(),mtime=0)
  def read(_root,name,_release):return json.dumps(self.summary).encode() if name.startswith('daily-cohorts/') else source
  names=[]
  for prefix,kind in (('daily-hybrid-v1','hybrid'),('daily-neighbors-v1','neighbors')):
   experiment={'schema':'fireatlas-daily-'+kind+'-experiment-v1','region':'norcal','versions':['6.03','2'],'inputs':original['inputs'],'platform_counts':original['platform_counts'],'synthetic':False,'scientific_admission':False,'estimates_admitted':False}
   experiment['result_sha256']=digest(experiment)
   bundle={'schema':'fireatlas-daily-'+kind+'-bundle-v1','original_release_id':self.release,'original_artifact':'cohort-daily/'+self.cohort+'.json.gz','original_artifact_sha256':hashlib.sha256(source).hexdigest(),'original_result_sha256':original['result_sha256'],'experiment':experiment}
   name=prefix+'/'+digest(bundle)+'.json.gz';(self.work/name).write_bytes(gzip.compress(json.dumps(bundle).encode(),mtime=0));names.append(name)
  report={'schema':'fireatlas-daily-heldout-diagnostic-report-v1','release_id':self.release,'artifact':'cohort-daily/'+self.cohort+'.json.gz','artifact_sha256':hashlib.sha256(source).hexdigest(),'input_sha256':original['input_sha256'],'result_sha256':original['result_sha256'],'region':'norcal','versions':['6.03','2'],'original_checks':{},'method_source_sha256':{},'diagnostics':{'fixture':True},'scientific_admission':False,'daily_estimates_admitted':False}
  self.report.write_text(json.dumps(report))
  with patch.object(reg.qualification_publication,'read',side_effect=read),patch.object(reg.daily_estimates,'verify'),patch.object(daily_hybrid_experiment,'verify') as hybrid_check,patch.object(daily_neighbors_experiment,'verify') as neighbor_check,patch.object(daily_diagnostics,'analyze',return_value={'fixture':True}),patch.object(diagnose_daily_holdouts,'source_hashes',return_value={}),patch.object(reg.acquisition,'budget'):
   result=reg.registration(self.work,self.pub,'norcal',['6.03','2'],self.release,*names,self.report)
   self.assertEqual(len(result['registered']),3);hybrid_check.assert_called_once();neighbor_check.assert_called_once()
   before=(self.work/'successor-evidence.json').read_bytes();diagnostics_before=sorted(p.name for p in (self.work/'daily-diagnostics-v1').iterdir());report['diagnostics']={'fixture':False};self.report.write_text(json.dumps(report))
   with self.assertRaisesRegex(ValueError,'recount differs'):reg.registration(self.work,self.pub,'norcal',['6.03','2'],self.release,*names,self.report)
   self.assertEqual(before,(self.work/'successor-evidence.json').read_bytes())
   self.assertEqual(diagnostics_before,sorted(p.name for p in (self.work/'daily-diagnostics-v1').iterdir()))


if __name__=='__main__':unittest.main()
