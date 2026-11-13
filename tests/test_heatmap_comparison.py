"""Comparison correctness and agent integration; isolated synthetic records only."""
import copy
from datetime import date
import json
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fireatlas.heatmap_comparison import build_comparison
from fireatlas.assistant.comparison_research import publish, weather_context, research_question
from fireatlas.assistant.contracts import normalize_context
from fireatlas.assistant.agent import run_agent
from fireatlas.assistant.service import AssistantService
from fireatlas.studio.assistant import StudioAssistant
from fireatlas.studio.heat import prepare_comparison
from tests.studio_support import StudioCase


def record(day, lon=88.6, lat=24.4):
    return {'longitude': lon, 'latitude': lat, 'acquisition_utc': day+'T12:00:00Z'}


def study(year=2024, rows=None, label='Synthetic area'):
    return {'label': label, 'bbox': [88, 24, 89, 25], 'start': f'{year}-01-01', 'end': f'{year}-12-31',
            'check': {'product': 'VIIRS_NOAA20_SP', 'sensor': 'NOAA-20 VIIRS',
                      'available_start': f'{year}-01-01', 'available_end': f'{year}-12-31',
                      'source_csv_sha256': 'synthetic-window', 'records': rows or []}}


class RankingTests(unittest.TestCase):
    def test_narrative_count_relations_are_checked_against_the_referenced_years(self):
        from fireatlas.heatmap_comparison import narrative_issue
        payload=build_comparison([study(y,[record(f'{y}-05-01',88.6+i*.02) for i in range(y-2022)]) for y in (2023,2024,2025)],mode='annual_peaks')
        self.assertIsNotNone(narrative_issue(payload,'The counts are equal for 2023 and 2024.'))
        self.assertIsNotNone(narrative_issue(payload,'The occupied cells decreased across the years.'))
        self.assertIsNone(narrative_issue(payload,'The occupied cells increased across the years.'))
        self.assertIsNone(narrative_issue(payload,'The same product was used across years.'))
        self.assertIsNone(narrative_issue(payload,'2023 had fewer occupied cells than 2024.'))
        self.assertIsNone(narrative_issue(payload,'The counts are not equal for 2023 and 2024.'))
        self.assertIsNone(narrative_issue(payload,'Are the counts equal for 2023 and 2024?'))
        self.assertIsNotNone(narrative_issue(payload,'2025 has 3 cells, +2 over 2024.'))
        self.assertIsNone(narrative_issue(payload,'2025 has 3 cells, +1 over 2024.'))

    def test_explicit_weather_extrema_use_the_actual_panel_and_unknown_stays_unknown(self):
        from fireatlas.heatmap_comparison import narrative_issue
        payload=build_comparison([study(y,[record(f'{y}-05-01')]) for y in (2023,2024,2025)],mode='annual_peaks')
        for p,t,r in zip(payload['panels'],(35.2,38.6,37.6),(7.9,1.8,0)):
            p['weather']={'status':'available','air_temperature_max_c':t,'rainfall_7d_mm':r}
        self.assertIsNotNone(narrative_issue(payload,'Rainfall declines step by step, and the latest peak day is the hottest of the three seven-day summaries.'))
        self.assertIsNone(narrative_issue(payload,'The middle year had the hottest window. The first year was wettest and coolest; the final year was driest.'))
        self.assertIsNotNone(narrative_issue(payload,'The hottest window was 2025.'))
        payload['panels'][0]['weather']['rainfall_7d_mm']=None
        self.assertIsNotNone(narrative_issue(payload,'The final year was driest.'))
    def test_model_envelope_decoder_preserves_arguments_and_refuses_ambiguity(self):
        from fireatlas.assistant.local import normalize_comparison_arguments
        self.assertEqual(normalize_comparison_arguments('{"annual_peaks":{"places":["Test"],"years":[2023,2025]}}'),{'mode':'annual_peaks','places':['Test'],'years':[2023,2025]})
        conflicting={'annual_peaks':{'mode':'regions','places':['Test']}}
        self.assertEqual(normalize_comparison_arguments(conflicting),conflicting)
        self.assertEqual(normalize_comparison_arguments('not json'),'not json')

    def test_peak_uses_distinct_cells_not_repeat_detections_and_keeps_leap_day(self):
        rows = [record('2024-02-29')]*8+[record('2024-03-01'),record('2024-03-01',88.8)]
        payload = build_comparison([study(rows=rows)], mode='annual_peaks')
        panel = payload['panels'][0]
        self.assertEqual((panel['day'], panel['occupied_cells'], panel['detections']), ('2024-03-01', 2, 2))
        self.assertEqual(len(payload['searches'][0]['days']), 366)
        raw = build_comparison([study(rows=rows)], mode='annual_peaks', rank_by='detections')
        self.assertEqual(raw['panels'][0]['day'], '2024-02-29')

    def test_ties_are_retained_and_zero_year_has_no_invented_winner(self):
        payload = build_comparison([study(2023), study(rows=[record('2024-05-03'), record('2024-05-01')])], mode='annual_peaks')
        self.assertIsNone(payload['panels'][0]['day'])
        self.assertIsNone(payload['panels'][1]['cell_delta'])
        self.assertEqual(payload['panels'][1]['day'], '2024-05-01')
        self.assertEqual(payload['panels'][1]['tied_dates'], ['2024-05-01','2024-05-03'])

    def test_partial_window_mixed_product_and_duplicate_years_fail(self):
        partial = study();partial['check']['available_start']='2024-02-01'
        with self.assertRaisesRegex(ValueError,'entire'):build_comparison([partial],mode='annual_peaks')
        other=study(2025);other['check']['product']='MODIS_SP'
        with self.assertRaisesRegex(ValueError,'same explicit'):build_comparison([study(),other],mode='annual_peaks')
        self.assertEqual(len(build_comparison([study(2022),study(2024)],mode='annual_peaks')['panels']),2)
        with self.assertRaisesRegex(ValueError,'distinct'):build_comparison([study(2024),study(2024)],mode='annual_peaks')
        missing=study();missing['check']['source_windows']=[{'start':'2024-01-01','end':'2024-12-30','sha256':'synthetic'}]
        with self.assertRaisesRegex(ValueError,'full requested'):build_comparison([missing],mode='annual_peaks')

    def test_bad_dates_locations_and_panel_overflow_are_refused(self):
        with self.assertRaisesRegex(ValueError,'outside'):build_comparison([study(rows=[record('2025-01-01')])])
        with self.assertRaisesRegex(ValueError,'boundary'):build_comparison([study(rows=[record('2024-01-01',90)])])
        with self.assertRaisesRegex(ValueError,'six panels'):
            build_comparison([study(y,[record(f'{y}-05-{d:02}') for d in (1,2,3)]) for y in (2022,2023,2024)],mode='annual_peaks',top_days=3)

    def test_shared_scale_is_frozen_and_identical_cells_have_identical_pixels(self):
        payload=build_comparison([study(2023,[record('2023-05-01')]),study(2024,[record('2024-05-01')])],mode='annual_peaks')
        result=publish(SimpleNamespace(store=SimpleNamespace(artifact=lambda *args:'test')), 'test', payload)
        snapshot={'scope':result['context'],'receipt_sha256':result['sha256'],'release_id':result['release_id']}
        visual=prepare_comparison(snapshot,result)
        self.assertEqual(visual['panels'][0]['heat']['data'],visual['panels'][1]['heat']['data'])
        self.assertTrue(all(panel['heat']['domain']==payload['heat_scale']['domain'] for panel in visual['panels']))
        payload['heat_scale']['domain'][1]+=1
        with self.assertRaisesRegex(Exception,'scale'):prepare_comparison(snapshot,result)

    def test_weather_null_stays_unknown_and_invalid_units_are_unavailable(self):
        daily={'time':[f'2024-05-{d:02}' for d in range(1,8)],'temperature_2m_max':[30]*7,
               'precipitation_sum':[None]+[0]*6,'wind_speed_10m_max':[12]*7}
        data={'daily':daily,'daily_units':{'temperature_2m_max':'°C','precipitation_sum':'mm','wind_speed_10m_max':'km/h'}}
        response=SimpleNamespace(read=lambda _:json.dumps(data).encode())
        with patch('fireatlas.assistant.comparison_research.urlopen') as opened:
            opened.return_value.__enter__.return_value=response
            weather=weather_context([88,24,89,25],'2024-05-07',threading.Event(),time.monotonic()+20)
            self.assertEqual(weather['status'],'available');self.assertIsNone(weather['rainfall_7d_mm'])
            data['daily_units']['wind_speed_10m_max']='mph'
            self.assertEqual(weather_context([88,24,89,25],'2024-05-07',threading.Event(),time.monotonic()+20)['status'],'unavailable')
        stop=threading.Event();stop.set()
        with self.assertRaises(InterruptedError):weather_context([88,24,89,25],'2024-05-07',stop,time.monotonic()+20)


