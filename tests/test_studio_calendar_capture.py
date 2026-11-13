"""Raw calendar captures retain actual values and unknown days in Studio."""
import unittest
from fireatlas.studio.visuals import prepared


class CalendarCaptureTests(unittest.TestCase):
    def test_raw_calendar_preview_retains_scope_and_unknowns(self):
        snapshot = {'id': 'calendar', 'scope': {'bbox': [-122, 39, -120, 41], 'start': '2024-07-01', 'end': '2024-07-31', 'day': None}, 'method': {'unit': 'cell-days'}}
        receipt = {'operation': 'calendar', 'payload': {'daily': [
            {'date_utc': '2024-06-30', 'detected_cell_days': 7},
            {'date_utc': '2024-07-01', 'detected_cell_days': 3},
            {'date_utc': '2024-07-02', 'detected_cell_days': None, 'partial_import_detected_cell_days': 8},
            {'date_utc': '2024-07-03', 'detected_cell_days': 0},
        ]}}
        visual = prepared({'type': 'calendar'}, [snapshot], {'calendar': receipt}, {})
        self.assertEqual(visual['kind'], 'calendar')
        self.assertEqual([(day['date'], day['value']) for day in visual['days']], [('2024-07-01', 3), ('2024-07-02', None), ('2024-07-03', 0)])
        self.assertEqual(visual['days'][1]['evidence_state'], 'unknown')

    def test_comparison_preview_uses_only_selected_experiment(self):
        snapshot = {'id': 'comparison', 'scope': {'bbox': [-122, 39, -120, 41], 'start': '2025-01-01', 'end': '2025-12-31', 'day': None}, 'comparison_selection': {'experiment': 'forward/2025/7', 'mode': 'adjusted'}}
        row = {'date': '2025-07', 'modis': 10, 'reference': 12, 'prediction': 11.5, 'raw_switch': 10, 'adjusted_switch': 11.5}
        receipt = {'operation': 'comparability', 'payload': {'result': {'experiments': {'forward/2025/7': {'rows': [row]}, 'nested/2025/7': {'rows': []}}}}}
        visual = prepared({'type': 'chart'}, [snapshot], {'comparison': receipt}, {})
        self.assertEqual(visual['kind'], 'monthly-comparison')
        self.assertEqual(visual['rows'], [row])
        self.assertEqual(visual['mode'], 'adjusted')


if __name__ == '__main__':
    unittest.main()
