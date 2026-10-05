"""Owned prompt shortcuts and curated composition, without model transports."""
import copy
from unittest.mock import patch
from fireatlas.studio.prompts import PRESETS, resolve, submit
from fireatlas.studio.errors import StudioError
try:
    from studio_support import StudioCase
except ImportError:
    from .studio_support import StudioCase


class PromptTests(StudioCase):
    def request(self, board=None):
        return {'message':PRESETS[0]['prompt'],'context':{
            'schema':'fireatlas-jarvis-context-v1','surface':'studio','origin_instance_id':'prompt-source',
            'origin_tab_id':'prompt-tab','context_revision':1,'study_selection':{**self.study['context'],'day':'2015-07-04'},
            'active_view':{'kind':'map','operation':'replay','source':'joint','temporal_mode':'daily'},
            'destination':{'intent':'append','board_id':board['id'],'revision':board['revision']} if board else {'intent':'new-board'},
            'result_refs':[],'selected_object_ids':[]}}

    def test_destination_question_has_only_editable_owned_canvases_and_no_effects(self):
        mine=self.board(title='My presentation');self.board(self.other,title='Someone else')
        with patch.object(self.service.science,'call',side_effect=AssertionError('No science before selection')):
            answer=submit(self.service,self.owner,self.request(mine),'question')
        self.assertEqual(answer['status'],'needs_destination')
        self.assertEqual([b['id'] for b in answer['choices']],[mine['id']])
        with self.service.store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM commands').fetchone()[0],0)
        self.assertEqual(self.service.get_document(self.owner,mine['id'])['revision'],1)

    def test_curated_presentation_is_complete_frozen_and_retry_safe(self):
        body=self.request();body['destination']={'intent':'new-board'}
        command=submit(self.service,self.owner,body,'curated-prompt',background=False)['command']
        self.assertEqual(command['status'],'awaiting_view_ack',command)
        did=command['outputs']['document_id'];doc=self.service.get_document(self.owner,did)
        self.assertGreaterEqual(len(doc['state']['cards']),11)
        self.assertEqual(len(doc['state']['groups']),4)
        maps=[c for c in doc['state']['cards'].values() if c['type']=='map']
        self.assertEqual({c['display']['source'] for c in maps},{'joint','MODIS_SP','VIIRS_SNPP_SP'})
        self.assertTrue(all(c['display']['day']=='2015-07-04' for c in maps))
        self.assertTrue(all(c['display']['preview_on_open'] for c in doc['state']['cards'].values()))
        self.assertTrue(all(c['follow']=='pinned' for c in doc['state']['cards'].values()))
        self.assertTrue(any(c['type']=='observation' for c in doc['state']['cards'].values()))
        story=self.service.get_story(self.owner,command['outputs']['story_id'])
        self.assertEqual(len(story['body']['chapters']),6);self.assertIsNotNone(story['resolved'])
        self.assertTrue(self.service.validate_workflow(self.service.get_workflow(self.owner,command['outputs']['workflow_id'])['definition'])['valid'])
        again=submit(self.service,self.owner,body,'curated-prompt',background=False)['command']
        self.assertEqual(again['id'],command['id'])
        self.assertEqual(self.service.get_document(self.owner,did)['revision'],doc['revision'])

    def test_append_preserves_existing_work_and_keeps_original_source(self):
        doc=self.add_card(self.board(),'unrelated',kind='text',text='Keep my note')
        original=copy.deepcopy(doc['state']['cards']['unrelated'])
        body=self.request();body['destination']={'intent':'append','board_id':doc['id'],'revision':doc['revision']}
        command=submit(self.service,self.owner,body,'append-curated',background=False)['command']
        self.assertEqual(command['status'],'awaiting_view_ack',command)
        fresh=self.service.get_document(self.owner,doc['id'])
        self.assertEqual(fresh['state']['cards']['unrelated'],original)
        bottom=original['transform']['y']+original['transform']['h']
        self.assertTrue(all(c['transform']['y']>bottom for cid,c in fresh['state']['cards'].items() if cid!='unrelated'))

    def test_other_identity_destination_and_bad_choice_are_rejected(self):
        other=self.board(self.other)
        body=self.request();body['destination']={'intent':'append','board_id':other['id'],'revision':1}
        with self.assertRaises(StudioError):submit(self.service,self.owner,body,'not-owned',background=False)
        body['destination']='invalid'
        with self.assertRaises(StudioError):submit(self.service,self.owner,body,'invalid',background=False)

    def test_unknown_and_negated_requests_remain_with_tool_selecting_agent(self):
        for message in ('What does this map show?', 'Do not send data to canvas', 'Create a chart without sending it to canvas', 'Delete all canvas cards', 'Export this board'):
            self.assertIsNone(resolve(message))
        self.assertEqual(resolve('Send this data to the canvas')['arguments'],{'layout':'curated'})
        self.assertEqual(resolve(PRESETS[1]['prompt'])['case'],'park-2024')
        with self.assertRaises(StudioError):resolve('Edited selection','curated-current')

    def test_data_presets_select_real_operations(self):
        for preset in PRESETS:
            if preset.get('operation'):
                self.assertEqual(submit(self.service,self.owner,{'message':preset['prompt']},'operation')['operation'],preset['operation'])
