from copy import deepcopy
import unittest

from fireatlas import native_context as nc
from fireatlas.core import TO_GRID
from fireatlas.qualification import digest
import math
from pathlib import Path
import tempfile
from unittest.mock import patch
import numpy as np
from fireatlas.masks import connect_store, checksum
from scripts import native_context_pipeline as pipeline


def seal(value):
    value.pop('input_sha256', None)
    value['input_sha256'] = digest(value)
    return value


def fixture():
    px, py = TO_GRID.transform(-120.5, 37.5)
    x, y = math.floor(px / 1000), math.floor(py / 1000)
    # Park's case includes these sample centres; source-aligned line indices are
    # synthetic and cannot enter authentic publications.
    lon, lat = -121.8, 40.0
    px, py = TO_GRID.transform(lon, lat)
    x, y = math.floor(px / 1000), math.floor(py / 1000)
    output = []
    for product, source, platform in [('MOD14', 'MODIS_SP', 'Terra'), ('VNP14IMG', 'VIIRS_SNPP_SP', 'S-NPP')]:
        rows = [[0, 0, lat, lon, 9 if product == 'MOD14' else 5, x, y, 3000, 1000, 0],
                [0, 1, lat, lon, 5 if product == 'MOD14' else 9, x, y, 12000, 5000, 0]]
        output.append({'producer_id': product + '-isolated-fixture', 'geo_producer_id': 'fixture-geo', 'product': product,
                       'source_id': source, 'platform': platform, 'start_utc': '2024-07-24T10:00:00Z', 'end_utc': '2024-07-24T10:05:00Z',
                       'file_sha256': 'a' * 64, 'geo_sha256': 'b' * 64, 'width': 2, 'height': 1,
                       'native_sample_count': 2, 'native_samples_sha256': digest([r[:7] for r in rows]),
                       'status': 'extracted', 'unavailable_reason': None, 'samples': rows,
                       'layers': {'solar': {'scale': .01, 'offset': 0, 'fill': -32768, 'valid_range': [0, 18000], 'units': 'degrees'},
                                  'sensor': {'scale': .01, 'offset': 0, 'fill': -32768, 'valid_range': [0, 18000], 'units': 'degrees'},
                                  'flags': {'fill': 255 if product == 'MOD14' else None, 'flag_masks': '{1,2,4,8}' if product == 'VNP14IMG' else None,
                                            'flag_meanings': 'Input_invalid Pointing_bad Terrain_bad SolarAngle_bad' if product == 'VNP14IMG' else None}}})
    return seal({'schema': nc.SCHEMA, 'case_id': 'park-2024', 'synthetic': True, 'method': nc.METHOD,
                 'method_sources': nc.method_identity(), 'sample_fields': nc.FIELDS, 'granules': output, 'native_pixel_count': 4})


