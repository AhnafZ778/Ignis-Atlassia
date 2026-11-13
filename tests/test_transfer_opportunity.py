"""Manufactured engineering evidence only; no real reviewers or qualified bridges."""
import copy,gzip,json,tempfile,unittest
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
from calendar import monthrange
from unittest.mock import patch
from fireatlas import transfer as counts,transfer_opportunity as method
from fireatlas.qualification import digest
from tests.test_transfer_coverage import transfer_fixture,rehash
from tests.test_opportunity_frames import fixture as native_fixture
from fireatlas import opportunity_frames,opportunity_review
from tests.test_opportunity_frames import seal


def count_evidence(*,mock_authentic=False):
    value=transfer_fixture()
    if not mock_authentic:return counts.analyze(value,synthetic=True)
    value['synthetic']=False;rehash(value)
    review={'schema':'fireatlas-direct-transfer-review-v1','protocol_sha256':counts.protocol()['protocol_sha256'],
            'scope':'protocol','evidence_sha256':None,'human_authored':True,'automated_agent':False,'decision':'approve',
            'signed_utc':datetime.now(timezone.utc).isoformat(),
            'reviewer':{k:'Explicitly manufactured engineering-only reviewer' for k in ('name','affiliation','qualification','independence_statement')}}
    return counts.analyze(value,review=review)


def approved(scope='protocol',evidence=None):
    review=method.review_template(scope,evidence)
    review.update(human_authored=True,automated_agent=False,decision='approve',signed_utc=datetime.now(timezone.utc).isoformat())
    review['reviewer']={k:'Manufactured fixture, not a scientific signature' for k in review['reviewer']}
    review['attestations']={k:True for k in review['attestations']};review['support_rationale']='Manufactured applicability rationale for engineering gate verification.'
    return review


def packets(evidence,*,unknown=False):
    result=[]
    for row in evidence['inputs']['months']:
        if row['exclusion_reasons']:continue
        month=row['month'];start=date.fromisoformat(month+'-01');end=start.replace(day=monthrange(start.year,start.month)[1])
        cohorts=[evidence['source_cohort'],evidence['target_cohort']];rows=[]
        for day in (start+timedelta(days=i) for i in range((end-start).days+1)):
            for c in cohorts:
                areas={'detected':0.,'observed-without-detection':0. if unknown else 1000.,'cloud':0.,'unusable':0.,'no-pass':0.,'unknown':1000. if unknown else 0.}
                rows.append({'date':day.isoformat(),'cohort':c,'area_m2':1000.,'state_area_m2':areas,
                             'state_area_fraction':{k:v/1000. for k,v in areas.items()},'spatially_complete':True,
                             'expected_cells':1,'represented_cells':1,'missing_area_m2':0.,'acquisition_groups':1,'candidate_granules':2})
        report={'schema':'fireatlas-regional-opportunity-report-v2','region':evidence['region'],'cohorts':cohorts,
                'start':start.isoformat(),'end':end.isoformat(),'daily_support':rows,'validated_opportunity':True,'spatial_temporal_complete':True}
        report['result_sha256']=digest(report)
        result.append({'campaign':{'synthetic':evidence['synthetic'],'result_sha256':digest(month)},'report':report})
    return result


def frozen_protocol():
    value=method.protocol();value['state']='frozen-proposal-awaiting-human-approval';return value


