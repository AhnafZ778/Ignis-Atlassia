"""Synthetic exact-byte daily release checks; no scientific validation implied."""
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit,parse_qs
from fireatlas.qualification import digest
from scripts import verify_daily_research_release as verify


class DailyReleaseVerifierTests(unittest.TestCase):
 def test_exact_cohorts_and_endpoint_bytes_fail_closed(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);work=root/'work';site=root/'site';work.mkdir();(work/'campaign').mkdir();(work/'campaign/.acquisition.lock').touch();pub=site/'data/qualification';pub.mkdir(parents=True)
   release='a'*64;(pub/'current.json').write_text(json.dumps({'release_id':release}));registrations={k:{} for k,_,_,_ in verify.KINDS};files={}
   for region,cohort in [('norcal','b'*16),('punjab-haryana','c'*16)]:
    original={'region':region,'versions':['6.03','2'],'synthetic':False};original['result_sha256']=digest(original)
    name='cohort-daily/'+cohort+'.json.gz';files[name]=gzip.compress(json.dumps(original).encode())
    item={'id':cohort,'region':region,'versions':['6.03','2'],'reproduction_artifact':name,'result_sha256':original['result_sha256']}
    for registry,field,family,prefix in verify.KINDS:
     directory=work/prefix;directory.mkdir(exist_ok=True);p=directory/(cohort+'.json');content=(region+field).encode();p.write_bytes(content)
     name=family+'/'+cohort+('.json' if field=='diagnostics' else '.json.gz');files[name]=content
     registrations[registry][cohort]={'artifact':str(p.relative_to(work)),'sha256':hashlib.sha256(content).hexdigest()}
     item[field]={'state':'experimental','reproduction_artifact':name,'scientific_admission' if field=='diagnostics' else 'estimates_admitted':False}
    files['daily-cohorts/'+region+'.json']=json.dumps({'region':region,'entries':[item]}).encode()
   (work/'successor-evidence.json').write_text(json.dumps(registrations))
   def read(_root,name,_release):return files[name]
   def route(url,limit=verify.LIMIT):
    parsed=urlsplit(url)
    if parsed.path.startswith('/api/'):
     family=parsed.path.rsplit('/',1)[1];cohort=parse_qs(parsed.query)['id'][0];name=family+'/'+cohort+('.json' if family=='daily-diagnostics' else '.json.gz')
    else:name=parsed.path.split('/releases/'+release+'/')[1]
    return files[name]
   def checked(_work,entry,_original,_root):return {},verify.qualification_successors.frozen_file(work/entry['artifact'])
   with patch.object(verify.qualification_publication,'read',side_effect=read),patch.object(verify,'fetch',side_effect=route),patch.object(verify.qualification_successors,'daily_hybrid_asset',side_effect=checked),patch.object(verify.qualification_successors,'daily_neighbors_asset',side_effect=checked),patch.object(verify.qualification_successors,'daily_diagnostics_asset',side_effect=checked):
    report=verify.verify(site,work,'http://localhost:8127','http://localhost:8130');self.assertTrue(report['verified']);self.assertEqual(len(report['regions']),2)
    with patch.object(verify,'fetch',return_value=b'wrong'):
     with self.assertRaisesRegex(ValueError,'static or API bytes'):verify.verify(site,work,'http://localhost:8127','http://localhost:8130')
    changed=json.loads(files['daily-cohorts/norcal.json']);changed['entries'][0]['neighbors']['estimates_admitted']=True;files['daily-cohorts/norcal.json']=json.dumps(changed).encode()
    with self.assertRaisesRegex(ValueError,'admission'):verify.verify(site,work,'http://localhost:8127','http://localhost:8130')
    changed['entries'][0]['neighbors']['estimates_admitted']=False;files['daily-cohorts/norcal.json']=json.dumps(changed).encode()
    saved=registrations['daily_neighbors'].pop('b'*16);(work/'successor-evidence.json').write_text(json.dumps(registrations))
    with self.assertRaisesRegex(ValueError,'missing or pending'):verify.verify(site,work,'http://localhost:8127','http://localhost:8130')
    registrations['daily_neighbors']['b'*16]=saved;(work/'successor-evidence.json').write_text(json.dumps(registrations))
    p=work/saved['artifact'];original_bytes=p.read_bytes();p.write_bytes(b'tampered')
    with self.assertRaisesRegex(ValueError,'registered evidence'):verify.verify(site,work,'http://localhost:8127','http://localhost:8130')
    p.write_bytes(original_bytes)
    with patch.object(verify.qualification_successors,'daily_hybrid_asset',return_value=None):
     with self.assertRaisesRegex(ValueError,'does not match'):verify.verify(site,work,'http://localhost:8127','http://localhost:8130')
    source_name='cohort-daily/'+'b'*16+'.json.gz';source_before=files[source_name];source=json.loads(gzip.decompress(source_before));source['region']='punjab-haryana';files[source_name]=gzip.compress(json.dumps(source).encode())
    with self.assertRaisesRegex(ValueError,'source identity'):verify.verify(site,work,'http://localhost:8127','http://localhost:8130')
    files[source_name]=source_before
    def changing_route(url,limit=verify.LIMIT):
     content=route(url);(pub/'current.json').write_text(json.dumps({'release_id':'d'*64}));return content
    with patch.object(verify,'fetch',side_effect=changing_route):
     with self.assertRaisesRegex(ValueError,'Release changed'):verify.verify(site,work,'http://localhost:8127','http://localhost:8130')


if __name__=='__main__':unittest.main()
