"""Explicit, cached place lookup. External geography is never wildfire evidence."""
import json
import os
import re
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from ..core import validate_bbox
from ..replay import CASES

_LOCK=threading.Lock()

def lookup(place, cache_path):
    if not isinstance(place,str) or not 2<=len(place.strip())<=180:
        raise ValueError('Enter a place name between 2 and 180 characters.')
    name=re.sub(r'[^a-z0-9]+',' ',place.lower()).strip()
    for key,case in CASES.items():
        if name in {key.replace('-',' '),key.split('-')[0],key.split('-')[0]+' fire',re.sub(r'[^a-z0-9]+',' ',case['title'].lower()).strip()}:
            w,s,e,n=case['bbox']
            return {'status':'resolved','place':place,'choices':[{'title':case['title'],'bbox':[w,s,e,n],'longitude':(w+e)/2,'latitude':(s+n)/2,'context':{'case':key,'bbox':case['bbox'],'start':case['start'],'end':case['end']},'source':'Local study catalog'}]}
    path=Path(cache_path);path.parent.mkdir(parents=True,exist_ok=True)
    with _LOCK,sqlite3.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS places(query TEXT PRIMARY KEY,created REAL,body TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS request_clock(id INTEGER PRIMARY KEY,time REAL)')
        row=db.execute('SELECT body FROM places WHERE query=? AND created>?',(name,time.time()-30*86400)).fetchone()
        if row:return json.loads(row[0])
        clock=db.execute('SELECT time FROM request_clock WHERE id=1').fetchone()
        if clock and time.time()-clock[0]<1.1:
            raise ValueError('Place lookup is rate limited. Wait a moment before searching another place.')
        db.execute('INSERT OR REPLACE INTO request_clock VALUES(1,?)',(time.time(),));db.commit()
        url=os.getenv('FIREATLAS_GEOCODER_URL','https://nominatim.openstreetmap.org/search')
        query=urllib.parse.urlencode({'q':place.strip(),'format':'jsonv2','limit':3,'addressdetails':1})
        request=urllib.request.Request(url+'?'+query,headers={'User-Agent':os.getenv('FIREATLAS_GEOCODER_USER_AGENT','FireAtlasScientificWorkspace/1.0 (explicit place search; local NASA Space Apps project)'), 'Accept':'application/json','Accept-Language':'en'})
        try:
            with urllib.request.urlopen(request,timeout=8) as response:raw=json.loads(response.read(200000))
        except Exception:
            raise ValueError('Place service is unavailable. Saved fire studies still resolve locally; enter boundary coordinates for a custom study.') from None
        if not isinstance(raw,list):raise ValueError('Place service returned an invalid response. Use a saved study or enter boundary coordinates.')
        choices=[]
        for item in raw[:3]:
            try:
                s,n,w,e=map(float,item['boundingbox']);lon=float(item['lon']);lat=float(item['lat'])
                if w==e:w-=.005;e+=.005
                if s==n:s-=.005;n+=.005
                validate_bbox((w,s,e,n));bbox=[w,s,e,n]
                if not w<=lon<=e or not s<=lat<=n:continue
                choices.append({'title':str(item['display_name'])[:400],'bbox':bbox,'longitude':lon,'latitude':lat,'source':'OpenStreetMap / Nominatim','source_url':'https://www.openstreetmap.org/'+str(item['osm_type'])+'/'+str(item['osm_id'])})
            except (KeyError,ValueError,TypeError):continue
        # Never choose between several plausible places on the scientist's behalf.
        result={'status':'resolved' if len(choices)==1 else 'choose_place' if choices else 'not_found','place':place,'choices':choices,
            'note':'Place bounds are geographic context, not fire boundaries. Moving the camera does not change the study or download observations.'}
        db.execute('INSERT OR REPLACE INTO places VALUES(?,?,?)',(name,time.time(),json.dumps(result)));db.commit()
        return result
