"""Durable deterministic recipes around the existing science and Studio stores.

Client view descriptors describe presentation only. Owned scientific receipts are
resolved on the server; capture never turns image pixels into measurements.
"""
from __future__ import annotations
import copy
import hashlib
import json
import secrets
import threading
from urllib.parse import urlsplit

from ..assistant.contracts import normalize_context, digest
from . import evidence, graph
from .errors import Conflict, StudioError, NotFound, Forbidden
from .store import dumps
from .workflow import validate

CONTEXT_SCHEMA = 'fireatlas-jarvis-context-v1'
RECIPES = {
    'visualization_to_investigation': {'effect': 'append-board', 'retry': 'checkpoint', 'charts': 4},
    'selection_to_chart_set': {'effect': 'append-board', 'retry': 'checkpoint', 'charts': 4},
    'findings_to_workflow': {'effect': 'append-board', 'retry': 'checkpoint'},
    'board_to_portable_exports': {'effect': 'prepare-export', 'retry': 'checkpoint'},
    'continue_investigation': {'effect': 'selected-objects', 'retry': 'checkpoint'},
}
ARGUMENTS={
    'visualization_to_investigation':{'export_formats','layout'}, 'selection_to_chart_set':{'export_formats'}, 'findings_to_workflow':{'export_formats'},
    'board_to_portable_exports':{'format','revision','scope'},
    'continue_investigation':{'action','workflow_id','node_id','metric','source','story_id','story_revision','chapter_ids','study'},
}
FOLLOW_ACTIONS={'arrange','pin','explain_node','show_data','run_workflow','replace_chart','change_view','arrange_chapters','apply_workflow','add_charts'}
STUDY_KEYS = {'year','month','bbox','as_of','series','day','distance_km','gap_days','region','layer','case','start','end','source','metric','view','context','revision','mask_id','scale'}
SURFACES = {'atlas','investigate','replay','assistant','research','evidence','studio','story','workflow','mcp'}
TERMINAL = {'completed','failed','cancelled','partial'}


def normalize(value):
    if not isinstance(value, dict) or value.get('schema') != CONTEXT_SCHEMA:
        raise StudioError('Use the versioned JARVIS context envelope.', code='invalid-context')
    if value.get('surface') not in SURFACES:
        raise StudioError('This surface cannot package an investigation.', code='unsupported-surface')
    for name in ('origin_instance_id', 'origin_tab_id'):
        graph.check_id(value.get(name), name)
    rev = value.get('context_revision')
    if type(rev) is not int or rev < 0:
        raise StudioError('Context revision must be a nonnegative integer.', code='invalid-context')
    study = value.get('study_selection')
    if not isinstance(study, dict):
        raise StudioError('Capture an applied scientific selection.', code='invalid-context')
    try:
        study = normalize_context({k:v for k,v in study.items() if k in STUDY_KEYS})
    except (ValueError, TypeError, KeyError) as error:
        raise StudioError(str(error), code='invalid-context') from None
    objects = value.get('selected_object_ids', [])
    if not isinstance(objects, list) or len(objects) > 100:
        raise StudioError('Select at most 100 objects.', code='invalid-context')
    for oid in objects:
        graph.check_id(oid)
    view = graph.small_json(value.get('active_view') or {}, 'Captured view', 16000)
    if set(view) - {'id','kind','pane','metric','temporal_mode','source','visible_sources','day','scale','domain','kernel','weighting','palette','opacity','camera','layers','calculation_contract','geometry','caption','operation','arguments','display_scope'}:
        raise StudioError('Unknown captured view setting.', code='invalid-context')
    refs = value.get('result_refs', [])
    if not isinstance(refs, list) or len(refs) > 8 or any(not isinstance(r,dict) or set(r)-{'id','document_id','snapshot_id'} for r in refs):
        raise StudioError('Use at most eight owned result references.', code='invalid-context')
    destination = value.get('destination') or {'intent':'new-board'}
    if not isinstance(destination,dict) or set(destination)-{'board_id','intent','revision'} or destination.get('intent') not in {'new-board','append','update-selection'}:
        raise StudioError('Choose a supported board destination.', code='invalid-context')
    if destination.get('board_id'): graph.check_id(destination['board_id'])
    route = value.get('return_destination', '')
    url = urlsplit(route)
    if not isinstance(route,str) or len(route)>5000 or url.scheme or url.netloc or route.startswith('//') or '..' in url.path.split('/'):
        raise StudioError('Return links must stay inside this application.', code='invalid-context')
    if url.fragment and (__import__('re').fullmatch(r'[A-Za-z0-9_./:%-]{1,256}',url.fragment) is None):raise StudioError('Return fragments must name a public section.')
    # URLs contain only public study/display selection, never notebook or owned object IDs.
    from urllib.parse import parse_qsl
    if any(k not in STUDY_KEYS | {'calendar_metric','scope','split','tab','section','context_version','analysis_month','guide','guide_step','origin_route','geometry'} for k,_ in parse_qsl(url.query)):
        raise StudioError('Return links contain unsupported private parameters.', code='invalid-context')
    return {'schema':CONTEXT_SCHEMA,'surface':value['surface'],'origin_instance_id':value['origin_instance_id'],
            'origin_tab_id':value['origin_tab_id'],'context_revision':rev,'study_selection':study,
            'active_view':view,'selected_object_ids':objects,'result_refs':refs,'destination':destination,
            'release_identity':str(value.get('release_identity') or '')[:128], 'return_destination':route,
            'source_document_revision':value.get('source_document_revision')}


