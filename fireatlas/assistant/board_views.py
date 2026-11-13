"""Typed, source-backed whiteboard views. Rendering never invents measurements."""
from __future__ import annotations
import re
import unicodedata
from collections import Counter
from datetime import date, timedelta
from .contracts import normalize_context
from ..replay import CASES

VIEW_OPERATIONS = {
    'regional-comparison': 'regional_comparison',
    'firms-region-heatmap':'firms_region', 'firms-country':'firms_country', 'firms-country-heatmap':'firms_country', 'heatmap':'replay', 'coordinates':'observations', 'satellites':'replay',
    'similar':'similar_patterns', 'calendar':'calendar', 'archive':'archive_search', 'factors':'environment_context', 'analogues':'environment_analogues', 'park-satellites':'park_platforms',
}

# User-facing view vocabulary. Order within a response follows the prompt.
_VIEW_TERMS = {
    'heatmap': r'heat\s?maps?',
    'calendar': r'(?:readings?\s+)?calendars?|daily\s+(?:readings?|detections?)',
    'coordinates': r'coordinate(?:s|\s+maps?)|point\s+maps?|original\s+(?:locations|coordinates)|(?:hotspot|detection)\s+locations',
    'satellites': r'satellite\s+(?:comparison|charts?|counts?|observations)|different\s+satellites',
    'readings': r'(?:reading(?:s)?(?=\s*(?:[,.:?!+&]|$|(?:and|plus|can|for|in|of|over|near|around|across|from)\b)))|(?:historical|archived)\s+(?:readings?|observations?|records?|detections?|data)|(?:raw\s+)?(?:thermal|satellite|FIRMS)\s+(?:readings?|data)|readings?\s+table|raw\s+records?|thermal\s+(?:detections?|hotspots?)|(?:fire\s+)?hotspots?',
    'archive': r'(?:historical|archive)\s+(?:windows|search)',
    'similar': r'(?:similar|related)\s+(?:fires|events|profiles)',
    'factors': r'(?:NDVI|elevation|environmental|measured)\s+(?:maps?|factors)|factor\s+maps?',
    'analogues': r'environmental\s+(?:analogues|matches)',
    'harmonized': r'harmoni[sz]ed\s+(?:calendar|reading|readings|counts|activity)',
    'comparability': r'(?:monthly\s+)?comparability(?:\s+results)?|held.out\s+comparison',
    'missingness': r'(?:missing|unavailable)\s+(?:dates|days)|export\s+(?:status|gaps)',
    'persistence': r'(?:detection\s+)?persistence(?:\s+summary)?|repeatedly\s+observed\s+cells',
    'inventory': r'(?:source|sensor|archive)\s+inventory',
    'overlap': r'(?:sensor|monthly)\s+overlap',
    'coverage': r'(?:observation|satellite)\s+coverage',
    'validation': r'(?:study\s+)?validation\s+(?:gates|checks|results)',
}
VIEW_NAMES = {
    'heatmap':'Heatmap', 'calendar':'Reading calendar', 'coordinates':'Coordinate map',
    'satellites':'Satellite comparison', 'readings':'Reading table', 'archive':'Archive windows',
    'similar':'Similar profiles', 'factors':'Measured factors', 'analogues':'Environmental matches',
    'harmonized':'Harmonized comparison', 'comparability':'Monthly comparability',
    'missingness':'Export status', 'persistence':'Persistence summary',
    'inventory':'Source inventory','overlap':'Sensor overlap','coverage':'Coverage summary','validation':'Validation checks',
}
AREA_VIEW_PATTERN = r'(?:'+'|'.join(_VIEW_TERMS[kind] for kind in ('heatmap','calendar','coordinates','satellites','readings'))+r')'
_VIEW_ACTION = r'\b(?:show|add|bring|fetch|create|draw|display|plot|compare|provide|give|get|make|generate|find|pull|list|need|want|load|render)\b'


def normalize_board_prompt(message):
    """Normalize chart words and punctuation while preserving place names and dates."""
    text=unicodedata.normalize('NFKC',str(message or '')).translate(str.maketrans({'’':"'",'−':'-','–':'-','—':' — ','‑':'-'}))
    text=' '.join(text.split())
    text=re.sub(r'\b(?:heat[ -]+maps?|haetmaps?|heatmapps?|heatmpas?)\b',
                lambda m:'heatmaps' if m[0].lower().endswith('s') else 'heatmap',text,flags=re.I)
    text=re.sub(r'\b(?:raeding|reding|readng)(s?)\b',r'reading\1',text,flags=re.I)
    text=re.sub(r'\bcalender(s?)\b',r'calendar\1',text,flags=re.I)
    text=re.sub(r'\b((?:19|20|21)\d{2})[/.](\d{2})[/.](\d{2})\b',r'\1-\2-\3',text)
    return re.sub(r'(?<=\d)\s*d\b',' days',text,flags=re.I)


