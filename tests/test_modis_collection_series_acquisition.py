"""Bounded acquisition behavior with a simulated public archive."""
import gzip
import fcntl
import hashlib
import json
from pathlib import Path
import shlex
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from scripts import acquire_modis_collection_series as cli
from scripts import compare_modis_collection_series as compare
from fireatlas.modis_collection_pilot import HEADER


class FakeSftp:
    def __init__(self, files, behavior=None): self.files=files;self.behavior=behavior or {};self.before='';self.exitstatus=0;self.alive=True
    def expect(self, patterns): return 1 if isinstance(patterns,list) else 0
    def sendline(self, command):
        if command.startswith('ls -l '):
            remote=command[6:]; content=self.files.get(remote)
            self.before='' if content is None else f'-rw-r--r-- 1 x y {len(content)} Jan 1 00:00 {remote}'
        elif command.startswith('get '):
            _, remote, target=shlex.split(command)
            mode=self.behavior.get(remote)
            data=self.files[remote]
            Path(target).write_bytes(data[:-1] if mode=='truncated' else data)
            self.before="Couldn't download file" if mode=='error' else ('Connection reset by peer' if mode=='reset' else '')
        elif command=='bye': self.alive=False
    def close(self, force=False): self.alive=False
    def isalive(self): return self.alive


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.work=Path(self.temp.name);self.dest=self.work/'modis-collection-series-v1'
        (self.work/'campaign').mkdir();(self.work/'campaign/.acquisition.lock').touch()
        payload=gzip.compress((HEADER+'\n20200229 0128 T 39 -121 303.3 292.5 362 7.0 54 0 N\n').encode())
        self.files={f'/data/MODIS/{collection}/MCD14ML/{name}':payload for collection,name in cli.filenames('2020-02').items()}
        self.behavior={}

    def run_acquire(self):
        fake=types.SimpleNamespace(spawn=lambda *a,**k:FakeSftp(self.files,self.behavior),EOF=object(),TIMEOUT=object())
        with patch.object(cli,'public_login',return_value=('unused','unused')), patch.dict(sys.modules,{'pexpect':fake}), patch.object(cli,'budget'):
            return cli.acquire('2020-02',self.work,self.dest)

    def test_resume_and_corruption(self):
        first=self.run_acquire();self.assertEqual(set(first),{'C6','C61'})
        self.assertEqual(first,self.run_acquire())
        path=self.dest/cli.filenames('2020-02')['C6'];path.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):self.run_acquire()

    def test_missing_file_stops_before_download(self):
        self.files.pop(next(iter(self.files)))
        with self.assertRaises(ValueError):self.run_acquire()
        self.assertEqual(list(self.dest.glob('*.gz')),[])

    def test_changed_receipt_and_symlinks_rejected(self):
        result=self.run_acquire();name=cli.filenames('2020-02')['C6']
        path=self.dest/name;receipt=self.dest/(name+'.receipt.json')
        value=json.loads(receipt.read_text());value['month']='2020-03';receipt.write_text(json.dumps(value))
        with self.assertRaises(ValueError):cli.verify_existing(path,receipt,'C6','2020-02')
        self.assertEqual(result['C6']['sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
        path.unlink();path.symlink_to(self.work/'elsewhere')
        with self.assertRaises(ValueError):cli.checked_paths(self.work,self.dest,'2020-02')

    def test_receipt_bound_recount_is_repeatable_and_detects_tampering(self):
        self.run_acquire()
        with patch.object(compare,'budget'):
            first=compare.recount('2020-02',self.work,self.dest)
            self.assertEqual(first,compare.recount('2020-02',self.work,self.dest))
            self.assertEqual(first['regions']['norcal']['month_cell_days']['both'],1)
            name=cli.filenames('2020-02')['C61'];(self.dest/name).write_bytes(b'bad')
            with self.assertRaises(ValueError):compare.recount('2020-02',self.work,self.dest)

    def test_interrupted_second_download_resumes_first(self):
        second=list(self.files)[1];self.behavior[second]='truncated'
        with self.assertRaises(ValueError):self.run_acquire()
        self.assertTrue((self.dest/(cli.filenames('2020-02')['C6']+'.receipt.json')).exists())
        self.assertFalse((self.dest/(cli.filenames('2020-02')['C61']+'.receipt.json')).exists())
        self.behavior.clear()
        self.assertEqual(set(self.run_acquire()),{'C6','C61'})

    def test_reported_failure_even_with_complete_bytes_is_not_receipted(self):
        for mode in ('error','reset'):
            with self.subTest(mode=mode):
                self.behavior[next(iter(self.files))]=mode
                with self.assertRaises(ValueError):self.run_acquire()
                self.assertFalse(any(self.dest.glob('*.receipt.json')))

    def test_storage_limit_stops_before_network(self):
        with patch.object(cli,'budget',side_effect=ValueError('budget exceeded')), patch.object(cli,'public_login') as login:
            with self.assertRaisesRegex(ValueError,'budget exceeded'):cli.acquire('2020-02',self.work,self.dest)
            login.assert_not_called()

    def test_invalid_gzip_is_not_receipted(self):
        first=next(iter(self.files));self.files[first]=b'not-gzip'
        with self.assertRaises((ValueError,OSError,EOFError)):self.run_acquire()
        self.assertFalse(any(self.dest.glob('*.receipt.json')))

    def test_changed_original_during_recount_is_rejected(self):
        self.run_acquire();real=compare.compare_month
        def mutate(month,paths,provenance):
            result=real(month,paths,provenance)
            paths['C6'].write_bytes(b'changed')
            return result
        with patch.object(compare,'compare_month',side_effect=mutate),patch.object(compare,'budget'):
            with self.assertRaises(ValueError):compare.recount('2020-02',self.work,self.dest)
        self.assertFalse(any(self.dest.glob('comparison-*.json')))

    def test_budget_check_runs_while_exclusive_lock_is_held(self):
        def check_lock(*args):
            with (self.work/'campaign/.acquisition.lock').open('a') as other:
                with self.assertRaises(BlockingIOError):fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB)
            raise ValueError('stop before network')
        with patch.object(cli,'budget',side_effect=check_lock):
            with self.assertRaisesRegex(ValueError,'stop before network'):cli.acquire('2020-02',self.work,self.dest)
