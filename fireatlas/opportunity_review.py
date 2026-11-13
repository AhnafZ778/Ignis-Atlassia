"""Hash-bound independent opportunity review and regional completeness reports.

Review identity is supplied and verified by the owner, never generated here.
Recounting an unsigned or AI-authored packet leaves admission closed.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
from .qualification import digest
from . import opportunity_frames as frames

MAX_FRAMES=256
MAX_ROWS=8_000_000
REQUIRED_EXAMPLES={'detected','observed-without-detection','cloud','unusable','unknown'}
ATTESTATIONS=('original_processing','provider_boundary_origin','boundary_inventory_complete',
              'native_collection_mapping','cmr_receipt_origin','candidate_geometry_adequate')


def bounded_results(results):
    if not isinstance(results,list) or not 1<=len(results)<=MAX_FRAMES:
        raise ValueError('A bounded nonempty frame campaign is required.')
    if len({r['result_sha256'] for r in results})!=len(results) or sum(len(r['daily_cells']) for r in results)>MAX_ROWS:
        raise ValueError('Duplicate frames or campaign row limit exceeded.')


def template(results):
    bounded_results(results)
    for result in results: frames.verify(result)
    return {'schema':'fireatlas-opportunity-review-v2','protocol_sha256':frames.protocol()['protocol_sha256'],
            'frame_sha256s':sorted(r['result_sha256'] for r in results),'scope':'processing-and-geometry',
            'human_authored':False,'automated_agent':None,'decision':'pending','signed_utc':None,
            'reviewer':{k:'' for k in ('name','affiliation','qualification','independence_statement')},
            'attestations':{k:False for k in ATTESTATIONS},'examples':[],
            'native_collection_mappings':[], 'limitations':[]}


def review_state(review, results):
    checks={'identity':False,'binding':False,'attestations':False,'examples':False,'collection_mapping':False}
    if not isinstance(review,dict): return {'approved':False,'no_pass_reviewed':False,'checks':checks}
    person=review.get('reviewer')
    try:
        stamp=frames.utc(review['signed_utc'])
        checks['identity']=(review.get('human_authored') is True and review.get('automated_agent') is False
            and review.get('decision')=='approve' and stamp<=datetime.now(timezone.utc)
            and isinstance(person,dict) and all(isinstance(person.get(k),str) and person[k].strip()
                for k in ('name','affiliation','qualification','independence_statement')))
    except (ValueError,TypeError,AttributeError,KeyError): pass
    checks['binding']=(review.get('schema')=='fireatlas-opportunity-review-v2'
        and review.get('protocol_sha256')==frames.protocol()['protocol_sha256']
        and review.get('scope')=='processing-and-geometry'
        and review.get('frame_sha256s')==sorted(r['result_sha256'] for r in results))
    checks['attestations']=all(review.get('attestations',{}).get(k) is True for k in ATTESTATIONS)
    expected={digest({'cohort':r['cohort'],'native_versions':r['native_versions']}) for r in results}
    mappings=review.get('native_collection_mappings',[])
    if isinstance(mappings,list):
        checks['collection_mapping']=(len(mappings)==len(expected) and
            {digest({'cohort':m.get('cohort'),'native_versions':m.get('native_versions')}) for m in mappings}==expected
            and all(isinstance(m.get('evidence_reference'),str) and m['evidence_reference'].strip() for m in mappings))
    indexed={r['result_sha256']:r for r in results}; seen=set(); confirmed=set(); no_pass=False; valid=True
    examples=review.get('examples',[])
    if not isinstance(examples,list) or len(examples)>1000: examples=[];valid=False
    for example in examples:
        try:
            key=(example['frame_sha256'],example['date'],example['grid_x'],example['grid_y'])
            if key in seen: valid=False
            seen.add(key); r=indexed[key[0]]
            row=next(row for row in r['daily_cells'] if (row['date'],row['grid_x'],row['grid_y'])==key[1:])
            state=row['geometric_state']
            if not isinstance(example.get('evidence_reference'),str) or not example['evidence_reference'].strip():valid=False
            if example.get('outcome')=='agree' and example.get('state')==state:
                confirmed.add(state)
            elif example.get('outcome')=='confirmed-no-pass' and example.get('state')=='no-candidate' and state=='no-candidate' and not r['geometry_failures']:
                no_pass=True
            else: valid=False  # disagreement/unresolved outcomes are preserved, never accepted silently.
        except (ValueError,TypeError,KeyError,StopIteration):valid=False
    checks['examples']=valid and REQUIRED_EXAMPLES<=confirmed
    return {'approved':all(checks.values()),'checks':checks,'no_pass_reviewed':valid and no_pass,
            'review_sha256':digest(review),'owner_must_verify_identity':True}


def campaign(results, review=None, *, original_directory=None):
    """Qualification is restricted to these exact frames and actual re-extraction."""
    bounded_results(results)
    for r in results: frames.verify(r)
    state=review_state(review,results); authentic=not any(r['synthetic'] for r in results)
    original=[]
    if authentic and original_directory is not None:
        original=[frames.bind_original_files(r,original_directory) for r in results]
    admitted=authentic and bool(original) and state['approved']
    no_pass=admitted and state['no_pass_reviewed']
    classified=[]
    for r in results:
        rows=[]
        for row in r['daily_cells']:
            geometric=row['geometric_state']
            code=(geometric if admitted and geometric!='no-candidate' else 'no-pass' if no_pass and geometric=='no-candidate' else 'unknown')
            # Any ambiguous/unsupported candidate geometry prevents no-pass for the frame.
            if code=='no-pass' and r['geometry_failures']: code='unknown'
            rows.append({**row,'validated_opportunity':code})
        classified.append({'frame_sha256':r['result_sha256'],'scope':r['scope'],'tile':r['tile'],
                           'cohort':r['cohort'],'start':r['start'],'end':r['end'],'daily_cells':rows})
    value={'schema':'fireatlas-opportunity-campaign-v2','protocol':frames.protocol(),'frames':results,'review':review,
           'review_state':state,'original_file_bindings':original,'synthetic':not authentic,
           'validated_observation_opportunity':admitted,'no_pass_enabled':no_pass,'classified_frames':classified,
           'interpretation':'Exact reviewed tiles and dates only; owner must verify human identity. Unknown states remain unknown. Pilot review never extends to regional history.'}
    value['result_sha256']=digest(value);return value


def verify_campaign(value,*,original_directory=None):
    if value.get('original_file_bindings') and original_directory is None:
        raise ValueError('Original directory required to reproduce a file-bound opportunity campaign.')
    rebuilt=campaign(value['frames'],value['review'],original_directory=original_directory)
    if digest(rebuilt)!=digest(value):raise ValueError('Opportunity campaign recount differs.')
    return {'verified':True,'result_sha256':value['result_sha256'],'validated_observation_opportunity':value['validated_observation_opportunity']}


def regional_report(value, region, first, last, cohorts, *, original_directory=None):
    """Area-weighted regional support; missing tiles/dates never become coverage.

    Reports cover at most31days; longer campaigns aggregate immutable reports.
    Spatial completeness is exact grid identity, including clipped boundary cells.
    """
    verify_campaign(value,original_directory=original_directory)
    if region not in frames.REGIONS:raise ValueError('A pilot cannot qualify a fixed region.')
    days=frames.dates(first,last); scope=frames.domain(region)
    if not isinstance(cohorts,list) or not 1<=len(cohorts)<=2 or len({digest(c) for c in cohorts})!=len(cohorts):
        raise ValueError('One or two distinct exact standard cohorts required.')
    for c in cohorts:
        if set(c)!={'source','version'} or c['source'] not in frames.PRODUCTS or not isinstance(c['version'],str) or not c['version'].strip():
            raise ValueError('Exact standard source/version cohort required.')
    # Tile partition identities use integer cells; an area sum alone could hide
    # equal-area overlaps and holes.
    area=(scope['projected_bounds'][2]-scope['projected_bounds'][0])*(scope['projected_bounds'][3]-scope['projected_bounds'][1])
    x0,y0,x1,y1=scope['grid_bounds'];expected_cells=(x1-x0)*(y1-y0)
    requested={digest(c):c for c in cohorts}; groups=defaultdict(dict);valid_states={'detected','observed-without-detection','cloud','unusable','unknown','no-pass'}
    for f in value['classified_frames']:
        key=digest(f['cohort'])
        if f['scope']['id']!=region or key not in requested:continue
        for row in f['daily_cells']:
            if row['date'] not in days:continue
            bucket=groups[(key,row['date'])];cell=(row['grid_x'],row['grid_y'])
            if cell in bucket:raise ValueError('Overlapping regional tiles/date records are not independent coverage.')
            if row['validated_opportunity'] not in valid_states:raise ValueError('Unsupported validated opportunity state.')
            bucket[cell]=row
    rows=[]
    for key,c in requested.items():
        for day in days:
            bucket=groups[(key,day)];areas={state:0. for state in sorted(valid_states)}
            for row in bucket.values():areas[row['validated_opportunity']]+=row['area_m2']
            missing=max(0.,area-sum(areas.values()));areas['unknown']+=missing
            complete=len(bucket)==expected_cells
            rows.append({'date':day,'cohort':c,'expected_cells':expected_cells,'represented_cells':len(bucket),
                         'spatially_complete':complete,'area_m2':area,'state_area_m2':areas,
                         'state_area_fraction':{k:v/area for k,v in areas.items()},
                         'missing_area_m2':missing,'candidate_granules':len({p for r in bucket.values() for p in r['candidate_acquisitions']}),
                         'acquisition_groups':len({p for r in bucket.values() for p in r['candidate_acquisition_groups']})})
    differences=[]
    if len(cohorts)==2:
        for day in days:
            a,b=[next(r for r in rows if r['date']==day and r['cohort']==c) for c in cohorts]
            differences.append({'date':day,'state_fraction_difference_target_minus_source':{k:b['state_area_fraction'][k]-a['state_area_fraction'][k] for k in sorted(valid_states)}})
    result={'schema':'fireatlas-regional-opportunity-report-v2','protocol_sha256':frames.protocol()['protocol_sha256'],
            'campaign_sha256':value['result_sha256'],'region':region,'start':first,'end':last,'cohorts':cohorts,
            'daily_support':rows,'differences':differences,'spatial_temporal_complete':all(r['spatially_complete'] for r in rows),
            'validated_opportunity':value['validated_observation_opportunity'] and all(r['spatially_complete'] for r in rows),
            'historical_transfer_admitted':False,
            'interpretation':'Full-domain area-weighted opportunity changes, with explicit unknown area. No cell-independence or causal claim. A separate transfer protocol and conclusion review must assess applicability and unresolved support.'}
    result['result_sha256']=digest(result);return result