class TransferOpportunityTests(unittest.TestCase):
    def test_missing_reports_stay_closed_with_exact_whole_month_support(self):
        evidence=count_evidence();value=method.build(evidence)
        self.assertTrue(method.verify(value)['verified']);self.assertFalse(value['ready_for_conclusions'])
        support=value['opportunity_support'];expected=len(method.required_dates(evidence))*2
        self.assertEqual(96,support['required_months']);self.assertEqual(expected,len(support['missing']))
        self.assertIn('2012-02-29',{r['date'] for r in support['missing']})
        self.assertFalse(value['historical_extrapolation_admitted']);self.assertFalse(value['forecasting_admitted'])
    def test_real_packet_mismatched_pilot_region_cannot_qualify(self):
        frame=opportunity_frames.evaluate(native_fixture());campaign=opportunity_review.campaign([frame])
        evidence=count_evidence()
        packet={'campaign':campaign,'report':{'schema':'fireatlas-regional-opportunity-report-v2','region':'grove-2025',
                'cohorts':[evidence['source_cohort'],evidence['target_cohort']]}}
        with self.assertRaisesRegex(ValueError,'region'):method.build(evidence,[packet])
    def test_report_recount_and_scope_reject_summaries_without_campaigns(self):
        evidence=count_evidence();packet=packets(evidence)[0]
        with self.assertRaises(ValueError):method.build(evidence,[{'report':packet['report']}])
        for change in ('cohort','region','synthetic'):
            value=copy.deepcopy(packet)
            if change=='cohort':value['report']['cohorts'].reverse()
            elif change=='region':value['report']['region']='punjab-haryana'
            else:value['campaign']['synthetic']=False
            with self.subTest(change=change),self.assertRaises(ValueError):method.build(evidence,[value])
        with patch.object(opportunity_review,'regional_report',return_value={**packet['report'],'validated_opportunity':False}):
            with self.assertRaisesRegex(ValueError,'recount'):method.build(evidence,[packet])
    def test_mocked_full_support_needs_independent_approvals_then_bound_conclusion(self):
        evidence=count_evidence(mock_authentic=True);p=frozen_protocol();data=packets(evidence)
        report=lambda campaign,region,start,end,cohorts,**kw:next(x['report'] for x in data if x['report']['start']==start)
        def native_support(campaign,first,last,scope_id,cohorts):
            season=next(k for k,v in method.SEASONS.items() if int(first[5:7]) in v)
            return {(digest(c),platform,season):{'sampled_area_m2':1000.,'known_area_m2':1000.,'usable_area_m2':1000.,'groups':{first+platform},'known_groups':{first+platform},'geometry_failure_groups':set()} for c in cohorts for platform in counts.PLATFORMS[c['source']]}
        with patch.object(method,'protocol',return_value=p),patch.object(opportunity_review,'regional_report',side_effect=report),patch.object(method,'platform_samples',side_effect=native_support):
            protocol_review=approved();value=method.build(evidence,iter(data),protocol_review=protocol_review)
            self.assertTrue(value['ready_for_conclusions']);self.assertFalse(value['admitted'])
            conclusion=approved('conclusions',value['result_sha256'])
            admitted=method.admission(value,conclusion,iter(data));self.assertTrue(admitted['admitted'])
            self.assertEqual(96,len(admitted['permitted_months']));self.assertFalse(admitted['historical_extrapolation_admitted'])
            conclusion['automated_agent']=True
            self.assertFalse(method.admission(value,conclusion,iter(data))['admitted'])
            protocol_review['automated_agent']=True
            self.assertFalse(method.build(evidence,iter(data),protocol_review=protocol_review)['ready_for_conclusions'])
            protocol_review['automated_agent']=False
            with patch.object(method,'platform_samples',return_value={}):
                missing=method.build(evidence,iter(data),protocol_review=protocol_review)
                self.assertFalse(missing['ready_for_conclusions']);self.assertFalse(missing['opportunity_support']['checks']['platform_season_support'])
            def omit_aqua(*args):return {k:v for k,v in native_support(*args).items() if k[1]!='Aqua'}
            with patch.object(method,'platform_samples',side_effect=omit_aqua):
                missing=method.build(evidence,iter(data),protocol_review=protocol_review)
                self.assertFalse(missing['ready_for_conclusions'])
                self.assertEqual(4,len([r for r in missing['opportunity_support']['platform_acquisition_support'] if r['platform']=='Aqua' and r['known_area_m2']==0]))
    def test_all_unknown_missing_days_duplicate_and_out_of_scope_reports(self):
        evidence=count_evidence();data=packets(evidence,unknown=True)
        report=lambda campaign,region,start,end,cohorts,**kw:next(x['report'] for x in data if x['report']['start']==start)
        with patch.object(opportunity_review,'regional_report',side_effect=report):
            value=method.build(evidence,iter(data));self.assertFalse(value['opportunity_support']['checks']['all_seasons_have_known_and_usable_support'])
            self.assertFalse(value['ready_for_conclusions'])
            value=method.build(evidence,iter(data[:-1]));self.assertTrue(value['opportunity_support']['missing'])
            with self.assertRaisesRegex(ValueError,'Duplicate'):method.build(evidence,iter([data[0],data[0]]))
            changed=copy.deepcopy(data[0]);changed['report']['daily_support'][0]['date']='2030-01-01'
            with patch.object(opportunity_review,'regional_report',return_value=changed['report']):
                with self.assertRaisesRegex(ValueError,'outside'):method.build(evidence,[changed])
    def test_resealed_manual_flags_and_metrics_do_not_survive_verify(self):
        value=method.build(count_evidence());value['checks']['regional_opportunity_evaluated']=True;value['ready_for_conclusions']=True
        value['result_sha256']=digest({k:v for k,v in value.items() if k!='result_sha256'})
        with self.assertRaisesRegex(ValueError,'recount'):method.verify(value)
    def test_human_and_scope_claims_cannot_be_replaced_by_a_signature(self):
        with patch.object(method,'protocol',return_value=frozen_protocol()):
            value=approved('conclusions','a'*64)
            for change in ('rationale','attestation','binding','date'):
                altered=copy.deepcopy(value)
                if change=='rationale':altered['support_rationale']=''
                elif change=='attestation':altered['attestations']['unknown_support']=False
                elif change=='binding':altered['evidence_sha256']='b'*64
                else:altered['signed_utc']='2126-01-01T00:00:00Z'
                with self.subTest(change=change):self.assertFalse(method.review_state(altered,'conclusions','a'*64)['approved'])
    def test_platform_geometry_failures_and_companions_remain_explicit(self):
        native=native_fixture();native['pixels']=[];native['native_files']=[];native['geometry_artifacts']=[]
        page=native['inventory']['products'][0]['pages'][0];body=json.loads(page['source_utf8'])
        body['feed']['entry'][0].pop('boxes');page['source_utf8']=json.dumps(body)
        import hashlib
        page['sha256']=hashlib.sha256(page['source_utf8'].encode()).hexdigest()
        frame=opportunity_frames.evaluate(seal(native));campaign=opportunity_review.campaign([frame])
        support=method.platform_samples(campaign,native['start'],native['end'],native['scope_id'],[native['cohort']])
        row=next(iter(support.values()));self.assertEqual(1,len(row['geometry_failure_groups']))
        self.assertEqual(1,len(row['groups']));self.assertEqual(0,row['known_area_m2']);self.assertEqual(0,row['usable_area_m2'])
    def test_platform_native_area_requires_review_and_deduplicates_fragments(self):
        frame=opportunity_frames.evaluate(native_fixture());campaign=opportunity_review.campaign([frame])
        raw=method.platform_samples(campaign,frame['start'],frame['end'],frame['scope']['id'],[frame['cohort']]);row=next(iter(raw.values()))
        self.assertEqual(1,len(row['groups']));self.assertEqual(0,row['known_area_m2'])
        # Manufactured review bit only exercises this helper; campaign recount
        # and final admission would reject it. No scientific approval implied.
        campaign['validated_observation_opportunity']=True
        campaign['frames'][0]['acquisitions'].append(copy.deepcopy(campaign['frames'][0]['acquisitions'][0]))
        row=next(iter(method.platform_samples(campaign,frame['start'],frame['end'],frame['scope']['id'],[frame['cohort']]).values()))
        self.assertAlmostEqual(1_000_000,row['sampled_area_m2']);self.assertAlmostEqual(1_000_000,row['usable_area_m2'])
        self.assertEqual(1,len(row['known_groups']))

    def test_platform_pilot_and_other_cohort_support_cannot_leak_into_region(self):
        frame=opportunity_frames.evaluate(native_fixture());campaign=opportunity_review.campaign([frame])
        self.assertEqual({},method.platform_samples(campaign,frame['start'],frame['end'],'norcal',[frame['cohort']]))
        self.assertEqual({},method.platform_samples(campaign,frame['start'],frame['end'],frame['scope']['id'],[{'source':'VIIRS_SNPP_SP','version':'other'}]))

    def test_cli_generated_compressed_review_roundtrips_evaluate_and_admit(self):
        from scripts import transfer_opportunity_pipeline as cli
        from scripts.native_context_pipeline import load
        import contextlib,io
        with tempfile.TemporaryDirectory() as td,patch.object(cli,'ROOT',Path(td)),contextlib.redirect_stdout(io.StringIO()):
            work=Path(td)/'data/qualification';work.mkdir(parents=True)
            counts_path=work/'synthetic-counts.json';counts_path.write_text(json.dumps(count_evidence()))
            protocol_review=work/'protocol-review.json.gz';evaluation=work/'evaluation.json.gz'
            conclusion=work/'conclusion.json.gz';admission=work/'admission.json.gz'
            calls=[['review-template','--output',str(protocol_review)],
                ['evaluate','--evidence',str(counts_path),'--protocol-review',str(protocol_review),'--output',str(evaluation)]]
            for args in calls:
                with patch('sys.argv',['transfer_opportunity_pipeline',*args]):cli.main()
            value=load(evaluation)
            with patch('sys.argv',['transfer_opportunity_pipeline','review-template','--scope','conclusions','--evidence-sha256',value['result_sha256'],'--output',str(conclusion)]):cli.main()
            with patch('sys.argv',['transfer_opportunity_pipeline','admit','--evidence',str(evaluation),'--conclusions',str(conclusion),'--output',str(admission)]):cli.main()
            self.assertFalse(load(admission)['admitted']);self.assertEqual('pending',load(conclusion)['decision'])

    def test_packet_index_is_streamed_and_rejects_paths_and_duplicates(self):
        from scripts.transfer_opportunity_pipeline import packet_stream
        with tempfile.TemporaryDirectory() as td:
            work=Path(td);packet=work/'packet.gz';packet.write_bytes(gzip.compress(json.dumps({'packet':'synthetic'}).encode()))
            index=work/'index.json';index.write_text(json.dumps({'schema':'fireatlas-transfer-opportunity-packet-index-v1','files':['packet.gz']}))
            self.assertEqual([{'packet':'synthetic'}],list(packet_stream(index,work)))
            for files in [['../outside.gz'],['packet.gz','packet.gz'],[str(packet.resolve())]]:
                index.write_text(json.dumps({'schema':'fireatlas-transfer-opportunity-packet-index-v1','files':files}))
                with self.assertRaises(ValueError):list(packet_stream(index,work))

if __name__=='__main__':unittest.main()