def positive_view_request(message):
    text=normalize_board_prompt(message)
    if re.match(r"^(?:please\s+)?(?:no\b|skip\b|avoid\b|never\b|do\s+not\b|don't\b)",text,re.I):
        affirmative=re.search(r'[,;]\s*(?:but\s+)?(?=(?:show|provide|give|just|only|instead)\b)(.+)',text,re.I)
        return affirmative[1] if affirmative else ''
    return re.split(r"\s*(?:[,;]\s*|\band\s+|\s+)(?:without|skip|no|avoid|not|don't|do not)\s+",text,maxsplit=1,flags=re.I)[0]


def requested_kinds(message):
    """Identify requested visual forms without guessing their data scope."""
    message=positive_view_request(message)
    if not message or re.match(r'^(?:why|how (?:does|do|is|are)|explain|tell me (?:why|how)|(?:is|are)\s+(?:NOAA|VIIRS|MODIS))\b',message,re.I):
        return ()
    if re.match(r'^(?:what (?:is|are)|which|is|are|does|should)\b',message,re.I) and not re.search(
        r'\b(?:readings?|heatmaps?|calendars?)\s+(?:(?:are\s+)?available\s+)?(?:for|in|near|around|from)\b',message,re.I,
    ):
        return ()
    if not re.search(_VIEW_ACTION,message,re.I):
        scoped=bool(re.search(r'\b(?:readings?|heatmaps?|calendars?)\s+(?:(?:are\s+)?available\s+)?(?:for|in|near|around|from)\b',message,re.I))
        shorthand=bool(re.search(r'^(?:'+AREA_VIEW_PATTERN+r')\b|(?:[:—]|\s+-{1,2}\s+)\s*(?:'+AREA_VIEW_PATTERN+r')\b|\b(?:'+AREA_VIEW_PATTERN+r')\s*[.!]*$',message,re.I))
        if not (scoped or shorthand):
            return ()
    document_reading=bool(re.search(r'\breading\s+of\s+(?:the\s+)?(?:attached|selected|this|my)\b',message,re.I))
    matches = sorted((match.start(), -len(match[0]), kind, match.end()) for kind, pattern in _VIEW_TERMS.items()
                     for match in re.finditer(r'\b(?:'+pattern+r')\b', message, re.I)
                     if not (document_reading and kind=='readings' and match[0].lower()=='reading'))
    kinds = []
    end = -1
    for start, _, kind, stop in matches:
        if start >= end and kind not in kinds:
            kinds.append(kind)
            end = stop
    return tuple(kinds)


FIRMS_VIEWS = {
    'firms_region': {kind:'firms-region-'+kind for kind in ('heatmap','calendar','coordinates','satellites','readings')},
    'firms_country': {'heatmap':'firms-country-heatmap','coordinates':'firms-country',
                      'calendar':'firms-country-calendar','satellites':'firms-country-satellites',
                      'readings':'firms-country-readings'},
}
for operation, views in FIRMS_VIEWS.items():
    VIEW_OPERATIONS.update(dict.fromkeys(views.values(), operation))


def area_reading_views(message, kinds):
    if 'readings' not in kinds or re.search(r'\b(?:table|raw|original|records?|all|historical|archived)\b',message,re.I):
        return kinds
    return tuple(dict.fromkeys('calendar' if kind=='readings' else kind for kind in kinds))


def firms_days(payload, scope):
    first,last=map(date.fromisoformat,(scope['start'],scope['end']))
    dates=[(first+timedelta(days=index)).isoformat() for index in range((last-first).days+1)]
    counts=Counter(row['acquisition_utc'][:10] for row in payload['records'])
    primary=next((item for item in payload.get('checks',[]) if item['product']==payload.get('product')), {})
    lo,hi=primary.get('available_start',dates[0]),primary.get('available_end',dates[-1])
    return [{'date':day,'returned':counts[day] if lo<=day<=hi else None} for day in dates]


def project_firms_views(answer, operation, result_id, kinds, reference=None, *, payload, scope):
    available = FIRMS_VIEWS[operation]
    supported = [kind for kind in kinds if kind in available]
    unsupported = [VIEW_NAMES[kind] for kind in kinds if kind not in available]
    comparison_needs_products = 'satellites' in supported and len(payload.get('checks',[])) < 2
    comparison_note = 'A satellite comparison needs at least two products in the same saved window. Ask for a new comparison to fetch both.'
    if comparison_needs_products:
        supported.remove('satellites')
        answer.setdefault('limitations', []).append(comparison_note)
    if not supported:
        summary = (comparison_note
                   if comparison_needs_products else 'Ask for a map, calendar, or reading table from this source. Monthly comparability needs an evaluated region.')
        return {'title':'This source cannot produce that view','kind':'Study clarification',
                'summary':summary,
                'limitations':unsupported,'claims':[]}
    link = {'referenceUrl': reference} if reference else {}
    answer['data_views'] = [{'kind':available[kind], 'result_id':result_id, **link} for kind in supported[:4]]
    if 'calendar' in supported[:4]:
        counts=firms_days(payload,scope)
        if len(counts)<=5:
            items=', '.join(day['date'][5:]+' · '+(format(day['returned'],',') if day['returned'] is not None else 'unavailable') for day in counts)
            answer['summary'] += ' Daily returned detections (UTC) '+items+'.'
        else:
            queried=sum(day['returned'] is not None for day in counts)
            answer['summary'] += f' The calendar includes all {len(counts):,} UTC dates in the request.'
            if queried<len(counts):
                answer['summary'] += f' FIRMS listed {queried:,} of those dates for the mapped product.'
        answer['spoken_summary']=answer['summary']
    if unsupported:
        answer.setdefault('limitations', []).append(
            'This FIRMS window supports the requested observation views shown here. '
            + ', '.join(unsupported) + ' require a supported study or a different calculation.'
        )
    if len(supported) > 4:
        answer.setdefault('limitations', []).append('This board request places up to four views. Ask for the remaining view separately.')
    return answer


