"""Resolve a named place and query a bounded window of NASA FIRMS records."""
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import json
import math
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .. import fetch
from ..settings import firms_key
from .board_views import (AREA_VIEW_PATTERN, FIRMS_VIEWS, VIEW_NAMES, normalize_board_prompt,
                          positive_view_request, requested_kinds, requests_heatmap_catalog)
from .contracts import normalize_context
from .firms_country import PRODUCTS, LIMIT, countries, read_area_records, requested_products, words
from .regional_fire import publish_regional_map, sundarbans_scope
from .firms_history import (PEAK_QUERY, PEAK_SUFFIX, PERIOD_SUFFIX, archive_summary, calendar_default,
                           event_context, historical_period, narrow_to_peak_month, peak_metric, peak_search_period,
                           plan_history, recent_window, requests_peak_month, window_readings)

WINDOW_KM = 40


_LOCATOR = r'(?:in|for|of|over|near|around|across|from|at)'
_PLACE_WORDS = r"[^\W\d_][\w ,.'’()-]{1,99}"
_VIEW_SEPARATOR = r'\s*(?:[,;]|\+|&|\band\b|\bplus\b)\s*'
_PLACE_TAIL = (PERIOD_SUFFIX + '|' + PEAK_SUFFIX + rf'|{_VIEW_SEPARATOR}(?:also\s+)?(?:a\s+|the\s+)?{AREA_VIEW_PATTERN}'
               r'|\s+(?:(?:with|using)\s+(?:MODIS|VIIRS|NOAA|Suomi|S-?NPP)|and\s+(?:explain|tell|what|summari[sz]e)\b)')
_PLACE_ALIASES = {'dacca':'Dhaka','chittagong':'Chattogram','comilla':'Cumilla',
                  'jessore':'Jashore','barisal':'Barishal','bogra':'Bogura'}


def place_request(message):
    """Find one explicit place without guessing a missing geographic scope."""
    message=positive_view_request(message)
    if not any(kind in FIRMS_VIEWS['firms_region'] for kind in requested_kinds(message)) or requests_heatmap_catalog(message):
        return None
    visual=AREA_VIEW_PATTERN
    # Most requests name the place after one or more view types.
    located=re.search(visual + rf'\s*(?:[,;]\s*)?(?:(?:can|could) (?:you|I) (?:show|get|see)\s+|(?:are\s+)?available\s+)?{_LOCATOR}\s+(.+)',message,re.I)
    front=re.match(rf'{_LOCATOR}\s+(.+?),\s*(?=(?:(?:please|can|could|would|show|provide|give|pull|make|draw|display|need|want)\b|{visual}\b))',message,re.I)
    if front:
        candidate=front[1]
    elif located:
        candidate=located[1]
    else:
        separated=re.search(r'\s*[:—]\s*|\s+-{1,2}\s+',message)
        if separated:
            before,after=message[:separated.start()],message[separated.end():]
            candidate=after if requested_kinds(before) else before
        else:
            leading=re.match(rf'(?:(?:please\s+)?(?:(?:can|could|would) you\s+)?(?:show|provide|give|make|draw|display|get|pull|need|want)\s+)?(?:me\s+)?(?:a\s+|the\s+)?(?:close[- ]?up\s+)?(.+?)\s+{visual}\b',message,re.I)
            direct=re.match(rf'(?:{visual})(?:{_VIEW_SEPARATOR}{visual})*\s+(.+)',message,re.I)
            candidate=direct[1] if direct else leading[1] if leading else ''
    candidate=re.sub(rf"^(?:(?:the|its|(?:19|20|21)\d{{2}}'s)\s+)?{PEAK_QUERY}\s+{_LOCATOR}\s+",'',candidate,flags=re.I)
    candidate=re.sub(r'^(?:a|any) (?:wildfire|(?:forest )?fire)(?: that)?(?: happened| occurred)? (?:in|near|around) ','',candidate,flags=re.I)
    candidate=re.sub(r'^(?:19|20|21)\d{2}\s+','',candidate)
    place=re.split(_PLACE_TAIL,candidate,maxsplit=1,flags=re.I)[0].strip(' ,.;?!')
    place=re.sub(r'^the\s+|\s+(?:please|pls|plz|thanks|on (?:the|this) board)$','',place,flags=re.I)
    if not re.fullmatch(_PLACE_WORDS,place) or re.search(
        r'\b(?:a fire|a wildfire|this|these|my|selected|current|last|past|days|anywhere|everywhere|satellite|show|provide|need|want|please|readings?|heatmaps?|calendars?|between|where|document|csv|pdf|attached|what|which|when|pls|plz|today|yesterday)\b',place,re.I,
    ):
        return None
    if words(place) not in countries() and ',' not in place:
        # Preserve complete country names before considering a country qualifier.
        parts=place.split()
        for index in range(1,len(parts)):
            suffix=' '.join(parts[index:])
            if words(suffix) in countries():
                locality=' '.join(parts[:index])
                place=re.sub(r'\s+(?:in|of)$','',locality,flags=re.I)+', '+suffix.strip('()')
                break
    return place


