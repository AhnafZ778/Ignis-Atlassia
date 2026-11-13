"""Bounded synthetic engineering checks; these do not constitute science review."""
import copy
from calendar import monthrange
from datetime import datetime,timezone
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from fireatlas import transfer as tr,coverage as cov,disagreement as dis,acquisition as acq
from fireatlas.qualification import digest
from fireatlas.core import TO_GRID
from fireatlas.validity import CASES
from tests.test_qualification import HEADER,Response,discovery


def rehash(value,key='input_sha256'):
    value[key]=digest({k:v for k,v in value.items() if k!=key});return value


def transfer_fixture():
    x,y=TO_GRID.transform(-121,40);x,y=int(x//1000),int(y//1000)
    a={'source':'MODIS_SP','version':'6.03'};b={'source':'VIIRS_SNPP_SP','version':'2'}
    notice=json.dumps({'schema':'fireatlas-sensor-notices-v1','notices':[]})
    import hashlib
    notice={'source_utf8':notice,'sha256':hashlib.sha256(notice.encode()).hexdigest()}
    ledgers=[];daily=[];cells={tuple(a.values()):{},tuple(b.values()):{}};platforms={c:{} for c in cells}
    for year in range(2012,2020):
        for month in range(1,13):
            stamp=f'{year}-{month:02d}';day=stamp+'-01';n=1+month%8
            for role,c,ps,factor in [('source',a,['Terra'],1),('target',b,['S-NPP'],3)]:
                values=[[x+i,y] for i in range(n*factor)]
                daily.append({'role':role,'date':day,'cells':values,'platforms':ps,'file_sha256s':['a'*64]})
                cells[tuple(c.values())][day]=set(map(tuple,values));platforms[tuple(c.values())][day]=set(ps)
                ledgers.append({**c,'month':stamp,'start':day,'end':stamp+f'-{monthrange(year,month)[1]}','file_sha256':'a'*64,'complete_export':True,'coverage_basis':'request-metadata'})
    supported=tr.ledger_months(ledgers,tuple(cells));months=sorted(supported[tuple(a.values())])
    return rehash({'schema':'fireatlas-direct-transfer-input-v1','region':'norcal','source_cohort':a,'target_cohort':b,'synthetic':True,'units':tr.UNITS,'grid':tr.GRID,'count_basis':tr.COUNT_BASIS,'notice_snapshot':notice,'observation_files':[{**c,'file_sha256':'a'*64} for c in (a,b)],'daily_cells':daily,'export_ledger':ledgers,'months':tr.summarize(months,supported,cells,platforms,tuple(a.values()),tuple(b.values()),notice)})


def inventory_fixture():
    case='grove-2025';w,s,e,n=CASES[case]['bbox'];products=[]
    for name in ('MOD14','MYD14','VNP14IMG','MOD03','MYD03','VNP03IMG'):
        gs=[{'producer_id':'test-MOD14','cmr_id':'test-CMR','product':name,'version':'61','start_utc':'2025-08-01T12:00:00Z','end_utc':'2025-08-01T12:05:00Z','candidate_geometry':{'boxes':[f'{s} {w} {n} {e}']}}] if name=='MOD14' else []
        products.append({'product':name,'version':'61','inventory_complete':True,'cmr_hits':len(gs),'granules':gs,'pages':[{'entries':len(gs),'hits':len(gs),'sha256':'a'*64}]})
    return {'schema':'fireatlas-acquisition-inventory-v2','case_id':case,'inventory_complete':True,'products':products}


def pixel_fixture(mask=5,quality='valid',fraction=1.):
    inventory=inventory_fixture();x,y=cov.interior_cells('grove-2025')[0];a,b=x*1000,y*1000
    pixel={'producer_id':'test-MOD14','line':0,'sample':0,'mask_class':mask,'quality':quality,'native_file_sha256':'a'*64,'geolocation_sha256':'b'*64,'geometry_reference_sha256':'c'*64,'polygon':[[a,b],[a+1000*fraction,b],[a+1000*fraction,b+1000],[a,b+1000],[a,b]]}
    return cov.footprint_input('grove-2025',inventory,[pixel],synthetic=True),inventory,[(x,y)]


class TransferTests(unittest.TestCase):
    def test_verified_reimport_keeps_earlier_owned_authentic_union_rows(self):
        from fireatlas.core import connect,ingest
        from fireatlas.regions import REGIONS
        with tempfile.TemporaryDirectory() as td,connect(Path(td)/'isolated-fixture.sqlite3') as db:
            for source,satellite,instrument,version in [('MODIS_SP','T','MODIS','6.03'),('VIIRS_SNPP_SP','N','VIIRS','2')]:
                path=Path(td)/(source+'.csv');path.write_text(HEADER+f'40,-121,2012-02-01,1200,{satellite},{instrument},90,{version},1,1,2,D\n')
                first=ingest(db,path,source,batch_key='partial-fixture')
                verified=ingest(db,path,source,complete_month='2012-02',bbox=REGIONS['norcal']['bbox'],batch_key='verified-fixture')
                self.assertEqual(1,first['rows_inserted']);self.assertEqual(0,verified['rows_inserted'])
                db.execute('INSERT INTO source_exports VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(verified['batch_id'],'norcal',source,'2012-02','2012-02-01','2012-02-29',*REGIONS['norcal']['bbox'],1,'request-metadata',json.dumps([version]),'a'*64,'b'*64))
            inputs=tr.capture(db,'norcal',{'source':'MODIS_SP','version':'6.03'},{'source':'VIIRS_SNPP_SP','version':'2'})
            self.assertEqual(1,inputs['months'][0]['source_count']);self.assertEqual(1,inputs['months'][0]['target_count']);self.assertEqual(1,len(tr.validate(inputs,False)))
    def test_forward_backward_intervals_recount_and_no_admission(self):
        result=tr.analyze(transfer_fixture(),synthetic=True)
        self.assertTrue(tr.verify(json.loads(json.dumps(result)))['verified']);self.assertFalse(result['admitted']);self.assertFalse(result['performance_pass'])
        for direction,ev in result['evaluation'].items():
            self.assertEqual(3,len(ev['folds']));self.assertEqual(36,len(ev['rows']))
            for fold in ev['folds']:
                a,b,c=map(set,(fold['training_months'],fold['calibration_months'],fold['test_months']))
                self.assertFalse(a&b or a&c or b&c)
                self.assertTrue(max(a)<min(b)<min(c) if direction=='forward' else min(a)>max(b)>max(c))
    def test_tampered_aggregate_scope_platform_ledger_and_source_fail(self):
        for change in ('count','units','grid','platform','ledger','notice','provenance'):
            value=transfer_fixture()
            if change=='count':value['months'][0]['target_count']+=1
            elif change=='units':value['units']='fires'
            elif change=='grid':value['grid']='another-grid'
            elif change=='platform':value['daily_cells'][0]['platforms']=['NOAA-20']
            elif change=='ledger':value['export_ledger'][0]['complete_export']=False
            elif change=='notice':value['notice_snapshot']['source_utf8']+=' '
            else:value['daily_cells'][0]['file_sha256s']=['f'*64]
            with self.subTest(change=change),self.assertRaises(ValueError):tr.analyze(rehash(value),synthetic=True)
    def test_training_factors_ignore_test_and_calibration_outcomes(self):
        rows=tr.validate(transfer_fixture(),True);before=tr.evaluate(rows,'forward')
        for r in rows:
            if r['year']>=2015:r['viirs']*=11
        after=tr.evaluate(rows,'forward')
        self.assertEqual(before['folds'][0]['selected_model'],after['folds'][0]['selected_model'])
        self.assertEqual([r['prediction'] for r in before['rows'] if r['year']==2017],[r['prediction'] for r in after['rows'] if r['year']==2017])
    def test_ai_receipt_and_human_identity_cannot_mix(self):
        fixture=transfer_fixture()
        with self.assertRaisesRegex(ValueError,'mix'):tr.analyze(fixture,synthetic=True,experimental=tr.experimental_review())
        fixture['synthetic']=False;rehash(fixture)
        # Authentic evaluations remain blocked while the method is in draft.
        if tr.protocol()['state'].startswith('draft'):
            with self.assertRaisesRegex(ValueError,'Freeze'):tr.analyze(fixture,experimental=tr.experimental_review())
        else:
            result=tr.analyze(fixture,experimental=tr.experimental_review());self.assertFalse(result['performance_pass']);self.assertTrue(tr.verify(result)['verified'])
        for review in ({},None,{'human_authored':True,'reviewer':{}}, {'reviewer':[]}):self.assertFalse(tr.review_state(review)['approved'])
    def test_frozen_notices_recount_independent_of_live_file(self):
        value=transfer_fixture()
        with patch.object(tr,'notice_snapshot',side_effect=AssertionError('live notices used')):self.assertEqual(96,len(tr.validate(value,True)))


class CoverageTests(unittest.TestCase):
    def test_candidate_envelope_is_self_contained_and_recountable(self):
        inventory=inventory_fixture();cells=cov.interior_cells('grove-2025')[:1]
        result=cov.envelope_report('grove-2025',inventory,cells=cells)
        self.assertTrue(cov.verify(json.loads(json.dumps(result)))['verified'])
        self.assertFalse(result['validated_observation_opportunity']);self.assertIsNone(result['opportunity_denominator'])
        result['acquisitions'][0]['intersections'][0]['envelope_fraction']=0
        with self.assertRaisesRegex(ValueError,'recount'):cov.verify(result)
    def test_calculated_states_never_promote_synthetic_or_partial_coverage(self):
        for mask,quality,fraction,state in [(5,'valid',1.,'observed-without-detection'),(8,'valid',1.,'detected'),(4,'valid',1.,'cloud'),(2,'valid',1.,'unusable'),(0,'valid',1.,'unknown'),(6,'valid',1.,'unknown'),(5,'unknown',1.,'unknown'),(8,'valid',.5,'unknown')]:
            inputs,inventory,cells=pixel_fixture(mask,quality,fraction);result=cov.evaluate_pixels(inputs,inventory,synthetic=True,cells=cells)
            with self.subTest(mask=mask,quality=quality,fraction=fraction):
                self.assertEqual(state,result['rows'][0]['geometric_sample_state']);self.assertFalse(result['admitted']);self.assertIsNone(result['opportunity_denominator']);self.assertFalse(result['no_pass_enabled']);self.assertTrue(cov.verify(result)['verified'])
    def test_cloud_clear_overlap_stays_unknown(self):
        inputs,inventory,cells=pixel_fixture();cloud=copy.deepcopy(inputs['pixels'][0]);cloud.update(sample=1,mask_class=4);inputs['pixels'].append(cloud)
        result=cov.evaluate_pixels(rehash(inputs),inventory,synthetic=True,cells=cells)
        self.assertEqual('unknown',result['rows'][0]['geometric_sample_state']);self.assertEqual(1.,result['rows'][0]['ambiguous_overlap_fraction'])
    def test_origin_geometry_resource_and_inventory_guards(self):
        inputs,inventory,cells=pixel_fixture()
        bad=copy.deepcopy(inputs);bad['geometry_origin']='interpolated-centres'
        with self.assertRaisesRegex(ValueError,'centroid'):cov.evaluate_pixels(rehash(bad),inventory,synthetic=True,cells=cells)
        bad=copy.deepcopy(inputs);bad['pixels'][0]['polygon'][-1]=[0,0]
        with self.assertRaises(ValueError):cov.evaluate_pixels(rehash(bad),inventory,synthetic=True,cells=cells)
        with patch.object(cov,'MAX_TOTAL_VERTICES',4),self.assertRaisesRegex(ValueError,'vertex'):cov.evaluate_pixels(inputs,inventory,synthetic=True,cells=cells)
        partial=copy.deepcopy(inventory);partial['products'][0]['pages'][0]['hits']=2
        self.assertFalse(cov.complete_inventory(partial,'grove-2025'))
        duplicated=copy.deepcopy(inventory);duplicated['products'].append(copy.deepcopy(duplicated['products'][-1]))
        self.assertFalse(cov.complete_inventory(duplicated,'grove-2025'))
    def test_authentic_native_class_hash_and_centre_binding(self):
        from fireatlas.masks import FROM_GRID
        inputs,inventory,cells=pixel_fixture();inputs['synthetic']=False;rehash(inputs);x,y=cells[0];lon,lat=FROM_GRID.transform((x+.5)*1000,(y+.5)*1000)
        original={'producer_id':'test-MOD14','line':0,'sample':0,'mask_class':5,'file_sha256':'a'*64,'geo_sha256':'b'*64,'case_id':'grove-2025','lon':lon,'lat':lat}
        result=cov.evaluate_pixels(inputs,inventory,cells=cells,original_samples=[original]);self.assertTrue(cov.verify(result)['verified'])
        for key,value in [('mask_class',8),('file_sha256','e'*64),('lon',0)]:
            bad={**original,key:value}
            with self.subTest(key=key),self.assertRaises(ValueError):cov.evaluate_pixels(inputs,inventory,cells=cells,original_samples=[bad])
        result['rows'][0]['usable_fraction']=.9
        with self.assertRaisesRegex(ValueError,'recount'):cov.verify(result)


def pass_fixture():
    a={'producer_id':'m','source_id':'MODIS_SP','platform':'Terra','grid_x':0,'grid_y':0,'start_utc':'2025-08-01T12:00:00Z','end_utc':'2025-08-01T12:05:00Z','state':'detected','class_counts':{8:1},'file_sha256':'a'*64,'geo_sha256':'b'*64}
    return [a,{**a,'producer_id':'v','source_id':'VIIRS_SNPP_SP','platform':'S-NPP','start_utc':'2025-08-01T12:40:00Z','end_utc':'2025-08-01T12:45:00Z','state':'cloud-obscured','class_counts':{4:1}}]


class DisagreementTests(unittest.TestCase):
    def test_cluster_bootstrap_counts_reproduce_expanded_cell_resampling(self):
        from fireatlas.opportunity import group_uncertainty,confusion
        import random
        groups=[[{'modis_granule':f'm{i}','viirs_granule':f'v{i}','category':category} for category in ['both_detected']*(i+2)+['modis_only']*(4-i)+['viirs_only']*i+['both_without_detection']*50] for i in range(4)]
        rng=random.Random(20261027);samples=[]
        for _ in range(500):samples.append(confusion([r for g in rng.choices(groups,k=4) for r in g])['positive_jaccard'])
        samples.sort();expected=[samples[int(499*.05)],samples[int(499*.95)]]
        self.assertEqual(expected,group_uncertainty([r for g in groups for r in g])['positive_jaccard_interval'])
    def test_all_state_rematching_preserves_cloud_and_actual_denominators(self):
        passes=pass_fixture();result=dis.analyze(passes)
        self.assertEqual(0,result['experiments']['30']['all_matched_sample_pairs']);self.assertEqual(1,result['experiments']['60']['positive_pairs_with_cloud_sample'])
        pair=result['experiments']['60']['pairs'][0];self.assertEqual('unresolved',pair['physical_cause']);self.assertEqual('unknown',pair['full_cell_opportunity'])
        self.assertIn('cloud-mask-in-sampled-native-pixels',[r['condition'] for r in pair['supported_conditions']]);self.assertTrue(dis.verify(json.loads(json.dumps(result)),passes)['verified'])
        result['experiments']['60']['positive_sample_pairs']=42
        with self.assertRaisesRegex(ValueError,'recount'):dis.verify(result,passes)
    def test_duplicate_sample_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Duplicate'):dis.analyze(pass_fixture()*2)


class ParallelAcquisitionTests(unittest.TestCase):
    def test_one_day_fallback_preserves_cap_and_resumes_the_saved_plan(self):
        from scripts.acquire_qualification_overlap import acquire_month
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);calls=[]
            def acquire(root,plan,**kwargs):
                calls.append(plan)
                if plan['window_days']==5:raise ValueError('Provider response exceeded bounded volume; request remains incomplete.')
            with patch('scripts.acquire_qualification_overlap.acq.acquire',side_effect=acquire):
                result=acquire_month(root,'norcal','2012-02',('MODIS_SP',),discovery(),2)
                again=acquire_month(root,'norcal','2012-02',('MODIS_SP',),discovery(),2)
            self.assertEqual([5,1,1],[p['window_days'] for p in calls]);self.assertEqual(29,len(result['requests']));self.assertEqual(result['requests'],again['requests']);self.assertEqual(acq.WINDOW_LIMIT,result['request_byte_ceiling'])
    def test_one_day_receipts_import_a_verified_zero_month(self):
        planned=acq.plan('norcal',['2012-02'],['MODIS_SP'],discovery(),window_days=1)
        with tempfile.TemporaryDirectory() as td,patch.object(acq,'firms_key',return_value='test-not-a-credential'),patch.object(acq.time,'sleep'):
            acq.acquire(td,planned,opener=lambda *a,**k:Response(HEADER.encode()))
            result=acq.import_month(td,planned,'MODIS_SP','2012-02');self.assertEqual(0,result['rows_read'])
            merged=Path(td)/'months/norcal-MODIS_SP-2012-02.csv';before=merged.stat().st_mtime_ns
            again=acq.import_month(td,planned,'MODIS_SP','2012-02');self.assertTrue(again['already_imported']);self.assertEqual(before,merged.stat().st_mtime_ns)
            merged.write_text('corrupt merged bytes')
            self.assertTrue(acq.import_month(td,planned,'MODIS_SP','2012-02')['already_imported']);self.assertEqual(HEADER,merged.read_text())
    def test_rate_limit_failure_is_sanitized_atomic_and_resumable(self):
        planned=acq.plan('norcal',['2012-02'],['MODIS_SP'],discovery());calls=[]
        def fail(*args,**kwargs):
            calls.append(1);raise HTTPError('https://secret.invalid/private',429,'rate',{'Retry-After':'30'},None)
        with tempfile.TemporaryDirectory() as td,patch.object(acq,'firms_key',return_value='test-not-a-credential'):
            with self.assertRaisesRegex(ValueError,'HTTP 429.*30') as raised:acq.acquire(td,planned,workers=2,opener=fail)
            self.assertNotIn('secret',str(raised.exception));self.assertEqual(1,len(calls));self.assertFalse(list(Path(td).glob('requests/*.json')));self.assertFalse(list(Path(td).glob('requests/*.part')));self.assertFalse(list(Path(td).glob('plans/*.json')))
            with patch.object(acq.time,'sleep'):
                acq.acquire(td,planned,workers=2,opener=lambda *a,**k:Response(HEADER.encode()))
            self.assertTrue(all(acq.receipt_valid(td,r) for r in planned['requests']))
            acq.acquire(td,planned,workers=2,opener=lambda *a,**k:self.fail('duplicate request'))
    def test_invalid_workers_and_budget_fail_before_network(self):
        planned=acq.plan('norcal',['2012-02'],['MODIS_SP'],discovery())
        with tempfile.TemporaryDirectory() as td:
            for workers in (0,3,True):
                with self.assertRaises(ValueError):acq.acquire(td,planned,workers=workers)
            with patch.object(acq,'CAP_BYTES',1),self.assertRaisesRegex(ValueError,'Storage'):acq.acquire(td,planned,workers=2,opener=lambda *a,**k:self.fail('network before reserve'))


class CampaignTransferTests(unittest.TestCase):
    def test_acquired_platforms_receive_separate_direct_recounted_experiments(self):
        from scripts import complete_mentor_campaign as campaign
        from fireatlas.core import connect,ingest
        from fireatlas.regions import REGIONS
        with tempfile.TemporaryDirectory() as td:
            work=Path(td);(work/'campaign').mkdir()
            with connect(work/'campaign/observations.sqlite3') as db:
                for source,satellite,version in [('VIIRS_SNPP_SP','N','2'),('VIIRS_NOAA20_SP','1','2.0'),('VIIRS_NOAA21_SP','2','3')]:
                    file=work/(source+'.csv');file.write_text(HEADER+f'40,-121,2025-02-01,1200,{satellite},VIIRS,90,{version},1,1,2,D\n')
                    imported=ingest(db,file,source,complete_month='2025-02',bbox=REGIONS['norcal']['bbox'])
                    db.execute('INSERT INTO source_exports VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(imported['batch_id'],'norcal',source,'2025-02','2025-02-01','2025-02-28',*REGIONS['norcal']['bbox'],1,'request-metadata',json.dumps([version]),'a'*64,'b'*64))
            with patch.object(campaign,'WORK',work):records=campaign.assess_transfers()
            self.assertEqual(2,len(records));self.assertEqual({'VIIRS_NOAA20_SP','VIIRS_NOAA21_SP'},{r['target_cohort']['source'] for r in records})
            for record in records:
                evidence=json.loads((work/record['artifact']).read_text());self.assertTrue(tr.verify(evidence)['verified']);self.assertFalse(evidence['admitted']);self.assertEqual(1,evidence['eligible_months']);self.assertEqual([],evidence['factor_chain'])
            index=json.loads((work/'transfer-results.json').read_text());self.assertFalse(index['scientific_admission']);self.assertTrue(index['unresolved'])


if __name__=='__main__':unittest.main()