def selected_reading_requested(message):
    """Recognize a request to derive a view from a saved selection."""
    if re.search(r'\d|\b(?:today|yesterday|latest|recent|MODIS|VIIRS|NOAA|SNPP|FRP)\b', message, re.I):
        return False
    return bool(re.search(
        r'\b(?:for|of|from|using|based on)\s+(?:this|the selected|the saved|the attached)\s+'
        r'(?:study|evidence|scope|readings?|heatmap|map|calendar|card)\s*[.?!]*\s*\Z',
        message, re.I,
    ))


def selected_firms_answer(store, owner, studio, kinds):
    """Project only verified, board-owned saved FIRMS observations."""
    from .agent import guided_answer
    receipts = {}
    refs=studio.get('frozen_evidence_refs',{})
    for identifier in studio.get('frozen_evidence_ids',[]):
        ref=refs.get(identifier)
        if not ref:
            continue
        receipt=store.get_artifact(owner,identifier,'evidence')['body']
        receipts.setdefault(ref['snapshotId'],(identifier,receipt))
    if not any(receipt['operation'] in FIRMS_VIEWS for _,receipt in receipts.values()):
        return None
    if len(receipts)!=1:
        return {'title':'Choose one saved source','kind':'Study clarification',
                'summary':'Select one saved map or reading to derive the new views from its exact dates and products.',
                'claims':[]}
    identifier,receipt=next(iter(receipts.values()))
    operation,payload,scope=receipt['operation'],receipt['payload'],receipt['context']
    answer=guided_answer({**receipt,'id':identifier})
    answer['kind']='Saved scientific view'
    answer['limitations']=list(answer['limitations'])
    reference=payload.get('incident') or payload.get('event_context') or payload.get('reference') or {}
    return project_firms_views(answer,operation,identifier,kinds,reference.get('url'),payload=payload,scope=scope)


def view_context(current, overrides, message, unscoped=False, resolved_places=()):
    """An empty board cannot silently use the assistant's internal default study."""
    overrides = dict(overrides or {})
    if 'source' in overrides and 'series' not in overrides:
        overrides['series']={'joint':'joint','MODIS_SP':'modis','VIIRS_SNPP_SP':'viirs-snpp'}.get(overrides['source'],overrides['source'])
    elif 'series' in overrides and 'source' not in overrides:
        current={key:value for key,value in current.items() if key!='source'}
    case = overrides.get('case')
    named = bool(case in CASES and re.search(r'\b'+re.escape(case.split('-')[0])+r'\b', message, re.I))
    if case and case!=current.get('case') and not named:
        raise ValueError('Name the requested study before switching to another case.')
    requested_box=overrides.get('bbox')
    if requested_box is not None:
        try:requested_box=[float(value) for value in (requested_box.split(',') if isinstance(requested_box,str) else requested_box)]
        except (TypeError,ValueError):raise ValueError('Specify four valid geographic boundary coordinates.') from None
        explicit=all(any(re.search(r'(?<![\d.])'+re.escape(form)+r'(?![\d.])',message) for form in {str(value),format(value,'.12g')}) for value in requested_box)
        resolved=any(place.get('requested_place') and place['requested_place'].casefold() in message.casefold() and place['bbox'][0]<=requested_box[0]<requested_box[2]<=place['bbox'][2] and place['bbox'][1]<=requested_box[1]<requested_box[3]<=place['bbox'][3] for place in resolved_places) if len(requested_box)==4 else False
        canonical=named and requested_box==list(CASES[case]['bbox'])
        previous=list(current.get('bbox') or [])
        if requested_box!=previous and not (canonical or explicit or resolved):
            raise ValueError('The selected boundary changed without a requested location. Keep the selected study or specify the new boundary.')
        if named and not canonical and not (explicit or resolved):
            raise ValueError('Keep the named study boundary unless a different boundary was explicitly requested.')
        overrides['bbox']=requested_box
    custom = all(key in overrides for key in ('bbox','start','end'))
    if unscoped and not named:
        if not custom or not all(str(overrides[key]) in message for key in ('start','end')):
            raise ValueError('Name a supported study (Park, Camp or Grove), or specify a boundary and UTC date range.')
        if not all(str(value) in message for value in overrides['bbox']):
            raise ValueError('Specify the geographic boundary before requesting satellite views.')
    setup = dict(current)
    if case and case != setup.get('case'):
        for key in ('bbox','start','end','year','month','day','as_of'):
            setup.pop(key,None)
    elif any(key in overrides for key in ('start','end','year','month')):
        setup.pop('case',None)
        if 'year' in overrides or 'month' in overrides:
            for key in ('start','end','day','as_of'): setup.pop(key,None)
    if ('start' in overrides or 'end' in overrides) and 'day' not in overrides:
        setup.pop('day',None)
    cfg=normalize_context({**setup,**overrides})
    changed=any(cfg[key]!=current.get(key) for key in ('start','end'))
    canonical=named and cfg['start']==CASES[case]['start'] and cfg['end']==CASES[case]['end']
    if changed and ('start' in overrides or 'end' in overrides) and not canonical and not interval_requested(message,cfg['start'],cfg['end'],int(CASES[case]['start'][:4]) if named else None):
        raise ValueError('Keep the selected UTC interval or explicitly request the new dates; do not narrow the study silently.')
    return cfg

