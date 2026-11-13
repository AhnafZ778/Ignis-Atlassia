"""Synthetic checks of local exact-byte collection release verification."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from unittest.mock import patch
from scripts import verify_collection_release as verifier


class CollectionReleaseVerifierTests(unittest.TestCase):
    def test_validates_original_and_both_routes_and_rejects_changes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);site=root/'site';work=root/'work';(work/'campaign').mkdir(parents=True)
            (work/'campaign/.acquisition.lock').touch();pub=site/'data/qualification';pub.mkdir(parents=True)
            pointer=pub/'current.json';pointer.write_text(json.dumps({'release_id':'a'*64}))
            source={'result_sha256':'b'*64,'transfer_qualified':False};body=json.dumps(source).encode()
            with patch.object(verifier,'read',return_value=body),patch.object(verifier,'preflight',return_value=source),patch.object(verifier,'verify_sources') as check,patch.object(verifier,'fetch',return_value=body):
                report=verifier.verify(site,work,'http://127.0.0.1:8127','http://localhost:8130')
                self.assertTrue(report['static_and_api_match']);check.assert_called_once()
            with patch.object(verifier,'read',return_value=body),patch.object(verifier,'preflight',return_value=source),patch.object(verifier,'fetch',side_effect=[body,b'changed']):
                with self.assertRaisesRegex(ValueError,'route bytes'):verifier.verify(site,work,'http://127.0.0.1:8127','http://localhost:8130')
            def change(*_args):pointer.write_text(json.dumps({'release_id':'c'*64}))
            with patch.object(verifier,'read',return_value=body),patch.object(verifier,'preflight',return_value=source),patch.object(verifier,'fetch',return_value=body),patch.object(verifier,'verify_sources',side_effect=change):
                with self.assertRaisesRegex(ValueError,'pointer changed'):verifier.verify(site,work,'http://127.0.0.1:8127','http://localhost:8130')
    def test_rejects_nonlocal_or_unexpected_origins(self):
        for value in ('https://example.com','http://example.com','http://localhost/path','http://localhost?token=x','http://user@localhost'):
            with self.subTest(value=value),self.assertRaises(ValueError):verifier.local_origin(value)
    def test_rejects_redirect_and_symlinked_campaign(self):
        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302);self.send_header('Location','http://example.com/other');self.end_headers()
            def log_message(self,*_args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Redirect)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with self.assertRaises(HTTPError) as error:verifier.fetch(f'http://127.0.0.1:{server.server_port}/artifact')
            self.assertEqual(error.exception.code,302)
        finally:server.shutdown();server.server_close();thread.join()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);work=root/'work';work.mkdir();outside=root/'outside';outside.mkdir()
            (work/'campaign').symlink_to(outside,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'escapes'):
                verifier.verify(root/'site',work,'http://localhost:8127','http://localhost:8130')
    def test_daily_response_bound_supports_large_local_artifact(self):
        body=b'x'*1_000_001
        class Large(BaseHTTPRequestHandler):
            def do_GET(self):self.send_response(200);self.end_headers();self.wfile.write(body)
            def log_message(self,*_args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Large);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            url=f'http://127.0.0.1:{server.server_port}/artifact'
            with self.assertRaisesRegex(ValueError,'exceeds bound'):verifier.fetch(url)
            self.assertEqual(verifier.fetch(url,limit=2_000_000),body)
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
