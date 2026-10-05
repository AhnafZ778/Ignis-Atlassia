"""Freeze existing prepared context images; no fetching or scientific inference."""
from __future__ import annotations
import base64
import hashlib
import json
from pathlib import Path
from .errors import StudioError

STATIC = Path(__file__).resolve().parents[1] / 'static'
MAX_LAYER_BYTES = 1_500_000


def catalog():
    manifest = STATIC / 'replay-context/manifest.json'
    try:
        data = manifest.read_bytes()
        return {'manifest_sha256': hashlib.sha256(data).hexdigest(), 'layers': json.loads(data)['layers']}
    except (OSError, ValueError, KeyError):
        return {'manifest_sha256': None, 'layers': {}}


def freeze(scope, selected):
    """Bind a supplied layer to its exact prepared footprint and dated provenance."""
    if not selected:
        return []
    inventory = catalog()
    candidates = inventory['layers'].get(scope.get('case'), {})
    if not candidates:
        candidates = next((layers for layers in inventory['layers'].values()
                           if any(layer.get('bounds') == scope['bbox'] for layer in layers.values())), {})
    frozen = []
    for name in selected:
        meta = candidates.get(name)
        if not meta or meta.get('status') != 'available' or meta.get('bounds') != scope['bbox']:
            raise StudioError('Context layer ' + name + ' is unavailable for this exact frozen footprint.', code='scene-context')
        path = (STATIC / meta['path']).resolve()
        if not path.is_relative_to((STATIC / 'replay-context').resolve()) or not path.is_file() or path.stat().st_size > MAX_LAYER_BYTES:
            raise StudioError('Prepared context layer bytes are missing or oversized.', code='scene-context')
        data = path.read_bytes()
        if len(data) != meta['bytes'] or hashlib.sha256(data).hexdigest() != meta['sha256'] or not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise StudioError('Prepared context layer does not match its recorded input hash.', code='scene-context')
        frozen.append({'name': name, 'metadata': meta, 'manifest_sha256': inventory['manifest_sha256'],
                       'mime': 'image/png', 'data': base64.b64encode(data).decode(),
                       'disclosure': 'Dated supplied landscape context; not observation opportunity, incident membership or independent validation.'})
    return frozen


def verify(layers, scope):
    """Check embedded bytes and scope without reading the current local manifest."""
    for layer in layers:
        meta = layer['metadata']
        data = base64.b64decode(layer['data'], validate=True)
        if (len(data) > MAX_LAYER_BYTES or len(data) != meta['bytes'] or hashlib.sha256(data).hexdigest() != meta['sha256']
                or meta['bounds'] != scope['bbox'] or layer['mime'] != 'image/png' or not data.startswith(b'\x89PNG\r\n\x1a\n')):
            raise StudioError('Frozen context layer bytes or footprint disagree with their recorded evidence.', code='scene-context')