def prepare(service, owner, kind, context, overrides, message, unscoped, cancel, deadline, arguments=None, unresolved_places=(), resolved_places=()):
    if kind not in VIEW_OPERATIONS:
        raise ValueError('Choose an available scientific board view.')
    overrides=dict(overrides or {})
    # Fill omitted fields only from explicit, unambiguous user intent.
    named=[case for case in CASES if re.search(r'\b'+re.escape(case.split('-')[0])+r'\b',message,re.I)]
    if len(named)==1:overrides.setdefault('case',named[0])
    dates=list(dict.fromkeys(re.findall(r'\b\d{4}-\d{2}-\d{2}\b',message)))
    if len(dates)==2:
        overrides.setdefault('start',dates[0]);overrides.setdefault('end',dates[1])
    wanted_sources=requested_view_sources(message,kind)
    if len(wanted_sources)==1 and not any(key in overrides for key in ('source','series')):
        overrides['source']=next(iter(wanted_sources))
    cfg = view_context(context, overrides, message, unscoped, resolved_places)
    wanted_sources=requested_view_sources(message,kind)
    if wanted_sources and cfg['source'] not in wanted_sources:
        raise ValueError('The requested '+kind+' uses '+', '.join(sorted(wanted_sources))+'. Preserve a requested source; do not substitute another sensor.')
    if kind in {'coordinates','calendar','similar'}:
        if cfg['source'] in {'MODIS_SP','VIIRS_SNPP_SP'}:
            cfg=normalize_context({**cfg,'series':'modis' if cfg['source']=='MODIS_SP' else 'viirs-snpp'})
        elif cfg['series'] in {'modis','viirs-snpp'}:
            cfg=normalize_context({**cfg,'source':'MODIS_SP' if cfg['series']=='modis' else 'VIIRS_SNPP_SP'})
    arguments = {'limit':200} if kind in {'coordinates','archived-readings'} else dict(arguments or {})
    if kind=='analogues':
        from ..environment_analogues import context_publication
        from pathlib import Path
        directory=Path(__file__).resolve().parents[2]/'site/data/environment-analogues/v1'
        catalog=context_publication(directory)
        if not arguments.get('cell_id'):
            raise ValueError('Choose a target environmental pilot cell before matching. Available cell IDs: '+', '.join(cell['id'] for cell in catalog['cells'][:12]))
        arguments['expected_environment_sha256']=catalog['source_sha256']
    if kind in {'coordinates','archived-readings'} and cfg.get('day'):
        cfg=normalize_context({**cfg,'start':cfg['day'],'end':cfg['day'],'as_of':cfg['day']})
    operation=VIEW_OPERATIONS[kind]
    if kind=='satellites' and cfg.get('case')=='park-2024' and cfg['bbox']==[-122.0,39.5,-121.3,40.5] and cfg['start']>='2024-07-25' and cfg['end']<='2024-07-28' and cfg['source']=='joint':
        operation='park_platforms'
    validate_place_scope(cfg,operation,unresolved_places,resolved_places)
    result=service.science.call(owner,operation,cfg,arguments,cancel,deadline)
    return result


def requests_data_view(message):
    return bool(requested_kinds(message))


def validate_place_scope(cfg, operation, unresolved_places=(), resolved_places=()):
    """Shared place guard for both ordinary investigations and board views."""
    if operation in {'availability','method','sources'}:
        return
    if unresolved_places:
        raise ValueError('The place name is unresolved. Ask for its geographic boundary and UTC dates before querying measurements.')
    if resolved_places:
        box=cfg['bbox']
        if not any(place['bbox'][0]<=box[0]<box[2]<=place['bbox'][2] and place['bbox'][1]<=box[1]<box[3]<=place['bbox'][3] for place in resolved_places):
            raise ValueError('The measurement boundary does not match the geographic place just requested. Do not reuse a different study.')

