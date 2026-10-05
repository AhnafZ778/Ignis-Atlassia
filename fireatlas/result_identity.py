"""Stable identities for regional calculations; presentation wording is excluded."""
from __future__ import annotations
import hashlib
import json
from .provenance import sanitize_public_payload


def encoded(value):
    return json.dumps(sanitize_public_payload(value), sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def scientific_material(result):
    meta={key:value for key,value in result['meta'].items()
          if key not in {'verdict','result_sha256','release_id','bundle'}}
    return json.loads(encoded({'schema':result['schema'],'meta':meta,'days':result['days'],
            'months':[{key:value for key,value in item.items() if key!='verdict'} for item in result['months']],
            'calibration':result['calibration'],'availability':result['availability']}))


def identify_calendar(result, *, history_end=None, dependencies=None):
    if history_end is not None: result['meta']['period']['history_end']=history_end
    if dependencies is not None: result['meta']['dependencies']=dependencies
    result['meta']['release_id']=digest({'inputs':result['meta']['inputs'],
        'calibration_id':result['meta']['calibration_id'],
        'history_end':result['meta']['period'].get('history_end'),
        'dependencies':result['meta'].get('dependencies',{})})
    result['meta']['result_sha256']=digest(scientific_material(result))
    result['meta']['bundle']={'schema':'fireatlas-regional-study-v1','status':'local-service',
        'url':'api/v2/study','contract':'harmonized-activity'}
    return result
