"""Historical FIRMS checks around a documented regional fire."""
from datetime import date, datetime, timezone
import hashlib
import re
import time
from urllib.parse import quote

from .. import fetch
from ..settings import firms_key
from .board_views import project_firms_views, requests_open_fire_heatmap
from .contracts import digest, normalize_context
from .firms_country import LIMIT, read_area_records

START, END = '2024-05-04', '2024-05-06'
BOUNDS = [89.58, 22.25, 89.87, 22.55]
REFERENCE = {
    'name': 'Amrabunia locality',
    'latitude': 22.41466,
    'longitude': 89.72334,
    'url': 'https://www.geonames.org/7486535/amrabunia.html',
}
INCIDENT = {
    'name': 'Reported fire near Amurbunia, Chandpai Range',
    'date': START,
    'url': 'https://www.bssnews.net/news/187145',
}
PRODUCTS = {
    'MODIS_SP': ('MODIS', 'brightness'),
    'VIIRS_SNPP_SP': ('Suomi-NPP VIIRS', 'bright_ti4'),
    'VIIRS_NOAA20_SP': ('NOAA-20 VIIRS', 'bright_ti4'),
    'VIIRS_NOAA21_SP': ('NOAA-21 VIIRS', 'bright_ti4'),
}


_SUNDARBANS_LANDSCAPE = 'https://ntca.gov.in/assets/uploads/Reports/WII/status_tigers_sundarban_landscape_india_bangladesh.pdf'


def sundarbans_scope(place):
    """Named landscape rectangles derived from the joint landscape report."""
    match=re.fullmatch(r'(?:the\s+)?sund(?:ar|er)bans?(?:\s+(?:mangrove\s+)?forest)?(?:[ ,]+(?:in\s+)?(Bangladesh|India))?',place,re.I)
    if not match:
        return None
    side=(match[1] or '').lower()
    label,bounds={
        'bangladesh':('Sundarbans landscape · Bangladesh-side search box',[89,21.5,89.91667,22.5]),
        'india':('Sundarbans landscape · India-side search box',[88.03222,21.66778,89.10028,22.15583]),
        '':('Sundarbans landscape · Bangladesh and India search box',[88.03222,21.5,89.91667,22.5]),
    }[side]
    west,south,east,north=bounds
    reference={'name':'Sundarbans','latitude':(south+north)/2,'longitude':(west+east)/2,
               'url':_SUNDARBANS_LANDSCAPE,'source':'Joint Sundarban landscape report'}
    return label,bounds,reference


def requests_sundarbans_heatmap(message):
    return requests_open_fire_heatmap(message, r'(?:east(?:ern)?\s+)?sund(?:ar|er)bans?(?:\s+(?:mangrove\s+)?forest)?')


def sundarbans_answer(service, owner, cancel, deadline, *, kinds=('heatmap',)):
    key = firms_key()
    if not key:
        raise ValueError('Checking the Sundarbans archive requires a server-side NASA FIRMS map key.')
    extent = ','.join(map(str, BOUNDS))
    days = (date.fromisoformat(END) - date.fromisoformat(START)).days + 1
    west, south, east, north = BOUNDS
    checks = []
    for source, (sensor, band) in PRODUCTS.items():
        if cancel.is_set() or time.monotonic() > deadline:
            raise InterruptedError('Investigation stopped or timed out.')
        url = '/'.join((fetch.BASE_URL, quote(key, safe=''), source, extent, str(days), START))
        body = fetch._download(url, f'{sensor} historical Sundarbans readings', limit=800_000)
        records = []
        for row in read_area_records(body, band, cancel, deadline):
            day = row['acquisition_utc'][:10]
            if not (START <= day <= END and west <= row['longitude'] <= east and south <= row['latitude'] <= north):
                raise ValueError('NASA FIRMS returned a reading outside the requested Sundarbans window.')
            if len(records) >= LIMIT:
                raise ValueError('Too many historical readings for this board view.')
            records.append(row)
        checks.append({'product': source, 'sensor': sensor, 'band': band, 'detections': len(records),
                       'source_csv_sha256': hashlib.sha256(body.encode('utf-8')).hexdigest(), 'records': records})
    if cancel.is_set() or time.monotonic() > deadline:
        raise InterruptedError('Investigation stopped or timed out.')

    selected = max(checks, key=lambda check: check['detections'])
    has_detections = bool(selected['detections'])
    label = 'heatmap' if has_detections else 'FIRMS search area'
    summary = (
        f'{selected["sensor"]} returned {selected["detections"]:,} detections in the May 4–6, 2024 UTC search area '
        'near the reported Amurbunia fire. Individual detections have no confirmed incident attribution.'
        if has_detections else
        'A fire was reported near Amurbunia on May 4, 2024. Four NASA FIRMS products returned no detections '
        'in the mapped area for May 4–6 UTC. The incident report is linked on the board.'
    )
    payload = {
        'title': f'Eastern Sundarbans · {label}', 'incident': INCIDENT, 'reference': REFERENCE,
        'product': selected['product'] if has_detections else None, 'sensor': selected['sensor'] if has_detections else None,
        'checks': checks, 'records': selected['records'], 'note': summary,
    }
    context = normalize_context({'bbox': BOUNDS, 'start': START, 'end': END, 'day': START, 'year': 2024, 'month': 5})
    return publish_regional_map(service, owner, context, payload,kinds=kinds)


def publish_regional_map(service, owner, context, payload, *, kinds=('heatmap',)):
    checks=payload['checks']
    live=any(item['product'].endswith('_NRT') for item in checks)
    receipt = {
        'schema': 'fireatlas-assistant-evidence-v1', 'operation': 'firms_region', 'context': context,
        'method': {'id': 'nasa-firms-area-nrt-v1' if live else 'nasa-firms-historical-area-v1', 'unit': 'returned detection records',
                   'filter': 'NASA FIRMS area queries by product, UTC dates and bounds.'},
        'release_id': 'nasa-firms-region:'+digest([(item['product'], item['source_csv_sha256']) for item in checks]),
        'release_frozen': False, 'grid': 'original coordinates',
        'payload': {**payload,'retrieved_utc':datetime.now(timezone.utc).isoformat(timespec='seconds')},
        'limitations': ['Returned detections describe satellite records in the search window. The reference pin marks a locality.'],
    }
    receipt['sha256'] = digest(receipt)
    identifier = service.store.artifact(owner, 'evidence', receipt)
    from .agent import guided_answer
    response = guided_answer({'id': identifier, **receipt})
    reference=payload.get('incident') or payload.get('event_context') or payload['reference']
    response['kind']='Saved scientific view'
    return project_firms_views(response,'firms_region',identifier,kinds,reference['url'],payload=payload,scope=context)
