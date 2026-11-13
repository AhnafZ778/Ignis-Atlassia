import unittest
from unittest.mock import patch

from fireatlas.assistant.web_references import requested_query, search_answer, search_references, research_wording


class WebReferenceTests(unittest.TestCase):
    def test_shared_catalog_keeps_handles_and_reports_omitted_sources_at_portable_bound(self):
        from fireatlas.assistant.web_references import register_sources
        catalog=[{'id':'R'+str(n+1),'title':str(n),'url':'https://example.org/'+str(n)} for n in range(11)]
        existing=dict(catalog[3]);sources=[{'title':'New','url':'https://example.org/new'},{'title':'Omitted','url':'https://example.org/omitted'}]
        self.assertTrue(register_sources(catalog,sources))
        self.assertEqual(len(catalog),12);self.assertEqual(catalog[3],existing)
        self.assertEqual(catalog[-1]['id'],'R12')
        self.assertFalse(register_sources(catalog,[sources[0]]))
        self.assertEqual(len(catalog),12)

    def test_metadata_platform_identifiers_do_not_admit_measurement_numbers(self):
        sources=[{'id':'R1','title':'Sentinel-3 intercomparison with the 375 m VIIRS product'}]
        text=research_wording('Review Sentinel-3 and 375 m VIIRS methods (R1).',sources,['R1'])
        self.assertFalse(any(character.isdigit() for character in text))
        for text in ('There were 375 records.','There were 3 fires.','Use Sentinel-2.','R99 says so.'):
            self.assertTrue(any(character.isdigit() for character in research_wording(text,sources,['R1'])))

    def test_explicit_search_uses_only_user_terms(self):
        self.assertEqual(requested_query('Find papers on VIIRS detection and pin the results'), 'VIIRS detection')
        self.assertEqual(requested_query('Could you look up NASA FIRMS online?'), 'NASA FIRMS')
        self.assertIsNone(requested_query('Search for rainfall in the attached PDF'))
        self.assertIsNone(requested_query('Label the saved heatmap'))

    def test_result_is_linked_public_metadata_and_scholarly_stays_on_crossref(self):
        source={'title':'Fire study','url':'https://doi.org/10.1234/fire','snippet':'Journal','provider':'Crossref'}
        with patch('fireatlas.assistant.web_references._crossref',return_value=[source,source]) as crossref, patch(
            'fireatlas.assistant.web_references._wikipedia'
        ) as wiki:
            result=search_answer('Find papers on wildfire','wildfire')
        crossref.assert_called_once_with('wildfire')
        wiki.assert_not_called()
        self.assertEqual(result['web_sources'],[source])
        self.assertEqual(result['claims'],[])

    def test_unreachable_provider_is_reported(self):
        with patch.dict('os.environ',{'OLLAMA_API_KEY':''}), patch(
            'fireatlas.assistant.web_references._crossref',side_effect=TimeoutError
        ), patch('fireatlas.assistant.web_references._wikipedia',side_effect=TimeoutError):
            with patch('fireatlas.assistant.web_references._nasa',side_effect=TimeoutError):
                with self.assertRaisesRegex(ValueError,'temporarily unavailable'):
                    search_references('wildfire')

    def test_real_doi_and_nasa_collection_parsers_keep_valid_identifiers_and_strip_markup(self):
        from fireatlas.assistant.web_references import _crossref, _nasa
        with patch('fireatlas.assistant.web_references._get_json',return_value={'message':{'items':[
            {'title':['<i>VIIRS wildfire detection</i>'],'DOI':'10.1234/viirs.2024','container-title':['Journal'],'published':{'date-parts':[[2024]]}},
            {'title':['Invalid'],'DOI':'javascript:bad'}]}}):
            found=_crossref('VIIRS');self.assertEqual(len(found),1)
            self.assertEqual(found[0]['url'],'https://doi.org/10.1234/viirs.2024')
            self.assertEqual(found[0]['title'],'VIIRS wildfire detection')
        with patch('fireatlas.assistant.web_references._get_json',return_value={'feed':{'entry':[
            {'id':'C1234-LPCLOUD','title':'NASA vegetation','summary':'<p>Collection metadata</p>'},
            {'id':'http://localhost','title':'Bad'}]}}):
            found=_nasa('vegetation');self.assertEqual(len(found),1)
            self.assertEqual(found[0]['provider'],'NASA Earthdata CMR')

    def test_stopped_search_never_contacts_a_provider(self):
        import threading
        stopped=threading.Event();stopped.set()
        with patch('fireatlas.assistant.web_references._get_json') as request:
            with self.assertRaises(InterruptedError):search_references('wildfire',cancel=stopped)
        request.assert_not_called()

    def test_exact_doi_lookup_cannot_return_unrelated_bibliographic_matches(self):
        from fireatlas.assistant.web_references import _crossref
        article={'DOI':'10.1234/fire','title':['Exact original methods'],'container-title':['Journal'],'published':{'date-parts':[[2025]]}}
        for query in ('10.1234/fire','https://doi.org/10.1234/fire'):
            with self.subTest(query=query),patch('fireatlas.assistant.web_references._get_json',return_value={'message':article}) as get:
                sources=_crossref(query)
                self.assertEqual(get.call_args.args[0],'https://api.crossref.org/works/10.1234%2Ffire')
                self.assertEqual(sources[0]['url'],'https://doi.org/10.1234/fire')
        with patch('fireatlas.assistant.web_references._get_json',return_value={'message':{**article,'DOI':'10.9999/other'}}):
            with self.assertRaises(ValueError):_crossref('10.1234/fire')