def requested_view_sources(message, kind):
    """Keep source qualifications local to each requested view; allow multiple same-kind views."""
    noun={'calendar':r'calendar','heatmap':r'heat\s?map','coordinates':r'(?:coordinate(?:s| map)?|original records)'}.get(kind)
    if not noun:return set()
    sensor=r'(MODIS|S-?NPP|VIIRS(?:\s+S-?NPP)?|NOAA[- ]?20|NOAA[- ]?21)'
    between=r'(?:(?![.,;]|\b(?:and|or|plus)\b).)'
    patterns=(sensor+between+r'{0,40}\b'+noun+r'\b',r'\b'+noun+r'\b'+between+r'{0,24}'+sensor)
    found=set()
    for pattern in patterns:
        for match in re.finditer(pattern,message,re.I):
            token=re.sub(r'[^a-z0-9]','',match.group(1).lower())
            found.add('MODIS_SP' if token=='modis' else 'VIIRS_SNPP_SP' if token in {'snpp','viirs','viirssnpp'} else 'VIIRS_NOAA20_SP' if token=='noaa20' else 'VIIRS_NOAA21_SP')
    return found

def requested_view_source(message,kind):
    sources=requested_view_sources(message,kind)
    return next(iter(sources)) if len(sources)==1 else None

def requests_related_view(message):
    text=str(message or '').lower()
    return bool(re.search(r'\b(?:similar|analogue|analogous)\b',text) and
        re.search(r'\b(?:find|fetch|bring|show|connect|link|compare)\b',text) and
        re.search(r'\b(?:visualization|heatmap|map|readings|satellite|thermal|chart|event|situation)\b',text))

def interval_requested(message,start,end,named_year=None):
    """Conservative authorization for explicitly requested ISO or English UTC dates."""
    from datetime import date
    import calendar
    first,last=date.fromisoformat(start),date.fromisoformat(end)
    text=message.casefold()
    if start in text and end in text:return True
    def day_named(day):
        months='(?:'+calendar.month_name[day.month].casefold()+'|'+calendar.month_abbr[day.month].casefold()+')'
        return bool(re.search(r'\b'+months+r'\s+0?'+str(day.day)+r'\b',text) and (str(day.year) in text or named_year==day.year))
    if day_named(first) and day_named(last):return True
    if first.year==last.year and first.month==last.month:
        month='(?:'+calendar.month_name[first.month].casefold()+'|'+calendar.month_abbr[first.month].casefold()+')'
        year=str(first.year) in text or named_year==first.year
        if year and re.search(r'\b'+month+r'\s+0?'+str(first.day)+r'\s*(?:[-–]|to|through)\s*0?'+str(last.day)+r'\b',text):return True
        if year and first.day==1 and last.day==calendar.monthrange(first.year,first.month)[1] and re.search(r'\b'+month+r'\s*,?\s*'+str(first.year)+r'\b',text):return True
    return False


def explicit_single_view(message, *, requested_kind=None):
    """Resolve only an unambiguous named-study display request.

    This skips an unnecessary local tool-selection inference. The normal scope,
    source, ownership and cancellation guards still execute in prepare().
    """
    if not requests_data_view(message) or requests_related_view(message):return None
    if re.search(r'\b(?:in|near|within|around|bbox|boundary|latitude|longitude|temperature|brightness|kelvin|celsius)\b',message,re.I):return None
    cases=[case for case in CASES if re.search(r'\b'+re.escape(case.split('-')[0])+r'\b',message,re.I)]
    if len(cases)!=1:return None
    patterns={'heatmap':r'\bheat\s?map\b','coordinates':r'\bcoordinates?\b',
        'calendar':r'\bcalendar\b','satellites':r'\bsatellite (?:readings|counts|comparison|observations)\b|\bdifferent satellites\b',
        'factors':r'\b(?:NDVI|elevation|environmental|measured) (?:maps?|factors)\b'}
    kinds=[requested_kind] if requested_kind else [kind for kind,pattern in patterns.items() if re.search(pattern,message,re.I)]
    if len(kinds)!=1:return None
    kind=kinds[0];case=cases[0];canonical=CASES[case]
    if not requested_kind and (kind=='factors' or re.search(r'\b(?:FRP|persistence)\b',message,re.I)):return None
    dates=list(dict.fromkeys(re.findall(r'\b\d{4}-\d{2}-\d{2}\b',message)))
    if len(dates)>2:return None
    args={'kind':kind,'case_id':case}
    import calendar
    from datetime import date
    months={name.lower():month for month in range(1,13) for name in (calendar.month_name[month],calendar.month_abbr[month])}
    month_pattern='(?:'+'|'.join(sorted(months,key=len,reverse=True))+')'
    ranges=list(re.finditer(r'\b('+month_pattern+r')\.?\s+(\d{1,2})\s*(?:[-–]|to|through)\s*(\d{1,2})(?:\s*,?\s+(\d{4}))?\b',message,re.I))
    if len(ranges)>1:return None
    if not dates and not ranges and re.search(r'\d|\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b',message,re.I):
        if not interval_requested(message,canonical['start'],canonical['end'],int(canonical['start'][:4])):return None
    if ranges:
        match=ranges[0];year=int(match[4] or canonical['start'][:4]);month=months[match[1].lower()]
        try:first,last=date(year,month,int(match[2])).isoformat(),date(year,month,int(match[3])).isoformat()
        except ValueError:return None
        if first>last:return None
        args.update(start=first,end=last)
        if len(dates)==1 and kind in {'heatmap','coordinates','readings'}:args['day']=dates[0]
        elif dates and dates!=[first,last]:return None
    elif len(dates)==2:args.update(start=dates[0],end=dates[1])
    elif len(dates)==1:
        if kind in {'heatmap','coordinates','readings'}:args['day']=dates[0]
        else:args.update(start=dates[0],end=dates[0])
    sources=requested_view_sources(message,kind)
    if len(sources)>1:return None
    if sources:
        source=next(iter(sources))
        if source not in {'joint','MODIS_SP','VIIRS_SNPP_SP'}:return None
        args['source']=source
    if not requested_kind and re.search(r'\bFRP\b',message,re.I):args['metric']='frp'
    elif not requested_kind and re.search(r'\bpersistence\b',message,re.I):args['metric']='persistence'
    return args

