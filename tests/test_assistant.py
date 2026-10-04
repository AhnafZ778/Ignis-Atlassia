"""Scientific parity and assistant trust-boundary regressions, using temporary fixtures."""
import contextlib
import io
import json
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fireatlas import core, research, replay
from fireatlas.demo import make_demo,BBOX
from fireatlas.assistant.contracts import normalize_context
from fireatlas.assistant.science import Science,readonly
from fireatlas.assistant.store import Store
from fireatlas.assistant.service import AssistantService
from fireatlas.assistant.agent import fact,run_agent

class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.database=self.root/'study.sqlite3'
        with contextlib.redirect_stdout(io.StringIO()):make_demo(self.root/'fixtures',self.database)
        with core.connect(self.database) as db:db.execute('UPDATE batches SET demo=0')
        self.service=AssistantService(self.database,self.root/'private.sqlite3');self.addCleanup(self.service.close)
        self.cfg=normalize_context({'year':2015,'month':7,'bbox':list(BBOX),'revision':1})
        self.owner=self.service.store.create_session(self.cfg)
        self.service.store.update_session(self.owner,self.cfg,{'instance':'tab-one'})
    def test_scientific_parity_and_source_units(self):
        evidence=self.service.science.call(self.owner,'research',self.cfg)
        with readonly(self.database) as db:expected=research.report(db,year=2015,month=7,bbox=BBOX)
        self.assertEqual(evidence['payload']['report_id'],expected['report_id'])
        self.assertEqual(evidence['payload']['overlap']['totals'],expected['overlap']['totals'])
        card=fact(evidence,'/raw_pixels');self.assertEqual(card['unit'],'records')
        self.assertEqual(fact(evidence,'/overlap/jaccard')['unit'],'ratio')
        with readonly(self.database) as db:
            with self.assertRaises(Exception):db.execute('DELETE FROM observations')
    def test_agent_visual_explanation_uses_retrieved_evidence_only(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        from fireatlas.assistant.presentation import validate_visualization
        evidence=self.service.science.call(self.owner,'missingness',self.cfg)
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('saved_evidence',{'result_id':evidence['id']})])
            # Incompatible charts are retried rather than published with the wrong unit.
            kind='overlap' if len(calls)==2 else 'availability'
            value={'title':'Source availability','interpretation':'Readings and export status are separate evidence.'}
            if len(calls)==2:value['visualizations']=[{'result_id':evidence['id'],'kind':kind}]
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,value)])
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}):
            answer=run_agent(self.service,self.owner,'Explain these gaps visually',self.cfg,{},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(len(calls),3)
        self.assertEqual(answer['visualizations'],[{'result_id':evidence['id'],'kind':'availability'}])
        self.assertIn(evidence['id'],answer['evidence_ids'])
        with self.assertRaises(ValueError):validate_visualization(evidence,'daily')
        self.assertEqual(validate_visualization(evidence,'workflow')['kind'],'workflow')
    def test_visual_request_cannot_publish_incorrect_chart_units(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        evidence=self.service.science.call(self.owner,'replay',self.cfg)
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('saved_evidence',{'result_id':evidence['id']})])
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Sensor chart','interpretation':'This chart shows detected cell-days per source.'})])
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}):
            answer=run_agent(self.service,self.owner,'Show a daily MODIS and VIIRS graph',self.cfg,{},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['kind'],'Checked visual explanation')
        self.assertTrue(answer['ai_wording_unavailable'])
        self.assertEqual(answer['visualizations'],[{'result_id':evidence['id'],'kind':'daily'}])
        self.assertNotIn('detected cell-days',answer['summary'])
    def test_explicit_month_comparison_preserves_actual_scope_and_calculation(self):
        context=normalize_context({**self.cfg,'start':'2015-07-12','end':'2015-08-05','day':'2015-08-02','as_of':'2015-08-05'})
        for month,start,end in [('2015-07','2015-07-12','2015-07-31'),('2015-08','2015-08-01','2015-08-05')]:
            evidence=self.service.science.call(self.owner,'research',context,{'study_month':month})
            actual=evidence['context']
            self.assertEqual((actual['start'],actual['end']),(start,end))
            self.assertEqual(actual['bbox'],context['bbox'])
            with readonly(self.database) as db:
                expected=research.report(db,year=actual['year'],month=actual['month'],bbox=BBOX,
                    as_of=end,distance_km=actual['distance_km'],gap_days=actual['gap_days'],start_date=start if start[8:] != "01" else None)
            self.assertEqual(evidence['payload']['report_id'],expected['report_id'])
            self.assertEqual(evidence['payload']['overlap']['totals'],expected['overlap']['totals'])
        self.assertEqual(context['end'],'2015-08-05')
        for month in ['2015-06','2015-09','invalid']:
            with self.subTest(month=month),self.assertRaises(ValueError):
                self.service.science.call(self.owner,'research',context,{'study_month':month})
        with self.assertRaises(ValueError):self.service.science.call(self.owner,'replay',context,{'study_month':'2015-07'})
    def test_replay_persistence_and_missingness(self):
        result=self.service.science.call(self.owner,'replay',self.cfg)
        with readonly(self.database) as db:expected=replay.build_case(db,'custom-observation-study',study={'title':'Custom observation study','subtitle':'Stored observation records; incident membership unverified','start':'2015-07-01','end':'2015-07-31','selected_day':'2015-07-01','bbox':list(BBOX),'notes':[result['limitations'][0]]})
        self.assertEqual(result['payload']['summary'],expected['summary'])
        persisted=self.service.science.call(self.owner,'persistence',self.cfg)['payload']
        dates={}
        for frame in result['payload']['frames']:
            for cell in frame['cells']:dates.setdefault(f"{cell['grid_x']},{cell['grid_y']}",set()).add(frame['date_utc'])
        self.assertEqual({c['cell_id']:c['observed_days'] for c in persisted['cells']},{k:len(v) for k,v in dates.items()})
        gaps=self.service.science.call(self.owner,'missingness',self.cfg)['payload']
        self.assertEqual(gaps['days'][0]['products'],result['payload']['frames'][0]['products'])
    def test_missingness_preserves_every_date_and_separates_empty_from_incomplete(self):
        from fireatlas.assistant.agent import evidence_preview,guided_answer
        result=self.service.science.call(self.owner,'missingness',self.cfg)
        preview=evidence_preview(result,self.cfg)
        self.assertEqual(len(preview['payload']['days']),31)
        for source in ['MODIS_SP','VIIRS_SNPP_SP']:
            days=result['payload']['days'];summary=result['payload']['summary'][source]
            self.assertEqual(summary['incomplete_export_days'],sum(d['products'][source]['state']!='complete_export' for d in days))
            self.assertEqual(summary['no_imported_record_days'],sum(d['products'][source]['detections']==0 for d in days))
            self.assertEqual(fact(result,'/summary/'+source+'/incomplete_export_days')['unit'],'UTC days')
        for notice in result['payload']['availability_notices']:
            self.assertLessEqual(notice['start_utc'][:10],self.cfg['end']);self.assertGreaterEqual(notice['end_utc'][:10],self.cfg['start'])
        self.assertEqual(len(guided_answer(result)['claims']),8)

    def test_display_actions_validate_settings_and_keep_places_private(self):
        place={'title':'Geographic example','bbox':[-121,39,-120,40],'longitude':-120.5,'latitude':39.5}
        identifier=self.service.store.artifact(self.owner,'place',place)
        action=self.service.action(self.owner,'assistant',self.cfg,{'instance':'tab-one'},options={'kind':'focus_place','place_id':identifier})
        self.assertEqual(action['context'],self.cfg);self.assertEqual(action['place'],place)
        other=self.service.store.create_session(self.cfg)
        with self.assertRaises(PermissionError):self.service.action(other,'assistant',self.cfg,{},options={'kind':'focus_place','place_id':identifier})
        controls=self.service.action(self.owner,'replay',self.cfg,{},options={'kind':'set_view','settings':{'source':'VIIRS_SNPP_SP','view':'2d','layer':'ndvi','day':'2015-07-12'}})
        self.assertEqual(controls['context']['series'],'viirs-snpp');self.assertEqual(controls['context']['view'],'2d');self.assertEqual(controls['context']['context'],'ndvi')
        self.assertEqual(controls['context']['bbox'],self.cfg['bbox'])
        for settings in [{'scope':'study'},{'source':'fiction'},{'day':'2015-08-01'},{'metric':'frp'}]:
            with self.subTest(settings=settings),self.assertRaises(ValueError):self.service.action(self.owner,'assistant',self.cfg,{},options={'kind':'set_view','settings':settings})

    def test_geographic_resolver_coordinates_cache_and_ambiguity(self):
        from fireatlas.assistant.places import lookup
        raw=[{'boundingbox':['23.6','24','90.2','90.6'],'lat':'23.8','lon':'90.4','display_name':'Example city','osm_type':'relation','osm_id':1},
            {'boundingbox':['23','25','90','91'],'lat':'24','lon':'90.5','display_name':'Example district','osm_type':'relation','osm_id':2}]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def read(self,*_):return json.dumps(raw).encode()
        cache=self.root/'places.sqlite3'
        with patch('fireatlas.assistant.places.urllib.request.urlopen',return_value=Response()) as network:
            result=lookup('Example city, Example country',cache)
            self.assertEqual(result['status'],'choose_place');self.assertEqual(result['choices'][0]['bbox'],[90.2,23.6,90.6,24])
            self.assertEqual(lookup('Example city, Example country',cache),result);network.assert_called_once()
        with patch('fireatlas.assistant.places.urllib.request.urlopen') as network:
            self.assertEqual(lookup('Park Fire',cache)['status'],'resolved');network.assert_not_called()

    def test_opencv_outline_preserves_image_size_and_rejects_unregistered_bounds(self):
        import cv2,numpy as np,base64
        from fireatlas.assistant.figures import annotate
        pixels=np.zeros((100,240,3),dtype=np.uint8);_,png=cv2.imencode('.png',pixels)
        image={'data':base64.b64encode(png).decode(),'caption':'Test evidence guide','regions':[{'target':'source-catalog','rect':[10,30,220,60],'label':'Source evidence'}]}
        result=annotate(image,'source-catalog');marked=cv2.imdecode(np.frombuffer(base64.b64decode(result['data']),dtype=np.uint8),cv2.IMREAD_COLOR)
        self.assertEqual(marked.shape,pixels.shape);self.assertGreater(np.count_nonzero(marked),0)
        with self.assertRaises(ValueError):annotate(image,'heat-field')
        image['regions'][0]['rect']=[10,30,400,60]
        with self.assertRaises(ValueError):annotate(image,'source-catalog')

    def test_agent_can_outline_only_a_registered_owned_figure(self):
        import cv2,numpy as np,base64
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        _,png=cv2.imencode('.png',np.zeros((100,240,3),dtype=np.uint8))
        image={'data':base64.b64encode(png).decode(),'mime':'image/png','caption':'Actual evidence guide','revision':self.cfg['revision'],'regions':[{'target':'source-catalog','rect':[10,30,220,60],'label':'Source catalog'}]}
        identifier=self.service.store.artifact(self.owner,'image',image);calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('annotate_figure',{'image_id':identifier,'target':'source-catalog'})])
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Evidence callout','interpretation':'The source catalog is outlined in the attached evidence guide.'})])
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}):
            answer=run_agent(self.service,self.owner,'Outline this source catalog',self.cfg,{},threading.Event(),time.monotonic()+30,lambda _:None,images=[(png.tobytes(),'image/png')],model=FunctionModel(respond))
        self.assertEqual(len(answer['figure_ids']),1);self.assertEqual(answer['claims'],[])
        figure=self.service.store.get_artifact(self.owner,answer['figure_ids'][0],'annotated_figure')['body']
        self.assertEqual(figure['image_id'],identifier);self.assertEqual(figure['target'],'source-catalog')
    def test_selected_day_preview_and_fact_labels_keep_sensor_date_and_unit(self):
        from fireatlas.assistant.agent import evidence_preview
        result=self.service.science.call(self.owner,'replay',self.cfg)
        day=result['payload']['frames'][10]['date_utc']
        preview=evidence_preview(result,{**self.cfg,'day':day})
        self.assertEqual(preview['selected_frame_path'],'/frames/10')
        self.assertEqual(preview['selected_frame']['products'],result['payload']['frames'][10]['products'])
        self.assertNotIn('observations',preview['payload'])
        self.assertNotIn('cells',preview['selected_frame'])
        for source,name in [('MODIS_SP','MODIS'),('VIIRS_SNPP_SP','VIIRS S-NPP')]:
            card=fact(result,f'/frames/10/products/{source}/detections')
            self.assertIn(name,card['label']);self.assertIn(day,card['label'])
            self.assertEqual(card['unit'],'records')
            self.assertEqual(fact(result,f'/frames/10/products/{source}/cell_days')['unit'],'cells')
    def test_displayed_day_question_reuses_owned_matching_map_evidence(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        evidence=self.service.science.call(self.owner,'replay',self.cfg)
        day=evidence['payload']['frames'][10]['date_utc']
        cfg={**self.cfg,'day':day}
        calls=[]
        def respond(messages,info):
            content=next(p.content for m in messages for p in getattr(m,'parts',[]) if getattr(p,'part_kind','')=='user-prompt')
            prompt=json.loads(content[0] if isinstance(content,list) else content)
            prepared=prompt['prepared_evidence']
            self.assertEqual(len(prepared),1)
            self.assertEqual(prepared[0]['id'],evidence['id'])
            self.assertEqual(prepared[0]['selected_frame']['date_utc'],day)
            candidates=prepared[0]['selected_frame_claims']
            self.assertTrue(any(c['path']=='/frames/10/date_utc' for c in candidates))
            selected=next(c for c in candidates if c['path']=='/frames/10/products/MODIS_SP/detections')
            calls.append(1)
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Selected source readings','interpretation':'Sensor records remain separate and their export status must be checked before comparing them.','claims':[{'result_id':selected['result_id'],'path':selected['path'],'label':'MODIS selected-day detections'}]})])
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}):
            answer=run_agent(self.service,self.owner,'Compare counts for the selected UTC day.',cfg,{'instance':'tab-one','result_id':evidence['id']},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(len(calls),1)
        self.assertEqual(answer['claims'][0]['value'],evidence['payload']['frames'][10]['products']['MODIS_SP']['detections'])
        self.assertEqual(answer['claims'][0]['path'],'/frames/10/products/MODIS_SP/detections')

    def test_displayed_map_from_another_study_is_not_prepared_evidence(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        evidence=self.service.science.call(self.owner,'replay',self.cfg)
        cfg={**self.cfg,'bbox':[-121.9,39.1,-120.1,40.9]}
        def respond(messages,info):
            content=next(p.content for m in messages for p in getattr(m,'parts',[]) if getattr(p,'part_kind','')=='user-prompt')
            prompt=json.loads(content[0] if isinstance(content,list) else content)
            self.assertEqual(prompt['prepared_evidence'],[])
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Clarify the observation scope','interpretation':'Load the map for the current boundary before comparing its readings.','clarification':'Load the map for the current boundary before comparing its readings.'})])
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}):
            answer=run_agent(self.service,self.owner,'Compare counts for this map.',cfg,{'instance':'tab-one','result_id':evidence['id']},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['claims'],[])

    def test_original_rows_paginate_without_counting_map_samples(self):
        first=self.service.science.call(self.owner,'observations',self.cfg,{'limit':3})['payload'];all_ids=[]
        current=first
        while True:
            all_ids.extend(r['detection_id'] for r in current['records'])
            if not current['next_cursor']:break
            current=self.service.science.call(self.owner,'observations',self.cfg,{'limit':3,'cursor':current['next_cursor']})['payload']
        self.assertEqual(len(set(all_ids)),first['total']);self.assertGreater(first['total'],first['returned'])

    def test_historical_windows_match_original_source_rows(self):
        result=self.service.science.call(self.owner,'archive_search',self.cfg,{'first_year':2015,'last_year':2015})['payload']
        with readonly(self.database) as db:
            w,s,e,n=self.cfg['bbox']
            expected=db.execute("SELECT source_id,COUNT(*) FROM observations WHERE processing_level='SP' AND lon>=? AND lon<=? AND lat>=? AND lat<=? AND acquisition_utc>=? AND acquisition_utc<? GROUP BY source_id",(w,e,s,n,'2015-01-01','2016-01-01')).fetchall()
        self.assertEqual(result['total_imported_records'],sum(r[1] for r in expected))
        for source,key in [('MODIS_SP','modis_records'),('VIIRS_SNPP_SP','viirs_records')]:
            self.assertEqual(sum(x[key] for x in result['windows']),next((r[1] for r in expected if r[0]==source),0))
        modis=self.service.science.call(self.owner,'archive_search',{**self.cfg,'source':'MODIS_SP','series':'modis'},{'first_year':2015,'last_year':2015})['payload']
        self.assertTrue(all(w['viirs_records']==0 for w in modis['windows']))
        with self.assertRaises(ValueError):self.service.science.call(self.owner,'archive_search',self.cfg,{'first_year':2000,'last_year':2027})
        self.assertIn('not confirmed',result['note'])

    def test_prompt_refinement_is_explicit_and_keeps_scope(self):
        from fireatlas.assistant.prompts import prepare_question
        original=dict(self.cfg)
        result=prepare_question('Predict the hottest spread of the Camp fire using MODIS and VIIRS',self.cfg,{'result_id':'known-id','path':'/frames/20/cells/15'})
        self.assertEqual(self.cfg,original)
        self.assertFalse(result['context_changed'])
        self.assertEqual(result['named_case'],'camp-2018')
        self.assertIn('radiative power',result['suggested_question'])
        self.assertIn('/frames/20/cells/15',result['suggested_question'])
        self.assertIn('another study',result['suggested_question'])
        long=prepare_question('hottest simulate earlier compare MODIS VIIRS Camp '+ 'x'*1740,self.cfg)
        self.assertLessEqual(len(long['suggested_question']),3000)

    def test_agent_inspects_unpreviewed_cell_and_pins_its_actual_date(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        evidence=self.service.science.call(self.owner,'replay',self.cfg)
        index=next(i for i,f in enumerate(evidence['payload']['frames']) if i>=3 and f['cells'])
        path=f'/frames/{index}/cells/0'
        sample=evidence['payload']['frames'][index]['cells'][0]
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('inspect_selection',{'result_id':evidence['id'],'path':path})])
            if len(calls)==2:
                result=next(p.content for m in reversed(messages) for p in getattr(m,'parts',[]) if getattr(p,'part_kind','')=='tool-return')
                if isinstance(result,str):result=json.loads(result)
                self.assertEqual(result['frame_products'],evidence['payload']['frames'][index]['products'])
                self.assertEqual(result['source_frame_date'],evidence['payload']['frames'][index]['date_utc'])
                return ModelResponse(parts=[ToolCallPart('annotate_evidence',{'result_id':evidence['id'],'path':path,'text':'Reported satellite sample; compare the available sensor readings.'})])
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Selected sample','interpretation':'The annotation identifies an actual returned sample.','claims':[{'result_id':evidence['id'],'path':path+'/modis_detections','label':'MODIS detections'}]})])
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}):
            answer=run_agent(self.service,self.owner,'Inspect this selected cell',self.cfg,{'instance':'tab-one','selection':{'result_id':evidence['id'],'path':path}},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        note=self.service.store.artifacts(self.owner,'annotation')[0]['body']
        self.assertEqual(note['context']['day'],evidence['payload']['frames'][index]['date_utc'])
        self.assertEqual(note['geometry']['coordinates'],[sample['ring']])
        self.assertEqual(note['path'],path)
        self.assertEqual(answer['claims'][0]['value'],sample['modis_detections'])
    def test_published_presets_return_checked_evidence_when_model_cannot_validate(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        def invalid(messages,info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Unsupported model prose','interpretation':'There were 999 fires.'})])
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            answer=run_agent(self.service,self.owner,'Check the selected study’s source availability.',self.cfg,{},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(invalid))
            self.assertEqual(answer['kind'],'Checked archive workflow');self.assertEqual(len(answer['claims']),8)
            result=self.service.science.call(self.owner,'replay',self.cfg)
            frame=next(i for i,f in enumerate(result['payload']['frames']) if f['cells']);path=f'/frames/{frame}/cells/0'
            selected=run_agent(self.service,self.owner,'Inspect the selected cell. Explain its readings and annotate it.',self.cfg,{'selection':{'result_id':result['id'],'path':path}},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(invalid))
        self.assertEqual(selected['kind'],'Checked selected-sample workflow')
        self.assertTrue(any(c['path']==path+'/modis_detections' for c in selected['claims']))
        for claim in selected['claims']:self.assertEqual(claim['value'],fact(result,claim['path'])['value'])
        note=self.service.store.artifacts(self.owner,'annotation')[0]['body']
        self.assertEqual(note['path'],path);self.assertEqual(note['context']['day'],result['payload']['frames'][frame]['date_utc'])

    def test_ambiguous_places_never_allow_the_model_to_choose_a_camera_target(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('resolve_study_place',{'place':'Example'})])
            result=next(p.content for m in messages for p in getattr(m,'parts',[]) if getattr(p,'tool_name',None)=='resolve_study_place' and getattr(p,'part_kind','')=='tool-return')
            if isinstance(result,str):result=json.loads(result)
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Camera','clarification':'I picked the first result.','actions':[{'destination':'assistant','options':{'kind':'focus_place','place_id':result['choices'][0]['place_id']}}]})])
        choice={'title':'Example city','bbox':[-121,39,-120,40],'longitude':-120.5,'latitude':39.5}
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}),patch('fireatlas.assistant.places.lookup',return_value={'status':'choose_place','choices':[choice,{**choice,'title':'Example district'}]}):
            answer=run_agent(self.service,self.owner,'Locate Example',self.cfg,{},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['actions'],[]);self.assertEqual(answer['claims'],[]);self.assertEqual(len(answer['places']),2)
    def test_agent_repairs_annotation_text_without_saving_invalid_claims(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        evidence=self.service.science.call(self.owner,'replay',self.cfg)
        index=next(i for i,f in enumerate(evidence['payload']['frames']) if f['cells'])
        path=f'/frames/{index}/cells/0'
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('annotate_evidence',{'result_id':evidence['id'],'path':path,'text':'MODIS recorded 1 detection here.'})])
            if len(calls)==2:
                self.assertEqual(self.service.store.artifacts(self.owner,'annotation'),[])
                self.assertTrue(any(getattr(p,'part_kind','')=='retry-prompt' for m in messages for p in getattr(m,'parts',[])))
                return ModelResponse(parts=[ToolCallPart('annotate_evidence',{'result_id':evidence['id'],'path':path,'text':'Reported satellite sample; inspect the linked source readings.'})])
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Annotated sample','interpretation':'The label is linked to the actual sample.','claims':[{'result_id':evidence['id'],'path':path+'/modis_detections','label':'MODIS detections'}]})])
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}):
            answer=run_agent(self.service,self.owner,'Label the selected sample',self.cfg,{'instance':'tab-one','selection':{'result_id':evidence['id'],'path':path}},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        notes=self.service.store.artifacts(self.owner,'annotation')
        self.assertEqual(len(notes),1);self.assertEqual(len(calls),3)
        self.assertEqual(notes[0]['body']['text'],'Reported satellite sample; inspect the linked source readings.')
        self.assertEqual(answer['claims'][0]['path'],path+'/modis_detections')
    def test_agent_repairs_numerical_prose_into_useful_checked_explanation(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        evidence=self.service.science.call(self.owner,'research',self.cfg)
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('saved_evidence',{'result_id':evidence['id']})])
            interpretation='The union contains 4 cell-days.' if len(calls)==2 else 'The union counts each observed cell once per date when either sensor reports it; shared cells are not added twice.'
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Sensor union','interpretation':interpretation,'claims':[{'result_id':evidence['id'],'path':'/overlap/totals/union','label':'union'}]})])
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}):
            answer=run_agent(self.service,self.owner,'Explain the observed union',self.cfg,{'instance':'tab-one'},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(len(calls),3);self.assertEqual(answer['claims'][0]['value'],4)
        self.assertIn('not added twice',answer['summary'])
        self.assertNotIn('checked evidence is shown below',answer['summary'])
    def test_sessions_actions_and_context_revisions(self):
        evidence=self.service.science.call(self.owner,'method',self.cfg)
        other=self.service.store.create_session(self.cfg)
        with self.assertRaises(PermissionError):self.service.store.get_artifact(other,evidence['id'])
        action=self.service.action(self.owner,'overlap',self.cfg,{'instance':'tab-one'},evidence['id'])
        with self.assertRaises(ValueError):self.service.acknowledge(self.owner,action['id'],{'revision':0,'instance':'tab-one','state':'applied'})
        self.assertTrue(self.service.acknowledge(self.owner,action['id'],{'revision':1,'instance':'tab-one','state':'applied'})['acknowledged'])
        self.assertTrue(self.service.acknowledge(self.owner,action['id'],{'revision':1,'instance':'tab-one','state':'applied'})['duplicate'])
        stale=self.service.action(self.owner,'overlap',self.cfg,{'instance':'tab-one'})
        self.service.store.update_session(self.owner,{**self.cfg,'revision':2},{'instance':'tab-one'})
        with self.assertRaises(ValueError):self.service.acknowledge(self.owner,stale['id'],{'revision':1,'instance':'tab-one','state':'applied'})
        with self.assertRaises(ValueError):self.service.store.update_session(self.owner,self.cfg,{'instance':'tab-one'})
        with self.assertRaises(ValueError):self.service.store.update_session(self.owner,{**self.cfg,'revision':3},{'instance':'tab-two'})
    def test_budget_reservations_are_atomic_and_uncertain_usage_stays_reserved(self):
        store=Store(self.root/'cost.sqlite3',daily_limit=100,session_limit=100)
        owner=store.create_session(self.cfg)
        def reserve():
            try:return store.reserve(owner,30)
            except ValueError:return None
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(lambda _:reserve(),range(8)))
        self.assertEqual(sum(r is not None for r in results),3)
        store.reconcile(owner,next(r for r in results if r),None)
        self.assertEqual(store.budget(owner)['used_or_reserved'],90/1e6)
    def test_idempotency_cancel_and_report_escape(self):
        first,fresh=self.service.store.create_run(self.owner,'duplicate',{'question':'test'})
        second,new=self.service.store.create_run(self.owner,'duplicate',{'question':'test'})
        self.assertTrue(fresh);self.assertFalse(new);self.assertEqual(first,second)
        self.service.cancel(self.owner,first)
        self.service.store.finish(self.owner,first,'completed',{'fake':'late response'})
        self.assertEqual(self.service.store.run(self.owner,first)['status'],'cancelled')
        self.service.store.artifact(self.owner,'answer',{'title':'<script>evil()</script>','kind':'test','summary':'<img onerror=evil()>','claims':[]})
        report=self.service.report_html(self.owner)
        self.assertNotIn('<script>evil()',report);self.assertIn('&lt;script&gt;',report)
    def test_strict_context_and_no_joint_frp(self):
        for cfg in ({'source':'joint','metric':'frp'},{'bbox':[1,2,float('nan'),4]},{'revision':True},{'start':'2024-08-01','end':'2024-07-01'},{'region':'made-up'}):
            with self.subTest(cfg=cfg),self.assertRaises(ValueError):normalize_context(cfg)
        with self.assertRaises(ValueError):self.service.science.call(self.owner,'research',normalize_context({'case':'park-2024'}))
    def test_provider_contract_without_network(self):
        try:
            from pydantic_ai.models.function import FunctionModel
            from pydantic_ai.messages import ModelResponse,ToolCallPart
        except ImportError:self.skipTest('Optional provider dependencies are not installed.')
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('investigate',{'operation':'research'})])
            # Science returns its full result ID; test function locates the tool result.
            result=next(part.content for m in reversed(messages) for part in getattr(m,'parts',[]) if getattr(part,'part_kind','')=='tool-return')
            result=json.loads(result) if isinstance(result,str) else result
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Checked overlap','interpretation':'The shared cells are supported by the source comparison.','claims':[{'result_id':result['id'],'path':'/overlap/totals/union','label':'A misleading invented label'}],'actions':[]})])
        with patch.dict('os.environ',{'OPENAI_API_KEY':'not-a-real-key','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}):
            answer=run_agent(self.service,self.owner,'Compare sensors',self.cfg,{'instance':'tab-one'},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['claims'][0]['value'],4)
        self.assertEqual(answer['claims'][0]['label'],'union')
        self.assertEqual(len(calls),2)

    def test_agent_repairs_invalid_evidence_references_before_publication(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart
        for invalid in ('overlap.totals.union', '/overlap/totals/nonexistent'):
            with self.subTest(path=invalid):
                calls=[]
                evidence=None
                def respond(messages,info):
                    nonlocal evidence
                    calls.append(1)
                    if len(calls)==1:
                        return ModelResponse(parts=[ToolCallPart('investigate',{'operation':'research'})])
                    if evidence is None:
                        evidence=next(p.content for m in messages for p in getattr(m,'parts',[]) if getattr(p,'part_kind','')=='tool-return' and getattr(p,'tool_name','')=='investigate')
                        if isinstance(evidence,str):evidence=json.loads(evidence)
                    path=invalid if len(calls)==2 else '/overlap/totals/union'
                    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Checked sensor overlap','interpretation':'The comparison preserves each sensor source.','claims':[{'result_id':evidence['id'],'path':path,'label':'union'}]})])
                with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}):
                    answer=run_agent(self.service,self.owner,'Compare sensors',self.cfg,{'instance':'tab-one'},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
                self.assertEqual(len(calls),3)
                self.assertEqual(answer['claims'][0]['value'],4)
                self.assertEqual(answer['claims'][0]['path'],'/overlap/totals/union')

    def test_agent_recovers_from_invalid_monthly_tool_scope(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart
        cfg=normalize_context({**self.cfg,'start':'2015-07-12','end':'2015-08-05','day':'2015-07-12','as_of':'2015-08-05'})
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('investigate',{'operation':'research'})])
            if len(calls)==2:
                self.assertTrue(any(getattr(p,'part_kind','')=='retry-prompt' for m in messages for p in getattr(m,'parts',[])))
                return ModelResponse(parts=[ToolCallPart('investigate',{'operation':'research','arguments':{'study_month':'2015-07'}})])
            result=next(p.content for m in reversed(messages) for p in getattr(m,'parts',[]) if getattr(p,'part_kind','')=='tool-return')
            if isinstance(result,str):result=json.loads(result)
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'July source comparison','interpretation':'This calculation covers the explicitly selected calendar month.','claims':[{'result_id':result['id'],'path':'/overlap/totals/union','label':'union'}]})])
        self.service.store.update_session(self.owner,cfg,{'instance':'tab-one'})
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}):
            answer=run_agent(self.service,self.owner,'Compare sensors in July in this study',cfg,{'instance':'tab-one'},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(len(calls),3)
        evidence=self.service.store.get_artifact(self.owner,answer['evidence_ids'][0])['body']
        self.assertEqual((evidence['context']['start'],evidence['context']['end']),('2015-07-12','2015-07-31'))

    def test_unfamiliar_place_requires_clarification_not_current_study_facts(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, ToolCallPart
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:
                return ModelResponse(parts=[ToolCallPart('resolve_study_place',{'place':'Bangladesh'})])
            if len(calls)==2:
                # A plausible-sounding unsupported answer must be rejected.
                return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Regional findings','interpretation':'The selected California detections describe the requested region.'})])
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Define the Bangladesh study','interpretation':'The requested location needs a geographic boundary.','clarification':'What west, south, east, north coordinates and UTC dates should I check for Bangladesh?'})])
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}),patch.object(self.service.science,'call') as query,patch('fireatlas.assistant.places.lookup',return_value={'status':'not_found','choices':[]}):
            answer=run_agent(self.service,self.owner,'Have there been wildfires near Bangladesh?',self.cfg,{'instance':'tab-one'},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        query.assert_not_called()
        self.assertEqual(len(calls),3)
        self.assertEqual(answer['kind'],'AI clarification')
        self.assertIn('Bangladesh',answer['summary'])
        self.assertEqual(answer['claims'],[])
        self.assertEqual(answer['actions'],[])

    def test_resolved_new_place_cannot_be_queried_using_old_study_boundary(self):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('resolve_study_place',{'place':'Dhaka'})])
            if len(calls)==2:return ModelResponse(parts=[ToolCallPart('investigate',{'operation':'replay'})])
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Choose dates','clarification':'What UTC interval should I check for this geographic area?'})])
        place={'title':'Dhaka','bbox':[90.2,23.6,90.6,24],'longitude':90.4,'latitude':23.8}
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}),patch('fireatlas.assistant.places.lookup',return_value={'status':'resolved','choices':[place]}),patch.object(self.service.science,'call') as query:
            answer=run_agent(self.service,self.owner,'Inspect Dhaka',self.cfg,{},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        query.assert_not_called();self.assertEqual(answer['claims'],[]);self.assertEqual(len(calls),3)

    def test_http_ownership_origin_exports_and_actual_run(self):
        from fireatlas.web import handler_factory
        with patch('fireatlas.assistant.AssistantService',return_value=self.service):
            handler=handler_factory(self.database)
        handler.log_message=lambda *_:None
        server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        origin=f'http://127.0.0.1:{server.server_port}'
        def request(route,body=None,cookie='',origin_header=None):
            headers={'Cookie':cookie,'Origin':origin if origin_header is None else origin_header}
            if body is not None:headers['Content-Type']='application/json'
            req=urllib.request.Request(origin+'/api/assistant/'+route,data=json.dumps(body).encode() if body is not None else None,headers=headers)
            try:response=urllib.request.urlopen(req,timeout=5)
            except urllib.error.HTTPError as error:response=error
            with response:return response.status,json.loads(response.read()),response.headers
        with patch.dict('os.environ',{'FIREATLAS_ASSISTANT_ORIGIN':origin}):
            self.assertEqual(request('sessions',{'context':self.cfg},origin_header='https://untrusted.example')[0],403)
            code,body,headers=request('sessions',{'context':self.cfg});self.assertEqual(code,200)
            cookie=headers['Set-Cookie'].split(';')[0]
            self.assertIn('HttpOnly',headers['Set-Cookie']);self.assertIn('SameSite=Strict',headers['Set-Cookie'])
            for _ in range(35):self.assertEqual(request('sessions',{'context':self.cfg},cookie=cookie)[0],200)
            self.assertEqual(request('views',{'context':self.cfg,'view':{'instance':'http-tab'}},cookie)[0],200)
            code,run,_=request('runs',{'context':self.cfg,'view':{'instance':'http-tab'},'operation':'research','nonce':'one-http-run'},cookie)
            self.assertEqual(code,202)
            for _ in range(100):
                _,receipt,_=request('runs/'+run['id'],cookie=cookie)
                if receipt['status'] in {'completed','failed'}:break
                time.sleep(.02)
            self.assertEqual(receipt['status'],'completed',receipt)
            evidence=receipt['body']['evidence_ids'][0]
            self.assertEqual(request('evidence/'+evidence,cookie=cookie)[0],200)
            _,_,other=request('sessions',{'context':self.cfg})
            self.assertEqual(request('evidence/'+evidence,cookie=other['Set-Cookie'].split(';')[0])[0],403)
            _,export,_=request('exports',cookie=cookie)
            self.assertEqual(export['evidence'][0]['id'],evidence)
            self.assertEqual(request('notebook',cookie=cookie)[1]['items'][0]['kind'],'answer')
            self.assertEqual(request('images',{'mime':'image/png','data':'not-base64','revision':1},cookie)[0],400)

    def test_gateway_ag_ui_stream_and_public_write_boundary(self):
        try:
            from starlette.testclient import TestClient
            from fireatlas.assistant.gateway import create_app
        except ImportError:self.skipTest('Optional gateway dependencies are not installed.')
        with patch('fireatlas.assistant.AssistantService',return_value=self.service),patch.dict('os.environ',{}):
            app=create_app(self.database,'http://testserver')
            with TestClient(app) as client:
                self.assertEqual(client.post('/api/data/sync',json={}).status_code,403)
                headers={'Origin':'http://testserver'}
                self.assertEqual(client.post('/api/assistant/sessions',json={'context':self.cfg},headers=headers).status_code,200)
                client.post('/api/assistant/views',json={'context':self.cfg,'view':{'instance':'gateway-tab'}},headers=headers)
                run=client.post('/api/assistant/runs',json={'context':self.cfg,'view':{'instance':'gateway-tab'},'operation':'method','nonce':'gateway-run'},headers=headers).json()
                with client.stream('GET',f"/api/assistant/runs/{run['id']}/stream") as response:
                    events=[json.loads(line[6:]) for line in response.iter_lines() if line.startswith('data: ')]
                self.assertEqual(events[0]['type'],'RUN_STARTED')
                self.assertEqual(events[-1]['type'],'RUN_FINISHED')
                self.assertTrue(any(e['type']=='STEP_FINISHED' for e in events))
                self.assertNotIn(self.owner,json.dumps(events))
                self.assertEqual(client.get('/assistant.html').status_code,200)

    def test_openai_responses_transport_tool_claim_and_image_contract(self):
        try:
            import httpx
            from openai import AsyncOpenAI
        except ImportError:self.skipTest('Optional OpenAI dependencies are not installed.')
        calls=[]
        def transport(request):
            body=json.loads(request.content);calls.append(body)
            self.assertEqual(request.url.path,'/v1/responses')
            self.assertFalse(body['store']);self.assertEqual(body['max_output_tokens'],1200)
            if len(calls)==1:
                part={'type':'function_call','id':'fc_1','call_id':'call_1','name':'investigate','arguments':json.dumps({'operation':'research'})}
            else:
                returned=next(v for v in body['input'] if v.get('type')=='function_call_output')
                evidence=json.loads(returned['output'])
                output=next(t['name'] for t in body['tools'] if t['name'] not in {'investigate','saved_evidence','annotate_evidence','resolve_study_place','inspect_selection','annotate_figure'})
                part={'type':'function_call','id':'fc_2','call_id':'call_2','name':output,'arguments':json.dumps({'title':'Checked overlap','interpretation':'The calculation preserves both sensor sources.','claims':[{'result_id':evidence['id'],'path':'/overlap/totals/union','label':'union'}],'actions':[]})}
            return httpx.Response(200,json={'id':'resp_'+str(len(calls)),'object':'response','created_at':1,'model':'gpt-6-luna','status':'completed','output':[part],'usage':{'input_tokens':100,'output_tokens':40,'total_tokens':140}})
        client=AsyncOpenAI(api_key='not-real',max_retries=0,http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)))
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.5'}),patch('openai.AsyncOpenAI',return_value=client):
            answer=run_agent(self.service,self.owner,'Inspect the attached figure',self.cfg,{'instance':'tab-one'},threading.Event(),time.monotonic()+30,lambda _:None,images=[(b'large test figure'*20000,'image/png')])
        self.assertEqual(answer['claims'][0]['value'],4)
        self.assertEqual(len(calls),2)
        self.assertTrue(any(v.get('type')=='input_image' for i in calls[0]['input'] for v in i.get('content',[]) if isinstance(v,dict)))

    def test_free_catalog_rejects_paid_variants_and_costs(self):
        from fireatlas.assistant.free_models import free_entry,verified_routes
        entry={'id':'test/model:free','pricing':{'prompt':'0','completion':'0'},'supported_parameters':['tools','tool_choice'],'architecture':{'input_modalities':['text','image']}}
        self.assertTrue(free_entry(entry,True))
        for change in ({'id':'test/model'},{'pricing':{'prompt':'0','completion':'0','request':'0.01'}},{'supported_parameters':['tools']},{'pricing':{'prompt':'nan','completion':'0'}}):
            self.assertFalse(free_entry({**entry,**change}))
        with self.assertRaises(ValueError):verified_routes('paid/model')

    def test_openrouter_free_transport_claims_and_zero_cost(self):
        import httpx
        from openai import AsyncOpenAI
        from fireatlas.assistant.free_models import TEXT_MODEL,VISION_MODEL
        calls=[]
        def transport(request):
            body=json.loads(request.content);calls.append(body)
            self.assertEqual(request.url.path,'/api/v1/chat/completions')
            self.assertEqual(body['provider']['max_price'],{'prompt':0,'completion':0})
            self.assertTrue(body['provider']['require_parameters'])
            self.assertEqual(body['plugins'],[])
            self.assertTrue(all(m.endswith(':free') for m in body['models']))
            if len(calls)==1:name,args='investigate',{'operation':'research'}
            else:
                evidence=json.loads(next(m['content'] for m in body['messages'] if m['role']=='tool'))
                name=next(t['function']['name'] for t in body['tools'] if t['function']['name'] not in {'investigate','saved_evidence','annotate_evidence','resolve_study_place','inspect_selection','annotate_figure'})
                args={'title':'Checked overlap','interpretation':'Sources stay separate.','claims':[{'result_id':evidence['id'],'path':'/overlap/totals/union','label':'union'}]}
            return httpx.Response(200,json={'id':'free_'+str(len(calls)),'provider':'test-provider','object':'chat.completion','created':1,'model':VISION_MODEL,'choices':[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[{'id':'call_'+str(len(calls)),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}}],'usage':{'prompt_tokens':100,'completion_tokens':40,'total_tokens':140,'cost':0}})
        client=AsyncOpenAI(api_key='not-real',base_url='https://openrouter.ai/api/v1',max_retries=0,http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)))
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'openrouter','OPENROUTER_API_KEY':'not-real'}),patch('fireatlas.assistant.free_models.verified_routes',return_value=[VISION_MODEL]),patch('openai.AsyncOpenAI',return_value=client):
            answer=run_agent(self.service,self.owner,'Read this figure',self.cfg,{'instance':'tab-one'},threading.Event(),time.monotonic()+30,lambda _:None,images=[(b'fake figure','image/png')])
        self.assertEqual(answer['claims'][0]['value'],4)
        self.assertEqual(answer['model'],VISION_MODEL)
        self.assertTrue(answer['free_only'])
        self.assertEqual(self.service.store.budget(self.owner)['used_or_reserved'],0)
        self.assertTrue(all(r['body']['reported_cost']==0 for r in self.service.store.artifacts(self.owner,'inference_receipt')))
        self.assertTrue(any(c.get('type')=='image_url' for m in calls[0]['messages'] if isinstance(m.get('content'),list) for c in m['content']))
        from fireatlas.assistant.voice import speech
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'openrouter','OPENROUTER_API_KEY':'not-real','OPENAI_API_KEY':'not-real'}),self.assertRaises(ValueError):speech(self.service,self.owner,'synthesize',{})

    def test_aiand_routes_verify_capabilities_prices_and_reasoning(self):
        import hashlib
        from fireatlas.assistant import aiand
        def entry(name, vision=True):
            return {'id':name,'currency':'usd','input_per_1m':'0.15','output_per_1m':'0.5',
                    'capabilities':['tool_calling']+(['vision'] if vision else []),'reasoning_efforts':['none','low','high']}
        catalog={name:entry(name,name!=aiand.DEEP_MODEL) for name in aiand.routes().values()}
        with patch.dict('os.environ',{'AIAND_API_KEY':'test-private'}),patch.object(aiand,'_cache',catalog),patch.object(aiand,'_stamp',hashlib.sha256(b'test-private').digest()),patch.object(aiand,'_updated',time.monotonic()):
            self.assertEqual(aiand.verified_model()['model'],aiand.EFFICIENT_MODEL)
            self.assertEqual(aiand.verified_model('deep')['model'],aiand.DEEP_MODEL)
            self.assertEqual(aiand.verified_model('deep',True)['model'],aiand.DEEP_VISION_MODEL)
            self.assertEqual(aiand.verified_model('efficient',True)['model'],aiand.EFFICIENT_VISION_MODEL)
            for invalid in ({'currency':'eur'},{'input_per_1m':'nan'},{'output_per_1m':'6'},{'input_per_1m':'0'},{'capabilities':['vision']},{'capabilities':['tool_calling']},{'reasoning_efforts':['max']}):
                with patch.dict(catalog,{aiand.EFFICIENT_VISION_MODEL:{**entry(aiand.EFFICIENT_VISION_MODEL),**invalid}}),self.assertRaises(ValueError):aiand.verified_model(vision=True)
            with self.assertRaises(ValueError):aiand.verified_model('unlimited')
        import httpx
        with patch.dict('os.environ',{'AIAND_API_KEY':'test-private'}),patch.object(aiand,'_cache',None),patch('httpx.get',side_effect=httpx.ConnectError('private provider error')):
            with self.assertRaisesRegex(ValueError,'No inference was sent'):aiand.verified_model()

    def test_aiand_chat_tools_vision_reasoning_and_cost_receipts(self):
        import httpx
        from openai import AsyncOpenAI
        from fireatlas.assistant.aiand import BASE_URL,EFFICIENT_MODEL,DEEP_MODEL,DEEP_VISION_MODEL
        for depth,images,model in [('efficient',None,EFFICIENT_MODEL),('efficient',[(b'test fixture image','image/png')],DEEP_VISION_MODEL),('deep',None,DEEP_MODEL),('deep',[(b'test fixture image','image/png')],DEEP_VISION_MODEL)]:
            calls=[]
            def transport(request):
                body=json.loads(request.content);calls.append(body)
                self.assertEqual(str(request.url),BASE_URL+'/chat/completions')
                self.assertEqual(body['model'],model)
                self.assertEqual(body['reasoning_effort'],'high' if depth=='deep' else 'none' if images else 'low')
                self.assertEqual(body['max_completion_tokens'],2400 if depth=='deep' else 1600)
                self.assertFalse(body['store']);self.assertFalse(body['parallel_tool_calls'])
                if len(calls)==1:name,args='investigate',{'operation':'research'}
                else:
                    evidence=json.loads(next(m['content'] for m in body['messages'] if m['role']=='tool'))
                    name=next(t['function']['name'] for t in body['tools'] if t['function']['name'] not in {'investigate','saved_evidence','annotate_evidence','resolve_study_place','inspect_selection','annotate_figure'})
                    args={'title':'Checked overlap','interpretation':'Sources stay separate.','claims':[{'result_id':evidence['id'],'path':'/overlap/totals/union','label':'Distinct union'}]}
                return httpx.Response(200,json={'id':'paid_'+str(len(calls)),'object':'chat.completion','created':1,'model':model,'choices':[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[{'id':'call_'+str(len(calls)),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}}],'usage':{'prompt_tokens':11000 if images else 100,'completion_tokens':40,'total_tokens':11040 if images else 140}})
            config={'model':model,'input_price':0.15,'output_price':0.5,'reasoning_effort':'high' if depth=='deep' else 'none' if images else 'low','max_tokens':2400 if depth=='deep' else 1600,'analysis_depth':depth,'vision':bool(images),'price_basis':'test catalog'}
            client=AsyncOpenAI(api_key='test-private',base_url=BASE_URL,max_retries=0,http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)))
            with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'aiand','AIAND_API_KEY':'test-private'}),patch('fireatlas.assistant.aiand.verified_model',return_value=config) as verify,patch('openai.AsyncOpenAI',return_value=client):
                caps=self.service.capabilities();self.assertEqual(caps['analysis_modes'],['efficient','deep']);self.assertNotIn('test-private',json.dumps(caps))
                answer=run_agent(self.service,self.owner,'Compare these sources',self.cfg,{'instance':'tab-one','analysis_depth':depth},threading.Event(),time.monotonic()+30,lambda _:None,images=images)
            verify.assert_called_once_with(depth,bool(images))
            self.assertEqual(answer['claims'][0]['value'],4)
            self.assertEqual(answer['analysis_depth'],depth)
            self.assertEqual(answer['estimated_cost_usd'],0.00334 if images else 0.00007)
            self.assertEqual(answer['inference_calls'],2)
            self.assertFalse(answer['free_only'])
            if images:self.assertTrue(any(c.get('type')=='image_url' for m in calls[0]['messages'] if isinstance(m.get('content'),list) for c in m['content']))
        receipts=self.service.store.artifacts(self.owner,'inference_receipt')
        self.assertEqual(len(receipts),8)
        self.assertEqual(self.service.store.budget(self.owner)['used_or_reserved'],0.00682)

if __name__=='__main__':unittest.main()
