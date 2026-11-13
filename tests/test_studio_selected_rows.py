import csv, io, zipfile
from unittest.mock import patch
from tests.studio_support import StudioCase
from fireatlas.studio.selected_rows import selection_rows
from fireatlas.studio.errors import StudioError

class SelectionExportTests(StudioCase):
    def test_selected_observation_roundtrip_and_csv(self):
        study={**self.study['context'],'day':'2015-07-04'}
        receipt=self.service.science.call(self.owner,'replay',study)
        row=next(r for r in receipt['payload']['observations'] if r['date']=='2015-07-04')
        selection={'target':'observation-record','date':row['date'],'record_id':row['id'],'geometry':{'type':'Point','coordinates':[row['longitude'],row['latitude']]}}
        context={'schema':'fireatlas-jarvis-context-v1','surface':'investigate','origin_instance_id':'select-test','origin_tab_id':'select-tab','context_revision':1,'study_selection':study,'active_view':{'kind':'map','operation':'replay','source':'joint','geometry':{'type':'selected-observations','selection':selection}},'result_refs':[],'destination':{'intent':'new-board'},'selected_object_ids':[]}
        command=self.service.commands.submit(self.owner,{'recipe':'visualization_to_investigation','context':context,'arguments':{'layout':'minimal'}},'selection-one',background=False)
        self.assertEqual(command['status'],'awaiting_view_ack',command)
        doc=self.service.get_document(self.owner,command['outputs']['document_id'])
        snap=next(iter(doc['snapshots'].values()));self.assertEqual(snap['selected_observations']['record_id'],row['id'])
        with patch('fireatlas.studio.portability.StorageBudget.check',return_value={}):
            job=self.service.portability.submit(self.owner,doc['id'],{'format':'native'},background=False)
        self.assertEqual(job['status'],'completed',job)
        path,_=self.service.portability.download(self.owner,job['id'])
        with zipfile.ZipFile(path) as z:
            files=[n for n in z.namelist() if n.startswith('observations/')];self.assertEqual(len(files),1)
            records=list(csv.DictReader(io.StringIO(z.read(files[0]).decode())))
            self.assertEqual([r['id'] for r in records],[row['id']])
        restored=self.service.portability.restore(self.other,path)['document']
        self.assertEqual(next(iter(restored['snapshots'].values()))['selected_observations']['record_id'],row['id'])
        bad=dict(selection,record_id='invented')
        with self.assertRaises(StudioError):selection_rows(bad,receipt,row['date'],'joint')

    def test_no_selection_produces_no_selected_csv(self):
        doc,snap=self.bound_board(operation='replay',kind='map')
        with patch('fireatlas.studio.portability.StorageBudget.check',return_value={}):
            job=self.service.portability.submit(self.owner,doc['id'],{'format':'native'},background=False)
        self.assertEqual(job['status'],'completed',job)
        path,_=self.service.portability.download(self.owner,job['id'])
        with zipfile.ZipFile(path) as archive:self.assertFalse(any(n.startswith('observations/') for n in archive.namelist()))

    def test_cell_polygon_and_source_filter(self):
        study={**self.study['context'],'day':'2015-07-04'}
        receipt=self.service.science.call(self.owner,'replay',study)
        row=next(r for r in receipt['payload']['observations'] if r['date']=='2015-07-04')
        frame=next(f for f in receipt['payload']['frames'] if f['date_utc']==row['date'])
        cell=next(c for c in frame['cells'] if c['grid_x']==row['grid_x'] and c['grid_y']==row['grid_y'])
        selection={'target':'observation-cell','date':row['date'],'cell_id':str(row['grid_x'])+','+str(row['grid_y']),'geometry':{'type':'Polygon','coordinates':[cell['ring']]}}
        _,values=selection_rows(selection,receipt,row['date'],row['source_id'])
        self.assertIn(row['id'],[r['id'] for r in values])
        self.assertTrue(all(r['source_id']==row['source_id'] for r in values))
        polygon={'target':'query-boundary','date':row['date'],'geometry':selection['geometry']}
        _,area=selection_rows(polygon,receipt,row['date'],'joint')
        self.assertIn(row['id'],[r['id'] for r in area])
        tiny={'target':'query-boundary','date':row['date'],'geometry':{'type':'Polygon','coordinates':[[[-122,39],[-121.9999,39],[-121.9999,39.0001],[-122,39]]]}}
        _,empty=selection_rows(tiny,receipt,row['date'],'joint')
        self.assertEqual(empty,[])
        bad=dict(selection,cell_id='0,0')
        with self.assertRaises(StudioError):selection_rows(bad,receipt,row['date'],'joint')
