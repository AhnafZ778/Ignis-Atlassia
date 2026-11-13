import copy
from datetime import date,timedelta,datetime,timezone
import io,json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fireatlas import qualification as q, comparability_v2 as v2, acquisition as acq, opportunity as opp
from fireatlas.core import connect


def fixture():
    days=[];d=date(2012,1,1)
    while d<date(2020,1,1):
        value=(d.day+d.month)%9
        days.append({'date':d.isoformat(),'sources':{s:{'cells':value*factor,'raw':value*factor,'versions':[version], 'verified_export':True,'processing_gap':False} for s,factor,version in [('MODIS_SP',1,'61.03'),('VIIRS_SNPP_SP',3,'2.0')]}})
        d+=timedelta(days=1)
    return {'schema':'fireatlas-comparability-input-v1','region':'norcal','versions':['61.03','2.0'],'synthetic':True,'days':days}


class ProtocolTests(unittest.TestCase):
    def test_template_never_approves_and_malformed_closes(self):
        self.assertFalse(q.approval(q.review_template())['approved'])
        for reviewer in (None,[],3): self.assertFalse(q.approval({'reviewer':reviewer})['approved'])
        value=fixture();value.pop('synthetic')
        with self.assertRaisesRegex(ValueError,'approval'): v2.analyze(value)
    def test_synthetic_is_never_authentic(self):
        with self.assertRaisesRegex(ValueError,'Synthetic'): v2.analyze(fixture())
    def test_frozen_protocol_hash_changes_with_bytes(self):
        p=q.protocol();self.assertEqual(q.digest({k:v for k,v in p.items() if k!='protocol_sha256'}),p['protocol_sha256'])
    def test_chronological_partitions_and_interval_coverage(self):
        bundle=v2.analyze(fixture(),synthetic=True)
        self.assertFalse(bundle['result']['performance_pass']);self.assertFalse(bundle['result']['admission']['monthly_product'])
        for ev in bundle['result']['evaluation'].values():
            self.assertEqual(3,len(ev['folds']))
            for fold in ev['folds']:
                self.assertLess(max(fold['training_years']),min(fold['calibration_years']))
                self.assertLess(max(fold['calibration_years']),fold['test_year'])
                self.assertFalse(set(fold['training_months'])&set(fold['calibration_months']))
            self.assertEqual(1,ev['adjusted']['coverage'])
        self.assertTrue(v2.verify(bundle)['verified'])
        altered=copy.deepcopy(bundle);altered['result']['evaluation']['forward']['rows'][0]['interval'][1]+=1
        with self.assertRaisesRegex(ValueError,'recount'):v2.verify(altered)
    def test_test_and_calibration_cannot_change_training_model(self):
        a=fixture();b=copy.deepcopy(a)
        for day in b['days']:
            if day['date']>='2015-01-01':
                item=day['sources']['VIIRS_SNPP_SP'];item['cells']*=7;item['raw']*=7
        ea=v2.analyze(a,synthetic=True)['result']['evaluation']['forward'];eb=v2.analyze(b,synthetic=True)['result']['evaluation']['forward']
        fa,fb=ea['folds'][0],eb['folds'][0]
        self.assertEqual(fa['selected_model'],fb['selected_model']);self.assertEqual(ea['rows'][0]['prediction'],eb['rows'][0]['prediction'])
        self.assertNotEqual(fa['log1p_radii'],fb['log1p_radii'])
    def test_unknown_gap_mixed_and_sparse_quarters(self):
        value=fixture();value['days'][0]['sources']['MODIS_SP']['cells']=None
        value['days'][34]['sources']['VIIRS_SNPP_SP']['processing_gap']=True
        value['days'][62]['sources']['MODIS_SP']['versions']=['6.03','61.03']
        p=v2.pending(value);reasons={r for m in p['excluded_months'] for r in m['reasons']}
        self.assertTrue({'unknown-source-total','documented-processing-gap','unknown-or-mixed-product-version'}<=reasons)
        value['days']=[d for d in value['days'] if not d['date'].startswith(('2017-01','2017-02','2017-03'))]
        ev=v2.analyze(value,synthetic=True)['result']['evaluation']['forward'];self.assertFalse(ev['checks']['test_support'])
    def test_all_zero_baseline_is_unqualified(self):
        self.assertEqual([0,0],v2.bounds(0,0));self.assertEqual([124,124],v2.bounds(124,0))

    def test_ai_experiment_recounts_but_cannot_qualify(self):
        # Explicit test fixture relabel, confined to memory; never published.
        value=fixture();value['synthetic']=False
        receipt=q.experimental_review()
        bundle=v2.analyze(value,experimental=receipt)
        self.assertFalse(bundle['result']['review_state']['approved'])
        self.assertFalse(bundle['result']['performance_pass'])
        self.assertTrue(v2.verify(bundle)['verified'])
        from fireatlas.research_review import monthly_release_gate
        gate=monthly_release_gate(bundle,native_evidence={})
        self.assertFalse(gate['checks']['not_ai_experimental'])
        self.assertFalse(gate['monthly_product_admitted'])
        altered=copy.deepcopy(bundle);altered['result']['experimental_review']=None
        with self.assertRaisesRegex(ValueError,'approval'):v2.verify(altered)
        altered=copy.deepcopy(bundle);altered['result']['performance_pass']=True
        with self.assertRaisesRegex(ValueError,'recount'):v2.verify(altered)

    def test_ai_review_is_bound_and_never_mixed_with_other_modes(self):
        value=fixture();receipt=q.experimental_review();receipt['human_authored']=True
        value['synthetic']=False
        with self.assertRaisesRegex(ValueError,'frozen'):v2.analyze(value,experimental=receipt)
        with self.assertRaisesRegex(ValueError,'mix'):v2.analyze(value,q.review_template(),experimental=q.experimental_review())
        with self.assertRaisesRegex(ValueError,'Synthetic'):v2.analyze(fixture(),experimental=q.experimental_review())
        with self.assertRaisesRegex(ValueError,'mix'):v2.analyze(fixture(),synthetic=True,experimental=q.experimental_review())
        with self.assertRaisesRegex(ValueError,'frozen'):v2.analyze(value,experimental=q.experimental_review('daily'))

    def test_daily_ai_experiment_validates_contract_and_recounts(self):
        from fireatlas import daily_estimates as daily
        from fireatlas.research_review import daily_release_gate
        value=fixture();value['days']=value['days'][:10];value['synthetic']=False
        counts={d['date']:{'terra':d['sources']['MODIS_SP']['cells'],'aqua':0} for d in value['days']}
        result=daily.analyze(value,counts,experimental=q.experimental_review('daily'))
        self.assertTrue(daily.verify(result)['verified'])
        self.assertFalse(daily_release_gate(result)['daily_estimates_admitted'])
        self.assertFalse(result['performance_pass'])
        value['schema']='unrelated-contract-v99'
        with self.assertRaisesRegex(ValueError,'Versioned'):daily.analyze(value,counts,experimental=q.experimental_review('daily'))


