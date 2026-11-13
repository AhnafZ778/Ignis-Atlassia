"""Bounded public NASA catalog discovery, separate from data acquisition.

Original pages can be retained by the caller; portable reports contain normalized
metadata, original response hashes and exact queries, not downloaded science.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
import hashlib
import html
import json
import math
import re
import time
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .contracts import digest

BASE='https://cmr.earthdata.nasa.gov/search/'
MAX_BYTES=512_000
MAX_REPORT_BYTES=19_000
SCOPE=('NASA catalog metadata only. No observation files were downloaded or analyzed. '
       'Granule intersection does not establish clear-sky pixel coverage, fire absence or causation. '
       'Listed variables are catalog metadata, not measured values; missing metadata remains unknown. '
       'Portable reports retain normalized metadata and original response hashes/links, not complete original pages.')


def check(cancel,deadline):
    if cancel is not None and cancel.is_set() or deadline is not None and time.monotonic()>deadline:
        raise InterruptedError('NASA discovery stopped.')


def concept(value,prefix='C'):
    if not isinstance(value,str) or not re.fullmatch(prefix+r'\d{1,20}-[A-Za-z0-9_]{1,60}',value):
        raise ValueError('Use an exact NASA catalog concept identifier.')
    return value


def plain(value,limit):
    return ' '.join(html.unescape(re.sub(r'<[^>]*>',' ',value if isinstance(value,str) else '')).split())[:limit]


def query_scope(topic,bbox,start,end,collection_id,variable_name=None):
    if not isinstance(topic,str) or len(topic)>200 or not topic.strip() and not collection_id:
        raise ValueError('Use a public NASA topic or exact collection identifier.')
    if collection_id:concept(collection_id)
    if variable_name is not None and (not collection_id or not isinstance(variable_name,str) or not 1<=len(variable_name)<=120 or variable_name.count('*')+variable_name.count('?')>4):
        raise ValueError('Use a bounded variable-name pattern only with an exact collection.')
    if bbox is not None:
        if not isinstance(bbox,list) or len(bbox)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in bbox):
            raise ValueError('Use west/south/east/north numeric bounds.')
        w,s,e,n=bbox
        if not -180<=w<e<=180 or not -90<=s<n<=90:raise ValueError('Use increasing non-antimeridian bounds.')
    if bool(start)!=bool(end):raise ValueError('Supply both inclusive UTC dates.')
    if start:
        first,last=date.fromisoformat(start),date.fromisoformat(end)
        if first.isoformat()!=start or last.isoformat()!=end or last<first or (last-first).days>1095:
            raise ValueError('Use canonical inclusive UTC dates covering at most three years.')
        # CMR includes query boundaries; granule results are separately checked
        # against the requested half-open UTC-day interval when dates exist.
        try:temporal=first.isoformat()+'T00:00:00Z,'+(last+timedelta(days=1)).isoformat()+'T00:00:00Z'
        except OverflowError:raise ValueError('The final UTC date is outside the supported calendar.') from None
    else:temporal=None
    return {'topic':topic.strip(),'bbox':bbox,'start':start,'end':end,'collection_id':collection_id,'variable_name':variable_name},temporal


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def fetch(path,*,cancel=None,deadline=None):
    """Fixed-origin request, no auth, no redirects, bounded reads and deadline."""
    check(cancel,deadline)
    timeout=min(12,max(.1,deadline-time.monotonic())) if deadline is not None else 12
    with build_opener(NoRedirect()).open(Request(BASE+path,headers={'Accept':'application/json','User-Agent':'FireAtlas/1.0 (public NASA catalog discovery)'}),timeout=timeout) as response:
        pieces=[];size=0
        while True:
            check(cancel,deadline)
            chunk=response.read(min(65536,MAX_BYTES+1-size))
            if not chunk:break
            pieces.append(chunk);size+=len(chunk)
            if size>MAX_BYTES:raise ValueError('NASA catalog response exceeds the reading bound.')
        hits=response.headers.get('CMR-Hits')
    check(cancel,deadline)
    return b''.join(pieces),int(hits) if isinstance(hits,str) and hits.isdigit() else None


def empty(state='not_requested'):
    return {'state':state,'reported_hits':None,'listing_complete':None,'items':[]}


def timestamp(value):
    if not isinstance(value,str):return None
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        return parsed if parsed.utcoffset() is not None and parsed.utcoffset().total_seconds()==0 else None
    except ValueError:return None


def discover(topic='',*,bbox=None,start=None,end=None,collection_id=None,variable_name=None,cancel=None,deadline=None,retain=None):
    query,temporal=query_scope(topic,bbox,start,end,collection_id,variable_name)
    if collection_id and (not bbox or not start):raise ValueError('Inspect a collection with explicit region bounds and UTC dates.')
    report={'schema':'fireatlas-nasa-discovery-v1','query':query,'retrieved_at':datetime.now(timezone.utc).isoformat(),
            'collections':empty(),'granules':empty(),'variables':empty(),'pages':[],
            'download_access':'not_checked','geography':None,'scope':SCOPE}

    def page(kind,path,params,limit,umm=False):
        check(cancel,deadline)
        suffix=path+'?'+urlencode(params,doseq=True)
        raw,hits=fetch(suffix,cancel=cancel,deadline=deadline)
        if len(raw)>MAX_BYTES:raise ValueError('NASA response exceeds bound.')
        meta={'kind':kind,'url':BASE+suffix,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        if retain:retain(raw,meta)
        data=json.loads(raw)
        items=data['items'] if umm else data['feed']['entry']
        total=data.get('hits',hits) if umm else hits
        if total is not None and (type(total) is not int or total<0):raise ValueError('Invalid NASA catalog hit count.')
        if not isinstance(items,list) or len(items)>limit or any(not isinstance(item,dict) for item in items) or total is not None and total<len(items):
            raise ValueError('Invalid bounded NASA catalog page.')
        report['pages'].append(meta)
        return items,total

    params={'page_size':1 if collection_id else 3}
    if collection_id:params['concept_id']=collection_id
    else:
        params['keyword']=query['topic']
        if bbox:params['bounding_box']=','.join(map(str,bbox))
        if temporal:params['temporal']=temporal
    try:
        entries,hits=page('collections','collections.json',params,params['page_size'])
        selected=[];ids=set()
        for entry in entries:
            identifier=concept(entry.get('id'))
            if identifier in ids or collection_id and identifier!=collection_id:raise ValueError('NASA collection identity differs.')
            ids.add(identifier)
            title=plain(entry.get('title') or entry.get('dataset_id'),220)
            if not title:raise ValueError('NASA collection title is missing.')
            selected.append({'concept_id':identifier,'title':title,'short_name':plain(entry.get('short_name'),80) or None,
                'version':plain(entry.get('version_id'),40) or None,'start':plain(entry.get('time_start'),80) or None,
                'end':plain(entry.get('time_end'),80) or None,'summary':plain(entry.get('summary'),400),
                'url':BASE+'concepts/'+identifier+'.html','reference_id':None})
        report['collections']={'state':'returned','reported_hits':hits,'listing_complete':hits==len(selected) if hits is not None else None,'items':selected}
    except (OSError,ValueError,KeyError,TypeError,AttributeError,RecursionError):
        report['collections']=empty('unavailable')
        check(cancel,deadline)
        return finish(report)
    if not collection_id or not entries:
        check(cancel,deadline)
        return finish(report)

    try:
        params={'collection_concept_id':collection_id,'bounding_box':','.join(map(str,bbox)),'temporal':temporal,'page_size':5,'sort_key[]':['start_date','producer_granule_id']}
        granules,hits=page('granules','granules.json',params,5)
        selected=[];ids=set();omitted=False
        first=datetime.combine(date.fromisoformat(start),datetime.min.time(),timezone.utc)
        last=datetime.combine(date.fromisoformat(end)+timedelta(days=1),datetime.min.time(),timezone.utc)
        for entry in granules:
            identifier=concept(entry.get('id'),'G')
            parent=entry.get('collection_concept_id')
            if identifier in ids or parent is not None and parent!=collection_id:raise ValueError('NASA granule identity differs.')
            ids.add(identifier)
            lo,hi=timestamp(entry.get('time_start')),timestamp(entry.get('time_end'))
            if lo is not None and lo>=last or hi is not None and hi<first:omitted=True;continue
            selected.append({'concept_id':identifier,'title':plain(entry.get('title') or entry.get('producer_granule_id'),220),
                'start':plain(entry.get('time_start'),80) or None,'end':plain(entry.get('time_end'),80) or None,
                'url':BASE+'concepts/'+identifier+'.umm_json','temporal_scope_checked':lo is not None and hi is not None})
        report['granules']={'state':'returned','reported_hits':hits,'listing_complete':False if omitted else hits==len(selected) if hits is not None else None,'items':selected}
    except (OSError,ValueError,KeyError,TypeError,AttributeError,RecursionError):report['granules']=empty('unavailable')

    try:
        associations=entries[0].get('associations',{})
        associated=associations.get('variables') if isinstance(associations,dict) else None
        exact=isinstance(associated,list) and all(isinstance(v,str) and re.fullmatch(r'V\d{1,20}-[A-Za-z0-9_]{1,60}',v) for v in associated)
        if exact and not associated:
            report['variables']={'state':'returned','reported_hits':0,'listing_complete':True,'items':[]}
        else:
            params={'page_size':8}
            if exact and not variable_name:params['concept_id[]']=associated[:8]
            else:
                params['keyword']=collection_id
                if variable_name:params.update({'name':variable_name,'options[name][pattern]':'true'})
            variables,hits=page('variables','variables.umm_json_v1_1',params,8,umm=True)
            selected=[];ids=set()
            for entry in variables:
                meta,umm=entry['meta'],entry['umm'];identifier=concept(meta.get('concept-id'),'V')
                linked=[v.get('concept-id') if isinstance(v,dict) else v for v in entry.get('associations',{}).get('collections',[])]
                if identifier in ids:raise ValueError('Duplicate NASA variable.')
                ids.add(identifier)
                if exact and identifier not in (associated if variable_name else associated[:8]):raise ValueError('NASA variable identity differs.')
                if not exact and collection_id not in linked:continue
                selected.append({'concept_id':identifier,'name':plain(umm.get('Name'),160),'long_name':plain(umm.get('LongName'),220) or None,
                    'units':plain(umm.get('Units'),80) or None,'definition':plain(umm.get('Definition'),220),
                    'association_basis':'collection_metadata' if exact else 'variable_metadata','url':BASE+'concepts/'+identifier+'.umm_json'})
            complete=bool(exact and len(associated)<=8 and set(associated)==ids)
            report['variables']={'state':'returned','reported_hits':hits,'listing_complete':complete,'items':selected}
    except (OSError,ValueError,KeyError,TypeError,AttributeError,RecursionError):report['variables']=empty('unavailable')
    check(cancel,deadline)
    return finish(report)


def finish(report):
    report['sha256']=digest({k:v for k,v in report.items() if k!='sha256'})
    if len(json.dumps(report,allow_nan=False).encode())>MAX_REPORT_BYTES:raise ValueError('NASA discovery report exceeds its portable bound.')
    return report


def source_cards(report):
    """Only collection links become citations; granules/variables stay metadata."""
    detail=''
    if report['query']['collection_id']:
        g,v=report['granules'],report['variables']
        detail=(' Granules: '+(str(len(g['items']))+' candidates listed (bounded)' if g['state']=='returned' else g['state'])+'.'
                +' Variable names: '+(', '.join(item['name'][:55] for item in v['items'][:3])+' (bounded)' if v['items'] else v['state'])+'.')
    return [{'title':item['title'],'url':item['url'],'provider':'NASA Earthdata CMR',
             'snippet':('Catalog metadata only; files/access not checked. '+(item['short_name'] or item['concept_id'])+' · version '+(item['version'] or 'unknown')+'.'+detail)[:340]}
            for item in report['collections']['items']]


def validate_reports(reports,sources):
    """Portable integrity/shape checks are not provider or scientific approval."""
    if not isinstance(reports,list) or len(reports)>3:raise ValueError('Invalid NASA reports.')
    known={s.get('id'):s for s in sources if isinstance(s,dict) and isinstance(s.get('id'),str)}
    top={'schema','query','retrieved_at','collections','granules','variables','pages','download_access','geography','scope','sha256'}
    fields={'collections':{'concept_id','title','short_name','version','start','end','summary','url','reference_id'},
            'granules':{'concept_id','title','start','end','url','temporal_scope_checked'},
            'variables':{'concept_id','name','long_name','units','definition','association_basis','url'}}
    for report in reports:
        if not isinstance(report,dict) or set(report)!=top or report['schema']!='fireatlas-nasa-discovery-v1' or report['download_access']!='not_checked' or report['scope']!=SCOPE:
            raise ValueError('Invalid NASA discovery receipt.')
        if len(json.dumps(report,allow_nan=False).encode())>MAX_REPORT_BYTES or timestamp(report['retrieved_at']) is None:raise ValueError('Invalid NASA reading scope.')
        query=report['query']
        if not isinstance(query,dict) or set(query)!={'topic','bbox','start','end','collection_id','variable_name'}:raise ValueError('Invalid NASA query.')
        query_scope(query['topic'],query['bbox'],query['start'],query['end'],query['collection_id'],query['variable_name'])
        geography=report['geography']
        if geography is not None:
            if not isinstance(geography,dict) or set(geography)!={'label','source','url'} or any(not isinstance(v,str) or len(v)>1800 for v in geography.values()):raise ValueError('Invalid NASA geography provenance.')
            link=urlsplit(geography['url'])
            if link.scheme!='https' or not link.hostname or link.username or link.password or link.query or link.fragment:raise ValueError('Invalid NASA geographic reference.')
        if query['collection_id'] and (not query['bbox'] or not query['start']):raise ValueError('Invalid NASA inspection scope.')
        for kind,limit,prefix in (('collections',3,'C'),('granules',5,'G'),('variables',8,'V')):
            part=report[kind]
            if not isinstance(part,dict) or set(part)!={'state','reported_hits','listing_complete','items'} or part['state'] not in {'returned','unavailable','not_requested'}:raise ValueError('Invalid NASA result state.')
            if part['reported_hits'] is not None and (type(part['reported_hits']) is not int or part['reported_hits']<0):raise ValueError('Invalid NASA catalog count.')
            if part['listing_complete'] is not None and type(part['listing_complete']) is not bool:raise ValueError('Invalid NASA listing scope.')
            items=part['items']
            if not isinstance(items,list) or len(items)>limit or part['state']!='returned' and (items or part['reported_hits'] is not None or part['listing_complete'] is not None):raise ValueError('Invalid NASA result list.')
            if part['reported_hits'] is not None and part['reported_hits']<len(items) or part['listing_complete'] is True and part['reported_hits']!=len(items):raise ValueError('Invalid NASA listing completeness.')
            seen=set()
            for item in items:
                if not isinstance(item,dict) or set(item)!=fields[kind]:raise ValueError('Invalid NASA metadata record.')
                identifier=concept(item['concept_id'],prefix)
                if identifier in seen:raise ValueError('Duplicate NASA metadata identity.')
                seen.add(identifier)
                if item['url']!=BASE+'concepts/'+identifier+('.html' if prefix=='C' else '.umm_json'):raise ValueError('Invalid NASA metadata link.')
                for key,value in item.items():
                    if key not in {'reference_id','temporal_scope_checked'} and value is not None and (not isinstance(value,str) or len(value)>500):raise ValueError('Invalid NASA metadata text.')
                if prefix=='C':
                    if query['collection_id'] and identifier!=query['collection_id']:raise ValueError('NASA collection identity differs.')
                    rid=item['reference_id']
                    if rid is not None and (not isinstance(rid,str) or rid not in known or known[rid]['url']!=item['url'] or known[rid]['title']!=item['title']):raise ValueError('NASA reference identity differs.')
                elif prefix=='G' and type(item['temporal_scope_checked']) is not bool:raise ValueError('Invalid NASA temporal state.')
                elif prefix=='V' and item['association_basis'] not in {'collection_metadata','variable_metadata'}:raise ValueError('Invalid NASA variable association.')
            if not query['collection_id'] and kind!='collections' and part['state']!='not_requested':raise ValueError('NASA child listing has no collection.')
        pages=report['pages']
        if not isinstance(pages,list) or len(pages)>3:raise ValueError('Invalid NASA page receipts.')
        kinds=set()
        for page in pages:
            if not isinstance(page,dict) or set(page)!={'kind','url','bytes','sha256'} or page['kind'] not in fields or not isinstance(page['url'],str) or not page['url'].startswith(BASE+{'collections':'collections.json?','granules':'granules.json?','variables':'variables.umm_json_v1_1?'}[page['kind']]) or len(page['url'])>2500:
                raise ValueError('Invalid NASA original page.')
            if type(page['bytes']) is not int or not 0<=page['bytes']<=MAX_BYTES or not isinstance(page['sha256'],str) or not re.fullmatch(r'[0-9a-f]{64}',page['sha256']):raise ValueError('Invalid NASA original response identity.')
            kind=page['kind'];link=urlsplit(page['url']);params=parse_qs(link.query,keep_blank_values=True)
            if kind in kinds or link.fragment:raise ValueError('Invalid NASA original query.')
            kinds.add(kind)
            _,temporal=query_scope(query['topic'],query['bbox'],query['start'],query['end'],query['collection_id'],query['variable_name'])
            bounds=','.join(map(str,query['bbox'])) if query['bbox'] else None
            if kind=='collections':
                expected={'page_size':['1'],'concept_id':[query['collection_id']]} if query['collection_id'] else {'page_size':['3'],'keyword':[query['topic']]}
                if not query['collection_id']:
                    if bounds:expected['bounding_box']=[bounds]
                    if temporal:expected['temporal']=[temporal]
            elif kind=='granules':
                expected={'page_size':['5'],'collection_concept_id':[query['collection_id']],'bounding_box':[bounds],'temporal':[temporal],'sort_key[]':['start_date','producer_granule_id']}
            else:
                expected={'page_size':['8']}
                if 'concept_id[]' in params:
                    identifiers=params['concept_id[]']
                    if query['variable_name'] or not 1<=len(identifiers)<=8 or len(set(identifiers))!=len(identifiers):raise ValueError('Invalid NASA variable query.')
                    for identifier in identifiers:concept(identifier,'V')
                    expected['concept_id[]']=identifiers
                    if any(item['concept_id'] not in identifiers for item in report['variables']['items']):raise ValueError('NASA variable query identity differs.')
                else:
                    expected['keyword']=[query['collection_id']]
                    if query['variable_name']:expected.update({'name':[query['variable_name']],'options[name][pattern]':['true']})
            if params!=expected:raise ValueError('NASA original query differs from its scope.')
        for kind in fields:
            if report[kind]['items'] and kind not in kinds:raise ValueError('NASA metadata has no original page identity.')
        if report['sha256']!=digest({k:v for k,v in report.items() if k!='sha256'}):raise ValueError('NASA report digest differs.')
