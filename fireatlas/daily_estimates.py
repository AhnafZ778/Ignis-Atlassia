"""Separate approval-gated daily reconstruction research; never location synthesis."""
from __future__ import annotations
from collections import defaultdict
from datetime import date
import importlib.metadata
import math
import warnings
from .qualification import protocol, require_evaluation_review, digest
from .comparability import complete_months
from .comparability_v2 import interval_radius, bounds, scores as monthly_scores
from .calibration import _point_factors,_factor_for
from .core import calendar_row_included
from .regions import REGIONS

MODELS=('no_harmonization','annual_ratio','monthly_ratio','hurdle_poisson')

def scores(rows):
    value=monthly_scores(rows);value['n_utc_days']=value.pop('n_months');return value


def features(row):
    day=date.fromisoformat(row['date']);angle=2*math.pi*(day.timetuple().tm_yday-1)/(366 if day.year%4==0 and (day.year%100!=0 or day.year%400==0) else 365)
    return [1.,math.log1p(row['modis']),math.log1p(row['terra']),math.log1p(row['aqua']),math.sin(angle),math.cos(angle)]


def fit_predict(train,target):
    if importlib.metadata.version('statsmodels')!='0.15.0': raise ValueError('Install the pinned statsmodels==0.15.0 optional research dependency.')
    import numpy as np
    from statsmodels.discrete.truncated_model import HurdleCountModel
    from statsmodels.tools.sm_exceptions import ConvergenceWarning, HessianInversionWarning
    y=np.array([r['viirs'] for r in train]);x=np.array([features(r) for r in train]);xt=np.array([features(r) for r in target])
    if not (np.any(y==0) and np.any(y>0)) or np.linalg.matrix_rank(x)<x.shape[1]: raise ValueError('Hurdle training needs both occurrence states and full-rank prediction-time inputs.')
    with warnings.catch_warnings():
        warnings.simplefilter('error',ConvergenceWarning);warnings.simplefilter('error',HessianInversionWarning);warnings.simplefilter('error',RuntimeWarning)
        fitted=HurdleCountModel(y,x,dist='poisson',zerodist='poisson').fit(method='bfgs',disp=False,maxiter=200)
        expected=fitted.predict(xt,which='mean');probability=1-fitted.predict(xt,which='prob-zero')
    if not np.all(np.isfinite(expected)) or np.any(expected<0) or not np.all(np.isfinite(probability)) or np.any(probability<0) or np.any(probability>1): raise ValueError('Hurdle fit produced invalid expected counts or probabilities.')
    return {'expected':[float(v) for v in expected],'probability_positive':[float(v) for v in probability], 'parameters':[float(v) for v in fitted.params], 'dependency':'statsmodels==0.15.0','environment':{name:importlib.metadata.version(name) for name in ('statsmodels','numpy','scipy','pandas')}}


def capture_features(db,inputs):
    """Count native-platform occupied cell unions under the same row filter."""
    region=inputs['region'];w,s,e,n=REGIONS[region]['bbox'];marks=defaultdict(lambda:defaultdict(set))
    for r in db.execute("""SELECT o.acquisition_utc,o.platform,o.grid_x,o.grid_y,o.raw_json FROM observations o JOIN batches b ON b.id=o.batch_id
          WHERE b.demo=0 AND o.source_id='MODIS_SP' AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=?""",(w,e,s,n)):
        if not calendar_row_included(r['raw_json']):continue
        platform={'T':'terra','TERRA':'terra','A':'aqua','AQUA':'aqua'}.get(r['platform'].upper())
        if platform is None: raise ValueError('Unknown MODIS platform; do not silently infer breakdown.')
        marks[r['acquisition_utc'][:10]][platform].add((r['grid_x'],r['grid_y']))
    return {d['date']:{p:len(marks[d['date']][p]) for p in ('terra','aqua')} for d in inputs['days']}


