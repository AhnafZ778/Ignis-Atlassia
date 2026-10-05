import { InvestigationActions } from './components/InvestigationActions';
import { PresentationPresets } from './components/PresentationPresets';
import { Component, lazy, Suspense, useEffect, useMemo, useState, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { api, ApiError, uid } from './api';
import { Board } from './components/Board';
import { BoardTools } from './components/BoardTools';
import { Inspector } from './components/Inspector';
import { StoryDirector } from './components/StoryDirector';
import { Outline } from './components/Outline';
import { RoomPanel } from './components/RoomPanel';
import { StudyPanel } from './components/StudyPanel';
import { StudioProvider, useStudio } from './store';
import { CARD_TYPES, type CardType, type Study } from './types';
import './styles.css';

function studyFromLocation(): Study | undefined {
  const params = new URLSearchParams(window.location.search);
  const keys = ['region', 'case', 'year', 'month', 'start', 'end', 'as_of', 'day', 'series', 'metric', 'view', 'scale', 'distance_km', 'gap_days', 'layer', 'source', 'bbox'];
  const uiKeys = ['calendar_metric', 'method_id', 'unit', 'release_id', 'result_sha256', 'analysis_month', 'origin_route'];
  const context: Record<string, unknown> = {};
  for (const key of keys) {
    const value = params.get(key);
    if (value == null || value === '') continue;
    if (['year', 'month', 'distance_km', 'gap_days', 'origin_year', 'origin_month'].includes(key)) {
      const number = Number(value);
      if (Number.isFinite(number)) context[key] = number;
    } else if (key === 'bbox') {
      const numbers = value.split(',').map(Number);
      context[key] = numbers.length === 4 && numbers.every(Number.isFinite) ? numbers : value;
    } else context[key] = value;
  }
  const ui: Record<string, string> = { origin: 'analytical-handoff' };
  for (const key of uiKeys) {
    const value = params.get(key);
    if (value != null && value !== '') ui[key] = value;
  }
  if (!Object.keys(context).length) return undefined;
  return { context, ui };
}

type Tab = 'board' | 'outline' | 'story' | 'workflow' | 'room';
const TldrawBoard = lazy(() => import('./components/TldrawBoard').then((module) => ({ default: module.TldrawBoard })));
const WorkflowPanel = lazy(() => import('./components/WorkflowPanel').then((module) => ({ default: module.WorkflowPanel })));
class CanvasBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <><p role="alert">The licensed canvas could not initialize. The saved evidence board and linear outline remain usable.</p><Board /></> : this.props.children; }
}

const defaultCard = (type: CardType, index: number) => ({
  id: uid('card'), type, title: CARD_TYPES.find((item) => item.type === type)?.label || type,
  text: '', binding: null, snapshot_id: null, asset_id: null, display: {}, provenance: {}, locked: false,
  transform: { x: 40 + (index % 3) * 390, y: 40 + Math.floor(index / 3) * 280, w: 360, h: 240 },
  follow: 'board' as const, pinned_study: null
});

function CapabilityChips() {
  const { caps } = useStudio();
  if (!caps) return null;
  const items = [
    ['canvas', caps.canvas?.active === 'tldraw' ? 'Canvas ready' : 'Outline fallback'],
    ['workflow', caps.workflow?.active === 'react-flow' ? 'Workflow editor ready' : 'Workflow fallback'],
    ['video', caps.video?.available ? 'Video ready' : 'Video unavailable'],
    ['collaboration', caps.collaboration?.available ? 'Rooms ready' : 'Rooms unavailable']
  ];
  return <div className="chips" aria-label="Studio capabilities">{items.map(([key, label]) => {
    const state = (caps as unknown as Record<string, { available?: boolean }>)[key];
    return <span className={`chip ${state?.available === false ? 'warn' : 'ok'}`} key={key}>{label}</span>;
  })}</div>;
}

function Library() {
  const { doc, transact, canEdit, notify } = useStudio();
  if (!doc) return null;
  return <aside className="panel" aria-label="Card library">
    <h2>Add evidence card</h2>
    <p className="muted">Cards are bounded views over checked scientific results. Freeze evidence in the inspector before citing it in a story.</p>
    <div className="palette">
      {CARD_TYPES.map((item) => <button key={item.type} type="button" disabled={!canEdit || doc.state.order.length >= 100} onClick={async () => {
        const card = defaultCard(item.type, doc.state.order.length);
        const result = await transact([{ op: 'add_card', card }]);
        if (result) notify(`${item.label} card added.`);
      }}><strong>{item.label}</strong><span>{item.hint}</span></button>)}
    </div>
    <div className="row" style={{ marginTop: 10 }}><TemplateButton /><span className="muted">{doc.state.order.length}/100 cards · one study context · UTC evidence</span></div>
  </aside>;
}

