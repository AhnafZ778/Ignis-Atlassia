"""Optional provider-neutral coordinator. All numerical output is evidence-rendered."""
from __future__ import annotations

import json
import math
import os
import re
import time
from pathlib import Path
from typing import Literal

from .contracts import DESTINATIONS, LIMITATION, normalize_context, pointer


def provider_config():
    provider = os.getenv("FIREATLAS_AI_PROVIDER", "openai")
    if provider not in {"openai", "google", "openrouter", "aiand"}:
        raise ValueError("AI provider must be openai, google, openrouter or aiand.")
    if provider == 'aiand':
        from .aiand import routes
        choices=routes()
        return {'provider':provider,'model':choices['efficient'],'vision_model':choices['efficient_vision'],
                'models':choices,'configured':bool(os.getenv('AIAND_API_KEY')),
                'input_price':None,'output_price':None,'free_only':False}
    if provider == 'openrouter':
        from .free_models import TEXT_MODEL, VISION_MODEL
        model = os.getenv('FIREATLAS_OPENROUTER_MODEL', TEXT_MODEL)
        vision = os.getenv('FIREATLAS_OPENROUTER_VISION_MODEL', VISION_MODEL)
        return {'provider': provider, 'model': model, 'vision_model': vision,
                'configured': bool(os.getenv('OPENROUTER_API_KEY')) and model.endswith(':free') and vision.endswith(':free'),
                'input_price': 0.0, 'output_price': 0.0, 'free_only': True}
    key = os.getenv("OPENAI_API_KEY" if provider == "openai" else "GOOGLE_API_KEY", "")
    model = os.getenv("FIREATLAS_AI_MODEL", "gpt-6-luna" if provider == "openai" else "gemini-3.8-flash")
    prices = [os.getenv("FIREATLAS_AI_INPUT_USD_PER_MILLION"),os.getenv("FIREATLAS_AI_OUTPUT_USD_PER_MILLION")]
    try:
        parsed_prices=[float(p) if p else None for p in prices]
    except (ValueError,TypeError):
        parsed_prices=[None,None]
    valid_prices = all(p is not None and math.isfinite(p) and p>0 for p in parsed_prices)
    configured = bool(key and valid_prices)
    return {"provider": provider, "model": model, "configured": configured,
            "input_price": parsed_prices[0], "output_price": parsed_prices[1]}


def compact(value, depth=0):
    if depth > 7:
        return "Detail available in evidence inspector."
    if isinstance(value,dict):
        return {k:compact(v,depth+1) for k,v in value.items() if k not in {"raw_json", "pixels", "paired_observations", "request_hashes"}}
    if isinstance(value,list):
        return [compact(v,depth+1) for v in value[:3]]
    if isinstance(value,str):
        return value[:1600]
    return value


def evidence_preview(result, context):
    """Bound geometry-heavy previews while preserving the selected day's facts."""
    preview=compact(result)
    if result['operation']=='replay':
        preview['payload'].pop('observations',None)
        for frame in preview['payload'].get('frames',[]):
            frame.pop('cells',None)
        for i,frame in enumerate(result['payload']['frames']):
            if frame['date_utc']==context.get('day'):
                preview['selected_frame']={k:v for k,v in frame.items() if k!='cells'}
                preview['selected_frame_path']=f'/frames/{i}'
                preview['selected_frame_claims']=[{'result_id':result['id'],'path':f'/frames/{i}/products/{source}/{field}',
                    'value':product[field],'unit':'records' if field=='detections' else 'cells'}
                    for source,product in frame['products'].items() for field in ('detections','cell_days')]
                for key in ('date_utc','joint_cell_days'):
                    if key in frame:
                        preview['selected_frame_claims'].append(fact(result,f'/frames/{i}/{key}'))
                for source,product in frame['products'].items():
                    if 'label' in product:
                        preview['selected_frame_claims'].append(fact(result,f'/frames/{i}/products/{source}/label'))
                break
        preview['preview_note']='Frames are limited examples. Selected frame and summary values are authoritative. Use selected_frame_claims for the displayed day; inspect_selection retrieves exact cells or records. Geometry and provenance remain in saved evidence.'
    if result['operation']=='missingness':
        preview['payload']['days']=[{'date':d['date'],'products':{k:{field:v[field] for field in ('state','label','detections','pass_cloud_opportunity')} for k,v in d['products'].items()}} for d in result['payload']['days']]
    preview['claim_candidates']=guided_answer(result)['claims']
    return preview