HEADER='latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,scan,track,frp,daynight\n'
class Response(io.BytesIO):
    def __init__(self,body,headers=None):super().__init__(body);self.headers=headers or {};self.status=200
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

def discovery():return {'schema':'fireatlas-source-availability-v1','retrieved_utc':datetime.now(timezone.utc).isoformat(),'products':[{'data_id':'MODIS_SP','min_date':'2000-11-01','max_date':'2026-07-31'}]}

class AcquisitionTests(unittest.TestCase):
    def test_runner_retries_both_busy_states_only(self):
        from scripts.acquire_qualification_overlap import retry_busy
        for message in ('Another campaign acquisition/import is active.','Another campaign acquisition is active.'):
            operation=unittest.mock.Mock(side_effect=[ValueError(message),'complete'])
            with patch('scripts.acquire_qualification_overlap.time.sleep'):
                self.assertEqual('complete',retry_busy(operation))
            self.assertEqual(2,operation.call_count)
        operation=unittest.mock.Mock(side_effect=ValueError('Storage gate closed'))
        with self.assertRaisesRegex(ValueError,'Storage'):retry_busy(operation)
        self.assertEqual(1,operation.call_count)
    def test_unavailable_product_not_substituted(self):
        p=acq.plan('norcal',['2012-01'],['VIIRS_NOAA21_SP'],discovery());self.assertFalse(p['requests']);self.assertEqual(1,len(p['unavailable']))
    def test_truncated_body_never_completes(self):
        p=acq.plan('norcal',['2012-02'],['MODIS_SP'],discovery())
        with tempfile.TemporaryDirectory() as td,patch.object(acq,'firms_key',return_value='test-not-a-credential'),patch.object(acq.time,'sleep'):
            with self.assertRaisesRegex(ValueError,'byte length'):acq.acquire(td,p,opener=lambda *a,**k:Response(HEADER.encode(),{'Content-Length':str(len(HEADER)+100)}))
            self.assertFalse(list(Path(td).glob('requests/*.json')))
    def test_empty_complete_is_idempotent_and_corruption_rejected(self):
        p=acq.plan('norcal',['2012-02'],['MODIS_SP'],discovery())
        with tempfile.TemporaryDirectory() as td,patch.object(acq,'firms_key',return_value='test-not-a-credential'),patch.object(acq.time,'sleep'):
            acq.acquire(td,p,opener=lambda *a,**k:Response(HEADER.encode(),{'Content-Length':str(len(HEADER))}))
            a=acq.import_month(td,p,'MODIS_SP','2012-02');b=acq.import_month(td,p,'MODIS_SP','2012-02')
            self.assertEqual(0,a['rows_read']);self.assertTrue(b['already_imported']);self.assertEqual([],a['versions'])
            acq.acquire(td,p,opener=lambda *a,**k:self.fail('duplicate download'))
            next((Path(td)/'requests').glob('*.csv')).write_text('corrupt')
            with self.assertRaisesRegex(ValueError,'corrupt'):acq.acquire(td,p)
    def test_atomic_ledger_failure_rolls_back_rows(self):
        p=acq.plan('norcal',['2012-02'],['MODIS_SP'],discovery())
        with tempfile.TemporaryDirectory() as td,patch.object(acq,'firms_key',return_value='test-not-a-credential'),patch.object(acq.time,'sleep'):
            acq.acquire(td,p,opener=lambda *a,**k:Response(HEADER.encode()))
            with connect(Path(td)/'observations.sqlite3') as db:db.execute("CREATE TRIGGER reject_receipt BEFORE INSERT ON source_exports BEGIN SELECT RAISE(ABORT,'blocked'); END")
            with self.assertRaises(Exception):acq.import_month(td,p,'MODIS_SP','2012-02')
            with connect(Path(td)/'observations.sqlite3') as db:
                for name in ('batches','export_windows','source_exports'):self.assertEqual(0,db.execute('SELECT count(*) FROM '+name).fetchone()[0])
    def test_budget_rejects_before_request(self):
        p=acq.plan('norcal',['2012-02'],['MODIS_SP'],discovery())
        with tempfile.TemporaryDirectory() as td,patch.object(acq,'CAP_BYTES',1):
            with self.assertRaisesRegex(ValueError,'Storage'):acq.acquire(td,p,opener=lambda *a,**k:self.fail('request before storage check'))


