"""Evidence-backed sampled conditions around detections, never inferred causes."""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import datetime
import re
from .masks import timestamp,pass_state
from .qualification import digest
from .opportunity import interval_distance


def analyze(passes):
    """Rematch ALL sampled states independently for each time tolerance.

    Cloud and unknown observations are retained here, and are never included in
    a usable-pair confusion table or an observation-opportunity denominator.
    """
    if not isinstance(passes,list) or len(passes)>500000:raise ValueError('Bounded native pass inputs required.')
    groups=defaultdict(lambda:defaultdict(list));seen=set();normalized=[]
    for p in passes:
        if p.get('source_id') not in ('MODIS_SP','VIIRS_SNPP_SP') or not all(type(p.get(k)) is int for k in ('grid_x','grid_y')):raise ValueError('Exact supported source and grid required.')
        counts=p.get('class_counts')
        if not isinstance(counts,dict) or any(str(k) not in tuple(map(str,range(10))) or type(v) is not int or v<=0 for k,v in counts.items()):raise ValueError('Positive original native mask-class counts required.')
        counts={int(k):v for k,v in counts.items()}
        if p.get('state')!=pass_state(counts):raise ValueError('Sampled state differs from original mask-class counts.')
        for field in ('file_sha256','geo_sha256'):
            if not isinstance(p.get(field),str) or not re.fullmatch('[0-9a-f]{64}',p[field]):raise ValueError('Original native/geolocation hashes required.')
        for field in ('start_utc','end_utc'):
            value=datetime.fromisoformat(p[field].replace('Z','+00:00'))
            if value.tzinfo is None or value.utcoffset().total_seconds()!=0:raise ValueError('Acquisition intervals must be UTC.')
        if timestamp(p['end_utc'])<timestamp(p['start_utc']):raise ValueError('Acquisition interval is reversed.')
        p={**p,'class_counts':counts};normalized.append(p)
        key=(p['producer_id'],p['grid_x'],p['grid_y'])
        if key in seen:raise ValueError('Duplicate native sampled acquisition/cell.')
        seen.add(key)
        if p['state'] not in ('detected','observed-without-detection','cloud-obscured','unknown'):raise ValueError('Unknown native sample state.')
        groups[(p['grid_x'],p['grid_y'])][p['source_id']].append(p)
    experiments={}
    for tolerance in (30,60,90):
        pairs=[];state_counts=Counter();total=0
        for (x,y),sources in sorted(groups.items()):
            candidates=[]
            for m in sources['MODIS_SP']:
                for v in sources['VIIRS_SNPP_SP']:
                    maximum,gap=interval_distance(m['start_utc'],m['end_utc'],v['start_utc'],v['end_utc'])
                    if maximum<=tolerance:
                        candidates.append((gap,m['producer_id'],v['producer_id'],maximum,m,v))
            used_m=set();used_v=set()
            for gap,mid,vid,maximum,m,v in sorted(candidates,key=lambda c:c[:3]):
                if mid in used_m or vid in used_v:continue
                used_m.add(mid);used_v.add(vid);total+=1;state_counts[m['state']+' / '+v['state']]+=1
                if 'detected' not in (m['state'],v['state']):continue
                conditions=[]
                for label,p in [('MODIS',m),('VIIRS',v)]:
                    if p['state']=='cloud-obscured':conditions.append({'condition':'cloud-mask-in-sampled-native-pixels','sensor':label,'granule':p['producer_id'],'class_counts':p['class_counts']})
                    elif p['state']=='unknown':conditions.append({'condition':'mixed-or-unusable-native-sample','sensor':label,'granule':p['producer_id'],'class_counts':p['class_counts']})
                if gap:conditions.append({'condition':'different-acquisition-intervals','start_gap_minutes':gap,'granules':[mid,vid]})
                conditions.append({'condition':'different-native-spatial-support','MODIS':'1km nominal native pixel; scan-dependent footprint','VIIRS':'375m nominal native pixel; scan-dependent footprint','explanation':'Instrument context, not an assigned cause.'})
                pairs.append({'grid_x':x,'grid_y':y,'modis_granule':mid,'viirs_granule':vid,'modis_platform':m['platform'],'viirs_platform':v['platform'],
                    'modis_state':m['state'],'viirs_state':v['state'],'modis_interval':[m['start_utc'],m['end_utc']],'viirs_interval':[v['start_utc'],v['end_utc']],
                    'maximum_endpoint_gap_minutes':maximum,'start_gap_minutes':gap,'modis_class_counts':{str(k):c for k,c in sorted(m['class_counts'].items())},'viirs_class_counts':{str(k):c for k,c in sorted(v['class_counts'].items())},
                    'evidence_hashes':{'modis_native':m['file_sha256'],'modis_geo':m['geo_sha256'],'viirs_native':v['file_sha256'],'viirs_geo':v['geo_sha256']},
                    'supported_conditions':conditions,'physical_cause':'unresolved','full_cell_opportunity':'unknown','exact_pixel_acquisition_time':'unavailable; granule intervals retained'})
        experiments[str(tolerance)]={'matching':'independently recomputed all-state closest-start deterministic one-to-one per sampled cell','all_matched_sample_pairs':total,'sampled_state_matrix':dict(sorted(state_counts.items())),
            'positive_sample_pairs':len(pairs),'positive_pairs_with_cloud_sample':sum('cloud-obscured' in (r['modis_state'],r['viirs_state']) for r in pairs),
            'positive_pairs_with_unknown_sample':sum('unknown' in (r['modis_state'],r['viirs_state']) for r in pairs),'pairs':pairs}
    value={'schema':'fireatlas-native-disagreement-conditions-v1','native_input_sha256':digest(normalized),'experiments':experiments,
        'interpretation':'Documented sampled conditions, not validated physical causes. All-state matches have different denominators from usable-only confusion metrics. Adjacent cells and acquisitions are dependent. Full-cell coverage and between-pass fire activity remain unknown.'}
    value['result_sha256']=digest(value);return value


def verify(value,passes):
    if digest(analyze(passes))!=digest(value):raise ValueError('Native condition recount differs.')
    return {'verified':True,'result_sha256':value['result_sha256']}
