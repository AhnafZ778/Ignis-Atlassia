"""Optional offline neural speech. No provider key or remote request is used."""
from __future__ import annotations

import functools
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_MODEL = Path(__file__).resolve().parents[2] / 'data/voices/en_US-ljspeech-high.onnx'


def model_path():
    return Path(os.getenv('FIREATLAS_STUDIO_VOICE_MODEL', str(DEFAULT_MODEL))).expanduser().resolve()


@functools.lru_cache(maxsize=4)
def fingerprint(path, size, modified):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hashlib.sha256(stream.read()).hexdigest()


def capability():
    path = model_path()
    if importlib.util.find_spec('piper') is None or not path.is_file() or not Path(str(path) + '.json').is_file():
        return {'available': False, 'reason': 'Install requirements/studio-voice.txt and download the configured Piper voice to enable offline narration.'}
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        return {'available': False, 'reason': 'Offline narration requires ffmpeg and ffprobe.'}
    stat = path.stat()
    identity = fingerprint(str(path), stat.st_size, stat.st_mtime_ns)
    return {'available': True, 'provider': 'piper', 'model': 'piper:' + path.stem + ':' + identity[:16],
            'voice': path.stem, 'model_sha256': identity, 'per_request_usd': 0, 'story_budget_usd': 0,
            'disclosure': 'AI-generated neural narration, synthesized locally from the saved checked story. No speech API key or provider upload.'}


def synthesize(text, cancelled=lambda: False):
    if not isinstance(text, str) or not 1 <= len(text) <= 800:
        raise ValueError('Use a checked narration segment of 1–800 characters.')
    if cancelled():
        raise ValueError('Narration cancelled.')
    process = subprocess.Popen([sys.executable, '-m', 'fireatlas.studio.local_voice', '--worker'],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    submitted = json.dumps({'model': str(model_path()), 'text': text}).encode()
    started = time.monotonic()
    try:
        while True:
            try:
                audio, _ = process.communicate(input=submitted, timeout=.2)
                break
            except subprocess.TimeoutExpired:
                submitted = None
                if cancelled() or time.monotonic() - started > 90:
                    raise ValueError('Offline narration cancelled or timed out.')
        if process.returncode or not audio or len(audio) > 8 * 1024 * 1024:
            raise ValueError('Offline narration could not produce verified audio.')
        return audio
    finally:
        if process.poll() is None:
            import signal
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()


def worker():
    """Isolate ONNX allocation and bound CPU threads; output MP3 bytes only."""
    import io
    import re
    import wave
    import datetime
    import onnxruntime
    from piper import PiperVoice, SynthesisConfig
    from piper.config import PiperConfig
    from piper.voice import ESPEAK_DATA_DIR
    request = json.loads(sys.stdin.buffer.read(16_384))
    path = Path(request['model'])
    config = json.loads(Path(str(path) + '.json').read_text())
    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    voice = PiperVoice(config=PiperConfig.from_dict(config),
                       session=onnxruntime.InferenceSession(str(path), sess_options=options, providers=['CPUExecutionProvider']),
                       espeak_data_dir=ESPEAK_DATA_DIR)
    text = request['text']
    for label, spoken in [('VIIRS', 'veers'), ('S-NPP', 'Suomi N P P'), ('UTC', 'U T C'), ('MODIS', 'moh dis')]:
        text = re.sub(r'\b' + re.escape(label) + r'\b', spoken, text)
    text = re.sub(r'\b\d{4}-\d{2}-\d{2}\b', lambda m: datetime.date.fromisoformat(m[0]).strftime('%B %d, %Y'), text)
    output = io.BytesIO()
    with wave.open(output, 'wb') as handle:
        voice.synthesize_wav(text, handle, syn_config=SynthesisConfig(length_scale=1.02, noise_scale=.45, noise_w_scale=.6))
    encoded = subprocess.run(['ffmpeg', '-v', 'error', '-i', 'pipe:0', '-af', 'loudnorm=I=-16:TP=-1.5:LRA=9',
                              '-ar', '48000', '-ac', '1', '-c:a', 'libmp3lame', '-b:a', '128k', '-f', 'mp3', 'pipe:1'],
                             input=output.getvalue(), capture_output=True, timeout=30, check=True)
    sys.stdout.buffer.write(encoded.stdout)


if __name__ == '__main__':
    worker()
