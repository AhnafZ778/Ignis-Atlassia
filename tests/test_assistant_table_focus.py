import unittest
from fireatlas.assistant.table_focus import matching_row, requested_date, chronological_pattern, contradicts_pattern
from fireatlas.assistant.agent import invalid_interpretation

class TableFocusTests(unittest.TestCase):
    def test_explicit_dates_and_ambiguous_requests(self):
        self.assertEqual(requested_date('Compare July 27, 2024'), '2024-07-27')
        self.assertEqual(requested_date('Compare 2024-07-27'), '2024-07-27')
        self.assertIsNone(requested_date('Compare July 27, 2024 to July 28, 2024'))
        self.assertIsNone(requested_date('Compare February 31, 2024'))

    def test_requires_a_unique_exact_date_in_the_retrieved_page(self):
        rows=[['2024-07-25','3'],['2024-07-27','9']]
        self.assertEqual(matching_row('What happened July 27, 2024?',rows),('2024-07-27',1))
        self.assertEqual(matching_row('What happened July 28, 2024?',rows),('2024-07-28',None))
        self.assertEqual(matching_row('What happened July 27, 2024?',rows+[rows[1]]),('2024-07-27',None))

    def test_platform_identifiers_are_allowed_but_unchecked_numbers_are_not(self):
        self.assertFalse(invalid_interpretation('NOAA-20 and NOAA-21 show different readings.'))
        self.assertTrue(invalid_interpretation('NOAA-20 recorded 348 detections.'))
        self.assertTrue(invalid_interpretation('NOAA-20 caused the fire.'))
        self.assertFalse(invalid_interpretation('On July 27, 2024 NOAA-20 recorded 1,495 detections.', ['2024-07-27','1495']))
        self.assertTrue(invalid_interpretation('NOAA-20 recorded 1496 detections.', ['1495']))
        self.assertTrue(invalid_interpretation('NOAA-20 recorded -348 detections.', ['348']))
        self.assertTrue(invalid_interpretation('NOAA-20 recorded 348.5 detections.', ['348']))

    def test_dated_group_pattern_catches_false_steady_decline_and_wrong_extreme(self):
        groups=[{'group':f'2024-07-{25+i}','mean':value} for i,value in enumerate([603,607,348,190])]
        pattern=chronological_pattern(groups)
        self.assertEqual(pattern['successive_direction'],['increase','decrease','decrease'])
        self.assertTrue(contradicts_pattern('The values drop steadily.',pattern))
        self.assertTrue(contradicts_pattern('The steepest decline was after the third date.',pattern))
        self.assertFalse(contradicts_pattern('The steepest decline was after the second date.',pattern))
        self.assertFalse(contradicts_pattern('The values rise then fall.',pattern))
        self.assertIsNone(chronological_pattern([{'group':'2024-07-25','mean':1},{'group':'2024-07-26','mean':None}]))
        self.assertIsNone(chronological_pattern([{'group':'north','mean':1},{'group':'south','mean':2}]))

    def test_neighbor_comparisons_keep_sensor_directions_and_missing_values(self):
        from fireatlas.assistant.table_focus import neighboring_comparisons
        payload={'columns':['date','MODIS_SP','VIIRS_SNPP_SP','VIIRS_NOAA21_SP'],
                 'rows':[['2024-07-27','348','','2073'],['2024-07-26','607','','2019']]}
        comparisons=neighboring_comparisons(payload,'Explain July 27.')
        self.assertEqual([(c['field'],c['direction']) for c in comparisons],[('MODIS','lower'),('VIIRS NOAA-21','higher')])
        self.assertEqual(comparisons[0]['previous_date'],'2024-07-26')
        payload['rows'].append(['2024-07-26','0','','0'])
        self.assertEqual(neighboring_comparisons(payload,'Explain July 27.'),[])


class NumericDirectionTests(unittest.TestCase):
    def test_checks_stated_before_and_after_values(self):
        from fireatlas.assistant.table_focus import contradicts_numeric_change
        self.assertTrue(contradicts_numeric_change("A decrease in thermal detections from 603 to 607, indicating a reduction."))
        self.assertTrue(contradicts_numeric_change("Recorded detections rose from 1,295 to 1,102."))
        self.assertFalse(contradicts_numeric_change("Recorded detections increased from 603 to 607."))
        self.assertFalse(contradicts_numeric_change("Recorded detections did not decrease from 603 to 607."))
        self.assertFalse(contradicts_numeric_change("Detections increased from 2024-07-25 to 2024-07-26."))
