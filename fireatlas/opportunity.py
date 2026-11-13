"""Candidate acquisition ledger and genuinely recomputed native pair diagnostics.

Centroid samples remain centroid samples. This pilot deliberately never creates a
full-cell opportunity denominator or a no_pass classification from missing data.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from functools import lru_cache
from datetime import datetime, timezone
import json
import random
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from .qualification import digest
from .validity import CASES
from .granules import PRODUCTS
from .masks import timestamp


def discover_product(case_id,product,version,role,*,opener=urlopen,max_pages=100):
    case=CASES[case_id]
    from datetime import date,timedelta
    end=(date.fromisoformat(case['end'])+timedelta(days=1)).isoformat()
    params={'short_name':product,'version':version,'temporal':f"{case['start']}T00:00:00Z,{end}T00:00:00Z",'bounding_box':','.join(map(str,case['bbox'])),'page_size':'2000','sort_key[]':['start_date','producer_granule_id']}
    url='https://cmr.earthdata.nasa.gov/search/granules.json?'+urlencode(params,doseq=True)
    token=None;tokens=set();ids=set();entries=[];pages=[];hits=None;reason=None
    for index in range(max_pages):
        headers={'CMR-Search-After':token} if token else {}
        with opener(Request(url,headers=headers),timeout=30) as response:
            body=response.read(16_000_001)
            if len(body)>16_000_000: raise ValueError('CMR page exceeds bounded metadata size.')
            count=int(response.headers['CMR-Hits']);next_token=response.headers.get('CMR-Search-After')
        page=json.loads(body)['feed']['entry'];pages.append({'page':index+1,'sha256':__import__('hashlib').sha256(body).hexdigest(),'entries':len(page),'hits':count})
        if hits is not None and hits!=count: reason='inventory-changed-during-pagination';break
        hits=count
        for entry in page:
            if entry['id'] in ids: reason='duplicate-cmr-id';break
            ids.add(entry['id'])
            links=[]
            for link in entry.get('links',[]):
                parts=urlsplit(link.get('href',''))
                if link.get('rel','').endswith('/data#') and parts.scheme=='https' and not parts.username and not parts.password and not parts.query:
                    links.append(link['href'])
            entries.append({'cmr_id':entry['id'],'producer_id':entry.get('producer_granule_id'),'start_utc':entry['time_start'],'end_utc':entry.get('time_end'),
                            'product':product,'version':version,'role':role,'collection_concept_id':entry.get('collection_concept_id'),
                            'candidate_geometry':{k:entry[k] for k in ('polygons','boxes','points','lines') if k in entry},
                            'orbit':entry.get('orbit_calculated_spatial_domains',[]),'platforms':entry.get('platforms',[]),'download_urls':links})
        if reason: break
        if len(entries)==hits: break
        if not page or not next_token: reason='pagination-ended-before-hit-count';break
        if next_token in tokens: reason='repeated-pagination-token';break
        tokens.add(next_token);token=next_token
    else: reason='pagination-limit'
    complete=reason is None and hits is not None and len(entries)==hits
    return {'product':product,'version':version,'role':role,'query':url,'cmr_hits':hits,'inventory_complete':complete,'incomplete_reason':reason,
            'pages':pages,'granules':sorted(entries,key=lambda r:(r['start_utc'],r['cmr_id']))}


def discover_case(case_id,*,opener=urlopen):
    products=[discover_product(case_id,*p,opener=opener) for p in PRODUCTS]
    return {'schema':'fireatlas-acquisition-inventory-v2','case_id':case_id,'retrieved_utc':datetime.now(timezone.utc).isoformat(),
            'inventory_complete':all(p['inventory_complete'] for p in products),'products':products,
            'interpretation':'Complete candidate search is not verified full-pass coverage. Native/geolocation and quality evidence are separate.'}


def ledger(case_id,inventory,native_inventory):
    if inventory.get('case_id')!=case_id: raise ValueError('Wrong-case candidate inventory.')
    native={g['producer_id']:g for g in native_inventory};groups=[]
    companion={'MOD14':'MOD03','MYD14':'MYD03','VNP14IMG':'VNP03IMG'}
    candidates=[g for p in inventory['products'] for g in p['granules']]
    for g in candidates:
        if g['product'] not in companion: continue
        source=native.get(g['producer_id'],{});geo=[c for c in candidates if c['product']==companion[g['product']] and c['start_utc']==g['start_utc']]
        orbit=g.get('orbit') or []
        # Orbit identity is kept as provider metadata, never upgraded to a complete pass.
        identity=digest([g.get('platforms'),orbit]) if orbit else g['cmr_id']
        groups.append({**g,'group_id':identity,'group_kind':'provider-orbit-candidate' if orbit else 'acquisition-group',
                       'native_status':source.get('status','missing'),'file_sha256':source.get('file_sha256'),'geolocation_sha256':source.get('geo_sha256'),
                       'geolocation_candidates':[x['producer_id'] for x in geo],
                       'missing_reasons':([] if source.get('status')=='processed' else ['native-file-not-processed'])+([] if geo else ['matching-geolocation-candidate-missing']),
                       'spatial_support':'candidate-granule-geometry; native classified pixels are centroids only',
                       'opportunity_state':'unknown','validated_no_pass':False})
    result={'schema':'fireatlas-opportunity-ledger-v2','case_id':case_id,'inventory_complete':inventory['inventory_complete'],
            'inventory_sha256':digest(inventory),'acquisitions':groups,'no_pass_enabled':False,'opportunity_denominator':None,
            'export_completeness':'separate source-export ledger','native_sampled_state':'available only where decoded native centroids exist',
            'unresolved':['Pixel footprint and quality geometry not qualified.','Independent positive, non-detection, cloud, unusable and verified no-pass examples pending.'],
            'interpretation':'Intervals without candidates remain unknown. Candidate footprints and centroid states do not establish full-cell clear/cloud/no-pass coverage.'}
    result['result_sha256']=digest(result);return result


@lru_cache(maxsize=50000)
def interval_distance(modis_start,modis_end,viirs_start,viirs_end):
    """Exact UTC differences shared by repeated cells; no matching is cached."""
    m=[timestamp(modis_start),timestamp(modis_end)];v=[timestamp(viirs_start),timestamp(viirs_end)]
    return max(abs((a-b).total_seconds()) for a in m for b in v)/60,abs((m[0]-v[0]).total_seconds())/60


def rematch(passes,tolerance):
    """Rerun eligibility and deterministic 1:1 matching at EACH tolerance."""
    if tolerance not in (30,60,90): raise ValueError('Use 30, 60 or 90 minutes.')
    groups=defaultdict(lambda:defaultdict(list))
    for p in passes:
        if p['state'] in ('detected','observed-without-detection'):
            groups[(p['grid_x'],p['grid_y'])][p['source_id']].append(p)
    output=[]
    for (x,y),sources in sorted(groups.items()):
        candidates=[]
        for m in sources['MODIS_SP']:
            for v in sources['VIIRS_SNPP_SP']:
                maximum,gap=interval_distance(m['start_utc'],m['end_utc'],v['start_utc'],v['end_utc'])
                if maximum<=tolerance:
                    candidates.append((gap,m['producer_id'],v['producer_id'],maximum,m,v))
        used_m=set();used_v=set()
        for gap,mid,vid,maximum,m,v in sorted(candidates,key=lambda c:c[:3]):
            if mid in used_m or vid in used_v: continue
            used_m.add(mid);used_v.add(vid)
            category='both_detected' if m['state']==v['state']=='detected' else 'modis_only' if m['state']=='detected' else 'viirs_only' if v['state']=='detected' else 'both_without_detection'
            conditions=[{'condition':'different-acquisition-times','evidence':[mid,vid],'start_gap_minutes':gap}] if gap else []
            output.append({'grid_x':x,'grid_y':y,'modis_granule':mid,'viirs_granule':vid,'modis_platform':m['platform'],'viirs_platform':v['platform'],
                           'date_utc':m['start_utc'][:10],'category':category,'start_gap_minutes':gap,'maximum_endpoint_gap_minutes':maximum,
                           'time_uncertainty':'granule interval; exact pixel acquisition time unavailable',
                           'evidence_hashes':[m['file_sha256'],m['geo_sha256'],v['file_sha256'],v['geo_sha256']],
                           'supported_conditions':conditions,'cause':'unresolved','opportunity_subset':'usable sampled centroids; full-cell opportunity unknown'})
    return output


def confusion(pairs):
    c=Counter(r['category'] for r in pairs);both=c['both_detected'];mu=both+c['modis_only'];vu=both+c['viirs_only'];union=mu+c['viirs_only']
    return {'n_pairs':len(pairs),**{k:c[k] for k in ('both_detected','modis_only','viirs_only','both_without_detection')},
            'positive_union_pairs':union,'positive_jaccard':both/union if union else None,
            'viirs_overlap_of_modis':{'numerator':both,'denominator':mu,'value':both/mu if mu else None},
            'modis_overlap_of_viirs':{'numerator':both,'denominator':vu,'value':both/vu if vu else None},
            'overall_agreement':(both+c['both_without_detection'])/len(pairs) if pairs else None}


def group_uncertainty(pairs,replicates=500):
    # Connected granule components keep all neighboring cells and reused passes
    # together. Pair IDs alone would split dependent shared-granule comparisons.
    parent={}
    def find(x):
        parent.setdefault(x,x)
        while parent[x]!=x: x=parent[x]
        return x
    for r in pairs:
        a,b=find(r['modis_granule']),find(r['viirs_granule']);parent[b]=a
    clusters=defaultdict(list)
    for r in pairs: clusters[find(r['modis_granule'])].append(r)
    result={'independent_groups':len(clusters),'method':'seeded bootstrap of connected acquisition-granule groups; descriptive not guaranteed temporal coverage','positive_jaccard_interval':None}
    if len(clusters)<3: result['reason']='fewer-than-three-acquisition-groups';return result
    # Jaccard depends only on category totals. Keep the identical group order,
    # random draws and integer counts without materializing every sampled cell
    # on each replicate; this is the same cluster bootstrap, not a new method.
    rng=random.Random(20261027);groups=[Counter(r['category'] for r in rows) for rows in clusters.values()];samples=[]
    for _ in range(replicates):
        counts=Counter()
        for group in rng.choices(groups,k=len(groups)):counts.update(group)
        union=sum(counts[k] for k in ('both_detected','modis_only','viirs_only'))
        metric=counts['both_detected']/union if union else None
        if metric is not None: samples.append(metric)
    if samples:
        samples.sort();result['positive_jaccard_interval']=[samples[int((len(samples)-1)*.05)],samples[int((len(samples)-1)*.95)]]
    return result


def diagnostics(passes):
    result={}
    for tolerance in (30,60,90):
        pairs=rematch(passes,tolerance)
        result[str(tolerance)]={'matching':'independently-recomputed deterministic greedy one-to-one within each grid cell',
                                'metrics':confusion(pairs),'group_uncertainty':group_uncertainty(pairs),'pairs':pairs,
                                'platforms':{p:confusion([r for r in pairs if r['modis_platform']==p]) for p in sorted({r['modis_platform'] for r in pairs})}}
    return {'schema':'fireatlas-native-rematching-v2','thresholds':result,'independent_review':'pending',
            'daynight_sensitivity':'Unavailable in this native evidence contract; no inferred day/night classifications',
            'interpretation':'Sampled-state agreement only; no fire-truth accuracy, validated opportunity denominator or causal attribution.'}


def sampled_sensitivity(passes):
    """Reaggregate native centroid class counts, then rematch each configuration."""
    from .masks import pass_state
    output=[]
    for scale in (1,2,4):
        for exclude_low in (False,True):
            grouped={}
            for p in passes:
                key=(p['producer_id'],p['grid_x']//scale,p['grid_y']//scale)
                if key not in grouped:grouped[key]={**p,'grid_x':key[1],'grid_y':key[2],'class_counts':Counter()}
                counts=Counter(p['class_counts'])
                if exclude_low and counts.get(7):counts[6]+=counts.pop(7)
                grouped[key]['class_counts'].update(counts)
            sampled=[]
            for p in grouped.values():sampled.append({**p,'state':pass_state(p['class_counts'])})
            for tolerance in (30,60,90):
                pairs=rematch(sampled,tolerance)
                output.append({'grid_metres':1000*scale,'exclude_low_confidence':exclude_low,'tolerance_minutes':tolerance,'metrics':confusion(pairs),
                               'spatial_support':'reaggregated native centroids, not pixel footprints','independent_review':'pending'})
    return output
