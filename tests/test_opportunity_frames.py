"""Synthetic engineering evidence only; mocked signatures are not scientific review."""
import copy,hashlib,json,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
import numpy as np
from pyproj import Transformer
from fireatlas import opportunity_frames as f,opportunity_review as r
from fireatlas.qualification import digest
from fireatlas.coverage import interior_cells


def seal(value,key='input_sha256'):
    value[key]=digest({k:v for k,v in value.items() if k!=key});return value


def fixture(code=5,day=1,*,scope='grove-2025',tile=None,flags=0,fill=255,fraction=1.,empty=False):
    x,y=interior_cells('grove-2025')[0] if tile is None else tile[:2]
    tile=tile or [x,y,x+1,y+1]
    a,b=x*1000,y*1000
    shape=[[a,b],[a+1000*fraction,b],[a+1000*fraction,b+1000],[a,b+1000],[a,b]]
    lon,lat=Transformer.from_crs('EPSG:6933','EPSG:4326',always_xy=True).transform(a+500*fraction,b+500)
    producer='VNP14IMG.A2025213.1200.002.test.nc';geo='VNP03IMG.A2025213.1200.002.test.nc'
    versions={'VNP14IMG':'002','VNP03IMG':'2'};stamp=f'2025-08-{day:02d}';products=[]
    bbox=f.domain(scope)['bbox'];w,s,e,n=bbox
    for name,version in versions.items():
        entries=[] if empty else [{'id':'test-'+name,'producer_granule_id':producer if name=='VNP14IMG' else geo,
            'time_start':stamp+'T12:00:00Z','time_end':stamp+'T12:06:00Z','boxes':[f'{s} {w} {n} {e}']}]
        body=json.dumps({'feed':{'entry':entries}})
        products.append({'product':name,'version':version,'query':f.query_url(scope,stamp,stamp,name,version),
                         'pages':[{'request_after':None,'response_after':None,'hits':len(entries),
                         'source_utf8':body,'sha256':hashlib.sha256(body.encode()).hexdigest()}]})
    native_hash=hashlib.sha256(b'mask').hexdigest();geo_hash=hashlib.sha256(b'geo').hexdigest()
    pixel={'producer_id':producer,'geo_producer_id':geo,'line':0,'sample':0,'mask_class':code,'lat':lat,'lon':lon,
           'quality_flag':flags,'native_file_sha256':native_hash,'geolocation_sha256':geo_hash,'polygon':shape}
    body=json.dumps({'schema':'fireatlas-provider-boundary-transcription-v1','origin':'provider-pixel-boundaries','pixels':[pixel]})
    h=hashlib.sha256(body.encode()).hexdigest();pixel['geometry_reference_sha256']=h
    return seal({'schema':'fireatlas-opportunity-frame-input-v2','synthetic':True,'crs':'EPSG:6933',
        'geometry_origin':'provider-pixel-boundaries','scope_id':scope,'tile':tile,'start':stamp,'end':stamp,
        'cohort':{'source':'VIIRS_SNPP_SP','version':'2'},'native_versions':versions,
        'inventory':{'schema':'fireatlas-native-inventory-receipts-v1','scope_id':scope,'start':stamp,'end':stamp,
                     'retrieved_utc':'2026-10-27T00:00:00Z','products':products},
        'native_files':[] if empty else [{'producer_id':producer,'geo_producer_id':geo,'width':1,'height':1,
                        'native_file_sha256':native_hash,'geolocation_sha256':geo_hash,'quality_flag_fill':fill}],
        'geometry_artifacts':[] if empty else [{'source_reference':'https://ladsweb.modaps.eosdis.nasa.gov/test/boundaries',
                              'source_utf8':body,'sha256':h}], 'pixels':[] if empty else [pixel]})


def reviewed_fixture(*,mock_authentic=False):
    inputs=[fixture(code,day) for day,code in enumerate((8,5,4,1,6),1)]
    inputs.append(fixture(day=6,empty=True))
    for value in inputs:
        value['synthetic']=not mock_authentic;seal(value)
    results=[f.evaluate(value) for value in inputs]
    review=r.template(results)
    review.update(human_authored=True,automated_agent=False,decision='approve',signed_utc=datetime.now(timezone.utc).isoformat(),
                  reviewer={k:'Synthetic engineering reviewer fixture' for k in review['reviewer']})
    review['attestations']={k:True for k in r.ATTESTATIONS}
    review['native_collection_mappings']=[{'cohort':results[0]['cohort'],'native_versions':results[0]['native_versions'],'evidence_reference':'synthetic mapping test'}]
    for value in results:
        row=value['daily_cells'][0]
        review['examples'].append({'frame_sha256':value['result_sha256'],'date':row['date'],'grid_x':row['grid_x'],'grid_y':row['grid_y'],
            'state':row['geometric_state'],'outcome':'confirmed-no-pass' if row['geometric_state']=='no-candidate' else 'agree',
            'evidence_reference':'synthetic example, no authentic science approval'})
    return results,review


