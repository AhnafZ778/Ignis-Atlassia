"""Derive two-period comparisons from an existing monthly evidence bundle.

The estimates and observations are inherited from the frozen parent; no model
is refitted here. Same-calendar-month, exact-cohort pairs only.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
from collections import defaultdict

SCHEMA = 'fireatlas-finding-comparisons-v1'


def _measure(first, second):
    if first is None or second is None:
        return {'first': first, 'second': second, 'difference': None,
                'percent': None, 'direction': 'unavailable'}
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or
           not math.isfinite(v) or v < 0 for v in (first, second)):
        raise ValueError('Monthly values must be finite nonnegative numbers.')
    difference = second - first
    return {'first': first, 'second': second, 'difference': difference,
            'percent': difference / first * 100 if first else None,
            'direction': 'increase' if difference > 0 else 'decrease' if difference < 0 else 'unchanged'}


def derive(bundle):
    if bundle.get('schema') != 'fireatlas-comparability-bundle-v1':
        raise ValueError('Unsupported comparison evidence.')
    result = bundle['result']
    if result.get('schema') != 'fireatlas-monthly-comparability-v1':
        raise ValueError('Unsupported monthly result.')
    pairs = []
    for protocol in ('forward', 'nested'):
        grouped = defaultdict(list)
        for row in result.get('evaluation', {}).get(protocol, {}).get('rows', []):
            grouped[(row['month'], tuple(row['versions']))].append(row)
        for (month, versions), rows in sorted(grouped.items()):
            for a, b in itertools.combinations(sorted(rows, key=lambda r: r['year']), 2):
                if a['year'] == b['year']:
                    raise ValueError('Duplicate year and month.')
                series = {name: _measure(a.get(key), b.get(key)) for name, key in
                          (('modis', 'modis'), ('viirs', 'reference'), ('adjusted', 'prediction'))}
                directions = {item['direction'] for item in series.values() if item['direction'] != 'unavailable'}
                pairs.append({'protocol': protocol, 'month': month, 'years': [a['year'], b['year']],
                              'dates': [a['date'], b['date']], 'versions': list(versions),
                              'series': series, 'direction_differs': len(directions) > 1,
                              'models': [a.get('model'), b.get('model')],
                              'training_years': [a.get('training_years'), b.get('training_years')]})
    material = {'schema': SCHEMA, 'region': result['region'], 'unit': result['unit'],
                'parent_result_sha256': result['result_sha256'],
                'parent_input_sha256': result['input_sha256'],
                'parent_method': result['method_version'], 'pairs': pairs}
    material['result_sha256'] = hashlib.sha256(json.dumps(material, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return material


def published_pair(directory, region, month, first_year, second_year, expected_hash, selected_series='modis'):
    """Resolve exactly one published comparison by verified bytes and identity."""
    from pathlib import Path
    if region not in ('norcal','punjab-haryana') or selected_series not in ('modis','viirs','adjusted'):
        raise ValueError('Choose a supported region and series.')
    if any(type(x) is not int for x in (month,first_year,second_year)):
        raise ValueError('Choose a calendar month and two years.')
    path=Path(directory)
    manifest=json.loads((path/'manifest.json').read_text())
    name=region+'.json'
    content=(path/name).read_bytes()
    if manifest.get('schema')!='fireatlas-finding-publication-v1' or hashlib.sha256(content).hexdigest()!=manifest['files'][name]['sha256']:
        raise ValueError('The published comparison failed its manifest check.')
    data=json.loads(content)
    if data.get('schema')!=SCHEMA or data['region']['id']!=region or data.get('result_sha256')!=expected_hash:
        raise ValueError('The comparison changed; reload before saving.')
    hashed={k:v for k,v in data.items() if k not in ('result_sha256','source_file_sha256')}
    if hashlib.sha256(json.dumps(hashed,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()!=data['result_sha256']:
        raise ValueError('The published comparison result identity is invalid.')
    matches=[p for p in data['pairs'] if p['protocol']=='forward' and p['month']==month and p['years']==[first_year,second_year]]
    if len(matches)!=1:
        raise ValueError('This exact pair is not available in the published comparison.')
    return {'schema':'fireatlas-finding-investigation-v1','region':data['region'], 'unit':data['unit'],
            'publication_sha256':hashlib.sha256(content).hexdigest(),'result_sha256':data['result_sha256'],
            'parent_result_sha256':data['parent_result_sha256'],'parent_input_sha256':data['parent_input_sha256'],
            'parent_method':data['parent_method'],'selected_series':selected_series,'comparison':matches[0],
            'note':'Same-month change from the published forward-evaluation results; adjusted values are estimates.'}
