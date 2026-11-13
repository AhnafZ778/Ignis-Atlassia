"""Synthetic tests: mathematical model and conservative failure handling only."""
import copy
import json
import unittest
from pyproj import Transformer
from fireatlas import experimental_pixel_geometry as m

INV = Transformer.from_crs('EPSG:6933', 'EPSG:4326', always_xy=True)


def fixture(product='MOD14', line=5, sample=5):
    geo, lines = m.PRODUCTS[product]
    centers = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            lon, lat = INV.transform(-12000000 + dc * 1000 + dr * 100, 4700000 + dr * 900)
            centers.append({'line':line+dr, 'sample':sample+dc, 'lon':lon, 'lat':lat,
                            'quality_flag':0, 'mask_class':5})
    value = {'schema':m.SCHEMA, 'synthetic':True, 'crs':'EPSG:6933',
             'source':{'mask_product':product, 'geo_product':geo,
                       'mask_id':product+'.A2024201.1730.061.test.hdf', 'geo_id':geo+'.A2024201.1730.061.test.hdf',
                       'mask_sha256':'a'*64, 'geo_sha256':'b'*64,
                       'mask_version':'061', 'geo_version':'061', 'width':100, 'height':lines*4,
                       'scan_layout':'product-scan-row-major', 'lines_per_scan':lines,
                       'quality_flag_fill':255, 'start_utc':'2024-07-19T17:30:00Z', 'end_utc':'2024-07-19T17:35:00Z'},
             'stencils':[{'line':line, 'sample':sample, 'centers':centers}]}
    return seal(value)


def seal(value):
    value['input_sha256']=m.digest({k:v for k,v in value.items() if k!='input_sha256'})
    return value


class MidpointTest(unittest.TestCase):
    def test_affine_geometry_recounts_and_cannot_claim_coverage(self):
        result=m.evaluate(fixture())
        row=result['rows'][0]
        self.assertEqual(row['status'], 'modeled')
        self.assertAlmostEqual(row['modeled_area_m2'], 900000, places=4)
        self.assertEqual(len(row['modeled_polygon_epsg6933']), 5)
        self.assertFalse(result['validated_opportunity'])
        self.assertFalse(result['no_pass_enabled'])
        self.assertFalse(result['provider_boundary'])
        self.assertTrue(m.verify(json.loads(json.dumps(result)))['verified'])

    def test_both_scan_seams_and_array_edges_remain_unresolved(self):
        for product,line in [('MOD14',9), ('MOD14',10), ('VNP14IMG',31), ('VNP14IMG',32)]:
            with self.subTest(product=product, line=line):
                self.assertEqual(m.evaluate(fixture(product,line))['rows'][0]['reason'], 'scan-seam')
        self.assertEqual(m.evaluate(fixture(line=0))['rows'][0]['reason'], 'array-edge')

    def test_unsupported_stencil_states_remain_unresolved(self):
        for case in ('missing', 'indices', 'geo', 'flags', 'fill', 'unknown-fill', 'deleted', 'unusable', 'degenerate', 'dateline'):
            v=fixture(); point=v['stencils'][0]['centers'][0]
            if case=='missing':v['stencils'][0]['centers'].pop()
            elif case=='indices':point['line']+=1
            elif case=='geo':point['lat']=None
            elif case=='flags':point['quality_flag']=1
            elif case=='fill':point['quality_flag']=255
            elif case=='unknown-fill':v['source']['quality_flag_fill']=None
            elif case=='deleted':point['mask_class']=1
            elif case=='unusable':point['mask_class']=2
            elif case=='dateline':
                v['stencils'][0]['centers'][0]['lon']=179.9;v['stencils'][0]['centers'][1]['lon']=-179.9
            elif case=='degenerate':
                for p in v['stencils'][0]['centers']:p['lat']=v['stencils'][0]['centers'][4]['lat'];p['lon']=v['stencils'][0]['centers'][4]['lon']
            with self.subTest(case=case):
                self.assertEqual(m.evaluate(seal(v))['rows'][0]['status'], 'unresolved')
                self.assertIsNone(m.evaluate(v)['rows'][0]['modeled_polygon_epsg6933'])

    def test_identity_dimensions_order_and_tampering(self):
        result=m.evaluate(fixture());result['rows'][0]['modeled_area_m2']+=1
        with self.assertRaises(ValueError):m.verify(result)
        for field,val in [('lines_per_scan',32),('height',31),('geo_product','MYD03'),
                          ('mask_sha256','x'*64),('scan_layout','unknown'),('start_utc','2024-01-01'),
                          ('geo_id','MOD03.A2024201.1735.061.test.hdf'),('mask_version','062')]:
            v=fixture();v['source'][field]=val
            with self.subTest(field=field),self.assertRaises(ValueError):m.evaluate(seal(v))
        v=fixture();v['stencils']*=2
        with self.assertRaises(ValueError):m.evaluate(seal(v))
        v=fixture();v['source']['width']=True
        with self.assertRaises(ValueError):m.evaluate(seal(v))
        v=fixture();v['stencils'][0]['centers'][4]['lat']+=0.001
        with self.assertRaises(ValueError):m.evaluate(v)

    def test_non_leap_year_day_366_is_not_a_valid_producer_date(self):
        v=fixture()
        for key in ('mask_id','geo_id'):
            v['source'][key]=v['source'][key].replace('A2024201.1730','A2023366.0000')
        v['source']['start_utc']='2024-01-01T00:00:00Z';v['source']['end_utc']='2024-01-01T00:05:00Z'
        with self.assertRaisesRegex(ValueError,'invalid'):m.evaluate(seal(v))

    def test_descending_axes_and_mismatched_projection(self):
        v=fixture()
        for p in v['stencils'][0]['centers']:p['lon']*=-1
        self.assertEqual(m.evaluate(seal(v))['rows'][0]['status'],'modeled')
        v['crs']='EPSG:4326'
        with self.assertRaises(ValueError):m.evaluate(seal(v))

