"""Chronological monthly qualification, isolated from the frozen v1 experiment."""
from __future__ import annotations
from collections import Counter
import math
from .comparability import complete_months, digest, metric, choose, source_switch
from .calibration import MODELS, _point_factors, _factor_for
from .qualification import protocol, require_evaluation_review, approval
from .regions import REGIONS

SCHEMA = 'fireatlas-monthly-comparability-v2'


def interval_radius(calibration, nominal=.9):
    errors = sorted(abs(math.log1p(r['prediction']) - math.log1p(r['reference'])) for r in calibration)
    rank = math.ceil((len(errors) + 1) * nominal)
    if not errors or rank > len(errors):
        raise ValueError('Insufficient calibration residuals for finite interval radius.')
    return errors[rank-1]


def bounds(prediction, radius):
    if radius == 0:
        return [prediction, prediction]
    center = math.log1p(prediction)
    return [max(0., math.nextafter(math.expm1(center-radius), -math.inf)), math.nextafter(math.expm1(center+radius), math.inf)]


def scores(rows):
    result = metric(rows)
    if not rows:
        return {**result, 'signed_error': None, 'covered_count':0, 'interval_count':0, 'coverage': None, 'mean_interval_width': None, 'interval_score': None}
    total_width = total_score = covered = 0
    for r in rows:
        lo, hi = r['interval']; y = r['reference']
        width = hi-lo
        total_width += width
        total_score += width + 20 * max(lo-y, y-hi, 0)
        covered += lo <= y <= hi
    return {**result, 'signed_error': sum(r['prediction']-r['reference'] for r in rows)/len(rows),
            'covered_count':covered,'interval_count':len(rows),'coverage': covered/len(rows), 'mean_interval_width': total_width/len(rows), 'interval_score': total_score/len(rows)}


def _select(train, mode):
    if mode == 'nested':
        return choose(train)[0]
    predictions = {m: [] for m in MODELS}
    for year in sorted({r['year'] for r in train}):
        earlier = [r for r in train if r['year'] < year]
        if len({r['year'] for r in earlier}) < 2:
            continue
        a, months = _point_factors(earlier)
        if a is None:
            continue
        for r in train:
            if r['year'] == year:
                for m in MODELS:
                    predictions[m].append({'prediction': r['modis']*_factor_for(m,a,months,r['month']), 'reference':r['viirs']})
    available = [(metric(v)['median_absolute_log_error'], m) for m,v in predictions.items() if v]
    return min(available)[1] if available else None