def requests_heatmap_catalog(message):
    text=normalize_board_prompt(message)
    return bool(re.search(r'\b(?:what|which|list|available|options)\b',text,re.I)
                and re.search(r'\bheatmaps?\b',text,re.I)
                and re.search(r'\b(?:available|options|list|can (?:you|it) (?:bring|add|show|get|make))\b',text,re.I)
                and not re.search(r'\bheatmaps?\s+(?:for|in|of|over|near|around|from)\b|\b(?:show|add|bring|plot) (?:me )?(?:a|the|this) heatmap\b',text,re.I)
                and not re.search(r'\b(?:for|in|near|around|from)\s+[^?]+',text,re.I))


def heatmap_catalog():
    options = []
    for case in CASES.values():
        name = case['title'].split(' · ')[0]
        day = case['selected_day']
        options.append({'label':name, 'detail':f"{day} UTC · detection density",
                        'question':f"Show a heatmap of {name} on {day}."})
    return {'title':'Available heatmaps','kind':'View catalog',
            'summary':'Choose a saved study to add its detection-density map. For current country readings, ask for a country and a recent date window.',
            'view_options':options,'claims':[]}


def requests_open_fire_heatmap(message, place_pattern):
    """Identify a heatmap request that delegates the choice of an incident."""
    if not requests_data_view(message) or requests_heatmap_catalog(message) or requests_related_view(message):
        return False
    if not re.search(r'\bheat\s?map\b', message, re.I):
        return False
    # Leave explicitly requested fires, times, sensors and subregions to the
    # normal scope resolver.
    if re.search(r'\d|\b(?:park|camp|grove|recent|latest|current|today|yesterday|MODIS|VIIRS|NOAA|SNPP|FRP)\b', message, re.I):
        return False
    pattern = rf"""
        \b(?:a|any|one|some)\s+(?:historic(?:al)?\s+)?
        (?:
            (?:wildfire|(?:forest\s+)?fire)(?:\s+(?:that\s+)?(?:happened|occurred|burned))?
            \s+(?:in|from)\s+(?:the\s+)?{place_pattern}
            |
            (?:the\s+)?{place_pattern}\s+(?:wildfire|(?:forest\s+)?fire)(?:\s+heat\s?map)?
        )
        (?:\s+on\s+(?:the|this)\s+board)?(?:\s+please)?[.!?\s]*\Z
    """
    return bool(re.search(pattern, message, re.I | re.X))


def choose_archived_heatmap(message):
    """Resolve an open choice of a California fire using the saved case catalog."""
    if not requests_open_fire_heatmap(message, r'(?:northern\s+)?california'):
        return None
    case_id = 'park-2024'
    case = CASES[case_id]
    day = case['selected_day']
    closeup = bool(re.search(r'\b(?:close[- ]?up|zoom(?:ed)?[- ]?in|detailed)\b', message, re.I))
    # Keep the incident reference inside a smaller window within the study bounds.
    bbox = [-122.0, 39.60, -121.50, 40.00] if closeup else case['bbox']
    return {'case':case_id,'start':day,'end':day,'day':day,'bbox':bbox,'source':'MODIS_SP','series':'modis'}


def archived_heatmap_answer(service, owner, scope, cancel, deadline, *, message=None):
    kinds=requested_kinds(message or '')
    if len(kinds)>1:
        specs=[(kind,{'use_context':True}) for kind in kinds if kind in _ARCHIVE_KINDS]
        return archive_bundle_answer(service,owner,specs,message,normalize_context(scope),cancel,deadline)
    evidence = service.science.call(owner, 'replay', scope, cancel=cancel, deadline=deadline)
    case = CASES[scope['case']]
    frame = next((item for item in evidence['payload']['frames'] if item['date_utc'] == scope['day']), None)
    product = frame['products']['MODIS_SP'] if frame else None
    if not product or not product['detections']:
        raise ValueError('The Park Fire archive has no MODIS detections in this saved window.')
    name = case['title'].split(' · ')[0]
    view = 'close-up' if scope['bbox'] != case['bbox'] else 'heatmap'
    title = f'{name} · California {view}'
    day = date.fromisoformat(scope['day'])
    return {
        'title': title,
        'kind': 'Saved scientific view',
        'summary': (f'I chose the {name} in Northern California. MODIS recorded {product["detections"]:,} detections '
                    f'across {product["cell_days"]:,} grid cells in this view on {day:%B} {day.day}, {day.year} UTC.'),
        'data_views': [{'kind':'heatmap','result_id':evidence['id'],'title':title}],
        'claims': [],
    }


