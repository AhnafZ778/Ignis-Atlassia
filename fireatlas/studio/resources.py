"""Local render resource accounting. No archive/notebook files are scanned or deleted.

Linux /proc supplies identities, ancestry, resident pages and CPU ticks for the
controlled worker. Sampled limits can briefly overshoot; they are not a kernel
allocation quota. Shared resident pages are conservatively counted per process.
"""
from __future__ import annotations

import os
import json
import shutil
import signal
import time
from pathlib import Path

from .errors import StudioError, Unavailable

MEMORY_LIMIT = 2 * 1024 ** 3
CPU_SECONDS = 6000
STORAGE_LIMIT = 8 * 1024 ** 3
STORAGE_FILES = 20_000
FREE_HEADROOM = 128 * 1024 ** 2


def process_info(pid, proc=Path('/proc')):
    """Return a process identity and counters; disappearance is normal during sampling."""
    try:
        path = proc / str(pid) / 'stat'
        if path.stat().st_uid != os.getuid():
            return None
        fields = path.read_text().rpartition(')')[2].split()
        return {'pid': int(pid), 'state': fields[0], 'ppid': int(fields[1]), 'group': int(fields[2]),
                'session': int(fields[3]), 'start': int(fields[19]), 'rss': int(fields[21]),
                'ticks': int(fields[11]) + int(fields[12])}
    except (FileNotFoundError, ProcessLookupError):
        return None
    except (OSError, ValueError, IndexError) as error:
        raise Unavailable('The renderer process monitor cannot read local resource counters. '
                          'Story editing and reader export remain available.', code='render-monitor-unavailable') from error


def monitor_available():
    try:
        return process_info(os.getpid()) is not None and hasattr(os, 'killpg')
    except (StudioError, AttributeError):
        return False


class ProcessBudget:
    def __init__(self, pid):
        self.pid = pid
        root = process_info(pid)
        if not root or root['group'] != pid or root['session'] != pid:
            raise Unavailable('The controlled renderer session could not be monitored.', code='render-monitor-unavailable')
        self.known = {pid: root['start']}
        self.ticks = {(pid, root['start']): root['ticks']}
        self.page_size = os.sysconf('SC_PAGE_SIZE')
        self.clock_ticks = os.sysconf('SC_CLK_TCK')
        self.peak_rss = max(0, root['rss']) * self.page_size

    def save(self, directory):
        if len(self.known) > 1024:
            raise StudioError('The renderer exceeded its tracked-process limit.', code='render-process-limit')
        temporary = Path(directory) / 'worker-state.tmp'
        temporary.write_text(json.dumps({'schema': 'fireatlas-render-worker-v1', 'pid': self.pid,
                                         'known': self.known}), encoding='utf-8')
        temporary.replace(Path(directory) / 'worker.json')

    def sample(self):
        catalog = {}
        for path in Path('/proc').iterdir():
            if path.name.isdigit():
                info = process_info(int(path.name))
                if info:
                    catalog[info['pid']] = info
        session_owned = any(info['session'] == self.pid and self.known.get(pid) == info['start']
                            for pid, info in catalog.items())
        members = {pid: info for pid, info in catalog.items()
                   if (session_owned and info['session'] == self.pid) or self.known.get(pid) == info['start']}
        # Also track children that create their own sessions. Keep their start
        # identities after reparenting; never signal a PID reused for other work.
        while True:
            added = {pid: info for pid, info in catalog.items() if pid not in members and info['ppid'] in members}
            if not added:
                break
            members.update(added)
        for pid, info in members.items():
            self.known[pid] = info['start']
            key = (pid, info['start'])
            self.ticks[key] = max(self.ticks.get(key, 0), info['ticks'])
        self.peak_rss = max(self.peak_rss, sum(max(0, info['rss']) for info in members.values()) * self.page_size)
        return self.report()

    def report(self):
        return {'peak_summed_resident_bytes': self.peak_rss,
                'sampled_cpu_seconds': round(sum(self.ticks.values()) / self.clock_ticks, 3),
                'tracked_process_identities': len(self.ticks), 'sampling_seconds': .2,
                'basis': 'Controlled Linux session and observed descendants; shared RSS counted per process. '
                         'CPU retains sampled ticks of exited processes; very short-lived work can fall between samples.'}

    def _live(self):
        live = {}
        for pid, start in list(self.known.items()):
            info = process_info(pid)
            if info and info['start'] == start and info['state'] != 'Z':
                live[pid] = info
        return live

    def _signal(self, sig):
        live = self._live()
        # A matching start identity in this group proves the group still belongs
        # to this job. This also works if the Node parent has already exited.
        if any(info['group'] == self.pid for info in live.values()):
            try:
                os.killpg(self.pid, sig)
            except ProcessLookupError:
                pass
        for pid, info in live.items():
            if info['group'] != self.pid:
                try:
                    os.kill(pid, sig)
                except ProcessLookupError:
                    pass

    def terminate(self):
        """Stop only verified job processes, including observed detached descendants."""
        self._signal(signal.SIGTERM)
        deadline = time.monotonic() + 2
        while self._live() and time.monotonic() < deadline:
            time.sleep(.05)
        self._signal(signal.SIGKILL)