def peak_calendar_question(message):
    match=re.fullmatch(rf"(?:when was|what(?: was)?|which(?: was)?|find|show(?: me)?)\s+(?:the\s+)?((?:(?:19|20|21)\d{{2}}'s\s+)?{PEAK_QUERY}\s+{_LOCATOR}\s+.+)",message,re.I)
    return 'Show the reading calendar for '+match[1] if match else message


def missing_place(message):
    remaining=re.sub(r'\b'+AREA_VIEW_PATTERN+r'\b',' ',positive_view_request(message),flags=re.I)
    remaining=re.sub(r'\b(?:please|pls|plz|can|could|would|you|I|show|add|bring|fetch|draw|display|plot|provide|give|get|make|pull|need|want|a|the|me|and|plus)\b',' ',remaining,flags=re.I)
    return not re.search(r'\w',remaining)


def conflicting_places(message):
    clauses=re.split(_VIEW_SEPARATOR,positive_view_request(message),maxsplit=8,flags=re.I)
    places={words(place) for clause in clauses if (place:=place_request(clause))}
    return len(places)>1


def place_followup(message, last_question):
    """Carry scope forward only when the last board request had a real location."""
    previous=normalize_board_prompt(last_question)
    previous_place=place_request(previous)
    kinds=[kind for kind in requested_kinds(previous) if kind in FIRMS_VIEWS['firms_region']]
    if not previous_place or not kinds:
        return None
    name=normalize_board_prompt(message).strip(' .?!')
    name=re.sub(r'^(?:(?:same|now) (?:for|in)|what about|how about)\s+|\s+(?:please|pls|plz)$','',name,flags=re.I)
    views=' and '.join(VIEW_NAMES[kind].lower() for kind in kinds)
    if re.fullmatch(r'(?:in\s+|for\s+)?(?:19|20|21)\d{2}(?:-\d{2}(?:-\d{2})?)?',name,re.I):
        date_text=re.sub(r'^(?:in|for)\s+','',name,flags=re.I)
        sensors=[PRODUCTS[source][0] for source in requested_products(previous)]
        sensor_text=' using '+' and '.join(sensors) if sensors else ''
        peak_text=''
        if requests_peak_month(previous):
            peak_text=' during its peak month' + (' by raw detections' if peak_metric(previous)=='detections' else '')
        return f'Show a {views} for {previous_place}{peak_text} on {date_text}{sensor_text}'
    if re.search(PERIOD_SUFFIX,name,re.I):
        expanded=f'Show a {views} for {name}'
        if place_request(expanded):
            return expanded
    if not re.fullmatch(r"[^\W\d_][\w.'’()-]*(?:[ ,]+[^\W\d_][\w.'’()-]*){0,4}",name):
        return None
    if re.search(r'\b(?:thanks|thank|hello|help|please|ok|okay|sure|yes|no|why|how|what|when|where|show|view|map|redo|undo|again|source|it|you)\b',name,re.I):
        return None
    # Retain an explicit date or sensor when switching only the location.
    if re.search(PERIOD_SUFFIX,previous,re.I) or requested_products(previous) or requests_peak_month(previous):
        pattern=re.escape(previous_place).replace(', ',r'(?:,\s*|\s+(?:in\s+)?)')
        updated,count=re.subn(r'(?<!\w)'+pattern+r'(?!\w)',lambda _:name,previous,count=1,flags=re.I)
        return updated if count else None
    return f'Show a {views} for {name}'


