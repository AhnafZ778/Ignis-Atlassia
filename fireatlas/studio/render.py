"""Bounded render service: one job at a time, persistent lifecycle, cancellation and interruption recovery.

Remotion consumes only the resolved story (data), never user-supplied code. When Remotion is not
available the job is refused with a truthful state and story editing and static export carry on.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import threading
import time
import signal
import shutil
from collections import deque
from pathlib import Path

from . import capabilities, narration, resources, story
from .errors import Conflict, NotFound, StudioError, Unavailable
from .store import dumps

STATES = ("queued", "running", "completed", "failed", "canceled")
PHASES = ("queued", "preparing-assets", "narrating", "generating-video", "rendering", "encoding", "finalizing", "completed", "failed", "canceled")
WORKING_LIMIT = 1024 * 1024 * 1024
INPUT_LIMIT = 32_000_000
RECOVERY_ERROR = 'An interrupted worker could not be safely recovered. Existing stories and downloads remain available.'
ARTIFACTS = {"video": "briefing.mp4", "manifest": "manifest.json", "transcript": "transcript.txt", "captions": "captions.vtt",
             "evidence": "evidence-hashes.json"}
MIME = {"briefing.mp4": "video/mp4", "manifest.json": "application/json", "transcript.txt": "text/plain; charset=utf-8",
        "captions.vtt": "text/vtt; charset=utf-8", "evidence-hashes.json": "application/json"}


def node_runner(job_dir, progress, cancel, *, script=None):
    """Run the configured local renderer. Output lines ``PROGRESS <0..1>`` update the job; cancel terminates it."""
    script = script or ("render-local.mjs" if os.getenv("FIREATLAS_STUDIO_LOCAL_RENDER", "").lower() in {"1", "true", "yes", "on"} else "render.mjs")
    if not resources.monitor_available():
        raise Unavailable('Local video requires the Linux process-resource monitor. Reader exports remain available.', code='render-monitor-unavailable')
    process = subprocess.Popen(["node", "--max-old-space-size=768", script, str(Path(job_dir).resolve())], cwd=str(capabilities.RENDER_DIR), stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        budget = resources.ProcessBudget(process.pid)
        budget.save(job_dir)
    except Exception:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=3)
        process.stdout.close()
        raise
    def stop_worker():
        try:
            budget.terminate()
        except (OSError, StudioError):
            # If monitoring fails, the unreaped Popen child still has its own
            # reserved PID/session. Fail closed without touching other jobs.
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
    lines = deque(maxlen=32)
    started = time.monotonic()
    timed_out = threading.Event()
    storage_exceeded = threading.Event()
    stopped = threading.Event()
    resource_error = []
    def watch():
        checked_storage = 0
        try:
            while not stopped.is_set() and process.poll() is None:
                measured = budget.sample()
                budget.save(job_dir)
                if measured['peak_summed_resident_bytes'] > resources.MEMORY_LIMIT:
                    raise StudioError('The renderer and its observed child processes exceeded the 2 GiB resident-memory limit. '
                                      'Use fewer image chapters.', code='render-memory-limit')
                if measured['sampled_cpu_seconds'] > resources.CPU_SECONDS:
                    raise StudioError('The renderer exceeded its cumulative CPU-time limit. Use a shorter story.', code='render-cpu-limit')
                if time.monotonic() - checked_storage >= 1:
                    checked_storage = time.monotonic()
                    if resources.file_usage([Path(job_dir)])['bytes'] > WORKING_LIMIT:
                        storage_exceeded.set()
                    storage_check = getattr(progress, 'storage', None)
                    if storage_check:
                        storage_check()
                if cancel.is_set() or storage_exceeded.is_set() or time.monotonic() - started > 900:
                    if not cancel.is_set() and not storage_exceeded.is_set():
                        timed_out.set()
                    stop_worker()
                    return
                stopped.wait(.2)
        except Exception as error:
            resource_error.append(error)
            stop_worker()
    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    try:
        with process.stdout as output:
            for line in output:
                lines.append(line.rstrip()[:1000])
                if line.startswith("PROGRESS "):
                    try:
                        progress(float(line.split()[1]))
                    except ValueError:
                        pass
                elif line.startswith('PHASE '):
                    phase = line.strip().split(' ', 1)[1]
                    callback = getattr(progress, 'phase', None)
                    if phase in ('preparing-assets', 'rendering', 'encoding', 'finalizing') and callback:
                        callback(phase)
        code = process.wait()
    finally:
        stopped.set()
        watcher.join(timeout=3)
        stop_worker()
        process.wait(timeout=3)
        if watcher.is_alive():
            raise Unavailable('The renderer resource monitor did not finish. Nothing was published.', code='render-monitor-unavailable')
        measured_callback = getattr(progress, 'resources', None)
        if measured_callback:
            measured_callback(budget.report())
    if cancel.is_set():
        return None
    if resource_error:
        raise resource_error[0]
    if timed_out.is_set():
        raise StudioError("The renderer exceeded its 15-minute execution limit.", code="render-timeout")
    if storage_exceeded.is_set():
        raise StudioError('The render exceeded its 1 GiB working-file limit. Use a shorter story.', code='render-limit')
    if code != 0:
        raise StudioError("The renderer exited with an error: " + " ".join(list(lines)[-3:])[:300], code="render-failed")
    return Path(job_dir) / ARTIFACTS["video"]


class RenderManager:
    def __init__(self, store, runner=node_runner, capability=capabilities.video, narration_capability=capabilities.narration,
                 synthesize=None, background=True, synthesize_factory=None, audio_probe=narration.audio_duration,
                 storage_budget=None):
        self.store, self.runner, self.capability = store, runner, capability
        self.narration_capability, self.synthesize, self.background = narration_capability, synthesize, background
        self.synthesize_factory = synthesize_factory
        self.audio_probe = audio_probe
        self.root = store.root / "renders"
        self.root.mkdir(parents=True, exist_ok=True)
        self.storage = storage_budget or resources.StorageBudget(store.root)
        self.events, self.lock = {}, threading.Lock()
        self.recovery_error = None
        self.recover()

    def recover(self):
        """A restart never resumes a half-finished Remotion process: interrupted jobs fail visibly and may be resubmitted."""
        with self.store.connection(write=True) as db:
            now = self.store.clock()
            interrupted = [row['id'] for row in db.execute("SELECT id FROM renders WHERE status IN ('queued','running') OR error=?", (RECOVERY_ERROR,))]
            db.execute("UPDATE renders SET status='failed',phase='failed',error=?,updated=? WHERE status IN ('queued','running')",
                       ("interrupted: the service stopped during this render. Submit it again; nothing was published.", now))
        for identifier in interrupted:
            try:
                if self.runner is node_runner and resources.monitor_available():
                    resources.recover_worker(self.root / identifier)
                self._clean_working(self.root / identifier, discard=True)
                with self.store.connection(write=True) as db:
                    db.execute('UPDATE renders SET error=? WHERE id=?', ('interrupted: worker stopped and unfinished media discarded. Submit the saved story again.', identifier))
            except (OSError, StudioError) as error:
                self.recovery_error = RECOVERY_ERROR
                with self.store.connection(write=True) as db:
                    db.execute('UPDATE renders SET error=? WHERE id=?', (self.recovery_error, identifier))

    def submit(self, principal, document_id, story_id, resolved, key=None, narration_requested=False):
        if self.recovery_error:
            raise Unavailable(self.recovery_error, code='render-recovery-unavailable')
        if not isinstance(narration_requested, bool):
            raise StudioError("Narration requires an explicit Boolean choice.", code="invalid-render")
        state = self.capability()
        if not state["available"]:
            raise Unavailable("Video rendering is unavailable: " + state["reason"] + " Story editing and static export remain available.", code="video-unavailable")
        engine = state.get('engine', 'local')
        if engine == 'aiand-native-video':
            from .aiand_video import verify_access
            verify_access()
        blocking = [w for w in resolved["warnings"] if w["problem"] in ("evidence-unfrozen", "card-missing", "checked-field-unavailable", "scene-context")]
        if blocking:
            raise StudioError("Resolve the story's evidence before rendering: " + blocking[0]["message"], code="story-not-ready", details={"warnings": blocking})
        job_dir, created_dir = None, False
        try:
            with self.store.connection(write=True) as db:
                self.store.require(db, principal, document_id, "editor")
                replayed = self.store.replay(db, principal, "render", key)
                if replayed:
                    return {**replayed, "idempotent_replay": True}
                if db.execute("SELECT 1 FROM renders WHERE status IN ('queued','running')").fetchone():
                    raise Conflict("One render runs at a time. Wait for it or cancel it.", code="render-busy")
                self.storage.check(additional_bytes=WORKING_LIMIT + narration.AUDIO_TOTAL_LIMIT, additional_files=1000)
                frozen = dumps(resolved)
                if len(frozen.encode()) > INPUT_LIMIT:
                    raise StudioError('Saved scene inputs exceed 32 MB. Reduce visible imagery or chapters.', code='render-limit')
                identifier, now = "rnd_" + secrets.token_urlsafe(12), self.store.clock()
                db.execute("INSERT INTO renders(id,owner_id,document_id,story_id,story_revision,status,profile,manifest,artifact,error,cancel,progress,created,updated) VALUES(?,?,?,?,?,?,?,NULL,NULL,NULL,0,0,?,?)",
                           (identifier, principal, document_id, story_id, resolved["story_revision"], "queued", dumps(resolved["profile"]), now, now))
                # Preparation writes and queue admission succeed together. A full
                # volume must not leave an unstartable job reserving the queue.
                job_dir = self.root / identifier
                job_dir.mkdir()
                created_dir = True
                (job_dir / "resolved.json").write_text(frozen, encoding='utf-8')
                (job_dir / "options.json").write_text(dumps({"narration_requested": narration_requested, "engine": engine}), encoding='utf-8')
                job = self._view(db, identifier)
                self.store.remember(db, principal, "render", key, job)
        except Exception as error:
            if created_dir:
                shutil.rmtree(job_dir)
            if isinstance(error, OSError):
                raise Unavailable('Render preparation could not be saved. No job or speech request was started; '
                                  'existing stories and downloads remain available.', code='render-storage-unavailable') from error
            raise
        self.events[identifier] = threading.Event()
        if self.background:
            threading.Thread(target=self.execute, args=(identifier, principal), daemon=True, name="studio-render").start()
        return job

    def _view(self, db, identifier):
        row = db.execute("SELECT * FROM renders WHERE id=?", (identifier,)).fetchone()
        provider = self.root / identifier / 'provider-progress.json'
        detail = json.loads(provider.read_text()) if provider.is_file() else None
        return {"id": row["id"], "status": row["status"], "progress": row["progress"], "story_id": row["story_id"], 'provider_progress': detail,
                'phase': row['phase'],
                "story_revision": row["story_revision"], "profile": json.loads(row["profile"]), "error": row["error"],
                "manifest": json.loads(row["manifest"]) if row["manifest"] else None, "created": row["created"], "updated": row["updated"],
                "artifacts": {k: f"/api/studio/renders/{row['id']}/artifact?name={k}" for k in ARTIFACTS} if row["status"] == "completed" else {},
                "cancel_requested": bool(row["cancel"])}

    def get(self, principal, identifier):
        with self.store.connection() as db:
            row = db.execute("SELECT document_id FROM renders WHERE id=?", (identifier,)).fetchone()
            if not row:
                raise NotFound("Render not found.", code="render-not-found")
            self.store.require(db, principal, row["document_id"])
            return self._view(db, identifier)

    def cancel(self, principal, identifier):
        with self.store.connection(write=True) as db:
            row = db.execute("SELECT document_id,status FROM renders WHERE id=?", (identifier,)).fetchone()
            if not row:
                raise NotFound("Render not found.", code="render-not-found")
            self.store.require(db, principal, row["document_id"], "editor")
            if row["status"] in ("queued", "running"):
                db.execute("UPDATE renders SET cancel=1,status=CASE WHEN status='queued' THEN 'canceled' ELSE status END,phase=CASE WHEN status='queued' THEN 'canceled' ELSE phase END,updated=? WHERE id=?",
                           (self.store.clock(), identifier))
            view = self._view(db, identifier)
        flag = self.events.get(identifier)
        if flag:
            flag.set()
        return view

    def artifact(self, principal, identifier, name):
        view = self.get(principal, identifier)
        if view["status"] != "completed" or name not in ARTIFACTS:
            raise NotFound("That artifact is not available.", code="artifact-not-found")
        path = self.root / identifier / ARTIFACTS[name]
        if not path.is_file():
            raise NotFound("That artifact is not available.", code="artifact-not-found")
        return path, MIME[ARTIFACTS[name]]

    def _update(self, identifier, **fields):
        with self.store.connection(write=True) as db:
            row = db.execute("SELECT cancel,status FROM renders WHERE id=?", (identifier,)).fetchone()
            if row['status'] in ('completed', 'failed', 'canceled'):
                return False
            if row['cancel'] and fields.get('status') == 'completed':
                db.execute("UPDATE renders SET status='canceled',phase='canceled',error=?,updated=? WHERE id=?",
                           ('Canceled before publication; the finished artifact was discarded.', self.store.clock(), identifier))
                return False
            if fields.get('status') in ('completed', 'failed', 'canceled'):
                fields['phase'] = fields['status']
            sets = ",".join(f"{k}=?" for k in fields) + ",updated=?"
            db.execute(f"UPDATE renders SET {sets} WHERE id=?", (*fields.values(), self.store.clock(), identifier))
            # Keep the parent operation durable even when no browser is polling.
            # A canceled/failed generation must never be revived by late frames.
            current = db.execute('SELECT status,phase,progress,error FROM renders WHERE id=?', (identifier,)).fetchone()
            db.execute("UPDATE story_generations SET status=?,phase=?,progress=?,error=?,updated=? "
                       "WHERE render_id=? AND cancel=0 AND status NOT IN ('failed','cancelled')",
                       ('completed' if current['status'] == 'completed' else
                        'partial' if current['status'] in ('failed', 'canceled') else 'running',
                        current['phase'], .65 + .35*current['progress'], current['error'], self.store.clock(), identifier))
            return True

    def _clean_working(self, job_dir, discard=False):
        """Remove this job's controlled intermediates, preserving its saved story and paid cache."""
        for name in ('frames', 'browser-profile', 'audio'):
            path = job_dir / name
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
        for name in ('silent.mp4', 'subtitled.mp4', 'chapter-audio.txt', 'chapter-audio.mp3', 'partial.mp4', 'worker.json', 'worker-state.tmp'):
            (job_dir / name).unlink(missing_ok=True)
        if discard:
            for name in ARTIFACTS.values():
                (job_dir / name).unlink(missing_ok=True)

    @staticmethod
    def _file_identity(path):
        digest = hashlib.sha256()
        size = 0
        with path.open('rb') as stream:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                digest.update(chunk)
        return {'sha256': digest.hexdigest(), 'bytes': size}

    def execute(self, identifier, principal):
        job_dir = self.root / identifier
        cancel = self.events.setdefault(identifier, threading.Event())
        with self.lock:
            with self.store.connection() as db:
                row = db.execute("SELECT status,cancel FROM renders WHERE id=?", (identifier,)).fetchone()
            if row["status"] != "queued" or row["cancel"]:
                return
            if not self._update(identifier, status='running', phase='preparing-assets'):
                return
            try:
                self.storage.check()
                resolved = json.loads((job_dir / "resolved.json").read_text())
                public = story.public_copy(resolved)
                # Bound the prepared scene before any paid narration begins.
                if len(dumps(public).encode()) > INPUT_LIMIT:
                    raise StudioError('Prepared scene inputs exceed 32 MB. Reduce visible imagery or chapters.', code='render-limit')
                options = json.loads((job_dir / "options.json").read_text())
                capability = self.narration_capability() if options.get("narration_requested") else {"available": False, "reason": "The author chose a captioned video without AI narration."}
                if capability.get('provider') != 'piper' and self.synthesize is None and self.synthesize_factory is None:
                    capability = {"available": False, "reason": "The existing assistant speech runtime is unavailable. Captions remain complete."}
                plan = narration.preflight(resolved["scenes"], capability, self._spoken_today(principal), revision_key=resolved["sha256"])
                audio = {"status": "captions-only", "reason": plan["reason"], "segments": []}
                synth = self.synthesize
                if plan['available'] and capability.get('provider') == 'piper':
                    from .local_voice import synthesize
                    synth = lambda text: synthesize(text, cancel.is_set)
                elif plan["available"] and self.synthesize_factory:
                    synth = self.synthesize_factory(principal, resolved["sha256"], plan["model"], plan["voice"])
                if plan["available"] and synth:
                    self._update(identifier, phase='narrating')
                    audio = narration.narrate(plan, self.store.root / "narration", synth, lambda n: self.store.artifact(principal, "voice_receipt", {"characters": n, "created": time.time(), "sha256": ""}), cancelled=cancel.is_set,
                                               progress=lambda fraction: self._update(identifier, progress=round(.15*fraction, 4)))
                timing_changes = []
                if capability.get('provider') == 'piper':
                    public, timing_changes = narration.fit_local_timing(public, audio, self.store.root / 'narration', probe=self.audio_probe)
                audio = narration.check_audio(audio, public['scenes'], self.store.root / 'narration', probe=self.audio_probe, cancelled=cancel.is_set)
                audio['skipped_chapters'] = plan['skipped']
                audio['provider'] = capability.get('provider', 'openai')
                audio['model'] = plan['model']
                if cancel.is_set() or audio['status'] == 'canceled':
                    self._update(identifier, status='canceled', error='Canceled before rendering; cached narration was retained.')
                    return
                audio_dir = job_dir / "audio"
                audio_dir.mkdir(exist_ok=True)
                for item in audio["segments"]:
                    (audio_dir / item["file"]).write_bytes((self.store.root / "narration" / item["file"]).read_bytes())
                (job_dir / "input.json").write_text(json.dumps({"resolved": public, "audio": audio["segments"], "narration": audio["status"]}, sort_keys=True))
                (job_dir / ARTIFACTS["captions"]).write_text(story.captions(public))
                (job_dir / ARTIFACTS["transcript"]).write_text(story.transcript(public))
                def progress(value):
                    if isinstance(value, (int, float)) and 0 <= value <= 1:
                        self._update(identifier, progress=round(.15 + .8 * value, 4))
                progress.phase = lambda phase: self._update(identifier, phase=phase) if phase in ('preparing-assets', 'generating-video', 'rendering', 'encoding', 'finalizing') else False
                measured_resources = {}
                progress.resources = measured_resources.update
                progress.storage = self.storage.check
                native = options.get('engine') == 'aiand-native-video'
                if native:
                    from .aiand_video import run
                    video = run(job_dir, progress, cancel, self.store.root/'aiand-video-cache')
                else:
                    video = self.runner(job_dir, progress, cancel)
                if cancel.is_set() or video is None:
                    self._update(identifier, status="canceled", error="Canceled before the video finished; partial output was discarded.")
                    return
                if video.stat().st_size > 512 * 1024 * 1024:
                    video.unlink()
                    raise StudioError("The encoded video exceeds 512 MiB. Use a shorter story.", code="render-limit")
                progress.phase('finalizing')
                evidence = [{"snapshot_id": sid, "snapshot_sha256": s["snapshot_sha256"], "receipt_sha256": s["receipt_sha256"], "release_id": s["release_id"]}
                            for sid, s in sorted(public["snapshots"].items())]
                (job_dir / ARTIFACTS["evidence"]).write_text(json.dumps(evidence, indent=2, sort_keys=True))
                files = {name: self._file_identity(job_dir / name)
                         for name in (ARTIFACTS["video"], ARTIFACTS["transcript"], ARTIFACTS["captions"], ARTIFACTS["evidence"])}
                manifest = {"schema": "fireatlas-studio-render-manifest-v1", "render_id": identifier, "story_sha256": public["sha256"],
                            "profile": public["profile"], "engine": "local-svg-ffmpeg" if os.getenv("FIREATLAS_STUDIO_LOCAL_RENDER", "").lower() in {"1", "true", "yes", "on"} else "remotion", "narration": {k: audio.get(k) for k in ("status", "provider", "model", "attempted_status", "reason", "disclosure", "segments", "cached_segments", "timing", "skipped_chapters")},
                            "files": files, "evidence": evidence,
                            "rasterizer": "chromium" if os.getenv("FIREATLAS_STUDIO_LOCAL_RENDER", "").lower() in {"1", "true", "yes", "on"} else "remotion-chromium",
                            "captions_fallback": audio["status"] != "narrated",
                            "subtitles": {"embedded": self.runner is node_runner, "codec": "mov_text" if self.runner is node_runner else None,
                                          "caption_version": public.get('caption_version', 1),
                                          "source": ARTIFACTS['captions'], "text": "Saved resolved narration, with authored caption/title fallback.",
                                          "activation": "Default subtitle track; display support depends on the video player."},
                            "limitations": public["limitations"]}
                manifest['execution_limits'] = {'node_heap_mb': 768, 'working_bytes': WORKING_LIMIT, 'input_bytes': INPUT_LIMIT,
                                                'output_bytes': 512 * 1024 * 1024, 'deadline_seconds': 900, 'encoder_threads': 2,
                                                'summed_resident_bytes': resources.MEMORY_LIMIT, 'sampled_cpu_seconds': resources.CPU_SECONDS,
                                                'retained_storage_bytes': self.storage.limit, 'retained_file_limit': resources.STORAGE_FILES,
                                                'free_disk_headroom_bytes': resources.FREE_HEADROOM, 'sampling_seconds': .2}
                manifest['resource_observation'] = measured_resources or {'verified': False, 'reason': 'The selected runner did not supply process counters.'}
                manifest['presentation_timing'] = {'saved_story_duration_seconds': resolved['profile']['duration_seconds'],
                                                   'video_duration_seconds': public['profile']['duration_seconds'], 'adjustments': timing_changes}
                manifest['renderer_configuration'] = {'adapter_version': 3, 'frame_design': 'editorial-field-notes-v1',
                                                      'motion_fps': 30, 'remotion_version': '4.0.532' if manifest['engine'] == 'remotion' else None,
                                                      'phase_protocol': 1, 'caption_version': public.get('caption_version', 1)}
                if native:
                    manifest['engine'] = 'aiand-native-video'
                    manifest['provider'] = json.loads((job_dir/'provider-receipts.json').read_text())
                    manifest['limitations'] = [*manifest['limitations'], manifest['provider']['disclosure']]
                    manifest['renderer_configuration']['video_generation_adapter_version'] = 1
                    manifest['execution_limits']['provider_poll_seconds'] = 10
                    manifest['execution_limits']['provider_wait_seconds_per_clip'] = 3600
                (job_dir / ARTIFACTS["manifest"]).write_text(json.dumps(manifest, indent=2, sort_keys=True))
                self._update(identifier, status="completed", progress=1.0, manifest=dumps(manifest))
            except Exception as error:  # noqa: BLE001 - every failure becomes a visible job state
                self._update(identifier, status="canceled" if cancel.is_set() else "failed", error=(str(error) if isinstance(error, StudioError) else "The render failed: " + type(error).__name__)[:400])
            finally:
                with self.store.connection() as db:
                    terminal = db.execute('SELECT status FROM renders WHERE id=?', (identifier,)).fetchone()['status']
                if terminal in ('completed', 'failed', 'canceled'):
                    self._clean_working(job_dir, discard=terminal != 'completed')

    def _spoken_today(self, principal):
        cutoff = time.time() - 86400
        with self.store.connection() as db:
            rows = db.execute("SELECT body FROM science_results WHERE principal_id=? AND kind='voice_receipt' AND created>?", (principal, cutoff)).fetchall()
        return sum(json.loads(r["body"]).get("characters", 0) for r in rows)