if __name__=='__main__': unittest.main()

class OriginalBindingTest(unittest.TestCase):
    def test_empty_stencils_cannot_report_verified_original_samples(self):
        v=fixture();v['synthetic']=False;v['stencils']=[]
        with self.assertRaisesRegex(ValueError,'At least one'):
            m.verify_original_files(m.evaluate(seal(v)),'.')

    def test_binding_checks_all_samples_and_original_bytes(self):
        import hashlib, tempfile
        from pathlib import Path
        from unittest.mock import patch
        import numpy as np
        v=fixture();v['synthetic']=False
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('mask','geo'):
                p=root/v['source'][name+'_id'];p.write_bytes(name.encode())
                v['source'][name+'_sha256']=hashlib.sha256(name.encode()).hexdigest()
            result=m.evaluate(seal(v))
            mapping={'FireMask':'mask_class','Latitude':'lat','Longitude':'lon','gflags':'quality_flag'}
            class Layer:
                RasterXSize=100;RasterYSize=40
                def __init__(self,key):self.key=key
                def ReadAsArray(self,x,y,w,h):
                    return np.array([p[self.key] for p in v['stencils'][0]['centers']]).reshape(3,3)
            def reader(path,names):return None,Layer(mapping[names[0]])
            with patch('fireatlas.masks.native_layer',side_effect=reader), patch('fireatlas.native_context.layer_metadata',return_value={'fill':255}):
                self.assertEqual(m.verify_original_files(result,root)['centers_checked'],9)
                changed=False
                def changing_reader(path,names):
                    nonlocal changed
                    if not changed:
                        (root/v['source']['mask_id']).write_bytes(b'changed while reading')
                        changed=True
                    return reader(path,names)
                with patch('fireatlas.masks.native_layer',side_effect=changing_reader):
                    with self.assertRaisesRegex(ValueError,'changed during'):
                        m.verify_original_files(result,root)
                (root/v['source']['mask_id']).write_bytes(b'mask')
                altered=copy.deepcopy(result);altered['input']['stencils'][0]['centers'][0]['lat']+=.01
                altered['input']=seal(altered['input']);altered=m.evaluate(altered['input'])
                with self.assertRaises(ValueError):m.verify_original_files(altered,root)
                (root/v['source']['mask_id']).write_bytes(b'changed')
                with self.assertRaises(ValueError):m.verify_original_files(result,root)
