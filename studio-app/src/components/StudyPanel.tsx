import { useEffect, useState } from 'react';
import { useStudio } from '../store';
import { propagate } from '../lib/graph';
import type { StudyContext } from '../types';

/** Form changes remain drafts; frozen evidence and existing stories are never silently rebound. */
export function StudyPanel() {
  const { doc, canEdit, busy, transact, notify, selected } = useStudio();
  const current = doc!.state.study.context || {};
  const [draft, setDraft] = useState<StudyContext>(current);
  const [bounds, setBounds] = useState(String(Array.isArray(current.bbox) ? current.bbox.join(', ') : current.bbox || ''));
  useEffect(() => { setDraft(current); setBounds(Array.isArray(current.bbox) ? current.bbox.join(', ') : String(current.bbox || '')); }, [doc?.id, doc?.context_revision]);
  const update = (key: string, value: unknown) => setDraft((old) => ({ ...old, [key]: value }));
  return <details className="panel" style={{ margin: '0 clamp(16px,4vw,40px) 12px' }}><summary>Applied study and linked display</summary>
    <div className="row"><label className="field">UTC start<input type="date" value={String(draft.start || '')} disabled={!canEdit || busy} onChange={(e) => update('start', e.target.value)} /></label><label className="field">UTC end<input type="date" value={String(draft.end || '')} disabled={!canEdit || busy} onChange={(e) => update('end', e.target.value)} /></label><label className="field">Selected UTC day<input type="date" value={String(draft.day || '')} disabled={!canEdit || busy} onChange={(e) => update('day', e.target.value)} /></label></div>
    <label className="field">Study boundary: west, south, east, north<input value={bounds} disabled={!canEdit || busy} onChange={(e) => setBounds(e.target.value)} /></label>
    <div className="row"><label className="field">Visible sensor (display selection)<select value={String(draft.source || 'joint')} disabled={!canEdit || busy} onChange={(e) => update('source', e.target.value)}><option value="joint">Both sensors</option><option value="MODIS_SP">MODIS</option><option value="VIIRS_SNPP_SP">VIIRS S-NPP</option></select></label><label className="field">Map statistic<select value={String(draft.metric || 'density')} disabled={!canEdit || busy} onChange={(e) => update('metric', e.target.value)}><option value="density">Occupied-cell heat</option><option value="persistence">Distinct observed UTC dates</option><option value="frp">Single-source peak FRP</option></select></label></div>
    <button className="btn primary" disabled={!canEdit || busy} onClick={async () => {
      const bbox = bounds.split(',').map((v) => Number(v.trim()));
      if (bbox.length !== 4 || bbox.some((v) => !Number.isFinite(v))) { notify('Provide four finite boundary coordinates. The current study remains applied.'); return; }
      const samePreset = JSON.stringify(bbox) === JSON.stringify(current.bbox) && draft.start === current.start && draft.end === current.end;
      const context = { ...draft, bbox, ...(samePreset ? {} : { case: undefined }), year: Number(String(draft.start).slice(0, 4)), month: Number(String(draft.start).slice(5, 7)), as_of: String(draft.end) };
      const applied = await transact([{ op: 'set_study', study: { ...doc!.state.study, context } }]);
      if (applied) notify('Study applied. Frozen cards retain their original evidence; refreeze them explicitly to calculate this scope.');
    }}>Apply study draft</button>
    {selected ? <button className="btn" disabled={!canEdit || busy} onClick={() => {
      const result = propagate(doc!.state, selected, doc!.snapshots);
      const targets = result.reached.filter((id) => id !== selected && !doc!.state.cards[id].locked && doc!.state.cards[id].follow !== 'pinned');
      if (!targets.length) { notify('No compatible unpinned linked cards can follow this selection.'); return; }
      if (targets.length > 50) { notify('Apply at most 50 linked card changes in one transaction. The board remains unchanged.'); return; }
      void transact(targets.map((id) => ({ op: 'update_card', id, patch: { follow: 'selected', follow_card_id: selected, pinned_study: null } }))).then((done) => done && notify(`${targets.length} linked cards now follow the selected card’s study. Frozen receipts remain unchanged.`));
    }}>Apply context to compatible linked cards</button> : null}
    <p className="muted">This is a study boundary, not a detection polygon or camera focus. Research uses its supported month intersection. Harmonized activity requires an exact calibrated regional box. Changing sensor display does not rewrite a harmonized headline or frozen result.</p>
  </details>;
}
