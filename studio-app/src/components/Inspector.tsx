import { useEffect, useMemo, useState } from 'react';
import { api, ApiError, uid } from '../api';
import { compatibility, effectiveStudy } from '../lib/graph';
import { useStudio } from '../store';
import type { Binding, Card, Connection } from '../types';
import { JarvisPanel } from './JarvisPanel';
import { FactTable, CardBody } from './CardBody';

const DEFAULT_OPERATIONS = ['replay', 'research', 'calendar', 'harmonized', 'persistence', 'missingness', 'compare', 'sensitivity', 'exposure', 'validation', 'method', 'sources', 'observations', 'availability', 'archive_search'];
const toBase64 = (buffer: ArrayBuffer) => { let binary = ''; const bytes = new Uint8Array(buffer); for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000)); return btoa(binary); };
const stateLabel = (doc: { state: { cards: Record<string, Card> } }, id: string) => doc.state.cards[id]?.title || id;

function Links({ card }: { card: Card }) {
  const { doc, transact, canEdit, notify } = useStudio();
  const state = doc!.state;
  const [target, setTarget] = useState('');
  const [kind, setKind] = useState<Connection['kind']>('context');
  const others = state.order.filter((id) => id !== card.id);
  const snapshots = doc!.snapshots || {};
  const reasons = useMemo(() => (target && state.cards[target] ? compatibility(card, state.cards[target], kind, state, snapshots) : []), [card, target, kind, state, snapshots]);
  const mine = Object.values(state.connections).filter((c) => c.source === card.id || c.target === card.id);
  return (
    <section aria-labelledby="links-title">
      <h3 id="links-title">Linked cards</h3>
      {mine.length ? <ul style={{ paddingLeft: 18, margin: '0 0 8px' }}>{mine.map((c) => (
        <li key={c.id}>{c.kind}: {state.cards[c.source]?.title || c.source} → {state.cards[c.target]?.title || c.target}{' '}
          {canEdit ? <button type="button" className="btn small" onClick={() => transact([{ op: 'disconnect', id: c.id }])}>Unlink</button> : null}</li>))}</ul> : <p className="muted">No links. Links share a study, a scale or a comparison between compatible cards.</p>}
      {canEdit && others.length ? (
        <div>
          <div className="row">
            <label className="field" style={{ flex: 1, margin: 0 }}>Link to
              <select value={target} onChange={(e) => setTarget(e.target.value)}><option value="">Choose a card…</option>{others.map((id) => <option key={id} value={id}>{state.cards[id].title || id}</option>)}</select></label>
            <label className="field" style={{ margin: 0 }}>Kind
              <select value={kind} onChange={(e) => setKind(e.target.value as Connection['kind'])}><option value="context">Context</option><option value="scale">Shared scale</option><option value="compare">Comparison</option></select></label>
          </div>
          {reasons.length ? <div className="banner warn" role="status" style={{ margin: '8px 0 0' }}>Not compatible: {reasons.join(' ')}</div> : null}
          <button type="button" className="btn small" style={{ marginTop: 8 }} disabled={!target || reasons.length > 0}
            onClick={async () => { const done = await transact([{ op: 'connect', connection: { id: uid('link'), source: card.id, target, kind } }]); if (done) { notify('Linked.'); setTarget(''); } }}>Link cards</button>
        </div>
      ) : null}
    </section>
  );
}

