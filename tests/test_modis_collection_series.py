"""Tests for the independent multi-month collection comparison method."""
import gzip
from pathlib import Path
import tempfile
import unittest

from fireatlas import modis_collection_pilot as pilot
from fireatlas import modis_collection_series as series


def row(day, longitude='-121', platform='T'):
    return f'{day} 0128 {platform} 39 {longitude} 303.3 292.5 362 7.0 54 0 N\n'


class SeriesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def source(self, name, rows):
        path = self.root / name
        with gzip.open(path, 'wt') as stream:
            stream.write(pilot.HEADER+'\n'+rows)
        return path

    def test_leap_month_and_missing_overlap(self):
        paths={'C6':self.source('a.gz',row('20200229')),
               'C61':self.source('b.gz',row('20200229')+row('20200229',longitude='-120.9'))}
        result=series.compare_month('2020-02',paths,{'C6':{},'C61':{}})
        days=result['regions']['norcal']['days']
        self.assertEqual(len(days),29)
        self.assertEqual(days[-1]['date'],'2020-02-29')
        self.assertEqual(days[-1]['jaccard'],0.5)
        self.assertIsNone(days[0]['jaccard'])
        self.assertFalse(result['transfer_qualified'])
        self.assertFalse(result['independent_review'])

    def test_wrong_month_bad_date_and_missing_collection_fail(self):
        for month in ('2020-13','2020-2','1999-12','2020-00'):
            with self.subTest(month=month), self.assertRaises(ValueError): series.parse_month(month)
        path=self.source('wrong.gz',row('20200301'))
        with self.assertRaises(ValueError): series.read_month(path,'2020-02')
        with self.assertRaises(ValueError): series.compare_month('2020-02',{'C6':path},{'C6':{}})

    def test_january_pilot_equivalence(self):
        paths={'C6':self.source('a.gz',row('20230101')+row('20230102')),
               'C61':self.source('b.gz',row('20230101')+row('20230102',longitude='-120.9'))}
        provenance={'C6':{},'C61':{}}
        old=pilot.compare(paths,provenance)
        new=series.compare_month('2023-01',paths,provenance)
        self.assertEqual(old['regions'],new['regions'])
        self.assertEqual(new,series.compare_month('2023-01',paths,provenance))

    def test_series_missing_month_is_unknown_and_tampering_fails(self):
        paths={'C6':self.source('a.gz',row('20230101')),'C61':self.source('b.gz',row('20230101'))}
        value=series.compare_month('2023-01',paths,{'C6':{},'C61':{}})
        report=series.summarize(['2023-01','2023-02'],{'2023-01':value})
        self.assertEqual((report['requested_months'],report['supplied_months']),(2,1))
        self.assertEqual(report['months'][0]['status'],'supplied')
        self.assertEqual(report['months'][1]['status'],'missing')
        self.assertIsNone(report['months'][1]['regions'])
        with self.assertRaises(ValueError):series.summarize(['2023-01','2023-01'],{})
        value['regions']['norcal']['month_cell_days']['both']=999
        with self.assertRaises(ValueError):series.summarize(['2023-01'],{'2023-01':value})
