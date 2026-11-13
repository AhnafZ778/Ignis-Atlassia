"""Synthetic tests for the one-month MODIS collection comparison."""
import gzip
import contextlib
import hashlib
import io
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import threading
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from fireatlas import modis_collection_pilot as pilot
from fireatlas import modis_collection_publication as publication
from scripts import compare_modis_collections as cli


def row(day='20230101', clock='0128', platform='T', lat='39', lon='-121', kind='0'):
    return f'{day} {clock} {platform} {lat} {lon} 303.3 292.5 362 7.0 54 {kind} N\n'


class ModisCollectionPilotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
    def make(self, name, rows, header=pilot.HEADER):
        path = self.root / name
        with gzip.open(path, 'wt') as out: out.write(header + '\n' + rows)
        return path
    def test_distinct_cells_platform_counts_and_empty_union(self):
        a = self.make('a.gz', row() + row(platform='A') + row(kind='1'))
        b = self.make('b.gz', row() + row(lon='-120.9'))
        result = pilot.compare({'C6': a, 'C61': b}, {'C6': {'sha256':'a'}, 'C61': {'sha256':'b'}})
        d = result['regions']['norcal']['days'][0]
        self.assertEqual((d['c6_cells'],d['c61_cells'],d['both_cells'],d['c61_only_cells']), (1,2,1,1))
        self.assertEqual(d['c6_rows'], {'A':1,'T':1})
        self.assertEqual(d['jaccard'], 0.5)
        self.assertIsNone(result['regions']['norcal']['days'][1]['jaccard'])
        self.assertEqual(result['regions']['norcal']['month_cell_days']['union'],2)
        self.assertEqual(result['regions']['norcal']['month_cell_days']['jaccard'],0.5)
        self.assertIsNone(result['regions']['punjab-haryana']['month_cell_days']['jaccard'])
        self.assertFalse(result['transfer_qualified'])
        self.assertEqual(result, pilot.compare({'C6': a, 'C61': b}, {'C6': {'sha256':'a'}, 'C61': {'sha256':'b'}}))
    def test_rejects_malformed_and_wrong_month(self):
        for contents in (row(day='20230201'), row(lat='nan'), row(platform='X'), 'bad row\n'):
            with self.subTest(contents=contents):
                with self.assertRaises(ValueError): pilot.read_month(self.make('invalid.gz',contents))
        with self.assertRaises(ValueError):pilot.read_month(self.make('header.gz',row(),header='wrong'))
    def test_month_pools_cell_days_instead_of_daily_ratios(self):
        a=self.make('a.gz',row()+row(day='20230102'))
        b=self.make('b.gz',row()+row(lon='-120.9')+row(lon='-120.8')+row(day='20230102'))
        result=pilot.compare({'C6':a,'C61':b},{'C6':{},'C61':{}})
        total=result['regions']['norcal']['month_cell_days']
        self.assertEqual((total['c6'],total['c61'],total['both'],total['union']),(2,4,2,4))
        self.assertEqual(total['jaccard'],0.5)
    def test_expanded_and_line_bounds(self):
        path=self.make('large.gz',row())
        with patch.object(pilot,'MAX_EXPANDED',30):
            with self.assertRaises(ValueError):pilot.read_month(path)
        with self.assertRaises(ValueError):pilot.read_month(self.make('line.gz','x'*4100+'\n'))

    def test_recount_rejects_symlinked_paths(self):
        work=self.root/'work';work.mkdir();dest=work/'pilot';dest.mkdir()
        campaign=work/'campaign';campaign.mkdir()
        outside=self.root/'outside';outside.mkdir()
        with patch.object(cli,'WORK',work), patch.object(cli,'DEST',dest):
            cli.checked_paths()
            for name in (next(iter(cli.FILES.values())), next(iter(cli.FILES.values()))+'.receipt.json'):
                path=dest/name;path.symlink_to(outside/'file')
                with self.assertRaises(ValueError):cli.checked_paths()
                path.unlink()
            lock=campaign/'.acquisition.lock';lock.symlink_to(outside/'lock')
            with self.assertRaises(ValueError):cli.checked_paths()
            lock.unlink();dest.rmdir();dest.symlink_to(outside,target_is_directory=True)
            with self.assertRaises(ValueError):cli.checked_paths()

    def test_locked_recount_is_idempotent_and_checks_source_bytes(self):
        work=self.root/'work';work.mkdir();dest=work/'modis-collection-pilot-v1';dest.mkdir();(work/'campaign').mkdir()
        for collection,name in cli.FILES.items():
            path=dest/name
            content=(pilot.HEADER+'\n'+row()).encode()
            path.write_bytes(gzip.compress(content))
            receipt={'schema':'fireatlas-modis-month-download-v1','provider':'University of Maryland MODIS fire team',
                     'server':'fuoco.geog.umd.edu','remote_path':f'/data/MODIS/{collection}/MCD14ML/{name}',
                     'collection':collection,'filename':name,'month':'2023-01',
                     'retrieved_utc':'2026-01-01T00:00:00+00:00','download_complete':True,
                     'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                     'expanded_bytes':len(content)}
            (dest/(name+'.receipt.json')).write_text(json.dumps(receipt))
        with patch.object(cli,'ROOT',self.root),patch.object(cli,'WORK',work),patch.object(cli,'DEST',dest),patch.object(cli,'budget'):
            self.assertIsNone(publication.preflight(work))
            with contextlib.redirect_stdout(io.StringIO()) as first:cli.main()
            with contextlib.redirect_stdout(io.StringIO()) as second:cli.main()
            self.assertEqual(json.loads(first.getvalue()),json.loads(second.getvalue()))
            with self.assertRaises(ValueError):publication.verify_sources(work,None)
            released=publication.preflight(work)
            publication.verify_sources(work,released)
            # Exercise the real exporter handoff with unrelated expensive
            # science inputs replaced by bounded synthetic fixtures.
            from fireatlas.core import connect
            from fireatlas import coverage, disagreement, qualification_successors
            from fireatlas import web
            from fireatlas.qualification_publication import read
            from scripts import export_qualification as exporter
            from scripts import verify_collection_release as verifier
            db=self.root/'science.sqlite3';site=self.root/'site'
            with connect(db):pass
            with patch.object(exporter,'capture',return_value={}), \
                 patch.object(exporter,'pending',return_value={}), \
                 patch.object(exporter,'inventory',return_value={'regions':{},'claims':{}}), \
                 patch.object(exporter,'read_evidence',side_effect=lambda case:{'inventory':[],'pixels':[]}), \
                 patch.object(exporter,'passes_from_pixels',return_value=[]), \
                 patch.object(exporter,'fallback',return_value={}), \
                 patch.object(exporter,'ledger',return_value={}), \
                 patch.object(exporter,'budget'), \
                 patch.object(coverage,'envelope_report',return_value={'acquisitions':[]}), \
                 patch.object(disagreement,'analyze',return_value={'experiments':{}}), \
                 patch.object(qualification_successors,'assets',return_value={}):
                export_result=exporter.publish(db,site,work,include_native=False)
                published=json.loads(read(site/'data/qualification','collection-pilot.json'))
                self.assertEqual(published,released)
                with patch.object(web,'PROJECT_ROOT',self.root):
                    api_handler=web.handler_factory(db)
                    api=ThreadingHTTPServer(('127.0.0.1',0),api_handler)
                    static=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(site)))
                    threads=[threading.Thread(target=server.serve_forever,daemon=True) for server in (api,static)]
                    for thread in threads:thread.start()
                    try:
                        checked=verifier.verify(site,work,f'http://127.0.0.1:{static.server_port}',f'http://127.0.0.1:{api.server_port}')
                        self.assertTrue(checked['verified'])
                        self.assertEqual(checked['result_sha256'],released['result_sha256'])
                    finally:
                        for server in (api,static):server.shutdown();server.server_close()
                        for thread in threads:thread.join()
                        api_handler.assistant.close()
                        if api_handler.studio is not None:api_handler.studio.close()
                pointer=(site/'data/qualification/current.json').read_bytes()
                with patch.object(publication,'verify_sources',side_effect=ValueError('changed source')):
                    with self.assertRaisesRegex(ValueError,'changed source'):
                        exporter.publish(db,site,work,include_native=False)
                self.assertEqual((site/'data/qualification/current.json').read_bytes(),pointer)
                self.assertEqual(json.loads(pointer)['release_id'],export_result['release_id'])
            result_path=dest/('comparison-'+released['result_sha256']+'.json')
            result_bytes=result_path.read_bytes();result_path.write_text('{}')
            with self.assertRaises(ValueError):publication.verify_sources(work,released)
            result_path.write_bytes(result_bytes)
            receipt_path=dest/(cli.FILES['C6']+'.receipt.json')
            receipt_bytes=receipt_path.read_bytes();receipt_path.write_text('{}')
            with self.assertRaises(ValueError):publication.verify_sources(work,released)
            receipt_path.write_bytes(receipt_bytes)
            result_path.unlink()
            with self.assertRaises(ValueError):publication.verify_sources(work,released)
            result_path.write_bytes(result_bytes)
            (dest/cli.FILES['C6']).write_bytes(b'corrupt')
            with self.assertRaises(ValueError):cli.main()
            with self.assertRaises(ValueError):publication.verify_sources(work,released)

    def test_publication_rejects_dangling_directory_symlink(self):
        work=self.root/'work';work.mkdir()
        (work/'modis-collection-pilot-v1').symlink_to(self.root/'missing',target_is_directory=True)
        with self.assertRaises(ValueError):publication.preflight(work)


if __name__ == '__main__': unittest.main()
