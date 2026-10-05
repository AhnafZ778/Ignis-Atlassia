import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { chartTable, chartCsv, downloadCard } from '../lib/chartValues';
import { api } from '../api';
import type { Card, Fact, Snapshot, StudyContext, DisplaySelection } from '../types';
import { useStudio } from '../store';
import { HeatPreview } from './HeatPreview';
import { effectiveStudy } from '../lib/graph';

export const MAX_LIVE_MAPS = 2;
const slots = new Set<string>();
const claim = (id: string) => { if (slots.has(id)) return true; if (slots.size >= MAX_LIVE_MAPS) return false; slots.add(id); return true; };
const release = (id: string) => { slots.delete(id); };
export const liveMapCount = () => slots.size;

const fmt = (fact: Fact) => (fact.value === null || fact.state !== 'observed' ? (fact.state === 'unknown' ? 'unknown' : 'unavailable') : `${fact.value}`);

export function FactBars({ facts, unit }: { facts: Fact[]; unit: string }) {
  const observed = facts.filter((f) => f.state === 'observed' && typeof f.value === 'number').slice(0, 12);
  if (!observed.length || new Set(facts.map((fact) => fact.unit)).size > 1) return <FactTable facts={facts} />;
  const top = Math.max(1, ...observed.map((f) => f.value as number));
  return (
    <div className="bars" role="list" aria-label={`Values in ${unit}, shared zero baseline`}>
      {observed.map((f) => (
        <div className="bar" role="listitem" key={f.path}>
          <span>{f.label}</span>
          <span className="bar-track" aria-hidden="true"><span className="bar-fill" style={{ width: `${Math.max(2, ((f.value as number) / top) * 100)}%` }} /></span>
          <strong>{f.value} <small>{f.unit}</small></strong>
        </div>
      ))}
    </div>
  );
}

export function FactTable({ facts }: { facts: Fact[] }) {
  return (
    <table className="facts">
      <thead><tr><th scope="col">Value</th><th scope="col">Reading</th><th scope="col">Unit</th></tr></thead>
      <tbody>
        {facts.slice(0, 20).map((f) => (
          <tr key={f.path}><td>{f.label}</td><td className={f.state === 'observed' ? '' : `state-${f.state}`}>{fmt(f)}</td><td>{f.unit}</td></tr>
        ))}
      </tbody>
    </table>
  );
}