def fact(evidence, path, label=None):
    value = pointer(evidence["payload"], path)
    if isinstance(value,(dict,list)) or value is None or isinstance(value,bool):
        raise ValueError("A fact must reference a concrete scalar; missing values remain unavailable.")
    if isinstance(value,float) and not math.isfinite(value):
        raise ValueError("Invalid numerical evidence.")
    key=path.rsplit("/",1)[-1]
    unit=evidence["method"]["unit"]
    if "frp" in key:unit="MW"
    elif key in {"ratio","jaccard"}:unit="ratio"
    elif key in {"longitude","latitude","lon","lat"}:unit="degrees"
    elif key in {"distance_km"}:unit="km"
    elif key in {"gap_days","observed_days","detected_days","days","incomplete_export_days","no_imported_record_days"}:unit="UTC days"
    elif '/raw_pixels/' in path or key.endswith("detections") or key in {"raw_pixels","returned","imported_records","eligible_unique_detections","raw_rows_in_aoi","duplicate_alias_rows_removed","excluded_non_vegetation_rows"} or key=='total' and evidence['operation']=='observations':unit="records"
    elif key=="total_cells" or key.endswith("_cells") or evidence["operation"]=="compare" and path.startswith("/counts/"):unit="cells"
    elif path.startswith('/frames/') and key in {'cell_days','joint_cell_days'}:unit='cells'
    elif key=="count" and ("/candidates/" in path or evidence['operation']=='sensitivity'):unit="groups"
    elif key in {'year','month'}:unit='UTC calendar '+key
    elif key in {'grid_x','grid_y'}:unit='1 km grid index'
    elif key=='export_requests':unit='export requests'
    elif key in {"per_100_observed_cell_days","detected_in_mask","observed_cell_days","detections_without_mask"}:
        # A rate is inseparable from its denominator and declared mask status.
        unit="detections per 100 observed cell-days" if key=="per_100_observed_cell_days" else "cell-days"
    elif not isinstance(value,(int,float)):unit="reported metadata"
    if label is None and evidence['operation']=='missingness':
        parts=path.split('/')
        source=next(({'MODIS_SP':'MODIS','VIIRS_SNPP_SP':'VIIRS S-NPP'}[v] for v in parts if v in {'MODIS_SP','VIIRS_SNPP_SP'}),'Source')
        label=source+' '+key.replace('_',' ')
    if label is None and evidence['operation']=='replay':
        match=re.fullmatch(r'/frames/(\d+)/(?:products/(MODIS_SP|VIIRS_SNPP_SP)/)?([^/]+)',path)
        if match:
            frame=evidence['payload']['frames'][int(match[1])]
            source={'MODIS_SP':'MODIS','VIIRS_SNPP_SP':'VIIRS S-NPP'}.get(match[2],'Both sensors')
            field={'cell_days':'occupied cells','joint_cell_days':'distinct occupied cells','frp_max_mw':'peak FRP','frp_sum_mw':'summed FRP'}.get(key,key.replace('_',' '))
            label=f"{source} {field} · {frame['date_utc']}"
        else:
            for source,name in [('MODIS_SP','MODIS'),('VIIRS_SNPP_SP','VIIRS S-NPP')]:
                if f'/summary/sources/{source}/' in path:label=f'{name} study {key.replace("_"," ")}'
    card={"result_id": evidence["id"], "path": path, "label": str(label or key).replace("_"," ")[:100], "value": value, "unit": unit, "method_id": evidence["method"]["id"], "release_id": evidence["release_id"]}
    if key=="per_100_observed_cell_days":
        row=pointer(evidence["payload"],path.rsplit("/",1)[0])
        card["denominator"]={"observed_cell_days":row["observed_cell_days"],"detected_in_mask":row["detected_in_mask"],"mask_status":evidence["payload"]["coverage"]["status"]}
    return card


def guided_answer(evidence):
    op, payload = evidence["operation"], evidence["payload"]
    cards=[]
    def add(path,label,unit=None):
        try:
            card=fact(evidence,path,label)
            if unit: card["unit"]=unit
            cards.append(card)
        except (KeyError,IndexError,ValueError,TypeError):
            pass
    if op in {"research","exposure"}:
        for key,label in (("modis","MODIS"),("viirs","VIIRS S-NPP"),("both","Shared"),("union","Distinct union")):
            add("/overlap/totals/"+key,label,"cell-days")
        add("/raw_pixels","Eligible imported rows","records")
        add("/candidates/count","Connected candidate groups","groups")
    elif op=="replay":
        add("/summary/eligible_unique_detections","Eligible unique detections","records")
        add("/summary/joint_cell_days","Distinct union","cell-days")
        add("/summary/detected_days","Days with imported detections","UTC days")
    elif op=="observations":
        add("/total","Full matching original records","records")
        add("/returned","Records in this page","records")
    elif op=="persistence":
        add("/total_cells","Observed cells","cells")
        add("/cells/0/observed_days","Most persistent reported cell","distinct observed UTC days")
    elif op=="compare":
        for key in payload["counts"]:
            add("/counts/"+key,key,"cells")
    elif op=="archive_search":
        add("/total_windows","Historical detection windows","monthly windows")
        add("/total_imported_records","Matching imported rows","records")
        if payload.get('windows'):
            add('/windows/0/month','Largest imported monthly window','UTC month')
            add('/windows/0/peak_day','Replayable peak observation date','UTC date')
            add('/windows/0/modis_records','MODIS rows in that window','records')
            add('/windows/0/viirs_records','VIIRS S-NPP rows in that window','records')
    elif op=="missingness":
        for source,name in [('MODIS_SP','MODIS'),('VIIRS_SNPP_SP','VIIRS S-NPP')]:
            for field,label,unit in [('incomplete_export_days','incomplete export days','UTC days'),('incomplete_export_dates','incomplete export dates','reported UTC dates'),('no_imported_record_days','days without imported records','UTC days'),('no_imported_record_dates','dates without imported records','reported UTC dates')]:
                add('/summary/'+source+'/'+field,name+' '+label,unit)
    elif op=="availability":
        for i, source in enumerate(payload["sources"]):
            add(f"/sources/{i}/imported_records",source["source_id"],"imported records")
    title = {"archive_search":"Historical archive search", "replay":"Historical observation study", "research":"Sensor overlap and candidate evidence", "exposure":"Coverage and denominators", "persistence":"Distinct observed-date persistence", "missingness":"Source availability through the study", "compare":"Change in observed locations", "sensitivity":"Candidate threshold experiment", "availability":"Stored source inventory", "sources":"Curated research references", "method":"Calculation methods", "calendar":"Raw observed-cell calendar", "harmonized":"Regional VIIRS-equivalent calendar", "validation":"Scientific evidence gates", "observations":"Original observation records"}[op]
    note = payload.get("note") or payload.get("temporal_scope") or LIMITATION
    return {"title": title, "summary": note, "kind": "deterministic scientific tool", "claims": cards, "evidence_ids": [evidence["id"]], "actions": [], "spoken_summary": title+". "+note, "limitations": evidence["limitations"]}


