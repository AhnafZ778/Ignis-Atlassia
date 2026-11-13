"""Direct collection/platform transfer registry; no implicit factor chaining.

This registry never turns a smoothly joined curve into scientific acceptance.
Every bridge needs a separately approved hash-bound evaluation and conclusion.
"""
from __future__ import annotations
from datetime import date,datetime,timezone
import re
from .qualification import digest
from .core import SOURCES


def bridge_template(region,source_cohort,target_cohort):
    return {'schema':'fireatlas-direct-transfer-review-v1','region':region,'source_cohort':source_cohort,'target_cohort':target_cohort,
            'direct_evidence_sha256':None,'protocol_sha256':None,'evidence_type':'direct-observed-overlap','performance_pass':False,
            'backward_transfer_evaluated':False,'seasonal_evaluated':False,'platform_composition_evaluated':False,'opportunity_change_evaluated':False,
            'scope':'conclusions','evidence_sha256':None,'automated_agent':None,'decision':'pending','human_authored':False,'reviewer':{'name':'','affiliation':'','qualification':'','independence_statement':''},'signed_utc':None,
            'limitations':[],'permitted_period':None}


def direct_bridge_check(review,evidence,approved_protocol):
    """Recount direct experiments; signatures cannot replace numerical evidence."""
    from .transfer import verify,protocol,review_state
    checks={k:False for k in ('direct_evidence','approved_protocol','review_identity','performance','backward_transfer','seasonal','platform_composition','opportunity_change')}
    if not all(isinstance(v,dict) for v in (review,evidence,approved_protocol)):return {'admitted':False,'checks':checks}
    try:
        verify(evidence)
        frozen=protocol();p=approved_protocol.get('protocol',{});attestation=approved_protocol.get('review')
        checks['approved_protocol']=digest(p)==digest(frozen) and review_state(attestation)['approved']
        checks['direct_evidence']=evidence.get('synthetic') is False and evidence.get('evidence_type')=='direct-observed-overlap' and evidence.get('factor_chain')==[]
        checks['review_identity']=review_state(review,scope='conclusions',evidence_sha256=evidence['result_sha256'])['approved'] and all(review.get(k)==evidence.get(k) for k in ('region','source_cohort','target_cohort'))
        checks['performance']=evidence.get('performance_pass') is True and evidence.get('experimental_review') is None
        backward=evidence['evaluation']['backward']
        checks['backward_transfer']=backward['performance_pass'] and len(backward['folds'])>=frozen['partition']['test_groups']
        checks['seasonal']=all(all(v['n_months']>0 and v['weighted_absolute_percentage_error'] is not None for v in ev['seasonal'].values()) for ev in evidence['evaluation'].values())
        checks['platform_composition']=all(ev['platform_compositions'] and all(v['n_months']>=frozen['partition']['test_months'] for v in ev['platform_compositions'].values()) for ev in evidence['evaluation'].values())
        # Count-only source records do not contain validated observation geometry.
        # A transfer cannot inherit this evidence from monthly qualification.
        checks['opportunity_change']=evidence.get('opportunity_change_evaluated') is True
    except (ValueError,KeyError,TypeError,AttributeError):
        return {'schema':'fireatlas-direct-transfer-admission-v1','admitted':False,'checks':checks,'reason':'Missing or invalid frozen protocol, direct evidence recount or review.'}
    return {'schema':'fireatlas-direct-transfer-admission-v1','admitted':all(checks.values()),'checks':checks,
            'evidence_sha256':evidence['result_sha256'],
            'reason':'Separate direct-transfer checks; AI exploration cannot qualify a historical bridge.',
            'unresolved':[key for key,passed in checks.items() if not passed]}


def historical_record(observations,estimates,admitted_bridges):
    """Keep estimates separate and reject unqualified collection/platform moves."""
    if not isinstance(observations,list) or not isinstance(estimates,list):raise ValueError('Explicit observation and estimate records required.')
    known=set()
    for row in observations:
        if row.get('kind')!='observation' or row.get('date') in known:raise ValueError('Unique dated original observations required.')
        date.fromisoformat(row['date']);known.add(row['date'])
    for row in estimates:
        bridge=admitted_bridges.get(row.get('bridge_sha256'),{})
        if row.get('kind')!='counterfactual-estimate' or bridge.get('admitted') is not True:raise ValueError('Unqualified historical transfer; no estimate admitted.')
        if row.get('date') in known:raise ValueError('An estimate cannot overwrite an observation.')
        if not row.get('interval') or not row.get('model_sha256') or not row.get('input_sha256'):raise ValueError('Historical estimate identity and uncertainty required.')
    return {'schema':'fireatlas-historical-record-v2','observations':observations,'estimates':estimates,
            'continuous_claim':False,'interpretation':'Pre-VIIRS values are counterfactual estimates, never historical VIIRS measurements; unsupported intervals remain missing.'}


def future_reservation(start,end,latest_inspected):
    first,last=date.fromisoformat(start),date.fromisoformat(end)
    if first<=datetime.now(timezone.utc).date() or last<first or date.fromisoformat(latest_inspected)>=first:raise ValueError('A genuinely future untouched evaluation period is required.')
    result={'schema':'fireatlas-future-evaluation-reservation-v1','start_utc':start,'end_utc':end,'latest_inspected_utc_date':latest_inspected,
            'reserved_utc':datetime.now(timezone.utc).isoformat(),'prospective_monitoring_admitted':False,
            'status':'declared-reservation-requires-protocol-and-access-audit','interpretation':'A declared reservation is not evidence of completed prospective evaluation or enforced blinding.'}
    result['reservation_sha256']=digest(result);return result
