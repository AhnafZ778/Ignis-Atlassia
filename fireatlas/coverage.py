"""Bounded polygon/quality coverage calculations, separate from centroid samples.

Provider granule envelopes support candidate intersection only. Pixel footprints
require explicit boundary provenance; interpolated centres are not accepted as
provider boundaries. Scientific/no-pass qualification requires external evidence.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import date,datetime,timezone
import math,re,sqlite3
from pathlib import Path
from .qualification import digest
from .core import TO_GRID
from .validity import CASES

MAX_CELLS=20000
MAX_GRANULES=500
MAX_ENVELOPE_CELLS=1_000_000
MAX_PIXELS=200000
MAX_TOTAL_VERTICES=1_000_000
MAX_INTERSECTIONS=2_000_000
HASH=re.compile('[0-9a-f]{64}\\Z')


def geometry_library():
    try:
        from shapely.geometry import Polygon,box
        from shapely.ops import unary_union
    except ImportError as exc:raise RuntimeError('Footprint research requires the pinned shapely research extra.') from exc
    return Polygon,box,unary_union


def polygon(points,*,geographic=False):
    Polygon,_,_=geometry_library()
    if not isinstance(points,list) or not 4<=len(points)<=10000:raise ValueError('A bounded explicit closed polygon ring is required.')
    if any(not isinstance(p,(list,tuple)) or len(p)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in p) for p in points):raise ValueError('Finite 2D polygon vertices required.')
    if points[0]!=points[-1]:raise ValueError('Polygon ring must be explicitly closed.')
    if geographic:
        if any(abs(x)>180 or abs(y)>90 for x,y in points) or max(p[0] for p in points)-min(p[0] for p in points)>180:raise ValueError('Unsupported geographic or dateline-wrapping geometry remains unknown.')
        points=[TO_GRID.transform(*p) for p in points]
    result=Polygon(points)
    if not result.is_valid or result.is_empty or result.area<=0:raise ValueError('Invalid, empty or self-intersecting polygon.')
    return result


def interior_cells(case_id):
    _,box,_=geometry_library();w,s,e,n=CASES[case_id]['bbox'];x0,y0=TO_GRID.transform(w,s);x1,y1=TO_GRID.transform(e,n)
    cells=[(x,y) for x in range(math.ceil(x0/1000),math.floor(x1/1000)) for y in range(math.ceil(y0/1000),math.floor(y1/1000))]
    if len(cells)>MAX_CELLS:raise ValueError('Coverage pilot exceeds bounded cell count.')
    return cells


def candidate_geometry(granule):
    """CMR polygon coordinates are latitude longitude; preserve all rings."""
    _,box,unary_union=geometry_library();raw=granule.get('candidate_geometry',{});parts=[]
    rings=[ring for group in raw.get('polygons',[]) for ring in group]
    if len(rings)>32 or any(not isinstance(ring,str) or len(ring)>400000 for ring in rings):raise ValueError('Provider geometry exceeds bounded ring size.')
    for group in raw.get('polygons',[]):
        for ring in group:
            numbers=[float(v) for v in ring.split()]
            if len(numbers)%2:raise ValueError('Malformed CMR polygon.')
            parts.append(polygon([[numbers[i+1],numbers[i]] for i in range(0,len(numbers),2)],geographic=True))
    # Bounding rectangles are retained as envelopes, not pixel boundaries.
    for value in raw.get('boxes',[]):
        numbers=list(map(float,value.split()))
        if len(numbers)!=4:raise ValueError('Malformed CMR bounding rectangle.')
        s,w,n,e=numbers
        parts.append(polygon([[w,s],[e,s],[e,n],[w,n],[w,s]],geographic=True))
    if not parts:raise ValueError('No supported provider polygon/envelope geometry.')
    return unary_union(parts)


def complete_inventory(inventory,case_id):
    if inventory.get('case_id')!=case_id or inventory.get('inventory_complete') is not True:return False
    products=inventory.get('products',[])
    if len(products)!=6 or {p.get('product') for p in products}!={'MOD14','MYD14','VNP14IMG','MOD03','MYD03','VNP03IMG'}:return False
    for p in products:
        gs=p.get('granules',[]);pages=p.get('pages',[])
        if p.get('inventory_complete') is not True or p.get('cmr_hits')!=len(gs) or len({g['cmr_id'] for g in gs})!=len(gs):return False
        if sum(page['entries'] for page in pages)!=len(gs) or any(page['hits']!=len(gs) or not HASH.fullmatch(page['sha256']) for page in pages):return False
    return True


def envelope_report(case_id,inventory,*,cells=None):
    """Compute actual provider-envelope intersections, without clear/no-pass claims."""
    if case_id not in CASES or inventory.get('case_id')!=case_id:raise ValueError('Fixed-case inventory required.')
    _,box,_=geometry_library();cells=interior_cells(case_id) if cells is None else [tuple(c) for c in cells]
    allowed=set(interior_cells(case_id))
    if len(cells)>MAX_CELLS or len(set(cells))!=len(cells) or any(tuple(c) not in allowed for c in cells):raise ValueError('Unique fully interior pilot cells required.')
    granules=[g for p in inventory['products'] for g in p['granules'] if g['product'] in ('MOD14','MYD14','VNP14IMG')];out=[];failures=[]
    if len(granules)>MAX_GRANULES or len(granules)*len(cells)>MAX_ENVELOPE_CELLS:raise ValueError('Candidate/cell pilot exceeds bounded intersection workload.')
    for g in granules:
        try:shape=candidate_geometry(g)
        except (ValueError,TypeError,KeyError,OverflowError) as exc:failures.append({'producer_id':g['producer_id'],'reason':str(exc)});continue
        intersections=[]
        for x,y in cells:
            cell=box(x*1000,y*1000,(x+1)*1000,(y+1)*1000)
            area=shape.intersection(cell).area
            if area>0:intersections.append({'grid_x':x,'grid_y':y,'envelope_fraction':min(1.,area/1_000_000)})
        out.append({'producer_id':g['producer_id'],'product':g['product'],'version':g['version'],'start_utc':g['start_utc'],'end_utc':g.get('end_utc'),
                    'geometry_sha256':digest(g['candidate_geometry']),'intersections':intersections,'intersected_cells':len(intersections)})
    value={'schema':'fireatlas-candidate-envelope-coverage-v1','case_id':case_id,'inventory':inventory,'inventory_sha256':digest(inventory),'inventory_complete':complete_inventory(inventory,case_id),
           'grid':'EPSG:6933 1000m fully interior cells only','n_cells':len(cells),'cell_ids':[list(c) for c in cells],'acquisitions':out,'geometry_failures':failures,
           'validated_observation_opportunity':False,'no_pass_enabled':False,'opportunity_denominator':None,
           'interpretation':'Intersections are provider granule-envelope geometry only. They do not establish pixel quality, clear sky, full-cell opportunity or verified no-pass.'}
    value['result_sha256']=digest(value);return value


def pixel_bounds(pixels):
    if not isinstance(pixels,list) or len(pixels)>MAX_PIXELS:raise ValueError('Pixel-footprint pilot exceeds bounded input size.')
    vertices=0
    for pixel in pixels:
        if not isinstance(pixel,dict) or not isinstance(pixel.get('polygon'),list):raise ValueError('Explicit bounded pixel polygons required.')
        vertices+=len(pixel['polygon'])
        if vertices>MAX_TOTAL_VERTICES:raise ValueError('Pixel-footprint total vertex limit exceeded.')


def footprint_input(case_id,inventory,pixels,*,synthetic=False):
    """Build a recountable contract; caller must supply actual boundary evidence."""
    pixel_bounds(pixels)
    value={'schema':'fireatlas-pixel-footprint-input-v1','case_id':case_id,'inventory_sha256':digest(inventory),'synthetic':synthetic,
           'crs':'EPSG:6933','geometry_origin':'provider-pixel-boundaries','pixels':pixels}
    value['input_sha256']=digest(value);return value


def native_samples(inputs):
    """Freeze the original decoded mask sample and file identities for each pixel."""
    from .masks import STORE
    result=[]
    with sqlite3.connect(Path(STORE).resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        for p in inputs['pixels']:
            row=db.execute('SELECT p.*,g.file_sha256,g.geo_sha256 FROM pixels p JOIN granules g ON p.case_id=g.case_id AND p.producer_id=g.producer_id WHERE p.case_id=? AND p.producer_id=? AND p.line=? AND p.sample=?',(inputs['case_id'],p['producer_id'],p['line'],p['sample'])).fetchone()
            if row is None:raise ValueError('Provider boundary has no matching original decoded native sample; retain it as unsupported.')
            result.append(dict(row))
    return result


def evaluate_pixels(inputs,inventory,*,synthetic=False,cells=None,original_samples=None):
    if inputs.get('schema')!='fireatlas-pixel-footprint-input-v1' or inputs.get('synthetic') is not synthetic or inputs.get('crs')!='EPSG:6933' or inputs.get('geometry_origin')!='provider-pixel-boundaries':raise ValueError('Explicit provider pixel boundaries required; centroid interpolation is not a validated footprint.')
    pixel_bounds(inputs.get('pixels'))
    if digest({k:v for k,v in inputs.items() if k!='input_sha256'})!=inputs.get('input_sha256') or inputs['inventory_sha256']!=digest(inventory):raise ValueError('Pixel/inventory identity differs.')
    if synthetic and original_samples is not None:raise ValueError('Synthetic boundary tests cannot mix with authentic native samples.')
    source_samples=None if synthetic else (native_samples(inputs) if original_samples is None else original_samples)
    if source_samples is not None:
        if len(source_samples)!=len(inputs['pixels']):raise ValueError('Every authentic boundary needs its original decoded sample.')
        source_samples={(r['producer_id'],r['line'],r['sample']):r for r in source_samples}
        if len(source_samples)!=len(inputs['pixels']):raise ValueError('Duplicate original native sample.')
    case=inputs['case_id'];envelopes=envelope_report(case,inventory,cells=cells);_,box,unary_union=geometry_library()
    granules={g['producer_id']:g for p in inventory['products'] for g in p['granules'] if g['product'] in ('MOD14','MYD14','VNP14IMG')}
    grouped=defaultdict(list);seen=set();pixels=inputs['pixels']
    if len(pixels)>MAX_PIXELS:raise ValueError('Pixel-footprint pilot exceeds bounded input size.')
    for pixel in pixels:
        identifier=(pixel['producer_id'],pixel['line'],pixel['sample'])
        if identifier in seen or identifier[0] not in granules:raise ValueError('Duplicate pixel or unknown acquisition.')
        seen.add(identifier)
        if any(type(pixel.get(k)) is not int or pixel[k]<0 for k in ('line','sample')) or type(pixel.get('mask_class')) is not int or not 0<=pixel['mask_class']<=9:raise ValueError('Invalid pixel index/class.')
        if not all(isinstance(pixel.get(k),str) and HASH.fullmatch(pixel[k]) for k in ('native_file_sha256','geolocation_sha256','geometry_reference_sha256')):raise ValueError('Native, geolocation and boundary provenance hashes required.')
        if pixel.get('quality') not in ('valid','invalid','unknown'):raise ValueError('Explicit decoded quality state required.')
        shape=polygon(pixel['polygon'])
        if source_samples is not None:
            from shapely.geometry import Point
            original=source_samples.get(identifier)
            if not original or original['mask_class']!=pixel['mask_class'] or original['file_sha256']!=pixel['native_file_sha256'] or original['geo_sha256']!=pixel['geolocation_sha256'] or original['case_id']!=case:raise ValueError('Boundary class/file identities differ from the original native sample.')
            center=Point(*TO_GRID.transform(original['lon'],original['lat']))
            if not shape.buffer(.001).covers(center):raise ValueError('Declared footprint does not contain its original pixel centre.')
        if shape.area>100_000_000:raise ValueError('Native pixel exceeds the declared pilot geometry limit.')
        grouped[identifier[0]].append((pixel,shape))
    rows=[];contacts=0
    for acquisition in envelopes['acquisitions']:
        identifier=acquisition['producer_id'];native=grouped[identifier]
        from shapely.strtree import STRtree
        tree=STRtree([shape for pixel,shape in native])
        for cell in acquisition['intersections']:
            x,y=cell['grid_x'],cell['grid_y'];square=box(x*1000,y*1000,(x+1)*1000,(y+1)*1000);pieces=defaultdict(list);evidence=[];fire=False
            for index in tree.query(square):
                pixel,shape=native[int(index)]
                contacts+=1
                if contacts>MAX_INTERSECTIONS:raise ValueError('Pixel/cell intersection operation limit exceeded.')
                if not shape.intersects(square):continue
                clipped=shape.intersection(square)
                if clipped.area<=0:continue
                kind='unknown' if pixel['quality']=='unknown' or pixel['mask_class'] in (0,6) else 'usable' if pixel['quality']=='valid' and pixel['mask_class'] in (3,5,7,8,9) else 'cloud' if pixel['quality']=='valid' and pixel['mask_class']==4 else 'unusable'
                pieces[kind].append(clipped);fire=fire or (kind=='usable' and pixel['mask_class'] in (7,8,9));evidence.append([pixel['producer_id'],pixel['line'],pixel['sample']])
            areas={k:unary_union(v) for k,v in pieces.items()};fractions={k:areas[k].area/1_000_000 if k in areas else 0. for k in ('usable','cloud','unusable','unknown')}
            overlap=sum(areas[a].intersection(areas[b]).area for a,b in [('usable','cloud'),('usable','unusable'),('cloud','unusable')] if a in areas and b in areas)/1_000_000
            state='unknown'
            if overlap<=1e-9 and fractions['unknown']<=1e-9:
                if fractions['usable']>=1-1e-9:state='detected' if fire else 'observed-without-detection'
                elif fractions['cloud']>=1-1e-9:state='cloud'
                elif fractions['unusable']>=1-1e-9:state='unusable'
            rows.append({'producer_id':identifier,'start_utc':acquisition['start_utc'],'end_utc':acquisition['end_utc'],'product':acquisition['product'],'grid_x':x,'grid_y':y,
                         'geometric_sample_state':state,'usable_fraction':fractions['usable'],'cloud_fraction':fractions['cloud'],'unusable_fraction':fractions['unusable'],
                         'unknown_fraction':fractions['unknown'],'ambiguous_overlap_fraction':overlap,'positive_footprint_intersects':fire,'pixel_references':evidence,'validated_opportunity':'unknown'})
    value={'schema':'fireatlas-pixel-footprint-coverage-v1','case_id':case,'synthetic':synthetic,'inputs':inputs,'inventory':inventory,'original_native_samples':None if source_samples is None else sorted(source_samples.values(),key=lambda r:(r['producer_id'],r['line'],r['sample'])),'cell_ids':envelopes['cell_ids'],
           'input_sha256':inputs['input_sha256'],'rows':rows,'state_counts':dict(Counter(r['geometric_sample_state'] for r in rows)),
           'geometry_failures':envelopes['geometry_failures'],'inventory_complete':envelopes['inventory_complete'],'no_pass_enabled':False,'opportunity_denominator':None,
           'admitted':False,'independent_geometry_review':'pending','interpretation':'Calculated geometric/quality sample states only. Independent processing/geometry review is required for validated observation opportunity; no-pass remains disabled.'}
    value['result_sha256']=digest(value);return value


def verify(value):
    if value.get('schema')=='fireatlas-candidate-envelope-coverage-v1':
        rebuilt=envelope_report(value['case_id'],value['inventory'],cells=value['cell_ids'])
    elif value.get('schema')=='fireatlas-pixel-footprint-coverage-v1':
        rebuilt=evaluate_pixels(value['inputs'],value['inventory'],synthetic=value.get('synthetic') is True,cells=value['cell_ids'],original_samples=value.get('original_native_samples'))
    else:raise ValueError('Unsupported coverage evidence schema.')
    if digest(rebuilt)!=digest(value):raise ValueError('Footprint coverage recount differs.')
    return {'verified':True,'result_sha256':value['result_sha256'],'synthetic':value.get('synthetic')}
