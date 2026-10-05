"""Curated layouts over frozen scientific snapshots; no generated measurements."""
from __future__ import annotations


def presentation_entries(operation, snapshot, snapshots, source):
    entries=[('map' if operation=='replay' else 'calendar' if operation=='harmonized' else 'chart','Captured visualization',snapshot,source)]
    if operation=='replay':
        entries += [('map','MODIS · occupied-cell heat',snapshot,'MODIS_SP'),('map','S-NPP VIIRS · occupied-cell heat',snapshot,'VIIRS_SNPP_SP')]
    if operation in {'replay','research','harmonized','calendar','missingness'}:
        entries.append(('chart','Daily activity · captured contract',snapshot,source))
    if operation=='replay':
        entries += [('chart','MODIS · daily occupied cells',snapshot,'MODIS_SP'),('chart','S-NPP VIIRS · daily occupied cells',snapshot,'VIIRS_SNPP_SP')]
    entries += [('timeline','Collected-export availability',sid,'joint') for sid in snapshots[1:]]
    entries += [('finding','Checked findings and interpretation',snapshot,source)]
    if operation in {'replay','research'}:entries.append(('observation','Original source records',snapshot,source))
    entries += [('note-question','Question and evidence boundary',None,'joint'),('chapter-frame','Editable presentation and workflow',None,'joint')]
    return entries


def decorate(ops, entries, context, payload, top, identifier):
    day=context['study_selection'].get('day') or context['active_view'].get('day')
    if not day and payload.get('frames'):
        # A named study preset explicitly requests a curated opening frame.
        # A submitted day always takes precedence over this documented choice.
        day=max(payload['frames'],key=lambda frame:frame['joint_cell_days'])['date_utc']
    maps=[]; charts=[]; evidence=[]; ending=[]
    for index,(kind,title,_,source) in enumerate(entries):
        card=ops[index]['card']
        card['transform']={'x':40+(index%3)*460,'y':top+(index//3)*410,'w':420,'h':350}
        card['display']['day']=day
        # Prepare bounded frozen schematics immediately for the curated board;
        # live map SDKs still require explicit activation.
        card['display']['preview_on_open']=True
        if kind=='map' and index>0:
            card['display'].update(preview='heat',temporal_mode='daily',scale='study-fixed')
        if kind=='note-question':
            card['text']='What do these dated observations support, and what remains unknown? Inspect source states, units and original rows. Detections do not establish ignition, a perimeter or continuous spread.'
        if kind=='chapter-frame':
            card['text']='Open Story for the six editable chapters. Open Workflow to inspect the registered operations and explicitly rerun them. Frozen evidence remains unchanged.'
        group=maps if kind in {'map','calendar'} else charts if kind=='chart' else ending if kind in {'note-question','chapter-frame'} else evidence
        group.append(card['id'])
    for name,title,ids in [('views','01 / Captured view and sensor maps',maps),('activity','02 / Activity through time',charts),('evidence','03 / Evidence, availability and findings',evidence),('story','04 / Questions, story and workflow',ending)]:
        if ids:ops.append({'op':'set_group','group':{'id':identifier('group-'+name),'title':title,'card_ids':ids}})
    return day


def parent_index(entries, index):
    kind,_,_,source=entries[index]
    if kind=='chart':
        return next((i for i,e in enumerate(entries[:index]) if e[0] in {'map','calendar'} and e[3]==source),0)
    if kind in {'finding','timeline'}:
        return next((i for i,e in enumerate(entries[:index]) if e[0]=='chart'),0)
    if kind in {'observation','note-question','chapter-frame'}:
        return next((i for i,e in enumerate(entries[:index]) if e[0]=='finding'),0)
    return 0
