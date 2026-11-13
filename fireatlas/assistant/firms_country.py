"""Recent country detections retrieved directly from NASA FIRMS."""
from __future__ import annotations

import csv
import gzip
import io
import json
import math
import re
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from .. import fetch
from ..settings import firms_key
from .contracts import digest, normalize_context
from .firms_history import (archive_summary, calendar_default, event_context, historical_period,
                           narrow_to_peak_month, peak_metric, peak_search_period, plan_history, recent_window,
                           requests_peak_month, window_readings)

PRODUCTS = {
    'VIIRS_NOAA20_NRT': ('NOAA-20 VIIRS', 'bright_ti4'),
    'VIIRS_NOAA21_NRT': ('NOAA-21 VIIRS', 'bright_ti4'),
    'VIIRS_SNPP_NRT': ('Suomi-NPP VIIRS', 'bright_ti4'),
    'MODIS_NRT': ('MODIS Terra/Aqua', 'brightness'),
}
LIMIT = 12000
METHOD = {'id': 'nasa-firms-country-area-nrt-v1', 'unit': 'detection records',
          'filter': 'NASA FIRMS near-real-time area readings for one product, filtered to a simplified Natural Earth country boundary. Brightness is channel brightness temperature (K).'}

def words(text):
    return ' '.join(re.findall(r'[a-z0-9]+', unicodedata.normalize('NFKD', text.casefold()).encode('ascii', 'ignore').decode()))

@lru_cache(maxsize=1)
def boundary_reference():
    path = Path(__file__).resolve().parents[1]/'samples/country_boundaries.json.gz'
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        return json.load(stream)

@lru_cache(maxsize=1)
def countries():
    entries = boundary_reference()['countries']
    return {words(alias):(code,item['names'][0]) for code,item in entries.items() for alias in item['names']}

def inside_ring(lon, lat, ring):
    inside = False
    previous_x,previous_y = ring[-1]
    for x,y in ring:
        if (y>lat)!=(previous_y>lat) and lon<(previous_x-x)*(lat-y)/(previous_y-y)+x:
            inside = not inside
        previous_x,previous_y = x,y
    return inside

def indexed_polygons(polygons):
    for outer,*holes in polygons:
        lon,lat=zip(*outer)
        yield (min(lon),min(lat),max(lon),max(lat)),outer,holes

def inside_country(lon,lat,polygons):
    return any(west<=lon<=east and south<=lat<=north and inside_ring(lon,lat,outer)
               and not any(inside_ring(lon,lat,hole) for hole in holes)
               for (west,south,east,north),outer,holes in polygons)

def is_heatmap_request(message):
    return bool(re.search(r'\bheat\s?maps?\b', message, re.I))

def request_candidate(message):
    return bool(re.search(r'\b(?:thermal (?:readings?|detections?|hotspots?|data|observations?)|fire (?:detections?|hotspots?)|active fires?|FIRMS|hotspots?|heat\s?maps?|satellite (?:readings?|detections?))\b',message,re.I)
                and re.search(r'\b(?:show|get|give|provide|fetch|bring|pull|plot|map|add|find|what|list|make|generate|create|draw|display)\b',message,re.I)
                and not re.search(r"\b(?:don't|do not|never|without)\b",message,re.I))