def run_agent(service, owner, message, context, view, cancel, deadline, progress, images=None, model=None):
    config = provider_config()
    if not config["configured"]:
        raise ValueError("AI is not configured. Add a server-side provider key and verified pricing. The scientific action buttons already work with stored data.")
    from pydantic import BaseModel, Field
    from pydantic_ai import Agent, UsageLimits, ModelRetry
    from pydantic_ai.models.wrapper import WrapperModel
    from pydantic_ai.models import infer_model
    from pydantic_ai.messages import ModelMessagesTypeAdapter
    class Claim(BaseModel):
        result_id: str = Field(description="Copy the exact id of retrieved evidence. Use claim_candidates supplied by the tool when available.")
        path: str = Field(pattern=r"^/", description="JSON pointer into the retrieved payload, e.g. /summary/eligible_unique_detections. Use slash-separated keys, not dot notation.")
        label: str = Field(max_length=100)
    class Action(BaseModel):
        destination: Literal["overview","atlas","calendar","harmonized","replay","timeline","records","overlap","candidates","exposure","validation","sources","method","review","assistant","terrain"]
        result_id: str | None = None
        options: dict = Field(default_factory=dict,description="Allowlisted display parameters. Copy place_id from a resolved place; ambiguous places require the scientist to choose. No selectors or scripts.",json_schema_extra={
            'additionalProperties':False,'properties':{
                'kind':{'type':'string','enum':['navigate','focus_place','highlight','set_view']},
                'place_id':{'type':'string'},'target':{'type':'string','enum':list(__import__('fireatlas.assistant.presentation',fromlist=['TARGETS']).TARGETS)},
                'candidate_id':{'type':'string','maxLength':100},
                'settings':{'type':'object','additionalProperties':False,'properties':{
                    'source':{'type':'string','enum':['joint','MODIS_SP','VIIRS_SNPP_SP']},
                    'metric':{'type':'string','enum':['density','persistence','frp']},
                    'layer':{'type':'string','enum':['none','ndvi','landcover','terrain','burned-area']},
                    'view':{'type':'string','enum':['2d','3d']},'scope':{'type':'string','enum':['daily','history']},
                    'split':{'type':'boolean'},'day':{'type':'string','format':'date'}}}}})
    class Visualization(BaseModel):
        result_id: str = Field(description="Exact retrieved evidence id. The browser renders every value from that calculation; supply no invented chart data.")
        kind: Literal['daily','availability','overlap','archive','inventory','persistence','comparison','workflow']
    class Draft(BaseModel):
        title: str = Field(max_length=120)
        interpretation: str = Field(default="",max_length=600, description="One short supported explanation, fewer than 600 characters. No numbers, dates or measurements here: put requested scalar values in claims.")
        clarification: str | None = Field(default=None,max_length=300)
        claims: list[Claim] = Field(default_factory=list,max_length=12, description="Only requested scalar facts. Prefer the tool's claim_candidates. Do not cite notes lists, missing fields, or add unrequested claims.")
        actions: list[Action] = Field(default_factory=list,max_length=3)
        visualizations: list[Visualization] = Field(default_factory=list,max_length=2,description="Open a chart or method diagram when the scientist asks for a graph, diagram or visual explanation. Match the kind to the retrieved calculation.")
    free_only = config.get('free_only', False)
    if config['provider']=='aiand':
        from .aiand import verified_model
        config.update(verified_model(view.get('analysis_depth','efficient'),bool(images)))
    routes = []
    if free_only:
        from .free_models import verified_routes
        config['model'] = config['vision_model'] if images else config['model']
        routes = verified_routes(config['model'], bool(images))
    if not free_only and (config["input_price"] is None or config["output_price"] is None or min(config["input_price"],config["output_price"])<=0):
        raise ValueError("Provider pricing must be positive and verified before public AI is enabled.")
    results=[]
    visual_requested=bool(re.search(r'\b(?:graph|chart|diagram)\b|\bexplain\b.*\bvisually\b',message,re.I))
    diagram_requested=bool(re.search(r'\bdiagram\b',message,re.I)) and not re.search(r'\b(?:graph|chart)\b',message,re.I)
    # The three published examples have known workflows. Supply their exact
    # evidence once, instead of making the model rediscover it over many turns.
    preset=None
    selection_preset=message.startswith(('Inspect the selected cell.','Inspect the selected observation using its exact evidence path.'))
    if message.startswith('Check the selected study’s source availability.'):
        preset='missingness'
    elif message.startswith('Search historical detection windows from 2006 onward'):
        preset='archive_search'
    elif selection_preset and not (view.get('selection') or {}).get('path'):
        return {'title':'Select an observation first','summary':'Click a heatmap cell, a satellite mark, or a row in Browse records, then ask again. A geographic note alone has no MODIS or VIIRS sample to inspect.', 'kind':'Study clarification','claims':[], 'evidence_ids':[], 'actions':[], 'limitations':[], 'spoken_summary':'Select a recorded sample first.'}
    prepared_selection=None
    # Reuse the already calculated map for questions about the displayed study.
    # This preserves its exact paths without another model-driven archive query.
    if view.get('result_id') and re.search(r'\b(currently selected|selected (?:UTC )?day|this (?:study|map)|displayed (?:day|frame))\b',message,re.I):
        try:
            current={'id':view['result_id'],**service.store.get_artifact(owner,view['result_id'],'evidence')['body']}
            if (current['operation']=='replay' and current['release_id']==service.science.release()['id']
                    and all(current['context'].get(k)==context.get(k) for k in ('bbox','start','end'))):
                results.append(current)
        except (PermissionError,ValueError,KeyError):
            pass  # A stale or unavailable map still requires a fresh tool query.
    if selection_preset and (view.get('selection') or {}).get('path'):
        chosen=view['selection']
        previous={'id':chosen['result_id'],**service.store.get_artifact(owner,chosen['result_id'],'evidence')['body']}
        if previous['release_id']!=service.science.release()['id']:raise ValueError('The selected record belongs to an older archive release. Reload the map.')
        cell=pointer(previous['payload'],chosen['path'])
        if not isinstance(cell,dict):raise ValueError('Select an actual observation cell or record.')
        results.append(previous)
        prepared_selection={'result_id':previous['id'],'path':chosen['path'],'selected_observation':cell,'scalar_claim_paths':{k:chosen['path']+'/'+k for k,v in cell.items() if type(v) in (int,float,str)}}
        if chosen['path'].startswith('/frames/'):
            f=int(chosen['path'].split('/')[2]);prepared_selection['frame_products']=previous['payload']['frames'][f]['products'];prepared_selection['frame_products_path']=f'/frames/{f}/products'
    if preset:
        progress(preset)
        results.append(service.science.call(owner,preset,context,{'first_year':2006} if preset=='archive_search' else {},cancel,deadline))
    unresolved_places=set()
    ambiguous_place_ids=set()
    resolved_places=[]
    annotated_figures=[]
    used_models=[]
    call_costs=[]
    instructions=Path(__file__).with_name("system.md").read_text()
    class BudgetModel(WrapperModel):
        async def request(self,messages,model_settings,model_request_parameters):
            if cancel.is_set() or time.monotonic()>deadline:raise InterruptedError("Investigation stopped.")
            # UTF-8 serialized bytes are a deliberately pessimistic token bound,
            # including tool schemas and selected inline images. Oversized contexts
            # are refused before a paid request. Every call is reserved separately.
            serialized=ModelMessagesTypeAdapter.dump_json(messages)
            size=len(serialized)+len(repr(model_request_parameters).encode())
            def image_adjustment(value):
                if isinstance(value,dict):
                    if value.get('kind')=='binary' and str(value.get('media_type','')).startswith('image/'):
                        # Uploaded figures are bounded to 1536px. Reserve vision
                        # tokens instead of treating base64 bytes as input text.
                        return 16000-len(value.get('data',''))
                    return sum(image_adjustment(v) for v in value.values())
                if isinstance(value,list):return sum(image_adjustment(v) for v in value)
                return 0
            size+=image_adjustment(json.loads(serialized))
            if size>160000:raise ValueError("Conversation or figure is too large. Narrow the investigation or attach a smaller selected figure.")
            if free_only:
                with service.store.connection() as db:
                    if db.execute("SELECT 1 FROM artifacts WHERE kind='inference_cost_error' LIMIT 1").fetchone():
                        raise ValueError('Free inference is paused after a provider cost discrepancy. Stored-data tools remain available.')
                service.store.throttle('openrouter-free-global', limit=10, seconds=60)
                reservation=None
            else:
                reservation=service.store.reserve(owner,math.ceil(size*config["input_price"]+config.get('max_tokens',1200)*config["output_price"]))
            try:
                response=await self.wrapped.request(messages,model_settings,model_request_parameters)
            except Exception as error:
                if free_only:
                    status=getattr(error,'status_code',None)
                    if status==429:
                        raise ValueError('Free model capacity or account quota reached. Try later; no paid fallback or key rotation was used.') from None
                    if status in (401,403):
                        raise ValueError('OpenRouter rejected the configured key. Update the private server configuration.') from None
                    if status==400:
                        raise ValueError('The free provider rejected required tool or image parameters. Stored-data tools remain available; no paid fallback was used.') from None
                    if status==402:
                        raise ValueError('OpenRouter account access is restricted. No paid request or fallback was made.') from None
                    if status in (404,502,503):
                        raise ValueError('The verified free models are currently unavailable. Stored-data tools remain available; no paid fallback was used.') from None
                raise
            service.store.artifact(owner,'model_diagnostic',{'tool_calls':[{'name':p.tool_name,'argument_length':len(str(p.args))} for p in response.parts if hasattr(p,'tool_name')], 'finish_reason':response.finish_reason,'input_tokens':response.usage.input_tokens,'output_tokens':response.usage.output_tokens})
            used_models.append(response.model_name)
            usage=response.usage
            if free_only:
                reported_cost=(response.provider_details or {}).get('cost')
                service.store.artifact(owner,'inference_receipt',{'provider':'openrouter','model':response.model_name,'free_only':True,'reported_cost':reported_cost,'input_tokens':usage.input_tokens,'output_tokens':usage.output_tokens})
                if reported_cost is not None and float(reported_cost)>0:
                    service.store.artifact(owner,'inference_cost_error',{'provider':'openrouter','reported_cost':reported_cost})
                    raise ValueError('OpenRouter reported a nonzero cost for a free-only request. Stop AI and review the provider receipt.')
                return response
            actual=math.ceil(usage.input_tokens*config["input_price"]+usage.output_tokens*config["output_price"]) if usage.input_tokens else None
            service.store.reconcile(owner,reservation,actual)
            call_costs.append(actual)
            if config['provider']=='aiand':
                service.store.artifact(owner,'inference_receipt',{'provider':'aiand','model':response.model_name,
                    'input_tokens':usage.input_tokens,'output_tokens':usage.output_tokens,
                    'estimated_cost_usd':actual/1e6 if actual is not None else None,
                    'price_basis':config['price_basis'],'analysis_depth':config['analysis_depth']})
            return response
    if model is None:
        if config['provider']=='openrouter':
            from openai import AsyncOpenAI
            from pydantic_ai.models.openrouter import OpenRouterModel
            from pydantic_ai.providers.openrouter import OpenRouterProvider
            class FreeOpenRouterModel(OpenRouterModel):
                def _process_response(self, raw):
                    result=super()._process_response(raw)
                    # The framework omits a literal zero cost; retain it explicitly.
                    if getattr(raw,'usage',None) is not None:
                        result.provider_details=result.provider_details or {}
                        result.provider_details['cost']=getattr(raw.usage,'cost',None)
                    return result
            client=AsyncOpenAI(api_key=os.environ['OPENROUTER_API_KEY'],base_url='https://openrouter.ai/api/v1',max_retries=0)
            model=FreeOpenRouterModel(config['model'],provider=OpenRouterProvider(openai_client=client))
        elif config['provider']=='aiand':
            from openai import AsyncOpenAI
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider
            from pydantic_ai.profiles.openai import OpenAIModelProfile
            from .aiand import BASE_URL
            client=AsyncOpenAI(api_key=os.environ['AIAND_API_KEY'],base_url=BASE_URL,max_retries=0,default_headers={'User-Agent':'FireAtlas/1.0'})
            model=OpenAIChatModel(config['model'],provider=OpenAIProvider(openai_client=client),
                profile=OpenAIModelProfile(supports_image_input=config['vision'],openai_supports_reasoning=True,openai_chat_supports_max_completion_tokens=True))
        elif config['provider']=='openai':
            from openai import AsyncOpenAI
            from pydantic_ai.models.openai import OpenAIResponsesModel
            from pydantic_ai.providers.openai import OpenAIProvider
            model=OpenAIResponsesModel(config['model'],provider=OpenAIProvider(openai_client=AsyncOpenAI(max_retries=0)))
        else:
            from pydantic_ai.models.google import GoogleModel
            from pydantic_ai.providers.google import GoogleProvider
            from google.genai.types import HttpRetryOptions
            model=GoogleModel(config['model'],provider=GoogleProvider(retry_options=HttpRetryOptions(attempts=1)))
    agent=Agent(BudgetModel(model), output_type=Draft, instructions=instructions, retries=1)
    def retrieved_evidence(result_id):
        if cancel.is_set() or time.monotonic()>deadline:
            raise InterruptedError('Investigation stopped.')
        try:
            result={'id':result_id,**service.store.get_artifact(owner,result_id,'evidence')['body']}
        except (PermissionError,ValueError):
            raise ModelRetry('Use the exact evidence id supplied by the current selection, earlier findings, or an investigation tool. This evidence is unavailable to this workspace.') from None
        if result['release_id']!=service.science.release()['id']:
            raise ModelRetry('The evidence belongs to an older data release. Recalculate it before inspecting, comparing, or annotating.')
        return result
    @agent.tool_plain
    def resolve_study_place(place: str) -> dict:
        """Find geographic places or saved fires. Use returned place_id in a focus_place action to move the camera. Ambiguous results require a choice; geography never supplies fire measurements."""
        from .places import lookup
        try:value=lookup(place,service.store.path.parent/'places-v2.sqlite3')
        except ValueError as error:raise ModelRetry(str(error)) from None
        for choice in value['choices']:
            choice['place_id']=service.store.artifact(owner,'place',choice)
            if value['status']!='resolved':ambiguous_place_ids.add(choice['place_id'])
            resolved_places.append(choice)
        if value['status']=='resolved':unresolved_places.discard(place)
        else:unresolved_places.add(place)
        return value

    @agent.output_validator
    def verify_draft(draft: Draft) -> Draft:
        for known in {context.get('case'),*(r['context'].get('case') for r in results)}-{None}:
            draft.interpretation=draft.interpretation.replace(known,'the selected study')
        from .presentation import validate_options,VIEW_SETTINGS
        by_id={r['id']:r for r in results}
        from .presentation import validate_visualization,VISUAL_KINDS
        if visual_requested and not draft.clarification and not draft.visualizations:
            candidate=next((r for r in reversed(results) if diagram_requested or r['operation'] in VISUAL_KINDS),None)
            if candidate:draft.visualizations=[Visualization(result_id=candidate['id'],kind='workflow' if diagram_requested else VISUAL_KINDS[candidate['operation']])]
        for visual in draft.visualizations:
            if visual.result_id not in by_id:raise ModelRetry('Retrieve the scientific calculation before showing its chart. Use its exact evidence id.')
            try:validate_visualization(by_id[visual.result_id],visual.kind)
            except ValueError as error:raise ModelRetry(str(error)) from None
            if visual.kind in {'daily','availability','archive','inventory'} and re.search(r'(?:counts?|counting|plots?|represent\w*|show\w*)[^.!?]{0,70}(?:cell[\s-]*days|occupied cells|grid cells)',draft.interpretation,re.I):
                raise ModelRetry('This graph plots source-specific detection records, not cells or cell-days. Explain its actual record units and export status; cell-day values can remain separate checked claim cards.')
        for action in draft.actions:
            try:validate_options(action.options)
            except ValueError as error:raise ModelRetry(str(error)) from None
            if action.options.get('place_id') in ambiguous_place_ids:
                raise ModelRetry('Several geographic places matched. Return a clarification with no camera action; the interface presents the choices for the scientist to select.')
            if action.destination not in DESTINATIONS or action.result_id and action.result_id not in by_id:
                raise ModelRetry('Use only a supported destination and an id from retrieved evidence.')
            if action.options.get('kind')=='set_view':
                base=by_id[action.result_id]['context'] if action.result_id else context
                settings=action.options.get('settings',{});source=settings.get('source',base['source'])
                if set(settings)-VIEW_SETTINGS.get(action.destination,set()):raise ModelRetry('Those controls are unavailable on this page. The assistant map supports source, metric, layer, day, scope and split; Replay also supports terrain view; Atlas supports source, layer and day. Navigate to a compatible destination.')
                try:normalize_context({**base,**{k:v for k,v in settings.items() if k in {'source','metric','layer','day','view'}},'series':{'joint':'joint','MODIS_SP':'modis','VIIRS_SNPP_SP':'viirs-snpp'}[source]})
                except ValueError as error:raise ModelRetry(str(error)+'. Display dates must belong to their study. A historical window needs its own replay evidence before navigation; identify the window without changing the map when the scientist only asks to search.') from None
            if preset=='archive_search' and draft.actions:
                raise ModelRetry('This preset asks to identify historical windows, not change the selected study. Return checked window claims without actions; the interface provides buttons to open a chosen window.')
        if unresolved_places and not draft.clarification:
            raise ModelRetry("Ask the scientist to choose among the returned geographic places, or provide a boundary when none matched. Do not use current-study readings for that place.")
        if draft.clarification:
            if draft.claims or draft.visualizations:
                raise ModelRetry("A clarification must have no measurement claims. Ask one clear location/date question.")
            return draft
        by_id={r["id"]:r for r in results}
        for claim in draft.claims:
            if claim.result_id not in by_id:
                raise ModelRetry("Use the id of a retrieved evidence result. Do not invent or abbreviate its id.")
            try:
                fact(by_id[claim.result_id],claim.path)
            except (KeyError,IndexError,ValueError,TypeError):
                candidates=guided_answer(by_id[claim.result_id])['claims']
                candidates+=evidence_preview(by_id[claim.result_id],context).get('selected_frame_claims',[])
                paths=[c['path'] for c in candidates]
                raise ModelRetry(f"Invalid scalar claim {claim.path!r}. Remove it or use a returned scalar path. Valid checked candidates for this result: {paths}. Lists of notes cannot be scalar claims.") from None
        if draft.actions and not draft.claims:
            draft.interpretation='The requested display controls are ready. The browser will report whether they were applied; source observations remain unchanged.'
            for action in draft.actions:
                if action.options.get('kind') in {'set_view','focus_place','highlight'}:action.result_id=None
        if re.search(r"\d|\b(caused|extinguished|proved|confirmed perimeter|predicts)\b",draft.interpretation,re.I):
            raise ModelRetry('Rewrite the interpretation as a useful short explanation of the retrieved observations, without digits, dates, numerical measurements, or causal/forecast conclusions. Keep exact values and dates in the checked claim cards; do not replace the explanation with generic boilerplate.')
        return draft

    @agent.tool_plain
    def investigate(operation: str, context_overrides: dict | None = None, arguments: dict | None = None) -> dict:
        """Query stored evidence. Supported operations: archive_search, availability, observations, replay, research, calendar, harmonized, persistence, missingness, compare, sensitivity, exposure, validation, method, sources. Values in claims use JSON pointers into returned payload. Context overrides must describe the scientist's requested study; do not silently narrow it."""
        if cancel.is_set() or time.monotonic()>deadline:
            raise InterruptedError("Investigation stopped.")
        overrides=context_overrides or {}
        if unresolved_places and operation not in {"availability","method","sources"}:
            raise ModelRetry("The place name is unresolved. Ask the scientist for its geographic boundary and UTC dates before querying measurements. Do not use the current study for another location.")
        setup=dict(context)
        if overrides.get('case') and overrides['case']!=setup.get('case'):
            for key in ('bbox','start','end','year','month','day','as_of'):setup.pop(key,None)
        elif 'year' in overrides or 'month' in overrides:
            for key in ('case','start','end','as_of','day'):setup.pop(key,None)
        elif 'start' in overrides or 'end' in overrides:
            setup.pop('case',None);setup.pop('day',None)
        try:
            cfg=normalize_context({**setup,**overrides})
            if resolved_places and operation not in {'availability','method','sources'}:
                box=cfg['bbox']
                matches=any(p['bbox'][0]<=box[0]<box[2]<=p['bbox'][2] and p['bbox'][1]<=box[1]<box[3]<=p['bbox'][3] for p in resolved_places)
                if not matches:raise ModelRetry('The measurement boundary does not match the geographic place just requested. Use the resolver bounds explicitly, or clarify the intended boundary and dates. Never answer a new place question with the old study readings.')
            progress(operation)
            result=service.science.call(owner,operation,cfg,arguments,cancel,deadline)
        except ValueError as error:
            raise ModelRetry(str(error)+" Preserve the requested scope. Use replay for multi-month source summaries; research needs an explicit study_month argument or separate requested monthly intervals.") from None
        results.append(result)
        return evidence_preview(result,cfg)
    @agent.tool_plain
    def saved_evidence(result_id:str)->dict:
        """Retrieve evidence cited in an earlier turn of this scientist's notebook; re-check its release before comparison."""
        result=retrieved_evidence(result_id)
        results.append(result)
        return evidence_preview(result,context)
    @agent.tool_plain
    def inspect_selection(result_id: str, path: str) -> dict:
        """Read an actual selected cell or detection, even when outside the truncated tool preview. Return its original evidence paths for verified claims and annotations."""
        result=retrieved_evidence(result_id)
        if len(path)>200 or not path.startswith(("/frames/","/observations/","/cells/","/records/")):
            raise ModelRetry("Inspect a returned observation or cell object using its actual selection path.")
        try:
            cell=pointer(result["payload"],path)
        except (ValueError,KeyError,TypeError,IndexError):
            raise ModelRetry("The selected evidence path is unavailable. Ask the scientist to select an actual cell or record.") from None
        if not isinstance(cell,dict):
            raise ModelRetry("Choose a cell or observation object, not a list or scalar.")
        results.append(result)
        selected={"result_id":result_id,"path":path,"selected_observation":cell,"scalar_claim_paths":{key:path+"/"+key for key,value in cell.items() if type(value) in (int,float,str)},"context":result["context"],"note":"Readings describe the selected returned sample, not local fire causality or perimeter membership. A source detection count of zero is a returned cell count; null FRP is unavailable power. Neither implies an incomplete source export. Use the frame's product state for export completeness."}
        if result['operation']=='replay':
            frame_index=int(path.split('/')[2]) if path.startswith('/frames/') else next((i for i,f in enumerate(result['payload']['frames']) if f['date_utc']==cell.get('date')),None)
            if frame_index is not None:
                selected['source_frame_date']=result['payload']['frames'][frame_index]['date_utc']
                selected['frame_products']=result['payload']['frames'][frame_index]['products']
                selected['frame_products_path']=f'/frames/{frame_index}/products'
        return selected

    @agent.tool_plain
    def annotate_evidence(result_id:str,path:str,text:str)->dict:
        """Pin a brief descriptive interpretation to an actual returned cell/record. Use no digits, dates, numerical or causal claims in text; exact measurements stay in linked claim cards. Path must point to an actual geometric sample."""
        from .contracts import pointer
        from .annotations import validate_geometry
        result=retrieved_evidence(result_id)
        try:cell=pointer(result['payload'],path)
        except (ValueError,KeyError,TypeError,IndexError):
            raise ModelRetry('Annotate the exact returned cell or record path from the selected evidence. This path is unavailable.') from None
        if not isinstance(cell,dict) or len(text)>600:raise ModelRetry('Annotation requires a returned cell or record and a description under six hundred characters.')
        if re.search(r'\d|\b(caused|extinguished|proved|forecast)\b',text,re.I):raise ModelRetry('Remove every digit, date, numerical and causal claim from annotation text. Use a short descriptive label such as "MODIS reported this sample; compare the linked sensor readings." Put exact measurements in checked answer claims instead.')
        geometry={'type':'Polygon','coordinates':[cell['ring']]} if cell.get('ring') else {'type':'Point','coordinates':[cell.get('longitude',cell.get('lon')),cell.get('latitude',cell.get('lat'))]}
        annotation_context=dict(result['context'])
        if path.startswith('/frames/'):
            annotation_context['day']=result['payload']['frames'][int(path.split('/')[2])]['date_utc']
        elif cell.get('date'):
            annotation_context['day']=cell['date']
        elif cell.get('acquisition_utc'):
            annotation_context['day']=cell['acquisition_utc'][:10]
        try:geometry=validate_geometry(geometry)
        except (ValueError,TypeError):raise ModelRetry('Select an actual sample cell or detection with returned geometry before annotating it.') from None
        identifier=service.store.artifact(owner,'annotation',{'text':text,'context':annotation_context,'result_id':result_id,'path':path,'kind':'AI-assisted interpretation','geometry':geometry,'target':'observation-cell'})
        results.append(result)
        return {'annotation_id':identifier,'result_id':result_id,'path':path}
    @agent.tool_plain
    def annotate_figure(image_id:str,target:str)->dict:
        """Use OpenCV to outline a registered region in an attached figure. No measurements or locations are inferred from its pixels."""
        from .figures import annotate
        if cancel.is_set() or time.monotonic()>deadline:raise InterruptedError('Investigation stopped.')
        try:
            image=service.store.get_artifact(owner,image_id,'image')['body']
            if image['revision']!=context['revision']:raise ValueError('Attach a figure for the current view first.')
            value=annotate(image,target)
        except (ValueError,PermissionError) as error:raise ModelRetry(str(error)) from None
        identifier=service.store.artifact(owner,'annotated_figure',{**value,'image_id':image_id,'revision':context['revision']})
        annotated_figures.append(identifier)
        return {'figure_id':identifier,'caption':value['caption'],'target':target,'note':'Visual evidence callout only. Numerical conclusions still require source evidence.'}
    from .connectors import catalog,call
    approved=catalog()
    if approved:
        @agent.tool_plain
        def curated_research(connector:str,tool:str,arguments:dict)->dict:
            """Call only an operator-approved MCP reference or geocoding tool. External output cannot become stored fire measurements."""
            if cancel.is_set():raise InterruptedError('Investigation stopped.')
            return call(connector,tool,arguments)
    history=[{"question":a["body"].get("question"),"title":a["body"].get("title"),"context":a["body"].get("context"),"evidence_ids":a["body"].get("evidence_ids")} for a in reversed(service.store.artifacts(owner,"answer")[:6])]
    prompt=json.dumps({"question":message,"attached_figures":[{"id":r["id"],"caption":r["body"]["caption"],"regions":r["body"].get("regions",[])} for r in service.store.artifacts(owner,"image")[:2] if r["body"]["revision"]==context["revision"]] if images else [],"prepared_selection":prepared_selection,"prepared_evidence":[evidence_preview(r,context) for r in results],"recent_investigations":history,"context":context,"view":view,"selected_evidence":view.get("selection"),"destinations":list(DESTINATIONS),"visual_targets":__import__("fireatlas.assistant.presentation",fromlist=["TARGETS"]).TARGETS,"curated_connectors":[{"id":c["id"],"tools":c["tools"],"scope":c["scope"]} for c in approved]},allow_nan=False)
    inputs=[prompt]
    if images:
        from pydantic_ai import BinaryContent
        for data,mime in images:
            inputs.append(BinaryContent(data=data,media_type=mime,
                vendor_metadata={'detail':'low'} if config['provider']=='aiand' and config['analysis_depth']=='efficient' else None))
    # No automatic retries of an uncertain billed call. Its cost stays reserved.
    settings={"timeout":min(90,max(1,deadline-time.monotonic())),"max_tokens":config.get('max_tokens',1200)}
    if free_only:
        settings.update({'max_tokens':2400,'openrouter_models':routes,
                         'openrouter_provider':{'require_parameters':True,'max_price':{'prompt':0,'completion':0}},
                         'openrouter_reasoning':{'enabled':False},'extra_body':{'plugins':[]}})
    elif config['provider']=='aiand':settings.update({'openai_reasoning_effort':config['reasoning_effort'],'openai_store':False,'parallel_tool_calls':False})
    elif config["provider"]=="google": settings["google_thinking_config"]={"thinking_level":"LOW"}
    else:settings.update({"openai_reasoning_effort":"low","openai_store":False})
    from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
    try:
        # A checked figure accompanies successive tool calls. Its billed image
        # tokens need a separate bounded allowance, without changing USD caps.
        response=agent.run_sync(inputs,usage_limits=UsageLimits(request_limit=4 if free_only else 8,input_tokens_limit=30000 if images and not free_only else 20000,output_tokens_limit=6000,tool_calls_limit=12), model_settings=settings)
    except (UnexpectedModelBehavior,UsageLimitExceeded) as error:
        if prepared_selection and not cancel.is_set():
            chosen=prepared_selection;cards=[]
            for key in ('source_id','platform','acquisition_utc','modis_detections','viirs_detections','modis_frp_max_mw','viirs_frp_max_mw','frp_mw','confidence','longitude','latitude'):
                path=chosen['scalar_claim_paths'].get(key)
                if path:cards.append(fact(results[0],path))
            for source in ('MODIS_SP','VIIRS_SNPP_SP'):
                if chosen.get('frame_products_path'):cards.append(fact(results[0],chosen['frame_products_path']+'/'+source+'/label'))
            text='Recorded satellite sample. Inspect the linked sensor readings and source export status; this sample does not establish a fire perimeter or continuous coverage.'
            existing=any(r['body'].get('result_id')==chosen['result_id'] and r['body'].get('path')==chosen['path'] for r in service.store.artifacts(owner,'annotation'))
            if not existing:annotate_evidence(chosen['result_id'],chosen['path'],text)
            return {'title':'Selected observation evidence','summary':text,'kind':'Checked selected-sample workflow','claims':cards[:12],'evidence_ids':[chosen['result_id']],'actions':[],'limitations':[LIMITATION],'spoken_summary':text,'ai_wording_unavailable':True,'provider':config['provider'],'model':used_models[-1] if used_models else config['model'],'estimated_cost_usd':sum(call_costs)/1e6 if call_costs and all(c is not None for c in call_costs) else None}
        if unresolved_places and resolved_places and not cancel.is_set():
            text='Several geographic places matched. Choose the place below to move the camera; your study dates and observation boundary stay unchanged.'
            return {'title':'Choose the geographic place','summary':text,'kind':'Geographic clarification','places':resolved_places,'claims':[],'evidence_ids':[],'actions':[],'limitations':[],'spoken_summary':text,'provider':config['provider'],'model':used_models[-1] if used_models else config['model'],'estimated_cost_usd':sum(call_costs)/1e6 if call_costs and all(c is not None for c in call_costs) else None}
        if visual_requested and results and not unresolved_places and not cancel.is_set():
            from .presentation import VISUAL_KINDS
            evidence=next((r for r in reversed(results) if diagram_requested or r['operation'] in VISUAL_KINDS),None)
            if evidence:
                answer=guided_answer(evidence)
                answer.update({'kind':'Checked visual explanation','visualizations':[{'result_id':evidence['id'],'kind':'workflow' if diagram_requested else VISUAL_KINDS[evidence['operation']]}],
                    'summary':'The visual uses exact returned source values and their calculation units. Inspect a bar for its evidence path, and use the table to compare source status. Missing records do not establish no fire.',
                    'provider':config['provider'],'model':used_models[-1] if used_models else config['model'],'ai_wording_unavailable':True,
                    'estimated_cost_usd':sum(call_costs)/1e6 if call_costs and all(c is not None for c in call_costs) else None})
                return answer
        if preset and results and not cancel.is_set():
            evidence=results[0];answer=guided_answer(evidence)
            if preset=='missingness':
                complete=all(s['incomplete_export_days']==0 for s in evidence['payload']['summary'].values())
                answer['summary']=('Both source export requests are complete throughout this study. Dates without imported records are listed separately below. ' if complete else 'Incomplete source exports and dates without imported records are listed separately below. ')+'Neither state establishes no fire or clear satellite coverage. The daily status table is the authoritative record.'
            answer.update({'kind':'Checked archive workflow','provider':config['provider'],'model':used_models[-1] if used_models else config['model'],'analysis_depth':config.get('analysis_depth'),'ai_wording_unavailable':True,'estimated_cost_usd':sum(call_costs)/1e6 if call_costs and all(c is not None for c in call_costs) else None})
            return answer
        if isinstance(error,UsageLimitExceeded):raise ValueError('The question exceeded its bounded analysis allowance. Retrieved evidence is saved; no unsupported answer was published.') from None
        raise ValueError("The AI could not verify its answer against the retrieved records. No unchecked answer was published. Try a narrower question or use a stored-data task.") from None
    if cancel.is_set() or time.monotonic()>deadline:
        raise InterruptedError("Investigation stopped.")
    draft=response.output
    inference_metadata={"analysis_depth":config.get('analysis_depth'),
        "estimated_cost_usd":sum(call_costs)/1e6 if call_costs and all(c is not None for c in call_costs) else None,
        "price_basis":config.get('price_basis'),"inference_calls":len(used_models)}
    if draft.clarification:
        return {"title":"Clarify the study", "summary":draft.clarification,"kind":"AI clarification","places":resolved_places,"claims":[],"evidence_ids":[],"actions":[service.action(owner,a.destination,context,view,a.result_id,a.options) for a in draft.actions],"limitations":[],"spoken_summary":draft.clarification,"provider":config['provider'],"model":used_models[-1] if used_models else config['model'],"free_only":free_only,**inference_metadata}
    if not results and (draft.actions or annotated_figures):
        return {'title':draft.title,'summary':draft.interpretation,'kind':'AI display action','figure_ids':annotated_figures,'places':resolved_places,'claims':[], 'evidence_ids':[], 'actions':[service.action(owner,a.destination,context,view,a.result_id,a.options) for a in draft.actions], 'limitations':[], 'spoken_summary':draft.interpretation,'provider':config['provider'],'model':used_models[-1] if used_models else config['model'],**inference_metadata}
    if not results:
        raise ValueError("No scientific evidence was retrieved; no factual answer was published.")
    by_id={r["id"]:r for r in results}
    from .presentation import validate_visualization
    visualizations=[validate_visualization(by_id[v.result_id],v.kind) for v in draft.visualizations]
    cards=[]
    for claim in draft.claims:
        if claim.result_id not in by_id:
            raise ValueError("A claim referred to unavailable evidence.")
        cards.append(fact(by_id[claim.result_id],claim.path))
    # The free-form interpretation is visibly separated. Numerical prose is not accepted.
    summary=draft.interpretation
    if re.search(r"\d|\b(caused|extinguished|proved|confirmed perimeter|predicts)\b",summary,re.I):
        summary="The checked evidence is shown below. Inspect source status and method details before interpreting this pattern."
    actions=[]
    for action in draft.actions:
        if action.destination not in DESTINATIONS or action.result_id and action.result_id not in by_id:
            raise ValueError("Unsupported presentation action.")
        actions.append(service.action(owner,action.destination,context,view,action.result_id,action.options))
    # Numerical speech is composed from the same checked fields as the visible cards.
    spoken=" ".join(f"{c['label']}: {c['value']} {c['unit']}." for c in cards[:3])
    title=guided_answer(results[-1])['title'] if re.search(r'\d|\b(caused|proved|extinguished)\b',draft.title,re.I) else draft.title
    return {"title":title,"summary":summary,"kind":"AI-assisted interpretation","visualizations":visualizations,"figure_ids":annotated_figures,"places":resolved_places,"claims":cards,"evidence_ids":list(by_id),"actions":actions,"limitations":[LIMITATION],"spoken_summary":spoken+" "+LIMITATION,"provider":config["provider"],"model":used_models[-1] if used_models else config["model"],"models_used":list(dict.fromkeys(used_models)),"free_only":free_only,**inference_metadata}
