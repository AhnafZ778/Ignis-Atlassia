"""Scientific-view checks use isolated synthetic archives, never live-provider proof."""
import threading
import time
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch
from tests.studio_support import StudioCase
from fireatlas.assistant.board_views import choose_archived_heatmap, view_context
from fireatlas.assistant.contracts import normalize_context
from fireatlas.assistant.service import AssistantService
from fireatlas.studio.assistant import StudioAssistant
from fireatlas.studio.errors import NotFound, StudioError
from fireatlas.studio.board_views import render

class ScopeTests(unittest.TestCase):
    def test_open_choice_uses_a_bounded_california_archive(self):
        scope = choose_archived_heatmap('Show a closeup heatmap of a wildfire that happened in california')
        self.assertEqual(scope['case'], 'park-2024')
        self.assertEqual(scope['day'], '2024-07-25')
        self.assertEqual(scope['bbox'], [-122.0, 39.60, -121.50, 40.00])
        self.assertEqual(scope['source'], 'MODIS_SP')
        self.assertEqual(choose_archived_heatmap('Show any California wildfire heatmap')['bbox'],
                         [-122.0, 39.5, -121.3, 40.5])

    def test_accepts_the_article_and_regional_name_variants(self):
        from fireatlas.assistant.regional_fire import requests_sundarbans_heatmap
        self.assertEqual(choose_archived_heatmap(
            'Show a closeup heatmap of a fire that happened in the California\n')['case'], 'park-2024')
        self.assertTrue(requests_sundarbans_heatmap(
            'Show a closeup heatmap of a fire that happened in the Sundarban'))
        self.assertTrue(requests_sundarbans_heatmap('Show any Sundarbans forest fire heatmap'))
        self.assertFalse(requests_sundarbans_heatmap('Show a fire heatmap in the Sundarbans for 2021'))

    def test_bundle_parses_views_and_scope_independently(self):
        from fireatlas.assistant.board_views import explicit_board_bundle, requested_kinds
        from fireatlas.assistant.place_fire import place_request
        question='Provide heatmap and reading calendar for Rajshahi'
        self.assertEqual(requested_kinds(question),('heatmap','calendar'))
        self.assertEqual(place_request(question),'Rajshahi')
        self.assertEqual(place_request('Show a heatmap for Rajshahi and a reading calendar'),'Rajshahi')
        self.assertEqual(requested_kinds('Show harmonized calendar for Northern California'),('harmonized',))
        self.assertEqual([kind for kind,_ in explicit_board_bundle(
            'Show a heatmap and reading calendar for Park Fire from 2024-07-25 to 2024-07-28')],['heatmap','calendar'])

    def test_firms_bundle_shares_the_same_receipt_across_empty_and_nonempty_days(self):
        from types import SimpleNamespace
        from fireatlas.assistant.place_fire import place_answer
        question='Provide heatmap and reading calendar for Rajshahi from 2024-05-04 to 2024-05-06'
        saved=[]
        service=SimpleNamespace(store=SimpleNamespace(artifact=lambda _, kind, receipt: saved.append(receipt) or 'shared'))
        location={'id':1185128,'name':'Rajshahi','country':'Bangladesh','latitude':24.374,'longitude':88.60114}
        body=('latitude,longitude,acq_date,acq_time,bright_ti4,frp\n'
              '24.37,88.60,2024-05-05,0231,310.2,2.5\n')
        with patch('fireatlas.assistant.place_fire.locate',return_value=[location]), patch(
            'fireatlas.assistant.place_fire.firms_key',return_value='test-key'
        ), patch('fireatlas.assistant.firms_history.fetch.availability',return_value=[{
            'data_id':'VIIRS_NOAA20_SP','min_date':'2018-04-01','max_date':'2024-12-31',
        }]), patch('fireatlas.assistant.place_fire.fetch._download',return_value=body) as download:
            answer=place_answer(service,'owner','Rajshahi',question,threading.Event(),time.monotonic()+5)
        self.assertEqual(download.call_count,1)
        self.assertEqual([view['result_id'] for view in answer['data_views']],['shared','shared'])
        self.assertEqual([view['kind'] for view in answer['data_views']],['firms-region-heatmap','firms-region-calendar'])
        snapshot={'scope':saved[0]['context'],'snapshot_sha256':'hash'}
        calendar=render(snapshot,saved[0],'firms-region-calendar')
        heatmap=render(snapshot,saved[0],'firms-region-heatmap')
        self.assertEqual([item['returned'] for item in calendar['visual']['days']],[0,1,0])
        self.assertEqual(heatmap['visual']['total'],calendar['visual']['total'])
        self.assertIn('05-05 · 1',answer['summary'])
        ET.fromstring(calendar['svg'])

        from fireatlas.assistant.board_views import selected_firms_answer, selected_reading_requested
        self.assertTrue(selected_reading_requested('Show a reading calendar from this heatmap.'))
        self.assertFalse(selected_reading_requested('Show the 2024-05-04 calendar from this heatmap.'))
        self.assertFalse(selected_reading_requested('Show a reading calendar from this heatmap for Dhaka.'))
        with patch('fireatlas.assistant.place_fire.fetch._download') as download, patch.object(
            service.store, 'get_artifact', return_value={'body': saved[0]}, create=True,
        ):
            selection={'frozen_evidence_ids':['selected'], 'frozen_evidence_refs':{'selected':{'snapshotId':'original'}}}
            followup=selected_firms_answer(service.store,'owner',selection,('calendar',))
            comparison=selected_firms_answer(service.store,'owner',selection,('satellites',))
        download.assert_not_called()
        self.assertEqual(followup['data_views'],[{'kind':'firms-region-calendar','result_id':'selected','referenceUrl':saved[0]['payload']['reference']['url']}])
        self.assertIn('05-05 · 1',followup['summary'])
        self.assertIn('at least two products',comparison['summary'])
        self.assertFalse(comparison.get('data_views'))

    def test_year_scope_preserves_all_days_and_each_firms_window(self):
        from datetime import date
        from types import SimpleNamespace
        from fireatlas.assistant.firms_history import historical_period
        from fireatlas.assistant.place_fire import place_answer, place_request
        question='Show a heatmap and reading calendar for Dinajpur of 2024.'
        self.assertEqual(place_request(question),'Dinajpur')
        self.assertEqual(place_request('Show historical readings for Dinajpur in Bangladesh in March 2024.'),'Dinajpur, Bangladesh')
        self.assertEqual(historical_period('March 2024',date(2026,11,10)),(date(2024,3,1),date(2024,3,31)))
        saved=[]
        service=SimpleNamespace(store=SimpleNamespace(artifact=lambda _, kind, receipt: saved.append(receipt) or 'year'))
        location={'id':1,'name':'Dinajpur','country':'Bangladesh','latitude':25.6,'longitude':88.6}
        availability=[{'data_id':'VIIRS_NOAA20_SP','min_date':'2018-04-01','max_date':'2024-12-31'}]
        header='latitude,longitude,acq_date,acq_time,bright_ti4,frp\n'
        def area(url,label,**kwargs):
            source,_,span,start=url.split('/')[-4:]
            self.assertEqual(source,'VIIRS_NOAA20_SP')
            self.assertIn(int(span),range(1,6))
            return header+('25.6,88.6,2024-02-29,1330,312,2.0\n' if start=='2024-02-25' else '')
        with patch('fireatlas.assistant.place_fire.locate',return_value=[location]), patch(
            'fireatlas.assistant.place_fire.firms_key',return_value='test-key'
        ), patch('fireatlas.assistant.firms_history.fetch.availability',return_value=availability), patch(
            'fireatlas.assistant.firms_history.fetch._download',side_effect=area
        ) as download:
            answer=place_answer(service,'owner','Dinajpur',question,threading.Event(),time.monotonic()+10)
        self.assertEqual(download.call_count,74)
        receipt=saved[0]
        check=receipt['payload']['checks'][0]
        self.assertEqual(check['source_windows'][-1]['end'],'2024-12-31')
        self.assertEqual(check['source_windows'][0]['start'],'2024-01-01')
        snapshot={'scope':receipt['context'],'snapshot_sha256':'hash'}
        self.assertEqual({view['result_id'] for view in answer['data_views']},{'year'})
        calendar=render(snapshot,receipt,'firms-region-calendar')
        self.assertEqual(len(calendar['visual']['days']),366)
        self.assertEqual(calendar['visual']['total'],1)
        self.assertEqual(calendar['visual']['days'][59],{'date':'2024-02-29','returned':1})
        self.assertIn('2024-02-29 UTC',calendar['svg'])
        self.assertNotIn('fill="transparent"',calendar['svg'])
        ET.fromstring(calendar['svg'])

    def test_all_history_catalog_and_partial_archive_dates(self):
        from datetime import date
        from fireatlas.assistant.firms_country import PRODUCTS
        from fireatlas.assistant.firms_history import plan_history
        from fireatlas.assistant.board_views import firms_days
        available=[{'data_id':'MODIS_SP','min_date':'2000-11-01','max_date':'2026-08-31'}]
        with patch('fireatlas.assistant.firms_history.fetch.availability',return_value=available):
            _,catalog=plan_history('Dinajpur, Bangladesh',('readings',),'all',(),PRODUCTS)
            plans,unused=plan_history('Dinajpur',('calendar',),(date(2000,1,1),date(2000,12,31)),(),PRODUCTS)
        self.assertEqual(len(catalog['view_options']),27)
        self.assertIn('heatmap and reading calendar and reading table',catalog['view_options'][-1]['question'])
        self.assertIsNone(unused)
        source,lo,hi=plans[0]
        days=firms_days({'records':[],'product':source,'checks':[{'product':source,'available_start':str(lo),'available_end':str(hi)}]},
                        {'start':'2000-10-31','end':'2000-11-01'})
        self.assertEqual([item['returned'] for item in days],[None,0])

    def test_area_heat_and_month_calendar_share_the_site_grid(self):
        from datetime import date
        from fireatlas.assistant.board_views import area_reading_views
        from fireatlas.assistant.firms_history import calendar_default
        from fireatlas.studio.heat import prepare_area
        scope={'bbox':[90.2,23.6,90.6,24.0],'start':'2024-04-01','end':'2024-04-30'}
        row={'longitude':90.4,'latitude':23.8,'acquisition_utc':'2024-04-04T01:00+00:00'}
        payload={'title':'Dhaka','sensor':'NOAA-20 VIIRS','product':'VIIRS_NOAA20_SP',
                 'checks':[{'product':'VIIRS_NOAA20_SP'}],'records':[row,{**row,'acquisition_utc':'2024-04-04T03:00+00:00'}]}
        receipt={'operation':'firms_region','payload':payload}
        snapshot={'scope':scope,'snapshot_sha256':'snapshot','receipt_sha256':'receipt','release_id':'source'}
        heat=prepare_area(snapshot,receipt)
        self.assertEqual((heat['count'],heat['detections'],heat['sigma_km']),(1,2,1))
        self.assertEqual(heat['interval'],{'start':'2024-04-01','end':'2024-04-30'})
        calendar=render(snapshot,receipt,'firms-region-calendar')
        self.assertEqual(len(calendar['visual']['days']),30)
        self.assertEqual(calendar['visual']['days'][3]['returned'],2)
        self.assertEqual(calendar['visual']['cell_days'][3]['value'],1)
        self.assertIn('April 2024 UTC',calendar['svg'])
        self.assertIn('Monday',calendar['svg'])
        self.assertIn('2 det.',calendar['svg'])
        self.assertEqual(area_reading_views('Provide heat map and reading for Dhaka',('heatmap','readings')),
                         ('heatmap','calendar'))
        self.assertEqual(area_reading_views('Show raw readings for Dhaka',('readings',)),('readings',))
        self.assertEqual(calendar_default('Show reading calendar for Dhaka',('calendar',),date(2026,11,10)),
                         (date(2026,11,1),date(2026,11,10)))

    def test_peak_month_prompt_variations(self):
        from datetime import date
        from fireatlas.assistant.firms_history import peak_metric, peak_search_period, requests_peak_month
        from fireatlas.assistant.place_fire import peak_calendar_question, place_request
        from fireatlas.assistant.regional_fire import sundarbans_scope
        today=date(2026,11,10)
        prompts={
            "Show heatmap and calendar reading of Sundarban during it's peak fire activity season last year":'Sundarban',
            'Show calendar for the busiest month in Dhaka in 2025':'Dhaka',
            'Show heatmap for Sundarbans, Bangladesh in its peak wildfire season in 2025':'Sundarbans, Bangladesh',
            'Show heatmap of Dinajpur during the month with the most detections last year':'Dinajpur',
            'Show calendar for peak fire month in Bangladesh in 2025':'Bangladesh',
            'Show heatmap and readings for the most active fire month in Rajshahi last year':'Rajshahi',
            'When was the peak fire activity in Sundarbans last year?':'Sundarbans',
            'Which month had the most detections in Sundarbans in 2025?':'Sundarbans',
            'When was fire activity highest in Dhaka last year?':'Dhaka',
            "When was 2025's busiest month in Sundarbans?":'Sundarbans',
        }
        for prompt, place in prompts.items():
            with self.subTest(prompt=prompt):
                self.assertTrue(requests_peak_month(prompt))
                self.assertEqual(peak_search_period(prompt,today),(date(2025,1,1),date(2025,12,31)))
                self.assertEqual(place_request(peak_calendar_question(prompt)),place)
        self.assertEqual(sundarbans_scope('Sundarban')[1],[88.03222,21.5,89.91667,22.5])
        self.assertEqual(sundarbans_scope('Sundarbans, India')[1][0],88.03222)
        self.assertIsNone(sundarbans_scope('Sundarban Road'))
        self.assertFalse(requests_peak_month('Show a heatmap of peak temperatures for Dhaka'))
        self.assertEqual(peak_metric('month with the highest number of detections'),'detections')
        with self.assertRaisesRegex(ValueError,'complete UTC month'):
            peak_search_period('Peak month from 2025-01-04 to 2025-01-23',today)
        self.assertEqual(peak_search_period('Peak month from 2025-01-04 to 2025-03-23',today),
                         (date(2025,2,1),date(2025,2,28)))

    def test_peak_month_ranks_calendar_cells_or_explicit_detections(self):
        from datetime import date
        from fireatlas.assistant.firms_history import narrow_to_peak_month
        first,last=date(2025,1,1),date(2025,3,31)
        rows=[{'acquisition_utc':d+'T00:00+00:00','longitude':90.4,'latitude':23.8}
              for d in ['2025-01-01']*4+['2025-02-01','2025-02-02','2025-03-01','2025-03-02']]
        check={'sensor':'NOAA-20 VIIRS','records':rows,'source_windows':[{'sha256':'archive-window'}]}
        (selected,start,end,evidence,note),clarification=narrow_to_peak_month([check],first,last)
        self.assertIsNone(clarification)
        self.assertEqual((start,end),(date(2025,2,1),date(2025,2,28)))
        self.assertEqual(evidence['tied_months'],['2025-02','2025-03'])
        self.assertEqual(selected['detections'],2)
        self.assertEqual(selected['source_windows'],check['source_windows'])
        self.assertIn('tied',note)
        (_,start,_,evidence,_),_=narrow_to_peak_month([check],first,last,'detections')
        self.assertEqual(start,first)
        self.assertEqual(evidence['metric'],'returned detections')
        peak,clarification=narrow_to_peak_month([{**check,'records':[]}],first,last)
        self.assertIsNone(peak)
        self.assertIn('tied at zero',clarification['summary'])

    def test_board_area_prompt_variations(self):
        from fireatlas.assistant.board_views import requested_kinds, requests_heatmap_catalog
        from fireatlas.assistant.place_fire import (conflicting_places, missing_place, place_followup,
                                                    place_followup_from_history, place_request)
        for opening in ('Provide', 'Could you pull', 'I need', 'Show me'):
            for join in ('and', '+', '&', 'plus'):
                for preposition in ('for', 'in', 'near', 'around', 'of'):
                    prompt=f'{opening} heat map {join} reading {preposition} Dhaka'
                    with self.subTest(prompt=prompt):
                        self.assertEqual(requested_kinds(prompt),('heatmap','readings'))
                        self.assertEqual(place_request(prompt),'Dhaka')
                        self.assertFalse(requests_heatmap_catalog(prompt))
        variations={
            'Dhaka — heatmap + readings':'Dhaka',
            'heat map + readings: Dhaka':'Dhaka',
            'For Dhaka, could you pull me a heat map & readings?':'Dhaka',
            'For Dacca, could you pull me a heat map & reading for yesterday?':'Dacca',
            'For Dhaka, Bangladesh, show me a heatmap for yesterday':'Dhaka, Bangladesh',
            'heatmap Dhaka':'Dhaka',
            'Dhaka heatmap':'Dhaka',
            'heatmapp + raedings for Dhaka':'Dhaka',
            'What are the readings for Dhaka?':'Dhaka',
            'Which heatmaps are available for Dhaka?':'Dhaka',
            'heat map for Dhaka for yesterday':'Dhaka',
            'calender for Dhaka last month':'Dhaka',
            '2024 Dhaka heatmap':'Dhaka',
            'heatmap for Dhaka on 2024/07/25':'Dhaka',
            'heatmap for Dhaka Bangladesh':'Dhaka, Bangladesh',
            'heatmap for Dhaka in Bangladesh':'Dhaka, Bangladesh',
            'heatmap for Dhaka, not Rajshahi':'Dhaka',
            'heatmap for Trinidad and Tobago':'Trinidad and Tobago',
        }
        for prompt,place in variations.items():
            with self.subTest(prompt=prompt):
                self.assertEqual(place_request(prompt),place)
        self.assertTrue(conflicting_places('Show heatmap for Dhaka and calendar for Rajshahi'))
        self.assertTrue(conflicting_places('Show Dhaka heatmap and Rajshahi calendar'))
        self.assertFalse(conflicting_places('Show heatmap for Dhaka and calendar for Dhaka'))
        self.assertTrue(missing_place('Show a heatmap, please'))
        self.assertEqual(requested_kinds('Show heatmap for Dhaka, no calendar'),('heatmap',))
        self.assertEqual(requested_kinds('Do not show heatmap for Dhaka'),())
        self.assertEqual(requested_kinds("Don't show a heatmap, just readings for Dhaka"),('readings',))
        self.assertEqual(requested_kinds("Heatmap for Dhaka, don't include a calendar"),('heatmap',))
        self.assertEqual(requested_kinds('Show a reading of the attached CSV'),())
        for prompt in ('What is a heatmap?', 'Is NOAA-20 better than MODIS for heatmaps?',
                       'Show a reading of the attached CSV','Explain this heatmap'):
            self.assertIsNone(place_request(prompt))
        previous='Show a heatmap for Rajshahi on 2024-07-25 using MODIS'
        self.assertEqual(place_followup('Same for Dhaka?',previous),
                         'Show a heatmap for Dhaka on 2024-07-25 using MODIS')
        self.assertEqual(place_followup('2023?',previous),
                         'Show a heatmap for Rajshahi on 2023 using MODIS Terra/Aqua')
        turns=[{'question':previous},{'question':'Same for Dhaka?'}]
        self.assertEqual(place_followup_from_history('2024-07-26?',turns),
                         'Show a heatmap for Dhaka on 2024-07-26 using MODIS Terra/Aqua')

    def test_named_place_and_place_only_followup(self):
        from fireatlas.assistant.place_fire import place_followup, place_request
        self.assertEqual(place_request('Show a Rajshahi heatmap'),'Rajshahi')
        self.assertEqual(place_request('Show thermal readings in Rajshahi, Bangladesh for the last 3 days'),'Rajshahi, Bangladesh')
        self.assertEqual(place_request('Show a closeup heatmap of a fire that happened in the Rajshahi'),'Rajshahi')
        self.assertEqual(place_request('Show a heatmap for Rajshahi on 2024-05-04'),'Rajshahi')
        self.assertEqual(place_followup('Rajshahi','Provide heatmap for Bangladesh'),'Show a heatmap for Rajshahi')
        self.assertIsNone(place_followup('How does it work','Provide heatmap for Bangladesh'))
        self.assertIsNone(place_followup('Rajshahi','Explain the result'))

    def test_historical_region_zero_results_keep_a_source_linked_map(self):
        from types import SimpleNamespace
        from fireatlas.assistant.regional_fire import sundarbans_answer
        receipts=[]
        service=SimpleNamespace(store=SimpleNamespace(artifact=lambda _, kind, receipt: receipts.append(receipt) or 'saved'))
        def empty_csv(url, label, **kwargs):
            band='brightness' if '/MODIS_SP/' in url else 'bright_ti4'
            return f'latitude,longitude,acq_date,acq_time,{band},frp\n'
        with patch('fireatlas.assistant.regional_fire.firms_key', return_value='test-key'), patch(
            'fireatlas.assistant.regional_fire.fetch._download', side_effect=empty_csv
        ) as download:
            answer=sundarbans_answer(service, 'owner', threading.Event(), time.monotonic()+5)
        self.assertEqual(download.call_count, 4)
        self.assertEqual([item['value'] for item in answer['claims']], [0,0,0,0])
        self.assertEqual(answer['data_views'][0]['referenceUrl'], receipts[0]['payload']['incident']['url'])
        preview=render({'scope':receipts[0]['context'],'snapshot_sha256':'hash'}, receipts[0], 'firms-region-heatmap')
        self.assertEqual(preview['visual']['total'], 0)
        self.assertEqual(preview['visual']['cells'], [])
        self.assertIn('Amrabunia locality', preview['svg'])
        ET.fromstring(preview['svg'])

    def test_open_choice_does_not_replace_a_specific_scope(self):
        for question in (
            'Show a close-up heatmap of Park Fire in California',
            'Show a heatmap of a wildfire in Southern California',
            'Show a heatmap of a wildfire in California in 2018',
            'Show a California wildfire heatmap near Los Angeles',
            'Show a wildfire heatmap in Bangladesh',
        ):
            with self.subTest(question=question):
                self.assertIsNone(choose_archived_heatmap(question))

    def test_empty_board_requires_explicit_requested_scope(self):
        with self.assertRaises(ValueError):view_context({},None,'Show a heatmap',True)
        with self.assertRaises(ValueError):view_context({}, {'case':'park-2024'}, 'Show a heatmap',True)
        cfg=view_context({}, {'case':'park-2024','day':'2024-07-27'}, 'Show Park Fire',True)
        self.assertEqual(cfg['bbox'],[-122,39.5,-121.3,40.5])
        self.assertEqual(cfg['day'],'2024-07-27')

    def test_missing_satellite_is_not_drawn_as_zero(self):
        source={'scope':{'bbox':[0,0,1,1],'start':'2024-07-27','end':'2024-07-27'},'snapshot_sha256':'hash'}
        receipt={'operation':'replay','payload':{'frames':[{'date_utc':'2024-07-27','products':{
            'MODIS_SP':{'detections':0,'state':'complete_export'},
            'VIIRS_SNPP_SP':{'detections':0,'state':'documented_product_gap'}}}]}}
        result=render(source,receipt,'satellites')
        values=result['visual']['values'][0]['sources']
        self.assertEqual(values['MODIS_SP']['value'],0)
        self.assertIsNone(values['VIIRS_SNPP_SP']['value'])
        ET.fromstring(result['svg'])

