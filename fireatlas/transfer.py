"""Direct, exact-cohort transfer experiments with chronological and backward tests.

The target remains another observed sensor/product record. Neither successful
prediction nor an AI audit establishes ground-truth fires or historical truth.
"""
from __future__ import annotations
from calendar import monthrange
from collections import Counter,defaultdict
from datetime import date,timedelta,datetime,timezone
import hashlib,json,math,re
from pathlib import Path
from .qualification import digest
from .regions import REGIONS
from .core import SOURCES,calendar_row_included
from .comparability_v2 import interval_radius,bounds,scores,_select
from .calibration import MODELS,_point_factors,_factor_for

ROOT=Path(__file__).resolve().parents[1]
UNITS='occupied common-grid centroid cell-days per complete UTC month'
GRID='EPSG:6933 1000m'
COUNT_BASIS='Union of authentic stored exact-cohort observations; request-backed exports establish UTC completeness, not exclusive import-batch ownership.'
MAX_CELL_ROWS=5_000_000
PLATFORMS={'MODIS_SP':{'Terra','Aqua'},'VIIRS_SNPP_SP':{'S-NPP'},'VIIRS_NOAA20_SP':{'NOAA-20'},'VIIRS_NOAA21_SP':{'NOAA-21'}}


def platform_name(source,value):
    key=str(value).upper().replace('-','').replace(' ','')
    names={'T':'Terra','TERRA':'Terra','A':'Aqua','AQUA':'Aqua','N':'S-NPP','SNPP':'S-NPP','SUOMINPP':'S-NPP','1':'NOAA-20','N20':'NOAA-20','J1':'NOAA-20','JPSS1':'NOAA-20','NOAA20':'NOAA-20','2':'NOAA-21','N21':'NOAA-21','J2':'NOAA-21','JPSS2':'NOAA-21','NOAA21':'NOAA-21'}
    name=names.get(key)
    if name not in PLATFORMS.get(source,set()):raise ValueError('Unknown or incompatible source/platform identity.')
    return name


def ledger_months(ledgers,selected):
    supported={c:set() for c in selected}
    for r in ledgers:
        c=(r.get('source'),r.get('version'))
        if c not in supported or r.get('complete_export') is not True or r.get('coverage_basis')!='request-metadata' or not isinstance(r.get('file_sha256'),str) or not re.fullmatch('[0-9a-f]{64}',r['file_sha256']):raise ValueError('Hash-bound exact-cohort export evidence required.')
        first=date.fromisoformat(r['month']+'-01');last=first.replace(day=monthrange(first.year,first.month)[1])
        if r['start']==first.isoformat() and r['end']==last.isoformat():supported[c].add(r['month'])
    return supported


def notice_snapshot():
    from .availability import NOTICE_FILE
    body=NOTICE_FILE.read_bytes()
    return {'source_utf8':body.decode('utf-8'),'sha256':hashlib.sha256(body).hexdigest()}


def frozen_notices(value):
    if not isinstance(value,dict) or not isinstance(value.get('source_utf8'),str) or len(value['source_utf8'])>1_000_000 or hashlib.sha256(value['source_utf8'].encode()).hexdigest()!=value.get('sha256'):raise ValueError('Hash-bound frozen sensor notice bytes required.')
    material=json.loads(value['source_utf8'])
    if material.get('schema')!='fireatlas-sensor-notices-v1' or not isinstance(material.get('notices'),list):raise ValueError('Unsupported frozen notice ledger.')
    notices=[]
    for item in material['notices']:
        first=datetime.fromisoformat(item['start_utc'].replace('Z','+00:00'));last=datetime.fromisoformat(item['end_utc'].replace('Z','+00:00'))
        if first.tzinfo is None or last.tzinfo is None or first.utcoffset().total_seconds()!=0 or last.utcoffset().total_seconds()!=0 or last<first:raise ValueError('Frozen notice must have an ordered UTC interval.')
        notices.append((item['source_id'],first,last))
    return notices


