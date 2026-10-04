"""Same-origin public gateway. Local import/sync and review write routes stay private."""
from __future__ import annotations
import argparse
import asyncio
import contextlib
import os
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path


def create_app(database,origin):
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import Response,JSONResponse,StreamingResponse
    from starlette.routing import Route
    from ..web import handler_factory
    from ..provenance import sanitize_public_payload
    from . import http
    os.environ['FIREATLAS_ASSISTANT_ORIGIN']=origin.rstrip('/')
    handler=handler_factory(Path(database))
    local=ThreadingHTTPServer(('127.0.0.1',0),handler)
    @contextlib.asynccontextmanager
    async def lifespan(app):
        thread=threading.Thread(target=local.serve_forever,daemon=True);thread.start()
        yield
        await asyncio.to_thread(local.shutdown);local.server_close();handler.assistant.close()
    async def proxy(request:Request):
        path=request.url.path
        allowed=request.method=='GET' or path.startswith('/api/assistant/') and request.method in {'POST','DELETE'}
        if not allowed:return JSONResponse({'error':'This public gateway supports read-only science and private assistant workspaces. Imports and review writes run locally.'},status_code=403)
        pieces=[];size=0
        async for chunk in request.stream():
            size+=len(chunk)
            if size>3_000_000:return JSONResponse({'error':'Request exceeds 3 MB.'},status_code=413)
            pieces.append(chunk)
        body=b''.join(pieces)
        url=f'http://127.0.0.1:{local.server_port}{path}'+('?' + request.url.query if request.url.query else '')
        headers={k:v for k,v in request.headers.items() if k.lower() in {'content-type','origin','cookie'}}
        def load():
            req=urllib.request.Request(url,data=body if request.method=='POST' else None,method=request.method,headers=headers)
            try:r=urllib.request.urlopen(req,timeout=120)
            except urllib.error.HTTPError as error:r=error
            with r:return r.status,dict(r.headers),r.read()
        try:code,head,data=await asyncio.to_thread(load)
        except (OSError,TimeoutError):return JSONResponse({'error':'Analysis service unavailable.'},status_code=503)
        output={k:v for k,v in head.items() if k.lower() in {'content-type','content-disposition','set-cookie','cache-control','x-content-type-options'}}
        return Response(data,status_code=code,headers=output)
    async def stream(request:Request):
        import hashlib,json,time
        from http.cookies import SimpleCookie
        cookies=SimpleCookie();cookies.load(request.headers.get('cookie',''))
        owner=cookies[http.COOKIE].value if http.COOKIE in cookies else ''
        identifier=request.path_params['run_id']
        try:handler.assistant.store.run(owner,identifier)
        except PermissionError:return JSONResponse({'error':'Investigation unavailable in this workspace.'},status_code=403)
        async def events():
            after=0;step=None;started=False;until=time.monotonic()+320
            shared={'threadId':hashlib.sha256(owner.encode()).hexdigest()[:20],'runId':identifier}
            def encode(value):return 'data: '+json.dumps(value)+'\n\n'
            while not await request.is_disconnected() and time.monotonic()<until:
                updates=await asyncio.to_thread(handler.assistant.store.events,owner,identifier,after)
                for event in updates:
                    after=event['id'];kind=event['type']
                    if kind=='RUN_STARTED':
                        started=True;yield encode({'type':'RUN_STARTED',**shared})
                    elif kind=='STEP_STARTED':
                        if step:yield encode({'type':'STEP_FINISHED','stepName':step})
                        step=event['name'];yield encode({'type':'STEP_STARTED','stepName':step})
                    elif kind in {'RUN_ERROR','RUN_FINISHED'}:
                        if step:yield encode({'type':'STEP_FINISHED','stepName':step});step=None
                        if kind=='RUN_ERROR':yield encode({'type':'RUN_ERROR','message':event['message']})
                        else:yield encode({'type':'RUN_FINISHED',**shared})
                        return
                receipt=await asyncio.to_thread(handler.assistant.store.run,owner,identifier)
                if receipt['status'] in {'completed','failed','cancelled'} and not updates:
                    if not started:yield encode({'type':'RUN_STARTED',**shared})
                    yield encode({'type':'RUN_FINISHED',**shared});return
                yield ': keepalive\n\n'
                await asyncio.sleep(.5)
        return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})
    return Starlette(routes=[Route('/api/assistant/runs/{run_id}/stream',stream),Route('/{path:path}',proxy,methods=['GET','POST','DELETE','PUT','PATCH'])],lifespan=lifespan)


def main():
    p=argparse.ArgumentParser();p.add_argument('--db',default='data/fireatlas.sqlite3');p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8000);p.add_argument('--origin',default='http://127.0.0.1:8000');a=p.parse_args()
    import uvicorn
    uvicorn.run(create_app(a.db,a.origin),host=a.host,port=a.port,limit_concurrency=32,timeout_keep_alive=5)
if __name__=='__main__':main()
