"""Retrospective, month-by-month MODIS collection overlap research.

This separate method preserves the original January pilot and never admits a
collection bridge. Callers must bind inputs to original download receipts.
"""
from __future__ import annotations

from calendar import monthrange
from collections import Counter, defaultdict
from datetime import datetime
import gzip
import math
import re

from .core import GRID_VERSION, TO_GRID
from .modis_collection_pilot import HEADER, MAX_EXPANDED, digest
from .regions import REGIONS


def parse_month(month):
    if not isinstance(month, str) or not re.fullmatch(r'\d{4}-\d{2}', month):
        raise ValueError('Month must be YYYY-MM.')
    year, number = map(int, month.split('-'))
    if year < 2000 or not 1 <= number <= 12:
        raise ValueError('Unsupported MODIS month.')
    return year, number


def read_month(path, month):
    year, number = parse_month(month)
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
                if len(stamp) != 8 or len(clock) not in (1, 2, 3, 4) or (date.year, date.month) != (year, number):
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


def compare_month(month, paths, provenance):
    year, number = parse_month(month)
    if set(paths) != {'C6', 'C61'} or set(provenance) != {'C6', 'C61'}:
        raise ValueError('Both collection originals are required.')
    first, counts_first = read_month(paths['C6'], month)
    second, counts_second = read_month(paths['C61'], month)
    regions = {}
    for region in REGIONS:
        days = []
        for day in range(1, monthrange(year, number)[1] + 1):
            date = f'{month}-{day:02d}'
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
        regions[region]={'bbox':list(REGIONS[region]['bbox']), 'days':days,
                         'month_cell_days':{'c6':shared+only_c6, 'c61':shared+only_c61,
                         'both':shared, 'c6_only':only_c6, 'c61_only':only_c61,
                         'union':union, 'jaccard':shared/union if union else None}}
    result={'schema':'fireatlas-modis-collection-month-v2', 'month':month,
            'grid':GRID_VERSION, 'source_files':provenance, 'regions':regions,
            'method':'Type 0 detection centroids, unique 1 km cells per UTC day; T/A row counts retain source platform.',
            'scope':'One global-file month; zero counts do not establish observation opportunity or absence of fire.',
            'transfer_qualified':False, 'independent_review':False}
    result['result_sha256']=digest(result)
    return result


def summarize(requested_months, results):
    """Format supplied month results; a hash alone does not prove source recount."""
    if not isinstance(requested_months, list) or not 1 <= len(requested_months) <= 240:
        raise ValueError('One to 240 requested months are required.')
    for month in requested_months: parse_month(month)
    if requested_months != sorted(set(requested_months)):
        raise ValueError('Requested months must be unique and chronological.')
    if not isinstance(results, dict) or set(results)-set(requested_months):
        raise ValueError('Unexpected monthly result.')
    rows=[]
    for month in requested_months:
        value=results.get(month)
        if value is None:
            rows.append({'month':month,'status':'missing','result_sha256':None,'regions':None})
            continue
        if (not isinstance(value,dict) or value.get('schema')!='fireatlas-modis-collection-month-v2'
                or value.get('month')!=month or value.get('grid')!=GRID_VERSION
                or value.get('transfer_qualified') is not False or value.get('independent_review') is not False
                or digest({k:v for k,v in value.items() if k!='result_sha256'})!=value.get('result_sha256')
                or not isinstance(value.get('regions'),dict) or set(value['regions'])!=set(REGIONS)):
            raise ValueError('Invalid monthly result identity or scope.')
        rows.append({'month':month,'status':'supplied','result_sha256':value['result_sha256'],
                     'regions':{region:value['regions'][region]['month_cell_days'] for region in REGIONS}})
    result={'schema':'fireatlas-modis-collection-series-v1','months':rows,
            'requested_months':len(rows),'supplied_months':sum(row['status']=='supplied' for row in rows),
            'transfer_qualified':False,'independent_review':False,
            'scope':'Supplied monthly summaries require separate original-file recount; missing months are unknown, and overlap does not establish observation opportunity or a qualified bridge.'}
    result['result_sha256']=digest(result)
    return result