class ScientificViewTests(StudioCase):
    def setUp(self):
        super().setUp()
        self.assistant=AssistantService(self.database,self.root/'assistant/workspace.sqlite3')
        self.addCleanup(self.assistant.close)
        self.service.assistant=self.assistant
        self.bridge=StudioAssistant(self.service,self.assistant)
        self.assistant.studio_bridge=self.bridge
        self.doc=self.board()
        self.session=self.service.assistant_owner(self.owner)
        self.assistant.store.artifact(self.session,'studio_access',{'principal':self.owner,'document_id':self.doc['id']})

    def save_run(self,kind,result):
        run,_=self.assistant.store.create_run(self.session,'view-'+kind,{})
        self.service.store.artifact(self.owner,'assistant_run',{'document_id':self.doc['id'],'run_id':run,
            'owner':self.session,'board_revision':self.doc['revision'],'run_nonce':'view-'+kind})
        self.assistant.store.finish(self.session,run,'completed',{'claims':[],'data_views':[{'kind':kind,'result_id':result['id']}]})
        return run

    def test_view_only_receipts_are_owned_persistent_idempotent_and_renderable(self):
        for kind,operation in [('satellites','replay'),('coordinates','observations'),('calendar','calendar'),('archive','archive_search')]:
            result=self.assistant.science.call(self.session,operation,normalize_context(self.study['context']))
            run=self.save_run(kind,result)
            binding=self.bridge.preserve_claims(self.owner,self.doc['id'],run)['bindings'][result['id']]
            self.assertEqual(binding,self.bridge.preserve_claims(self.owner,self.doc['id'],run)['bindings'][result['id']])
            report=self.service.snapshot_report(self.owner,self.doc['id'],binding['snapshotId'])
            self.assertTrue(report['verification']['verified'])
            preview=self.service.snapshot_preview(self.owner,self.doc['id'],binding['snapshotId'],kind)
            ET.fromstring(preview['svg'])
            self.assertIsNotNone(preview['visual'])
            with self.assertRaises(NotFound):self.bridge.preserve_claims(self.other,self.doc['id'],run)

    def test_portable_note_keeps_its_owned_snapshot_links(self):
        result=self.assistant.science.call(self.session,'observations',normalize_context(self.study['context']))
        run=self.save_run('coordinates',result)
        binding=self.bridge.preserve_claims(self.owner,self.doc['id'],run)['bindings'][result['id']]
        ref={key:binding[key] for key in ('documentId','snapshotId','snapshotHash')}
        doc=self.service.get_document(self.owner,self.doc['id'])
        changes=[{'kind':'element','id':'note','position':0,'value':{'id':'note','type':'rectangle','x':0,'y':0,'width':440,'height':200,
            'customData':{'fireatlas':{'documentId':doc['id'],'kind':'assistant-analysis-note','sourceBindings':[ref]}}}}]
        doc=self.service.transact(self.owner,doc['id'],{'base_revision':doc['revision'],'ops':[{'op':'patch_whiteboard','changes':changes}]})
        with patch('fireatlas.studio.portability.StorageBudget.check',return_value={}):
            job=self.service.portability.submit(self.owner,doc['id'],{'format':'native','revision':doc['revision']},background=False)
        self.assertEqual(job['status'],'completed',job)
        path,_=self.service.portability.download(self.owner,job['id'])
        restored=self.service.portability.restore(self.other,path)['document']
        drawing=self.service.store.whiteboard(self.other,restored['id'])
        note=drawing['elements'][0]['customData']['fireatlas']
        saved=note['sourceBindings'][0]
        self.assertEqual(saved['documentId'],restored['id'])
        self.assertNotEqual(saved['snapshotId'],binding['snapshotId'])
        self.assertEqual(saved['snapshotHash'],restored['snapshots'][saved['snapshotId']]['snapshot_sha256'])
        self.assertTrue(self.service.snapshot_report(self.other,restored['id'],saved['snapshotId'])['verification']['verified'])

    def test_calendar_model_preview_contains_the_requested_days_not_january(self):
        from fireatlas.assistant.agent import evidence_preview
        cfg=normalize_context({'case':'park-2024','start':'2024-07-25','end':'2024-07-28','source':'MODIS_SP','series':'modis'})
        result=self.assistant.science.call(self.session,'calendar',cfg)
        preview=evidence_preview(result,cfg)
        self.assertEqual([row['date_utc'] for row in preview['payload']['daily']],['2024-07-25','2024-07-26','2024-07-27','2024-07-28'])
        self.assertNotIn('monthly',preview['payload'])
        self.assertFalse(preview['payload']['preview_truncated'])
        for claim in preview['claim_candidates']:
            index=int(claim['path'].split('/')[2])
            self.assertTrue(result['payload']['daily'][index]['date_utc'].startswith('2024-07-'))

    def test_selected_frame_candidates_include_human_readable_count_labels(self):
        from fireatlas.assistant.agent import evidence_preview
        result={'id':'synthetic','operation':'replay','method':{'id':'fixture','unit':'cells'},'release_id':'fixture',
                'payload':{'frames':[{'date_utc':'2024-07-27','joint_cell_days':2,'products':{
                    'MODIS_SP':{'detections':3,'cell_days':2,'state':'complete_export'}}}]}}
        preview=evidence_preview(result,{'day':'2024-07-27'})
        numeric=[claim for claim in preview['selected_frame_claims'] if isinstance(claim['value'],int)]
        self.assertTrue(all(claim.get('label') for claim in numeric))
        self.assertEqual(next(claim['value'] for claim in numeric if claim['path'].endswith('/detections')),3)

    def test_blank_sensor_cannot_shift_the_following_values_in_model_context(self):
        from fireatlas.assistant.agent import evidence_preview
        result={'id':'test','operation':'csv_table','method':{'id':'imported-csv-v1','unit':'reported value'},'release_id':'fixture',
            'payload':{'name':'synthetic-test.csv','columns':['UTC date','MODIS_SP','VIIRS_SNPP_SP','VIIRS_NOAA20_SP','VIIRS_NOAA21_SP'],
                       'offset':0,'total_rows':1,'rows':[['2024-07-27','348','','1495','2073']]}}
        preview=evidence_preview(result,{},'Explain July 27.')
        row=preview['payload']['records'][0]
        self.assertEqual(row['VIIRS S-NPP'],'unavailable')
        self.assertEqual(result['payload']['rows'][0][2],'')
        self.assertEqual(row['VIIRS NOAA-20'],'1495')
        self.assertEqual(row['VIIRS NOAA-21'],'2073')
        self.assertNotIn('rows',preview['payload'])

    def test_healthy_export_metadata_is_kept_when_the_question_asks_for_it(self):
        from fireatlas.assistant.agent import evidence_preview
        result={'id':'test','operation':'csv_table','method':{'id':'imported-csv-v1','unit':'reported value'},'release_id':'fixture',
            'payload':{'name':'synthetic-test.csv','columns':['UTC date','MODIS_SP','MODIS_SP state'],
                       'offset':0,'total_rows':1,'rows':[['2024-07-27','348','complete_export']]}}
        normal=evidence_preview(result,{},'Explain July 27.')
        self.assertNotIn('MODIS status',normal['payload']['records'][0])
        status=evidence_preview(result,{},'Is the export complete on July 27?')
        self.assertEqual(status['payload']['records'][0]['MODIS status'],'complete_export')
        self.assertEqual(result['payload']['rows'][0][-1],'complete_export')

    def test_wrong_view_operation_is_rejected(self):
        result=self.assistant.science.call(self.session,'calendar',normalize_context(self.study['context']))
        run=self.save_run('coordinates',result)
        with self.assertRaises(StudioError):self.bridge.preserve_claims(self.owner,self.doc['id'],run)

    def test_real_model_tool_path_uses_scientific_calculation(self):
        from fireatlas.assistant.agent import run_agent
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('prepare_board_view',{'kind':'calendar','case_id':'park-2024','start':'2024-07-25','end':'2024-07-28','day':'2024-07-27'})])
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Calendar ready','interpretation':'The calendar retains unavailable dates as unknown.'})])
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True,'frozen_evidence_ids':[],'frozen_evidence_refs':{}}}
        env={'FIREATLAS_AI_PROVIDER':'openai','OPENAI_API_KEY':'not-real','FIREATLAS_AI_INPUT_USD_PER_MILLION':'0.1','FIREATLAS_AI_OUTPUT_USD_PER_MILLION':'0.2'}
        with patch.dict('os.environ',env):
            run_agent(self.assistant,self.session,'Show a calendar for Park Fire from 2024-07-25 to 2024-07-28',normalize_context({}),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(view['studio']['requested_board_views'][0]['kind'],'calendar')
        result=self.assistant.store.get_artifact(self.session,view['studio']['requested_board_views'][0]['result_id'],'evidence')['body']
        self.assertEqual(result['operation'],'calendar')
        self.assertEqual(result['context']['case'],'park-2024')

    def test_local_model_uses_real_view_tools_without_paid_reservations(self):
        from fireatlas.assistant.agent import run_agent
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,ToolCallPart,TextPart
        calls=[]
        def respond(messages,info):
            self.assertNotIn('run_studio_recipe',[tool.name for tool in info.function_tools])
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('prepare_board_view',{'kind':'calendar','case_id':'park-2024','start':'2024-07-25','end':'2024-07-28','source':'MODIS_SP'})])
            return ModelResponse(parts=[TextPart('The calendar shows recorded activity. Missing readings remain unknown.')])
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True,'frozen_evidence_ids':[],'frozen_evidence_refs':{}}}
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'local'},clear=True):
            answer=run_agent(self.assistant,self.session,'Show a MODIS calendar for Park Fire from 2024-07-25 to 2024-07-28',normalize_context({}),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(view['studio']['requested_board_views'][0]['kind'],'calendar')
        self.assertEqual(answer['provider'],'local')
        self.assertEqual(answer['estimated_cost_usd'],0)
        self.assertEqual(answer['limitations'],[])
        with self.assistant.store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM reservations').fetchone()[0],0)

    def test_local_natural_concept_answer_is_not_forced_to_query_measurements(self):
        from fireatlas.assistant.agent import run_agent
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,TextPart
        def respond(messages,info):
            return ModelResponse(parts=[TextPart('A sharper sensor can detect smaller hot spots. Compare the same sensor over time before interpreting the count as a change in fire activity.')])
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'local'},clear=True):
            answer=run_agent(self.assistant,self.session,'Explain why sharper sensors can record more thermal readings.',normalize_context({}),{},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['kind'],'AI general explanation')
        self.assertEqual(answer['claims'],[])
        self.assertEqual(answer['provider'],'local')
        self.assertLess(len(answer['summary'].split()),60)

    def test_general_explanation_can_use_numbered_steps_and_sensor_specs(self):
        from fireatlas.assistant.agent import run_agent
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,TextPart
        text='1. MODIS has a nominal 1 km resolution.\n2. VIIRS has a nominal 375 m resolution; compare each sensor consistently.'
        def respond(messages,info):
            self.assertEqual(info.function_tools,[])
            return ModelResponse(parts=[TextPart(text)])
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'local'},clear=True):
            answer=run_agent(self.assistant,self.session,'Explain the difference between MODIS and VIIRS resolution.',normalize_context({}),{},threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['kind'],'AI general explanation')
        self.assertEqual(answer['summary'],text)
        self.assertEqual(answer['claims'],[])

    def test_local_natural_reply_cannot_pretend_a_map_was_created(self):
        from fireatlas.assistant.agent import run_agent
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,TextPart
        def respond(messages,info):return ModelResponse(parts=[TextPart('Your map was created.')])
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True,'frozen_evidence_ids':[],'frozen_evidence_refs':{}}}
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'local'},clear=True):
            answer=run_agent(self.assistant,self.session,'Show a heatmap for this investigation.',normalize_context({}),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['kind'],'Assistant unavailable')
        self.assertFalse(view['studio'].get('requested_board_views'))

    def test_local_natural_figure_reply_can_use_verified_scope_dates(self):
        from fireatlas.assistant.agent import run_agent
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,TextPart,ToolCallPart
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:return ModelResponse(parts=[ToolCallPart('prepare_board_view',{'kind':'calendar'})])
            return ModelResponse(parts=[TextPart('The MODIS calendar for 2024-07-25 to 2024-07-28 is ready. Missing records remain unknown.')])
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True,'frozen_evidence_ids':[],'frozen_evidence_refs':{}}}
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'local'},clear=True):
            answer=run_agent(self.assistant,self.session,'Show a MODIS calendar for Park Fire from 2024-07-25 to 2024-07-28',normalize_context({}),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(answer['kind'],'AI-assisted interpretation')
        self.assertIn('2024-07-25',answer['summary'])
        self.assertEqual(answer['estimated_cost_usd'],0)
        self.assertEqual(len(calls),2)

    def test_local_calendar_remains_available_while_a_csv_is_selected(self):
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,TextPart,ToolCallPart
        table=add(self.service.store,self.owner,self.doc['id'],'synthetic-test.csv',b'date,value\n2024-07-27,5\n')
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True,'frozen_evidence_ids':[],
              'frozen_evidence_refs':{},'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            self.assertEqual(info.function_tools,[])
            return ModelResponse(parts=[TextPart('The MODIS calendar is ready. Compare adjacent days within this sensor.')])
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'local'},clear=True):
            answer=run_agent(self.assistant,self.session,'Show a MODIS calendar for Park Fire from 2024-07-25 to 2024-07-28.',
                             normalize_context({}),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(calls,[1])
        self.assertEqual(view['studio']['requested_board_views'][0]['kind'],'calendar')
        self.assertEqual(answer['kind'],'AI-assisted interpretation')

    def test_explicit_heatmap_uses_one_compact_inference_with_checked_counts(self):
        import json
        from fireatlas.assistant.agent import run_agent
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,TextPart
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True,'frozen_evidence_ids':[],'frozen_evidence_refs':{}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            self.assertEqual(info.function_tools,[])
            contents=[value for message in messages for part in message.parts for value in ([part.content] if isinstance(getattr(part,'content',None),str) else part.content if isinstance(getattr(part,'content',None),list) else []) if isinstance(value,str)]
            prepared=json.loads(next(value for value in contents if value.startswith('{"question"')).split('\n/no_think')[0])
            self.assertNotIn('studio',prepared)
            values=prepared['calculated_views'][0]['source_values']
            self.assertTrue(all('label' in value for value in values))
            return ModelResponse(parts=[TextPart('The heatmap is ready. Compare the original detection locations next.')])
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'local'},clear=True):
            answer=run_agent(self.assistant,self.session,'Show a heatmap of Park Fire on 2024-07-27.',normalize_context({}),view,
                             threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(calls,[1])
        self.assertEqual(answer['kind'],'AI-assisted interpretation')
        self.assertEqual(view['studio']['requested_board_views'][0]['kind'],'heatmap')

    def test_local_explanation_of_saved_heatmap_uses_its_dated_values_in_one_call(self):
        import json
        from fireatlas.assistant.agent import run_agent
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, TextPart
        study=normalize_context(self.study['context'])
        context=normalize_context({**study,'day':study['start']})
        result=self.assistant.science.call(self.session,'replay',context)
        ref={'documentId':self.doc['id'],'snapshotId':'original','snapshotHash':'verified'}
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':False,
              'frozen_evidence_ids':[result['id']],'frozen_evidence_refs':{result['id']:ref}}}
        calls=[]
        reply='Group detections by grid location and acquisition time to see which locations were observed repeatedly.'
        def respond(messages,info):
            self.assertEqual(info.function_tools,[])
            contents=[value for message in messages for part in message.parts for value in ([part.content] if isinstance(getattr(part,'content',None),str) else part.content if isinstance(getattr(part,'content',None),list) else []) if isinstance(value,str)]
            prompt=next(value for value in contents if value.startswith('{"question"'))
            calls.append(json.loads(prompt.split('\n/no_think')[0])['calculated_views'][0])
            return ModelResponse(parts=[TextPart(reply)])
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'local'},clear=True), patch.object(self.assistant.science,'call') as fresh:
            answer=run_agent(self.assistant,self.session,'What stands out in this selected Park Fire heatmap, and what should I check next?',
                             context,view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        fresh.assert_not_called()
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['scope']['day'],context['day'])
        self.assertEqual(calls[0]['kind'],'heatmap')
        self.assertTrue(calls[0]['source_values'])
        self.assertEqual(answer['summary'],reply)
        self.assertEqual(answer['evidence_ids'],[result['id']])

    def test_local_challenge_uses_frozen_values_without_new_science_or_tools(self):
        from fireatlas.assistant.agent import run_agent
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,TextPart
        result=self.assistant.science.call(self.session,'replay',normalize_context(self.study['context']))
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'challenge':True,'unscoped':False,
              'frozen_evidence_ids':[result['id']],'frozen_evidence_refs':{}}}
        calls=[]
        reply='The apparent change could reflect different overpass sampling. Check acquisition times and compare locations observed by the same sensor.'
        def respond(messages,info):
            calls.append(1)
            self.assertEqual(info.function_tools,[])
            return ModelResponse(parts=[TextPart(reply)])
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'local'},clear=True),patch.object(self.assistant.science,'call') as fresh:
            answer=run_agent(self.assistant,self.session,'Challenge the selected finding.',normalize_context(self.study['context']),view,
                             threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        fresh.assert_not_called()
        self.assertEqual(calls,[1])
        self.assertEqual(answer['summary'],reply)
        self.assertEqual(answer['evidence_ids'],[result['id']])

    def test_small_local_table_is_preloaded_complete_and_answered_in_one_call(self):
        import json
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,TextPart
        table=add(self.service.store,self.owner,self.doc['id'],'synthetic-test.csv',b'date,MODIS,NOAA20,NOAA20 state\n2024-07-27,348,1495,partial_export\n')
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True,'frozen_evidence_ids':[],'frozen_evidence_refs':{},'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        calls=[]
        def respond(messages,info):
            calls.append(1)
            contents=[value for message in messages for part in message.parts for value in ([part.content] if isinstance(getattr(part,'content',None),str) else part.content if isinstance(getattr(part,'content',None),list) else []) if isinstance(value,str)]
            prompt=next(value for value in contents if value.startswith('{"question"'))
            prepared=json.loads(prompt.split('\n/no_think')[0])['selected_table']
            self.assertEqual(list(prepared['records'][0]),['date','MODIS','NOAA20','NOAA20 status'])
            self.assertEqual(prepared['records'][0]['NOAA20 status'],'partial_export')
            self.assertNotIn('investigate',[tool.name for tool in info.function_tools])
            self.assertNotIn('To fetch or compare thermal heatmaps',str(info.instructions))
            self.assertNotIn('read_selected_table',[tool.name for tool in info.function_tools])
            return ModelResponse(parts=[TextPart('On July 27, NOAA-20 recorded 1495 readings compared with 348 for MODIS. Compare each source consistently over time.')])
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'local'},clear=True):
            answer=run_agent(self.assistant,self.session,'Compare these days in the selected table.',normalize_context({}),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(len(calls),1)
        self.assertEqual(answer['kind'],'AI-assisted interpretation')
        self.assertTrue(all(claim['source_binding']['datasetId']==table['id'] for claim in answer['claims']))
        self.assertEqual(answer['limitations'],[])

    def test_late_selected_park_row_binds_all_counts_without_a_retry(self):
        from pathlib import Path
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,TextPart
        table=add(self.service.store,self.owner,self.doc['id'],'Park source.csv',
                  (Path(__file__).parents[1]/'fireatlas/static/park-example.csv').read_bytes())
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True,'frozen_evidence_ids':[],
              'frozen_evidence_refs':{},'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        calls=[]
        reply=('The satellite readings on July 27 show that MODIS has a value of 348, while VIIRS S-NPP is unavailable, '
               'and VIIRS NOAA-20 has a value of 1495, while VIIRS NOAA-21 has 2073. A useful next comparison would '
               'be to check the same sensor on an adjacent date to identify any changes or gaps in the data.')
        def respond(messages,info):
            calls.append(1)
            return ModelResponse(parts=[TextPart(reply)])
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'local'},clear=True):
            answer=run_agent(self.assistant,self.session,'Explain the satellite readings on July 27 and suggest one useful next comparison.',
                             normalize_context({}),view,threading.Event(),time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(calls,[1])
        self.assertEqual(answer['summary'],reply)
        self.assertEqual(answer['kind'],'AI-assisted interpretation')
        self.assertTrue({'348','1495','2073'}.issubset({str(claim['value']) for claim in answer['claims']}))
        self.assertTrue(all(claim['source_binding']['datasetId']==table['id'] for claim in answer['claims']))

    def test_selected_source_can_compare_a_neighboring_row_with_exact_bindings(self):
        from fireatlas.studio.datasets import add
        from fireatlas.assistant.agent import run_agent
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse,TextPart
        import json
        table=add(self.service.store,self.owner,self.doc['id'],'synthetic-test.csv',b'date,MODIS\n2024-07-26,607\n2024-07-27,348\n')
        view={'studio':{'document_id':self.doc['id'],'whiteboard':True,'unscoped':True,'frozen_evidence_ids':[],
              'frozen_evidence_refs':{},'selected_dataset':{k:table[k] for k in ('id','name','sha256','columns','row_count')}}}
        calls=[]
        text='MODIS detections declined from 607 on July 26 to 348 on July 27. Check overpass timing before interpreting the change.'
        def respond(messages,info):
            calls.append(1)
            contents=[value for message in messages for part in message.parts for value in ([part.content] if isinstance(getattr(part,'content',None),str) else part.content if isinstance(getattr(part,'content',None),list) else []) if isinstance(value,str)]
            content=next(value for value in contents if value.startswith('{"question"'))
            table=json.loads(content.split('\n/no_think')[0])['selected_table']
            self.assertEqual(table['records'][0]['date'],'2024-07-27')
            self.assertEqual(table['checked_comparisons'][0]['previous_date'],'2024-07-26')
            self.assertEqual(table['checked_comparisons'][0]['direction'],'lower')
            return ModelResponse(parts=[TextPart(text)])
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'local'},clear=True):
            answer=run_agent(self.assistant,self.session,'Explain July 27.',normalize_context({}),view,threading.Event(),
                             time.monotonic()+30,lambda _:None,model=FunctionModel(respond))
        self.assertEqual(calls,[1])
        self.assertEqual(answer['summary'],text)
        self.assertTrue({'607','348','2024-07-26','2024-07-27'}.issubset({str(claim['value']) for claim in answer['claims']}))

    def test_published_park_satellites_and_environment_are_preserved_with_real_source_hashes(self):
        cfg=normalize_context({'case':'park-2024','start':'2024-07-25','end':'2024-07-28','day':'2024-07-27'})
        for kind,operation in [('park-satellites','park_platforms'),('factors','environment_context')]:
            result=self.assistant.science.call(self.session,operation,cfg)
            run=self.save_run(kind,result)
            binding=self.bridge.preserve_claims(self.owner,self.doc['id'],run)['bindings'][result['id']]
            preview=self.service.snapshot_preview(self.owner,self.doc['id'],binding['snapshotId'],kind)
            ET.fromstring(preview['svg'])
            if kind=='park-satellites':
                row=next(row for row in preview['visual']['values'] if row['date']=='2024-07-27')
                self.assertEqual(row['sources']['MODIS_SP']['value'],348)
                self.assertEqual(row['sources']['VIIRS_NOAA20_SP']['value'],1495)
                self.assertEqual(row['sources']['VIIRS_NOAA21_SP']['value'],2073)
                self.assertIsNone(row['sources']['VIIRS_SNPP_SP']['value'])
            else:
                self.assertEqual(len(preview['visual']['source_sha256']),64)
                self.assertGreater(len(preview['visual']['cells']),0)
                self.assertIn('NDVI',preview['svg'])
                self.assertIn('Elevation',preview['svg'])

