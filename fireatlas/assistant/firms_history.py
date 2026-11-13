"""Bounded NASA FIRMS archive queries shared by country and locality views."""
import calendar
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import hashlib
import json
import re
import time
from urllib.parse import quote, urlencode
from urllib.request import urlopen

from .. import fetch

_HISTORY = r'(?:all\s+(?:(?:available|the)\s+)?(?:historical|archived)|full\s+(?:available\s+)?(?:historical|archive|history)|all[- ]time|entire\s+(?:archive|history)|(?:historical|archived)\s+(?:(?:satellite|thermal|FIRMS)\s+)?(?:readings|records|observations|detections|data))'
_DATE = r'\d{4}-\d{2}-\d{2}'
_MONTHS={name.casefold():month for month in range(1,13) for name in (calendar.month_name[month],calendar.month_abbr[month])}
_MONTH = r'(?:'+'|'.join(_MONTHS)+r')'
_YEAR = r'(?:19|20|21)\d{2}'
PERIOD_SUFFIX = (rf'\s+(?:(?:in|of|for|during|since|from|on)\s+(?:{_DATE}|{_MONTH}\s+{_YEAR}|{_YEAR}(?:-\d{2})?)\b'
                 rf'|(?:{_DATE}|{_YEAR})(?=\s*(?:[.?!]|$))|(?:in\s+)?(?:{_HISTORY})\b'
                 r'|(?:(?:in|of|for|during)\s+)?(?:last|this)\s+year\b|(?:(?:for|on)\s+)?(?:today|yesterday)\b|(?:(?:in|for|during)\s+)?(?:this|last)\s+(?:month|week)\b|(?:for\s+)?(?:the\s+)?(?:last|past|latest)\s+\d+)')

def historical_period(message, today):
    """Return explicit UTC bounds, 'all' for a catalog, or None for a recent query."""
    raw_dates = list(dict.fromkeys(re.findall(rf'\b{_DATE}\b', message)))
    if raw_dates:
        try:
            dates = [date.fromisoformat(value) for value in raw_dates]
        except ValueError:
            raise ValueError('Use valid YYYY-MM-DD dates for the satellite search.') from None
        if len(dates) == 1 and re.search(r'\bsince\s+'+re.escape(raw_dates[0]), message, re.I):
            dates.append(today)
        first, last = dates[0], dates[-1]
        if len(dates)>2 or last<first or last>today:
            raise ValueError('Use an ordered UTC date window ending today or earlier.')
        return first,last
    month_match=re.search(rf'\b({_MONTH})\s+({_YEAR})\b',message,re.I)
    iso_month=re.search(rf'\b({_YEAR})-(\d{{2}})\b',message)
    if month_match or iso_month:
        year,month=(int(month_match[2]),_MONTHS[month_match[1].casefold()]) if month_match else tuple(map(int,iso_month.groups()))
        if not 1<=month<=12 or (year,month)>(today.year,today.month):
            raise ValueError('Use a valid calendar month ending today or earlier.')
        return date(year,month,1),min(today,date(year,month,calendar.monthrange(year,month)[1]))
    years=list(dict.fromkeys(int(value) for value in re.findall(rf'\b{_YEAR}\b',message)))
    if years:
        if len(years)>2 or years[0]>years[-1] or years[-1]>today.year:
            raise ValueError('Choose an ordered year or year range ending in the current year or earlier.')
        first=date(years[0],1,1)
        last=today if re.search(r'\bsince\s+'+str(years[0]),message,re.I) else min(today,date(years[-1],12,31))
        return first,last
    if re.search(r'\b(?:this|last) week\b',message,re.I):
        monday=today-timedelta(days=today.weekday())
        return (monday-timedelta(days=7),monday-timedelta(days=1)) if re.search(r'\blast week\b',message,re.I) else (monday,today)
    if re.search(r'\b(?:this|last) month\b',message,re.I):
        start=today.replace(day=1)
        end=start-timedelta(days=1)
        return (end.replace(day=1),end) if re.search(r'\blast month\b',message,re.I) else (start,today)
    if re.search(r'\blast year\b',message,re.I):
        return date(today.year-1,1,1),date(today.year-1,12,31)
    if re.search(r'\b(?:this year|year to date)\b',message,re.I):
        return date(today.year,1,1),today
    if re.search(rf'\b{_HISTORY}\b',message,re.I):
        return 'all'
    return None

