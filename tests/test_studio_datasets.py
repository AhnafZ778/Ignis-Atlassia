import unittest
from unittest.mock import patch
from tests.studio_support import StudioCase
from fireatlas.studio.datasets import add, read, parse_csv, scatter, summarize
from fireatlas.studio.errors import StudioError, LimitExceeded, Conflict, NotFound


class DatasetTests(StudioCase):
    def test_group_summary_retains_unknown_and_invalid_values(self):
        from fireatlas.studio.datasets import add,group_summary
        from fireatlas.studio.errors import NotFound,LimitExceeded
        board=self.board();table=add(self.service.store,self.owner,board['id'],'groups.csv',b'area,value\nA,0\nA,4\nA,\nB,no\n,8\n')
        result=group_summary(self.service.store,self.owner,board['id'],table['id'],'area','value')
        self.assertEqual(result['groups'],[{'group':'A','rows':3,'numeric_count':2,'missing_count':1,'non_numeric_count':0,'mean':2}, {'group':'B','rows':1,'numeric_count':0,'missing_count':0,'non_numeric_count':1,'mean':None}, {'group':None,'rows':1,'numeric_count':1,'missing_count':0,'non_numeric_count':0,'mean':8}])
        with self.assertRaises(NotFound):group_summary(self.service.store,self.other,board['id'],table['id'],'area','value')
        data=('area,value\n'+''.join(f'{i},1\n' for i in range(31))).encode()
        many=add(self.service.store,self.owner,board['id'],'many.csv',data)
        with self.assertRaises(LimitExceeded):group_summary(self.service.store,self.owner,board['id'],many['id'],'area','value')
    def test_summary_uses_all_rows_and_distinguishes_zero_missing_and_nonnumeric(self):
        doc=self.board();data=b'x,y\n0,1\n-2,\n4,word\n,2\nNaN,3\n'
        table=add(self.service.store,self.owner,doc['id'],'sample.csv',data)
        result=summarize(self.service.store,self.owner,doc['id'],table['id'],['x','y'])
        self.assertEqual(result['total_rows'],5)
        self.assertEqual(result['columns'][0],{'column':'x','numeric_count':3,'missing_count':1,'non_numeric_count':1,'minimum':-2,'maximum':4,'mean':2/3,'median':0})
        self.assertEqual(result['columns'][1]['mean'],2)
        self.assertEqual(result['columns'][1]['non_numeric_count'],1)
        with self.assertRaises(StudioError):summarize(self.service.store,self.owner,doc['id'],table['id'],['x','x'])
        with self.assertRaises(NotFound):summarize(self.service.store,self.other,doc['id'],table['id'],['x'])

    def test_summary_handles_extremes_and_empty_numeric_columns(self):
        doc=self.board();table=add(self.service.store,self.owner,doc['id'],'extremes.csv',b'x,y\n-1e308,\n1e308,word\n')
        result=summarize(self.service.store,self.owner,doc['id'],table['id'],['x','y'])
        self.assertEqual(result['columns'][0]['mean'],0)
        self.assertEqual(result['columns'][0]['median'],0)
        self.assertIsNone(result['columns'][1]['mean'])
    def test_scatter_uses_finite_numeric_pairs_and_preserves_rows(self):
        doc=self.board(); data=b'x,y\n0,1\n-2.5,3e2\n,4\nNaN,1\n1_0,2\n1,inf\n'
        table=add(self.service.store,self.owner,doc['id'],'plot.csv',data)
        result=scatter(self.service.store,self.owner,doc['id'],table['id'],'x','y')
        self.assertEqual(result['points'],[{'row':2,'x':0.0,'y':1.0},{'row':3,'x':-2.5,'y':300.0}])
        self.assertEqual(result['skipped_rows'],4)
        self.assertEqual(result['total_rows'],6)
        self.assertEqual(result['sha256'],table['sha256'])
        with self.assertRaises(StudioError):scatter(self.service.store,self.owner,doc['id'],table['id'],'x','x')
        with self.assertRaises(NotFound):scatter(self.service.store,self.other,doc['id'],table['id'],'x','y')

    def test_scatter_rejects_more_than_5000_numeric_pairs(self):
        doc=self.board();table=add(self.service.store,self.owner,doc['id'],'large.csv',b'x,y\n'+b'1,2\n'*5001)
        with self.assertRaises(LimitExceeded):scatter(self.service.store,self.owner,doc['id'],table['id'],'x','y')

    def test_csv_rows_are_owned_exact_and_idempotent(self):
        doc=self.board();data='name,value\n"rain, fog",0\nclear,\n'.encode()
        first=add(self.service.store,self.owner,doc['id'],'observations.csv',data)
        second=add(self.service.store,self.owner,doc['id'],'different.csv',data)
        self.assertEqual(first['id'],second['id']);self.assertTrue(second['existing'])
        view,original=read(self.service.store,self.owner,doc['id'],first['id'],1,1)
        self.assertEqual(original,data);self.assertEqual(view['preview'],[['clear','']]);self.assertEqual(view['row_count'],2)
        with self.assertRaises(NotFound):read(self.service.store,self.other,doc['id'],first['id'])

    def test_rejects_bad_or_oversized_tables(self):
        for value in (b'a,a\n1,2',b'a,b\n1',b'\xff'):
            with self.subTest(value=value),self.assertRaises(StudioError):parse_csv(value)
        with self.assertRaises(LimitExceeded):parse_csv(b'a\n'+b'x'*(5*1024*1024))

    def test_package_restores_referenced_csv_and_its_board_link(self):
        doc=self.board();data=b'date,count\n2024-01-01,0\n'
        dataset=add(self.service.store,self.owner,doc['id'],'data.csv',data)
        elem={'id':'csv-card','type':'text','text':'Data','x':0,'y':0,'width':20,'height':20,'customData':{'fireatlas':{'documentId':doc['id'],'datasetId':dataset['id'],'datasetHash':dataset['sha256']}}}
        doc=self.service.transact(self.owner,doc['id'],{'base_revision':doc['revision'],'ops':[{'op':'patch_whiteboard','changes':[{'kind':'element','id':'csv-card','position':0,'value':elem}]}]})
        with patch('fireatlas.studio.portability.StorageBudget.check',return_value={}):
            job=self.service.portability.submit(self.owner,doc['id'],{'format':'native','revision':doc['revision']},background=False)
        self.assertEqual(job['status'],'completed',job)
        path,_=self.service.portability.download(self.owner,job['id'])
        restored=self.service.portability.restore(self.other,path)['document']
        scene=self.service.store.whiteboard(self.other,restored['id']);meta=scene['elements'][0]['customData']['fireatlas']
        self.assertEqual(meta['documentId'],restored['id']);self.assertNotEqual(meta['datasetId'],dataset['id'])
        info,original=read(self.service.store,self.other,restored['id'],meta['datasetId'])
        self.assertEqual(original,data);self.assertEqual(info['preview'],[['2024-01-01','0']])

    def test_package_keeps_unplaced_uploads_and_rejects_broken_references(self):
        doc=self.board();dataset=add(self.service.store,self.owner,doc['id'],'saved.csv',b'value\n1\n')
        element={'id':'note','type':'text','text':'Note','x':0,'y':0,'width':10,'height':10}
        doc=self.service.transact(self.owner,doc['id'],{'base_revision':doc['revision'],'ops':[{'op':'patch_whiteboard','changes':[{'kind':'element','id':'note','position':0,'value':element}]}]})
        with patch('fireatlas.studio.portability.StorageBudget.check',return_value={}):job=self.service.portability.submit(self.owner,doc['id'],{'format':'native'},background=False)
        self.assertEqual(job['status'],'completed',job)
        path,_=self.service.portability.download(self.owner,job['id'])
        imported=self.service.portability.restore(self.other,path)
        self.assertEqual(read(self.service.store,self.other,imported['document']['id'],imported['id_map'][dataset['id']])[1],b'value\n1\n')
        element['customData']={'fireatlas':{'documentId':doc['id'],'datasetId':'missing','datasetHash':'wrong'}}
        doc=self.service.transact(self.owner,doc['id'],{'base_revision':doc['revision'],'ops':[{'op':'patch_whiteboard','changes':[{'kind':'element','id':'note','position':0,'value':element}]}]})
        with self.assertRaises(StudioError):self.service.portability.capture(self.owner,doc['id'])

    def test_retry_rejects_changed_dataset_manifest_at_same_board_revision(self):
        doc=self.add_card(self.board(),'note',kind='text',text='note')
        with patch('fireatlas.studio.portability.StorageBudget.check',return_value={}), patch('fireatlas.studio.portability.board_svg',side_effect=RuntimeError('interrupted')):
            job=self.service.portability.submit(self.owner,doc['id'],{'format':'native'},background=False)
        self.assertEqual(job['status'],'failed')
        add(self.service.store,self.owner,doc['id'],'new.csv',b'value\n1\n')
        self.assertEqual(self.service.get_document(self.owner,doc['id'])['revision'],doc['revision'])
        with self.assertRaises(Conflict):self.service.portability.retry(self.owner,job['id'])
