"""Synthetic-only checks for bounded public monthly archive acquisition."""
import gzip
import hashlib
import json
import os
import shlex
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import acquire_modis_collection_overlap as acquire


def receipt_for(path,collection,name):
    return {'schema':'fireatlas-modis-month-download-v1','provider':'University of Maryland MODIS fire team',
            'server':acquire.HOST,'remote_path':f'/data/MODIS/{collection}/MCD14ML/{name}',
            'collection':collection,'filename':name,'month':'2023-01','retrieved_utc':'2026-01-01T00:00:00+00:00',
            'download_complete':True,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'expanded_bytes':8}


class FakeSFTP:
    EOF=object();TIMEOUT=object()
    def __init__(self,body):self.body=body;self.before='';self.exitstatus=0
    def expect(self,_pattern):return 0
    def sendline(self,line):
        if line.startswith('ls -l '):
            remote=line[6:];self.before=f'-rw-r--r-- 1 owner group {len(self.body)} Jan 01 00:00 {remote}\n'
        elif line.startswith('get '):
            target=shlex.split(line)[2];Path(target).write_bytes(self.body)
    def isalive(self):return False
    def close(self,force=False):pass


class ModisCollectionAcquisitionTests(unittest.TestCase):
    def test_guide_output_is_bounded_while_streaming(self):
        command=(sys.executable,'-c','import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write(b"x"*2000001)')
        with patch.object(acquire,'GUIDE_COMMAND',command):
            with self.assertRaisesRegex(ValueError,'exceeds bound'):
                acquire.extract_guide_text(b'fixture')
        command=(sys.executable,'-c','import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write(b"small")')
        with patch.object(acquire,'GUIDE_COMMAND',command):
            self.assertEqual(acquire.extract_guide_text(b'fixture'),b'small')

    def test_repeat_import_checks_originals_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory);dest=work/'pilot';dest.mkdir();(work/'campaign').mkdir()
            for collection,name in acquire.FILES.items():
                path=dest/name;path.write_bytes(gzip.compress(b'example\n'))
                (dest/(name+'.receipt.json')).write_text(json.dumps(receipt_for(path,collection,name)))
            with patch.object(acquire,'WORK',work),patch.object(acquire,'DEST',dest),patch.object(acquire,'public_login') as login:
                self.assertEqual(len(acquire.acquire()),2);login.assert_not_called()
                first=dest/next(iter(acquire.FILES.values()));first.write_bytes(b'corrupt')
                with self.assertRaisesRegex(ValueError,'differs'):acquire.acquire()
                login.assert_not_called()

    def test_receipt_provenance_tampering_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.gz';path.write_bytes(gzip.compress(b'example\n'))
            receipt=path.with_suffix('.json');record=receipt_for(path,'C6',acquire.FILES['C6'])
            for key,value in [('provider','forged'),('server','other'),('remote_path','/elsewhere'),('month','2022-01'),('retrieved_utc','invalid')]:
                with self.subTest(key=key):
                    receipt.write_text(json.dumps({**record,key:value}))
                    with self.assertRaisesRegex(ValueError,'differs'):acquire.verify_existing(path,receipt,'C6',acquire.FILES['C6'])

    def test_resume_unreceipted_original_and_safe_random_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory);dest=work/'pilot';dest.mkdir();(work/'campaign').mkdir();body=gzip.compress(b'example\n')
            fake=FakeSFTP(body);module=types.SimpleNamespace(spawn=lambda *a,**k:fake,EOF=fake.EOF,TIMEOUT=fake.TIMEOUT)
            original_replace=os.replace
            def interrupted(source,target):
                if str(target).endswith('.receipt.json'):raise OSError('synthetic interruption')
                return original_replace(source,target)
            with patch.object(acquire,'WORK',work),patch.object(acquire,'DEST',dest),patch.object(acquire,'public_login',return_value=('test','test')),patch.dict(sys.modules,{'pexpect':module}):
                with patch('os.replace',side_effect=interrupted):
                    with self.assertRaises(OSError):acquire.acquire()
                first=dest/acquire.FILES['C6'];self.assertTrue(first.exists())
                self.assertEqual(len(acquire.acquire()),2)
                self.assertEqual(first.read_bytes(),body)
                self.assertFalse(list(dest.glob('.modis-*')))

    def test_symlinked_destination_is_rejected_before_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);work=root/'work';work.mkdir();outside=root/'outside';outside.mkdir();dest=work/'pilot';dest.symlink_to(outside,target_is_directory=True)
            with patch.object(acquire,'WORK',work),patch.object(acquire,'DEST',dest):
                with self.assertRaisesRegex(ValueError,'escapes'):acquire.acquire()
            self.assertEqual(list(outside.iterdir()),[])

    def test_expanded_bound_and_corrupt_gzip_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'original.gz';path.write_bytes(gzip.compress(b'x'*100))
            with patch.object(acquire,'MAX_EXPANDED',99):
                with self.assertRaisesRegex(ValueError,'expanded|Expanded'):acquire.validate_gzip(path)
            path.write_bytes(b'not gzip')
            with self.assertRaises(OSError):acquire.validate_gzip(path)


if __name__=='__main__':unittest.main()
