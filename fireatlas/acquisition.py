"""Bounded resumable FIRMS regional acquisition into an isolated campaign store.

Original databases and archives are never changed. Per-request original bytes and
receipts survive interruption; complete-month imports require every receipt.
"""
from __future__ import annotations
from calendar import monthrange
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen
from .core import REQUIRED_COLUMNS, connect, ingest
from .fetch import BASE_URL, availability
from .qualification import digest
from .regions import REGIONS
from .settings import firms_key

CAP_BYTES=10_000_000_000
MIN_FREE_BYTES=20_000_000_000
WINDOW_LIMIT=2_000_000
SOURCES=('MODIS_SP','VIIRS_SNPP_SP','VIIRS_NOAA20_SP','VIIRS_NOAA21_SP')


def utcnow(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.tmp')
    try:
        with temporary.open('w') as f:
            json.dump(value,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
        temporary.replace(path)
    finally: temporary.unlink(missing_ok=True)


def usage(root):
    root=Path(root)
    total=0
    if root.exists():
        for path in root.rglob('*'):
            try:
                info=path.stat()
                if stat.S_ISREG(info.st_mode):total+=info.st_size
            except FileNotFoundError:
                # A concurrent worker can atomically rename a temporary file.
                # The whole-batch reserve still bounds every request's bytes.
                continue
    return total


def budget(root,reserve=0):
    root=Path(root);probe=root
    while not probe.exists(): probe=probe.parent
    project=Path(__file__).resolve().parents[1]
    task_store=project/'data/qualification'
    if root.resolve().is_relative_to(task_store.resolve()):
        used=usage(task_store)+usage(project/'site/data/qualification')
    else: used=usage(root)
    free=shutil.disk_usage(probe).free
    if reserve<0 or used+reserve>CAP_BYTES or free-reserve<MIN_FREE_BYTES:
        raise ValueError('Storage gate closed: campaign must stay within 10 GB and leave at least 20 GB free.')
    return {'used_bytes':used,'free_bytes':free,'reserved_upper_bound_bytes':reserve,'cap_bytes':CAP_BYTES,'minimum_free_bytes':MIN_FREE_BYTES}


def discover():
    return {'schema':'fireatlas-source-availability-v1','provider':'NASA FIRMS','retrieved_utc':utcnow(),
            'products':availability(), 'interpretation':'Provider availability only; does not establish compatible collection history or downloaded export completeness.'}


def plan(region,months,sources,discovery,*,window_days=5):
    if region not in REGIONS or not sources or any(s not in SOURCES for s in sources): raise ValueError('Supported fixed region and standard products required.')
    if not months or len(months)>12 or len(set(months))!=len(months): raise ValueError('Use 1–12 unique UTC months per bounded acquisition batch.')
    if type(window_days) is not int or window_days not in (1,5):raise ValueError('Exact one-day or five-day acquisition windows required.')
    if discovery.get('schema')!='fireatlas-source-availability-v1': raise ValueError('Current provider availability receipt required.')
    try: age=(datetime.now(timezone.utc)-datetime.fromisoformat(discovery['retrieved_utc'].replace('Z','+00:00'))).total_seconds()
    except (KeyError,ValueError,TypeError): raise ValueError('Invalid availability timestamp.') from None
    if not 0<=age<=86400: raise ValueError('Refresh provider availability before acquisition (maximum age 24 hours).')
    products={r['data_id']:r for r in discovery['products']};requests=[];unsupported=[]
    for month in sorted(months):
        first=date.fromisoformat(month+'-01');last=first.replace(day=monthrange(first.year,first.month)[1])
        if first.strftime('%Y-%m')!=month: raise ValueError('Canonical UTC month required.')
        for source in sorted(set(sources)):
            available=products.get(source)
            if not available or not available['min_date']<=first.isoformat() or available['max_date']<last.isoformat():
                unsupported.append({'month':month,'source':source,'reason':'full-month-standard-product-unavailable'});continue
            for offset in range(0,last.day,window_days):
                start=first+timedelta(days=offset);span=min(window_days,last.day-offset)
                material={'region':region,'bbox':list(REGIONS[region]['bbox']),'source':source,'start':start.isoformat(),'days':span}
                requests.append({**material,'id':digest(material)})
    result={'schema':'fireatlas-acquisition-plan-v1','provider':'NASA FIRMS','region':region,'requests':requests,
            'unavailable':unsupported,'availability':discovery,'request_byte_ceiling':WINDOW_LIMIT,'window_days':window_days,
            'volume_upper_bound_bytes':len(requests)*WINDOW_LIMIT*4,
            'volume_basis':'Enforced request ceilings plus 3x allowance for merged CSV, shadow database and receipts; not an asserted provider file size.'}
    result['plan_sha256']=digest(result)
    return result


def validate_csv(path,request):
    count=0;excluded_bbox=[];versions=set();start=date.fromisoformat(request['start']);end=start+timedelta(days=request['days']);w,s,e,n=request['bbox']
    with Path(path).open(newline='',encoding='utf-8-sig') as f:
        reader=csv.DictReader(f)
        if not REQUIRED_COLUMNS.issubset(reader.fieldnames or []): raise ValueError('Provider response is not a complete FIRMS CSV header.')
        fields=reader.fieldnames
        for line,row in enumerate(reader,2):
            day=date.fromisoformat(row['acq_date']);lon=float(row['longitude']);lat=float(row['latitude'])
            if not start<=day<end:raise ValueError('Provider row outside requested UTC window.')
            if not w<=lon<=e or not s<=lat<=n:
                # Preserve the original provider bytes. A small provider edge
                # overshoot is explicitly excluded from the exact study box;
                # larger departures still stop acquisition as a bad response.
                if not w-.00002<=lon<=e+.00002 or not s-.00002<=lat<=n+.00002:raise ValueError('Provider row outside requested region beyond declared edge margin.')
                excluded_bbox.append({'csv_line':line,'latitude':lat,'longitude':lon})
            if not isinstance(row.get('version'),str) or not row['version'].strip() or len(row['version'])>40: raise ValueError('Unknown or malformed provider product version.')
            versions.add(row['version']);count+=1
    result={'rows':count,'versions':sorted(versions),'fields':fields}
    if excluded_bbox:result.update(excluded_bbox_rows=excluded_bbox,in_scope_rows=count-len(excluded_bbox),bbox_rule='Exact requested bounds; provider rows within0.00002degree exterior margin retained in original bytes and explicitly excluded from imported study. Larger departures invalidate request.')
    return result


def receipt_valid(root,request):
    body=Path(root)/'requests'/(request['id']+'.csv');meta=body.with_suffix('.json')
    if not meta.exists() or not body.exists(): return False
    r=json.loads(meta.read_text())
    if r.get('request')!=request or r.get('complete') is not True or hashlib.sha256(body.read_bytes()).hexdigest()!=r.get('original_sha256'): raise ValueError('Stored acquisition receipt/hash is corrupt; do not silently reuse it.')
    parsed=validate_csv(body,request)
    if r.get('schema')!='fireatlas-acquisition-receipt-v1' or r.get('provider')!='NASA FIRMS' or r.get('bytes')!=body.stat().st_size or any(r.get(k)!=v for k,v in parsed.items()):
        raise ValueError('Stored receipt metadata does not reproduce original bytes.')
    if any(k in r and r[k]!=parsed.get(k) for k in ('excluded_bbox_rows','in_scope_rows','bbox_rule')):
        raise ValueError('Stored bounding-box exclusions do not reproduce original bytes.')
    expected_cohort={'source':request['source'],'observed_versions':parsed['versions'],'empty_export_version':'unknown' if not parsed['rows'] else None}
    if r.get('processing_cohort')!=expected_cohort:
        raise ValueError('Stored processing cohort does not reproduce original bytes.')
    return True


def acquire(root,acquisition_plan,*,opener=urlopen,delay=1.5,workers=1):
    if type(workers) is not int or workers not in (1,2):raise ValueError('Use one or two bounded acquisition workers.')
    root=Path(root)
    expected=dict(acquisition_plan);expected.pop('plan_sha256',None)
    if digest(expected)!=acquisition_plan.get('plan_sha256'): raise ValueError('Acquisition plan identity differs.')
    # Revalidate freshness and exact request material before making provider calls.
    replay=plan(acquisition_plan['region'],sorted({r['start'][:7] for r in acquisition_plan['requests']}),sorted({r['source'] for r in acquisition_plan['requests']}),acquisition_plan['availability'],window_days=acquisition_plan.get('window_days',5))
    if replay['requests']!=acquisition_plan['requests']: raise ValueError('Acquisition request plan differs.')
    remaining=[r for r in acquisition_plan['requests'] if not receipt_valid(root,r)]
    budget(root,len(remaining)*WINDOW_LIMIT*4)
    key=firms_key()
    if remaining and not key: raise ValueError('Owner-authenticated FIRMS access required.')
    root.mkdir(parents=True,exist_ok=True)
    # A process lock prevents competing campaigns from consuming the same budget.
    lock=root/'.acquisition.lock'
    import fcntl
    with lock.open('a') as guard:
        try: fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('Another campaign acquisition is active.') from None
        budget(root,sum(not receipt_valid(root,r) for r in acquisition_plan['requests'])*WINDOW_LIMIT*4)
        def http_failure(exc):
            retry=exc.headers.get('Retry-After') if exc.headers else None
            return ValueError(f'Provider HTTP {exc.code}; resume after provider recovery'+(f' (retry after {retry} seconds)' if retry and retry.isdigit() else ''))
        def download(request,before_open=None):
            if receipt_valid(root,request):return
            budget(root,WINDOW_LIMIT*4)
            directory=root/'requests';directory.mkdir(exist_ok=True);path=directory/(request['id']+'.csv');temp=path.with_suffix('.part')
            url='/'.join((BASE_URL,quote(key,safe=''),request['source'],','.join(map(str,request['bbox'])),str(request['days']),request['start']))
            try:
                if before_open is not None:before_open()
                try:
                    response=opener(url,timeout=30)
                except HTTPError as exc:
                    raise http_failure(exc) from None
                except (URLError,TimeoutError,OSError):
                    raise ValueError('Provider transport interrupted; request remains incomplete and can be resumed.') from None
                with response,temp.open('wb') as f:
                    if getattr(response,'status',200)!=200 or response.headers.get('Content-Range'):
                        raise ValueError('Partial provider response: request remains incomplete.')
                    length=response.headers.get('Content-Length')
                    if length and int(length)>WINDOW_LIMIT: raise ValueError('Provider file exceeds reserved request ceiling; request remains incomplete.')
                    total=0;sha=hashlib.sha256()
                    while True:
                        try:chunk=response.read(64*1024)
                        except HTTPError as exc:
                            raise http_failure(exc) from None
                        except (URLError,TimeoutError,OSError):
                            raise ValueError('Provider transport interrupted; request remains incomplete and can be resumed.') from None
                        if not chunk:break
                        total+=len(chunk)
                        if total>WINDOW_LIMIT: raise ValueError('Provider response exceeded bounded volume; request remains incomplete.')
                        budget(root,len(chunk));f.write(chunk);sha.update(chunk)
                    if length and total!=int(length):
                        raise ValueError('Interrupted provider response: byte length differs; request remains incomplete.')
                    f.flush();os.fsync(f.fileno())
                parsed=validate_csv(temp,request);temp.replace(path)
                atomic_json(path.with_suffix('.json'),{'schema':'fireatlas-acquisition-receipt-v1','request':request,'provider':'NASA FIRMS',
                    'retrieved_utc':utcnow(),'complete':True,'original_sha256':sha.hexdigest(),'bytes':total,**parsed,
                    'processing_cohort':{'source':request['source'],'observed_versions':parsed['versions'],'empty_export_version':'unknown' if not parsed['rows'] else None},
                    'coverage_basis':'provider-successful-exact-window-response; export completeness only; usable footprint unknown'})
            finally: temp.unlink(missing_ok=True)
        if workers==1:
            for request in acquisition_plan['requests']:
                if receipt_valid(root,request):continue
                download(request);time.sleep(max(1.5,delay))
        else:
            from concurrent.futures import ThreadPoolExecutor,as_completed
            from threading import Lock,Event
            rate_lock=Lock();cancel=Event();next_start=[0.]
            def rate_slot():
                with rate_lock:
                    if cancel.is_set():raise ValueError('Acquisition cancelled before provider request.')
                    wait=max(0.,next_start[0]-time.monotonic())
                    if wait:time.sleep(wait)
                    if cancel.is_set():raise ValueError('Acquisition cancelled before provider request.')
                    next_start[0]=time.monotonic()+max(3.,delay)
            def scheduled(request):
                if cancel.is_set():return
                try:download(request,before_open=rate_slot)
                except BaseException:
                    cancel.set();raise
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures=[pool.submit(scheduled,r) for r in acquisition_plan['requests']]
                for future in as_completed(futures):
                    try:future.result()
                    except BaseException:
                        cancel.set()
                        for other in futures:other.cancel()
                        break
            # Running workers have now completed. A later rate limit, disk
            # error or data failure must not be hidden by an earlier transport
            # failure and accidentally retried.
            failures=[]
            for future in futures:
                if future.cancelled():continue
                try:future.result()
                except BaseException as exc:
                    if str(exc)!='Acquisition cancelled before provider request.':failures.append(exc)
            if failures:
                retryable='Provider transport interrupted; request remains incomplete and can be resumed.'
                size_limits={'Provider file exceeds reserved request ceiling; request remains incomplete.',
                             'Provider response exceeded bounded volume; request remains incomplete.'}
                # A size error permits a smaller-window fallback, so it must
                # never mask any error that should stop further requests.
                def priority(exc):
                    if not isinstance(exc,ValueError):return 0
                    if str(exc)==retryable:return 2
                    if str(exc) in size_limits:return 1
                    return 0
                raise min(failures,key=priority)
            if not all(receipt_valid(root,r) for r in acquisition_plan['requests']):raise ValueError('Acquisition cancelled; incomplete requests remain resumable.')
        atomic_json(root/'plans'/(acquisition_plan['plan_sha256']+'.json'),acquisition_plan)
    return {'complete_requests':len(acquisition_plan['requests']),'storage':budget(root),'plan_sha256':acquisition_plan['plan_sha256']}


def import_month(root,acquisition_plan,source,month):
    """Atomic isolated import, with the same campaign lock and hard write budget."""
    import contextlib
    import fcntl
    root=Path(root);region=acquisition_plan['region']
    if region not in REGIONS or source not in SOURCES: raise ValueError('Unsupported import cohort.')
    first=date.fromisoformat(month+'-01');days=monthrange(first.year,first.month)[1]
    if first.strftime('%Y-%m')!=month: raise ValueError('Canonical UTC month required.')
    root.mkdir(parents=True,exist_ok=True)
    with (root/'.acquisition.lock').open('a') as guard:
        try: fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('Another campaign acquisition/import is active.') from None
        requests=[r for r in acquisition_plan['requests'] if r['source']==source and r['start'].startswith(month)]
        expected={first+timedelta(days=i) for i in range(days)};covered=set();receipts=[]
        for r in requests:
            if r['region']!=region or r['bbox']!=list(REGIONS[region]['bbox']) or r['id']!=digest({k:r[k] for k in ('region','bbox','source','start','days')}): raise ValueError('Request identity or fixed bounds differ.')
            if not receipt_valid(root,r): raise ValueError('Incomplete request: month not imported.')
            for i in range(r['days']):
                day=date.fromisoformat(r['start'])+timedelta(days=i)
                if day in covered: raise ValueError('Overlapping acquisition windows.')
                covered.add(day)
            receipts.append(json.loads((root/'requests'/(r['id']+'.json')).read_text()))
        if covered!=expected: raise ValueError('Every expected UTC date must be verified before import.')
        output=root/'months'/f'{region}-{source}-{month}.csv';output.parent.mkdir(exist_ok=True);temp=output.with_suffix('.part')
        receipt_identity=digest(receipts);versions=sorted({v for r in receipts for v in r['versions']})
        database=root/'observations.sqlite3'
        if output.exists() and database.exists():
            # Original window bytes were all checked above. A prior immutable
            # merged file and matching ledger can resume without rewriting it.
            with sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True) as previous:
                previous.row_factory=sqlite3.Row
                existing=previous.execute('''SELECT b.*,e.request_start,e.request_end,e.west,e.south,e.east,e.north,e.complete_export,e.coverage_basis,e.product_versions_json,e.request_sha256
                    FROM source_exports e JOIN batches b ON b.id=e.batch_id
                    WHERE e.region_id=? AND e.source_id=? AND e.month=? AND e.parent_sha256=?''',(region,source,month,receipt_identity)).fetchone()
                expected_window=json.dumps([month,REGIONS[region]['bbox'],region+receipt_identity])
                if existing and existing['demo']==0 and existing['source_id']==source and existing['window_key']==expected_window and existing['request_start']==first.isoformat() and existing['request_end']==first.replace(day=days).isoformat() and tuple(existing[k] for k in ('west','south','east','north'))==REGIONS[region]['bbox'] and existing['complete_export']==1 and existing['coverage_basis']=='request-metadata' and json.loads(existing['product_versions_json'])==versions and existing['request_sha256']==digest(requests) and hashlib.sha256(output.read_bytes()).hexdigest()==existing['file_sha256']:
                    excluded=previous.execute('SELECT count(*) FROM excluded_rows WHERE batch_id=?',(existing['id'],)).fetchone()[0]
                    budget(root)
                    return {'batch_id':existing['id'],'rows_read':existing['row_count'],'rows_inserted':0,'rows_excluded':excluded,'already_imported':True,'versions':versions,'empty_version_eligibility':'unknown unless independently documented','receipt_sha256':receipt_identity}
        budget(root,sum(r['bytes'] for r in receipts)*3+1_000_000)
        try:
            with temp.open('wb',buffering=0) as raw:
                class Writer:
                    reserved=0
                    def write(self,text):
                        body=text.encode('utf-8')
                        if len(body)>self.reserved:
                            # Reserve a bounded block before writing any byte;
                            # rescanning every campaign file for every CSV row
                            # makes long-record import needlessly quadratic.
                            self.reserved=max(65536,len(body));budget(root,self.reserved)
                        raw.write(body);self.reserved-=len(body);return len(text)
                writer=None
                for r in requests:
                    with (root/'requests'/(r['id']+'.csv')).open(newline='',encoding='utf-8-sig') as original:
                        reader=csv.DictReader(original)
                        if writer is None: writer=csv.DictWriter(Writer(),fieldnames=reader.fieldnames);writer.writeheader()
                        if reader.fieldnames!=writer.fieldnames: raise ValueError('Product fields changed across windows.')
                        w,s,e,n=REGIONS[region]['bbox']
                        for row in reader:
                            if w<=float(row['longitude'])<=e and s<=float(row['latitude'])<=n:writer.writerow(row)
                os.fsync(raw.fileno())
            temp.replace(output)
            # Reserve headroom for the journal and enforce SQLite's hard page
            # ceiling. Progress checks include journal/other campaign growth.
            state=budget(root,1_000_000)
            allowance=min(CAP_BYTES-state['used_bytes'],state['free_bytes']-MIN_FREE_BYTES)
            if allowance<1_000_000: raise ValueError('Insufficient import headroom.')
            with connect(root/'observations.sqlite3') as db:
                page_size=db.execute('PRAGMA page_size').fetchone()[0]
                current_pages=db.execute('PRAGMA page_count').fetchone()[0]
                db.execute(f'PRAGMA max_page_count={current_pages+int(allowance//(2*page_size))}')
                next_check=0.
                def check_budget():
                    nonlocal next_check
                    if time.monotonic()<next_check:return 0
                    next_check=time.monotonic()+.25
                    try: budget(root,65536);return 0
                    except ValueError:return 1
                db.set_progress_handler(check_budget,2000)
                db.execute('BEGIN IMMEDIATE')
                class TransactionProxy:
                    def execute(self,*a,**k):return db.execute(*a,**k)
                    def transaction(self):return contextlib.nullcontext()
                # ingest must not commit before the request ledger is installed.
                result=ingest(TransactionProxy(),output,source,source_uri='urn:fireatlas:qualification:'+receipt_identity,complete_month=month,bbox=REGIONS[region]['bbox'],batch_key=region+receipt_identity)
                db.execute('INSERT OR REPLACE INTO source_exports VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (result['batch_id'],region,source,month,first.isoformat(),first.replace(day=days).isoformat(),*REGIONS[region]['bbox'],1,'request-metadata',json.dumps(versions),receipt_identity,digest(requests)))
                budget(root,65536)
            budget(root)
            return {**result,'versions':versions,'empty_version_eligibility':'unknown unless independently documented','receipt_sha256':receipt_identity}
        finally: temp.unlink(missing_ok=True)
