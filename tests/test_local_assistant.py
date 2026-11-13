"""Local provider configuration checks; no real model or network required."""
import asyncio,unittest
from types import SimpleNamespace
from unittest.mock import patch
from fireatlas.assistant.agent import provider_config
from fireatlas.assistant.local import configuration,prepare_tools,tool_names

class LocalConfigurationTests(unittest.TestCase):
    def test_local_requires_no_cloud_key_or_paid_prices(self):
        with patch.dict('os.environ',{'FIREATLAS_AI_PROVIDER':'local'},clear=True):
            cfg=provider_config()
        self.assertTrue(cfg['configured'])
        self.assertEqual(cfg['provider'],'local')
        self.assertEqual(cfg['model'],'ignis-scientist:latest')
        self.assertEqual(cfg['input_price'],0)
        self.assertIsNone(cfg['vision_model'])
    def test_local_endpoint_cannot_silently_be_a_remote_provider(self):
        for url in ('https://example.com/v1','http://example.com/v1','http://key@localhost:11434/v1'):
            with patch.dict('os.environ',{'FIREATLAS_LOCAL_URL':url}):
                with self.assertRaises(ValueError):configuration()
    def test_local_exposes_science_reads_without_unrelated_canvas_effects(self):
        names=tool_names({'whiteboard':True},'Show a map')
        self.assertIn('prepare_board_view',names)
        self.assertIn('show_related_candidate',names)
        self.assertNotIn('run_studio_recipe',names)
        self.assertNotIn('draft_studio_action',names)
    def test_prepare_tools_filters_and_shortens_definitions(self):
        from pydantic_ai.tools import ToolDefinition
        definitions=[ToolDefinition(name='prepare_board_view',description='Long '*500),ToolDefinition(name='run_studio_recipe')]
        prepared=asyncio.run(prepare_tools(SimpleNamespace(deps={'prepare_board_view'}),definitions))
        self.assertEqual([item.name for item in prepared],['prepare_board_view'])
        self.assertLess(len(prepared[0].description),400)
        self.assertEqual(definitions[0].description,'Long '*500)

    def test_conceptual_opinions_do_not_need_irrelevant_measurement_tools(self):
        from fireatlas.assistant.local import conceptual_request
        self.assertTrue(conceptual_request('Explain why sharper sensors can record more thermal readings.'))
        self.assertTrue(conceptual_request('What is your opinion on comparing sensors?'))
        self.assertFalse(conceptual_request('Show a MODIS calendar for Park Fire.'))
        self.assertFalse(conceptual_request('Explain this measured chart.'))
        self.assertFalse(conceptual_request('Why do the sensors disagree?',{'selected_dataset':{'id':'table'}}))

    def test_detection_counts_are_not_described_as_observation_coverage(self):
        from fireatlas.assistant.local import invalid_detection_coverage
        results=[{'operation':'calendar'}]
        self.assertTrue(invalid_detection_coverage('The calendar shows the area covered by satellite observations.',results))
        self.assertFalse(invalid_detection_coverage('The calendar does not show observation coverage.',results))
        self.assertFalse(invalid_detection_coverage('It shows places where heat was detected.',results))
        heatmap=[{'operation':'replay'}]
        self.assertTrue(invalid_detection_coverage('The majority of the area was affected by the fire.',heatmap))
        self.assertTrue(invalid_detection_coverage('This suggests that the fire was widespread and intense.',heatmap))
        self.assertFalse(invalid_detection_coverage('There were 348 detections across 288 grid cells. Check acquisition times at repeated locations.',heatmap))
        self.assertTrue(invalid_detection_coverage('The maps show the burned area increasing.',[{'operation':'regional_comparison'}]))
        self.assertTrue(invalid_detection_coverage('The increase indicates growing demand in the region.',[{'operation':'regional_comparison'}]))
        self.assertFalse(invalid_detection_coverage('Hypothesis: traffic could influence ignition risk; test it with independent transport data.',[{'operation':'regional_comparison'}]))

    def test_reasoned_hypotheses_and_negations_are_not_blocked_as_causal_claims(self):
        from fireatlas.assistant.agent import invalid_interpretation
        self.assertFalse(invalid_interpretation('Hypothesis: sensor differences could have caused the higher count.'))
        self.assertFalse(invalid_interpretation('This does not establish that the fire was extinguished.'))
        self.assertTrue(invalid_interpretation('The fire was extinguished.'))
        self.assertTrue(invalid_interpretation('There were 99999 readings.'))
        self.assertFalse(invalid_interpretation('There were 348 readings.',[348]))

    def test_general_explanations_do_not_load_unused_tool_schemas(self):
        self.assertEqual(tool_names({'whiteboard':True},'Explain why sharper satellites can detect more hot spots.'),set())
        self.assertIn('prepare_board_view',tool_names({'whiteboard':True},'Show a calendar for Park Fire.'))

    def test_natural_date_labels_resolve_to_the_checked_date(self):
        from fireatlas.assistant.agent import invalid_interpretation
        self.assertFalse(invalid_interpretation('The readings on July 27 differ by sensor.',['2024-07-27']))
        self.assertTrue(invalid_interpretation('The readings on July 29 differ by sensor.',['2024-07-27']))
        self.assertFalse(invalid_interpretation('May 1, 2023 and May 1, 2024 have readings.',['2023-05-01','2024-05-01']))
        self.assertTrue(invalid_interpretation('May 1, 2025 has readings.',['2023-05-01','2024-05-01']))

    def test_an_unselected_board_table_does_not_force_an_irrelevant_read(self):
        from fireatlas.assistant.local import conceptual_request
        self.assertTrue(conceptual_request('Why do sharper sensors detect smaller hot spots?',{'selected_dataset':{'id':'table'},'dataset_scope':'board'}))
        self.assertFalse(conceptual_request('Explain this spike.',{'selected_dataset':{'id':'table'},'dataset_scope':'board'}))

    def test_selected_table_does_not_offer_unrelated_satellite_calculations(self):
        names=tool_names({'whiteboard':True,'selected_dataset':{'id':'table'}},'Explain the satellite readings and suggest a next comparison.')
        self.assertEqual(names,{'read_selected_table','prepare_heatmap_comparison'})
        self.assertNotIn('investigate',names)
        self.assertIn('compare_selected_groups',tool_names({'whiteboard':True,'selected_dataset':{'id':'table'}},'Create a grouped mean chart.'))

    def test_yearless_date_uses_the_source_without_guessing_an_ambiguous_year(self):
        from fireatlas.assistant.table_focus import matching_row
        self.assertEqual(matching_row('Explain July 27.',[['2024-07-25','603'],['2024-07-27','348']]),('2024-07-27',1))
        self.assertEqual(matching_row('Explain July 27.',[['2023-07-27','123'],['2024-07-27','348']]),(None,None))

    def test_selected_csv_does_not_hide_requested_scientific_views(self):
        studio={'whiteboard':True,'selected_dataset':{'id':'table'}}
        for question in ('Show a heatmap of Park Fire on 2024-07-27.',
                         'Show a MODIS calendar for Park Fire.',
                         'Show the measured NDVI and elevation maps for Park Fire.',
                         'Find a similar thermal profile and bring a coordinate view.'):
            with self.subTest(question=question):
                self.assertIn('prepare_board_view',tool_names(studio,question))

    def test_direct_view_resolution_does_not_override_custom_scope_or_missing_dates(self):
        from fireatlas.assistant.board_views import explicit_single_view
        self.assertEqual(explicit_single_view('Show a heatmap of Park Fire on 2024-07-27.'),
                         {'kind':'heatmap','case_id':'park-2024','day':'2024-07-27'})
        self.assertIsNone(explicit_single_view('Show a Park Fire heatmap in Bangladesh.'))
        self.assertIsNone(explicit_single_view('Show a Park Fire heatmap on July 24.'))
        self.assertIsNone(explicit_single_view('Show a heatmap for this investigation.'))

    def test_an_unavailable_sensor_cannot_be_described_as_agreeing(self):
        from fireatlas.assistant.local import invalid_detection_coverage
        result={'operation':'replay','context':{'day':'2024-07-27'},'payload':{'frames':[{'date_utc':'2024-07-27','products':{
            'MODIS_SP':{'detections':348,'state':'complete_export'},
            'VIIRS_SNPP_SP':{'detections':0,'state':'documented_product_gap'}}}]}}
        self.assertTrue(invalid_detection_coverage('Both sensors report the same total.',[result]))
        self.assertFalse(invalid_detection_coverage('Both sensors cannot report the same total here.',[result]))

    def test_selected_day_does_not_discard_the_requested_english_study_range(self):
        from fireatlas.assistant.board_views import explicit_single_view
        self.assertEqual(explicit_single_view('Show a heatmap of Park Fire on 2024-07-27, using the July 25–28 study.'),
                         {'kind':'heatmap','case_id':'park-2024','day':'2024-07-27','start':'2024-07-25','end':'2024-07-28'})
        self.assertEqual(explicit_single_view('Show a MODIS calendar for Park Fire, July 25–28, 2024.')['start'],'2024-07-25')

    def test_checked_compact_date_ranges_do_not_trigger_false_retries(self):
        from fireatlas.assistant.agent import invalid_interpretation
        self.assertFalse(invalid_interpretation('The study spans July 25–28, 2024.',['2024-07-25','2024-07-28']))
        self.assertTrue(invalid_interpretation('The study spans July 24–28, 2024.',['2024-07-25','2024-07-28']))
