import { useEffect, useId, useRef, useState } from 'react';

export function InvestigationName({ title, disabled, onSave }: { title: string; disabled: boolean; onSave: (title: string) => Promise<boolean> }) {
  const id = useId();
  const [draft, setDraft] = useState(title), [saving, setSaving] = useState(false), [status, setStatus] = useState('');
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { setDraft(title); }, [title]);
  return <form className="investigation-name" onSubmit={async (event) => {
    event.preventDefault(); const name = draft.trim();
    if (!name || name.length > 120) { setStatus('Enter an investigation name of 1–120 characters.'); return; }
    if (disabled || saving || name === title) return;
    setSaving(true); setStatus('Saving investigation name…');
    try { const saved = await onSave(name); if (mounted.current) setStatus(saved ? 'Investigation name saved.' : 'Name was not saved. Your draft is retained; resolve the save conflict or retry.'); }
    catch (error) { if (mounted.current) setStatus(error instanceof Error ? error.message : 'Could not save the name.'); }
    finally { if (mounted.current) setSaving(false); }
  }}>
    <label className="name-label" htmlFor={id}>Investigation name</label>
    <div className="row"><input id={id} className="st-title-input" aria-label="Board title" value={draft} maxLength={120} required disabled={disabled || saving} onChange={(e) => { setDraft(e.target.value); setStatus(''); }} onKeyDown={(e) => { if (e.key === 'Escape') { setDraft(title); setStatus('Name edit cancelled.'); } }} /><button className="btn" type="submit" disabled={disabled || saving || !draft.trim() || draft.trim() === title}>{saving ? 'Saving…' : 'Save name'}</button></div>
    <span className="muted" role="status">{status || (disabled ? 'This investigation is read-only.' : 'Enter a name, then press Enter or Save name.')}</span>
  </form>;
}

export function NewInvestigationDialog({ defaultName, onCreate, onClose }: { defaultName: string; onCreate: (title: string) => Promise<void>; onClose: () => void }) {
  const id = useId(), dialog = useRef<HTMLDialogElement>(null), field = useRef<HTMLInputElement>(null);
  const [name, setName] = useState(defaultName), [working, setWorking] = useState(false), [error, setError] = useState('');
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.showModal(); field.current?.focus(); field.current?.select();
    return () => { dialog.current?.close(); if (previous?.isConnected) previous.focus(); };
  }, []);
  return <dialog ref={dialog} className="new-investigation-dialog" aria-labelledby={id} onCancel={(e) => { e.preventDefault(); if (!working) onClose(); }}>
    <form onSubmit={async (e) => {
      e.preventDefault(); const title = name.trim();
      if (!title || title.length > 120) { setError('Enter an investigation name of 1–120 characters.'); return; }
      if (working) return; setWorking(true); setError('');
      try { await onCreate(title); onClose(); } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not create the investigation.'); setWorking(false); }
    }}>
      <h2 id={id}>Name your investigation</h2>
      <label className="field">Investigation name<input ref={field} value={name} maxLength={120} required disabled={working} onChange={(e) => setName(e.target.value)} /></label>
      <p className="muted">This name appears in your saved investigations. You can rename it later.</p>
      {error ? <p role="alert">{error}</p> : null}
      <div className="row"><button className="btn primary" type="submit" disabled={working || !name.trim()}>{working ? 'Creating…' : 'Create investigation'}</button><button className="btn" type="button" disabled={working} onClick={onClose}>Cancel</button></div>
    </form>
  </dialog>;
}
