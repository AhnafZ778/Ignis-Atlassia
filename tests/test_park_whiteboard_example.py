import csv
import io
import unittest
from html.parser import HTMLParser

from fireatlas.studio.park_chart import published_timeline
from fireatlas.web import ASSETS
from scripts.build_park_whiteboard_example import ROOT, build


class Counts(HTMLParser):
    def __init__(self):
        super().__init__();self.circles=0;self.scripts=0
    def handle_starttag(self,tag,attrs):
        if tag=='circle':self.circles+=1
        if tag=='script':self.scripts+=1


class ParkWhiteboardExampleTests(unittest.TestCase):
    def test_example_recounts_sources_and_matches_both_site_outputs(self):
        page,table=build()
        rows=list(csv.DictReader(io.StringIO(table.decode())))
        truth=published_timeline()
        self.assertEqual([r['UTC date'] for r in rows],[r['date'] for r in truth])
        for result,reference in zip(rows,truth):
            for source,value in reference['values'].items():
                self.assertEqual(result[source],'' if value is None else str(value))
                self.assertEqual(result[source+' state'],reference['states'][source])
        selected=next(row for row in truth if row['date']=='2024-07-27')
        parser=Counts();parser.feed(page.decode())
        self.assertEqual(parser.circles,sum(selected['values'][key] for key in ('MODIS_SP','VIIRS_NOAA20_SP','VIIRS_NOAA21_SP')))
        self.assertEqual(parser.scripts,0)
        for base in (ROOT/'site',ROOT/'fireatlas/static'):
            self.assertEqual((base/'park-example.html').read_bytes(),page)
            self.assertEqual((base/'park-example.csv').read_bytes(),table)
        self.assertEqual(ASSETS['/park-example.html'][0],'park-example.html')
        self.assertEqual(ASSETS['/park-example.csv'][0],'park-example.csv')
