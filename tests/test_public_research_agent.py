import json
import threading
import time
from unittest.mock import patch

from tests.studio_support import StudioCase
from fireatlas.assistant.agent import run_agent
from fireatlas.assistant.contracts import normalize_context, digest
from fireatlas.assistant.service import AssistantService
from fireatlas.studio.assistant import StudioAssistant

class PublicResearchAgentTests(StudioCase):
    def setUp(self):
        super().setUp()
        self.assistant=AssistantService(self.database,self.root/'assistant/workspace.sqlite3');self.addCleanup(self.assistant.close)
        self.service.assistant=self.assistant
        self.bridge=StudioAssistant(self.service,self.assistant);self.assistant.studio_bridge=self.bridge
        self.doc=self.board();self.session=self.service.assistant_owner(self.owner)
        self.assistant.store.artifact(self.session,'studio_access',{'principal':self.owner,'document_id':self.doc['id']})

    def test_agent_can_choose_a_public_search_and_returns_only_retrieved_sources(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:
                self.assertIn('search_public_research',[tool.name for tool in info.function_tools])
                return ModelResponse(parts=[ToolCallPart('search_public_research',{'query':'wildfire fuel moisture','scholarly':True})])
            return ModelResponse(parts=[ToolCallPart('final_result',{'title':'Fuel moisture references','interpretation':
                'Read the supporting study at https://fabricated.example/paper.' if len(calls)==2 else 'Public references are ready. Read the original methods before adopting a fuel-moisture explanation.','claims':[]})])
        source={'title':'Fuel moisture study','url':'https://doi.org/10.1234/fuel','snippet':'Journal metadata','provider':'Crossref'}
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True}}
        with patch('fireatlas.assistant.agent.provider_config',return_value={'provider':'openai','model':'test','configured':True,'input_price':1,'output_price':1}),patch('fireatlas.assistant.web_references.search_references',return_value=[source]):
            answer=run_agent(self.assistant,self.session,'Investigate literature about fuel moisture.',normalize_context({}),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(len(calls),3)
        self.assertNotIn('fabricated.example',json.dumps(answer))
        self.assertEqual(answer['web_sources'],[{**source,'id':'R1'}]);self.assertEqual(answer['claims'],[])
        receipt=self.assistant.store.get_artifact(self.session,view['studio']['public_search_receipts'][0],'public_research')['body']
        self.assertEqual(receipt['sha256'],digest({k:v for k,v in receipt.items() if k!='sha256'}))

    def test_structured_research_has_small_output_schema_and_keeps_scientific_tools(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        calls=[]
        source={'title':'Sentinel-3 fuel moisture methods','url':'https://doi.org/10.1234/fuel','snippet':'Metadata only','provider':'Crossref'}
        research={'synthesis':'The references concern fuel conditions and detection methods (R1); their findings need original-source review.',
                  'hypothesis':'Fuel dryness may affect thermal detectability.',
                  'proposed_test':'Match overpass time, cloud conditions and vegetation, then compare independent fuel-moisture measurements with detection outcomes.',
                  'source_ids':['R1']}
        def respond(messages,info):
            calls.append({'tools':{t.name for t in info.function_tools},'output':info.output_tools[0].parameters_json_schema})
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('search_public_research',{'query':'fuel moisture satellite detection','scholarly':True})])
            schema=calls[-1]['output']
            self.assertEqual(set(schema['properties']),{'title','synthesis','hypothesis','proposed_test','source_ids','clarification'})
            self.assertEqual(schema['$defs'],{})
            self.assertEqual(schema['properties']['source_ids']['items']['enum'],['R1'])
            self.assertIn('ONE short sentence per prose field',info.instructions)
            self.assertEqual(calls[-1]['tools'],calls[0]['tools'])
            self.assertIn('investigate',calls[-1]['tools'])
            self.assertLess(len(json.dumps(schema)),len(json.dumps(calls[0]['output']))/2)
            return ModelResponse(parts=[ToolCallPart('final_result',{'title':'Sentinel-3 fuel conditions and detection','research_answer':json.dumps(research)})])
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True,'selected_notes':[{'text':'A prior board idea.'}]}}
        with patch('fireatlas.assistant.agent.provider_config',return_value={'provider':'openai','model':'test','configured':True,'input_price':1,'output_price':1}),patch('fireatlas.assistant.web_references.search_references',return_value=[source]):
            answer=run_agent(self.assistant,self.session,'Investigate literature and propose a fuel-moisture test.',normalize_context({}),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(len(calls),2)
        self.assertEqual(answer['kind'],'AI public research')
        self.assertEqual(answer['research_answer'],research)
        self.assertIn('Proposed test:',answer['summary']);self.assertEqual(answer['claims'],[])
        self.assertEqual(answer['web_sources'][0]['id'],'R1')
        diagnostics=self.assistant.store.artifacts(self.session,'model_diagnostic')
        self.assertTrue(all('schema_bytes' in d['body'] and 'message_bytes' in d['body'] for d in diagnostics))
        self.assertNotIn(research['proposed_test'],json.dumps(diagnostics))

    def test_flat_json_text_and_deep_nested_retry_keep_owned_sources(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart,TextPart
        source={'title':'Fuel methods','url':'https://doi.org/10.1234/fuel','snippet':'Metadata only','provider':'Crossref'}
        brief={'synthesis':'Original methods need review.','hypothesis':'Fuel dryness may affect detectability.','proposed_test':'Match independent fuel measurements to overpass conditions.','source_ids':['R1']}
        for deep_retry in (False,True):
            calls=[]
            def respond(messages,info):
                calls.append(True)
                if len(calls)==1:return ModelResponse(parts=[ToolCallPart('search_public_research',{'query':'fuel moisture','scholarly':True})])
                if deep_retry and len(calls)==2:return ModelResponse(parts=[ToolCallPart('final_result',{'title':'Malformed','research_answer':'['*1500+'0'+']'*1500})])
                return ModelResponse(parts=[TextPart(json.dumps({'title':'Fuel study',**brief}))])
            with self.subTest(deep_retry=deep_retry),patch('fireatlas.assistant.agent.provider_config',return_value={'provider':'openai','model':'test','configured':True,'input_price':1,'output_price':1}),patch('fireatlas.assistant.web_references.search_references',return_value=[source]):
                answer=run_agent(self.assistant,self.session,'Investigate fuel-moisture literature.',normalize_context({}),{'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True}},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
                self.assertEqual(len(calls),3 if deep_retry else 2)
                self.assertEqual(answer['research_answer'],brief)
                self.assertEqual(answer['web_sources'][0]['url'],source['url'])
        with self.assistant.store.connection() as db:
            self.assertTrue(all(row['state']=='settled' for row in db.execute('SELECT state FROM reservations')))

    def test_separately_bounded_research_sections_can_form_a_longer_summary(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        source={'title':'Fuel methods','url':'https://doi.org/10.1234/fuel','snippet':'Metadata only','provider':'Crossref'}
        brief={'synthesis':'Review the original methods before adopting findings. '*9,
               'hypothesis':'Fuel conditions may affect detectability. '*8,
               'proposed_test':'Match independent fire-presence references with cloud, overpass and viewing conditions. '*8,
               'source_ids':['R1']}
        calls=[]
        def respond(messages,info):
            calls.append(True)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('search_public_research',{'query':'fuel moisture','scholarly':True})])
            return ModelResponse(parts=[ToolCallPart('final_result',{'title':'Proposed investigation',**brief})])
        with patch('fireatlas.assistant.agent.provider_config',return_value={'provider':'openai','model':'test','configured':True,'input_price':1,'output_price':1}),patch('fireatlas.assistant.web_references.search_references',return_value=[source]):
            answer=run_agent(self.assistant,self.session,'Investigate fuel-moisture literature.',normalize_context({}),{'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True}},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(len(calls),2)
        self.assertGreater(len(answer['summary']),1200)
        self.assertLessEqual(len(answer['summary']),2400)
        self.assertEqual(answer['research_answer'],{key:value.strip() if isinstance(value,str) else value for key,value in brief.items()})
        diagnostics=self.assistant.store.artifacts(self.session,'model_diagnostic')
        final=next(item['body'] for item in reversed(diagnostics) if item['body']['output_field_lengths'])
        for field in ('synthesis','hypothesis','proposed_test'):
            self.assertEqual(final['output_field_lengths']['research_answer.'+field],len(brief[field]))
            self.assertNotIn(brief[field],json.dumps(final))

    def test_invented_research_reference_and_measurement_require_correction(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        source={'title':'Fuel methods','url':'https://doi.org/10.1234/fuel','snippet':'Metadata only','provider':'Crossref'}
        for defect in ('reference','measurement','address','empty','whitespace','title','title-cause','title-clarification'):
            calls=[]
            valid={'synthesis':'Original methods need review.','hypothesis':'Fuel dryness may affect detectability.','proposed_test':'Match independent fuel measurements to overpass conditions.','source_ids':['R1']}
            def respond(messages,info):
                calls.append(True)
                if len(calls)==1:return ModelResponse(parts=[ToolCallPart('search_public_research',{'query':'fuel moisture','scholarly':True})])
                research=dict(valid)
                if len(calls)==2:
                    if defect in {'title','title-cause','title-clarification'}:
                        title='Fuel moisture caused missed fires' if defect=='title-cause' else 'Fuel moisture caused 999 missed fires'
                        bad={'title':title,'research_answer':research}
                        if defect=='title-clarification':bad={'title':title,'clarification':'Which study should we inspect?'}
                        return ModelResponse(parts=[ToolCallPart('final_result',bad)])
                    elif defect=='reference':research['source_ids']=['R99']
                    elif defect=='measurement':research['synthesis']='There were 999 fires.'
                    elif defect=='address':research['proposed_test']='Read https://fabricated.example/paper.'
                    elif defect=='whitespace':research['proposed_test']=' \n  '
                    else:return ModelResponse(parts=[ToolCallPart('final_result',{'title':'Empty'})])
                return ModelResponse(parts=[ToolCallPart('final_result',{'title':'Fuel study','research_answer':research})])
            with self.subTest(defect=defect),patch('fireatlas.assistant.agent.provider_config',return_value={'provider':'openai','model':'test','configured':True,'input_price':1,'output_price':1}),patch('fireatlas.assistant.web_references.search_references',return_value=[source]):
                answer=run_agent(self.assistant,self.session,'Investigate fuel-moisture literature.',normalize_context({}),{'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True}},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
                self.assertEqual(len(calls),3)
                self.assertEqual(answer['research_answer'],valid)

    def test_reads_two_owned_saved_references_without_changing_handles(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        from fireatlas.assistant.public_reading import read_reference
        sources=[{'id':f'R{i}','title':f'Synthetic methods {i}','url':f'https://doi.org/10.1234/source{i}','snippet':'Metadata only','provider':'Crossref'} for i in (1,2)]
        self.service.store.artifact(self.owner,'whiteboard_conversation',{'document_id':self.doc['id'],'run_id':'saved','question':'Which methods?','title':'References','summary':'Metadata only.','claims':[],'web_sources':sources})
        calls=[]
        def original_read(source,**kwargs):
            doi=source['url'].split('doi.org/')[1]
            metadata=json.dumps({'resultList':{'result':[{'doi':doi,'abstractText':'Original synthetic abstract.'}]}}).encode()
            with patch('fireatlas.assistant.public_reading.fetch',return_value=metadata):return read_reference(source,**kwargs)
        def respond(messages,info):
            calls.append(True)
            if len(calls)<=2:return ModelResponse(parts=[ToolCallPart('read_public_reference',{'reference_id':'R2' if len(calls)==1 else 'R1','focus':'methods'})])
            return ModelResponse(parts=[ToolCallPart('final_result',{'title':'Original methods','synthesis':'The original abstracts describe the methods.','hypothesis':'Observation conditions may matter.','proposed_test':'Match independent fire references with observation opportunity.','source_ids':['R1','R2']})])
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True}}
        with patch('fireatlas.assistant.agent.provider_config',return_value={'provider':'openai','model':'test','configured':True,'input_price':1,'output_price':1}),patch('fireatlas.assistant.public_reading.read_reference',side_effect=original_read):
            answer=run_agent(self.assistant,self.session,'Read the original methods for R2 and R1.',normalize_context({}),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(len(calls),3);self.assertEqual(answer['web_sources'],sources)
        self.assertEqual([r['source_id'] for r in answer['public_readings']],['R2','R1'])
        self.assertTrue(all(r['status']=='abstract' for r in answer['public_readings']))
        self.bridge.save_conversation_turn(self.session,self.doc['id'],'read','Read methods',answer)
        self.assertEqual(self.bridge.conversation(self.session,self.doc['id'])[-1]['public_readings'],answer['public_readings'])

    def test_specific_read_url_cannot_resolve_to_a_different_saved_paper(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        source={'id':'R1','title':'Latest methods','url':'https://doi.org/10.1234/latest','snippet':'Metadata only','provider':'Crossref'}
        self.service.store.artifact(self.owner,'whiteboard_conversation',{'document_id':self.doc['id'],'run_id':'latest','question':'Sources?','title':'Sources','summary':'Metadata','claims':[],'web_sources':[source]})
        calls=[]
        def respond(messages,info):
            calls.append(True)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('read_public_reference',{'reference_id':'R1'})])
            return ModelResponse(parts=[ToolCallPart('final_result',{'title':'Source unavailable','clarification':'Please select the original reference again.'})])
        with patch('fireatlas.assistant.agent.provider_config',return_value={'provider':'openai','model':'test','configured':True,'input_price':1,'output_price':1}),patch('fireatlas.assistant.public_reading.read_reference') as read:
            answer=run_agent(self.assistant,self.session,'Read R1. Source URL: https://doi.org/10.1234/older',normalize_context({}),{'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True}},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        read.assert_not_called();self.assertEqual(answer['kind'],'AI clarification')

    def test_research_history_is_compact_and_board_context_is_not_duplicated(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart,UserPromptPart
        receipt={'query':'x','raw_payload':'x'*40000}
        history=[{'question':'What next?','summary':'Compare fuel conditions.','claims':[],
                  'public_research_receipts':[receipt], 'web_sources':[{'title':'Original methods','url':'https://doi.org/10.1234/fuel','snippet':'x'*1000}],
                  'research_team':{'status':'partial','specialists':[{'status':'completed','label':'Scientific skeptic','insight':'Match observation opportunity.','next_test':'Compare acquisition times.','sources':[receipt]}]}}]
        seen=[]
        def respond(messages,info):
            content=next(part.content for message in messages for part in message.parts if isinstance(part,UserPromptPart))
            payload=json.loads(content[0] if isinstance(content,list) else content)
            self.assertNotIn('studio',payload['view'])
            self.assertEqual(payload['studio']['document_id'],self.doc['id'])
            recent=payload['recent_investigations'][0]
            self.assertNotIn('public_research_receipts',recent)
            self.assertEqual(recent['public_references'][0]['url'],'https://doi.org/10.1234/fuel')
            self.assertEqual(recent['research_team']['specialists'][0]['next_test'],'Compare acquisition times.')
            self.assertLess(len(json.dumps(recent)),1500)
            seen.append(True)
            return ModelResponse(parts=[ToolCallPart('final_result',{'title':'Next step','clarification':'Which fuel-moisture measure should the next test use?','claims':[]})])
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True}}
        with patch('fireatlas.assistant.agent.provider_config',return_value={'provider':'openai','model':'test','configured':True,'input_price':1,'output_price':1}),patch.object(self.bridge,'conversation',return_value=history):
            run_agent(self.assistant,self.session,'What could the skeptic test next?',normalize_context({}),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertTrue(seen)

    def test_followup_keeps_the_complete_proposed_test_and_its_later_reference_handle(self):
        from fireatlas.assistant.agent import conversation_context
        brief={'synthesis':'Read original methods.','hypothesis':'Moisture may affect detectability.','proposed_test':'Match independent moisture measurements to acquisition conditions.','source_ids':['R6']}
        sources=[{'id':f'R{i}','title':'Original method','url':f'https://doi.org/10.1234/method{i}'} for i in range(1,9)]
        recent=conversation_context([{'question':'What could be tested?','summary':'Do not duplicate this formatted answer.','research_answer':brief,'web_sources':sources}])[0]
        self.assertEqual(recent['research_answer'],brief)
        self.assertEqual(recent['public_references'],[sources[5]])
        self.assertEqual(recent['summary'],brief['synthesis'])

    def test_non_studio_history_retains_receipt_and_scope_for_followups(self):
        from fireatlas.assistant.agent import conversation_context
        turn={'question':'Compare these observations','summary':'Read the original source.','context':{'year':2024,'month':7,'source':'VIIRS_SNPP_SP'},'evidence_ids':['owned-receipt']}
        recent=conversation_context([turn])[0]
        self.assertEqual(recent['context'],turn['context'])
        self.assertEqual(recent['evidence_ids'],['owned-receipt'])

    def test_failed_optional_team_preserves_primary_answer_and_saved_sources(self):
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True},'research_team':True}
        run,_=self.assistant.store.create_run(self.session,'optional-team',{})
        with patch('fireatlas.assistant.service.run_agent',return_value={'title':'Original answer','summary':'Primary evidence remains available.','claims':[]}),patch('fireatlas.assistant.research_team.review',side_effect=ValueError('Verified cheap route unavailable.')):
            self.assistant._run(self.session,run,normalize_context({}),view,'Explain the evidence.',None,{},threading.Event(),[])
        result=self.assistant.store.run(self.session,run)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['body']['title'],'Original answer')
        self.assertEqual(result['body']['research_team']['status'],'unavailable')
        turns=self.bridge.conversation(self.session,self.doc['id'])
        self.assertEqual(turns[-1]['research_team']['status'],'unavailable')

    def test_search_clarification_cannot_publish_an_invented_address(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('search_public_research',{'query':'wildfire fuel moisture','scholarly':True})])
            if len(calls)==2:return ModelResponse(parts=[ToolCallPart('final_result',{'title':'Clarify','clarification':'Did you mean https://fabricated.example/paper?','claims':[]})])
            return ModelResponse(parts=[ToolCallPart('final_result',{'title':'References','interpretation':'Review the retrieved methods before choosing a test.','claims':[]})])
        source={'title':'Fuel moisture study','url':'https://doi.org/10.1234/fuel','snippet':'Journal metadata','provider':'Crossref'}
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True}}
        with patch('fireatlas.assistant.agent.provider_config',return_value={'provider':'openai','model':'test','configured':True,'input_price':1,'output_price':1}),patch('fireatlas.assistant.web_references.search_references',return_value=[source]):
            answer=run_agent(self.assistant,self.session,'Investigate literature about fuel moisture.',normalize_context({}),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(len(calls),3)
        self.assertNotIn('fabricated.example',json.dumps(answer))

    def test_explicit_search_handles_are_saved_without_mutating_original_receipt(self):
        source={'title':'Original methods','url':'https://doi.org/10.1234/fuel','snippet':'Metadata only','provider':'Crossref'}
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True}}
        run,_=self.assistant.store.create_run(self.session,'explicit-handles',{})
        with patch('fireatlas.assistant.web_references.search_references',return_value=[source]),patch('fireatlas.assistant.service.run_agent') as model:
            self.assistant._run(self.session,run,normalize_context({}),view,'Find papers on fuel moisture',None,{},threading.Event(),[])
        model.assert_not_called()
        body=self.assistant.store.run(self.session,run)['body']
        self.assertEqual(body['web_sources'],[{**source,'id':'R1'}])
        receipt=self.assistant.store.get_artifact(self.session,body['web_search_receipts'][0],'public_research')['body']
        self.assertEqual(receipt['sources'],[source])
        self.assertEqual(self.bridge.conversation(self.session,self.doc['id'])[-1]['web_sources'],body['web_sources'])

    def test_explicit_public_search_does_not_require_a_model(self):
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True}}
        with patch.object(self.assistant,'capabilities',return_value={'ai_available':False,'reason':'No model'}),patch.object(self.assistant.pool,'submit'):
            result=self.assistant.start(self.session,{'message':'Find papers on wildfire','context':self.assistant.store.session(self.session)['context'],'view':view})
        self.assertEqual(result['status'],'queued')

    def test_comparison_words_in_explicit_paper_search_do_not_invoke_the_model(self):
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True}}
        run,_=self.assistant.store.create_run(self.session,'comparison-literature',{})
        with patch('fireatlas.assistant.web_references.search_references',return_value=[]),patch('fireatlas.assistant.service.run_agent') as model:
            self.assistant._run(self.session,run,normalize_context({}),view,'Find papers on thermal differences across years',None,{},threading.Event(),[])
        model.assert_not_called()
        self.assertEqual(self.assistant.store.run(self.session,run)['status'],'completed')

    def test_unexpected_optional_failure_and_deadline_preserve_the_completed_answer(self):
        for index,error in enumerate((TimeoutError('private provider detail'),RuntimeError('private provider detail'),InterruptedError('deadline'))):
            view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True},'research_team':True}
            run,_=self.assistant.store.create_run(self.session,'optional-failure-'+str(index),{})
            with patch('fireatlas.assistant.service.run_agent',return_value={'title':'Original answer','summary':'Primary evidence remains available.','claims':[]}),patch('fireatlas.assistant.research_team.review',side_effect=error):
                self.assistant._run(self.session,run,normalize_context({}),view,'Explain the evidence.',None,{},threading.Event(),[])
            result=self.assistant.store.run(self.session,run)
            self.assertEqual(result['status'],'completed')
            self.assertEqual(result['body']['title'],'Original answer')
            self.assertNotIn('private provider detail',json.dumps(result))
