"""Public reference retrieval for the local Investigation assistant."""
from concurrent.futures import ThreadPoolExecutor
import html
import json
import os
import re
from urllib.parse import urlencode, urlsplit, quote, unquote
from urllib.request import Request, urlopen


def register_sources(catalog,sources):
    """Keep stable handles and a shared portable twelve-reference ceiling."""
    for source in sources:
        if source['url'] in {item['url'] for item in catalog}:continue
        if len(catalog)>=12:continue
        number=1
        while f'R{number}' in {item['id'] for item in catalog}:number+=1
        catalog.append({**source,'id':f'R{number}'})
    return any(source['url'] not in {item['url'] for item in catalog} for source in sources)


def research_wording(text, sources, cited_ids):
    """Ignore actual citation/product identifiers, never their numbers alone.

    This is a narrow numeric-wording aid, not verification of semantic truth.
    """
    known={source.get('id'):source for source in sources if isinstance(source.get('id'),str)}
    wording=text
    for identifier in cited_ids:
        if identifier in known:
            wording=re.sub(r'\b'+re.escape(identifier)+r'\b','reference',wording)
    platforms={m.group(0) for source in sources for m in re.finditer(r'\b(?:Sentinel-[1-6][A-D]?|Landsat\s+[1-9])\b',source.get('title',''),re.I)}
    for platform in platforms:
        wording=re.sub(r'\b'+re.escape(platform)+r'\b','satellite platform',wording,flags=re.I)
    resolutions={m.group(1) for source in sources for pattern in (r'\bVIIRS\s+(\d+)\s*m\b',r'\b(\d+)\s*m\s+VIIRS\b') for m in re.finditer(pattern,source.get('title',''),re.I)}
    for resolution in resolutions:
        wording=re.sub(r'\bVIIRS(?:[’\']s)?\s+'+re.escape(resolution)+r'\s*m\b','VIIRS product',wording,flags=re.I)
        wording=re.sub(r'\b'+re.escape(resolution)+r'\s*m\s+VIIRS\b','VIIRS product',wording,flags=re.I)
    return wording


def requested_query(message):
    text=' '.join(message.split())
    if re.search(r'\b(?:attached|uploaded|saved|selected)\s+(?:pdf|document|table|sources?|board)\b',text,re.I) and not re.search(r'\b(?:web|internet|online)\b',text,re.I):return None
    prefix=(r'^(?:please\s+)?(?:(?:can|could|would) you\s+)?'
            r'(?:search(?:\s+(?:the\s+)?(?:web|internet|online))?\s+for|'
            r'(?:look up|google)|(?:find|show me)\s+(?:research\s+)?'
            r'(?:sources|papers|studies|articles|references)\s+(?:on|for|about))\s+')
    match=re.match(prefix,text,re.I)
    if not match:
        return None
    if re.fullmatch(r'search\s+for\s*',match[0],re.I):
        return None
    query=re.sub(r'\s+(?:and|then)\s+(?:pin|add|put)\b.*$','',text[match.end():],flags=re.I)
    return re.sub(r'\s+(?:on the web|on the internet|online)$','',query.rstrip('.!?'),flags=re.I).strip()[:300]



def _get_json(url, *, body=None, token=None):
    headers={'Accept':'application/json','User-Agent':'FireAtlas-Investigation/1.0 (public reference search)'}
    if body is not None:
        headers['Content-Type']='application/json'
    if token:
        headers['Authorization']='Bearer '+token
    with urlopen(Request(url, data=body, headers=headers), timeout=10) as response:
        return json.loads(response.read(1_000_000))


def _plain(value, limit):
    return ' '.join(html.unescape(re.sub(r'<[^>]+>',' ',str(value or ''))).split())[:limit]


def _source(title, url, description, provider):
    if not isinstance(url,str) or len(url)>1500:
        return None
    link=urlsplit(url)
    title=_plain(title,220)
    if link.scheme!='https' or not link.hostname or link.username or link.password or not title:
        return None
    return {'title':title,'url':url,'snippet':_plain(description,340),'provider':provider}


