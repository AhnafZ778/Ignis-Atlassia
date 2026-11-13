"""Synthetic protocol fixtures; actual provider checks are recorded separately."""
import hashlib,json,threading,time,unittest
from unittest.mock import patch
from fireatlas.assistant.public_reading import read_reference,MAX_RESPONSE
from fireatlas.assistant.contracts import digest
SOURCE={'id':'R1','title':'Synthetic wildfire methods','url':'https://doi.org/10.1234/fire'}
META=json.dumps({'resultList':{'result':[{'doi':'10.1234/fire','pmcid':'PMC123','isOpenAccess':'Y','license':'CC BY','abstractText':'An original abstract.'}]}}).encode()
ARTICLE=b'<article><front><article-meta><article-id pub-id-type="doi">10.1234/fire</article-id><abstract><p>Original abstract.</p></abstract></article-meta></front><body><sec><title>Methods</title><p>Match independent fire references and cloud masks.</p><p>Keep unknown observation opportunities unknown.</p></sec></body></article>'
class PublicReadingTests(unittest.TestCase):
 def test_reads_original_sections_and_binds_hashes(self):
  with patch('fireatlas.assistant.public_reading.fetch',side_effect=[META,ARTICLE]) as fetch:
   report=read_reference(SOURCE,focus='methods cloud')
  self.assertEqual(report['status'],'article_passages');self.assertEqual(report['license'],'CC BY')
  self.assertEqual(report['content_sha256'],hashlib.sha256(ARTICLE).hexdigest())
  self.assertTrue(any(p['section']=='Methods' and p['text']=='Match independent fire references and cloud masks.' for p in report['passages']))
  self.assertEqual(report['sha256'],digest({k:v for k,v in report.items() if k!='sha256'}))
  self.assertIn('DOI%3A%2210.1234%2Ffire%22',fetch.call_args_list[0].args[0])
 def test_mismatched_original_identity_only_allows_matching_metadata_abstract(self):
  with patch('fireatlas.assistant.public_reading.fetch',side_effect=[META,ARTICLE.replace(b'10.1234/fire',b'10.9999/other')]):report=read_reference(SOURCE)
  self.assertEqual(report['status'],'abstract');self.assertNotIn('content_sha256',report)
  self.assertEqual(report['passages'][0]['text'],'An original abstract.')
 def test_closed_text_or_missing_article_has_explicit_scope(self):
  for record in ({'doi':'10.1234/fire','isOpenAccess':'N','abstractText':'Abstract only.'},{'doi':'10.9999/other','isOpenAccess':'Y'}):
   with self.subTest(record=record),patch('fireatlas.assistant.public_reading.fetch',return_value=json.dumps({'resultList':{'result':[record]}}).encode()) as fetch:
    report=read_reference(SOURCE);self.assertEqual(fetch.call_count,1)
    self.assertEqual(report['status'],'abstract' if record.get('abstractText') else 'unavailable')
 def test_rejects_arbitrary_urls_without_fetching(self):
  for url in ('http://doi.org/10.1234/fire','https://localhost/private','https://doi.org/10.1234/fire?secret=x','https://doi.org/../../private'):
   with self.subTest(url=url),patch('fireatlas.assistant.public_reading.fetch') as fetch:
    with self.assertRaises(ValueError):read_reference({**SOURCE,'url':url})
    fetch.assert_not_called()
 def test_unsafe_xml_does_not_become_article_passages(self):
  with patch('fireatlas.assistant.public_reading.fetch',side_effect=[META,b'<!DOCTYPE article [<!ENTITY x "bad">]><article>&x;</article>']):report=read_reference(SOURCE)
  self.assertEqual(report['status'],'abstract')
 def test_cancel_and_deadline_propagate(self):
  cancel=threading.Event();cancel.set()
  for kwargs in ({'cancel':cancel},{'deadline':time.monotonic()-1}):
   with self.subTest(kwargs=kwargs),patch('fireatlas.assistant.public_reading.fetch',side_effect=InterruptedError()):
    with self.assertRaises(InterruptedError):read_reference(SOURCE,**kwargs)
 def test_full_paragraph_truncation_is_explicit_and_hashes_original(self):
  text='original '*300
  article=ARTICLE.replace(b'Match independent fire references and cloud masks.',text.encode())
  with patch('fireatlas.assistant.public_reading.fetch',side_effect=[META,article]):report=read_reference(SOURCE,focus='original')
  passage=next(p for p in report['passages'] if p['truncated'])
  self.assertEqual(len(passage['text']),1500);self.assertEqual(passage['paragraph_sha256'],hashlib.sha256(text.strip().encode()).hexdigest())
 def test_portable_statuses_bind_identity_and_reject_tampering(self):
  import copy
  from fireatlas.assistant.public_reading import validate_reports
  for metadata,article in ((META,ARTICLE),(META,None),(b'{"resultList":{"result":[]}}',None)):
   with patch('fireatlas.assistant.public_reading.fetch',side_effect=[metadata,article] if article else [metadata,OSError()]):report=read_reference(SOURCE)
   validate_reports([report],[SOURCE])
   for field,bad in (('doi',[]),('source_id',[]),('url','https://doi.org/10.9999/other')):
    changed=copy.deepcopy(report);changed[field]=bad;changed['sha256']=digest({k:v for k,v in changed.items() if k!='sha256'})
    with self.subTest(status=report['status'],field=field),self.assertRaises(ValueError):validate_reports([changed],[SOURCE])
 def test_fetch_refuses_redirects_and_oversized_payloads(self):
  import io
  from fireatlas.assistant.public_reading import fetch,NoRedirect
  self.assertIsNone(NoRedirect().redirect_request(None,None,None,None,None,None))
  with patch('fireatlas.assistant.public_reading.build_opener') as opener:
   opener.return_value.open.return_value.__enter__.return_value=io.BytesIO(b'x'*(MAX_RESPONSE+1))
   with self.assertRaises(ValueError):fetch('PMC123/fullTextXML')
 def test_prose_punctuation_resolves_only_to_owned_doi_identity(self):
  from fireatlas.assistant.public_reading import requested_urls
  known=['https://doi.org/10.1234/fire','https://doi.org/10.1234/ending.)']
  for text in ('Read https://doi.org/10.1234/fire.','Read [methods](https://doi.org/10.1234/fire).','Read `https://doi.org/10.1234/fire`.'):
   self.assertEqual(requested_urls(text,known),[known[0]])
  self.assertEqual(requested_urls('Read https://doi.org/10.1234/ending.)',known),[known[1]])
  self.assertEqual(requested_urls('Read https://doi.org/10.1234/fire.evil.',known),['https://doi.org/10.1234/fire.evil.'])
