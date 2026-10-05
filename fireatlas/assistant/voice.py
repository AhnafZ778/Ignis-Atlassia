"""Bounded speech adapters. Narration only consumes a saved, checked answer."""
from __future__ import annotations
import base64
import math
import io
import wave
import os
import tempfile
import time
from pathlib import Path


def speech(service,owner,operation,body):
    from .agent import provider_config
    if provider_config().get('free_only'):
        raise ValueError('Paid speech is disabled in free-only mode. Use typed conversation.')
    from openai import OpenAI
    if not os.getenv("OPENAI_API_KEY"):raise ValueError("Speech provider is not configured.")
    client=OpenAI(timeout=30,max_retries=0)
    prior=service.store.artifacts(owner,"voice_receipt")
    today=time.time()-86400
    if operation=="transcribe":
        rate=float(os.getenv("FIREATLAS_STT_MAX_REQUEST_USD","0"))
        if not math.isfinite(rate) or rate<=0:raise ValueError("A verified maximum transcription request cost is required.")
        audio=base64.b64decode(body.get("data",""),validate=True)
        if not 1<=len(audio)<=1_500_000:raise ValueError("Audio must be smaller than 1.5 MB.")
        # Independently inspect media duration; a client-supplied duration is not trusted.
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"recording.wav";path.write_bytes(audio)
            try:
                with wave.open(io.BytesIO(audio),'rb') as recording:
                    if recording.getnchannels()!=1 or recording.getsampwidth()!=2 or recording.getframerate()>48000:raise ValueError('Use mono PCM16 WAV at up to 48 kHz.')
                    duration=recording.getnframes()/recording.getframerate()
                    if len(recording.readframes(recording.getnframes()))!=recording.getnframes()*2:raise ValueError('Audio data is incomplete.')
            except (wave.Error,EOFError,ZeroDivisionError):
                raise ValueError('Use a valid mono WAV recording or typed chat.') from None
            if not 0<duration<=21:raise ValueError("Speak for at most 20 seconds per turn.")
            recorded=sum(v["body"].get("duration",0) for v in prior if v["body"].get("created",0)>today and v["body"].get("operation")=="transcribe")
            if recorded+duration>180:raise ValueError("This workspace's recorded-speech allowance has been reached.")
            reservation=service.store.reserve(owner,math.ceil(rate*1e6))
            with path.open("rb") as handle:
                transcript=client.audio.transcriptions.create(model=os.getenv("FIREATLAS_STT_MODEL","gpt-transcribe"),file=handle)
            service.store.reconcile(owner,reservation,math.ceil(rate*1e6))
            service.store.artifact(owner,"voice_receipt",{"operation":operation,"duration":duration,"created":time.time()})
            return {"transcript":transcript.text,"duration":duration,"note":"Edit ambiguous dates or coordinates before sending. Raw audio was not retained."}
    if operation=="synthesize":
        rate=float(os.getenv("FIREATLAS_TTS_MAX_REQUEST_USD","0"))
        if not math.isfinite(rate) or rate<=0:raise ValueError("A verified maximum narration request cost is required.")
        answer=service.store.get_artifact(owner,body.get("answer_id"),"answer")["body"]
        current=service.store.session(owner)["context"]
        if answer["context_revision"]!=current["revision"]:raise ValueError("Answer belongs to a previous study. Select a current answer before narration.")
        text=answer.get("spoken_summary","")[:800]
        if not text:raise ValueError("This answer has no approved narration.")
        characters=sum(v["body"].get("characters",0) for v in prior if v["body"].get("created",0)>today and v["body"].get("operation")=="synthesize")
        if characters+len(text)>4000:raise ValueError("This workspace's narration allowance has been reached.")
        reservation=service.store.reserve(owner,math.ceil(rate*1e6))
        response=client.audio.speech.create(model=os.getenv("FIREATLAS_TTS_MODEL","gpt-4o-mini-tts"),voice="coral",input=text,response_format="mp3")
        data=response.read()
        service.store.reconcile(owner,reservation,math.ceil(rate*1e6))
        service.store.artifact(owner,"voice_receipt",{"operation":operation,"characters":len(text),"created":time.time(),"answer_id":body["answer_id"]})
        return {"data":base64.b64encode(data).decode(),"mime":"audio/mpeg","text":text,"disclosure":"AI-generated narration of checked evidence; not an eyewitness account."}
    raise ValueError("Unsupported speech operation.")


def synthesize_checked(service, owner, text, reference, *, model=None, voice="coral", transport=None):
    """Narrate one server-resolved Studio segment through the existing speech ledger.

    Only internal callers may provide text here. They must first resolve checked fields
    against owned receipts. Uncertain failures leave the reservation held, exactly as
    ordinary assistant speech does; there is no automatic paid retry.
    """
    from .agent import provider_config
    if provider_config().get('free_only'):
        raise ValueError("Paid speech is disabled in free-only mode.")
    if not isinstance(text, str) or not 1 <= len(text) <= 800:
        raise ValueError("Checked speech segments contain 1–800 characters.")
    rate = float(os.getenv("FIREATLAS_TTS_MAX_REQUEST_USD", "0"))
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError("A verified maximum narration request cost is required.")
    if transport is None and not os.getenv("OPENAI_API_KEY"):
        raise ValueError("Speech provider is not configured.")
    prior = service.store.artifacts(owner, "voice_receipt")
    characters = sum(v["body"].get("characters", 0) for v in prior
                     if v["body"].get("created", 0) > time.time() - 86400 and v["body"].get("operation") == "synthesize")
    if characters + len(text) > 4000:
        raise ValueError("This workspace's narration allowance has been reached.")
    reservation = service.store.reserve(owner, math.ceil(rate * 1e6))
    if transport:
        data = transport(text)
    else:
        from openai import OpenAI
        client = OpenAI(timeout=30, max_retries=0)
        data = client.audio.speech.create(model=model or os.getenv("FIREATLAS_TTS_MODEL", "gpt-4o-mini-tts"),
                                          voice=voice, input=text, response_format="mp3").read()
    if not data or len(data) > 8_000_000:
        raise ValueError("The speech response was empty or exceeded 8 MB.")
    service.store.reconcile(owner, reservation, math.ceil(rate * 1e6))
    service.store.artifact(owner, "voice_receipt", {"operation": "synthesize", "characters": len(text), "created": time.time(),
                                                   "studio_reference": reference, "reservation": reservation})
    return data
