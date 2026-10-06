"""Native provider transport, credential-specific video access and durable recovery."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fireatlas.studio import aiand_video as video
from fireatlas.studio.errors import StudioError


ACCESS = {'key': 'private-test-key', 'credential_sha256': 'a'*64, 'model': video.MODEL,
          'per_second_usd': .08, 'resolution': '768p', 'terms_version': 'test'}


class VideoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.frame = self.root/'frame.png'
        self.frame.write_bytes(b'authentic-frozen-reference')
        self.cancel = threading.Event()

    def tearDown(self):
        self.tmp.cleanup()

    def test_selects_video_enabled_key_before_any_paid_submission(self):
        seen = []
        def handle(request):
            key = request.headers['Authorization']
            seen.append((request.method, request.url.path, key))
            if request.url.path.endswith('acceptance'):
                return httpx.Response(200, json={'accepted': key.endswith('video-key'), 'version': 'v1'})
            return httpx.Response(200, json={'data': [{'id': video.MODEL, 'pricing':[{'resolution':'768p','currency':'usd','per_second':'0.08'}]}]})
        original = httpx.Client
        with patch.object(video, '_access', None), patch.object(video, 'configured_keys', return_value=['chat-key','video-key']), \
             patch('httpx.Client', side_effect=lambda **kw: original(transport=httpx.MockTransport(handle), **kw)):
            access = video.verify_access()
        self.assertEqual(access['key'], 'video-key')
        self.assertTrue(all(method == 'GET' for method,_,_ in seen))

    def test_real_endpoint_shapes_cached_delivery_and_frozen_reference(self):
        seen, bodies = [], []
        def handle(request):
            seen.append((request.method, request.url.path))
            if request.url.path.endswith('/files'):
                self.assertIn(b'purpose', request.read())
                return httpx.Response(200, json={'id':'file-frame'})
            if request.method == 'POST':
                bodies.append(json.loads(request.read()))
                return httpx.Response(200, json={'id':'video-real','status':'completed','cost':'0.32','currency':'usd'})
            return httpx.Response(200, content=b'\x00\x00\x00\x18ftypisom'+b'verified-mp4'*8)
        client = video.VideoClient(ACCESS, httpx.Client(transport=httpx.MockTransport(handle)))
        for _ in range(2):
            path, receipt = client.clip(self.root/'cache', self.frame, 'Evidence motion', 4, self.cancel.is_set, lambda *args: None)
            self.assertTrue(path.exists())
            self.assertEqual(receipt['video_id'], 'video-real')
        self.assertEqual(len(bodies), 1)
        self.assertEqual(bodies[0]['model'], video.MODEL)
        self.assertEqual(bodies[0]['image_reference'], [{'file_id':'file-frame','role':'first_frame'}])
        self.assertEqual(bodies[0]['aspect_ratio'], '16:9')
        self.assertEqual(receipt['quote_usd'], .32)
        client.close()

    def test_uncertain_creation_is_not_repeated_and_reconciles_unique_remote_job(self):
        posted = []
        def handle(request):
            if request.url.path.endswith('/files'):
                return httpx.Response(200,json={'id':'file-frozen'})
            if request.method == 'POST':
                posted.append(json.loads(request.read()))
                raise httpx.ReadTimeout('unknown usage')
            if request.url.path.endswith('/videos'):
                return httpx.Response(200,json={'data':[{'id':'video-recovered','status':'completed',**posted[0]}]})
            return httpx.Response(200,content=b'\0\0\0\x18ftypisom'+b'content'*20)
        client = video.VideoClient(ACCESS,httpx.Client(transport=httpx.MockTransport(handle)))
        with self.assertRaisesRegex(StudioError,'uncertain'):
            client.clip(self.root/'cache', self.frame, 'Captured evidence', 4, self.cancel.is_set, lambda *a: None)
        _, receipt = client.clip(self.root/'cache', self.frame, 'Captured evidence', 4, self.cancel.is_set, lambda *a: None)
        self.assertEqual(receipt['video_id'], 'video-recovered')
        self.assertEqual(len(posted), 1)
        client.close()

    def test_cancellation_retains_remote_id_without_another_submission(self):
        def handle(request):
            if request.url.path.endswith('/files'):
                return httpx.Response(200,json={'id':'file-frozen'})
            self.cancel.set()
            return httpx.Response(200,json={'id':'video-pending','status':'queued'})
        client = video.VideoClient(ACCESS,httpx.Client(transport=httpx.MockTransport(handle)))
        with self.assertRaisesRegex(StudioError,'cannot abort'):
            client.clip(self.root/'cache',self.frame,'Motion',4,self.cancel.is_set,lambda *a:None)
        saved = json.loads(next((self.root/'cache').glob('*/job.json')).read_text())
        self.assertEqual(saved['video_id'],'video-pending')
        client.close()

    def test_provider_credit_failure_is_explicit_not_a_local_fallback(self):
        def handle(request):
            if request.url.path.endswith('/files'):
                return httpx.Response(200,json={'id':'file-frozen'})
            return httpx.Response(402,json={'error':{'code':'insufficient_credits'}})
        client = video.VideoClient(ACCESS,httpx.Client(transport=httpx.MockTransport(handle)))
        with self.assertRaises(StudioError) as error:
            client.clip(self.root/'cache',self.frame,'Motion',4,self.cancel.is_set,lambda *a:None)
        self.assertEqual(error.exception.code,'insufficient_credits')
        client.close()