def eligible(inputs,platform_counts):
    # Daily eligibility is not inherited from monthly performance, but uses the
    # same source evidence requirements date by date, including exact cohorts.
    rows=[];seen=set();pair=inputs.get('versions')
    if not isinstance(pair,list) or len(pair)!=2 or not all(isinstance(v,str) and v for v in pair): raise ValueError('Explicit exact source-version cohort required.')
    # Reuse full validation, not full-month eligibility: missing individual days
    # remain excluded while supported dates can enter a daily-only protocol.
    complete_months(inputs)
    for d in inputs['days']:
        stamp=d['date']
        if stamp in seen: raise ValueError('Duplicate date.')
        seen.add(stamp);sources=d['sources'];items=[sources[s] for s in ('MODIS_SP','VIIRS_SNPP_SP')]
        if any(not v['verified_export'] or v['processing_gap'] or v['cells'] is None or v['raw'] is None or v['versions']!=[pair[i]] for i,v in enumerate(items)):continue
        counts=platform_counts.get(stamp)
        if not isinstance(counts,dict) or set(counts)!={'terra','aqua'} or any(type(counts.get(k)) is not int or counts[k]<0 for k in ('terra','aqua')):raise ValueError('Known authentic platform counts required for each eligible date.')
        modis=items[0]['cells']
        if not max(counts.values())<=modis<=sum(counts.values()):raise ValueError('Platform counts are inconsistent with the MODIS union.')
        rows.append({'date':stamp,'year':int(stamp[:4]),'month':int(stamp[5:7]),'modis':modis,'viirs':items[1]['cells'],**counts})
    return rows


