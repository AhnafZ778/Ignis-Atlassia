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
    def test_model_receives_only_current_whiteboards_recent_conversation(self):
        import json, threading, time
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
        board=self.board(); owner=self.grant(board)
        self.bridge.save_conversation_turn(owner,board['id'],'run-a','What is the pattern?',{'title':'Pattern','summary':'The selected note describes a comparison.'})
        other=self.board(title='Other board'); self.grant(other)
        self.bridge.save_conversation_turn(owner,other['id'],'run-b','Another investigation',{'summary':'Private context'})
        view={'studio':{'document_id':board['id'],'whiteboard':True,'unscoped':True,'frozen_evidence_ids':[], 'frozen_evidence_refs':{},'selected_notes':[{'element_id':'note','text':'Compare the sensors'}]}}
        prompts=[]
        def respond(messages,info):
            for message in messages:
                for part in message.parts:
                    if not isinstance(part,UserPromptPart): continue
                    for content in part.content if isinstance(part.content,list) else [part.content]:
                        if isinstance(content,str) and content.startswith('{'): prompts.append(json.loads(content))
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Follow-up','interpretation':'Compare the selected sensors.'})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            run_agent(self.assistant,owner,'Explain that again',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        history=prompts[0]['recent_investigations']
        self.assertEqual([entry['question'] for entry in history],['What is the pattern?'])
        self.assertEqual(history[0]['summary'],'The selected note describes a comparison.')

    def test_conversation_survives_assistant_session_replacement_and_is_owned(self):
        board=self.board(); owner=self.grant(board)
        self.bridge.save_conversation_turn(owner,board['id'],'run-one','Why?',{'title':'Answer','summary':'Because of the evidence.','claims':[{'label':'Count','value':4,'unit':'cells'}]})
        self.bridge.save_conversation_turn(owner,board['id'],'run-one','Why?',{'title':'Answer','summary':'Because of the evidence.'})
        fresh=self.assistant.store.create_session(self.study['context'])
        self.assistant.store.artifact(fresh,'studio_access',{'principal':self.owner,'document_id':board['id']})
        self.assertEqual(self.bridge.conversation(fresh,board['id']),[{'question':'Why?','title':'Answer','summary':'Because of the evidence.','claims':[{'label':'Count','value':4,'unit':'cells'}]}])
        outsider=self.service.assistant_owner(self.other)
        with self.assertRaises(PermissionError):self.bridge.conversation(outsider,board['id'])
        for index in range(35):self.bridge.save_conversation_turn(fresh,board['id'],f'run-{index}',str(index),{'title':'','summary':''})
        self.assertEqual([item['question'] for item in self.bridge.conversation(fresh,board['id'])],[str(index) for index in range(29,35)])
        with self.service.store.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM science_results WHERE principal_id=? AND kind='whiteboard_conversation'",(self.owner,)).fetchone()[0],30)
        self.service.store.delete_document(self.owner,board['id'],board['revision'])
        with self.service.store.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM science_results WHERE principal_id=? AND kind='whiteboard_conversation'",(self.owner,)).fetchone()[0],0)

    def test_completed_whiteboard_run_saves_conversation(self):
        import threading
        from fireatlas.assistant.contracts import normalize_context
        board=self.board(); owner=self.grant(board)
        run,_=self.assistant.store.create_run(owner,'conversation-run',{})
        view={'studio':{'document_id':board['id'],'whiteboard':True}}
        with patch('fireatlas.assistant.service.run_agent',return_value={'title':'Answer','summary':'A useful summary','claims':[]}):
            self.assistant._run(owner,run,normalize_context(self.study['context']),view,'Explain the trend',None,{},threading.Event(),[])
        self.assertEqual(self.assistant.store.run(owner,run)['status'],'completed')
        self.assertEqual(self.bridge.conversation(owner,board['id'])[0]['summary'],'A useful summary')

    def test_selecting_saved_assistant_snapshot_reuses_only_owned_evidence(self):
        document,snapshot=self.bound_board(operation='replay',kind='map')
        element={'id':'saved-claim','type':'text','text':'Saved value','x':0,'y':0,'width':100,'height':20,
                 'customData':{'fireatlas':{'documentId':document['id'],'snapshotId':snapshot['id'],'snapshotHash':snapshot['snapshot_sha256']}}}
        document=self.service.transact(self.owner,document['id'],{'base_revision':document['revision'],'ops':[{'op':'patch_whiteboard','changes':[{'kind':'element','id':'saved-claim','position':0,'value':element}]}]})
        body={'base_revision':document['revision'],'whiteboard':True,'selected_snapshot_elements':['saved-claim']}
        with patch.object(self.assistant,'start',return_value={'id':'job'}) as start:
            self.bridge.start(self.owner,document['id'],body)
            studio=start.call_args.args[1]['view']['studio']
            self.assertEqual(len(studio['frozen_evidence_ids']),1)
            ref=studio['frozen_evidence_refs'][studio['frozen_evidence_ids'][0]]
            self.assertEqual(ref['snapshotId'],snapshot['id'])
            self.assertNotIn('cardId',ref)
            self.assertFalse(studio['unscoped'])
        with self.assertRaises(StudioError):self.bridge.start(self.owner,document['id'],{**body,'selected_snapshot_elements':['missing']})
        with self.assertRaises(NotFound):self.bridge.start(self.other,document['id'],body)
        element['customData']['fireatlas']['snapshotHash']='changed'
        altered=self.service.transact(self.owner,document['id'],{'base_revision':document['revision'],'ops':[{'op':'patch_whiteboard','changes':[{'kind':'element','id':'saved-claim','position':0,'value':element}]}]})
        with self.assertRaises(StudioError):self.bridge.start(self.owner,document['id'],{**body,'base_revision':altered['revision']})

    def test_challenge_on_analysis_note_resolves_its_owned_frozen_sources(self):
        document,snapshot=self.bound_board(operation='replay',kind='map')
        ref={'documentId':document['id'],'snapshotId':snapshot['id'],'snapshotHash':snapshot['snapshot_sha256']}
        second=self.service.resolve_binding(self.owner,document['id'],{'operation':'observations','context':{},'arguments':{}})['snapshot']
        second_ref={'documentId':document['id'],'snapshotId':second['id'],'snapshotHash':second['snapshot_sha256']}
        note={'id':'analysis-note','type':'text','text':'Repeated observations could explain the pattern.','x':0,'y':0,'width':200,'height':40,
              'customData':{'fireatlas':{'documentId':document['id'],'kind':'assistant-analysis-note','sourceBindings':[ref,second_ref]}}}
        document=self.service.transact(self.owner,document['id'],{'base_revision':document['revision'],
            'ops':[{'op':'patch_whiteboard','changes':[{'kind':'element','id':note['id'],'position':0,'value':note}]}]})
        body={'base_revision':document['revision'],'whiteboard':True,'whiteboard_challenge':True,
              'selected_snapshot_elements':[note['id']],'selected_note_elements':[note['id']]}
        with patch.object(self.assistant,'start',return_value={'id':'job'}) as start:
            self.bridge.start(self.owner,document['id'],body)
            studio=start.call_args.args[1]['view']['studio']
            self.assertTrue(studio['challenge'])
            self.assertEqual(len(studio['frozen_evidence_ids']),2)
            self.assertEqual(studio['selected_notes'][0]['text'],note['text'])
        ref['snapshotHash']='wrong'
        changed=self.service.transact(self.owner,document['id'],{'base_revision':document['revision'],
            'ops':[{'op':'patch_whiteboard','changes':[{'kind':'element','id':note['id'],'position':0,'value':note}]}]})
        with self.assertRaises(StudioError):self.bridge.start(self.owner,document['id'],{**body,'base_revision':changed['revision']})

    def test_preserve_completed_assistant_claims_is_owned_and_idempotent(self):
        from fireatlas.assistant.agent import fact
        document, snapshot = self.bound_board(operation='replay', kind='map')
        receipt = self.service.snapshot_receipt(self.owner, document['id'], snapshot['id'])['receipt']
        owner = self.grant(document)
        result_id = self.assistant.store.artifact(owner, 'evidence', receipt)
        claim = fact({**receipt, 'id':result_id}, snapshot['facts'][0]['path'])
        result_id = claim['result_id']
        def complete(nonce, value):
            run,_ = self.assistant.store.create_run(owner, nonce, {})
            self.service.store.artifact(self.owner, 'assistant_run', {'document_id':document['id'],'run_id':run,'owner':owner,'board_revision':document['revision'],'run_nonce':nonce})
            self.assistant.store.finish(owner, run, 'completed', {'claims':[value]})
            return run
        run=complete('real-run', claim)
        first = self.bridge.preserve_claims(self.owner, document['id'], run)['bindings'][result_id]
        second = self.bridge.preserve_claims(self.owner, document['id'], run)['bindings'][result_id]
        self.assertEqual(first, second)
        self.assertTrue(self.service.snapshot_report(self.owner, document['id'], first['snapshotId'])['verification']['verified'])
        element={'id':'assistant-claim','type':'text','text':'Saved claim','x':0,'y':0,'width':100,'height':20,
                 'customData':{'fireatlas':{'documentId':document['id'],'snapshotId':first['snapshotId'],'snapshotHash':first['snapshotHash'],
                                            'claims':[{'result_id':first['resultId'],'path':claim['path'],'value':claim['value']}]}}}
        current=self.service.transact(self.owner,document['id'],{'base_revision':document['revision'],'ops':[{'op':'patch_whiteboard','changes':[{'kind':'element','id':'assistant-claim','position':0,'value':element}]}]})
        with patch('fireatlas.studio.portability.StorageBudget.check',return_value={}):
            job=self.service.portability.submit(self.owner,document['id'],{'format':'native','revision':current['revision']},background=False)
        self.assertEqual(job['status'],'completed',job)
        path,_=self.service.portability.download(self.owner,job['id'])
        restored=self.service.portability.restore(self.other,path)['document']
        meta=self.service.store.whiteboard(self.other,restored['id'])['elements'][0]['customData']['fireatlas']
        self.assertTrue(self.service.snapshot_report(self.other,restored['id'],meta['snapshotId'])['verification']['verified'])
        self.assertEqual(meta['claims'][0]['result_id'],restored['snapshots'][meta['snapshotId']]['result_id'])
        with self.assertRaises(NotFound):
            self.bridge.preserve_claims(self.other, document['id'], run)
        forged=complete('forged-run', {**claim, 'value':999999999})
        with self.assertRaises(StudioError):
            self.bridge.preserve_claims(self.owner, document['id'], forged)

    def test_guided_replay_claim_keeps_its_unit_when_preserved(self):
        from fireatlas.assistant.agent import fact, guided_answer
        document, snapshot = self.bound_board(operation='replay', kind='map')
        receipt = self.service.snapshot_receipt(self.owner, document['id'], snapshot['id'])['receipt']
        owner = self.grant(document)
        result_id = self.assistant.store.artifact(owner, 'evidence', receipt)
        full = {**receipt, 'id': result_id}
        claim = next(item for item in guided_answer(full)['claims'] if item['path'] == '/summary/joint_cell_days')
        self.assertEqual(claim['unit'], 'cell-days')
        self.assertEqual(fact(full, claim['path'])['unit'], claim['unit'])
        run, _ = self.assistant.store.create_run(owner, 'guided-unit', {})
        self.service.store.artifact(self.owner, 'assistant_run', {'document_id':document['id'], 'run_id':run, 'owner':owner, 'board_revision':document['revision'], 'run_nonce':'guided-unit'})
        self.assistant.store.finish(owner, run, 'completed', {'claims':[claim]})
        saved = self.bridge.preserve_claims(self.owner, document['id'], run)['bindings'][result_id]
        report = self.service.snapshot_report(self.owner, document['id'], saved['snapshotId'])
        self.assertTrue(report['verification']['verified'])
        saved_receipt = self.service.snapshot_receipt(self.owner, document['id'], saved['snapshotId'])
        self.assertEqual(saved_receipt['receipt']['sha256'], receipt['sha256'])
        forged, _ = self.assistant.store.create_run(owner, 'wrong-unit', {})
        self.service.store.artifact(self.owner, 'assistant_run', {'document_id':document['id'], 'run_id':forged, 'owner':owner, 'board_revision':document['revision'], 'run_nonce':'wrong-unit'})
        self.assistant.store.finish(owner, forged, 'completed', {'claims':[{**claim, 'unit':'records'}]})
        with self.assertRaises(StudioError):
            self.bridge.preserve_claims(self.owner, document['id'], forged)

    def test_assistant_can_read_selected_board_notes(self):
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
        import threading, time
        board = self.board(); owner = self.grant(board)
        view = {'studio': {'document_id':board['id'], 'whiteboard':True, 'unscoped':True,
                           'frozen_evidence_ids':[], 'frozen_evidence_refs':{},
                           'selected_notes':[{'element_id':'note','text':'Compare July counts'}]}}
        calls = []
        def respond(messages, info):
            calls.append(1)
            if len(calls) == 1:
                return ModelResponse(parts=[ToolCallPart('read_selected_board_notes', {})])
            note = next(p.content for message in messages for p in message.parts if isinstance(p, ToolReturnPart) and p.tool_name == 'read_selected_board_notes')
            self.assertEqual(note['notes'][0]['text'], 'Compare July counts')
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {'title':'A comparison', 'interpretation':'Compare the July counts between sensors.'})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ', env):
            answer = run_agent(self.assistant, owner, 'Explain the selected note', normalize_context(self.study['context']), view, threading.Event(), time.monotonic()+30, lambda _:None, model=FunctionModel(respond))
        self.assertEqual(answer['title'], 'A comparison')

    def test_selected_board_notes_are_loaded_from_owned_saved_scene(self):
        doc = self.board()
        elements = [
            {'id':'shape','type':'rectangle','x':0,'y':0,'width':100,'height':50},
            {'id':'label','type':'text','text':'Compare the two sensors','containerId':'shape','x':0,'y':0,'width':100,'height':20},
            {'id':'private','type':'text','text':'Unselected note','x':0,'y':80,'width':100,'height':20},
        ]
        changes = [{'kind':'element','id':element['id'],'position':i,'value':element} for i, element in enumerate(elements)]
        doc = self.service.transact(self.owner, doc['id'], {'base_revision':doc['revision'],'ops':[{'op':'patch_whiteboard','changes':changes}]})
        body = {'base_revision':doc['revision'], 'whiteboard':True, 'selected_note_elements':['shape']}
        with patch.object(self.assistant, 'start', return_value={'id':'job'}) as start:
            self.bridge.start(self.owner, doc['id'], body)
            self.assertEqual(start.call_args.args[1]['view']['studio']['selected_notes'], [{'element_id':'label','text':'Compare the two sensors'}])
        for selection in (['missing'], ['private'] * 21, ['shape','missing']):
            with self.assertRaises(StudioError):
                self.bridge.start(self.owner, doc['id'], {**body, 'selected_note_elements':selection})
        with self.assertRaises(NotFound):
            self.bridge.start(self.other, doc['id'], body)

    def test_model_can_read_whole_board_notes(self):
        import threading, time
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
        board=self.board(); owner=self.grant(board)
        view={'studio':{'document_id':board['id'],'whiteboard':True,'unscoped':True,
                        'frozen_evidence_ids':[], 'frozen_evidence_refs':{}, 'notes_scope':'board',
                        'selected_notes':[{'element_id':'note','text':'Compare the two sensors'},
                                          {'element_id':'generated','text':'Earlier diagram','origin':'assistant_placed'}]}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:
                return ModelResponse(parts=[ToolCallPart('read_selected_board_notes',{})])
            result=next(part.content for message in messages for part in message.parts if isinstance(part,ToolReturnPart) and part.tool_name=='read_selected_board_notes')
            self.assertEqual(result['scope'],'board')
            self.assertEqual(result['notes'][0]['text'],'Compare the two sensors')
            self.assertEqual(result['notes'][1]['origin'],'assistant_placed')
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Investigation','interpretation':'The board compares the sensors.'})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Explain the investigation',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['title'],'Investigation')

    def test_selected_visual_is_owned_bounded_and_attached_to_run(self):
        import base64, struct
        doc=self.board()
        shape={'id':'shape','type':'rectangle','x':0,'y':0,'width':100,'height':50}
        doc=self.service.transact(self.owner,doc['id'],{'base_revision':doc['revision'],'ops':[{'op':'patch_whiteboard','changes':[{'kind':'element','id':'shape','position':0,'value':shape}]}]})
        png=b'\x89PNG\r\n\x1a\n'+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',100,50)
        body={'base_revision':doc['revision'],'whiteboard':True,'message':'Describe this',
              'visual_capture':{'element_ids':['shape'],'png':base64.b64encode(png).decode()}}
        with patch.object(self.assistant,'start',return_value={'id':'job'}) as start:
            self.bridge.start(self.owner,doc['id'],body)
            owner,request=start.call_args.args
            self.assertEqual(request['view']['studio']['selected_visual']['element_ids'],['shape'])
            self.assertEqual(len(request['image_ids']),1)
            self.assertEqual(self.assistant.store.get_artifact(owner,request['image_ids'][0],'image')['body']['data'],body['visual_capture']['png'])
        with self.assertRaises(StudioError):self.bridge.start(self.owner,doc['id'],{**body,'visual_capture':{**body['visual_capture'],'element_ids':['missing']}})
        with self.assertRaises(NotFound):self.bridge.start(self.other,doc['id'],body)
        with self.assertRaises(StudioError):self.bridge.start(self.owner,doc['id'],{**body,'visual_capture':{**body['visual_capture'],'png':'invalid'}})

    def test_selected_visual_can_receive_nonmeasurement_interpretation(self):
        import threading,time
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart
        board=self.board();owner=self.grant(board)
        view={'studio':{'document_id':board['id'],'whiteboard':True,'unscoped':True,'selected_visual':{'element_ids':['shape']},'frozen_evidence_ids':[],'frozen_evidence_refs':{}}}
        def respond(messages,info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Selected visual','interpretation':'The drawing contains a shape.',
                'diagram':{'nodes':[{'id':'visual','kind':'context','label':'A shape'},{'id':'question','kind':'question','label':'What does it represent?'}],
                           'edges':[{'source':'visual','target':'question','relation':'question'}]}})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Draw a diagram of this visual',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,images=[(b'visual','image/png')],model=FunctionModel(respond))
        self.assertEqual(answer['kind'],'AI interpretation of selected visual')
        self.assertEqual(answer['claims'],[])
        self.assertEqual(answer['diagram']['nodes'][0]['label'],'A shape')

    def test_note_diagram_can_use_owner_checked_context_without_extra_tool_call(self):
        import threading, time
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart
        board=self.board(); owner=self.grant(board)
        view={'studio':{'document_id':board['id'],'whiteboard':True,'unscoped':True,
                        'frozen_evidence_ids':[], 'frozen_evidence_refs':{}, 'notes_scope':'board',
                        'selected_notes':[{'element_id':'note','text':'Compare the sensors'}]}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            self.assertIn('Compare the sensors',str(messages))
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{
                'title':'Board notes','interpretation':'The notes compare the sensors.',
                'diagram':{'nodes':[{'id':'context','label':'Sensor comparison','kind':'context'},
                                    {'id':'question','label':'What differs?','kind':'question'}],
                           'edges':[{'source':'context','target':'question','relation':'question'}]}})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Draw a diagram of the board notes',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(len(calls),1)
        self.assertEqual(answer['diagram']['nodes'][0]['label'],'Sensor comparison')

    def test_note_only_diagram_is_returned_after_reading_board(self):
        import threading, time
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart
        board=self.board(); owner=self.grant(board)
        view={'studio':{'document_id':board['id'],'whiteboard':True,'unscoped':True,
                        'frozen_evidence_ids':[], 'frozen_evidence_refs':{}, 'notes_scope':'board',
                        'selected_notes':[{'element_id':'note','text':'Compare the two sensors'}]}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:
                return ModelResponse(parts=[ToolCallPart('read_selected_board_notes',{})])
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{
                'title':'Board explanation','interpretation':'The board compares the sensors.',
                'diagram':{'nodes':[{'id':'context','label':'Cloud cover','kind':'context'},
                                    {'id':'summary','label':'A shorter model label','kind':'interpretation'},
                                    {'id':'question','label':'What differs between the sensors?','kind':'question'}],
                           'edges':[{'source':'context','target':'summary','relation':'context'},{'source':'summary','target':'question','relation':'question'}]}})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Draw a diagram explaining the board',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual([node['kind'] for node in answer['diagram']['nodes']],['context','interpretation','question'])
        self.assertEqual(answer['diagram']['nodes'][1]['label'],answer['summary'])
        self.assertEqual(answer['diagram']['edges'][1]['target'],'question')

    def test_note_only_diagram_cannot_claim_unread_evidence(self):
        import threading, time
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart
        board=self.board(); owner=self.grant(board)
        ref={'documentId':board['id'],'cardId':'card','snapshotId':'snap','snapshotHash':'hash'}
        view={'studio':{'document_id':board['id'],'whiteboard':True,'unscoped':True,
                        'frozen_evidence_ids':[], 'frozen_evidence_refs':{'saved':ref}, 'notes_scope':'board',
                        'selected_notes':[{'element_id':'note','text':'Compare sensors'}]}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:
                return ModelResponse(parts=[ToolCallPart('read_selected_board_notes',{})])
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{
                'title':'Board','interpretation':'The notes compare the sensors.',
                'diagram':{'nodes':[{'id':'source','label':'Saved evidence','kind':'evidence','evidence_id':'saved'}], 'edges':[]}})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Draw a diagram of the board',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertIsNone(answer['diagram'])
        self.assertEqual(answer['summary'],'The notes compare the sensors.')

    def test_note_question_model_failure_does_not_request_a_study(self):
        import threading,time
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart
        from pydantic_ai.exceptions import UnexpectedModelBehavior
        board=self.board(); owner=self.grant(board)
        view={'studio':{'document_id':board['id'],'whiteboard':True,'unscoped':True,
              'frozen_evidence_ids':[], 'frozen_evidence_refs':{}, 'notes_scope':'board',
              'selected_notes':[{'element_id':'note','text':'Compare sensors'}]}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('read_selected_board_notes',{})])
            raise UnexpectedModelBehavior('test-only failure')
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Draw a diagram of the board',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['kind'],'Assistant unavailable')
        self.assertEqual(answer['fallback_reason'],'UnexpectedModelBehavior')
        self.assertTrue(answer['ai_wording_unavailable'])
        self.assertNotIn('study',answer['summary'].lower())

    def test_whiteboard_question_model_failure_offers_retry_without_study_prompt(self):
        import threading, time
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.exceptions import UnexpectedModelBehavior
        board=self.board(); owner=self.grant(board)
        view={'studio':{'document_id':board['id'],'whiteboard':True,'unscoped':True,
              'frozen_evidence_ids':[], 'frozen_evidence_refs':{}, 'notes_scope':'board',
              'selected_notes':[{'element_id':'note','text':'Compare sensors'}]}}
        def fail(messages,info):
            raise UnexpectedModelBehavior('test-only failure')
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'What does this note suggest?',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(fail))
        self.assertEqual(answer['kind'],'Assistant unavailable')
        self.assertIn('try asking again',answer['summary'])
        self.assertEqual(answer['claims'],[])
        self.assertEqual(answer['fallback_reason'],'UnexpectedModelBehavior')

    def test_unselected_whiteboard_question_reads_bounded_owned_notes(self):
        doc = self.board()
        elements = [{'id':f'note-{i}','type':'text','text':f'Board note {i}','x':0,'y':i*20,'width':100,'height':20} for i in range(25)]
        changes = [{'kind':'element','id':item['id'],'position':i,'value':item} for i,item in enumerate(elements)]
        doc = self.service.transact(self.owner, doc['id'], {'base_revision':doc['revision'],'ops':[{'op':'patch_whiteboard','changes':changes}]})
        body = {'base_revision':doc['revision'], 'whiteboard':True}
        with patch.object(self.assistant, 'start', return_value={'id':'job'}) as start:
            self.bridge.start(self.owner, doc['id'], body)
            studio = start.call_args.args[1]['view']['studio']
            self.assertEqual(studio['notes_scope'], 'board')
            self.assertEqual(len(studio['selected_notes']), 20)
            self.assertEqual(studio['selected_notes'][0]['text'], 'Board note 0')
            self.bridge.start(self.owner, doc['id'], {**body, 'selected_note_elements':['note-2']})
            studio = start.call_args.args[1]['view']['studio']
            self.assertEqual(studio['notes_scope'], 'selection')
            self.assertEqual([note['text'] for note in studio['selected_notes']], ['Board note 2'])
        with self.assertRaises(NotFound):
            self.bridge.start(self.other, doc['id'], body)

    def test_note_diagram_failure_before_read_does_not_ask_for_study(self):
        import threading, time
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.exceptions import UnexpectedModelBehavior
        from pydantic_ai.models.function import FunctionModel
        board=self.board(); owner=self.grant(board)
        view={'studio':{'document_id':board['id'],'whiteboard':True,'unscoped':True,
                        'frozen_evidence_ids':[], 'frozen_evidence_refs':{}, 'notes_scope':'board',
                        'selected_notes':[{'element_id':'note','text':'Compare the sensors'}]}}
        def fail_before_read(messages,info):
            raise UnexpectedModelBehavior('test-only failure')
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Draw a diagram of the board',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(fail_before_read))
        self.assertEqual(answer['kind'],'Assistant unavailable')
        self.assertNotIn('study',answer['summary'].lower())

    def test_board_notes_identify_assistant_placed_text_and_bound_labels(self):
        doc = self.board()
        elements = [
            {'id':'user-note','type':'text','text':'Researcher note','x':0,'y':0,'width':100,'height':20},
            {'id':'ai-box','type':'rectangle','x':0,'y':30,'width':100,'height':50,
             'customData':{'fireatlas':{'documentId':doc['id'],'kind':'assistant-diagram'}}},
            {'id':'ai-label','type':'text','text':'AI interpretation','containerId':'ai-box','x':0,'y':30,'width':100,'height':20},
            {'id':'ai-text','type':'text','text':'An earlier explanation','x':0,'y':90,'width':100,'height':20,
             'customData':{'fireatlas':{'documentId':doc['id'],'kind':'assistant-explanation'}}},
            {'id':'untrusted-tag','type':'text','text':'Other text','x':0,'y':120,'width':100,'height':20,
             'customData':{'fireatlas':'malformed'}},
        ]
        changes=[{'kind':'element','id':item['id'],'position':i,'value':item} for i,item in enumerate(elements)]
        doc=self.service.transact(self.owner,doc['id'],{'base_revision':doc['revision'],'ops':[{'op':'patch_whiteboard','changes':changes}]})
        body={'base_revision':doc['revision'],'whiteboard':True}
        with patch.object(self.assistant,'start',return_value={'id':'job'}) as start:
            self.bridge.start(self.owner,doc['id'],body)
            notes=start.call_args.args[1]['view']['studio']['selected_notes']
            self.assertEqual([n.get('origin') for n in notes],[None,None,'assistant_placed','assistant_placed'])
            self.bridge.start(self.owner,doc['id'],{**body,'selected_note_elements':['ai-box']})
            notes=start.call_args.args[1]['view']['studio']['selected_notes']
            self.assertEqual(notes,[{'element_id':'ai-label','text':'AI interpretation','origin':'assistant_placed'}])

    def test_whole_board_prioritizes_other_notes_before_earlier_assistant_output(self):
        doc=self.board()
        elements=[{'id':f'ai-{i}','type':'text','text':f'AI output {i}','x':0,'y':i*20,'width':100,'height':20,
                   'customData':{'fireatlas':{'documentId':doc['id'],'kind':'assistant-explanation'}}} for i in range(20)]
        elements.append({'id':'new-note','type':'text','text':'A later research note','x':0,'y':420,'width':100,'height':20})
        changes=[{'kind':'element','id':item['id'],'position':i,'value':item} for i,item in enumerate(elements)]
        doc=self.service.transact(self.owner,doc['id'],{'base_revision':doc['revision'],'ops':[{'op':'patch_whiteboard','changes':changes}]})
        with patch.object(self.assistant,'start',return_value={'id':'job'}) as start:
            self.bridge.start(self.owner,doc['id'],{'base_revision':doc['revision'],'whiteboard':True})
            notes=start.call_args.args[1]['view']['studio']['selected_notes']
            self.assertEqual(len(notes),20)
            self.assertEqual(notes[0]['element_id'],'new-note')
            self.assertEqual([n['element_id'] for n in notes[1:]],[f'ai-{i}' for i in range(19)])
            self.bridge.start(self.owner,doc['id'],{'base_revision':doc['revision'],'whiteboard':True,'selected_note_elements':['ai-19']})
            self.assertEqual(start.call_args.args[1]['view']['studio']['selected_notes'][0]['element_id'],'ai-19')

    def test_whole_board_prioritizes_research_note_over_chart_labels(self):
        doc=self.board()
        elements=[{'id':f'chart-{i}','type':'text','text':f'Value {i}','x':0,'y':i*20,'width':100,'height':20,
                   'customData':{'fireatlas':{'documentId':doc['id'],'kind':'park-platform-chart'}}} for i in range(25)]
        elements.append({'id':'question','type':'text','text':'Why did the readings differ?','x':0,'y':600,'width':100,'height':20})
        changes=[{'kind':'element','id':item['id'],'position':i,'value':item} for i,item in enumerate(elements)]
        doc=self.service.transact(self.owner,doc['id'],{'base_revision':doc['revision'],'ops':[{'op':'patch_whiteboard','changes':changes}]})
        with patch.object(self.assistant,'start',return_value={'id':'job'}) as start:
            self.bridge.start(self.owner,doc['id'],{'base_revision':doc['revision'],'whiteboard':True})
            notes=start.call_args.args[1]['view']['studio']['selected_notes']
            self.assertEqual(len(notes),20)
            self.assertEqual(notes[0]['element_id'],'question')
            self.assertEqual([n['element_id'] for n in notes[1:]],[f'chart-{i}' for i in range(19)])

    def test_whole_board_resolves_only_one_unambiguous_linked_table(self):
        from fireatlas.studio.datasets import add
        doc=self.board()
        table=add(self.service.store,self.owner,doc['id'],'sample.csv',b'day,count\n1,4\n')
        def shape(identifier,table_id,sha):
            return {'id':identifier,'type':'text','text':'Chart','x':0,'y':0,'width':100,'height':20,
                    'customData':{'fireatlas':{'documentId':doc['id'],'datasetId':table_id,'datasetHash':sha,'rowOffset':0}}}
        items=[shape('chart',table['id'],table['sha256']),{'id':'note','type':'text','text':'Explain the board','x':0,'y':30,'width':100,'height':20}]
        changes=[{'kind':'element','id':item['id'],'position':i,'value':item} for i,item in enumerate(items)]
        doc=self.service.transact(self.owner,doc['id'],{'base_revision':doc['revision'],'ops':[{'op':'patch_whiteboard','changes':changes}]})
        with patch.object(self.assistant,'start',return_value={'id':'job'}) as start:
            self.bridge.start(self.owner,doc['id'],{'base_revision':doc['revision'],'whiteboard':True})
            view=start.call_args.args[1]['view']['studio']
            self.assertEqual(view['selected_dataset']['id'],table['id'])
            self.assertEqual(view['dataset_scope'],'board')
            self.assertNotIn('selected_row_offset',view['selected_dataset'])
            self.assertEqual(view['notes_scope'],'board')
        second=add(self.service.store,self.owner,doc['id'],'second.csv',b'day,count\n1,7\n')
        new=shape('other',second['id'],second['sha256'])
        doc=self.service.transact(self.owner,doc['id'],{'base_revision':doc['revision'],'ops':[{'op':'patch_whiteboard','changes':[{'kind':'element','id':'other','position':2,'value':new}]}]})
        with patch.object(self.assistant,'start',return_value={'id':'job'}) as start:
            self.bridge.start(self.owner,doc['id'],{'base_revision':doc['revision'],'whiteboard':True})
            self.assertNotIn('selected_dataset',start.call_args.args[1]['view']['studio'])

    def test_diagram_fallback_keeps_saved_source_and_open_question(self):
        from pydantic_ai.models.function import FunctionModel
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        import threading,time
        document,snap=self.bound_board(operation='replay',kind='map');owner=self.grant(document)
        receipt=self.service.snapshot_receipt(self.owner,document['id'],snap['id'])['receipt']
        eid=self.assistant.store.artifact(owner,'evidence',receipt)
        binding={'documentId':document['id'],'cardId':document['state']['order'][0],'snapshotId':snap['id'],'snapshotHash':snap['snapshot_sha256'],'title':'Source'}
        view={'studio':{'document_id':document['id'],'whiteboard':True,'frozen_evidence_ids':[eid],'frozen_evidence_refs':{eid:binding}}}
        from pydantic_ai.exceptions import UnexpectedModelBehavior
        def fail(messages,info):raise UnexpectedModelBehavior('fixture wording failure')
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Draw a diagram of the evidence',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(fail))
        self.assertEqual(answer['diagram']['nodes'][0]['binding'],binding)
        self.assertEqual(answer['diagram']['nodes'][1]['kind'],'question')
        with patch.dict('os.environ',env):
            combined=run_agent(self.assistant,owner,'Draw a diagram and a chart',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(fail))
        self.assertEqual(combined['diagram']['nodes'][0]['binding'],binding)
        self.assertEqual(combined['visualizations'],[])  # A map is not a monthly comparison.
        for request in ('Explain the evidence without a chart', "Explain it, but don't draw a chart", 'Explain it with no grouped chart'):
            with self.subTest(request=request),patch.dict('os.environ',env):
                result=run_agent(self.assistant,owner,request,normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(fail))
            self.assertFalse(result.get('visualizations'))

    def test_comparison_diagram_fallback_explains_selected_series_with_checked_values(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.exceptions import UnexpectedModelBehavior
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        import threading,time
        document,snap=self.bound_board(operation='replay',kind='map');owner=self.grant(document)
        receipt=self.service.snapshot_receipt(self.owner,document['id'],snap['id'])['receipt']
        receipt['operation']='finding_comparison'
        receipt['payload']={'schema':'fireatlas-finding-investigation-v1','selected_series':'modis','comparison':{'series':{'modis':{'first':8,'second':3,'difference':-5},'viirs':{'first':2,'second':7,'difference':5}}}}
        eid=self.assistant.store.artifact(owner,'evidence',receipt)
        binding={'documentId':document['id'],'cardId':document['state']['order'][0],'snapshotId':snap['id'],'snapshotHash':snap['snapshot_sha256']}
        other_receipt={**receipt,'operation':'sources'}
        other_id=self.assistant.store.artifact(owner,'evidence',other_receipt)
        other_binding={**binding,'snapshotId':'other-snapshot'}
        view={'studio':{'document_id':document['id'],'whiteboard':True,'frozen_evidence_ids':[other_id,eid],'frozen_evidence_refs':{other_id:other_binding,eid:binding},'selected_comparisons':[{'snapshot_id':snap['id'],'series':'viirs'}]}}
        def fail(messages,info):raise UnexpectedModelBehavior('fixture wording failure')
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Explain and diagram this',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(fail))
        self.assertEqual(answer['summary'],'S-NPP observed activity increased between the selected periods.')
        self.assertEqual([claim['value'] for claim in answer['claims']],[2,7,5])
        self.assertTrue(all(claim['binding']==binding for claim in answer['claims']))
        self.assertTrue(answer['ai_wording_unavailable'])
        with patch.dict('os.environ',env):
            combined=run_agent(self.assistant,owner,'Draw a diagram and a chart',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(fail))
        self.assertTrue(combined['ai_wording_unavailable'])
        self.assertEqual(combined['visualizations'],[{'result_id':eid,'kind':'monthly-comparison','binding':binding}])
        self.assertEqual(combined['diagram']['nodes'][0]['binding'],binding)
        for request in ('Draw a diagram and scatter plot','Draw a diagram and grouped chart'):
            with self.subTest(request=request),patch.dict('os.environ',env):
                result=run_agent(self.assistant,owner,request,normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(fail))
            self.assertEqual(result['visualizations'],[])
        with patch.dict('os.environ',env):
            flow=run_agent(self.assistant,owner,'Draw a flow chart',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(fail))
        self.assertTrue(flow['diagram'])
        self.assertEqual(flow['visualizations'],[])
        with patch.dict('os.environ',env):
            only_diagram=run_agent(self.assistant,owner,'Draw a diagram but no chart',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(fail))
        self.assertTrue(only_diagram['diagram'])
        self.assertEqual(only_diagram['visualizations'],[])
        from fireatlas.assistant.board_diagram import validate_diagram
        validate_diagram(answer['diagram'],[eid])
        self.assertEqual(answer['diagram']['nodes'][0]['binding'],binding)
        multiple={**view,'studio':{**view['studio'],'selected_comparisons':[{'snapshot_id':snap['id'],'series':'viirs'},{'snapshot_id':snap['id'],'series':'modis'}]}}
        with patch.dict('os.environ',env):
            result=run_agent(self.assistant,owner,'Explain and diagram this',normalize_context(self.study['context']),multiple,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(fail))
        self.assertTrue(result['summary'].startswith('For the first selected comparison view:'))
        self.assertEqual([claim['value'] for claim in result['claims']],[2,7,5])
        for first,second,expected in [(0,0,'was unchanged'),(0,4,'increased'),(None,4,'Compare')]:
            receipt['payload']['comparison']['series']['viirs']={'first':first,'second':second,'difference':None if first is None else second-first}
            self.assistant.store.update_artifact(owner,eid,'evidence',receipt)
            with self.subTest(first=first,second=second),patch.dict('os.environ',env):
                result=run_agent(self.assistant,owner,'Explain and diagram this',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(fail))
            self.assertIn(expected,result['summary'])
            self.assertTrue(all(claim['value'] is not None for claim in result['claims']))
    def test_model_compares_imported_groups_using_all_rows(self):
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
        import threading,time
        board=self.board();owner=self.grant(board)
        table=add(self.service.store,self.owner,board['id'],'sample.csv',b'area,value\nA,0\nA,4\nB,7\n')
        view={'studio':{'document_id':board['id'],'whiteboard':True,'frozen_evidence_ids':[],
            'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('compare_selected_groups',{'group_column':'area','value_column':'value'})])
            result=next(p.content for message in messages for p in message.parts if isinstance(p,ToolReturnPart) and p.tool_name=='compare_selected_groups')
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Groups','interpretation':'The groups have different reported averages.',
                'claims':[{'result_id':result['result_id'],'path':'/groups/0/mean','label':'Mean'}],
                'diagram':{'nodes':[{'id':'source','kind':'evidence','label':'Table','evidence_id':result['result_id']},{'id':'question','kind':'question','label':'How do groups differ?'}], 'edges':[{'source':'source','target':'question','relation':'question'}]},
                'visualizations':[{'result_id':result['result_id'],'kind':'csv-groups'}]})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Compare the groups',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['claims'][0]['value'],2)
        self.assertEqual(answer['claims'][0]['label'],'A · mean')
        self.assertEqual(answer['claims'][0]['source_binding'],{'documentId':board['id'],'datasetId':table['id'],'datasetHash':table['sha256'],'groupColumn':'area','valueColumn':'value','groupName':'A','groupMetric':'mean'})
        self.assertEqual(answer['visualizations'][0]['binding'],{'documentId':board['id'],'datasetId':table['id'],'datasetHash':table['sha256'],'groupColumn':'area','valueColumn':'value'})
        self.assertEqual(answer['diagram']['nodes'][0]['binding'],answer['visualizations'][0]['binding'])

    def test_model_retries_false_steady_trend_in_dated_chart(self):
        import threading,time
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart,ToolReturnPart
        board=self.board();owner=self.grant(board)
        table=add(self.service.store,self.owner,board['id'],'days.csv',b'date,count\n2024-07-25,603\n2024-07-26,607\n2024-07-27,348\n2024-07-28,190\n')
        view={'studio':{'document_id':board['id'],'whiteboard':True,'frozen_evidence_ids':[],
                       'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('compare_selected_groups',{'group_column':'date','value_column':'count'})])
            result=next(p.content for m in messages for p in m.parts if isinstance(p,ToolReturnPart) and p.tool_name=='compare_selected_groups')
            self.assertEqual(result['chronological_pattern']['successive_direction'],['increase','decrease','decrease'])
            interpretation='The values drop steadily.' if len(calls)==2 else 'The values rise slightly, then fall.'
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Comparison','interpretation':interpretation,
                'claims':[{'result_id':result['result_id'],'path':'/groups/0/mean','label':'First'}]})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Compare the chart',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(len(calls),3)
        self.assertIn('rise slightly, then fall',answer['summary'])

    def test_model_can_explain_a_selected_group_as_an_aggregate(self):
        import threading,time
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart,ToolReturnPart
        board=self.board();owner=self.grant(board)
        table=add(self.service.store,self.owner,board['id'],'groups.csv',b'area,count\nA,3\nA,5\nB,9\n')
        selected={**{k:table[k] for k in ('id','name','sha256','columns','row_count')},
                  'selected_group':{'group_column':'area','value_column':'count','name':'A','index':0}}
        view={'studio':{'document_id':board['id'],'whiteboard':True,'frozen_evidence_ids':[],'selected_dataset':selected}}
        def respond(messages,info):
            returned=[p.content for m in messages for p in m.parts if isinstance(p,ToolReturnPart) and p.tool_name=='compare_selected_groups']
            if not returned:return ModelResponse(parts=[ToolCallPart('compare_selected_groups',{'group_column':'area','value_column':'count'})])
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Selected group','interpretation':'The selected group averages 4 across 2 rows.',
                'claims':[{'result_id':returned[-1]['result_id'],'path':'/groups/0/mean','label':'Average'},
                          {'result_id':returned[-1]['result_id'],'path':'/groups/0/rows','label':'Rows'}]})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Explain this bar',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual([claim['value'] for claim in answer['claims']],[4,2])
        self.assertEqual(answer['claims'][0]['source_binding']['groupName'],'A')
        from pydantic_ai.exceptions import UnexpectedModelBehavior
        calls=[]
        def fail_after_group(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('read_selected_table',{'columns':['area','count']})])
            raise UnexpectedModelBehavior('fixture failure')
        with patch.dict('os.environ',env):
            fallback=run_agent(self.assistant,owner,'Explain this bar',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(fail_after_group))
        self.assertTrue(fallback['ai_wording_unavailable'])
        self.assertEqual([claim['value'] for claim in fallback['claims']],[4,2,2,0,0])
        self.assertTrue(all(claim['source_binding']['groupName']=='A' for claim in fallback['claims']))
        calls.clear()
        with patch.dict('os.environ',env):
            diagram=run_agent(self.assistant,owner,'Explain and draw a diagram of this bar',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(fail_after_group))
        self.assertTrue(diagram['ai_wording_unavailable'])
        self.assertEqual(diagram['claims'][0]['value'],4)
        self.assertTrue(diagram['diagram']['nodes'])

    def test_grouped_chart_survives_model_failure_after_calculation(self):
        import threading,time
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        from pydantic_ai.exceptions import UnexpectedModelBehavior
        board,snapshot=self.bound_board(operation='replay',kind='map');owner=self.grant(board)
        table=add(self.service.store,self.owner,board['id'],'sample.csv',b'area,value\nA,2\nA,4\n')
        view={'studio':{'document_id':board['id'],'whiteboard':True,'frozen_evidence_ids':[],
            'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('compare_selected_groups',{'group_column':'area','value_column':'value'})])
            raise UnexpectedModelBehavior('fixture failure')
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Draw a diagram and grouped chart',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertTrue(answer['ai_wording_unavailable'])
        self.assertEqual(answer['visualizations'][0]['kind'],'csv-groups')
        self.assertEqual(answer['visualizations'][0]['binding']['datasetId'],table['id'])
        element={'id':'table','type':'text','text':'Table','x':0,'y':0,'width':10,'height':10,
                 'customData':{'fireatlas':{'documentId':board['id'],'datasetId':table['id'],'datasetHash':table['sha256']}}}
        board=self.service.transact(self.owner,board['id'],{'base_revision':board['revision'],'ops':[{'op':'patch_whiteboard','changes':[{'kind':'element','id':'table','position':0,'value':element}]}]})
        with patch.object(self.assistant,'start',return_value={'id':'job'}) as start:
            self.bridge.start(self.owner,board['id'],{'base_revision':board['revision'],'whiteboard':True,'selected_cards':['c1'],'selected_dataset_elements':['table']})
            mixed=start.call_args.args[1]['view']
        eid=mixed['studio']['frozen_evidence_ids'][0]
        with self.assertRaises(NotFound):
            self.bridge.start(self.other,board['id'],{'base_revision':board['revision'],'whiteboard':True,'selected_cards':['c1'],'selected_dataset_elements':['table']})
        calls.clear()
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Draw a diagram and grouped chart',normalize_context(self.study['context']),mixed,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['visualizations'][0]['kind'],'csv-groups')
        self.assertEqual({k:answer['visualizations'][0]['binding'][k] for k in ('documentId','datasetId','datasetHash')},
                         {'documentId':board['id'],'datasetId':table['id'],'datasetHash':table['sha256']})
        mixed['studio']['frozen_evidence_ids']=[eid]
        mixed['studio'].pop('csv_group_refs',None)
        calls.clear()
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Draw a diagram and chart',normalize_context(self.study['context']),mixed,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['visualizations'][0]['kind'],'csv-groups')
        mixed['studio']['frozen_evidence_ids']=[eid]
        mixed['studio'].pop('csv_group_refs',None)
        calls.clear()
        def twice(messages,info):
            calls.append(1)
            if len(calls)<3:return ModelResponse(parts=[ToolCallPart('compare_selected_groups',{'group_column':'area','value_column':'value'})])
            raise UnexpectedModelBehavior('fixture failure')
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Draw a diagram and grouped chart',normalize_context(self.study['context']),mixed,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(twice))
        self.assertEqual(answer['kind'],'Clarification')
        self.assertEqual(answer['visualizations'],[])
        mixed['studio']['frozen_evidence_ids']=[eid]
        mixed['studio'].pop('csv_group_refs',None)
        stopped=threading.Event();calls.clear()
        def cancel_after_tool(messages,info):
            from pydantic_ai.messages import ToolReturnPart
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('compare_selected_groups',{'group_column':'area','value_column':'value'})])
            self.assertTrue(any(isinstance(part,ToolReturnPart) and part.tool_name=='compare_selected_groups' for message in messages for part in message.parts))
            stopped.set()
            raise UnexpectedModelBehavior('fixture failure')
        with patch.dict('os.environ',env),self.assertRaises(InterruptedError):
            run_agent(self.assistant,owner,'Draw a diagram and grouped chart',normalize_context(self.study['context']),mixed,stopped,time.monotonic()+30,lambda _:None,model=FunctionModel(cancel_after_tool))

    def test_grouped_chart_request_offers_chart_when_model_omits_visual_intent(self):
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
        import threading,time
        board=self.board();owner=self.grant(board)
        table=add(self.service.store,self.owner,board['id'],'sample.csv',b'area,value\nA,2\nB,4\n')
        view={'studio':{'document_id':board['id'],'whiteboard':True,'frozen_evidence_ids':[],
            'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('compare_selected_groups',{'group_column':'area','value_column':'value'})])
            result=next(p.content for message in messages for p in message.parts if isinstance(p,ToolReturnPart) and p.tool_name=='compare_selected_groups')
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Groups','interpretation':'The table has grouped readings.',
                'claims':[{'result_id':result['result_id'],'path':'/groups/0/mean','label':'Mean'}]})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Create a grouped bar chart of mean value by area',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['visualizations'][0]['kind'],'csv-groups')
        self.assertEqual(answer['visualizations'][0]['binding']['datasetHash'],table['sha256'])

    def test_invalid_grouped_claim_is_retried_instead_of_crashing(self):
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart, RetryPromptPart
        import threading,time
        board=self.board(); owner=self.grant(board)
        table=add(self.service.store,self.owner,board['id'],'sample.csv',b'area,value\nA,2\nB,4\n')
        view={'studio':{'document_id':board['id'],'whiteboard':True,'frozen_evidence_ids':[],
            'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:
                return ModelResponse(parts=[ToolCallPart('compare_selected_groups',{'group_column':'area','value_column':'value'})])
            result=next(p.content for message in messages for p in message.parts if isinstance(p,ToolReturnPart) and p.tool_name=='compare_selected_groups')
            if len(calls)>2:
                self.assertTrue(any(isinstance(part,RetryPromptPart) for message in messages for part in message.parts))
            path='/groups/0/no_such_field' if len(calls)==2 else '/groups/0/mean'
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Groups','interpretation':'The table has grouped readings.',
                'claims':[{'result_id':result['result_id'],'path':path,'label':'Mean'}]})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Compare the groups',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(len(calls),3)
        self.assertEqual(answer['claims'][0]['value'],2)
    def test_blank_investigation_starts_with_unscoped_source_context(self):
        document=self.service.create_document(self.owner, {'title':'Blank investigation'})
        with patch.object(self.assistant,'start',return_value={'id':'job'}) as start:
            self.bridge.start(self.owner,document['id'],{'base_revision':document['revision'],'whiteboard':True})
        self.assertTrue(start.call_args.args[1]['view']['studio']['unscoped'])

    def test_blank_board_selected_snapshot_supplies_its_own_study(self):
        document=self.service.create_document(self.owner,{'title':'Blank investigation'})
        document=self.add_card(document,'evidence',kind='map')
        binding={'operation':'replay','context':self.study['context'],'arguments':{}}
        snapshot=self.service.resolve_binding(self.owner,document['id'],binding)['snapshot']
        document=self.service.transact(self.owner,document['id'],{'base_revision':document['revision'],'ops':[{'op':'update_card','id':'evidence','patch':{'snapshot_id':snapshot['id'],'binding':binding}}]})
        with patch.object(self.assistant,'start',return_value={'id':'job'}) as start:
            self.bridge.start(self.owner,document['id'],{'base_revision':document['revision'],'whiteboard':True,'selected_cards':['evidence']})
        request=start.call_args.args[1]
        self.assertFalse(request['view']['studio']['unscoped'])
        self.assertEqual(request['context']['year'],snapshot['context']['year'])

    def test_unscoped_board_does_not_query_default_satellite_study(self):
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart, RetryPromptPart
        import threading,time
        board=self.service.create_document(self.owner,{'title':'Blank'});owner=self.grant(board)
        view={'studio':{'document_id':board['id'],'whiteboard':True,'unscoped':True,'frozen_evidence_ids':[],'frozen_evidence_refs':{}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('investigate',{'operation':'replay'})])
            retries=[part.content for message in messages for part in message.parts if isinstance(part,RetryPromptPart)]
            self.assertTrue(any('Choose a study region and dates' in str(value) for value in retries))
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Choose a study','clarification':'Which region and dates should I use?'})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env), patch.object(self.assistant.science,'call') as science:
            answer=run_agent(self.assistant,owner,'Show a satellite map',normalize_context({}),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        science.assert_not_called()
        self.assertEqual(answer['kind'],'AI clarification')

    def test_challenge_does_not_replace_selected_evidence_with_new_calculation(self):
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart, RetryPromptPart
        import threading,time
        board=self.board();owner=self.grant(board)
        view={'studio':{'document_id':board['id'],'whiteboard':True,'challenge':True,'frozen_evidence_ids':[],'frozen_evidence_refs':{}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('investigate',{'operation':'comparability'})])
            retries=[part.content for message in messages for part in message.parts if isinstance(part,RetryPromptPart)]
            self.assertTrue(any('selected frozen evidence' in str(value) for value in retries))
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'More evidence','clarification':'What evidence would help compare these sensors?'})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env), patch.object(self.assistant.science,'call') as science:
            answer=run_agent(self.assistant,owner,'Challenge this finding',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        science.assert_not_called()
        self.assertEqual(answer['kind'],'AI clarification')

    def test_model_searches_board_sources_and_returns_clickable_exact_match(self):
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
        import threading,time
        board=self.board();owner=self.grant(board)
        table=add(self.service.store,self.owner,board['id'],'weather.csv',b'place,condition\nPark,smoke plume\n')
        view={'studio':{'document_id':board['id'],'whiteboard':True,'frozen_evidence_ids':[],'frozen_evidence_refs':{}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('search_investigation_sources',{'query':'smoke'})])
            found=next(part.content for message in messages for part in message.parts if isinstance(part,ToolReturnPart) and part.tool_name=='search_investigation_sources')
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Source match','interpretation':'The table contains a matching condition.',
                'claims':[{'result_id':found['result_id'],'path':'/matches/0/excerpt','label':'Source excerpt'}]})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Find smoke in my sources',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['claims'][0]['value'],'smoke plume')
        self.assertEqual(answer['limitations'],[])
        self.assertEqual((answer['source_matches'][0]['source_id'],answer['source_matches'][0]['source_sha256']),(table['id'],table['sha256']))
        self.assertEqual(answer['claims'][0]['source_binding'],{'documentId':board['id'],'datasetId':table['id'],'datasetHash':table['sha256'],'rowOffset':0})

    def test_usage_limit_diagnostic_is_a_fixed_category(self):
        from fireatlas.assistant.agent import usage_limit_category
        self.assertEqual(usage_limit_category(Exception('Exceeded the input_tokens_limit of 45000 (private content)')),'input_tokens_limit')
        self.assertEqual(usage_limit_category(Exception('Exceeded the per_request_input_tokens_limit of 1')),'per_request_input_tokens_limit')
        self.assertEqual(usage_limit_category(Exception('private content only')),'other')

    def test_table_challenge_keeps_question_and_checked_claims(self):
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
        import threading,time
        board=self.board();owner=self.grant(board)
        table=add(self.service.store,self.owner,board['id'],'park.csv',b'date,count\n2024-07-27,348\n')
        view={'studio':{'document_id':board['id'],'whiteboard':True,'challenge':True,'frozen_evidence_ids':[],
                        'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('read_selected_table',{'columns':['date','count']})])
            result=next(p.content for m in messages for p in m.parts if isinstance(p,ToolReturnPart) and p.tool_name=='read_selected_table')
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Challenge','interpretation':'The selected table reports a detection count.',
                'clarification':'What other source could explain the gap?','claims':[{'result_id':result['result_id'],'path':'/rows/0/1','label':'Count'}]})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Challenge this finding',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(len(calls),2)
        self.assertIn('What other source',answer['summary'])
        self.assertEqual(answer['claims'][0]['value'],'348')
        self.assertEqual(answer['claims'][0]['source_binding']['datasetId'],table['id'])
        self.assertFalse(answer.get('ai_wording_unavailable',False))

    def test_group_challenge_keeps_question_claims_and_valid_chart(self):
        import threading,time
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart,ToolReturnPart
        board=self.board();owner=self.grant(board)
        table=add(self.service.store,self.owner,board['id'],'groups.csv',b'area,count\nA,3\nA,5\nB,9\n')
        selected={**{k:table[k] for k in ('id','name','sha256','columns','row_count')},
                  'selected_group':{'group_column':'area','value_column':'count','name':'A','index':0}}
        view={'studio':{'document_id':board['id'],'whiteboard':True,'challenge':True,'frozen_evidence_ids':[],'selected_dataset':selected}}
        def respond(messages,info):
            returned=[p.content for m in messages for p in m.parts if isinstance(p,ToolReturnPart) and p.tool_name=='compare_selected_groups']
            if not returned:return ModelResponse(parts=[ToolCallPart('compare_selected_groups',{'group_column':'area','value_column':'count'})])
            identifier=returned[-1]['result_id']
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Challenge','interpretation':'The groups differ.',
                'clarification':'What explains the difference?', 'claims':[{'result_id':identifier,'path':'/groups/0/mean','label':'Mean'}],
                'visualizations':[{'result_id':identifier,'kind':'csv-groups'}]})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Challenge this finding',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertFalse(answer.get('ai_wording_unavailable',False))
        self.assertIn('What explains the difference?',answer['summary'])
        self.assertEqual(answer['claims'][0]['value'],4)
        self.assertEqual(answer['visualizations'][0]['kind'],'csv-groups')

    def test_challenge_fallback_keeps_selected_table_and_search_matches(self):
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart
        from pydantic_ai.exceptions import UnexpectedModelBehavior
        import threading,time
        board=self.board();owner=self.grant(board)
        table=add(self.service.store,self.owner,board['id'],'park.csv',b'date,count,status\n2024-07-27,348,gap\n')
        view={'studio':{'document_id':board['id'],'whiteboard':True,'challenge':True,'frozen_evidence_ids':[],
                        'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('read_selected_table',{'columns':['date','count','status']})])
            if len(calls)==2:return ModelResponse(parts=[ToolCallPart('search_investigation_sources',{'query':'gap'})])
            raise UnexpectedModelBehavior('fixture wording failure')
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Challenge this finding',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertTrue(answer['ai_wording_unavailable'])
        self.assertEqual([c['value'] for c in answer['claims']],['2024-07-27','348','gap'])
        self.assertEqual(answer['claims'][1]['source_binding']['datasetId'],table['id'])
        self.assertEqual(answer['source_matches'][0]['excerpt'],'gap')

    def test_source_search_results_survive_model_failure(self):
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart
        from pydantic_ai.exceptions import UnexpectedModelBehavior
        import threading,time
        board=self.board();owner=self.grant(board)
        table=add(self.service.store,self.owner,board['id'],'weather.csv',b'place,condition\nPark,smoke plume\n')
        view={'studio':{'document_id':board['id'],'whiteboard':True,'frozen_evidence_ids':[],'frozen_evidence_refs':{}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('search_investigation_sources',{'query':'smoke'})])
            raise UnexpectedModelBehavior('fixture wording failure')
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Find smoke in my sources',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertTrue(answer['ai_wording_unavailable'])
        self.assertEqual(answer['source_matches'][0]['source_id'],table['id'])
        self.assertEqual(answer['source_matches'][0]['excerpt'],'smoke plume')

    def test_model_can_resume_search_to_find_later_source(self):
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
        import threading,time
        board=self.board();owner=self.grant(board)
        for number in range(4):add(self.service.store,self.owner,board['id'],f'{number}.csv',f'v\nclear{number}\n'.encode())
        target=add(self.service.store,self.owner,board['id'],'last.csv',b'v\nsmoke plume\n')
        view={'studio':{'document_id':board['id'],'whiteboard':True,'frozen_evidence_ids':[],'frozen_evidence_refs':{}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            returns=[part.content for message in messages for part in message.parts if isinstance(part,ToolReturnPart) and part.tool_name=='search_investigation_sources']
            if not returns:return ModelResponse(parts=[ToolCallPart('search_investigation_sources',{'query':'smoke'})])
            if len(returns)==1:return ModelResponse(parts=[ToolCallPart('search_investigation_sources',{'query':'smoke','cursor':returns[0]['payload']['next_cursor']})])
            found=returns[-1]
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Match','interpretation':'A later table contains a matching condition.',
                'claims':[{'result_id':found['result_id'],'path':'/matches/0/excerpt','label':'Source excerpt'}]})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Find smoke in my sources',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['source_matches'][0]['source_id'],target['id'])
        self.assertEqual(answer['claims'][0]['value'],'smoke plume')

    def test_model_prepares_scatter_from_selected_owned_table(self):
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
        import threading,time
        board=self.board();owner=self.grant(board)
        table=add(self.service.store,self.owner,board['id'],'sample.csv',b'x,y\n0,2\n1,3\n')
        view={'studio':{'document_id':board['id'],'whiteboard':True,'frozen_evidence_ids':[],
              'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('prepare_selected_scatter',{'x_column':'x','y_column':'y'})])
            result=next(p.content for message in messages for p in message.parts if isinstance(p,ToolReturnPart) and p.tool_name=='prepare_selected_scatter')
            self.assertEqual(result['plotted_rows'],2)
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Scatter plot','interpretation':'The selected columns can be compared visually.',
                   'visualizations':[{'result_id':result['result_id'],'kind':'csv-scatter'}]})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Plot x against y',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['visualizations'][0]['binding'],{'documentId':board['id'],'datasetId':table['id'],'datasetHash':table['sha256'],'xColumn':'x','yColumn':'y'})
        self.assertEqual(answer['limitations'],[])

    def test_model_summarizes_all_selected_csv_rows_with_checked_units(self):
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
        import threading,time
        board=self.board();owner=self.grant(board)
        table=add(self.service.store,self.owner,board['id'],'sample.csv',b'x\n0\n2\n4\n')
        view={'studio':{'document_id':board['id'],'whiteboard':True,'frozen_evidence_ids':[],
              'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('summarize_selected_table',{'columns':['x']})])
            result=next(p.content for message in messages for p in message.parts if isinstance(p,ToolReturnPart) and p.tool_name=='summarize_selected_table')
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Table summary','interpretation':'The selected column has a range of values.',
                    'claims':[{'result_id':result['result_id'],'path':'/columns/0/mean','label':'Mean'}]})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Summarize this table',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['claims'][0]['value'],2)
        self.assertEqual(answer['claims'][0]['unit'],'source units unspecified')
        self.assertEqual(answer['claims'][0]['label'],'x · mean')
        self.assertEqual(answer['claims'][0]['source_binding'],{'documentId':board['id'],'datasetId':table['id'],'datasetHash':table['sha256'],'summaryColumn':'x','summaryMetric':'mean'})

    def test_selected_pdf_page_is_checked_against_owned_board(self):
        from fireatlas.studio.source_documents import add
        board=self.board();source=add(self.service.store,self.owner,board['id'],'paper.pdf',b'%PDF-test')
        element={'id':'paper','type':'text','text':'excerpt','x':0,'y':0,'width':10,'height':10,'customData':{'fireatlas':{'documentId':board['id'],'sourceDocumentId':source['id'],'sourceDocumentHash':source['sha256'],'page':2}}}
        board=self.service.transact(self.owner,board['id'],{'base_revision':board['revision'],'ops':[{'op':'patch_whiteboard','changes':[{'kind':'element','id':'paper','position':0,'value':element}]}]})
        with patch.object(self.assistant,'start',return_value={'id':'job'}) as start:
            self.bridge.start(self.owner,board['id'],{'base_revision':board['revision'],'whiteboard':True,'selected_source_elements':['paper']})
            selected=start.call_args.args[1]['view']['studio']['selected_source']
            self.assertEqual((selected['id'],selected['page'],selected['sha256']),(source['id'],2,source['sha256']))
        with self.assertRaises(StudioError):self.bridge.start(self.owner,board['id'],{'base_revision':board['revision'],'whiteboard':True,'selected_source_elements':['missing']})
        with self.assertRaises(NotFound):self.bridge.start(self.other,board['id'],{'base_revision':board['revision'],'whiteboard':True,'selected_source_elements':['paper']})

    def test_model_reads_selected_pdf_page_as_source_evidence(self):
        from fireatlas.studio.source_documents import add
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
        import threading,time
        board=self.board();owner=self.grant(board)
        source=add(self.service.store,self.owner,board['id'],'paper.pdf',b'%PDF-test')
        view={'studio':{'document_id':board['id'],'whiteboard':True,'frozen_evidence_ids':[],
                        'selected_source':{'id':source['id'],'name':source['name'],'sha256':source['sha256'],'page':2}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('read_selected_document_page',{})])
            returned=next(p.content for message in messages for p in message.parts if isinstance(p,ToolReturnPart) and p.tool_name=='read_selected_document_page')
            self.assertEqual(returned['payload']['text'],'Reported observation')
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Document','interpretation':'The source describes an observation.',
                 'claims':[{'result_id':returned['result_id'],'path':'/text','label':'Source text'}]})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env),patch('fireatlas.studio.source_documents.extract_page',return_value={'text':'Reported observation','truncated':False}):
            answer=run_agent(self.assistant,owner,'Explain this paper',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['claims'][0]['value'],'Reported observation')
        self.assertEqual(answer['claims'][0]['method_id'],'pdf-text-extraction-v1')
        self.assertEqual(answer['claims'][0]['source_binding'],{'documentId':board['id'],'sourceDocumentId':source['id'],'sourceDocumentHash':source['sha256'],'page':2})

    def test_model_reads_selected_csv_page_as_checked_owned_evidence(self):
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
        import threading,time
        document=self.board();owner=self.grant(document)
        table=add(self.service.store,self.owner,document['id'],'sample.csv',b'x,y\n0,2\n1,3\n')
        view={'studio':{'document_id':document['id'],'whiteboard':True,'frozen_evidence_ids':[],
                        'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('read_selected_table',{'columns':['x','y'],'offset':0})])
            returned=next(p.content for message in messages for p in message.parts if isinstance(p,ToolReturnPart) and p.tool_name=='read_selected_table')
            self.assertEqual(returned['payload']['rows'],[['0','2'],['1','3']])
            self.assertEqual([(item['path'], item['value']) for item in returned['claim_candidates']],
                             [('/rows/0/0','0'),('/rows/0/1','2'),('/rows/1/0','1'),('/rows/1/1','3')])
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Imported table','interpretation':'The table contains paired readings.',
                'claims':[{'result_id':returned['result_id'],'path':'/rows/0/0','label':'First x'}]})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'What is in this table?',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['claims'][0]['value'],'0')
        self.assertEqual(answer['claims'][0]['label'],'x · CSV record 2')
        self.assertEqual(answer['claims'][0]['method_id'],'imported-csv-v1')
        self.assertEqual(answer['claims'][0]['source_binding'],{'documentId':document['id'],'datasetId':table['id'],'datasetHash':table['sha256'],'rowOffset':0})
        calls.clear()
        fresh={'studio':{'document_id':document['id'],'whiteboard':True,'frozen_evidence_ids':[],
                         'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Explain and draw a diagram',normalize_context(self.study['context']),fresh,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['diagram']['nodes'][0]['binding'],{'documentId':document['id'],'datasetId':table['id'],'datasetHash':table['sha256']})
        self.assertEqual(answer['diagram']['nodes'][0]['label'],'sample.csv\nFields: x · y')
        self.assertEqual(answer['diagram']['nodes'][1]['kind'],'interpretation')
        self.assertEqual(answer['diagram']['nodes'][1]['label'],answer['summary'])
        other,snapshot=self.bound_board(operation='replay',kind='map')
        receipt=self.service.snapshot_receipt(self.owner,other['id'],snapshot['id'])['receipt']
        eid=self.assistant.store.artifact(owner,'evidence',receipt)
        def mixed_view():
            return {'studio':{'document_id':document['id'],'whiteboard':True,'frozen_evidence_ids':[eid],
                    'frozen_evidence_refs':{eid:{'documentId':document['id'],'snapshotId':snapshot['id'],'snapshotHash':snapshot['snapshot_sha256']}},
                    'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        calls.clear()
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Explain and draw a diagram',normalize_context(self.study['context']),mixed_view(),threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['diagram']['nodes'][0]['binding']['datasetId'],table['id'])
        from pydantic_ai.exceptions import UnexpectedModelBehavior
        calls.clear()
        def fail_after_read(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('read_selected_table',{'columns':['x','y'],'offset':0})])
            raise UnexpectedModelBehavior('fixture failure')
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Explain and draw a diagram',normalize_context(self.study['context']),mixed_view(),threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(fail_after_read))
        self.assertTrue(answer['ai_wording_unavailable'])
        self.assertEqual(answer['diagram']['nodes'][0]['binding']['datasetId'],table['id'])
        self.assertEqual(answer['diagram']['nodes'][0]['label'],'sample.csv\nFields: x · y')
        self.assertEqual([claim['value'] for claim in answer['claims']], ['0', '2', '1', '3'])
        self.assertEqual([claim['label'] for claim in answer['claims']], ['x · CSV record 2','y · CSV record 2','x · CSV record 3','y · CSV record 3'])
        self.assertEqual(answer['claims'][0]['source_binding']['rowOffset'], 0)
        self.assertEqual(answer['fallback_reason'], 'UnexpectedModelBehavior')

    def test_selected_table_retries_empty_interpretation_and_blank_claim(self):
        import threading,time
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart,ToolReturnPart
        board=self.board();owner=self.grant(board)
        table=add(self.service.store,self.owner,board['id'],'sample.csv',b'date,count,status\n2024-07-27,,gap\n')
        view={'studio':{'document_id':board['id'],'whiteboard':True,'frozen_evidence_ids':[],
                       'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('read_selected_table',{'columns':['date','count','status']})])
            result=next(p.content for m in messages for p in m.parts if isinstance(p,ToolReturnPart) and p.tool_name=='read_selected_table')
            if len(calls)==2: interpretation, path='', '/rows/0/2'
            else: interpretation, path='The reading is unavailable because the table records a gap.', '/rows/0/2'
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Comparison','interpretation':interpretation,'claims':[{'result_id':result['result_id'],'path':path,'label':'Status'}]})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Compare the values',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(len(calls),3)
        self.assertIn('gap',answer['summary'])
        self.assertEqual([c['value'] for c in answer['claims']],['gap'])
        from fireatlas.assistant.agent import fact
        evidence={'operation':'csv_table','payload':{'columns':['count'],'rows':[['  ']],'offset':0},'method':{'id':'csv','unit':'reported value'},'release_id':'test','id':'test'}
        with self.assertRaises(ValueError):fact(evidence,'/rows/0/0')

    def test_large_selected_table_fallback_keeps_bounded_source_linked_claims(self):
        import threading,time
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        from pydantic_ai.exceptions import UnexpectedModelBehavior
        board=self.board();owner=self.grant(board)
        table=add(self.service.store,self.owner,board['id'],'many.csv',b'a,b,c,d,e\n1,2,3,4,5\n6,7,8,9,10\n11,12,13,14,15\n')
        view={'studio':{'document_id':board['id'],'whiteboard':True,'frozen_evidence_ids':[],
                       'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('read_selected_table',{'columns':['a','b','c','d','e']})])
            raise UnexpectedModelBehavior('fixture failure')
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Compare the values',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertTrue(answer['ai_wording_unavailable'])
        self.assertEqual(len(answer['claims']),12)
        self.assertEqual(answer['claims'][0]['value'],'1')
        self.assertEqual(answer['claims'][0]['source_binding']['rowOffset'],0)
        self.assertEqual(answer['claims'][-1]['source_binding']['rowOffset'],2)

    def test_table_fallback_focuses_the_requested_date(self):
        import threading,time
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        from pydantic_ai.exceptions import UnexpectedModelBehavior
        board=self.board();owner=self.grant(board)
        table=add(self.service.store,self.owner,board['id'],'days.csv',b'date,count,status\n2024-07-25,3,complete\n2024-07-27,9,gap\n')
        view={'studio':{'document_id':board['id'],'whiteboard':True,'frozen_evidence_ids':[],
                       'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        def run(question):
            calls=[]
            def respond(messages,info):
                calls.append(1)
                if len(calls)==1:return ModelResponse(parts=[ToolCallPart('read_selected_table',{'columns':['date','count','status']})])
                raise UnexpectedModelBehavior('fixture failure')
            env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
            with patch.dict('os.environ',env):
                return run_agent(self.assistant,owner,question,normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        answer=run('Compare July 27, 2024')
        self.assertEqual([c['value'] for c in answer['claims']],['2024-07-27','9','gap'])
        self.assertTrue(all(c['source_binding']['rowOffset']==1 for c in answer['claims']))
        missing=run('Compare July 28, 2024')
        self.assertEqual(missing['claims'],[])
        self.assertIn('does not uniquely identify',missing['summary'])
        multiple=run('Compare July 25, 2024 and July 27, 2024')
        self.assertEqual(multiple['claims'],[])
        self.assertIn('requested dates',multiple['summary'])
        diagram=run('Draw a diagram for July 27, 2024')
        self.assertEqual([c['value'] for c in diagram['claims']],['2024-07-27','9','gap'])
        self.assertTrue(all(c['source_binding']['rowOffset']==1 for c in diagram['claims']))
        self.assertTrue(diagram['diagram']['nodes'])
        missing_diagram=run('Draw a diagram for July 28, 2024')
        self.assertEqual(missing_diagram['claims'],[])
        self.assertIn('Open the table',missing_diagram['summary'])

    def test_explanation_can_include_a_checked_table_value(self):
        import threading,time
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart,ToolReturnPart
        board=self.board();owner=self.grant(board)
        table=add(self.service.store,self.owner,board['id'],'day.csv',b'date,count\n2024-07-27,1495\n')
        view={'studio':{'document_id':board['id'],'whiteboard':True,'frozen_evidence_ids':[],
                       'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        def respond(messages,info):
            returned=[p.content for m in messages for p in m.parts if isinstance(p,ToolReturnPart) and p.tool_name=='read_selected_table']
            if not returned:return ModelResponse(parts=[ToolCallPart('read_selected_table',{'columns':['date','count']})])
            identifier=returned[-1]['result_id']
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Comparison','interpretation':'On July 27, 2024 NOAA-20 recorded 1,495 detections.',
                'claims':[{'result_id':identifier,'path':'/rows/0/0','label':'Date'},{'result_id':identifier,'path':'/rows/0/1','label':'Count'}]})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Compare the table',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertFalse(answer.get('ai_wording_unavailable',False))
        self.assertIn('1,495',answer['summary'])
        self.assertEqual([claim['value'] for claim in answer['claims']],['2024-07-27','1495'])
        fresh_view={'studio':{'document_id':board['id'],'whiteboard':True,'frozen_evidence_ids':[],
                       'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        with patch.dict('os.environ',env):
            with_diagram=run_agent(self.assistant,owner,'Explain and draw a diagram of the table',normalize_context(self.study['context']),fresh_view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertFalse(with_diagram.get('ai_wording_unavailable',False))
        self.assertTrue(any(node['kind']=='interpretation' and '1,495' in node['label'] for node in with_diagram['diagram']['nodes']))

    def test_selected_table_read_accepts_eleven_columns(self):
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
        import threading,time
        board=self.board(); owner=self.grant(board)
        columns=[f'c{i}' for i in range(11)]
        table=add(self.service.store,self.owner,board['id'],'wide.csv',(','.join(columns)+'\n'+','.join(str(i) for i in range(11))+'\n').encode())
        view={'studio':{'document_id':board['id'],'whiteboard':True,'frozen_evidence_ids':[],
                        'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('read_selected_table',{'columns':columns})])
            result=next(p.content for m in messages for p in m.parts if isinstance(p,ToolReturnPart) and p.tool_name=='read_selected_table')
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Table','interpretation':'The table contains a row of observations.',
                'claims':[{'result_id':result['result_id'],'path':'/rows/0/10','label':'Last column'}]})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Explain this table',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['claims'][0]['value'],'10')

    def test_selected_table_is_resolved_from_the_saved_owned_scene(self):
        from fireatlas.studio.datasets import add
        doc=self.board()
        table=add(self.service.store,self.owner,doc['id'],'sample.csv',b'x,y\n1,2\n3,4\n')
        def element(identifier,row):
            return {'id':identifier,'type':'text','text':'Table','x':0,'y':0,'width':10,'height':10,'customData':{'fireatlas':{'documentId':doc['id'],'datasetId':table['id'],'datasetHash':table['sha256'],'rowOffset':row}}}
        changes=[{'kind':'element','id':name,'position':i,'value':element(name,row)} for i,(name,row) in enumerate([('table',1),('other-row',0),('invalid',99)])]
        doc=self.service.transact(self.owner,doc['id'],{'base_revision':doc['revision'],'ops':[{'op':'patch_whiteboard','changes':changes}]})
        with patch.object(self.assistant,'start',return_value={'id':'job'}) as start:
            self.bridge.start(self.owner,doc['id'],{'base_revision':doc['revision'],'whiteboard':True,'selected_dataset_elements':['table']})
            source=start.call_args.args[1]['view']['studio']['selected_dataset']
            self.assertEqual((source['id'],source['sha256']),(table['id'],table['sha256']))
            self.assertEqual(source['selected_row_offset'],1)
            self.bridge.start(self.owner,doc['id'],{'base_revision':doc['revision'],'whiteboard':True,'selected_dataset_elements':['table','other-row']})
            self.assertNotIn('selected_row_offset',start.call_args.args[1]['view']['studio']['selected_dataset'])
            self.bridge.start(self.owner,doc['id'],{'base_revision':doc['revision'],'whiteboard':True,'selected_dataset_elements':['invalid']})
            self.assertNotIn('selected_row_offset',start.call_args.args[1]['view']['studio']['selected_dataset'])
        with self.assertRaises(StudioError):
            self.bridge.start(self.owner,doc['id'],{'base_revision':doc['revision'],'whiteboard':True,'selected_dataset_elements':['missing']})
        with self.assertRaises(NotFound):
            self.bridge.start(self.other,doc['id'],{'base_revision':doc['revision'],'whiteboard':True,'selected_dataset_elements':['table']})

    def test_selected_chart_group_is_recalculated_and_scoped(self):
        from fireatlas.studio.datasets import add
        doc=self.board()
        table=add(self.service.store,self.owner,doc['id'],'groups.csv',b'area,count\nA,3\nA,5\nB,9\n')
        def item(identifier,name,deleted=False):
            return {'id':identifier,'type':'rectangle','x':0,'y':0,'width':20,'height':20,'isDeleted':deleted,
                    'customData':{'fireatlas':{'documentId':doc['id'],'datasetId':table['id'],'datasetHash':table['sha256'],
                    'kind':'dataset-group-chart','groupColumn':'area','valueColumn':'count','groupName':name,'groupMetric':'mean'}}}
        items=[item('a','A'),item('b','B'),item('bad','missing'),item('deleted','A',True)]
        doc=self.service.transact(self.owner,doc['id'],{'base_revision':doc['revision'],'ops':[{'op':'patch_whiteboard','changes':[
            {'kind':'element','id':shape['id'],'position':i,'value':shape} for i,shape in enumerate(items)]}]})
        base={'base_revision':doc['revision'],'whiteboard':True}
        with patch.object(self.assistant,'start',return_value={'id':'job'}) as start:
            self.bridge.start(self.owner,doc['id'],{**base,'selected_dataset_elements':['a']})
            source=start.call_args.args[1]['view']['studio']['selected_dataset']
            self.assertEqual(source['selected_group'],{'group_column':'area','value_column':'count','name':'A','index':0})
            self.bridge.start(self.owner,doc['id'],{**base,'selected_dataset_elements':['a','b']})
            self.assertNotIn('selected_group',start.call_args.args[1]['view']['studio']['selected_dataset'])
        for selected in ('bad','deleted'):
            with self.assertRaises(StudioError):self.bridge.start(self.owner,doc['id'],{**base,'selected_dataset_elements':[selected]})

    def test_whiteboard_chart_request_uses_saved_comparison_reference(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        import threading,time
        document,snap=self.bound_board(operation='replay',kind='map');owner=self.grant(document)
        receipt=self.service.snapshot_receipt(self.owner,document['id'],snap['id'])['receipt']
        # Synthetic operation fixture tests routing only; values remain in the snapshot preview.
        receipt['operation']='finding_comparison'
        eid=self.assistant.store.artifact(owner,'evidence',receipt)
        binding={'documentId':document['id'],'cardId':document['state']['order'][0],'snapshotId':snap['id'],'snapshotHash':snap['snapshot_sha256'],'title':'Saved comparison'}
        view={'studio':{'document_id':document['id'],'whiteboard':True,'frozen_evidence_ids':[eid],'frozen_evidence_refs':{eid:binding},
                        'selected_comparisons':[{'snapshot_id':snap['id'],'series':'adjusted'}]}}
        calls=[]
        def respond(messages,info):
            self.assertIn('adjusted MODIS estimate', info.instructions)
            calls.append([p.content for message in messages for p in message.parts if type(p).__name__=='RetryPromptPart'])
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Comparison','interpretation':'Compare the observations.',
                'visualizations':[{'result_id':eid,'kind':'monthly-comparison'}]})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Show a chart',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertIn('visualizations',answer,(answer,calls[-1]))
        self.assertEqual(answer['visualizations'][0]['binding'],binding)

        def respond_with_diagram(messages,info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Comparison','interpretation':'Compare the observations.',
                'diagram':{'nodes':[{'id':'source','kind':'evidence','label':'Evidence','evidence_id':eid},
                                    {'id':'question','kind':'question','label':'How do the periods compare?'}],
                           'edges':[{'source':'source','target':'question','relation':'question'}]}})])
        with patch.dict('os.environ',env):
            combined=run_agent(self.assistant,owner,'Draw a diagram and a chart',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond_with_diagram))
        self.assertEqual(combined['diagram']['nodes'][0]['binding'],binding)
        self.assertEqual(combined['visualizations'],[{'result_id':eid,'kind':'monthly-comparison','binding':binding}])
        other_receipt={**receipt,'payload':{**receipt['payload'],'review_fixture':'other comparison'}}
        other_id=self.assistant.store.artifact(owner,'evidence',other_receipt)
        other_binding={**binding,'snapshotId':'other-snapshot'}
        multiple={'studio':{**view['studio'],'frozen_evidence_ids':[eid,other_id],
            'frozen_evidence_refs':{other_id:other_binding,eid:binding}}}
        with patch.dict('os.environ',env):
            combined=run_agent(self.assistant,owner,'Draw a diagram and a chart',normalize_context(self.study['context']),multiple,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond_with_diagram))
        self.assertEqual(combined['diagram']['nodes'][0]['binding'],binding)
        self.assertEqual(combined['visualizations'],[{'result_id':eid,'kind':'monthly-comparison','binding':binding}])
        def respond_without_diagram(messages,info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Comparison','interpretation':'Compare the observations.'})])
        with patch.dict('os.environ',env):
            combined=run_agent(self.assistant,owner,'Draw a diagram and a chart',normalize_context(self.study['context']),multiple,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond_without_diagram))
        self.assertEqual(combined['diagram']['nodes'][0]['binding'],binding)
        self.assertEqual(combined['visualizations'][0]['binding'],binding)
        with patch.dict('os.environ',env):
            only_chart=run_agent(self.assistant,owner,'Draw a chart but no diagram',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond_without_diagram))
        self.assertFalse(only_chart['diagram'])
        self.assertEqual(only_chart['visualizations'][0]['binding'],binding)

    def test_checked_claim_carries_its_exact_saved_card_binding(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart
        from fireatlas.assistant.agent import run_agent, guided_answer
        from fireatlas.assistant.contracts import normalize_context
        import threading,time
        document,snap=self.bound_board(operation='replay',kind='map');owner=self.grant(document)
        receipt=self.service.snapshot_receipt(self.owner,document['id'],snap['id'])['receipt']
        eid=self.assistant.store.artifact(owner,'evidence',receipt)
        candidate=guided_answer({**receipt,'id':eid})['claims'][0]
        binding={'documentId':document['id'],'cardId':document['state']['order'][0],'snapshotId':snap['id'],'snapshotHash':snap['snapshot_sha256'],'title':'Source'}
        view={'studio':{'document_id':document['id'],'whiteboard':True,'frozen_evidence_ids':[eid],'frozen_evidence_refs':{eid:binding}}}
        def respond(messages,info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Source value','interpretation':'The selected evidence contains an observation.',
                'claims':[{'result_id':eid,'path':candidate['path'],'label':'Observation'}]})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Describe the saved source',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['claims'][0]['binding'],binding)

    def test_selected_comparison_view_is_resolved_from_owned_saved_scene(self):
        document, snap = self.bound_board(operation='replay', kind='map')
        card_id = document['state']['order'][0]
        ref = {'documentId': document['id'], 'cardId': card_id, 'snapshotId': snap['id'],
               'snapshotHash': snap['snapshot_sha256'], 'kind': 'finding-alternative', 'comparisonSeries': 'viirs'}
        element = {'id': 'view', 'type': 'text', 'text': 'view', 'x': 0, 'y': 0, 'width': 10, 'height': 10,
                   'customData': {'fireatlas': ref}}
        document = self.service.transact(self.owner, document['id'], {'base_revision': document['revision'],
            'ops': [{'op': 'patch_whiteboard', 'changes': [{'kind': 'element', 'id': 'view', 'position': 0, 'value': element}]}]})
        receipt = self.service.snapshot_receipt(self.owner, document['id'], snap['id'])['receipt']
        receipt['operation'] = 'finding_comparison'
        receipt['payload'] = {'schema': 'fireatlas-finding-investigation-v1', 'comparison': {'series': {'viirs': {'first': 1}}}}
        body = {'base_revision': document['revision'], 'whiteboard': True, 'selected_cards': [card_id], 'selected_comparison_elements': ['view']}
        with patch.object(self.service, 'snapshot_receipt', return_value={'receipt': receipt}), patch.object(self.assistant, 'start', return_value={'id': 'job'}) as start:
            self.bridge.start(self.owner, document['id'], body)
            self.assertEqual(start.call_args.args[1]['view']['studio']['selected_comparisons'], [{'snapshot_id': snap['id'], 'series': 'viirs'}])
            with self.assertRaises(StudioError):
                self.bridge.start(self.owner, document['id'], {**body, 'selected_comparison_elements': ['missing']})
            with self.assertRaises(StudioError):
                self.bridge.start(self.owner, document['id'], {**body, 'selected_cards': []})
            with self.assertRaises(NotFound):
                self.bridge.start(self.other, document['id'], body)

    def test_whiteboard_diagram_binds_saved_evidence_and_replaces_model_label(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        import threading,time
        document,snap=self.bound_board(operation='replay',kind='map')
        owner=self.grant(document)
        receipt=self.service.snapshot_receipt(self.owner,document['id'],snap['id'])['receipt']
        eid=self.assistant.store.artifact(owner,'evidence',receipt)
        card=document['state']['order'][0]
        binding={'documentId':document['id'],'cardId':card,'snapshotId':snap['id'],'snapshotHash':snap['snapshot_sha256']}
        view={'studio':{'document_id':document['id'],'whiteboard':True,'frozen_evidence_ids':[eid], 'frozen_evidence_refs':{eid:binding}}}
        def respond(messages,info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Evidence','interpretation':'Compare the observations.',
                'diagram':{'nodes':[{'id':'source','kind':'evidence','label':'Unverified label','evidence_id':eid},
                                    {'id':'source_again','kind':'evidence','label':'Another label','evidence_id':eid},
                                    {'id':'question','kind':'question','label':'How do sensors differ?'}],
                           'edges':[{'source':'source','target':'question','relation':'question'},
                                    {'source':'source_again','target':'question','relation':'question'}]}})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Draw a diagram',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['diagram']['nodes'][0]['label'],'Saved evidence')
        self.assertEqual(answer['diagram']['nodes'][0]['binding'],binding)
        self.assertEqual(len(answer['diagram']['nodes']),2)
        self.assertEqual(len(answer['diagram']['edges']),1)
        self.assertEqual(answer['visualizations'],[])

        def empty_interpretation(messages,info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Evidence','interpretation':'',
                'diagram':{'nodes':[{'id':'source','kind':'evidence','label':'Evidence','evidence_id':eid}], 'edges':[]}})])
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Draw a diagram',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(empty_interpretation))
        self.assertEqual(answer['summary'],'The selected evidence is shown below.')

        def invalid_diagram(messages,info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Evidence','interpretation':'The observed patterns differ between sensors.',
                'diagram':{'nodes':[{'id':'source','kind':'evidence','label':'There were 999 fires','evidence_id':eid},
                                    {'id':'question','kind':'question','label':'How do sensors differ?'}],
                           'edges':[{'source':'source','target':'question','relation':'question'}]}})])
        with patch.dict('os.environ',env):
            result=run_agent(self.assistant,owner,'Draw a diagram',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(invalid_diagram))
        self.assertEqual(result['summary'],'The observed patterns differ between sensors.')
        self.assertFalse(result.get('ai_wording_unavailable',False))
        self.assertEqual(result['diagram']['nodes'][0]['binding'],binding)
        self.assertTrue(all('999' not in node['label'] for node in result['diagram']['nodes']))
        other_receipt={**receipt,'payload':{**receipt['payload'],'review_fixture':'another source'}}
        other_id=self.assistant.store.artifact(owner,'evidence',other_receipt)
        other_binding={**binding,'snapshotId':'another-snapshot'}
        multiple={'studio':{**view['studio'],'frozen_evidence_ids':[eid,other_id],
                            'frozen_evidence_refs':{eid:binding,other_id:other_binding}}}
        with patch.dict('os.environ',env):
            ambiguous=run_agent(self.assistant,owner,'Draw a diagram',normalize_context(self.study['context']),multiple,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(invalid_diagram))
        self.assertEqual(ambiguous['summary'],'The observed patterns differ between sensors.')
        self.assertIsNone(ambiguous['diagram'])

    def test_string_diagram_does_not_discard_model_explanation(self):
        import json, threading, time
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        document,snap=self.bound_board(operation='replay',kind='map');owner=self.grant(document)
        receipt=self.service.snapshot_receipt(self.owner,document['id'],snap['id'])['receipt']
        eid=self.assistant.store.artifact(owner,'evidence',receipt)
        binding={'documentId':document['id'],'cardId':document['state']['order'][0],'snapshotId':snap['id'],'snapshotHash':snap['snapshot_sha256']}
        view={'studio':{'document_id':document['id'],'whiteboard':True,'frozen_evidence_ids':[eid],'frozen_evidence_refs':{eid:binding}}}
        valid={'nodes':[{'id':'source','label':'Evidence','kind':'evidence','evidence_id':eid}],'edges':[]}
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        for value in (json.dumps(valid),'A diagram of the evidence',
                      {'nodes':[{'id':'source','kind':'evidence','evidence_id':eid}],'edges':[]},
                      {'nodes':[{'id':'source','kind':'invented','label':'Source','evidence_id':eid}],'edges':[]},
                      {'nodes':[],'edges':[{'source':'a','target':'b','relation':'unsupported'}]},
                      {'nodes':[{'id':'source','kind':'evidence','label':'Source','evidence_id':eid}]*7},
                      {'nodes':[{'id':'source','kind':'evidence','label':'Source','evidence_id':'invented'}]},
                      {'nodes':[{'id':'source','kind':'evidence','label':'Source','evidence_id':eid}],
                       'edges':[{'source':'source','target':'missing','relation':'context'}]},
                      {'nodes':'not a collection','edges':[]},
                      ['not','a','diagram']):
            def respond(messages,info):
                return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Comparison','interpretation':'The sensors show different observed activity.','diagram':value})])
            with self.subTest(value=value),patch.dict('os.environ',env):
                answer=run_agent(self.assistant,owner,'Explain and diagram this',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
            self.assertEqual(answer['summary'],'The sensors show different observed activity.')
            self.assertFalse(answer.get('ai_wording_unavailable',False))
            self.assertTrue(answer['diagram'])
            self.assertEqual(answer['diagram']['nodes'][0]['binding'],binding)
            self.assertNotIn('invented',str(answer['diagram']))

    def test_model_cannot_salvage_qualitative_sentences_from_numeric_prose(self):
        import threading,time
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        from fireatlas.assistant.agent import run_agent
        from fireatlas.assistant.contracts import normalize_context
        document,snap=self.bound_board(operation='replay',kind='map');owner=self.grant(document)
        receipt=self.service.snapshot_receipt(self.owner,document['id'],snap['id'])['receipt']
        eid=self.assistant.store.artifact(owner,'evidence',receipt)
        binding={'documentId':document['id'],'cardId':document['state']['order'][0],'snapshotId':snap['id'],'snapshotHash':snap['snapshot_sha256']}
        view={'studio':{'document_id':document['id'],'whiteboard':True,'frozen_evidence_ids':[eid],'frozen_evidence_refs':{eid:binding}}}
        def respond(messages,info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Comparison','interpretation':'The sensors show different observed activity. There were 999 fires. Compare the sources carefully.'})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.assistant,owner,'Explain this',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertTrue(answer.get('ai_wording_unavailable'))
        self.assertNotIn('The sensors show different observed activity.',answer['summary'])
        self.assertNotIn('999',answer['summary'])
        with patch.dict('os.environ',env):
            diagram=run_agent(self.assistant,owner,'Draw a diagram',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(diagram['observed_retry_categories'],['interpretation'])
        self.assertNotIn('999',str(diagram['observed_retry_categories']))
        def malformed_with_bad_prose(messages,info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Comparison','interpretation':'There were 999 fires.',
                'diagram':{'nodes':[{'id':'source','kind':'evidence','evidence_id':eid}]}})])
        with patch.dict('os.environ',env):
            diagram=run_agent(self.assistant,owner,'Draw a diagram',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(malformed_with_bad_prose))
        self.assertTrue(diagram['ai_wording_unavailable'])
        self.assertNotIn('999',diagram['summary'])
        def malformed(messages,info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Comparison','interpretation':'Compare the observations.',
                'claims':[{'result_id':eid,'label':'Missing path'}]})])
        with patch.dict('os.environ',env):
            diagram=run_agent(self.assistant,owner,'Draw a diagram',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(malformed))
        self.assertEqual(diagram['observed_retry_categories'],['schema:claims'])
        def long_explanation(messages,info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Comparison','interpretation':'x'*1201})])
        with patch.dict('os.environ',env):
            diagram=run_agent(self.assistant,owner,'Draw a diagram',normalize_context(self.study['context']),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(long_explanation))
        self.assertEqual(diagram['observed_retry_categories'],['schema:interpretation','schema:interpretation:string_too_long'])

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
