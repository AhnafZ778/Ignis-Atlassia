"""Shared assistant runtime used by the local server and optional ASGI gateway."""
from __future__ import annotations

import concurrent.futures
import html
import json
import secrets
import threading
import time
from pathlib import Path

from .agent import guided_answer, provider_config, run_agent
from .contracts import DESTINATIONS, METHODS, digest, normalize_context
from .science import Science, OPERATIONS
from .store import Store


class AssistantService:
    def __init__(self,database,state=None):
        self.store=Store(state or Path(database).parent/"assistant/workspace.sqlite3")
        self.science=Science(database,self.store)
        self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=2,thread_name_prefix="fireatlas-assistant")
        self.cancellations={}
        self.lock=threading.Lock()

    def capabilities(self):
        import importlib.util
        import os,math
        from .connectors import catalog
        config=provider_config()
        installed=importlib.util.find_spec("pydantic_ai") is not None
        try:
            voice_available=bool(os.getenv('OPENAI_API_KEY')) and importlib.util.find_spec('openai') is not None and all(math.isfinite(float(os.getenv(k,'0'))) and float(os.getenv(k,'0'))>0 for k in ('FIREATLAS_STT_MAX_REQUEST_USD','FIREATLAS_TTS_MAX_REQUEST_USD'))
        except ValueError:voice_available=False
        if config.get('free_only'):voice_available=False
        return {"schema":"fireatlas-assistant-capabilities-v1","ai_available":config["configured"] and installed,"provider":config["provider"],"model":config["model"],"vision_model":config.get("vision_model"),"model_routes":config.get("models",{}),"analysis_modes":["efficient","deep"] if config["provider"]=="aiand" else [],"free_only":config.get("free_only",False),"reason":None if config["configured"] and installed else "Provider key, verified prices and optional assistant dependencies are required for conversational AI. Stored-data investigation tools are available.","operations":OPERATIONS,"destinations":DESTINATIONS,"methods":METHODS,"voice":{"available":voice_available,"disclosure":"AI-generated voice, not an eyewitness", "mode":"bounded transcription → checked science → narration"},"connectors":[{"id":"fireatlas","status":"available","scope":"stored scientific data, read-only"},{"id":"references","status":"available","scope":"curated local documentation"}]+[{"id":c["id"],"scope":c["scope"],"status":"configured","tools":c["tools"]} for c in catalog()],"release":{k:v for k,v in self.science.release().items() if k!="manifest"}}

    def start(self,owner,request):
        if not isinstance(request,dict): raise ValueError("Investigation needs an object.")
        context=normalize_context(request.get("context"))
        view=request.get("view") or {}
        if not isinstance(view,dict): raise ValueError("Invalid view state.")
        current=self.store.session(owner)
        if current["context"]["revision"]!=context["revision"]:
            raise ValueError("Study settings changed. Register the current view before investigating.")
        if current["view"].get("instance") and current["view"]["instance"]!=view.get("instance"):
            raise ValueError("Transfer control to this view before starting an investigation.")
        message=request.get("message","")
        if not isinstance(message,str) or len(message)>3000: raise ValueError("Question must be at most 3,000 characters.")
        operation=request.get("operation")
        if operation and operation not in OPERATIONS: raise ValueError("Unsupported scientific operation.")
        if not operation and not self.capabilities()["ai_available"]:
            raise ValueError(self.capabilities()["reason"])
        nonce=request.get("nonce") or secrets.token_urlsafe(16)
        if not isinstance(nonce,str) or len(nonce)>100: raise ValueError("Invalid request ID.")
        run,fresh=self.store.create_run(owner,nonce,{"context":context,"view":view,"message":message,"operation":operation})
        if fresh:
            cancel=threading.Event()
            with self.lock: self.cancellations[run]=cancel
            self.pool.submit(self._run,owner,run,context,view,message,operation,request.get("arguments") or {},cancel,request.get("image_ids") or [])
        return {"id":run,"status":self.store.run(owner,run)["status"]}

    def _run(self,owner,run,context,view,message,operation,args,cancel,image_ids):
        deadline=time.monotonic()+(300 if operation=="sensitivity" else 120)
        def progress(stage):
            self.store.event(owner,run,{"type":"STEP_STARTED","name":stage,"message":"Checking imported records: "+{"replay":"daily detection map","missingness":"export status by date","research":"MODIS and VIIRS overlap","availability":"source inventory","persistence":"repeatedly observed cells","observations":"original detection records","resolve_study_place":"named study location"}.get(stage,stage.replace("_"," "))})
        try:
            self.store.finish(owner,run,"running",{"context":context,"question":message})
            self.store.event(owner,run,{"type":"RUN_STARTED"})
            if operation:
                progress(operation)
                evidence=self.science.call(owner,operation,context,args,cancel,deadline)
                answer=guided_answer(evidence)
            else:
                import base64
                images=[]
                if len(image_ids)>2: raise ValueError("Attach at most two selected figures.")
                for identifier in image_ids:
                    attachment=self.store.get_artifact(owner,identifier,"image")["body"]
                    if attachment["revision"]!=context["revision"] or time.time()-attachment["created"]>600:
                        raise ValueError("Selected figure is stale. Capture the current visualization again.")
                    images.append((base64.b64decode(attachment["data"]),attachment["mime"]))
                answer=run_agent(self,owner,message,context,view,cancel,deadline,progress,images)
            if cancel.is_set(): raise InterruptedError("Investigation stopped.")
            answer.update({"context":context,"context_revision":context["revision"],"view_instance":view.get("instance"),"question":message,"run_id":run})
            notebook=self.store.artifact(owner,"answer",answer)
            answer["notebook_id"]=notebook
            self.store.finish(owner,run,"completed",answer)
            self.store.event(owner,run,{"type":"RUN_FINISHED","outcome":"completed"})
        except Exception as error:
            import traceback
            self.store.artifact(owner,'run_diagnostic',{'error_type':type(error).__name__,'frames':[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(error.__traceback__)[-8:]]})
            if cancel.is_set():
                self.store.cancel(owner,run)
                self.store.event(owner,run,{"type":"RUN_FINISHED","outcome":"cancelled"})
            else:
                # Provider exceptions can contain request details: do not expose secrets.
                safe=str(error) if isinstance(error,(ValueError,PermissionError,TimeoutError,InterruptedError)) else "The investigation could not finish. Completed evidence remains in the notebook; no uncertain provider call was retried."
                if type(error).__name__ in {'ModelAPIError','ModelHTTPError'}:
                    safe='The AI provider could not complete this request. Stored-data tasks and checked evidence charts remain available. Try the AI later; the uncertain provider call was not retried.'
                self.store.finish(owner,run,"failed",{"error":safe,"context":context})
                self.store.event(owner,run,{"type":"RUN_ERROR","message":safe})
        finally:
            with self.lock: self.cancellations.pop(run,None)

    def cancel(self,owner,run):
        self.store.cancel(owner,run)
        with self.lock:
            flag=self.cancellations.get(run)
            if flag: flag.set()

    def action(self,owner,destination,context,view,result_id=None,options=None):
        if destination not in DESTINATIONS: raise ValueError("Unknown semantic destination.")
        from .presentation import validate_options,TARGETS,VIEW_SETTINGS
        options=validate_options(options)
        if options.get('target'):destination=TARGETS[options['target']][0]
        expected_revision=context["revision"]
        if result_id:
            evidence=self.store.get_artifact(owner,result_id,"evidence")["body"]
            context={**evidence["context"],"revision":expected_revision}
        if options['kind']=='set_view':
            settings=options.get('settings',{})
            if set(settings)-VIEW_SETTINGS.get(destination,set()):raise ValueError('Those display controls are unavailable on this page. Use Atlas, Replay or the assistant map.')
            source=settings.get('source',context['source'])
            context=normalize_context({**context,**{k:v for k,v in settings.items() if k in {'source','metric','layer','day','view'}},**({'context':settings['layer']} if 'layer' in settings else {}),'series':{'joint':'joint','MODIS_SP':'modis','VIIRS_SNPP_SP':'viirs-snpp'}[source]})
        place=None
        if options['kind']=='focus_place':
            place=self.store.get_artifact(owner,options['place_id'],'place')['body']
        route,section=DESTINATIONS[destination]
        if options.get('target'):section=TARGETS[options['target']][1]
        value={"destination":destination,"route":route,"section":section,"context":context,"expected_revision":expected_revision,"instance":view.get("instance"),"result_id":result_id,"expires":time.time()+120,"state":"pending","options":options,"place":place}
        identifier=self.store.artifact(owner,"action",value)
        return {"id":identifier,**value}

    def acknowledge(self,owner,identifier,value):
        action=self.store.get_artifact(owner,identifier,"action")["body"]
        current=self.store.session(owner)
        if action["state"]!="pending":
            return {"acknowledged":True,"state":action["state"],"duplicate":True}
        if action["expires"]<time.time() or value.get("revision")!=action["expected_revision"] or action["instance"]!=value.get("instance") or current["view"].get("instance")!=value.get("instance"):
            raise ValueError("Action is expired or belongs to an older view/context.")
        if current["context"]["revision"]!=action["expected_revision"]:
            raise ValueError("Study context changed before this action was applied.")
        if value.get("state") not in {"applied","failed"}:raise ValueError("Action needs an applied or failed acknowledgement.")
        action.update({"state":value["state"],"actual":value.get("actual")})
        self.store.update_artifact(owner,identifier,"action",action)
        return {"id":self.store.artifact(owner,"ack",{"action_id":identifier,"state":value.get("state","failed"),"actual":value.get("actual"),"revision":value["revision"]}),"acknowledged":True}

    def export(self,owner):
        notes=self.store.artifacts(owner,limit=-1)
        evidence=[r for r in notes if r["kind"]=="evidence"]
        answers=[r for r in notes if r["kind"]=="answer"]
        context=self.store.session(owner)["context"]
        document={"schema":"fireatlas-assistant-notebook-v1","context":context,"release":self.science.release(),"answers":answers,"evidence":evidence,"annotations":[r for r in notes if r["kind"]=="annotation"],"notes":[r for r in notes if r["kind"]=="note"]}
        document["sha256"]=digest(document)
        return document

    def report_html(self,owner):
        value=self.export(owner)
        esc=lambda x:html.escape(str(x))
        sections=[]
        for record in reversed(value["answers"]):
            a=record["body"]
            rows="".join(f'<tr><td>{esc(c["label"])}</td><td>{esc(c["value"])}</td><td>{esc(c["unit"])}</td><td>{esc(c["result_id"])} {esc(c["path"])}</td></tr>' for c in a.get("claims",[]))
            sections.append(f'<section><h2>{esc(a["title"])}</h2><p>{esc(a["kind"])}</p><p>{esc(a["summary"])}</p><table><tr><th>Measure</th><th>Value</th><th>Unit</th><th>Evidence</th></tr>{rows}</table><p>{esc(" ".join(a.get("limitations",[])))}</p></section>')
        raw=json.dumps(value,indent=2,allow_nan=False)
        figures=[]
        for r in self.store.artifacts(owner,"image")[:8]:
            image=r["body"]
            figures.append(f'<figure><img alt="Selected scientific figure" src="data:{esc(image["mime"])};base64,{esc(image["data"])}"><figcaption>{esc(image.get("caption","Selected visualization"))}</figcaption></figure>')
        return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>FireAtlas reproducible investigation</title><style>body{font:16px system-ui;max-width:1050px;margin:40px auto;padding:24px;color:#172b31}table{border-collapse:collapse;width:100%;font-size:12px}td,th{padding:8px;border:1px solid #a7b8ba;text-align:left;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}img{max-width:100%}section{margin:30px 0}button{padding:12px}@media print{button{display:none}section{break-inside:avoid}}</style><button onclick="print()">Print / Save as PDF</button><h1>FireAtlas scientific investigation</h1><p>AI-assisted findings and deterministic tools; source observations do not establish fire perimeters or forecasts.</p><p>Notebook hash: '+esc(value["sha256"])+ '</p><h2>Study settings</h2><pre>'+esc(json.dumps(value["context"],indent=2))+'</pre>'+''.join(sections)+''.join(figures)+'<h2>Reproducibility receipt and complete evidence</h2><pre>'+esc(raw)+'</pre></html>'

    def close(self):
        with self.lock:
            for flag in self.cancellations.values(): flag.set()
        self.pool.shutdown(wait=False,cancel_futures=True)
