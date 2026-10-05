import { useEffect, useId, useRef, useState } from 'react';

export function DeleteInvestigationDialog({ title, onDelete, onClose }: { title: string; onDelete: () => Promise<void>; onClose: () => void }) {
  const heading = useId(), description = useId(), dialog = useRef<HTMLDialogElement>(null), cancel = useRef<HTMLButtonElement>(null);
  const [working, setWorking] = useState(false), [error, setError] = useState('');
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.showModal(); cancel.current?.focus();
    return () => { dialog.current?.close(); if (previous?.isConnected && !previous.matches(':disabled')) previous.focus(); else [...document.querySelectorAll<HTMLButtonElement>('.studio-app button')].find((button) => button.textContent === 'Blank investigation')?.focus(); };
  }, []);
  return <dialog ref={dialog} className="delete-investigation-dialog" aria-labelledby={heading} aria-describedby={description} onCancel={(event) => { event.preventDefault(); if (!working) onClose(); }}>
    <div className="delete-icon" aria-hidden="true"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7" /></svg></div>
    <span className="st-eyebrow">SAVED INVESTIGATION</span><h2 id={heading}>Delete this investigation?</h2>
    <p id={description}>Are you sure you want to delete <strong className="delete-title">{title}</strong>? Its canvas, story and workflow will disappear from your saved investigations. This cannot be undone in Studio.</p>
    <p className="muted">Your other investigations, scientific data and presentation presets stay available.</p>
    {error ? <p className="delete-error" role="alert">{error}</p> : null}
    <div className="delete-actions"><button ref={cancel} className="btn" type="button" disabled={working} onClick={onClose}>Keep investigation</button><button className="btn danger" type="button" disabled={working} onClick={async () => {
      if (working) return; setWorking(true); setError('');
      try { await onDelete(); onClose(); } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not delete the investigation. Please try again.'); setWorking(false); }
    }}>{working ? 'Deleting…' : 'Delete investigation'}</button></div>
  </dialog>;
}