class FrameTests(unittest.TestCase):
    def test_states_recount_and_no_admission(self):
        for code,state in [(8,'detected'),(5,'observed-without-detection'),(4,'cloud'),(1,'unusable'),(0,'unknown'),(6,'unknown')]:
            with self.subTest(code=code):
                result=f.evaluate(fixture(code));self.assertEqual(state,result['daily_cells'][0]['geometric_state'])
                self.assertTrue(f.verify(json.loads(json.dumps(result)))['verified'])
                self.assertFalse(result['validated_observation_opportunity']);self.assertFalse(result['no_pass_enabled'])
    def test_partial_quality_unknown_and_verified_empty_distinct(self):
        for kw in ({'fraction':.5},{'flags':1},{'fill':0},{'fill':None}):
            self.assertEqual('unknown',f.evaluate(fixture(**kw))['daily_cells'][0]['geometric_state'])
        result=f.evaluate(fixture(empty=True))
        self.assertEqual('no-candidate',result['daily_cells'][0]['geometric_state'])
        self.assertEqual('unknown',r.campaign([result])['classified_frames'][0]['daily_cells'][0]['validated_opportunity'])
    def test_companion_only_candidate_is_missing_mask_evidence_not_no_pass(self):
        value=fixture();page=value['inventory']['products'][0]['pages'][0]
        page['source_utf8']=json.dumps({'feed':{'entry':[]}});page['hits']=0
        page['sha256']=hashlib.sha256(page['source_utf8'].encode()).hexdigest()
        value.update(pixels=[],native_files=[],geometry_artifacts=[])
        result=f.evaluate(seal(value));self.assertEqual(1,len(result['unpaired_geolocation']))
        self.assertEqual('unknown',result['daily_cells'][0]['geometric_state'])
        self.assertTrue(result['daily_cells'][0]['candidate_acquisitions'])

    def test_paired_companion_extent_or_missing_geometry_does_not_disappear(self):
        from pyproj import Transformer
        inverse=Transformer.from_crs('EPSG:6933','EPSG:4326',always_xy=True)
        x,y=interior_cells('grove-2025')[0]
        for missing in (False,True):
            for code,known in [(5,'observed-without-detection'),(4,'cloud')]:
                value=fixture(code=code,tile=[x,y,x+2,y+1])
                w,s=inverse.transform(x*1000,y*1000);e,n=inverse.transform((x+1)*1000,(y+1)*1000)
                for product in value['inventory']['products']:
                    page=product['pages'][0];body=json.loads(page['source_utf8'])
                    if product['product']=='VNP14IMG':body['feed']['entry'][0]['boxes']=[f'{s} {w} {n} {e}']
                    elif missing:body['feed']['entry'][0].pop('boxes')
                    page['source_utf8']=json.dumps(body);page['sha256']=hashlib.sha256(page['source_utf8'].encode()).hexdigest()
                result=f.evaluate(seal(value));states=[row['geometric_state'] for row in result['daily_cells']]
                self.assertEqual([known,'unknown'],states)
                self.assertEqual(1,len(result['unsupported_geolocation']))
                self.assertFalse(result['unpaired_geolocation'])

    def test_boundary_roi_cell_uses_clipped_area(self):
        x,y,_,_=f.domain('grove-2025')['grid_bounds'];cells=f.tile_cells('grove-2025',[x,y,x+1,y+1])
        self.assertGreater(cells[0][2].area,0);self.assertLess(cells[0][2].area,1_000_000)
    def test_missing_changed_or_repeated_inventory_is_rejected(self):
        for change in ('missing-product','hits','bytes','token','duplicate','cohort','version'):
            value=fixture();page=value['inventory']['products'][0]['pages'][0]
            if change=='missing-product':value['inventory']['products'].pop()
            elif change=='hits':page['hits']+=1
            elif change=='bytes':page['source_utf8']+=' '
            elif change=='token':page['request_after']='missing previous page'
            elif change=='duplicate':value['inventory']['products'][1]=copy.deepcopy(value['inventory']['products'][0])
            elif change=='cohort':value['cohort']['source']='VIIRS_SNPP_NRT'
            else:value['native_versions']['VNP14IMG']='wrong'
            with self.subTest(change=change),self.assertRaises(ValueError):f.evaluate(seal(value))
    def test_missing_candidate_geometry_is_unknown_every_cell(self):
        value=fixture();page=value['inventory']['products'][0]['pages'][0];body=json.loads(page['source_utf8'])
        body['feed']['entry'][0].pop('boxes');page['source_utf8']=json.dumps(body);page['sha256']=hashlib.sha256(page['source_utf8'].encode()).hexdigest()
        result=f.evaluate(seal(value));self.assertTrue(result['geometry_failures'])
        self.assertEqual('unknown',result['daily_cells'][0]['geometric_state'])
    def test_midnight_and_inclusive_query_boundary_do_not_invent_a_day(self):
        for first,last,expected in [('2025-08-01T23:59:00Z','2025-08-02T00:05:00Z','unknown'),
                                   ('2025-08-02T00:00:00Z','2025-08-02T00:06:00Z','no-candidate')]:
            value=fixture()
            for item in value['inventory']['products']:
                page=item['pages'][0];body=json.loads(page['source_utf8'])
                body['feed']['entry'][0].update(time_start=first,time_end=last)
                page['source_utf8']=json.dumps(body);page['sha256']=hashlib.sha256(page['source_utf8'].encode()).hexdigest()
            self.assertEqual(expected,f.evaluate(seal(value))['daily_cells'][0]['geometric_state'])
    def test_conflicting_pixel_polygons_and_inadequate_envelope_are_unknown(self):
        value=fixture();second=copy.deepcopy(value['pixels'][0]);second.update(sample=1,mask_class=4)
        value['pixels'].append(second);value['native_files'][0]['width']=2
        artifact=value['geometry_artifacts'][0];body=json.loads(artifact['source_utf8'])
        body['pixels'].append({k:v for k,v in second.items() if k!='geometry_reference_sha256'})
        artifact['source_utf8']=json.dumps(body);artifact['sha256']=hashlib.sha256(artifact['source_utf8'].encode()).hexdigest()
        for pixel in value['pixels']:pixel['geometry_reference_sha256']=artifact['sha256']
        result=f.evaluate(seal(value));self.assertEqual('unknown',result['daily_cells'][0]['geometric_state'])
        self.assertAlmostEqual(1,result['acquisitions'][0]['rows'][0]['conflicting_fraction'])
        value=fixture();page=value['inventory']['products'][0]['pages'][0];body=json.loads(page['source_utf8'])
        body['feed']['entry'][0]['boxes']=['0 0 1 1'];page['source_utf8']=json.dumps(body)
        page['sha256']=hashlib.sha256(page['source_utf8'].encode()).hexdigest()
        result=f.evaluate(seal(value));self.assertTrue(result['geometry_failures'])
        self.assertEqual('unknown',result['daily_cells'][0]['geometric_state'])
    def test_original_paginated_receipts_preserve_search_after_chain(self):
        import io
        original=fixture();mask=json.loads(original['inventory']['products'][0]['pages'][0]['source_utf8'])['feed']['entry'][0]
        second=copy.deepcopy(mask);second.update(id='test-second',producer_granule_id=mask['producer_granule_id']+'-second')
        geo=json.loads(original['inventory']['products'][1]['pages'][0]['source_utf8'])['feed']['entry'][0]
        class Response(io.BytesIO):
            def __init__(self,entries,hits,token=None):
                super().__init__(json.dumps({'feed':{'entry':entries}}).encode());self.headers={'CMR-Hits':str(hits)}
                if token:self.headers['CMR-Search-After']=token
        def opener(request,**kwargs):
            if 'VNP03IMG' in request.full_url:return Response([geo],1)
            if request.get_header('Cmr-search-after'):return Response([second],2)
            return Response([mask],2,'after-first')
        result=f.discover('grove-2025',original['start'],original['end'],original['native_versions'],opener=opener)
        original['inventory']=result;self.assertEqual(3,len(f.inventory(original)))
        pages=next(p['pages'] for p in result['products'] if p['product']=='VNP14IMG')
        self.assertEqual('after-first',pages[1]['request_after'])
        pages[1]['request_after']='different'
        with self.assertRaises(ValueError):f.inventory(original)

    def test_original_identity_shape_boundary_and_scope_tampering_fails(self):
        for change in ('file','sample','boundary','scope','origin','tile'):
            value=fixture()
            if change=='file':value['pixels'][0]['native_file_sha256']='b'*64
            elif change=='sample':value['pixels'][0]['sample']=1
            elif change=='boundary':value['geometry_artifacts'][0]['source_utf8']+=' '
            elif change=='scope':value['scope_id']='norcal'
            elif change=='origin':value['geometry_origin']='interpolated-centres'
            else:value['tile'][2]=value['tile'][0]+50000
            with self.subTest(change=change),self.assertRaises(ValueError):f.evaluate(seal(value))
    def test_statistics_resealed_after_tampering_are_recounted(self):
        value=f.evaluate(fixture());value['daily_cells'][0]['geometric_state']='cloud';seal(value,'result_sha256')
        with self.assertRaises(ValueError):f.verify(value)
    def test_discovery_retains_complete_pages_and_rejects_truncated_search(self):
        from tests.test_qualification import Response
        class CMRResponse(Response):
            def __init__(self,entries,hits,token=None):
                super().__init__(json.dumps({'feed':{'entry':entries}}).encode(),{'CMR-Hits':str(hits)})
                if token:self.headers['CMR-Search-After']=token
        calls=[]
        def opener(request,**kwargs):
            calls.append(request)
            return CMRResponse([],0)
        inv=f.discover('grove-2025','2025-08-01','2025-08-01',{'VNP14IMG':'002','VNP03IMG':'2'},opener=opener)
        value=fixture(empty=True);value['inventory']=inv;self.assertEqual({},f.inventory(value));self.assertEqual(2,len(calls))
        with self.assertRaises(ValueError):f.discover('grove-2025','2025-08-01','2025-08-01',{'VNP14IMG':'002'},opener=lambda *a,**k:CMRResponse([],1))
        with self.assertRaisesRegex(ValueError,'bounded frame'):f.discover('grove-2025','2025-08-01','2025-08-01',{'VNP14IMG':'002'},opener=lambda *a,**k:CMRResponse([],501))
    def test_actual_sds_binding_rejects_resealed_wrong_class(self):
        value=fixture();value['synthetic']=False;result=f.evaluate(seal(value))
        class Band:
            def GetMetadata(self):return {}
            def GetNoDataValue(self):return 255
        class Layer:
            RasterXSize=RasterYSize=1
            def __init__(self,v):self.v=v
            def GetMetadata(self):return {}
            def GetRasterBand(self,n):return Band()
            def ReadAsArray(self,*args):return np.array([[self.v]])
        expected=value['pixels'][0]
        def layer(path,names):
            key='mask_class' if names[0]=='FireMask' else 'lat' if names[0]=='Latitude' else 'lon' if names[0]=='Longitude' else 'quality_flag'
            return '',Layer(expected[key])
        with tempfile.TemporaryDirectory() as td,patch('fireatlas.masks.native_layer',side_effect=layer):
            Path(td,expected['producer_id']).write_bytes(b'mask');Path(td,expected['geo_producer_id']).write_bytes(b'geo')
            self.assertEqual(1,f.bind_original_files(result,td)['pixels_checked'])
            altered=copy.deepcopy(value);altered['pixels'][0]['mask_class']=8
            with self.assertRaisesRegex(ValueError,'does not reproduce'):f.bind_original_files(f.evaluate(seal(altered)),td)


