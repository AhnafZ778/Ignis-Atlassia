"""Portable occupied-cell heat images from frozen replay receipts.

The geographic Gaussian and study-wide joint maximum match FireAtlasMap.
This is a display statistic, never additional detections or burned area.
Only controlled PNG bytes are produced; no imagery service is contacted.
"""
from __future__ import annotations

import array
import base64
import hashlib
import math
import struct
import zlib

from .errors import LimitExceeded, StudioError

SCHEMA = "fireatlas-studio-heat-v1"
WIDTH, HEIGHT = 360, 170
SOURCES = ("joint", "MODIS_SP", "VIIRS_SNPP_SP")
STOPS = ((255, 242, 178), (254, 196, 79), (252, 141, 60), (227, 74, 51), (179, 0, 0))


def concentration(cells, target):
    value = 0.0
    for cell in cells:
        dy = (cell['latitude'] - target['latitude']) * 111.32
        dx = (cell['longitude'] - target['longitude']) * 111.32 * math.cos(math.radians(target['latitude']))
        distance = dx * dx + dy * dy
        if distance <= 9:
            value += math.exp(-distance / 2)
    return value


def maximum(frames):
    """Same occupied-center reference, all dates and both sensor panes."""
    result = 0.0
    for frame in frames:
        cells = frame['cells']
        cosine = math.cos(math.radians(cells[0]['latitude'])) if cells else 1
        bins = {}
        for cell in cells:
            key = (math.floor(cell['longitude'] * 111.32 * cosine), math.floor(cell['latitude'] * 111.32))
            bins.setdefault(key, []).append(cell)
        for target in cells:
            x = math.floor(target['longitude'] * 111.32 * cosine)
            y = math.floor(target['latitude'] * 111.32)
            radius = math.ceil(3 * cosine / math.cos(math.radians(target['latitude']))) + 1
            near = [cell for dx in range(-radius, radius + 1) for dy in range(-4, 5)
                    for cell in bins.get((x + dx, y + dy), [])]
            result = max(result, concentration(near, target))
    return result or 1.0


def png(values, domain):
    """Small deterministic RGBA PNG; transparency carries the dark map surface."""
    rows = bytearray()
    for y in range(HEIGHT):
        rows.append(0)
        for value in values[y * WIDTH:(y + 1) * WIDTH]:
            ratio = min(1.0, value / domain)
            if ratio < .008:
                rows.extend((0, 0, 0, 0))
                continue
            position = ratio * 4
            index = min(3, math.floor(position))
            fraction = position - index
            rgb = [math.floor(first + (last - first) * fraction + .5)
                   for first, last in zip(STOPS[index], STOPS[index + 1])]
            rows.extend((*rgb, math.floor(215 * math.sqrt(ratio) + .5)))
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', WIDTH, HEIGHT, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b''))


def prepare(snapshot, receipt, selection, source):
    if source not in SOURCES:
        raise StudioError('Choose a standard sensor for the frozen heat image.', code='scene-context')
    frames = receipt['payload'].get('frames') or []
    if len(frames) > 31 or sum(len(frame['cells']) for frame in frames) > 10000:
        raise LimitExceeded('Frozen heat preparation retains the replay detail limits without sampling.', code='scene-limit')
    bounds = snapshot['scope']['bbox']
    if (len(bounds) != 4 or any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in bounds)
            or not -180 <= bounds[0] < bounds[2] <= 180 or not -86 <= bounds[1] < bounds[3] <= 86):
        raise StudioError('Frozen heat images require a valid common-grid study boundary.', code='scene-context')
    for candidate in frames:
        for cell in candidate['cells']:
            if any(not isinstance(cell.get(key), (int, float)) or isinstance(cell.get(key), bool)
                   or not math.isfinite(cell[key]) for key in ('longitude', 'latitude')):
                raise StudioError('Frozen heat coordinates must be finite.', code='scene-context')
            # The occupied grid-cell center can sit just beyond the exact
            # centroid selection box. Crop its display, retaining its count.
            if not -180 <= cell['longitude'] <= 180 or not -86 <= cell['latitude'] <= 86:
                raise StudioError('Frozen heat cells must stay inside the common-grid geographic domain.', code='scene-context')
    if selection.get('start') or selection.get('end'):
        raise StudioError('This heat image uses one UTC date. Use a common-cell interval map for an interval.', code='scene-context')
    day = selection.get('day') or snapshot['scope'].get('day') or snapshot['scope']['start']
    frame = next((frame for frame in frames if frame['date_utc'] == day), None)
    if frame is None:
        raise StudioError('The selected heat-image date is absent from the frozen receipt.', code='scene-context')
    cells = [cell for cell in frame['cells'] if source == 'joint' or source in cell['sources']]
    domain = maximum(frames)
    return {**raster_fields(snapshot, cells, domain), 'day':day, 'source':source,
            'products':frame['products'], 'scale_scope':'full frozen study, all dates and both sensors',
            'label':'Schematic common-cell heat; no perimeter or burned-area estimate'}


