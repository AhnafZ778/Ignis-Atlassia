"""Engineering-only publication tests; no authentic review is manufactured."""
import copy,gzip,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from fireatlas import qualification_successors as s,opportunity_frames as f,opportunity_review as review
from fireatlas.qualification import digest
from tests.test_opportunity_frames import fixture,seal
from tests.test_transfer_opportunity import count_evidence


def pilot_frame(*,x_offset=0):
    value=fixture(empty=True);value.update(synthetic=False,start='2025-07-04',end='2025-07-04')
    value['inventory'].update(start=value['start'],end=value['end'])
    for product in value['inventory']['products']:
        product['query']=f.query_url('grove-2025',value['start'],value['end'],product['product'],product['version'])
    value['tile'][0]+=x_offset;value['tile'][2]+=x_offset
    return f.evaluate(seal(value))


def write(root,name,value):
    path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(value).encode(),mtime=0))
    return {'artifact':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'result_sha256':value['result_sha256']}


class SuccessorTests(unittest.TestCase):
    def test_daily_diagnostics_require_matching_source_and_exact_recount(self):
        from fireatlas import daily_diagnostics
        from scripts.diagnose_daily_holdouts import source_hashes
        from tests.test_daily_diagnostics import fixture
        original={**fixture(),'result_sha256':'a'*64,'input_sha256':'b'*64,'region':'norcal','versions':['6.03','2'],'checks':{}}
        source=gzip.compress(json.dumps(original).encode(),mtime=0)
        report={'schema':'fireatlas-daily-heldout-diagnostic-report-v1','release_id':'c'*64,
                'result_sha256':'a'*64,'input_sha256':'b'*64,'region':'norcal','versions':['6.03','2'],
                'artifact':'cohort-daily/'+'d'*16+'.json.gz','artifact_sha256':hashlib.sha256(source).hexdigest(),
                'original_checks':{},'method_source_sha256':source_hashes(),'diagnostics':daily_diagnostics.analyze(original),
                'scientific_admission':False,'daily_estimates_admitted':False}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'daily-diagnostics-v1/report.json';path.parent.mkdir();path.write_text(json.dumps(report))
            entry={'artifact':'daily-diagnostics-v1/report.json','sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                   'source_release_id':'c'*64,'result_sha256':'a'*64}
            with patch('fireatlas.qualification_publication.read',return_value=source):
                checked=s.daily_diagnostics_asset(root,entry,original,root)
                self.assertEqual(report,checked[0]);self.assertEqual(entry['sha256'],checked[1].sha256)
                self.assertIsNone(s.daily_diagnostics_asset(root,entry,{**original,'result_sha256':'f'*64},root))
                altered=copy.deepcopy(report);altered['diagnostics']['overall']['n_utc_days']=999
                path.write_text(json.dumps(altered));entry['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
                with self.assertRaisesRegex(ValueError,'recount differs'):s.daily_diagnostics_asset(root,entry,original,root)
            path.write_text('corrupt')
            with self.assertRaisesRegex(ValueError,'bytes differ'):s.daily_diagnostics_asset(root,entry,original,root)

    def test_monthly_source_receipt_requires_exact_bundle_capture_and_lock(self):
        bundle={'result':{'input_sha256':'a'*64,'result_sha256':'b'*64}}
        proof={'schema':'fireatlas-monthly-source-provenance-v1','status':'verified',
               'monthly_input_sha256':'a'*64,'monthly_result_sha256':'b'*64,
               'source_capture_sha256':'c'*64,'eligible_months':1,'eligible_utc_days_checked':29,
               'original_sources_reopened':True,'scientific_admission':False}
        proof['result_sha256']=digest(proof)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'monthly-provenance-v1/proof.json';path.parent.mkdir();path.write_text(json.dumps(proof))
            entry={'artifact':'monthly-provenance-v1/proof.json','sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                   'monthly_input_sha256':'a'*64,'monthly_result_sha256':'b'*64}
            key='1'*16;values={'cohort-monthly/'+key+'.json':bundle,'monthly-cohorts/norcal.json':{'entries':[{'id':key}]}}
            (root/'successor-evidence.json').write_text(json.dumps({'schema':'fireatlas-successor-evidence-index-v1','monthly_provenance':{key:entry}}))
            with self.assertRaisesRegex(ValueError,'publisher campaign lock'):s.assets(root,copy.deepcopy(values))
            with patch('fireatlas.monthly_source_provenance.capture_for_bundle',return_value={'input_sha256':'c'*64}), \
                 patch('fireatlas.monthly_source_provenance._verify_while_locked',return_value=proof) as recount:
                out=s.assets(root,copy.deepcopy(values),campaign_locked=True)
                reference=out['monthly-provenance/'+key+'.json']
                self.assertIsInstance(reference,s.FrozenFile)
                self.assertEqual(path.read_bytes(),reference.path.read_bytes())
                self.assertEqual(entry['sha256'],reference.sha256)
                recount.assert_called_once()
                self.assertEqual('verified',out['monthly-cohorts/norcal.json']['entries'][0]['source_provenance']['status'])
                newer=copy.deepcopy(bundle);newer['result']['input_sha256']='d'*64
                self.assertIsNone(s.monthly_provenance_asset(root,entry,newer))
                path.write_text('{"changed":true}')
                self.assertNotEqual(reference.sha256,s.frozen_file(path).sha256)
                path.write_text(json.dumps(proof))
            preflight={'entry_sha256':digest(entry),'bundle_sha256':digest(bundle),'status':'verified-recount','source_files':{},'database_files':{},'plan_files':[]}
            with patch('fireatlas.monthly_source_provenance._verify_while_locked') as recount:
                self.assertEqual(proof,s.monthly_provenance_asset(root,entry,bundle,preflight=preflight)[0]);recount.assert_not_called()
                altered=copy.deepcopy(bundle);altered['result']['extra']='changed'
                with self.assertRaisesRegex(ValueError,'preflight no longer matches'):
                    s.monthly_provenance_asset(root,entry,altered,preflight=preflight)
                with self.assertRaisesRegex(ValueError,'preflight no longer matches'):
                    s.monthly_provenance_asset(root,entry,bundle,preflight={**preflight,'entry_sha256':'0'*64})
                self.assertIsNone(s.monthly_provenance_asset(root,entry,bundle,preflight={**preflight,'status':'pending'}))
                with self.assertRaisesRegex(ValueError,'publisher campaign lock'):
                    s.assets(root,copy.deepcopy(values),monthly_preflight={key:preflight})
            with patch('fireatlas.monthly_source_provenance.capture_for_bundle',return_value={'input_sha256':'d'*64}), \
                 patch('fireatlas.monthly_source_provenance._verify_while_locked') as recount:
                self.assertIsNone(s.monthly_provenance_asset(root,entry,bundle));recount.assert_not_called()
            with patch('fireatlas.monthly_source_provenance.capture_for_bundle',return_value={'input_sha256':'c'*64}), \
                 patch('fireatlas.monthly_source_provenance._verify_while_locked',return_value={**proof,'status':'partial'}):
                with self.assertRaisesRegex(ValueError,'no longer reproduces'):s.monthly_provenance_asset(root,entry,bundle)
            path.write_text('{}')
            with self.assertRaisesRegex(ValueError,'bytes differ'):s.monthly_provenance_asset(root,entry,bundle)

    def test_daily_hybrid_requires_matching_frozen_source_and_recount(self):
        original={'result_sha256':'a'*64,'region':'norcal','versions':['6.03','2'],
                  'inputs':{'region':'norcal'},'platform_counts':{'one':1}}
        experiment={'schema':'fireatlas-daily-hybrid-experiment-v1','region':'norcal','versions':['6.03','2'],
                    'inputs':original['inputs'],'platform_counts':original['platform_counts'],
                    'synthetic':False,'scientific_admission':False,'estimates_admitted':False}
        experiment['result_sha256']=digest(experiment)
        source=gzip.compress(json.dumps(original).encode(),mtime=0)
        bundle={'schema':'fireatlas-daily-hybrid-bundle-v1','original_release_id':'b'*64,
                'original_artifact':'cohort-daily/'+'c'*16+'.json.gz',
                'original_artifact_sha256':hashlib.sha256(source).hexdigest(),
                'original_result_sha256':original['result_sha256'],'experiment':experiment}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);name='daily-hybrid-v1/'+digest(bundle)+'.json.gz'
            path=root/name;path.parent.mkdir();path.write_bytes(gzip.compress(json.dumps(bundle).encode(),mtime=0))
            entry={'artifact':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'result_sha256':experiment['result_sha256']}
            with patch('fireatlas.qualification_publication.read',return_value=source), \
                 patch('fireatlas.daily_hybrid_experiment.verify') as check:
                result=s.daily_hybrid_asset(root,entry,original,root)
                self.assertEqual(bundle,result[0]);check.assert_called_once_with(experiment)
                newer={**original,'result_sha256':'f'*64}
                self.assertIsNone(s.daily_hybrid_asset(root,entry,newer,root))
                with self.assertRaisesRegex(ValueError,'scope'):
                    s.daily_hybrid_asset(root,entry,{**original,'region':'punjab-haryana'},root)
            (root/name).write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'source bytes differ'):
                s.daily_hybrid_asset(root,entry,original,root)
    def test_daily_neighbors_requires_matching_frozen_source_and_recount(self):
        original={'result_sha256':'a'*64,'region':'norcal','versions':['6.03','2'],
                  'inputs':{'region':'norcal'},'platform_counts':{'one':1}}
        experiment={'schema':'fireatlas-daily-neighbors-experiment-v1','region':'norcal','versions':['6.03','2'],
                    'inputs':original['inputs'],'platform_counts':original['platform_counts'],
                    'synthetic':False,'scientific_admission':False,'estimates_admitted':False}
        experiment['result_sha256']=digest(experiment)
        source=gzip.compress(json.dumps(original).encode(),mtime=0)
        bundle={'schema':'fireatlas-daily-neighbors-bundle-v1','original_release_id':'b'*64,
                'original_artifact':'cohort-daily/'+'c'*16+'.json.gz',
                'original_artifact_sha256':hashlib.sha256(source).hexdigest(),
                'original_result_sha256':original['result_sha256'],'experiment':experiment}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);name='daily-neighbors-v1/'+digest(bundle)+'.json.gz'
            path=root/name;path.parent.mkdir();path.write_bytes(gzip.compress(json.dumps(bundle).encode(),mtime=0))
            entry={'artifact':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'result_sha256':experiment['result_sha256']}
            with patch('fireatlas.qualification_publication.read',return_value=source), \
                 patch('fireatlas.daily_neighbors_experiment.verify') as check:
                result=s.daily_neighbors_asset(root,entry,original,root)
                self.assertEqual(bundle,result[0]);check.assert_called_once_with(experiment)
                newer={**original,'result_sha256':'f'*64}
                self.assertIsNone(s.daily_neighbors_asset(root,entry,newer,root))
                with self.assertRaisesRegex(ValueError,'scope'):
                    s.daily_neighbors_asset(root,entry,{**original,'region':'punjab-haryana'},root)
            (root/name).write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'source bytes differ'):
                s.daily_neighbors_asset(root,entry,original,root)
    def test_provenance_receipt_bound_to_recounted_exact_input(self):
        count=count_evidence();identity=count['input_sha256']
        proof={'schema':'fireatlas-transfer-provenance-verification-v1','input_sha256':identity,'status':'verified',
               'original_sources_reopened':True,'scientific_admission':False,'historical_deployment_admitted':False}
        proof['result_sha256']=digest(proof)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'provenance-v1/proof.json';path.parent.mkdir();path.write_text(json.dumps(proof))
            entry={'artifact':'provenance-v1/proof.json','sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'input_sha256':identity}
            with patch.object(s,'current_transfer_capture',return_value={'input_sha256':identity}), \
                 patch('fireatlas.transfer_provenance.verify_capture',return_value=proof) as check:
                self.assertEqual(proof,s.provenance_asset(root,entry,count));check.assert_called_once()
            newer=copy.deepcopy(count);newer['input_sha256']='f'*64
            with patch('fireatlas.transfer_provenance.verify_capture') as check:
                self.assertIsNone(s.provenance_asset(root,entry,newer));check.assert_not_called()
            with patch.object(s,'current_transfer_capture',return_value={'input_sha256':identity}), \
                 patch('fireatlas.transfer_provenance.verify_capture',return_value={**proof,'status':'partial'}),self.assertRaisesRegex(ValueError,'no longer reproduces'):
                s.provenance_asset(root,entry,count)
            path.write_text('{}')
            with self.assertRaisesRegex(ValueError,'bytes differ'):s.provenance_asset(root,entry,count)

    def test_transfer_source_growth_makes_only_the_old_receipt_pending(self):
        from fireatlas import acquisition,transfer,transfer_provenance
        from fireatlas.core import connect
        from tests.test_qualification import HEADER,Response
        from tests.test_transfer_provenance import TransferProvenanceTests
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory);campaign=work/'campaign';campaign.mkdir()
            fixture=TransferProvenanceTests('test_verified_capture_and_idempotent_reimport')
            fixture.setUp();self.addCleanup(fixture.doCleanups);fixture.root=campaign
            old=fixture.populate()
            def evidence(capture):
                return {'inputs':capture,'input_sha256':capture['input_sha256'],'region':capture['region'],
                        'source_cohort':capture['source_cohort'],'target_cohort':capture['target_cohort']}
            def register(capture,name):
                proof=transfer_provenance.verify_capture(capture,campaign/'observations.sqlite3',campaign)
                self.assertEqual('verified',proof['status'])
                path=work/'provenance-v1'/name;path.parent.mkdir(exist_ok=True)
                path.write_text(json.dumps(proof))
                return {'artifact':str(path.relative_to(work)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                        'input_sha256':capture['input_sha256']}
            entry=register(old,'old.json');self.assertEqual('verified',s.provenance_asset(work,entry,evidence(old))['status'])
            original=next((campaign/'requests').glob('*.csv'));body=original.read_bytes()
            original.write_bytes(body+b'corrupt')
            with self.assertRaises(ValueError):s.provenance_asset(work,entry,evidence(old))
            original.write_bytes(body)
            plan=acquisition.plan('norcal',['2012-03'],['MODIS_SP'],fixture.discovery)
            row='40,-121,2012-03-01,1200,T,MODIS,90,6.03,1,1,2,D\n'
            calls=iter([HEADER+row]+[HEADER]*(len(plan['requests'])-1))
            with patch.object(acquisition,'firms_key',return_value='fixture'),patch.object(acquisition.time,'sleep'):
                acquisition.acquire(campaign,plan,opener=lambda *a,**k:Response(next(calls).encode()))
            acquisition.import_month(campaign,plan,'MODIS_SP','2012-03')
            self.assertIsNone(s.provenance_asset(work,entry,evidence(old)))
            with connect(campaign/'observations.sqlite3') as db:
                fresh=transfer.capture(db,'norcal',*fixture.cohorts)
            self.assertNotEqual(old['input_sha256'],fresh['input_sha256'])
            new_entry=register(fresh,'fresh.json')
            self.assertEqual('verified',s.provenance_asset(work,new_entry,evidence(fresh))['status'])
    def test_partial_pilot_adds_missing_cells_to_unknown_not_no_pass(self):
        campaign=review.campaign([pilot_frame()]);summary=s.footprint_summary([campaign],'grove-2025')
        self.assertFalse(summary['scope_complete']);self.assertFalse(summary['validated_observation_opportunity']);self.assertFalse(summary['no_pass_enabled'])
        for row in summary['cohorts'][0]['days']:
            self.assertEqual(648,row['expected_cells']);self.assertEqual(648,row['unknown_cells']);self.assertEqual(0,row['usable_cells'])
        self.assertEqual(1,summary['cohorts'][0]['days'][0]['represented_cells'])
        self.assertEqual(0,summary['cohorts'][0]['days'][1]['represented_cells'])
    def test_disjoint_parts_aggregate_but_overlaps_and_foreign_scope_fail(self):
        a=review.campaign([pilot_frame()]);b=review.campaign([pilot_frame(x_offset=1)])
        self.assertEqual(2,s.footprint_summary([a,b],'grove-2025')['cohorts'][0]['days'][0]['represented_cells'])
        with self.assertRaisesRegex(ValueError,'Overlapping'):s.footprint_summary([a,a],'grove-2025')
        with self.assertRaisesRegex(ValueError,'scope'):s.footprint_summary([a],'park-2024')
        a['synthetic']=True
        with self.assertRaisesRegex(ValueError,'synthetic'):s.footprint_summary([a],'grove-2025')
    def test_registered_original_gzip_bytes_retained_and_tamper_fails(self):
        campaign=review.campaign([pilot_frame()])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);entry=write(root,'opportunity-v2/part.json.gz',campaign)
            index={'schema':'fireatlas-successor-evidence-index-v1','footprints':{'grove-2025':[entry]},'transfers':{}}
            (root/'successor-evidence.json').write_text(json.dumps(index));out=s.assets(root,{})
            name=out['footprint-summary/grove-2025.json']['parts'][0]['artifact']
            self.assertIsInstance(out[name],s.FrozenFile);self.assertEqual(entry['sha256'],out[name].sha256)
            self.assertEqual('not-acquired',out['footprint-summary/park-2024.json']['state'])
            path=root/entry['artifact'];path.write_bytes(path.read_bytes()+b'x')
            with self.assertRaisesRegex(ValueError,'registered hash'):s.assets(root,{})
    def test_path_traversal_and_duplicate_parts_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ('../foreign.json.gz','/tmp/foreign.json.gz','transfer-opportunity-v2/foreign.json.gz'):
                with self.assertRaises(ValueError):s.indexed_path(root,name,prefix='opportunity-v2')
            campaign=review.campaign([pilot_frame()]);entry=write(root,'opportunity-v2/part.json.gz',campaign)
            (root/'successor-evidence.json').write_text(json.dumps({'schema':'fireatlas-successor-evidence-index-v1','footprints':{'grove-2025':[entry,entry]}}))
            with self.assertRaisesRegex(ValueError,'Duplicate'):s.assets(root,{})
    def test_symlinked_namespace_cannot_escape_counted_root(self):
        with tempfile.TemporaryDirectory() as directory,tempfile.TemporaryDirectory() as foreign:
            root=Path(directory);(root/'opportunity-v2').symlink_to(foreign,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'counted namespace'):
                s.indexed_path(root,'opportunity-v2/part.json.gz',prefix='opportunity-v2')
    def test_changed_source_after_recount_cannot_change_frozen_identity(self):
        campaign=review.campaign([pilot_frame()])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);entry=write(root,'opportunity-v2/part.json.gz',campaign)
            (root/'successor-evidence.json').write_text(json.dumps({'schema':'fireatlas-successor-evidence-index-v1','footprints':{'grove-2025':[entry]}}))
            path=root/entry['artifact'];original=review.verify_campaign
            def mutate_after_verify(*args,**kwargs):
                result=original(*args,**kwargs);path.write_bytes(path.read_bytes()+b'mutated');return result
            with patch.object(review,'verify_campaign',side_effect=mutate_after_verify):out=s.assets(root,{})
            name=out['footprint-summary/grove-2025.json']['parts'][0]['artifact']
            self.assertEqual(entry['sha256'],out[name].sha256)
            self.assertNotEqual(s.frozen_file(path).sha256,out[name].sha256)
    def test_transfer_pending_capture_rebases_only_unsigned_empty_review(self):
        count=count_evidence();evaluation=s.transfer_opportunity.build(count)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);entry=write(root,'transfer-opportunity-v2/old.json.gz',evaluation)
            conclusion=s.transfer_opportunity.review_template('conclusions',evaluation['result_sha256'])
            path=root/'transfer-opportunity-v2/conclusion.json.gz';path.write_bytes(gzip.compress(json.dumps(conclusion).encode()))
            entry['conclusions']='transfer-opportunity-v2/conclusion.json.gz'
            (root/'successor-evidence.json').write_text(json.dumps({'schema':'fireatlas-successor-evidence-index-v1','footprints':{},'transfers':{'0'*16:entry}}))
            # Mimic a valid newly recounted count identity through the controlled
            # count-build seam; this checks publication state ownership only.
            newer=copy.deepcopy(count);newer['result_sha256']='f'*64
            with patch.object(s.transfer_opportunity,'build',return_value=evaluation):
                out=s.assets(root,{'cohort-transfer/'+('0'*16)+'.json':newer})
                self.assertIsNone(out['transfer-opportunity/'+('0'*16)+'.json']['conclusions'])
            conclusion.update(human_authored=True,decision='approve')
            path.write_bytes(gzip.compress(json.dumps(conclusion).encode()))
            with patch.object(s.transfer_opportunity,'build',return_value=evaluation),self.assertRaisesRegex(ValueError,'Stale'):
                s.assets(root,{'cohort-transfer/'+('0'*16)+'.json':newer})

if __name__=='__main__':unittest.main()