def stable(command, role):
    return 'j_' + hashlib.sha256((command+':'+role).encode()).hexdigest()[:30]


class Commands:
    def __init__(self, service):
        self.service, self.store = service, service.store
        self.lock = threading.RLock()
        self.active = {}
        # No model request is made here. Interrupted deterministic commands remain resumable.
        with self.store.connection(write=True) as db:
            db.execute("UPDATE commands SET status='partial',error='Server restarted; resume the saved command.' WHERE status NOT IN ('completed','partial','failed','cancelled','awaiting_view_ack')")

    def context(self, principal, value):
        body = normalize(value)
        destination = body['destination'].get('board_id')
        if destination:
            with self.store.connection() as db: self.store.require(db, principal, destination, 'editor')
        with self.store.connection(write=True) as db:
            old = db.execute('SELECT * FROM studio_contexts WHERE principal_id=? AND instance_id=?', (principal,body['origin_instance_id'])).fetchone()
            if old and (body['context_revision'] < old['revision'] or (body['context_revision']==old['revision'] and old['body']!=dumps(body))):
                raise Conflict('This submitting instance has a newer context.', code='stale-context')
            db.execute('INSERT OR REPLACE INTO studio_contexts VALUES(?,?,?,?,?,?)',
                       (principal,body['origin_instance_id'],body['origin_tab_id'],body['context_revision'],dumps(body),self.store.clock()))
        return body

    def get(self, principal, command):
        with self.store.connection() as db:
            row = db.execute('SELECT * FROM commands WHERE id=? AND principal_id=?', (command,principal)).fetchone()
            steps = db.execute('SELECT name,input_hash,output,created FROM command_steps WHERE command_id=? ORDER BY created', (command,)).fetchall()
        if not row: raise NotFound('Command not found.')
        return {k:json.loads(row[k]) if k in {'context','arguments','outputs'} else row[k] for k in row.keys() if k not in {'principal_id','request_key'}} | {
            'steps':[dict(s) | {'output':json.loads(s['output'])} for s in steps],
            'message': 'Saved; open board to continue.' if row['status']=='awaiting_view_ack' else row['error'] or ('Saved operation completed.' if row['status']=='completed' else row['phase'].replace('_',' '))}

    def submit(self, principal, body, key, assistant_owner=None, background=True):
        if not isinstance(key,str) or not 1 <= len(key) <= 160: raise StudioError('A command requires an idempotency key.')
        recipe = body.get('recipe')
        if recipe not in RECIPES: raise StudioError('Choose a registered recipe.')
        context = normalize(body.get('context'))
        args = graph.small_json(body.get('arguments') or {}, 'Recipe arguments', 16000)
        if set(args)-ARGUMENTS[recipe]:raise StudioError('Unknown typed recipe argument.')
        if 'layout' in args and args['layout'] != 'curated':raise StudioError('Choose the supported curated layout.')
        if 'export_formats' in args and (not isinstance(args['export_formats'],list) or not 1<=len(args['export_formats'])<=5 or len(set(args['export_formats']))!=len(args['export_formats']) or any(f not in {'native','excalidraw','svg','png','pdf'} for f in args['export_formats'])):
            raise StudioError('Choose up to five distinct supported local export formats.')
        if recipe=='continue_investigation' and args.get('action') not in FOLLOW_ACTIONS:raise StudioError('Choose a supported follow-up action.')
        if recipe=='board_to_portable_exports' and not context['destination'].get('board_id'):raise StudioError('Choose an existing saved board for export.')
        request_hash = digest({'recipe':recipe,'context':context,'arguments':args,'preview':body.get('preview')})
        with self.store.connection() as db:
            old = db.execute('SELECT id,request_hash FROM commands WHERE principal_id=? AND request_key=?',(principal,key)).fetchone()
        if old:
            if old['request_hash'] != request_hash: raise Conflict('This request key belongs to another command.',code='idempotency-conflict')
            return self.get(principal,old['id'])
        if context['destination'].get('board_id') and context['selected_object_ids']:
            doc=self.store.get_document(principal,context['destination']['board_id'])
            captured=context.get('source_document_revision')
            if type(captured) is not int: raise StudioError('Capture the source document revision for selected objects.')
            if any(i not in doc['state']['cards'] or doc['object_revisions'].get('card:'+i,0)>captured for i in context['selected_object_ids']):
                raise Conflict('A selected object changed after capture.',code='stale-object')
        self.context(principal,context)
        # Captured receipts must already be owned; resolve before creating a worker/checkpoint.
        refs=[]
        for ref in context['result_refs']:
            if ref.get('document_id') and ref.get('snapshot_id'):
                receipt=self.service.snapshot_receipt(principal,ref['document_id'],ref['snapshot_id'])['receipt']
            elif assistant_owner and self.service.assistant:
                receipt=self.service.assistant.store.get_artifact(assistant_owner,ref['id'],'evidence')['body']
            else:
                receipt=self.store.get_artifact(principal,ref['id'],'evidence')['body']
            if normalize_context(receipt['context']) != context['study_selection']:
                # Revision is a UI guard, not a scientific selection.
                presentation = {'revision','day','source','metric','view','scale','layer'} if receipt['operation']=='replay' else {'revision'}
                if {k:v for k,v in receipt['context'].items() if k not in presentation} != {k:v for k,v in context['study_selection'].items() if k not in presentation}:
                    raise Conflict('The saved result does not match the captured study.',code='incompatible-result')
            if context['release_identity'] and receipt['release_id'] != context['release_identity']:
                raise Conflict('The captured result has another release.',code='stale-result')
            refs.append(receipt)
        preview=body.get('preview')
        if preview is not None:
            import base64
            if not isinstance(preview,dict) or preview.get('mime')!='image/png': raise StudioError('Captured previews must be PNG.')
            try: raw=base64.b64decode(preview['data'],validate=True)
            except (ValueError,KeyError): raise StudioError('Invalid preview PNG.') from None
            if len(raw)>1_500_000 or not raw.startswith(b'\x89PNG\r\n\x1a\n'): raise StudioError('Preview exceeds the existing PNG asset limit.')
        cid='cmd_'+secrets.token_hex(12)
        with self.store.connection(write=True) as db:
            now=self.store.clock()
            try:
                db.execute('INSERT INTO commands VALUES(?,?,?,?,?,?,?,?,?,?,?,0,?,?)',
                           (cid,principal,key,request_hash,recipe,dumps(context),dumps(args),'accepted','accepted','{}',None,now,now))
            except __import__('sqlite3').IntegrityError:
                old=db.execute('SELECT id,request_hash FROM commands WHERE principal_id=? AND request_key=?',(principal,key)).fetchone()
                if not old or old['request_hash']!=request_hash: raise Conflict('Conflicting command key.')
                cid=old['id']
            for i,receipt in enumerate(refs):
                rid=stable(cid,'receipt-'+str(i))
                db.execute('INSERT OR IGNORE INTO science_results VALUES(?,?,?,?,?,?)',(rid,principal,'evidence',receipt['sha256'],dumps(receipt),now))
            db.execute('INSERT OR IGNORE INTO command_steps VALUES(?,?,?,?,?)',(cid,'capture',request_hash,dumps({'results':[stable(cid,'receipt-'+str(i)) for i in range(len(refs))],'preview':preview}),now))
        self.start(principal,cid,background)
        return self.get(principal,cid)

    def start(self, principal, cid, background=True):
        with self.lock:
            if cid in self.active: return
            flag=threading.Event(); self.active[cid]=flag
        if background: threading.Thread(target=self.execute,args=(principal,cid,flag),daemon=True,name='studio-recipe').start()
        else: self.execute(principal,cid,flag)

    def step(self, cid, name):
        with self.store.connection() as db:
            row=db.execute('SELECT output FROM command_steps WHERE command_id=? AND name=?',(cid,name)).fetchone()
        return json.loads(row['output']) if row else None

    def checkpoint(self,cid,name,value,identity=None):
        with self.store.connection(write=True) as db:
            row=db.execute('SELECT cancel FROM commands WHERE id=?',(cid,)).fetchone()
            if row['cancel']: raise InterruptedError('Command cancelled.')
            db.execute('INSERT OR REPLACE INTO command_steps VALUES(?,?,?,?,?)',(cid,name,digest(identity or value),dumps(value),self.store.clock()))

    def update(self,cid, status, outputs=None,error=None):
        with self.store.connection(write=True) as db:
            row=db.execute('SELECT cancel,outputs FROM commands WHERE id=?',(cid,)).fetchone()
            if row['cancel'] and status!='cancelled': raise InterruptedError('Command cancelled.')
            merged={**json.loads(row['outputs']),**(outputs or {})}
            db.execute('UPDATE commands SET status=?,phase=?,outputs=?,error=?,updated=? WHERE id=?',
                       (status,status,dumps(merged),error,self.store.clock(),cid))

    def execute(self,principal,cid,flag):
        try:
            command=self.get(principal,cid)
            if command['cancel']: return
            context=command['context']; args=command['arguments']; recipe=command['recipe']
            if recipe=='board_to_portable_exports':
                job=self.step(cid,'export')
                if not job:
                    job=self.service.portability.submit(principal,context['destination'].get('board_id'),args,key=cid)
                    self.checkpoint(cid,'export',job)
                self.update(cid,'preparing_results',{'export_job_id':job['id']})
                import time
                deadline=time.monotonic()+160
                while job['status'] in {'queued','preparing'}:
                    if flag.is_set() or self.get(principal,cid)['cancel']:raise InterruptedError('Command cancelled.')
                    if time.monotonic()>deadline:raise StudioError('Export preparation continues. Read the saved export job.')
                    time.sleep(.25);job=self.service.portability.get(principal,job['id'])
                if job['status']!='completed':raise StudioError(job.get('error') or 'Export preparation failed.')
                self.update(cid,'completed',{'export_job_id':job['id'],'download':job['download']}); return
            destination=self.step(cid,'destination')
            if not destination:
                self.update(cid,'capturing')
                did=context['destination'].get('board_id')
                if did: document=self.store.get_document(principal,did)
                else: document=self.store.create_document(principal,('Investigation · '+str(context['study_selection'].get('case') or context['study_selection'].get('region') or 'captured study'))[:120],{'context':context['study_selection']},cid)
                destination={'document_id':document['id']}; self.checkpoint(cid,'destination',destination)
            did=destination['document_id']
            self.update(cid,'capturing',{'document_id':did,'return_destination':context['return_destination']})
            if recipe=='continue_investigation' and args.get('action') in {'arrange','pin','explain_node','show_data','run_workflow','replace_chart','change_view','arrange_chapters','apply_workflow'}:
                self.follow(principal,cid,did,context,args); return
            prepared=self.step(cid,'prepared')
            if not prepared:
                self.update(cid,'preparing_results')
                capture=self.step(cid,'capture'); receipts=[self.store.get_artifact(principal,r,'evidence')['body'] | {'id':r} for r in capture['results']]
                primary=context['active_view'].get('operation') or ('harmonized' if context['active_view'].get('calculation_contract')=='harmonized' else 'replay')
                if recipe=='findings_to_workflow' and not receipts:
                    doc=self.service.get_document(principal,did)
                    for oid in context['selected_object_ids']:
                        snap=doc['snapshots'].get(doc['state']['cards'][oid].get('snapshot_id'))
                        if snap: receipts.append(self.service.snapshot_receipt(principal,did,snap['id'])['receipt'] | {'id':snap['result_id']})
                if not receipts:
                    receipt=self.service.science.call(principal,primary,context['study_selection'],context['active_view'].get('arguments') or {},flag)
                    receipts=[receipt]
                expected=context['active_view'].get('arguments',{}).get('expected_result_sha256')
                if expected and receipts[0]['payload'].get('meta',{}).get('result_sha256')!=expected:
                    raise Conflict('The displayed harmonized result changed. Recapture its current result; the selection was retained.',code='stale-result')
                operation=receipts[0]['operation']
                omissions=[]
                if operation not in {'replay','research','harmonized','calendar','missingness'}:
                    omissions.append({'artifact':'daily activity charts','reason':'This evidence contract does not provide a compatible daily activity series.'})
                # Availability is a distinct contract; retain its label instead of treating it as fire activity.
                if operation!='missingness' and recipe!='findings_to_workflow':
                    try:
                        availability=self.service.science.call(principal,'missingness',context['study_selection'],{},flag)
                        if availability['release_id']!=receipts[0]['release_id']:raise StudioError('Availability has another release; frozen source retained.')
                        receipts.append(availability)
                    except (ValueError,StudioError,TimeoutError) as e: omissions.append({'artifact':'availability','reason':str(e)})
                snaps=[]
                for i,receipt in enumerate(receipts[:4]):
                    release=self.service.science.release()
                    if release.get('id') != receipt['release_id']:
                        release={'manifest':{}}
                    snap=evidence.build_snapshot(receipt,release, {'operation':receipt['operation'],'context':receipt['context'],'arguments':{}})
                    if not release.get('manifest'):
                        snap['dependency_hashes']={};snap['dependency_status']='Original dependency manifest unavailable; original receipt and release identity retained.'
                    snap=self.store.add_snapshot(principal,did,snap,stable(cid,'snapshot-'+str(i))); snaps.append(snap['id'])
                prepared={'snapshots':snaps,'primary_operation':operation,'omissions':omissions,'trace':[{'operation':r['operation'],'context':r['context'],'result_id':r['id'],'receipt_sha256':r['sha256'],'execution':'saved-result' if i<len(capture['results']) else 'recorded-execution'} for i,r in enumerate(receipts)]}
                self.checkpoint(cid,'prepared',prepared)
            self.update(cid,'building_workflow')
            workflow=self.step(cid,'workflow')
            if not workflow:
                nodes=[]
                for i,sid in enumerate(prepared['snapshots']):
                    snap=self.store.get_snapshot(principal,did,sid)
                    # Frozen node preserves the old result; operation node reruns on the current board study.
                    nodes += [{'id':f'frozen{i}','type':'evidence_input','label':'Captured evidence','params':{'snapshot_id':sid}},
                              {'id':f'calculate{i}','type':'operation','label':f"Rerun {snap['operation']}",'params':{'operation':snap['operation'],'context':context['study_selection'],'arguments':{}}},
                              {'id':f'card{i}','type':'card_output','label':'Prepare checked card','inputs':{'content':f'calculate{i}'},'params':{'card_type':'chart','title':f"{snap['operation']} result"}}]
                nodes.append({'id':'insert','type':'board_insert','label':'Insert new frozen result cards','inputs':{'items':[f'card{i}' for i in range(len(prepared['snapshots']))]}})
                nodes.append({'id':'export','type':'portable_export','label':'Prepare whole-board native export','inputs':{'board':'insert'},'params':{'format':'native'}})
                definition={'nodes':nodes}; validate(definition)
                wid=stable(cid,'workflow')
                with self.store.connection(write=True) as db:
                    self.store.require(db,principal,did,'editor'); now=self.store.clock()
                    db.execute('INSERT OR IGNORE INTO workflows VALUES(?,?,?,?,?,?,?)',(wid,did,principal,1,dumps(definition),now,now))
                workflow={'id':wid,'definition':definition,'label':'Runnable workflow'}; self.checkpoint(cid,'workflow',workflow)
            insertion=self.step(cid,'insertion')
            if not insertion:
                self.update(cid,'applying_board')
                doc=self.store.get_document(principal,did)
                base=context['destination'].get('revision') or doc['revision']
                top=max((c['transform']['y']+c['transform']['h'] for c in doc['state']['cards'].values()),default=-20)+60
                source_view=context['active_view']; snapshot=self.store.get_snapshot(principal,did,prepared['snapshots'][0])
                entries=[]
                if recipe not in {'selection_to_chart_set','findings_to_workflow'}:
                    entries.append(('map' if prepared['primary_operation']=='replay' else 'calendar' if prepared['primary_operation']=='harmonized' else 'source-evidence' if prepared['primary_operation']=='validation' else 'chart','Captured visualization',snapshot['id'], source_view.get('source') or context['study_selection']['source']))
                if prepared['primary_operation'] in {'replay','research','harmonized','calendar','missingness'}:
                    entries.append(('chart','Daily activity · captured contract',snapshot['id'],context['study_selection']['source']))
                if prepared['primary_operation']=='replay':
                    for source in ('MODIS_SP','VIIRS_SNPP_SP'): entries.append(('chart',('MODIS' if source=='MODIS_SP' else 'S-NPP VIIRS')+' · daily occupied cells',snapshot['id'],source))
                for sid in prepared['snapshots'][1:]: entries.append(('timeline','Collected-export availability',sid,'joint'))
                entries.append(('finding','Checked findings',snapshot['id'],context['study_selection']['source']))
                entries.append(('note-question','Question to investigate',None,'joint'))
                if args.get('layout')=='curated':
                    from .composition import presentation_entries
                    entries=presentation_entries(prepared['primary_operation'],snapshot['id'],prepared['snapshots'],source_view.get('source') or context['study_selection']['source'])
                ops=[]
                preview=self.step(cid,'capture').get('preview'); aid=None
                if preview:
                    import base64
                    asset_step=self.step(cid,'preview_asset')
                    if not asset_step:
                        asset_step=self.service.add_asset(principal,did,base64.b64decode(preview['data']), 'User-approved scientific display preview', 'Captured FireAtlas schematic; original records remain authoritative',identifier=stable(cid,'preview-asset'))
                        self.checkpoint(cid,'preview_asset',asset_step)
                    aid=asset_step['id']
                for i,(kind,title,sid,source) in enumerate(entries):
                    view={**source_view,'source':source} if i==0 else {}
                    card={'id':stable(cid,'card-'+str(i)),'type':kind,'title':title,'text':source_view.get('caption','')[:4000] if i==0 else 'Frozen evidence. Inspect the cited result and its scope.',
                          'snapshot_id':sid,'asset_id':aid if i==0 else None,
                          'display':{'day':context['study_selection'].get('day'),'source':source,'captured_view':view, **({'preview':'heat'} if kind=='map' and not aid else {})},
                          'provenance':{'command_id':cid,'workflow_id':workflow['id'],'return_destination':context['return_destination']},
                          'follow':'pinned','pinned_study':{'context':{**context['study_selection'],'source':source}},
                          'transform':{'x':40+(i%3)*410,'y':top+(i//3)*310,'w':380,'h':270}}
                    ops.append({'op':'add_card','card':card})
                if args.get('layout')=='curated':
                    from .composition import decorate
                    receipt=self.service.snapshot_receipt(principal,did,snapshot['id'])['receipt']
                    decorate(ops,entries,context,receipt['payload'],top,lambda role:stable(cid,role))
                if not doc['state'].get('workflow_id'):ops.append({'op':'set_workflow','id':workflow['id']})
                for i in range(1,len(entries)):
                    parent=0
                    if args.get('layout')=='curated':
                        from .composition import parent_index
                        parent=parent_index(entries,i)
                    ops.append({'op':'connect','connection':{'id':stable(cid,'link-'+str(i)),'source':stable(cid,'card-'+str(parent)),'target':stable(cid,'card-'+str(i)),'kind':'context'}})
                self.store.apply_transaction(principal,did,{'base_revision':base,'allow_merge':True,'ops':ops,'group_id':cid},cid,_command=cid)
                insertion=self.step(cid,'insertion')
            if args.get('layout')=='curated' and not self.step(cid,'presentation_story'):
                from .story import default_story, clean_story, adapt_narration
                doc=self.store.get_document(principal,did)
                card_ids=[oid for oid in doc['state']['order'] if doc['state']['cards'][oid]['provenance'].get('command_id')==cid]
                body=default_story(doc['state'],'Curated investigation · '+str(context['study_selection'].get('case') or context['study_selection'].get('region') or 'selected study'),card_ids)
                body['audience']='presenter';body['target_duration_seconds']=90
                body['chapters']=[{**adapt_narration(chapter,'presenter'),'duration_seconds':15} for chapter in body['chapters']]
                maps=[oid for oid in card_ids if doc['state']['cards'][oid]['type']=='map']
                if maps:
                    body['chapters'][0]['visible_cards']=maps[:3]
                    body['chapters'][0]['evidence_cards']=maps[:3]
                body=clean_story(body);story_id=stable(cid,'story')
                if flag.is_set():raise InterruptedError('Command cancelled.')
                with self.store.connection(write=True) as db:
                    self.store.require(db,principal,did,'editor');now=self.store.clock()
                    if not db.execute('SELECT 1 FROM stories WHERE id=?',(story_id,)).fetchone() and db.execute('SELECT COUNT(*) FROM stories WHERE document_id=?',(did,)).fetchone()[0]>=10:
                        raise StudioError('This Canvas already has ten stories. The saved cards remain available; choose another Canvas for another presentation.',code='story-limit')
                    db.execute('INSERT OR IGNORE INTO stories VALUES(?,?,?,?,?,?,?)',(story_id,did,principal,body['title'],1,now,now))
                    db.execute('INSERT OR IGNORE INTO story_revisions VALUES(?,?,?,?,NULL,NULL,?,?)',(story_id,1,doc['revision'],dumps(body),principal,now))
                self.service.resolve_story(principal,story_id)
                self.checkpoint(cid,'presentation_story',{'id':story_id,'revision':1})
                self.update(cid,'saved',{'story_id':story_id})
            package={'schema':'fireatlas-investigation-package-v1','id':stable(cid,'package'),'command_id':cid,'source_context':context,
                     'source_view':context['active_view'],'evidence_refs':prepared['snapshots'],'cards':insertion['object_ids'],'workflow':workflow,
                     'operation_trace':prepared['trace'],'omissions':prepared['omissions'],'document_id':did,'revision':insertion['revision'],
                     **({'story':self.step(cid,'presentation_story')} if args.get('layout')=='curated' else {})}
            with self.store.connection(write=True) as db:
                db.execute('INSERT OR IGNORE INTO investigation_packages VALUES(?,?,?,?,?,?)',(package['id'],cid,principal,did,dumps(package),self.store.clock()))
            if args.get('export_formats'):
                import time
                jobs=[]
                for fmt in args['export_formats']:
                    step='portable_export_'+fmt;job=self.step(cid,step)
                    if not job:
                        job=self.service.portability.submit(principal,did,{'revision':insertion['revision'],'format':fmt},key=cid+':'+fmt)
                        self.checkpoint(cid,step,{'id':job['id']})
                    current=self.service.portability.get(principal,job['id'])
                    if current['status']=='failed':current=self.service.portability.retry(principal,job['id'])
                    self.update(cid,'preparing_exports',{'package_id':package['id'],'workflow_id':workflow['id'],'export_job_ids':jobs+[job['id']]})
                    for _ in range(320):
                        if flag.is_set():raise InterruptedError('Command cancelled.')
                        current=self.service.portability.get(principal,job['id'])
                        if current['status'] not in {'queued','preparing'}:break
                        time.sleep(.5)
                    if current['status']!='completed':raise StudioError(current.get('error') or 'Export is still preparing. Resume this saved command.')
                    jobs.append(job['id'])
            self.update(cid,'awaiting_view_ack',{'package_id':package['id'],'workflow_id':workflow['id'],'return_destination':context['return_destination']})
        except InterruptedError:
            self.update(cid,'cancelled',error='Cancelled; previously saved evidence is retained.')
        except Exception as error:
            try: self.update(cid,'partial' if self.step(cid,'destination') else 'failed',error=str(error)[:500])
            except InterruptedError: self.update(cid,'cancelled')
        finally:
            with self.lock: self.active.pop(cid,None)

    def follow(self,principal,cid,did,context,args):
        doc=self.service.get_document(principal,did); ids=context['selected_object_ids']; action=args['action']
        if action=='explain_node':
            wf=self.service.get_workflow(principal,args['workflow_id'])
            if wf['document_id']!=did: raise Forbidden('Workflow belongs to another board.')
            node=next((n for n in wf['definition']['nodes'] if n['id']==args.get('node_id')),None)
            if node is None: raise StudioError('Select a saved workflow node.')
            self.update(cid,'completed',{'node':node,'execution_label':'Runnable definition; recorded outputs are separate.'});return
        if action=='show_data':
            if len(ids)!=1: raise StudioError('Select one evidence card.')
            snap=doc['state']['cards'][ids[0]].get('snapshot_id')
            if not snap: raise StudioError('This card has no frozen evidence.')
            self.update(cid,'completed',{'snapshot_id':snap,'document_id':did});return
        if action=='run_workflow':
            wf=self.service.get_workflow(principal,args['workflow_id'])
            if wf['document_id']!=did: raise Forbidden('Workflow belongs to another board.')
            old=self.step(cid,'workflow_run')
            if not old:
                old=self.service.run_workflow(principal,wf['id'],run_id=stable(cid,'workflow-run'));self.checkpoint(cid,'workflow_run',old)
            self.update(cid,'completed',{'run_id':old['id']});return
        if action=='apply_workflow':
            source=self.service.get_workflow(principal,args['workflow_id'])
            if source['document_id']!=did: raise Forbidden('Workflow belongs to another board.')
            from ..assistant.contracts import normalize_context
            study=normalize_context(args.get('study') or {})
            new=self.store.create_document(principal,'Workflow applied to '+str(study.get('case') or study.get('region') or 'another study'),{'context':study},cid+':study')
            wid=stable(cid,'applied-workflow')
            # Frozen references retain the captured source; rerunnable operation nodes use the explicit new study.
            definition=copy.deepcopy(source['definition']);definition['nodes']=[n for n in definition['nodes'] if n['type']!='evidence_input']
            for node in definition['nodes']:
                if node['type']=='operation':node.setdefault('params',{})['context']=study
            validate(definition)
            with self.store.connection(write=True) as db:
                now=self.store.clock();db.execute('INSERT OR IGNORE INTO workflows VALUES(?,?,?,?,?,?,?)',(wid,new['id'],principal,1,dumps(definition),now,now))
            result=self.service.run_workflow(principal,wid,run_id=stable(cid,'applied-run'))
            self.update(cid,'completed',{'new_document_id':new['id'],'workflow_id':wid,'run_id':result['id'],'message':'New run on the explicit study. The captured investigation is unchanged.'});return
        if action=='arrange_chapters':
            saved=self.service.get_story(principal,args['story_id'])
            if saved['document_id']!=did:raise Forbidden('Story belongs to another board.')
            order=args.get('chapter_ids')
            if not isinstance(order,list) or len(order)!=len(set(order)) or set(order)!={c['id'] for c in saved['body']['chapters']}:raise StudioError('Supply every existing chapter exactly once.')
            old=self.step(cid,'story_order')
            if not old:
                body=copy.deepcopy(saved['body']);lookup={c['id']:c for c in body['chapters']};body['chapters']=[lookup[c] for c in order]
                updated=self.service.update_story(principal,saved['id'],{'expected_revision':args.get('story_revision'),'story':body},key=cid)
                self.checkpoint(cid,'story_order',{'story_id':saved['id'],'revision':updated['revision'],'inverse':saved['body']})
            self.update(cid,'completed',{'story_id':saved['id']});return
        if not ids or any(i not in doc['state']['cards'] for i in ids): raise StudioError('Choose existing cards.')
        ops=[]
        for i,oid in enumerate(ids):
            if action=='arrange': ops.append({'op':'move_card','id':oid,'transform':{**doc['state']['cards'][oid]['transform'],'x':40+(i%3)*410,'y':40+(i//3)*310}})
            elif action=='pin': ops.append({'op':'update_card','id':oid,'patch':{'follow':'pinned','pinned_study':{'context':context['study_selection']},'display':{**doc['state']['cards'][oid]['display'],'day':context['study_selection']['day']}}})
            elif action=='change_view':
                metric=args.get('metric','density');source=args.get('source','joint')
                if doc['state']['cards'][oid]['type']!='map' or metric not in {'density','persistence','frp'} or source not in {'joint','MODIS_SP','VIIRS_SNPP_SP'} or metric=='frp' and source=='joint':raise StudioError('Choose a compatible map statistic and one sensor for native FRP.')
                card=doc['state']['cards'][oid];selection=copy.deepcopy(card.get('pinned_study') or doc['state']['study']);selection['context'].update(metric=metric,source=source)
                ops.append({'op':'update_card','id':oid,'patch':{'asset_id':None,'follow':'pinned','pinned_study':selection,'display':{'day':context['study_selection']['day'],'source':source,**({'preview':'heat'} if metric=='density' else {})}}})
            elif action=='replace_chart':
                if doc['state']['cards'][oid]['type']!='chart':raise StudioError('Select a chart to change its displayed source.')
                source=args.get('source','joint')
                if source not in {'joint','MODIS_SP','VIIRS_SNPP_SP'}: raise StudioError('Choose a supported source.')
                ops.append({'op':'update_card','id':oid,'patch':{'display':{**doc['state']['cards'][oid]['display'],'source':source}}})
        prior=self.step(cid,'insertion')
        if not prior:
            self.store.apply_transaction(principal,did,{'base_revision':context['destination'].get('revision') or doc['revision'],'allow_merge':True,'ops':ops,'group_id':cid},cid,_command=cid)
        self.update(cid,'awaiting_view_ack',{'object_ids':ids})

    def action(self,principal,cid,action,body=None):
        body=body or {}; command=self.get(principal,cid)
        if action=='cancel':
            if command['status']=='completed': raise Conflict('This command is completed. Undo its change explicitly.')
            with self.store.connection(write=True) as db: db.execute("UPDATE commands SET cancel=1,status='cancelled',phase='cancelled',updated=? WHERE id=?",(self.store.clock(),cid))
            with self.lock:
                if cid in self.active: self.active[cid].set()
        elif action=='resume':
            if command['status']=='completed': return command
            if command['cancel']: raise Conflict('Cancelled commands cannot deliver late actions. Submit a new command.')
            if command['status']=='awaiting_view_ack':return command
            if command['status'] in {'partial','failed'}:self.update(cid,'accepted',error=None)
            self.start(principal,cid)
        elif action=='ack':
            if command['status'] not in {'awaiting_view_ack','completed'}: raise Conflict('This command has not saved its destination objects yet.')
            if command['cancel']: raise Conflict('A cancelled command cannot be acknowledged.')
            output=command['outputs']; did=output.get('document_id')
            instance=graph.check_id(body.get('instance_id'),'destination instance')
            with self.store.connection() as db:
                registered=db.execute('SELECT body FROM studio_contexts WHERE principal_id=? AND instance_id=?',(principal,instance)).fetchone()
            if not registered or json.loads(registered['body'])['destination'].get('board_id')!=did: raise Conflict('Register the actual destination instance first.')
            doc=self.store.get_document(principal,did)
            if body.get('document_id')!=did or body.get('revision')!=doc['revision'] or set(body.get('object_ids',[]))!=set(output.get('object_ids',[])):
                raise Conflict('Acknowledgment does not match the applied board.')
            if any(oid not in doc['state']['cards'] for oid in output.get('object_ids',[])): raise Conflict('An inserted object is no longer available.')
            self.update(cid,'completed',{'acknowledged_instance':instance})
        elif action=='undo':
            if command['outputs'].get('undone'):return command
            output=command['outputs']; tid=output.get('transaction_id')
            if not tid:
                order=self.step(cid,'story_order')
                if not order:raise StudioError('This command has no mutation to undo.')
                saved=self.service.get_story(principal,order['story_id'])
                if saved['revision']!=order['revision']:raise Conflict('This story changed after the command. Later edits were retained.')
                updated=self.service.update_story(principal,order['story_id'],{'expected_revision':saved['revision'],'story':order['inverse']},key='undo:'+cid)
                self.update(cid,'completed',{'undone':True,'story_revision':updated['revision']});return self.get(principal,cid)
            result=self.store.undo(principal,output['document_id'],'command-undo:'+cid,transaction_id=tid)
            self.update(cid,'completed',{'undone':True,'undo_revision':result['revision']})
        else: raise StudioError('Unsupported command action.')
        return self.get(principal,cid)

    def package(self,principal,pid):
        with self.store.connection() as db: row=db.execute('SELECT * FROM investigation_packages WHERE id=? AND principal_id=?',(pid,principal)).fetchone()
        if not row: raise NotFound('Package not found.')
        self.store.get_document(principal,row['document_id'])
        return json.loads(row['body'])