def summarize(months,supported,cells,platforms,a,b,notice_material):
    notices=frozen_notices(notice_material)
    rows=[]
    for month in months:
        first=date.fromisoformat(month+'-01');days=[first+timedelta(days=i) for i in range(monthrange(first.year,first.month)[1])]
        reasons=[]
        for label,c in [('source',a),('target',b)]:
            if month not in supported[c]:reasons.append(label+'-verified-exact-cohort-export-missing')
        start=datetime.fromisoformat(first.isoformat()+'T00:00:00+00:00');end=start+timedelta(days=len(days))
        if any(source in (a[0],b[0]) and lo<end and hi>=start for source,lo,hi in notices):reasons.append('documented-processing-gap')
        rows.append({'month':month,'source_count':None if reasons else sum(len(cells[a].get(d.isoformat(),set())) for d in days),'target_count':None if reasons else sum(len(cells[b].get(d.isoformat(),set())) for d in days),
                     'source_platforms':sorted({p for d in days for p in platforms[a].get(d.isoformat(),set())}),'target_platforms':sorted({p for d in days for p in platforms[b].get(d.isoformat(),set())}),'exclusion_reasons':reasons})
    return rows


def protocol():
    value=json.loads((ROOT/'fireatlas/protocols/direct-transfer-v1.0.0.json').read_text())
    for name,expected in value['source_sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('Transfer source differs from frozen protocol; create a successor before evaluation.')
    return {**value,'protocol_sha256':digest(value)}


def cohort(value):
    if not isinstance(value,dict) or set(value)!={'source','version'} or value.get('source') not in SOURCES or SOURCES[value['source']][1]!='SP' or not isinstance(value.get('version'),str) or not value['version'].strip() or len(value['version'])>40:
        raise ValueError('Explicit standard-product source and exact version required; NRT is excluded.')
    return value['source'],value['version']


def capture(db,region,source_cohort,target_cohort):
    """Capture original cells and request-backed exact-cohort ledgers read-only."""
    if region not in REGIONS:raise ValueError('Fixed qualification region required.')
    a,b=cohort(source_cohort),cohort(target_cohort)
    if a==b:raise ValueError('A direct transfer needs two distinct source/product cohorts.')
    w,s,e,n=REGIONS[region]['bbox'];ledgers=[]
    for c in (a,b):
        for row in db.execute('''SELECT e.*,b.file_sha256,b.demo FROM source_exports e JOIN batches b ON e.batch_id=b.id
             WHERE e.region_id=? AND e.source_id=? AND b.demo=0 AND e.complete_export=1 AND e.coverage_basis='request-metadata'
               AND e.west<=? AND e.south<=? AND e.east>=? AND e.north>=?''',(region,c[0],w,s,e,n)):
            r=dict(row)
            versions=json.loads(r['product_versions_json'])
            if versions==[c[1]]:
                ledgers.append({'source':c[0],'version':c[1],'month':r['month'],'start':r['request_start'],'end':r['request_end'],'file_sha256':r['file_sha256'],'complete_export':True,'coverage_basis':'request-metadata'})
    supported=ledger_months(ledgers,(a,b))
    months=sorted(supported[a]|supported[b]);cells={c:defaultdict(set) for c in (a,b)};platforms={c:defaultdict(set) for c in (a,b)};files={c:defaultdict(set) for c in (a,b)}
    for c in (a,b):
        if not months:continue
        first=months[0]+'-01';last=date.fromisoformat(months[-1]+'-01');end=(last.replace(day=monthrange(last.year,last.month)[1])+timedelta(days=1)).isoformat()
        for r in db.execute('''SELECT o.acquisition_utc,o.grid_x,o.grid_y,o.platform,o.raw_json,b.file_sha256 FROM observations o JOIN batches b ON o.batch_id=b.id
              WHERE b.demo=0 AND o.source_id=? AND o.product_version=? AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=?
                AND o.acquisition_utc>=? AND o.acquisition_utc<?''',(c[0],c[1],w,e,s,n,first,end)):
            if not calendar_row_included(r['raw_json']):continue
            stamp=r['acquisition_utc'][:10]
            if stamp[:7] not in months:continue
            cells[c][stamp].add((r['grid_x'],r['grid_y']));platforms[c][stamp].add(platform_name(c[0],r['platform']));files[c][stamp].add(r['file_sha256'])
    notice_material=notice_snapshot();rows=summarize(months,supported,cells,platforms,a,b,notice_material)
    daily_cells=[{'role':role,'date':day,'cells':[list(c) for c in sorted(values)],'platforms':sorted(platforms[c][day]),'file_sha256s':sorted(files[c][day])} for role,c in [('source',a),('target',b)] for day,values in sorted(cells[c].items())]
    value={'schema':'fireatlas-direct-transfer-input-v1','region':region,'source_cohort':source_cohort,'target_cohort':target_cohort,'synthetic':False,
           'units':UNITS,'grid':GRID,'count_basis':COUNT_BASIS,'notice_snapshot':notice_material,'observation_files':[{'source':c[0],'version':c[1],'file_sha256':h} for c in (a,b) for h in sorted({h for hs in files[c].values() for h in hs})],'daily_cells':daily_cells,'months':rows,'export_ledger':sorted(ledgers,key=lambda r:(r['source'],r['version'],r['month'],r['file_sha256']))}
    value['input_sha256']=digest(value);return value


def validate(inputs,synthetic):
    if not isinstance(inputs,dict) or inputs.get('schema')!='fireatlas-direct-transfer-input-v1' or inputs.get('region') not in REGIONS:raise ValueError('Versioned fixed-region direct-transfer input required.')
    if inputs.get('synthetic') is not synthetic:raise ValueError('Authentic and synthetic direct-transfer inputs cannot mix.')
    a,b=cohort(inputs['source_cohort']),cohort(inputs['target_cohort'])
    if a==b:raise ValueError('Distinct cohorts required.')
    if inputs.get('units')!=UNITS or inputs.get('grid')!=GRID or inputs.get('count_basis')!=COUNT_BASIS:raise ValueError('Exact transfer grid and count units required.')
    raw=inputs.get('daily_cells')
    if not isinstance(raw,list) or len(raw)>25000 or len(inputs.get('months',[]))>400 or len(inputs.get('export_ledger',[]))>10000:raise ValueError('Transfer input exceeds declared record bounds.')
    if sum(len(r.get('cells',[])) for r in raw)>MAX_CELL_ROWS:raise ValueError('Transfer cell input exceeds declared bound.')
    material={k:v for k,v in inputs.items() if k!='input_sha256'}
    if digest(material)!=inputs.get('input_sha256'):raise ValueError('Transfer input identity differs.')
    declared={c:set() for c in (a,b)}
    for file in inputs.get('observation_files',[]):
        c=(file.get('source'),file.get('version'));h=file.get('file_sha256')
        if c not in declared or not isinstance(h,str) or not re.fullmatch('[0-9a-f]{64}',h) or h in declared[c]:raise ValueError('Unique exact-cohort original-file hashes required.')
        declared[c].add(h)
    supported=ledger_months(inputs['export_ledger'],(a,b));months=sorted(supported[a]|supported[b]);cells={c:{} for c in (a,b)};platforms={c:{} for c in (a,b)};seen_days=set()
    w,s,e,n=REGIONS[inputs['region']]['bbox']
    from .core import TO_GRID
    x0,y0=TO_GRID.transform(w,s);x1,y1=TO_GRID.transform(e,n)
    for day in raw:
        if day.get('role') not in ('source','target'):raise ValueError('Unknown transfer input role.')
        c=a if day['role']=='source' else b;stamp=date.fromisoformat(day['date']).isoformat();key=(day['role'],stamp)
        if key in seen_days or stamp[:7] not in months:raise ValueError('Duplicate or unsupported daily-cell record.')
        seen_days.add(key);values=day['cells'];labels=day.get('platforms');hashes=day.get('file_sha256s')
        if not isinstance(hashes,list) or len(hashes)!=len(set(hashes)) or not set(hashes)<=declared[c] or bool(values)!=bool(hashes):raise ValueError('Daily cells require declared authentic source-file provenance.')
        if not isinstance(labels,list) or len(labels)!=len(set(labels)) or not set(labels)<=PLATFORMS.get(c[0],set()) or (bool(values)!=bool(labels)):raise ValueError('Exact compatible platform identities required.')
        if any(not isinstance(v,list) or len(v)!=2 or any(type(i) is not int for i in v) or not (math.floor(x0/1000)<=v[0]<=math.floor(x1/1000) and math.floor(y0/1000)<=v[1]<=math.floor(y1/1000)) for v in values):raise ValueError('Grid cells outside fixed scope or invalid.')
        coordinates={tuple(v) for v in values}
        if len(coordinates)!=len(values):raise ValueError('Duplicate daily grid cell.')
        cells[c][stamp]=coordinates;platforms[c][stamp]=set(labels)
    if digest(summarize(months,supported,cells,platforms,a,b,inputs.get('notice_snapshot')))!=digest(inputs['months']):raise ValueError('Transfer monthly count/eligibility recount differs from frozen cells and ledgers.')
    rows=[];seen=set()
    for r in inputs['months']:
        stamp=date.fromisoformat(r['month']+'-01')
        if r['month'] in seen:raise ValueError('Duplicate transfer month.')
        seen.add(r['month'])
        if r['exclusion_reasons']:continue
        if any(type(r.get(k)) is not int or r[k]<0 for k in ('source_count','target_count')):raise ValueError('Known nonnegative monthly counts required.')
        rows.append({'date':r['month'],'year':stamp.year,'month':stamp.month,'modis':r['source_count'],'viirs':r['target_count'],
                     'source_platforms':r['source_platforms'],'target_platforms':r['target_platforms']})
    return sorted(rows,key=lambda r:r['date'])


def evaluate(rows,direction):
    if direction not in ('forward','backward'):raise ValueError('Unknown transfer direction.')
    p=protocol();policy=p['partition'];predictions=[];folds=[];skipped=[]
    quarters=lambda group:sorted({(r['month']-1)//3+1 for r in group})
    for year in sorted({r['year'] for r in rows}):
        train=[r for r in rows if r['year']<year-2] if direction=='forward' else [r for r in rows if r['year']>year+2]
        calibration=[r for r in rows if r['year'] in ((year-2,year-1) if direction=='forward' else (year+1,year+2))];test=[r for r in rows if r['year']==year]
        support={'training_months':len(train),'training_years':len({r['year'] for r in train}),'calibration_months':len(calibration),'calibration_quarters':quarters(calibration),'test_months':len(test),'test_quarters':quarters(test)}
        reasons=[]
        if len(train)<policy['training_months'] or support['training_years']<policy['training_years']:reasons.append('training-support')
        if len(calibration)<policy['calibration_months'] or quarters(calibration)!=[1,2,3,4]:reasons.append('calibration-support-or-seasons')
        if len(test)<policy['test_months'] or quarters(test)!=[1,2,3,4]:reasons.append('test-support-or-seasons')
        if reasons:skipped.append({'year':year,'support':support,'reasons':reasons});continue
        model=_select(train,'nested');annual,monthly=_point_factors(train)
        if model is None or annual is None:skipped.append({'year':year,'support':support,'reasons':['training-factor-unavailable']});continue
        radii={m:interval_radius([{'prediction':r['modis']*_factor_for(m,annual,monthly,r['month']),'reference':r['viirs']} for r in calibration]) for m in MODELS}
        folds.append({'test_year':year,'support':support,'training_months':[r['date'] for r in train],'calibration_months':[r['date'] for r in calibration],'test_months':[r['date'] for r in test],'selected_model':model,'radii':radii})
        for r in test:
            fixed={m:r['modis']*_factor_for(m,annual,monthly,r['month']) for m in MODELS}
            predictions.append({'date':r['date'],'year':year,'month':r['month'],'source_count':r['modis'],'reference':r['viirs'],'prediction':fixed[model],'interval':bounds(fixed[model],radii[model]),'model':model,
                                'fixed':fixed,'fixed_intervals':{m:bounds(fixed[m],radii[m]) for m in MODELS},'source_platforms':r['source_platforms'],'target_platforms':r['target_platforms']})
    baselines={m:scores([{**r,'prediction':r['fixed'][m],'interval':r['fixed_intervals'][m]} for r in predictions]) for m in MODELS};adjusted=scores(predictions);raw=baselines['no_harmonization']
    base=raw['median_absolute_log_error'];improvement=(base-adjusted['median_absolute_log_error'])/base if base else None
    gates=p['admission_rules'];checks={'test_groups':len(folds)>=policy['test_groups'],'log_improvement':improvement is not None and improvement>=gates['minimum_log_improvement'],
        'wape':adjusted['weighted_absolute_percentage_error'] is not None and raw['weighted_absolute_percentage_error'] is not None and adjusted['weighted_absolute_percentage_error']<=raw['weighted_absolute_percentage_error'],
        'coverage':adjusted['coverage'] is not None and adjusted['coverage']>=gates['minimum_coverage'],'interval_score':adjusted['interval_score'] is not None and raw['interval_score'] is not None and adjusted['interval_score']<=raw['interval_score']}
    return {'direction':direction,'rows':predictions,'folds':folds,'skipped':skipped,'adjusted':adjusted,'raw':raw,'baselines':baselines,'relative_log_improvement':improvement,'checks':checks,'performance_pass':all(checks.values()),
            'seasonal':{name:scores([r for r in predictions if r['month'] in months]) for name,months in {'DJF':[12,1,2],'MAM':[3,4,5],'JJA':[6,7,8],'SON':[9,10,11]}.items()},
            'platform_compositions':{key:scores([r for r in predictions if digest([r['source_platforms'],r['target_platforms']])==key]) for key in sorted({digest([r['source_platforms'],r['target_platforms']]) for r in predictions})}}


def review_state(review,*,scope='protocol',evidence_sha256=None):
    p=protocol()
    if not isinstance(review,dict):return {'approved':False,'reason':'human-review-missing'}
    person=review.get('reviewer')
    checks=[review.get('schema')=='fireatlas-direct-transfer-review-v1', review.get('protocol_sha256')==p['protocol_sha256'],review.get('scope')==scope,
            review.get('evidence_sha256')==evidence_sha256, review.get('human_authored') is True,review.get('automated_agent') is False,review.get('decision')=='approve',
            isinstance(person,dict) and all(isinstance(person.get(k),str) and person[k].strip() for k in ('name','affiliation','qualification','independence_statement'))]
    try:
        stamp=datetime.fromisoformat(review.get('signed_utc','').replace('Z','+00:00'))
        checks.append(stamp.tzinfo is not None and stamp.utcoffset().total_seconds()==0 and stamp<=datetime.now(timezone.utc))
    except (ValueError,TypeError,AttributeError):checks.append(False)
    return {'approved':all(checks),'review_sha256':digest(review),'owner_must_verify_identity':True}


def experimental_review():
    p=protocol()
    return {'schema':'fireatlas-direct-transfer-ai-review-v1','protocol_sha256':p['protocol_sha256'],'audit_scope':p['ai_audit_scope'],
            'automated_agent':True,'human_authored':False,'independent_scientific_approval':False}


def analyze(inputs,*,synthetic=False,experimental=None,review=None):
    if not synthetic and protocol()['state']!='frozen-proposal-awaiting-human-approval':raise ValueError('Freeze and review the transfer protocol before authentic evaluation.')
    if synthetic:
        if experimental is not None or review is not None:raise ValueError('Synthetic fixtures cannot mix with authentic reviews.')
    elif experimental is not None:
        if review is not None or digest(experimental)!=digest(experimental_review()):raise ValueError('Frozen AI experiment receipt required; human review cannot mix.')
    elif not review_state(review)['approved']:raise ValueError('Signed independent transfer protocol approval or explicit AI-experimental mode required.')
    rows=validate(inputs,synthetic);p=protocol();ev={d:evaluate(rows,d) for d in ('forward','backward')}
    result={'schema':'fireatlas-direct-transfer-evidence-v1','protocol':p,'region':inputs['region'],'source_cohort':inputs['source_cohort'],'target_cohort':inputs['target_cohort'],'synthetic':synthetic,
        'evidence_type':'direct-observed-overlap','factor_chain':[],'inputs':inputs,'input_sha256':inputs['input_sha256'],'eligible_months':len(rows),'evaluation':ev,
        'numerical_screening_pass':all(e['performance_pass'] for e in ev.values()),'performance_pass':not synthetic and experimental is None and all(e['performance_pass'] for e in ev.values()),'review':review,'experimental_review':experimental,'opportunity_change_evaluated':False,'admitted':False,
        'execution_review':'AI-reviewed exploratory implementation; independent scientific approval pending.',
        'interpretation':'Direct mapping of observed product records only. Backward testing uses later training/calibration and is retrospective; it is not a forecast or historical VIIRS observation. Temporal interval guarantees are not claimed.'}
    result['result_sha256']=digest(result);return result


def verify(result):
    rebuilt=analyze(result['inputs'],synthetic=result.get('synthetic') is True,experimental=result.get('experimental_review'),review=result.get('review'))
    if digest(rebuilt)!=digest(result):raise ValueError('Direct transfer statistical recount differs.')
    return {'verified':True,'result_sha256':result['result_sha256'],'synthetic':result['synthetic']}