class ComparisonAgentTests(StudioCase):
    def setUp(self):
        super().setUp()
        self.assistant=AssistantService(self.database,self.root/'assistant/workspace.sqlite3')
        self.addCleanup(self.assistant.close)
        self.service.assistant=self.assistant
        self.bridge=StudioAssistant(self.service,self.assistant);self.assistant.studio_bridge=self.bridge
        self.doc=self.board();self.session=self.service.assistant_owner(self.owner)
        self.assistant.store.artifact(self.session,'studio_access',{'principal':self.owner,'document_id':self.doc['id']})

    def test_model_can_plan_three_years_then_freeze_and_reopen_the_comparison(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart,TextPart
        payload=build_comparison([study(y,[record(f'{y}-05-01')]) for y in (2022,2023,2024)],mode='annual_peaks')
        result=publish(self.assistant,self.session,payload)
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:self.assertIn('prepare_heatmap_comparison',[tool.name for tool in info.function_tools])
            else:self.assertEqual(info.function_tools,[])
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('prepare_heatmap_comparison',{'places':['Synthetic area'],'mode':'annual_peaks','years':[2022,2023,2024],'include_weather':False})])
            return ModelResponse(parts=[TextPart('The peak-day footprint is similar across the selected years. Compare acquisition times before attributing the pattern to weather.')])
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True,'frozen_evidence_ids':[],'frozen_evidence_refs':{}}}
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'local'},clear=True), patch('fireatlas.assistant.comparison_research.prepare',return_value=result):
            answer=run_agent(self.assistant,self.session,'Compare busiest days across three years for Synthetic area.',normalize_context({}),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertFalse(answer.get('ai_wording_unavailable'));self.assertEqual(len(calls),2)
        run,_=self.assistant.store.create_run(self.session,'comparison-test',{})
        answer['data_views']=view['studio']['requested_board_views']
        self.assistant.store.finish(self.session,run,'completed',answer)
        self.service.store.artifact(self.owner,'assistant_run',{'document_id':self.doc['id'],'run_id':run,'owner':self.session,'board_revision':self.doc['revision']})
        with patch.object(self.service.science,'release',side_effect=FileNotFoundError('No local imported archive')):
            binding=self.bridge.preserve_claims(self.owner,self.doc['id'],run)['bindings'][result['id']]
        report=self.service.snapshot_report(self.owner,self.doc['id'],binding['snapshotId'])
        self.assertTrue(report['verification']['verified'])
        preview=self.service.snapshot_preview(self.owner,self.doc['id'],binding['snapshotId'],'regional-comparison')
        self.assertEqual(len(preview['visual']['panels']),3)
        saved=self.service.snapshot_receipt(self.owner,self.doc['id'],binding['snapshotId'])['receipt']
        self.assertEqual(saved['payload']['searches'][0]['records'],payload['searches'][0]['records'])
        element={'id':'later-panel','type':'image','customData':{'fireatlas':{**binding,'comparisonPanel':2}}}
        document=self.service.transact(self.owner,self.doc['id'],{'base_revision':self.doc['revision'],'ops':[{'op':'patch_whiteboard','changes':[{'kind':'element','id':element['id'],'position':0,'value':element}]}]})
        with patch.object(self.assistant,'start',return_value={'id':'job'}) as started:
            self.bridge.start(self.owner,self.doc['id'],{'base_revision':document['revision'],'whiteboard':True,'selected_snapshot_elements':['later-panel'],'message':'Explain this selected panel.'})
            selected=started.call_args.args[1]['view']['studio']['selected_comparison_panels']
            self.assertEqual(selected[0]['start'],'2024-05-01')
            self.assertEqual(selected[0]['index'],2)

    def test_comparison_request_reaches_model_instead_of_single_area_dispatch(self):
        question='Compare heatmaps for Dhaka and Rajshahi from 2024-04-01 to 2024-04-30.'
        self.assertTrue(research_question(question))
        run,_=self.assistant.store.create_run(self.session,'route-test',{})
        with patch('fireatlas.assistant.service.run_agent',return_value={'title':'Planned comparison','summary':'test','claims':[]}) as model:
            self.assistant._run(self.session,run,normalize_context({}),{'studio':{'whiteboard':True}},question,None,{},threading.Event(),[])
        model.assert_called_once()

    def test_unqualified_local_narration_keeps_all_three_panels_without_a_second_inference(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        payload=build_comparison([study(y,[record(f'{y}-05-01')]) for y in (2023,2024,2025)],mode='annual_peaks')
        result=publish(self.assistant,self.session,payload);calls=[]
        def respond(messages,info):
            calls.append(1)
            return ModelResponse(parts=[ToolCallPart('prepare_heatmap_comparison',{'places':['Synthetic area'],'mode':'annual_peaks'})])
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True}}
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'local'},clear=True),patch('fireatlas.assistant.comparison_research.prepare',return_value=result),patch('pydantic_ai.models.openai.OpenAIChatModel',return_value=FunctionModel(respond)):
            answer=run_agent(self.assistant,self.session,'Compare peak days across three years for Synthetic area.',normalize_context({}),view,threading.Event(),time.monotonic()+30,lambda _:None)
        self.assertEqual(len(calls),1)
        self.assertTrue(answer['ai_wording_unavailable'])
        self.assertIn('not qualified',answer['summary'])
        self.assertIn('local-comparison-narration-unqualified',answer['observed_retry_categories'])
        self.assertEqual({claim['path'].split('/')[2] for claim in answer['claims']},{'0','1','2'})
        self.assertEqual(view['studio']['requested_board_views'][0]['result_id'],result['id'])

    def test_hosted_comparison_uses_focused_tools_checked_patterns_and_canonical_claim_labels(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        from fireatlas.assistant.agent import evidence_preview
        payload=build_comparison([study(y,[record(f'{y}-05-01',88.6+i*.02) for i in range(n)]) for y,n in ((2023,2),(2024,1),(2025,3))],mode='annual_peaks')
        result=publish(self.assistant,self.session,payload);calls=[]
        patterns=evidence_preview(result,result['context'])['checked_patterns']['occupied_cells']
        self.assertEqual(patterns,{'minimum_panels':[1],'maximum_panels':[2],'successive_directions':['decrease','increase']})
        def respond(messages,info):
            calls.append(1)
            self.assertEqual({tool.name for tool in info.function_tools},{'prepare_heatmap_comparison','search_public_research'})
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('prepare_heatmap_comparison',{'places':['Synthetic area'],'mode':'annual_peaks'})])
            return ModelResponse(parts=[ToolCallPart('final_result',{'title':'Peak comparison','interpretation':'Counts dipped then increased; no significance test was run. Test fuel moisture with a longer seasonal record.',
                'claims':[{'result_id':result['id'],'path':'/panels/2/cell_delta','label':'Incorrect model reference year'}]})])
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True}}
        with patch('fireatlas.assistant.agent.provider_config',return_value={'provider':'openai','model':'test','configured':True,'input_price':1,'output_price':1}),patch('fireatlas.assistant.comparison_research.prepare',return_value=result):
            answer=run_agent(self.assistant,self.session,'Compare annual peak days across three years for Synthetic area.',normalize_context({}),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertFalse(answer.get('ai_wording_unavailable'))
        self.assertEqual(len(calls),2)
        self.assertIn('vs 2023',answer['claims'][0]['label'])
        self.assertNotIn('Incorrect model',answer['claims'][0]['label'])

    def test_frozen_comparison_followup_model_failure_retains_evidence_instead_of_new_view_error(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.exceptions import UnexpectedModelBehavior
        payload=build_comparison([study(y,[record(f'{y}-05-01')]) for y in (2023,2024,2025)],mode='annual_peaks')
        result=publish(self.assistant,self.session,payload)
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'frozen_evidence_ids':[result['id']],
            'frozen_evidence_refs':{result['id']:{'documentId':self.doc['id'],'snapshotId':'test','snapshotHash':result['sha256']}}}}
        def fail(messages,info):raise UnexpectedModelBehavior('Simulated wording failure')
        with patch('fireatlas.assistant.agent.provider_config',return_value={'provider':'openai','model':'test','configured':True,'input_price':1,'output_price':1}),patch('fireatlas.assistant.comparison_research.prepare') as acquire:
            answer=run_agent(self.assistant,self.session,'Compare the three saved yearly heatmaps. Explain rainfall hypotheses without new acquisition.',normalize_context({}),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(fail))
        acquire.assert_not_called()
        self.assertTrue(answer['ai_wording_unavailable'])
        self.assertEqual(answer['evidence_ids'],[result['id']])
        self.assertEqual({claim['path'].split('/')[2] for claim in answer['claims']},{'0','1','2'})
        self.assertNotIn('could not prepare that view',answer['summary'])

    def test_frozen_comparison_followup_answers_without_requiring_a_new_view(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        payload=build_comparison([study(y,[record(f'{y}-05-01')]) for y in (2023,2024,2025)],mode='annual_peaks')
        result=publish(self.assistant,self.session,payload);calls=[]
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'frozen_evidence_ids':[result['id']],
            'frozen_evidence_refs':{result['id']:{'documentId':self.doc['id'],'snapshotId':'test','snapshotHash':result['sha256']}}}}
        def respond(messages,info):
            calls.append(1)
            return ModelResponse(parts=[ToolCallPart('final_result',{'title':'Saved comparison','interpretation':'The observed counts are equal. Test a rainfall hypothesis with a longer seasonal record.',
                'claims':[{'result_id':result['id'],'path':'/panels/2/occupied_cells','label':'Final peak occupied cells'}]})])
        with patch('fireatlas.assistant.agent.provider_config',return_value={'provider':'openai','model':'test','configured':True,'input_price':1,'output_price':1}),patch('fireatlas.assistant.comparison_research.prepare') as acquire:
            answer=run_agent(self.assistant,self.session,'Compare the three saved yearly heatmaps. Explain rainfall hypotheses without new acquisition.',normalize_context({}),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        acquire.assert_not_called()
        self.assertEqual(len(calls),1)
        self.assertFalse(answer.get('ai_wording_unavailable'))
        self.assertIn('observed counts are equal',answer['summary'])
        self.assertFalse(view['studio'].get('requested_board_views'))

    def test_comparison_retries_unsupported_statistical_wording(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart, TextPart
        payload=build_comparison([study(y,[record(f'{y}-05-01')]) for y in (2023,2024,2025)],mode='annual_peaks')
        result=publish(self.assistant,self.session,payload);calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('prepare_heatmap_comparison',{'places':['Synthetic area'],'mode':'annual_peaks'})])
            return ModelResponse(parts=[TextPart('There is no significant difference.' if len(calls)==2 else 'The observed counts are equal. Compare acquisition times before proposing a weather explanation.')])
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True}}
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'local'},clear=True),patch('fireatlas.assistant.comparison_research.prepare',return_value=result):
            answer=run_agent(self.assistant,self.session,'Compare peak days across three years for Synthetic area.',normalize_context({}),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(len(calls),3)
        self.assertFalse(answer.get('ai_wording_unavailable'))
        self.assertIn('observed counts are equal',answer['summary'])


if __name__=='__main__':unittest.main()