class GeographicGuardTests(unittest.TestCase):
    def test_both_view_and_investigation_guard_reject_a_different_place(self):
        from fireatlas.assistant.board_views import validate_place_scope,prepare
        from types import SimpleNamespace
        from unittest.mock import Mock
        cfg=normalize_context({'case':'park-2024','start':'2024-07-25','end':'2024-07-28'})
        with self.assertRaises(ValueError):validate_place_scope(cfg,'replay',{'unresolved location'},[])
        with self.assertRaises(ValueError):validate_place_scope(cfg,'replay',[],[{'bbox':[88,20,93,27]}])
        science=SimpleNamespace(call=Mock())
        with self.assertRaises(ValueError):
            prepare(SimpleNamespace(science=science),'owner','heatmap',cfg,{},'Show this study',False,threading.Event(),time.monotonic()+10,unresolved_places={'unresolved location'})
        science.call.assert_not_called()

    def test_switching_a_scoped_case_requires_that_requested_case(self):
        cfg=normalize_context({'case':'park-2024'})
        with self.assertRaises(ValueError):view_context(cfg,{'case':'camp-2018'},'Show this selected study',False)

    def test_archive_figure_uses_actual_search_period_not_reference_dates(self):
        snapshot={'scope':{'bbox':[0,0,1,1],'start':'2024-07-25','end':'2024-07-28'},'snapshot_sha256':'hash'}
        receipt={'operation':'archive_search','payload':{'first_year':2006,'last_year':2026,'bbox':[0,0,1,1],'windows':[],'total_windows':0}}
        preview=render(snapshot,receipt,'archive')
        self.assertEqual(preview['visual']['scope']['start'],'2006-01-01')
        self.assertEqual(preview['visual']['scope']['end'],'2026-12-31')
        self.assertIn('2006-01-01',preview['svg'])

