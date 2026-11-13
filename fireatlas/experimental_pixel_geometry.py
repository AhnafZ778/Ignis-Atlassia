"""Research-only midpoint polygons from native geolocation centers.

These are *modeled shapes*, never provider footprints or observation coverage.
Original-byte verification and scientific reference validation are separate.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re

from pyproj import Transformer
from shapely.geometry import Point, Polygon

SCHEMA = 'fireatlas-experimental-midpoint-input-v1'
RESULT_SCHEMA = 'fireatlas-experimental-midpoint-result-v1'
METHOD = 'center-stencil-midpoints-v1.0.0'
MAX_STENCILS = 10_000
HASH = re.compile(r'[0-9a-f]{64}\Z')
# Product-supported ordering must also be declared and checked against original metadata.
PRODUCTS = {'MOD14': ('MOD03', 10), 'MYD14': ('MYD03', 10),
            'VNP14IMG': ('VNP03IMG', 32)}
VALID_MASKS = frozenset((3, 4, 5, 7, 8, 9))
TRANSFORM = Transformer.from_crs('EPSG:4326', 'EPSG:6933', always_xy=True)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _utc(value):
    if not isinstance(value, str):
        raise ValueError('UTC times must be explicit strings.')
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('Invalid UTC time.') from exc
    if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
        raise ValueError('Explicit UTC time required.')
    return stamp


def _name(value):
    return (isinstance(value, str) and bool(value) and len(value) <= 255
            and bool(re.fullmatch(r'[A-Za-z0-9._-]+', value)) and Path(value).name == value)


def _source(src):
    if not isinstance(src, dict) or src.get('mask_product') not in PRODUCTS:
        raise ValueError('A supported native standard product is required.')
    geo, scan_lines = PRODUCTS[src['mask_product']]
    if src.get('geo_product') != geo:
        raise ValueError('Native mask/geolocation product pairing differs.')
    for key in ('mask_id', 'geo_id'):
        if not _name(src.get(key)) or not src[key].startswith(src['mask_product' if key == 'mask_id' else 'geo_product'] + '.'):
            raise ValueError('Explicit original producer basenames are required.')
    parsed = []
    for key in ('mask_id', 'geo_id'):
        parts = src[key].split('.')
        if len(parts) < 5 or not re.fullmatch(r'A[0-9]{7}', parts[1]) or not re.fullmatch(r'[0-9]{4}', parts[2]):
            raise ValueError('Standard acquisition date and time must be present in producer names.')
        try:
            stamp = datetime.strptime(parts[1] + parts[2], 'A%Y%j%H%M')
        except ValueError as exc:
            raise ValueError('Producer acquisition date or time is invalid.') from exc
        if stamp.strftime('A%Y%j%H%M') != parts[1] + parts[2]:
            raise ValueError('Producer acquisition date or time is invalid.')
        parsed.append((stamp, parts[3]))
    if parsed[0][0] != parsed[1][0]:
        raise ValueError('Mask and geolocation producer acquisition times differ.')
    for key in ('mask_sha256', 'geo_sha256'):
        if not isinstance(src.get(key), str) or not HASH.fullmatch(src[key]):
            raise ValueError('Original SHA-256 identities are required.')
    for key in ('mask_version', 'geo_version'):
        if not isinstance(src.get(key), str) or not src[key].strip() or len(src[key]) > 40:
            raise ValueError('Exact native product versions are required.')
    def same_version(a, b):
        return int(a) == int(b) if a.isdigit() and b.isdigit() else a == b
    if not all(same_version(src[key], parsed[i][1]) for i, key in enumerate(('mask_version', 'geo_version'))):
        raise ValueError('Producer filename and declared native version differ.')
    for key in ('width', 'height'):
        if type(src.get(key)) is not int or not 3 <= src[key] <= 100_000:
            raise ValueError('Bounded aligned native array dimensions are required.')
    if (src.get('scan_layout') != 'product-scan-row-major' or src.get('lines_per_scan') != scan_lines
            or src['height'] % scan_lines):
        raise ValueError('Declared product scan layout and complete scan dimensions required.')
    fill = src.get('quality_flag_fill')
    if fill is not None and (type(fill) is not int or not 0 <= fill <= 255):
        raise ValueError('Invalid raw quality-flag fill value.')
    start, end = _utc(src.get('start_utc')), _utc(src.get('end_utc'))
    if start > end or start.replace(tzinfo=None, second=0, microsecond=0) != parsed[0][0]:
        raise ValueError('Acquisition interval is reversed or does not match producer time.')


def _unresolved(line, sample, reason):
    return {'line': line, 'sample': sample, 'status': 'unresolved', 'reason': reason,
            'modeled_polygon_epsg6933': None, 'modeled_area_m2': None}


def _calculate(src, stencil):
    if not isinstance(stencil, dict) or type(stencil.get('line')) is not int or type(stencil.get('sample')) is not int:
        raise ValueError('Each stencil needs integer target indices.')
    line, sample = stencil['line'], stencil['sample']
    if not 0 <= line < src['height'] or not 0 <= sample < src['width']:
        raise ValueError('Target index is outside its source arrays.')
    entries = stencil.get('centers')
    if not isinstance(entries, list) or len(entries) != 9:
        return _unresolved(line, sample, 'missing-neighbor-stencil')
    if line == 0 or line + 1 >= src['height'] or sample == 0 or sample + 1 >= src['width']:
        return _unresolved(line, sample, 'array-edge')
    scan = src['lines_per_scan']
    if (line - 1) // scan != (line + 1) // scan:
        return _unresolved(line, sample, 'scan-seam')
    if src.get('quality_flag_fill') is None:
        return _unresolved(line, sample, 'unknown-flag-fill')
    ordered = []
    for index, point in enumerate(entries):
        row, col = divmod(index, 3)
        if (not isinstance(point, dict) or type(point.get('line')) is not int or type(point.get('sample')) is not int
                or point['line'] != line + row - 1 or point['sample'] != sample + col - 1):
            return _unresolved(line, sample, 'neighbor-index-mismatch')
        lat, lon, flags, mask = (point.get(k) for k in ('lat', 'lon', 'quality_flag', 'mask_class'))
        if (type(lat) not in (int, float) or type(lon) not in (int, float)
                or not math.isfinite(lat) or not math.isfinite(lon) or not -86 <= lat <= 86 or not -180 <= lon <= 180):
            return _unresolved(line, sample, 'missing-or-invalid-geolocation')
        if type(flags) is not int or flags == src['quality_flag_fill'] or flags != 0:
            return _unresolved(line, sample, 'unsupported-geolocation-quality')
        if type(mask) is not int or mask not in VALID_MASKS:
            return _unresolved(line, sample, 'missing-or-unusable-neighbor')
        x, y = TRANSFORM.transform(lon, lat)
        if not math.isfinite(x) or not math.isfinite(y):
            return _unresolved(line, sample, 'invalid-projection')
        ordered.append((x, y))
    # Projected midpoint arithmetic is not valid across the longitude seam.
    lons = [point['lon'] for point in entries]
    if any(abs(lons[a] - lons[b]) > 180 for a,b in
           ((0,1),(1,2),(3,4),(4,5),(6,7),(7,8),(0,3),(3,6),(1,4),(4,7),(2,5),(5,8))):
        return _unresolved(line, sample, 'projection-discontinuity')
    if len(set(ordered)) != 9:
        return _unresolved(line, sample, 'duplicate-centers')
    # Mean of the four adjacent centers, once per target corner.
    corners = []
    for indices in ((0, 1, 3, 4), (1, 2, 4, 5), (4, 5, 7, 8), (3, 4, 6, 7)):
        corners.append([sum(ordered[i][0] for i in indices) / 4,
                        sum(ordered[i][1] for i in indices) / 4])
    shape = Polygon(corners)
    if (not shape.is_valid or not math.isfinite(shape.area) or shape.area <= 0
            or not shape.covers(Point(*ordered[4]))):
        return _unresolved(line, sample, 'degenerate-or-folded-model')
    corners.append(corners[0][:])
    return {'line': line, 'sample': sample, 'status': 'modeled', 'reason': None,
            'modeled_polygon_epsg6933': corners, 'modeled_area_m2': shape.area}


def evaluate(inputs):
    """Recount a bounded, explicitly ordered set of raw center stencils."""
    if not isinstance(inputs, dict) or inputs.get('schema') != SCHEMA or type(inputs.get('synthetic')) is not bool:
        raise ValueError('Experimental input schema and synthetic state required.')
    if inputs.get('crs') != 'EPSG:6933':
        raise ValueError('Only the declared equal-area projection is supported.')
    src = inputs.get('source'); _source(src)
    stencils = inputs.get('stencils')
    if not isinstance(stencils, list) or len(stencils) > MAX_STENCILS:
        raise ValueError('A bounded stencil list is required.')
    if inputs.get('input_sha256') != digest({k: v for k, v in inputs.items() if k != 'input_sha256'}):
        raise ValueError('Input identity differs.')
    rows = []; previous = None
    for stencil in stencils:
        row = _calculate(src, stencil); key = (row['line'], row['sample'])
        if previous is not None and key <= previous:
            raise ValueError('Stencil targets must be strictly ordered and unique.')
        previous = key; rows.append(row)
    result = {'schema': RESULT_SCHEMA, 'method': METHOD, 'geometry_origin': 'experimental-center-interpolation',
              'input': inputs, 'rows': rows, 'status_counts': dict(Counter(r['status'] for r in rows)),
              'validated_opportunity': False, 'no_pass_enabled': False,
              'provider_boundary': False, 'original_files_verified': False,
              'interpretation': 'Modeled local shapes only; no validated footprint, observation opportunity, no-pass or fire absence is established.'}
    result['result_sha256'] = digest(result)
    return result


def verify(result):
    if not isinstance(result, dict) or digest(evaluate(result.get('input'))) != digest(result):
        raise ValueError('Experimental geometry recount differs.')
    return {'verified': True, 'result_sha256': result['result_sha256'],
            'scope': 'self-contained modeled geometry recount; original-file and scientific validation are separate'}


def verify_original_files(result, directory):
    """Re-extract every supplied 3x3 stencil from exact original native files.

    This verifies bytes, aligned dimensions, fill metadata and supplied samples.
    It does not establish physical boundaries, the scan layout, collection
    compatibility, or scientific validity of modeled shapes.
    """
    verify(result)
    inputs = result['input']
    if inputs['synthetic']:
        raise ValueError('Synthetic inputs cannot bind authentic original files.')
    if not inputs['stencils']:
        raise ValueError('At least one complete stencil is required to bind original samples.')
    from .masks import checksum, native_layer
    from .native_context import layer_metadata
    root = Path(directory).resolve()
    if not root.is_dir():
        raise ValueError('Original native directory unavailable.')
    src = inputs['source']
    originals = {}
    for key in ('mask', 'geo'):
        matches = [p for p in root.rglob(src[key + '_id']) if p.is_file()]
        if (len(matches) != 1 or not matches[0].resolve().is_relative_to(root)
                or checksum(matches[0]) != src[key + '_sha256']):
            raise ValueError('Missing, ambiguous or altered original native file.')
        originals[key] = matches[0]
    layers = {'mask_class': native_layer(originals['mask'], ('FireMask', 'fire_mask', 'fire mask'))[1],
              'lat': native_layer(originals['geo'], ('Latitude', 'latitude'))[1],
              'lon': native_layer(originals['geo'], ('Longitude', 'longitude'))[1],
              'quality_flag': native_layer(originals['geo'], ('gflags', 'quality_flag'))[1]}
    if any((v.RasterXSize, v.RasterYSize) != (src['width'], src['height']) for v in layers.values()):
        raise ValueError('Original native array dimensions differ.')
    if layer_metadata(layers['quality_flag'], 'flags')['fill'] != src['quality_flag_fill']:
        raise ValueError('Original raw quality flag fill metadata differs.')
    checked = 0
    for stencil in inputs['stencils']:
        line, sample = stencil['line'], stencil['sample']
        neighbors = stencil['centers']
        if (len(neighbors) != 9 or line < 1 or line + 1 >= src['height'] or sample < 1 or sample + 1 >= src['width']):
            raise ValueError('Incomplete or out-of-bounds stencil cannot bind originals.')
        arrays = {key: layer.ReadAsArray(sample - 1, line - 1, 3, 3) for key, layer in layers.items()}
        for index, neighbor in enumerate(neighbors):
            row, col = divmod(index, 3)
            if (not isinstance(neighbor, dict) or neighbor.get('line') != line + row - 1
                    or neighbor.get('sample') != sample + col - 1):
                raise ValueError('Original stencil indices differ.')
            for key, array in arrays.items():
                value = neighbor.get(key)
                raw = float(array[row, col])
                if type(value) not in (int, float) or not math.isfinite(raw) or raw != value:
                    raise ValueError('Original native stencil value differs.')
            checked += 1
    # Check again after extraction: a file changed during the read cannot
    # inherit the earlier fingerprint in the binding receipt.
    for key,path in originals.items():
        if not path.resolve().is_relative_to(root) or checksum(path) != src[key + '_sha256']:
            raise ValueError('Original native file changed during sample extraction.')
    return {'schema': 'fireatlas-experimental-midpoint-original-binding-v1',
            'result_sha256': result['result_sha256'], 'verified': True,
            'stencils_checked': len(inputs['stencils']), 'centers_checked': checked,
            'scope': 'Original file hashes, array dimensions, quality fill and supplied samples; scan layout, physical boundaries and scientific validity remain unverified.'}
