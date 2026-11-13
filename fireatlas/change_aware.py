"""Experimental monthly change-aware model. No production release or evaluation.

Inputs are monthly counts from one region/cohort. This module never loads data
or approves protocols; callers must enforce the external review gate before
using real observations for a new evaluation.
"""
from __future__ import annotations
import math

MODEL_VERSION = 'change-aware-log-v1-experimental'


def _features(row):
    month = row['month']
    x, y = row['modis'], row['reference']
    if type(row['year']) is not int or type(month) is not int or not 1 <= month <= 12:
        raise ValueError('Invalid year or calendar month.')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in (x, y)):
        raise ValueError('Counts must be finite and nonnegative.')
    return [float(i == month - 1) for i in range(12)] + [math.log1p(x)], math.log1p(y)


def _solve(matrix, values):
    a = [row[:] + [value] for row, value in zip(matrix, values)]
    for col in range(len(a)):
        pivot = max(range(col, len(a)), key=lambda i: abs(a[i][col]))
        if abs(a[pivot][col]) < 1e-12:
            raise ValueError('Model design is singular.')
        a[col], a[pivot] = a[pivot], a[col]
        scale = a[col][col]
        a[col] = [v / scale for v in a[col]]
        for i in range(len(a)):
            if i != col:
                factor = a[i][col]
                a[i] = [x - factor * y for x, y in zip(a[i], a[col])]
    return [row[-1] for row in a]


def fit(rows, *, test_year, change_weight=1.0, ridge=0.01):
    """Fit on explicitly provided earlier rows; reject rather than hide leakage.

    Minimize mean squared log1p level error plus weighted mean squared
    same-month consecutive-year change error, with ridge regularization.
    """
    if type(test_year) is not int or not rows or not math.isfinite(change_weight) or change_weight < 0 or not math.isfinite(ridge) or ridge <= 0:
        raise ValueError('Invalid model settings or empty training set.')
    records = {}
    for row in rows:
        if row['year'] >= test_year:
            raise ValueError('Training must precede the held-out year.')
        key = row['year'], row['month']
        if key in records:
            raise ValueError('Duplicate training month.')
        records[key] = _features(row)
    matrix = [[ridge if i == j else 0.0 for j in range(13)] for i in range(13)]
    target = [0.0] * 13
    def add(x, y, weight):
        for i in range(13):
            target[i] += weight*x[i]*y
            for j in range(13): matrix[i][j] += weight*x[i]*x[j]
    for x, y in records.values(): add(x, y, 1/len(records))
    changes = []
    for (year, month), (x, y) in records.items():
        previous = records.get((year - 1, month))
        if previous:
            changes.append(([a-b for a,b in zip(x, previous[0])], y-previous[1]))
    for x,y in changes: add(x, y, change_weight/len(changes))
    return {'version': MODEL_VERSION, 'coefficients': _solve(matrix, target),
            'test_year': test_year, 'training_years': sorted({key[0] for key in records}),
            'training_months': len(records), 'change_pairs': len(changes),
            'change_weight': change_weight, 'ridge': ridge}


def predict(model, month, modis):
    x, _ = _features({'year': model['test_year'], 'month': month, 'modis': modis, 'reference': 0})
    log_prediction = sum(a*b for a,b in zip(x, model['coefficients']))
    if log_prediction > 700:
        raise ValueError('Model prediction is outside numeric range.')
    return max(0.0, math.expm1(log_prediction))


