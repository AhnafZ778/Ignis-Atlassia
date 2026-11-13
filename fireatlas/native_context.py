"""Aligned native solar/view angles and geolocation-flag sensitivity.

This sidecar preserves the original mask processor. Angles describe sampled
centres, not pixel boundaries or validated observation opportunity. Day/night
is an explicit common solar-angle diagnostic, not a copied product flag.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import math
from pathlib import Path
import re
import sqlite3

from .core import GRID_METERS, GRID_VERSION, TO_GRID
from .masks import PRODUCTS, STORE, checksum, native_layer, pass_state, timestamp
from .opportunity import confusion, group_uncertainty, rematch
from .qualification import digest
from .validity import CASES

SCHEMA = 'fireatlas-native-context-input-v1'
RESULT_SCHEMA = 'fireatlas-native-context-result-v1'
FIELDS = ['line', 'sample', 'lat', 'lon', 'mask_class', 'grid_x', 'grid_y',
          'solar_zenith_raw', 'sensor_zenith_raw', 'geolocation_flags_raw']
MAX_PIXELS = 2_000_000
MAX_GRANULES = 200
SUBSETS = {
    'all': 'All sampled centres',
    'day': 'Day · solar zenith below 85°',
    'night': 'Night · solar zenith above 85°',
    'illumination-unknown': 'Solar angle unknown or at boundary',
    'flags-zero': 'Raw geolocation flag equals zero',
    'flags-nonzero': 'Raw geolocation flag is nonzero (excluding fill)',
    'view-under-40': 'Sensor zenith below 40°',
    'view-40-plus': 'Sensor zenith at least 40°',
}
METHOD = {
    'grid': GRID_VERSION,
    'sampling': 'Exact original native line/sample alignment; no resampling; centroid support only.',
    'illumination': 'Common diagnostic: solar zenith <85 degrees day, >85 night; within half an encoded quantum of 85 degrees remains unknown. Not a native product day/night flag.',
    'angle_quality': 'Fill/out-of-range values remain unknown. VIIRS invalid-input or solar-angle-bad bits invalidate the solar diagnostic; unknown flag bits invalidate angle diagnostics. MODIS nonzero flags conservatively leave angles unknown because bit meanings are not inferred.',
    'flags': 'Zero/nonzero are raw flag subsets, not scientifically validated geolocation quality. VIIRS bit names are interpreted only when native attributes match masks 1/2/4/8 and their published meanings.',
    'matching': 'Reaggregate each pixel subset independently to sampled cell/acquisition states, then rerun deterministic one-to-one matching separately at 30/60/90 minutes.',
    'uncertainty': 'Connected shared-acquisition groups; same descriptive seeded bootstrap as native rematching. No guaranteed coverage or independent cell interpretation.',
    'scope': 'Fixed native pilot windows only; no full-cell coverage, no-pass, daily reconstruction or causal attribution.',
    'sources': [
        'https://modis.gsfc.nasa.gov/data/dataprod/mod03.php',
        'https://ladsweb.modaps.eosdis.nasa.gov/filespec/VIIRS/1/VNP03IMG',
    ],
}


def method_identity():
    root = Path(__file__).parent
    return {name: checksum(root / name) for name in
            ('native_context.py', 'masks.py', 'opportunity.py', 'core.py', 'validity.py')}


def _numbers(value):
    return [float(n) for n in re.findall(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?', value)]


def layer_metadata(layer, kind):
    """Read only relevant SDS attributes, never native paths/global metadata."""
    band = layer.GetRasterBand(1)
    attrs = {**layer.GetMetadata(), **band.GetMetadata()}
    nodata = band.GetNoDataValue()
    if nodata is None and '_FillValue' in attrs:
        nodata = float(attrs['_FillValue'])
    if kind == 'flags':
        return {'fill': nodata, 'flag_masks': attrs.get('flag_masks'),
                'flag_meanings': attrs.get('flag_meanings')}
    scale = band.GetScale()
    if scale is None:
        scale = float(attrs['scale_factor']) if 'scale_factor' in attrs else None
    offset = band.GetOffset()
    offset = float(attrs.get('add_offset', 0)) if offset is None else offset
    bounds = _numbers(attrs.get('valid_range', ''))
    if len(bounds) != 2 and 'valid_min' in attrs and 'valid_max' in attrs:
        bounds = [float(attrs['valid_min']), float(attrs['valid_max'])]
    result = {'scale': scale, 'offset': offset, 'fill': nodata,
              'valid_range': bounds, 'units': attrs.get('units')}
    _validate_angle_metadata(result)
    return result


def _validate_angle_metadata(meta):
    if (not isinstance(meta, dict) or meta.get('units') != 'degrees'
            or not isinstance(meta.get('scale'), (int, float))
            or not math.isfinite(meta['scale']) or not 0 < meta['scale'] <= 1
            or meta.get('offset') != 0 or len(meta.get('valid_range', [])) != 2
            or meta['valid_range'][0] != 0
            or not 179.99 <= meta['valid_range'][1] * meta['scale'] <= 180.01
            or meta.get('fill') is None or not math.isfinite(meta['fill'])
            or meta['valid_range'][0] <= meta['fill'] <= meta['valid_range'][1]):
        raise ValueError('Missing or unsupported native angle scaling/range/fill metadata.')


def angle(raw, meta):
    if raw == meta['fill'] or not meta['valid_range'][0] <= raw <= meta['valid_range'][1]:
        return None
    return raw * meta['scale']


def classify(row, granule):
    solar, sensor, flags = row[7:]
    meta = granule['layers']
    quality = 'unknown' if flags == meta['flags']['fill'] else ('zero' if flags == 0 else 'nonzero')
    solar_value, sensor_value = angle(solar, meta['solar']), angle(sensor, meta['sensor'])
    conditions = []
    if granule['product'] == 'VNP14IMG':
        known = _numbers(meta['flags'].get('flag_masks') or '') == [1, 2, 4, 8]
        known = known and (meta['flags'].get('flag_meanings') or '').split() == ['Input_invalid', 'Pointing_bad', 'Terrain_bad', 'SolarAngle_bad']
        if not known or quality == 'unknown' or flags & ~15:
            solar_value = sensor_value = None
        else:
            conditions = [name for bit, name in zip((1, 2, 4, 8), ('input-invalid', 'pointing-bad', 'terrain-bad', 'solar-angle-bad')) if flags & bit]
            if flags & 9:
                solar_value = None
            if flags & 3:
                sensor_value = None
    elif quality != 'zero':
        solar_value = sensor_value = None
    boundary = max(1e-6, meta['solar']['scale'] / 2)
    light = ('unknown' if solar_value is None or abs(solar_value - 85) <= boundary
             else 'day' if solar_value < 85 else 'night')
    view = ('unknown' if sensor_value is None else
            'under-40' if sensor_value < 40 - meta['sensor']['scale'] / 2 else '40-plus')
    return light, quality, view, conditions, solar_value, sensor_value


def _base_rows(rows):
    return [row[:7] for row in rows]


def capture(case_id, directory, store=STORE):
    """Freeze exact aligned samples, rechecking original mask and geo bytes."""
    if case_id not in CASES:
        raise ValueError('Unsupported fixed native pilot.')
    files = defaultdict(list)
    for path in Path(directory).rglob('*'):
        if path.is_file() and path.suffix.lower() in {'.hdf', '.nc', '.h5'}:
            files[path.name].append(path)
    with sqlite3.connect(Path(store).resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        inventory = [dict(r) for r in db.execute('SELECT * FROM granules WHERE case_id=? ORDER BY producer_id', (case_id,))]
        count = db.execute('SELECT COUNT(*) FROM pixels WHERE case_id=?', (case_id,)).fetchone()[0]
        if count > MAX_PIXELS or len(inventory) > MAX_GRANULES:
            raise ValueError('Native context pilot exceeds bounded pixel/granule limits.')
        records = {g['producer_id']: [list(r) for r in db.execute(
            'SELECT line,sample,lat,lon,mask_class,grid_x,grid_y FROM pixels WHERE case_id=? AND producer_id=? ORDER BY line,sample',
            (case_id, g['producer_id']))] for g in inventory}
    output = []
    for g in inventory:
        record = {k: g[k] for k in ('producer_id', 'geo_producer_id', 'product', 'source_id', 'platform', 'start_utc', 'end_utc', 'file_sha256', 'geo_sha256', 'width', 'height')}
        rows = records[g['producer_id']]
        record.update(native_sample_count=len(rows), native_samples_sha256=digest(rows), status='unavailable', unavailable_reason=None, samples=[])
        if g['status'] != 'processed':
            record['unavailable_reason'] = 'Original native mask is not processed.'
            output.append(record)
            continue
        mask_paths = files.get(g['producer_id'], []) or files.get(g['producer_id'] + '.hdf', []) or files.get(g['producer_id'] + '.nc', [])
        geo_paths = files.get(g['geo_producer_id'], [])
        if len(mask_paths) != 1 or len(geo_paths) != 1:
            record['unavailable_reason'] = 'Missing or ambiguous original mask/geolocation file.'
            output.append(record)
            continue
        if checksum(mask_paths[0]) != g['file_sha256'] or checksum(geo_paths[0]) != g['geo_sha256']:
            raise ValueError('Original native/geolocation file checksum differs; extraction stopped.')
        layers = {
            'solar': native_layer(geo_paths[0], ('SolarZenith', 'solar_zenith'))[1],
            'sensor': native_layer(geo_paths[0], ('SensorZenith', 'sensor_zenith'))[1],
            'flags': native_layer(geo_paths[0], ('gflags', 'quality_flag'))[1],
            'lat': native_layer(geo_paths[0], ('Latitude', 'latitude'))[1],
            'lon': native_layer(geo_paths[0], ('Longitude', 'longitude'))[1],
            'mask': native_layer(mask_paths[0], ('FireMask', 'fire_mask', 'fire mask'))[1],
        }
        if any((d.RasterXSize, d.RasterYSize) != (g['width'], g['height']) for d in layers.values()):
            raise ValueError('Native context shape mismatch; no inferred alignment is allowed.')
        record['layers'] = {key: layer_metadata(layers[key], 'flags' if key == 'flags' else 'angle') for key in ('solar', 'sensor', 'flags')}
        selected = defaultdict(list)
        for row in rows:
            selected[row[0] // 32 * 32].append(row)
        for first, group in sorted(selected.items()):
            height = min(32, g['height'] - first)
            arrays = {key: d.ReadAsArray(0, first, g['width'], height) for key, d in layers.items()}
            for row in group:
                line, sample = row[:2]
                r = line - first
                if (float(arrays['lat'][r, sample]), float(arrays['lon'][r, sample]), int(arrays['mask'][r, sample])) != tuple(row[2:5]):
                    raise ValueError('Original native sample coordinates/class do not reproduce.')
                record['samples'].append(row + [int(arrays[key][r, sample]) for key in ('solar', 'sensor', 'flags')])
        record['status'] = 'extracted'
        output.append(record)
    value = {'schema': SCHEMA, 'case_id': case_id, 'synthetic': False,
             'method': METHOD, 'method_sources': method_identity(), 'sample_fields': FIELDS,
             'granules': output, 'native_pixel_count': count}
    value['input_sha256'] = digest(value)
    validate(value)
    return value


def validate(inputs):
    if (inputs.get('schema') != SCHEMA or inputs.get('case_id') not in CASES
            or type(inputs.get('synthetic')) is not bool or inputs.get('method') != METHOD
            or inputs.get('method_sources') != method_identity() or inputs.get('sample_fields') != FIELDS):
        raise ValueError('Native context identity/method mismatch.')
    material = dict(inputs)
    expected = material.pop('input_sha256', None)
    if digest(material) != expected:
        raise ValueError('Native context input checksum differs.')
    granules = inputs.get('granules')
    if not isinstance(granules, list) or not granules or len(granules) > MAX_GRANULES:
        raise ValueError('Native context requires a bounded nonempty inventory.')
    total = 0
    ids = set()
    west, south, east, north = CASES[inputs['case_id']]['bbox']
    for g in granules:
        if g['producer_id'] in ids or g['product'] not in PRODUCTS:
            raise ValueError('Duplicate or unsupported native product.')
        ids.add(g['producer_id'])
        _, source, platform = PRODUCTS[g['product']]
        first, last = timestamp(g['start_utc']), timestamp(g['end_utc'])
        if ((g['source_id'], g['platform']) != (source, platform)
                or first.tzinfo is None or last.tzinfo is None
                or first.utcoffset().total_seconds() != 0 or last.utcoffset().total_seconds() != 0 or first > last):
            raise ValueError('Native source/platform/time identity differs.')
        if g['start_utc'][:10] < CASES[inputs['case_id']]['start'] or g['start_utc'][:10] > CASES[inputs['case_id']]['end']:
            raise ValueError('Native acquisition is outside the fixed case.')
        if g['status'] not in ('extracted', 'unavailable') or not isinstance(g['samples'], list):
            raise ValueError('Invalid native extraction state.')
        count = g['native_sample_count']
        if type(count) is not int or count < 0 or count > MAX_PIXELS:
            raise ValueError('Invalid native sample support.')
        total += count
        if total > MAX_PIXELS:
            raise ValueError('Native pixel limit exceeded.')
        if g['status'] == 'unavailable':
            if g['samples'] or not g['unavailable_reason']:
                raise ValueError('Unavailable native context must retain a reason and no substituted samples.')
            continue
        if any(type(g[key]) is not int or not 0 < g[key] <= 10000 for key in ('width', 'height')):
            raise ValueError('Native raster dimensions are invalid or exceed the pilot bound.')
        for key in ('file_sha256', 'geo_sha256', 'native_samples_sha256'):
            if not re.fullmatch('[a-f0-9]{64}', g.get(key) or ''):
                raise ValueError('Missing original native identity.')
        for key in ('solar', 'sensor'):
            _validate_angle_metadata(g['layers'][key])
        if (not isinstance(g['layers'].get('flags'), dict)
                or set(g['layers']['flags']) != {'fill', 'flag_masks', 'flag_meanings'}):
            raise ValueError('Missing native quality metadata.')
        fill = g['layers']['flags']['fill']
        if fill is not None and (type(fill) not in (int, float) or not math.isfinite(fill) or fill != int(fill) or not 0 <= fill <= 255):
            raise ValueError('Invalid native flag fill value.')
        if count != len(g['samples']) or digest(_base_rows(g['samples'])) != g['native_samples_sha256']:
            raise ValueError('Native sample count or original identity differs.')
        last = (-1, -1)
        for row in g['samples']:
            if not isinstance(row, list) or len(row) != len(FIELDS):
                raise ValueError('Invalid native sample fields.')
            line, sample, lat, lon, code, x, y, solar, sensor, flags = row
            if (any(type(row[i]) is not int for i in (0, 1, 4, 5, 6, 7, 8, 9))
                    or not 0 <= line < g['height'] or not 0 <= sample < g['width']
                    or (line, sample) <= last or not 0 <= code <= 9
                    or not -32768 <= solar <= 32767 or not -32768 <= sensor <= 32767
                    or not 0 <= flags <= 255 or not south <= lat <= north or not west <= lon <= east):
                raise ValueError('Invalid, duplicate or outside-case native sample.')
            px, py = TO_GRID.transform(lon, lat)
            if (math.floor(px / GRID_METERS), math.floor(py / GRID_METERS)) != (x, y):
                raise ValueError('Native centroid grid does not reproduce.')
            last = (line, sample)
    if total != inputs.get('native_pixel_count'):
        raise ValueError('Native total support differs.')


def bind_original_store(inputs, store=STORE):
    """Publication also binds captured masks to the actual original read-only store."""
    with sqlite3.connect(Path(store).resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        originals = {g['producer_id']: dict(g) for g in db.execute('SELECT * FROM granules WHERE case_id=?', (inputs['case_id'],))}
        if set(originals) != {g['producer_id'] for g in inputs['granules']}:
            raise ValueError('Original native inventory differs.')
        for g in inputs['granules']:
            if any(originals[g['producer_id']][key] != g[key] for key in ('file_sha256', 'geo_sha256', 'product', 'source_id', 'platform', 'start_utc', 'end_utc', 'width', 'height', 'geo_producer_id')):
                raise ValueError('Original native granule identity differs.')
            rows = [list(r) for r in db.execute('SELECT line,sample,lat,lon,mask_class,grid_x,grid_y FROM pixels WHERE case_id=? AND producer_id=? ORDER BY line,sample', (inputs['case_id'], g['producer_id']))]
            if len(rows) != g['native_sample_count'] or digest(rows) != g['native_samples_sha256']:
                raise ValueError('Original native sample identity differs.')


def analyze(inputs):
    validate(inputs)
    grouped = {key: defaultdict(Counter) for key in SUBSETS}
    inventory = {g['producer_id']: g for g in inputs['granules']}
    lights, flags, views, conditions = Counter(), Counter(), Counter(), Counter()
    by_acquisition = []
    for g in inputs['granules']:
        local_lights, local_flags, local_views = Counter(), Counter(), Counter()
        angles = {'solar': [], 'sensor': []}
        for row in g['samples']:
            light, quality, view, names, solar, sensor = classify(row, g)
            lights[light] += 1; flags[quality] += 1; views[view] += 1
            local_lights[light] += 1; local_flags[quality] += 1; local_views[view] += 1
            conditions.update(names)
            if solar is not None: angles['solar'].append(solar)
            if sensor is not None: angles['sensor'].append(sensor)
            subsets = ['all', light if light != 'unknown' else 'illumination-unknown']
            if quality != 'unknown': subsets.append('flags-' + quality)
            if view != 'unknown': subsets.append('view-' + view)
            key = (g['producer_id'], row[5], row[6])
            for subset in subsets:
                grouped[subset][key][row[4]] += 1
        by_acquisition.append({'producer_id': g['producer_id'], 'source_id': g['source_id'], 'platform': g['platform'], 'status': g['status'],
                               'native_samples': g['native_sample_count'], 'extracted_samples': len(g['samples']),
                               'illumination_samples': dict(local_lights), 'raw_flag_samples': dict(local_flags),
                               'view_samples': dict(local_views), 'angle_ranges_degrees': {key: [min(v), max(v)] if v else None for key, v in angles.items()},
                               'file_sha256': g['file_sha256'], 'geo_sha256': g['geo_sha256'], 'unavailable_reason': g['unavailable_reason']})
    experiments = {}
    for subset, counts in grouped.items():
        passes = []
        for (identifier, x, y), classes in sorted(counts.items()):
            g = inventory[identifier]
            passes.append({'producer_id': identifier, 'source_id': g['source_id'], 'platform': g['platform'],
                           'start_utc': g['start_utc'], 'end_utc': g['end_utc'], 'grid_x': x, 'grid_y': y,
                           'file_sha256': g['file_sha256'], 'geo_sha256': g['geo_sha256'],
                           'state': pass_state(classes), 'class_counts': dict(classes)})
        thresholds = {}
        for tolerance in (30, 60, 90):
            pairs = rematch(passes, tolerance)
            thresholds[str(tolerance)] = {'metrics': confusion(pairs), 'group_uncertainty': group_uncertainty(pairs),
                                          'platforms': {platform: confusion([p for p in pairs if p['modis_platform'] == platform]) for platform in sorted({p['modis_platform'] for p in pairs})}}
        experiments[subset] = {'label': SUBSETS[subset], 'sampled_cell_acquisitions': len(passes),
                               'pixel_samples': sum(sum(c.values()) for c in counts.values()),
                               'sampled_states': dict(Counter(p['state'] for p in passes)), 'thresholds': thresholds}
        counts.clear()
    result = {'schema': RESULT_SCHEMA, 'case_id': inputs['case_id'], 'synthetic': inputs['synthetic'],
              'input_sha256': inputs['input_sha256'], 'method': METHOD, 'method_sources': inputs['method_sources'],
              'native_pixel_count': inputs['native_pixel_count'], 'extracted_pixel_count': sum(lights.values()),
              'illumination_samples': dict(lights), 'raw_flag_samples': dict(flags), 'view_samples': dict(views),
              'documented_viirs_flag_samples': dict(conditions), 'acquisitions': by_acquisition, 'subsets': experiments,
              'admitted': False, 'independent_processing_review': 'pending', 'validated_observation_opportunity': False,
              'physical_causes': 'unresolved', 'no_pass_enabled': False}
    result['result_sha256'] = digest(result)
    return result


def bind_original_files(inputs, directory, store=STORE):
    """Prove raw angles/flags and metadata against original geolocation bytes.

    An original-file SHA declared inside a resealed input is insufficient. This
    performs the actual native extraction again; offline arithmetic verification
    is deliberately a different, weaker scope.
    """
    if inputs.get('synthetic') is not False:
        raise ValueError('Synthetic native context cannot bind to authentic files.')
    actual = capture(inputs['case_id'], directory, store)
    if actual['input_sha256'] != inputs['input_sha256']:
        raise ValueError('Native angle/flag samples or metadata differ from original file extraction.')


def verify(bundle, *, store=None, directory=None):
    if set(bundle) != {'inputs', 'result'}:
        raise ValueError('Native context bundle must contain exact inputs and result.')
    if store is not None:
        if bundle['inputs']['synthetic'] is not False:
            raise ValueError('Synthetic native context cannot bind to authentic observations.')
        bind_original_store(bundle['inputs'], store)
    if directory is not None:
        bind_original_files(bundle['inputs'], directory, store or STORE)
    actual = analyze(bundle['inputs'])
    if digest(actual) != digest(bundle['result']):
        raise ValueError('Native context statistics do not reproduce from raw samples.')
    return {'verified': True, 'case_id': actual['case_id'], 'result_sha256': actual['result_sha256'],
            'native_pixel_count': actual['native_pixel_count'], 'extracted_pixel_count': actual['extracted_pixel_count'],
            'verification_scope': 'original-native-files-and-recount' if directory is not None else 'original-mask-store-and-recount' if store is not None else 'self-contained-statistical-recount',
            'scientifically_admitted': False}
