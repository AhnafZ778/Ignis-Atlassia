import { useState } from 'react';
import { useStudio } from '../store';
import type { Card, Snapshot } from '../types';

export function MapBackgroundControls({ card }: { card: Card; snapshot: Snapshot; documentId: string; day?: string }) {
  const { canEdit, busy, transact } = useStudio();
  const background = String(card.display?.background || 'auto');
  const on = background !== 'none';
  const [saving, setSaving] = useState(false);
  return <div className="map-background-control"><button type="button" className="map-background-dot" role="switch" aria-label="Map background" aria-checked={on} title={on ? 'Hide map background' : 'Show map background'} disabled={!canEdit || card.locked || busy || saving} onClick={async () => {
    if (saving || busy) return;
    const previous = String(card.display?.previous_background || 'auto');
    setSaving(true);
    try { await transact([{ op: 'update_card', id: card.id, patch: { display: { ...card.display, background: on ? 'none' : previous === 'none' ? 'auto' : previous, ...(on ? { previous_background: background } : {}) } } }]); }
    finally { setSaving(false); }
  }}><span className="map-background-indicator" aria-hidden="true" /></button></div>;
}