def place_followup_from_history(message, turns):
    previous=''
    for turn in turns:
        question=turn['question']
        previous=place_followup(question,previous) or question
    return place_followup(message,previous)


@lru_cache(maxsize=128)
def locate(place):
    name,*qualifiers = [part.strip() for part in place.split(',')]
    name=_PLACE_ALIASES.get(words(name),name)
    params = urlencode({'name':name,'count':25 if qualifiers else 8,'language':'en','format':'json'})
    try:
        request = Request('https://geocoding-api.open-meteo.com/v1/search?'+params, headers={'Accept':'application/json'})
        with urlopen(request, timeout=6) as response:
            data = json.loads(response.read(100_000))
    except (OSError, ValueError):
        raise ValueError('Place lookup is unavailable. Try the location again in a moment.') from None
    base = words(name)
    matches = [item for item in data.get('results', []) if words(item.get('name','')) == base]
    if qualifiers:
        qualifiers=set(map(words,qualifiers))
        matches=[item for item in matches if qualifiers <= {words(item.get(key) or '') for key in ('country','country_code','admin1','admin2','admin3','admin4')}]
    if not matches:
        return []
    settlements = [item for item in matches if item.get('feature_code','').startswith('PPL')]
    capitals = [item for item in settlements if item.get('feature_code') in {'PPLC','PPLA','PPLA2'}]
    populated=[item for item in settlements if (item.get('population') or 0)>0]
    return capitals or populated or settlements or matches


