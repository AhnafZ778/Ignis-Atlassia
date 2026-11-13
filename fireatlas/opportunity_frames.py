"""Tiled native footprint calculations with self-contained CMR receipts.

Calculated states are experimental until a separately bound human processing /
geometry review is accepted. A provider-envelope or pixel centre is never a
pixel footprint. This successor leaves the frozen pilot algorithms unchanged.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .core import TO_GRID
from .coverage import candidate_geometry, geometry_library, polygon
from .qualification import digest
from .regions import REGIONS
from .validity import CASES

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = {
    'MODIS_SP': {'MOD14': 'MOD03', 'MYD14': 'MYD03'},
    'VIIRS_SNPP_SP': {'VNP14IMG': 'VNP03IMG'},
    'VIIRS_NOAA20_SP': {'VJ114IMG': 'VJ103IMG'},
    'VIIRS_NOAA21_SP': {'VJ214IMG': 'VJ203IMG'},
}
MAX_CELLS = 20_000
MAX_GRANULES = 500
MAX_PIXELS = 200_000
MAX_VERTICES = 1_000_000
MAX_CONTACTS = 2_000_000
MAX_DAILY_ROWS = 200_000
HASH = re.compile(r'[0-9a-f]{64}\Z')
STATES = ('detected', 'observed-without-detection', 'cloud', 'unusable', 'unknown', 'no-candidate')


def protocol():
    value = json.loads((ROOT / 'fireatlas/protocols/native-opportunity-v2.0.1.json').read_text())
    for name, expected in value['source_sha256'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Opportunity method differs from its frozen proposal; create a successor.')
    return {**value, 'protocol_sha256': digest(value)}


def utc(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
        raise ValueError('Explicit UTC acquisition times required.')
    return stamp


def domain(scope_id):
    if scope_id not in REGIONS and scope_id not in CASES:
        raise ValueError('A fixed qualification region or native pilot is required.')
    bbox = list((REGIONS.get(scope_id) or CASES[scope_id])['bbox'])
    x0, y0 = TO_GRID.transform(bbox[0], bbox[1])
    x1, y1 = TO_GRID.transform(bbox[2], bbox[3])
    return {'id': scope_id, 'bbox': bbox, 'projected_bounds': [x0, y0, x1, y1],
            'grid_bounds': [math.floor(x0 / 1000), math.floor(y0 / 1000), math.ceil(x1 / 1000), math.ceil(y1 / 1000)],
            'kind': 'region' if scope_id in REGIONS else 'pilot'}


def dates(first, last):
    start, end = date.fromisoformat(first), date.fromisoformat(last)
    if first != start.isoformat() or last != end.isoformat() or end < start or (end - start).days >= 31:
        raise ValueError('A canonical inclusive interval of 1–31 UTC dates is required.')
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


def tile_cells(scope_id, tile):
    scope = domain(scope_id)
    if not isinstance(tile, list) or len(tile) != 4 or any(type(v) is not int for v in tile):
        raise ValueError('An explicit integer half-open grid tile is required.')
    a, b, c, d = tile
    x0, y0, x1, y1 = scope['grid_bounds']
    if not x0 <= a < c <= x1 or not y0 <= b < d <= y1 or (c - a) * (d - b) > MAX_CELLS:
        raise ValueError('Tile is outside its fixed domain or exceeds the cell bound.')
    _, box, _ = geometry_library()
    boundary = box(*scope['projected_bounds'])
    return [(x, y, box(x * 1000, y * 1000, (x + 1) * 1000, (y + 1) * 1000).intersection(boundary))
            for x in range(a, c) for y in range(b, d)]


def query_url(scope_id, first, last, product, version):
    days = dates(first, last)
    end = (date.fromisoformat(days[-1]) + timedelta(days=1)).isoformat()
    params = {'short_name': product, 'version': version,
              'temporal': days[0] + 'T00:00:00Z,' + end + 'T00:00:00Z',
              'bounding_box': ','.join(map(str, domain(scope_id)['bbox'])),
              'page_size': '2000', 'sort_key[]': ['start_date', 'producer_granule_id']}
    return 'https://cmr.earthdata.nasa.gov/search/granules.json?' + urlencode(params, doseq=True)


def discover(scope_id, first, last, native_versions, *, opener=urlopen, max_pages=100):
    """Preserve original public CMR page bytes and SearchAfter continuity."""
    if (not isinstance(native_versions, dict) or not native_versions
            or len(native_versions) > 4 or type(max_pages) is not int or not 1 <= max_pages <= 100
            or any(k not in {p for pair in PRODUCTS.values() for p in (*pair, *pair.values())}
                   or not isinstance(v, str) or not v.strip() or len(v) > 40 for k,v in native_versions.items())):
        raise ValueError('Bounded explicit standard native products and versions required.')
    products = []; acquired_bytes=0; acquired_hits=0
    for product, version in sorted(native_versions.items()):
        url = query_url(scope_id, first, last, product, version)
        pages = []; token = None; seen = set(); hits = None; count = 0
        for _ in range(max_pages):
            with opener(Request(url, headers={'CMR-Search-After': token} if token else {}), timeout=30) as response:
                body = response.read(16_000_001)
                total = int(response.headers['CMR-Hits'])
                following = response.headers.get('CMR-Search-After')
            if len(body) > 16_000_000:
                raise ValueError('Bounded CMR metadata page exceeded.')
            acquired_bytes+=len(body)
            if hits is None:acquired_hits+=total
            if total>MAX_GRANULES or acquired_hits>MAX_GRANULES*2 or acquired_bytes>64_000_000:
                raise ValueError('CMR metadata exceeds bounded frame granules/bytes; subdivide the requested interval.')
            entries = json.loads(body)['feed']['entry']
            if not isinstance(entries,list) or len(entries)>2000 or total < 0 or count + len(entries) > total:
                raise ValueError('Invalid CMR page/hit count; inventory remains incomplete.')
            if hits is not None and total != hits:
                raise ValueError('CMR inventory changed during pagination; keep acquisition incomplete.')
            hits = total; count += len(entries)
            pages.append({'request_after': token, 'response_after': following, 'hits': total,
                          'source_utf8': body.decode('utf-8'), 'sha256': hashlib.sha256(body).hexdigest()})
            if count == total: break
            if not entries or not following or following in seen:
                raise ValueError('CMR pagination incomplete or repeated; inventory remains unknown.')
            seen.add(following); token = following
        else:
            raise ValueError('CMR pagination exceeds bounded inventory.')
        products.append({'product': product, 'version': version, 'query': url, 'pages': pages})
    return {'schema': 'fireatlas-native-inventory-receipts-v1', 'scope_id': scope_id,
            'start': first, 'end': last, 'retrieved_utc': datetime.now(timezone.utc).isoformat(), 'products': products}


def inventory(inputs):
    """Recount completeness from raw pages; ignore summary passed booleans."""
    cohort = inputs['cohort']
    if (set(cohort) != {'source', 'version'} or cohort['source'] not in PRODUCTS
            or not isinstance(cohort['version'], str) or not cohort['version'].strip() or len(cohort['version']) > 40):
        raise ValueError('An exact standard source/version cohort is required.')
    versions = inputs['native_versions']; pairs = PRODUCTS[cohort['source']]
    if (not isinstance(versions, dict) or set(versions) != set(pairs) | set(pairs.values())
            or any(not isinstance(v, str) or not v.strip() or len(v) > 40 for v in versions.values())):
        raise ValueError('Explicit mask and companion native versions required; no NRT substitution.')
    inv = inputs['inventory']
    if (inv.get('schema') != 'fireatlas-native-inventory-receipts-v1'
            or any(inv.get(k) != inputs[k] for k in ('scope_id', 'start', 'end'))
            or len(inv.get('products', [])) != len(versions)):
        raise ValueError('Inventory scope or expected product count differs.')
    utc(inv['retrieved_utc'])
    all_granules = {}; products_seen = set(); acquired_bytes=0; acquired_hits=0; first = utc(inputs['start'] + 'T00:00:00Z')
    end = utc(inputs['end'] + 'T00:00:00Z') + timedelta(days=1)
    for item in inv['products']:
        product, version = item['product'], item['version']
        if product in products_seen or versions.get(product) != version or item.get('query') != query_url(inputs['scope_id'], inputs['start'], inputs['end'], product, version):
            raise ValueError('Duplicate product or wrong native query scope/version.')
        products_seen.add(product); pages = item.get('pages', [])
        if not pages or len(pages) > 100:
            raise ValueError('Complete bounded original CMR pages required.')
        expected_after = None; tokens = set(); expected_hits = None; ids = set()
        for index, page in enumerate(pages):
            body = page['source_utf8'].encode()
            acquired_bytes+=len(body)
            if acquired_bytes>64_000_000:raise ValueError('Original CMR metadata exceeds bounded total bytes.')
            if len(body) > 16_000_000 or hashlib.sha256(body).hexdigest() != page.get('sha256') or page.get('request_after') != expected_after:
                raise ValueError('CMR page bytes or pagination identity differs.')
            hits = page['hits']
            if type(hits) is not int or not 0<=hits<=MAX_GRANULES or expected_hits not in (None, hits):
                raise ValueError('CMR hit count changed or is invalid.')
            if expected_hits is None:acquired_hits+=hits
            if acquired_hits>MAX_GRANULES*2:raise ValueError('Original CMR inventory exceeds bounded total granules.')
            expected_hits = hits
            entries = json.loads(body)['feed']['entry']
            if not isinstance(entries, list) or len(entries) > 2000:
                raise ValueError('Invalid CMR result page.')
            for entry in entries:
                identifier = entry['id']; producer = entry['producer_granule_id']
                if (not isinstance(identifier,str) or not identifier or len(identifier)>256
                        or not isinstance(producer,str) or len(producer)>256 or identifier in ids
                        or not producer.startswith(product + '.') or producer in all_granules):
                    raise ValueError('Duplicate CMR/native identity or wrong product.')
                ids.add(identifier)
                lo, hi = utc(entry['time_start']), utc(entry['time_end'])
                if hi < lo or hi < first or lo > end:
                    raise ValueError('Native acquisition interval does not match query scope.')
                all_granules[producer] = {'producer_id': producer, 'cmr_id': identifier, 'product': product, 'version': version,
                    'start_utc': entry['time_start'], 'end_utc': entry['time_end'],
                    'candidate_geometry': {k: entry[k] for k in ('polygons', 'boxes', 'points', 'lines') if k in entry},
                    'collection_concept_id': entry.get('collection_concept_id')}
                mask_product=product if product in pairs else next(k for k,v in pairs.items() if v==product)
                all_granules[producer]['acquisition_group_id']=digest([cohort['source'],mask_product,lo.isoformat()])
            expected_after = page.get('response_after')
            if index < len(pages) - 1:
                if not entries or not expected_after or expected_after in tokens or len(ids) >= hits:
                    raise ValueError('CMR pages are truncated, repeated or extend beyond completion.')
                tokens.add(expected_after)
        if len(ids) != expected_hits:
            raise ValueError('Original CMR pages do not contain every expected granule.')
    if products_seen != set(versions) or len(all_granules) > MAX_GRANULES * 2:
        raise ValueError('Native inventory missing products or exceeds bounded granules.')
    return all_granules


def _geometry_records(inputs):
    artifacts = inputs.get('geometry_artifacts')
    if not isinstance(artifacts, list) or len(artifacts) > MAX_GRANULES:
        raise ValueError('Explicit provider-boundary provenance required.')
    result = {}; total = 0; hashes = set()
    for artifact in artifacts:
        source = urlsplit(artifact['source_reference'])
        if (source.scheme != 'https' or not source.hostname or not source.hostname.endswith(('.nasa.gov', '.noaa.gov'))
                or source.query or source.fragment or source.username or source.password):
            raise ValueError('A public provider reference without credentials/query is required.')
        body = artifact['source_utf8'].encode(); total += len(body)
        if total > 64_000_000 or hashlib.sha256(body).hexdigest() != artifact.get('sha256') or artifact['sha256'] in hashes:
            raise ValueError('Boundary-transcription bytes, uniqueness or size differ.')
        hashes.add(artifact['sha256']); value = json.loads(body)
        if value.get('schema') != 'fireatlas-provider-boundary-transcription-v1' or value.get('origin') != 'provider-pixel-boundaries':
            raise ValueError('Provider boundaries required; centre interpolation is not accepted.')
        if not isinstance(value.get('pixels'),list): raise ValueError('Boundary pixel records required.')
        for row in value['pixels']:
            if (not isinstance(row,dict) or not isinstance(row.get('producer_id'),str)
                    or any(type(row.get(k)) is not int or row[k]<0 for k in ('line','sample'))):
                raise ValueError('Explicit native boundary indices required.')
            key = (row['producer_id'], row['line'], row['sample'])
            if key in result: raise ValueError('Duplicate boundary transcription pixel.')
            result[key] = (row, artifact['sha256'])
            if len(result) > MAX_PIXELS: raise ValueError('Boundary pixel count exceeds pilot bound.')
    return result


def file_records(inputs, native):
    """One immutable aligned-file identity per represented mask granule."""
    records=inputs.get('native_files')
    if not isinstance(records,list) or len(records)>MAX_GRANULES:
        raise ValueError('Bounded explicit native-file metadata required.')
    result={}; pairs=PRODUCTS[inputs['cohort']['source']]
    for r in records:
        g=native.get(r.get('producer_id'))
        geo=native.get(r.get('geo_producer_id'))
        if (not g or g['product'] not in pairs or r['producer_id'] in result or not geo
                or geo['product']!=pairs[g['product']] or utc(geo['start_utc'])!=utc(g['start_utc'])
                or any(type(r.get(k)) is not int or not 1<=r[k]<=10000 for k in ('width','height'))
                or any(not isinstance(r.get(k),str) or not HASH.fullmatch(r[k]) for k in ('native_file_sha256','geolocation_sha256'))
                or 'quality_flag_fill' not in r
                or (r['quality_flag_fill'] is not None and (type(r['quality_flag_fill']) is not int or not 0<=r['quality_flag_fill']<=255))):
            raise ValueError('Invalid or ambiguous native/geolocation metadata.')
        result[r['producer_id']]=r
    return result


def evaluate(inputs):
    """Recount one bounded tile/date frame; never itself grant admission."""
    if (inputs.get('schema') != 'fireatlas-opportunity-frame-input-v2' or type(inputs.get('synthetic')) is not bool
            or inputs.get('crs') != 'EPSG:6933' or inputs.get('geometry_origin') != 'provider-pixel-boundaries'
            or digest({k:v for k,v in inputs.items() if k != 'input_sha256'}) != inputs.get('input_sha256')):
        raise ValueError('Source-bound explicit native footprint input required.')
    days = dates(inputs['start'], inputs['end']); scope = domain(inputs['scope_id'])
    cells = tile_cells(inputs['scope_id'], inputs['tile'])
    if len(days) * len(cells) > MAX_DAILY_ROWS:
        raise ValueError('Daily cell ledger exceeds bounded frame size; use smaller tiles/date intervals.')
    native = inventory(inputs); boundaries = _geometry_records(inputs); files=file_records(inputs,native)
    pairs = PRODUCTS[inputs['cohort']['source']]
    masks = [g for g in native.values() if g['product'] in pairs]
    if len(masks) > MAX_GRANULES or len(native) * len(cells) > 1_000_000:
        raise ValueError('Native candidate/tile workload exceeds bound.')
    pixels = inputs.get('pixels')
    if not isinstance(pixels, list) or len(pixels) > MAX_PIXELS:
        raise ValueError('Bounded original native samples required.')
    _, _, union = geometry_library()
    from shapely.geometry import Point
    from shapely.strtree import STRtree
    grouped = defaultdict(list); seen = set(); vertices = 0
    for p in pixels:
        key = (p['producer_id'], p['line'], p['sample'])
        g = native.get(key[0])
        if key in seen or not g or g['product'] not in pairs or any(type(p[k]) is not int or p[k] < 0 for k in ('line', 'sample')):
            raise ValueError('Duplicate/invalid native sample or acquisition identity.')
        seen.add(key)
        f=files.get(key[0])
        if (not f or p['line']>=f['height'] or p['sample']>=f['width']
                or any(p.get(k)!=f[k] for k in ('native_file_sha256','geolocation_sha256','geo_producer_id'))):
            raise ValueError('Sample exceeds or differs from its single aligned native file.')
        if type(p['mask_class']) is not int or not 0 <= p['mask_class'] <= 9 or type(p['quality_flag']) is not int or not 0 <= p['quality_flag'] <= 255:
            raise ValueError('Invalid native mask class or quality flag.')
        if not all(isinstance(p.get(k),str) and HASH.fullmatch(p[k]) for k in ('native_file_sha256','geolocation_sha256','geometry_reference_sha256')):
            raise ValueError('Native, geolocation and boundary identities required.')
        geo = native.get(p['geo_producer_id'])
        if not geo or geo['product'] != pairs[g['product']] or utc(geo['start_utc']) != utc(g['start_utc']):
            raise ValueError('Exact companion geolocation identity required.')
        record = boundaries.get(key)
        if (not record or record[1] != p['geometry_reference_sha256']
                or any(record[0].get(k) != p.get(k) for k in ('polygon','native_file_sha256','geolocation_sha256','geo_producer_id'))):
            raise ValueError('Pixel boundary does not match frozen provider transcription.')
        vertices += len(p['polygon'])
        if vertices > MAX_VERTICES: raise ValueError('Native footprint vertex limit exceeded.')
        shape = polygon(p['polygon'])
        if shape.area > 100_000_000: raise ValueError('Footprint exceeds bounded pixel geometry.')
        if not all(type(p[k]) in (int,float) and math.isfinite(p[k]) for k in ('lat','lon')) or abs(p['lat']) > 90 or abs(p['lon']) > 180:
            raise ValueError('Finite original geolocation coordinates required.')
        if not shape.buffer(.001).covers(Point(*TO_GRID.transform(p['lon'],p['lat']))):
            raise ValueError('Provider boundary does not contain the original native centre.')
        grouped[g['producer_id']].append((p,shape))
    acquisitions = []; failures = []; contacts = 0; daily = defaultdict(list)
    first, end = utc(days[0]+'T00:00:00Z'), utc(days[-1]+'T00:00:00Z')+timedelta(days=1)
    for g in masks:
        start, finish = utc(g['start_utc']), utc(g['end_utc'])
        if start >= end or finish < first: continue  # CMR's inclusive query boundary is retained in raw receipts.
        affected = [day for day in days if start < utc(day+'T00:00:00Z')+timedelta(days=1) and finish >= utc(day+'T00:00:00Z')]
        ambiguous_date = start.date() != finish.date()
        try: envelope = candidate_geometry(g)
        except (ValueError,KeyError,TypeError,OverflowError):
            failures.append(g['producer_id'])
            for day in affected:
                for x,y,cell in cells: daily[(day,x,y)].append(('unknown',g['producer_id']))
            continue
        items = grouped[g['producer_id']]; tree = STRtree([shape for _,shape in items]); rows=[]
        # An envelope that excludes supplied native boundaries cannot safely cull
        # other candidate cells. Retain the entire tile as unknown for this acquisition.
        if any(not envelope.buffer(.001).covers(shape) for _,shape in items):
            failures.append(g['producer_id'])
            for day in affected:
                for x,y,cell in cells: daily[(day,x,y)].append(('unknown',g['producer_id']))
            continue
        for x,y,cell in cells:
            if not envelope.intersects(cell) or envelope.intersection(cell).area <= 0: continue
            pieces=defaultdict(list); fire=False; refs=[]
            for index in tree.query(cell):
                p,shape=items[int(index)]; contacts+=1
                if contacts > MAX_CONTACTS: raise ValueError('Native footprint intersection bound exceeded.')
                clipped=shape.intersection(cell)
                if clipped.area <= 0: continue
                fill=files[g['producer_id']]['quality_flag_fill']
                kind=('unknown' if fill is None or p['quality_flag']==fill or p['quality_flag'] != 0 or p['mask_class'] in (0,6) else
                      'usable' if p['mask_class'] in (3,5,7,8,9) else 'cloud' if p['mask_class']==4 else 'unusable')
                pieces[kind].append(clipped);fire=fire or (kind=='usable' and p['mask_class'] in (7,8,9));refs.append([g['producer_id'],p['line'],p['sample']])
            areas={k:union(v) for k,v in pieces.items()};area=cell.area
            fractions={k:areas[k].area/area if k in areas else 0. for k in ('usable','cloud','unusable','unknown')}
            conflict=sum(areas[a].intersection(areas[b]).area for a,b in [('usable','cloud'),('usable','unusable'),('cloud','unusable')] if a in areas and b in areas)/area
            state='unknown'
            if not ambiguous_date and conflict <= 1e-9 and fractions['unknown'] <= 1e-9:
                if fractions['usable'] >= 1-1e-9:state='detected' if fire else 'observed-without-detection'
                elif fractions['cloud'] >= 1-1e-9:state='cloud'
                elif fractions['unusable'] >= 1-1e-9:state='unusable'
            rows.append({'grid_x':x,'grid_y':y,'area_m2':area,'geometric_state':state,'fractions':fractions,
                         'conflicting_fraction':conflict,'positive_footprint_intersects':fire,'pixel_references':refs,
                         'utc_date_ambiguous':ambiguous_date})
            for day in affected:daily[(day,x,y)].append((state,g['producer_id']))
        acquisitions.append({**g,'rows':rows})
    # Preserve companion spatial support even when its start time matches a mask.
    # Only the mask candidate's represented extent may suppress the corresponding
    # companion extent. Invalid/missing companion geometry leaves the remainder
    # of the tile unknown; native known states inside the mask stay intact.
    paired=defaultdict(list)
    for g in masks:paired[(pairs[g['product']],utc(g['start_utc']))].append(g)
    unpaired=[];unsupported=[]
    for g in native.values():
        if g['product'] in pairs:continue
        start,finish=utc(g['start_utc']),utc(g['end_utc'])
        if start>=end or finish<first:continue
        matched=paired[(g['product'],start)]
        if not matched:unpaired.append(g['producer_id'])
        mask_shapes=[]
        for mask in matched:
            try:mask_shapes.append(candidate_geometry(mask))
            except (ValueError,KeyError,TypeError,OverflowError):pass
        represented=union(mask_shapes)
        affected=[day for day in days if start<utc(day+'T00:00:00Z')+timedelta(days=1) and finish>=utc(day+'T00:00:00Z')]
        try:envelope=candidate_geometry(g).difference(represented)
        except (ValueError,KeyError,TypeError,OverflowError):
            envelope=None;failures.append(g['producer_id'])
        rows=[]
        for x,y,cell in cells:
            if ((envelope is not None and envelope.intersection(cell).area<=cell.area*1e-9)
                    or (envelope is None and represented.buffer(.001).covers(cell))):continue
            rows.append({'grid_x':x,'grid_y':y,'area_m2':cell.area,'geometric_state':'unknown',
                         'unresolved_reason':'geolocation-extent-without-matching-mask-support'})
            for day in affected:daily[(day,x,y)].append(('unknown',g['producer_id']))
        if rows:
            unsupported.append(g['producer_id'])
            acquisitions.append({**g,'rows':rows,'unresolved_reason':'geolocation-extent-without-matching-mask-support'})
    ledger=[]
    for day in days:
        for x,y,cell in cells:
            states=daily[(day,x,y)];codes=[s[0] for s in states]
            state=('detected' if 'detected' in codes else 'observed-without-detection' if 'observed-without-detection' in codes else
                   codes[0] if codes and len(set(codes))==1 else 'no-candidate' if not codes else 'unknown')
            ledger.append({'date':day,'grid_x':x,'grid_y':y,'area_m2':cell.area,'geometric_state':state,
                           'candidate_acquisitions':sorted({s[1] for s in states}),
                           'candidate_acquisition_groups':sorted({native[s[1]]['acquisition_group_id'] for s in states}),
                           'validated_opportunity':'unknown'})
    result={'schema':'fireatlas-opportunity-frame-v2','protocol':protocol(),'scope':scope,'tile':inputs['tile'],
            'start':inputs['start'],'end':inputs['end'],'cohort':inputs['cohort'],'native_versions':inputs['native_versions'],
            'synthetic':inputs['synthetic'],'inputs':inputs,'input_sha256':inputs['input_sha256'],
            'acquisitions':acquisitions,'daily_cells':ledger,'geometry_failures':failures,'unpaired_geolocation':unpaired,
            'unsupported_geolocation':unsupported,
            'geometric_state_counts':dict(Counter(r['geometric_state'] for r in ledger)),
            'validated_observation_opportunity':False,'no_pass_enabled':False,
            'interpretation':'Geometric/quality calculations only. No-candidate is not validated no-pass. A pilot/tile cannot silently establish region-wide opportunity or historical transfer.'}
    result['result_sha256']=digest(result)
    return result


def verify(result):
    rebuilt=evaluate(result['inputs'])
    if digest(rebuilt)!=digest(result): raise ValueError('Native opportunity frame recount differs.')
    return {'verified':True,'result_sha256':result['result_sha256'],'synthetic':result['synthetic'],
            'scope':'self-contained-geometric-recount; original files and independent processing review remain separate'}


def bind_original_files(result, directory):
    """Re-read actual original SDS samples; a resealed checksum is insufficient.

    This binds centres/classes/raw flags and dimensions, not boundary authenticity.
    The latter still requires the provider transcription and independent review.
    """
    verify(result)
    if result['synthetic']: raise ValueError('Synthetic frames cannot bind authentic original files.')
    from .masks import native_layer, checksum
    from .native_context import layer_metadata
    root=Path(directory).resolve(); files={}
    if not root.is_dir(): raise ValueError('Original native directory unavailable.')
    for p in root.rglob('*'):
        if p.is_file() and p.suffix.lower() in {'.nc','.hdf','.h5'}:
            if not p.resolve().is_relative_to(root): raise ValueError('Native symlink escapes original-file root.')
            files.setdefault(p.name,[]).append(p)
    def locate(producer, expected):
        if Path(producer).name!=producer: raise ValueError('Native producer identity must be a basename.')
        found=[p for name in (producer,producer+'.nc',producer+'.hdf',producer+'.h5') for p in files.get(name,[])]
        if len(found)!=1 or checksum(found[0])!=expected: raise ValueError('Missing, ambiguous or altered original native file.')
        return found[0]
    inputs=result['inputs']; records=file_records(inputs,inventory(inputs)); grouped=defaultdict(list)
    for p in inputs['pixels']: grouped[p['producer_id']].append(p)
    checked=0
    for producer, rows in sorted(grouped.items()):
        record=records[producer]
        mask=locate(producer,record['native_file_sha256']);geo=locate(record['geo_producer_id'],record['geolocation_sha256'])
        layers={
            'mask_class':native_layer(mask,('FireMask','fire_mask','fire mask'))[1],
            'lat':native_layer(geo,('Latitude','latitude'))[1],
            'lon':native_layer(geo,('Longitude','longitude'))[1],
            'quality_flag':native_layer(geo,('gflags','quality_flag'))[1]}
        if (any((l.RasterXSize,l.RasterYSize)!=(record['width'],record['height']) for l in layers.values())
                or layer_metadata(layers['quality_flag'],'flags')['fill']!=record['quality_flag_fill']):
            raise ValueError('Original native dimensions or flag fill metadata differ.')
        strips=defaultdict(list)
        for p in rows: strips[p['line']//16*16].append(p)
        for first, pixels in sorted(strips.items()):
            arrays={k:layer.ReadAsArray(0,first,record['width'],min(16,record['height']-first)) for k,layer in layers.items()}
            for p in pixels:
                for key, values in arrays.items():
                    raw=float(values[p['line']-first,p['sample']])
                    if not math.isfinite(raw) or raw!=p[key]: raise ValueError('Original native centre/class/flag does not reproduce.')
                checked+=1
    return {'schema':'fireatlas-opportunity-original-binding-v2','frame_sha256':result['result_sha256'],
            'pixels_checked':checked,'files_checked':len(grouped),'verified':True,
            'scope':'Original aligned native classes, coordinates, raw flags, fill metadata, file hashes and dimensions; provider boundaries require separate review.'}
