"""Human-owned method/conclusion and formative task-study release gates."""
from __future__ import annotations
from .qualification import approval,digest
from .comparability_v2 import verify
from .mask_review import validate_review, REQUIRED_SAMPLES
from datetime import datetime,timezone
import math

TASKS=('compare_raw_adjusted','interpret_selected_example','identify_unsupported_month','distinguish_estimate_observation','reproduce_download')


def task_study_template(release_sha256):
    return {'schema':'fireatlas-scientist-task-study-v1','release_sha256':release_sha256,'human_observed':False,
            'observer':'','signed_utc':None,'participants':[{'participant_id':str(i),'qualification':'','without_guidance':None,
                'elapsed_seconds':None,'tasks':{t:None for t in TASKS},'critical_misunderstandings':[],'notes':''} for i in range(1,6)]}


def task_study_check(study,release_sha256):
    if not isinstance(study,dict):return {'passed':False,'reason':'task-study-missing'}
    people=study.get('participants');base=study.get('schema')=='fireatlas-scientist-task-study-v1' and study.get('release_sha256')==release_sha256 and study.get('human_observed') is True and bool(study.get('observer')) and bool(study.get('signed_utc'))
    if not isinstance(people,list) or len(people)!=5:return {'passed':False,'reason':'five-qualified-participants-required'}
    if not all(isinstance(p,dict) for p in people):return {'passed':False,'reason':'invalid-participant-record'}
    try:
        stamp=datetime.fromisoformat(study.get('signed_utc','').replace('Z','+00:00'))
        base=base and stamp.tzinfo is not None and stamp.utcoffset().total_seconds()==0 and stamp<=datetime.now(timezone.utc)
    except (ValueError,TypeError,AttributeError):base=False
    identities=[p.get('participant_id') for p in people]
    if not all(isinstance(x,str) for x in identities):return {'passed':False,'reason':'invalid-participant-identity'}
    if len(set(identities))!=5 or any(not x for x in identities):return {'passed':False,'reason':'unique-participants-required'}
    successes=0;critical=[]
    for p in people:
        if not isinstance(p.get('critical_misunderstandings'),list) or not p.get('qualification') or p.get('without_guidance') is not True:base=False
        critical+=p.get('critical_misunderstandings',[]) if isinstance(p.get('critical_misunderstandings'),list) else ['invalid-record']
        seconds=p.get('elapsed_seconds');tasks=p.get('tasks',{})
        if not isinstance(tasks,dict):base=False;continue
        successes+=type(seconds) in (int,float) and 0<seconds<=300 and all(tasks.get(t) is True for t in TASKS)
    return {'passed':bool(base and successes>=4 and not critical),'completed_within_five_minutes':successes,'participants':5,
            'critical_misunderstandings':critical,'study_sha256':digest(study),'scope':'Formative usability only; not universal usability evidence.'}


def monthly_release_gate(bundle,conclusion_review=None,native_reviews=None,study=None,*,native_evidence=None):
    verify(bundle);r=bundle['result'];result_hash=r['result_sha256']
    protocol_ok=approval(r.get('review'))['approved']
    conclusion=approval(conclusion_review,scope='conclusions',evidence_sha256=result_hash)
    reviews=native_reviews or {};natives={}
    for case in ('park-2024','grove-2025'):
        try:
            evidence=native_evidence[case] if native_evidence is not None else __import__('fireatlas.masks',fromlist=['read_evidence']).read_evidence(case)
            summary=validate_review(reviews.get(case,{}),evidence)
            contradictions=[]
            for sample in summary['samples']:
                if sample['outcome']!='agree':continue
                source=next(s for s in reviews[case]['samples'] if (s['producer_id'],s['line'],s['sample'])==(sample['producer_id'],sample['line'],sample['sample']))
                if sample['observed_mask_class']!=source['expected_mask_class'] or any(sample['observed_'+k]!=source['expected_'+k] for k in ('grid_x','grid_y')) or any(not math.isclose(sample['observed_'+k],source['expected_'+k],rel_tol=0,abs_tol=1e-6) for k in ('lat','lon')):
                    contradictions.append({'producer_id':sample['producer_id'],'line':sample['line'],'sample':sample['sample'],'reason':'agree-contradicts-observed-native-values'})
            stamp=datetime.fromisoformat(summary['reviewer']['reviewed_utc'].replace('Z','+00:00'))
            valid_time=stamp.tzinfo is not None and stamp.utcoffset().total_seconds()==0 and stamp<=datetime.now(timezone.utc)
            natives[case]={**summary,'review_sha256':digest(reviews[case]),'contradictory_agreements':contradictions,'valid_review_time':valid_time}
        except (ValueError,KeyError,TypeError,AttributeError):
            natives[case]={'status':'missing-or-invalid-human-review','independent_signoff':False}
    native_ok=all(v.get('status')=='complete' and v.get('reviewed_samples',0)>=REQUIRED_SAMPLES and v.get('independent_signoff') is True and v.get('disagreements')==0 and not v.get('contradictory_agreements') and v.get('valid_review_time') is True for v in natives.values())
    task=task_study_check(study,result_hash)
    checks={'authentic':r.get('synthetic') is False,'not_ai_experimental':r.get('experimental_review') is None,'protocol_approved':protocol_ok,'performance_qualified':r['performance_pass'],
            'conclusions_approved':conclusion['approved'],'native_processing_reviewed':native_ok,'formative_task_study':task['passed']}
    return {'schema':'fireatlas-monthly-release-admission-v1','result_sha256':result_hash,'checks':checks,'monthly_product_admitted':all(checks.values()),
            'daily_reconstruction':False,'historical_transfer':False,'prospective_monitoring':False,
            'task_study':task,'conclusion_review':conclusion,'native_review_checks':natives,
            'interpretation':'A human attestation is imported evidence; the owner remains responsible for verifying reviewer identity and signatures.'}


def daily_release_gate(result,conclusion_review=None,monthly_prerequisite=None):
    from .daily_estimates import verify as verify_daily
    verify_daily(result)
    conclusion=approval(conclusion_review,'daily',scope='conclusions',evidence_sha256=result['result_sha256'])
    checks={'authentic':result.get('synthetic') is False,'not_ai_experimental':result.get('experimental_review') is None,'protocol_approved':approval(result.get('review'),'daily')['approved'],
            'performance_qualified':result.get('performance_pass') is True,'three_supported_test_years':len(result.get('folds',[]))>=3,
            'conclusions_approved':conclusion['approved'],
            'monthly_milestone':isinstance(monthly_prerequisite,dict) and monthly_prerequisite.get('monthly_product_admitted') is True}
    return {'schema':'fireatlas-daily-release-admission-v1','region':result['region'],'result_sha256':result['result_sha256'],
            'checks':checks,'daily_estimates_admitted':all(checks.values()),'conclusion_review':conclusion,
            'historical_transfer':False,'prospective_monitoring':False,'units':'expected observed S-NPP centroid cell-days',
            'interpretation':'Daily qualification is separate from monthly qualification; expected counts and intervals never become observed detection locations.'}
