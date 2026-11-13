import json
from pathlib import Path
from fireatlas.studio.prompts import submit
try:
    from studio_support import StudioCase
except ImportError:
    from .studio_support import StudioCase

class FindingStudioTests(StudioCase):
    def test_alternatives_keep_separate_immutable_values_and_existing_cards(self):
        data=json.loads((Path(__file__).resolve().parents[1]/'site/data/finding-comparisons/v1/norcal.json').read_text())
        pair=next(p for p in data['pairs'] if p['protocol']=='forward')
        year=pair['years'][1];month=pair['month']; date=pair['dates'][1]
        study={'year':year,'month':month,'bbox':data['region']['bbox'],'region':'norcal','start':date+'-01','end':date+'-28','as_of':date+'-28','series':'joint','source':'joint'}
        def request(series,destination,revision):
            return {'message':'Save this study on Canvas.','destination':destination,'context':{'schema':'fireatlas-jarvis-context-v1','surface':'research','origin_instance_id':'finding-test','origin_tab_id':'finding-tab','context_revision':revision,'study_selection':study,'active_view':{'kind':'chart','operation':'finding_comparison','source':'joint','caption':'Two-period comparison','arguments':{'finding_month':month,'finding_first_year':pair['years'][0],'finding_second_year':year,'expected_finding_sha256':data['result_sha256'],'finding_series':series}},'destination':destination,'result_refs':[],'selected_object_ids':[]}}
        first=submit(self.service,self.owner,request('modis',{'intent':'new-board'},1),'finding-one',background=False)['command']
        self.assertEqual(first['status'],'awaiting_view_ack',first)
        did=first['outputs']['document_id']; doc=self.service.get_document(self.owner,did)
        self.assertEqual({c['type'] for c in doc['state']['cards'].values()},{'chart','note-question'})
        first_chart=next(c for c in doc['state']['cards'].values() if c['type']=='chart')
        first_snap=doc['snapshots'][first_chart['snapshot_id']]
        self.assertEqual(first_snap['finding_selection']['series'],'modis')
        self.assertEqual(first_snap['scope']['period_kind'],'disjoint_months')
        self.assertEqual([p['start'][:7] for p in first_snap['scope']['periods']],pair['dates'])
        second=submit(self.service,self.owner,request('viirs',{'intent':'append','board_id':did,'revision':doc['revision']},2),'finding-two',background=False)['command']
        self.assertEqual(second['status'],'awaiting_view_ack',second)
        newer=self.service.get_document(self.owner,did)
        self.assertEqual(newer['state']['cards'][first_chart['id']],first_chart)
        charts=[c for c in newer['state']['cards'].values() if c['type']=='chart']
        self.assertEqual(len(charts),2)
        self.assertEqual({newer['snapshots'][c['snapshot_id']]['finding_selection']['series'] for c in charts},{'modis','viirs'})
        self.assertEqual(charts[0]['transform']['y'],charts[1]['transform']['y'])
        self.assertNotEqual(charts[0]['transform']['x'],charts[1]['transform']['x'])
        note=next(c for c in newer['state']['cards'].values() if c['type']=='note-question')
        newer=self.service.transact(self.owner,did,{'base_revision':newer['revision'],'ops':[{'op':'update_card','id':note['id'],'patch':{'text':'My interpretation'}}]})
        from unittest.mock import patch
        with patch('fireatlas.studio.portability.StorageBudget.check',return_value={}):
            job=self.service.portability.submit(self.owner,did,{'format':'native','revision':newer['revision']},background=False)
        self.assertEqual(job['status'],'completed',job)
        path,_=self.service.portability.download(self.owner,job['id'])
        restored=self.service.portability.restore(self.other,path)['document']
        self.assertTrue(any(c['text']=='My interpretation' for c in restored['state']['cards'].values()))
        self.assertEqual({s['finding_selection']['series'] for s in restored['snapshots'].values()},{'modis','viirs'})
        self.assertTrue(all(self.service.snapshot_report(self.other,restored['id'],snap['id'])['verification']['verified'] for snap in restored['snapshots'].values()))
