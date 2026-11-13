"""Local Ollama configuration and compact scientific-tool selection."""
from __future__ import annotations
import os
from urllib.parse import urlsplit

DEFAULT_MODEL='ignis-scientist:latest'

def normalize_comparison_arguments(arguments):
    """Decode an alternate model JSON envelope without interpreting user text.

    Small tool models sometimes emit {annual_peaks: {places: ..., years: ...}}
    instead of the equivalent flat discriminator. All values still pass the
    tool's ordinary typed validation; ambiguous or conflicting shapes stay raw.
    """
    import json
    try:value=json.loads(arguments) if isinstance(arguments,str) else arguments
    except (ValueError,TypeError):return arguments
    if not isinstance(value,dict) or len(value)!=1:return arguments
    mode=next(iter(value))
    if mode not in {'regions','annual_peaks','saved'} or not isinstance(value[mode],dict):return arguments
    inner=value[mode]
    if 'mode' in inner and inner['mode']!=mode:return arguments
    return {**inner,'mode':mode}

def configuration():
    endpoint=os.getenv('FIREATLAS_LOCAL_URL','http://127.0.0.1:11434/v1').rstrip('/')
    url=urlsplit(endpoint)
    if url.scheme!='http' or url.hostname not in {'127.0.0.1','localhost','::1'} or url.username or url.password or url.query or url.fragment:
        raise ValueError('Local inference needs an HTTP loopback Ollama endpoint.')
    model=os.getenv('FIREATLAS_LOCAL_MODEL',DEFAULT_MODEL)
    return {'provider':'local','model':model,'vision_model':None,'configured':True,
            'base_url':endpoint,'input_price':0.0,'output_price':0.0,'free_only':False,
            'local':True,'max_tokens':450}

def tool_names(studio, message):
    """Avoid sending every Canvas/workflow tool to a small local model."""
    comparison = {'prepare_heatmap_comparison'} if studio and studio.get('whiteboard') and not studio.get('challenge') else set()
    from .comparison_research import research_question
    if comparison and research_question(message) and not (studio.get('selected_dataset') or studio.get('selected_source')):
        return comparison | ({'saved_evidence'} if studio.get('frozen_evidence_refs') else set())
    if conceptual_request(message,studio):return set()
    if studio and studio.get('challenge'):
        names={'saved_evidence','read_selected_board_notes','search_investigation_sources'}
        if studio.get('selected_dataset'):names.add('read_selected_table')
        if studio.get('selected_source'):names.add('read_selected_document_page')
        return comparison | names
    if studio and studio.get('selected_dataset') and not (studio.get('frozen_evidence_refs') and studio.get('dataset_scope')=='board'):
        from .board_views import requests_data_view,requests_related_view
        if requests_data_view(message) or requests_related_view(message):
            return comparison | {'prepare_board_view','show_related_candidate'}
        names={'read_selected_table'}
        import re
        if re.search(r'\b(scatter|correlation)\b',message,re.I):names.add('prepare_selected_scatter')
        if re.search(r'\b(grouped|average|mean|aggregate|bar chart)\b',message,re.I):names.add('compare_selected_groups')
        if re.search(r'\b(search|passage|pdf|sources)\b',message,re.I):names.add('search_investigation_sources')
        return comparison | names
    names={'investigate','search_public_research'}
    if studio:
        names|={'saved_evidence','read_selected_board_notes'}
        if studio.get('selected_source'):names.add('read_selected_document_page')
        if studio.get('selected_dataset'):
            names|={'read_selected_table','prepare_selected_scatter','compare_selected_groups'}
        if studio.get('whiteboard') and not studio.get('challenge'):
            names|={'prepare_board_view','show_related_candidate'}
        if any(word in message.lower() for word in ('search','source','passage','pdf')):names.add('search_investigation_sources')
        if any(word in message.lower() for word in ('location','near','where','boundary')):names.add('resolve_study_place')

    return comparison | names

async def prepare_tools(ctx, definitions):
    # Once one complete comparison is returned, the local model only needs to
    # explain it; omit tool schemas from that response step.
    if (not isinstance(ctx.deps,dict) or ctx.deps.get('local',True)) and any(getattr(part,'part_kind',None)=='tool-return' and getattr(part,'tool_name',None)=='prepare_heatmap_comparison'
           and isinstance(getattr(part,'content',None),dict) and part.content.get('operation')=='regional_comparison'
           for message in getattr(ctx,'messages',[]) for part in message.parts):
        return []
    allowed=ctx.deps['allowed'] if isinstance(ctx.deps,dict) else ctx.deps
    message=ctx.deps.get('message','').lower() if isinstance(ctx.deps,dict) else ''
    from dataclasses import replace
    descriptions={
        'prepare_heatmap_comparison':'Fetch comparable heatmaps. annual_peaks: one place, requested years (omit for last three). regions: two places, exact start/end dates. saved: selected FIRMS maps and places=[]. Shared scale and verified weather. Use requested places and dates.',
        'prepare_board_view':'Add a source-linked map/chart to the board. Park: case_id park-2024; omit bbox; explicit start/end/day. Kinds: heatmap, coordinates, satellites, calendar, factors, similar. Calendar counts places with heat detections, not satellite observation coverage or burned area. Similar uses one sensor and 2–14 reference days.',
        'show_related_candidate':'Fetch a visualization for a returned similar-pattern candidate. Copy result_id and candidate_index; default coordinates on its first date.',
        'investigate':'Calculate an available scientific operation in the requested context. Preserve source/date/boundary. Use method for definitions; use prepare_board_view for whiteboard figures.',
        'saved_evidence':'Read an owned existing scientific receipt by its exact result_id.',
    }
    prepared=[]
    import copy
    for definition in definitions:
        if definition.name not in allowed:continue
        schema=copy.deepcopy(definition.parameters_json_schema)
        if definition.name=='prepare_board_view':
            properties=schema.get('properties',{})
            if not any(word in message for word in ('similar','archive','historical')):
                for key in ('first_year','last_year','regions'):properties.pop(key,None)
            if 'analogu' not in message:properties.pop('cell_id',None)
        prepared.append(replace(definition,description=descriptions.get(definition.name,definition.description),parameters_json_schema=schema))
    return prepared