class ViewIntentTests(unittest.TestCase):
    def test_scoped_boundaries_cannot_change_without_request(self):
        cfg=normalize_context({'case':'park-2024'})
        with self.assertRaises(ValueError):view_context(cfg,{'bbox':[88,20,93,27]},'Show this selected study',False)
        with self.assertRaises(ValueError):view_context(cfg,{'case':'park-2024','bbox':[88,20,93,27]},'Show Park Fire',False)
    def test_explicit_source_qualifications_are_local_and_can_be_multiple(self):
        from fireatlas.assistant.board_views import requested_view_sources
        self.assertEqual(requested_view_sources('Show a MODIS calendar and a VIIRS calendar','calendar'),{'MODIS_SP','VIIRS_SNPP_SP'})
        text='Show a heatmap and a MODIS raw observed-cell calendar'
        self.assertEqual(requested_view_sources(text,'heatmap'),set())
        self.assertEqual(requested_view_sources(text,'calendar'),{'MODIS_SP'})
    def test_omitted_fields_use_explicit_request_but_wrong_source_is_rejected(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from fireatlas.assistant.board_views import prepare
        science=SimpleNamespace(call=Mock(return_value={'id':'result'}))
        service=SimpleNamespace(science=science)
        message='Show a MODIS calendar for Park Fire from 2024-07-25 to 2024-07-28'
        prepare(service,'owner','calendar',normalize_context({}),{},message,True,threading.Event(),time.monotonic()+10)
        cfg=science.call.call_args.args[2]
        self.assertEqual((cfg['case'],cfg['start'],cfg['end'],cfg['source']),('park-2024','2024-07-25','2024-07-28','MODIS_SP'))
        with self.assertRaises(ValueError):prepare(service,'owner','calendar',normalize_context({}),{'source':'VIIRS_SNPP_SP'},message,True,threading.Event(),time.monotonic()+10)

    def test_selected_interval_cannot_be_silently_narrowed(self):
        cfg=normalize_context({'case':'park-2024','start':'2024-07-25','end':'2024-07-28'})
        with self.assertRaises(ValueError):view_context(cfg,{'start':'2024-07-25','end':'2024-07-26'},'Find a similar profile for this study',False)
        changed=view_context(cfg,{'start':'2024-07-25','end':'2024-07-26'},'Use July 25–26, 2024',False)
        self.assertEqual(changed['end'],'2024-07-26')
