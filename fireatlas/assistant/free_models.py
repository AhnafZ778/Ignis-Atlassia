"""OpenRouter free-only routing. Catalog verification fails closed."""
from __future__ import annotations

import json
import math
import threading
import time
import urllib.request

TEXT_MODEL = 'nvidia/nemotron-3-ultra-550b-a55b:free'
VISION_MODEL = 'google/gemma-4-31b-it:free'
TEXT_FALLBACKS = ('nvidia/nemotron-3-super-120b-a12b:free', VISION_MODEL)
VISION_FALLBACKS = ('google/gemma-4-26b-a4b-it:free', 'qwen/qwen3.8-27b:free')
_lock = threading.Lock()
_catalog = None
_updated = 0.0


def free_entry(entry, vision=False):
    if not entry.get('id', '').endswith(':free'):
        return False
    prices = entry.get('pricing', {})
    try:
        if not {'prompt', 'completion'} <= prices.keys() or any(
            not math.isfinite(float(v)) or float(v) != 0 for v in prices.values()
        ):
            return False
    except (ValueError, TypeError):
        return False
    parameters = entry.get('supported_parameters', [])
    return ('tools' in parameters and 'tool_choice' in parameters
            and (not vision or 'image' in entry.get('architecture', {}).get('input_modalities', [])))


def verified_routes(primary, vision=False):
    global _catalog, _updated
    if not primary.endswith(':free'):
        raise ValueError('Free-only mode rejects paid models and automatic routers.')
    with _lock:
        if _catalog is None or time.monotonic() - _updated > 300:
            try:
                with urllib.request.urlopen('https://openrouter.ai/api/v1/models', timeout=15) as response:
                    data = json.loads(response.read(8_000_000))
                _catalog = {m['id']: m for m in data['data']}
                _updated = time.monotonic()
            except Exception:
                raise ValueError('Cannot verify free model prices. No inference request was sent; stored-data tools remain available.') from None
        candidates = (primary, *(VISION_FALLBACKS if vision else TEXT_FALLBACKS))
        routes = list(dict.fromkeys(m for m in candidates if free_entry(_catalog.get(m, {}), vision)))
        if primary not in routes:
            raise ValueError('The configured model is no longer a verified free tool/vision model. No paid fallback is permitted.')
        return routes[:3]  # OpenRouter permits at most three fallback model IDs.