def comparison_brief(result):
    """Small-model reasoning context; full provenance remains in its receipt."""
    return {'id':result['id'],'operation':'regional_comparison','unit':'distinct occupied 1 km cells',
            'ranking_metric':result['payload']['rank_by'],
            'panels':[{key:panel[key] for key in ('label','year','day',result['payload']['rank_by'],'cell_delta','state')}
                      | {'weather':{key:value for key,value in panel['weather'].items() if key in
                                    {'status','air_temperature_max_c','rainfall_7d_mm','wind_max_kmh'}}}
                      for panel in result['payload']['panels']],
            'instruction':'These are satellite thermal detections, not human occupancy or demand. The comparison is ready. Give two short sentences describing equal/different recorded thermal counts; no significance test was performed. Suggest one concrete next check.'}


def conceptual_request(message, studio=None):
    """General explanations/opinions need no fabricated measurement receipt."""
    import re
    from .board_views import requests_data_view,requests_related_view
    from .comparison_research import research_question
    if research_question(message) or requests_data_view(message) or requests_related_view(message):return False
    if re.search(r'\d|\b(?:Park|Camp|Grove|today|yesterday|latest)\b|\bhow many\b',message,re.I):return False
    if studio and any(studio.get(key) for key in ('selected_source','frozen_evidence_refs','challenge')):return False
    if studio and studio.get('selected_dataset') and studio.get('dataset_scope')!='board':return False
    if re.search(r'\b(?:this|these|selected|current|recorded|measured|calculate|fetch|draw|show|plot|import|export)\b',message,re.I):return False
    return bool(re.search(r'\b(?:explain|why|how|what|which|should|could|opinion|hypothesis|your take|suggest|recommend|hello|hi|thanks)\b',message,re.I))


def readiness(config):
    """Check the installed profile, without loading weights or contacting a cloud."""
    import json,urllib.request
    endpoint=urlsplit(config['base_url'])
    url=endpoint._replace(path='/api/tags',query='',fragment='').geturl()
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url,timeout=1) as response:models=json.load(response).get('models',[])
        if any(row.get('name')==config['model'] for row in models):return True,None
        return False,'Install the local profile with python3 scripts/setup_local_assistant.py --activate.'
    except (OSError,ValueError):
        return False,'Start Ollama locally, then retry. No hosted-model fallback is enabled.'


def invalid_detection_coverage(text, results):
    """Detection-only figures cannot attest observation opportunity or burned area."""
    import re
    if not results or any(item.get('operation')=='exposure' for item in results):return False
    if not any(item.get('operation') in {'calendar','replay','observations','park_platforms','regional_comparison'} for item in results):return False
    for result in results:
        if result.get('operation')!='replay':continue
        day=result.get('context',{}).get('day')
        frame=next((item for item in result.get('payload',{}).get('frames',[]) if item.get('date_utc')==day),None)
        if frame and sum(product.get('state')=='complete_export' or product.get('detections',0)>0 for product in frame.get('products',{}).values())<2:
            for sentence in re.split(r'[.!?]',text.lower()):
                if re.search(r'\b(?:both|all) (?:sensors|satellites|platforms) (?:report|show|record|detect)',sentence) and not re.search(r"\b(?:not|cannot|can't|don't)\b",sentence):return True
    for sentence in re.split(r'[.!?]',text.lower()):
        if re.search(r"\b(?:not|no|cannot|can't|doesn't|isn't|aren't|without)\b",sentence):continue
        if any(item.get('operation')=='regional_comparison' for item in results) and re.search(r'\b(?:demand|traffic|population|human occupancy)\b',sentence) and not re.search(r'\b(?:hypothesis|may|might|could|possibly)\b',sentence):return True
        if re.search(r'\b(?:shows?|indicat\w*|measur\w*|represent\w*)\b',sentence) and re.search(r'area covered|observation coverage|burned area|fire perimeter|fire(?:.s)? (?:spread|intensity)',sentence):return True
        if re.search(r'\b(?:fire|burn\w*|affect\w*)\b',sentence) and re.search(
            r'\bwidespread\b|\b(?:fire|blaze) (?:was|is) (?:intense|severe)\b|\band (?:intense|severe)\b|'
            r'\b(?:most|majority|portion|percentage|fraction|extent) of (?:the |this )?(?:study |fire )?(?:area|region|park|land)\b',
            sentence,
        ):return True
    return False

SOURCE_EXPLANATION_INSTRUCTIONS = (
    "Act as a scientific research partner. Answer in at most 65 words: first the key pattern on the requested date, "
    "then one concrete next test using available sensors and dates. Keep each value attached to its correct sensor. "
    "records is the selected evidence; checked_comparisons gives verified higher/lower directions against the preceding recorded date. Use these directions rather than guessing a trend. For the next investigation, propose checking the acquisition times or shared detection locations of the available sensors, rather than rechecking the table. Counts are thermal detections, "
    "not fire intensity, smoke emissions or burned area. Different resolution and overpass timing can change counts. "
    "A documented product gap already explains a blank; choose available measurements for the next test. "
    "Use ordinary words without JSON, provenance IDs or generic disclaimers. The app supplies source links."
)