def resolve(message, place=None):
    from .board_views import requested_kinds, requests_heatmap_catalog
    from ..replay import CASES
    if not (request_candidate(message) or requested_kinds(message)) or requests_heatmap_catalog(message):
        return None
    if any(re.search(r'\b'+re.escape(key.split('-')[0])+r'\b', message,re.I) for key in CASES):
        return None
    # Only explicit country scope goes to NASA. A general explanation never does.
    normalized = words(message)
    locations = [m.end() for m in re.finditer(r'\b(?:in|for|from|over|of|across)\s+',normalized)]
    catalog = countries()
    by_code = {row[0].lower():row for row in catalog.values()}
    aliases = {'usa':'usa', 'us':'usa','united states':'usa','uk':'gbr','south korea':'kor',
               'north korea':'prk','russia':'rus','vietnam':'vnm','czech republic':'cze'}
    names = {**catalog, **by_code, **{name:by_code[code] for name,code in aliases.items() if code in by_code}}
    # Prefer the longest prefix at a location, then reject distinct countries.
    explicit=names.get(words(place or ''))
    found={explicit[0]:explicit} if explicit else {}
    for offset in locations:
        tail = re.sub(r'^the\s+', '', normalized[offset:])
        matches = [name for name in names if tail==name or tail.startswith(name+' ')]
        if matches:
            country = names[max(matches,key=len)]
            found[country[0]] = country
    if not found:
        return None
    if len(found)!=1 or re.search(r'\b(?:and|versus|vs)\s+(?:in\s+)?(?:'+'|'.join(re.escape(name) for name in catalog)+r')\b',normalized):
        raise ValueError('Ask for one country at a time so each board map has a clear source.')
    today=datetime.now(timezone.utc).date()
    history=peak_search_period(message,today) if requests_peak_month(message) else historical_period(message,today)
    if history is None and re.search(r'\byesterday\b',message,re.I):
        yesterday=datetime.now(timezone.utc).date()-timedelta(days=1)
        history=(yesterday,yesterday)
    period = re.search(r'\b(\d+)\s*days?\b',message,re.I)
    days = int(period[1]) if period else 1 if re.search(r'\b(today|last 24 hours)\b',message,re.I) else 3
    if history is None and not 1<=days<=5:
        raise ValueError('Choose a country window from 1 to 5 recent days.')
    sources = requested_products(message)
    if (len(sources)>1 and 'satellites' not in requested_kinds(message)) or re.search(r'\b(?:Landsat|GOES|Sentinel)\b',message,re.I):
        raise ValueError('Choose a supported country product: NOAA-20, NOAA-21, Suomi-NPP, or MODIS.')
    return next(iter(found.values())), history or days, sources[0] if sources else 'VIIRS_NOAA20_NRT'


def requested_products(message):
    patterns = {'VIIRS_NOAA20_NRT':r'NOAA[- ]?20','VIIRS_NOAA21_NRT':r'NOAA[- ]?21',
                'VIIRS_SNPP_NRT':r'S[- ]?NPP|Suomi','MODIS_NRT':r'MODIS'}
    return [source for source,pattern in patterns.items() if re.search(r'\b(?:'+pattern+r')\b',message,re.I)]


def read_area_records(content, band, cancel, deadline):
    reader = csv.DictReader(io.StringIO(content))
    required = {'latitude','longitude','acq_date','acq_time',band,'frp'}
    if not required.issubset(reader.fieldnames or ()):
        raise ValueError('NASA FIRMS did not return an area CSV. Check the server key and try a shorter window.')
    for row in reader:
        if cancel.is_set() or time.monotonic()>deadline:
            raise InterruptedError('Investigation stopped or timed out.')
        try:
            lat,lon,brightness = (float(row[field]) for field in ('latitude','longitude',band))
            frp = float(row['frp']) if row['frp'] else None
            day = date.fromisoformat(row['acq_date'])
            hhmm = row['acq_time'].zfill(4)
            clock = datetime.strptime(hhmm,'%H%M').time()
            if not (-90<=lat<=90 and -180<=lon<=180 and math.isfinite(brightness) and brightness>0 and (frp is None or math.isfinite(frp) and frp>=0)):
                raise ValueError()
        except (ValueError,TypeError,AttributeError):
            raise ValueError('NASA FIRMS returned an invalid area reading. No partial figure was saved.') from None
        yield {'latitude':lat,'longitude':lon,'brightness_k':brightness,'frp_mw':frp,
               'acquisition_utc':datetime.combine(day,clock,tzinfo=timezone.utc).isoformat(timespec='minutes')}


