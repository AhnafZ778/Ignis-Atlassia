"""Synthetic handoff checks for the private native publication worker."""
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fireatlas import native_context
from scripts import preflight_native_context as preflight


class NativePreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);self.directory=root/'native';self.directory.mkdir()
        self.store=root/'store.sqlite3';self.store.write_bytes(b'store')
        self.mask=self.directory/'mask.hdf';self.mask.write_bytes(b'mask')
        self.geo=self.directory/'geo.nc';self.geo.write_bytes(b'geo')
        self.context=root/'context.json.gz'
        self.bundle={'inputs':{'case_id':'park-2024','synthetic':False,'input_sha256':'a'*64,
                    'granules':[{'producer_id':'mask','geo_producer_id':'geo.nc'}]},
                     'result':{'case_id':'park-2024','synthetic':False}}
        self.context.write_bytes(gzip.compress(json.dumps(self.bundle).encode()))

    def run_worker(self, callback=None):
        with patch.object(native_context,'validate'), patch.object(native_context,'verify'), patch.object(native_context,'bind_original_store'), \
             patch.object(native_context,'bind_original_files',side_effect=callback):
            return preflight.run(self.context,self.directory,self.store,'park-2024')

    def test_original_file_changes_and_duplicate_paths_invalidate_handoff(self):
        record=self.run_worker()
        preflight.verify_sources(self.context,self.directory,self.store,record)
        self.mask.write_bytes(b'altered')
        with self.assertRaisesRegex(ValueError,'Native file inventory changed'):
            preflight.verify_sources(self.context,self.directory,self.store,record)
        self.mask.write_bytes(b'mask')
        (self.directory/'other').mkdir();(self.directory/'other/mask.hdf').write_bytes(b'mask')
        with self.assertRaisesRegex(ValueError,'Native file inventory changed'):
            preflight.verify_sources(self.context,self.directory,self.store,record)

    def test_changes_during_reextraction_fail(self):
        def mutate(*_args):self.geo.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Native file inventory changed'):
            self.run_worker(mutate)

    def test_context_and_store_wal_changes_fail(self):
        record=self.run_worker()
        (self.store.parent/(self.store.name+'-wal')).write_bytes(b'new')
        with self.assertRaisesRegex(ValueError,'Native store changed'):
            preflight.verify_sources(self.context,self.directory,self.store,record)
        (self.store.parent/(self.store.name+'-wal')).unlink()
        self.context.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Native context changed'):
            preflight.verify_sources(self.context,self.directory,self.store,record)


if __name__=='__main__':unittest.main()
