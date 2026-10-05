"""Supported prompt shortcuts share the durable, owned Canvas recipe runner.

Only clear composition requests use these shortcuts. Other questions remain
with the model's existing tool selection; no measurements are inferred here.
"""
from __future__ import annotations
import copy
import re
from .errors import StudioError
from .orchestration import normalize
from ..assistant.contracts import normalize_context

PRESETS = [
    {'id':'curated-current', 'title':'Present this study', 'prompt':'Create a comprehensive presentation on Canvas from this study, with paired sensor heat maps, daily charts, an availability timeline, checked findings, original records, connected groups, an editable story and a runnable workflow.', 'recipe':'visualization_to_investigation', 'arguments':{'layout':'curated'}},
    *[{'id':'curated-'+case, 'title':title+' presentation', 'prompt':f'Create a curated {title} presentation on Canvas with paired heat maps, charts, evidence, an editable story and a runnable workflow.', 'recipe':'visualization_to_investigation', 'arguments':{'layout':'curated'}, 'case':case}
      for case,title in [('park-2024','Park Fire 2024'),('camp-2018','Camp Fire 2018'),('grove-2025','Grove Fire 2025')]],
    {'id':'checked-charts', 'title':'Add checked charts', 'prompt':'Add the supported daily activity charts and availability timeline from this study to Canvas.', 'recipe':'selection_to_chart_set', 'arguments':{}},
    {'id':'source-states', 'title':'Check observation gaps', 'prompt':'Check the source export states and processing gaps for this study.', 'operation':'missingness'},
    {'id':'source-rows', 'title':'Inspect original records', 'prompt':'Inspect the original satellite records for this study.', 'operation':'observations'},
]

def catalog():
    return {'schema':'fireatlas-jarvis-prompts-v1', 'presets':copy.deepcopy(PRESETS)}

def resolve(message, preset_id=None):
    if not isinstance(message,str) or len(message)>3000:
        raise StudioError('Use a prompt of at most 3,000 characters.')
    if preset_id:
        found=next((p for p in PRESETS if p['id']==preset_id),None)
        if not found:raise StudioError('Choose a supported prompt preset.')
        if message.strip()!=found['prompt']:raise StudioError('The edited prompt no longer matches that preset. Submit it as a custom question.')
        return copy.deepcopy(found)
    exact=next((p for p in PRESETS if p['prompt'].casefold()==message.strip().casefold()),None)
    if exact:return copy.deepcopy(exact)
    # Questions, negations, exports and requests for existing-object edits
    # must not unexpectedly insert a new presentation.
    imperative=re.sub(r'^\s*(?:(?:can|could|would) you\s+|i want you to\s+)','',message,flags=re.I)
    if not re.match(r'^\s*(?:please\s+)?(?:create|build|design|make|compose|prepare|package|send|move|add)\b',imperative,re.I):return None
    if re.search(r"\b(?:don't|do not|without|never|export|delete|remove|undo|replace)\b",message,re.I):return None
    if not re.search(r'\b(?:canvas|whiteboard)\b',message,re.I):return None
    if not re.search(r'\b(?:presentation|comprehensive|curated|workflow|heatmap|heat map|data|study|charts?|evidence|this|it)\b',message,re.I):return None
    result=copy.deepcopy(PRESETS[0])
    matches=[]
    for case,name in [('park-2024','Park'),('camp-2018','Camp'),('grove-2025','Grove')]:
        if re.search(r'\b'+name+r'(?:\s+Fire)?\b',message,re.I):matches.append(case)
    if len(matches)>1:return None
    if matches:result['case']=matches[0]
    return result

def submit(service, principal, body, key, assistant_owner=None, background=True):
    plan=resolve(body.get('message',''),body.get('preset_id'))
    if not plan:return {'handled':False}
    if plan.get('operation'):return {'handled':True,'operation':plan['operation']}
    captured=normalize(body.get('context'))
    if plan.get('case'):
        captured.update(study_selection=normalize_context({'case':plan['case']}),result_refs=[],selected_object_ids=[],release_identity='')
        captured['active_view']={'kind':'map','operation':'replay','source':'joint','visible_sources':['MODIS_SP','VIIRS_SNPP_SP'],'metric':'density','temporal_mode':'daily','scale':'study-fixed'}
    destination=body.get('destination')
    if destination is None:
        with service.store.connection() as db:
            boards=[b for b in service.list_documents(principal)['documents'] if service.store.role(db,principal,b['id']) in {'owner','editor'}]
        # No context, command, board, receipt or provider call is created until
        # the user selects an actual destination.
        return {'handled':True,'status':'needs_destination','question':'Which Canvas should receive this investigation?',
                'choices':[{'id':b['id'],'title':b['title'],'revision':b['revision']} for b in boards],
                'source_context':captured,'plan':{'recipe':plan['recipe'],'arguments':plan['arguments']}}
    if not isinstance(destination,dict) or destination.get('intent') not in {'new-board','append'} or (destination.get('intent')=='new-board' and destination.get('board_id')) or (destination.get('intent')=='append' and not destination.get('board_id')):
        raise StudioError('Choose a new Canvas or an editable existing Canvas.')
    captured['destination']=destination
    # Source card IDs belong to the captured source board, not the selected
    # destination. Receipts still carry their owned source document reference.
    original=(body.get('context') or {}).get('destination',{}).get('board_id')
    if destination.get('board_id')!=original:captured['selected_object_ids']=[]
    arguments={**plan['arguments'],**({'export_formats':body['export_formats']} if 'export_formats' in body else {})}
    command=service.commands.submit(principal,{'recipe':plan['recipe'],'context':captured,'arguments':arguments,
        **({'preview':body['preview']} if body.get('preview') and not plan.get('case') else {})},key,assistant_owner=assistant_owner,background=background)
    return {'handled':True,'status':'submitted','command':command}