function TemplateButton() {
  const { doc, notify, open, isCurrent, canEdit } = useStudio();
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState('');
  if (!doc) return null;
  return <button className="btn primary" type="button" disabled={busy || !canEdit || doc.state.order.length > 0} onClick={async () => {
    setBusy(true);
    try {
      const result = await api.studioAction(doc.id, { action: 'build_investigation', base_revision: doc.revision });
      if (!result.document || !isCurrent(doc.id)) return;
      open(result.document);
      const board = result.document;
      const snapshots = new Map<string, string>();
      const patches = [];
      const unavailable: string[] = [];
      for (const id of board.state.order) {
        const card = board.state.cards[id];
        if (!card.binding) continue;
        if (!isCurrent(board.id, board.context_revision)) return;
        setProgress(`Preparing ${card.title}…`);
        const signature = JSON.stringify(card.binding);
        let sid = snapshots.get(signature);
        if (!sid) {
          try { const evidence = await api.resolveBinding(board.id, card.binding); sid = evidence.snapshot.id; snapshots.set(signature, sid); }
          catch (error) { unavailable.push(`${card.title}: ${error instanceof Error ? error.message : 'Evidence unavailable'}`); continue; }
        }
        patches.push({ op: 'update_card', id, patch: { snapshot_id: sid } });
      }
      if (!isCurrent(board.id, board.context_revision)) return;
      if (patches.length) await api.transact(board.id, board.revision, patches, { group_id: 'studio-template-evidence' });
      const fresh = await api.getDocument(board.id);
      if (!isCurrent(board.id, board.context_revision)) return;
      open(fresh);
      notify(unavailable.length ? `Supported evidence frozen. Detail needs an explicit narrower scope: ${unavailable.join('; ')}` : 'Investigation ready with frozen scientific evidence.');
    } catch (error) { notify(error instanceof ApiError ? error.message : 'The board template could not be created.'); }
    finally { setBusy(false); }
  }}>{busy ? progress || 'Building…' : 'Build from current study'}</button>;
}

