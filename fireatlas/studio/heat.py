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
    w, s, e, n = snapshot['scope']['bbox']
    values = array.array('f', [0]) * (WIDTH * HEIGHT)
    cells = [cell for cell in frame['cells'] if source == 'joint' or source in cell['sources']]
    for cell in cells:
        x, y = (cell['longitude'] - w) / (e - w) * WIDTH, (n - cell['latitude']) / (n - s) * HEIGHT
        sx = max(.35, WIDTH / ((e - w) * 111.32 * math.cos(math.radians(cell['latitude']))))
        sy = max(.35, HEIGHT / ((n - s) * 111.32))
        for row in range(max(0, math.floor(y - sy * 3)), min(HEIGHT, math.ceil(y + sy * 3))):
            for col in range(max(0, math.floor(x - sx * 3)), min(WIDTH, math.ceil(x + sx * 3))):
                distance = ((col - x) / sx) ** 2 + ((row - y) / sy) ** 2
                if distance <= 9:
                    values[row * WIDTH + col] += math.exp(-distance / 2)
    domain = maximum(frames)
    data = png(values, domain)
    return {'kind': 'heat', 'schema': SCHEMA, 'scope': snapshot['scope'], 'day': day, 'source': source,
            'receipt_sha256': snapshot['receipt_sha256'], 'release_id': snapshot['release_id'],
            'count': len(cells), 'products': frame['products'], 'domain': [0, domain],
            'scale_scope': 'full frozen study, all dates and both sensors', 'sigma_km': 1, 'support_sigma': 3,
            'unit': 'Gaussian occupied-cell concentration', 'mime': 'image/png',
            'width': WIDTH, 'height': HEIGHT, 'sha256': hashlib.sha256(data).hexdigest(),
            'data': base64.b64encode(data).decode(),
            'label': 'Schematic common-cell heat; no perimeter or burned-area estimate'}
