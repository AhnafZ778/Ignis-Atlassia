"""A one-month, fixed-region comparison of original MODIS collection files.

This descriptive pilot is not a temporal transfer qualification or coverage mask.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path

from .core import GRID_VERSION, TO_GRID
from .regions import REGIONS

HEADER = 'YYYYMMDD HHMM sat lat lon T21 T31 sample FRP conf type dn'
MAX_EXPANDED = 256_000_000


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read_month(path):
    """Read all records, validating time and coordinates before regional filtering."""
    cells = {region: defaultdict(set) for region in REGIONS}
    counts = {region: defaultdict(Counter) for region in REGIONS}
    total = 0
    with gzip.open(path, 'rb') as source:
        header = source.readline(4097); total += len(header)
        if len(header) > 4096 or header.decode('ascii').strip() != HEADER:
            raise ValueError('Unexpected MODIS monthly header.')
        while raw := source.readline(4097):
            total += len(raw)
            if total > MAX_EXPANDED or len(raw) > 4096:
                raise ValueError('MODIS monthly input exceeds the processing bound.')
            try:
                fields = raw.decode('ascii').split()
                if len(fields) != 12: raise ValueError('Invalid field count.')
                stamp, clock, platform, lat, lon = fields[:5]
                date = datetime.strptime(stamp + clock.zfill(4), '%Y%m%d%H%M')
                if len(stamp) != 8 or len(clock) not in (1, 2, 3, 4) or date.strftime('%Y%m') != '202301':
                    raise ValueError('Unexpected acquisition time.')
                lat, lon = float(lat), float(lon)
                if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                    raise ValueError('Invalid coordinates.')
                if platform not in ('T', 'A') or fields[10] not in ('0', '1', '2', '3') or fields[11] not in ('D', 'N'):
                    raise ValueError('Unexpected satellite or category.')
            except (UnicodeError, ValueError, OverflowError) as exc:
                raise ValueError('Invalid MODIS source record.') from exc
            if fields[10] != '0': continue
            day = date.strftime('%Y-%m-%d')
            for region, definition in REGIONS.items():
                west, south, east, north = definition['bbox']
                if west <= lon <= east and south <= lat <= north:
                    x, y = TO_GRID.transform(lon, lat)
                    cells[region][day].add((math.floor(x / 1000), math.floor(y / 1000)))
                    counts[region][day][platform] += 1
    return cells, counts


def compare(paths, provenance):
    if set(paths) != {'C6', 'C61'} or set(provenance) != {'C6', 'C61'}:
        raise ValueError('Both collection originals are required.')
    first, counts_first = read_month(paths['C6'])
    second, counts_second = read_month(paths['C61'])
    regions = {}
    for region in REGIONS:
        days = []
        for day in range(1, 32):
            date = f'2023-01-{day:02d}'
            a, b = first[region][date], second[region][date]
            union = len(a | b)
            days.append({'date': date, 'c6_cells': len(a), 'c61_cells': len(b),
                         'both_cells': len(a & b), 'c6_only_cells': len(a - b),
                         'c61_only_cells': len(b - a),
                         'jaccard': len(a & b) / union if union else None,
                         'c6_rows': dict(sorted(counts_first[region][date].items())),
                         'c61_rows': dict(sorted(counts_second[region][date].items()))})
        shared=sum(d['both_cells'] for d in days)
        only_c6=sum(d['c6_only_cells'] for d in days)
        only_c61=sum(d['c61_only_cells'] for d in days)
        union=shared+only_c6+only_c61
        regions[region] = {'bbox': list(REGIONS[region]['bbox']), 'days': days,
                           'month_cell_days': {'c6': shared+only_c6, 'c61': shared+only_c61,
                                               'both': shared, 'c6_only': only_c6, 'c61_only': only_c61,
                                               'union': union, 'jaccard': shared/union if union else None}}
    result = {'schema': 'fireatlas-modis-collection-pilot-v1', 'month': '2023-01',
              'grid': GRID_VERSION, 'source_files': provenance, 'regions': regions,
              'method': 'Type 0 detection centroids, unique 1 km cells per UTC day; T/A row counts retain source platform.',
              'scope': 'One global-file month; file-based zero counts do not establish clear observation or absence of fire.',
              'transfer_qualified': False, 'independent_review': False}
    result['result_sha256'] = digest(result)
    return result