_ARCHIVE_KINDS = {
    'heatmap':'heatmap', 'calendar':'calendar', 'coordinates':'coordinates',
    'satellites':'satellites', 'readings':'archived-readings', 'factors':'factors',
    'missingness':'export-status', 'persistence':'persistence-summary',
    'comparability':'monthly-comparability-summary', 'harmonized':'harmonized-summary',
    'inventory':'inventory-summary','overlap':'overlap-summary','coverage':'coverage-summary','validation':'validation-summary',
}
VIEW_OPERATIONS['archived-readings']='observations'
_SUMMARY_OPERATIONS = {
    'export-status':'missingness', 'persistence-summary':'persistence',
    'monthly-comparability-summary':'comparability', 'harmonized-summary':'harmonized',
    'inventory-summary':'availability', 'overlap-summary':'research',
    'coverage-summary':'exposure', 'validation-summary':'validation',
}
VIEW_OPERATIONS.update(_SUMMARY_OPERATIONS)


def reading_statement(kind, result):
    """Build concise prose from the same payload used to render the figure."""
    payload,scope=result['payload'],result['context']
    if kind=='heatmap':
        day=scope['day'] or scope['start']
        frame=next((item for item in payload['frames'] if item['date_utc']==day),None)
        if frame:
            cells=sum(scope['source']=='joint' or scope['source'] in item['sources'] for item in frame['cells'])
            return f'The heatmap shows {cells:,} occupied grid cells on {day} UTC.'
    if kind=='calendar':
        days=[row for row in payload.get('daily',[]) if scope['start']<=row['date_utc']<=scope['end']]
        if days:
            reported=sum(row.get('detected_cell_days') is not None for row in days)
            if len(days)==1:
                return (f'The calendar gives the observed-cell total for {days[0]["date_utc"]} UTC.' if reported
                        else f'The calendar shows missing coverage for {days[0]["date_utc"]} UTC.')
            return f'The calendar covers {len(days)} UTC days and reports observed-cell totals for {reported}.'
    if kind=='satellites' and result['operation']=='park_platforms':
        entries=[]
        for source,label in (('MODIS_SP','MODIS'),('VIIRS_SNPP_SP','Suomi-NPP'),
                             ('VIIRS_NOAA20_SP','NOAA-20'),('VIIRS_NOAA21_SP','NOAA-21')):
            values=[row['values'].get(source) for row in payload['rows']]
            available=[value for value in values if value is not None]
            entries.append(f'{label} {sum(available):,}' if available else f'{label} unavailable')
        return 'Recorded detections by product for the selected dates are '+', '.join(entries)+'.'
    if kind in ('coordinates','readings'):
        return f'{payload["total"]:,} original records match the requested archive window.'
    if kind=='missingness':
        values=payload['summary']
        return f'MODIS has {values["MODIS_SP"]["incomplete_export_days"]} UTC days with incomplete exports, and Suomi-NPP has {values["VIIRS_SNPP_SP"]["incomplete_export_days"]}.'
    if kind=='persistence':
        repeated=sum(item['observed_days']>1 for item in payload['cells'])
        return f'{repeated:,} of {payload["total_cells"]:,} observed grid cells were recorded on more than one UTC day.'
    if kind=='factors':
        return f'The Park pilot contains {payload["cell_count"]:,} cells with vegetation and elevation context.'
    if kind in ('comparability','harmonized'):
        matched=payload.get('result',{}).get('eligibility',{}).get('complete_matched_months')
        if type(matched) is int:
            return f'The evaluation uses {matched:,} complete matched months for the fixed comparison region.'
    if kind=='inventory':
        return 'The inventory lists authentic imported records separately by source.'
    return None


def explicit_board_bundle(message, *, has_study=False):
    """Plan compatible archive readings from the same named or evaluated region."""
    kinds = requested_kinds(message)
    if not kinds or requests_heatmap_catalog(message) or requests_related_view(message):
        return None
    specs=[]
    for kind in kinds:
        if kind not in _ARCHIVE_KINDS:
            continue
        args=explicit_single_view(message, requested_kind=kind)
        if args:
            specs.append((kind, args))
    if not specs and kinds==('inventory',) and not re.search(r'\b(?:for|in|near|around|from)\b',message,re.I):
        return [('inventory',{})]
    if specs:
        return specs
    if has_study and re.search(r'\b(?:this|current|selected|attached|saved) (?:study|evidence|scope|reading)\b',message,re.I):
        if not re.search(r'\d|\b(?:yesterday|today|last|near|within|around|for|in|from)\b(?!\s+(?:this|the|current|selected|attached|saved)\b)',message,re.I):
            return [(kind,{'use_context':True}) for kind in kinds if kind in _ARCHIVE_KINDS] or None

    from ..regions import REGIONS
    regions=[region for region,pattern in {'norcal':r'norcal|northern\s+california',
                                          'punjab-haryana':r'punjab[\s–-]+haryana'}.items()
             if re.search(r'\b(?:'+pattern+r')\b',message,re.I)]
    if len(regions)==1 and set(kinds)<= {'comparability','harmonized'}:
        if re.search(r'\d|\b(?:day|daily|today|yesterday|week)\b',message,re.I):
            raise ValueError('Evaluated comparability uses the complete published monthly overlap, without a daily or custom-date result.')
        region=regions[0]
        return [(kind,{'region':region,'bbox':REGIONS[region]['bbox']}) for kind in kinds]
    return None


