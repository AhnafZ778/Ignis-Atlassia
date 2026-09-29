"""Scientific boundary tests. Tiny samples are fabricated and never used by the site."""
import copy
import io
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from fireatlas.granules import load
from fireatlas.masks import (METHOD, SCHEMA, native_layer, pass_state, paired_observations, timestamp,
                            expected_pairs, process, read_evidence, summarize, reconcile)
from fireatlas.mask_download import checklist
from fireatlas.core import TO_GRID
import math


class MaskBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.inventory = load()
        self.pair = expected_pairs(self.inventory, 'grove-2025')[0]
        self.native = {'schema': SCHEMA, 'case_id': 'grove-2025', 'method': copy.deepcopy(METHOD),
                       'inventory': [], 'pixels': []}

    def granule(self, source='MODIS_SP', start='2025-07-04T23:59:00Z', end='2025-07-05T00:04:00Z', identifier='m'):
        return {'source_id': source, 'start_utc': start, 'end_utc': end, 'producer_id': identifier,
                'state': 'detected', 'grid_x': -1, 'grid_y': 1}

    def test_cloud_unknown_bowtie_and_mixed_cells_are_not_clear(self):
        self.assertEqual(pass_state({3: 5, 5: 10}), 'observed-without-detection')
        self.assertEqual(pass_state({4: 10}), 'cloud-obscured')
        for codes in ({0: 1}, {1: 1}, {2: 1}, {6: 1}, {3: 1, 4: 1}, {5: 1, 6: 1}, {}):
            self.assertEqual(pass_state(codes), 'unknown')
        self.assertEqual(pass_state({7: 1, 4: 20}), 'detected')

    def test_missing_gdal_reports_native_install_guidance(self):
        with patch.dict(sys.modules, {'osgeo': None}):
            with self.assertRaisesRegex(RuntimeError, 'GDAL with HDF4/netCDF support'):
                native_layer('sample.hdf', ('fire mask',))

    def test_pairing_crosses_utc_midnight_and_requires_all_endpoints_within_90_minutes(self):
        modis = self.granule()
        viirs = self.granule('VIIRS_SNPP_SP', '2025-07-05T01:24:00Z', '2025-07-05T01:29:00Z', 'v')
        self.assertEqual(len(paired_observations([modis, viirs])), 1)
        viirs['end_utc'] = '2025-07-05T01:29:01Z'
        self.assertEqual(paired_observations([modis, viirs]), [])
        viirs['end_utc'] = '2025-07-05T01:29:00Z'
        viirs['state'] = 'cloud-obscured'
        self.assertEqual(paired_observations([modis, viirs]), [])

    def test_repeated_passes_are_paired_once_per_cell(self):
        modis = self.granule()
        viirs = self.granule('VIIRS_SNPP_SP', identifier='v')
        another = self.granule('VIIRS_SNPP_SP', identifier='v2')
        self.assertEqual(len(paired_observations([modis, viirs, another])), 1)

    def test_missing_downloads_never_become_no_pass_and_do_not_pass_gates(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Path(temp) / 'masks.sqlite3'
            outcome = process(Path(temp), 'grove-2025', store)
            self.assertEqual(outcome['processed'], 0)
            evidence = read_evidence('grove-2025', store)
            result = summarize('grove-2025', [], evidence, self.inventory, '2025-07-04')
            self.assertEqual(result['status'], 'not-loaded')
            self.assertFalse(result['inventory_complete'])
            self.assertEqual(result['expected_fire_granules'], 20)
            self.assertEqual(result['selected_day_cells'], [])
            self.assertEqual(result['no_pass_status'], 'not-derived-without-verified-footprints')
            self.assertFalse(result['reconciliation']['passes_target'])
            self.assertEqual(result['raw_mask_review']['reviewed_samples'], 0)

    def test_native_grid_assignment_is_recomputed(self):
        lon, lat = -121.4, 39.4
        x, y = TO_GRID.transform(lon, lat)
        self.native['pixels'] = [{'producer_id': 'bad', 'line': 0, 'sample': 0, 'lat': lat,
                                 'lon': lon, 'mask_class': 8, 'grid_x': math.floor(x/1000) + 1,
                                 'grid_y': math.floor(y/1000)}]
        with self.assertRaisesRegex(ValueError, 'grid assignment'):
            summarize('grove-2025', [], self.native, self.inventory, '2025-07-04')

    def test_native_decode_failure_discards_partial_pixels_and_records_exception(self):
        def broken(*args):
            yield {'height': 1, 'width': 1, 'invalid_geolocation': 0}, [(0, 0, 39.4, -121.4, 8, -1, 1)]
            raise ValueError('invalid class')
        with tempfile.TemporaryDirectory() as temp:
            store = Path(temp) / 'masks.sqlite3'
            Path(temp, Path(urlsplit(self.pair['granule']['download_url']).path).name).write_bytes(b'fixture')
            Path(temp, Path(urlsplit(self.pair['geo']['download_url']).path).name).write_bytes(b'fixture')
            with patch('fireatlas.masks.decode_file', broken):
                process(temp, 'grove-2025', store)
            evidence = read_evidence('grove-2025', store)
            self.assertEqual(evidence['pixels'], [])
            record = next(g for g in evidence['inventory'] if g['producer_id'] == self.pair['granule']['producer_id'])
            self.assertEqual(record['status'], 'failed')
            self.assertIn('invalid class', record['error'])

    def test_checklist_has_exact_urls_and_product_versions(self):
        entries = checklist()
        self.assertEqual(len(entries), 268)
        self.assertEqual(len(checklist('grove-2025')), 40)
        self.assertTrue(all(urlsplit(row['download_url']).hostname in {'data.lpdaac.earthdatacloud.nasa.gov', 'data.laadsdaac.earthdatacloud.nasa.gov', 'ladsweb.modaps.eosdis.nasa.gov'} for row in entries))
        self.assertEqual({r['version'] for r in entries if r['product'] == 'VNP14IMG'}, {'002'})
        with self.assertRaises(ValueError):
            checklist('unknown')

    def test_reconciliation_requires_platform_time_and_proximity_and_keeps_confidence_disagreement(self):
        lon, lat = -121.4, 39.4
        x, y = TO_GRID.transform(lon, lat)
        gx, gy = math.floor(x / 1000), math.floor(y / 1000)
        pixel = {'producer_id': 'm', 'line': 2, 'sample': 4, 'lat': lat, 'lon': lon,
                 'mask_class': 8, 'grid_x': gx, 'grid_y': gy}
        granule = {**self.granule(), 'status': 'processed', 'platform': 'Terra'}
        evidence = {'inventory': [granule], 'pixels': [pixel]}
        row = {'detection_id': 'test-only', 'platform': 'Terra', 'lat': lat, 'lon': lon,
               'source_id': 'MODIS_SP', 'acquisition_utc': '2025-07-05T00:00:00Z',
               'confidence_raw': '90', 'grid_x': gx, 'grid_y': gy}
        outcome = reconcile([row], evidence)[0]
        self.assertEqual(outcome['status'], 'matched')
        self.assertFalse(outcome['confidence_agrees'])
        self.assertEqual(outcome['native_line'], 2)
        for confidence, native_class in (('29', 7), ('30', 8), ('79', 8), ('80', 9)):
            with self.subTest(confidence=confidence):
                pixel['mask_class'] = native_class
                outcome = reconcile([{**row, 'confidence_raw': confidence}], evidence)[0]
                self.assertTrue(outcome['confidence_agrees'])
        for changes in ({'platform': 'Aqua'}, {'acquisition_utc': '2025-07-05T00:06:00Z'}, {'lon': lon + .01}):
            with self.subTest(changes=changes):
                self.assertEqual(reconcile([{**row, **changes}], evidence)[0]['status'], 'unreconciled')


if __name__ == '__main__':
    unittest.main()
