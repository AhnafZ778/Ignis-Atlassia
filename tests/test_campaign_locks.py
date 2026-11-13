import sqlite3
import tempfile
from threading import Barrier, Event, Lock
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from fireatlas import acquisition as acq
from scripts.acquire_qualification_overlap import retry_busy, retry_provider
from tests.test_qualification import discovery, Response, HEADER

class CampaignLockTests(unittest.TestCase):
    def test_only_transient_database_and_campaign_locks_retry(self):
        for error in (sqlite3.OperationalError('database is locked'),sqlite3.OperationalError('database table is locked'),ValueError('Another campaign acquisition/import is active.')):
            calls=[]
            def import_once():
                calls.append(True)
                if len(calls)<3:raise error
                return {'rows_inserted':5}
            with patch('scripts.acquire_qualification_overlap.time.sleep'):
                self.assertEqual(retry_busy(import_once),{'rows_inserted':5})
            self.assertEqual(len(calls),3)
    def test_storage_schema_and_data_failures_do_not_retry(self):
        for error in (sqlite3.OperationalError('no such table: observations'),sqlite3.OperationalError('database or disk is full'),ValueError('Storage gate closed'),ValueError('Original bytes differ')):
            with patch('scripts.acquire_qualification_overlap.time.sleep') as sleep:
                with self.assertRaises(type(error)):retry_busy(lambda: (_ for _ in ()).throw(error))
                sleep.assert_not_called()
    def test_lock_wait_has_a_deadline(self):
        with patch('scripts.acquire_qualification_overlap.time.monotonic',side_effect=[0,601]),patch('scripts.acquire_qualification_overlap.time.sleep') as sleep:
            with self.assertRaises(sqlite3.OperationalError):retry_busy(lambda: (_ for _ in ()).throw(sqlite3.OperationalError('database is locked')))
            sleep.assert_not_called()
    def test_provider_retries_only_recognized_transport_failures(self):
        for message in ('Provider transport interrupted; request remains incomplete and can be resumed.',
                        'FIRMS request failed for availability: primary and secondary servers unreachable'):
            calls=[]
            def operation():
                calls.append(True)
                if len(calls)<3:raise ValueError(message)
                return 'complete'
            with patch('scripts.acquire_qualification_overlap.time.sleep') as sleep:
                self.assertEqual(retry_provider(operation),'complete')
                self.assertEqual([call.args[0] for call in sleep.call_args_list],[3,6])
            self.assertEqual(len(calls),3)
        for message in ('Provider HTTP 429; resume after provider recovery','Storage gate closed','Original bytes differ'):
            with patch('scripts.acquire_qualification_overlap.time.sleep') as sleep:
                with self.assertRaises(ValueError):retry_provider(lambda: (_ for _ in ()).throw(ValueError(message)))
                sleep.assert_not_called()
    def test_provider_retry_stops_after_three_attempts(self):
        calls=[]
        def operation():
            calls.append(True)
            raise ValueError('Provider transport interrupted; request remains incomplete and can be resumed.')
        with patch('scripts.acquire_qualification_overlap.time.sleep') as sleep:
            with self.assertRaises(ValueError):retry_provider(operation)
        self.assertEqual(len(calls),3)
        self.assertEqual(sleep.call_count,2)
    def test_local_write_failure_is_not_reclassified_or_retried(self):
        plan=acq.plan('norcal',['2012-02'],['MODIS_SP'],discovery());calls=[]
        def opener(*args,**kwargs):
            calls.append(True);return Response(HEADER.encode())
        with tempfile.TemporaryDirectory() as directory, patch.object(acq,'firms_key',return_value='fixture'), \
             patch.object(acq.os,'fsync',side_effect=OSError('synthetic local disk failure')), \
             patch('scripts.acquire_qualification_overlap.time.sleep'):
            with self.assertRaisesRegex(OSError,'synthetic local disk failure'):
                retry_provider(lambda:acq.acquire(directory,plan,opener=opener,workers=1))
        self.assertEqual(len(calls),1)
    def test_rate_limit_during_response_read_is_not_retried(self):
        plan=acq.plan('norcal',['2012-02'],['MODIS_SP'],discovery());calls=[]
        class RateLimitedResponse(Response):
            def read(self,*args):
                raise HTTPError('https://example.invalid',429,'synthetic rate limit',{},None)
        def opener(*args,**kwargs):
            calls.append(True);return RateLimitedResponse(HEADER.encode())
        with tempfile.TemporaryDirectory() as directory, patch.object(acq,'firms_key',return_value='fixture'), \
             patch('scripts.acquire_qualification_overlap.time.sleep'):
            with self.assertRaisesRegex(ValueError,'Provider HTTP 429'):
                retry_provider(lambda:acq.acquire(directory,plan,opener=opener,workers=1))
        self.assertEqual(len(calls),1)
    def test_concurrent_rate_limit_is_not_hidden_by_transport_failure(self):
        plan=acq.plan('norcal',['2012-02'],['MODIS_SP'],discovery())
        barrier=Barrier(2);first=Event();lock=Lock();calls=[]
        def opener(*args,**kwargs):
            with lock:
                index=len(calls);calls.append(index)
            if index<2:
                barrier.wait(timeout=5)
                if index==0:
                    first.set();raise URLError('synthetic transport failure')
                first.wait(timeout=5);Event().wait(.1)
                raise HTTPError('https://example.invalid',429,'synthetic rate limit',{},None)
            return Response(HEADER.encode())
        with tempfile.TemporaryDirectory() as directory, patch.object(acq,'firms_key',return_value='fixture'), \
             patch('scripts.acquire_qualification_overlap.time.sleep'):
            with self.assertRaisesRegex(ValueError,'Provider HTTP 429'):
                retry_provider(lambda:acq.acquire(directory,plan,opener=opener,workers=2))
        self.assertEqual(len(calls),2)
    def test_concurrent_rate_limit_prevents_size_fallback(self):
        plan=acq.plan('norcal',['2012-02'],['MODIS_SP'],discovery())
        barrier=Barrier(2);first=Event();lock=Lock();calls=[]
        def opener(*args,**kwargs):
            with lock:
                index=len(calls);calls.append(index)
            barrier.wait(timeout=5)
            if index==0:
                first.set();return Response(HEADER.encode(),{'Content-Length':str(acq.WINDOW_LIMIT+1)})
            first.wait(timeout=5);Event().wait(.1)
            raise HTTPError('https://example.invalid',429,'synthetic rate limit',{},None)
        with tempfile.TemporaryDirectory() as directory, patch.object(acq,'firms_key',return_value='fixture'), \
             patch('scripts.acquire_qualification_overlap.time.sleep'):
            with self.assertRaisesRegex(ValueError,'Provider HTTP 429'):
                retry_provider(lambda:acq.acquire(directory,plan,opener=opener,workers=2))
        self.assertEqual(len(calls),2)

if __name__=='__main__':unittest.main()
