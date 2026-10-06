"""AI authoring is mocked; receipts and infographic scenes are resolved for real."""
import importlib.util
import json
import threading
import unittest
from unittest.mock import Mock, patch

try:
    from studio_support import StudioCase
except ImportError:  # both unittest discovery and package-based focused runs
    from .studio_support import StudioCase
from fireatlas.studio.story_generation import StoryGeneration
from fireatlas.studio.errors import Conflict, StudioError


def draft(material):
    card = material['cards'][0]
    return {'title': 'Reading the satellite record', 'chapters': [
        {'title': title, 'caption': 'Inspect the dated observations in this study.', 'card_ids': [card['id']],
         'duration_seconds': 15, 'transition': 'fade', 'narration_segments': [
             {'kind': 'text', 'text': 'The recorded evidence reports'},
             {'kind': 'checked-field', 'snapshot_id': card['snapshot_id'], 'path': card['facts'][0]['path'], 'format': 'with-unit'},
             {'kind': 'text', 'text': 'within the selected study. These observations do not establish a fire perimeter.'}]}
        for title in ['Where the observations begin', 'Activity through time', 'Reading the sensors', 'What remains unknown']]}


class GenerationTests(StudioCase):
    def manager(self, author=None):
        fn = author or Mock(side_effect=lambda instructions, material, flag: (draft(material), {'provider': 'aiand', 'model': 'mock'}))
        return StoryGeneration(self.service, author=fn, background=False), fn

    def test_saves_checked_scenes_once_and_freezes_document_revision(self):
        doc, snapshot = self.bound_board()
        manager, author = self.manager()
        job = manager.submit(self.owner, doc['id'], {'expected_revision': doc['revision'], 'render': False}, 'story-once-key')
        self.assertEqual(job['status'], 'completed', job)
        self.assertEqual(job['progress'], 1)
        self.assertEqual(job['phase'], 'story-ready')
        saved = self.service.get_story(self.owner, job['story_id'])
        self.assertEqual(saved['document_revision'], doc['revision'])
        self.assertEqual(len(saved['resolved']['scenes']), 4)
        self.assertTrue(all(s['narration_checked'] for s in saved['resolved']['scenes']))
        self.assertEqual(saved['resolved']['snapshots'][snapshot['id']]['receipt_sha256'], snapshot['receipt_sha256'])
        self.service.transact(self.owner, doc['id'], {'base_revision': doc['revision'], 'ops': [{'op': 'update_card', 'id': 'c1', 'patch': {'title': 'Later edit'}}]})
        again = manager.submit(self.owner, doc['id'], {'expected_revision': doc['revision'], 'render': False}, 'story-once-key')
        self.assertEqual(again['story_id'], saved['id'])
        self.assertEqual(author.call_count, 1)
        self.assertEqual(self.service.get_story(self.owner, saved['id'])['resolved'], saved['resolved'])

    def test_rejects_stale_unauthorized_and_unfrozen_requests_before_inference(self):
        doc, _ = self.bound_board()
        manager, author = self.manager()
        with self.assertRaises(Conflict):
            manager.submit(self.owner, doc['id'], {'expected_revision': 0})
        with self.assertRaises(StudioError):
            manager.submit(self.other, doc['id'], {'expected_revision': doc['revision']})
        plain = self.add_card(self.board())
        with self.assertRaises(StudioError):
            manager.submit(self.owner, plain['id'], {'expected_revision': plain['revision']})
        author.assert_not_called()

    def test_bad_citation_or_invented_measurement_publishes_no_story(self):
        doc, _ = self.bound_board()
        for kind in ['number', 'pointer', 'foreign-card']:
            def author(instructions, material, flag):
                output = draft(material)
                if kind == 'number': output['chapters'][0]['caption'] = 'A measured 99999 fires.'
                elif kind == 'pointer': output['chapters'][0]['narration_segments'][1]['path'] = '/invented'
                else: output['chapters'][0]['card_ids'] = ['foreign']
                return output, {'provider': 'aiand'}
            manager, _ = self.manager(author)
            job = manager.submit(self.owner, doc['id'], {'expected_revision': doc['revision'], 'render': False})
            self.assertEqual(job['status'], 'failed', job)
            self.assertIsNone(job['story_id'])
        self.assertEqual(self.service.document_projects(self.owner, doc['id'])['stories'], [])

    def test_cancelled_provider_result_cannot_insert_and_restart_does_not_repeat_call(self):
        doc, _ = self.bound_board()
        def author(instructions, material, flag):
            flag.set()
            return draft(material), {'provider': 'aiand'}
        manager, _ = self.manager(author)
        job = manager.submit(self.owner, doc['id'], {'expected_revision': doc['revision']})
        self.assertIsNone(job['story_id'])
        fresh, retry = self.manager()
        self.assertEqual(fresh.get(self.owner, job['id'])['status'], 'failed')
        retry.assert_not_called()

    def test_video_unavailable_keeps_interactive_story(self):
        doc, _ = self.bound_board()
        manager, _ = self.manager()
        with patch.object(self.service.renders, 'capability', return_value={'available': False, 'reason': 'test renderer offline'}):
            job = manager.submit(self.owner, doc['id'], {'expected_revision': doc['revision']})
        self.assertEqual(job['status'], 'partial', job)
        self.assertIsNotNone(self.service.get_story(self.owner, job['story_id'])['resolved'])
        self.assertIn('test renderer offline', job['error'])

    def test_saved_story_checkpoint_stays_running_until_video_admission_and_completion(self):
        doc, _ = self.bound_board()
        manager, author = self.manager()
        entered, release = threading.Event(), threading.Event()
        video = {'id': 'test-video', 'status': 'queued', 'phase': 'queued', 'progress': 0, 'error': None}
        outcome = []
        def start(*args, **kwargs):
            self.assertTrue(kwargs['narration_requested'])
            entered.set()
            if not release.wait(5):
                raise AssertionError('test admission timed out')
            return video
        with patch.object(self.service, 'start_render', side_effect=start), patch.object(self.service.renders, 'get', side_effect=lambda *args: dict(video)):
            worker = threading.Thread(target=lambda: outcome.append(manager.submit(self.owner, doc['id'], {'expected_revision': doc['revision']}, 'checkpoint-test')))
            worker.start()
            try:
                self.assertTrue(entered.wait(5))
                with self.service.store.connection() as db:
                    identifier = db.execute('SELECT id FROM story_generations').fetchone()[0]
                checkpoint = manager.get(self.owner, identifier)
                self.assertEqual((checkpoint['status'], checkpoint['phase'], checkpoint['progress']), ('running', 'preparing-video', .65))
                self.assertIsNotNone(self.service.get_story(self.owner, checkpoint['story_id'])['resolved'])
            finally:
                release.set()
                worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(outcome[0]['status'], 'running')
            video.update(status='completed', phase='completed', progress=1)
            finished = manager.get(self.owner, identifier)
            self.assertEqual((finished['status'], finished['progress']), ('completed', 1))
            with self.service.store.connection() as db:
                row = db.execute('SELECT status,progress FROM story_generations WHERE id=?', (identifier,)).fetchone()
                self.assertEqual(tuple(row), ('completed', 1))
            # A retry restores the finished job, without requesting another draft.
            again = manager.submit(self.owner, doc['id'], {'expected_revision': doc['revision']}, 'checkpoint-test')
            self.assertEqual(again['id'], identifier)
            author.assert_called_once()

    def test_render_completion_updates_parent_without_browser_and_does_not_revive_cancel(self):
        doc, _ = self.bound_board()
        manager, _ = self.manager()
        self.service.renders.background = False
        with patch.object(self.service.renders, 'capability', return_value={'available': True}):
            job = manager.submit(self.owner, doc['id'], {'expected_revision': doc['revision']})
        renderer = self.service.renders
        renderer._update(job['render_id'], status='completed', progress=1)
        with self.service.store.connection() as db:
            row = db.execute('SELECT status,phase,progress FROM story_generations WHERE id=?', (job['id'],)).fetchone()
            self.assertEqual(tuple(row), ('completed', 'completed', 1))
        # A canceled generation remains canceled when a renderer later stops.
        with patch.object(renderer, 'capability', return_value={'available': True}):
            second = manager.submit(self.owner, doc['id'], {'expected_revision': doc['revision']})
        manager.cancel(self.owner, second['id'])
        renderer._update(second['render_id'], status='completed', progress=1)
        self.assertEqual(manager.get(self.owner, second['id'])['status'], 'cancelled')

    def test_missing_bindings_are_frozen_without_replacing_the_board(self):
        doc = self.add_card(self.board(), binding={'operation': 'research', 'context': {}, 'arguments': {}})
        manager, _ = self.manager()
        job = manager.submit(self.owner, doc['id'], {'expected_revision': doc['revision'], 'render': False})
        self.assertEqual(job['status'], 'completed', job)
        self.assertIsNone(self.service.get_document(self.owner, doc['id'])['state']['cards']['c1']['snapshot_id'])
        self.assertTrue(self.service.get_story(self.owner, job['story_id'])['resolved']['snapshots'])

    def test_retained_storyboard_can_finish_without_repeating_provider_call(self):
        import time
        doc, _ = self.bound_board()
        manager, author = self.manager()
        with patch('fireatlas.studio.story_generation.compose', side_effect=StudioError('interrupted validation')):
            job = manager.submit(self.owner, doc['id'], {'expected_revision': doc['revision'], 'render': False})
        self.assertTrue(job['can_resume'])
        manager.resume(self.owner, job['id'])
        for _ in range(100):
            job = manager.get(self.owner, job['id'])
            if job['status'] in {'completed', 'failed'}: break
            time.sleep(.02)
        self.assertEqual(job['status'], 'completed', job)
        self.assertEqual(author.call_count, 1)

    def test_readable_day_components_of_verified_date_lists_are_checked(self):
        from fireatlas.studio.evidence import check_narration
        snapshots = [{'facts': [{'state': 'observed', 'value': '2024-07-29, 2024-07-30'}]}]
        self.assertTrue(check_narration('July 29 and July 30', snapshots)['checked'])
        self.assertFalse(check_narration('July 999', snapshots)['checked'])


