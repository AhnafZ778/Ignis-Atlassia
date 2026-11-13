"""Deployment boundaries and public starter integrity (no model/provider calls)."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

from fireatlas.hosted import public_origin, prepare_database
from fireatlas.core import connect

ROOT=Path(__file__).resolve().parents[1]


class HostedTests(unittest.TestCase):
    def test_origin_fails_closed_before_starting_stores(self):
        for value in ('','http://demo.onrender.com','https://user:pass@example.org','https://example.org/path','https://example.org?x=1','https://example.org#x','https://exa\nmple.org','https://example.org:bad'):
            with self.subTest(value=value),self.assertRaises(ValueError):public_origin({'FIREATLAS_PUBLIC_ORIGIN':value})
        self.assertEqual(public_origin({'RENDER_EXTERNAL_URL':'https://demo.onrender.com/'}),'https://demo.onrender.com')
        self.assertEqual(public_origin({'FIREATLAS_PUBLIC_ORIGIN':'http://127.0.0.1:8123'}),'http://127.0.0.1:8123')

    def test_new_store_authentic_seed_and_restart_preserve_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            database=prepare_database(directory)
            with connect(database) as db:
                before=db.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
                self.assertGreater(before,0)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM batches WHERE demo=1').fetchone()[0],0)
                self.assertGreater(db.execute('SELECT COUNT(*) FROM export_windows').fetchone()[0],0)
            prepare_database(directory)
            with connect(database) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM observations').fetchone()[0],before)
            self.assertFalse((Path(directory)/'.authentic-bootstrap-pending').exists())

    def test_synthetic_store_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            database=prepare_database(directory)
            with connect(database) as db:
                db.execute('UPDATE batches SET demo=1');db.commit()
            with self.assertRaisesRegex(ValueError,'synthetic'):prepare_database(directory)

    def test_interrupted_bootstrap_is_not_published_and_can_retry(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            with patch('fireatlas.archive.import_bundle',side_effect=OSError('interrupted')):
                with self.assertRaises(OSError):prepare_database(directory)
            self.assertFalse((Path(directory)/'fireatlas.sqlite3').exists())
            self.assertTrue((Path(directory)/'.authentic-bootstrap-pending').exists())
            database=prepare_database(directory)
            with connect(database) as db:
                self.assertGreater(db.execute('SELECT COUNT(*) FROM observations').fetchone()[0],0)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM batches WHERE demo=1').fetchone()[0],0)
            self.assertFalse((Path(directory)/'.authentic-bootstrap-pending').exists())

    def test_public_starter_is_conversation_free_and_hash_bound(self):
        from fireatlas.studio.portability import read_archive
        path=ROOT/'deployment/demo/rajshahi-peak-days.fireatlas.zip'
        bundle,_=read_archive(path)
        self.assertEqual(bundle['conversation'],[])
        self.assertEqual(bundle['comments'],[])
        self.assertGreater(len(bundle['whiteboard']['objects']),0)
        self.assertGreater(len(bundle['results']),0)
        provenance=json.loads(path.with_suffix('.provenance.json').read_text())
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),provenance['public_package_sha256'])
        with zipfile.ZipFile(path) as archive:
            for name,digest in provenance['preserved_result_sha256'].items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),digest)

    @unittest.skipUnless(shutil.which('node'),'Node required for Vercel build')
    def test_vercel_build_requires_safe_public_target_and_preserves_deep_links(self):
        # Public variables only, so no runtime/provider credentials enter the build.
        env={'PATH':os.environ['PATH']}
        script=ROOT/'scripts/build_vercel.mjs'
        for target in ('','http://demo.onrender.com','https://user:pass@example.org','https://example.org/path','https://example.org?x=1','https://example.org#x'):
            result=subprocess.run(['node',str(script)],env={**env,'FIREATLAS_RENDER_URL':target},capture_output=True)
            self.assertNotEqual(result.returncode,0)
        result=subprocess.run(['node',str(script)],env={**env,'FIREATLAS_RENDER_URL':'https://demo.onrender.com','VERCEL_URL':'demo.onrender.com'},capture_output=True)
        self.assertNotEqual(result.returncode,0)
        result=subprocess.run(['node',str(script)],env={**env,'FIREATLAS_RENDER_URL':'https://demo.onrender.com'},capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        html=(ROOT/'deployment/vercel-dist/index.html').read_text()
        self.assertIn('location.pathname+location.search+location.hash',html)
        self.assertNotIn('AIAND_API_KEY',html)

    def test_git_ignore_keeps_runtime_private_and_delivery_files_trackable(self):
        private=['.env.assistant','data/assistant/workspace.sqlite3','deployment/local-data/studio.db-wal','.vercel/project.json','deployment/vercel-dist/index.html']
        public=['Dockerfile','.dockerignore','render.yaml','vercel.json','scripts/build_vercel.mjs','deployment/demo/rajshahi-peak-days.fireatlas.zip']
        for name in private+public:
            status=subprocess.run(['git','check-ignore','--no-index','-q',name],cwd=ROOT).returncode
            self.assertEqual(status,0 if name in private else 1,name)


if __name__=='__main__':unittest.main()
