"""Real controlled-worker limits and retained-export admission, without provider calls."""
from __future__ import annotations
import os
import json
import time
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fireatlas.studio import capabilities, resources
from fireatlas.studio.errors import StudioError
from fireatlas.studio.render import RenderManager, node_runner, WORKING_LIMIT
from fireatlas.studio.narration import AUDIO_TOTAL_LIMIT
try:
    from studio_support import StudioCase
    from test_studio_story import AVAILABLE, NARRATION_OFF, fake_video
except ImportError:
    from .studio_support import StudioCase
    from .test_studio_story import AVAILABLE, NARRATION_OFF, fake_video


@unittest.skipUnless(shutil.which('node') and resources.monitor_available(), 'Node and Linux /proc are required for the actual worker test.')
class WorkerResourcesTests(unittest.TestCase):
    def run_worker(self, source, **limits):
        measured = {}
        def progress(value):
            pass
        progress.resources = measured.update
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); job = root / 'job'; job.mkdir()
            (root / 'render-local.mjs').write_text(source)
            with patch.dict(os.environ, {'FIREATLAS_STUDIO_LOCAL_RENDER': '1'}), patch('fireatlas.studio.capabilities.RENDER_DIR', root):
                patches = [patch.object(resources, name, value) for name, value in limits.items()]
                for item in patches: item.start()
                try:
                    with self.assertRaises(StudioError) as refused:
                        node_runner(job, progress, threading.Event())
                finally:
                    for item in reversed(patches): item.stop()
            return refused.exception, measured, (job / 'child.pid').read_text() if (job / 'child.pid').exists() else None

    def test_memory_limit_includes_a_detached_child_and_does_not_stop_unrelated_work(self):
        control = subprocess.Popen(['node', '-e', 'setInterval(()=>{},1000)'], start_new_session=True)
        try:
            error, measured, child_pid = self.run_worker("""
import { spawn } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
const child = spawn(process.execPath, ['-e', 'globalThis.keep=Buffer.alloc(96*1024*1024,7);setInterval(()=>{},1000)'], {detached:true,stdio:'ignore'});
writeFileSync(join(process.argv[2], 'child.pid'), String(child.pid));
setInterval(()=>{},1000);
""", MEMORY_LIMIT=100 * 1024 ** 2)
            self.assertEqual(error.code, 'render-memory-limit')
            self.assertGreaterEqual(measured['tracked_process_identities'], 2)
            self.assertGreater(measured['peak_summed_resident_bytes'], 100 * 1024 ** 2)
            self.assertIsNotNone(child_pid)
            child = resources.process_info(int(child_pid))
            self.assertTrue(child is None or child['state'] == 'Z', child)
            self.assertIsNone(control.poll(), 'Other same-user work must remain running.')
        finally:
            control.terminate(); control.wait(timeout=5)

    def test_cpu_limit_terminates_an_actual_busy_worker(self):
        error, measured, _ = self.run_worker('while(true) { Math.sqrt(Math.random()); }', CPU_SECONDS=.06)
        self.assertEqual(error.code, 'render-cpu-limit')
        self.assertGreater(measured['sampled_cpu_seconds'], .06)

    def test_monitor_failure_stops_the_worker_and_reports_unavailable(self):
        with patch.object(resources.ProcessBudget, 'sample', side_effect=StudioError('Counters unavailable', code='render-monitor-unavailable')):
            error, _, _ = self.run_worker('setInterval(()=>{},1000)')
        self.assertEqual(error.code, 'render-monitor-unavailable')


