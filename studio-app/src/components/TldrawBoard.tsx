import { useEffect, useRef, useState } from 'react';
import { BaseBoxShapeUtil, HTMLContainer, T, Tldraw, createShapeId, type Editor, type TLShape } from 'tldraw';
import 'tldraw/tldraw.css';
import { useStudio } from '../store';
import { CardBody } from './CardBody';
import type { Transform } from '../types';

declare module 'tldraw' {
  interface TLGlobalShapePropsMap {
    'fireatlas-evidence': { w: number; h: number; cardId: string };
  }
}
type EvidenceShape = TLShape<'fireatlas-evidence'>;
type Bridge = { move(cardId: string, transform: Transform, origin: Transform): void };
const bridges = new WeakMap<Editor, Bridge>();
const shapeId = (cardId: string) => createShapeId(`evidence-${cardId}`);
const linkShapeId = (linkId: string) => createShapeId(`connection-${linkId}`);

function EvidenceCard({ shape }: { shape: EvidenceShape }) {
  const { doc } = useStudio();
  const card = doc?.state.cards[shape.props.cardId];
  if (!doc || !card) return <div>Card unavailable</div>;
  const snapshot = card.snapshot_id ? doc.snapshots?.[card.snapshot_id] || null : null;
  return <HTMLContainer style={{ width: shape.props.w, height: shape.props.h, border: '1px solid #cbd5e1', borderRadius: 12, background: 'white', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
    <div className="card-head"><span className="card-type">{card.type}</span><strong>{card.title}</strong>{card.locked ? <span>Locked</span> : null}</div>
    <div className="card-body" style={{ pointerEvents: 'none' }}><CardBody card={card} snapshot={snapshot} documentId={doc.id} /></div>
    {snapshot ? <div className="card-foot">Frozen evidence · {snapshot.unit}</div> : null}
  </HTMLContainer>;
}
class EvidenceShapeUtil extends BaseBoxShapeUtil<EvidenceShape> {
  static override type = 'fireatlas-evidence' as const;
  static override props = { w: T.number, h: T.number, cardId: T.string };
  override getDefaultProps() { return { w: 360, h: 240, cardId: '' }; }
  override canEdit() { return false; }
  override hideRotateHandle() { return true; }
  override component(shape: EvidenceShape) { return <EvidenceCard shape={shape} />; }
  override getIndicatorPath(shape: EvidenceShape) { const path = new Path2D(); path.rect(0, 0, shape.props.w, shape.props.h); return path; }
  override onTranslateEnd(initial: EvidenceShape, current: EvidenceShape) { this.save(current, initial); }
  override onResizeEnd(initial: EvidenceShape, current: EvidenceShape) { this.save(current, initial); }
  private save(shape: EvidenceShape, initial: EvidenceShape) {
    bridges.get(this.editor)?.move(shape.props.cardId, { x: shape.x, y: shape.y, w: Math.max(160, shape.props.w), h: Math.max(100, shape.props.h) }, { x: initial.x, y: initial.y, w: initial.props.w, h: initial.props.h });
  }
}
const shapeUtils = [EvidenceShapeUtil];

/** The SDK is a presentation adapter. Private revisioned board records remain authoritative. */
export function TldrawBoard() {
  const { doc, caps, transact, select, selected, canEdit, undo, redo, isCurrent, canvasCards } = useStudio();
  const [editor, setEditor] = useState<Editor | null>(null);
  const latest = useRef({ doc, transact, select, canEdit, isCurrent }); latest.current = { doc: doc ? { ...doc, state: { ...doc.state, cards: canvasCards } } : doc, transact, select, canEdit, isCurrent };
  const syncing = useRef(false);
  useEffect(() => {
    if (!editor || !doc) return;
    bridges.set(editor, { move: (id, transform, origin) => {
      const now = latest.current;
      if (!now.doc || !now.canEdit || now.doc.state.cards[id]?.locked) return;
      const card = now.doc.state.cards[id];
      const group = Object.values(now.doc.state.groups || {}).find((g) => g.card_ids.includes(id));
      const resizing = card.transform.w !== transform.w || card.transform.h !== transform.h;
      void now.transact(group && !resizing ? [{ op: 'move_group', id: group.id, dx: transform.x - card.transform.x, dy: transform.y - card.transform.y }] : [{ op: 'move_card', id, transform, layout_origin: origin }]);
    } });
    const unlisten = editor.store.listen(() => {
      if (syncing.current) return;
      const now = latest.current;
      const id = editor.getSelectedShapes().find((s) => s.type === 'fireatlas-evidence') as EvidenceShape | undefined;
      if (now.doc && now.doc.selection.card_id !== (id?.props.cardId || null)) now.select(id?.props.cardId || null);
      try { sessionStorage.setItem(`fireatlas-canvas-camera:${now.doc?.id}`, JSON.stringify(editor.getCamera())); } catch { /* camera is optional per-user state */ }
    }, { source: 'user', scope: 'session' });
    editor.updateInstanceState({ isReadonly: !canEdit });
    const beforeCreate = editor.sideEffects.registerBeforeCreateHandler('shape', (shape) => {
      if (shape.type === 'arrow' && String(shape.id).startsWith('shape:connection-')) return shape;
      if (shape.type !== 'fireatlas-evidence' || !latest.current.doc?.state.cards[(shape as EvidenceShape).props.cardId] || shape.id !== shapeId((shape as EvidenceShape).props.cardId)) throw new Error('Add scientific cards through the Studio card library.');
      return shape;
    });
    const beforeDelete = editor.sideEffects.registerBeforeDeleteHandler('shape', () => syncing.current ? undefined : false);
    const keys = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'z') return;
      if (event.target instanceof HTMLElement && event.target.closest('input,textarea,select')) return;
      event.preventDefault(); event.stopPropagation(); void (event.shiftKey ? redo() : undo());
    };
    window.addEventListener('keydown', keys, true);
    return () => { unlisten(); beforeCreate(); beforeDelete(); bridges.delete(editor); window.removeEventListener('keydown', keys, true); };
  }, [editor, doc?.id, canEdit, undo, redo]);
  useEffect(() => {
    if (!editor || !doc) return;
    syncing.current = true;
    try {
      editor.run(() => {
        const wanted = new Set(doc.state.order.map(shapeId));
        Object.values(doc.state.connections).forEach((link) => wanted.add(linkShapeId(link.id)));
        // Server deletions must bypass the user-facing delete guard.
        for (const shape of editor.getCurrentPageShapes()) if (!wanted.has(shape.id)) editor.store.remove([shape.id]);
        for (const card of Object.values(canvasCards)) {
          const shape = { id: shapeId(card.id), type: 'fireatlas-evidence' as const, x: card.transform.x, y: card.transform.y, isLocked: Boolean(card.locked), props: { w: card.transform.w, h: card.transform.h, cardId: card.id } };
          if (editor.getShape(shape.id)) editor.updateShape(shape); else editor.createShape(shape);
        }
        for (const link of Object.values(doc.state.connections)) {
          const a = canvasCards[link.source], b = canvasCards[link.target];
          if (!a || !b) continue;
          const start = { x: a.transform.x + a.transform.w, y: a.transform.y + a.transform.h / 2 };
          const end = { x: b.transform.x, y: b.transform.y + b.transform.h / 2 };
          const arrow: any = { id: linkShapeId(link.id), type: 'arrow', x: start.x, y: start.y, isLocked: true,
            props: { start: { x: 0, y: 0 }, end: { x: end.x - start.x, y: end.y - start.y }, bend: 0, color: link.kind === 'scale' ? 'orange' : link.kind === 'compare' ? 'violet' : 'blue', labelColor: 'black', fill: 'none', dash: 'draw', size: 's', arrowheadStart: 'none', arrowheadEnd: 'arrow', font: 'sans', text: '', align: 'middle', labelPosition: 0.5, scale: 1 } };
          if (editor.getShape(arrow.id)) editor.updateShape(arrow); else editor.createShape(arrow);
        }
        if (selected && doc.state.cards[selected]) editor.setSelectedShapes([shapeId(selected)]); else editor.selectNone();
      }, { history: 'ignore' });
    } finally { syncing.current = false; }
  }, [editor, doc, selected, canvasCards]);
  const licenseKey = String(caps?.canvas?.public_license_key || '');
  return <section aria-label="Infinite evidence canvas" className="sdk-board"><div className="row sdk-toolbar"><button className="btn" onClick={() => editor?.setCurrentTool('select')}>Select cards</button><button className="btn" onClick={() => editor?.setCurrentTool('hand')}>Pan canvas</button><button className="btn" onClick={() => editor?.zoomToFit({ animation: { duration: 0 } })}>Fit cards</button><button className="btn" onClick={() => editor?.zoomIn()}>Zoom in</button><button className="btn" onClick={() => editor?.zoomOut()}>Zoom out</button><button className="btn" disabled={!canEdit} onClick={() => { const c = editor?.getCamera(); if (c) void transact([{ op: 'set_viewport', viewport: { x: c.x * c.z, y: c.y * c.z, zoom: Math.max(0.1, Math.min(4, c.z)) } }]); }}>Save canvas view</button><button className="btn" onClick={() => { const v = doc?.state.viewport; if (v) editor?.setCamera({ x: v.x / v.zoom, y: v.y / v.zoom, z: v.zoom }); }}>Restore saved view</button><span className="muted">Inspect and edit content in the rail or linear outline.</span><span className="muted" data-connection-count>{Object.keys(doc?.state.connections || {}).length} visible board links</span></div><div style={{ position: 'relative', height: 640 }}><Tldraw licenseKey={licenseKey} shapeUtils={shapeUtils} hideUi onMount={(mounted) => { setEditor(mounted); try { const camera = JSON.parse(sessionStorage.getItem(`fireatlas-canvas-camera:${doc?.id}`) || 'null'); if (camera) mounted.setCamera(camera); else if (doc?.state.viewport) { const v = doc.state.viewport; mounted.setCamera({ x: v.x / v.zoom, y: v.y / v.zoom, z: v.zoom }); } } catch { /* use SDK default camera */ } }} /></div></section>;
}
