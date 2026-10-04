"""HTTP boundary for the assistant, shared with the existing flat-route server."""
from __future__ import annotations

import base64
import json
import math
import os
import struct
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit

from .contracts import normalize_context

COOKIE="fireatlas_workspace"


def handle(handler,service):
    url=urlsplit(handler.path)
    if not url.path.startswith("/api/assistant/"):
        return False
    try:
        route=url.path.removeprefix("/api/assistant/").strip("/")
        method=handler.command
        params=parse_qs(url.query)
        if method=="GET" and route=="capabilities":
            handler._json(service.capabilities());return True
        if method not in {"GET","POST","DELETE"}: raise ValueError("Unsupported method.")
        if method!="GET":
            expected=os.getenv("FIREATLAS_ASSISTANT_ORIGIN") or "http://"+handler.headers.get("Host","")
            host=urlsplit(expected).hostname
            if not os.getenv("FIREATLAS_ASSISTANT_ORIGIN") and host not in {"localhost","127.0.0.1","::1"}:
                raise PermissionError("Configure FIREATLAS_ASSISTANT_ORIGIN for public deployment.")
            if handler.headers.get("Origin")!=expected:
                raise PermissionError("Assistant updates require a same-origin request.")
        body={}
        if method=="POST":
            size=int(handler.headers.get("Content-Length","0"))
            if handler.headers.get("Content-Type","").split(";")[0]!="application/json" or not 0<size<=3_000_000:
                raise ValueError("Use a JSON request of at most 3 MB.")
            body=json.loads(handler.rfile.read(size))
            if not isinstance(body,dict): raise ValueError("Request must be an object.")
        cookie=SimpleCookie()
        cookie.load(handler.headers.get("Cookie",""))
        owner=cookie[COOKIE].value if COOKIE in cookie else ""
        if route=="sessions" and method=="POST":
            import hashlib
            service.store.purge_expired()
            try: session=service.store.session(owner)
            except PermissionError:
                service.store.throttle("session:"+hashlib.sha256(handler.client_address[0].encode()).hexdigest(),30,3600)
                owner=service.store.create_session(normalize_context(body.get("context")))
                session=service.store.session(owner)
            encoded=json.dumps({"context":session["context"],"view":session["view"],"budget":service.store.budget(owner)}).encode()
            handler.send_response(HTTPStatus.OK)
            handler.send_header("Content-Type","application/json")
            handler.send_header("Content-Length",str(len(encoded)))
            secure="; Secure" if (os.getenv("FIREATLAS_ASSISTANT_ORIGIN","").startswith("https://")) else ""
            handler.send_header("Set-Cookie",f"{COOKIE}={owner}; HttpOnly; SameSite=Strict; Path=/; Max-Age=604800{secure}")
            handler.send_header("Cache-Control","no-store")
            handler.end_headers();handler.wfile.write(encoded);return True
        session=service.store.session(owner)
        if method!="GET":service.store.throttle("updates:"+owner,80,60)
        if route=="sessions" and method=="GET":
            handler._json({"context":session["context"],"view":session["view"],"budget":service.store.budget(owner)})
        elif route=="sessions" and method=="DELETE":
            with service.lock:
                active=list(service.cancellations)
            for identifier in active:
                try:service.cancel(owner,identifier)
                except PermissionError:pass
            service.store.delete_session(owner);handler._json({"deleted":True})
        elif route=="views" and method=="POST":
            context=normalize_context(body.get("context"))
            view=body.get("view")
            if not isinstance(view,dict) or not isinstance(view.get("instance"),str) or len(view["instance"])>100:
                raise ValueError("A registered browser view is required.")
            service.store.update_session(owner,context,view)
            handler._json({"context":context,"registered":True})
        elif route=="prompts" and method=="POST":
            from .prompts import prepare_question
            handler._json(prepare_question(body.get("question"),body.get("context",session["context"]),body.get("selection")))
        elif route=="runs" and method=="POST":
            handler._json(service.start(owner,body),HTTPStatus.ACCEPTED)
        elif route.startswith("runs/"):
            parts=route.split("/")
            identifier=parts[1]
            if len(parts)==2 and method=="GET":handler._json(service.store.run(owner,identifier))
            elif len(parts)==3 and parts[2]=="cancel" and method=="POST":
                service.cancel(owner,identifier);handler._json({"cancelled":True})
            elif len(parts)==3 and parts[2]=="events" and method=="GET":
                handler._json({"events":service.store.events(owner,identifier,int(params.get("after",["0"])[0]))})
            else: raise ValueError("Unknown investigation action.")
        elif route in {"notebook","annotations"}:
            if method=="GET":
                items=service.store.artifacts(owner,'annotation' if route=='annotations' else None,limit=-1)
                handler._json({'items':[r for r in items if r['kind'] in {'annotation','answer','note'}]})
            elif method=="POST":
                text=body.get("text","")
                if not isinstance(text,str) or len(text)>3000:raise ValueError("Note must contain at most 3,000 characters.")
                value={"text":text,"context":normalize_context(body.get("context",session["context"])),"kind":body.get("kind","scientist note")}
                evidence_id=body.get("result_id")
                if evidence_id:
                    service.store.get_artifact(owner,evidence_id,"evidence")
                    value["result_id"]=evidence_id
                if route=="annotations":
                    from .annotations import validate_geometry
                    geometry=body.get("geometry")
                    if geometry is not None:
                        value["geometry"]=validate_geometry(geometry)
                    value["target"]=body.get("target")
                    if body.get("path"):
                        from .contracts import pointer
                        if not evidence_id or not isinstance(body["path"],str) or len(body["path"])>200 or not body["path"].startswith(("/frames/","/observations/","/cells/","/records/")):
                            raise ValueError("A linked annotation needs a returned evidence path.")
                        evidence=service.store.get_artifact(owner,evidence_id,"evidence")["body"]
                        if evidence["release_id"]!=service.science.release()["id"]:
                            raise ValueError("Recalculate the selected evidence before annotating it against the current release.")
                        sample=pointer(evidence["payload"],body["path"])
                        if not isinstance(sample,dict):
                            raise ValueError("Annotation paths must identify an actual sample or cell.")
                        value["path"]=body["path"]
                        value["context"]=dict(evidence["context"])
                        if body["path"].startswith("/frames/"):
                            value["context"]["day"]=evidence["payload"]["frames"][int(body["path"].split("/")[2])]["date_utc"]
                        elif sample.get("acquisition_utc"):
                            value["context"]["day"]=sample["acquisition_utc"][:10]
                        # A linked sample annotation uses the actual returned geometry.
                        if sample.get("ring"):
                            value["geometry"]=validate_geometry({"type":"Polygon","coordinates":[sample["ring"]]})
                        elif sample.get("longitude",sample.get("lon")) is not None:
                            value["geometry"]=validate_geometry({"type":"Point","coordinates":[sample.get("longitude",sample.get("lon")),sample.get("latitude",sample.get("lat"))]})
                handler._json({"id":service.store.artifact(owner,"annotation" if route=="annotations" else "note",value)})
            else:raise ValueError("Unsupported notebook action.")
        elif route.startswith("evidence/") and method=="GET":
            handler._json(service.store.get_artifact(owner,route.split("/")[1]))
        elif route.startswith("artifacts/") and method=="DELETE":
            service.store.delete_artifact(owner,route.split("/")[1]);handler._json({"deleted":True})
        elif route=='places' and method=='POST':
            from .places import lookup
            service.store.throttle('place-session:'+owner,limit=12,seconds=60)
            value=lookup(body.get('query'),service.store.path.parent/'places-v2.sqlite3')
            for choice in value['choices']:
                choice['place_id']=service.store.artifact(owner,'place',choice)
            handler._json(value)
        elif route=='figures/annotate' and method=='POST':
            image=service.store.get_artifact(owner,body.get('image_id'),'image')['body']
            if image['revision']!=session['context']['revision']:raise ValueError('The figure belongs to an older study view.')
            from .figures import annotate
            value=annotate(image,body.get('target'))
            value.update({'revision':image['revision'],'created':time.time(),'image_id':body['image_id']})
            value['id']=service.store.artifact(owner,'annotated_figure',value)
            handler._json(value)
        elif route=="images" and method=="POST":
            if body.get("revision")!=session["context"]["revision"]:raise ValueError("Figure context is stale.")
            if body.get("mime")!="image/png":raise ValueError("Selected figures must use PNG.")
            raw=base64.b64decode(body.get("data",""),validate=True)
            if not 24<=len(raw)<=1_500_000 or raw[:8]!=b'\x89PNG\r\n\x1a\n' or raw[12:16]!=b'IHDR':raise ValueError("Invalid or oversized selected figure.")
            width,height=struct.unpack('>II',raw[16:24])
            if not 1<=width<=1536 or not 1<=height<=1536:raise ValueError("Selected figure must be at most 1536 pixels on each edge.")
            regions=body.get('regions',[])
            if not isinstance(regions,list) or len(regions)>20:raise ValueError('A figure supports at most twenty visual regions.')
            from .presentation import TARGETS
            for region in regions:
                if not isinstance(region,dict) or region.get('target') not in {*TARGETS,'selected-sample','heat-field'}:raise ValueError('Unknown figure target.')
                box=region.get('rect',[])
                if len(box)!=4 or not all(type(v) in (float,int) and math.isfinite(v) for v in box):raise ValueError('Invalid figure region.')
                x,y,w,h=box
                if not (0<=x<width and 0<=y<height and w>0 and h>0 and x+w<=width and y+h<=height):raise ValueError('Figure region exceeds the image.')
            value={"regions":regions,"data":body["data"],"mime":"image/png","revision":body["revision"],"created":time.time(),"caption":str(body.get("caption","Selected scientific visualization"))[:500]}
            handler._json({"id":service.store.artifact(owner,"image",value)})
        elif route=="masks" and method=="POST":
            from ..research import validate_mask,context as research_context
            config=normalize_context(body.get("context",session["context"]))
            setup,start,end=research_context(config["year"],config["month"],config["bbox"],config["as_of"],config["distance_km"],config["gap_days"])
            from datetime import date
            start=date.fromisoformat(config["start"])
            mask=body.get("mask")
            validate_mask(mask,setup,start,end)
            handler._json({"id":service.store.artifact(owner,"mask",mask),"status":"synthetic demonstration" if mask.get("synthetic") else "user-supplied unvalidated"})
        elif route.startswith("actions/") and route.endswith("/ack") and method=="POST":
            handler._json(service.acknowledge(owner,route.split("/")[1],body))
        elif route=="actions" and method=="POST":
            handler._json(service.action(owner,body.get("destination"),normalize_context(body.get("context",session["context"])),session["view"],body.get("result_id"),body.get("options")))
        elif route=="exports" and method=="GET":
            if params.get("format",[""])[0]=="html":
                handler._respond(service.report_html(owner).encode(),"text/html; charset=utf-8",filename="fireatlas-investigation.html")
            else:
                handler._respond(json.dumps(service.export(owner),indent=2).encode(),"application/json",filename="fireatlas-investigation.json")
        elif route.startswith("voice/") and method=="POST":
            from .voice import speech
            handler._json(speech(service,owner,route.split("/")[1],body))
        else:
            handler._json({"error":"Assistant route not found."},HTTPStatus.NOT_FOUND)
    except PermissionError as error:handler._json({"error":str(error)},HTTPStatus.FORBIDDEN)
    except (ValueError,KeyError,TypeError,OverflowError) as error:handler._json({"error":str(error)},HTTPStatus.BAD_REQUEST)
    except Exception:
        handler._json({"error":"Assistant service unavailable. The scientific pages remain usable."},HTTPStatus.SERVICE_UNAVAILABLE)
    return True
