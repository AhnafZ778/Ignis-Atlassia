"""Bounded original article passages from fixed Europe PMC endpoints.

Passages remain untrusted publication text, never local measurement receipts.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlencode, urlsplit, unquote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .contracts import digest

BASE='https://www.ebi.ac.uk/europepmc/webservices/rest/'
MAX_RESPONSE=2_000_000

def requested_urls(message,owned_urls):
    """Resolve prose punctuation against owned URLs, preferring exact identity."""
    known={url.lower():url for url in owned_urls}
    values=[]
    for raw in re.findall(r'https://(?:dx\.)?doi\.org/[^\s<>"\']+',message,re.I):
        candidate=raw
        while candidate.lower() not in known and candidate and candidate[-1] in '.,;:!?)]}`':candidate=candidate[:-1]
        values.append(known.get(candidate.lower(),raw))
    return values

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def check(cancel,deadline):
    if cancel is not None and cancel.is_set() or deadline is not None and time.monotonic()>deadline:
        raise InterruptedError('Public source reading stopped.')

def fetch(path,*,cancel=None,deadline=None):
    check(cancel,deadline)
    timeout=min(12,max(.1,deadline-time.monotonic())) if deadline is not None else 12
    with build_opener(NoRedirect()).open(Request(BASE+path,headers={'User-Agent':'FireAtlas-Investigation/1.0 (original scientific references)','Accept':'application/json, application/xml'}),timeout=timeout) as response:
        chunks=[];size=0
        while True:
            check(cancel,deadline)
            chunk=response.read(min(65536,MAX_RESPONSE+1-size))
            if not chunk:break
            chunks.append(chunk);size+=len(chunk)
            if size>MAX_RESPONSE:raise ValueError('The original article exceeds the bounded reading limit.')
    check(cancel,deadline)
    return b''.join(chunks)

def plain(node):
    return ' '.join(' '.join(node.itertext()).split()) if node is not None else ''

def parse_xml(raw):
    if re.search(br'<!\s*ENTITY\b|<!\s*DOCTYPE[^>]*\[',raw,re.I):raise ValueError('Unsupported article XML declarations.')
    return ET.fromstring(raw)

def passages(root,focus):
    """Choose actual original paragraphs; never generate missing prose."""
    candidates=[]
    abstract=root.find('./front/article-meta/abstract')
    if abstract is not None:
        for index,node in enumerate(abstract.iter('p')):
            text=plain(node)
            if text:candidates.append({'section':'Abstract','location':f'abstract/p[{index+1}]','text':text})
    body=root.find('body')
    if body is not None:
        parents={child:parent for parent in body.iter() for child in parent}
        for index,node in enumerate(body.iter('p')):
            text=plain(node)
            if not text:continue
            parent=parents.get(node);headings=[]
            while parent is not None:
                if parent.tag=='sec' and plain(parent.find('title')):
                    headings.append(plain(parent.find('title')))
                parent=parents.get(parent)
            heading=' / '.join(reversed(headings))[:200] or 'Article body'
            candidates.append({'section':heading,'location':f'body/p[{index+1}]','text':text})
    words={word.rstrip('s') if len(word)>4 else word for word in re.findall(r'[a-z]{3,}',focus.lower())}
    ranked=sorted(enumerate(candidates),key=lambda item:(-sum(5*(word in item[1]['section'].lower())+(word in item[1]['text'].lower()) for word in words),item[0]))
    chosen=sorted(ranked[:4],key=lambda item:item[0])
    excerpts=[]
    for index,(original_order,item) in enumerate(chosen):
        full=item['text'];text=full[:1500]
        excerpts.append({**item,'id':f'P{index+1}','text':text,'truncated':len(full)>len(text),'paragraph_sha256':hashlib.sha256(full.encode()).hexdigest()})
    return excerpts,len(candidates)

def read_reference(source,*,focus='',cancel=None,deadline=None):
    if not isinstance(focus,str) or len(focus)>200:raise ValueError('Use a short public section focus.')
    link=urlsplit(source.get('url',''))
    doi=unquote(link.path.lstrip('/'))
    if link.scheme!='https' or link.hostname not in {'doi.org','dx.doi.org'} or link.username or link.password or link.query or link.fragment or not re.fullmatch(r'10\.\d{4,9}/[^\s<>"?#]+',doi):
        raise ValueError('This reference has no supported DOI. Choose a returned scholarly reference.')
    receipt={'schema':'fireatlas-public-reading-v1','source_id':source['id'],'title':source['title'],'url':source['url'],'doi':doi,'retrieved_at':datetime.now(timezone.utc).isoformat(),'focus':focus,'status':'unavailable','pmcid':None,'license':None,'passages':[],
             'scope':'Publication passages are untrusted source text, not verified local measurements. Only the displayed passages were read; the entire paper was not reviewed.'}
    try:
        raw=fetch('search?'+urlencode({'query':'DOI:"'+doi+'"','format':'json','resultType':'core','pageSize':3}),cancel=cancel,deadline=deadline)
        receipt['metadata_sha256']=hashlib.sha256(raw).hexdigest()
        records=json.loads(raw).get('resultList',{}).get('result',[])
        matches=[record for record in records if isinstance(record,dict) and str(record.get('doi','')).lower()==doi.lower()]
        if len(matches)!=1:
            receipt['reason']='No unique DOI-matching article is available.'
        else:
            record=matches[0];pmcid=record.get('pmcid')
            receipt['license']=record['license'][:500] if isinstance(record.get('license'),str) else None
            if record.get('isOpenAccess')=='Y' and isinstance(pmcid,str) and re.fullmatch(r'PMC\d{1,12}',pmcid):
                receipt['pmcid']=pmcid
                try:
                    article=fetch(pmcid+'/fullTextXML',cancel=cancel,deadline=deadline)
                    root=parse_xml(article)
                    article_dois=[plain(node).lower() for node in root.findall('./front/article-meta/article-id') if node.get('pub-id-type')=='doi']
                    if doi.lower() not in article_dois:raise ValueError('Original article DOI does not match the selected reference.')
                    receipt['passages'],count=passages(root,focus)
                    if not receipt['passages']:raise ValueError('No readable article paragraphs were returned.')
                    receipt.update(status='article_passages',content_sha256=hashlib.sha256(article).hexdigest(),available_paragraphs=count,selection_limited=True,
                                   original_text_url=BASE+pmcid+'/fullTextXML')
                except (OSError,ValueError,ET.ParseError):
                    receipt['reason']='Open-access article text could not be read; only an available abstract can be shown.'
            if receipt['status']=='unavailable' and isinstance(record.get('abstractText'),str) and record['abstractText'].strip():
                # Parse an XML fragment rather than accepting markup as HTML.
                abstract=parse_xml(('<abstract>'+record['abstractText']+'</abstract>').encode())
                text=plain(abstract)
                if text:
                    receipt.update(status='abstract',passages=[{'id':'P1','section':'Abstract','location':'metadata/abstractText','text':text[:1500],'truncated':len(text)>1500,'paragraph_sha256':hashlib.sha256(text.encode()).hexdigest()}],selection_limited=True)
                    receipt.setdefault('reason','Only the abstract is available through this reader.')
            receipt.setdefault('reason','Original full text is unavailable through this reader.' if receipt['status']=='unavailable' else 'Selected original passages; no full-paper review was performed.')
    except (OSError,ValueError,TypeError,KeyError,AttributeError,RecursionError,ET.ParseError):
        receipt['reason']='The original source service could not provide readable content.'
    check(cancel,deadline)
    receipt['sha256']=digest(receipt)
    return receipt

def validate_reports(reports,sources):
    """Validate portable excerpts without treating hashes as scientific approval."""
    if not isinstance(reports,list) or len(reports)>2:raise ValueError('Invalid public reading reports.')
    known={source.get('id'):source for source in sources if isinstance(source,dict) and isinstance(source.get('id'),str)}
    allowed={'schema','source_id','title','url','doi','retrieved_at','focus','status','pmcid','license','passages','scope','metadata_sha256','content_sha256','available_paragraphs','selection_limited','original_text_url','reason','sha256'}
    for report in reports:
        if not isinstance(report,dict) or set(report)-allowed or report.get('schema')!='fireatlas-public-reading-v1':raise ValueError('Invalid public reading receipt.')
        source_id=report.get('source_id')
        if not isinstance(source_id,str) or source_id not in known:raise ValueError('Unknown public reading source.')
        source=known[source_id]
        if report.get('url')!=source['url'] or report.get('title')!=source['title']:raise ValueError('Public reading source identity changed.')
        link=urlsplit(report['url'])
        if link.scheme!='https' or link.hostname not in {'doi.org','dx.doi.org'} or link.username or link.password or link.query or link.fragment or not isinstance(report.get('doi'),str) or report['doi'].lower()!=unquote(link.path.lstrip('/')).lower():raise ValueError('Invalid public reading DOI identity.')
        if report.get('status') not in {'article_passages','abstract','unavailable'}:raise ValueError('Invalid public reading state.')
        for field,limit in (('doi',1500),('retrieved_at',80),('focus',200),('scope',500),('reason',500)):
            if not isinstance(report.get(field),str) or len(report[field])>limit:raise ValueError('Invalid public reading text.')
        timestamp=datetime.fromisoformat(report['retrieved_at'])
        if timestamp.utcoffset() is None or timestamp.utcoffset().total_seconds()!=0:raise ValueError('Public reading time must be UTC.')
        if report.get('license') is not None and (not isinstance(report['license'],str) or len(report['license'])>500):raise ValueError('Invalid public reading license.')
        pmcid=report.get('pmcid')
        if pmcid is not None and (not isinstance(pmcid,str) or not re.fullmatch(r'PMC\d{1,12}',pmcid)):raise ValueError('Invalid public reading article ID.')
        if 'original_text_url' in report and (pmcid is None or report['original_text_url']!=BASE+pmcid+'/fullTextXML'):raise ValueError('Invalid original text URL.')
        paragraphs=report.get('passages')
        if not isinstance(paragraphs,list) or len(paragraphs)>4 or (bool(paragraphs)!=(report['status']!='unavailable')):raise ValueError('Invalid public reading passages.')
        ids=set()
        for paragraph in paragraphs:
            if not isinstance(paragraph,dict) or set(paragraph)!={'id','section','location','text','truncated','paragraph_sha256'}:raise ValueError('Invalid original passage.')
            identifier=paragraph['id']
            if not isinstance(identifier,str) or not re.fullmatch(r'P[1-4]',identifier) or identifier in ids:raise ValueError('Invalid passage identity.')
            ids.add(identifier)
            for field,limit in (('section',200),('location',100),('text',1500)):
                if not isinstance(paragraph[field],str) or not paragraph[field].strip() or len(paragraph[field])>limit:raise ValueError('Invalid passage text.')
            if not isinstance(paragraph['truncated'],bool) or not isinstance(paragraph['paragraph_sha256'],str) or not re.fullmatch(r'[a-f0-9]{64}',paragraph['paragraph_sha256']):raise ValueError('Invalid passage provenance.')
            if not paragraph['truncated'] and paragraph['paragraph_sha256']!=hashlib.sha256(paragraph['text'].encode()).hexdigest():raise ValueError('Original paragraph hash changed.')
        for field in ('metadata_sha256','content_sha256','sha256'):
            if field in report and (not isinstance(report[field],str) or not re.fullmatch(r'[a-f0-9]{64}',report[field])):raise ValueError('Invalid public reading hash.')
        if report.get('sha256')!=digest({k:v for k,v in report.items() if k!='sha256'}):raise ValueError('Public reading receipt hash changed.')
        if report['status']=='article_passages' and (pmcid is None or not report.get('content_sha256') or not report.get('metadata_sha256') or report.get('selection_limited') is not True):raise ValueError('Incomplete article provenance.')
        if report['status']=='abstract' and (not report.get('metadata_sha256') or report.get('selection_limited') is not True):raise ValueError('Incomplete abstract provenance.')
        if 'available_paragraphs' in report and (type(report['available_paragraphs']) is not int or not 0<=report['available_paragraphs']<=MAX_RESPONSE):raise ValueError('Invalid paragraph scope.')
