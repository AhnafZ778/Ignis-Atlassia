"""Durable, revision-bound JARVIS story authoring over frozen Studio evidence."""
from __future__ import annotations

import json
import datetime
import re
import secrets
import threading
import time
from pathlib import Path

from . import story
from .errors import Conflict, NotFound, StudioError, Unavailable
from .store import dumps

INSTRUCTIONS = Path(__file__).with_name('story_system.md').read_text()
TERMINAL = {'completed', 'partial', 'failed', 'cancelled'}


def compose(output, capture):
    """The model directs prose and card order; it cannot change calculations or display inputs."""
    if not isinstance(output, dict) or set(output) != {'title', 'chapters'}:
        raise StudioError('AI& returned an unsupported story structure.')
    chapters = output['chapters']
    if not isinstance(chapters, list) or not 4 <= len(chapters) <= 6:
        raise StudioError('AI& must return four to six complete chapters.')
    allowed = capture['selected_cards']
    state, snapshots = capture['state'], capture['snapshots']
    assembled = []
    for index, chapter in enumerate(chapters):
        if not isinstance(chapter, dict) or set(chapter) != {'title', 'caption', 'card_ids', 'duration_seconds', 'transition', 'narration_segments'}:
            raise StudioError('AI& returned an unsupported chapter.')
        ids = chapter['card_ids']
        if not isinstance(ids, list) or not 1 <= len(ids) <= 3 or any(not isinstance(cid, str) or cid not in allowed for cid in ids):
            raise StudioError('AI& selected a card outside the captured investigation.')
        ids = list(ids)
        primary_display = state['cards'][ids[0]].get('display') or {}
        if state['cards'][ids[0]]['type'] == 'map' and primary_display.get('preview') == 'heat':
            # Keep an existing matching sensor pair together; this never creates
            # another cohort, date or scale and respects the explicitly selected cards.
            for cid in allowed:
                other = state['cards'][cid]
                display = other.get('display') or {}
                if (len(ids) < 3 and cid not in ids and other['type'] == 'map'
                        and other['snapshot_id'] == state['cards'][ids[0]]['snapshot_id']
                        and display.get('preview') == 'heat' and display.get('day') == primary_display.get('day')
                        and {display.get('source'), primary_display.get('source')} == {'MODIS_SP', 'VIIRS_SNPP_SP'}):
                    ids.append(cid)
        evidence_ids = list(dict.fromkeys(ids))
        date_refs = capture.get('date_refs', [])
        all_fields = {(sid, f['path']) for sid, s in snapshots.items() for f in s['facts']} | {(ref['snapshot_id'], ref['path']) for ref in date_refs}
        from .evidence import check_narration
        segments = chapter['narration_segments']
        from .narrative import validate_segments
        if isinstance(segments, list):
            grounded = []
            for segment in segments:
                if isinstance(segment, dict) and segment.get('kind') == 'text':
                    text = segment.get('text', '')
                    for ref in date_refs:
                        date = datetime.date.fromisoformat(ref['value'])
                        pattern = re.compile(r'\b'+date.strftime('%B')+r'\s+0?'+str(date.day)+r'\b', re.I)
                        match = pattern.search(text)
                        if match:
                            grounded.extend([{'kind': 'text', 'text': text[:match.start()]},
                                {'kind': 'checked-field', 'snapshot_id': ref['snapshot_id'], 'path': ref['path'], 'format': 'raw'}])
                            text = text[match.end():]
                    grounded.append({**segment, 'text': text})
                else:
                    grounded.append(segment)
            segments = grounded
        # The director may cite another selected card while showing a map.
        # Attach that owned receipt rather than rejecting a valid cross-card citation.
        if isinstance(segments, list):
            for segment in segments:
                if not isinstance(segment, dict) or segment.get('kind') != 'checked-field':
                    continue
                ref = (segment.get('snapshot_id'), segment.get('path'))
                if ref not in all_fields:
                    raise StudioError('AI& cited a field outside the captured investigation.')
                source = next(cid for cid in allowed if state['cards'][cid]['snapshot_id'] == ref[0])
                if source not in evidence_ids:
                    evidence_ids.append(source)
                # Format is presentation, never model-defined units or arithmetic.
                segment['format'] = 'raw' if segment.get('format') == 'raw' else 'with-unit'
        cited = [snapshots[state['cards'][cid]['snapshot_id']] for cid in evidence_ids]
        cited.append({'facts': date_refs})  # Verified selected-frame dates, never new measurements.
        validate_segments(segments)
        if not segments:
            raise StudioError('AI& returned an empty narration.')
        for segment in segments:
            if segment['kind'] == 'text':
                if not check_narration(segment.get('text', ''), cited)['checked']:
                    raise StudioError('AI& used a number outside the captured scientific evidence.')
                segment['author'] = 'assistant'
        if not all(isinstance(chapter.get(k), str) for k in ('title', 'caption')) or not check_narration(chapter['title'] + ' ' + chapter['caption'], cited)['checked']:
            raise StudioError('AI& used a caption number outside the captured scientific evidence.')
        duration = chapter['duration_seconds']
        if type(duration) not in (int, float) or not 8 <= duration <= 24:
            raise StudioError('AI& returned invalid chapter timing.')
        primary = state['cards'][ids[0]]
        display = primary.get('display') or {}
        # Frozen card display takes precedence over model direction.
        selected = {'day': display['day']} if display.get('day') else {}
        assembled.append({'id': f'scene-{index+1}', 'title': chapter['title'], 'caption': chapter['caption'],
                          'narration': '', 'narration_segments': segments, 'card_id': ids[0],
                          'visible_cards': ids, 'evidence_cards': evidence_ids, 'selection': selected,
                          'source_filter': display.get('source') if display.get('source') in {'joint', 'MODIS_SP', 'VIIRS_SNPP_SP'} else 'joint',
                          'duration_seconds': duration, 'transition': chapter['transition']})
    duration = sum(c['duration_seconds'] for c in assembled)
    if not 45 <= duration <= 120:
        raise StudioError('AI& returned an invalid film duration.')
    return story.clean_story({'title': output['title'], 'chapters': assembled,
        'audience': 'presenter', 'target_duration_seconds': duration,
        'author_note': 'AI& authored the narration. Numerical fields resolve from captured scientific receipts.',
        'style': {'theme': 'ignis-infographic', 'motion': 'reduced-motion-safe', 'author': 'aiand'}})


