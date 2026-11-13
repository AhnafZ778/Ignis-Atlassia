import unittest
from pydantic_ai import ModelRetry
from fireatlas.assistant.board_diagram import validate_diagram, coalesce_diagram_nodes, table_source_label, fallback_evidence_diagram


class BoardDiagramTests(unittest.TestCase):
    def test_fallback_uses_full_safe_interpretation_or_a_question(self):
        text='The observations differ. The missing platform needs separate inspection.'
        diagram=fallback_evidence_diagram('table',text,table=True)
        self.assertEqual(diagram['nodes'][1]['label'],text)
        self.assertEqual(diagram['nodes'][1]['kind'],'interpretation')
        for unsafe in ('', 'There were 42 fires.', 'Wind caused the fire.'):
            self.assertEqual(fallback_evidence_diagram('table',unsafe,table=True)['nodes'][1]['kind'],'question')

    def test_checked_interpretation_can_be_used_without_opening_other_numeric_labels(self):
        text='NOAA-20 recorded 348 detections.'
        diagram=fallback_evidence_diagram('table',text,table=True,allow_interpretation_numbers=True)
        self.assertEqual(diagram['nodes'][1]['label'],text)
        bad={'nodes':[{'id':'c','kind':'context','label':'348 detections'}],'edges':[]}
        with self.assertRaises(ModelRetry):validate_diagram(bad,set(),allow_interpretation_numbers=True)
        name={'nodes':[{'id':'c','kind':'context','label':'NOAA-20 observations'}],'edges':[]}
        self.assertEqual(validate_diagram(name,set()),name)

    def test_table_source_label_uses_bounded_source_metadata(self):
        self.assertEqual(table_source_label('Park.csv',['date','MODIS','NOAA-20','state']),
                         'Park.csv\nFields: date · MODIS · NOAA-20 · …')
        self.assertEqual(table_source_label(None,None),'Selected table')
        self.assertNotIn('\n\n',table_source_label('x\n\ny',['a\nb']))

    def test_duplicate_source_nodes_share_connections_without_duplicates_or_loops(self):
        diagram={'nodes':[{'id':'first','kind':'evidence','evidence_id':'table','label':'Selected table'},
                          {'id':'second','kind':'evidence','evidence_id':'table','label':'Selected table'},
                          {'id':'other','kind':'evidence','evidence_id':'other','label':'Saved evidence'},
                          {'id':'question','kind':'question','evidence_id':None,'label':'What differs?'}],
                 'edges':[{'source':'first','target':'second','relation':'context'},
                          {'source':'first','target':'question','relation':'question'},
                          {'source':'second','target':'question','relation':'question'},
                          {'source':'other','target':'second','relation':'context'}]}
        result=coalesce_diagram_nodes(diagram)
        self.assertEqual([n['id'] for n in result['nodes']],['first','other','question'])
        self.assertEqual(result['edges'],[{'source':'first','target':'question','relation':'question'},
                                          {'source':'other','target':'first','relation':'context'}])
        self.assertEqual(len(diagram['nodes']),4)

    def test_repeated_interpretation_keeps_distinct_questions(self):
        diagram={'nodes':[{'id':'a','kind':'interpretation','label':'The observations differ.'},
                          {'id':'b','kind':'interpretation','label':'The observations differ.'},
                          {'id':'q1','kind':'question','label':'Why compare?'},
                          {'id':'q2','kind':'question','label':'What is missing?'}],
                 'edges':[{'source':'a','target':'q1','relation':'question'},
                          {'source':'b','target':'q2','relation':'question'}]}
        result=coalesce_diagram_nodes(diagram)
        self.assertEqual([n['id'] for n in result['nodes']],['a','q1','q2'])
        self.assertEqual([edge['source'] for edge in result['edges']],['a','a'])

    def test_context_is_descriptive_and_not_a_source(self):
        diagram={'nodes':[{'id':'context','label':'Cloud cover','kind':'context','evidence_id':None}], 'edges':[]}
        self.assertEqual(validate_diagram(diagram,set()),diagram)
        diagram['nodes'][0]['evidence_id']='receipt'
        with self.assertRaises(ModelRetry):validate_diagram(diagram,{'receipt'})
        diagram['nodes'][0]['evidence_id']=None
        diagram['nodes'][0]['label']='x'*121
        with self.assertRaises(ModelRetry):validate_diagram(diagram,set())
    def test_accepts_only_retrieved_evidence_and_existing_nodes(self):
        diagram={'nodes':[{'id':'source','label':'Satellite observations','kind':'evidence','evidence_id':'actual'},
                          {'id':'question','label':'Compare the sensors?','kind':'question','evidence_id':None}],
                 'edges':[{'source':'source','target':'question','relation':'question'}]}
        self.assertEqual(validate_diagram(diagram,{'actual'}),diagram)
        with self.assertRaises(ModelRetry):validate_diagram(diagram,set())
        diagram['edges'][0]['target']='missing'
        with self.assertRaises(ModelRetry):validate_diagram(diagram,{'actual'})

    def test_rejects_unchecked_numeric_and_causal_labels(self):
        for label in ('There were 10 fires','Wind caused the fire'):
            with self.subTest(label=label), self.assertRaises(ModelRetry):
                validate_diagram({'nodes':[{'id':'a','kind':'interpretation','label':label,'evidence_id':None}],'edges':[]},set())
