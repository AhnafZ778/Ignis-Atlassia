import json
from pathlib import Path
from tests.studio_support import StudioCase

class EnvironmentCaptureTest(StudioCase):
    def test_save_and_provenance(self):
        directory=Path(__file__).resolve().parents[1]/'site/data/environment-analogues/v1'
        manifest=json.loads((directory/'manifest.json').read_text());identity=manifest['files']['park.json']['sha256']
        study={'case':'park-2024','year':2024,'month':7,'bbox':[-122.0,39.5,-121.3,40.5],'region':'norcal','start':'2024-07-25','end':'2024-07-28','as_of':'2024-07-28','day':'2024-07-25','series':'modis','source':'MODIS_SP'}
        ctx={'schema':'fireatlas-jarvis-context-v1','surface':'research','origin_instance_id':'environment-test','origin_tab_id':'env-tab','context_revision':1,'study_selection':study,'active_view':{'kind':'chart','operation':'environment_analogues','source':'MODIS_SP','arguments':{'cell_id':'1-0','expected_environment_sha256':identity}},'destination':{'intent':'new-board'},'selected_object_ids':[],'result_refs':[]}
        out=self.service.commands.submit(self.owner,{'recipe':'visualization_to_investigation','context':ctx,'arguments':{'layout':'minimal'}},'environment-save',background=False)
        self.assertEqual(out['status'],'awaiting_view_ack',out)
        doc=self.service.get_document(self.owner,out['outputs']['document_id']);snap=next(iter(doc['snapshots'].values()))
        self.assertEqual(snap['operation'],'environment_analogues');self.assertEqual(snap['scope']['start'],'2024-07-25');self.assertEqual(snap['scope']['end'],'2024-07-28');self.assertEqual(snap['scope']['source'],'MODIS_SP')
        receipt=self.service.snapshot_receipt(self.owner,doc['id'],snap['id'])['receipt'];self.assertEqual(receipt['payload']['target']['id'],'1-0');self.assertEqual(len(receipt['payload']['matches']),5)
        self.assertTrue(self.service.snapshot_report(self.owner,doc['id'],snap['id'])['verification']['verified'])
