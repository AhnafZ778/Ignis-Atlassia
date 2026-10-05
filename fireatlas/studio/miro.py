"""Explicit operator-configured Miro transfer; no publishing during packaging."""
from __future__ import annotations
import base64
import hashlib
import html
import json
import os
import secrets
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from .errors import StudioError, Forbidden, Unavailable, Conflict, NotFound
from .store import dumps

API='https://api.miro.com/v2'


def fingerprint(remote):
    from urllib.parse import urlsplit,urlunsplit
    value={k:remote.get(k) for k in ('data','position','geometry','style','parent','startItem','endItem')}
    if isinstance(value['data'],dict) and value['data'].get('imageUrl'):
        data=dict(value['data']);u=urlsplit(data['imageUrl']);data['imageUrl']=urlunsplit((u.scheme,u.netloc,u.path,'',''));value['data']=data
    return hashlib.sha256(dumps(value).encode()).hexdigest()


class Miro:
    def __init__(self,service,transport=None):
        self.service,self.store=service,service.store
        self.transport=transport or self.request
        self.lock=threading.Lock()
        with self.store.connection(write=True) as db:
            db.execute("UPDATE export_jobs SET status='partial',error='Transfer interrupted. Resume to reconcile recorded remote identities before retrying.' WHERE format='miro' AND status IN ('queued','preparing')")

    def capabilities(self):
        return {'available':bool(os.getenv('FIREATLAS_MIRO_ACCESS_TOKEN') and self.allowed()),'destinations':sorted(self.allowed()),
                'reason':'Configure FIREATLAS_MIRO_ACCESS_TOKEN and FIREATLAS_MIRO_BOARD_IDS. Public servers also require FIREATLAS_MIRO_PUBLISHER_IDS.',
                'verification':'Adapter capability only; no live transfer is implied.'}

    def allowed(self):return {s.strip() for s in os.getenv('FIREATLAS_MIRO_BOARD_IDS','').split(',') if s.strip()}

    def request(self,method,path,body=None,upload=None):
        token=os.getenv('FIREATLAS_MIRO_ACCESS_TOKEN')
        if not token:raise Unavailable('Miro token is unconfigured.')
        headers={'Authorization':'Bearer '+token,'Accept':'application/json'};data=None
        if upload:
            raw,mime=upload
            if len(raw)>6_000_000:raise StudioError('Miro image upload exceeds 6 MB.')
            boundary='fireatlas-'+secrets.token_hex(12)
            payload={k:body[k] for k in ('data','position','geometry','parent') if k in body}
            data=(f'--{boundary}\r\nContent-Disposition: form-data; name="resource"; filename="figure"\r\nContent-Type: {mime}\r\n\r\n'.encode()+raw+
                  f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="data"\r\nContent-Type: application/json\r\n\r\n{dumps(payload)}\r\n--{boundary}--\r\n'.encode())
            headers['Content-Type']='multipart/form-data; boundary='+boundary
        elif body is not None:data=dumps(body).encode();headers['Content-Type']='application/json'
        for attempt in range(3):
            try:
                with urlopen(Request(API+path,data=data,headers=headers,method=method),timeout=20) as response:
                    return json.loads(response.read(8_000_000))
            except HTTPError as error:
                if error.code==429 and attempt<2:
                    try:delay=float(error.headers.get('Retry-After','1'))
                    except ValueError:delay=1
                    time.sleep(min(10,max(0,delay)));continue
                raise StudioError('Miro rejected the request ('+str(error.code)+'). Check permissions and token configuration.',code='miro-http') from None
            except (URLError,TimeoutError):
                # Creates can have succeeded. Never replay them automatically.
                if method!='GET':raise Conflict('Remote completion is uncertain. Inspect Miro before resuming.',code='miro-uncertain') from None
                if attempt==2:raise Unavailable('Miro could not be reached.') from None
        raise Unavailable('Miro rate limit remains active.')

    def submit(self,principal,did,body,key=None,background=True):
        board=body.get('board_id');mode=body.get('mode','first')
        if board not in self.allowed():raise Forbidden('Select an explicitly allowed Miro board.')
        origin=os.getenv('FIREATLAS_STUDIO_ORIGIN') or os.getenv('FIREATLAS_ASSISTANT_ORIGIN')
        if origin and principal not in {s.strip() for s in os.getenv('FIREATLAS_MIRO_PUBLISHER_IDS','').split(',')}:raise Forbidden('This identity is not an approved Miro publisher.')
        if mode not in {'first','repeat-as-new','update-existing'}:raise StudioError('Choose a supported transfer mode.')
        with self.store.connection() as db:self.store.require(db,principal,did,'editor')
        job_id='miro_'+hashlib.sha256((principal+':'+(key or secrets.token_hex(12))).encode()).hexdigest()[:24]
        with self.store.connection() as db:old=db.execute('SELECT id FROM export_jobs WHERE id=?',(job_id,)).fetchone()
        if old:return self.get(principal,job_id)
        bundle,binaries=self.service.portability.capture(principal,did,body.get('revision'),body.get('scope'))
        ir=self.service.portability.intermediate(bundle,binaries)
        if not self.lock.acquire(False):raise Conflict('A Miro transfer is already active.')
        now=self.store.clock();payload={'board_id':board,'mode':mode,'previous_job_id':body.get('previous_job_id'),'ir':ir,'report':[]}
        try:
            if mode=='update-existing':
                previous=self.get(principal,body.get('previous_job_id'))
                if previous['body']['board_id']!=board:raise StudioError('Update the same remote board.')
            with self.store.connection(write=True) as db:db.execute('INSERT INTO export_jobs VALUES(?,?,?,?,?,?,?,NULL,NULL,?,?)',(job_id,principal,did,bundle['source_document']['revision'],'miro','queued',dumps(payload),now,now))
            if background:threading.Thread(target=self.execute,args=(principal,job_id),daemon=True,name='studio-miro').start()
            else:self.execute(principal,job_id)
        except BaseException:
            if self.lock.locked():self.lock.release()
            raise
        return self.get(principal,job_id)

    def get(self,principal,jid):
        with self.store.connection() as db:row=db.execute("SELECT * FROM export_jobs WHERE id=? AND principal_id=? AND format='miro'",(jid,principal)).fetchone()
        if not row:raise NotFound('Miro transfer not found.')
        self.store.get_document(principal,row['document_id'])
        body=json.loads(row['body']);body.pop('ir',None)
        return {'id':jid,'document_id':row['document_id'],'status':row['status'],'body':body,'error':row['error']}

    def item(self,jid,local):
        with self.store.connection() as db:row=db.execute('SELECT * FROM remote_items WHERE job_id=? AND local_id=?',(jid,local)).fetchone()
        return dict(row)|{'body':json.loads(row['body'])} if row else None

    def resume(self,principal,jid,background=True):
        saved=self.get(principal,jid)
        if saved['status']=='completed':return saved
        if saved['body']['board_id'] not in self.allowed():raise Forbidden('This destination is no longer allowed.')
        with self.store.connection() as db:self.store.require(db,principal,saved['document_id'],'editor')
        origin=os.getenv('FIREATLAS_STUDIO_ORIGIN') or os.getenv('FIREATLAS_ASSISTANT_ORIGIN')
        if origin and principal not in set(os.getenv('FIREATLAS_MIRO_PUBLISHER_IDS','').split(',')):raise Forbidden('Approved publisher identity required.')
        if not self.lock.acquire(False):raise Conflict('Another transfer is active.')
        if background:threading.Thread(target=self.execute,args=(principal,jid),daemon=True).start()
        else:self.execute(principal,jid)
        return self.get(principal,jid)

    def reconcile(self,jid,local,board,old):
        from urllib.parse import urlencode
        expected=old['body']['payload']
        def matches(remote):
            def subset(a,b):
                return all(k in b and subset(v,b[k]) for k,v in a.items()) if isinstance(a,dict) and isinstance(b,dict) else a==b
            return all(subset(v,remote.get(k)) for k,v in expected.items())
        candidates=[];cursor=None;complete=False
        if old.get('remote_id'):
            candidates=[self.transport('GET',f'/boards/{board}/{old["body"]["endpoint"]}/{old["remote_id"]}')];complete=True
        else:
            # Never repeat an uncertain create. Find a unique matching marker/content and placement first.
            for _ in range(40):
                query={'limit':50,'type':old['body']['endpoint'].rstrip('s')}
                if cursor:query['cursor']=cursor
                result=self.transport('GET',f'/boards/{board}/items?'+urlencode(query))
                candidates.extend(r for r in result.get('data',[]) if matches(r))
                cursor=result.get('cursor')
                if not cursor:complete=True;break
        candidates=[r for r in candidates if matches(r)]
        if not complete or len(candidates)!=1:
            raise Conflict('Remote completion remains ambiguous. No duplicate was created; inspect the destination or explicitly transfer as new.',code='miro-uncertain')
        remote=candidates[0]
        body={'fingerprint':fingerprint(remote),'endpoint':old['body']['endpoint'],'content_sha256':old['body'].get('content_sha256')}
        with self.store.connection(write=True) as db:db.execute("UPDATE remote_items SET remote_id=?,status='completed',body=? WHERE job_id=? AND local_id=?",(remote['id'],dumps(body),jid,local))
        return remote['id']

    def remote(self,jid,local,board,endpoint,payload,upload=None,previous=None):
        old=self.item(jid,local)
        if old:
            if old['status']=='completed':return old['remote_id']
            return self.reconcile(jid,local,board,old)
        content_sha256=hashlib.sha256(dumps(payload).encode()+(upload[0] if upload else b'')).hexdigest()
        prior=self.item(previous,local) if previous else None
        if prior and prior['remote_id']:
            remote=self.transport('GET',f'/boards/{board}/{endpoint}/{prior["remote_id"]}')
            if fingerprint(remote)!=prior['body'].get('fingerprint'):raise Conflict('A remote participant edited '+local+'. Their change was preserved.',code='miro-remote-edit')
            if endpoint=='images' and upload:
                if content_sha256==prior['body'].get('content_sha256'):
                    with self.store.connection(write=True) as db:db.execute('INSERT INTO remote_items VALUES(?,?,?,?,?)',(jid,local,prior['remote_id'],'completed',dumps(prior['body'])))
                    return prior['remote_id']
                raise Conflict('The image content changed. Use an explicit new transfer; the existing remote image was retained.',code='miro-image-update')
            method='PATCH';path=f'/boards/{board}/{endpoint}/{prior["remote_id"]}'
        else:method='POST';path=f'/boards/{board}/{endpoint}'
        with self.store.connection(write=True) as db:db.execute('INSERT INTO remote_items VALUES(?,?,?,?,?)',(jid,local,prior['remote_id'] if prior else None,'creating',dumps({'endpoint':endpoint,'payload':payload,'content_sha256':content_sha256})))
        result=self.transport(method,path,payload,upload=upload) if upload else self.transport(method,path,payload)
        if not result.get('id'):raise Conflict('Miro returned no item identity; inspect the destination before retrying.',code='miro-uncertain')
        with self.store.connection(write=True) as db:db.execute("UPDATE remote_items SET remote_id=?,status='completed',body=? WHERE job_id=? AND local_id=?",(result['id'],dumps({'fingerprint':fingerprint(result),'endpoint':endpoint,'content_sha256':content_sha256}),jid,local))
        return result['id']

    def execute(self,principal,jid):
        try:
            with self.store.connection() as db:row=db.execute('SELECT body FROM export_jobs WHERE id=?',(jid,)).fetchone()
            job=json.loads(row['body']);ir=job['ir'];board=job['board_id'];previous=job.get('previous_job_id') if job['mode']=='update-existing' else None
            with self.store.connection(write=True) as db:db.execute("UPDATE export_jobs SET status='preparing' WHERE id=?",(jid,))
            self.transport('GET',f'/boards/{board}')
            right=max(o['transform']['x']+o['transform']['w'] for o in ir['objects'])+80;bottom=max(o['transform']['y']+o['transform']['h'] for o in ir['objects'])+80
            frame=self.remote(jid,'export-frame',board,'frames',{'data':{'title':(ir['title']+' · '+jid[-8:])[:60]},'position':{'x':right/2,'y':bottom/2},'geometry':{'width':max(100,right),'height':max(100,bottom)}},previous=previous)
            ids={}
            for obj in ir['objects']:
                marker=previous or jid
                t=obj['transform'];position={'x':t['x']+t['w']/2,'y':t['y']+t['h']/2,'origin':'center'}
                payload={'data':{'content':html.escape(obj['title'])+'<br>'+html.escape(obj.get('caption','')).replace('\n','<br>')+'<br><small>FireAtlas '+marker+' / '+obj['id']+'</small>','shape':'rectangle'},'position':position,'geometry':{'width':t['w'],'height':t['h']},'parent':{'id':frame},'style':{'fillColor':'#fffdf7'}}
                ids[obj['id']]=self.remote(jid,obj['id'],board,'shapes',payload,previous=previous)
                if obj.get('image'):
                    preview=obj['image'];raw=base64.b64decode(preview['data_url'].split(',',1)[1])
                    self.remote(jid,obj['id']+'-image',board,'images',{'data':{'title':'FireAtlas '+marker+' / '+obj['id']+'-image','altText':obj['title']},'position':position,'geometry':{'width':max(40,t['w']-24)},'parent':{'id':frame}},upload=(raw,preview['mime']),previous=previous)
            for link in ir['connectors']:
                if link['source'] not in ids or link['target'] not in ids:job['report'].append({'id':link['id'],'conversion':'Endpoint missing; connector omitted visibly in report.'});continue
                self.remote(jid,link['id'],board,'connectors',{'startItem':{'id':ids[link['source']]},'endItem':{'id':ids[link['target']]},'shape':'straight'},previous=previous)
            job.pop('ir');job['remote_url']='https://miro.com/app/board/'+board+'/';job['items']=len(ids)
            with self.store.connection(write=True) as db:db.execute("UPDATE export_jobs SET status='completed',body=?,updated=? WHERE id=?",(dumps(job),self.store.clock(),jid))
        except Exception as error:
            with self.store.connection(write=True) as db:db.execute("UPDATE export_jobs SET status='partial',error=?,updated=? WHERE id=?",(str(error)[:500],self.store.clock(),jid))
        finally:self.lock.release()
