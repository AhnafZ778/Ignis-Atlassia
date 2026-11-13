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
        local_ready,local_reason=True,None
        if config.get('local'):
            from .local import readiness
            local_ready,local_reason=readiness(config)
        try:
            voice_available=bool(os.getenv('OPENAI_API_KEY')) and importlib.util.find_spec('openai') is not None and all(math.isfinite(float(os.getenv(k,'0'))) and float(os.getenv(k,'0'))>0 for k in ('FIREATLAS_STT_MAX_REQUEST_USD','FIREATLAS_TTS_MAX_REQUEST_USD'))
        except ValueError:voice_available=False
        if config.get('free_only') or config.get('local'):voice_available=False
        try:
            release={k:v for k,v in self.science.release().items() if k!='manifest'}
        except Exception:  # An unavailable science archive must not block private authoring.
            release=None
        return {"schema":"fireatlas-assistant-capabilities-v1","ai_available":config["configured"] and installed and local_ready,"provider":config["provider"],"model":config["model"],"vision_model":config.get("vision_model"),"model_routes":config.get("models",{}),"analysis_modes":["efficient","deep"] if config["provider"]=="aiand" else [],"free_only":config.get("free_only",False),"reason":local_reason if not local_ready else None if config["configured"] and installed else "Provider key, verified prices and optional assistant dependencies are required for conversational AI. Stored-data investigation tools are available.","operations":OPERATIONS,"destinations":DESTINATIONS,"methods":METHODS,"voice":{"available":voice_available,"disclosure":"AI-generated voice, not an eyewitness", "mode":"bounded transcription → checked science → narration"},"connectors":[{"id":"fireatlas","status":"available" if release else "unavailable","scope":"stored scientific data, read-only"},{"id":"references","status":"available","scope":"curated local documentation"},{"id":"public-references","status":"available","scope":"explicit Investigation web queries, read-only"}]+[{"id":c["id"],"scope":c["scope"],"status":"configured","tools":c["tools"]} for c in catalog()],"release":release}

    def start(self,owner,request):
        if not isinstance(request,dict): raise ValueError("Investigation needs an object.")
        context=normalize_context(request.get("context"))
        view=request.get("view") or {}
        if not isinstance(view,dict): raise ValueError("Invalid view state.")
        if view.get('jarvis_attachment_id'):
            bridge=getattr(self,'studio_bridge',None)
            if not bridge: raise ValueError('Canvas orchestration is unavailable.')
            attached=bridge.surface(owner,view['jarvis_attachment_id'],context)
            if attached['context']['origin_instance_id']!=view.get('jarvis_instance_id'):
                raise ValueError('The attached source belongs to another submitting view.')
        current=self.store.session(owner)
        if current["context"]["revision"]!=context["revision"]:
            raise ValueError("Study settings changed. Register the current view before investigating.")
        if current["view"].get("instance") and current["view"]["instance"]!=view.get("instance"):
            raise ValueError("Transfer control to this view before starting an investigation.")
        message=request.get("message","")
        if not isinstance(message,str) or len(message)>3000: raise ValueError("Question must be at most 3,000 characters.")
        operation=request.get("operation")
        if operation and operation not in OPERATIONS: raise ValueError("Unsupported scientific operation.")
        from .board_views import choose_archived_heatmap, requested_kinds, requests_heatmap_catalog, requests_reading_catalog
        from .firms_country import request_candidate
        from .regional_fire import requests_sundarbans_heatmap
        studio = view.get('studio') or {}
        from .comparison_research import research_question
        from .web_references import requested_query
        direct = not research_question(message) and studio.get('whiteboard') and not studio.get('challenge') and (requests_heatmap_catalog(message) or requests_reading_catalog(message) or requested_kinds(message) or request_candidate(message) or choose_archived_heatmap(message) or requests_sundarbans_heatmap(message))
        direct=direct or bool(studio.get('whiteboard') and not studio.get('challenge') and requested_query(message))
        if not operation and not direct and not self.capabilities()["ai_available"]:
            raise ValueError(self.capabilities()["reason"])
        nonce=request.get("nonce") or secrets.token_urlsafe(16)
        if not isinstance(nonce,str) or len(nonce)>100: raise ValueError("Invalid request ID.")
        view={**view,'jarvis_run_nonce':nonce}
        run,fresh=self.store.create_run(owner,nonce,{"context":context,"view":view,"message":message,"operation":operation})
        if fresh:
            cancel=threading.Event()
            with self.lock: self.cancellations[run]=cancel
            self.pool.submit(self._run,owner,run,context,view,message,operation,request.get("arguments") or {},cancel,request.get("image_ids") or [])
        return {"id":run,"status":self.store.run(owner,run)["status"]}

    def _run(self,owner,run,context,view,message,operation,args,cancel,image_ids):
        deadline=time.monotonic()+(480 if (view.get('studio') or {}).get('whiteboard') else 300 if operation=='sensitivity' else 120)
        def progress(stage):
            special={'searching public references':'Searching public scientific references…',
                     'research_team_observations':'Observation analyst reviewing checked evidence…',
                     'research_team_skeptic':'Scientific skeptic checking alternative explanations…',
                     'research_team_experiment':'Experiment designer proposing the next test…'}
            self.store.event(owner,run,{"type":"STEP_STARTED","name":stage,"at":time.time(),"message":special.get(stage) or "Checking imported records: "+{"replay":"daily detection map","missingness":"export status by date","research":"MODIS and VIIRS overlap","availability":"source inventory","persistence":"repeatedly observed cells","observations":"original detection records","resolve_study_place":"named study location"}.get(stage,stage.replace("_"," "))})
        try:
            self.store.finish(owner,run,"running",{"context":context,"question":message})
            self.store.event(owner,run,{"type":"RUN_STARTED"})
            from .board_views import (
                archive_bundle_answer, archived_heatmap_answer, choose_archived_heatmap, explicit_board_bundle, FIRMS_VIEWS,
                heatmap_catalog, reading_catalog, requested_kinds, requests_heatmap_catalog, requests_reading_catalog,
                selected_firms_answer, selected_reading_requested, area_reading_views, normalize_board_prompt, positive_view_request, AREA_VIEW_PATTERN,
            )
            from . import firms_country, place_fire, regional_fire
            from .firms_history import historical_period, requests_peak_month
            from datetime import datetime, timezone
            import re
            studio = view.get('studio') or {}
            from .comparison_research import research_question
            eligible_whiteboard=studio.get('whiteboard') and not studio.get('challenge') and not operation and not image_ids
            whiteboard_question = eligible_whiteboard and not research_question(message)
            from .web_references import requested_query, search_answer
            web_query=requested_query(message) if eligible_whiteboard else None
            normalized_request=normalize_board_prompt(message)
            map_request=positive_view_request(normalized_request)
            declined_views=whiteboard_question and not map_request and re.search(AREA_VIEW_PATTERN,normalized_request,re.I)
            archived_scope = choose_archived_heatmap(map_request) if whiteboard_question else None
            sundarbans = whiteboard_question and regional_fire.requests_sundarbans_heatmap(map_request)
            if whiteboard_question and not web_query and map_request and not requests_peak_month(map_request) and not requested_kinds(message) and not firms_country.request_candidate(message) and isinstance(studio.get('document_id'),str) and getattr(self, 'studio_bridge', None):
                history=self.studio_bridge.conversation(owner,studio['document_id'])
                if history:
                    map_request=place_fire.place_followup_from_history(message,history) or map_request
            kinds=requested_kinds(map_request)
            if whiteboard_question and not kinds and requests_peak_month(map_request):
                map_request=place_fire.peak_calendar_question(map_request)
                kinds=requested_kinds(map_request)
            saved_answer = (selected_firms_answer(self.store,owner,studio,kinds)
                            if whiteboard_question and kinds and selected_reading_requested(message) else None)
            peak=whiteboard_question and bool(kinds) and requests_peak_month(map_request)
            archive_specs=explicit_board_bundle(map_request,has_study=not studio.get('unscoped')) if whiteboard_question and not (web_query or archived_scope or sundarbans or saved_answer or peak) else None
            resolve_area=whiteboard_question and not (web_query or archived_scope or sundarbans or archive_specs or saved_answer)
            place=place_fire.place_request(map_request) if resolve_area else None
            conflict=resolve_area and kinds and place_fire.conflicting_places(map_request)
            country=(firms_country.resolve(map_request,place) if resolve_area and not conflict and (not place or ',' not in place)
                     and (not kinds or any(kind in FIRMS_VIEWS['firms_country'] for kind in kinds)) else None)
            if web_query:
                progress('searching public references')
                answer=search_answer(message,web_query,cancel=cancel,deadline=deadline)
                identifier=self.store.artifact(owner,'public_research',answer['web_search'])
                answer['web_search_receipts']=[identifier]
                answer['web_sources']=[{**source,'id':f'R{index+1}'} for index,source in enumerate(answer['web_sources'])]
            elif whiteboard_question and requests_heatmap_catalog(message):
                answer = heatmap_catalog()
            elif whiteboard_question and requests_reading_catalog(message):
                answer = reading_catalog()
            elif conflict:
                answer={'title':'Choose one location','kind':'Study clarification','claims':[],
                        'summary':'You requested views for different locations. Ask for each location separately to keep their sources distinct.'}
            elif declined_views:
                answer={'title':'No view requested','kind':'Study clarification','claims':[],
                        'summary':'No satellite view was fetched.'}
            elif saved_answer:
                answer = saved_answer
            elif archive_specs:
                progress('retrieving scoped archive readings')
                answer = archive_bundle_answer(self,owner,archive_specs,message,context,cancel,deadline)
            elif archived_scope:
                progress('replay')
                answer = archived_heatmap_answer(self, owner, archived_scope, cancel, deadline,message=message)
            elif sundarbans:
                progress('historical NASA FIRMS readings near Amurbunia')
                answer = regional_fire.sundarbans_answer(self, owner, cancel, deadline,kinds=kinds or ('heatmap',))
            elif country:
                historical=not isinstance(country[1],int)
                if historical:
                    deadline=max(deadline,time.monotonic()+160)
                progress('NASA FIRMS archive by country' if historical else 'live NASA FIRMS country readings')
                answer = firms_country.answer(self, owner, country, cancel, deadline,kinds=area_reading_views(map_request,kinds) or ('coordinates',),
                                             products=firms_country.requested_products(map_request),message=map_request)
            elif place:
                historical=peak or historical_period(map_request,datetime.now(timezone.utc).date())
                if historical:
                    deadline=max(deadline,time.monotonic()+160)
                progress('ranking monthly NASA FIRMS observations' if peak else 'NASA FIRMS archive by location' if historical else 'resolving place and checking NASA FIRMS')
                answer = place_fire.place_answer(self, owner, place, map_request, cancel, deadline,kinds=area_reading_views(map_request,kinds))
            elif peak:
                answer={'title':'Name the peak search area','kind':'Study clarification','claims':[],
                        'summary':'Give a place and year so I can rank complete UTC months. For example, “Show the peak fire month for the Sundarbans in 2025.”'}
            elif resolve_area and kinds and set(kinds)<=FIRMS_VIEWS['firms_region'].keys() and place_fire.missing_place(map_request):
                answer={'title':'Which location?','kind':'Study clarification','claims':[],
                        'summary':'Name a city, country, or saved study. For example, “Show a heatmap and readings for Dhaka.”'}
            elif whiteboard_question and kinds and set(kinds)<={'harmonized','comparability'}:
                answer={'title':'Choose an evaluated region','kind':'Study clarification','claims':[],
                        'summary':'Monthly comparability is available for Northern California and Punjab–Haryana. For Rajshahi or another custom area, ask for raw FIRMS readings.'}
            elif operation:
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
            if studio.get('web_sources'):
                answer['web_sources']=studio['web_sources']
                answer['web_search_receipts']=studio.get('public_search_receipts',[])
            if studio.get('public_readings'):
                answer['public_readings']=studio['public_readings']
            if studio.get('nasa_discoveries'):
                answer['nasa_discoveries']=studio['nasa_discoveries']
            if view.get('research_team') is True:
                if not studio.get('whiteboard') or studio.get('challenge'):
                    answer['research_team']={'status':'unavailable','specialists':[],'note':'Start research team outside a frozen challenge.'}
                else:
                    from .research_team import review
                    try:answer['research_team']=review(self,owner,message,answer,view,cancel,deadline,progress)
                    except InterruptedError:
                        if cancel.is_set():raise
                        answer['research_team']={'status':'unavailable','specialists':[],'note':'The optional review reached its time limit. Your main investigation is available.'}
                    except (ValueError,PermissionError) as error:
                        answer['research_team']={'status':'unavailable','specialists':[],'note':str(error)}
                    except Exception:
                        answer['research_team']={'status':'unavailable','specialists':[],'note':'The optional research team could not finish. Your main investigation is available.'}
            if cancel.is_set(): raise InterruptedError("Investigation stopped.")
            answer.update({"context":context,"context_revision":context["revision"],"view_instance":view.get("instance"),"question":message,"run_id":run})
            studio = view.get('studio') if isinstance(view.get('studio'), dict) else {}
            if studio.get('whiteboard') and isinstance(studio.get('document_id'), str):
                if studio.get('requested_board_views'):
                    answer['data_views'] = studio['requested_board_views']
                answer['conversation_board_id'] = studio['document_id']
                if getattr(self, 'studio_bridge', None):
                    self.studio_bridge.save_conversation_turn(owner, studio['document_id'], run, message, answer)
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
        self.store.run(owner,run)
        with self.store.connection() as db:
            nonce=db.execute('SELECT nonce FROM runs WHERE id=? AND session=?',(run,owner)).fetchone()['nonce']
        self.store.cancel(owner,run)
        with self.lock:
            flag=self.cancellations.get(run)
            if flag: flag.set()
        if getattr(self,'studio_bridge',None):self.studio_bridge.cancel_commands(owner,nonce)

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
