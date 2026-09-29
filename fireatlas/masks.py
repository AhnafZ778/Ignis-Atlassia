"""Native MOD14/MYD14/VNP14IMG mask evidence on the calendar's centroid grid.

Uses GDAL for native HDF4/netCDF and paired geolocation; never extrapolates
centroids into full footprints. Missing/ambiguous cells stay unknown. No-pass
requires a separate verified footprint inventory and is never asserted here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pyproj import Transformer

from .core import TO_GRID, GRID_METERS, GRID_VERSION
from .granules import load as load_inventory

STORE = Path(__file__).resolve().parent.parent / 'data' / 'validity_masks.sqlite3'
SCHEMA = 'fireatlas-native-mask-evidence-v1'
FROM_GRID = Transformer.from_crs('EPSG:6933', 'EPSG:4326', always_xy=True)
PRODUCTS = {'MOD14': ('MOD03', 'MODIS_SP', 'Terra'),
            'MYD14': ('MYD03', 'MODIS_SP', 'Aqua'),
            'VNP14IMG': ('VNP03IMG', 'VIIRS_SNPP_SP', 'S-NPP')}
CLASS_NAMES = {0: 'missing-input', 1: 'not-processed-or-bowtie', 2: 'unusable',
               3: 'non-fire-water', 4: 'cloud', 5: 'non-fire-land',
               6: 'unknown', 7: 'fire-low', 8: 'fire-nominal', 9: 'fire-high'}
METHOD = {
    'grid': GRID_VERSION,
    'classes': {str(code): name for code, name in CLASS_NAMES.items()},
    'clear_classes': [3, 5], 'fire_classes': [7, 8, 9], 'cloud_class': 4,
    'geometry': 'native pixel centroid sampling; no footprint rasterization or full-cell coverage claim',
    'unknown_rule': 'unusable/mixed clear-cloud cells, absent files, no sampled centroid, invalid geolocation remain unknown',
    'no_pass_rule': 'never derived from this centroid processor or a missing CMR candidate',
    'daily_rule': 'fire takes precedence; non-fire or cloud requires a complete source candidate inventory and consistent sampled pass states',
    'pair_rule': 'same sampled 1 km cell; usable mask states; every endpoint of the two granule time intervals within 90 minutes; closest interval-centre pair first; each pass used once per cell',
    'reconciliation_rule': 'same platform; native fire centroid within 100 m; FIRMS minute within native interval plus 60-second rounding tolerance; report confidence disagreements separately',
    'modis_guide': 'https://modis-fire.umd.edu/files/MODIS_C6_C6.1_Fire_User_Guide_1.0.pdf',
    'viirs_guide': 'https://www.earthdata.nasa.gov/s3fs-public/2024-07/VIIRS_C2_AF-375m_User_Guide_1.0.pdf',
}


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def checksum(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def connect_store(path=STORE):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript('''
        CREATE TABLE IF NOT EXISTS granules (
            case_id TEXT, producer_id TEXT, product TEXT, source_id TEXT,
            platform TEXT, start_utc TEXT, end_utc TEXT, cmr_id TEXT,
            file_sha256 TEXT, geo_producer_id TEXT, geo_sha256 TEXT,
            status TEXT, error TEXT, mask_dataset TEXT, latitude_dataset TEXT,
            longitude_dataset TEXT, width INTEGER, height INTEGER,
            invalid_geolocation INTEGER, PRIMARY KEY(case_id,producer_id));
        CREATE TABLE IF NOT EXISTS pixels (
            case_id TEXT, producer_id TEXT, line INTEGER, sample INTEGER,
            lat REAL, lon REAL, mask_class INTEGER, grid_x INTEGER, grid_y INTEGER,
            PRIMARY KEY(case_id,producer_id,line,sample));
        CREATE INDEX IF NOT EXISTS mask_cells ON pixels(case_id,grid_x,grid_y);
    ''')
    return db


def native_layer(path, names):
    try:
        from osgeo import gdal
    except ImportError as error:
        raise RuntimeError(
            'Native mask processing needs GDAL with HDF4/netCDF support; '
            'see docs/NATIVE_MASK_VALIDATION.md'
        ) from error

    gdal.UseExceptions()
    gdal.SetConfigOption('GDAL_NETCDF_BOTTOMUP', 'NO')
    driver = 'HDF4' if Path(path).suffix.lower() == '.hdf' else 'netCDF'
    if gdal.GetDriverByName(driver) is None:
        raise RuntimeError(
            f'Native mask processing needs GDAL with the {driver} driver; '
            'see docs/NATIVE_MASK_VALIDATION.md'
        )
    root = gdal.Open(str(path))
    if root is None:
        raise ValueError('Native product could not be opened by GDAL')
    layers = []
    for uri, description in root.GetSubDatasets():
        # HDF4 names occur in descriptions, HDF5/netCDF variables in URI suffixes.
        label = uri.rsplit(':', 1)[-1].strip('"').rsplit('/', 1)[-1]
        descriptive = description.split(']')[-1].split('(')[0].strip()
        normalize = lambda s: re.sub(r'[^a-z0-9]', '', s.lower())
        if any(normalize(candidate) in {normalize(label), normalize(descriptive)} for candidate in names):
            layers.append((uri, gdal.Open(uri)))
    if len(layers) != 1:
        raise ValueError(f'Expected one {names} layer, found {len(layers)}; refusing inferred alignment')
    return layers[0]


def decode_file(mask_path, geo_path, bbox):
    """Yield clipped native samples in bounded strips; shape mismatch is fatal."""
    try:
        import numpy as np
    except ImportError as error:
        raise RuntimeError(
            'Native mask processing needs NumPy; run `uv sync --extra masks` '
            'and see docs/NATIVE_MASK_VALIDATION.md'
        ) from error
    mask_uri, mask = native_layer(mask_path, ('fire mask', 'fire_mask', 'FireMask'))
    lat_uri, latitude = native_layer(geo_path, ('Latitude', 'latitude'))
    lon_uri, longitude = native_layer(geo_path, ('Longitude', 'longitude'))
    shape = (mask.RasterYSize, mask.RasterXSize)
    if any((layer.RasterYSize, layer.RasterXSize) != shape for layer in (latitude, longitude)):
        raise ValueError('Mask/geolocation shapes differ; no resampling or guessed alignment is allowed')
    metadata = {'mask_dataset': mask_uri, 'latitude_dataset': lat_uri,
                'longitude_dataset': lon_uri, 'height': shape[0], 'width': shape[1],
                'invalid_geolocation': 0}
    west, south, east, north = bbox
    for offset in range(0, shape[0], 128):
        height = min(128, shape[0] - offset)
        codes = mask.ReadAsArray(0, offset, shape[1], height)
        lat = latitude.ReadAsArray(0, offset, shape[1], height)
        lon = longitude.ReadAsArray(0, offset, shape[1], height)
        valid = np.isfinite(lat) & np.isfinite(lon) & (abs(lat) <= 90) & (abs(lon) <= 180)
        metadata['invalid_geolocation'] += int((~valid).sum())
        included = valid & (lon >= west) & (lon <= east) & (lat >= south) & (lat <= north)
        lines, columns = np.nonzero(included)
        selected_codes = codes[included]
        if np.any((selected_codes < 0) | (selected_codes > 9) | (selected_codes != np.floor(selected_codes))):
            raise ValueError('Unexpected native mask class; refusing to treat fill values as observations')
        x, y = TO_GRID.transform(lon[included], lat[included])
        rows = [(int(r + offset), int(c), float(a), float(o), int(k),
                 math.floor(float(px) / GRID_METERS), math.floor(float(py) / GRID_METERS))
                for r, c, a, o, k, px, py in zip(lines, columns, lat[included], lon[included], selected_codes, x, y)]
        yield metadata, rows


def expected_pairs(inventory, case_id):
    case = inventory['cases'][case_id]
    products = {item['product']: item for item in case['products']}
    pairs = []
    for product, (companion, source, platform) in PRODUCTS.items():
        for granule in products[product]['granules']:
            geos = [item for item in products[companion]['granules'] if item['start_utc'] == granule['start_utc']]
            pairs.append({'product': product, 'source_id': source, 'platform': platform,
                          'granule': granule, 'geo': geos[0] if len(geos) == 1 else None})
    return pairs


def process(directory, case_id, store=STORE):
    inventory = load_inventory()
    bbox = inventory['cases'][case_id]['bbox']
    filenames = defaultdict(list)
    for path in Path(directory).rglob('*'):
        if path.is_file() and path.suffix.lower() in {'.hdf', '.nc', '.h5'}:
            filenames[path.name].append(path)
    with connect_store(store) as db:
        for pair in expected_pairs(inventory, case_id):
            granule, geo = pair['granule'], pair['geo']
            identifier = granule['producer_id']
            db.execute('DELETE FROM pixels WHERE case_id=? AND producer_id=?', (case_id, identifier))
            db.execute('DELETE FROM granules WHERE case_id=? AND producer_id=?', (case_id, identifier))
            record = {key: pair[key] for key in ('product', 'source_id', 'platform')}
            record.update(case_id=case_id, producer_id=identifier, start_utc=granule['start_utc'],
                          end_utc=granule['end_utc'], cmr_id=granule['cmr_id'],
                          geo_producer_id=geo['producer_id'] if geo else None, status='missing', error=None)
            mask_name = Path(urlsplit(granule['download_url']).path).name
            geo_name = Path(urlsplit(geo['download_url']).path).name if geo else None
            mask_paths = filenames[mask_name]
            geo_paths = filenames[geo_name] if geo_name else []
            try:
                if len(mask_paths) > 1 or len(geo_paths) > 1:
                    raise ValueError('Ambiguous duplicate native filename; place one exact version in input directory')
                if not mask_paths or not geo_paths:
                    record['error'] = 'Missing native fire mask or unique companion geolocation'
                else:
                    record.update(file_sha256=checksum(mask_paths[0]), geo_sha256=checksum(geo_paths[0]))
                    for metadata, rows in decode_file(mask_paths[0], geo_paths[0], bbox):
                        # Dataset identifiers contain local paths; retain only native layer names in exports.
                        record.update({key: value if not key.endswith('_dataset') else value.rsplit(':', 1)[-1]
                                       for key, value in metadata.items()})
                        db.executemany('INSERT INTO pixels VALUES(?,?,?,?,?,?,?,?,?)',
                                       [(case_id, identifier, *row) for row in rows])
                    record['status'] = 'processed'
            except (ValueError, RuntimeError, ImportError) as error:
                db.execute('DELETE FROM pixels WHERE case_id=? AND producer_id=?', (case_id, identifier))
                record.update(status='failed', error=str(error))
            keys = list(record)
            db.execute(f"INSERT INTO granules ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})", list(record.values()))
            db.commit()
    load_evidence.cache_clear()
    evidence = load_evidence(case_id, str(store), Path(store).stat().st_mtime_ns)
    return {'case_id': case_id, 'expected_fire_granules': len(evidence['inventory']),
            'processed': sum(item['status'] == 'processed' for item in evidence['inventory']),
            'clipped_native_pixels': len(evidence['pixels'])}


@lru_cache(maxsize=2)
def load_evidence(case_id, path, modified):
    with connect_store(path) as db:
        inventory = [dict(row) for row in db.execute('SELECT * FROM granules WHERE case_id=? ORDER BY producer_id', (case_id,))]
        pixels = [dict(row) for row in db.execute('SELECT * FROM pixels WHERE case_id=? ORDER BY producer_id,line,sample', (case_id,))]
    return {'schema': SCHEMA, 'case_id': case_id, 'method': METHOD, 'inventory': inventory, 'pixels': pixels}


def read_evidence(case_id, path=STORE):
    if not Path(path).exists():
        return {'schema': SCHEMA, 'case_id': case_id, 'method': METHOD, 'inventory': [], 'pixels': []}
    return load_evidence(case_id, str(path), Path(path).stat().st_mtime_ns)


def pass_state(counts):
    if any(counts.get(code, 0) for code in (7, 8, 9)):
        return 'detected'
    if counts and all(code in (3, 5) for code in counts):
        return 'observed-without-detection'
    if counts and all(code == 4 for code in counts):
        return 'cloud-obscured'
    return 'unknown'


def passes_from_pixels(evidence):
    groups = defaultdict(Counter)
    for pixel in evidence['pixels']:
        x, y = TO_GRID.transform(pixel['lon'], pixel['lat'])
        if (math.floor(x / GRID_METERS), math.floor(y / GRID_METERS)) != (pixel['grid_x'], pixel['grid_y']):
            raise ValueError('Native pixel grid assignment does not reproduce')
        if pixel['mask_class'] not in CLASS_NAMES:
            raise ValueError('Invalid native mask class')
        groups[(pixel['producer_id'], pixel['grid_x'], pixel['grid_y'])][pixel['mask_class']] += 1
    by_id = {item['producer_id']: item for item in evidence['inventory'] if item['status'] == 'processed'}
    result = []
    for (identifier, x, y), counts in sorted(groups.items()):
        if identifier not in by_id:
            raise ValueError('Native pixel references an unprocessed granule')
        granule = by_id[identifier]
        result.append({'producer_id': identifier, 'source_id': granule['source_id'],
                       'platform': granule['platform'], 'start_utc': granule['start_utc'],
                       'end_utc': granule['end_utc'], 'grid_x': x, 'grid_y': y,
                       'state': pass_state(counts), 'class_counts': dict(counts),
                       'file_sha256': granule['file_sha256'], 'geo_sha256': granule['geo_sha256']})
    return result


def paired_observations(passes):
    groups = defaultdict(lambda: defaultdict(list))
    for item in passes:
        if item['state'] in {'detected', 'observed-without-detection'}:
            groups[(item['grid_x'], item['grid_y'])][item['source_id']].append(item)
    pairs = []
    for (x, y), sources in sorted(groups.items()):
        candidates = []
        for modis in sources['MODIS_SP']:
            for viirs in sources['VIIRS_SNPP_SP']:
                bounds = [abs((timestamp(a) - timestamp(b)).total_seconds()) for a in (modis['start_utc'], modis['end_utc'])
                          for b in (viirs['start_utc'], viirs['end_utc'])]
                if max(bounds) <= 90 * 60:
                    gap = abs((timestamp(modis['start_utc']) - timestamp(viirs['start_utc'])).total_seconds())
                    candidates.append((gap, modis['producer_id'], viirs['producer_id'], modis, viirs))
        used = set()
        for gap, mid, vid, modis, viirs in sorted(candidates, key=lambda item: item[:3]):
            if mid in used or vid in used:
                continue
            used.update((mid, vid))
            pairs.append({'grid_x': x, 'grid_y': y, 'modis_granule': mid, 'viirs_granule': vid,
                          'start_time_gap_minutes': round(gap / 60, 2),
                          'modis_state': modis['state'], 'viirs_state': viirs['state'],
                          'date_utc': modis['start_utc'][:10]})
    return pairs


def reconcile(rows, evidence):
    from .validity import _km
    granules = {g['producer_id']: g for g in evidence['inventory'] if g['status'] == 'processed'}
    fire = defaultdict(list)
    for pixel in evidence['pixels']:
        if pixel['mask_class'] >= 7:
            fire[(pixel['grid_x'], pixel['grid_y'])].append(pixel)
    result = []
    platform = {'T': 'Terra', 'TERRA': 'Terra', 'A': 'Aqua', 'AQUA': 'Aqua',
                'N': 'S-NPP', 'SNPP': 'S-NPP', 'S-NPP': 'S-NPP', 'SUOMI NPP': 'S-NPP'}
    for row in rows:
        time = timestamp(row['acquisition_utc'])
        candidates = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for pixel in fire[(row['grid_x'] + dx, row['grid_y'] + dy)]:
                    granule = granules[pixel['producer_id']]
                    if granule['source_id'] != row['source_id'] or granule['platform'] != platform.get(row['platform'].upper()):
                        continue
                    if not timestamp(granule['start_utc']) - timedelta(seconds=60) <= time <= timestamp(granule['end_utc']) + timedelta(seconds=60):
                        continue
                    distance = _km(row['lat'], row['lon'], pixel['lat'], pixel['lon']) * 1000
                    if distance <= 100:
                        candidates.append((distance, pixel['producer_id'], pixel['line'], pixel['sample'], pixel))
        nearest = min(candidates, key=lambda item: item[:4]) if candidates else None
        outcome = {'detection_id': row['detection_id'], 'source_id': row['source_id'],
                   'acquisition_utc': row['acquisition_utc'], 'status': 'matched' if nearest else 'unreconciled'}
        if nearest:
            distance, identifier, line, sample, pixel = nearest
            confidence = str(row['confidence_raw']).strip().lower()
            expected = {'l': 7, 'n': 8, 'h': 9}.get(confidence)
            if row['source_id'] == 'MODIS_SP' and confidence.isdigit():
                expected = 7 if int(confidence) < 30 else 8 if int(confidence) < 80 else 9
            outcome.update(producer_id=identifier, native_line=line, native_sample=sample,
                           distance_m=round(distance, 3), native_class=pixel['mask_class'],
                           confidence_agrees=expected == pixel['mask_class'])
        result.append(outcome)
    return result


def summarize(case_id, rows, evidence, inventory, selected_date):
    expected = expected_pairs(inventory, case_id)
    expected_ids = {p['granule']['producer_id'] for p in expected}
    records = {g['producer_id']: g for g in evidence['inventory']}
    if evidence.get('case_id') != case_id or evidence.get('schema') != SCHEMA or evidence.get('method') != METHOD:
        raise ValueError('Native mask evidence identity or processing method mismatch')
    complete = {}
    ledger = []
    for pair in expected:
        native = records.get(pair['granule']['producer_id'])
        ledger.append({'product': pair['product'], 'producer_id': pair['granule']['producer_id'],
                       'geo_producer_id': pair['geo']['producer_id'] if pair['geo'] else None,
                       'status': native['status'] if native else 'missing',
                       'file_sha256': native.get('file_sha256') if native else None,
                       'error': native.get('error') if native else 'Native file not processed'})
    for source in ('MODIS_SP', 'VIIRS_SNPP_SP'):
        required = [p for p in expected if p['source_id'] == source]
        complete[source] = bool(required) and all(records.get(p['granule']['producer_id'], {}).get('status') == 'processed' for p in required)
    if set(records) - expected_ids:
        raise ValueError('Native ledger contains a granule outside the frozen inventory')
    for pair in expected:
        record = records.get(pair['granule']['producer_id'])
        if record and record['status'] == 'processed':
            for key, value in {'product': pair['product'], 'source_id': pair['source_id'], 'platform': pair['platform'],
                               'start_utc': pair['granule']['start_utc'], 'end_utc': pair['granule']['end_utc'],
                               'geo_producer_id': pair['geo']['producer_id'] if pair['geo'] else None}.items():
                if record[key] != value:
                    raise ValueError('Native granule metadata does not match frozen CMR inventory')
            if not all(re.fullmatch('[0-9a-f]{64}', record.get(key, '')) for key in ('file_sha256', 'geo_sha256')):
                raise ValueError('Missing source or geolocation checksum')
    passes = passes_from_pixels(evidence)
    daily = defaultdict(list)
    for item in passes:
        daily[(item['start_utc'][:10], item['source_id'], item['grid_x'], item['grid_y'])].append(item)
    cells = []
    counts = defaultdict(Counter)
    for (day, source, x, y), observations in sorted(daily.items()):
        states = {p['state'] for p in observations}
        state = 'detected' if 'detected' in states else next(iter(states)) if complete[source] and len(states) == 1 else 'unknown'
        counts[day][state] += 1
        if day == selected_date:
            lon, lat = FROM_GRID.transform((x + .5) * GRID_METERS, (y + .5) * GRID_METERS)
            cells.append({'source_id': source, 'grid_x': x, 'grid_y': y, 'lon': lon, 'lat': lat,
                          'state': state, 'granules': [p['producer_id'] for p in observations],
                          'class_counts': {str(code): count for code, count in sum((Counter(p['class_counts']) for p in observations), Counter()).items()}})
    matches = reconcile(rows, evidence)
    paired = paired_observations(passes)
    processed = sum(g['status'] == 'processed' for g in records.values())
    matched = sum(m['status'] == 'matched' for m in matches)
    # Samples are a deterministic review queue, never an automatic human sign-off.
    strata = defaultdict(list)
    for pixel in evidence['pixels']:
        source = records[pixel['producer_id']]['source_id']
        strata[(source, pixel['mask_class'])].append(pixel)
    samples = []
    for bucket in strata.values():
        bucket.sort(key=lambda p: hashlib.sha256(f"{p['producer_id']}:{p['line']}:{p['sample']}".encode()).hexdigest())
    while len(samples) < 30 and any(strata.values()):
        for key in sorted(strata):
            if strata[key] and len(samples) < 30:
                samples.append(strata[key].pop())
    return {
        'status': 'not-loaded' if not processed else 'processed-unreviewed',
        'spatial_validation': 'centroid-sampling-only; footprint coverage not established',
        'method': METHOD, 'expected_fire_granules': len(expected), 'processed_fire_granules': processed,
        'inventory_complete': all(complete.values()), 'complete_sources': complete,
        'ledger': ledger, 'clipped_native_pixels': len(evidence['pixels']),
        'selected_day_cells': cells, 'daily_sampled_state_counts': {day: dict(c) for day, c in counts.items()},
        'reconciliation': {'total_firms_pixels': len(rows), 'matched': matched,
                           'fraction': matched / len(rows) if rows else None,
                           'target_fraction': .98, 'passes_target': bool(rows) and matched / len(rows) >= .98,
                           'confidence_disagreements': sum(m.get('confidence_agrees') is False for m in matches),
                           'results': matches},
        'paired_observations': {'sample_size': len(paired), 'pairs': paired,
                                'agreement': sum(p['modis_state'] == p['viirs_state'] for p in paired),
                                'interpretation': 'descriptive usable centroid-sampled pairs; no sensitivity calibration or full-cell exposure'},
        'raw_mask_review': {'required_samples': 30, 'reviewed_samples': 0, 'status': 'pending-independent-human-review', 'samples': samples},
        'no_pass_status': 'not-derived-without-verified-footprints',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path('NASA_data/fire_masks'))
    parser.add_argument('--case', choices=('park-2024', 'grove-2025'), required=True)
    parser.add_argument('--store', type=Path, default=STORE)
    args = parser.parse_args()
    print(json.dumps(process(args.input, args.case, args.store), indent=2))


if __name__ == '__main__':
    main()