@unittest.skipUnless(importlib.util.find_spec('httpx'), 'optional assistant transport not installed')
class CredentialTests(unittest.TestCase):
    def test_catalog_authentication_fallback_never_retries_inference(self):
        import httpx
        from fireatlas.assistant import aiand
        entry = {'id': aiand.STORY_MODEL, 'capabilities': ['tool_calling'], 'currency': 'usd',
                 'input_per_1m': 1, 'output_per_1m': 4, 'reasoning_efforts': ['high']}
        responses = [httpx.Response(401, request=httpx.Request('GET', aiand.BASE_URL)),
                     httpx.Response(200, json={'data': [entry]}, request=httpx.Request('GET', aiand.BASE_URL))]
        store = Mock(); store.reserve.return_value = 'reservation'
        with patch.dict('os.environ', {'AIAND_API_KEY': 'first-private', 'AIAND_API_KEYS': 'first-private,second-private'}, clear=True), \
             patch.object(aiand, '_cache', None), patch.object(aiand, '_authenticated_key', None), \
             patch('httpx.get', side_effect=responses) as catalog, patch('httpx.post', side_effect=httpx.ReadTimeout('private')) as post:
            with self.assertRaisesRegex(ValueError, 'not retried'):
                aiand.structured_story(store, 'owner', 'instructions', {}, threading.Event())
            self.assertEqual(catalog.call_count, 2)
            self.assertEqual(post.call_count, 1)
            self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Bearer second-private')
            self.assertEqual(post.call_args.kwargs['json']['model'], aiand.STORY_MODEL)
            self.assertEqual(post.call_args.kwargs['json']['reasoning_effort'], 'high')
            store.reconcile.assert_not_called()

    def test_success_records_usage_without_private_key(self):
        import httpx
        from fireatlas.assistant import aiand
        store = Mock(); store.reserve.return_value = 'r'
        config = {'model': 'verified', 'input_price': .1, 'output_price': .5, 'reasoning_effort': 'low', 'price_basis': 'catalog'}
        payload = {'model': 'verified', 'usage': {'prompt_tokens': 200, 'completion_tokens': 100},
                   'choices': [{'finish_reason': 'stop', 'message': {'content': '{"title":"Checked"}'}}]}
        response = httpx.Response(200, json=payload, request=httpx.Request('POST', aiand.BASE_URL))
        with patch.object(aiand, 'verified_model', return_value=config), patch.object(aiand, '_authenticated_key', 'private-value'), patch('httpx.post', return_value=response) as post:
            output, receipt = aiand.structured_story(store, 'owner', 'system', {}, threading.Event())
        self.assertEqual(output['title'], 'Checked')
        self.assertNotIn('private-value', json.dumps(receipt))
        store.reconcile.assert_called_once_with('owner', 'r', 70)
        self.assertEqual(post.call_args.kwargs['json']['response_format'], {'type': 'json_object'})