PEAK_QUERY = (r'(?:peak\s+(?:(?:fire|wildfire|thermal|activity|detections?|observations?)\s+)*'
              r'(?:season|month|period|activity|detections?|observations?)|busiest(?:\s+(?:fire|wildfire|thermal))?\s+month'
              r'|(?:worst|most\s+active)\s+(?:(?:fire|wildfire)\s+)?(?:month|season)'
              r'|month\s+(?:with|had|saw)\s+(?:the\s+)?(?:most|highest)\s+(?:number\s+of\s+)?(?:(?:raw|fire|thermal|wildfire)\s+)?(?:detections?|activity|fires?)'
              r'|(?:fire|wildfire|thermal)\s+activity\s+(?:was\s+)?(?:highest|at\s+its\s+peak))')
PEAK_SUFFIX = rf"\s+(?:(?:during|at|in|for|on)\s+)?(?:(?:its|it['’]s|the)\s+)?{PEAK_QUERY}\b"


def requests_peak_month(message):
    return bool(re.search(r'\b'+PEAK_QUERY+r'\b',message,re.I))


def peak_search_period(message, today):
    """Rank only complete UTC months in a bounded historical search."""
    if re.search(r'\b(?:dry season|wet season|monsoon|summer|winter|spring|autumn)\b',message,re.I) and not re.search(rf'\b{_DATE}\b',message):
        raise ValueError('Give explicit UTC start and end dates for the named season so its peak can be ranked.')
    requested=historical_period(message,today)
    if requested is None:
        if re.search(r'\b(?:today|yesterday|\d+\s*days?|since|dry season|monsoon)\b',message,re.I):
            raise ValueError('Choose a year or an explicit range containing complete UTC months to find the peak month.')
        return date(today.year-1,1,1),date(today.year-1,12,31)
    if requested=='all' or (requested[1]-requested[0]).days>365:
        raise ValueError('Choose one year or a shorter date range for a peak-month search.')
    first,last=requested
    if first.day!=1:
        first=(first.replace(day=28)+timedelta(days=4)).replace(day=1)
    if last.day!=calendar.monthrange(last.year,last.month)[1] or last==today:
        last=last.replace(day=1)-timedelta(days=1)
    if first>last:
        raise ValueError('The date range needs at least one complete UTC month to find its peak.')
    return first,last


def peak_metric(message):
    raw=re.search(r'\b(?:(?:most|highest|peak)\s+(?:(?:number of|raw|fire|thermal|wildfire)\s+)*detections?|by\s+(?:raw\s+)?detections?)\b',message,re.I)
    return 'detections' if raw else 'occupied_cell_days'


def narrow_to_peak_month(checks, first, last, metric='occupied_cell_days'):
    """Rank by the requested metric, defaulting to the board calendar’s occupied cells."""
    from ..studio.heat import cell_index
    check,=checks
    cells=defaultdict(set)
    records=defaultdict(list)
    for row in check['records']:
        day=row['acquisition_utc'][:10]
        cells[day[:7]].add((day,*cell_index(row)))
        records[day[:7]].append(row)
    month=first
    totals=[]
    while month<=last:
        name=month.strftime('%Y-%m')
        totals.append({'month':name,'occupied_cell_days':len(cells[name]),'detections':len(records[name])})
        month=(month.replace(day=28)+timedelta(days=4)).replace(day=1)
    maximum=max(item[metric] for item in totals)
    unit='returned detections' if metric=='detections' else 'occupied 1 km cell-days'
    if not maximum:
        return None, {'title':'No peak month in these readings','kind':'Study clarification','claims':[],
                      'summary':f'{check["sensor"]} returned zero detections from {first} to {last} UTC. Every searched month tied at zero.'}
    winners=[item for item in totals if item[metric]==maximum]
    winner=winners[0]
    start=date.fromisoformat(winner['month']+'-01')
    end=start.replace(day=calendar.monthrange(start.year,start.month)[1])
    selected={**check,'records':records[winner['month']],'detections':winner['detections'],
              'available_start':start.isoformat(),'available_end':end.isoformat()}
    selection={'search_start':first.isoformat(),'search_end':last.isoformat(),
               'metric':unit,'months':totals,'selected_month':winner['month'],
               'tied_months':[item['month'] for item in winners]}
    note=f' {start:%B %Y} was the peak observed month from {first} to {last} UTC by {unit} ({maximum:,}).'
    if len(winners)>1:
        note=f' {len(winners)} months tied at {maximum:,} {unit}. Showing the earliest, {start:%B %Y}.'
    return (selected,start,end,selection,note),None


