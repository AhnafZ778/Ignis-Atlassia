"""AI& routing with authenticated capability and USD price verification."""
from __future__ import annotations
import hashlib
import math
import os
import threading
import time

BASE_URL = 'https://api.aiand.com/v1'
EFFICIENT_MODEL = 'zai-org/glm-5.3-flash'
EFFICIENT_VISION_MODEL = 'deepseek-ai/deepseek-v4.1-flash'
DEEP_MODEL = 'deepseek-ai/deepseek-v4-pro'
DEEP_VISION_MODEL = 'deepseek-ai/deepseek-v4.1-flash'
STORY_MODEL = 'zai-org/glm-5.3'
_lock = threading.Lock()
_cache = None
_stamp = None
_updated = 0.0
_authenticated_key = None


def configured_keys():
    """Private ordered credentials. Never put these in a capability or receipt."""
    return list(dict.fromkeys(k.strip() for k in
                [os.getenv('AIAND_API_KEY', ''), *os.getenv('AIAND_API_KEYS', '').split(',')] if k.strip()))


def authenticated_key():
    # Callers first verify the model/catalog. Avoid a second verification that
    # would replace the selected deep/vision route or repeat a network request.
    keys = configured_keys()
    if not keys:
        raise ValueError('AI& requires a private server-side API key.')
    return _authenticated_key if _authenticated_key in keys else keys[0]


def routes():
    return {'efficient': os.getenv('FIREATLAS_AIAND_MODEL', EFFICIENT_MODEL),
            'efficient_vision': os.getenv('FIREATLAS_AIAND_VISION_MODEL', EFFICIENT_VISION_MODEL),
            'deep': os.getenv('FIREATLAS_AIAND_DEEP_MODEL', DEEP_MODEL),
            'deep_vision': os.getenv('FIREATLAS_AIAND_DEEP_VISION_MODEL', DEEP_VISION_MODEL)}


def verified_model(depth='efficient', vision=False, *, model=None, reasoning_effort=None):
    global _cache, _stamp, _updated, _authenticated_key
    if depth not in {'efficient', 'deep'}:
        raise ValueError('Choose efficient or deep analysis.')
    keys = configured_keys()
    if not keys:
        raise ValueError('AI& requires a private server-side API key.')
    stamp = hashlib.sha256('\n'.join(keys).encode()).digest()
    with _lock:
        if _cache is None or _stamp != stamp or time.monotonic()-_updated > 300:
            import httpx
            catalog = None
            try:
                for key in keys:
                    response = httpx.get(BASE_URL+'/models', headers={'Authorization':'Bearer '+key, 'User-Agent':'FireAtlas/1.0'}, timeout=15)
                    # Only rejected authentication permits trying another credential.
                    # Inference is never replayed using a different key.
                    if response.status_code in (401, 403):
                        continue
                    response.raise_for_status()
                    catalog = {m['id']:m for m in response.json()['data']}
                    _authenticated_key = key
                    break
                if catalog is None:
                    raise ValueError()
                _cache = catalog
            except Exception:
                raise ValueError('AI& model access and prices could not be verified. No inference was sent; archive tools remain available.') from None
            _stamp, _updated = stamp, time.monotonic()
    name = model or routes()[depth+'_vision' if vision else depth]
    entry = _cache.get(name, {})
    capabilities = entry.get('capabilities', [])
    if 'tool_calling' not in capabilities or vision and 'vision' not in capabilities:
        raise ValueError('The selected AI& model does not support the required tools or figures.')
    try:
        ip, op = float(entry['input_per_1m']), float(entry['output_per_1m'])
        ceilings = float(os.getenv('FIREATLAS_AIAND_MAX_INPUT_PRICE','2')), float(os.getenv('FIREATLAS_AIAND_MAX_OUTPUT_PRICE','5'))
        if entry.get('currency')!='usd' or not all(math.isfinite(p) and p>0 for p in (ip,op,*ceilings)) or ip>ceilings[0] or op>ceilings[1]:
            raise ValueError()
    except (KeyError,ValueError,TypeError):
        raise ValueError('AI& prices exceed configured USD limits or cannot be verified. No paid request was sent.') from None
    effort = reasoning_effort or ('high' if depth=='deep' else 'none' if name.startswith('deepseek-ai/') else 'low')
    if effort not in entry.get('reasoning_efforts', []):
        raise ValueError('The selected AI& model does not support the requested reasoning setting.')
    return {'model':name, 'input_price':ip, 'output_price':op, 'reasoning_effort':effort,
            'max_tokens':2400 if depth=='deep' else 1600, 'analysis_depth':depth,
            'vision':vision, 'currency':'USD', 'price_basis':'authenticated AI& model catalog; uncached upper bound'}


def structured_story(store, owner, instructions, material, cancel):
    """One accounted AI& authoring call. No paid retries, including after a timeout."""
    import json
    import httpx
    if cancel.is_set():
        raise ValueError('Story generation cancelled.')
    model = {**verified_model('deep', model=os.getenv('FIREATLAS_AIAND_STORY_MODEL', STORY_MODEL),
                             reasoning_effort=os.getenv('FIREATLAS_AIAND_STORY_EFFORT', 'high')), 'max_tokens': 8192}
    messages = [{'role': 'system', 'content': instructions},
                {'role': 'user', 'content': json.dumps(material, ensure_ascii=False, allow_nan=False)}]
    size = len(json.dumps(messages).encode())
    if size > 100_000:
        raise ValueError('Selected story material is too large. Choose fewer evidence cards.')
    reserved = store.reserve(owner, max(1, math.ceil(size * model['input_price'] + model['max_tokens'] * model['output_price'])))
    try:
        response = httpx.post(BASE_URL+'/chat/completions', headers={
            'Authorization': 'Bearer '+_authenticated_key, 'User-Agent': 'FireAtlas/1.0'},
            json={'model': model['model'], 'messages': messages, 'max_tokens': model['max_tokens'],
                  'reasoning_effort': model['reasoning_effort'], 'response_format': {'type': 'json_object'}}, timeout=180)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        # Uncertain usage remains reserved using ordinary assistant accounting.
        raise ValueError('AI& could not complete this story request. Existing stories remain available; the request was not retried.') from None
    usage = payload.get('usage') or {}
    incoming, outgoing = usage.get('prompt_tokens'), usage.get('completion_tokens')
    actual = math.ceil(incoming * model['input_price'] + outgoing * model['output_price']) if type(incoming) is int and type(outgoing) is int and incoming >= 0 and outgoing >= 0 else None
    store.reconcile(owner, reserved, actual)
    receipt = {'provider': 'aiand', 'model': payload.get('model', model['model']), 'usage': usage,
               'estimated_cost_usd': actual / 1e6 if actual is not None else None,
               'price_basis': model['price_basis'], 'operation': 'infographic-story'}
    store.artifact(owner, 'inference_receipt', receipt)
    if cancel.is_set():
        raise ValueError('Story generation cancelled.')
    try:
        choice = payload['choices'][0]
        if choice.get('finish_reason') != 'stop':
            raise ValueError()
        content = choice['message']['content']
        if not isinstance(content, str) or len(content.encode()) > 32_000:
            raise ValueError()
        return json.loads(content), receipt
    except (ValueError, KeyError, TypeError, IndexError):
        raise ValueError('AI& returned an incomplete story. No draft was published; existing stories are retained.') from None
