"""Synthetic NASA catalog fixtures, never authentic observations."""
import copy
import hashlib
import json
import threading
import time
import unittest
from unittest.mock import patch
from fireatlas.assistant import nasa_discovery as nasa

C='C123-SYNTHETIC';V='V123-SYNTHETIC';G='G123-SYNTHETIC'
BBOX=[88.4,24.2,88.8,24.6]


def catalog(variables=None,identifier=C):
    entry={'id':identifier,'title':'Synthetic soil moisture catalog','short_name':'TEST','version_id':'1',
           'summary':'Synthetic metadata, not measured soil moisture.','time_start':'2020-01-01T00:00:00Z'}
    if variables is not None:entry['associations']={'variables':variables}
    return json.dumps({'feed':{'entry':[entry]}}).encode(),1


def granules(identifier=G,parent=C,start='2025-04-01T00:00:00Z'):
    return json.dumps({'feed':{'entry':[{'id':identifier,'title':'synthetic.h5','collection_concept_id':parent,
            'time_start':start,'time_end':start} ]}}).encode(),1


def variable(identifier=V,associated=C,units=None):
    return {'meta':{'concept-id':identifier},'umm':{'Name':'soil_moisture','LongName':'Synthetic soil moisture','Units':units},
            'associations':{'collections':[{'concept-id':associated}]}}


def variables(items=None):
    items=items if items is not None else [variable()]
    return json.dumps({'items':items,'hits':len(items)}).encode(),None