def calendar_default(message, kinds, today):
    if 'calendar' in kinds and not re.search(r'\b(?:today|yesterday|\d+\s*days?|last 24 hours)\b',message,re.I):
        return today.replace(day=1),today
    return None


def recent_window(period, today):
    return isinstance(period,tuple) and 0<=(today-period[0]).days<31

def archive_products(available, products, period, default, compare):
    if products:
        return [source.replace('_NRT','_SP') for source in products]
    if compare:
        return [source.replace('_NRT','_SP') for source in default]
    if period!='all':
        first,last=period
        covering=[source for source in available if available[source][0]<=first<=last<=available[source][1]]
        for source in default:
            if (standard:=source.replace('_NRT','_SP')) in covering:
                return [standard]
    # MODIS offers the longest baseline for a history catalog.
    return ['MODIS_SP']

def plan_history(label, kinds, period, products, default, *, peak=False):
    if peak and ('satellites' in kinds or len(products)>1):
        raise ValueError('Find the peak month with one FIRMS product first. Then compare satellites for that month.')
    available={item['data_id']:tuple(map(date.fromisoformat,(item['min_date'],item['max_date'])))
               for item in fetch.availability() if item['data_id'].endswith('_SP')}
    selected=archive_products(available,products,period,default,'satellites' in kinds)
    if len(selected)<2 and 'satellites' in kinds:
        raise ValueError('Choose at least two satellite products for a comparison.')
    if peak and (len(selected)!=1 or selected[0] not in available or
                 not available[selected[0]][0]<=period[0]<=period[1]<=available[selected[0]][1]):
        raise ValueError('Finding a peak needs one FIRMS product with archive dates covering the whole search. Choose one product and a fully available year or date range.')
    covered=[available[source] for source in selected if source in available]
    if not covered:
        raise ValueError('NASA FIRMS lists no standard-processing dates for the requested products.')
    start,end=min(first for first,_ in covered),max(last for _,last in covered)
    first,last=(start,end) if period=='all' else (max(start,period[0]),min(end,period[1]))
    if first>last:
        return [],{'title':'Dates outside the FIRMS archive','kind':'Study clarification','claims':[],
                   'summary':f'The selected NASA FIRMS products list dates from {start} through {end} UTC. Choose a date within that range.'}
    if period=='all' or (period[1]-period[0]).days>365:
        from .board_views import VIEW_NAMES
        views_to_load=('heatmap','calendar','readings') if set(kinds)=={'readings'} else kinds
        views=' and '.join(VIEW_NAMES[kind].lower() for kind in views_to_load if kind in {'heatmap','calendar','coordinates','readings','satellites'})
        # Use exact selectable slices, including partial first/last years.
        options=[]
        for year in range(last.year,first.year-1,-1):
            lo,hi=max(first,date(year,1,1)),min(last,date(year,12,31))
            sensor_clause=' using '+' and '.join(default[src.replace('_SP','_NRT')][0] for src in selected) if not (len(selected)>1 and not products) else ''
            options.append({'label':str(year),'detail':f'{lo} to {hi} UTC · NASA FIRMS',
                            'action':'Load year','question':f'Show {views} for {label} from {lo} to {hi}{sensor_clause} and summarize documented wildfire events.'})
        sources=', '.join(default[src.replace('_SP','_NRT')][0] for src in selected)
        return [],{'title':f'{label} · FIRMS archive','kind':'View catalog','claims':[],
                   'summary':f'NASA FIRMS lists {sources} archive dates from {start} through {end} UTC. Choose a year to retrieve that year’s views and check for documented wildfire events.',
                   'view_options':options}
    plans=[(source,max(period[0],available[source][0]),min(period[1],available[source][1])) for source in selected
           if source in available and available[source][0]<=period[1] and available[source][1]>=period[0]]
    if not plans:
        raise ValueError('NASA FIRMS lists no dates for the selected products in that window.')
    return plans,None

