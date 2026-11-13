import unittest
import shutil
from unittest.mock import patch

from .studio_support import StudioCase
from fireatlas.studio import datasets, source_documents, source_search
from fireatlas.studio.errors import NotFound, StudioError


class SourceSearchTests(StudioCase):
    @unittest.skipUnless(shutil.which('pdfinfo') and shutil.which('pdftotext'), 'Poppler is optional')
    def test_short_real_pdf_ends_without_a_false_missing_page(self):
        from .test_studio_source_documents import simple_pdf
        doc = self.board()
        source_documents.add(self.service.store, self.owner, doc['id'], 'short.pdf', simple_pdf(b'unique smoke plume'))
        result = source_search.search(self.service.store, self.owner, doc['id'], 'smoke')
        self.assertEqual(result['scanned_pages'], 1)
        self.assertEqual(result['matches'][0]['page'], 1)
        self.assertEqual(result['unavailable'], [])
        self.assertIsNone(result['next_cursor'])

    def test_known_page_failure_is_not_mistaken_for_end_of_document(self):
        doc = self.board()
        source_documents.add(self.service.store, self.owner, doc['id'], 'broken.pdf', b'%PDF-test')
        with patch.object(source_documents, 'page_count', return_value=2), patch.object(source_documents, 'extract_page', side_effect=StudioError('Unreadable')):
            result = source_search.search(self.service.store, self.owner, doc['id'], 'smoke')
        self.assertEqual(result['unavailable'][0]['page'], 1)

    def test_reports_pages_beyond_search_limit(self):
        doc = self.board()
        source_documents.add(self.service.store, self.owner, doc['id'], 'long.pdf', b'%PDF-test')
        with patch.object(source_documents, 'page_count', return_value=22), patch.object(source_documents, 'extract_page', return_value={'text': 'clear', 'truncated': False}):
            first = source_search.search(self.service.store, self.owner, doc['id'], 'smoke')
            second = source_search.search(self.service.store, self.owner, doc['id'], 'smoke', cursor=first['next_cursor'])
        self.assertEqual(second['scanned_pages'], 8)
        self.assertEqual(second['unavailable'][0]['page'], 21)
        self.assertIsNone(second['next_cursor'])

    def test_search_returns_exact_owned_rows_and_bounded_pdf_passages(self):
        doc = self.board()
        table = datasets.add(self.service.store, self.owner, doc['id'], 'readings.csv', b'place,condition\nPark,smoke plume\nOther,clear\n')
        pdf = source_documents.add(self.service.store, self.owner, doc['id'], 'notes.pdf', b'%PDF-test')
        def extract(data, page):
            if page == 1:
                return {'text': 'An observed smoke plume appears here.', 'truncated': False}
            raise StudioError('Page unavailable')
        with patch.object(source_documents, 'extract_page', side_effect=extract):
            result = source_search.search(self.service.store, self.owner, doc['id'], 'SMOKE')
        self.assertEqual([item['kind'] for item in result['matches']], ['csv', 'pdf'])
        row, page = result['matches']
        self.assertEqual((row['source_id'], row['source_sha256'], row['row_offset'], row['column'], row['excerpt']),
                         (table['id'], table['sha256'], 0, 'condition', 'smoke plume'))
        self.assertEqual((page['source_id'], page['page']), (pdf['id'], 1))
        self.assertIn('smoke plume', page['excerpt'])
        self.assertEqual(result['scanned_tables'], 1)
        self.assertEqual(result['scanned_pages'], 1)
        self.assertTrue(result['unavailable'])
        with self.assertRaises(NotFound):
            source_search.search(self.service.store, self.other, doc['id'], 'smoke')
        with self.assertRaises(StudioError):
            source_search.search(self.service.store, self.owner, doc['id'], 'x')

    def test_match_limit_and_cancellation_are_explicit(self):
        doc = self.board()
        datasets.add(self.service.store, self.owner, doc['id'], 'sample.csv', ('value\n' + 'smoke\n' * 10).encode())
        result = source_search.search(self.service.store, self.owner, doc['id'], 'smoke')
        self.assertEqual(len(result['matches']), 8)
        self.assertTrue(result['stopped_at_match_limit'])
        continued = source_search.search(self.service.store, self.owner, doc['id'], 'smoke', cursor=result['next_cursor'])
        self.assertEqual([item['row_offset'] for item in continued['matches']], [8, 9])
        self.assertIsNone(continued['next_cursor'])
        with self.assertRaises(StudioError):
            source_search.search(self.service.store, self.owner, doc['id'], 'other', cursor=result['next_cursor'])
        datasets.add(self.service.store, self.owner, doc['id'], 'new.csv', b'v\nnew\n')
        with self.assertRaises(StudioError):
            source_search.search(self.service.store, self.owner, doc['id'], 'smoke', cursor=result['next_cursor'])
        with self.assertRaises(InterruptedError):
            source_search.search(self.service.store, self.owner, doc['id'], 'smoke', cancelled=lambda: True)

    def test_continues_past_four_sources_and_through_later_pdf_pages(self):
        doc = self.board()
        for number in range(5):
            datasets.add(self.service.store, self.owner, doc['id'], f'{number}.csv', f'v\nother{number}\n'.encode())
        source_documents.add(self.service.store, self.owner, doc['id'], 'long.pdf', b'%PDF-long')
        def extract(data, page):
            if page > 14: raise StudioError('No page')
            return {'text': 'late smoke' if page == 14 else 'clear', 'truncated': False}
        with patch.object(source_documents, 'extract_page', side_effect=extract):
            first = source_search.search(self.service.store, self.owner, doc['id'], 'smoke')
            second = source_search.search(self.service.store, self.owner, doc['id'], 'smoke', cursor=first['next_cursor'])
            third = source_search.search(self.service.store, self.owner, doc['id'], 'smoke', cursor=second['next_cursor'])
        self.assertEqual(first['scanned_tables'], 4)
        self.assertEqual(second['scanned_pages'], 12)
        self.assertEqual(third['matches'][0]['page'], 14)
        self.assertIsNone(third['next_cursor'])
