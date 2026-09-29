"""Independently recount exported evidence without the server or calendar code.

Uses a separate analytical EPSG:6933 transform and stdlib only. This verifies
calculations and frozen-file consistency; it is not independent scientific
review of NASA observations, raw swaths, or incident association.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import zipfile
from collections import Counter, defaultdict


def projected(lon, lat):
    """WGS84 Lambert cylindrical equal area, standard parallel 30 degrees."""
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -86 <= lat <= 86):
        raise ValueError('Coordinates outside pilot projection domain')
    semi_major = 6378137.0
    flattening = 1 / 298.257223563
    eccentricity_sq = flattening * (2 - flattening)
    eccentricity = math.sqrt(eccentricity_sq)
    phi = math.radians(lat)
    standard = math.radians(30)
    k0 = math.cos(standard) / math.sqrt(1 - eccentricity_sq * math.sin(standard) ** 2)
    sine = math.sin(phi)
    q = (1 - eccentricity_sq) * (
        sine / (1 - eccentricity_sq * sine ** 2)
        - math.log((1 - eccentricity * sine) / (1 + eccentricity * sine)) / (2 * eccentricity)
    )
    return semi_major * k0 * math.radians(lon), semi_major * q / (2 * k0)


def grid(lon, lat, metres=1000):
    x, y = projected(lon, lat)
    return math.floor(x / metres), math.floor(y / metres)


def check(path):
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        files = manifest['files']
        if set(archive.namelist()) != set(files) | {'manifest.json'}:
            raise ValueError('Evidence manifest does not enumerate every file')
        for name, digest in files.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError(f'Checksum mismatch: {name}')
        audit = json.loads(archive.read('case.json'))
        rows = json.loads(archive.read('observations.json'))
        native = json.loads(archive.read('native_masks.json')) if 'native_masks.json' in files else None
    marks = defaultdict(set)
    raw = Counter()
    sources = {'MODIS_SP', 'VIIRS_SNPP_SP'}
    for row in rows:
        if row['demo'] or row['source_id'] not in sources or row['processing_level'] != 'SP':
            raise ValueError('Unexpected source or fabricated observation in historical evidence')
        cell = grid(row['lon'], row['lat'])
        if cell != (row['grid_x'], row['grid_y']):
            raise ValueError('Analytical projection disagrees with source grid assignment')
        day, source = row['acquisition_utc'][:10], row['source_id']
        marks[day, source].add(cell)
        raw[day, source] += 1
    for day in audit['days']:
        when = day['date_utc']
        for source in sources:
            if day['raw_pixels'][source] != raw[when, source] or day['detected_cell_days'][source] != len(marks[when, source]):
                raise ValueError('Original pixel or per-source daily total does not reproduce')
        modis, viirs = marks[when, 'MODIS_SP'], marks[when, 'VIIRS_SNPP_SP']
        if day['joint_detected_cell_days'] != len(modis | viirs) or day['co_detected_cell_days'] != len(modis & viirs):
            raise ValueError('Daily union or co-detection total does not reproduce')
    for trial in audit['detection_sensitivity']:
        cells, retained = set(), 0
        for row in rows:
            confidence = str(row['confidence_raw']).strip().lower()
            low = confidence == 'l' or (row['source_id'] == 'MODIS_SP' and confidence.isdigit() and int(confidence) < 30)
            if trial['exclude_low_confidence'] and low:
                continue
            cells.add((row['acquisition_utc'][:10], *grid(row['lon'], row['lat'], trial['grid_metres'])))
            retained += 1
        if len(cells) != trial['joint_detected_cell_days'] or retained != trial['retained_raw_pixels']:
            raise ValueError('Grid/confidence sensitivity total does not reproduce')
    native_count = 0
    if native is not None:
        native_count = len(native['pixels'])
        counts = defaultdict(Counter)
        identifiers = {g['producer_id']: g for g in native['inventory'] if g['status'] == 'processed'}
        for pixel in native['pixels']:
            if grid(pixel['lon'], pixel['lat']) != (pixel['grid_x'], pixel['grid_y']):
                raise ValueError('Analytical projection disagrees with native mask grid')
            if pixel['producer_id'] not in identifiers or pixel['mask_class'] not in range(10):
                raise ValueError('Invalid native sample or granule reference')
            granule = identifiers[pixel['producer_id']]
            if granule['start_utc'][:10] == audit['selected_date_utc']:
                counts[granule['source_id'], pixel['grid_x'], pixel['grid_y']][str(pixel['mask_class'])] += 1
        displayed = audit['native_masks']['selected_day_cells']
        if len(displayed) != len(counts):
            raise ValueError('Native mask map-cell sample size differs')
        for cell in displayed:
            if dict(counts[cell['source_id'], cell['grid_x'], cell['grid_y']]) != cell['class_counts']:
                raise ValueError('Native class histogram does not reproduce')
        if audit['native_masks']['clipped_native_pixels'] != native_count:
            raise ValueError('Native sample count differs from frozen inputs')
    return {'calculations_reproduce': True, 'case_id': audit['case_id'], 'original_pixels': len(rows),
            'joint_cell_days': sum(day['joint_detected_cell_days'] for day in audit['days']),
            'native_samples': native_count, 'transform': 'independent analytical WGS84 EPSG:6933',
            'independent_scientific_review': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle')
    print(json.dumps(check(parser.parse_args().bundle), indent=2))