function App() {
  const { doc, caps, open, setCaps, undo, redo, busy, conflict, resolveConflict, transact, notice } = useStudio();
  const [tab, setTab] = useState<Tab>('board');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [boards, setBoards] = useState<{ id: string; title: string }[]>([]);
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        if (document.querySelector('meta[name="fireatlas-static-data"]')) throw new Error("Studio authoring needs the local Python service. This static release supports named investigations and portable exported story readers.");
        await api.ensurePrincipal();
        const capability = await api.capabilities();
        const listed = await api.listDocuments();
        const incoming = studyFromLocation();
        const handoffKey = incoming ? JSON.stringify(incoming) : null;
        const savedHandoff = sessionStorage.getItem('fireatlas-studio-handoff');
        const handoffBoard = sessionStorage.getItem('fireatlas-studio-handoff-board');
        const previousId = sessionStorage.getItem('fireatlas-studio-board');
        const recent = listed.documents.find((board) => board.id === previousId) || listed.documents[0];
        // An explicit analytical handoff creates a board for that scope; it
        // must never be replaced by another private board's saved context.
        const handoff = listed.documents.find((board) => board.id === handoffBoard);
        const requestedBoard = new URLSearchParams(location.search).get('board');
        let current = requestedBoard ? await api.getDocument(requestedBoard) : incoming ? (handoff && handoffKey === savedHandoff ? await api.getDocument(handoff.id) : null) : (recent ? await api.getDocument(recent.id) : null);
        if (!current) {
          const study = incoming;
          const label = study?.context?.case || study?.context?.region ? `Research Studio · ${String(study.context.case || study.context.region)}` : 'Research Studio board';
          current = await api.createDocument(label, study);
        }
        if (active) { setCaps(capability); open(current); setBoards([{ id: current.id, title: current.title }, ...listed.documents.filter((board) => board.id !== current!.id)]); sessionStorage.setItem('fireatlas-studio-board', current.id); if (handoffKey) { sessionStorage.setItem('fireatlas-studio-handoff', handoffKey); sessionStorage.setItem('fireatlas-studio-handoff-board', current.id); } }
      } catch (reason) { if (active) setError(reason instanceof Error ? reason.message : 'Studio could not start.'); }
      finally { if (active) setLoading(false); }
    })();
    return () => { active = false; };
  }, [open, setCaps]);
  const title = doc?.title || 'Research Studio';
  const rename = (value: string) => { if (doc && value.trim() && value !== doc.title) void transact([{ op: 'set_title', title: value.trim() }]); };
  const changeBoard = async (id: string) => { setLoading(true); try { const next = await api.getDocument(id); open(next); sessionStorage.setItem('fireatlas-studio-board', id); setTab('board'); } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not open the board.'); } finally { setLoading(false); } };
  const createBoard = async (study?: Study) => { setLoading(true); try { const next = await api.createDocument(study?.context?.case === 'park-2024' ? 'Park investigation' : 'Untitled investigation', study); open(next); setBoards((all) => [{ id: next.id, title: next.title }, ...all]); sessionStorage.setItem('fireatlas-studio-board', next.id); setTab('board'); } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Could not create the board.'); } finally { setLoading(false); } };
  const tabContent = useMemo(() => {
    if (!doc) return null;
    if (tab === 'outline') return <div className="workspace"><div className="panel"><h2>Linear outline</h2><Outline /></div><Inspector /></div>;
    if (tab === 'story') return <div className="workspace full"><StoryDirector key={doc.id} /></div>;
    if (tab === 'workflow') return <div className="workspace full"><Suspense fallback={<p>Opening Workflow Composer…</p>}><WorkflowPanel key={doc.id} /></Suspense></div>;
    if (tab === 'room') return null;
    return <div className="workspace"><div>{caps?.canvas?.active === 'tldraw' ? <CanvasBoundary key={`canvas:${doc.id}`}><Suspense fallback={<p>Opening the evidence canvas…</p>}><TldrawBoard key={doc.id} /></Suspense></CanvasBoundary> : <Board key={`board:${doc.id}`} />}<BoardTools key={`tools:${doc.id}`} /><div style={{ marginTop: 16 }}><Library /></div></div><Inspector /></div>;
  }, [doc, tab, caps]);
  if (loading) return <div className="studio-app"><p className="noscript">Opening the local Studio workspace…</p></div>;
  if (error) return <div className="studio-app"><div className="banner error"><strong>Studio unavailable.</strong><span>{error}</span><a href="./investigate.html">Return to Investigate</a></div></div>;
  return <div className="studio-app">
    <header className="st-head"><div><span className="st-eyebrow">RESEARCH STUDIO / LOCAL AUTHORING</span><input className="st-title-input" aria-label="Board title" defaultValue={title} key={`${doc?.id}-${doc?.title}`} disabled={!doc || doc.role === 'viewer'} onBlur={(event) => rename(event.currentTarget.value)} /><p className="st-sub">Arrange checked evidence into a reproducible board, story and optional briefing. The underlying scientific calculations remain unchanged.</p></div><div className="st-actions"><a className="btn" href="./investigate.html">Back to Investigate</a><button className="btn" type="button" disabled={!doc || busy} onClick={() => void undo()}>Undo</button><button className="btn" type="button" disabled={!doc || busy} onClick={() => void redo()}>Redo</button><span className="chip off">{busy ? 'Saving…' : `${doc?.role || 'viewer'} · rev ${doc?.revision || 0}`}</span></div></header>
    <CapabilityChips />
    {doc ? <InvestigationActions key={doc.id} /> : null}
    <PresentationPresets opened={(next) => { setBoards((all) => [{ id: next.id, title: next.title }, ...all.filter((b) => b.id !== next.id)]); sessionStorage.setItem('fireatlas-studio-board', next.id); }} navigate={setTab} />
    {notice ? <div className="banner" role="status">{notice}</div> : null}
    <div className="row" style={{ padding: '12px clamp(16px, 4vw, 40px)' }}><label className="field">Saved investigation<select value={doc?.id || ''} disabled={busy} onChange={(e) => void changeBoard(e.target.value)}>{boards.map((board) => <option value={board.id} key={board.id}>{board.id === doc?.id ? title : board.title}</option>)}</select></label><button className="btn" disabled={busy} onClick={() => void createBoard({ context: { case: 'park-2024' } })}>Start from Park</button><button className="btn" disabled={busy} onClick={() => void createBoard(doc?.state.study)}>New board from current study</button><button className="btn" disabled={busy} onClick={() => void createBoard()}>Blank investigation</button><span className="muted">Applied study: {doc?.state.study.context?.case || doc?.state.study.context?.region || 'Custom selection'} · {String(doc?.state.study.context?.start || '')} → {String(doc?.state.study.context?.end || '')} UTC</span></div>
    {conflict ? <div className="banner warn" role="alert"><strong>Board changed elsewhere.</strong><span>{conflict.message}</span><button className="btn small" type="button" onClick={() => void resolveConflict('reload')}>Reload</button><button className="btn small" type="button" onClick={() => void resolveConflict('retry')}>Retry my edit</button></div> : null}
    {doc ? <StudyPanel key={`study:${doc.id}`} /> : null}
    <nav className="tabs" aria-label="Studio views">{(['board', 'outline', 'story', 'workflow', 'room'] as Tab[]).map((value) => <button className="tab" key={value} type="button" aria-pressed={tab === value} onClick={() => setTab(value)}>{value === 'room' ? 'Shared room' : value[0].toUpperCase() + value.slice(1)}</button>)}</nav>
    <RoomPanel key={`room:${doc?.id}`} expanded={tab === 'room'} />
    {tabContent}
    {caps?.static_reader ? <p className="muted" style={{ padding: '16px clamp(16px, 4vw, 40px)' }}>Stories can be exported as static readers with frozen evidence, captions and schematic fallbacks.</p> : null}
  </div>;
}

createRoot(document.getElementById('studio-root')!).render(<StudioProvider><App /></StudioProvider>);
