"""Mocked Miro transports; these tests never publish externally."""
import copy
import os
from unittest.mock import patch
from tests.studio_support import StudioCase
from fireatlas.studio.miro import Miro
from fireatlas.studio.errors import Conflict, Forbidden

class MiroTests(StudioCase):
    def setUp(self):
        super().setUp();self.env=patch.dict(os.environ,{'FIREATLAS_MIRO_ACCESS_TOKEN':'test-token','FIREATLAS_MIRO_BOARD_IDS':'allowed'},clear=False);self.env.start();self.addCleanup(self.env.stop)
        self.calls=[];self.items={};self.uncertain=False
        def transport(method,path,body=None,upload=None):
            self.calls.append((method,path,copy.deepcopy(body),bool(upload)))
            if method=='GET':
                if '/items?' in path:return {'data':list(self.items.values())}
                identifier=path.split('/')[-1]
                return copy.deepcopy(self.items[identifier]) if identifier in self.items else {'id':'allowed'}
            if method=='PATCH':
                identifier=path.split('/')[-1];self.items[identifier].update(copy.deepcopy(body));return copy.deepcopy(self.items[identifier])
            identifier='remote-'+str(len(self.items));item={'id':identifier,**copy.deepcopy(body)};self.items[identifier]=item
            if self.uncertain and path.endswith('/shapes'):
                self.uncertain=False;raise Conflict('Mock lost creation response.',code='miro-uncertain')
            return copy.deepcopy(item)
        self.adapter=Miro(self.service,transport);self.service.miro=self.adapter
    def board_with_connections(self):
        doc=self.board();doc=self.add_card(doc,'a',kind='text',text='First');doc=self.add_card(doc,'b',kind='text',text='Second')
        return self.service.transact(self.owner,doc['id'],{'base_revision':doc['revision'],'ops':[{'op':'connect','connection':{'id':'link','source':'a','target':'b','kind':'context'}}]})
    def test_explicit_destination_and_endpoint_mapping(self):
        doc=self.board_with_connections()
        with self.assertRaises(Forbidden):self.adapter.submit(self.owner,doc['id'],{'board_id':'another'},background=False)
        job=self.adapter.submit(self.owner,doc['id'],{'board_id':'allowed'},key='one',background=False)
        self.assertEqual(job['status'],'completed',job)
        self.assertTrue(any(c[1].endswith('/frames') for c in self.calls));self.assertTrue(any(c[1].endswith('/shapes') for c in self.calls))
        connector=next(c[2] for c in self.calls if c[1].endswith('/connectors'))
        self.assertNotEqual(connector['startItem']['id'],connector['endItem']['id'])
        count=len(self.items);again=self.adapter.submit(self.owner,doc['id'],{'board_id':'allowed'},key='one',background=False)
        self.assertEqual(again['id'],job['id']);self.assertEqual(len(self.items),count)
    def test_uncertain_create_reconciles_without_duplicate(self):
        doc=self.board_with_connections();self.uncertain=True
        job=self.adapter.submit(self.owner,doc['id'],{'board_id':'allowed'},background=False)
        self.assertEqual(job['status'],'partial');self.assertEqual(len(self.items),2)
        resumed=self.adapter.resume(self.owner,job['id'],background=False)
        self.assertEqual(resumed['status'],'completed',resumed);self.assertEqual(len(self.items),4)
        self.assertEqual(sum(c[0]=='POST' and c[1].endswith('/shapes') for c in self.calls),2)
    def test_ambiguous_remote_outcome_and_participant_changes(self):
        doc=self.board_with_connections();self.uncertain=True
        job=self.adapter.submit(self.owner,doc['id'],{'board_id':'allowed'},background=False)
        duplicate=copy.deepcopy(self.items['remote-1']);duplicate['id']='ambiguous';self.items['ambiguous']=duplicate
        self.assertEqual(self.adapter.resume(self.owner,job['id'],background=False)['status'],'partial')
        self.assertEqual(sum(c[0]=='POST' and c[1].endswith('/shapes') for c in self.calls),1)
        # Separate successful transfer; update preserves participant edits.
        first=self.adapter.submit(self.owner,doc['id'],{'board_id':'allowed'},background=False)
        remote=self.adapter.item(first['id'],'a')['remote_id'];self.items[remote]['data']['content']='Collaborator edit'
        updated=self.adapter.submit(self.owner,doc['id'],{'board_id':'allowed','mode':'update-existing','previous_job_id':first['id']},background=False)
        self.assertEqual(updated['status'],'partial');self.assertEqual(self.items[remote]['data']['content'],'Collaborator edit')

    def test_http_rate_limits_are_bounded_and_uncertain_creates_are_not_repeated(self):
        from urllib.error import HTTPError,URLError
        from fireatlas.studio.errors import StudioError
        limited=HTTPError('https://api.miro.com/v2/boards/allowed/shapes',429,'Rate limited',{'Retry-After':'100'},None)
        with patch('fireatlas.studio.miro.urlopen',side_effect=limited) as transport,patch('fireatlas.studio.miro.time.sleep') as sleep:
            with self.assertRaises(StudioError):self.adapter.request('POST','/boards/allowed/shapes',{'data':{'content':'Test'}})
            self.assertEqual(transport.call_count,3);self.assertEqual([c.args[0] for c in sleep.call_args_list],[10,10])
        with patch('fireatlas.studio.miro.urlopen',side_effect=URLError('Uncertain completion')) as transport:
            with self.assertRaises(Conflict):self.adapter.request('POST','/boards/allowed/shapes',{'data':{'content':'Test'}})
            self.assertEqual(transport.call_count,1)

    def test_file_upload_uses_embedded_bytes_and_enforces_the_api_size_limit(self):
        from unittest.mock import MagicMock
        from fireatlas.studio.errors import StudioError
        response=MagicMock();response.__enter__.return_value.read.return_value=b'{"id":"image-id"}'
        with patch('fireatlas.studio.miro.urlopen',return_value=response) as transport:
            saved=self.adapter.request('POST','/boards/allowed/images',{'data':{'title':'Frozen map'}},upload=(b'bounded-image-bytes','image/png'))
            request=transport.call_args.args[0]
            self.assertEqual(saved['id'],'image-id');self.assertEqual(request.full_url,'https://api.miro.com/v2/boards/allowed/images')
            self.assertIn(b'name="resource"',request.data);self.assertIn(b'name="data"',request.data);self.assertIn(b'bounded-image-bytes',request.data)
            self.assertIn('multipart/form-data',request.get_header('Content-type'));self.assertNotIn(b'private',request.data)
        with patch('fireatlas.studio.miro.urlopen') as transport:
            with self.assertRaises(StudioError):self.adapter.request('POST','/boards/allowed/images',{'data':{}},upload=(b'x'*6_000_001,'image/png'))
            transport.assert_not_called()
