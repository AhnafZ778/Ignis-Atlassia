"""Descriptive diagnostics for frozen held-out daily model predictions.

These are retrospective sensor-comparison diagnostics, not fire-truth accuracy,
independent review, uncertainty guarantees, or an admission decision.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import math

SEASONS = {'DJF': (12, 1, 2), 'MAM': (3, 4, 5), 'JJA': (6, 7, 8), 'SON': (9, 10, 11)}
MAX_ROWS = 200_000
MAX_COUNT = 1_000_000_000_000


def _quantile(values, probability):
    if not values:
        return None
    ordered=sorted(values)
    position=(len(ordered)-1)*probability
    lower=int(position);upper=math.ceil(position)
    return ordered[lower]+(ordered[upper]-ordered[lower])*(position-lower)


def _number(value, *, minimum=None, maximum=None):
    if isinstance(value,bool) or not isinstance(value,(int,float)):
        raise ValueError('Finite numeric held-out values are required.')
    try:finite=math.isfinite(value)
    except OverflowError:finite=False
    if not finite:raise ValueError('Finite numeric held-out values are required.')
    if minimum is not None and value<minimum or maximum is not None and value>maximum:
        raise ValueError('Held-out value is outside its supported range.')
    return value


def summarize(rows):
    n=len(rows)
    if not n:
        return {'n_utc_days':0,'test_year_groups':0,'reference_total':0,'expected_total':0.0,
                'mean_signed_error':None,'median_signed_error':None,'absolute_error_p90':None,
                'occurrence_brier':None,'mean_occurrence_probability':None,'observed_positive_fraction':None,
                'interval_coverage':None,'interval_mean_width':None,'interval_days':0,'interval_covered_days':0}
    residuals=[r['expected_count']-r['reference'] for r in rows]
    intervals=[r for r in rows if r['interval'] is not None]
    covered=sum(r['interval'][0]<=r['reference']<=r['interval'][1] for r in intervals)
    return {'n_utc_days':n,'test_year_groups':len({r['year'] for r in rows}),
            'reference_total':sum(r['reference'] for r in rows),'expected_total':sum(r['expected_count'] for r in rows),
            'mean_signed_error':sum(residuals)/n,'median_signed_error':_quantile(residuals,.5),
            'absolute_error_p90':_quantile([abs(v) for v in residuals],.9),
            'occurrence_brier':sum((r['probability_positive']-(r['reference']>0))**2 for r in rows)/n,
            'mean_occurrence_probability':sum(r['probability_positive'] for r in rows)/n,
            'observed_positive_fraction':sum(r['reference']>0 for r in rows)/n,
            'interval_coverage':covered/len(intervals) if intervals else None,
            'interval_mean_width':sum(r['interval'][1]-r['interval'][0] for r in intervals)/len(intervals) if intervals else None,
            'interval_days':len(intervals),'interval_covered_days':covered}


def analyze(result):
    if result.get('schema')!='fireatlas-daily-estimate-research-v2' or not isinstance(result.get('rows'),list):
        raise ValueError('Versioned held-out daily evidence is required.')
    if len(result['rows'])>MAX_ROWS:
        raise ValueError('Held-out daily evidence exceeds the row bound.')
    rows=[];seen=set()
    for row in result['rows']:
        if not isinstance(row,dict):raise ValueError('Held-out row is invalid.')
        stamp=row.get('date')
        try: day=date.fromisoformat(stamp)
        except (TypeError,ValueError):raise ValueError('Canonical UTC date required.') from None
        if day.isoformat()!=stamp or stamp in seen:raise ValueError('Duplicate or noncanonical UTC date.')
        seen.add(stamp)
        if type(row.get('year')) is not int or type(row.get('month')) is not int or row['year']!=day.year or row['month']!=day.month:raise ValueError('Held-out calendar labels differ.')
        for name in ('reference','modis'):
            if type(row.get(name)) is not int or not 0<=row[name]<=MAX_COUNT:raise ValueError('Bounded nonnegative integer sensor counts required.')
        expected=_number(row.get('expected_count'),minimum=0,maximum=MAX_COUNT)
        probability=_number(row.get('probability_positive'),minimum=0,maximum=1)
        interval=row.get('interval')
        if interval is not None:
            if not isinstance(interval,list) or len(interval)!=2:raise ValueError('A two-bound interval or null is required.')
            lo=_number(interval[0],minimum=0,maximum=MAX_COUNT);hi=_number(interval[1],minimum=lo,maximum=MAX_COUNT)
            interval=[lo,hi]
        rows.append({'date':stamp,'year':day.year,'month':day.month,'reference':row['reference'],
                     'modis':row['modis'],'expected_count':expected,'probability_positive':probability,'interval':interval})
    years=sorted({r['year'] for r in rows})
    return {'schema':'fireatlas-daily-heldout-diagnostics-v1','n_test_year_groups':len(years),
            'overall':summarize(rows),
            'by_test_year':{str(year):summarize([r for r in rows if r['year']==year]) for year in years},
            'by_season':{season:summarize([r for r in rows if r['month'] in months]) for season,months in SEASONS.items()},
            'by_modis_state':{'zero':summarize([r for r in rows if r['modis']==0]),
                              'positive':summarize([r for r in rows if r['modis']>0]),
                              'zero_modis_positive_viirs':summarize([r for r in rows if r['modis']==0 and r['reference']>0])},
            'scientific_admission':False,'daily_estimates_admitted':False,
            'interpretation':'Descriptive retrospective held-out sensor counts. Brier score uses observed VIIRS positive/zero, '
                             'not fire truth. The zero-MODIS/positive-VIIRS subset is selected using the reference outcome; its Brier score '
                             'is descriptive and is not a calibration assessment. Year groups are reported as dependence units; '
                             'no independent-cell confidence interval is claimed.'}