def cell_index(record):
    """Use the same EPSG:6933 centroid assignment as the site's archive."""
    from ..core import GRID_METERS, TO_GRID
    x,y=TO_GRID.transform(record['longitude'],record['latitude'])
    return math.floor(x/GRID_METERS),math.floor(y/GRID_METERS)


def raster_fields(snapshot, cells, domain):
    w, s, e, n = snapshot['scope']['bbox']
    values = array.array('f', [0]) * (WIDTH * HEIGHT)
    for cell in cells:
        x, y = (cell['longitude'] - w) / (e - w) * WIDTH, (n - cell['latitude']) / (n - s) * HEIGHT
        sx = max(.35, WIDTH / ((e - w) * 111.32 * math.cos(math.radians(cell['latitude']))))
        sy = max(.35, HEIGHT / ((n - s) * 111.32))
        for row in range(max(0, math.floor(y - sy * 3)), min(HEIGHT, math.ceil(y + sy * 3))):
            for col in range(max(0, math.floor(x - sx * 3)), min(WIDTH, math.ceil(x + sx * 3))):
                distance = ((col - x) / sx) ** 2 + ((row - y) / sy) ** 2
                if distance <= 9:
                    values[row * WIDTH + col] += math.exp(-distance / 2)
    data=png(values,domain)
    return {'kind':'heat', 'schema':SCHEMA, 'scope':snapshot['scope'],
            'receipt_sha256':snapshot['receipt_sha256'], 'release_id':snapshot['release_id'],
            'count':len(cells), 'domain':[0,domain], 'sigma_km':1, 'support_sigma':3,
            'unit':'Gaussian occupied-cell concentration', 'mime':'image/png',
            'width':WIDTH, 'height':HEIGHT, 'sha256':hashlib.sha256(data).hexdigest(),
            'data':base64.b64encode(data).decode(), 'label':'Gaussian concentration of occupied 1 km cells'}


def prepare_area(snapshot, receipt):
    """Apply the replay heat renderer to the verified FIRMS interval's unique grid cells."""
    from ..core import GRID_METERS
    from ..replay import FROM_GRID
    payload=receipt['payload']
    records=payload['records']
    cells=[]
    for gx,gy in sorted({cell_index(row) for row in records}):
        longitude,latitude=FROM_GRID.transform((gx+.5)*GRID_METERS,(gy+.5)*GRID_METERS)
        cells.append({'longitude':longitude,'latitude':latitude})
    source=payload.get('product')
    primary=next((check for check in payload['checks'] if check['product']==source),{})
    scope=snapshot['scope']
    start,end=primary.get('available_start',scope['start']),primary.get('available_end',scope['end'])
    return {**raster_fields(snapshot,cells,maximum([{'cells':cells}])),
            'day':end,'interval':{'start':start,'end':end},
            'source':source, 'sensor':payload.get('sensor') or 'NASA FIRMS',
            'title':(payload.get('title') or payload.get('country') or 'FIRMS area')+' · thermal concentration',
            'detections':len(records), 'points':cells, 'reference':payload.get('reference'),
            'outline':payload.get('country_outline', []),
            'scale_scope':'unique occupied cells across the queried UTC interval'}


def prepare_comparison(snapshot, receipt):
    """One geographic Gaussian domain for every frozen comparison panel."""
    from ..core import GRID_METERS
    from ..replay import FROM_GRID
    panels = receipt['payload']['panels']
    frames = []
    for panel in panels:
        cells = []
        for gx, gy in sorted({cell_index(row) for row in panel['records']}):
            lon, lat = FROM_GRID.transform((gx+.5)*GRID_METERS, (gy+.5)*GRID_METERS)
            cells.append({'longitude': lon, 'latitude': lat})
        frames.append({'cells': cells})
    domain = receipt['payload']['heat_scale']['domain'][1]
    if not isinstance(domain, (int, float)) or not math.isfinite(domain) or domain <= 0 or abs(domain-maximum(frames)) > 1e-9:
        raise StudioError('The frozen comparison heat scale does not match its source cells.', code='receipt-mismatch')
    rendered = []
    for panel, frame in zip(panels, frames):
        scope = {**snapshot['scope'], 'bbox': panel['bbox'], 'start': panel['start'], 'end': panel['end'], 'day': panel['day']}
        heat = {**raster_fields({**snapshot, 'scope': scope}, frame['cells'], domain),
                'day': panel['day'] or panel['end'], 'interval': {'start': panel['start'], 'end': panel['end']},
                'source': panel['product'], 'sensor': panel['sensor'], 'title': panel['label'],
                'detections': panel['detections'], 'points': frame['cells'], 'reference': panel.get('reference'),
                'comparison_scale': True, 'scale_scope': 'shared across every panel in this frozen comparison'}
        rendered.append({**{k: v for k, v in panel.items() if k != 'records'}, 'heat': heat})
    return {'kind': 'regional-comparison', 'title': receipt['payload']['title'], 'mode': receipt['payload']['mode'],
            'rank_by': receipt['payload']['rank_by'], 'domain': [0, domain], 'panels': rendered,
            'note': receipt['payload']['note']}