def answer(service, owner, request, cancel, deadline, *, heatmap=False, kinds=None, products=(), message=''):
    from .agent import guided_answer
    from .board_views import project_firms_views
    (code,name),period,product = request
    kinds = kinds or (('heatmap',) if heatmap else ('coordinates',))
    now=datetime.now(timezone.utc)
    if isinstance(period,int):
        period=calendar_default(message,kinds,now.date()) or period
    history=period if not isinstance(period,int) else None
    peak=requests_peak_month(message)
    if not peak and recent_window(history,now.date()) and not re.search(r'\bstandard[- ]processing\b',message,re.I):
        history=None
    key = firms_key()
    if not key:
        raise ValueError('Country readings need a NASA FIRMS map key on the server. Saved heatmaps are still available.')
    reference=boundary_reference()
    boundary=reference['countries'][code]
    west,south,east,north=boundary['bounds']
    if east-west>160 or south < -86 or north > 86:
        raise ValueError('This country needs multiple geographic windows. Ask for a country with a single bounded region.')
    polygons=list(indexed_polygons(boundary['polygons']))
    if history is not None:
        plans,catalog=plan_history(name,kinds,history,products or ((product,) if product!='VIIRS_NOAA20_NRT' else ()),PRODUCTS,peak=peak)
        if catalog:
            return catalog
        first,last=history
    else:
        first,last=period if isinstance(period,tuple) else (now.date()-timedelta(days=period-1),now.date())
        selected=(products or tuple(PRODUCTS)) if 'satellites' in kinds else (product,)
        if 'satellites' in kinds and len(selected)==1:
            raise ValueError('Choose at least two satellite products or ask for a reading calendar for one sensor.')
        plans=[(source,first,last) for source in selected]
    start,end=first.isoformat(),last.isoformat()
    checks=[]
    for source,lo,hi in plans:
        sensor,band=PRODUCTS[source.replace('_SP','_NRT')]
        checks.append(window_readings(key,source,sensor,band,boundary['bounds'],lo,hi,cancel,deadline,
                                     read_records=read_area_records,limit=3_000_000,row_limit=LIMIT,
                                     within=lambda lon,lat:inside_country(lon,lat,polygons)))
    if cancel.is_set():
        raise InterruptedError('Investigation stopped or timed out.')
    peak_info=None
    if peak:
        selection,clarification=narrow_to_peak_month(checks,first,last,peak_metric(message))
        if clarification:
            return clarification
        selected,first,last,peak_info,peak_note=selection
        checks=[selected]
        start,end=first.isoformat(),last.isoformat()
    primary=checks[0]
    rows,product,sensor,band=primary['records'],primary['product'],primary['sensor'],primary['band']
    context=normalize_context({'bbox':boundary['bounds'],'start':start,'end':end,'day':end,
                               'year':int(start[:4]),'month':int(start[5:7])})
    source_hash=primary['source_csv_sha256']
    lo,hi=primary['available_start'],primary['available_end']
    interval=lo if lo==hi else f'{lo} to {hi}'
    summary=f'{sensor} returned {len(rows):,} detections in {name} for {interval} UTC.'
    if len(checks)>1:
        summary=(f'{name}. '+', '.join(f"{item['sensor']}: {item['detections']:,}" for item in checks)
                 +' returned detections. Individual views use '+sensor+'.')
    if peak_info:
        summary+=peak_note
    events=None
    if history is not None:
        if any(check['available_start']!=start or check['available_end']!=end for check in checks):
            summary += ' Archive dates by product: '+', '.join(
                f"{check['sensor']} {check['available_start']} to {check['available_end']}" for check in checks)+'.'
        events,event_note=event_context(message,boundary['bounds'],first,last,cancel,deadline)
        summary += archive_summary(rows)+event_note
    payload={'country':name,'country_code':code,'product':product,'sensor':sensor,'requested_days':(last-first).days+1,
             'source_csv_sha256':source_hash,'checks':checks,'query_bbox':boundary['bounds'],
             'boundary_source':reference['source'],'boundary_sha256':digest(boundary),
             'retrieved_utc':now.isoformat(timespec='seconds'),'records':rows,'detections':len(rows),'band':band,
             'minimum_brightness_k':min((row['brightness_k'] for row in rows),default=None),
             'maximum_brightness_k':max((row['brightness_k'] for row in rows),default=None),
             'note':summary}
    if history is not None:
        payload['archive']=True
    if peak_info:
        payload['peak_selection']=peak_info
    if events:
        payload['event_context']=events
    if 'heatmap' in kinds or history is not None:
        payload['country_outline'] = [outer for _,outer,_ in polygons]
    receipt={'schema':'fireatlas-assistant-evidence-v1','operation':'firms_country','method':{**METHOD,'id':'nasa-firms-country-area-archive-v1',
                       'filter':'NASA FIRMS standard-processing area readings filtered to a simplified Natural Earth country boundary.'} if history is not None else METHOD,'context':context,
             'release_id':'nasa-firms-country:'+digest({'csv':[item['source_csv_sha256'] for item in checks],'boundary':payload['boundary_sha256']}),'release_frozen':False,'grid':'original coordinates',
             'payload':payload,'limitations':['Country filtering uses a simplified Natural Earth boundary; points close to borders may be classified differently at finer resolution. Brightness is satellite-channel temperature.']}
    receipt['sha256']=digest(receipt)
    identifier=service.store.artifact(owner,'evidence',receipt)
    response=guided_answer({'id':identifier,**receipt})
    response['kind']='Saved scientific view' if history is not None else 'Live NASA FIRMS'
    return project_firms_views(response,'firms_country',identifier,kinds,events['url'] if events else None,payload=payload,scope=context)