class OpportunityTests(unittest.TestCase):
    def test_complete_pagination_and_changed_hits(self):
        count=0
        def open_page(request,**kwargs):
            nonlocal count
            if count:self.assertEqual('next',request.get_header('Cmr-search-after'))
            count+=1
            entry={'id':str(count),'producer_granule_id':str(count),'time_start':'2024-07-25T00:00:00Z','time_end':'2024-07-25T00:05:00Z','polygons':[['0 0 0 1 1 1 0 0']]}
            return Response(json.dumps({'feed':{'entry':[entry]}}).encode(),{'CMR-Hits':'2','CMR-Search-After':'next'})
        p=opp.discover_product('park-2024','MOD14','061','fire-mask',opener=open_page);self.assertTrue(p['inventory_complete']);self.assertEqual(2,len(p['pages']));self.assertTrue(p['granules'][0]['candidate_geometry'])
        inv={'case_id':'park-2024','inventory_complete':True,'products':[p]};ledger=opp.ledger('park-2024',inv,[])
        self.assertFalse(ledger['no_pass_enabled']);self.assertTrue(all(g['opportunity_state']=='unknown' for g in ledger['acquisitions']))
    def test_duplicate_page_never_complete(self):
        entry={'id':'same','time_start':'2024-07-25T00:00:00Z'}
        p=opp.discover_product('park-2024','MOD14','061','fire-mask',opener=lambda *a,**k:Response(json.dumps({'feed':{'entry':[entry]}}).encode(),{'CMR-Hits':'2','CMR-Search-After':'next'}))
        self.assertFalse(p['inventory_complete']);self.assertEqual('duplicate-cmr-id',p['incomplete_reason'])
    def test_actual_rematching_not_filtering(self):
        def p(identifier,source,start,end,state='detected'):return {'producer_id':identifier,'source_id':source,'start_utc':'2024-07-25T'+start+':00Z','end_utc':'2024-07-25T'+end+':00Z','grid_x':1,'grid_y':2,'state':state,'platform':'Terra' if source=='MODIS_SP' else 'S-NPP','file_sha256':'a'*64,'geo_sha256':'b'*64}
        # Closest start at90m has a long interval and is ineligible at30m;
        # rematching must recover the second candidate at30m.
        passes=[p('m','MODIS_SP','00:00','00:05'),p('v1','VIIRS_SNPP_SP','00:01','01:00'),p('v2','VIIRS_SNPP_SP','00:10','00:15')]
        a=opp.rematch(passes,90);b=opp.rematch(passes,30)
        self.assertEqual('v1',a[0]['viirs_granule']);self.assertEqual('v2',b[0]['viirs_granule']);self.assertEqual('unresolved',b[0]['cause'])
        m=opp.confusion(b);self.assertEqual(1,m['positive_union_pairs']);self.assertEqual(1,m['viirs_overlap_of_modis']['denominator'])
        self.assertIsNone(opp.group_uncertainty(b)['positive_jaccard_interval'])

