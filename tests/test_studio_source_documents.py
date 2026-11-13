import unittest
import shutil
from unittest.mock import patch

from tests.studio_support import StudioCase
from fireatlas.studio.errors import Conflict, LimitExceeded, NotFound, StudioError
from fireatlas.studio.source_documents import add, extract_page, list_documents, read


def simple_pdf(text=b'Document evidence example'):
    stream=b'BT /F1 18 Tf 72 720 Td ('+text+b') Tj ET'
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
             b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
             b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
             b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
    data=b'%PDF-1.4\n';offsets=[]
    for index,obj in enumerate(objects,1):
        offsets.append(len(data));data+=str(index).encode()+b' 0 obj\n'+obj+b'\nendobj\n'
    start=len(data);data+=b'xref\n0 6\n0000000000 65535 f \n'
    data+=b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets)
    return data+b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n'+str(start).encode()+b'\n%%EOF\n'


class SourceDocumentTests(StudioCase):
    def test_missing_pdf_reader_fails_clearly(self):
        with patch('fireatlas.studio.source_documents.shutil.which',return_value=None):
            with self.assertRaises(StudioError):extract_page(simple_pdf(),1)

    @unittest.skipUnless(shutil.which('pdftotext'), 'Poppler is optional')
    def test_real_pdf_page_extraction(self):
        result=extract_page(simple_pdf(),1)
        self.assertIn('Document evidence example',result['text'])
        self.assertFalse(result['truncated'])
        with self.assertRaises(StudioError):extract_page(simple_pdf(),21)
    def test_native_package_restores_original_and_remaps_document_link(self):
        board=self.board();data=b'%PDF-1.4\nsource\n%%EOF'
        source=add(self.service.store,self.owner,board['id'],'paper.pdf',data)
        element={'id':'paper','type':'text','text':'Paper','x':0,'y':0,'width':20,'height':20,
                 'customData':{'fireatlas':{'documentId':board['id'],'sourceDocumentId':source['id'],'sourceDocumentHash':source['sha256'],'page':1}}}
        board=self.service.transact(self.owner,board['id'],{'base_revision':board['revision'],'ops':[{'op':'patch_whiteboard','changes':[{'kind':'element','id':'paper','position':0,'value':element}]}]})
        with patch('fireatlas.studio.portability.StorageBudget.check',return_value={}):
            job=self.service.portability.submit(self.owner,board['id'],{'format':'native'},background=False)
        self.assertEqual(job['status'],'completed',job)
        path,_=self.service.portability.download(self.owner,job['id'])
        restored=self.service.portability.restore(self.other,path)['document']
        meta=self.service.store.whiteboard(self.other,restored['id'])['elements'][0]['customData']['fireatlas']
        self.assertEqual(meta['documentId'],restored['id'])
        self.assertNotEqual(meta['sourceDocumentId'],source['id'])
        self.assertEqual(meta['page'],1)
        self.assertEqual(read(self.service.store,self.other,restored['id'],meta['sourceDocumentId'])[1],data)

    def test_retry_rejects_documents_changed_after_export_preparation(self):
        board=self.add_card(self.board(),'note',kind='text',text='note')
        with patch('fireatlas.studio.portability.StorageBudget.check',return_value={}),patch('fireatlas.studio.portability.board_svg',side_effect=RuntimeError('interrupted')):
            job=self.service.portability.submit(self.owner,board['id'],{'format':'native'},background=False)
        self.assertEqual(job['status'],'failed')
        add(self.service.store,self.owner,board['id'],'paper.pdf',b'%PDF-test')
        with self.assertRaises(Conflict):self.service.portability.retry(self.owner,job['id'])

    def test_package_keeps_unplaced_documents_and_rejects_missing_reference(self):
        board=self.add_card(self.board(),'note',kind='text',text='note');data=b'%PDF-unplaced'
        source=add(self.service.store,self.owner,board['id'],'paper.pdf',data)
        with patch('fireatlas.studio.portability.StorageBudget.check',return_value={}):
            job=self.service.portability.submit(self.owner,board['id'],{'format':'native'},background=False)
        self.assertEqual(job['status'],'completed',job)
        path,_=self.service.portability.download(self.owner,job['id'])
        restored=self.service.portability.restore(self.other,path)
        self.assertEqual(read(self.service.store,self.other,restored['document']['id'],restored['id_map'][source['id']])[1],data)
        element={'id':'broken','type':'text','text':'Paper','x':0,'y':0,'width':20,'height':20,
                 'customData':{'fireatlas':{'documentId':board['id'],'sourceDocumentId':'missing'}}}
        self.service.transact(self.owner,board['id'],{'base_revision':board['revision'],'ops':[{'op':'patch_whiteboard','changes':[{'kind':'element','id':'broken','position':0,'value':element}]}]})
        with self.assertRaises(StudioError):self.service.portability.capture(self.owner,board['id'])

    def test_document_bytes_are_private_immutable_and_idempotent(self):
        board = self.board()
        data = b'%PDF-1.4\nexample source bytes\n%%EOF'
        first = add(self.service.store, self.owner, board['id'], 'paper.pdf', data)
        second = add(self.service.store, self.owner, board['id'], 'renamed.pdf', data)
        self.assertTrue(second['existing'])
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(read(self.service.store, self.owner, board['id'], first['id'])[1], data)
        self.assertEqual(list_documents(self.service.store, self.owner, board['id'])[0]['sha256'], first['sha256'])
        with self.assertRaises(NotFound):
            read(self.service.store, self.other, board['id'], first['id'])
        with self.assertRaises(NotFound):
            add(self.service.store, self.other, board['id'], 'paper.pdf', data)

    def test_rejects_invalid_or_excessive_content_and_corruption(self):
        board = self.board()
        with self.assertRaises(StudioError):
            add(self.service.store, self.owner, board['id'], 'paper.pdf', b'not a PDF')
        with self.assertRaises(LimitExceeded):
            add(self.service.store, self.owner, board['id'], 'paper.pdf', b'%PDF-' + b'x' * (10 * 1024 * 1024))
        source = add(self.service.store, self.owner, board['id'], 'paper.pdf', b'%PDF-test')
        with self.service.store.connection(write=True) as db:
            db.execute('UPDATE source_documents SET content=? WHERE id=?', (b'%PDF-modified', source['id']))
        with self.assertRaises(StudioError):
            read(self.service.store, self.owner, board['id'], source['id'])
