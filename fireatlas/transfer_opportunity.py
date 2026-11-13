"""Recounted direct-transfer admission with regional native opportunity evidence.

This successor wraps the frozen count experiment, rather than changing its
algorithms or treating a manually supplied opportunity flag as evidence.
"""
from __future__ import annotations
from calendar import monthrange
from collections import defaultdict
from datetime import date,datetime,timedelta,timezone
import hashlib,json
from pathlib import Path
from . import transfer,opportunity_review
from .qualification import digest

ROOT=Path(__file__).resolve().parents[1]
MAX_PACKETS=12_400
MAX_SUPPORT_ROWS=25_000
MAX_NATIVE_SAMPLES=2_000_000
MAX_PLATFORM_GROUPS=500_000
SEASONS={'DJF':(12,1,2),'MAM':(3,4,5),'JJA':(6,7,8),'SON':(9,10,11)}
NATIVE_PLATFORMS={p:platform for platform,products in {
    'Terra':('MOD14','MOD03'),'Aqua':('MYD14','MYD03'),'S-NPP':('VNP14IMG','VNP03IMG'),
    'NOAA-20':('VJ114IMG','VJ103IMG'),'NOAA-21':('VJ214IMG','VJ203IMG')}.items() for p in products}


def protocol():
    value=json.loads((ROOT/'fireatlas/protocols/direct-transfer-opportunity-v2.0.0.json').read_text())
    for name,expected in value['source_sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('Transfer opportunity method differs from its frozen proposal; create a successor.')
    return {**value,'protocol_sha256':digest(value)}


def review_template(scope='protocol',evidence_sha256=None):
    if scope not in ('protocol','conclusions'):raise ValueError('Explicit protocol or conclusions review scope required.')
    return {'schema':'fireatlas-transfer-opportunity-review-v2','protocol_sha256':protocol()['protocol_sha256'],
        'scope':scope,'evidence_sha256':evidence_sha256,'decision':'pending','human_authored':False,'automated_agent':None,
        'reviewer':{k:'' for k in ('name','affiliation','qualification','independence_statement')},'signed_utc':None,
        'attestations':{k:False for k in ('target_and_partitions','opportunity_changes','unknown_support','seasons_and_platforms','permitted_claims')},
        'support_rationale':'','limitations':[]}


def review_state(review,scope,evidence_sha256=None):
    if not isinstance(review,dict):return {'approved':False,'reason':'independent-human-review-missing'}
    person=review.get('reviewer');stamp=None
    try:
        stamp=datetime.fromisoformat(review.get('signed_utc','').replace('Z','+00:00'))
        valid_time=stamp.tzinfo is not None and stamp.utcoffset().total_seconds()==0 and stamp<=datetime.now(timezone.utc)
    except (ValueError,TypeError,AttributeError):valid_time=False
    checks={'binding':review.get('schema')=='fireatlas-transfer-opportunity-review-v2'
            and review.get('protocol_sha256')==protocol()['protocol_sha256'] and review.get('scope')==scope
            and review.get('evidence_sha256')==evidence_sha256,
        'human_identity':review.get('human_authored') is True and review.get('automated_agent') is False
            and isinstance(person,dict) and all(isinstance(person.get(k),str) and person[k].strip()
                for k in ('name','affiliation','qualification','independence_statement')),
        'signed_decision':review.get('decision')=='approve' and valid_time}
    if scope=='conclusions':
        checks['applicability']=isinstance(review.get('attestations'),dict) and all(review['attestations'].get(k) is True
            for k in ('target_and_partitions','opportunity_changes','unknown_support','seasons_and_platforms','permitted_claims'))
        checks['rationale']=isinstance(review.get('support_rationale'),str) and bool(review['support_rationale'].strip())
    return {'approved':all(checks.values()),'checks':checks,'review_sha256':digest(review),'owner_must_verify_identity':True}


def required_dates(evidence):
    """Every eligible complete month, not only dates chosen for a chart/test fold."""
    result=[]
    for row in evidence['inputs']['months']:
        if row['exclusion_reasons']:continue
        start=date.fromisoformat(row['month']+'-01')
        result.extend((start+timedelta(days=i)).isoformat() for i in range(monthrange(start.year,start.month)[1]))
    if len(result)>MAX_SUPPORT_ROWS//2 or len(set(result))!=len(result):
        raise ValueError('Transfer opportunity required dates exceed bound or repeat.')
    return sorted(result)


def platform_samples(campaign,first,last,scope_id,cohorts):
    """Native acquisition-cell support, kept distinct from daily ROI fractions.

    Companion/mask fragments of the same platform/start group and cell are
    combined before summing area. These are descriptive dependent samples,
    never independent-cell confidence bounds or validated complete passes.
    """
    samples={};failures=defaultdict(set);allowed={digest(c) for c in cohorts}
    for frame in campaign.get('frames',[]):
        if frame['scope']['id']!=scope_id or digest(frame['cohort']) not in allowed:continue
        key=digest(frame['cohort']);native=opportunity_review.frames.inventory(frame['inputs'])
        for producer in frame['geometry_failures']:
            g=native[producer];platform=NATIVE_PLATFORMS[g['product']]
            for day in opportunity_review.frames.dates(max(first,frame['start']),min(last,frame['end'])) if max(first,frame['start'])<=min(last,frame['end']) else []:
                if g['start_utc'][:10]<=day<=g['end_utc'][:10]:
                    season=next(k for k,v in SEASONS.items() if int(day[5:7]) in v)
                    failures[(key,platform,season)].add(g['acquisition_group_id'])
        for g in frame['acquisitions']:
            platform=NATIVE_PLATFORMS[g['product']]
            lo=max(first,frame['start'],g['start_utc'][:10]);hi=min(last,frame['end'],g['end_utc'][:10])
            if lo>hi:continue
            for day in opportunity_review.frames.dates(lo,hi):
                season=next(k for k,v in SEASONS.items() if int(day[5:7]) in v)
                for row in g['rows']:
                    identity=(key,platform,season,day,g['acquisition_group_id'],row['grid_x'],row['grid_y'])
                    if identity not in samples and len(samples)>=MAX_NATIVE_SAMPLES:
                        raise ValueError('Native acquisition-cell platform samples exceed bound; subdivide reports.')
                    sample=samples.setdefault(identity,{'area':row['area_m2'],'states':set(),'reviewed':campaign['validated_observation_opportunity']})
                    if sample['area']!=row['area_m2']:raise ValueError('Acquisition-cell area differs across native fragments.')
                    sample['states'].add(row['geometric_state'])
    result=defaultdict(lambda:{'sampled_area_m2':0.,'known_area_m2':0.,'usable_area_m2':0.,'groups':set(),'known_groups':set()})
    for identity,sample in samples.items():
        key,platform,season,day,group,_,_=identity;states=sample['states']
        state=('detected' if 'detected' in states else 'observed-without-detection' if 'observed-without-detection' in states
               else next(iter(states)) if len(states)==1 else 'unknown')
        row=result[(key,platform,season)];row['sampled_area_m2']+=sample['area'];row['groups'].add(group)
        if sample['reviewed'] and state!='unknown':
            row['known_area_m2']+=sample['area'];row['known_groups'].add(group)
            if state in ('detected','observed-without-detection'):row['usable_area_m2']+=sample['area']
    for key,groups in failures.items():result[key]['groups'].update(groups)
    return {key:{**row,'geometry_failure_groups':failures[key]} for key,row in result.items()}


def opportunity_support(evidence,packets,*,original_directory=None):
    """Stream and recount packets; reports without their campaigns are rejected."""
    required=set(required_dates(evidence));cohorts=[evidence['source_cohort'],evidence['target_cohort']]
    cohort_keys=[digest(c) for c in cohorts];observed={};dependencies=[];seen_reports=set();seen_packets=set();platforms={}
    for index,packet in enumerate(packets):
        if index>=MAX_PACKETS:raise ValueError('Transfer opportunity packet count exceeds bounded history.')
        if not isinstance(packet,dict) or set(packet)!={'campaign','report'}:
            raise ValueError('Each opportunity report requires its exact source campaign.')
        campaign,report=packet['campaign'],packet['report']
        identity=digest(packet)
        if identity in seen_packets:raise ValueError('Duplicate opportunity packet.')
        seen_packets.add(identity)
        if (report.get('region')!=evidence['region'] or report.get('cohorts')!=cohorts
                or report.get('schema')!='fireatlas-regional-opportunity-report-v2'):
            raise ValueError('Opportunity region or exact ordered transfer cohorts differ.')
        if campaign.get('synthetic') is not evidence['synthetic']:
            raise ValueError('Authentic and synthetic transfer/opportunity evidence cannot mix.')
        rebuilt=opportunity_review.regional_report(campaign,evidence['region'],report['start'],report['end'],cohorts,
                                                 original_directory=original_directory)
        if digest(rebuilt)!=digest(report):raise ValueError('Regional opportunity report recount differs.')
        if report['result_sha256'] in seen_reports:raise ValueError('Repeated regional report.')
        seen_reports.add(report['result_sha256'])
        for key,row in platform_samples(campaign,report['start'],report['end'],evidence['region'],cohorts).items():
            aggregate=platforms.setdefault(key,{'sampled_area_m2':0.,'known_area_m2':0.,'usable_area_m2':0.,'groups':set(),'known_groups':set(),'geometry_failure_groups':set()})
            for field in ('sampled_area_m2','known_area_m2','usable_area_m2'):aggregate[field]+=row[field]
            for field in ('groups','known_groups','geometry_failure_groups'):aggregate[field].update(row[field])
        if sum(len(row['groups']) for row in platforms.values())>MAX_PLATFORM_GROUPS:
            raise ValueError('Transfer native acquisition-group support exceeds bound.')
        dependencies.append({'packet_sha256':identity,'report_sha256':report['result_sha256'],
                             'campaign_sha256':campaign['result_sha256'],'start':report['start'],'end':report['end']})
        for row in report['daily_support']:
            key=(row['date'],digest(row['cohort']))
            if row['date'] not in required:raise ValueError('Opportunity dates extend outside the declared eligible comparison months.')
            if key in observed:raise ValueError('Overlapping opportunity date/cohort reports are not independent support.')
            if len(observed)>=MAX_SUPPORT_ROWS:raise ValueError('Transfer opportunity daily support exceeds bound.')
            observed[key]={**row,'report_sha256':report['result_sha256'],'reviewed':report['validated_opportunity']}
    missing=[{'date':day,'cohort':cohorts[i]} for day in sorted(required) for i,key in enumerate(cohort_keys) if (day,key) not in observed]
    seasonal=[]
    for c,key in zip(cohorts,cohort_keys):
        for name,months in SEASONS.items():
            rows=[r for (day,ck),r in observed.items() if ck==key and int(day[5:7]) in months]
            area=sum(r['area_m2'] for r in rows)
            seasonal.append({'cohort':c,'season':name,'represented_dates':len(rows),
                'known_area_fraction':sum(r['area_m2']-r['state_area_m2']['unknown'] for r in rows)/area if area else None,
                'usable_area_fraction':sum(r['state_area_m2']['detected']+r['state_area_m2']['observed-without-detection'] for r in rows)/area if area else None,
                'mean_acquisition_groups':sum(r['acquisition_groups'] for r in rows)/len(rows) if rows else None})
    platform_support=[]
    for c,key in zip(cohorts,cohort_keys):
        expected=sorted(transfer.PLATFORMS[c['source']])
        for platform in expected:
            for season in SEASONS:
                row=platforms.get((key,platform,season),{})
                platform_support.append({'cohort':c,'platform':platform,'season':season,
                    **{field:row.get(field,0.) for field in ('sampled_area_m2','known_area_m2','usable_area_m2')},
                    **{field:len(row.get(field,set())) for field in ('groups','known_groups','geometry_failure_groups')}})
    checks={'required_months_present':bool(required),'all_dates_and_cohorts':bool(required) and not missing,
            'spatially_complete':bool(observed) and all(r['spatially_complete'] for r in observed.values()),
            'independently_reviewed':bool(observed) and all(r['reviewed'] for r in observed.values()),
            'all_seasons_have_known_and_usable_support':all(r['known_area_fraction'] is not None and r['known_area_fraction']>0
                and r['usable_area_fraction'] is not None and r['usable_area_fraction']>0 for r in seasonal),
            'platform_season_support':bool(platform_support) and all(r['known_area_m2']>0 and r['usable_area_m2']>0 and r['known_groups']>0 for r in platform_support)}
    return {'schema':'fireatlas-transfer-opportunity-support-v2','region':evidence['region'],'cohorts':cohorts,
        'required_months':len([r for r in evidence['inputs']['months'] if not r['exclusion_reasons']]),
        'required_dates_per_cohort':len(required),'represented_date_cohort_pairs':len(observed),'missing':missing,
        'daily_support':sorted(observed.values(),key=lambda r:(r['date'],digest(r['cohort']))),'seasonal_support':seasonal,
        'platform_acquisition_support':platform_support,'platform_support_units':'Summed native acquisition-cell area per UTC date; dependent descriptive support, not daily regional coverage or independent samples.',
        'dependencies':sorted(dependencies,key=lambda r:(r['start'],r['end'],r['report_sha256'])),
        'checks':checks,'opportunity_change_evaluated':all(checks.values()),
        'interpretation':'Known/usable area support is required in every season and exact cohort. All unknown area remains explicit for independent applicability review; nonzero support alone never admits a transfer.'}


def build(evidence,packets=(),*,protocol_review=None,original_directory=None):
    transfer.verify(evidence)
    p=protocol()
    if evidence['synthetic'] is False and p['state']!='frozen-proposal-awaiting-human-approval':
        raise ValueError('Freeze the transfer opportunity proposal before authentic evaluation.')
    support=opportunity_support(evidence,packets,original_directory=original_directory)
    numerical=evidence['evaluation'];checks={
        'direct_evidence':evidence.get('evidence_type')=='direct-observed-overlap' and evidence.get('factor_chain')==[],
        'authentic':evidence['synthetic'] is False,
        'count_protocol_approved':transfer.review_state(evidence.get('review'))['approved'] and evidence.get('experimental_review') is None,
        'opportunity_protocol_approved':review_state(protocol_review,'protocol')['approved'],
        'forward_and_backward_performance':evidence['performance_pass'] is True and all(e['performance_pass'] for e in numerical.values()),
        'seasonal_count_support':all(all(v['n_months']>0 and v['weighted_absolute_percentage_error'] is not None for v in e['seasonal'].values()) for e in numerical.values()),
        'platform_count_support':all(e['platform_compositions'] and all(v['n_months']>=evidence['protocol']['partition']['test_months'] for v in e['platform_compositions'].values()) for e in numerical.values()),
        'regional_opportunity_evaluated':support['opportunity_change_evaluated']}
    compositions={}
    for direction,evaluation in numerical.items():
        named=[]
        for key,metrics in evaluation['platform_compositions'].items():
            example=next(r for r in evaluation['rows'] if digest([r['source_platforms'],r['target_platforms']])==key)
            named.append({'composition_sha256':key,'source_platforms':example['source_platforms'],
                          'target_platforms':example['target_platforms'],'metrics':metrics})
        compositions[direction]=named
    value={'schema':'fireatlas-direct-transfer-opportunity-v2','protocol':p,'region':evidence['region'],
        'source_cohort':evidence['source_cohort'],'target_cohort':evidence['target_cohort'],'synthetic':evidence['synthetic'],
        'count_evidence':evidence,'count_evidence_sha256':evidence['result_sha256'],'opportunity_support':support,
        'count_platform_support':compositions,
        'protocol_review':protocol_review,'checks':checks,'ready_for_conclusions':all(checks.values()),
        'admitted':False,'blind_confirmation':False,'historical_extrapolation_admitted':False,'forecasting_admitted':False,
        'interpretation':'Recounted direct retrospective product comparability and opportunity support only. Independent bound conclusions are separate. No untested historical extrapolation, original observation overwrite, synthetic location or factor chain.'}
    value['result_sha256']=digest(value);return value


def verify(value,packets=(),*,original_directory=None):
    rebuilt=build(value['count_evidence'],packets,protocol_review=value.get('protocol_review'),original_directory=original_directory)
    if digest(rebuilt)!=digest(value):raise ValueError('Transfer opportunity evaluation recount differs.')
    return {'verified':True,'result_sha256':value['result_sha256'],'ready_for_conclusions':value['ready_for_conclusions']}


def admission(value,conclusions,packets=(),*,original_directory=None):
    verify(value,packets,original_directory=original_directory)
    review=review_state(conclusions,'conclusions',value['result_sha256'])
    passed=value['ready_for_conclusions'] and review['approved']
    return {'schema':'fireatlas-direct-transfer-opportunity-admission-v2','evidence_sha256':value['result_sha256'],
        'region':value['region'],'source_cohort':value['source_cohort'],'target_cohort':value['target_cohort'],
        'checks':{**value['checks'],'independent_conclusions':review['approved']},'admitted':passed,
        'conclusions_review':review,'permitted_months':sorted({r['date'][:7] for r in value['opportunity_support']['daily_support']}) if passed else [],
        'historical_extrapolation_admitted':False,'forecasting_admitted':False,
        'interpretation':'Qualified scope is the recounted overlap only. Historical deployment outside these months requires its own source-era applicability evidence and protocol; owner verifies reviewer identity.'}