def place_answer(service, owner, place, message, cancel, deadline, kinds=None):
    kinds = kinds or requested_kinds(message) or ('heatmap',)
    now=datetime.now(timezone.utc).date()
    peak=requests_peak_month(message)
    history=peak_search_period(message,now) if peak else historical_period(message,now) or calendar_default(message,kinds,now)
    if re.search(r'\b(?:and|or|versus|vs)\b',place,re.I) and words(place) not in countries():
        return {'title':'Choose one location','kind':'Study clarification','claims':[],
                'summary':'Ask for one city or country at a time so each map uses a clear search area.'}
    region=sundarbans_scope(place)
    if region:
        label,bounds,reference=region
    else:
        matches = locate(place)
        if not matches:
            return {'title':'Location could not be resolved','kind':'Study clarification',
                    'summary':f'I couldn’t match “{place}” to a location. Include its country or administrative area.','claims':[]}
        if len(matches)>1:
            labels = list(dict.fromkeys(', '.join(dict.fromkeys(filter(None, (item['name'],item.get('admin1'),item.get('country')))))
                                        for item in matches))
            return {'title':'Choose a location','kind':'Study clarification',
                    'summary':'Several places match. Include the region or country to narrow the search.',
                    'view_options':[{'label':label,'detail':'FIRMS search around this location',
                        'question':re.sub(re.escape(place).replace(', ',r'(?:,\s*|\s+in\s+)'),lambda _:label,message,count=1,flags=re.I)} for label in labels[:4]],
                    'claims':[]}
        item = matches[0]
        latitude,longitude=float(item['latitude']),float(item['longitude'])
        if not (math.isfinite(latitude) and math.isfinite(longitude) and -85<latitude<85 and -180<longitude<180):
            raise ValueError('The location is outside the supported map area.')
        label = ', '.join(dict.fromkeys(filter(None, (item['name'], item.get('country')))))
        half_lat=WINDOW_KM/2/111.32
        half_lon=half_lat/math.cos(math.radians(latitude))
        bounds = [round(max(-180,longitude-half_lon),5),round(latitude-half_lat,5),
                  round(min(180,longitude+half_lon),5),round(latitude+half_lat,5)]
        reference={'name':item['name'],'latitude':latitude,'longitude':longitude,
                   'url':f'https://www.geonames.org/{int(item["id"])}','source':'GeoNames via Open-Meteo'}
    period = re.search(r'\b(\d+)\s*days?\b', message, re.I)
    days = int(period[1]) if period else 1 if re.search(r'\b(?:today|yesterday)\b',message,re.I) else 3
    if history is None and not 1<=days<=5:
        raise ValueError('For more than five days, request a year or explicit UTC dates.')
    products=requested_products(message)
    if (len(products)>1 and 'satellites' not in kinds) or re.search(r'\b(?:Landsat|GOES|Sentinel)\b',message,re.I):
        raise ValueError('Choose one supported product: MODIS, Suomi-NPP, NOAA-20, or NOAA-21.')
    key=firms_key()
    if not key:
        raise ValueError('A server-side NASA FIRMS map key is needed for this search.')
    # Keep an explicitly dated recent window on the existing live route.
    if not peak and recent_window(history,now) and not re.search(r'\bstandard[- ]processing\b',message,re.I):
        recent=history
        history=None
    elif history is None:
        end=now-timedelta(days=1) if re.search(r'\byesterday\b',message,re.I) else now
        recent=(end-timedelta(days=days-1),end)
    if history is not None:
        plans,catalog=plan_history(label,kinds,history,products,PRODUCTS,peak=peak)
        if catalog:
            return catalog
        first,last=history
    else:
        first,last=recent
        selected = products or (list(PRODUCTS) if 'satellites' in kinds else ['VIIRS_NOAA20_NRT'])
        if 'satellites' in kinds and len(selected)==1:
            raise ValueError('Choose at least two satellite products or ask for a reading calendar for one sensor.')
        plans=[(source,first,last) for source in selected]
    checks=[]
    for product,start,end in plans:
        sensor,band=PRODUCTS[product.replace('_SP','_NRT')]
        checks.append(window_readings(key,product,sensor,band,bounds,start,end,cancel,deadline,
                                     read_records=read_area_records,limit=800_000,row_limit=LIMIT))
    if cancel.is_set():
        raise InterruptedError('Investigation stopped.')
    peak_info=None
    if peak:
        selection,clarification=narrow_to_peak_month(checks,first,last,peak_metric(message))
        if clarification:
            return clarification
        selected,first,last,peak_info,peak_note=selection
        checks=[selected]
    primary=checks[0]
    product,sensor,records=primary['product'],primary['sensor'],primary['records']
    context=normalize_context({'bbox':bounds,'start':first.isoformat(),'end':last.isoformat(),'day':last.isoformat(),
                               'year':first.year,'month':first.month})
    lo,hi=primary['available_start'],primary['available_end']
    interval=lo if lo==hi else f'{lo} to {hi}'
    area=label if region else f'the roughly {WINDOW_KM} km search window around {label}'
    summary=f'{sensor} returned {len(records):,} detections in {area} for {interval} UTC.'
    if peak_info:
        summary+=peak_note
    payload={'title':label,'reference':reference,'product':product,'sensor':sensor,'checks':checks,
             'records':records,'note':summary}
    if peak_info:
        payload['peak_selection']=peak_info
    if len(checks)>1:
        summary=f'{label}. '+', '.join(f"{item['sensor']}: {item['detections']:,}" for item in checks)+' returned detections. Individual views use '+sensor+'.'
        payload['note']=summary
    if history is not None:
        payload['archive']=True
        if any(check['available_start']!=first.isoformat() or check['available_end']!=last.isoformat() for check in checks):
            payload['note'] += ' Archive dates by product: '+', '.join(
                f"{check['sensor']} {check['available_start']} to {check['available_end']}" for check in checks)+'.'
        events,event_note=event_context(message,bounds,first,last,cancel,deadline)
        payload['note'] += archive_summary(records)+event_note
        if events:
            payload['event_context']=events
    response=publish_regional_map(service,owner,context,payload,kinds=kinds)
    response['kind']='Live NASA FIRMS' if product.endswith('_NRT') else 'Saved scientific view'
    return response