def analyze(inputs,platform_counts,review=None,*,synthetic=False,experimental=None):
    if inputs.get('schema')!='fireatlas-comparability-input-v1':
        raise ValueError('Versioned comparability inputs required for daily research.')
    if not synthetic:
        if inputs.get('synthetic') is not None and inputs.get('synthetic') is not False: raise ValueError('Synthetic inputs cannot enter authentic research.')
    elif inputs.get('synthetic') is not True: raise ValueError('Synthetic research inputs must be labelled.')
    if inputs.get('region') not in REGIONS:raise ValueError('Unsupported region.')
    require_evaluation_review(review,'daily',experimental=experimental,synthetic=synthetic)
    rows=eligible(inputs,platform_counts);policy=protocol('daily')['partition'];predictions=[];folds=[];skipped=[]
    for year in sorted({r['year'] for r in rows}):
        train=[r for r in rows if r['year']<year-2];cal=[r for r in rows if r['year'] in (year-2,year-1)];test=[r for r in rows if r['year']==year]
        if len({r['year'] for r in train})<3 or len(train)<policy['minimum_training_days'] or len(cal)<policy['minimum_calibration_days'] or {((r['month']-1)//3+1) for r in cal}!={1,2,3,4} or len(test)<policy['minimum_test_days'] or {((r['month']-1)//3+1) for r in test}!={1,2,3,4}:
            skipped.append({'year':year,'reason':'chronological-support-or-season-insufficient'});continue
        denominator=sum(r['modis'] for r in train)
        if denominator==0:skipped.append({'year':year,'reason':'ratio-denominator-zero'});continue
        ratio,month_factors=_point_factors(train)
        try: hurdle=fit_predict(train,cal+test)
        except (ValueError,ImportError,importlib.metadata.PackageNotFoundError,Warning,ArithmeticError) as exc:
            skipped.append({'year':year,'reason':'hurdle-fit-unavailable','kind':type(exc).__name__});continue
        radii={}
        def value(r,index,model):return hurdle['expected'][index] if model=='hurdle_poisson' else r['modis']*_factor_for(model,ratio,month_factors,r['month'])
        for model in MODELS:radii[model]=interval_radius([{'prediction':value(r,i,model),'reference':r['viirs']} for i,r in enumerate(cal)])
        folds.append({'test_year':year,'training_years':sorted({r['year'] for r in train}),'calibration_years':[year-2,year-1],
                      'training_dates':[r['date'] for r in train],'calibration_dates':[r['date'] for r in cal],'parameters':hurdle['parameters'],'environment':hurdle.get('environment',{'kind':'synthetic-engineering-fixture'}),'radii':radii})
        for i,r in enumerate(test,len(cal)):
            fixed={m:value(r,i,m) for m in MODELS}
            predictions.append({**r,'reference':r['viirs'],'prediction':fixed['hurdle_poisson'],'interval':bounds(fixed['hurdle_poisson'],radii['hurdle_poisson']),
                                'expected_count':fixed['hurdle_poisson'],'probability_positive':hurdle['probability_positive'][i],
                                'fixed':fixed,'fixed_intervals':{m:bounds(fixed[m],radii[m]) for m in MODELS},
                                'estimate_type':'expected-observed-viirs-cell-days','opportunity_state':'unknown','applicability':'fixed-region exact standard cohort only'})
    metrics={m:scores([{**r,'prediction':r['fixed'][m],'interval':r['fixed_intervals'][m]} for r in predictions]) for m in MODELS}
    zero=[r for r in predictions if r['modis']==0 and r['reference']>0]
    zero_metrics={m:scores([{**r,'prediction':r['fixed'][m],'interval':r['fixed_intervals'][m]} for r in zero]) for m in MODELS}
    seasons={s:{m:scores([{**r,'prediction':r['fixed'][m],'interval':r['fixed_intervals'][m]} for r in predictions if r['month'] in months]) for m in MODELS} for s,months in {'DJF':[12,1,2],'MAM':[3,4,5],'JJA':[6,7,8],'SON':[9,10,11]}.items()}
    gates=protocol('daily')['gates'];checks={'three_test_groups':len(folds)>=3,'interval_coverage':bool(predictions) and metrics['hurdle_poisson']['coverage']>=gates['minimum_coverage'],'zero_recovery_support':len(zero)>=policy['minimum_zero_recovery_test_days']}
    for baseline in ('no_harmonization','annual_ratio','monthly_ratio'):
        a=metrics['hurdle_poisson'];b=metrics[baseline]
        checks[baseline+'_log_improvement']=bool(b['median_absolute_log_error']) and a['median_absolute_log_error']<=b['median_absolute_log_error']*(1-gates['minimum_log_error_improvement'])
        checks[baseline+'_wape']=a['weighted_absolute_percentage_error'] is not None and b['weighted_absolute_percentage_error'] is not None and a['weighted_absolute_percentage_error']<=b['weighted_absolute_percentage_error']
        checks[baseline+'_interval_score']=a['interval_score'] is not None and a['interval_score']<=b['interval_score']
        za=zero_metrics['hurdle_poisson']['median_absolute_log_error'];zb=zero_metrics[baseline]['median_absolute_log_error']
        checks[baseline+'_zero_improvement']=bool(zb) and za<=zb*(1-gates['minimum_zero_recovery_improvement'])
        checks[baseline+'_seasonal']=all(v[baseline]['weighted_absolute_percentage_error'] is not None and v['hurdle_poisson']['weighted_absolute_percentage_error']<=v[baseline]['weighted_absolute_percentage_error']*(1+gates['maximum_seasonal_wape_degradation']) for v in seasons.values())
    bins=[]
    for lo in (0,.2,.4,.6,.8):
        group=[r for r in predictions if lo<=r['probability_positive']<(lo+.2 if lo<.8 else 1.000001)]
        bins.append({'probability_bin':[lo,lo+.2],'n':len(group),'mean_probability':sum(r['probability_positive'] for r in group)/len(group) if group else None,'observed_positive_fraction':sum(r['reference']>0 for r in group)/len(group) if group else None})
    result={'schema':'fireatlas-daily-estimate-research-v2','protocol':protocol('daily'),'input_sha256':digest([inputs,platform_counts]),'region':inputs['region'],'versions':inputs['versions'],'synthetic':synthetic,
            'inputs':inputs,'platform_counts':platform_counts,'review':review,'experimental_review':experimental,'folds':folds,'skipped':skipped,'rows':predictions,'metrics':metrics,'zero_modis_positive_viirs':zero_metrics,'seasonal':seasons,'occurrence_calibration':bins,
            'per_test_year':{str(year):scores([r for r in predictions if r['year']==year]) for year in sorted({r['year'] for r in predictions})},
            'checks':checks,'performance_pass':not synthetic and experimental is None and all(checks.values()),'admitted':False,'independent_method_review':'pending',
            'supported_opportunity_subsets':'not evaluated: full-cell opportunity evidence unavailable','no_locations_generated':True}
    result['result_sha256']=digest(result);return result


def verify(result):
    rebuilt=analyze(result['inputs'],result['platform_counts'],result.get('review'),synthetic=result.get('synthetic') is True,experimental=result.get('experimental_review'))
    if digest(rebuilt)!=digest(result):raise ValueError('Daily statistical recount differs from frozen research evidence.')
    return {'verified':True,'synthetic':result['synthetic'],'result_sha256':result['result_sha256']}
