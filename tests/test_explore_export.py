"""Raw Explore publication and source/unknown-state regressions (isolated fixtures)."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from fireatlas.core import connect, calendar, ingest
from fireatlas.provenance import sanitize_public_payload
from fireatlas.regions import REGIONS
from scripts.export_explore import export
from tests.test_aggregates import FIELDS, _row


class ExploreExportTests(unittest.TestCase):
    def test_export_uses_raw_calendar_per_source_and_preserves_unknowns(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);database=root/'science.sqlite3'
            for source in ('MODIS_SP','VIIRS_SNPP_SP'):
                file=root/(source+'.csv')
                with file.open('w',newline='') as stream:
                    writer=csv.writer(stream);writer.writerow(FIELDS);writer.writerow(_row(source,'2024-07-25','1200'))
                with connect(database) as db:
                    ingest(db,file,source,complete_month='2024-07',bbox=REGIONS['norcal']['bbox'])
            m=export(database,root/'site',2024,2024)
            self.assertEqual(len(m['files']),6)
            for series in ('joint','modis','viirs-snpp'):
                entry=m['files']['norcal/'+series+'/2024'];body=(root/'site/data/explore'/entry['path']).read_bytes()
                self.assertEqual(hashlib.sha256(body).hexdigest(),entry['sha256'])
                value=json.loads(body)
                self.assertIsNone(value['monthly'][0]['detected_cell_days'])
                self.assertEqual(value['monthly'][6]['detected_cell_days'],1)
                self.assertEqual(value['monthly'][6]['source_raw_rows']['MODIS'],int(series!='viirs-snpp'))
                self.assertEqual(value['monthly'][6]['source_raw_rows']['VIIRS'],int(series!='modis'))
                self.assertEqual(value['daily'][206]['satellite_observation_coverage'],'unknown')
                for month in value['monthly']:month.pop('source_raw_rows')
                with connect(database) as db:expected=sanitize_public_payload(calendar(db,bbox=tuple(REGIONS['norcal']['bbox']),year=2024,series=series))
                self.assertEqual(value,json.loads(json.dumps(expected)))
            with self.assertRaisesRegex(ValueError,'overwrite'):
                export(database,root/'site',2024,2024)

    def test_synthetic_batches_cannot_enter_the_publication(self):
        from fireatlas.demo import make_demo
        import contextlib,io
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);database=root/'science.sqlite3'
            with contextlib.redirect_stdout(io.StringIO()):make_demo(root/'fixtures',database)
            with self.assertRaisesRegex(ValueError,'synthetic'):
                export(database,root/'site',2024,2024)
            self.assertFalse((root/'site/data/explore').exists())

    def test_committed_publication_has_all_years_and_matches_older_raw_results(self):
        root=Path(__file__).resolve().parents[1]/'site/data'
        m=json.loads((root/'explore/manifest.json').read_text())
        self.assertEqual(len(m['files']),126)
        self.assertEqual((m['calendar_start_year'],m['calendar_end_year']),(2006,2026))
        for region in REGIONS:
            for series in ('joint','modis','viirs-snpp'):
                for year in range(2006,2027):
                    entry=m['files'][f'{region}/{series}/{year}'];body=(root/'explore'/entry['path']).read_bytes()
                    self.assertEqual(len(body),entry['bytes']);self.assertEqual(hashlib.sha256(body).hexdigest(),entry['sha256'])
                    value=json.loads(body);self.assertEqual(value['series'],series);self.assertEqual(value['year'],year)
                    if series=='joint' and year in (2024,2026):
                        previous=json.loads((root/f'combined/{region}-{year}.json').read_text())
                        for item in value['monthly']:item.pop('source_raw_rows')
                        self.assertEqual(value,previous)
