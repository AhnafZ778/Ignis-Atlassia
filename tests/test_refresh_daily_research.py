"""Synthetic checks for daily research refresh orchestration."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import refresh_daily_research as refresh


class DailyRefreshTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=Path(self.temp.name)
  self.work=root/'work';self.pub=root/'pub';self.work.mkdir();self.pub.mkdir();self.release='a'*64
  (self.work/'campaign').mkdir();(self.work/'campaign/.acquisition.lock').touch()
  (self.pub/'current.json').write_text(json.dumps({'release_id':self.release}))
  self.paths=[]
  for name in ('hybrid.gz','neighbors.gz'):
   path=self.work/name;path.write_bytes(b'fixture');self.paths.append(path)
  self.summary={'region':'norcal','entries':[{'region':'norcal','versions':['6.03','2']}]} 
 def test_runs_all_steps_before_registration_and_rejects_wrong_scope(self):
  calls=[]
  def run(script,region,versions,release,output):
   calls.append(script);out={'region':region,'versions':versions,'estimates_admitted':False}
   if script=='evaluate_daily_hybrid.py':out['path']=str(self.paths[0])
   elif script=='evaluate_daily_neighbors.py':out['path']=str(self.paths[1])
   else:out={'region':region,'versions':versions,'daily_estimates_admitted':False};output.write_text(json.dumps(out))
   return out
  with patch.object(refresh,'WORK',self.work),patch.object(refresh,'PUBLICATION',self.pub),patch.object(refresh.qualification_publication,'read',return_value=json.dumps(self.summary).encode()),patch.object(refresh,'run_command',side_effect=run),patch.object(refresh.register_daily_research,'registration',return_value={'registered':True}) as register:
   self.assertTrue(refresh.refresh('norcal',['6.03','2'],self.release)['registered'])
   self.assertEqual(len(calls),3);register.assert_called_once()
   def wrong(*args):return {'region':'punjab-haryana','versions':['6.03','2'],'estimates_admitted':False}
   with patch.object(refresh,'run_command',side_effect=wrong):
    with self.assertRaises(ValueError):refresh.refresh('norcal',['6.03','2'],self.release)
   self.assertEqual(register.call_count,1)
 def test_rejects_stale_release_before_running(self):
  with patch.object(refresh,'WORK',self.work),patch.object(refresh,'PUBLICATION',self.pub),patch.object(refresh,'run_command') as run:
   with self.assertRaisesRegex(ValueError,'Current release changed'):refresh.refresh('norcal',['6.03','2'],'b'*64)
   run.assert_not_called()
 def test_command_output_bound_fails_closed(self):
  class Process:
   def __init__(self):self.stdout=io.BytesIO(b'x'*(refresh.LIMIT+1));self.returncode=None;self.killed=False
   def poll(self):return self.returncode
   def kill(self):self.killed=True;self.returncode=-9
   def wait(self):self.returncode=self.returncode if self.returncode is not None else 0;return self.returncode
  proc=Process()
  with patch.object(refresh.subprocess,'Popen',return_value=proc),patch.object(refresh.acquisition,'budget'):
   with self.assertRaisesRegex(ValueError,'exceeds bound'):refresh.run_command('fixture.py','norcal',['6.03','2'],self.release,self.work/'output')
   self.assertTrue(proc.killed);self.assertFalse((self.work/'output').exists())
 def test_temporary_output_is_budgeted_and_confined(self):
  with patch.object(refresh,'WORK',self.work),patch.object(refresh.acquisition,'budget',side_effect=ValueError('budget')):
   with self.assertRaisesRegex(ValueError,'budget'):refresh.store_output(self.work/'result',b'abc')
   self.assertFalse((self.work/'result').exists())
  with patch.object(refresh,'WORK',self.work),patch.object(refresh.acquisition,'budget') as budget:
   refresh.store_output(self.work/'result',b'abc');budget.assert_called_once_with(self.work,3)
   self.assertEqual((self.work/'result').read_bytes(),b'abc')
   with self.assertRaises(ValueError):refresh.store_output(self.work.parent/'outside',b'abc')
 def test_hung_subprocess_is_terminated_without_output(self):
  root=self.work.parent;directory=root/'scripts';directory.mkdir();(directory/'hang.py').write_text('import time\ntime.sleep(3)\n')
  timer=refresh.threading.Timer
  with patch.object(refresh,'ROOT',root),patch.object(refresh.threading,'Timer',side_effect=lambda _delay,fn:timer(0.05,fn)):
   with self.assertRaisesRegex(ValueError,'failed'):refresh.run_command('hang.py','norcal',['6.03','2'],self.release,self.work/'output')
  self.assertFalse((self.work/'output').exists())


if __name__=='__main__':unittest.main()
