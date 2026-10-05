import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useStudio } from '../store';
import type { RoomView } from '../types';
import type { Presence } from '../lib/collaboration';
import type { SharedLayout } from '../lib/sharedLayout';

export function RoomPanel({ expanded }: { expanded: boolean }) {
  const { doc, caps, selected, select, open, isCurrent, busy, conflict, notify, canEdit, setSharedGeometry, registerLayoutBridge } = useStudio();
  const layout = useRef<SharedLayout | null>(null);
  const [layoutMode, setLayoutMode] = useState(false);
  const [layoutReady, setLayoutReady] = useState(false);
  const [room, setRoom] = useState<RoomView | null>(null);
  const [status, setStatus] = useState('Shared rooms need configured Liveblocks authorization. Single-user authoring remains available.');
  const [others, setOthers] = useState<{ user: string; presence: Presence }[]>([]);
  const [inviteRole, setInviteRole] = useState<'editor' | 'viewer'>('viewer');
  const [invite, setInvite] = useState(''); const [join, setJoin] = useState('');
  const [comments, setComments] = useState<{ id: string; body: string; author: string; card_id: string | null; chapter?: { chapter_id: string; story_id: string; story_revision: number } | null }[]>([]);
  const [commentTarget, setCommentTarget] = useState('card');
  const [draft, setDraft] = useState(''); const [follow, setFollow] = useState(false);
  const [chapterState, setChapterState] = useState<{ chapter_id: string; story_id: string; story_revision: number } | null>(null);
  const transport = useRef<Awaited<ReturnType<typeof import('../lib/collaboration')['connectRoom']>> | null>(null);
  const state = useRef({ doc, busy, conflict, follow }); state.current = { doc, busy, conflict, follow };
  const presenterEpoch = useRef(0); const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { setRoom(doc?.room || null); presenterEpoch.current = 0; setInvite(''); setComments([]); setLayoutMode(false); setLayoutReady(false); setChapterState(null); setCommentTarget('card'); }, [doc?.id, doc?.room?.id]);
  useEffect(() => {
    if (!room) return;
    let live = true; let refreshing = false; const id = room.document_id;
    const refresh = async () => {
      if (!live || refreshing || !isCurrent(id)) return;
      refreshing = true;
      try {
        const fresh = await api.getDocument(id);
        const latest = state.current;
        if (live && isCurrent(id) && !latest.busy && !latest.conflict && !(document.activeElement as HTMLElement)?.matches('input,textarea,select,[contenteditable=true]') && fresh.revision > (latest.doc?.revision || 0)) open(fresh);
        // The explicit conflict path retains edits; background synchronization never overwrites them.
        const lines = await api.comments(room.id); if (live) setComments(lines.comments);
        const present = await api.presenter(room.id, presenterEpoch.current);
        if (live && present.changed) {
          presenterEpoch.current = present.epoch;
          if (state.current.follow) {
            const card = present.state.card_id;
            if (typeof card === 'string' && state.current.doc?.state.cards[card]) select(card);
            window.dispatchEvent(new CustomEvent('fireatlas-studio-presenter', { detail: present.state }));
          }
        }
      } catch (error) { if (live) setStatus(error instanceof Error ? error.message : 'Room refresh failed; saved edits remain usable.'); }
      finally { refreshing = false; }
    };
    if (room.adapter === 'liveblocks') {
      void import('../lib/collaboration').then(async ({ connectRoom }) => {
        if (!live) return;
        const connection = await connectRoom(room.id, () => api.authorizeRoom(room.id), {
          status: (value) => { if (live) setStatus('Liveblocks: ' + value); },
          others: (value) => { if (live) setOthers(value); },
          layout: (next) => { if (live && isCurrent(id)) { layout.current = next; setLayoutReady(true); const current = state.current.doc; if (current) setSharedGeometry(id, next.transforms(current)); } }, changed: () => { void refresh(); }
        });
        if (!live) connection.close(); else { transport.current = connection; if (state.current.doc) connection.reconcile(state.current.doc, canEdit); }
      }).catch((error) => { if (live) setStatus(String(error)); });
    } else {
      setStatus('Loopback room: local development only.');
    }
    void refresh();
    const poll = window.setInterval(() => {
      void refresh();
      if (room.adapter === 'loopback') void api.heartbeat(room.id).then((result) => { if (live) setOthers(result.presence.map((p) => ({ user: p.principal, presence: { card: null, cursor: null, chapter: null } }))); }).catch(() => undefined);
    }, 3000);
    const cursor = (event: PointerEvent) => transport.current?.presence({ cursor: { x: Math.round(event.clientX / window.innerWidth * 1000), y: Math.round(event.clientY / window.innerHeight * 1000) } });
    let lastPointer = 0;
    const pointer = (event: PointerEvent) => { if (event.timeStamp - lastPointer >= 80) { lastPointer = event.timeStamp; cursor(event); } };
    const chapter = (event: Event) => { const value = (event as CustomEvent).detail; setChapterState(value); transport.current?.presence({ chapter: value.chapter_id }); };
    window.addEventListener('pointermove', pointer); window.addEventListener('fireatlas-studio-chapter', chapter);
    return () => { live = false; layout.current = null; setSharedGeometry(id, {}); registerLayoutBridge(null); window.clearInterval(poll); transport.current?.close(); transport.current = null; window.removeEventListener('pointermove', pointer); window.removeEventListener('fireatlas-studio-chapter', chapter); };
  }, [room?.id, isCurrent, open, select, setSharedGeometry, registerLayoutBridge]);
  useEffect(() => { transport.current?.presence({ card: selected }); if (doc) { transport.current?.changed(doc.id, doc.revision, canEdit); transport.current?.reconcile(doc, canEdit); if (layout.current) setSharedGeometry(doc.id, layout.current.transforms(doc)); } }, [doc?.revision, selected, canEdit, setSharedGeometry]);
  useEffect(() => { registerLayoutBridge(layoutMode && canEdit && layoutReady ? layout.current : null); return () => registerLayoutBridge(null); }, [layoutMode, canEdit, layoutReady, registerLayoutBridge]);
  const act = async (action: () => Promise<void>) => { try { await action(); } catch (error) { if (mounted.current) setStatus(error instanceof Error ? error.message : 'The room action failed.'); } };
  if (!doc) return null;
  if (!expanded && !room) return null;
  const owner = room?.members.some((member) => member.you && member.role === 'owner');
  return <section className="panel room-panel" aria-label="Shared room" style={{ margin: '12px clamp(16px,4vw,40px)' }}>
    <div className="row"><h2>Shared room</h2><span role="status">{status}</span>{room ? <label><input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> Follow presenter</label> : null}</div>
    {room ? <div className="row"><span>{room.members.length} authorized members</span>{others.map((other) => <span className="chip off" key={other.user}>{other.user}: {other.presence.card ? doc.state.cards[other.presence.card]?.title || 'selected evidence' : 'viewing'}</span>)}{canEdit ? <button className="btn small" onClick={() => void act(async () => { await api.present(room.id, { card_id: selected, viewer_state: 'board' }, presenterEpoch.current); notify('Presenter selection published. Followers keep their own scientific evidence.'); })}>Present selected card</button> : null}</div> : null}
    {room && canEdit && chapterState ? <button className="btn small" onClick={() => void act(async () => { await api.present(room.id, { scene: chapterState.chapter_id, story_id: chapterState.story_id, story_revision: chapterState.story_revision, viewer_state: 'story', playing: false }, presenterEpoch.current); notify('Saved chapter published. Followers must open this same story revision.'); })}>Present saved chapter</button> : null}
    {room?.adapter === 'liveblocks' ? <div className="panel" aria-label="Shared layout draft">
      <p>Canvas layout is a shared draft. Moves and resizes merge by coordinate through Liveblocks; the saved story and scientific receipts stay fixed until you save.</p>
      {canEdit ? <label><input type="checkbox" checked={layoutMode} disabled={!layoutReady} onChange={(e) => setLayoutMode(e.target.checked)} /> Edit shared layout draft</label> : <p>Read-only view of the merged layout draft.</p>}
      <button className="btn" disabled={!canEdit || !layoutReady || busy || Boolean(conflict)} onClick={() => void act(async () => {
        const id = doc.id, shared = layout.current;
        if (!shared) return;
        const fresh = await api.getDocument(id);
        if (!isCurrent(id)) return;
        const ops = shared.projection(fresh);
        if (!ops.length) { shared.reconcile(fresh, canEdit); setSharedGeometry(id, shared.transforms(fresh)); setStatus('No unsaved shared layout changes.'); return; }
        const saved = await api.transact(id, fresh.revision, ops);
        if (!isCurrent(id)) return;
        shared.checkpoint(); shared.reconcile(saved, canEdit); open(saved); setSharedGeometry(id, shared.transforms(saved));
        setStatus('Merged layout saved as one reversible document transaction.');
      })}>Save merged layout</button>
      <p className="muted">Undo/redo affects your layout draft while its edit mode is enabled. Leave that mode to undo saved document transactions. Card content, links and groups use checked document edits.</p>
    </div> : null}
    {expanded ? <>
      {!room ? <div className="row"><button className="btn primary" disabled={!caps?.collaboration?.available || !doc.owner} onClick={() => void act(async () => { const next = await api.createRoom(doc.id); if (isCurrent(doc.id)) setRoom(next); })}>Open collaboration room</button><label className="field">Private one-use invite<input value={join} onChange={(e) => setJoin(e.target.value)} autoComplete="off" /></label><button className="btn" disabled={!join.trim()} onClick={() => void act(async () => { const joined = await api.redeem(join.trim()); const next = await api.getDocument(joined.document_id); if (!mounted.current) return; open(next); setRoom(await api.getRoom(joined.room_id)); setJoin(''); window.history.replaceState(null, '', window.location.pathname); sessionStorage.setItem('fireatlas-studio-board', next.id); })}>Join room</button></div> : <>
        <ul>{room.members.map((member) => <li key={member.principal}>{member.you ? 'You' : member.principal}: {member.role}</li>)}</ul>
        {owner ? <div className="row"><label>Invite role<select value={inviteRole} onChange={(e) => setInviteRole(e.target.value as 'editor' | 'viewer')}><option value="viewer">Viewer — read only</option><option value="editor">Editor — edit presentation</option></select></label><button className="btn" onClick={() => void act(async () => { const next = await api.invite(room.id, inviteRole); setInvite(next.token); })}>Create private invite</button>{invite ? <textarea aria-label="One-use private invite" readOnly value={invite} /> : null}</div> : null}
        <h3>Evidence comments</h3>{comments.map((comment) => <p key={comment.id}><strong>{comment.author}</strong> {comment.body}{comment.card_id ? ` · ${doc.state.cards[comment.card_id]?.title || 'removed card'}` : comment.chapter ? ` · ${comment.chapter.chapter_id}, saved story revision ${comment.chapter.story_revision}` : ''}</p>)}
        {canEdit ? <><label className="field">Attach comment to<select value={commentTarget} onChange={(e) => setCommentTarget(e.target.value)}><option value="card">Selected card</option>{chapterState ? <option value="chapter">Current saved chapter</option> : null}</select></label><label className="field">Comment<textarea value={draft} maxLength={1000} onChange={(e) => setDraft(e.target.value)} /></label><button className="btn" disabled={!draft.trim()} onClick={() => void act(async () => { await api.comment(room.id, draft, commentTarget === 'chapter' ? null : selected, commentTarget === 'chapter' ? chapterState : null); setDraft(''); setComments((await api.comments(room.id)).comments); })}>Save comment</button></> : <p>Viewer role is read only. Comments require an editor invite.</p>}
      </>}
      <p className="muted">The server validates roles and revision-checked edits. Liveblocks carries presence, revision hints and presentation coordinates; it receives no scientific rows or provider credentials. Reconnecting reloads the saved board. Conflicting edits stay available for explicit retry.</p>
    </> : null}
    {room && !expanded ? others.filter((p) => p.presence.cursor).map((p) => <span key={p.user} className="room-cursor" style={{ position: 'fixed', pointerEvents: 'none', zIndex: 80, left: `${p.presence.cursor!.x / 10}%`, top: `${p.presence.cursor!.y / 10}%` }}>↖ {p.user}</span>) : null}
  </section>;
}
