"""Model-callable comparison acquisition and frozen environmental context."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .. import fetch
from ..heatmap_comparison import METHOD, build_comparison
from ..settings import firms_key
from .contracts import digest, normalize_context
from .firms_country import read_area_records, PRODUCTS, LIMIT
from .firms_history import window_readings
from .place_fire import locate, WINDOW_KM
from .regional_fire import sundarbans_scope

PRODUCT_IDS = ('MODIS_SP', 'VIIRS_SNPP_SP', 'VIIRS_NOAA20_SP', 'VIIRS_NOAA21_SP')


def research_question(message):
    """Admission to the reasoning agent only; never parse a research plan here."""
    import re
    return bool(re.search(r'\b(?:compar\w*|differences?|versus|vs\.?|across|busiest|busy days|peak days|three years|3 years)\b', message, re.I)
                and re.search(r'\b(?:heatmaps?|regions?|areas?|years?|days?|thermal|readings?)\b', message, re.I))


def resolve_area(place):
    landscape = sundarbans_scope(place)
    if landscape:
        return landscape
    matches = locate(place)
    if len(matches) != 1:
        choices = ', '.join(', '.join(filter(None, (item.get('name'), item.get('admin1'), item.get('country')))) for item in matches[:4])
        raise ValueError('Name one unambiguous city/locality with its country. ' + ('Choices: ' + choices if choices else 'No matching locality was found.'))
    item = matches[0]
    lat, lon = float(item['latitude']), float(item['longitude'])
    if not -85 < lat < 85 or not -180 < lon < 180:
        raise ValueError('The comparison locality is outside the supported geographic grid.')
    dy = WINDOW_KM / 2 / 111.32
    dx = dy / math.cos(math.radians(lat))
    bounds = [round(max(-180, lon-dx), 5), round(lat-dy, 5), round(min(180, lon+dx), 5), round(lat+dy, 5)]
    label = ', '.join(dict.fromkeys(filter(None, (item['name'], item.get('country')))))
    return label, bounds, {'name': label, 'latitude': lat, 'longitude': lon,
                           'url': f'https://www.geonames.org/{int(item["id"])}',
                           'source': 'GeoNames via Open-Meteo; roughly 40 km search rectangle, not administrative boundary'}


def weather_context(bounds, day, cancel, deadline):
    """Seven UTC days at a reanalysis grid point, never a causal attribution."""
    if cancel.is_set() or time.monotonic() >= deadline:
        raise InterruptedError('Investigation stopped.')
    end = date.fromisoformat(day)
    start = end - timedelta(days=6)
    lat, lon = (bounds[1]+bounds[3])/2, (bounds[0]+bounds[2])/2
    params = {'latitude': lat, 'longitude': lon, 'start_date': str(start), 'end_date': str(end),
              'daily': 'temperature_2m_max,precipitation_sum,wind_speed_10m_max', 'models': 'era5', 'timezone': 'GMT', 'wind_speed_unit': 'kmh'}
    url = 'https://archive-api.open-meteo.com/v1/archive?' + urlencode(params)
    try:
        with urlopen(Request(url, headers={'Accept': 'application/json'}), timeout=min(10, max(1, deadline-time.monotonic()))) as response:
            raw = response.read(200_001)
        if len(raw) > 200_000:
            raise ValueError('Weather response too large.')
        value = json.loads(raw)
        daily = value['daily']
        expected = [(start+timedelta(days=i)).isoformat() for i in range(7)]
        if daily['time'] != expected:
            raise ValueError('Weather dates do not match the requested UTC window.')
        fields = ('temperature_2m_max', 'precipitation_sum', 'wind_speed_10m_max')
        if any(len(daily[key]) != 7 or any(v is not None and (type(v) not in (int, float) or not math.isfinite(v)) for v in daily[key]) for key in fields):
            raise ValueError('Weather values are invalid.')
        units = value['daily_units']
        if units['precipitation_sum'] != 'mm' or units['wind_speed_10m_max'] != 'km/h' or units['temperature_2m_max'] != '°C':
            raise ValueError('Weather units do not match the comparison.')
        def complete(key):
            return all(v is not None for v in daily[key])
        return {'status': 'available', 'source': 'ERA5 reanalysis via Open-Meteo', 'url': url,
                'sha256': hashlib.sha256(raw).hexdigest(), 'latitude': lat, 'longitude': lon,
                'start': str(start), 'end': str(end), 'daily': daily, 'units': units,
                'original_response': value, 'request_latitude': lat, 'request_longitude': lon,
                'air_temperature_max_c': max(daily['temperature_2m_max']) if complete('temperature_2m_max') else None,
                'rainfall_7d_mm': round(sum(daily['precipitation_sum']), 4) if complete('precipitation_sum') else None,
                'wind_max_kmh': max(daily['wind_speed_10m_max']) if complete('wind_speed_10m_max') else None,
                'note': 'Seven-day reanalysis at the search-box center; regional conditions and causation are not established.'}
    except (OSError, ValueError, KeyError, TypeError):
        return {'status': 'unavailable', 'note': 'Weather context could not be verified. Thermal evidence is retained; no weather values were invented.'}


def prepare(service, owner, *, places, years=None, start=None, end=None, mode='regions', product='VIIRS_NOAA20_SP',
            rank_by='occupied_cells', top_days=1, include_weather=True, cancel, deadline, progress):
    today = datetime.now(timezone.utc).date()
    if rank_by not in {'occupied_cells', 'detections'} or type(top_days) is not int or not 1 <= top_days <= 3:
        raise ValueError('Choose occupied_cells or detections and one to three peak days.')
    if mode not in {'regions', 'annual_peaks'} or product not in PRODUCT_IDS:
        raise ValueError('Choose regional heatmaps or annual peak days and one supported standard-processing FIRMS product.')
    if not isinstance(places, list) or not 1 <= len(places) <= 3 or any(not isinstance(p, str) or not 1 <= len(p.strip()) <= 120 for p in places):
        raise ValueError('Name one to three cities/localities, including their countries when needed.')
    if mode == 'annual_peaks':
        years = years or list(range(today.year-3, today.year))
        if len(places) != 1 or not 1 <= len(years) <= 3 or any(type(y) is not int or not 2000 <= y < today.year for y in years) or len(set(years)) != len(years):
            raise ValueError('Annual peaks compare one place across up to three completed calendar years.')
        intervals = [(f'{y}-01-01', f'{y}-12-31') for y in sorted(years)]
    else:
        if years:
            raise ValueError('Use annual_peaks for year ranking, or explicit start and end for a regional comparison.')
        if not start or not end:
            raise ValueError('Give explicit UTC start and end dates for the regional comparison.')
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if first > last or last > today or (last-first).days > 365:
            raise ValueError('Use a past UTC interval of at most one year.')
        intervals = [(start, end)]
    if len(places)*len(intervals)*top_days > 6:
        raise ValueError('Compare up to six heatmap panels at once.')
    key = firms_key()
    if not key:
        raise ValueError('NASA FIRMS access is not configured on this server. Compare saved heatmaps instead or configure acquisition.')
    available = {v['data_id']: (v['min_date'], v['max_date']) for v in fetch.availability()}
    if product not in available or any(not available[product][0] <= lo <= hi <= available[product][1] for lo, hi in intervals):
        raise ValueError('This product does not cover the entire requested interval. A partial year cannot establish its busiest day.')
    studies = []
    for place in places:
        label, bounds, reference = resolve_area(place)
        for lo, hi in intervals:
            progress('retrieving '+label+' '+lo+' to '+hi)
            sensor, band = PRODUCTS[product.replace('_SP', '_NRT')]
            check = window_readings(key, product, sensor, band, bounds, date.fromisoformat(lo), date.fromisoformat(hi), cancel, deadline,
                                    read_records=read_area_records, limit=800_000, row_limit=LIMIT)
            studies.append({'label': label, 'bbox': bounds, 'reference': reference, 'start': lo, 'end': hi, 'check': check})
    payload = build_comparison(studies, mode=mode, rank_by=rank_by, top_days=top_days)
    if include_weather:
        for panel in payload['panels']:
            if panel['state'] == 'queried':
                progress('checking weather context '+panel['label']+' '+panel['end'])
                panel['weather'] = weather_context(panel['bbox'], panel['end'], cancel, deadline)
    return publish(service, owner, payload)


def publish(service, owner, payload):
    from ..studio.heat import maximum
    from ..heatmap_comparison import cell_key
    from ..core import GRID_METERS
    from ..replay import FROM_GRID
    frames = []
    for candidate in payload['panels']:
        cells = []
        for gx, gy in sorted({cell_key(row) for row in candidate['records']}):
            lon, lat = FROM_GRID.transform((gx+.5)*GRID_METERS, (gy+.5)*GRID_METERS)
            cells.append({'longitude': lon, 'latitude': lat})
        frames.append({'cells': cells})
    payload['heat_scale'] = {'domain': [0, maximum(frames)], 'sigma_km': 1,
                             'unit': 'Gaussian occupied-cell concentration', 'basis': 'all frozen comparison panels'}
    panel = payload['panels'][0]
    context = normalize_context({'bbox': panel['bbox'], 'start': panel['start'], 'end': panel['end'], 'day': panel['start'],
                                 'year': int(panel['start'][:4]), 'month': int(panel['start'][5:7])})
    receipt = {'schema': 'fireatlas-assistant-evidence-v1', 'operation': 'regional_comparison', 'context': context,
               'method': METHOD, 'grid': 'EPSG:6933 centroid assignment; 1000 m cells', 'release_frozen': True,
               'release_id': 'regional-comparison:'+digest(payload), 'payload': payload,
               'limitations': [payload['note'], 'Weather is point reanalysis context, not a causal explanation or a region-wide measurement.']}
    receipt['sha256'] = digest(receipt)
    identifier = service.store.artifact(owner, 'evidence', receipt)
    return {**receipt, 'id': identifier}


def from_saved(service, owner, receipts, *, rank_by='occupied_cells', include_weather=True, cancel, deadline):
    """Compare the exact frozen windows selected on this owned board."""
    if not 2 <= len(receipts) <= 3:
        raise ValueError('Select two or three saved single-product heatmaps.')
    studies = []
    for receipt in receipts:
        payload, context = receipt['payload'], receipt['context']
        if receipt['operation'] not in {'firms_region', 'firms_country'}:
            raise ValueError('Saved comparison currently needs source-linked FIRMS area maps. Ask for named localities and dates to acquire a new comparison.')
        product = payload.get('product')
        check = next((item for item in payload.get('checks', []) if item.get('product') == product), None)
        if not check:
            raise ValueError('The saved map does not retain a single verified product window.')
        studies.append({'label': payload.get('title') or payload.get('country') or 'Saved area', 'bbox': context['bbox'],
                        'reference': payload.get('reference'), 'start': context['start'], 'end': context['end'], 'check': check})
    payload = build_comparison(studies, mode='saved', rank_by=rank_by)
    payload['source_receipt_sha256'] = [receipt['sha256'] for receipt in receipts]
    if include_weather:
        for panel in payload['panels']:
            panel['weather'] = weather_context(panel['bbox'], panel['end'], cancel, deadline)
    return publish(service, owner, payload)