class NativeContextTests(unittest.TestCase):
    def test_actual_pixel_subset_states_are_reaggregated_before_rematching(self):
        result = nc.analyze(fixture())
        self.assertEqual(result['subsets']['all']['thresholds']['90']['metrics']['both_detected'], 1)
        self.assertEqual(result['subsets']['day']['thresholds']['90']['metrics']['modis_only'], 1)
        self.assertEqual(result['subsets']['night']['thresholds']['90']['metrics']['viirs_only'], 1)
        self.assertEqual(result['subsets']['day']['pixel_samples'], 2)
        self.assertEqual(result['illumination_samples'], {'day': 2, 'night': 2})
        self.assertFalse(result['validated_observation_opportunity'])
        self.assertFalse(result['admitted'])

    def test_angle_fill_out_of_range_and_encoded_boundary_remain_unknown(self):
        g = fixture()['granules'][1]
        for value in (-32768, -1, 18001, 8500):
            row = g['samples'][0].copy(); row[7] = value
            self.assertEqual(nc.classify(row, g)[0], 'unknown')
        g['layers']['solar']['scale'] = .009999999776482582
        row[7] = 8500
        self.assertEqual(nc.classify(row, g)[0], 'unknown')

    def test_viirs_bits_use_native_names_and_unknown_bits_not_guessed(self):
        g = fixture()['granules'][1]
        row = g['samples'][0].copy()
        row[9] = 8
        state = nc.classify(row, g)
        self.assertEqual(state[0], 'unknown');self.assertEqual(state[3], ['solar-angle-bad'])
        row[9] = 2
        self.assertEqual(nc.classify(row, g)[0], 'day')
        self.assertEqual(nc.classify(row, g)[2], 'unknown')
        row[9] = 16
        self.assertEqual(nc.classify(row, g)[0], 'unknown')
        row[9] = 0; g['layers']['flags']['flag_meanings'] = 'unsupported-schema'
        self.assertEqual(nc.classify(row, g)[0], 'unknown')

    def test_modis_nonzero_flags_are_not_invented_quality_interpretation(self):
        g = fixture()['granules'][0]
        row = g['samples'][0].copy();row[9] = 1
        self.assertEqual(nc.classify(row, g)[:3], ('unknown', 'nonzero', 'unknown'))
        row[9] = 255
        self.assertEqual(nc.classify(row, g)[1], 'unknown')

    def test_exact_threshold_rematching_uses_interval_endpoints(self):
        value = fixture()
        value['granules'][1]['start_utc'] = '2024-07-24T10:40:00Z'
        value['granules'][1]['end_utc'] = '2024-07-24T10:45:00Z'
        result = nc.analyze(seal(value))
        ev = result['subsets']['day']['thresholds']
        self.assertEqual(ev['30']['metrics']['n_pairs'], 0)
        self.assertEqual(ev['60']['metrics']['n_pairs'], 1)
        self.assertEqual(ev['90']['group_uncertainty']['independent_groups'], 1)
        self.assertIsNone(ev['90']['group_uncertainty']['positive_jaccard_interval'])

    def test_missing_granule_evidence_is_not_zero_or_no_pass(self):
        value = fixture();g = value['granules'][1]
        g.update(status='unavailable', samples=[], unavailable_reason='Missing original file')
        result = nc.analyze(seal(value))
        self.assertEqual(result['native_pixel_count'], 4)
        self.assertEqual(result['extracted_pixel_count'], 2)
        self.assertEqual(result['subsets']['all']['thresholds']['90']['metrics']['n_pairs'], 0)
        self.assertFalse(result['no_pass_enabled'])

    def test_statistical_tampering_fails_even_with_refreshed_result_hash(self):
        value = fixture();result = nc.analyze(value)
        result['subsets']['day']['thresholds']['90']['metrics']['modis_only'] = 99
        result.pop('result_sha256');result['result_sha256'] = digest(result)
        with self.assertRaisesRegex(ValueError, 'statistics do not reproduce'):
            nc.verify({'inputs': value, 'result': result})

    def test_original_sample_duplicate_grid_and_source_mismatch_are_rejected(self):
        for mutate in ('duplicate', 'grid', 'source', 'count', 'hash', 'method'):
            value = fixture();g = value['granules'][0]
            if mutate == 'duplicate':g['samples'][1][:2] = g['samples'][0][:2]
            elif mutate == 'grid':g['samples'][0][5] += 1
            elif mutate == 'source':g['source_id'] = 'VIIRS_NOAA20_SP'
            elif mutate == 'count':g['native_sample_count'] += 1
            elif mutate == 'hash':g['geo_sha256'] = 'bad'
            else:value['method_sources'] = {}
            if mutate in ('duplicate', 'grid'):g['native_samples_sha256'] = digest([r[:7] for r in g['samples']])
            with self.assertRaises(ValueError):nc.validate(seal(value))

    def test_metadata_requires_explicit_units_scale_range_fill(self):
        original = fixture()['granules'][0]['layers']['solar']
        for field in ('units', 'scale', 'fill', 'valid_range'):
            meta = deepcopy(original);meta.pop(field)
            with self.assertRaises(ValueError):nc._validate_angle_metadata(meta)

    def test_offline_recount_is_deterministic_and_cannot_be_admitted(self):
        value = fixture();result = nc.analyze(value)
        verified = nc.verify({'inputs': value, 'result': result})
        self.assertTrue(verified['verified'])
        self.assertFalse(verified['scientifically_admitted'])
        self.assertEqual(digest(result), digest(nc.analyze(value)))

    def test_budget_output_containment_symlinks_and_atomic_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary) / 'work';work.mkdir()
            outside = Path(temporary) / 'outside';outside.mkdir()
            (work / 'escape').symlink_to(outside, target_is_directory=True)
            for output in (outside / 'result.gz', work / 'escape/result.gz'):
                with self.assertRaisesRegex(ValueError, 'budget-counted'):
                    pipeline.save(output, {'fixture': True}, work)
            output = work / 'result.gz'
            with patch.object(pipeline, 'budget'):
                pipeline.save(output, {'fixture': True}, work)
                original = output.read_bytes()
                with patch.object(pipeline, 'MAX_EXPANDED', 1):
                    with self.assertRaises(ValueError):pipeline.save(output, {'fixture': False}, work)
            self.assertEqual(output.read_bytes(), original)
            self.assertFalse(list(work.glob('.native-context-*')))

    def test_actual_extraction_binding_rejects_resealed_angle_tamper_and_shape_mismatch(self):
        class Layer:
            RasterXSize = 2
            RasterYSize = 1
            def __init__(self, values, flags=False):self.values=np.array([values]);self.flags=flags
            def ReadAsArray(self, *args):return self.values
            def GetRasterBand(self, number):return self
            def GetScale(self):return None if self.flags else .01
            def GetOffset(self):return None
            def GetNoDataValue(self):return 255 if self.flags else -32768
            def GetMetadata(self):return {} if self.flags else {'units':'degrees','valid_range':'0,18000'}
        value = fixture();g = value['granules'][0]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary);store = directory / 'native.sqlite3'
            mask = directory / (g['producer_id'] + '.hdf');mask.write_bytes(b'isolated synthetic mask')
            geo = directory / 'fixture-geo.nc';geo.write_bytes(b'isolated synthetic geo')
            with connect_store(store) as db:
                keys = ['case_id','producer_id','geo_producer_id','product','source_id','platform','start_utc','end_utc','file_sha256','geo_sha256','status','width','height']
                original = {**g,'case_id':'park-2024','status':'processed','geo_producer_id':geo.name,'file_sha256':checksum(mask),'geo_sha256':checksum(geo)}
                db.execute('INSERT INTO granules ('+','.join(keys)+') VALUES('+','.join('?' for k in keys)+')',[original[k] for k in keys])
                for row in g['samples']:db.execute('INSERT INTO pixels VALUES(?,?,?,?,?,?,?,?,?)',('park-2024',g['producer_id'],*row[:7]))
            layers = {'solar':Layer([3000,12000]),'sensor':Layer([1000,5000]),'flags':Layer([0,0],True),'lat':Layer([40,40]),'lon':Layer([-121.8,-121.8]),'mask':Layer([9,5])}
            def layer(path, names):
                name=names[0].lower()
                key='solar' if name=='solarzenith' else 'sensor' if name=='sensorzenith' else 'flags' if name=='gflags' else 'lat' if name=='latitude' else 'lon' if name=='longitude' else 'mask'
                return ('isolated-native-layer',layers[key])
            with patch.object(nc,'native_layer',side_effect=layer):
                authentic_capture=nc.capture('park-2024',directory,store)
                nc.bind_original_files(authentic_capture,directory,store)
                altered=deepcopy(authentic_capture);altered['granules'][0]['samples'][0][7]=12000;seal(altered)
                # A self-contained recount alone can reproduce edited raw inputs.
                result=nc.analyze(altered)
                self.assertTrue(nc.verify({'inputs':altered,'result':result},store=store)['verified'])
                with self.assertRaisesRegex(ValueError,'differ from original file extraction'):
                    nc.verify({'inputs':altered,'result':result},store=store,directory=directory)
                layers['solar'].RasterXSize=3
                with self.assertRaisesRegex(ValueError,'shape mismatch'):nc.capture('park-2024',directory,store)
                layers['solar'].RasterXSize=2
                geo.write_bytes(b'corrupt original bytes')
                with self.assertRaisesRegex(ValueError,'checksum differs'):nc.capture('park-2024',directory,store)


if __name__ == '__main__':
    unittest.main()
