"""Synthetic worker handoff tests; these do not verify provider origin."""
import hashlib
import fcntl
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from scripts import preflight_monthly_publication as preflight


class MonthlyPreflightTests(unittest.TestCase):
    def test_real_worker_under_parent_lock(self):
        from fireatlas import comparability, comparability_v2, monthly_source_provenance, qualification
        from fireatlas.core import connect
        from tests.test_transfer_provenance import TransferProvenanceTests
        fixture=TransferProvenanceTests('test_verified_capture_and_idempotent_reimport')
        fixture.setUp();self.addCleanup(fixture.doCleanups)
        work=fixture.root;fixture.root=work/'campaign';fixture.root.mkdir()
        capture=fixture.populate()
        with connect(fixture.root/'observations.sqlite3') as db:
            inputs=comparability.capture(db,'norcal')
        inputs['versions']=['6.03','2']
        bundle=comparability_v2.analyze(inputs,experimental=qualification.experimental_review('monthly'))
        proof=monthly_source_provenance.verify(bundle,capture,fixture.root/'observations.sqlite3',fixture.root)
        proof_path=work/'monthly-provenance-v1/proof.json';proof_path.parent.mkdir()
        proof_path.write_text(json.dumps(proof))
        entry={'artifact':'monthly-provenance-v1/proof.json','sha256':hashlib.sha256(proof_path.read_bytes()).hexdigest(),
               'monthly_input_sha256':proof['monthly_input_sha256'],'monthly_result_sha256':proof['monthly_result_sha256']}
        key=qualification.digest({'region':'norcal','versions':('6.03','2')})[:16]
        artifact=work/'results/cohorts/monthly.json';artifact.parent.mkdir(parents=True);artifact.write_text(json.dumps(bundle))
        (work/'successor-evidence.json').write_text(json.dumps({'monthly_provenance':{key:entry}}))
        (work/'cohort-results.json').write_text(json.dumps({'records':[{'kind':'monthly','region':'norcal','versions':['6.03','2'],'artifact':'results/cohorts/monthly.json'}]}))
        script=Path(preflight.__file__).resolve()
        with (fixture.root/'.acquisition.lock').open('a') as guard:
            fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
            result=subprocess.run([sys.executable,str(script),'--work',str(work),'--cohort',key],capture_output=True,text=True,timeout=30,check=True)
            record=json.loads(result.stdout)
            self.assertEqual('verified-recount',record['status'])
            self.assertTrue(record['source_files']);self.assertTrue(record['plan_files'])
            preflight.verify_sources(work,record)
            (fixture.root/'plans/extra.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'Plan inventory changed'):preflight.verify_sources(work,record)

    def test_source_and_database_changes_fail_final_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory);campaign=work/'campaign';campaign.mkdir()
            database=campaign/'observations.sqlite3';database.write_bytes(b'database')
            source=campaign/'source.csv';source.write_bytes(b'original')
            record={'source_files':{'source.csv':hashlib.sha256(b'original').hexdigest()},
                    'database_files':preflight.database_hashes(work),'plan_files':[]}
            preflight.verify_sources(work,record)
            source.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Original source changed'):preflight.verify_sources(work,record)
            source.write_bytes(b'original');database.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'database changed'):preflight.verify_sources(work,record)

    def test_database_wal_appearance_and_path_escape_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory);campaign=work/'campaign';campaign.mkdir()
            (campaign/'observations.sqlite3').write_bytes(b'database')
            record={'source_files':{},'database_files':preflight.database_hashes(work),'plan_files':[]}
            (campaign/'observations.sqlite3-wal').write_bytes(b'new')
            with self.assertRaisesRegex(ValueError,'database changed'):preflight.verify_sources(work,record)
            record['source_files']={'../outside':'a'*64}
            (work/'outside').write_bytes(b'outside')
            with self.assertRaisesRegex(ValueError,'Original source changed'):preflight.verify_sources(work,record)

    def test_added_plan_invalidates_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory);campaign=work/'campaign';campaign.mkdir()
            (campaign/'observations.sqlite3').write_bytes(b'database')
            record={'source_files':{},'database_files':preflight.database_hashes(work),'plan_files':[]}
            preflight.verify_sources(work,record)
            (campaign/'plans').mkdir();(campaign/'plans/new.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'Plan inventory changed'):preflight.verify_sources(work,record)


if __name__=='__main__':unittest.main()
