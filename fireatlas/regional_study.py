"""Bounded, frozen regional harmonized evidence and scientific verification.

This contract is separate from the generic union-calendar study. Hashes provide
integrity, not source authentication or independent scientific endorsement.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import sqlite3
import tempfile
import threading
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

from .availability import NOTICE_FILE
from .calendar_v2 import MCD64_REPORT, calendar_v2, prepare_calendar_v2
from .core import GRID_VERSION, TO_GRID, connect
from .provenance import sanitize_public_payload
from .regions import REGIONS
from .result_identity import digest, encoded, scientific_material

SCHEMA = 'fireatlas-regional-study-v1'
MAX_ROWS = 2_000_000
MAX_EXPANDED = 3 * 1024**3
MAX_COMPRESSED = 512 * 1024**2
MAX_RECORD = 64 * 1024
MAX_METADATA = 32 * 1024**2
CHUNK_ROWS = 100_000
CHUNK_BYTES = 128 * 1024**2
BUILD_LOCK = threading.Lock()
TABLES = ('batches', 'export_windows', 'source_exports')
SOURCES = ('MODIS_SP', 'VIIRS_SNPP_SP')

class StaleResult(ValueError):
    pass


def _selection(region, year, month, day, fallback_year):
    if region not in REGIONS or not 2006 <= year <= 2026 or not 1 <= month <= 12:
        raise ValueError('Supported regional box, year 2006–2026 and month 1–12 required.')
    if fallback_year != 2026:
        raise ValueError('Regional study v1 uses the production 2026 preparation horizon.')
    if day and (date.fromisoformat(day).isoformat() != day or day[:7] != f'{year:04d}-{month:02d}'):
        raise ValueError('Selected day must belong to the selected month.')
    return {'region':region, 'bbox':list(REGIONS[region]['bbox']), 'year':year,
            'month':month, 'day':day, 'fallback_year':fallback_year, 'timezone':'UTC',
            'metric':'harmonized-activity', 'grid':GRID_VERSION,
            'filter':'FIRMS type 0 or missing; all confidence levels',
            'deduplication':'distinct occupied grid cells per source/UTC date; no replay alias filtering'}


def build_bundle(db, output, **selection):
    """Freeze external dependencies and use one database read transaction."""
    owned=not db.in_transaction
    if owned:db.execute('BEGIN')
    try:
        with tempfile.TemporaryDirectory(prefix='fireatlas-regional-inputs-') as temporary:
            directory=Path(temporary)
            notices=json.loads(Path(selection.get('notice_path') or NOTICE_FILE).read_text())
            try:corroboration=json.loads(Path(selection.get('corroboration_path') or MCD64_REPORT).read_text())
            except (OSError,ValueError):corroboration={}
            notice_path=directory/'notices.json';notice_path.write_bytes(encoded(notices))
            corroboration_path=directory/'corroboration.json';corroboration_path.write_bytes(encoded(corroboration))
            prepared=selection.get('prepared')
            if prepared and prepared.get('notice_sha256')!=digest(notices):
                raise StaleResult('Sensor notices changed after preparation. Reload the selection before exporting.')
            return _build_bundle(db,output,**{**selection,'notice_path':notice_path,'corroboration_path':corroboration_path})
    finally:
        if owned:db.rollback()


def _build_bundle(db, output, *, region, year, month, day=None, fallback_year=2026,
                 expected_result_sha256=None, prepared=None, notice_path=None,
                 corroboration_path=None):
    """Write to disk inside a consistent caller-owned read transaction."""
    config=_selection(region, year, month, day, fallback_year)
    prepared=prepared or prepare_calendar_v2(db,region=region,fallback_year=fallback_year,notice_path=notice_path)
    result=calendar_v2(db,region=region,year=year,month=month,include_history=True,
                       prepared=prepared,corroboration_path=corroboration_path)
    if expected_result_sha256 and result['meta']['result_sha256'] != expected_result_sha256:
        raise StaleResult('The scientific inputs changed. Reload this selection before downloading its result.')
    config['history_start']=prepared['history_start'].isoformat()
    config['history_end']=prepared['history_end'].isoformat()
    bbox=config['bbox']
    clauses="o.source_id IN ('MODIS_SP','VIIRS_SNPP_SP') AND b.demo=0 AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=? AND substr(o.acquisition_utc,1,10)>=? AND substr(o.acquisition_utc,1,10)<=?"
    args=(bbox[0],bbox[2],bbox[1],bbox[3],config['history_start'],config['history_end'])
    count=db.execute(f'SELECT count(*) FROM observations o JOIN batches b ON b.id=o.batch_id WHERE {clauses}',args).fetchone()[0]
    if count > MAX_ROWS: raise ValueError(f'Regional result exceeds {MAX_ROWS:,} rows; no sampled bundle was created.')
    records={};expanded=0
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    try:
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as archive:
            def write(name, value):
                nonlocal expanded
                body=encoded(value)
                if len(body)>MAX_METADATA: raise ValueError('Regional metadata entry exceeds 32 MiB.')
                expanded+=len(body)
                if expanded>MAX_EXPANDED: raise ValueError('Regional expanded payload exceeds 3 GiB.')
                archive.writestr(name,body)
                records[name]={'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body)}
            write('selection.json',config)
            write('calendar-v2.json',result)
            write('calibration.json',result['calibration'])
            for table in TABLES:
                query=f"SELECT * FROM {table} WHERE source_id IN ('MODIS_SP','VIIRS_SNPP_SP')"
                if table=='batches': query+=' AND demo=0'
                else: query+=' AND batch_id IN (SELECT id FROM batches WHERE demo=0)'
                query+=' ORDER BY '+('id' if table=='batches' else 'batch_id')
                name=table.replace('_','-')+'.json';hasher=hashlib.sha256();size=0
                with archive.open(name,'w',force_zip64=True) as stream:
                    def append(body):
                        nonlocal size,expanded
                        size+=len(body);expanded+=len(body)
                        if size>MAX_METADATA or expanded>MAX_EXPANDED:raise ValueError('Regional metadata or expanded payload exceeds limit.')
                        stream.write(body);hasher.update(body)
                    append(b'[');first=True
                    for row in db.execute(query):
                        if not first:append(b',')
                        append(encoded(dict(row)));first=False
                    append(b']')
                records[name]={'sha256':hasher.hexdigest(),'bytes':size}
            write('notices.json',json.loads(Path(notice_path or NOTICE_FILE).read_text()))
            try: corroboration=json.loads(Path(corroboration_path or MCD64_REPORT).read_text())
            except (OSError,ValueError): corroboration={}
            write('corroboration.json',corroboration)
            write('method.json',{'schema':SCHEMA,'grid':GRID_VERSION,'calibration_method':result['calibration'].get('method_version'),
                'prediction_intervals':'withheld','float_comparison':{'rel_tol':1e-12,'abs_tol':1e-9},
                'limits':{'rows':MAX_ROWS,'expanded_bytes':MAX_EXPANDED,'compressed_bytes':MAX_COMPRESSED},
                'reproduction':'Full standard-source region history; source ledgers, notices, calibration and baselines frozen.'})
            write('release.json',{'release_id':result['meta']['release_id'],'result_sha256':result['meta']['result_sha256'],
                'created_utc':datetime.now(timezone.utc).isoformat(),'dependencies':result['meta']['dependencies']})
            write('README.json',{'verify':'uv run python -m fireatlas.regional_study verify path/to/result.zip',
                'metric':result['meta']['unit'],'boundary':'Occupied centroid cell-days are not fires or burned area.',
                'context':'Frozen corroboration is checked for metadata consistency; native rasters are not independently reprocessed.',
                'integrity':'Checksums are not signatures or NASA authentication.'})
            cursor=db.execute(f'SELECT o.* FROM observations o JOIN batches b ON b.id=o.batch_id WHERE {clauses} ORDER BY o.acquisition_utc,o.detection_id',args)
            part=0;stream=None;part_size=part_rows=0;hasher=None;name=None
            def close_part():
                if stream is not None:
                    stream.close();records[name]={'sha256':hasher.hexdigest(),'bytes':part_size,'rows':part_rows}
            try:
                for row in cursor:
                    body=encoded(dict(row))+b'\n'
                    if len(body)>MAX_RECORD: raise ValueError('Regional JSONL record exceeds 64 KiB.')
                    if stream is None or part_rows>=CHUNK_ROWS or part_size+len(body)>CHUNK_BYTES:
                        close_part();part+=1;name=f'observations/{part:04d}.jsonl';stream=archive.open(name,'w',force_zip64=True)
                        part_size=part_rows=0;hasher=hashlib.sha256()
                    expanded+=len(body)
                    if expanded>MAX_EXPANDED: raise ValueError('Regional expanded payload exceeds 3 GiB.')
                    stream.write(body);hasher.update(body);part_size+=len(body);part_rows+=1
                close_part();stream=None
            finally:
                if stream is not None: stream.close()
            manifest_body=encoded({'schema':SCHEMA,'observation_count':count,'files':records,
                'result_sha256':result['meta']['result_sha256'],'release_id':result['meta']['release_id']})
            if len(manifest_body)>MAX_METADATA or expanded+len(manifest_body)>MAX_EXPANDED:raise ValueError('Regional manifest or expanded payload exceeds limit.')
            archive.writestr('manifest.json',manifest_body)
        if output.stat().st_size>MAX_COMPRESSED: raise ValueError('Regional compressed archive exceeds 512 MiB.')
    except BaseException:
        output.unlink(missing_ok=True);raise
    return {'path':str(output),'rows':count,'bytes':output.stat().st_size,'result_sha256':result['meta']['result_sha256'],
            'release_id':result['meta']['release_id'],'schema':SCHEMA}


def _same(expected, actual, path='result'):
    if isinstance(expected,dict) and isinstance(actual,dict):
        if expected.keys()!=actual.keys(): raise ValueError(f'Scientific recount keys differ at {path}.')
        for key in expected: _same(expected[key],actual[key],path+'/'+key)
    elif isinstance(expected,list) and isinstance(actual,list):
        if len(expected)!=len(actual): raise ValueError(f'Scientific recount length differs at {path}.')
        for i,(a,b) in enumerate(zip(expected,actual)): _same(a,b,f'{path}/{i}')
    elif isinstance(expected,float) and isinstance(actual,(float,int)) and not isinstance(actual,bool):
        if not math.isfinite(expected) or not math.isclose(expected,actual,rel_tol=1e-12,abs_tol=1e-9):
            raise ValueError(f'Scientific recount differs at {path}: {expected} != {actual}.')
    elif type(expected)!=type(actual) or expected!=actual:
        raise ValueError(f'Scientific recount differs at {path}.')


def verify_bundle(path):
    """Validate safely, reconstruct SQLite, then recount/refit frozen science."""
    path=Path(path)
    if path.stat().st_size>MAX_COMPRESSED: raise ValueError('Compressed archive exceeds limit.')
    with tempfile.TemporaryDirectory(prefix='fireatlas-regional-verify-') as tmp, zipfile.ZipFile(path) as archive:
        entries=archive.infolist();names=[item.filename for item in entries]
        if len(names)!=len(set(names)) or len(names)>128:
            raise ValueError('Duplicate or excessive archive entries.')
        if 'manifest.json' not in names or archive.getinfo('manifest.json').file_size>MAX_METADATA:
            raise ValueError('Manifest missing or oversized.')
        manifest=json.loads(archive.read('manifest.json'))
        if manifest.get('schema')!=SCHEMA or set(names)!=set(manifest['files'])|{'manifest.json'}:
            raise ValueError('Unsupported schema or incomplete file inventory.')
        total=archive.getinfo('manifest.json').file_size
        for name,entry in manifest['files'].items():
            if name.startswith('/') or '..' in Path(name).parts or '\\' in name:
                raise ValueError('Unsafe archive path.')
            info=archive.getinfo(name)
            if info.file_size!=entry['bytes']: raise ValueError('Manifest size mismatch.')
            maximum=CHUNK_BYTES if name.startswith('observations/') else MAX_METADATA
            if info.file_size>maximum: raise ValueError('Entry expansion limit exceeded.')
            h=hashlib.sha256();size=0
            with archive.open(name) as source:
                for chunk in iter(lambda:source.read(1024*1024),b''):
                    size+=len(chunk);total+=len(chunk);h.update(chunk)
                    if total>MAX_EXPANDED: raise ValueError('Expanded archive exceeds limit.')
            if size!=info.file_size or h.hexdigest()!=entry['sha256']: raise ValueError(f'Checksum mismatch: {name}')
        required={'selection.json','calendar-v2.json','calibration.json','batches.json','export-windows.json',
                  'source-exports.json','notices.json','corroboration.json','method.json','release.json','README.json'}
        if not required.issubset(names): raise ValueError('Required frozen inputs missing.')
        read=lambda name:json.loads(archive.read(name))
        config=read('selection.json');checked=_selection(config['region'],config['year'],config['month'],config.get('day'),config['fallback_year'])
        if any(config[k]!=v for k,v in checked.items()): raise ValueError('Selection contract changed.')
        expected=read('calendar-v2.json')
        _same(expected['calibration'],read('calibration.json'),'calibration')
        db=connect(Path(tmp)/'recount.sqlite3')
        try:
            for table in TABLES:
                for row in read(table.replace('_','-')+'.json'):
                    if row['source_id'] not in SOURCES or (table=='batches' and row['demo']!=0):
                        raise ValueError('Non-authentic or unsupported cohort in regional package.')
                    cols=[item[1] for item in db.execute(f'PRAGMA table_info({table})')]
                    if set(row)!=set(cols): raise ValueError('Frozen table schema mismatch.')
                    db.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",[row[c] for c in cols])
            count=0;columns=[item[1] for item in db.execute('PRAGMA table_info(observations)')]
            insert=f"INSERT INTO observations ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})"
            w,s,e,n=config['bbox']
            for name in sorted(x for x in names if x.startswith('observations/')):
                part_count=0
                with archive.open(name) as source:
                    while True:
                        line=source.readline(MAX_RECORD+1)
                        if not line:break
                        if len(line)>MAX_RECORD:raise ValueError('JSONL record too large.')
                        row=json.loads(line);count+=1;part_count+=1
                        if count>MAX_ROWS or part_count>CHUNK_ROWS: raise ValueError('Observation limit exceeded.')
                        if set(row)!=set(columns) or row['source_id'] not in SOURCES or row['processing_level']!='SP':
                            raise ValueError('Observation contract mismatch.')
                        if not (w<=row['lon']<=e and s<=row['lat']<=n) or abs(row['lat'])>86:
                            raise ValueError('Observation outside recorded grid/AOI.')
                        if not '2006-07-01'<=row['acquisition_utc'][:10]<=config['history_end']:
                            raise ValueError('Observation outside preparation horizon.')
                        x,y=TO_GRID.transform(row['lon'],row['lat'])
                        if (math.floor(x/1000),math.floor(y/1000))!=(row['grid_x'],row['grid_y']):
                            raise ValueError('Stored grid differs from coordinates.')
                        db.execute(insert,[row[c] for c in columns])
                if part_count!=manifest['files'][name].get('rows'): raise ValueError('Chunk row count mismatch.')
            if count!=manifest['observation_count']: raise ValueError('Observation inventory mismatch.')
            db.commit()
            for name in ['notices.json','corroboration.json']: (Path(tmp)/name).write_bytes(archive.read(name))
            prepared=prepare_calendar_v2(db,region=config['region'],fallback_year=config['fallback_year'],notice_path=Path(tmp)/'notices.json')
            if prepared['history_start'].isoformat()!=config['history_start'] or prepared['history_end'].isoformat()!=config['history_end']:
                raise ValueError('Preparation horizon differs from frozen scope.')
            actual=calendar_v2(db,region=config['region'],year=config['year'],month=config['month'],include_history=True,
                prepared=prepared,corroboration_path=Path(tmp)/'corroboration.json')
            _same(scientific_material(expected),scientific_material(actual))
            _same(expected.get('history'),actual.get('history'),'history')
            if digest(scientific_material(actual))!=manifest['result_sha256']:
                raise ValueError('Scientific result identity mismatch.')
            release=read('release.json')
            if release['result_sha256']!=manifest['result_sha256'] or release['release_id']!=actual['meta']['release_id'] or manifest['release_id']!=release['release_id']:
                raise ValueError('Release identity mismatch.')
            return {'schema':SCHEMA,'status':'verified','rows':count,'result_sha256':manifest['result_sha256'],
                    'release_id':actual['meta']['release_id'],'checks':'hashes, grid, completeness, frozen calibration, daily/monthly states, baselines, season'}
        except sqlite3.Error as error:
            raise ValueError(f'Invalid frozen database: {error}') from error
        finally: db.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);subs=parser.add_subparsers(dest='command',required=True)
    verify=subs.add_parser('verify');verify.add_argument('bundle',type=Path)
    build=subs.add_parser('build');build.add_argument('--db',type=Path,required=True);build.add_argument('--region',choices=REGIONS,required=True)
    build.add_argument('--year',type=int,required=True);build.add_argument('--month',type=int,required=True);build.add_argument('--day');build.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='verify': result=verify_bundle(args.bundle)
    else:
        db=sqlite3.connect(args.db.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
        try:
            db.execute('BEGIN');result=build_bundle(db,args.output,region=args.region,year=args.year,month=args.month,day=args.day)
        finally: db.close()
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
