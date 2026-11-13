"""Studio context and typed draft actions for the existing JARVIS orchestrator.

This bridge delegates inference and optional budgeted specialist reviews to the
shared assistant service. Presentation proposals remain owned artifacts; applying
one still requires its exact board revision.
"""
from __future__ import annotations
import json
import math
import secrets
import base64
import binascii
import struct
import time
from . import graph
from .orchestration import CONTEXT_SCHEMA
from ..assistant.contracts import normalize_context
from .errors import Conflict, StudioError

ACTIONS = {'build_investigation', 'arrange_cards', 'create_story_draft', 'create_workflow_draft'}

class StudioAssistant:
    def __init__(self, studio, assistant):
        self.studio, self.assistant = studio, assistant

    def access(self, owner, document_id):
        grants = self.assistant.store.artifacts(owner, 'studio_access', limit=100)
        grant = next((g['body'] for g in grants if g['body']['document_id'] == document_id), None)
        if grant is None:
            raise PermissionError('This assistant workspace has no access to that Studio board.')
        return grant['principal']

    def save_conversation_turn(self, owner, document_id, run_id, question, answer):
        """Keep a bounded, board-owned conversation separate from science receipts."""
        principal = self.access(owner, document_id)
        def text(value, limit):
            return value[:limit] if isinstance(value, str) else ''
        body = {'document_id':document_id, 'run_id':run_id, 'question':text(question,1000),
                'title':text(answer.get('title'),200), 'summary':text(answer.get('summary'),2400)}
        claims = answer.get('claims') if isinstance(answer.get('claims'), list) else []
        body['claims'] = [{'label':text(item.get('label'),200),'value':item['value'],'unit':text(item.get('unit'),100)}
                          for item in claims[:12] if isinstance(item,dict) and isinstance(item.get('value'), (str,int,float))
                          and not isinstance(item.get('value'),bool) and (not isinstance(item['value'],str) or len(item['value'])<=400)
                          and (not isinstance(item['value'],float) or math.isfinite(item['value']))]
        # Persist the validated research outputs with their board, independently
        # of the expiring assistant workspace. These remain authored research.
        for key in ('web_sources','web_search','research_team','research_answer','public_readings','nasa_discoveries'):
            value=answer.get(key)
            if isinstance(value,(dict,list)) and len(json.dumps(value,allow_nan=False).encode())<=60000:
                body[key]=value
        receipts=[]
        for identifier in answer.get('web_search_receipts',[])[:2]:
            receipts.append(self.assistant.store.get_artifact(owner,identifier,'public_research')['body'])
        if receipts:body['public_research_receipts']=receipts
        with self.studio.store.connection(write=True) as db:
            self.studio.store.require(db, principal, document_id)
            existing = db.execute("SELECT id FROM science_results WHERE principal_id=? AND kind='whiteboard_conversation' AND json_extract(body,'$.document_id')=? AND json_extract(body,'$.run_id')=?", (principal,document_id,run_id)).fetchone()
            if not existing:
                db.execute('INSERT INTO science_results VALUES(?,?,?,?,?,?)', ('res_'+secrets.token_urlsafe(16),principal,'whiteboard_conversation','',json.dumps(body),self.studio.store.clock()))
            db.execute("""DELETE FROM science_results WHERE id IN (SELECT id FROM science_results
                WHERE principal_id=? AND kind='whiteboard_conversation' AND json_extract(body,'$.document_id')=?
                ORDER BY created DESC, rowid DESC LIMIT -1 OFFSET 30)""", (principal,document_id))

    def conversation(self, owner, document_id):
        principal = self.access(owner, document_id)
        return self.conversation_for_principal(principal, document_id)

    def conversation_for_principal(self, principal, document_id):
        with self.studio.store.connection() as db:
            self.studio.store.require(db, principal, document_id)
            rows = db.execute("""SELECT body FROM science_results WHERE principal_id=? AND kind='whiteboard_conversation'
                AND json_extract(body,'$.document_id')=? ORDER BY created DESC, rowid DESC LIMIT 6""", (principal,document_id)).fetchall()
        return [{k:v for k,v in json.loads(row['body']).items() if k in ('question','title','summary','claims','web_sources','web_search','public_research_receipts','research_team','research_answer','public_readings','nasa_discoveries')} for row in reversed(rows)]

    def board(self, owner, document_id):
        principal = self.access(owner, document_id)
        board = self.studio.get_document(principal, document_id)
        # Models receive bounded references and checked scalar previews, not a complete archive.
        return {'id': board['id'], 'revision': board['revision'], 'study': board['state']['study'],
                'cards': [{'id': c['id'], 'type': c['type'], 'title': c['title'], 'transform': c['transform'],
                           'locked': c['locked'], 'snapshot_id': c['snapshot_id'],
                           'facts': board['snapshots'].get(c['snapshot_id'], {}).get('facts', [])}
                          for c in board['state']['cards'].values()]}

    def command(self, owner, document_id, recipe, arguments, captured, key):
        principal=self.access(owner,document_id)
        self.studio.get_document(principal,document_id)
        if captured['destination'].get('board_id')!=document_id: raise PermissionError('Command destination differs from the attached board.')
        command=self.studio.commands.submit(principal,{'recipe':recipe,'context':captured,'arguments':arguments},key,assistant_owner=owner)
        self.assistant.store.artifact(owner,'jarvis_command',{'command_id':command['id'],'principal':principal,'request_key':key})
        return command

    def attach_surface(self, principal, owner, body):
        """An explicitly captured source is owned by both identities, not authorized by a tab ID."""
        self.assistant.store.session(owner)
        captured=self.studio.commands.context(principal,body.get('context'))
        preview=body.get('preview')
        if preview:
            import base64
            try: data=base64.b64decode(preview['data'],validate=True)
            except (ValueError,KeyError,TypeError): raise StudioError('Invalid captured preview.') from None
            if preview.get('mime')!='image/png' or len(data)>1_500_000 or not data.startswith(b'\x89PNG\r\n\x1a\n'):
                raise StudioError('Attach a bounded PNG preview.')
        # Resolve receipt ownership before granting the model any surface action.
        for ref in captured['result_refs']:
            if ref.get('document_id'):
                self.studio.snapshot_receipt(principal,ref['document_id'],ref['snapshot_id'])
            else: self.assistant.store.get_artifact(owner,ref['id'],'evidence')
        identifier=self.assistant.store.artifact(owner,'jarvis_surface',{'principal':principal,'context':captured,'preview':preview})
        return {'attachment_id':identifier,'instance_id':captured['origin_instance_id']}

    def surface(self, owner, attachment_id, context):
        attached=self.assistant.store.get_artifact(owner,attachment_id,'jarvis_surface')['body']
        expected=attached['context']['study_selection']
        actual=normalize_context(context)
        if {k:v for k,v in expected.items() if k!='revision'}!={k:v for k,v in actual.items() if k!='revision'}:
            raise Conflict('The attached source changed. Capture and attach the current view again.',code='stale-context')
        return attached

    def surface_command(self,owner,attachment_id,context,recipe,arguments,key):
        attached=self.surface(owner,attachment_id,context)
        command=self.studio.commands.submit(attached['principal'],{'recipe':recipe,'context':attached['context'],
            'arguments':arguments,**({'preview':attached['preview']} if attached.get('preview') else {})},key,assistant_owner=owner)
        self.assistant.store.artifact(owner,'jarvis_command',{'command_id':command['id'],'principal':attached['principal'],'request_key':key})
        return command

    def cancel_commands(self,owner,nonce):
        for item in self.assistant.store.artifacts(owner,'jarvis_command',limit=100):
            body=item['body']
            if not body['request_key'].startswith('jarvis:'+nonce+':'):continue
            command=self.studio.commands.get(body['principal'],body['command_id'])
            if command['status'] not in {'completed','cancelled','failed'}:
                self.studio.commands.action(body['principal'],command['id'],'cancel')

    def propose(self, owner, document_id, action, arguments, base_revision):
        principal = self.access(owner, document_id)
        document = self.studio.get_document(principal, document_id)
        if document['revision'] != base_revision:
            raise Conflict('The board changed. Inspect its current revision before drafting an action.', code='stale-action')
        if action not in ACTIONS or not isinstance(arguments, dict):
            raise StudioError('Draft a supported typed presentation action.', code='invalid-action')
        if action == 'arrange_cards':
            from .graph import clean_transform
            cards = arguments.get('cards')
            if set(arguments) != {'cards'} or not isinstance(cards, list) or not 1 <= len(cards) <= 100:
                raise StudioError('Arrange a bounded list of existing card IDs and transforms.')
            for card in cards:
                if set(card) != {'id', 'transform'} or card['id'] not in document['state']['cards']:
                    raise StudioError('Arrange existing cards only.')
                clean_transform(card['transform'])
                if document['state']['cards'][card['id']]['locked']:
                    raise StudioError('Unlock that card before arranging it.')
        elif action == 'create_story_draft':
            if set(arguments) - {'title', 'selected_cards', 'audience'}:
                raise StudioError('A story proposal chooses evidence cards and a communication goal; it cannot invent chapter measurements.')
            from .story import default_story
            default_story(document['state'], arguments.get('title'), arguments.get('selected_cards'))
            arguments = {'story': arguments}
        elif action == 'create_workflow_draft':
            from .workflow import templates, validate as validate_workflow
            if set(arguments) == {'template_id'}:
                template = next((item for item in templates() if item['id'] == arguments['template_id']), None)
                if template is None:
                    raise StudioError('Choose a supported workflow template.')
                arguments = {'definition': template['definition']}
            elif set(arguments) != {'definition'}:
                raise StudioError('A workflow proposal uses a supported template_id or a typed definition.')
            validate_workflow(arguments['definition'])
        elif arguments:
            raise StudioError('The investigation template takes its exact scope from the applied board study.')
        body = {'action': action, 'base_revision': base_revision, **arguments}
        proposal = {'document_id': document_id, 'base_revision': base_revision, 'action': action, 'body': body,
                    'run_nonce': (self.assistant.store.session(owner).get('view') or {}).get('studio', {}).get('run_nonce'),
                    'summary': {'build_investigation': 'Create the seven-card study template. Evidence remains unfrozen until calculated.',
                                'arrange_cards': 'Move or resize the listed existing cards.',
                                'create_story_draft': 'Create an AI& infographic story and film from the selected frozen evidence when configured; otherwise save a manual draft.',
                                'create_workflow_draft': 'Load an editable workflow draft. Saving and running remain separate explicit actions.'}[action]}
        identifier = self.assistant.store.artifact(owner, 'studio_proposal', proposal)
        return {'proposal_id': identifier, **proposal, 'requires_apply': True}

    def start(self, principal, document_id, body):
        with self.studio.assistant_lock:
            return self._start(principal, document_id, body)

    def _start(self, principal, document_id, body):
        document = self.studio.get_document(principal, document_id)
        if body.get('base_revision') != document['revision']:
            raise Conflict('This question belongs to an older board revision.', code='stale-action')
        owner = self.studio.assistant_owner(principal)
        with self.assistant.store.connection() as db:
            if db.execute("SELECT 1 FROM runs WHERE session=? AND status IN ('queued','running')", (owner,)).fetchone():
                raise Conflict('A JARVIS investigation is already running. Cancel it before changing the question context.', code='run-busy')
        previous = self.assistant.store.session(owner)
        study_context = (document['state'].get('study') or {}).get('context') or {}
        selected_ids = body.get('selected_cards') or []
        has_frozen_study = (isinstance(selected_ids, list) and len(selected_ids) == 1 and isinstance(selected_ids[0], str)
                            and bool(document['state']['cards'].get(selected_ids[0], {}).get('snapshot_id')))
        context = normalize_context({**study_context, 'revision': previous['context']['revision'] + 1})
        self.assistant.store.artifact(owner, 'studio_access', {'principal': principal, 'document_id': document_id})
        instance=graph.check_id(body.get('instance_id') or 'studio-'+document_id)
        view = {'page': 'assistant', 'instance': instance, 'take_control': True,
                'studio': {'document_id': document_id, 'document_revision': document['revision'], 'selected_cards': body.get('selected_cards', []),
                           'unscoped': not study_context and not has_frozen_study}}
        if body.get('whiteboard') is True:
            view['studio']['whiteboard'] = True
            if body.get('research_team') is not None and type(body['research_team']) is not bool:
                raise StudioError('Choose whether to use the research team.')
            view['research_team']=body.get('research_team') is True
            if body.get('whiteboard_challenge') is True:
                view['studio']['challenge'] = True
        visual_capture = body.get('visual_capture')
        if visual_capture is not None:
            if not view['studio'].get('whiteboard') or not isinstance(visual_capture,dict) or set(visual_capture)!={'element_ids','png'}:
                raise StudioError('Select a saved whiteboard visual first.')
            visual_ids=visual_capture['element_ids']
            if not isinstance(visual_ids,list) or not 1<=len(visual_ids)<=20 or any(not isinstance(i,str) for i in visual_ids):
                raise StudioError('Select up to twenty visual objects.')
            scene=self.studio.store.whiteboard(principal,document_id)['elements']
            present={item['id'] for item in scene if not item.get('isDeleted')}
            if any(i not in present for i in visual_ids):raise StudioError('The selected visual changed. Select it again.')
            encoded=visual_capture['png']
            if not isinstance(encoded,str) or len(encoded)>2_000_000:raise StudioError('The selected visual is too large.')
            try: raw=base64.b64decode(encoded,validate=True)
            except (ValueError,binascii.Error): raise StudioError('The selected visual is invalid.') from None
            if not 24<=len(raw)<=1_500_000 or raw[:8]!=b'\x89PNG\r\n\x1a\n' or raw[12:16]!=b'IHDR':raise StudioError('The selected visual is invalid.')
            width,height=struct.unpack('>II',raw[16:24])
            if not 1<=width<=1536 or not 1<=height<=1536:raise StudioError('The selected visual is too large.')
            view['studio']['selected_visual']={'element_ids':visual_ids}
        selected_snapshots = body.get('selected_snapshot_elements', [])
        if not isinstance(selected_snapshots, list) or len(selected_snapshots) > 6 or any(not isinstance(item, str) for item in selected_snapshots):
            raise StudioError('Select up to six saved evidence items.')
        standalone = []
        if selected_snapshots:
            if not view['studio'].get('whiteboard') or body.get('story_id'):
                raise StudioError('Select saved evidence from the investigation whiteboard.')
            elements = {item['id']:item for item in self.studio.store.whiteboard(principal, document_id)['elements'] if not item.get('isDeleted')}
            for element_id in selected_snapshots:
                custom = elements.get(element_id, {}).get('customData') or {}
                ref = custom.get('fireatlas') if isinstance(custom, dict) else None
                ref = ref if isinstance(ref, dict) else {}
                references=[ref] if ref.get('snapshotId') else ref.get('sourceBindings')
                if ref.get('documentId') != document_id or ref.get('cardId') or not isinstance(references,list) or not 1<=len(references)<=6:
                    raise StudioError('Select a current saved evidence item.')
                for source in references:
                    snapshot=document['snapshots'].get(source.get('snapshotId')) if isinstance(source,dict) else None
                    if not isinstance(source,dict) or source.get('documentId')!=document_id or not snapshot or snapshot['snapshot_sha256']!=source.get('snapshotHash'):
                        raise StudioError('Select a current saved evidence item.')
                    owned_receipt=self.studio.snapshot_receipt(principal,document_id,snapshot['id'])['receipt']
                    panel_index=ref.get('comparisonPanel')
                    if panel_index is not None:
                        panels=owned_receipt.get('payload',{}).get('panels',[])
                        if owned_receipt.get('operation')!='regional_comparison' or type(panel_index) is not int or not 0<=panel_index<len(panels):
                            raise StudioError('The selected comparison panel changed. Select it again.')
                        panel=panels[panel_index]
                        selection={'snapshot_id':snapshot['id'],'index':panel_index,'label':panel['label'],
                                   'start':panel['start'],'end':panel['end'],'search_start':panel['search_start'],
                                   'search_end':panel['search_end'],'product':panel['product']}
                        selected_panels=view['studio'].setdefault('selected_comparison_panels',[])
                        if selection not in selected_panels:selected_panels.append(selection)
                    if not any(item['id']==snapshot['id'] for item in standalone):standalone.append(snapshot)
            view['studio']['unscoped'] = False
        selected_notes = body.get('selected_note_elements', [])
        if not isinstance(selected_notes, list) or len(selected_notes) > 20 or any(not isinstance(item, str) for item in selected_notes):
            raise StudioError('Select up to 20 board notes or shapes.')
        whole_board_notes = (view['studio'].get('whiteboard') and not body.get('whiteboard_challenge') and
            not any(body.get(key) for key in ('selected_cards', 'selected_snapshot_elements', 'selected_dataset_elements',
                                               'selected_source_elements', 'selected_comparison_elements', 'selected_note_elements','visual_capture')))
        if selected_notes or whole_board_notes:
            if not view['studio'].get('whiteboard'):
                raise StudioError('Note selection requires the investigation whiteboard.')
            scene = self.studio.store.whiteboard(principal, document_id)['elements']
            elements = {item['id']: item for item in scene}
            if any(item not in elements or elements[item].get('isDeleted') for item in selected_notes):
                raise StudioError('Select notes from the current saved board.')
            ids = set(selected_notes)
            notes = []
            for item in scene:
                if item.get('isDeleted') or item.get('type') != 'text':
                    continue
                if not whole_board_notes and item['id'] not in ids and item.get('containerId') not in ids and item.get('frameId') not in ids:
                    continue
                text = item.get('text')
                if isinstance(text, str) and text.strip():
                    note = {'element_id': item['id'], 'text': text[:2000]}
                    # Bound Excalidraw labels may carry the provenance on their
                    # container instead of the text element itself.
                    container = elements.get(item.get('containerId'), {})
                    if container.get('isDeleted'):
                        container = {}
                    for candidate in (item, container):
                        custom = candidate.get('customData') or {}
                        ref = custom.get('fireatlas') if isinstance(custom, dict) else None
                        kind = ref.get('kind') if isinstance(ref, dict) else None
                        if isinstance(ref, dict) and ref.get('documentId') == document_id and isinstance(kind, str) and kind.startswith('assistant-'):
                            note['origin'] = 'assistant_placed'
                            break
                    notes.append(note)
                if not whole_board_notes and len(notes) == 20:
                    break
            if whole_board_notes:
                # Figure labels can otherwise crowd authored research notes
                # out of the bounded whole-board context. Keep chart text
                # available after authored notes and before old AI output.
                def note_priority(note):
                    item=elements[note['element_id']]
                    candidates=(item,elements.get(item.get('containerId'),{}),elements.get(item.get('frameId'),{}))
                    kinds=[]
                    for candidate in candidates:
                        if candidate.get('isDeleted'):continue
                        custom=candidate.get('customData') or {}
                        ref=custom.get('fireatlas') if isinstance(custom,dict) else None
                        if isinstance(ref,dict) and ref.get('documentId')==document_id:kinds.append(ref.get('kind'))
                    if any(isinstance(kind,str) and kind.startswith('assistant-') for kind in kinds):return 2
                    if any(kind in ('park-platform-chart','comparison-chart','dataset-group-chart','dataset-group-summary','scatter-values-table') for kind in kinds):return 1
                    return 0
                notes.sort(key=note_priority)
                notes = notes[:20]
            if not notes and selected_notes:
                raise StudioError('The selected items have no readable text.')
            if notes:
                view['studio']['selected_notes'] = notes
                view['studio']['notes_scope'] = 'board' if whole_board_notes else 'selection'
        selected_elements = body.get('selected_dataset_elements', [])
        if not isinstance(selected_elements, list) or len(selected_elements) > 10 or any(not isinstance(item, str) for item in selected_elements):
            raise StudioError('Select a saved table on this board.')
        if whole_board_notes:
            # The board itself can supply a table only when every visible table
            # reference identifies the same owned, hash-matching source.
            from .datasets import read
            table_refs=set()
            for item in scene:
                if item.get('isDeleted'):continue
                custom=item.get('customData') or {}
                ref=custom.get('fireatlas') if isinstance(custom,dict) else None
                if (isinstance(ref,dict) and ref.get('documentId')==document_id and
                    isinstance(ref.get('datasetId'),str) and ref['datasetId'] and
                    isinstance(ref.get('datasetHash'),str) and ref['datasetHash']):
                    table_refs.add((ref['datasetId'],ref['datasetHash']))
            if len(table_refs)==1:
                dataset_id,dataset_hash=next(iter(table_refs))
                try:info,_=read(self.studio.store,principal,document_id,dataset_id)
                except StudioError:info=None
                if info and info['sha256']==dataset_hash:
                    view['studio']['selected_dataset']={k:info[k] for k in ('id','sha256','name','columns','row_count')}
                    view['studio']['dataset_scope']='board'
        if selected_elements:
            if not view['studio'].get('whiteboard'):
                raise StudioError('Table selection requires the investigation whiteboard.')
            from .datasets import read
            scene = self.studio.store.whiteboard(principal, document_id)
            elements = {item['id']: item for item in scene['elements']}
            refs = []
            selected_rows = set()
            selected_groups = set()
            all_group_bound = True
            for element_id in selected_elements:
                element=elements.get(element_id, {})
                if element.get('isDeleted'):raise StudioError('Select a current saved table on this board.')
                custom = element.get('customData') or {}
                ref = custom.get('fireatlas') if isinstance(custom, dict) else None
                ref = ref if isinstance(ref, dict) else {}
                if ref.get('documentId') != document_id or not ref.get('datasetId') or not ref.get('datasetHash'):
                    raise StudioError('Select a saved table on this board.')
                info, _ = read(self.studio.store, principal, document_id, ref['datasetId'])
                if info['sha256'] != ref['datasetHash']:
                    raise Conflict('The selected table no longer matches its source.')
                row = ref.get('rowOffset')
                if type(row) is int and 0 <= row < info['row_count']:
                    selected_rows.add(row)
                group=ref.get('groupName')
                if (ref.get('kind')=='dataset-group-chart' and 'groupName' in ref and
                    (group is None or isinstance(group,str)) and ref.get('groupMetric')=='mean' and
                    isinstance(ref.get('groupColumn'),str) and isinstance(ref.get('valueColumn'),str)):
                    selected_groups.add((ref['groupColumn'],ref['valueColumn'],group))
                else:all_group_bound=False
                if not any(item['id'] == info['id'] for item in refs):
                    refs.append({'id': info['id'], 'sha256': info['sha256'], 'name': info['name'], 'columns': info['columns'], 'row_count': info['row_count']})
            if len(refs) != 1:
                raise StudioError('Select one table at a time.')
            if len(selected_rows) == 1:
                refs[0]['selected_row_offset'] = selected_rows.pop()
            if all_group_bound and len(selected_groups)==1:
                from .datasets import group_summary
                group_column,value_column,name=next(iter(selected_groups))
                grouped=group_summary(self.studio.store,principal,document_id,refs[0]['id'],group_column,value_column)
                if grouped['sha256']!=refs[0]['sha256']:raise Conflict('The selected table no longer matches its source.')
                index=next((i for i,item in enumerate(grouped['groups']) if item['group']==name),None)
                if index is None:raise StudioError('The selected chart group no longer exists.')
                refs[0].pop('selected_row_offset',None)
                refs[0]['selected_group']={'group_column':group_column,'value_column':value_column,'name':name,'index':index}
            view['studio']['selected_dataset'] = refs[0]
        selected_sources = body.get('selected_source_elements', [])
        if not isinstance(selected_sources,list) or len(selected_sources)>10 or any(not isinstance(item,str) for item in selected_sources):
            raise StudioError('Select a saved document on this board.')
        if selected_sources:
            if not view['studio'].get('whiteboard'):
                raise StudioError('Document selection requires the investigation whiteboard.')
            from .source_documents import read
            scene=self.studio.store.whiteboard(principal,document_id)
            elements={item['id']:item for item in scene['elements']}
            refs=[]
            for element_id in selected_sources:
                custom=elements.get(element_id,{}).get('customData') or {}
                ref=custom.get('fireatlas') if isinstance(custom,dict) else None
                ref=ref if isinstance(ref,dict) else {}
                if ref.get('documentId')!=document_id or not ref.get('sourceDocumentId') or not ref.get('sourceDocumentHash') or type(ref.get('page')) is not int or not 1<=ref['page']<=20:
                    raise StudioError('Select a saved document page on this board.')
                info,_=read(self.studio.store,principal,document_id,ref['sourceDocumentId'])
                if info['sha256']!=ref['sourceDocumentHash']:raise Conflict('The selected document no longer matches its source.')
                candidate={'id':info['id'],'sha256':info['sha256'],'name':info['name'],'page':ref['page']}
                if candidate not in refs:refs.append(candidate)
            if len(refs)!=1:raise StudioError('Select one document page at a time.')
            view['studio']['selected_source']=refs[0]
        selected_comparisons = body.get('selected_comparison_elements', [])
        if not isinstance(selected_comparisons, list) or len(selected_comparisons) > 6 or any(not isinstance(item, str) for item in selected_comparisons):
            raise StudioError('Select comparison views from this board.')
        if selected_comparisons:
            if not view['studio'].get('whiteboard'):
                raise StudioError('Comparison selection requires the investigation whiteboard.')
            elements = {item['id']: item for item in self.studio.store.whiteboard(principal, document_id)['elements']}
            selected_views = []
            for element_id in selected_comparisons:
                custom = elements.get(element_id, {}).get('customData') or {}
                ref = custom.get('fireatlas') if isinstance(custom, dict) else None
                ref = ref if isinstance(ref, dict) else {}
                card = document['state']['cards'].get(ref.get('cardId'))
                snapshot = document['snapshots'].get(ref.get('snapshotId'))
                series = ref.get('comparisonSeries')
                if (ref.get('documentId') != document_id or ref.get('kind') != 'finding-alternative'
                        or series not in ('modis', 'viirs', 'adjusted') or not card or not snapshot
                        or card.get('snapshot_id') != snapshot['id'] or snapshot['snapshot_sha256'] != ref.get('snapshotHash')
                        or card['id'] not in (body.get('selected_cards') or [])):
                    raise StudioError('Select a current saved comparison view.')
                receipt = self.studio.snapshot_receipt(principal, document_id, snapshot['id'])['receipt']
                payload = receipt.get('payload') or {}
                comparison = payload.get('comparison') if isinstance(payload, dict) else None
                series_data = comparison.get('series') if isinstance(comparison, dict) else None
                if (receipt.get('operation') != 'finding_comparison' or not isinstance(payload, dict) or payload.get('schema') != 'fireatlas-finding-investigation-v1'
                        or not isinstance(series_data, dict) or not isinstance(series_data.get(series), dict)):
                    raise StudioError('The selected view has no matching comparison evidence.')
                selected_view = {'snapshot_id': snapshot['id'], 'series': series}
                if selected_view not in selected_views:
                    selected_views.append(selected_view)
            view['studio']['selected_comparisons'] = selected_views
        if body.get('story_id'):
            story = self.studio.get_story(principal, body['story_id'], body.get('story_revision'))
            if story['document_id'] != document_id or not story.get('resolved'):
                raise StudioError('Choose a resolved story from this board before asking about its chapter.')
            scene = next((s for s in story['resolved']['scenes'] if s['chapter_id'] == body.get('chapter_id')), None)
            if scene is None:
                raise StudioError('That chapter does not belong to the saved story revision.')
            view['studio']['chapter'] = {'revision': story['revision'], 'chapter_id': scene['chapter_id'], 'title': scene['title'],
                                        'selection': scene['selection'], 'source_filter': scene['source_filter'], 'narration': scene['narration_text'],
                                        'visible_cards': scene.get('visible_cards', []), 'audience': scene.get('audience')}
            snapshots = [story['resolved']['snapshots'][sid] for sid in scene['evidence']]
            if snapshots:
                selected = scene.get('selection') or {}
                context = normalize_context({**snapshots[0]['context'],
                                             'day': selected.get('day') or snapshots[0]['scope'].get('day'),
                                             'start': selected.get('start') or snapshots[0]['scope'].get('start'),
                                             'end': selected.get('end') or snapshots[0]['scope'].get('end'),
                                             'source': scene.get('source_filter') or snapshots[0]['context'].get('source', 'joint'),
                                             'revision': previous['context']['revision'] + 1})
        else:
            ids = body.get('selected_cards') or ([] if standalone else document['state']['order'])
            if not isinstance(ids, list) or len(ids) > 100 or any(cid not in document['state']['cards'] for cid in ids):
                raise StudioError('Choose cards from the current board.')
            snapshots = [document['snapshots'][sid] for cid in ids if (sid := document['state']['cards'][cid]['snapshot_id'])]
            if len(snapshots) + len(standalone) > 6:
                raise StudioError('Select at most six saved evidence items.')
            snapshots.extend(standalone)
        if body.get('workflow_id'):
            saved=self.studio.get_workflow(principal,body['workflow_id'])
            if saved['document_id']!=document_id or saved['revision']!=body.get('workflow_revision'):
                raise Conflict('Select a node from the current saved workflow revision.')
            node=next((n for n in saved['definition']['nodes'] if n['id']==body.get('node_id')),None)
            if not node:raise StudioError('Select a saved workflow node.')
            view['studio']['workflow']={'id':saved['id'],'revision':saved['revision'],'node':node}
        frozen_ids = []
        for snapshot in snapshots[:6]:
            receipt = self.studio.snapshot_receipt(principal, document_id, snapshot['id'])['receipt']
            frozen_ids.append(self.assistant.store.artifact(owner, 'evidence', receipt))
        captured_cards=body.get('selected_cards') or []
        card=document['state']['cards'].get(captured_cards[0]) if len(captured_cards)==1 else None
        captured_view=(card.get('display',{}).get('captured_view') or {'kind':card['type']}) if card else {'kind':'board'}
        if card and not body.get('story_id'):
            from .graph import effective_study
            card_context=(effective_study(card,document['state']) or {}).get('context')
            if not card_context and card.get('snapshot_id'):
                card_context=(document['snapshots'].get(card['snapshot_id']) or {}).get('context')
            context=normalize_context({**(card_context or {}),'revision':context['revision']})
        elif standalone and not body.get('story_id'):
            context=normalize_context({**standalone[0]['context'], 'revision':context['revision']})
        if body.get('workflow_id'):captured_view={'kind':'workflow','id':body['node_id']}
        submitting={'schema':CONTEXT_SCHEMA,'surface':'story' if body.get('story_id') else 'workflow' if body.get('workflow_id') else 'studio','origin_instance_id':instance,
                    'origin_tab_id':body.get('tab_id') or instance,'context_revision':context['revision'],'study_selection':context,
                    'source_document_revision':document['revision'],'active_view':captured_view,'selected_object_ids':captured_cards,
                    'result_refs':[{'document_id':document_id,'snapshot_id':s['id']} for s in snapshots[:6]],
                    'destination':{'intent':'append','board_id':document_id,'revision':document['revision']},'return_destination':''}
        view['studio']['captured_context']=self.studio.commands.context(principal,submitting)
        view['studio']['frozen_evidence_ids'] = frozen_ids
        if view['studio'].get('whiteboard') and not body.get('story_id'):
            cards = [(cid, document['snapshots'][document['state']['cards'][cid]['snapshot_id']]) for cid in ids
                     if document['state']['cards'][cid]['snapshot_id']][:6]
            view['studio']['frozen_evidence_refs'] = {fid: {'documentId': document_id, 'cardId': cid, 'snapshotId': snap['id'], 'snapshotHash': snap['snapshot_sha256'], 'title': document['state']['cards'][cid]['title']}
                                                    for fid, (cid, snap) in zip(frozen_ids, cards)}
            for fid, snap in zip(frozen_ids[len(cards):], standalone):
                view['studio']['frozen_evidence_refs'][fid] = {'documentId':document_id, 'snapshotId':snap['id'], 'snapshotHash':snap['snapshot_sha256'], 'title':'Saved assistant evidence'}
        run_nonce = secrets.token_urlsafe(16)
        view['studio']['run_nonce'] = run_nonce
        self.assistant.store.update_session(owner, context, view)
        request = {'context': context, 'view': view, 'message': body.get('message', ''), 'operation': body.get('operation'),
                   'arguments': body.get('arguments', {}), 'nonce': run_nonce}
        if visual_capture is not None:
            figure={'regions':[],'data':encoded,'mime':'image/png','revision':context['revision'],'created':time.time(),'caption':'Selected whiteboard visual'}
            request['image_ids']=[self.assistant.store.artifact(owner,'image',figure)]
        job = self.assistant.start(owner, request)
        self.studio.store.artifact(principal, 'assistant_run', {'document_id': document_id, 'run_id': job['id'],
                                                               'owner': owner, 'board_revision': document['revision'], 'run_nonce': run_nonce})
        return job

    def run(self, principal, document_id, run_id, cancel=False):
        self.studio.get_document(principal, document_id)
        with self.studio.store.connection() as db:
            rows = db.execute("SELECT body FROM science_results WHERE principal_id=? AND kind='assistant_run'", (principal,)).fetchall()
        grant = next((json.loads(r['body']) for r in rows if json.loads(r['body']).get('run_id') == run_id and json.loads(r['body']).get('document_id') == document_id), None)
        if grant is None:
            raise PermissionError('That assistant investigation does not belong to this board.')
        if cancel:
            self.assistant.cancel(grant['owner'], run_id)
        result = self.assistant.store.run(grant['owner'], run_id)
        proposals = [dict(p['body'], id=p['id']) for p in self.assistant.store.artifacts(grant['owner'], 'studio_proposal')
                     if p['body']['document_id'] == document_id and p['body']['base_revision'] == grant['board_revision'] and
                        p['body'].get('run_nonce') == grant.get('run_nonce')]
        activity=[event for event in self.assistant.store.events(grant['owner'],run_id) if event.get('type')=='STEP_STARTED'][-8:]
        return {**result, 'proposals': proposals, 'board_revision': grant['board_revision'],'activity':activity}

    def apply(self, principal, document_id, proposal_id):
        owner = self.studio.assistant_owner(principal)
        proposal = self.assistant.store.get_artifact(owner, proposal_id, 'studio_proposal')['body']
        if proposal['document_id'] != document_id:
            raise PermissionError('That proposal belongs to another board.')
        return self.studio.presentation_action(principal, document_id, proposal['body'], key='assistant:' + proposal_id)

    def preserve_claims(self, principal, document_id, run_id):
        """Freeze unbound scientific claims from an owned completed run, never client-supplied values."""
        from ..assistant.contracts import digest
        from ..assistant.agent import fact
        from . import evidence as ev
        run = self.run(principal, document_id, run_id)
        if run['status'] != 'completed' or not isinstance(run.get('body'), dict):
            raise StudioError('Wait for the assistant to finish before saving its evidence.')
        claims = run['body'].get('claims') or []
        if not isinstance(claims, list) or len(claims) > 12:
            raise StudioError('The assistant returned too many evidence claims.')
        owner = self.studio.assistant_owner(principal)
        grouped = {}
        for claim in claims:
            if not isinstance(claim, dict) or claim.get('binding') or claim.get('source_binding'):
                continue
            rid, path = claim.get('result_id'), claim.get('path')
            if not isinstance(rid, str) or not isinstance(path, str):
                continue
            grouped.setdefault(rid, []).append(claim)
        from ..assistant.board_views import VIEW_OPERATIONS
        requested_views=run['body'].get('data_views') or []
        if not isinstance(requested_views,list) or len(requested_views)>4:
            raise StudioError('The assistant returned too many data views.')
        view_operations={}
        for item in requested_views:
            if not isinstance(item,dict) or item.get('kind') not in VIEW_OPERATIONS or not isinstance(item.get('result_id'),str):
                raise StudioError('The assistant returned an unsupported data view.')
            rid=item['result_id']
            view_operations.setdefault(rid,set()).add(VIEW_OPERATIONS[item['kind']])
            grouped.setdefault(rid,[])
        bindings = {}
        for rid, items in grouped.items():
            receipt = self.assistant.store.get_artifact(owner, rid, 'evidence')['body']
            if rid in view_operations and view_operations[rid] != {receipt.get('operation')}:
                raise StudioError('The data view does not match its scientific calculation.',code='invalid-evidence')
            if receipt.get('operation') not in self.studio.operations and not (rid in view_operations and receipt.get('operation') in {'firms_country','firms_region','regional_comparison'}):
                continue
            if digest({k:v for k,v in receipt.items() if k not in ('id','sha256')}) != receipt.get('sha256'):
                raise StudioError('The assistant calculation cannot be preserved as scientific evidence.', code='invalid-evidence')
            for claim in items:
                checked = fact({**receipt, 'id':rid}, claim['path'])
                if checked['value'] != claim.get('value') or checked['unit'] != claim.get('unit'):
                    raise StudioError('The assistant claim does not match its calculation.', code='invalid-evidence')
            paths = list(dict.fromkeys(item['path'] for item in items))
            identity = digest({'document':document_id, 'run':run_id, 'result':rid, 'paths':paths})
            saved_result = 'res_' + identity[:32]
            saved_snapshot = 'snap_' + identity[:32]
            # External frozen acquisition carries its own immutable provenance;
            # a new hosted instance need not have an imported local archive.
            external_frozen=receipt.get('release_frozen') and receipt.get('operation') in {'firms_country','firms_region','regional_comparison'}
            release = {'manifest':{}} if external_frozen else self.studio.science.release()
            if release.get('id') != receipt['release_id']:
                release = {'manifest':{}}
            snapshot = ev.build_snapshot({**receipt, 'id':saved_result}, release, {'operation':receipt['operation'], 'paths':paths, 'context':receipt['context']})
            if not release.get('id'):
                snapshot['dependency_hashes'] = {}
                snapshot['dependency_status'] = 'Original dependency manifest unavailable; frozen receipt retained.'
            saved = self.studio.store.preserve_assistant_snapshot(principal, document_id, saved_result, receipt, saved_snapshot, snapshot)
            bindings[rid] = {'documentId':document_id, 'snapshotId':saved['id'], 'snapshotHash':saved['snapshot_sha256'], 'resultId':saved_result}
        return {'bindings':bindings}
