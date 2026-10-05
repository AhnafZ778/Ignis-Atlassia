"""Studio reuses assistant ownership, checked results, cancellation and cost accounting."""
from __future__ import annotations
import types
import unittest
from unittest.mock import patch
try:
    from studio_support import StudioCase
except ImportError:
    from .studio_support import StudioCase
from fireatlas.assistant.service import AssistantService
from fireatlas.assistant.voice import synthesize_checked
from fireatlas.studio.assistant import StudioAssistant
from fireatlas.studio.errors import Conflict, NotFound, StudioError

class StudioAssistantTests(StudioCase):
    def test_model_canvas_recipe_is_returned_without_a_scientific_claim(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        import threading,time
        document=self.board();owner=self.grant(document)
        cfg=normalize_context(self.study['context'])
        view={'studio':{'document_id':document['id'],'frozen_evidence_ids':[],
              'run_nonce':'test-command','captured_context':{'destination':{'board_id':document['id']}}}}
        saved={'id':'cmd_saved','status':'accepted','phase':'accepted','outputs':{},'message':'accepted'}
        for invalid in (False,True):
            calls=[]
            def respond(messages,info):
                calls.append(1)
                if len(calls)==1:
                    return ModelResponse(parts=[ToolCallPart('run_studio_recipe',{'recipe':'visualization_to_investigation','arguments':{}})])
                draft={'title':'Canvas package','interpretation':'The Canvas command is saved.'}
                if invalid:draft['claims']=[{'result_id':'cmd_saved','path':'/outputs','label':'Command'}]
                return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,draft)])
            env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
            with self.subTest(invalid=invalid),patch.dict('os.environ',env),patch.object(self.bridge,'command',return_value=saved) as command:
                answer=run_agent(self.assistant,owner,'Package this map on my canvas',cfg,view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
            command.assert_called_once()
            self.assertEqual(answer['studio_commands'],[saved])
            self.assertEqual(answer['claims'],[])
            self.assertEqual(answer['kind'],'Checked Canvas operation')
            self.assertNotIn('opened',answer['summary'])

    def test_model_presentation_draft_survives_invalid_final_wording(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        import threading,time
        document=self.board();owner=self.grant(document);calls=[]
        view={'studio':{'document_id':document['id'],'frozen_evidence_ids':[],'run_nonce':'draft'}}
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('draft_studio_action',{'action':'build_investigation','arguments':{},'base_revision':document['revision']})])
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Invented','interpretation':'I added 999 satellite measurements.'})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Prepare this investigation',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(len(answer['studio_proposals']),1)
        self.assertTrue(answer['studio_proposals'][0]['requires_apply'])
        self.assertEqual(self.service.get_document(self.owner,document['id'])['revision'],document['revision'])
        self.assertNotIn('999',str(answer))

    def test_workflow_proposal_is_checked_and_never_runs_or_overwrites_a_saved_recipe(self):
        document = self.board()
        owner = self.grant(document)
        proposal = self.bridge.propose(owner, document['id'], 'create_workflow_draft', {'template_id': 'findings-to-story'}, document['revision'])
        applied = self.bridge.apply(self.owner, document['id'], proposal['proposal_id'])
        self.assertEqual(applied['workflow_draft']['document_id'], document['id'])
        self.assertTrue(applied['workflow_draft']['definition']['nodes'])
        self.assertIsNone(self.service.document_projects(self.owner, document['id'])['workflow'])
        self.assertEqual(self.service.get_document(self.owner, document['id'])['state'], document['state'])
        with self.service.store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM workflow_runs').fetchone()[0], 0)
        with self.assertRaises(StudioError):
            self.bridge.propose(owner, document['id'], 'create_workflow_draft', {'definition': {'nodes': [{'id': 'shell', 'type': 'script', 'params': {'code': 'bad'}}]}}, document['revision'])
        self.add_card(document, 'changed', 'text')
        with self.assertRaises(Conflict):
            self.bridge.apply(self.owner, document['id'], proposal['proposal_id'])

    def setUp(self):
        super().setUp()
        self.assistant = AssistantService(self.database, self.root / 'assistant' / 'workspace.sqlite3')
        self.addCleanup(self.assistant.close)
        self.service.assistant = self.assistant
        self.bridge = StudioAssistant(self.service, self.assistant)
        self.assistant.studio_bridge = self.bridge

    def grant(self, document):
        owner = self.service.assistant_owner(self.owner)
        self.assistant.store.artifact(owner, 'studio_access', {'principal': self.owner, 'document_id': document['id']})
        return owner

    def test_studio_cannot_read_another_assistant_session_or_board(self):
        document = self.board()
        owner = self.grant(document)
        self.assertEqual(self.bridge.board(owner, document['id'])['id'], document['id'])
        outsider = self.service.assistant_owner(self.other)
        with self.assertRaises(PermissionError): self.bridge.board(outsider, document['id'])
        with self.assertRaises(PermissionError): self.bridge.apply(self.other, document['id'], 'not-owned')

    def test_proposal_is_a_draft_until_applied_and_a_stale_proposal_cannot_mutate(self):
        document = self.add_card(self.board(), 'a', 'text')
        owner = self.grant(document)
        proposal = self.bridge.propose(owner, document['id'], 'arrange_cards', {'cards': [{'id': 'a', 'transform': {'x': 400, 'y': 100, 'w': 360, 'h': 240}}]}, document['revision'])
        before = self.service.get_document(self.owner, document['id'])
        self.assertNotEqual(before['state']['cards']['a']['transform']['x'], 400)
        applied = self.bridge.apply(self.owner, document['id'], proposal['proposal_id'])['document']
        self.assertEqual(applied['state']['cards']['a']['transform']['x'], 400)
        with self.assertRaises(Conflict): self.bridge.apply(self.owner, document['id'], proposal['proposal_id'])
        self.service.undo(self.owner, document['id'])
        self.assertEqual(self.service.get_document(self.owner, document['id'])['state']['cards']['a']['transform'], before['state']['cards']['a']['transform'])

    def test_proposals_cannot_invent_numeric_scene_data_or_edit_locked_cards(self):
        document = self.add_card(self.board(), 'a', 'text', locked=True)
        owner = self.grant(document)
        with self.assertRaises(StudioError): self.bridge.propose(owner, document['id'], 'create_story_draft', {'chapters': [{'values': [1, 2, 3]}]}, document['revision'])
        with self.assertRaises(StudioError): self.bridge.propose(owner, document['id'], 'arrange_cards', {'cards': [{'id': 'a', 'transform': {}}]}, document['revision'])

    def test_study_and_frozen_evidence_enter_the_existing_orchestrator(self):
        document, snapshot = self.bound_board()
        captured = {}
        def start(owner, request):
            captured.update(owner=owner, request=request)
            identifier, _ = self.assistant.store.create_run(owner, 'test-request', request)
            return {'id': identifier, 'status': 'queued'}
        with patch.object(self.assistant, 'start', side_effect=start):
            job = self.bridge.start(self.owner, document['id'], {'base_revision': document['revision'], 'operation': 'missingness'})
        view = captured['request']['view']
        self.assertEqual(view['studio']['document_id'], document['id'])
        receipt = self.assistant.store.get_artifact(captured['owner'], view['studio']['frozen_evidence_ids'][0], 'evidence')['body']
        self.assertEqual(receipt['sha256'], snapshot['receipt_sha256'])
        with self.assertRaises((PermissionError, NotFound)): self.bridge.run(self.other, document['id'], job['id'])
        before = self.assistant.store.session(captured['owner'])['context']
        with self.assertRaises(Conflict): self.bridge.start(self.owner, document['id'], {'base_revision': document['revision'], 'operation': 'missingness'})
        self.assertEqual(self.assistant.store.session(captured['owner'])['context'], before)
        self.bridge.run(self.owner, document['id'], job['id'], cancel=True)
        self.assertEqual(self.assistant.store.run(captured['owner'], job['id'])['status'], 'cancelled')

    def test_attached_analytical_surface_uses_same_runner_and_rejects_stale_or_foreign_reference(self):
        from fireatlas.studio.orchestration import CONTEXT_SCHEMA
        from fireatlas.assistant.contracts import normalize_context
        owner=self.service.assistant_owner(self.owner)
        study=normalize_context(self.study['context'])
        attached={'schema':CONTEXT_SCHEMA,'surface':'investigate','origin_instance_id':'pane-one','origin_tab_id':'tab-one',
            'context_revision':1,'study_selection':study,'active_view':{'operation':'replay','source':'MODIS_SP','domain':[0,7]},
            'result_refs':[],'destination':{'intent':'new-board'}}
        ref=self.bridge.attach_surface(self.owner,owner,{'context':attached})['attachment_id']
        with self.assertRaises(PermissionError):self.bridge.surface(self.service.assistant_owner(self.other),ref,study)
        with self.assertRaises(Conflict):self.bridge.surface(owner,ref,{**study,'day':'2015-07-02'})
        command=self.bridge.surface_command(owner,ref,study,'visualization_to_investigation',{},'jarvis:mock-nonce:package')
        import time
        for _ in range(100):
            saved=self.service.commands.get(self.owner,command['id'])
            if saved['status'] in {'awaiting_view_ack','failed','partial'}:break
            time.sleep(.03)
        self.assertEqual(saved['status'],'awaiting_view_ack',saved)
        self.bridge.cancel_commands(owner,'unrelated-nonce')
        self.assertEqual(self.service.commands.get(self.owner,command['id'])['status'],'awaiting_view_ack')
        self.bridge.cancel_commands(owner,'mock-nonce')
        self.assertEqual(self.service.commands.get(self.owner,command['id'])['status'],'cancelled')

    def test_speech_success_and_uncertain_failure_share_existing_budget_reservations(self):
        owner = self.service.assistant_owner(self.owner)
        with patch.dict('os.environ', {'FIREATLAS_TTS_MAX_REQUEST_USD': '0.01'}), patch('fireatlas.assistant.agent.provider_config', return_value={'free_only': False}):
            data = synthesize_checked(self.assistant, owner, 'A checked explanation.', 'test-revision', transport=lambda text: b'audio')
            self.assertEqual(data, b'audio')
            self.assertAlmostEqual(self.assistant.store.budget(owner)['used_or_reserved'], .01)
            def unavailable(text): raise RuntimeError('transport interrupted after send')
            with self.assertRaises(RuntimeError): synthesize_checked(self.assistant, owner, 'Another checked explanation.', 'test-revision', transport=unavailable)
            self.assertAlmostEqual(self.assistant.store.budget(owner)['used_or_reserved'], .02)
            with self.assistant.store.connection() as db:
                states = [r['state'] for r in db.execute('SELECT state FROM reservations WHERE session=?', (owner,))]
            self.assertIn('reserved', states)
            self.assertEqual(len(states), 2)
