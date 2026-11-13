"""HTTP access to exact frozen monthly source receipts, using synthetic bytes."""
import hashlib
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from fireatlas.core import connect
from fireatlas.qualification import digest
from fireatlas import web


class MonthlySourcePublicationTests(unittest.TestCase):
    def test_local_api_and_static_route_return_same_bound_bytes_and_reject_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            publication = root / 'site/data/qualification'
            identity = 'a' * 16
            name = f'monthly-provenance/{identity}.json'
            diagnostic_name = f'daily-diagnostics/{identity}.json'
            neighbors_name = f'daily-neighbors/{identity}.json.gz'
            collection_name = 'collection-pilot.json'
            content = b'{"synthetic_test_receipt":true}\n'
            material = {'schema': 'test-publication', 'files': {key: {
                'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()} for key in (name,diagnostic_name,neighbors_name,collection_name)}}
            release = digest(material)
            destination = publication / 'releases' / release
            (destination / 'monthly-provenance').mkdir(parents=True)
            (destination / 'daily-diagnostics').mkdir()
            (destination / 'daily-neighbors').mkdir()
            (destination / name).write_bytes(content)
            (destination / diagnostic_name).write_bytes(content)
            (destination / neighbors_name).write_bytes(content)
            (destination / collection_name).write_bytes(content)
            manifest = json.dumps({**material, 'release_id': release}).encode()
            (destination / 'manifest.json').write_bytes(manifest)
            (publication / 'current.json').write_text(json.dumps({
                'release_id': release, 'manifest_sha256': hashlib.sha256(manifest).hexdigest()}))
            database = root / 'science.sqlite3'
            with connect(database):
                pass
            with patch.object(web, 'PROJECT_ROOT', root):
                handler = web.handler_factory(database)
                server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base = f'http://127.0.0.1:{server.server_port}'
                try:
                    for path in (f'/api/v2/monthly-provenance?id={identity}',
                                 f'/api/v2/monthly-provenance?id={identity}&release={release}',
                                 f'/data/qualification/releases/{release}/{name}',
                                 f'/api/v2/daily-diagnostics?id={identity}&release={release}',
                                 f'/data/qualification/releases/{release}/{diagnostic_name}',
                                 f'/api/v2/daily-neighbors?id={identity}',
                                 f'/api/v2/daily-neighbors?id={identity}&release={release}',
                                 f'/data/qualification/releases/{release}/{neighbors_name}',
                                 '/api/v2/collection-pilot',
                                 f'/api/v2/collection-pilot?release={release}',
                                 f'/data/qualification/releases/{release}/{collection_name}'):
                        with urllib.request.urlopen(base + path) as response:
                            self.assertEqual(content, response.read())
                    for path in ('/api/v2/monthly-provenance?id=../../current.json',
                                 f'/api/v2/monthly-provenance?id={"b" * 16}',
                                 '/api/v2/daily-neighbors?id=../../current.json',
                                 f'/api/v2/daily-neighbors?id={"b" * 16}'):
                        with self.assertRaises(urllib.error.HTTPError) as caught:
                            urllib.request.urlopen(base + path)
                        self.assertEqual(503, caught.exception.code)
                    (destination / name).write_bytes(b'corrupted')
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        urllib.request.urlopen(base + f'/api/v2/monthly-provenance?id={identity}')
                    self.assertEqual(503, caught.exception.code)
                    (destination / collection_name).write_bytes(b'corrupted')
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        urllib.request.urlopen(base + '/api/v2/collection-pilot')
                    self.assertEqual(503, caught.exception.code)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()
                    handler.assistant.close()
                    if handler.studio is not None:
                        handler.studio.close()