def archive_bundle_answer(service, owner, specs, message, context, cancel, deadline):
    views,statements,unavailable,added=[],[],[],[]
    kinds=requested_kinds(message)
    planned={kind for kind,_ in specs}
    for kind in kinds:
        if kind not in planned:
            unavailable.append(f'{VIEW_NAMES[kind]} needs its own study or selection.')
    for kind,params in specs[:4]:
        args={key:value for key,value in params.items() if key!='kind'}
        try:
            if args.pop('use_context',False):
                result=prepare(service,owner,_ARCHIVE_KINDS[kind],context,{},message,False,cancel,deadline)
            elif 'case_id' in args:
                case=args.pop('case_id')
                args['case']=case
                if kind=='factors' and 'start' not in args and 'end' not in args:
                    # Published Park pilot window. The normal calculation checks it.
                    cfg=normalize_context({**args,'start':'2024-07-25','end':'2024-07-28'})
                    result=service.science.call(owner,'environment_context',cfg,cancel=cancel,deadline=deadline)
                else:
                    result=prepare(service,owner,_ARCHIVE_KINDS[kind],
                                   {'revision':context['revision']},args,message,True,cancel,deadline)
            else:
                # The fixed-region method owns its interval and validation.
                cfg=normalize_context({**args,'revision':context['revision']})
                result=service.science.call(owner,VIEW_OPERATIONS[_ARCHIVE_KINDS[kind]],cfg,cancel=cancel,deadline=deadline)
        except ValueError as error:
            unavailable.append(f'{VIEW_NAMES[kind]} · {error}')
            continue
        view={'kind':'park-satellites' if result['operation']=='park_platforms' else _ARCHIVE_KINDS[kind],'result_id':result['id']}
        if kind=='heatmap':
            case_title=CASES[result['context']['case']]['title'].split(' · ')[0] if result['context'].get('case') else 'Archived study'
            view['title']=case_title+' · detection heatmap'
        statement=reading_statement(kind,result)
        if statement:
            statements.append(statement)
        if kind=='harmonized' and re.search(r'\bcalendar\b',message,re.I):
            unavailable.append('The harmonization card is a monthly evaluation. Ask for the reading calendar to see dated observations.')
        views.append(view)
        added.append(VIEW_NAMES[kind].lower())
    if len(specs)>4:
        unavailable.append('Ask for the remaining views in a separate request. The board places up to four at a time.')
    if not views:
        return {'title':'Choose a supported scope','kind':'Study clarification',
                'summary':unavailable[0] if unavailable else 'Specify the place and date range for this reading.',
                'limitations':unavailable[1:],'claims':[]}
    scope=next((params.get('case_id') or params.get('region') for _,params in specs),None)
    name=CASES[scope]['title'].split(' · ')[0] if scope in CASES else 'Saved study readings'
    return {'title':name,'kind':'Saved scientific view','summary':' '.join(['Prepared '+', '.join(added)+'.',*dict.fromkeys(statements)]),
            'data_views':views,'limitations':unavailable,'claims':[]}


def requests_reading_catalog(message):
    return bool(re.search(r'\b(?:what|which|list)\b',message,re.I)
                and re.search(r'\b(?:readings|views|data|charts)\b',message,re.I)
                and re.search(r'\b(?:available|can you (?:bring|show|add|get))\b',message,re.I)
                and not requests_heatmap_catalog(message)
                and not re.search(r'\b(?:for|in|near|around|from)\s+[^?]+',message,re.I))


def reading_catalog():
    options=[
        ('Heatmap and reading calendar','Recent FIRMS · one shared search','Provide heatmap and reading calendar for Rajshahi'),
        ('Reading table and coordinate map','Original FIRMS rows and locations','Show a reading table and coordinate map for Bangladesh'),
        ('Park Fire satellite comparison','Published observations · July 25–28, 2024','Show Park Fire satellite comparison from 2024-07-25 to 2024-07-28'),
        ('Export status and persistence','Archived source gaps and repeatedly observed cells','Show Park Fire export status and persistence from 2024-07-25 to 2024-07-28'),
        ('Measured factors','Published Park pilot','Show Park Fire measured factors'),
        ('Source inventory','Authentic imported records by source','Show source inventory'),
        ('Monthly comparability','Evaluated MODIS and VIIRS overlap','Show monthly comparability for Northern California'),
    ]
    return {'title':'Board readings','kind':'View catalog',
            'summary':'Choose a reading or combine compatible views in one request. Name a place or saved study and add dates when needed.',
            'view_options':[{'label':label,'detail':detail,'question':question,'action':'Add to board'} for label,detail,question in options],
            'claims':[]}
