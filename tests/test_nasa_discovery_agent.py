"""Agent choices and owner-bound NASA metadata on synthetic fixtures."""
import json
import threading
import time
from unittest.mock import patch
from tests.studio_support import StudioCase
from tests.test_nasa_discovery import C,V,BBOX,catalog,granules,variables
from fireatlas.assistant.agent import run_agent,conversation_context
from fireatlas.assistant.contracts import normalize_context
from fireatlas.assistant.service import AssistantService
from fireatlas.studio.assistant import StudioAssistant
from fireatlas.assistant.nasa_discovery import validate_reports


class NasaDiscoveryAgentTests(StudioCase):
    def setUp(self):
        super().setUp()
        self.assistant=AssistantService(self.database,self.root/'assistant/workspace.sqlite3');self.addCleanup(self.assistant.close)
        self.service.assistant=self.assistant
        self.bridge=StudioAssistant(self.service,self.assistant);self.assistant.studio_bridge=self.bridge
        self.doc=self.board();self.session=self.service.assistant_owner(self.owner)
        self.assistant.store.artifact(self.session,'studio_access',{'principal':self.owner,'document_id':self.doc['id']})

    def run_model(self,respond,message,studio=None):
        from pydantic_ai.models.function import FunctionModel
        with patch('fireatlas.assistant.agent.provider_config',return_value={'provider':'openai','model':'test','configured':True,'input_price':1,'output_price':1}):
            return run_agent(self.assistant,self.session,message,normalize_context({}),{'studio':studio or {'document_id':self.doc['id'],'whiteboard':True,'unscoped':True}},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))

    def test_agent_chooses_search_then_exact_inspection_and_persists_original_receipts(self):
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        calls=[]
        args={'bbox':BBOX,'start':'2025-04-01','end':'2025-04-01'}
        def respond(messages,info):
            calls.append(info)
            self.assertIn('investigate',[t.name for t in info.function_tools])
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('discover_nasa_data',dict(args,topic='soil moisture'))])
            if len(calls)==2:return ModelResponse(parts=[ToolCallPart('discover_nasa_data',dict(args,collection_id=C,variable_name='*soil_moisture*'))])
            self.assertIn('no observation files were downloaded',info.instructions)
            return ModelResponse(parts=[ToolCallPart('final_result',{'title':'Soil moisture catalog candidates','synthesis':'The catalog lists soil moisture metadata; observation files and access remain unchecked.','hypothesis':'Soil moisture may be useful environmental context.','proposed_test':'Acquire matched observations with quality flags before testing their association with thermal patterns.','source_ids':['R1']})])
        with patch('fireatlas.assistant.nasa_discovery.fetch',side_effect=[catalog([V]),catalog([V]),granules(),variables()]):
            answer=self.run_model(respond,'Discover NASA soil moisture data for bounds '+json.dumps(BBOX)+' on the requested UTC day.')
        self.assertEqual(len(calls),3)
        self.assertEqual(len(answer['nasa_discoveries']),2)
        self.assertEqual(len(answer['web_sources']),1)
        self.assertIn('Granules: 1 candidates listed',answer['web_sources'][0]['snippet'])
        self.assertTrue(all(r['collections']['items'][0]['reference_id']=='R1' for r in answer['nasa_discoveries']))
        validate_reports(answer['nasa_discoveries'],answer['web_sources'])
        originals=self.assistant.store.artifacts(self.session,'nasa_cmr_response')
        self.assertEqual(len(originals),4)
        self.assertTrue(all('source_utf8' in item['body'] for item in originals))
        self.bridge.save_conversation_turn(self.session,self.doc['id'],'nasa','NASA candidates?',answer)
        turn=self.bridge.conversation(self.session,self.doc['id'])[-1]
        self.assertEqual(turn['nasa_discoveries'],answer['nasa_discoveries'])
        compact=conversation_context([turn])[0]
        self.assertNotIn('source_utf8',json.dumps(compact))
        self.assertEqual(compact['nasa_catalog'][1]['collections'][0]['concept_id'],C)
        with self.assertRaises(PermissionError):self.assistant.store.get_artifact(self.assistant.store.create_session(normalize_context()),originals[0]['id'],'nasa_cmr_response')

    def test_named_locality_uses_authoritative_resolver_instead_of_model_coordinates(self):
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        calls=[]
        def respond(messages,info):
            calls.append(True)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('discover_nasa_data',{'topic':'soil moisture','place':'Synthetic locality','start':'2025-04-01','end':'2025-04-01'})])
            return ModelResponse(parts=[ToolCallPart('final_result',{'title':'Catalog discovery','synthesis':'Catalog metadata is ready; observation files remain unchecked.','hypothesis':'Soil moisture may be useful context.','proposed_test':'Acquire quality-controlled observations before analysis.','source_ids':['R1']})])
        reference={'source':'Synthetic geographic fixture','url':'https://www.geonames.org/123'}
        with patch('fireatlas.assistant.comparison_research.resolve_area',return_value=('Synthetic locality search rectangle',BBOX,reference)) as resolve,patch('fireatlas.assistant.nasa_discovery.fetch',return_value=catalog()) as fetch:
            answer=self.run_model(respond,'Discover NASA soil moisture near Synthetic locality.')
        resolve.assert_called_once_with('Synthetic locality')
        self.assertIn('88.4%2C24.2%2C88.8%2C24.6',fetch.call_args.args[0])
        self.assertEqual(answer['nasa_discoveries'][0]['geography']['source'],reference['source'])

    def test_guessed_bounds_and_frozen_challenge_never_contact_nasa(self):
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        for challenge in (False,True):
            calls=[]
            def respond(messages,info):
                calls.append(True)
                if len(calls)==1:return ModelResponse(parts=[ToolCallPart('discover_nasa_data',{'topic':'soil moisture','bbox':BBOX})])
                return ModelResponse(parts=[ToolCallPart('final_result',{'title':'Choose a geographic scope','clarification':'Name an exact locality or supply explicit bounds outside a frozen Challenge.'})])
            studio={'document_id':self.doc['id'],'whiteboard':True,'unscoped':True}
            if challenge:studio['challenge']={'status':'frozen'}
            with self.subTest(challenge=challenge),patch('fireatlas.assistant.nasa_discovery.fetch') as fetch:
                result=self.run_model(respond,'Discover NASA data for the area.',studio)
                fetch.assert_not_called();self.assertEqual(result['kind'],'AI clarification')

    def test_three_attempt_ceiling_preserves_metadata_after_failed_wording(self):
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        calls=[]
        def respond(messages,info):
            calls.append(True)
            if len(calls)<=4:return ModelResponse(parts=[ToolCallPart('discover_nasa_data',{'topic':'soil moisture'})])
            return ModelResponse(parts=[ToolCallPart('final_result',{'title':'Catalog candidates','synthesis':'The catalog lists candidates; no files were acquired.','hypothesis':'Soil moisture may be useful context.','proposed_test':'Acquire matched observations before analysis.','source_ids':['R1']})])
        with patch('fireatlas.assistant.nasa_discovery.fetch',return_value=catalog()) as fetch:
            result=self.run_model(respond,'Discover NASA soil moisture candidates.')
        self.assertEqual(fetch.call_count,3)
        self.assertEqual(len(result['nasa_discoveries']),3)
        self.assertEqual(len(result['web_sources']),1)
