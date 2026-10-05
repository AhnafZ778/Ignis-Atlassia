"""Bounded narration: preflight, split, cache, never auto-retry a paid failure, fall back to captions."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import time
from pathlib import Path

SEGMENT_LIMIT = 800
DAILY_LIMIT = 4000
AUDIO_FILE_LIMIT = 8 * 1024 * 1024
AUDIO_TOTAL_LIMIT = 64 * 1024 * 1024
DISCLOSURE = "AI-generated voice of the saved story. Checked fields cite frozen evidence; explanatory prose remains authored interpretation. Not an eyewitness account."


def audio_duration(path):
    """Probe a controlled local file only; no network resources or shell interpolation."""
    result = subprocess.run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe', '-f', 'mp3', '-select_streams', 'a:0',
                             '-show_entries', 'stream=codec_type:format=duration', '-of', 'json', str(path)],
                            capture_output=True, text=True, timeout=10, check=True)
    if len(result.stdout) > 16_384:
        raise ValueError('oversized audio probe')
    data = json.loads(result.stdout)
    if not data.get('streams') or data['streams'][0].get('codec_type') != 'audio':
        raise ValueError('not an audio file')
    duration = float(data['format']['duration'])
    if not math.isfinite(duration) or duration <= 0 or duration > 300:
        raise ValueError('invalid audio duration')
    return duration


def check_audio(audio, scenes, cache_dir, *, probe=audio_duration, cancelled=lambda: False):
    """Check voiced chapters before either renderer can clip them. Keep paid cache entries intact."""
    if not audio.get('segments'):
        return {**audio, 'timing': {'checked': False, 'chapters': [], 'reason': 'No audio was selected for rendering.'}}
    if cancelled() or audio.get('status') == 'canceled':
        return {**audio, 'status': 'canceled', 'segments': [], 'timing': {'checked': False, 'chapters': [], 'reason': 'Canceled before audio preparation.'}}
    if audio.get('status') != 'narrated':
        return {**audio, 'attempted_status': audio.get('status'), 'status': 'captions-only', 'cached_segments': audio['segments'], 'segments': [],
                'reason': 'Speech generation was incomplete. The complete saved narration remains in captions and transcript; no audio was truncated or retried.',
                'timing': {'checked': False, 'chapters': [], 'reason': 'Incomplete speech was excluded.'}}
    root = Path(cache_dir).resolve()
    chapters = {scene['chapter_id']: scene for scene in scenes}
    durations, indexes, measured, accumulated = {}, set(), [], 0
    try:
        for item in audio['segments']:
            if cancelled():
                return {**audio, 'status': 'canceled', 'segments': [], 'timing': {'checked': False, 'chapters': [], 'reason': 'Canceled during audio preparation.'}}
            name, chapter, index = item['file'], item['chapter_id'], item['index']
            if not isinstance(name, str) or not re.fullmatch(r'[a-f0-9]{64}\.mp3', name) or chapter not in chapters:
                raise ValueError('invalid audio identity')
            if isinstance(index, bool) or not isinstance(index, int) or index < 0 or (chapter, index) in indexes:
                raise ValueError('invalid audio segment order')
            indexes.add((chapter, index))
            path = root / name
            if path.is_symlink() or path.resolve().parent != root or not path.is_file() or not 0 < path.stat().st_size <= AUDIO_FILE_LIMIT:
                raise ValueError('missing or oversized audio')
            with path.open('rb') as stream:
                content = stream.read(AUDIO_FILE_LIMIT + 1)
            if len(content) > AUDIO_FILE_LIMIT:
                raise ValueError('oversized audio')
            accumulated += len(content)
            if accumulated > AUDIO_TOTAL_LIMIT:
                raise ValueError('audio exceeds the 64 MiB preparation limit')
            if hashlib.sha256(content).hexdigest() != item['sha256']:
                raise ValueError('cached audio no longer matches its recorded hash')
            duration = probe(path)
            if not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 0 < duration <= 300:
                raise ValueError('invalid audio duration')
            durations[chapter] = durations.get(chapter, 0) + duration
            measured.append({**item, 'duration_seconds': duration})
        timings = []
        for chapter, duration in durations.items():
            sequence = sorted(i for c, i in indexes if c == chapter)
            if sequence != list(range(len(sequence))):
                raise ValueError('incomplete audio segment sequence')
            available = chapters[chapter]['duration_seconds']
            timings.append({'chapter_id': chapter, 'audio_seconds': duration, 'chapter_seconds': available,
                            'chapter_start_seconds': chapters[chapter]['start_seconds']})
            if duration > available:
                return {**audio, 'attempted_status': audio['status'], 'status': 'captions-only', 'cached_segments': measured, 'segments': [],
                        'reason': 'Generated speech exceeds a saved chapter duration. A complete captioned silent video was prepared. Increase the saved chapter duration before a new narrated export. Cached audio for this revision was retained.',
                        'timing': {'checked': False, 'chapters': timings, 'reason': 'Speech would be cut off at the saved chapter boundary.'}}
        return {**audio, 'segments': measured, 'timing': {'checked': True, 'chapters': timings,
                'scope': 'Complete local audio fits each voiced chapter; subtitle cues use saved chapter timing, not provider word timestamps.'}}
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        return {**audio, 'attempted_status': audio.get('status'), 'status': 'captions-only', 'cached_segments': audio['segments'], 'segments': [],
                'reason': 'Generated audio could not be verified as intact, bounded speech fitting its saved chapters. Complete captions and transcript were used; no paid request was retried.',
                'timing': {'checked': False, 'chapters': [], 'reason': 'Audio integrity or duration verification failed.'}}


def split_segments(text, limit=SEGMENT_LIMIT):
    text = " ".join((text or "").split())
    sentences = re.split(r"(?<=[.!?])\s+", text)
    segments, current = [], ""
    for sentence in sentences:
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            if current:
                segments.append(current)
                current = ""
            segments.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if current and len(current) + 1 + len(sentence) > limit:
            segments.append(current)
            current = sentence
        else:
            current = (current + " " + sentence).strip()
    if current:
        segments.append(current)
    return [s for s in segments if s]


def cache_key(text, model, voice, revision_key=""):
    return hashlib.sha256(f"{model}|{voice}|{revision_key}|{text}".encode()).hexdigest()


def preflight(scenes, capability, used_today=0, model=None, voice="coral", revision_key=""):
    """Decide what would be sent before any provider call. Unchecked narration is never voiced."""
    model = model or os.getenv("FIREATLAS_TTS_MODEL", "gpt-4o-mini-tts")
    segments, skipped = [], []
    for scene in scenes:
        if not scene["narration_text"]:
            continue
        if not scene["narration_checked"]:
            skipped.append({"chapter_id": scene["chapter_id"], "reason": "Narration cites numbers not found in the chapter's evidence."})
            continue
        for index, text in enumerate(split_segments(scene["narration_text"])):
            segments.append({"chapter_id": scene["chapter_id"], "index": index, "text": text, "key": cache_key(text, model, voice, revision_key)})
    characters = sum(len(s["text"]) for s in segments)
    report = {"segments": segments, "skipped": skipped, "characters": characters, "model": model, "voice": voice, "available": bool(capability.get("available")),
              "reason": capability.get("reason")}
    if not segments:
        report.update(available=False, reason="No checked narration text to voice.")
    elif report["available"] and used_today + characters > DAILY_LIMIT:
        report.update(available=False, reason=f"Narration would exceed the {DAILY_LIMIT}-character daily allowance; captions and transcript are used instead.")
    elif report["available"]:
        rate, budget = capability.get("per_request_usd", 0), capability.get("story_budget_usd", 0)
        report["estimated_usd"] = round(rate * len(segments), 6)
        if report["estimated_usd"] > budget:
            report.update(available=False, reason="Estimated narration cost exceeds the configured story budget; captions and transcript are used instead.")
    return report


def narrate(report, cache_dir, synthesize, record=lambda characters: None, cancelled=lambda: False):
    """Synthesize uncached segments. The first provider failure stops the run with no retry; cached audio is kept."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    done, status, reason = [], "narrated", None
    if not report["available"]:
        return {"status": "captions-only", "reason": report["reason"], "segments": [], "disclosure": DISCLOSURE}
    for segment in report["segments"]:
        if cancelled():
            return {"status": "canceled", "reason": "Narration was canceled before the next request.", "segments": done, "disclosure": DISCLOSURE}
        target = cache_dir / (segment["key"] + ".mp3")
        cached = target.is_file()
        if not cached:
            try:
                data = synthesize(segment["text"])
                if not data or not isinstance(data, bytes) or len(data) > AUDIO_FILE_LIMIT:
                    raise ValueError("empty audio")
            except Exception as error:  # a paid request may have been billed: never retry automatically
                status, reason = ("partial" if done else "captions-only"), "The narration provider failed (" + type(error).__name__ + "). It was not retried; captions and transcript are complete."
                break
            target.write_bytes(data)
            record(len(segment["text"]))
        done.append({"chapter_id": segment["chapter_id"], "index": segment["index"], "file": target.name, "cached": cached,
                     "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    return {"status": status, "reason": reason, "segments": done, "disclosure": DISCLOSURE, "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