class RetainedStorageTests(StudioCase):
    def ready(self):
        doc, _ = self.bound_board()
        manager = RenderManager(self.service.store, runner=fake_video, capability=AVAILABLE,
                                narration_capability=NARRATION_OFF, background=False)
        self.service.renders = manager
        return manager, self.service.create_story(self.owner, doc['id'], {})

    def test_capacity_refuses_new_jobs_without_deleting_completed_exports_or_spending(self):
        manager, story = self.ready()
        first = self.service.start_render(self.owner, story['id'])
        manager.execute(first['id'], self.owner)
        saved, _ = manager.artifact(self.owner, first['id'], 'video')
        original = saved.read_bytes()
        used = resources.file_usage([manager.root, manager.store.root / 'narration'])['bytes']
        manager.storage.limit = used + WORKING_LIMIT + AUDIO_TOTAL_LIMIT - 1
        manager.narration_capability = lambda: self.fail('Capacity refusal must precede speech.')
        manager.synthesize = lambda _: self.fail('Capacity refusal must precede speech.')
        with self.assertRaises(StudioError) as refused:
            self.service.start_render(self.owner, story['id'], narration_requested=True)
        self.assertEqual(refused.exception.code, 'render-storage-full')
        self.assertEqual(saved.read_bytes(), original)
        self.assertEqual(self.service.get_story(self.owner, story['id'])['revision'], story['revision'])
        with manager.store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM renders').fetchone()[0], 1)

    def test_low_volume_space_refuses_admission_and_file_write_failure_rolls_back_queue(self):
        manager, story = self.ready()
        with patch.object(resources.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)):
            with self.assertRaises(StudioError) as refused:
                self.service.start_render(self.owner, story['id'])
        self.assertEqual(refused.exception.code, 'render-storage-low')
        with patch.object(Path, 'write_text', side_effect=OSError('simulated full disk')):
            with self.assertRaises(StudioError) as failed:
                self.service.start_render(self.owner, story['id'])
        self.assertEqual(failed.exception.code, 'render-storage-unavailable')
        self.assertEqual(list(manager.root.iterdir()), [])
        with manager.store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM renders').fetchone()[0], 0)
        self.assertEqual(self.service.start_render(self.owner, story['id'])['status'], 'queued')

    def test_capacity_is_rechecked_before_audio_and_when_worker_checks_storage(self):
        manager, story = self.ready()
        job = self.service.start_render(self.owner, story['id'], narration_requested=True)
        manager.storage.limit = 1
        manager.narration_capability = lambda: self.fail('No speech preparation may happen after capacity changes.')
        manager.execute(job['id'], self.owner)
        result = manager.get(self.owner, job['id'])
        self.assertEqual(result['phase'], 'failed')
        self.assertIn('storage capacity', result['error'])
        self.assertEqual(result['artifacts'], {})

    @unittest.skipUnless(shutil.which('node') and resources.monitor_available(), 'Actual worker recovery needs Linux and Node.')
    def test_restart_stops_the_verified_encoder_and_detached_child_before_resubmission(self):
        manager, story = self.ready()
        job = self.service.start_render(self.owner, story['id'])
        manager._update(job['id'], status='running')
        job_dir = manager.root / job['id']
        script = self.root / 'render-local.mjs'
        script.write_text("""import { spawn } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
const child = spawn(process.execPath, ['-e','setInterval(()=>{},1000)'], {detached:true,stdio:'ignore'});
writeFileSync(join(process.argv[2],'child.pid'),String(child.pid));
setInterval(()=>{},1000);
""")
        process = subprocess.Popen(['node', str(script), str(job_dir.resolve())], start_new_session=True)
        try:
            deadline = time.monotonic() + 5
            while not (job_dir / 'child.pid').exists() and time.monotonic() < deadline: time.sleep(.02)
            child_pid = int((job_dir / 'child.pid').read_text())
            budget = resources.ProcessBudget(process.pid)
            budget.sample(); budget.save(job_dir)
            self.assertIn(child_pid, budget.known)
            restored = RenderManager(manager.store, capability=AVAILABLE, background=False)
            process.wait(timeout=5)
            self.assertIsNotNone(process.poll())
            child = resources.process_info(child_pid)
            self.assertTrue(child is None or child['state'] == 'Z', child)
            self.assertEqual(restored.get(self.owner, job['id'])['phase'], 'failed')
            self.assertIsNone(restored.recovery_error)
            self.assertFalse((job_dir / 'worker.json').exists())
            self.assertTrue((job_dir / 'resolved.json').exists())
            self.service.renders = restored
            self.assertEqual(self.service.start_render(self.owner, story['id'])['phase'], 'queued')
        finally:
            if process.poll() is None: process.terminate(); process.wait(timeout=5)

    @unittest.skipUnless(shutil.which('node') and resources.monitor_available(), 'Actual worker identity checks need Linux and Node.')
    def test_forged_worker_identity_never_signals_other_work_and_blocks_until_repaired(self):
        manager, story = self.ready()
        job = self.service.start_render(self.owner, story['id'])
        manager._update(job['id'], status='running')
        job_dir = manager.root / job['id']
        control = subprocess.Popen(['node', '-e', 'setInterval(()=>{},1000)'], start_new_session=True)
        try:
            budget = resources.ProcessBudget(control.pid); budget.save(job_dir)
            restored = RenderManager(manager.store, capability=AVAILABLE, background=False)
            self.assertIsNone(control.poll())
            self.assertIsNotNone(restored.recovery_error)
            with self.assertRaises(StudioError) as refused:
                restored.submit(self.owner, story['document_id'], story['id'], {'warnings': []})
            self.assertEqual(refused.exception.code, 'render-recovery-unavailable')
            again = RenderManager(manager.store, capability=AVAILABLE, background=False)
            self.assertIsNotNone(again.recovery_error, 'Restarting must not bypass an unresolved recovery problem.')
            self.assertIsNone(control.poll())
            # Remove only the test's forged worker record; the real saved story
            # and completed-download inventory remain untouched.
            (job_dir / 'worker.json').unlink()
            fixed = RenderManager(manager.store, capability=AVAILABLE, background=False)
            self.assertIsNone(fixed.recovery_error)
        finally:
            control.terminate(); control.wait(timeout=5)

    def test_unavailable_monitor_keeps_reader_capabilities_truthful(self):
        with patch.object(resources, 'monitor_available', return_value=False):
            state = capabilities.video()
        self.assertFalse(state['available'])
        self.assertIn('reader exports remain available', state['reason'])


if __name__ == '__main__':
    unittest.main()