export function Inspector() {
  const { doc, caps, selected, transact, canEdit, notify, reports, loadReport, addSnapshot, select, isCurrent } = useStudio();
  const card = selected && doc ? doc.state.cards[selected] : null;
  const [title, setTitle] = useState('');
  const [text, setText] = useState('');
  const [operation, setOperation] = useState('');
  const [args, setArgs] = useState('{}');
  const [path, setPath] = useState('');
  const [working, setWorking] = useState(false);
  const [license, setLicense] = useState('');
  const [attribution, setAttribution] = useState('');

  useEffect(() => {
    setTitle(card?.title ?? ''); setText(card?.text ?? '');
    setOperation(card?.binding?.operation ?? ''); setArgs(JSON.stringify(card?.binding?.arguments ?? {}, null, 0)); setPath(card?.binding?.path ?? '');
  }, [card?.id, card?.title, card?.text, card?.binding]);
  useEffect(() => { if (card?.snapshot_id) void loadReport(card.snapshot_id); }, [card?.snapshot_id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!doc) return null;
  if (!card) return <aside className="panel" aria-label="Inspector" tabIndex={-1}><h2>Inspector</h2><p className="muted">Select a card to edit its text, bind it to evidence, or link it to another card.</p><JarvisPanel key={doc.id} /></aside>;

  const editable = canEdit && !card.locked;
  const snapshot = card.snapshot_id ? doc.snapshots?.[card.snapshot_id] ?? null : null;
  const report = card.snapshot_id ? reports[card.snapshot_id] : undefined;
  const operations = (caps?.operations?.length ? caps.operations : DEFAULT_OPERATIONS).slice().sort();
  const evidenceType = ['chart', 'map', 'timeline', 'calendar', 'finding', 'observation', 'table', 'source-evidence', 'method-note', 'chapter-frame'].includes(card.type);
  const patch = (fields: Partial<Card>) => transact([{ op: 'update_card', id: card.id, patch: fields }]);

  const freeze = async () => {
    let parsed: Record<string, unknown> = {};
    try { parsed = args.trim() ? JSON.parse(args) : {}; if (typeof parsed !== 'object' || Array.isArray(parsed) || parsed === null) throw new Error(); } catch { notify('Arguments must be a JSON object, for example {"limit": 5}.'); return; }
    if (!operation) { notify('Choose a scientific operation first.'); return; }
    const binding: Binding = { operation, context: effectiveStudy(card, doc.state).context || {}, arguments: parsed, ...(path ? { path } : {}) };
    setWorking(true);
    try {
      const { snapshot: frozen } = await api.resolveBinding(doc.id, binding);
      if (!isCurrent(doc.id, doc.context_revision)) return;
      addSnapshot(frozen);
      const done = await transact([{ op: 'update_card', id: card.id, patch: { binding, snapshot_id: frozen.id } }]);
      if (done) notify('Evidence frozen. The card now cites an immutable snapshot.');
    } catch (error) { notify(error instanceof ApiError ? error.message : 'Evidence could not be resolved.'); } finally { setWorking(false); }
  };

  const upload = async (file: File | undefined) => {
    if (!file) return;
    if (license.trim().length < 2 || attribution.trim().length < 2) { notify('Enter the license and attribution before choosing an image.'); return; }
    if (file.size > 1_500_000) { notify('Images are limited to 1.5 MB.'); return; }
    try {
      const asset = await api.uploadAsset(doc.id, toBase64(await file.arrayBuffer()), license.trim(), attribution.trim());
      if (!isCurrent(doc.id, doc.context_revision)) return;
      await patch({ asset_id: asset.id, provenance: { ...card.provenance, license: license.trim(), attribution: attribution.trim(), sha256: asset.sha256 } });
    } catch (error) { notify(error instanceof ApiError ? error.message : 'Upload failed.'); }
  };

  return (
    <aside className="panel" aria-label="Inspector" tabIndex={-1}>
      <JarvisPanel key={doc.id} />
      <div className="row" style={{ justifyContent: 'space-between' }}><h2>{card.type.replace('-', ' ')} card</h2><button type="button" className="btn small" onClick={() => select(null)}>Close</button></div>
      <label className="field">Title<input value={title} maxLength={120} disabled={!editable} onChange={(e) => setTitle(e.target.value)} onBlur={() => title !== card.title && patch({ title })} /></label>
      {['text', 'quote', 'note-question', 'finding', 'method-note', 'chapter-frame', 'chart', 'map', 'timeline', 'calendar', 'table', 'source-evidence', 'observation'].includes(card.type) ? (
        <label className="field">{card.type === 'quote' ? 'Quote' : 'Text'}<textarea value={text} maxLength={4000} disabled={!editable} onChange={(e) => setText(e.target.value)} onBlur={() => text !== card.text && patch({ text })} /></label>
      ) : null}

      {evidenceType ? (
        <section aria-labelledby="evidence-title">
          <h3 id="evidence-title">Evidence</h3>
          <label className="field">Scientific operation
            <select value={operation} disabled={!editable} onChange={(e) => setOperation(e.target.value)}><option value="">Choose…</option>{operations.map((o) => <option key={o} value={o}>{o}</option>)}</select></label>
          <label className="field">Arguments (JSON, optional)<input value={args} disabled={!editable} onChange={(e) => setArgs(e.target.value)} spellCheck={false} /></label>
          <label className="field">Cited value path (optional)<input value={path} disabled={!editable} placeholder="/overlap/jaccard" onChange={(e) => setPath(e.target.value)} spellCheck={false} /></label>
          <button type="button" className="btn primary" disabled={!editable || working || !operation} onClick={freeze}>{working ? 'Resolving…' : snapshot ? 'Refreeze evidence' : 'Freeze evidence'}</button>
          <p className="muted">Runs the same calculation as Investigate and Research Lab against this board’s study, then stores an immutable, cited snapshot.</p>
          {snapshot ? (
            <div>
              <div className="row" style={{ margin: '8px 0' }}>
                {report ? <span className={`chip ${report.verification.verified ? 'ok' : 'bad'}`}>{report.verification.verified ? 'Receipt verified' : 'Receipt mismatch'}</span> : <span className="chip off">Checking receipt…</span>}
                {report ? <span className={`chip ${report.freshness.fresh ? 'ok' : 'warn'}`} title={report.freshness.note}>{report.freshness.fresh ? 'Current release' : 'Older release'}</span> : null}
                <span className="chip off">{snapshot.unit}</span>
              </div>
              {report && !report.verification.verified ? <div className="banner error">{report.verification.problems.join(' ')}</div> : null}
              {report && !report.freshness.fresh ? <p className="muted">{report.freshness.note}</p> : null}
              <FactTable facts={snapshot.facts} />
              <p className="muted">Method <span className="code">{snapshot.method.id}</span><br />Receipt <span className="code">{snapshot.receipt_sha256.slice(0, 16)}…</span><br />Release <span className="code">{snapshot.release_id.slice(0, 16)}…</span></p>
              {snapshot.limitations.length ? <ul className="muted" style={{ paddingLeft: 18 }}>{snapshot.limitations.map((l) => <li key={l}>{l}</li>)}</ul> : null}
            </div>
          ) : null}
        </section>
      ) : null}

      {card.type === 'map' && snapshot ? <details><summary>Inspect selected map</summary><CardBody card={card} snapshot={snapshot} documentId={doc.id} details={false} /></details> : null}
      {card.type === 'image' ? (
        <section aria-labelledby="image-title">
          <h3 id="image-title">Image</h3>
          <label className="field">License<input value={license} placeholder="e.g. CC BY 4.0, public domain" disabled={!editable} onChange={(e) => setLicense(e.target.value)} /></label>
          <label className="field">Attribution<input value={attribution} placeholder="Creator and source" disabled={!editable} onChange={(e) => setAttribution(e.target.value)} /></label>
          <label className="field">PNG, JPEG or WebP, up to 1.5 MB<input type="file" accept="image/png,image/jpeg,image/webp" disabled={!editable} onChange={(e) => void upload(e.target.files?.[0])} /></label>
          {card.provenance?.attribution ? <p className="muted">{String(card.provenance.license)} · {String(card.provenance.attribution)}</p> : null}
        </section>
      ) : null}

      <section aria-labelledby="follow-title">
        <h3 id="follow-title">Study</h3>
        <label className="field">This card follows
          <select value={card.follow} disabled={!editable} onChange={(e) => patch(e.target.value === 'pinned' ? { follow: 'pinned', pinned_study: doc.state.study, follow_card_id: null } : e.target.value === 'selected' ? { follow: 'selected', follow_card_id: doc.selection.card_id || null, pinned_study: null } : { follow: 'board', pinned_study: null, follow_card_id: null })}>
            <option value="board">The board study</option><option value="pinned">A pinned copy of the current study</option></select></label>
        <label className="field">Follow another card<select value={card.follow === 'selected' ? card.follow_card_id || '' : ''} disabled={!editable} onChange={(e) => patch(e.target.value ? { follow: 'selected', follow_card_id: e.target.value, pinned_study: null } : { follow: 'board', follow_card_id: null, pinned_study: null })}><option value="">Use study mode above</option>{doc.state.order.filter((id) => id !== card.id).map((id) => <option value={id} key={id}>{stateLabel(doc, id)}</option>)}</select></label>
        {card.follow === 'selected' ? <p className="muted">Source card: {card.follow_card_id ? stateLabel(doc, card.follow_card_id) : 'select a source card before saving this mode.'}</p> : null}
      </section>
      {canEdit ? <div className="row"><button type="button" className="btn" onClick={() => patch({ locked: !card.locked })}>{card.locked ? 'Unlock card' : 'Lock card'}</button><button type="button" className="btn" disabled={card.locked} onClick={() => transact([{ op: 'add_card', card: { ...card, id: uid('card'), title: `${card.title} copy`.slice(0, 120), transform: { ...card.transform, x: card.transform.x + 32, y: card.transform.y + 32 } } }])}>Duplicate card</button></div> : null}
      {!card.locked ? <Links card={card} /> : <p className="muted">Unlock this card before changing it.</p>}
      {editable ? <button type="button" className="btn danger" style={{ marginTop: 12 }} onClick={async () => { if (window.confirm('Remove this card and its links?')) { await transact([{ op: 'remove_card', id: card.id }]); select(null); } }}>Remove card</button> : null}
    </aside>
  );
}
