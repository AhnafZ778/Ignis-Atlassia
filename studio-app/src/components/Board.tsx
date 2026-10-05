import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { useStudio } from '../store';
import type { Card, Transform, Viewport } from '../types';
import { CardBody } from './CardBody';

type Drag = { id: string; mode: 'move' | 'resize'; startX: number; startY: number; origin: Transform; current: Transform };
const clampBox = (t: Transform): Transform => ({ ...t, x: Math.max(0, Math.round(t.x)), y: Math.max(0, Math.round(t.y)), w: Math.max(160, Math.round(t.w)), h: Math.max(100, Math.round(t.h)) });

export function Board() {
  const { doc, selected, select, transact, canEdit, canvasCards } = useStudio();
  const [view, setView] = useState<Viewport>(doc!.state.viewport || { x: 0, y: 0, zoom: 1 });
  const [panMode, setPanMode] = useState(false);
  const [spacePan, setSpacePan] = useState(false);
  const spaceHeld = useRef(false);
  const [panning, setPanning] = useState(false);
  const boardHost = useRef<HTMLDivElement>(null);
  const awaitingFirstCards = useRef(doc!.state.order.length === 0 || (new URLSearchParams(location.search).has('command') && doc!.state.viewport?.zoom === 1));
  const pan = useRef<{ x: number; y: number; pointerId: number; origin: Viewport } | null>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const dragRef = useRef<Drag | null>(null);
  const state = { ...doc!.state, cards: canvasCards };
  const groupOf = (id: string) => Object.values(state.groups || {}).find((g) => g.card_ids.includes(id));
  const boxOf = (card: Card): Transform => {
    if (!drag) return card.transform;
    if (drag.id === card.id) return drag.current;
    if (drag.mode === 'move' && groupOf(drag.id)?.card_ids.includes(card.id)) return { ...card.transform, x: card.transform.x + drag.current.x - drag.origin.x, y: card.transform.y + drag.current.y - drag.origin.y };
    return card.transform;
  };

  const size = useMemo(() => {
    let w = 1100, h = 640;
    for (const c of Object.values(state.cards)) { const t = boxOf(c); w = Math.max(w, t.x + t.w + 160); h = Math.max(h, t.y + t.h + 160); }
    return { w, h };
  }, [state, drag]);

  const fit = () => { const box = boardHost.current; if (box) setView({ x: 12, y: 12, zoom: Math.max(0.1, Math.min(1, (box.clientWidth - 24) / size.w, (box.clientHeight - 24) / size.h)) }); };
  useEffect(() => { if (!state.order.length || !awaitingFirstCards.current) return; awaitingFirstCards.current = false; const frame = requestAnimationFrame(fit); return () => cancelAnimationFrame(frame); }, [state.order.length]);

  const start = (event: PointerEvent<HTMLElement>, card: Card, mode: Drag['mode']) => {
    select(card.id);
    if (panMode || !canEdit || card.locked || (mode === 'move' && groupOf(card.id)?.card_ids.some((id) => state.cards[id].locked))) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    const next: Drag = { id: card.id, mode, startX: event.clientX, startY: event.clientY, origin: card.transform, current: card.transform };
    dragRef.current = next;
    setDrag(next);
  };
  const move = (event: PointerEvent<HTMLElement>) => {
    const d = dragRef.current;
    if (!d) return;
    const dx = (event.clientX - d.startX) / view.zoom, dy = (event.clientY - d.startY) / view.zoom;
    const current = clampBox(d.mode === 'move' ? { ...d.origin, x: d.origin.x + dx, y: d.origin.y + dy } : { ...d.origin, w: d.origin.w + dx, h: d.origin.h + dy });
    const next = { ...d, current };
    dragRef.current = next;
    setDrag(next);
  };
  const finish = async () => {
    const d = dragRef.current;
    dragRef.current = null;
    if (!d) return;
    const changed = JSON.stringify(d.current) !== JSON.stringify(d.origin);
    if (changed) {
      const group = d.mode === 'move' ? groupOf(d.id) : undefined;
      await transact(group ? [{ op: 'move_group', id: group.id, dx: d.current.x - d.origin.x, dy: d.current.y - d.origin.y }] : [{ op: 'move_card', id: d.id, transform: d.current, layout_origin: d.origin }]);
    }
    setDrag(null);
  };

  // Every wheel gesture inside this canvas zooms, even over scrollable cards
  // or embedded controls. Native capture prevents nested maps and React's
  // passive wheel listener from consuming it or scrolling the board/page.
  // Scrollbar dragging and pointer panning remain independent interactions.
  useEffect(() => {
    const onDocumentWheel = (event: globalThis.WheelEvent) => {
      const host = boardHost.current;
      if (!host) return;
      const rect = host.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) return;
      const target = event.target as Node | null;
      if (!target || !host.contains(target)) {
        const hit = document.elementFromPoint(event.clientX, event.clientY);
        if (!hit || !host.contains(hit)) return;
      }
      event.preventDefault(); event.stopImmediatePropagation();
      // Include manual scrollbar offsets so the same world point stays under
      // the pointer when a previously scrolled board is zoomed.
      const pointerX = event.clientX - rect.left - host.clientLeft + host.scrollLeft;
      const pointerY = event.clientY - rect.top - host.clientTop + host.scrollTop;
      const wheelDelta = event.deltaY || event.deltaX;
      const delta = event.deltaMode === 1 ? wheelDelta * 16 : event.deltaMode === 2 ? wheelDelta * host.clientHeight : wheelDelta;
      const factor = Math.exp(Math.max(-0.22, Math.min(0.22, -delta * 0.0015)));
      setView((current) => {
        const zoom = Math.max(0.1, Math.min(4, current.zoom * factor));
        if (zoom === current.zoom) return current;
        const worldX = (pointerX - current.x) / current.zoom;
        const worldY = (pointerY - current.y) / current.zoom;
        return { x: pointerX - worldX * zoom, y: pointerY - worldY * zoom, zoom };
      });
    };
    document.addEventListener('wheel', onDocumentWheel, { capture: true, passive: false });
    return () => document.removeEventListener('wheel', onDocumentWheel, true);
  }, []);
  const endPan = () => { pan.current = null; setPanning(false); };
  const clearSpace = () => { spaceHeld.current = false; setSpacePan(false); };
  useEffect(() => {
    const release = (event: globalThis.KeyboardEvent) => { if (event.code === 'Space') clearSpace(); };
    const blur = () => { clearSpace(); endPan(); };
    window.addEventListener('keyup', release); window.addEventListener('blur', blur);
    return () => { window.removeEventListener('keyup', release); window.removeEventListener('blur', blur); };
  }, []);
  const beginPan = (event: PointerEvent<HTMLDivElement>) => {
    if (pan.current || ![0, 1].includes(event.button)) return;
    const host = event.currentTarget, rect = host.getBoundingClientRect();
    // Native scrollbar tracks remain draggable instead of starting a pan.
    if (event.clientX >= rect.left + host.clientLeft + host.clientWidth || event.clientY >= rect.top + host.clientTop + host.clientHeight) return;
    const target = event.target as HTMLElement;
    // Controls and live maps retain their own gestures. Capture on the board
    // lets Pan canvas and Space-drag also work over frozen card previews.
    if (target.closest('button,input,textarea,select,a,summary,details,[contenteditable="true"],.leaflet-container,.resize')) return;
    const background = !target.closest('.card');
    if (!background && !panMode && !spaceHeld.current && event.button !== 1) return;
    event.preventDefault(); event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    pan.current = { x: event.clientX, y: event.clientY, pointerId: event.pointerId, origin: view };
    setPanning(true);
    if (background) { select(null); event.currentTarget.focus({ preventScroll: true }); }
  };
  const keys = (event: KeyboardEvent<HTMLElement>, card: Card) => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(card.id); return; }
    const step = event.shiftKey ? 64 : 16;
    const delta: Record<string, [number, number]> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    const d = delta[event.key];
    if (!d || !canEdit || card.locked) return;
    event.preventDefault();
    const group = groupOf(card.id);
    transact(group ? [{ op: 'move_group', id: group.id, dx: d[0], dy: d[1] }] : [{ op: 'move_card', id: card.id, layout_origin: card.transform, transform: clampBox({ ...card.transform, x: card.transform.x + d[0], y: card.transform.y + d[1] }) }]);
  };

  const cards = state.order.map((id) => state.cards[id]).filter(Boolean);
  if (!cards.length) {
    return <div className="board-wrap"><div className="empty-state"><h2>Your board is empty</h2><p>Add a card from the library, then bind it to evidence in the inspector.</p></div></div>;
  }
  return (
    <section aria-label="Evidence canvas"><div className="row canvas-toolbar"><button className="btn" aria-pressed={!panMode} onClick={() => setPanMode(false)}>Select cards</button><button className="btn" aria-pressed={panMode} onClick={() => setPanMode(true)}>Pan canvas</button><button className="btn" onClick={() => setView((v) => ({ ...v, zoom: Math.min(4, v.zoom * 1.25) }))}>Zoom in</button><button className="btn" onClick={() => setView((v) => ({ ...v, zoom: Math.max(0.1, v.zoom / 1.25) }))}>Zoom out</button><button className="btn" onClick={fit}>Fit all cards</button><button className="btn" onClick={() => setView({ x: 0, y: 0, zoom: 1 })}>Reset view</button><button className="btn" disabled={!canEdit} onClick={() => void transact([{ op: 'set_viewport', viewport: view }])}>Save canvas view</button><button className="btn" onClick={() => setView(state.viewport || { x: 0, y: 0, zoom: 1 })}>Restore saved view</button><span>{Math.round(view.zoom * 100)}%</span><span className="canvas-help">Drag empty canvas to pan · Space + drag anywhere · scroll to zoom</span></div>
    <div ref={boardHost} className={`board-wrap${panMode || spacePan ? ' pan-ready' : ''}${panning ? ' is-panning' : ''}`} role="region" aria-label="Evidence board. Drag empty canvas to pan, Space-drag to pan over cards, drag card headers to move cards, or scroll to zoom." tabIndex={0}
      onKeyDownCapture={(e) => { if (e.code !== 'Space' || (e.target as HTMLElement).closest('button,input,textarea,select,a,summary,[contenteditable="true"]')) return; e.preventDefault(); e.stopPropagation(); spaceHeld.current = true; setSpacePan(true); }}
      onPointerDownCapture={beginPan}
      onPointerMove={(e) => { const active = pan.current; if (active?.pointerId === e.pointerId) { e.preventDefault(); setView({ ...active.origin, x: active.origin.x + e.clientX - active.x, y: active.origin.y + e.clientY - active.y }); } }}
      onPointerUp={endPan} onPointerCancel={endPan} onLostPointerCapture={endPan}>
      <div style={{ width: Math.max(1100, size.w * view.zoom + view.x), height: Math.max(640, size.h * view.zoom + view.y), position: 'relative' }}>
      <div className="board-canvas" style={{ width: size.w, height: size.h, transform: `translate(${view.x}px,${view.y}px) scale(${view.zoom})`, transformOrigin: '0 0' }} onPointerDown={(e) => { if (e.target === e.currentTarget) select(null); }}>
        <svg className="board-links" width={size.w} height={size.h} aria-hidden="true">
          {Object.values(state.connections).map((link) => {
            const a = state.cards[link.source], b = state.cards[link.target];
            if (!a || !b) return null;
            const ta = boxOf(a), tb = boxOf(b);
            const x1 = ta.x + ta.w, y1 = ta.y + ta.h / 2, x2 = tb.x, y2 = tb.y + tb.h / 2, mid = Math.max(40, Math.abs(x2 - x1) / 2);
            return <path key={link.id} className={link.kind} d={`M${x1},${y1} C${x1 + mid},${y1} ${x2 - mid},${y2} ${x2},${y2}`} />;
          })}
        </svg>
        {Object.values(state.groups || {}).map((group) => { const boxes = group.card_ids.map((id) => boxOf(state.cards[id])); const x = Math.min(...boxes.map((t) => t.x)), y = Math.min(...boxes.map((t) => t.y)); return <div className="board-group" key={group.id} style={{ left: x - 10, top: y - 28, width: Math.max(...boxes.map((t) => t.x + t.w)) - x + 20, height: Math.max(...boxes.map((t) => t.y + t.h)) - y + 38 }}><span>{group.title}</span></div>; })}
        {cards.map((card) => {
          const t = boxOf(card);
          const snapshot = card.snapshot_id ? doc!.snapshots?.[card.snapshot_id] ?? null : null;
          return (
            <article key={card.id} className={`card${selected === card.id ? ' selected' : ''}`} aria-selected={selected === card.id} aria-label={`${card.type} card ${card.title || 'untitled'}`}
              style={{ left: t.x, top: t.y, width: t.w, height: t.h }} onPointerDown={(e) => {
                select(card.id);
                const target = e.target as HTMLElement;
                if (target.closest('button,input,textarea,select,a,summary,details,.resize,canvas,[role="button"]')) return;
                start(e, card, 'move');
              }} onPointerMove={move} onPointerUp={finish} onPointerCancel={finish}>
              <header className="card-head" tabIndex={0} aria-label={`Move ${card.title || card.type}`} onKeyDown={(e) => keys(e, card)}>
                <span className="card-type">{card.type.replace('-', ' ')}</span>
                <span className="card-title">{card.title || 'Untitled'}</span>
              </header>
              <div className="card-body"><CardBody card={card} snapshot={snapshot} documentId={doc!.id} /></div>
              {snapshot ? <footer className="card-foot"><span className="chip ok">frozen</span><span className="muted">{snapshot.unit} · {snapshot.scope.start} → {snapshot.scope.end}</span></footer> : null}
              {canEdit && !card.locked ? <div className="resize" aria-hidden="true" onPointerDown={(e) => { e.stopPropagation(); start(e, card, 'resize'); }} onPointerMove={move} onPointerUp={finish} onPointerCancel={finish} /> : null}
            </article>
          );
        })}
      </div></div>
    </div></section>
  );
}
