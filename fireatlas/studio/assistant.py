"""Studio context and typed draft actions for the existing JARVIS orchestrator.

No second model loop, provider client, or cost allowance is introduced. Presentation
proposals are owned artifacts; applying one still requires its exact board revision.
"""
from __future__ import annotations
import json
import secrets
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
                                'create_story_draft': 'Create an editable six-chapter story from selected board evidence.',
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
        context = normalize_context({**document['state']['study']['context'], 'revision': previous['context']['revision'] + 1})
        self.assistant.store.artifact(owner, 'studio_access', {'principal': principal, 'document_id': document_id})
        instance=graph.check_id(body.get('instance_id') or 'studio-'+document_id)
        view = {'page': 'assistant', 'instance': instance, 'take_control': True,
                'studio': {'document_id': document_id, 'document_revision': document['revision'], 'selected_cards': body.get('selected_cards', [])}}
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
            ids = body.get('selected_cards') or document['state']['order']
            if not isinstance(ids, list) or len(ids) > 100 or any(cid not in document['state']['cards'] for cid in ids):
                raise StudioError('Choose cards from the current board.')
            snapshots = [document['snapshots'][sid] for cid in ids if (sid := document['state']['cards'][cid]['snapshot_id'])]
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
            context=normalize_context({**effective_study(card,document['state'])['context'],'revision':context['revision']})
        if body.get('workflow_id'):captured_view={'kind':'workflow','id':body['node_id']}
        submitting={'schema':CONTEXT_SCHEMA,'surface':'story' if body.get('story_id') else 'workflow' if body.get('workflow_id') else 'studio','origin_instance_id':instance,
                    'origin_tab_id':body.get('tab_id') or instance,'context_revision':context['revision'],'study_selection':context,
                    'source_document_revision':document['revision'],'active_view':captured_view,'selected_object_ids':captured_cards,
                    'result_refs':[{'document_id':document_id,'snapshot_id':s['id']} for s in snapshots[:6]],
                    'destination':{'intent':'append','board_id':document_id,'revision':document['revision']},'return_destination':''}
        view['studio']['captured_context']=self.studio.commands.context(principal,submitting)
        view['studio']['frozen_evidence_ids'] = frozen_ids
        run_nonce = secrets.token_urlsafe(16)
        view['studio']['run_nonce'] = run_nonce
        self.assistant.store.update_session(owner, context, view)
        request = {'context': context, 'view': view, 'message': body.get('message', ''), 'operation': body.get('operation'),
                   'arguments': body.get('arguments', {}), 'nonce': run_nonce}
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
        return {**result, 'proposals': proposals, 'board_revision': grant['board_revision']}

    def apply(self, principal, document_id, proposal_id):
        owner = self.studio.assistant_owner(principal)
        proposal = self.assistant.store.get_artifact(owner, proposal_id, 'studio_proposal')['body']
        if proposal['document_id'] != document_id:
            raise PermissionError('That proposal belongs to another board.')
        return self.studio.presentation_action(principal, document_id, proposal['body'], key='assistant:' + proposal_id)
