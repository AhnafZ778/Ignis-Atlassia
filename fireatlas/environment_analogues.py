"""Deterministic spatial analogue ranking for one bounded environmental pilot."""
from __future__ import annotations
import math, statistics

SCHEMA='fireatlas-environment-matches-v1'

def matches(data, cell_id, limit=5):
    if data.get('schema')!='fireatlas-environment-analogues-v1':raise ValueError('Unsupported input.')
    cells=data['cells'];by_id={c['id']:c for c in cells}
    if len(by_id)!=len(cells) or cell_id not in by_id:raise ValueError('Choose an available cell.')
    if type(limit)!=int or not 1<=limit<=10:raise ValueError('Choose 1–10 matches.')
    for c in cells:
        if any(type(c[k]) not in (int,float) or not math.isfinite(c[k]) for k in ('ndvi_median','elevation_median_m')):raise ValueError('Missing environmental measurement.')
    def scale(key):
        seq=sorted(c[key] for c in cells);q=statistics.quantiles(seq,n=4,method='inclusive');return max(q[2]-q[0],1e-9)
    a,b=scale('ndvi_median'),scale('elevation_median_m');target=by_id[cell_id]
    row,col=map(int,cell_id.split('-'));ranked=[]
    for c in cells:
        y,x=map(int,c['id'].split('-'))
        if abs(row-y)<=1 and abs(col-x)<=1:continue
        nd=abs(c['ndvi_median']-target['ndvi_median'])/a; elev=abs(c['elevation_median_m']-target['elevation_median_m'])/b
        distance=math.sqrt((nd*nd+elev*elev)/2)
        ranked.append({'cell_id':c['id'],'distance':round(distance,6),'ndvi_component':round(nd,6),'elevation_component':round(elev,6)})
    ranked.sort(key=lambda x:(x['distance'],x['cell_id']))
    return {'target':cell_id,'matches':ranked[:limit],'scales':{'ndvi_iqr':a,'elevation_iqr_m':b},'method':'Equal-weight Euclidean distance after dividing each feature by its pilot-wide interquartile range; immediately adjacent cells excluded.'}


def resolve_publication(directory, cell_id, expected_hash):
    import hashlib, json
    from pathlib import Path
    path=Path(directory);manifest=json.loads((path/'manifest.json').read_text());raw=(path/'park.json').read_bytes();actual=hashlib.sha256(raw).hexdigest()
    if manifest.get('schema')!='fireatlas-environment-publication-v1' or manifest['files']['park.json']['sha256']!=actual or expected_hash!=actual:
        raise ValueError('Environmental data changed; reload the study.')
    data=json.loads(raw);ranking=matches(data,cell_id);lookup={c['id']:c for c in data['cells']}
    return {'schema':'fireatlas-environment-investigation-v1','target':lookup[cell_id], 'matches':[{**lookup[m['cell_id']],**m} for m in ranking['matches']], 'method':ranking['method'],'scales':ranking['scales'],'source_sha256':actual,'inputs':data['inputs'],'feature_window':data['feature_window'],'outcome_window':data['outcome_window'],'outcome_source':data['outcome_source'],'note':data['note']}

def context_publication(directory):
    """Read the existing published environmental grid with its exact file identity."""
    import hashlib, json
    from pathlib import Path
    directory=Path(directory)
    manifest=json.loads((directory/'manifest.json').read_text())
    data_bytes=(directory/'park.json').read_bytes()
    identity=manifest['files']['park.json']
    actual=hashlib.sha256(data_bytes).hexdigest()
    if identity['sha256']!=actual or identity['bytes']!=len(data_bytes):
        raise ValueError('The environmental publication failed its hash check.')
    data=json.loads(data_bytes)
    cells=data.get('cells')
    if not isinstance(cells,list) or not cells:
        raise ValueError('The environmental grid is unavailable.')
    for cell in cells:
        if any(type(cell.get(key)) not in (int,float) or not math.isfinite(cell[key]) for key in ('ndvi_median','elevation_median_m')):
            raise ValueError('An environmental measurement is unavailable.')
    return {**data,'source_sha256':actual,'cell_count':len(cells),
            'note':data.get('note','')+' Measured context does not establish causal impact; weather and human activity are not included.'}