class StoryGeneration:
    def __init__(self, service, author=None, background=True):
        self.service, self.store = service, service.store
        self.author, self.background = author, background
        self.flags, self.lock = {}, threading.RLock()
        with self.store.connection(write=True) as db:
            db.execute("UPDATE story_generations SET status=CASE WHEN story_id IS NULL THEN 'failed' ELSE 'partial' END, "
                       "phase='interrupted',error='The service restarted. Saved stories remain available; no paid request was repeated.' "
                       "WHERE status IN ('queued','running')")

    def capabilities(self):
        from ..assistant.aiand import configured_keys
        available = self.service.assistant is not None and bool(configured_keys())
        return {'available': available, 'provider': 'aiand', 'reason': None if available else
                'AI& story creation needs the existing assistant runtime and a server-side AIAND_API_KEY.',
                'disclosure': 'AI& authors the evidence-grounded storyboard; local rendering produces the infographic video.'}

    def submit(self, principal, document_id, body, key=None):
        with self.lock:
            with self.store.connection(write=True) as db:
                self.store.require(db, principal, document_id, 'editor')
                replay = self.store.replay(db, principal, 'ai-story:'+document_id, key)
                if replay:
                    return self.get(principal, replay['id'])
            document = self.service.get_document(principal, document_id)
            if body.get('expected_revision') != document['revision']:
                raise Conflict('The investigation changed. Create the story from the current revision.')
            if not self.author and not self.capabilities()['available']:
                raise Unavailable(self.capabilities()['reason'])
            ids = body.get('selected_cards', document['state']['order'])
            if not isinstance(ids, list) or not ids or len(ids) > 100 or any(not isinstance(cid, str) or cid not in document['state']['cards'] for cid in ids):
                raise StudioError('Choose existing investigation cards for the story.')
            supported = [cid for cid in ids if document['state']['cards'][cid].get('snapshot_id') or document['state']['cards'][cid].get('binding')]
            if not supported:
                raise StudioError('This investigation has no frozen scientific evidence. Choose a prepared presentation or bind its cards first.')
            snapshots = {sid: document['snapshots'][sid] for cid in supported if (sid := document['state']['cards'][cid]['snapshot_id'])}
            capture = {'state': document['state'], 'snapshots': snapshots, 'selected_cards': supported,
                       'release': document.get('release') or {'id': 'frozen'}, 'render': body.get('render', True)}
            if type(capture['render']) is not bool:
                raise StudioError('Render must be an explicit Boolean.')
            with self.store.connection(write=True) as db:
                self.store.require(db, principal, document_id, 'editor')
                if db.execute('SELECT revision FROM documents WHERE id=?', (document_id,)).fetchone()[0] != document['revision']:
                    raise Conflict('The investigation changed during capture. Create again from its current revision.')
                if db.execute("SELECT 1 FROM story_generations WHERE status IN ('queued','running')").fetchone():
                    raise Conflict('A story is already being prepared. Open its progress to continue.', code='story-busy')
                identifier, now = 'sgn_'+secrets.token_urlsafe(12), self.store.clock()
                db.execute('INSERT INTO story_generations(id,principal_id,document_id,document_revision,status,phase,progress,capture,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?)',
                           (identifier, principal, document_id, document['revision'], 'queued', 'capturing', .05, dumps(capture), now, now))
                self.store.remember(db, principal, 'ai-story:'+document_id, key, {'id': identifier})
            flag = threading.Event()
            self.flags[identifier] = flag
            if self.background:
                threading.Thread(target=self.run, args=(principal, identifier, flag), daemon=True).start()
            else:
                self.run(principal, identifier, flag)
            return self.get(principal, identifier)

    def get(self, principal, identifier):
        with self.store.connection() as db:
            row = db.execute('SELECT * FROM story_generations WHERE id=?', (identifier,)).fetchone()
            if not row:
                raise NotFound('Story generation not found.')
            self.store.require(db, principal, row['document_id'])
            view = {k: row[k] for k in ('id', 'document_id', 'document_revision', 'status', 'phase', 'progress', 'story_id', 'render_id', 'error', 'created')}
            view['receipt'] = json.loads(row['receipt']) if row['receipt'] else None
        if view['render_id']:
            render = self.service.renders.get(principal, view['render_id'])
            view['render'] = render
            if view['status'] not in {'cancelled', 'failed'}:
                view.update(status='completed' if render['status'] == 'completed' else 'partial' if render['status'] in {'failed', 'canceled'} else 'running',
                            phase=render.get('phase', render['status']), progress=.65 + .35*render['progress'], error=render['error'])
        view['can_resume'] = view['status'] == 'failed' and not view['story_id'] and self.saved_draft(row['principal_id'], identifier) is not None
        return view

    def cancel(self, principal, identifier):
        with self.lock, self.store.connection(write=True) as db:
            row = db.execute('SELECT * FROM story_generations WHERE id=?', (identifier,)).fetchone()
            if not row:
                raise NotFound('Story generation not found.')
            self.store.require(db, principal, row['document_id'], 'editor')
            db.execute("UPDATE story_generations SET cancel=1,status='cancelled',phase='cancelled',updated=? WHERE id=?", (self.store.clock(), identifier))
            if identifier in self.flags:
                self.flags[identifier].set()
        if row['render_id']:
            self.service.renders.cancel(principal, row['render_id'])
        return self.get(principal, identifier)

    def saved_draft(self, principal, identifier):
        with self.store.connection() as db:
            rows = db.execute("SELECT body FROM science_results WHERE principal_id=? AND kind='story_authoring_draft' ORDER BY created DESC LIMIT 100", (principal,)).fetchall()
        return next((body['output'] for row in rows if (body := json.loads(row['body'])).get('generation_id') == identifier), None)

    def resume(self, principal, identifier):
        """Explicitly finish a saved storyboard; never repeat an uncertain paid call."""
        with self.lock, self.store.connection(write=True) as db:
            row = db.execute('SELECT * FROM story_generations WHERE id=?', (identifier,)).fetchone()
            if not row:
                raise NotFound('Story generation not found.')
            self.store.require(db, principal, row['document_id'], 'editor')
            if row['status'] != 'failed' or row['story_id'] or self.saved_draft(principal, identifier) is None:
                raise Conflict('No unfinished saved storyboard is available. Saved films remain accessible; a new AI request requires Create story.')
            if db.execute("SELECT 1 FROM story_generations WHERE status IN ('queued','running')").fetchone():
                raise Conflict('A story is already being prepared.')
            db.execute("UPDATE story_generations SET status='queued',phase='checking-evidence',cancel=0,error=NULL WHERE id=?", (identifier,))
        flag = threading.Event()
        self.flags[identifier] = flag
        threading.Thread(target=self.run, args=(principal, identifier, flag), daemon=True).start()
        return self.get(principal, identifier)

    def update(self, identifier, **fields):
        with self.store.connection(write=True) as db:
            db.execute('UPDATE story_generations SET '+','.join(k+'=?' for k in fields)+',updated=? WHERE id=? AND cancel=0',
                       (*fields.values(), self.store.clock(), identifier))

    def run(self, principal, identifier, flag):
        try:
            with self.store.connection() as db:
                row = db.execute('SELECT * FROM story_generations WHERE id=?', (identifier,)).fetchone()
                capture = json.loads(row['capture'])
            from . import evidence, graph
            for cid in capture['selected_cards']:
                if flag.is_set():
                    return
                card = capture['state']['cards'][cid]
                if card['snapshot_id']:
                    continue
                binding = card['binding']
                context = {**(graph.effective_study(card, capture['state']).get('context') or {}), **(binding.get('context') or {})}
                result = self.service.science.call(principal, binding['operation'], context, binding.get('arguments') or {}, flag, time.monotonic()+120)
                release = self.service.science.release()
                if release['id'] != result['release_id']:
                    raise Conflict('The scientific inputs changed during story capture. Try again from the current investigation.')
                snapshot = self.store.add_snapshot(principal, row['document_id'], evidence.build_snapshot(result, release, binding))
                capture['snapshots'][snapshot['id']] = snapshot
                card['snapshot_id'] = snapshot['id']
            self.update(identifier, capture=dumps(capture))
            receipts = self.service._receipts(principal, row['document_id'], capture['snapshots'])
            capture['date_refs'] = []
            for cid in capture['selected_cards']:
                card = capture['state']['cards'][cid]
                day = card.get('display', {}).get('day')
                sid = card['snapshot_id']
                for index, frame in enumerate(receipts.get(sid, {}).get('payload', {}).get('frames', [])):
                    if day and frame.get('date_utc') == day:
                        ref = {'snapshot_id': sid, 'path': f'/frames/{index}/date_utc', 'value': day, 'unit': 'UTC date', 'state': 'observed', 'label': 'Captured acquisition date'}
                        if ref not in capture['date_refs']:
                            capture['date_refs'].append(ref)
            self.update(identifier, capture=dumps(capture))
            self.update(identifier, status='running', phase='writing-story', progress=.18)
            material = {'study': capture['state']['study'], 'title': capture['state']['title'],
                'cards': [{'id': cid, 'type': card['type'], 'title': card['title'], 'display': card['display'],
                          'snapshot_id': sid, 'scope': capture['snapshots'][sid]['scope'],
                          'method': capture['snapshots'][sid]['method'], 'facts': capture['snapshots'][sid]['facts'][:24]+[ref for ref in capture['date_refs'] if ref['snapshot_id'] == sid],
                          'limitations': capture['snapshots'][sid]['limitations'][:4]}
                         for cid in capture['selected_cards'] if (card := capture['state']['cards'][cid]) and (sid := card['snapshot_id'])]}
            cached = self.saved_draft(principal, identifier)
            if cached is not None:
                output, receipt = cached, json.loads(row['receipt']) if row['receipt'] else {}
            elif self.author:
                output, receipt = self.author(INSTRUCTIONS, material, flag)
            else:
                from ..assistant.aiand import structured_story
                output, receipt = structured_story(self.service.assistant.store, self.service.assistant_owner(principal), INSTRUCTIONS, material, flag)
            if flag.is_set():
                return
            if cached is None:
                self.store.artifact(principal, 'story_authoring_draft', {'generation_id': identifier, 'output': output})
            self.update(identifier, phase='checking-evidence', progress=.45, receipt=dumps(receipt))
            body = compose(output, capture)
            sid = 'str_'+secrets.token_urlsafe(12)
            resolved = story.resolve_story(body, capture['state'], capture['snapshots'], capture['release'],
                story_id=sid, story_revision=1, document_id=row['document_id'], document_revision=row['document_revision'],
                receipts=self.service._receipts(principal, row['document_id'], capture['snapshots']))
            if resolved['warnings'] and any(w['problem'] in {'evidence-unfrozen', 'card-missing', 'checked-field-unavailable', 'scene-context', 'narration-unchecked'} for w in resolved['warnings']):
                raise StudioError('Generated scenes could not be matched to the frozen evidence. No unchecked story was published.')
            if len(dumps(resolved).encode()) > 20_000_000:
                raise StudioError('The prepared story exceeds the existing scene size limit. Choose fewer evidence cards.')
            with self.lock, self.store.connection(write=True) as db:
                self.store.require(db, principal, row['document_id'], 'editor')
                if flag.is_set() or db.execute('SELECT cancel FROM story_generations WHERE id=?', (identifier,)).fetchone()[0]:
                    return
                now = self.store.clock()
                db.execute('INSERT INTO stories VALUES(?,?,?,?,?,?,?)', (sid, row['document_id'], principal, body['title'], 1, now, now))
                db.execute('INSERT INTO story_revisions VALUES(?,?,?,?,?,?,?,?)', (sid, 1, row['document_revision'], dumps(body), dumps(resolved), resolved['sha256'], principal, now))
                db.execute("UPDATE story_generations SET story_id=?,status='completed',phase='saved',progress=.65,updated=? WHERE id=?", (sid, now, identifier))
            if flag.is_set() or not capture['render']:
                self.update(identifier, progress=1.0)
                return
            try:
                with self.lock:
                    if flag.is_set():
                        return
                    render = self.service.start_render(principal, sid, key='ai-story:'+identifier)
                    self.update(identifier, render_id=render['id'], phase='rendering')
            except StudioError as error:
                self.update(identifier, status='partial', phase='story-ready', error=str(error))
        except Exception as error:
            message = str(error) if isinstance(error, (StudioError, ValueError)) else 'Story preparation failed. Saved investigations and stories remain available.'
            self.update(identifier, status='failed', phase='failed', error=message[:600])
        finally:
            self.flags.pop(identifier, None)
