"""Stories, the static reader export, narration and the render lifecycle."""
from __future__ import annotations

import base64
import json
import hashlib
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from pathlib import Path

try:
    from studio_support import StudioCase
except ImportError:  # run as tests.test_studio_*
    from .studio_support import StudioCase

from fireatlas import core
from fireatlas.studio import narration, story as stories
from fireatlas.studio.errors import Conflict, LimitExceeded, StudioError, Unavailable
from fireatlas.studio.render import RenderManager, node_runner

AVAILABLE = lambda: {"available": True, "reason": None}
NARRATION_OFF = lambda: {"available": False, "reason": "Narration is not configured in this test."}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 20


def fake_video(job_dir, progress, cancel):
    progress(0.5)
    path = Path(job_dir) / "briefing.mp4"
    path.write_bytes(b"\x00\x00\x00 ftypisom" + b"fake-video")
    progress(1.0)
    return path


class StoryTests(StudioCase):
    def paired_heat_story(self):
        document, snapshot = self.bound_board('replay', kind='map')
        document = self.service.transact(self.owner, document['id'], {'base_revision': document['revision'], 'ops': [
            {'op': 'update_card', 'id': 'c1', 'patch': {'display': {'preview': 'heat', 'source': 'MODIS_SP'}}}]})
        document = self.add_card(document, 'c2', kind='map', snapshot_id=snapshot['id'],
                                 display={'preview': 'heat', 'source': 'VIIRS_SNPP_SP'})
        created = self.story_for(document, title='Paired frozen heat', chapters=[{'id': 'paired', 'title': 'Two sensors, one study',
            'card_id': 'c1', 'visible_cards': ['c1', 'c2'], 'duration_seconds': 20}])
        return document, snapshot, created

    def test_paired_heat_gallery_matches_existing_kernel_and_preserves_zero_and_limits(self):
        from fireatlas.studio import heat
        document, snapshot, created = self.paired_heat_story()
        receipt = self.service.snapshot_receipt(self.owner, document['id'], snapshot['id'])['receipt']
        resolved = self.service.resolve_story(self.owner, created['id'])['resolved']
        scene = resolved['scenes'][0]
        views = scene['visible_card_views']
        self.assertEqual(scene['gallery_version'], 2)
        self.assertEqual([v['visual']['source'] for v in views], ['MODIS_SP', 'VIIRS_SNPP_SP'])
        self.assertEqual(views[0]['visual']['domain'], views[1]['visual']['domain'])
        self.assertEqual(scene['visual_svg'].count('href="data:image/png;base64,'), 2)
        from xml.etree import ElementTree
        ElementTree.fromstring(scene['visual_svg'])
        self.assertIn('Scale fixed across all study dates and both sensors', scene['visual_svg'])
        for view in views:
            data = base64.b64decode(view['visual']['data'])
            self.assertTrue(data.startswith(b'\x89PNG'))
            self.assertEqual(hashlib.sha256(data).hexdigest(), view['visual']['sha256'])
            self.assertEqual(view['visual']['count'], receipt['payload']['frames'][0]['products'][view['visual']['source']]['cell_days'])
        script = "const fs=require('fs'),FM=require('./fireatlas/static/assistant-map.js');const b=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(FM.createIndex(b).maxima));"
        if shutil.which('node'):
            maxima = json.loads(subprocess.run(['node', '-e', script], input=json.dumps(receipt['payload']), text=True,
                                              capture_output=True, check=True, timeout=10).stdout)
            self.assertAlmostEqual(heat.maximum(receipt['payload']['frames']), maxima['joint:daily'], places=12)
        blank = {**receipt, 'payload': {**receipt['payload'], 'frames': [{**receipt['payload']['frames'][0], 'cells': []}]}}
        empty = heat.prepare(snapshot, blank, {}, 'MODIS_SP')
        self.assertEqual(empty['count'], 0)
        self.assertEqual(empty['products'], receipt['payload']['frames'][0]['products'])
        with self.assertRaises(StudioError):
            heat.prepare(snapshot, receipt, {'start': snapshot['scope']['start'], 'end': snapshot['scope']['end']}, 'joint')
        bad = {**receipt, 'payload': {**receipt['payload'], 'frames': [{**receipt['payload']['frames'][0],
            'cells': [{**receipt['payload']['frames'][0]['cells'][0], 'latitude': 90}]}]}}
        with self.assertRaises(StudioError):
            heat.prepare(snapshot, bad, {}, 'joint')

    def test_heat_gallery_recounts_images_scale_and_count_after_forged_checksums(self):
        from fireatlas.studio import visuals
        _, _, created = self.paired_heat_story()
        output = self.root / 'gallery-reader'
        manifest = self.service.export_story(self.owner, created['id'], output)
        root = output / manifest['slug']
        self.assertTrue(stories.verify_reader(root)['verified'])
        original = (root / 'story.json').read_text()
        # The first shipped gallery layout remains reproducible after the
        # new layout adds the named study and exact bounds to the figure.
        legacy = json.loads(original)
        legacy_scene = legacy['resolved']['scenes'][0]
        legacy_scene['gallery_version'] = 1
        legacy_scene['visual_svg'] = visuals.svg(legacy_scene)
        (root / legacy['story_files']['fallbacks'][legacy_scene['chapter_id']]).write_text(legacy_scene['visual_svg'])
        (root / 'story.json').write_text(json.dumps(legacy))
        self.rehash_reader(root)
        self.assertTrue(stories.verify_reader(root)['verified'])
        for attack in ('count', 'scale', 'pixels', 'receipt'):
            with self.subTest(attack=attack):
                reader = json.loads(original)
                scene = reader['resolved']['scenes'][0]
                view = scene['visible_card_views'][0]['visual']
                if attack == 'count': view['count'] += 1000
                elif attack == 'scale':
                    for card in scene['visible_card_views']: card['visual']['domain'][1] = 999
                elif attack == 'pixels':
                    view['data'] = base64.b64encode(PNG).decode()
                    view['sha256'] = hashlib.sha256(PNG).hexdigest()
                else:
                    for card in scene['visible_card_views']: card['visual']['receipt_sha256'] = 'f' * 64
                scene['visual_svg'] = visuals.svg(scene)
                (root / reader['story_files']['fallbacks'][scene['chapter_id']]).write_text(scene['visual_svg'])
                (root / 'story.json').write_text(json.dumps(reader))
                self.rehash_reader(root)
                report = stories.verify_reader(root)
                self.assertFalse(report['verified'], report)
                self.assertIn('gallery visual disagrees', ' '.join(report['problems']))

    def test_paginated_captions_keep_all_words_and_chapter_boundaries_with_legacy_support(self):
        import html
        text = 'Read the selected UTC dates & native measurements <carefully>. ' * 5
        resolved = {'caption_version': 2, 'scenes': [{'start_seconds': 7, 'duration_seconds': 15,
            'narration_text': text, 'caption': '', 'title': 'A chapter'}]}
        vtt = stories.captions(resolved)
        blocks = vtt.strip().split('\n\n')[1:]
        self.assertGreater(len(blocks), 1)
        lines = [block.splitlines() for block in blocks]
        self.assertTrue(all(len(line[2]) < 120 for line in lines))
        self.assertEqual(' '.join(html.unescape(line[2]) for line in lines), ' '.join(text.split()))
        self.assertTrue(lines[0][1].startswith('00:00:07.000 --> '))
        self.assertTrue(lines[-1][1].endswith(' --> 00:00:22.000'))
        for before, after in zip(lines, lines[1:]):
            self.assertEqual(before[1].split(' --> ')[1], after[1].split(' --> ')[0])
        legacy = stories.captions({**resolved, 'caption_version': 1})
        self.assertEqual(legacy, 'WEBVTT\n\n1\n00:00:07.000 --> 00:00:22.000\n' + text + '\n')
        with self.assertRaises(StudioError):
            stories.captions({**resolved, 'caption_version': 999})

    def test_audience_adapts_starter_wording_without_changing_checked_selection(self):
        document, snapshot = self.bound_board('replay', kind='map')
        researcher = stories.default_story(document['state'])
        student = stories.clean_story({**researcher, 'audience': 'student'})
        self.assertNotEqual(student['chapters'][1]['narration'], researcher['chapters'][1]['narration'])
        self.assertIn('cell-day', student['chapters'][1]['narration'])
        for before, after in zip(researcher['chapters'], student['chapters']):
            self.assertEqual({k: v for k, v in before.items() if k != 'narration'}, {k: v for k, v in after.items() if k != 'narration'})
        story = self.story_for(document, **student)
        result = self.service.resolve_story(self.owner, story['id'])['resolved']
        self.assertEqual(result['scenes'][1]['narration_text'], student['chapters'][1]['narration'])
        self.assertEqual(result['snapshots'][snapshot['id']], snapshot)
        manual = {**student, 'chapters': [{**student['chapters'][0], 'narration': 'My explanation of the study.'}]}
        changed = stories.clean_story({**manual, 'audience': 'reviewer'})
        self.assertEqual(changed['chapters'][0]['narration'], 'My explanation of the study.')
        self.assertIsNone(changed['chapters'][0]['narration_template'])
        segments = [{"kind": "checked-field", "path": "/summary/joint_cell_days", "format": "with-unit"}]
        checked = stories.clean_story({**student, 'audience': 'public', 'chapters': [{**student['chapters'][0], 'narration_segments': segments}]})
        self.assertEqual(checked['chapters'][0]['narration_segments'], segments)
        self.assertIsNone(checked['chapters'][0]['narration_template'])
        with self.assertRaises(StudioError):
            stories.clean_story({**student, 'chapters': [{**student['chapters'][0], 'narration_template': 'arbitrary-script'}]})

    def test_map_camera_affine_crop_and_new_interval_labels_preserve_legacy_figures(self):
        from fireatlas.studio import visuals
        visual = {'scope': {'bbox': [0, 0, 10, 10]}, 'camera_transition': {'from_bbox': [0, 0, 10, 10], 'to_bbox': [0, 0, 5, 5]}}
        self.assertEqual(visuals.camera_matrix(visual, 1), [2, 0, 0, 2, -90, -435])
        document, snapshot = self.bound_board('replay', kind='map')
        body = {'title': 'Interval units', 'chapters': [{'id': 'map', 'title': 'Map', 'card_id': 'c1', 'evidence_cards': ['c1'],
            'duration_seconds': 20, 'selection': {'start': snapshot['scope']['start'], 'end': snapshot['scope']['end']}}]}
        story = self.story_for(document, **body)
        resolved = self.service.resolve_story(self.owner, story['id'])['resolved']
        scene = resolved['scenes'][0]
        self.assertEqual(scene['figure_version'], 2)
        self.assertIn('occupied common cell-days', scene['visual_svg'])
        self.assertIn('data-map-camera', scene['visual_svg'])
        old = {**scene, 'figure_version': 1}
        self.assertNotIn('data-map-camera', visuals.svg(old))
        self.assertNotIn('occupied common cell-days', visuals.svg(old))

    def test_preview_interval_and_cell_selection_use_only_frozen_rows(self):
        document, snapshot = self.bound_board('replay', kind='map')
        receipt = self.service.snapshot_receipt(self.owner, document['id'], snapshot['id'])['receipt']
        records = receipt['payload']['observations']
        record = records[0]
        day = record['acquisition_utc'][:10]
        cell = f"{record['grid_x']}:{record['grid_y']}"
        preview = self.service.snapshot_preview(self.owner, document['id'], snapshot['id'], 'observation', day, 'joint', cell=cell)
        expected = [r for r in records if r['acquisition_utc'][:10] == day and f"{r['grid_x']}:{r['grid_y']}" == cell]
        self.assertEqual(preview['visual']['available_rows'], len(expected))
        self.assertEqual(preview['visual']['selected_cell'], cell)
        self.assertEqual(self.service.get_document(self.owner, document['id'])['state'], document['state'])
        for selection in ({'cell': 'invalid'}, {'start': '2000-01-01', 'end': '2000-01-02'}):
            with self.assertRaises(StudioError):
                self.service.snapshot_preview(self.owner, document['id'], snapshot['id'], 'map', **selection)

    def test_visible_gallery_card_freezes_its_receipt_even_without_an_explicit_citation(self):
        document, primary = self.bound_board('replay', kind='map')
        document = self.add_card(document, 'visible', kind='source-evidence')
        other = self.service.resolve_binding(self.owner, document['id'], {'operation': 'missingness', 'context': {}, 'arguments': {}})['snapshot']
        document = self.service.transact(self.owner, document['id'], {'base_revision': document['revision'], 'ops': [
            {'op': 'update_card', 'id': 'visible', 'patch': {'snapshot_id': other['id'], 'binding': {'operation': 'missingness'}}}]})
        story = self.story_for(document, title='Gallery evidence', chapters=[{
            'id': 'gallery', 'title': 'Visible evidence', 'card_id': 'c1', 'evidence_cards': ['c1'],
            'visible_cards': ['visible'], 'duration_seconds': 20}])
        resolved = self.service.resolve_story(self.owner, story['id'])['resolved']
        self.assertEqual(set(resolved['snapshots']), {primary['id'], other['id']})
        self.assertIn(other['id'], resolved['scenes'][0]['evidence'])
        self.assertTrue(resolved['scenes'][0]['visible_card_views'][0]['frozen'])

    def rehash_reader(self, root):
        """Refresh all integrity fields so negative tests exercise recounting."""
        from fireatlas.assistant.contracts import digest
        import hashlib
        reader = json.loads((root / 'story.json').read_text())
        resolved = reader['resolved']
        resolved['sha256'] = digest({k: v for k, v in resolved.items() if k != 'sha256'})
        (root / 'story.json').write_text(json.dumps(reader, indent=2, sort_keys=True))
        manifest = json.loads((root / 'manifest.json').read_text())
        manifest['story_sha256'] = resolved['sha256']
        for entry in manifest['files']:
            data = (root / entry['path']).read_bytes()
            entry.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        manifest['manifest_sha256'] = digest({k: v for k, v in manifest.items() if k != 'manifest_sha256'})
        (root / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True))

    def story_for(self, document, **overrides):
        return self.service.create_story(self.owner, document["id"], overrides)

    def test_resolved_revision_is_immutable_after_the_board_changes(self):
        document, _ = self.bound_board()
        story = self.story_for(document)
        resolved = self.service.resolve_story(self.owner, story["id"])["resolved"]
        self.service.transact(self.owner, document["id"], {"base_revision": document["revision"], "ops": [
            {"op": "update_card", "id": "c1", "patch": {"title": "Later board title"}}]})
        again = self.service.resolve_story(self.owner, story["id"])["resolved"]
        self.assertEqual(again, resolved)
        updated = self.service.update_story(self.owner, story["id"], {"expected_revision": 1, "story": story["body"]})
        self.assertEqual(updated["revision"], 2)
        self.assertNotEqual(self.service.resolve_story(self.owner, story["id"])["resolved"]["sha256"], resolved["sha256"])

    def test_frozen_narration_reconstructs_scalars_dates_and_exports(self):
        document, snapshot = self.bound_board('replay', kind='map')
        receipt = self.service.snapshot_receipt(self.owner, document['id'], snapshot['id'])['receipt']
        segments = [
            {'kind': 'text', 'text': 'The recorded study has', 'author': 'user'},
            {'kind': 'checked-field', 'snapshot_id': snapshot['id'], 'path': '/summary/joint_cell_days', 'format': 'with-unit'},
            {'kind': 'text', 'text': 'and this frame is dated'},
            {'kind': 'checked-field', 'snapshot_id': snapshot['id'], 'path': '/frames/1/date_utc'}]
        created = self.story_for(document, title='Narrated receipts', chapters=[{'id': 'checked', 'title': 'Evidence', 'card_id': 'c1',
            'narration': 'Fallback authored text.', 'narration_segments': segments, 'duration_seconds': 20}])
        resolved = self.service.resolve_story(self.owner, created['id'])['resolved']
        scene = resolved['scenes'][0]
        expected = f"The recorded study has {receipt['payload']['summary']['joint_cell_days']} cell-days and this frame is dated {receipt['payload']['frames'][1]['date_utc']}"
        self.assertEqual(scene['narration_text'], expected)
        self.assertTrue(scene['narration_checked'])
        self.assertEqual(scene['narration_grounding']['mode'], 'structured')
        self.assertEqual(scene['narration_input']['segments'], segments)
        output = self.root/'narrated'; manifest = self.service.export_story(self.owner, created['id'], output); root = output/manifest['slug']
        report = stories.verify_reader(root)
        self.assertTrue(report['verified'], report['problems'])
        self.assertEqual(report['narrations_checked'], 1)
        self.assertTrue(report['captions_checked'] and report['transcript_checked'])

    def test_reader_rejects_forged_narration_with_every_checksum_refreshed(self):
        document, snapshot = self.bound_board('replay')
        created = self.story_for(document, title='Narration tamper', chapters=[{'id': 'checked', 'title': 'Evidence', 'card_id': 'c1',
            'narration_segments': [{'kind': 'checked-field', 'snapshot_id': snapshot['id'], 'path': '/summary/joint_cell_days', 'format': 'with-unit'}]}])
        output = self.root/'tamper'; manifest = self.service.export_story(self.owner, created['id'], output); root = output/manifest['slug']
        original = (root/'story.json').read_text()
        for attack in ('text', 'field', 'snapshot', 'classification'):
            with self.subTest(attack=attack):
                reader = json.loads(original); scene = reader['resolved']['scenes'][0]
                if attack == 'text': scene['narration_text'] = '987654321 cell-days'
                elif attack == 'field': scene['resolved_fields'][0]['value'] = 987654321
                elif attack == 'snapshot': scene['narration_input']['segments'][0]['snapshot_id'] = 'snap_uncited'
                else: scene['narration_checked'] = False
                (root/'story.json').write_text(json.dumps(reader))
                (root/'captions.vtt').write_text(stories.captions(reader['resolved']))
                (root/'transcript.txt').write_text(stories.transcript(reader['resolved']))
                self.rehash_reader(root)
                report = stories.verify_reader(root)
                self.assertFalse(report['verified'])
                self.assertIn('narration', ' '.join(report['problems']))

    def test_reader_rejects_caption_and_transcript_forgery_after_rehash(self):
        document, _ = self.bound_board('replay'); created = self.story_for(document)
        output = self.root/'representations'; manifest = self.service.export_story(self.owner, created['id'], output); root = output/manifest['slug']
        for name in ('captions.vtt', 'transcript.txt'):
            original = (root/name).read_bytes()
            (root/name).write_text('Forged numerical representation: 987654321')
            self.rehash_reader(root)
            report = stories.verify_reader(root)
            self.assertFalse(report['verified'])
            self.assertIn('text differs', ' '.join(report['problems']))
            (root/name).write_bytes(original)
        self.rehash_reader(root)
        self.assertTrue(stories.verify_reader(root)['verified'])

    def test_missing_narration_pointer_is_not_checked_and_blocks_export(self):
        document, _ = self.bound_board('replay')
        created = self.story_for(document, title='Unresolved pointer', chapters=[{'id': 'missing', 'title': 'Evidence', 'card_id': 'c1',
            'narration_segments': [{'kind': 'checked-field', 'path': '/does-not-exist'}]}])
        scene = self.service.resolve_story(self.owner, created['id'])['resolved']['scenes'][0]
        self.assertFalse(scene['narration_checked'])
        self.assertEqual(scene['narration_text'], 'unknown')
        with self.assertRaises(StudioError): self.service.export_story(self.owner, created['id'], self.root/'missing')

    def test_authored_interpretation_remains_authored_and_legacy_reader_stays_valid(self):
        document, _ = self.bound_board('replay')
        created = self.story_for(document, title='Authored explanation', chapters=[{'id': 'authored', 'title': 'Interpretation', 'card_id': 'c1',
            'narration': 'This is my explanation of the recorded observations.'}])
        scene = self.service.resolve_story(self.owner, created['id'])['resolved']['scenes'][0]
        self.assertEqual(scene['narration_grounding']['mode'], 'authored')
        self.assertIn('not independently verified', scene['narration_grounding']['note'])
        output = self.root/'legacy'; manifest = self.service.export_story(self.owner, created['id'], output); root = output/manifest['slug']
        reader = json.loads((root/'story.json').read_text())
        for scene in reader['resolved']['scenes']:
            scene.pop('narration_input'); scene.pop('narration_grounding')
        (root/'story.json').write_text(json.dumps(reader)); self.rehash_reader(root)
        report = stories.verify_reader(root)
        self.assertTrue(report['verified'], report['problems'])
        self.assertEqual(report['legacy_narrations_checked'], 1)
        self.assertEqual(report['narrations_checked'], 0)

    def test_reader_verifier_rejects_parent_paths_even_with_refreshed_manifest(self):
        document, _ = self.bound_board()
        story = self.story_for(document)
        output = self.root / "out"
        manifest = self.service.export_story(self.owner, story["id"], output)
        root = output / manifest["slug"]
        from fireatlas.assistant.contracts import digest
        manifest["files"][0]["path"] = "../outside.json"
        manifest["manifest_sha256"] = digest({k: v for k, v in manifest.items() if k != "manifest_sha256"})
        (root / "manifest.json").write_text(json.dumps(manifest))
        report = stories.verify_reader(root)
        self.assertFalse(report["verified"])
        self.assertIn("leaves the export", " ".join(report["problems"]))

    def test_default_story_is_two_minutes_at_1080p_landscape(self):
        document, _ = self.bound_board()
        story = self.story_for(document)
        self.assertEqual(len(story["body"]["chapters"]), 6)
        self.assertEqual(sum(c["duration_seconds"] for c in story["body"]["chapters"]), 120)
        self.assertEqual((story["profile"]["width"], story["profile"]["height"], story["profile"]["fps"]), (1920, 1080, 30))
        resolved = self.service.resolve_story(self.owner, story["id"])["resolved"]
        self.assertEqual(resolved["profile"]["duration_seconds"], 120)
        self.assertEqual(resolved["schema"], stories.RESOLVED_SCHEMA)
        self.assertFalse([w for w in resolved["warnings"] if w["problem"] in ("evidence-unfrozen", "card-missing")])
        self.assertTrue(all(scene["evidence"] for scene in resolved["scenes"]))

    def test_operation_specific_guided_units_survive_freezing_and_receipt_verification(self):
        from fireatlas.studio import evidence as ev
        for operation in ('replay', 'missingness', 'persistence', 'archive_search'):
            with self.subTest(operation=operation):
                document, snapshot = self.bound_board(operation)
                report = self.service.snapshot_report(self.owner, document['id'], snapshot['id'])
                self.assertTrue(report['verification']['verified'], report['verification']['problems'])
                self.assertTrue(ev.verify_snapshot(snapshot, self.service.snapshot_receipt(self.owner, document['id'], snapshot['id'])['receipt'])['verified'])

    def test_camera_crop_keeps_the_frozen_study_count_and_rejects_outside_focus(self):
        from fireatlas.studio import visuals
        document, snapshot = self.bound_board('replay', kind='map')
        document = self.add_card(document, 'c2', kind='note-question', text='A linked interpretation.')
        document = self.add_card(document, 'c3', kind='method-note', text='The recorded method remains visible.')
        receipt = self.service.snapshot_receipt(self.owner, document['id'], snapshot['id'])['receipt']
        bounds = snapshot['scope']['bbox']
        w,s,e,n = bounds
        crop = [w, s, (w+e)/2, (s+n)/2]
        plain = visuals.prepared({'type':'map'}, [snapshot], {snapshot['id']:receipt}, {})
        focused = visuals.prepared({'type':'map'}, [snapshot], {snapshot['id']:receipt}, {'camera':{'bbox':crop}})
        self.assertEqual(plain['count'], focused['count'])
        self.assertEqual(plain['points'], focused['points'])
        self.assertEqual(focused['viewport'], crop)
        self.assertEqual(focused['scope']['bbox'], bounds)
        with self.assertRaises(StudioError):
            visuals.prepared({'type':'map'}, [snapshot], {snapshot['id']:receipt}, {'camera':{'bbox':[w-1,s,e,n]}})

    def test_interval_highlights_and_audience_duration_are_resolved_into_shared_scene(self):
        document, snapshot = self.bound_board('replay', kind='map')
        document = self.add_card(document, 'c2', kind='note-question', text='A linked interpretation.')
        document = self.add_card(document, 'c3', kind='method-note', text='The recorded method remains visible.')
        receipt = self.service.snapshot_receipt(self.owner, document['id'], snapshot['id'])['receipt']
        cell = receipt['payload']['frames'][0]['cells'][0]
        highlight = f"{cell['grid_x']}:{cell['grid_y']}"
        body = {
            'title': 'Compact public briefing', 'audience': 'public', 'target_duration_seconds': 30,
            'chapters': [{
                'id': 'chapter-a', 'title': 'Interval', 'card_id': 'c1', 'evidence_cards': ['c1'],
                'visible_cards': ['c1', 'c2', 'c3'], 'duration_seconds': 20, 'selection': {
                    'start': snapshot['scope']['start'], 'end': snapshot['scope']['end'],
                    'highlight_cells': [highlight]
                }
            }, {
                'id': 'chapter-b', 'title': 'Second', 'card_id': 'c1', 'evidence_cards': ['c1'], 'duration_seconds': 20
            }]
        }
        created = self.service.create_story(self.owner, document['id'], body)
        resolved = self.service.resolve_story(self.owner, created['id'])['resolved']
        self.assertEqual(resolved['profile']['duration_seconds'], 30)
        self.assertTrue(resolved['duration_adapted'])
        scene = resolved['scenes'][0]
        self.assertEqual(scene['audience'], 'public')
        self.assertEqual(len(scene['visible_card_views']), 2)
        self.assertEqual(scene['visual']['interval']['start'], snapshot['scope']['start'])
        self.assertEqual(scene['visual']['interval']['end'], snapshot['scope']['end'])
        self.assertTrue(any(point['highlight'] for point in scene['visual']['points']))

    def test_animated_camera_is_frozen_and_stays_inside_scope(self):
        from fireatlas.studio import visuals
        document, snapshot = self.bound_board('replay')
        receipt = self.service.snapshot_receipt(self.owner, document['id'], snapshot['id'])['receipt']
        w, s, e, n = snapshot['scope']['bbox']
        scene = visuals.prepared({'type': 'map'}, [snapshot], {snapshot['id']: receipt}, {'camera': {
            'bbox': [w, s, e, n], 'from_bbox': [w, s, (w + e) / 2, (s + n) / 2],
            'to_bbox': [(w + e) / 2, (s + n) / 2, e, n]
        }})
        self.assertEqual(scene['camera_transition']['from_bbox'][0], w)
        with self.assertRaises(StudioError):
            visuals.prepared({'type': 'map'}, [snapshot], {snapshot['id']: receipt}, {'camera': {
                'bbox': [w, s, e, n], 'from_bbox': [w - 1, s, e, n], 'to_bbox': [w, s, e, n]
            }})

    def test_context_layers_freeze_exact_bytes_and_survive_changed_live_metadata(self):
        from fireatlas.studio import context_layers
        from unittest.mock import patch
        import hashlib
        static = self.root/'static'; folder=static/'replay-context';folder.mkdir(parents=True)
        (folder/'terrain.png').write_bytes(PNG)
        meta={'path':'replay-context/terrain.png','bounds':[0,0,1,1],'bytes':len(PNG),'sha256':hashlib.sha256(PNG).hexdigest(),'status':'available','product':'NASADEM','version':'001'}
        (folder/'manifest.json').write_text(json.dumps({'layers':{'test':{'terrain':meta}}}))
        scope={'case':'test','bbox':[0,0,1,1]}
        with patch.object(context_layers,'STATIC',static):
            frozen=context_layers.freeze(scope,['terrain'])
            (folder/'manifest.json').write_text('{}')
            context_layers.verify(frozen,scope)
            with self.assertRaises(StudioError):context_layers.freeze(scope,['terrain'])
        changed=json.loads(json.dumps(frozen));changed[0]['data']=base64.b64encode(PNG+b'changed').decode()
        with self.assertRaises(StudioError):context_layers.verify(changed,scope)

    def test_story_updates_use_revisions_and_preserve_the_losing_draft(self):
        document, _ = self.bound_board()
        story = self.story_for(document)
        draft = dict(story["body"], title="Edited")
        updated = self.service.update_story(self.owner, story["id"], {"expected_revision": 1, "story": draft})
        self.assertEqual(updated["revision"], 2)
        with self.assertRaises(Conflict) as stale:
            self.service.update_story(self.owner, story["id"], {"expected_revision": 1, "story": dict(story["body"], title="Late")})
        self.assertEqual(stale.exception.details["server_story"]["title"], "Edited")
        self.assertEqual(self.service.get_story(self.owner, story["id"], 1)["body"]["title"], story["body"]["title"])

    def test_chapter_and_duration_limits(self):
        chapters = [{"id": f"c{n}", "title": "x", "duration_seconds": 20} for n in range(25)]
        with self.assertRaises(LimitExceeded):
            stories.clean_story({"title": "t", "chapters": chapters})
        with self.assertRaises(LimitExceeded):
            stories.clean_story({"title": "t", "chapters": [{"id": f"c{n}", "duration_seconds": 300} for n in range(3)]})
        with self.assertRaises(StudioError):
            stories.clean_story({"title": "t", "chapters": [{"id": "a", "duration_seconds": 20, "script": "x"}]})

    def test_unfrozen_evidence_blocks_export(self):
        document = self.add_card(self.board(), "c1", binding={"operation": "research"})
        story = self.story_for(document)
        resolved = self.service.resolve_story(self.owner, story["id"])["resolved"]
        self.assertIn("evidence-unfrozen", {w["problem"] for w in resolved["warnings"]})
        with self.assertRaises(StudioError) as blocked:
            self.service.export_story(self.owner, story["id"], self.root / "out")
        self.assertEqual(blocked.exception.code, "story-not-ready")

    def test_narration_numbers_must_come_from_cited_evidence(self):
        document, snapshot = self.bound_board()
        value = next(f["value"] for f in snapshot["facts"] if f["state"] == "observed" and isinstance(f["value"], (int, float)))
        good = {"title": "t", "chapters": [{"id": "a", "title": "A", "card_id": "c1", "duration_seconds": 20, "narration": f"The cited value is {value}."}]}
        bad = {"title": "t", "chapters": [{"id": "a", "title": "A", "card_id": "c1", "duration_seconds": 20, "narration": "There were 987654321 detections."}]}
        for body, expected in ((good, True), (bad, False)):
            story = self.service.create_story(self.owner, document["id"], body)
            scene = self.service.resolve_story(self.owner, story["id"])["resolved"]["scenes"][0]
            self.assertEqual(scene["narration_checked"], expected)
        self.assertEqual(scene["narration_unmatched_numbers"], ["987654321"])

    def test_static_export_verifies_offline_after_the_live_archive_changes_and_leaks_nothing(self):
        document, snapshot = self.bound_board()
        story = self.story_for(document)
        output = self.root / "site" / "data" / "studio"
        manifest = self.service.export_story(self.owner, story["id"], output)
        root = output / manifest["slug"]
        with core.connect(self.database) as db:
            db.execute("UPDATE batches SET row_count=row_count+7")
        report = stories.verify_reader(root)
        self.assertTrue(report["verified"], report["problems"])
        self.assertEqual(report["receipts_checked"], 1)
        text = "".join(p.read_text(errors="ignore") for p in root.rglob("*") if p.is_file() and p.suffix != ".gz")
        for private in (self.owner, document["id"], story["id"], self.token):
            self.assertNotIn(private, text)
        self.assertFalse(stories.PRIVATE.search(text))
        self.assertTrue(json.loads((root / "manifest.json").read_text())["requires_backend"] is False)
        for path in root.rglob("*.json"):
            self.assertNotIn("/home/", path.read_text())
        self.assertEqual({s["slug"] for s in json.loads((output / "index.json").read_text())["stories"]}, {manifest["slug"]})
        self.assertTrue((root / "captions.vtt").read_text().startswith("WEBVTT"))
        self.assertTrue(list((root / "fallbacks").glob("*.svg")))
        self.assertTrue((root / "index.html").is_file())
        self.assertTrue((root / "reader.js").is_file())
        self.assertTrue((root / "reader.css").is_file())

    def test_a_changed_reader_file_or_changed_number_is_detected(self):
        document, snapshot = self.bound_board()
        story = self.story_for(document)
        output = self.root / "reader"
        manifest = self.service.export_story(self.owner, story["id"], output)
        root = output / manifest["slug"]
        caption = root / "captions.vtt"
        caption.write_text(caption.read_text() + "\nedited")
        self.assertFalse(stories.verify_reader(root)["verified"])
        # Refresh every checksum after forging a number: the bundled receipt still disagrees.
        manifest = self.service.export_story(self.owner, story["id"], output)
        root = output / manifest["slug"]
        snapshot_file = next((root / "evidence").glob("*.snapshot.json"))
        data = json.loads(snapshot_file.read_text())
        item = next(f for f in data["facts"] if f["state"] == "observed" and isinstance(f["value"], (int, float)))
        item["value"] += 500
        from fireatlas.assistant.contracts import digest
        data["snapshot_sha256"] = digest({k: v for k, v in data.items() if k != "snapshot_sha256"})
        snapshot_file.write_text(json.dumps(data, indent=2, sort_keys=True))
        reader = json.loads((root / 'story.json').read_text())
        reader['resolved']['snapshots'][data['id']] = data
        (root / 'story.json').write_text(json.dumps(reader))
        self.rehash_reader(root)
        report = stories.verify_reader(root)
        self.assertFalse(report["verified"])
        self.assertNotIn('checksum mismatch', ' '.join(report['problems']))
        self.assertNotIn('changed or missing', ' '.join(report['problems']))

    def test_forged_prepared_figure_fails_after_every_checksum_is_refreshed(self):
        document, _ = self.bound_board()
        story = self.story_for(document)
        manifest = self.service.export_story(self.owner, story['id'], self.root / 'out')
        root = self.root / 'out' / manifest['slug']
        reader = json.loads((root / 'story.json').read_text())
        scene = reader['resolved']['scenes'][0]
        original = scene['visual_svg']
        changed = original.replace('<text ', '<text data-forged="true" ', 1)
        self.assertNotEqual(changed, original)
        scene['visual_svg'] = changed
        (root / reader['story_files']['fallbacks'][scene['chapter_id']]).write_text(changed)
        (root / 'story.json').write_text(json.dumps(reader))
        self.rehash_reader(root)
        report = stories.verify_reader(root)
        self.assertFalse(report['verified'])
        self.assertIn('SVG differs from the checked scene', ' '.join(report['problems']))
        self.assertNotIn('checksum mismatch', ' '.join(report['problems']))
        self.assertNotIn('changed or missing', ' '.join(report['problems']))

    def test_image_assets_need_license_attribution_and_a_real_image_type(self):
        document = self.board()
        with self.assertRaises(StudioError):
            self.service.add_asset(self.owner, document["id"], PNG, "", "")
        with self.assertRaises(StudioError):
            self.service.add_asset(self.owner, document["id"], b"<svg onload=alert(1)></svg>" * 3, "CC-BY", "Someone")
        with self.assertRaises(LimitExceeded):
            self.service.add_asset(self.owner, document["id"], PNG + b"0" * 1_600_000, "CC-BY", "Someone")
        asset = self.service.add_asset(self.owner, document["id"], PNG, "CC-BY-4.0", "Example photographer")
        self.assertEqual(asset["mime"], "image/png")
        path, mime = self.service.asset_file(self.owner, asset["id"])
        self.assertEqual(path.read_bytes(), PNG)
        with self.assertRaises(StudioError):
            self.service.asset_file(self.other, asset["id"])


