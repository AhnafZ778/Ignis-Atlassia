import io
import math
import unittest
from unittest.mock import patch

from fireatlas.core import TO_GRID
from fireatlas.validation_check import projected, grid, check
from fireatlas.validity import build_evidence
from tests import test_validity


class IndependentRecountTests(unittest.TestCase):
    def test_analytical_projection_matches_reference_on_nontrivial_global_coordinates(self):
        for lon, lat in [(-121.4,39.4), (-122,40.5), (0,0), (-.1,-.1), (135,-35), (-179,85), (179,-85)]:
            analytical = projected(lon,lat)
            reference = TO_GRID.transform(lon,lat)
            for actual, expected in zip(analytical,reference):
                self.assertAlmostEqual(actual,expected,places=6)
            self.assertEqual(grid(lon,lat),tuple(math.floor(x/1000) for x in reference))

    def test_zip_recount_works_without_the_application_transform(self):
        test_validity.HistoricalValidityTests.setUpClass()
        try:
            from fireatlas.core import connect
            with connect(test_validity.HistoricalValidityTests.database) as db:
                bundle=build_evidence(db,'park-2024')
            with patch('fireatlas.validity._summarize',side_effect=AssertionError('shared implementation called')):
                result=check(io.BytesIO(bundle))
            self.assertEqual(result['joint_cell_days'],1606)
            self.assertEqual(result['original_pixels'],3137)
            self.assertFalse(result['independent_scientific_review'])
        finally:
            test_validity.HistoricalValidityTests.tearDownClass()


if __name__=='__main__':
    unittest.main()
