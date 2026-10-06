"""Native AI& video jobs: credential-specific access, durable checkpoints, no paid retry."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
import time
from pathlib import Path

from ..assistant.aiand import BASE_URL, configured_keys
from .errors import StudioError, Unavailable

MODEL = 'minimaxai/minimax-h3'
_lock = threading.Lock()
_access = None
_stamp = None
_checked = 0
PROMPT = """Create an elegant scientific infographic film, using this editorial reference frame.
Warm ivory, restrained navy and cobalt, soft amber thermal accents, generous negative space.
Smooth continuous motion, subtle layered depth and refined cinematic transitions; no flashes,
no shaky camera, no stock footage, no invented flames or physical fire spread.
Preserve the reference's scientific panel as a stationary region. Animate the surrounding
editorial atmosphere and abstract shapes, not numerical data, chart marks or map boundaries.
Do not invent labels, readings, perimeters, ignition events, measurement scales or statistics.
Keep clear space for overlaid authentic evidence and narration. Sound: quiet atmospheric
instrumental texture, no dialogue, vocals or spoken claims. The final editor overlays exact
checked charts and typography. This generated motion is illustrative, not a measurement.
Chapter direction: {title}. Context: {caption}
"""


def selected_engine():
    return os.getenv('FIREATLAS_STUDIO_VIDEO_PROVIDER', 'local').lower()


def _identity(key):
    return hashlib.sha256(key.encode()).hexdigest()


def verify_access():
    """A chat-authenticated key may not have personal video-terms acceptance."""
    global _access, _stamp, _checked
    import httpx
    keys = configured_keys()
    model = os.getenv('FIREATLAS_AIAND_VIDEO_MODEL', MODEL)
    stamp = hashlib.sha256(('\n'.join(keys)+'\n'+model).encode()).digest()
    with _lock:
        if _access and _stamp == stamp and time.monotonic()-_checked < 300:
            return _access
        if not keys:
            raise Unavailable('AI& video needs a configured server-side AIAND_API_KEY.', code='aiand-video-unconfigured')
        for key in keys:
            try:
                with httpx.Client(headers={'Authorization': 'Bearer '+key, 'User-Agent': 'FireAtlas/1.0'}, timeout=20) as client:
                    acceptance = client.get(BASE_URL+'/videos/acceptance')
                    if acceptance.status_code in (401, 403):
                        continue
                    acceptance.raise_for_status()
                    if acceptance.json().get('accepted') is not True:
                        continue
                    catalog = client.get(BASE_URL+'/videos/models')
                    catalog.raise_for_status()
                    entry = next((m for m in catalog.json()['data'] if m['id'] == model), None)
                    if not entry:
                        continue
                    rate = next((p for p in entry['pricing'] if p['resolution'] == '768p' and p['currency'].lower() == 'usd'), None)
                    price = float(rate['per_second']) if rate else float('nan')
                    if not math.isfinite(price) or price <= 0:
                        raise ValueError()
                    _access = {'key': key, 'credential_sha256': _identity(key), 'model': model,
                               'per_second_usd': price, 'resolution': '768p', 'terms_version': acceptance.json().get('version')}
                    _stamp, _checked = stamp, time.monotonic()
                    return _access
            except (httpx.HTTPError, KeyError, ValueError, TypeError):
                raise Unavailable('AI& video access or pricing could not be verified. No video was submitted.', code='aiand-video-access') from None
        raise Unavailable('AI& requires the key owner to accept Video Service Terms in the AI& console playground. None of the configured keys has access to this selected video model.', code='agreement_required')


def _save(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, sort_keys=True))
    temporary.replace(path)


def _hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024*1024):
            digest.update(chunk)
    return digest.hexdigest()


class VideoClient:
    def __init__(self, access=None, client=None):
        import httpx
        self.access = access or verify_access()
        self.client = client or httpx.Client(headers={'Authorization': 'Bearer '+self.access['key'], 'User-Agent': 'FireAtlas/1.0'}, timeout=90)

    def close(self):
        self.client.close()

    def _error(self, response):
        if response.is_success:
            return
        try:
            code = response.json().get('error', {}).get('code', 'provider-error')
        except (ValueError, AttributeError):
            code = 'provider-error'
        messages = {'agreement_required': 'Accept Video Service Terms in the AI& console for this key owner.',
                    'insufficient_credits': 'AI& has insufficient credits for the quoted video cost.',
                    'concurrency_limit_exceeded': 'AI& is already processing the allowed number of video jobs.',
                    'provider_unavailable': 'The AI& video engine is temporarily unavailable.',
                    'model_not_found': 'The configured AI& video model is unavailable to this account.'}
        raise StudioError(messages.get(code, 'AI& rejected this video request. No automatic paid retry was made.'), code=code if code in messages else 'aiand-video-error')

    def clip(self, cache, frame, prompt, seconds, cancelled, status):
        import httpx
        if type(seconds) is not int or not 4 <= seconds <= 15:
            raise StudioError('AI& clips require 4–15 seconds.', code='aiand-video-duration')
        identity = hashlib.sha256(json.dumps({'model': self.access['model'], 'prompt': prompt, 'seconds': seconds,
                                  'frame_sha256': _hash(frame),
                                  'credential_sha256': self.access['credential_sha256']}, sort_keys=True).encode()).hexdigest()
        folder = Path(cache)/identity
        folder.mkdir(parents=True, exist_ok=True)
        checkpoint, output = folder/'job.json', folder/'clip.mp4'
        saved = json.loads(checkpoint.read_text()) if checkpoint.exists() else {'model': self.access['model'], 'seconds': seconds,
                'quote_usd': seconds*self.access['per_second_usd'], 'credential_sha256': self.access['credential_sha256']}
        if saved.get('state') == 'downloaded' and output.exists() and _hash(output) == saved.get('output_sha256'):
            status('completed', saved)
            return output, {**saved, 'cache_hit': True, 'submitted_in_this_run': False}
        prompt = prompt+'\nReference identity: '+identity+'. Do not draw this metadata.'
        if saved.get('state') in ('failed', 'canceled'):
            saved['previous_video_ids'] = [*saved.get('previous_video_ids', []), saved.pop('video_id')]
            saved['state'] = 'retry-requested'
            _save(checkpoint, saved)
        if cancelled():
            raise StudioError('Video preparation cancelled; saved provider jobs can be reconnected.', code='video-canceled')
        if not saved.get('file_id'):
            with frame.open('rb') as stream:
                response = self.client.post(BASE_URL+'/files', data={'purpose': 'vision'}, files={'file': ('evidence-frame.png', stream, 'image/png')})
            self._error(response)
            file_id = response.json().get('id')
            if not isinstance(file_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', file_id):
                raise StudioError('AI& returned an invalid uploaded frame identity.')
            saved['file_id'] = file_id
            _save(checkpoint, saved)
        submitted_here = False
        if not saved.get('video_id'):
            if saved.get('state') == 'submitting':
                response = self.client.get(BASE_URL+'/videos', params={'limit': 100})
                self._error(response)
                matches = [v for v in response.json().get('data', []) if v.get('prompt') == prompt and v.get('model') == self.access['model'] and v.get('seconds') == seconds]
                if len(matches) == 1:
                    saved.update(video_id=matches[0]['id'], state=matches[0]['status'], cost=matches[0].get('cost'), currency=matches[0].get('currency'))
                    _save(checkpoint, saved)
                else:
                    raise StudioError('The earlier video submission has an uncertain outcome. Inspect AI& jobs before submitting again; no duplicate request was sent.', code='aiand-video-uncertain')
        if not saved.get('video_id'):
            if cancelled():
                raise StudioError('Video preparation cancelled before submission.', code='video-canceled')
            saved['state'] = 'submitting'
            _save(checkpoint, saved)
            try:
                response = self.client.post(BASE_URL+'/videos', json={'model': self.access['model'], 'prompt': prompt,
                      'seconds': seconds, 'aspect_ratio': '16:9', 'image_reference': [{'file_id': saved['file_id'], 'role': 'first_frame'}]})
                if not response.is_success:
                    saved['state'] = 'rejected'
                    _save(checkpoint, saved)
                    self._error(response)
                payload = response.json()
                video_id = payload.get('id')
                if not isinstance(video_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', video_id):
                    raise ValueError()
                saved.update(video_id=video_id, state=payload['status'], cost=payload.get('cost'), currency=payload.get('currency'))
                _save(checkpoint, saved)
                submitted_here = True
            except (httpx.HTTPError, ValueError, KeyError):
                raise StudioError('AI& video submission has an uncertain outcome. The checkpoint is retained; no paid retry was made.', code='aiand-video-uncertain') from None
        deadline = time.monotonic()+3600
        while saved.get('state') != 'completed':
            status(saved['state'], saved)
            if cancelled():
                raise StudioError('Local delivery cancelled. AI& cannot abort an admitted job; its ID is retained for later recovery and it may still be billed.', code='video-canceled')
            if saved['state'] in ('failed', 'canceled'):
                raise StudioError('AI& video generation '+saved['state']+'. The provider job is retained; no automatic retry was made.', code='aiand-video-failed')
            if time.monotonic() > deadline:
                raise StudioError('AI& is still processing the video. Its job ID is saved; refresh the saved film to reconnect without submitting again.', code='aiand-video-pending')
            event = getattr(cancelled, '__self__', None)
            if isinstance(event, threading.Event):
                if event.wait(10):
                    continue
            else:
                time.sleep(10)
            response = self.client.get(BASE_URL+'/videos/'+saved['video_id'])
            self._error(response)
            saved['state'] = response.json().get('status', 'in_progress')
            _save(checkpoint, saved)
        status('downloading', saved)
        partial = output.with_suffix('.part')
        try:
            size = 0
            with self.client.stream('GET', BASE_URL+'/videos/'+saved['video_id']+'/content') as response:
                self._error(response)
                with partial.open('wb') as target:
                    for chunk in response.iter_bytes(1024*1024):
                        size += len(chunk)
                        if cancelled() or size > 512*1024*1024:
                            raise StudioError('Video download cancelled or exceeds the existing 512 MiB output limit.')
                        target.write(chunk)
            with partial.open('rb') as stream:
                header = stream.read(32)
            if size < 32 or b'ftyp' not in header:
                raise StudioError('AI& did not return a valid MP4 container.')
            partial.replace(output)
        finally:
            partial.unlink(missing_ok=True)
        saved.update(state='downloaded', output_bytes=size, output_sha256=_hash(output))
        _save(checkpoint, saved)
        status('completed', saved)
        return output, {**saved, 'cache_hit': False, 'submitted_in_this_run': submitted_here}


def run(job_dir, progress, cancel, cache):
    """Native image-to-video per chapter, then exact-evidence composition and audio mux."""
    from .render import node_runner
    data = json.loads((job_dir/'input.json').read_text())
    scenes = data['resolved']['scenes']
    progress.phase('preparing-assets')
    node_runner(job_dir, lambda _: None, cancel, script='prepare-aiand.mjs')
    if cancel.is_set():
        return None
    client = VideoClient()
    receipts = []
    clips = []
    try:
        for index, scene in enumerate(scenes):
            seconds = max(4, min(15, math.ceil(scene['duration_seconds'])))
            def status(phase, record):
                public = {k:v for k,v in record.items() if k != 'credential_sha256'}
                _save(job_dir/'provider-progress.json', {'provider': 'aiand', 'model': client.access['model'], 'status': phase,
                     'chapter': index+1, 'chapters': len(scenes), 'seconds': seconds, 'quote_usd': seconds*client.access['per_second_usd'],
                     'video_id': public.get('video_id')})
                progress.phase('generating-video')
            clip, receipt = client.clip(cache, job_dir/'frames'/f'reference-{index}.png',
                                       PROMPT.format(title=scene['title'], caption=scene['caption']), seconds, cancel.is_set, status)
            clips.append({'chapter_id': scene['chapter_id'], 'path': str(clip.resolve()), 'sha256': receipt['output_sha256']})
            receipts.append({k:v for k,v in receipt.items() if k != 'credential_sha256'})
            progress(.8*(index+1)/len(scenes))
    finally:
        client.close()
    _save(job_dir/'native-clips.json', {'clips': clips})
    _save(job_dir/'provider-receipts.json', {'provider': 'aiand', 'model': client.access['model'], 'clips': receipts,
          'quoted_cost_usd': sum(r['quote_usd'] for r in receipts), 'native_resolution': '768p',
          'new_submission_cost_usd': sum(r['quote_usd'] for r in receipts if r.get('submitted_in_this_run')),
          'reused_clips': sum(bool(r.get('cache_hit')) for r in receipts),
          'disclosure': 'AI& generates illustrative motion and sound; exact frozen scientific graphics are composited above it. Output is upscaled to 1080p.'})
    def encode_progress(value):
        progress(.8+.2*value)
    encode_progress.phase = progress.phase
    encode_progress.resources = getattr(progress, 'resources', lambda _: None)
    encode_progress.storage = getattr(progress, 'storage', lambda: None)
    return node_runner(job_dir, encode_progress, cancel, script='compose-aiand.mjs')
