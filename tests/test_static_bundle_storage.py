import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.static_bundle_storage import prepare, assemble, prune_parts


class StaticBundleStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'bundles').mkdir()
        self.body = bytes(range(256)) * 10
        self.archive = self.root / 'bundles/example.zip'
        self.archive.write_bytes(self.body)
        item = {'path': 'bundles/example.zip', 'bytes': len(self.body),
                'sha256': hashlib.sha256(self.body).hexdigest()}
        (self.root / 'manifest.json').write_text(json.dumps({'bundles': {'test': item}}))
        self.storage = prepare(self.root, part_bytes=1024, minimum_bytes=1)

    def test_exact_reconstruction_and_repeated_assembly(self):
        self.archive.unlink()
        self.assertEqual(assemble(self.root), ['bundles/example.zip'])
        self.assertEqual(self.archive.read_bytes(), self.body)
        self.assertEqual(assemble(self.root), ['bundles/example.zip'])

    def test_damaged_part_is_rejected_without_publishing_archive(self):
        self.archive.unlink()
        part = self.root / self.storage['archives'][0]['parts'][0]['path']
        part.write_bytes(b'x' * part.stat().st_size)
        with self.assertRaisesRegex(ValueError, 'checksum'):
            assemble(self.root)
        self.assertFalse(self.archive.exists())
        self.assertEqual(list((self.root / 'bundles').glob('.assemble-*')), [])

    def test_updated_transport_hash_cannot_replace_release_identity(self):
        self.archive.unlink()
        entry = self.storage['archives'][0]
        entry['sha256'] = 'a' * 64
        (self.root / 'bundles/archive-storage.json').write_text(json.dumps(self.storage))
        with self.assertRaisesRegex(ValueError, 'identity'):
            assemble(self.root)

    def test_traversal_part_is_rejected(self):
        self.archive.unlink()
        self.storage['archives'][0]['parts'][0]['path'] = '../outside'
        (self.root / 'bundles/archive-storage.json').write_text(json.dumps(self.storage))
        with self.assertRaisesRegex(ValueError, 'escapes'):
            assemble(self.root)

    def test_publication_prunes_only_parts_and_preserves_exact_archive(self):
        self.archive.unlink()
        prune_parts(self.root)
        self.assertEqual(self.archive.read_bytes(), self.body)
        self.assertEqual(list((self.root / 'bundles').glob('*.part*')), [])
        self.assertEqual(assemble(self.root), ['bundles/example.zip'])

    def test_cleanup_cannot_delete_a_different_file(self):
        self.storage['archives'][0]['parts'][0]['path'] = 'bundles/example.zip'
        (self.root / 'bundles/archive-storage.json').write_text(json.dumps(self.storage))
        with self.assertRaisesRegex(ValueError, 'named transport'):
            prune_parts(self.root)
        self.assertEqual(self.archive.read_bytes(), self.body)


if __name__ == '__main__':
    unittest.main()
