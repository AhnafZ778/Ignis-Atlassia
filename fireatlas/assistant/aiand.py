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
_lock = threading.Lock()
_cache = None
_stamp = None
_updated = 0.0


def routes():
    return {'efficient': os.getenv('FIREATLAS_AIAND_MODEL', EFFICIENT_MODEL),
            'efficient_vision': os.getenv('FIREATLAS_AIAND_VISION_MODEL', EFFICIENT_VISION_MODEL),
            'deep': os.getenv('FIREATLAS_AIAND_DEEP_MODEL', DEEP_MODEL),
            'deep_vision': os.getenv('FIREATLAS_AIAND_DEEP_VISION_MODEL', DEEP_VISION_MODEL)}


def verified_model(depth='efficient', vision=False):
    global _cache, _stamp, _updated
    if depth not in {'efficient', 'deep'}:
        raise ValueError('Choose efficient or deep analysis.')
    key = os.getenv('AIAND_API_KEY', '')
    if not key:
        raise ValueError('AI& requires a private server-side API key.')
    stamp = hashlib.sha256(key.encode()).digest()
    with _lock:
        if _cache is None or _stamp != stamp or time.monotonic()-_updated > 300:
            import httpx
            try:
                response = httpx.get(BASE_URL+'/models', headers={'Authorization':'Bearer '+key, 'User-Agent':'FireAtlas/1.0'}, timeout=15)
                response.raise_for_status()
                _cache = {m['id']:m for m in response.json()['data']}
            except Exception:
                raise ValueError('AI& model access and prices could not be verified. No inference was sent; archive tools remain available.') from None
            _stamp, _updated = stamp, time.monotonic()
    name = routes()[depth+'_vision' if vision else depth]
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
    effort = 'high' if depth=='deep' else 'none' if name.startswith('deepseek-ai/') else 'low'
    if effort not in entry.get('reasoning_efforts', []):
        raise ValueError('The selected AI& model does not support the requested reasoning setting.')
    return {'model':name, 'input_price':ip, 'output_price':op, 'reasoning_effort':effort,
            'max_tokens':2400 if depth=='deep' else 1600, 'analysis_depth':depth,
            'vision':vision, 'currency':'USD', 'price_basis':'authenticated AI& model catalog; uncached upper bound'}
