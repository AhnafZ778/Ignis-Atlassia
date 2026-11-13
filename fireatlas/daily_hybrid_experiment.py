"""Retrospective, unqualified daily hybrid research; never an estimate release.

This successor is separate from the frozen daily v2 experiment.  It compares
fixed rules, with each rule's intervals calibrated using only prior years.
The inspected historical record is exploratory, not blind confirmation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import daily_estimates as daily
from .calibration import _factor_for, _point_factors
from .comparability_v2 import bounds, interval_radius
from .qualification import digest
from .regions import REGIONS

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'fireatlas/protocols/daily-hybrid-v1.0.0.json'
AI_POLICY = ROOT / 'fireatlas/protocols/ai-daily-hybrid-v1.0.0.json'
BASELINES = ('no_harmonization', 'annual_ratio', 'monthly_ratio', 'hurdle_poisson')
CANDIDATES = ('zero_hurdle_annual', 'zero_hurdle_monthly')
MODELS = BASELINES + CANDIDATES
SEASONS = {'DJF': (12, 1, 2), 'MAM': (3, 4, 5), 'JJA': (6, 7, 8), 'SON': (9, 10, 11)}


def protocol():
    value = json.loads(PROTOCOL.read_text())
    for name, expected in value['source_sha256'].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Frozen experimental method source changed; a new protocol is required.')
    return {**value, 'protocol_sha256': digest(value)}


def experimental_review():
    """Bind this AI-only exploration to its protocol and recorded audit."""
    p = protocol()
    policy = json.loads(AI_POLICY.read_text())
    if policy.get('protocol_sha256') != p['protocol_sha256'] or policy.get('protocol_id') != p['id']:
        raise ValueError('Experimental policy does not match this frozen protocol.')
    for name, expected in policy['audit_sha256'].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Experimental audit bytes changed; a new policy is required.')
    return {'schema': 'fireatlas-ai-daily-hybrid-review-v1', 'policy': policy,
            'policy_sha256': digest(policy), 'human_authored': False,
            'independent_scientific_approval': False}


def _prediction(row, hurdle, ratio, month_factors):
    raw = {name: row['modis'] * _factor_for(name, ratio, month_factors, row['month'])
           for name in BASELINES[:-1]}
    raw['hurdle_poisson'] = hurdle
    raw['zero_hurdle_annual'] = hurdle if row['modis'] == 0 else raw['annual_ratio']
    raw['zero_hurdle_monthly'] = hurdle if row['modis'] == 0 else raw['monthly_ratio']
    return raw


def _scores(rows, model):
    return daily.scores([{**r, 'prediction': r['fixed'][model],
                          'interval': r['fixed_intervals'][model]} for r in rows])


def analyze(inputs, platform_counts, *, synthetic=False, experimental=None):
    p = protocol()
    if inputs.get('schema') != 'fireatlas-comparability-input-v1' or inputs.get('region') not in REGIONS:
        raise ValueError('Fixed-region comparability inputs are required.')
    if synthetic:
        if inputs.get('synthetic') is not True or experimental:
            raise ValueError('Synthetic fixtures must be explicitly labelled and remain separate.')
    elif (inputs.get('synthetic') not in (None, False) or not isinstance(experimental, dict)
          or digest(experimental) != digest(experimental_review())):
        raise ValueError('Authentic retrospective exploration must be explicitly requested.')
    rows = daily.eligible(inputs, platform_counts)
    policy = p['partition']
    predictions, folds, skipped = [], [], []
    for year in sorted({r['year'] for r in rows}):
        train = [r for r in rows if r['year'] < year - 2]
        cal = [r for r in rows if r['year'] in (year - 2, year - 1)]
        test = [r for r in rows if r['year'] == year]
        quarters = lambda group: {(r['month'] - 1) // 3 + 1 for r in group}
        if (len({r['year'] for r in train}) < 3 or len(train) < policy['minimum_training_days']
                or len(cal) < policy['minimum_calibration_days'] or quarters(cal) != {1, 2, 3, 4}
                or len(test) < policy['minimum_test_days'] or quarters(test) != {1, 2, 3, 4}):
            skipped.append({'year': year, 'reason': 'chronological-support-or-season-insufficient'})
            continue
        if any(sum((r['modis'] == 0) == zero for r in cal) < policy['minimum_calibration_per_stratum']
               for zero in (True, False)):
            skipped.append({'year': year, 'reason': 'calibration-stratum-insufficient'})
            continue
        ratio, factors = _point_factors(train)
        if ratio is None:
            skipped.append({'year': year, 'reason': 'ratio-denominator-zero'})
            continue
        try:
            fitted = daily.fit_predict(train, cal + test)
            fixed_cal = [_prediction(r, fitted['expected'][i], ratio, factors) for i, r in enumerate(cal)]
            radii = {m: {stratum: interval_radius([
                {'prediction': fixed_cal[i][m], 'reference': r['viirs']}
                for i, r in enumerate(cal) if ('zero' if r['modis'] == 0 else 'positive') == stratum])
                for stratum in ('zero', 'positive')} for m in MODELS}
        except (ValueError, ImportError, ArithmeticError, Warning) as exc:
            skipped.append({'year': year, 'reason': 'fit-or-calibration-unavailable', 'kind': type(exc).__name__})
            continue
        folds.append({'test_year': year, 'training_years': sorted({r['year'] for r in train}),
                      'training_dates': [r['date'] for r in train], 'calibration_years': [year - 2, year - 1],
                      'calibration_dates': [r['date'] for r in cal], 'test_dates': [r['date'] for r in test],
                      'calibration_counts': {s: sum((r['modis'] == 0) == (s == 'zero') for r in cal)
                                             for s in ('zero', 'positive')},
                      'radii': radii, 'hurdle_parameters': fitted['parameters'], 'environment': fitted['environment']})
        for i, row in enumerate(test, len(cal)):
            fixed = _prediction(row, fitted['expected'][i], ratio, factors)
            stratum = 'zero' if row['modis'] == 0 else 'positive'
            predictions.append({**row, 'reference': row['viirs'], 'stratum': stratum, 'fixed': fixed,
                                'fixed_intervals': {m: bounds(fixed[m], radii[m][stratum]) for m in MODELS},
                                'opportunity_state': 'unknown'})
    metrics = {m: _scores(predictions, m) for m in MODELS}
    zero = [r for r in predictions if r['modis'] == 0 and r['reference'] > 0]
    zero_metrics = {m: _scores(zero, m) for m in MODELS}
    seasonal = {s: {m: _scores([r for r in predictions if r['month'] in months], m) for m in MODELS}
                for s, months in SEASONS.items()}
    gates = p['gates']
    checks = {}
    for model in CANDIDATES:
        a = metrics[model]
        checks[model] = {'test_groups': len(folds) >= policy['minimum_test_groups'],
                         'zero_recovery_support': len(zero) >= policy['minimum_zero_recovery_test_days'],
                         'interval_coverage': a['coverage'] is not None and a['coverage'] >= gates['minimum_coverage']}
        # The original hurdle remains a reported comparator.  These two
        # candidates intentionally equal it whenever MODIS is zero, so asking
        # either to improve on it in that subset would be mathematically impossible.
        for baseline in BASELINES[:-1]:
            b = metrics[baseline]
            za, zb = zero_metrics[model]['median_absolute_log_error'], zero_metrics[baseline]['median_absolute_log_error']
            checks[model][baseline + '_log_improvement'] = (b['median_absolute_log_error'] is not None and
                b['median_absolute_log_error'] > 0 and a['median_absolute_log_error'] is not None and
                a['median_absolute_log_error'] <= b['median_absolute_log_error'] * (1 - gates['minimum_log_error_improvement']))
            checks[model][baseline + '_wape'] = (a['weighted_absolute_percentage_error'] is not None and
                b['weighted_absolute_percentage_error'] is not None and a['weighted_absolute_percentage_error'] <= b['weighted_absolute_percentage_error'])
            checks[model][baseline + '_interval_score'] = (a['interval_score'] is not None and b['interval_score'] is not None and a['interval_score'] <= b['interval_score'])
            checks[model][baseline + '_zero_improvement'] = (zb is not None and zb > 0 and za is not None and za <= zb * (1 - gates['minimum_zero_recovery_improvement']))
            checks[model][baseline + '_seasonal'] = all(
                seasonal[s][model]['weighted_absolute_percentage_error'] is not None and
                seasonal[s][baseline]['weighted_absolute_percentage_error'] is not None and
                seasonal[s][model]['weighted_absolute_percentage_error'] <= seasonal[s][baseline]['weighted_absolute_percentage_error'] * (1 + gates['maximum_seasonal_wape_degradation'])
                for s in SEASONS)
    result = {'schema': 'fireatlas-daily-hybrid-experiment-v1', 'protocol': p,
              'inputs': inputs, 'platform_counts': platform_counts, 'input_sha256': digest([inputs, platform_counts]),
              'region': inputs['region'], 'versions': inputs['versions'], 'synthetic': synthetic,
              'experimental_review': experimental,
              'folds': folds, 'skipped': skipped, 'rows': predictions, 'metrics': metrics,
              'zero_modis_positive_viirs': zero_metrics, 'seasonal': seasonal, 'checks': checks,
              'scientific_admission': False, 'estimates_admitted': False,
              'interpretation': 'Retrospective experimental comparisons only; previously inspected dates are not blind confirmation. '
                                'No independent review, coverage qualification, synthetic locations or daily release is implied.'}
    result['result_sha256'] = digest(result)
    return result


def verify(result):
    rebuilt = analyze(result['inputs'], result['platform_counts'], synthetic=result['synthetic'],
                      experimental=result['experimental_review'])
    if digest(rebuilt) != digest(result):
        raise ValueError('Daily hybrid experiment recount differs.')
    return {'verified': True, 'result_sha256': result['result_sha256'], 'estimates_admitted': False}
