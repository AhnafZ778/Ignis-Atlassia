"""Offline speech capability, complete timing and optional real neural audio."""
import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fireatlas.studio import local_voice, narration


class LocalVoiceTests(unittest.TestCase):
    def test_missing_voice_is_unavailable_without_remote_requests(self):
        with patch.dict('os.environ', {'FIREATLAS_STUDIO_VOICE_MODEL': '/missing/voice.onnx'}):
            self.assertFalse(local_voice.capability()['available'])

    def test_offline_voice_does_not_consume_paid_character_or_cost_allowance(self):
        capability = {'available': True, 'provider': 'piper', 'model': 'local-frozen', 'voice': 'local-voice', 'per_request_usd': 0, 'story_budget_usd': 0}
        plan = narration.preflight([{'chapter_id': 'a', 'narration_text': 'The saved checked record.', 'narration_checked': True}], capability, used_today=100000)
        self.assertTrue(plan['available'])
        self.assertEqual(plan['model'], 'local-frozen')
        self.assertEqual(plan['estimated_usd'], 0)

    def test_video_timing_retains_every_word_and_does_not_mutate_saved_story(self):
        story = {'profile': {'duration_seconds': 20}, 'scenes': [
            {'chapter_id': 'a', 'duration_seconds': 10, 'start_seconds': 0, 'narration_text': 'Complete first chapter.'},
            {'chapter_id': 'b', 'duration_seconds': 10, 'start_seconds': 10, 'narration_text': 'Complete second chapter.'}]}
        saved = copy.deepcopy(story)
        audio = {'status': 'narrated', 'segments': [{'chapter_id': 'a', 'file': 'a.mp3'}]}
        prepared, changes = narration.fit_local_timing(story, audio, '/test', probe=lambda _: 13)
        self.assertEqual(story, saved)
        self.assertEqual(prepared['scenes'][0]['duration_seconds'], 14.2)
        self.assertEqual(prepared['scenes'][1]['start_seconds'], 14.2)
        self.assertEqual(prepared['profile']['duration_seconds'], 24.2)
        self.assertEqual(prepared['scenes'][0]['narration_text'], saved['scenes'][0]['narration_text'])
        self.assertEqual(len(changes), 1)

    @unittest.skipUnless(importlib.util.find_spec('piper') and local_voice.DEFAULT_MODEL.exists(), 'optional offline voice not installed')
    def test_real_neural_voice_produces_bounded_mp3_with_nonzero_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'speech.mp3'
            path.write_bytes(local_voice.synthesize('The satellite record shows dated observations within this study.'))
            self.assertTrue(1 < narration.audio_duration(path) < 30)
            self.assertLess(path.stat().st_size, narration.AUDIO_FILE_LIMIT)
        with self.assertRaisesRegex(ValueError, 'cancelled'):
            local_voice.synthesize('Canceled speech.', cancelled=lambda: True)


if __name__ == '__main__':
    unittest.main()