if __name__=='__main__':unittest.main()

class ReviewAndDailyTests(unittest.TestCase):
    def test_real_hurdle_uses_prediction_time_inputs_and_recovers_zero(self):
        import numpy as np
        from fireatlas.daily_estimates import fit_predict,features
        rng=np.random.default_rng(10);rows=[]
        for i in range(1800):
            d=date(2012,1,1)+timedelta(days=i);t=int(rng.poisson(1.4));a=int(rng.poisson(1.1));m=max(t,a)+int(rng.integers(0,min(t,a)+1));v=int(rng.poisson(1+2*m)) if rng.random()<.7 else 0
            rows.append({'date':d.isoformat(),'modis':m,'terra':t,'aqua':a,'viirs':v})
        prediction=fit_predict(rows[:1500],rows[1500:]);self.assertEqual(300,len(prediction['expected']))
        self.assertTrue(any(r['modis']==0 and x>0 for r,x in zip(rows[1500:],prediction['expected'])))
        row={**rows[-1],'viirs':999999};self.assertEqual(features(rows[-1]),features(row))
        with self.assertRaisesRegex(ValueError,'both occurrence'):fit_predict([{**r,'viirs':0} for r in rows[:1500]],rows[1500:])
    def test_daily_approval_and_synthetic_guard(self):
        from fireatlas.daily_estimates import analyze
        with self.assertRaisesRegex(ValueError,'Synthetic'):analyze(fixture(),{})
        value=fixture();value.pop('synthetic')
        with self.assertRaisesRegex(ValueError,'approval'):analyze(value,{})
    def test_task_study_requires_observed_complete_qualified_participants(self):
        from fireatlas.research_review import task_study_template,task_study_check,TASKS
        study=task_study_template('a'*64);self.assertFalse(task_study_check(study,'a'*64)['passed'])
        study.update(human_observed=True,observer='Synthetic test observer',signed_utc='2026-01-01T00:00:00Z')
        for p in study['participants']:p.update(qualification='Synthetic test qualification',without_guidance=True,elapsed_seconds=100,tasks={t:True for t in TASKS})
        self.assertTrue(task_study_check(study,'a'*64)['passed'])
        study['participants'][0]['critical_misunderstandings']=['called counts fire truth']
        self.assertFalse(task_study_check(study,'a'*64)['passed'])
        study['participants'][0]=None;self.assertFalse(task_study_check(study,'a'*64)['passed'])
    def test_summary_booleans_cannot_replace_native_documents(self):
        from fireatlas.research_review import monthly_release_gate
        bundle=v2.analyze(fixture(),synthetic=True)
        false_summary={case:{'status':'passed','reviewed':30,'unresolved':0,'disagree':0} for case in ('park-2024','grove-2025')}
        gate=monthly_release_gate(bundle,native_reviews=false_summary,native_evidence={})
        self.assertFalse(gate['monthly_product_admitted']);self.assertFalse(gate['checks']['native_processing_reviewed'])
    def test_future_and_observation_preservation(self):
        from fireatlas.continuity import future_reservation,historical_record
        with self.assertRaises(ValueError):future_reservation('2025-01-01','2025-12-31','2026-01-01')
        with self.assertRaises(ValueError):historical_record([{'kind':'observation','date':'2010-01-01'}],[{'kind':'counterfactual-estimate','date':'2010-01-01','bridge_sha256':'a','interval':[0,1],'model_sha256':'m','input_sha256':'i'}],{'a':{'admitted':True}})