def _crossref(query):
    requested=re.sub(r'^https?://(?:dx\.)?doi\.org/','',query.strip(),flags=re.I)
    requested=unquote(requested)
    exact=bool(re.fullmatch(r'10\.\d{4,9}/[^\s<>"?#]+',requested))
    if exact:
        item=_get_json('https://api.crossref.org/works/'+quote(requested,safe=''))['message']
        if str(item.get('DOI','')).lower()!=requested.lower():raise ValueError('DOI lookup returned a different reference.')
        items=[item]
    else:
        params=urlencode({'query.bibliographic':query,'rows':4,'select':'title,DOI,container-title,published'})
        items=_get_json('https://api.crossref.org/works?'+params)['message']['items']
    results=[]
    for item in items:
        doi=item.get('DOI','')
        if not re.fullmatch(r'10\.\d{4,9}/[^\s<>"?#]+',doi):
            continue
        journal=next(iter(item.get('container-title') or []),'')
        year=(item.get('published',{}).get('date-parts') or [[]])[0]
        detail=' · '.join(filter(None,(journal,str(year[0]) if year else '','DOI '+doi)))
        results.append(_source(next(iter(item.get('title') or []),''),'https://doi.org/'+doi,detail,'Crossref'))
    return results


def _wikipedia(query):
    params=urlencode({'action':'query','list':'search','srsearch':query,'srlimit':4,'format':'json','srnamespace':0})
    results=[]
    for item in _get_json('https://en.wikipedia.org/w/api.php?'+params)['query']['search']:
        page=item.get('pageid')
        if type(page) is int and page>0:
            results.append(_source(item.get('title'),f'https://en.wikipedia.org/?curid={page}',item.get('snippet'),'Wikipedia'))
    return results


def _ollama(query, token):
    payload=json.dumps({'query':query,'max_results':5}).encode()
    return [_source(item.get('title'),item.get('url'),item.get('content'),'Ollama Web Search')
            for item in _get_json('https://ollama.com/api/web_search',body=payload,token=token)['results']]


def _nasa(query):
    """Public collection discovery, not acquisition of scientific granules."""
    params=urlencode({'keyword':query,'page_size':3})
    results=[]
    for item in _get_json('https://cmr.earthdata.nasa.gov/search/collections.json?'+params)['feed']['entry']:
        concept=item.get('id','')
        if not re.fullmatch(r'C\d+-[A-Za-z0-9_]+',concept):continue
        results.append(_source(item.get('title') or item.get('dataset_id'),
            'https://cmr.earthdata.nasa.gov/search/concepts/'+concept+'.html',item.get('summary'),'NASA Earthdata CMR'))
    return results


def search_references(query, *, scholarly=False, cancel=None, deadline=None, provider_status=None):
    """Search fixed public endpoints and return plain linked metadata, never executable content."""
    import time
    if not isinstance(query,str) or not 1<=len(query.strip())<=300:raise ValueError('Use a public search query of 1–300 characters.')
    if cancel is not None and cancel.is_set() or deadline is not None and time.monotonic()>deadline:raise InterruptedError('Public research stopped.')
    token=os.getenv('OLLAMA_API_KEY')
    searches=[_crossref] if scholarly else [_nasa,_crossref,_wikipedia]
    results=[]
    succeeded=False
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[('Ollama Web Search',pool.submit(_ollama,query,token))] if token and not scholarly else []
        labels={_nasa:'NASA Earthdata CMR',_crossref:'Crossref',_wikipedia:'Wikipedia'}
        futures.extend((labels[search],pool.submit(search,query)) for search in searches)
        for label,future in futures:
            try:
                results.extend(future.result())
                succeeded=True
                if provider_status is not None:provider_status[label]='returned'
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                if provider_status is not None:provider_status[label]='unavailable'
                continue
    if cancel is not None and cancel.is_set() or deadline is not None and time.monotonic()>deadline:raise InterruptedError('Public research stopped.')
    if not succeeded:
        raise ValueError('Public reference search is temporarily unavailable. Try again in a moment.')
    unique={}
    for result in results:
        if result:
            unique.setdefault(result['url'],result)
    return list(unique.values())[:6]


def search_answer(message, query, *, cancel=None, deadline=None):
    scholarly=bool(re.search(r'\b(?:papers|studies|peer-reviewed|scholarly|doi)\b',message,re.I))
    statuses={}
    sources=search_references(query,scholarly=scholarly,provider_status=statuses,**({'cancel':cancel,'deadline':deadline} if cancel is not None or deadline is not None else {}))
    providers=', '.join(dict.fromkeys(item['provider'] for item in sources))
    summary=(f'Found {len(sources)} references for “{query}” via {providers}.'
             if sources else f'No references returned for “{query}”. Try a more specific term.')
    from datetime import datetime, timezone
    from .contracts import digest
    receipt={'query':query,'retrieved_at':datetime.now(timezone.utc).isoformat(),'sources':sources,'providers':statuses,'scope':'Public search metadata only; snippets are not full-paper findings or scientific measurements. Unavailable providers are not an exhaustive search.'}
    receipt['sha256']=digest(receipt)
    return {'web_search':receipt,'title':'Public reference search','kind':'Web references','summary':summary,
            'web_sources':sources,'claims':[]}