def window_readings(key, source, sensor, band, bounds, first, last, cancel, deadline, *,
                    read_records, limit, row_limit, within=None):
    """Fetch nonoverlapping five-day windows and retain each response's source digest."""
    extent=','.join(map(str,bounds))
    windows=[(first+timedelta(days=offset),min(5,(last-first).days+1-offset))
             for offset in range(0,(last-first).days+1,5)]
    west,south,east,north=bounds
    def download(window):
        if cancel.is_set() or time.monotonic()>deadline:
            raise InterruptedError('Investigation stopped or timed out.')
        start,days=window
        end=start+timedelta(days=days-1)
        url='/'.join((fetch.BASE_URL,quote(key,safe=''),source,extent,str(days),start.isoformat()))
        body=fetch._download(url,f'{sensor} readings for {start}',limit=limit)
        rows=[]
        for row in read_records(body,band,cancel,deadline):
            lat,lon=row['latitude'],row['longitude']
            if not (start.isoformat()<=row['acquisition_utc'][:10]<=end.isoformat()
                    and west<=lon<=east and south<=lat<=north):
                raise ValueError('NASA FIRMS returned a reading outside the requested window.')
            if within is None or within(lon,lat):
                rows.append(row)
        return {'start':start.isoformat(),'end':end.isoformat(),'sha256':hashlib.sha256(body.encode()).hexdigest()},rows

    receipts,rows=[],[]
    def collect(results):
        for receipt,records in results:
            if len(rows)+len(records)>row_limit:
                raise ValueError('This search exceeds the board’s record limit. Choose a shorter date range or a smaller area.')
            receipts.append(receipt)
            rows.extend(records)
    if len(windows)==1:
        collect(map(download,windows))
    else:
        with ThreadPoolExecutor(max_workers=6,thread_name_prefix='firms-archive') as pool:
            # Only queue one bounded batch so cancellation or a failed response stops new downloads.
            for offset in range(0,len(windows),6):
                collect(pool.map(download,windows[offset:offset+6]))
    from .contracts import digest
    return {'product':source,'sensor':sensor,'band':band,'detections':len(rows),'records':rows,
            'source_csv_sha256':receipts[0]['sha256'] if len(receipts)==1 else digest(receipts),
            'source_windows':receipts,'available_start':first.isoformat(),'available_end':last.isoformat()}


def archive_summary(records):
    if not records:
        return ' The archive returned no records in this area for the queried dates.'
    from collections import Counter
    days=Counter(row['acquisition_utc'][:10] for row in records)
    peak=max(days.values())
    dates=sorted(day for day,count in days.items() if count==peak)
    noun='detection' if peak==1 else 'detections'
    if len(dates)==1:
        return f' Detections were returned on {len(days):,} UTC dates. The peak was {peak:,} {noun} on {dates[0]}.'
    return f' Detections were returned on {len(days):,} UTC dates. The daily peak was {peak:,} {noun}, reached on {len(dates):,} dates.'


def event_context(message, bounds, first, last, cancel, deadline):
    """Check independently cataloged events only when the scientist asks for incident context."""
    if not re.search(r'\b(?:what (?:actually )?happened|(?:documented|reported) (?:wildfire|fire|incident|events?)|incident (?:reports?|history))\b',message,re.I):
        return None,''
    if cancel.is_set() or time.monotonic()>deadline:
        raise InterruptedError('Investigation stopped or timed out.')
    west,south,east,north=bounds
    base='https://eonet.gsfc.nasa.gov/api/v3/events'
    url=base+'?'+urlencode({'category':'wildfires','status':'all','start':first,'end':last,
                           'bbox':','.join(map(str,(west,north,east,south))),'limit':20})
    try:
        with urlopen(url,timeout=12) as response:
            data=json.loads(response.read(600_000))
        if not isinstance(data.get('events'),list):
            raise ValueError()
        events=[]
        for item in data['events']:
            identifier,title=item.get('id'),item.get('title')
            if not isinstance(title,str) or not isinstance(identifier,str) or not re.fullmatch(r'EONET_\d+',identifier):
                continue
            dates=sorted({geometry['date'][:10] for geometry in item.get('geometry') or []
                          if isinstance(geometry,dict) and isinstance(geometry.get('date'),str)
                          and re.fullmatch(_DATE,geometry['date'][:10])
                          and first.isoformat()<=geometry['date'][:10]<=last.isoformat()})
            events.append({'title':title[:180],'url':base+'/'+identifier,'dates_utc':dates})
    except (OSError,ValueError,AttributeError,TypeError):
        return {'url':url,'status':'unavailable','events':[]},' NASA EONET’s incident catalog could not be checked.'
    if cancel.is_set() or time.monotonic()>deadline:
        raise InterruptedError('Investigation stopped or timed out.')
    labels=[item['title']+(f" ({item['dates_utc'][0]} UTC)" if item['dates_utc'] else '') for item in events[:3]]
    summary=(' NASA EONET lists wildfire events in the search box: '+', '.join(labels)+'. '
             'These reports do not identify the cause of individual detections.'
             if events else ' NASA EONET returned no cataloged wildfire for this search box and period. Local incidents may be absent from its catalog.')
    return {'url':url,'status':'checked','events':events},summary
