import { useState } from 'react';
import { buildPresentation, PRESENTATIONS } from '../lib/presentation';
import { useStudio } from '../store';
import type { DocumentView } from '../types';

export function PresentationPresets({ opened, navigate }: { opened: (doc: DocumentView) => void; navigate: (tab: 'board' | 'story' | 'workflow') => void }) {
  const { doc, open, isCurrent, canEdit, notify } = useStudio();
  const [busy, setBusy] = useState<string | null>(null);
  const [status, setStatus] = useState('Choose a curated study. Each selection creates its own saved board and keeps your current work.');
  const [readyId, setReadyId] = useState<string | null>(null);
  const ready = readyId === doc?.id;
  return <section className="presentation-presets" aria-label="Presentation presets">
    <div className="preset-heading"><div><span className="st-eyebrow">PRESENTATION COLLECTION</span><h2>A study, ready to walk through</h2><p>Two sensor heat maps. Connected evidence. A story you can explain.</p></div><span className="chip off">Stored observations · no model required</span></div>
    <div className="preset-gallery">{PRESENTATIONS.map((preset, index) => <button className={`preset-option ${preset.tone}`} key={preset.id} disabled={Boolean(busy) || !canEdit} onClick={async () => {
      setBusy(preset.id); setReadyId(null);
      try { const board = await buildPresentation(preset.id, { open: (next) => { open(next); opened(next); navigate('board'); }, current: isCurrent, progress: setStatus }); opened(board); setReadyId(board.id); notify('Presentation preset prepared. The workflow is saved; execution and exports remain explicit.'); }
      catch (error) { setStatus(error instanceof Error ? error.message : 'Preset preparation failed. Its saved draft remains inspectable.'); }
      finally { setBusy(null); }
    }}><span className="preset-number">0{index + 1}</span><span className="st-eyebrow">{preset.eyebrow}</span><strong>{preset.title}</strong><span>{preset.description}</span><span className="preset-route" aria-hidden="true">MAPS <i>→</i> EVIDENCE <i>→</i> STORY</span><span className="preset-open">{busy === preset.id ? 'Preparing frozen evidence…' : `Open presentation · ${preset.duration} seconds`}</span></button>)}</div>
    <p role="status" className="preset-status">{status}</p>
    {ready ? <div className="row"><button className="btn primary" onClick={() => navigate('board')}>1 · Inspect linked heat maps</button><button className="btn" onClick={() => navigate('workflow')}>2 · See the workflow</button><button className="btn" onClick={() => navigate('story')}>3 · Play the curated story</button></div> : null}
  </section>;
}