def synthetic_fold(rows, *, test_year, change_weight=1.0):
    """Evaluate one chronological fold on synthetic development fixtures only.

    This is not a scientific-release entry point. Real-data evaluation requires
    the separately approved research protocol and a reproducible release path.
    """
    import statistics
    if any(r.get('_synthetic_fixture') is not True for r in rows):
        raise ValueError('Development evaluation accepts explicitly marked synthetic fixtures only.')
    training=[r for r in rows if r['year'] < test_year-2]
    calibration=[r for r in rows if test_year-2 <= r['year'] < test_year]
    test=[r for r in rows if r['year']==test_year]
    if len({r['year'] for r in training})<3 or len(training)<36 or len(calibration)<18 or len(test)<8 or {((r['month']-1)//3) for r in test}!={0,1,2,3}:
        raise ValueError('Insufficient chronological support for this development fold.')
    keys=set()
    for row in rows:
        _features(row); key=(row['year'],row['month'])
        if key in keys: raise ValueError('Duplicate monthly input.')
        keys.add(key)
    cohorts={(r.get('region'),tuple(r.get('versions',()))) for r in rows}
    if len(cohorts)!=1: raise ValueError('Do not pool regions or product cohorts.')
    model=fit(training,test_year=test_year-2,change_weight=change_weight)
    total=sum(r['modis'] for r in training)
    ratio=sum(r['reference'] for r in training)/total if total else None
    month_ratios={}
    for month in range(1,13):
        group=[r for r in training if r['month']==month]
        denom=sum(r['modis'] for r in group)
        month_ratios[month]=sum(r['reference'] for r in group)/denom if denom >= 30 else ratio
    offset=statistics.mean(math.log1p(r['reference'])-math.log1p(r['modis']) for r in training)
    def predicted(name,row):
        x=row['modis']
        if name=='identity': return float(x)
        if name=='annual_ratio': return x*ratio if ratio is not None else None
        if name=='monthly_ratio':
            factor=month_ratios[row['month']]
            return x*factor if factor is not None else None
        if name=='fixed_offset': return max(0.0,math.expm1(math.log1p(x)+offset))
        return predict(model,row['month'],x)
    report={}
    for name in ('identity','annual_ratio','monthly_ratio','fixed_offset','change_aware'):
        if ratio is None and name in ('annual_ratio','monthly_ratio'):
            report[name]={'status':'unavailable','reason':'Zero MODIS training denominator.'}
            continue
        residuals=sorted(abs(math.log1p(r['reference'])-math.log1p(predicted(name,r))) for r in calibration)
        rank=min(len(residuals),math.ceil((len(residuals)+1)*0.90))
        width=residuals[rank-1]
        estimates=[predicted(name,r) for r in test]
        errors=[abs(math.log1p(r['reference'])-math.log1p(p)) for r,p in zip(test,estimates)]
        denom=sum(r['reference'] for r in test)
        prior={(r['year'],r['month']):r for r in calibration}
        changes=[]; matches=[]
        for r,p in zip(test,estimates):
            earlier=prior.get((r['year']-1,r['month']))
            if earlier:
                observed=math.log1p(r['reference'])-math.log1p(earlier['reference'])
                estimated=math.log1p(p)-math.log1p(predicted(name,earlier))
                changes.append(abs(estimated-observed))
                matches.append((estimated>0)-(estimated<0)==(observed>0)-(observed<0))
        covered=[abs(math.log1p(r['reference'])-math.log1p(p))<=width for r,p in zip(test,estimates)]
        report[name]={'median_absolute_log_error':statistics.median(errors),
            'weighted_absolute_percentage_error':sum(abs(r['reference']-p) for r,p in zip(test,estimates))/denom if denom else None,
            'median_absolute_log_change_error':statistics.median(changes) if changes else None,
            'direction_agreement':sum(matches)/len(matches) if matches else None,
            'change_pairs':len(changes),'zero_modis_test_months':sum(r['modis']==0 for r in test),
            'empirical_interval_coverage':sum(covered)/len(covered), 'log_interval_half_width':width,
            'predictions':[{'year':r['year'],'month':r['month'],'estimate':p} for r,p in zip(test,estimates)]}
    return {'status':'synthetic-development-only','test_year':test_year,
            'training_years':sorted({r['year'] for r in training}),'calibration_years':sorted({r['year'] for r in calibration}),
            'training_months':len(training),'calibration_months':len(calibration),'test_months':len(test),'models':report}