function PreparedCard({ card, snapshot, documentId, context }: { card: Card; snapshot: Snapshot; documentId: string; context: StudyContext }) {
  const { doc, publishSelection } = useStudio();
  const [svg, setSvg] = useState('');
  const [visual, setVisual] = useState<any>(null);
  const [interval, setInterval] = useState({ start: snapshot.scope.start, end: snapshot.scope.end });
  const brush = useRef<number | null>(null);
  const [status, setStatus] = useState('Preparing frozen preview…');
  useEffect(() => {
    let active = true;
    setSvg(''); setVisual(null); setStatus('Preparing frozen preview…');
    if (JSON.stringify(context.bbox) !== JSON.stringify(snapshot.scope.bbox)) { setStatus('This card’s applied boundary differs from its frozen receipt. Refreeze explicitly to inspect the new study.'); return; }
    api.snapshotPreview(documentId, snapshot.id, card.type, context.day ? String(context.day) : undefined, String(context.source || 'joint'), (context as any).display_selection || {}).then((result) => {
      if (!active) return;
      setSvg(result.svg); setVisual(result.visual); setStatus('Prepared frozen evidence · schematic view');
    }).catch((error) => active && setStatus(error.message));
    return () => { active = false; };
  }, [documentId, snapshot.id, card.type, context.day, context.source, JSON.stringify(context.bbox), JSON.stringify(snapshot.scope.bbox), JSON.stringify((context as any).display_selection)]);
  const table = chartTable(visual);
  const filename = `chart-${snapshot.id}`;
  const emit = (value: DisplaySelection) => { if (doc) publishSelection(card.id, value, doc.context_revision, doc.id); };
  const brushIndex = (clientX: number, element: HTMLImageElement) => { const box = element.getBoundingClientRect(); return Math.max(0, Math.min((visual?.values?.length || 1) - 1, Math.floor(((clientX - box.left) / box.width * 960 - 80) / 800 * (visual?.values?.length || 1)))); };
  return <div>{svg ? <img src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`} alt={`${card.title}: frozen evidence schematic`} style={{ width: '100%', maxHeight: Math.max(80, Math.min(180, card.transform.h - 130)), objectFit: 'contain' }} onPointerDown={(e) => { if (card.type !== 'chart' || !visual?.values?.length) return; e.currentTarget.setPointerCapture(e.pointerId); brush.current = brushIndex(e.clientX, e.currentTarget); }} onPointerUp={(e) => { if (brush.current === null) return; const last = brushIndex(e.clientX, e.currentTarget), first = brush.current; brush.current = null; const a = visual.values[Math.min(first, last)].date, b = visual.values[Math.max(first, last)].date; emit({ start: a, end: b, day: a }); }} /> : <FactTable facts={snapshot.facts} />}<p className="map-note" role="status">{status}</p>{table ? <details><summary>Numeric table and chart downloads</summary><p className="muted">{table.note} Frozen receipt {snapshot.receipt_sha256}. Display interval {visual.interval?.start || snapshot.scope.start} → {visual.interval?.end || snapshot.scope.end}. CSV contains this prepared series, with unknown values distinct from zero.</p><div className="card-table-scroll"><table className="facts"><caption>{card.title} · {table.unit}</caption><thead><tr>{table.headers.map((h) => <th scope="col" key={h}>{h}</th>)}</tr></thead><tbody>{table.rows.map((row, i) => <tr key={i}>{row.map((v, j) => j === 0 ? <th scope="row" key={j}>{v ?? 'unknown'}</th> : <td key={j}>{v ?? 'unknown'}</td>)}</tr>)}</tbody></table></div><div className="row"><button className="btn small" onClick={() => downloadCard(filename + '.csv', chartCsv(table), 'text/csv;charset=utf-8')}>Download chart values CSV</button><button className="btn small" disabled={!svg} onClick={() => downloadCard(filename + '.svg', svg, 'image/svg+xml;charset=utf-8')}>Download chart SVG</button><button className="btn small" onClick={() => downloadCard(filename + '.json', JSON.stringify({ snapshot_id: snapshot.id, receipt_sha256: snapshot.receipt_sha256, method: snapshot.method, visual }, null, 2), 'application/json')}>Download chart context</button></div></details> : null}{visual?.selected_cell ? <p className="muted">Selected common cell: {visual.selected_cell} · {visual.available_rows} matching frozen rows</p> : null}{['chart', 'timeline', 'calendar'].includes(card.type) ? <details><summary>Focus linked UTC interval</summary><label className="field">Linked interval start<input type="date" min={snapshot.scope.start} max={snapshot.scope.end} value={interval.start} onChange={(e) => setInterval((v) => ({ ...v, start: e.target.value }))} /></label><label className="field">Linked interval end<input type="date" min={snapshot.scope.start} max={snapshot.scope.end} value={interval.end} onChange={(e) => setInterval((v) => ({ ...v, end: e.target.value }))} /></label><button className="btn small" disabled={!interval.start || !interval.end || interval.start > interval.end || interval.start < snapshot.scope.start || interval.end > snapshot.scope.end} onClick={() => emit({ ...interval, day: interval.start })}>Focus compatible cards</button><p className="muted">Brush a daily chart or use these dates. Only compatible unpinned linked cards follow; frozen totals retain their scope.</p></details> : null}</div>;
}
function MapCard({ card, snapshot, documentId, context, expanded = false }: { card: Card; snapshot: Snapshot; documentId: string; context: StudyContext; expanded?: boolean }) {
  const { doc, publishSelection } = useStudio();
  const host = useRef<HTMLDivElement>(null);
  const [interactive, setInteractive] = useState(expanded);
  const [expand, setExpand] = useState(false);
  const instanceId = useId();
  const [cell, setCell] = useState('');
  const [status, setStatus] = useState('');
  useEffect(() => {
    if (!interactive) return;
    const slot = documentId + ':' + card.id + ':' + instanceId;
    if (!claim(slot)) { setStatus(`Only ${MAX_LIVE_MAPS} maps can be active. Pause another map first.`); setInteractive(false); return; }
    const L = window.L, FM = window.FireAtlasMap;
    if (!L || !FM || !host.current) { setStatus('Map SDK unavailable. The prepared schematic remains usable.'); setInteractive(false); release(slot); return; }
    let canceled = false, map: any = null;
    setStatus('Loading frozen frame…');
    api.snapshotReceipt(documentId, snapshot.id).then(({ receipt }) => {
      if (canceled || !host.current) return;
      const bundle = receipt.payload;
      if (!Array.isArray(bundle?.frames) || !bundle.frames.length) throw new Error('This receipt has no map frames.');
      if (JSON.stringify(context.bbox) !== JSON.stringify(snapshot.scope.bbox)) throw new Error('Applied boundary differs from the frozen receipt. Refreeze explicitly.');
      const frames = bundle.frames as { date_utc: string }[];
      const at = context.day ? frames.findIndex((f) => f.date_utc === context.day) : 0;
      if (at < 0) throw new Error('The applied day is outside the frozen map frames.');
      const [w, s, e, n] = snapshot.scope.bbox;
      map = L.map(host.current, { preferCanvas: true, zoomControl: true, attributionControl: true, scrollWheelZoom: true });
      L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { attribution: 'Imagery © Esri · observations NASA FIRMS', maxZoom: 18 }).addTo(map);
      L.rectangle([[s, w], [n, e]], { color: '#237745', weight: 1, fill: false, dashArray: '4 4' }).addTo(map);
      map.fitBounds([[s, w], [n, e]], { padding: [8, 8] });
      const source = String(context.source || 'joint'), metric = String(context.metric || 'density');
      if (source === 'joint' && metric === 'frp') throw new Error('Choose one sensor for peak native FRP. Joint FRP is unavailable.');
      const index = FM.createIndex(bundle), frame = FM.frame(index, at, source, metric === 'persistence' ? 'history' : 'daily');
      if (metric === 'density') {
        const Heat = FM.install(L), heat = new Heat().addTo(map); heat.setData(frame);
        setStatus(`Frozen ${frames[at].date_utc} UTC · study-fixed 0–${frame.maximum.toFixed(2)} occupied-cell concentration · 1 km Gaussian · imagery optional`);
      } else {
        const maximum = metric === 'persistence' ? frames.length : Math.max(1, ...bundle.frames.flatMap((f: any) => f.cells.flatMap((c: any) => [c.modis_frp_max_mw || 0, c.viirs_frp_max_mw || 0])));
        for (const cell of frame.cells) {
          const value = metric === 'persistence' ? cell.observed_days : source === 'VIIRS_SNPP_SP' ? cell.viirs_frp_max_mw : cell.modis_frp_max_mw;
          if (value == null) continue;
          L.polygon(cell.ring.map((point: number[]) => [point[1], point[0]]), { color: '#102b35', weight: .6, fillColor: `hsl(${45 - 40 * value / maximum} 75% 45%)`, fillOpacity: .7 }).bindTooltip(`${value} ${metric === 'persistence' ? 'distinct observed UTC dates' : 'MW peak native FRP'} · ${frames[at].date_utc} UTC`).addTo(map);
        }
        setStatus(`Frozen ${frames[at].date_utc} UTC · study-fixed 0–${maximum} ${metric === 'persistence' ? 'distinct observed UTC dates through this date' : 'MW peak native FRP'} · imagery optional`);
      }
      const selectionRevision = doc?.context_revision;
      for (const cell of frame.cells) {
        L.polygon(cell.ring.map((point: number[]) => [point[1], point[0]]), { color: '#244f63', weight: 0.5, fillOpacity: 0.01 }).bindTooltip(`Common cell ${cell.grid_x}:${cell.grid_y} · ${frames[at].date_utc} UTC`).on('click', () => { if (canceled || selectionRevision == null) return; publishSelection(card.id, { day: frames[at].date_utc, cell: `${cell.grid_x}:${cell.grid_y}` }, selectionRevision, documentId); }).addTo(map);
      }
      requestAnimationFrame(() => map?.invalidateSize());
    }).catch((error) => { if (!canceled) { setStatus(error.message); setInteractive(false); } });
    return () => { canceled = true; map?.remove(); release(slot); };
  }, [interactive, card.id, documentId, snapshot.id, context.day, context.source, context.metric, JSON.stringify(context.bbox)]);
  return <div>{interactive ? <div ref={host} className="map-box" style={{ height: expanded ? 'min(65vh, 650px)' : 170 }} aria-label={`${card.title} interactive map`} /> : card.display?.preview === 'heat' && !(context as any).display_selection?.start && (!context.metric || context.metric === 'density') ? <HeatPreview title={card.title} snapshot={snapshot} documentId={documentId} context={context} /> : <PreparedCard card={card} snapshot={snapshot} documentId={documentId} context={context} />}<button className="btn small" onClick={() => setInteractive((value) => !value)}>{interactive ? 'Pause map interaction' : 'Interact with map'}</button>{!expanded ? <button className="btn small" onClick={() => { setInteractive(false); setExpand(true); }}>Expand map</button> : null}{expand ? <ExpandedMap card={card} snapshot={snapshot} documentId={documentId} context={context} close={() => setExpand(false)} /> : null}{status ? <p className="map-note" role="status">{status}</p> : null}<details><summary>Inspect a common cell</summary><label className="field">Common cell to inspect<input value={cell} placeholder="grid_x:grid_y" onChange={(e) => setCell(e.target.value)} /></label><button className="btn small" disabled={!/^-?\d{1,8}:-?\d{1,8}$/.test(cell)} onClick={() => { if (doc) publishSelection(card.id, { day: String(context.day || snapshot.scope.day || snapshot.scope.start), cell }, doc.context_revision, doc.id); }}>Focus linked cell evidence</button><p className="muted">Click a cell in the interactive map or enter its grid ID. Linked observations show matching rows within their frozen receipt.</p></details></div>;
}

export function CardBody({ card, snapshot, documentId, details = true }: { card: Card; snapshot: Snapshot | null; documentId: string; details?: boolean }) {
  const { selected, displaySelections, select } = useStudio();
  const host = useRef<HTMLDivElement>(null);
  const [loaded, setLoaded] = useState(typeof IntersectionObserver === 'undefined');
  useEffect(() => {
    if (loaded || !host.current || typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver((entries) => { if (entries.some((entry) => entry.isIntersecting)) { setLoaded(true); observer.disconnect(); } }, { rootMargin: '200px' });
    observer.observe(host.current);
    return () => observer.disconnect();
  }, [loaded]);
  const render = loaded || selected === card.id || Boolean(displaySelections[card.id]) || !snapshot;
  return <div ref={host} className="card-content-actions" onPointerDown={(e) => e.stopPropagation()}>{details ? <button className="btn small" onClick={() => { select(card.id); requestAnimationFrame(() => { const panel = document.querySelector<HTMLElement>('[aria-label="Inspector"]'); panel?.scrollIntoView({ block: 'nearest' }); panel?.focus(); }); }}>Open details</button> : null}{render ? <CardContent card={card} snapshot={snapshot} documentId={documentId} /> : <div><p className="muted">Frozen {snapshot.unit} preview loads when this card enters view.</p><button className="btn small" onClick={() => setLoaded(true)}>Load card preview</button></div>}</div>;
}

function CardContent({ card, snapshot, documentId }: { card: Card; snapshot: Snapshot | null; documentId: string }) {
  const { doc, displaySelections } = useStudio();
  const applied = doc ? effectiveStudy(card, doc.state).context || {} : {};
  const display = displaySelections[card.id];
  const visible = { ...applied, ...(card.display?.source ? { source: card.display.source } : {}), ...(card.display?.day ? { day: card.display.day } : {}) };
  const context = display ? { ...visible, ...(display.day ? { day: display.day } : {}), display_selection: display } : visible;
  if (card.type === 'text' || card.type === 'quote' || card.type === 'note-question') return card.text ? <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{card.type === 'quote' ? `“${card.text}”` : card.text}</p> : <p className="empty">Empty note or question</p>;
  if (card.type === 'image') return card.asset_id ? <img src={api.assetUrl(card.asset_id)} alt={card.title || 'Uploaded image'} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} /> : <p className="empty">No image uploaded.</p>;
  if (card.type === 'method-note' && !snapshot) return card.text ? <p style={{ margin: 0 }}>{card.text}</p> : <p className="empty">Freeze evidence to cite the method.</p>;
  if (card.type === 'chapter-frame' && !snapshot) return card.text ? <p style={{ margin: 0 }}>{card.text}</p> : <p className="empty">Select cards in the inspector to make a chapter frame.</p>;
  if (!snapshot) return <p className="empty">{card.binding ? 'Bound, but not frozen yet. Freeze it in the inspector.' : 'No evidence yet. Choose a scientific operation in the inspector.'}</p>;
  if (card.asset_id && card.display.captured_view) return <div><img src={api.assetUrl(card.asset_id)} alt={`${card.title}: captured source frame`} style={{width:'100%',maxHeight:Math.max(80,Math.min(180,card.transform.h-130)),objectFit:'contain'}} /><p className="map-note">{String((card.display.captured_view as any)?.caption || 'Frozen source display. Inspect its data and captured renderer settings in the package.')}</p><details><summary>Inspect frozen visualization data</summary><PreparedCard card={card} snapshot={snapshot} documentId={documentId} context={context} /></details></div>;
  if (card.type === 'map') return <MapCard card={card} snapshot={snapshot} documentId={documentId} context={context} />;
  if (card.type === 'method-note' || card.type === 'finding') {
    return <div><p style={{ margin: '0 0 4px' }}><strong>{snapshot.method.id}</strong> · unit {snapshot.method.unit}</p>{card.text ? <p style={{ margin: 0 }}>{card.text}</p> : null}<FactTable facts={snapshot.facts} /></div>;
  }
  if (['chart', 'timeline', 'calendar', 'observation'].includes(card.type)) return <PreparedCard card={card} snapshot={snapshot} documentId={documentId} context={context} />;
  return <FactTable facts={snapshot.facts} />;
}

function ExpandedMap({ card, snapshot, documentId, context, close }: { card: Card; snapshot: Snapshot; documentId: string; context: StudyContext; close: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [source, setSource] = useState(String(context.source || 'joint'));
  const [metric, setMetric] = useState(String(context.metric || 'density'));
  useEffect(() => { const previous = document.activeElement as HTMLElement | null; dialog.current?.showModal(); return () => { dialog.current?.close(); previous?.focus(); }; }, []);
  return createPortal(<dialog ref={dialog} className="studio-app expanded-card-map" aria-label={`Expanded map: ${card.title}`} onCancel={close}>
    <div className="row"><h2>{card.title}</h2><button className="btn" onClick={close}>Close expanded map</button></div>
    <p>{snapshot.scope.start} → {snapshot.scope.end} UTC · frozen study boundary {snapshot.scope.bbox.join(', ')}. These display controls retain the receipt and headline calculation.</p>
    <div className="row"><label className="field">Visible source<select value={source} onChange={(e) => { setSource(e.target.value); if (e.target.value === 'joint' && metric === 'frp') setMetric('density'); }}><option value="joint">Both sensors</option><option value="MODIS_SP">MODIS · circles</option><option value="VIIRS_SNPP_SP">S-NPP VIIRS · diamonds</option></select></label><label className="field">Map statistic<select value={metric} onChange={(e) => setMetric(e.target.value)}><option value="density">Occupied-cell concentration</option><option value="persistence">Distinct observed UTC dates</option><option value="frp" disabled={source === 'joint'}>Peak native FRP · single sensor</option></select></label></div>
    <MapCard card={card} snapshot={snapshot} documentId={documentId} context={{ ...context, source, metric }} expanded />
    <p className="muted">Study-fixed scale across dates and sensors. MODIS circles · VIIRS diamonds · shared squares in the schematic. Imagery is optional; missing tiles do not remove the frozen cells. Receipt {snapshot.receipt_sha256}.</p>
  </dialog>, document.body);
}