class PublicationTests(unittest.TestCase):
    def test_exact_manifest_reader_rejects_corruption_and_traversal(self):
        import hashlib
        from fireatlas.qualification_publication import read
        body=b'{"schema":"test"}\n';manifest={'schema':'fireatlas-qualification-publication-v2','state':'test','files':{'readiness.json':{'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}}};release=q.digest(manifest);manifest['release_id']=release
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);destination=root/'releases'/release;destination.mkdir(parents=True);(destination/'readiness.json').write_bytes(body);acq.atomic_json(destination/'manifest.json',manifest)
            acq.atomic_json(root/'current.json',{'release_id':release,'manifest_sha256':hashlib.sha256((destination/'manifest.json').read_bytes()).hexdigest()})
            self.assertEqual(body,read(root,'readiness.json'))
            with self.assertRaises(ValueError):read(root,'../readiness.json')
            with self.assertRaises(ValueError):read(root,'collection-pilot.json')
            (destination/'readiness.json').write_bytes(b'changed')
            with self.assertRaises(ValueError):read(root,'readiness.json')
    def test_published_native_metrics_reproduce_and_unknown_stays_unknown(self):
        import gzip
        from fireatlas.qualification_publication import read
        root=Path(__file__).resolve().parents[1]/'site/data/qualification'
        for case in ('park-2024','grove-2025'):
            inputs=json.loads(gzip.decompress(read(root,'native-inputs/'+case+'.json.gz')))
            summary=json.loads(read(root,'native-summary/'+case+'.json'))
            self.assertEqual(q.digest(inputs['passes']),inputs['sha256'])
            for tolerance in (30,60,90):self.assertEqual(opp.confusion(opp.rematch(inputs['passes'],tolerance)),summary['thresholds'][str(tolerance)]['metrics'])
            ledger=json.loads(read(root,'opportunity/'+case+'.json'));self.assertFalse(ledger['no_pass_enabled']);self.assertTrue(all(x['opportunity_state']=='unknown' for x in ledger['acquisitions']))

class NativeAdmissionTests(unittest.TestCase):
    def test_native_agreement_contradictions_and_future_review_block(self):
        from fireatlas.mask_review import make_template
        from fireatlas.research_review import monthly_release_gate
        evidence={};reviews={}
        for case in ('park-2024','grove-2025'):
            e={'case_id':case,'inventory':[{'producer_id':'m','source_id':'MODIS_SP','status':'processed','file_sha256':'a'*64,'geo_sha256':'b'*64}],
               'pixels':[{'producer_id':'m','line':i,'sample':0,'lat':40.,'lon':-121.,'mask_class':9,'grid_x':1,'grid_y':2} for i in range(30)]}
            r=make_template(case,e);r['reviewer'].update(name='Synthetic fixture reviewer',affiliation='Synthetic test',reviewed_utc='2026-01-01T00:00:00Z',independent=True);r['interpretation']='Synthetic engineering fixture only'
            for s in r['samples']:s.update(outcome='agree',observed_mask_class=9,observed_lat=40.,observed_lon=-121.,observed_grid_x=1,observed_grid_y=2)
            evidence[case]=e;reviews[case]=r
        bundle=v2.analyze(fixture(),synthetic=True)
        gate=monthly_release_gate(bundle,native_reviews=reviews,native_evidence=evidence);self.assertTrue(gate['checks']['native_processing_reviewed']);self.assertFalse(gate['monthly_product_admitted'])
        reviews['park-2024']['samples'][0]['observed_mask_class']=3
        self.assertFalse(monthly_release_gate(bundle,native_reviews=reviews,native_evidence=evidence)['checks']['native_processing_reviewed'])
        reviews['park-2024']['samples'][0]['observed_mask_class']=9;reviews['park-2024']['reviewer']['reviewed_utc']='2099-01-01T00:00:00Z'
        self.assertFalse(monthly_release_gate(bundle,native_reviews=reviews,native_evidence=evidence)['checks']['native_processing_reviewed'])

class DailyPartitionTests(unittest.TestCase):
    def test_daily_chronology_and_download_recount(self):
        from fireatlas import daily_estimates as daily
        value=fixture();counts={d['date']:{'terra':d['sources']['MODIS_SP']['cells'],'aqua':0} for d in value['days']}
        def synthetic_fit(train,target):
            return {'expected':[r['modis']*3+.1 for r in target],'probability_positive':[.8 for r in target],'parameters':[1.],'dependency':'explicit synthetic engineering mock'}
        with patch.object(daily,'fit_predict',synthetic_fit):
            result=daily.analyze(value,counts,synthetic=True);self.assertEqual(3,len(result['folds']));self.assertFalse(result['admitted']);self.assertFalse(result['performance_pass'])
            for fold in result['folds']:self.assertLess(max(fold['training_years']),min(fold['calibration_years']));self.assertLess(max(fold['calibration_years']),fold['test_year'])
            self.assertTrue(daily.verify(result)['verified'])
            result['rows'][0]['interval'][0]+=.01
            with self.assertRaisesRegex(ValueError,'recount'):daily.verify(result)

class NativeCacheTests(unittest.TestCase):
    def test_statistical_cache_tampering_cannot_publish(self):
        from scripts import export_qualification as export
        import hashlib
        empty={'schema':'fireatlas-comparability-input-v1','region':'norcal','days':[],'source_ledger':[],'latest_standard_utc':None}
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);db=root/'science.sqlite3';work=root/'work';site=root/'site'
            with connect(db):pass
            cache=work/'native';cache.mkdir(parents=True)
            method_hash=hashlib.sha256((export.ROOT/'fireatlas/opportunity.py').read_bytes()).hexdigest()
            fake={**opp.diagnostics([]),'case_id':'park-2024','native_input_sha256':q.digest([]),'method_sha256':method_hash,'sampled_sensitivity':opp.sampled_sensitivity([])}
            fake['thresholds']['30']['metrics']['n_pairs']=999999;acq.atomic_json(cache/'park-2024.json',fake)
            with patch.object(export,'capture',side_effect=lambda db,r:{**empty,'region':r}),patch.object(export,'inventory',return_value={'regions':{},'claims':{}}),patch.object(export,'read_evidence',side_effect=lambda c:{'case_id':c,'inventory':[],'pixels':[]}):
                with self.assertRaisesRegex(ValueError,'recount'):export.publish(db,site,work)
            self.assertFalse((site/'data/qualification/current.json').exists())

class ProviderBoundaryTests(unittest.TestCase):
    def test_edge_rows_preserved_but_excluded_from_exact_study(self):
        p=acq.plan('punjab-haryana',['2012-02'],['MODIS_SP'],discovery());r=p['requests'][0]
        body=(HEADER+'31.49993,73.79999,2012-02-01,1200,T,MODIS,90,6.03,1,1,2,D\n').encode()
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/'response.csv';file.write_bytes(body);v=acq.validate_csv(file,r)
            self.assertEqual(1,v['rows']);self.assertEqual(0,v['in_scope_rows']);self.assertEqual(1,len(v['excluded_bbox_rows']));self.assertEqual(body,file.read_bytes())
            file.write_bytes(body.replace(b'73.79999',b'73.70'))
            with self.assertRaisesRegex(ValueError,'beyond'):acq.validate_csv(file,r)

class EdgeImportTests(unittest.TestCase):
    def test_verified_edge_export_import_filters_without_altering_original(self):
        p=acq.plan('punjab-haryana',['2012-02'],['MODIS_SP'],discovery())
        original=(HEADER+'31.49993,73.79999,2012-02-01,1200,T,MODIS,90,6.03,1,1,2,D\n').encode()
        calls=0
        def provider(*a,**k):
            nonlocal calls
            calls+=1;return Response(original if calls==1 else HEADER.encode())
        with tempfile.TemporaryDirectory() as td,patch.object(acq,'firms_key',return_value='synthetic-test'),patch.object(acq.time,'sleep'):
            acq.acquire(td,p,opener=provider)
            stored=Path(td)/'requests'/(p['requests'][0]['id']+'.csv');self.assertEqual(original,stored.read_bytes())
            receipt=json.loads(stored.with_suffix('.json').read_text());self.assertEqual(1,len(receipt['excluded_bbox_rows']))
            imported=acq.import_month(td,p,'MODIS_SP','2012-02');self.assertEqual(0,imported['rows_inserted'])
            with connect(Path(td)/'observations.sqlite3') as db:self.assertEqual(1,db.execute('SELECT count(*) FROM source_exports WHERE complete_export=1').fetchone()[0]);self.assertEqual(0,db.execute('SELECT count(*) FROM observations').fetchone()[0])