class NarrationTests(unittest.TestCase):
    scene = lambda self, text, checked=True: {"chapter_id": "a", "narration_text": text, "narration_checked": checked}

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Optional local media tools are unavailable.')
    def test_actual_audio_duration_integrity_and_complete_chapter_fit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / ('a' * 64 + '.mp3')
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
                            '-c:a', 'libmp3lame', str(path)], check=True, capture_output=True)
            data = path.read_bytes()
            audio = {'status': 'narrated', 'segments': [{'chapter_id': 'a', 'index': 0, 'file': path.name,
                                                       'sha256': hashlib.sha256(data).hexdigest()}]}
            scenes = [{'chapter_id': 'a', 'start_seconds': 5, 'duration_seconds': 2}]
            result = narration.check_audio(audio, scenes, root)
            self.assertEqual(result['status'], 'narrated')
            self.assertTrue(result['timing']['checked'])
            self.assertAlmostEqual(result['segments'][0]['duration_seconds'], 1, delta=.1)
            self.assertEqual(result['timing']['chapters'][0]['chapter_start_seconds'], 5)
            short = narration.check_audio(audio, [{**scenes[0], 'duration_seconds': .5}], root)
            self.assertEqual(short['status'], 'captions-only')
            self.assertEqual(short['segments'], [])
            self.assertIn('exceeds', short['reason'])
            self.assertEqual(path.read_bytes(), data)
            path.write_bytes(data + b'changed')
            changed = narration.check_audio(audio, scenes, root)
            self.assertEqual(changed['status'], 'captions-only')
            self.assertFalse(changed['timing']['checked'])

    def test_partial_generation_and_cancellation_never_publish_incomplete_audio(self):
        calls = []
        def synthesize(text):
            calls.append(text)
            if len(calls) == 2:
                raise RuntimeError('provider failed')
            return b'fixture audio'
        plan = narration.preflight([self.scene('First chapter.'), {**self.scene('Second chapter.'), 'chapter_id': 'b'}],
                                   {'available': True, 'per_request_usd': 0, 'story_budget_usd': 1})
        with tempfile.TemporaryDirectory() as folder:
            attempted = narration.narrate(plan, folder, synthesize)
            self.assertEqual(attempted['status'], 'partial')
            result = narration.check_audio(attempted, [], folder, probe=lambda _: self.fail('Partial speech must not be rendered.'))
            self.assertEqual(result['status'], 'captions-only')
            self.assertEqual(result['attempted_status'], 'partial')
            self.assertFalse(result['segments'])
            self.assertTrue((Path(folder) / attempted['segments'][0]['file']).exists())
            canceled = narration.check_audio({**attempted, 'status': 'narrated'}, [], folder, cancelled=lambda: True)
            self.assertEqual(canceled['status'], 'canceled')
            self.assertFalse(canceled['segments'])
        self.assertEqual(len(calls), 2, 'The failed paid request must never be automatically retried.')

    def test_missing_reordered_and_unbounded_audio_fail_without_leaving_the_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); path = root / ('b' * 64 + '.mp3'); path.write_bytes(b'fixture')
            item = {'chapter_id': 'a', 'index': 0, 'file': path.name, 'sha256': hashlib.sha256(b'fixture').hexdigest()}
            scenes = [{'chapter_id': 'a', 'start_seconds': 0, 'duration_seconds': 20}]
            for segments in ([{**item, 'file': '../outside.mp3'}], [{**item, 'index': 1}], [item, item], [{**item, 'chapter_id': 'other'}]):
                result = narration.check_audio({'status': 'narrated', 'segments': segments}, scenes, root, probe=lambda _: 1)
                self.assertEqual(result['status'], 'captions-only')
                self.assertFalse(result['segments'])
            for duration in (float('nan'), float('inf'), -1, 500):
                result = narration.check_audio({'status': 'narrated', 'segments': [item]}, scenes, root, probe=lambda _: duration)
                self.assertEqual(result['status'], 'captions-only')

    def test_segments_are_bounded_and_unchecked_narration_is_never_voiced(self):
        long = " ".join(["A sentence that is rather long to fill the segment."] * 40)
        self.assertTrue(all(len(s) <= narration.SEGMENT_LIMIT for s in narration.split_segments(long)))
        plan = narration.preflight([self.scene("Checked."), {**self.scene("Unchecked 123."), "chapter_id": "b", "narration_checked": False}],
                                   {"available": True, "per_request_usd": 0.01, "story_budget_usd": 1})
        self.assertEqual([s["chapter_id"] for s in plan["segments"]], ["a"])
        self.assertEqual(plan["skipped"][0]["chapter_id"], "b")

    def test_budget_and_daily_allowance_fall_back_to_captions(self):
        capability = {"available": True, "per_request_usd": 0.5, "story_budget_usd": 0.1}
        self.assertFalse(narration.preflight([self.scene("Hello there.")], capability)["available"])
        capability = {"available": True, "per_request_usd": 0.0, "story_budget_usd": 1}
        self.assertFalse(narration.preflight([self.scene("Hello there.")], capability, used_today=narration.DAILY_LIMIT)["available"])

    def test_first_provider_failure_stops_without_retry_and_falls_back(self):
        import tempfile
        calls = []

        def failing(text):
            calls.append(text)
            raise RuntimeError("provider down")
        plan = narration.preflight([self.scene("One. Two."), {**self.scene("Three."), "chapter_id": "b"}], {"available": True, "per_request_usd": 0, "story_budget_usd": 1})
        with tempfile.TemporaryDirectory() as cache:
            result = narration.narrate(plan, cache, failing)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["status"], "captions-only")
        self.assertIn("not retried", result["reason"])

    def test_cached_audio_is_reused(self):
        import tempfile
        plan = narration.preflight([self.scene("Cached line.")], {"available": True, "per_request_usd": 0, "story_budget_usd": 1})
        calls = []
        with tempfile.TemporaryDirectory() as cache:
            for _ in range(2):
                result = narration.narrate(plan, cache, lambda t: calls.append(t) or b"mp3")
        self.assertEqual(len(calls), 1)
        self.assertTrue(result["segments"][0]["cached"])