def recover_worker(directory):
    """Stop a saved worker only after validating its PID start identities and command.

    An exact job-directory command match also covers a crash between spawn and
    the first identity write. This never scans or signals unrelated job paths.
    """
    directory = Path(directory).resolve()
    saved = directory / 'worker.json'
    known, root_pid = {}, None
    if saved.is_file():
        if saved.stat().st_size > 64_000:
            raise Unavailable('Interrupted renderer identity is oversized; no process was signaled.', code='render-recovery-unavailable')
        try:
            record = json.loads(saved.read_text())
            if record['schema'] != 'fireatlas-render-worker-v1' or not isinstance(record['known'], dict) or len(record['known']) > 1024:
                raise ValueError('worker schema')
            root_pid = int(record['pid'])
            known = {int(pid): int(start) for pid, start in record['known'].items()}
            if root_pid not in known or min(known) <= 0 or min(known.values()) < 0:
                raise ValueError('worker identity')
        except (ValueError, TypeError, KeyError) as error:
            raise Unavailable('Interrupted renderer identity is invalid; no process was signaled.', code='render-recovery-unavailable') from error

    def matches(pid):
        try:
            parts = (Path('/proc') / str(pid) / 'cmdline').read_bytes().split(b'\0')
        except (FileNotFoundError, ProcessLookupError):
            return False
        return str(directory).encode() in parts and any(Path(os.fsdecode(part)).name in ('render-local.mjs', 'render.mjs') for part in parts if part)

    if root_pid:
        info = process_info(root_pid)
        if info and info['start'] == known[root_pid] and info['state'] != 'Z' and not matches(root_pid):
            raise Unavailable('Interrupted renderer identity does not match this job; no process was signaled.', code='render-recovery-unavailable')
        budget = object.__new__(ProcessBudget)
        budget.pid, budget.known = root_pid, known
        budget.ticks, budget.peak_rss = {}, 0
        budget.page_size, budget.clock_ticks = os.sysconf('SC_PAGE_SIZE'), os.sysconf('SC_CLK_TCK')
        budget.sample()
        budget.terminate()
    # Account for a spawn whose initial identity write was interrupted.
    for path in Path('/proc').iterdir():
        if path.name.isdigit():
            pid = int(path.name)
            info = process_info(pid)
            if info and info['group'] == pid and info['session'] == pid and matches(pid):
                budget = ProcessBudget(pid)
                budget.sample()
                budget.terminate()


def file_usage(roots, max_files=STORAGE_FILES):
    size = count = 0
    for root in roots:
        if root.is_symlink():
            raise Unavailable('Render storage must use controlled local directories.', code='render-storage-unavailable')
        if not root.exists():
            continue
        for directory, folders, files in os.walk(root, followlinks=False, onerror=lambda error: _storage_error(error)):
            folders[:] = [name for name in folders if not (Path(directory) / name).is_symlink()]
            for name in files:
                path = Path(directory) / name
                try:
                    if path.is_symlink():
                        continue
                    size += path.stat().st_size
                    count += 1
                except FileNotFoundError:
                    continue  # An encoder can atomically rename its output.
                if count > max_files:
                    raise Unavailable('Retained render storage has reached its file-count limit. Existing downloads '
                                      'remain available; the operator can archive exports.', code='render-storage-full')
    return {'bytes': size, 'files': count}


def _storage_error(error):
    raise Unavailable('Render storage could not be inspected. Existing stories remain available.',
                      code='render-storage-unavailable') from error


class StorageBudget:
    def __init__(self, root, limit=STORAGE_LIMIT):
        self.root, self.limit = Path(root), limit

    def check(self, additional_bytes=0, additional_files=0):
        try:
            used = file_usage([self.root / 'renders', self.root / 'narration'])
            free = shutil.disk_usage(self.root).free
        except OSError as error:
            _storage_error(error)
        if used['bytes'] + additional_bytes > self.limit or used['files'] + additional_files > STORAGE_FILES:
            raise Unavailable('Retained exports and narration have reached the render storage capacity. '
                              'Existing downloads and saved stories remain available; the operator can archive exports.',
                              code='render-storage-full')
        if free < additional_bytes + FREE_HEADROOM:
            raise Unavailable('The render volume needs more free disk space before another export. '
                              'Existing downloads and saved stories remain available.', code='render-storage-low')
        return {**used, 'free_bytes': free, 'capacity_bytes': self.limit, 'admission_bytes': additional_bytes}