def evaluate(rows, mode):
    if mode not in ('nested', 'forward'):
        raise ValueError('Unknown selection protocol.')
    p = protocol()['partition']; predictions=[]; folds=[]; skipped=[]
    for year in sorted({r['year'] for r in rows}):
        train=[r for r in rows if r['year'] < year-2]
        cal=[r for r in rows if r['year'] in (year-2,year-1)]
        test=[r for r in rows if r['year'] == year]
        reasons=[]
        if len(train)<p['minimum_training_months'] or len({r['year'] for r in train})<p['minimum_training_years']: reasons.append('training-support')
        if len(cal)<p['minimum_calibration_months'] or {((r['month']-1)//3+1) for r in cal}!={1,2,3,4}: reasons.append('calibration-support-or-seasons')
        if len(test)<p['minimum_test_months'] or {((r['month']-1)//3+1) for r in test} != {1,2,3,4}: reasons.append('test-support-or-seasons')
        if reasons:
            skipped.append({'year':year,'reasons':reasons});continue
        selected=_select(train,mode);a,months=_point_factors(train)
        if selected is None or a is None:
            skipped.append({'year':year,'reasons':['training-factor-or-selection-unavailable']});continue
        radii={m:interval_radius([{'prediction':r['modis']*_factor_for(m,a,months,r['month']),'reference':r['viirs']} for r in cal]) for m in MODELS}
        years=sorted({r['year'] for r in train})
        fold={'test_year':year,'training_years':years,'calibration_years':[year-2,year-1],
              'training_months':[r['date'] for r in train], 'calibration_months':[r['date'] for r in cal],
              'test_months':[r['date'] for r in test], 'selected_model':selected,'log1p_radii':radii}
        folds.append(fold)
        for r in test:
            fixed={m:r['modis']*_factor_for(m,a,months,r['month']) for m in MODELS}
            predictions.append({**r,'reference':r['viirs'],'prediction':fixed[selected], 'interval':bounds(fixed[selected],radii[selected]),
                                'factor':_factor_for(selected,a,months,r['month']), 'model':selected,'training_years':years,
                                'calibration_years':[year-2,year-1], 'fixed':fixed,
                                'fixed_intervals':{m:bounds(fixed[m],radii[m]) for m in MODELS}})
    fixed={m:scores([{**r,'prediction':r['fixed'][m],'interval':r['fixed_intervals'][m]} for r in predictions]) for m in MODELS}
    adjusted=scores(predictions);raw=fixed['no_harmonization'];base=raw['median_absolute_log_error']
    improvement=(base-adjusted['median_absolute_log_error'])/base if base else None
    gates=protocol()['gates']
    checks={'test_support':len(folds)>=p['minimum_test_groups'], 'log_error_improvement':improvement is not None and improvement>=gates['minimum_log_error_improvement'],
            'wape':adjusted['weighted_absolute_percentage_error'] is not None and raw['weighted_absolute_percentage_error'] is not None and adjusted['weighted_absolute_percentage_error']<=raw['weighted_absolute_percentage_error'],
            'interval_coverage':adjusted['coverage'] is not None and adjusted['coverage']>=gates['minimum_coverage'],
            'interval_score':adjusted['interval_score'] is not None and adjusted['interval_score']<=raw['interval_score']}
    annual=[]
    for year in sorted({r['year'] for r in predictions}):
        group=[r for r in predictions if r['year']==year]
        if len(group)==12 and {r['month'] for r in group}==set(range(1,13)):
            annual.append({'year':year,'reference':sum(r['reference'] for r in group),'prediction':sum(r['prediction'] for r in group),'signed_error':sum(r['prediction']-r['reference'] for r in group)})
    return {'protocol':mode,'rows':predictions,'folds':folds,'skipped':skipped,'adjusted':adjusted,'raw':raw,'fixed_models':fixed,
            'relative_log_error_improvement':improvement,'checks':checks,'performance_pass':all(checks.values()),'complete_year_results':annual,
            'per_test_year':{str(year):scores([r for r in predictions if r['year']==year]) for year in sorted({r['year'] for r in predictions})},
            'seasonal_raw':{s:scores([{**r,'prediction':r['fixed']['no_harmonization'],'interval':r['fixed_intervals']['no_harmonization']} for r in predictions if r['month'] in months]) for s,months in {'DJF':[12,1,2],'MAM':[3,4,5],'JJA':[6,7,8],'SON':[9,10,11]}.items()},
            'seasonal':{s:scores([r for r in predictions if r['month'] in months]) for s,months in {'DJF':[12,1,2],'MAM':[3,4,5],'JJA':[6,7,8],'SON':[9,10,11]}.items()},
            'subsets':{'zero_modis_positive_viirs':scores([r for r in predictions if r['modis']==0 and r['reference']>0]),'zero_viirs':scores([r for r in predictions if r['reference']==0]),'small_viirs_1_to_10':scores([r for r in predictions if 0<r['reference']<=10])}}


def analyze(inputs, review=None, *, synthetic=False, experimental=None):
    if inputs.get('schema')!='fireatlas-comparability-input-v1' or inputs.get('region') not in REGIONS:
        raise ValueError('Fixed-region versioned inputs required.')
    if not synthetic:
        if inputs.get('synthetic') is not None and inputs.get('synthetic') is not False:
            raise ValueError('Synthetic inputs cannot enter an authentic evaluation.')
    elif inputs.get('synthetic') is not True:
        raise ValueError('Synthetic testing must be explicitly labelled in the input.')
    require_evaluation_review(review, experimental=experimental, synthetic=synthetic)
    pair=inputs.get('versions')
    if not isinstance(pair,list) or len(pair)!=2 or not all(isinstance(v,str) and v for v in pair):
        raise ValueError('Explicit exact product cohort required; no automatic cohort selection.')
    all_rows,excluded=complete_months(inputs)
    rows=[r for r in all_rows if r['versions']==pair]
    excluded += [{'month':r['date'],'reasons':['different-product-cohort']} for r in all_rows if r['versions']!=pair]
    evaluations={mode:evaluate(rows,mode) for mode in ('nested','forward')}
    result={'schema':SCHEMA,'protocol':protocol(),'input_sha256':digest(inputs),'region':inputs['region'],'versions':pair,
            'synthetic':synthetic,'review':review,'review_state':approval(review),'experimental_review':experimental,
            'eligible_months':len(rows),'excluded':excluded,'evaluation':evaluations,
            'performance_pass':not synthetic and experimental is None and all(e['performance_pass'] for e in evaluations.values()),
            'admission':{'independently_reviewed':False,'monthly_product':False,'daily_reconstruction':False,'historical_transfer':False,'prospective_monitoring':False},
            'interpretation':'Retrospective sensor-record comparability only. Human conclusion review is a separate release gate. Temporal dependence can invalidate nominal interval coverage.'}
    result['source_switches']={f'{mode}/{y}/{m}':source_switch(ev,y,m) for mode,ev in evaluations.items() for y in sorted({r['year'] for r in ev['rows']}) for m in range(2,13)}
    result['result_sha256']=digest(result)
    return {'schema':'fireatlas-comparability-bundle-v2','inputs':inputs,'result':result}


def pending(inputs):
    """Inventory only: this path deliberately does not fit or inspect holdouts."""
    rows,excluded=complete_months(inputs)
    counts=Counter(tuple(r['versions']) for r in rows)
    return {'schema':SCHEMA,'state':'protocol-approval-pending','protocol':protocol(), 'region':inputs['region'],
            'input_sha256':digest(inputs),'cohorts':[{'versions':list(k),'complete_months':n} for k,n in sorted(counts.items())],
            'excluded_months':excluded,'predictions':None,'admission':{'monthly_product':False,'independently_reviewed':False},
            'reason':'Signed independent protocol approval is required before new evaluation; existing v1 retrospective results remain separate.'}


def verify(bundle):
    result=bundle['result']
    rebuilt=analyze(bundle['inputs'],result.get('review'),synthetic=result.get('synthetic') is True,experimental=result.get('experimental_review'))
    if digest(rebuilt)!=digest(bundle):
        raise ValueError('Statistical recount failed; predictions, intervals, metrics or identity differ.')
    return {'verified':True,'synthetic':result['synthetic'],'result_sha256':result['result_sha256']}
