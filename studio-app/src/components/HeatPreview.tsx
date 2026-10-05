import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { Snapshot, StudyContext } from '../types';

/** Uses the existing geographic Gaussian and full-study scale from frozen replay. */
export function HeatPreview({ documentId, snapshot, context, title }: { documentId: string; snapshot: Snapshot; context: StudyContext; title: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [ready, setReady] = useState(false);
  const [status, setStatus] = useState('Preparing frozen heat map…');
  useEffect(() => {
    let active = true; setReady(false); setStatus('Preparing frozen heat map…');
    const g = canvas.current?.getContext('2d'); g?.clearRect(0, 0, 800, 450);
    api.snapshotReceipt(documentId, snapshot.id).then(({ receipt }) => {
      if (!active || !canvas.current) return;
      const FM = window.FireAtlasMap;
      if (!FM || !receipt.payload.frames?.length) throw new Error('Frozen replay heat renderer unavailable. Open details for the source evidence.');
      if (JSON.stringify(context.bbox) !== JSON.stringify(snapshot.scope.bbox)) throw new Error('Refreeze explicitly for a changed study boundary.');
      const index = FM.createIndex(receipt.payload), at = receipt.payload.frames.findIndex((f: any) => f.date_utc === (context.day || snapshot.scope.start));
      if (at < 0) throw new Error('The selected day is outside this frozen replay.');
      const frame = FM.frame(index, at, String(context.source || 'joint'), 'daily');
      const [w, s, e, n] = snapshot.scope.bbox;
      const g = canvas.current.getContext('2d')!;
      g.fillStyle = '#102b35'; g.fillRect(0, 0, 800, 450);
      // A uniform schematic projection retains the kernel's geographic width.
      const project = ([lat, lon]: number[]) => ({ x: 40 + (lon - w) / (e - w) * 720, y: 390 - (lat - s) / (n - s) * 340 });
      g.save(); g.beginPath(); g.rect(40, 50, 720, 340); g.clip();
      FM.drawHeat(g, 800, 450, frame, project); g.restore();
      canvas.current.dataset.maximum = String(frame.maximum); canvas.current.dataset.day = frame.date; canvas.current.dataset.source = String(context.source || 'joint');
      g.strokeStyle = '#8bb0b4'; g.strokeRect(40, 50, 720, 340);
      g.fillStyle = '#f3f8f5'; g.font = '16px sans-serif';
      g.fillText(`${frame.date} UTC · ${context.source === 'MODIS_SP' ? 'MODIS' : context.source === 'VIIRS_SNPP_SP' ? 'S-NPP VIIRS' : 'Both sensors'}`, 40, 28);
      g.font = '13px sans-serif'; g.fillText(`0–${frame.maximum.toFixed(2)} occupied-cell concentration · study-fixed · 1 km Gaussian`, 40, 418);
      g.fillText('Schematic of recorded common-cell centers · no perimeter or burned-area estimate', 40, 439);
      const states = Object.entries(receipt.payload.frames[at].products).map(([source, p]: any) => `${source}: ${p.state}`).join(' · ');
      setReady(true); setStatus(`${frame.cells.length} occupied cells · ${states}. Scale fixed across dates and panes. Imagery not required.`);
    }).catch((error) => active && setStatus(error.message));
    return () => { active = false; };
  }, [documentId, snapshot.id, context.day, context.source, JSON.stringify(context.bbox)]);
  return <div><canvas ref={canvas} width={800} height={450} role="img" aria-label={`${title}: frozen occupied-cell heat map`} style={{ width: '100%', borderRadius: 8 }} /><p className="map-note" role="status">{status}</p><button className="btn small" disabled={!ready} onClick={() => { const a = document.createElement('a'); a.download = `heat-${snapshot.id}-${context.source || 'joint'}-${context.day || snapshot.scope.start}.png`; a.href = canvas.current!.toDataURL('image/png'); a.click(); }}>Download heat map PNG</button></div>;
}