class RenderTests(StudioCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required for the actual bounded-worker check.')
    def test_node_worker_persists_phase_protocol_and_terminates_excess_working_storage(self):
        import os
        phases = []
        def progress(value):
            pass
        progress.phase = phases.append
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); job_dir = root / 'job'; job_dir.mkdir()
            (root / 'render-local.mjs').write_text("""import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
console.log('PHASE preparing-assets');
console.log('PHASE rendering');
console.log('PHASE finalizing');
writeFileSync(join(process.argv[2], 'oversized.tmp'), Buffer.alloc(1024));
setInterval(() => {}, 1000);
""")
            with patch.dict(os.environ, {'FIREATLAS_STUDIO_LOCAL_RENDER': '1'}), \
                    patch('fireatlas.studio.capabilities.RENDER_DIR', root), \
                    patch('fireatlas.studio.render.WORKING_LIMIT', 100):
                with self.assertRaises(StudioError) as refused:
                    node_runner(job_dir, progress, threading.Event())
            self.assertEqual(refused.exception.code, 'render-limit')
            self.assertEqual(phases, ['preparing-assets', 'rendering', 'finalizing'])

    def manager(self, **kwargs):
        defaults = dict(runner=fake_video, capability=AVAILABLE, narration_capability=NARRATION_OFF, background=False)
        defaults.update(kwargs)
        self.service.renders = RenderManager(self.service.store, **defaults)
        return self.service.renders

    def ready_story(self):
        document, _ = self.bound_board()
        return self.service.create_story(self.owner, document["id"], {})

    def test_video_unavailable_is_a_truthful_state_and_exports_still_work(self):
        story = self.ready_story()
        with self.assertRaises(Unavailable) as refused:
            self.service.start_render(self.owner, story["id"])
        self.assertEqual(refused.exception.code, "video-unavailable")
        self.assertEqual(refused.exception.status, 503)
        self.service.export_story(self.owner, story["id"], self.root / "out")

    def test_render_completes_with_a_manifest_that_names_the_caption_fallback(self):
        manager = self.manager()
        story = self.ready_story()
        job = self.service.start_render(self.owner, story["id"])
        view = manager.get(self.owner, job["id"])
        self.assertEqual(view["status"], "queued")
        manager.execute(job["id"], self.owner)
        view = manager.get(self.owner, job["id"])
        self.assertEqual(view["status"], "completed", view)
        self.assertTrue(view["manifest"]["captions_fallback"])
        self.assertEqual(view["manifest"]["narration"]["status"], "captions-only")
        self.assertEqual(view["manifest"]["profile"]["width"], 1920)
        self.assertFalse(view['manifest']['subtitles']['embedded'], 'A fake renderer cannot attest an embedded subtitle stream.')
        for name in ("video", "manifest", "transcript", "captions", "evidence"):
            path, mime = manager.artifact(self.owner, job["id"], name)
            self.assertTrue(path.is_file())
        with self.assertRaises(StudioError):
            manager.get(self.other, job["id"])

    def test_native_engine_calls_actual_adapter_and_records_provider_identity(self):
        manager = self.manager(capability=lambda: {'available': True, 'engine': 'aiand-native-video'})
        story = self.ready_story()
        def native(directory, progress, cancel, cache):
            (directory/'provider-receipts.json').write_text(json.dumps({'model':'minimaxai/minimax-h3','disclosure':'Generated motion with exact frozen evidence.','clips':[]}))
            return fake_video(directory, progress, cancel)
        with patch('fireatlas.studio.aiand_video.verify_access'), patch('fireatlas.studio.aiand_video.run', side_effect=native) as adapter:
            job = self.service.start_render(self.owner, story['id'])
            manager.execute(job['id'],self.owner)
        result = manager.get(self.owner,job['id'])
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual(result['manifest']['engine'],'aiand-native-video')
        self.assertEqual(result['manifest']['provider']['model'],'minimaxai/minimax-h3')
        adapter.assert_called_once()

    def test_native_failure_never_invokes_local_renderer(self):
        from unittest.mock import Mock
        local = Mock(side_effect=AssertionError('Local fallback must not run.'))
        manager = self.manager(runner=local,capability=lambda:{'available':True,'engine':'aiand-native-video'})
        story = self.ready_story()
        with patch('fireatlas.studio.aiand_video.verify_access'), patch('fireatlas.studio.aiand_video.run',side_effect=StudioError('AI& unavailable')):
            job=self.service.start_render(self.owner,story['id'])
            manager.execute(job['id'],self.owner)
        self.assertEqual(manager.get(self.owner,job['id'])['status'],'failed')
        local.assert_not_called()

    def test_narration_is_attempted_and_provider_failure_falls_back_silently(self):
        from fireatlas.studio.story import resolve_story  # noqa: F401 - ensure the module imports
        narrated = lambda: {"available": True, "reason": None, "per_request_usd": 0, "story_budget_usd": 1}
        document, snapshot = self.bound_board()
        value = next(f["value"] for f in snapshot["facts"] if f["state"] == "observed" and isinstance(f["value"], (int, float)))
        story = self.service.create_story(self.owner, document["id"], {"title": "Voiced", "chapters": [
            {"id": "a", "title": "A", "card_id": "c1", "duration_seconds": 20, "narration": f"The value is {value}."}]})
        manager = self.manager(narration_capability=narrated, synthesize=lambda text: (_ for _ in ()).throw(RuntimeError("down")))
        job = self.service.start_render(self.owner, story["id"], narration_requested=True)
        manager.execute(job["id"], self.owner)
        view = manager.get(self.owner, job["id"])
        self.assertEqual(view["status"], "completed")
        self.assertEqual(view["manifest"]["narration"]["status"], "captions-only")
        story2 = self.service.create_story(self.owner, document["id"], {"title": "Voiced two", "chapters": [
            {"id": "a", "title": "A", "card_id": "c1", "duration_seconds": 20, "narration": f"The value is {value}."}]})
        manager = self.manager(narration_capability=narrated, synthesize=lambda text: b"audio", audio_probe=lambda path: 0.2)
        job = self.service.start_render(self.owner, story2["id"], narration_requested=True)
        manager.execute(job["id"], self.owner)
        view = manager.get(self.owner, job["id"])
        self.assertEqual(view["manifest"]["narration"]["status"], "narrated")
        self.assertFalse(view["manifest"]["captions_fallback"])
        self.assertIn("AI-generated", view["manifest"]["narration"]["disclosure"])

    def test_overlong_voice_completes_as_silent_captions_without_paid_retry_or_story_change(self):
        calls = []
        document, _ = self.bound_board()
        story = self.service.create_story(self.owner, document['id'], {'chapters': [{
            'id': 'a', 'title': 'Study scope', 'card_id': 'c1', 'duration_seconds': 20, 'narration': 'Inspect this saved study.'}]})
        before = self.service.resolve_story(self.owner, story['id'])['resolved']
        manager = self.manager(narration_capability=lambda: {'available': True, 'per_request_usd': 0, 'story_budget_usd': 1},
                               synthesize=lambda text: calls.append(text) or b'fixture audio', audio_probe=lambda _: 150)
        for _ in range(2):
            job = self.service.start_render(self.owner, story['id'], narration_requested=True)
            manager.execute(job['id'], self.owner)
            view = manager.get(self.owner, job['id'])
            self.assertEqual(view['status'], 'completed', view)
            self.assertEqual(view['manifest']['narration']['status'], 'captions-only')
            self.assertIn('exceeds', view['manifest']['narration']['reason'])
            self.assertFalse(view['manifest']['narration']['timing']['checked'])
            self.assertTrue(view['manifest']['narration']['cached_segments'])
            prepared = json.loads((manager.root / job['id'] / 'input.json').read_text())
            self.assertEqual(prepared['audio'], [])
            self.assertEqual(prepared['resolved']['sha256'], stories.public_copy(before)['sha256'])
            self.assertEqual((manager.root / job['id'] / 'captions.vtt').read_text(), stories.captions(before))
        self.assertEqual(calls, ['Inspect this saved study.'])
        self.assertEqual(self.service.resolve_story(self.owner, story['id'])['resolved'], before)

    @unittest.skipUnless(shutil.which('node') and shutil.which('ffmpeg') and shutil.which('ffprobe') and
                         any(shutil.which(name) for name in ('chromium', 'chromium-browser', 'google-chrome')),
                         'Optional local rendering/audio tools are unavailable.')
    def test_actual_local_video_keeps_complete_audio_at_saved_chapter_boundaries(self):
        import array
        import math
        document, _ = self.bound_board('replay', kind='map')
        story = self.service.create_story(self.owner, document['id'], {'title': 'Local audio fixture QA', 'target_duration_seconds': 10,
            'chapters': [{'id': 'a', 'title': 'First fixture', 'card_id': 'c1', 'duration_seconds': 5, 'narration': 'Inspect the selected study.'},
                         {'id': 'b', 'title': 'Second fixture', 'card_id': 'c1', 'duration_seconds': 5, 'narration': 'Inspect the saved evidence.'}]})
        fixtures = []
        for frequency in (440, 880):
            result = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f'sine=frequency={frequency}:duration=0.5',
                                     '-c:a', 'libmp3lame', '-f', 'mp3', '-'], capture_output=True, check=True)
            fixtures.append(result.stdout)
        calls = []
        def fixture_provider(text):
            calls.append(text)
            return fixtures[len(calls) - 1]
        manager = self.manager(runner=node_runner, narration_capability=lambda: {'available': True, 'per_request_usd': 0, 'story_budget_usd': 1},
                               synthesize=fixture_provider)
        with patch.dict('os.environ', {'FIREATLAS_STUDIO_LOCAL_RENDER': '1'}):
            job = self.service.start_render(self.owner, story['id'], narration_requested=True)
            manager.execute(job['id'], self.owner)
        view = manager.get(self.owner, job['id'])
        self.assertEqual(view['status'], 'completed', view)
        self.assertEqual(view['manifest']['narration']['status'], 'narrated')
        self.assertTrue(view['manifest']['narration']['timing']['checked'])
        self.assertEqual([c['chapter_start_seconds'] for c in view['manifest']['narration']['timing']['chapters']], [0, 5])
        video, _ = manager.artifact(self.owner, job['id'], 'video')
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(video)], capture_output=True, text=True, check=True)
        streams = json.loads(probe.stdout)['streams']
        self.assertEqual([s['codec_type'] for s in streams], ['video', 'audio', 'subtitle'])
        self.assertAlmostEqual(float(next(s for s in streams if s['codec_type'] == 'audio')['duration']), 10, delta=.1)
        decoded = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(video), '-map', '0:a:0', '-ar', '48000', '-ac', '1', '-f', 's16le', '-'], capture_output=True, check=True)
        samples = array.array('h'); samples.frombytes(decoded.stdout)
        def rms(start, end):
            values = samples[round(start * 48000):round(end * 48000)]
            return math.sqrt(sum(v * v for v in values) / len(values)) / 32768
        for begin, end in ((.1, .4), (5.1, 5.4)):
            self.assertGreater(rms(begin, end), .01, 'Both complete fixture segments must be audible in their own chapters.')
        for begin, end in ((1, 4.5), (6, 9.5)):
            self.assertLess(rms(begin, end), .001, 'Padding must not move or overlap narration across chapters.')
        self.assertEqual(calls, ['Inspect the selected study.', 'Inspect the saved evidence.'])

    def test_one_render_at_a_time_and_queued_cancel(self):
        manager = self.manager()
        story = self.ready_story()
        job = self.service.start_render(self.owner, story["id"], key="render-key-1")
        again = self.service.start_render(self.owner, story["id"], key="render-key-1")
        self.assertTrue(again["idempotent_replay"])
        with self.assertRaises(Conflict) as busy:
            self.service.start_render(self.owner, story["id"])
        self.assertEqual(busy.exception.code, "render-busy")
        cancelled = manager.cancel(self.owner, job["id"])
        self.assertEqual(cancelled["status"], "canceled")
        manager.execute(job["id"], self.owner)
        self.assertEqual(manager.get(self.owner, job["id"])["status"], "canceled")

    def test_cancel_after_speech_does_not_start_the_encoder(self):
        document, _ = self.bound_board()
        story = self.service.create_story(self.owner, document['id'], {'chapters': [{
            'id': 'a', 'title': 'Saved scope', 'card_id': 'c1', 'duration_seconds': 20, 'narration': 'Inspect this selected study.'}]})
        job_id = []
        def synthesize(text):
            manager.cancel(self.owner, job_id[0])
            return b'fixture audio'
        manager = self.manager(runner=lambda *_: self.fail('Canceled speech must not start the encoder.'),
            narration_capability=lambda: {'available': True, 'per_request_usd': 0, 'story_budget_usd': 1}, synthesize=synthesize)
        job = self.service.start_render(self.owner, story['id'], narration_requested=True)
        job_id.append(job['id'])
        manager.execute(job['id'], self.owner)
        view = manager.get(self.owner, job['id'])
        self.assertEqual(view['status'], 'canceled')
        self.assertFalse(view['artifacts'])
        self.assertTrue(list((self.service.store.root / 'narration').glob('*.mp3')), 'Already generated audio remains cached, with no late video publication.')

    def test_running_cancel_discards_partial_output(self):
        started, release = threading.Event(), threading.Event()

        def slow(job_dir, progress, cancel):
            (Path(job_dir) / "partial.mp4").write_bytes(b"partial")
            started.set()
            cancel.wait(10)
            return None
        manager = self.manager(runner=slow, background=True)
        story = self.ready_story()
        job = self.service.start_render(self.owner, story["id"])
        self.assertTrue(started.wait(10))
        manager.cancel(self.owner, job["id"])
        deadline = time.time() + 10
        while time.time() < deadline and manager.get(self.owner, job["id"])["status"] != "canceled":
            time.sleep(0.05)
        self.assertEqual(manager.get(self.owner, job["id"])["status"], "canceled")
        self.assertFalse(list((manager.root / job["id"]).glob("*.mp4")))
        self.assertEqual(manager.get(self.owner, job["id"])["artifacts"], {})

    def test_restart_marks_a_running_job_failed_and_allows_resubmission(self):
        manager = self.manager()
        story = self.ready_story()
        job = self.service.start_render(self.owner, story["id"])
        manager._update(job["id"], status="running")
        work = manager.root / job['id']
        (work / 'frames').mkdir()
        (work / 'frames' / 'scene.png').write_bytes(b'partial frame')
        (work / 'briefing.mp4').write_bytes(b'unpublished video')
        recovered = self.manager()
        view = recovered.get(self.owner, job["id"])
        self.assertEqual(view["status"], "failed")
        self.assertIn("interrupted", view["error"])
        self.assertEqual(view['phase'], 'failed')
        self.assertFalse((work / 'frames').exists())
        self.assertFalse((work / 'briefing.mp4').exists())
        self.assertTrue((work / 'resolved.json').is_file())
        self.assertFalse(manager._update(job['id'], status='completed', progress=1))
        self.assertEqual(recovered.get(self.owner, job['id'])['status'], 'failed')
        self.assertEqual(self.service.start_render(self.owner, story["id"])["status"], "queued")

    def test_cancel_at_publication_never_exposes_a_finished_video(self):
        manager = self.manager(); story = self.ready_story()
        job = self.service.start_render(self.owner, story['id'])
        update = manager._update
        def cancel_at_commit(identifier, **fields):
            if fields.get('status') == 'completed':
                manager.cancel(self.owner, identifier)
            return update(identifier, **fields)
        manager._update = cancel_at_commit
        manager.execute(job['id'], self.owner)
        view = manager.get(self.owner, job['id'])
        self.assertEqual((view['status'], view['phase']), ('canceled', 'canceled'))
        self.assertEqual(view['artifacts'], {})
        self.assertFalse((manager.root / job['id'] / 'briefing.mp4').exists())
        with self.assertRaises(StudioError):
            manager.artifact(self.owner, job['id'], 'video')
        self.assertFalse(update(job['id'], status='completed', progress=1))
        self.assertFalse(update(job['id'], phase='encoding', progress=.9))
        self.assertEqual(self.service.get_story(self.owner, story['id'])['revision'], story['revision'])

    def test_render_phases_are_durable_and_intermediates_are_removed(self):
        seen = []
        def render(job_dir, progress, cancel):
            for phase in ('rendering', 'encoding'):
                progress.phase(phase)
                seen.append(manager.get(self.owner, job['id'])['phase'])
            (Path(job_dir) / 'frames').mkdir()
            (Path(job_dir) / 'frames' / 'scene.png').write_bytes(b'frame')
            (Path(job_dir) / 'silent.mp4').write_bytes(b'encoder intermediate')
            return fake_video(job_dir, progress, cancel)
        manager = self.manager(runner=render); story = self.ready_story()
        job = self.service.start_render(self.owner, story['id'])
        self.assertEqual(job['phase'], 'queued')
        manager.execute(job['id'], self.owner)
        self.assertEqual(seen, ['rendering', 'encoding'])
        final = manager.get(self.owner, job['id'])
        self.assertEqual(final['phase'], 'completed')
        self.assertEqual(final['manifest']['renderer_configuration']['phase_protocol'], 1)
        self.assertFalse((manager.root / job['id'] / 'frames').exists())
        self.assertFalse((manager.root / job['id'] / 'silent.mp4').exists())
        self.assertTrue(manager.artifact(self.owner, job['id'], 'video')[0].is_file())

    def test_oversized_scene_is_refused_before_speech_or_encoder(self):
        from unittest.mock import patch
        manager = self.manager(runner=lambda *_: self.fail('Oversized input reached encoder.'),
            narration_capability=lambda: {'available': True, 'per_request_usd': 0, 'story_budget_usd': 1},
            synthesize=lambda *_: self.fail('Oversized input reached speech.'))
        story = self.ready_story()
        job = self.service.start_render(self.owner, story['id'], narration_requested=True)
        with patch('fireatlas.studio.render.INPUT_LIMIT', 100):
            manager.execute(job['id'], self.owner)
        final = manager.get(self.owner, job['id'])
        self.assertEqual(final['phase'], 'failed')
        self.assertIn('32 MB', final['error'])
        self.assertEqual(final['artifacts'], {})

    def test_recent_export_history_is_owned_bounded_and_survives_recovery(self):
        manager = self.manager(); story = self.ready_story()
        job = self.service.start_render(self.owner, story['id'])
        manager.execute(job['id'], self.owner)
        current = self.service.document_projects(self.owner, story['document_id'])
        self.assertEqual(current['renders'][0]['id'], job['id'])
        self.assertEqual(current['renders'][0]['story_revision'], story['revision'])
        self.assertEqual(current['renders'][0]['status'], 'completed')
        recovered = self.manager()
        self.assertEqual(recovered.get(self.owner, job['id'])['status'], 'completed')
        self.assertEqual(self.service.document_projects(self.owner, story['document_id'])['renders'], current['renders'])
        other = self.board(title='Other scope')
        self.assertEqual(self.service.document_projects(self.owner, other['id'])['renders'], [])
        with self.assertRaises(StudioError):
            self.service.document_projects(self.other, story['document_id'])
        # Simulate a longer durable history; summaries must stay bounded and
        # must not load full manifests or video bytes just to open the editor.
        with self.service.store.connection(write=True) as db:
            for index in range(35):
                db.execute('INSERT INTO renders(id,owner_id,document_id,story_id,story_revision,status,profile,manifest,artifact,error,cancel,progress,created,updated) SELECT ?,owner_id,document_id,story_id,story_revision,status,profile,manifest,artifact,error,cancel,progress,?,updated FROM renders WHERE id=?',
                           ('history_' + str(index), time.time() + index, job['id']))
        history = self.service.document_projects(self.owner, story['document_id'])
        self.assertEqual(history['renders_total'], 36)
        self.assertEqual(len(history['renders']), 30)
        self.assertTrue(all('manifest' not in entry and 'artifacts' not in entry for entry in history['renders']))

    def test_renderer_failure_is_a_visible_state(self):
        def broken(job_dir, progress, cancel):
            raise StudioError("The renderer exited with an error: boom", code="render-failed")
        manager = self.manager(runner=broken)
        story = self.ready_story()
        job = self.service.start_render(self.owner, story["id"])
        manager.execute(job["id"], self.owner)
        view = manager.get(self.owner, job["id"])
        self.assertEqual(view["status"], "failed")
        self.assertIn("boom", view["error"])


if __name__ == "__main__":
    unittest.main()
