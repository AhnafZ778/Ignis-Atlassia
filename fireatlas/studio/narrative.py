"""Resolve structured story prose from cited frozen receipts, without model wording or live inputs."""
from __future__ import annotations

from . import evidence as ev
from .errors import LimitExceeded, StudioError
from .graph import canonical, check_id

SCHEMA = 'fireatlas-story-narration-v1'
AUTHORED_NOTE = 'Authored explanation; numeric references are screened against cited evidence. Interpretation is not independently verified.'
STRUCTURED_NOTE = 'Checked fields resolve from cited frozen receipts; surrounding explanation remains authored interpretation.'


def validate_segments(segments):
    if not isinstance(segments, list) or len(segments) > 32:
        raise StudioError('A chapter has at most 32 narration segments.', code='invalid-chapter')
    for segment in segments:
        if not isinstance(segment, dict) or set(segment) - {'kind', 'text', 'path', 'format', 'author', 'snapshot_id'} or segment.get('kind') not in ('text', 'checked-field'):
            raise StudioError('Narration segments are text or checked fields.', code='invalid-chapter')
        if segment['kind'] == 'text' and (not isinstance(segment.get('text', ''), str) or len(segment.get('text', '')) > 1200):
            raise StudioError('Narration text is limited to 1,200 characters per segment.', code='invalid-chapter')
        if segment['kind'] == 'checked-field' and (not isinstance(segment.get('path'), str) or not segment['path'].startswith('/') or len(segment['path']) > 512):
            raise StudioError('A checked narration field needs a bounded JSON pointer.', code='invalid-chapter')
        if segment.get('snapshot_id') is not None:
            check_id(segment['snapshot_id'], 'narration snapshot ID')
        if segment.get('format', 'raw') not in ('raw', 'with-unit') or segment.get('author', 'user') not in ('user', 'assistant'):
            raise StudioError('Narration accepts raw or with-unit fields and an explicit author.', code='invalid-chapter')
    if len(canonical(segments)) > 8000:
        raise LimitExceeded('Chapter narration segments exceed 8 KiB.', code='invalid-chapter')
    return segments


def resolve(authored_text, segments, snapshots, receipts):
    """Unknown scalars stay unknown. Absent/ambiguous fields are explicitly unresolved."""
    if not isinstance(authored_text, str) or len(authored_text) > 1200:
        raise StudioError('Authored narration is limited to 1,200 characters.', code='invalid-chapter')
    validate_segments(segments)
    fields, missing, parts = [], [], []
    for segment in segments:
        if segment['kind'] == 'text':
            parts.append(segment.get('text', ''))
            continue
        candidates = []
        for snapshot in snapshots:
            if segment.get('snapshot_id') and segment['snapshot_id'] != snapshot['id']:
                continue
            receipt = receipts.get(snapshot['id'])
            if not receipt:
                continue
            candidate = ev._state_of({**receipt, 'id': snapshot['result_id']}, segment['path'])
            if candidate['state'] != 'unavailable':
                candidates.append({**candidate, 'snapshot_id': snapshot['id']})
        field = candidates[0] if candidates and len({canonical({k: item[k] for k in ('value', 'unit', 'state')}) for item in candidates}) == 1 else None
        if field is None:
            missing.append(segment['path'])
            parts.append('unknown')
        else:
            fields.append(field)
            value = field['value']
            parts.append(str(value) + (' ' + field['unit'] if segment.get('format') == 'with-unit' else '') if value is not None else 'unknown')
    text = ' '.join(part for part in parts if part) if segments else authored_text
    if len(text) > 2400:
        raise LimitExceeded('Resolved chapter narration exceeds 2,400 characters.', code='story-too-long')
    checked = ev.check_narration(text, snapshots, resolved_fields=fields)
    mode = 'structured' if any(s['kind'] == 'checked-field' for s in segments) else 'authored'
    return {'text': text, 'fields': fields, 'missing': missing, 'checked': checked['checked'] and not missing,
            'unmatched_numbers': checked['unmatched_numbers'],
            'grounding': {'mode': mode, 'note': STRUCTURED_NOTE if mode == 'structured' else AUTHORED_NOTE}}
