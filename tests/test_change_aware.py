import unittest
from fireatlas.change_aware import fit, predict

class ChangeAwareTests(unittest.TestCase):
    def setUp(self):
        self.rows = [dict(year=y, month=m, modis=y-2018+m, reference=2*(y-2018+m)) for y in range(2019, 2023) for m in range(1, 13)]

    def test_fit_uses_only_training_and_is_deterministic(self):
        model = fit(self.rows, test_year=2023)
        self.assertEqual(model, fit(self.rows, test_year=2023))
        self.assertEqual(model['training_months'], 48)
        self.assertEqual(model['change_pairs'], 36)
        self.assertGreaterEqual(predict(model, 1, 0), 0)
        with self.assertRaises(ValueError): fit(self.rows, test_year=2022)

    def test_invalid_and_duplicate_rows(self):
        with self.assertRaises(ValueError): fit(self.rows+self.rows[:1], test_year=2023)
        with self.assertRaises(ValueError): fit([dict(year=2020, month=1, modis=float('nan'), reference=1)], test_year=2023)

    def test_synthetic_chronological_fold_and_baselines(self):
        from fireatlas.change_aware import synthetic_fold
        rows=[dict(_synthetic_fixture=True,year=y,month=m,modis=(0 if m==1 else y-2017+m),reference=2*(y-2017+m)) for y in range(2018,2024) for m in range(1,13)]
        result=synthetic_fold(rows,test_year=2023)
        self.assertEqual(result['training_years'],[2018,2019,2020])
        self.assertEqual(result['calibration_years'],[2021,2022])
        self.assertEqual(set(result['models']),{'identity','annual_ratio','monthly_ratio','fixed_offset','change_aware'})
        self.assertEqual(result['models']['change_aware']['change_pairs'],12)
        self.assertEqual(result['models']['annual_ratio']['predictions'][1]['estimate'],result['models']['monthly_ratio']['predictions'][1]['estimate'])
        no_training_modis=[dict(r,modis=0) if r['year']<=2020 else r for r in rows]
        no_ratio=synthetic_fold(no_training_modis,test_year=2023)
        self.assertEqual(no_ratio['models']['annual_ratio']['status'],'unavailable')
        self.assertEqual(no_ratio['models']['monthly_ratio']['status'],'unavailable')
        self.assertEqual(result['models']['identity']['zero_modis_test_months'],1)
        with self.assertRaises(ValueError): synthetic_fold(rows[:-6],test_year=2023)
        with self.assertRaises(ValueError): synthetic_fold([{k:v for k,v in r.items() if k!='_synthetic_fixture'} for r in rows],test_year=2023)