class ReviewTests(unittest.TestCase):
    def test_synthetic_signature_cannot_admit_and_ai_signature_is_rejected(self):
        values,review=reviewed_fixture();self.assertTrue(r.review_state(review,values)['approved'])
        self.assertFalse(r.campaign(values,review)['validated_observation_opportunity'])
        review['automated_agent']=True;self.assertFalse(r.review_state(review,values)['approved'])
    def test_no_directory_no_pass_and_bound_review_examples_mapping_required(self):
        values,review=reviewed_fixture()
        for v in values:
            v['inputs']['synthetic']=False;seal(v['inputs']);v.update(f.evaluate(v['inputs']))
        review['frame_sha256s']=sorted(v['result_sha256'] for v in values)
        self.assertFalse(r.campaign(values,review)['validated_observation_opportunity'])
        values,review=reviewed_fixture()
        for change in ('binding','mapping','examples','attestation','date'):
            altered=copy.deepcopy(review)
            if change=='binding':altered['frame_sha256s'].pop()
            elif change=='mapping':altered['native_collection_mappings'][0]['cohort']['version']='other'
            elif change=='examples':altered['examples'][0]['outcome']='unresolved'
            elif change=='attestation':altered['attestations']['candidate_geometry_adequate']=False
            else:altered['signed_utc']='2126-01-01T00:00:00Z'
            with self.subTest(change=change):self.assertFalse(r.review_state(altered,values)['approved'])
    def test_mocked_original_reextraction_required_and_no_pass_separate(self):
        # Entirely manufactured engineering fixtures; no real signature/admission.
        values,review=reviewed_fixture(mock_authentic=True)
        def binding(frame,directory):
            return {'frame_sha256':frame['result_sha256'],'verified':True,'pixels_checked':len(frame['inputs']['pixels'])}
        with patch.object(f,'bind_original_files',side_effect=binding):
            value=r.campaign(values,review,original_directory='mock-only')
            self.assertTrue(value['validated_observation_opportunity']);self.assertTrue(value['no_pass_enabled'])
            self.assertEqual('no-pass',value['classified_frames'][-1]['daily_cells'][0]['validated_opportunity'])
            with self.assertRaises(ValueError):r.verify_campaign(value)
            self.assertTrue(r.verify_campaign(value,original_directory='mock-only')['verified'])
            for first,last in [('2025-08-01','2025-08-01'),('2026-10-01','2026-10-01')]:
                report=r.regional_report(value,'norcal',first,last,[values[0]['cohort']],original_directory='mock-only')
                self.assertFalse(report['validated_opportunity']);self.assertFalse(report['spatial_temporal_complete'])
                self.assertEqual(0,report['daily_support'][0]['represented_cells'])
            review['examples'].pop()
            value=r.campaign(values,review,original_directory='mock-only')
            self.assertTrue(value['validated_observation_opportunity']);self.assertFalse(value['no_pass_enabled'])
            self.assertEqual('unknown',value['classified_frames'][-1]['daily_cells'][0]['validated_opportunity'])

    def test_full_campaign_recount_and_tampering(self):
        value=r.campaign([f.evaluate(fixture())]);self.assertTrue(r.verify_campaign(value)['verified'])
        value['classified_frames'][0]['daily_cells'][0]['validated_opportunity']='no-pass';seal(value,'result_sha256')
        with self.assertRaises(ValueError):r.verify_campaign(value)
    def test_regional_holes_dates_pilot_and_overlap(self):
        x,y,_,_=f.domain('norcal')['grid_bounds'];value=f.evaluate(fixture(scope='norcal',tile=[x,y,x+1,y+1]))
        campaign=r.campaign([value]);report=r.regional_report(campaign,'norcal','2025-08-01','2025-08-02',[value['cohort']])
        self.assertFalse(report['spatial_temporal_complete']);self.assertFalse(report['validated_opportunity'])
        self.assertEqual(0,report['daily_support'][1]['represented_cells'])
        self.assertAlmostEqual(1,report['daily_support'][1]['state_area_fraction']['unknown'])
        with self.assertRaises(ValueError):r.regional_report(campaign,'grove-2025','2025-08-01','2025-08-01',[value['cohort']])
        other=fixture(scope='norcal',tile=[x,y,x+1,y+1],flags=1);overlap=r.campaign([value,f.evaluate(other)])
        with self.assertRaisesRegex(ValueError,'Overlapping'):r.regional_report(overlap,'norcal','2025-08-01','2025-08-01',[value['cohort']])