class NasaDiscoveryTests(unittest.TestCase):
    def inspect(self,**kwargs):
        return nasa.discover(collection_id=C,bbox=BBOX,start='2025-04-01',end='2025-04-01',**kwargs)

    def test_exact_inspection_retains_original_pages_unknowns_and_associations(self):
        originals=[]
        replies=[catalog([V]),granules(),variables()]
        with patch.object(nasa,'fetch',side_effect=replies) as fetch:
            result=self.inspect(retain=lambda raw,meta:originals.append((raw,meta)))
        self.assertEqual(len(originals),3)
        self.assertTrue(all(meta['sha256']==hashlib.sha256(raw).hexdigest() for raw,meta in originals))
        self.assertEqual(result['collections']['items'][0]['end'],None)
        self.assertEqual(result['variables']['items'][0]['units'],None)
        self.assertTrue(result['variables']['listing_complete'])
        self.assertEqual(result['variables']['items'][0]['association_basis'],'collection_metadata')
        self.assertEqual(result['download_access'],'not_checked')
        self.assertTrue(result['granules']['items'][0]['temporal_scope_checked'])
        self.assertIn('collection_concept_id=C123-SYNTHETIC',fetch.call_args_list[1].args[0])
        nasa.validate_reports([result],[])

    def test_collection_search_keeps_spatial_utc_limits_and_does_not_fetch_children(self):
        raw,_=catalog()
        with patch.object(nasa,'fetch',return_value=(raw,73)) as fetch:
            result=nasa.discover('soil moisture',bbox=BBOX,start='2025-04-01',end='2025-04-01')
        self.assertEqual(fetch.call_count,1)
        url=fetch.call_args.args[0]
        self.assertIn('bounding_box=88.4%2C24.2%2C88.8%2C24.6',url)
        self.assertIn('2025-04-02T00%3A00%3A00Z',url)
        self.assertFalse(result['collections']['listing_complete'])
        self.assertEqual(result['variables']['state'],'not_requested')
        self.assertNotIn('source_utf8',json.dumps(result))
        nasa.validate_reports([result],[])

    def test_unavailable_granules_do_not_discard_returned_variables(self):
        with patch.object(nasa,'fetch',side_effect=[catalog([V]),TimeoutError(),variables()]):result=self.inspect()
        self.assertEqual(result['granules'],nasa.empty('unavailable'))
        self.assertEqual(result['variables']['state'],'returned')
        nasa.validate_reports([result],[])

    def test_zero_and_unknown_counts_are_distinct(self):
        empty=json.dumps({'feed':{'entry':[]}}).encode()
        for total,expected in ((0,True),(None,None)):
            with patch.object(nasa,'fetch',return_value=(empty,total)):result=nasa.discover('synthetic')
            self.assertEqual(result['collections']['reported_hits'],total)
            self.assertEqual(result['collections']['listing_complete'],expected)
            nasa.validate_reports([result],[])

    def test_mismatched_concepts_and_unassociated_variables_are_not_admitted(self):
        with patch.object(nasa,'fetch',return_value=catalog(identifier='C999-SYNTHETIC')) as fetch:
            result=self.inspect();self.assertEqual(fetch.call_count,1)
        self.assertEqual(result['collections']['state'],'unavailable')
        with patch.object(nasa,'fetch',side_effect=[catalog(),granules(parent='C999-SYNTHETIC'),variables([variable(associated='C999-SYNTHETIC')])]):result=self.inspect()
        self.assertEqual(result['granules']['state'],'unavailable')
        self.assertEqual(result['variables']['items'],[])
        self.assertFalse(result['variables']['listing_complete'])

    def test_exact_variable_name_filter_still_checks_collection_membership(self):
        with patch.object(nasa,'fetch',side_effect=[catalog([V,'V999-SYNTHETIC']),granules(),variables()]) as fetch:
            result=self.inspect(variable_name='*soil_moisture*')
        self.assertIn('name=%2Asoil_moisture%2A',fetch.call_args.args[0])
        self.assertIn('keyword=C123-SYNTHETIC',fetch.call_args.args[0])
        self.assertFalse(result['variables']['listing_complete'])
        self.assertEqual(result['variables']['items'][0]['concept_id'],V)
        nasa.validate_reports([result],[])

    def test_inclusive_cmr_next_day_boundary_does_not_become_requested_day_metadata(self):
        with patch.object(nasa,'fetch',side_effect=[catalog([]),granules(start='2025-04-02T00:00:00Z')]):result=self.inspect()
        self.assertEqual(result['granules']['reported_hits'],1)
        self.assertEqual(result['granules']['items'],[])
        self.assertFalse(result['granules']['listing_complete'])
        self.assertTrue(result['variables']['listing_complete'])

    def test_bad_scope_cancel_and_deadline_prevent_network(self):
        for kwargs in ({'bbox':[0,0,0,1]},{'bbox':[0,float('nan'),1,2]},{'bbox':[False,0,1,2]},
                       {'start':'2025-04-01'},{'start':'2020-01-01','end':'2025-01-01'},
                       {'start':'2025-04-02','end':'2025-04-01'},{'collection_id':'https://localhost/secret'},
                       {'collection_id':C},{'variable_name':'*'}):
            with self.subTest(kwargs=kwargs),patch.object(nasa,'fetch') as fetch:
                with self.assertRaises(ValueError):nasa.discover('synthetic',**kwargs)
                fetch.assert_not_called()
        stopped=threading.Event();stopped.set()
        for kwargs in ({'cancel':stopped},{'deadline':time.monotonic()-1}):
            with patch.object(nasa,'fetch') as fetch:
                with self.assertRaises(InterruptedError):nasa.discover('synthetic',**kwargs)
                fetch.assert_not_called()

    def test_cancel_during_transport_is_not_reported_as_unavailable(self):
        stop=threading.Event()
        def fail(*args,**kwargs):stop.set();raise TimeoutError()
        with patch.object(nasa,'fetch',side_effect=fail):
            with self.assertRaises(InterruptedError):nasa.discover('synthetic',cancel=stop)

    def test_portable_identity_and_receipt_mutations_are_rejected(self):
        with patch.object(nasa,'fetch',return_value=catalog()):result=nasa.discover('synthetic')
        source={**nasa.source_cards(result)[0],'id':'R1'}
        result['collections']['items'][0]['reference_id']='R1';nasa.finish(result)
        nasa.validate_reports([result],[source])
        for mutate in (lambda r:r.update(download_access='granted'),lambda r:r['collections']['items'][0].update(reference_id='R99'),
                       lambda r:r['pages'][0].update(url='https://localhost/secret'),lambda r:r.update(retrieved_at='2025-04-01T00:00:00'),
                       lambda r:r['variables'].update(state='returned'),lambda r:r.update(extra='secret')):
            changed=copy.deepcopy(result);mutate(changed);nasa.finish(changed)
            with self.assertRaises(ValueError):nasa.validate_reports([changed],[source])
        changed=copy.deepcopy(result);changed['scope']='Changed'
        with self.assertRaises(ValueError):nasa.validate_reports([changed],[source])

    def test_stream_byte_bound_and_redirects_are_enforced_without_auth(self):
        import io
        class Response(io.BytesIO):headers={}
        class Opener:
            def open(self,request,timeout):
                self.request=request;return Response(b'x'*(nasa.MAX_BYTES+1))
        opener=Opener()
        with patch.object(nasa,'build_opener',return_value=opener):
            with self.assertRaisesRegex(ValueError,'bound'):nasa.fetch('collections.json?keyword=synthetic')
        self.assertEqual(opener.request.full_url,nasa.BASE+'collections.json?keyword=synthetic')
        self.assertNotIn('Authorization',opener.request.headers)
        self.assertIsNone(nasa.NoRedirect().redirect_request(None,None,None,None,None,None))
