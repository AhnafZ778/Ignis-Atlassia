"""Retrospective similar-day daily research; never admits a daily product.

Only earlier training dates provide reference counts. The two subsequent years
calibrate intervals; held-out years are evaluated but never used for fitting.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import sys
from datetime import date
from pathlib import Path

from . import daily_estimates as daily, daily_hybrid_experiment as hybrid
from .comparability_v2 import bounds, interval_radius
from .qualification import digest

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'fireatlas/protocols/daily-neighbors-v1.0.0.json'
MODEL = 'similar_day_mean'


def protocol():
    spec = json.loads(PROTOCOL.read_text())
    for name, expected in spec['source_sha256'].items():
        path = (ROOT / name).resolve(strict=True)
        if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Frozen similar-day method changed; a new protocol is required.')
    return {**spec, 'protocol_sha256': digest(spec)}


def features(row):
    day = date.fromisoformat(row['date'])
    days = 366 if day.replace(month=12, day=31).timetuple().tm_yday == 366 else 365
    phase = 2 * math.pi * (day.timetuple().tm_yday - 1) / days
    return [math.log1p(row['modis']), 0.25 * math.log1p(row['terra']),
            0.25 * math.log1p(row['aqua']), math.sin(phase), math.cos(phase)]


def predict(train, target, k=64):
    """Mean observed VIIRS activity among k nearest training dates.

    Ties use chronological input order, which the caller fixes by date. No
    reference value from a prediction date enters its features or prediction.
    """
    import numpy as np
    if type(k) is not int or k < 1 or len(train) < k:
        raise ValueError('Insufficient earlier training dates for fixed neighbors.')
    train = sorted(train, key=lambda r: r['date'])
    if len({r['date'] for r in train}) != len(train):
        raise ValueError('Duplicate training dates.')
    x = np.asarray([features(r) for r in train], dtype=float)
    values = np.asarray([r['viirs'] for r in train], dtype=float)
    if not np.isfinite(x).all() or not np.isfinite(values).all() or (values < 0).any():
        raise ValueError('Finite non-negative training values required.')
    estimates, probabilities = [], []
    order = np.arange(len(train))
    for row in target:
        point = np.asarray(features(row), dtype=float)
        if not np.isfinite(point).all():
            raise ValueError('Finite prediction features required.')
        distance = ((x - point) ** 2).sum(axis=1)
        nearest = np.lexsort((order, distance))[:k]
        selected = values[nearest]
        estimates.append(float(selected.mean()))
        probabilities.append(float((selected > 0).mean()))
    return {'expected': estimates, 'probability_positive': probabilities}


def analyze(inputs, platform_counts, *, synthetic=False, experimental=None):
    spec = protocol()
    # The existing, separately frozen hybrid research carries the same dates,
    # eligibility, baselines, strata and original review policy.
    base = hybrid.analyze(inputs, platform_counts, synthetic=synthetic, experimental=experimental)
    eligible = daily.eligible(inputs, platform_counts)
    by_year = {}
    for row in base['rows']:
        by_year.setdefault(row['year'], []).append(row)
    result_rows, folds = [], []
    for fold in base['folds']:
        year = fold['test_year']
        train = [r for r in eligible if r['year'] < year - 2]
        cal = [r for r in eligible if r['year'] in (year - 2, year - 1)]
        test = by_year[year]
        predicted = predict(train, cal + test, k=spec['neighbors'])
        radii = {}
        for stratum in ('zero', 'positive'):
            calibration = [{'prediction': predicted['expected'][i], 'reference': r['viirs']}
                           for i, r in enumerate(cal) if ('zero' if r['modis'] == 0 else 'positive') == stratum]
            if len(calibration) < spec['minimum_calibration_per_stratum']:
                raise ValueError('Baseline fold has insufficient calibration support.')
            radii[stratum] = interval_radius(calibration)
        folds.append({'test_year': year, 'training_dates': [r['date'] for r in train],
                      'calibration_dates': [r['date'] for r in cal],
                      'test_dates': [r['date'] for r in test], 'radii': radii})
        for i, row in enumerate(test, len(cal)):
            prediction = predicted['expected'][i]
            result_rows.append({**row, 'fixed': {**row['fixed'], MODEL: prediction},
                'fixed_intervals': {**row['fixed_intervals'], MODEL: bounds(prediction, radii[row['stratum']])},
                'similar_day_probability_positive': predicted['probability_positive'][i]})
    models = hybrid.MODELS + (MODEL,)
    metrics = {m: hybrid._scores(result_rows, m) for m in models}
    zero = [r for r in result_rows if r['modis'] == 0 and r['reference'] > 0]
    zero_metrics = {m: hybrid._scores(zero, m) for m in models}
    seasonal = {s: {m: hybrid._scores([r for r in result_rows if r['month'] in months], m)
                    for m in models} for s, months in hybrid.SEASONS.items()}
    calibration = []
    for index in range(5):
        low, high = index / 5, (index + 1) / 5
        group = [r for r in result_rows if low <= r['similar_day_probability_positive']
                 and (r['similar_day_probability_positive'] < high or
                      (index == 4 and r['similar_day_probability_positive'] == 1))]
        count = len(group)
        calibration.append({'probability_bin': [low, high], 'n': count,
            'mean_probability': sum(r['similar_day_probability_positive'] for r in group) / count if count else None,
            'observed_positive_fraction': sum(r['reference'] > 0 for r in group) / count if count else None})
    occurrence_brier = (sum((r['similar_day_probability_positive'] - (r['reference'] > 0)) ** 2
                            for r in result_rows) / len(result_rows) if result_rows else None)
    gates = spec['gates'];candidate = metrics[MODEL]
    checks = {'test_groups': len(folds) >= 3, 'zero_recovery_support': len(zero) >= 30,
              'interval_coverage': candidate['coverage'] is not None and candidate['coverage'] >= gates['minimum_coverage']}
    for baseline in hybrid.BASELINES:
        b, a_zero, b_zero = metrics[baseline], zero_metrics[MODEL], zero_metrics[baseline]
        a_log, b_log = candidate['median_absolute_log_error'], b['median_absolute_log_error']
        za, zb = a_zero['median_absolute_log_error'], b_zero['median_absolute_log_error']
        checks[baseline + '_log_improvement'] = b_log is not None and b_log > 0 and a_log is not None and a_log <= b_log * (1-gates['minimum_log_error_improvement'])
        checks[baseline + '_wape'] = candidate['weighted_absolute_percentage_error'] is not None and b['weighted_absolute_percentage_error'] is not None and candidate['weighted_absolute_percentage_error'] <= b['weighted_absolute_percentage_error']
        checks[baseline + '_interval_score'] = candidate['interval_score'] is not None and b['interval_score'] is not None and candidate['interval_score'] <= b['interval_score']
        checks[baseline + '_zero_improvement'] = zb is not None and zb > 0 and za is not None and za <= zb * (1-gates['minimum_zero_recovery_improvement'])
        checks[baseline + '_seasonal'] = all(seasonal[s][MODEL]['weighted_absolute_percentage_error'] is not None and seasonal[s][baseline]['weighted_absolute_percentage_error'] is not None and seasonal[s][MODEL]['weighted_absolute_percentage_error'] <= seasonal[s][baseline]['weighted_absolute_percentage_error'] * (1+gates['maximum_seasonal_wape_degradation']) for s in hybrid.SEASONS)
    result = {'schema': 'fireatlas-daily-neighbors-experiment-v1', 'protocol': spec,
              'region': base['region'], 'versions': base['versions'], 'synthetic': synthetic,
              'input_sha256': base['input_sha256'], 'baseline_result_sha256': base['result_sha256'],
              'baseline_protocol': base['protocol'],
              'environment': {'python': sys.version.split()[0], **{name: importlib.metadata.version(name)
                              for name in ('numpy', 'scipy', 'pandas', 'statsmodels')}},
              'inputs': inputs, 'platform_counts': platform_counts, 'experimental_review': experimental,
              'folds': folds, 'baseline_folds': base['folds'], 'skipped': base['skipped'],
              'occurrence_calibration': calibration, 'occurrence_brier': occurrence_brier,
              'rows': result_rows, 'metrics': metrics,
              'zero_modis_positive_viirs': zero_metrics, 'seasonal': seasonal, 'checks': checks,
              'scientific_admission': False, 'estimates_admitted': False,
              'interpretation': 'Previously inspected dates are retrospective development evidence. Similar-day averages estimate observed sensor activity; they do not establish fire truth, observation opportunity, scientific approval or a daily release.'}
    result['result_sha256'] = digest(result)
    return result


def verify(result):
    rebuilt = analyze(result['inputs'], result['platform_counts'], synthetic=result['synthetic'],
                      experimental=result['experimental_review'])
    if digest(rebuilt) != digest(result):
        raise ValueError('Similar-day experiment recount differs.')
    return {'verified': True, 'result_sha256': result['result_sha256'], 'estimates_admitted': False}