class PipelineTests(unittest.TestCase):
    def test_discovery_preflight_counts_shared_work_before_any_provider_call(self):
        from scripts import opportunity_pipeline as cli
        argv=['opportunity_pipeline','discover','--scope','grove-2025','--start','2025-07-04','--end','2025-07-06',
              '--native-version','VNP14IMG','002','--output',str(cli.ROOT/'data/qualification/opportunity-v2/test-do-not-write.json.gz')]
        with patch('sys.argv',argv),patch.object(cli,'budget',side_effect=ValueError('Storage gate closed')) as gate,patch.object(f,'discover') as provider:
            with self.assertRaisesRegex(ValueError,'Storage gate'):cli.main()
            gate.assert_called_once_with(cli.ROOT/'data/qualification',129_000_000);provider.assert_not_called()
        argv.extend(['--work','/tmp/outside-shared-budget'])
        with patch('sys.argv',argv),patch.object(f,'discover') as provider:
            with self.assertRaisesRegex(ValueError,'shared budget'):cli.main()
            provider.assert_not_called()
    def test_multiple_frame_decompression_is_cumulatively_bounded(self):
        import gzip
        from scripts import opportunity_pipeline as cli
        with tempfile.TemporaryDirectory() as td:
            files=[]
            for i in range(2):
                p=Path(td)/(str(i)+'.gz');p.write_bytes(gzip.compress(b'{"test":"12345678"}'));files.append(p)
            with patch.object(cli,'MAX_EXPANDED',25):
                with self.assertRaisesRegex(ValueError,'expanded bytes'):cli.load_frames(files)


if __name__=='__main__':unittest.main()
