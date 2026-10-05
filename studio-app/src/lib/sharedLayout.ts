/** Provider CRDT presentation draft. No scientific values or private evidence enter Storage. */
import { LiveMap, LiveObject } from '@liveblocks/client';
import type { DocumentView, Transform } from '../types';
export const FIELDS = ['x', 'y', 'w', 'h', 'rotation'] as const;
type Field = typeof FIELDS[number];
export type LayoutFields = LiveMap<string, LiveObject<{ base: number; value: number }>>;
export interface LayoutBridge {
  apply(ops: unknown[], document: DocumentView): boolean;
  history(direction: 'undo' | 'redo'): void;
}
const value = (t: Transform, f: Field) => f === 'rotation' ? t.rotation || 0 : t[f];
const key = (id: string, f: Field) => `${id}:${f}`;
const valid = (f: Field, n: unknown): n is number => typeof n === 'number' && Number.isFinite(n) && (
  f === 'rotation' ? Math.abs(n) <= 360 : f === 'w' || f === 'h' ? n >= 40 && n <= 4000 : n >= -100000 && n <= 100000);
type Change = { key: string; before: number; after: number };
export class SharedLayout implements LayoutBridge {
  private undo: Change[][] = []; private redo: Change[][] = [];
  constructor(readonly fields: LayoutFields, private batch: (fn: () => void) => void) {}
  private field(k: string) { const item = this.fields.get(k); return item instanceof LiveObject ? item : null; }
  reconcile(document: DocumentView, writable: boolean) {
    if (!writable) return;
    this.batch(() => {
      for (const card of Object.values(document.state.cards)) for (const f of FIELDS) {
        const k = key(card.id, f), current = value(card.transform, f), item = this.field(k);
        if (!item) this.fields.set(k, new LiveObject({ base: current, value: current }));
        else if (item.get('base') === item.get('value')) item.update({ base: current, value: current });
        else if (item.get('value') === current) item.set('base', current);
      }
      for (const k of this.fields.keys()) if (!document.state.cards[k.slice(0, k.lastIndexOf(':'))]) this.fields.delete(k);
    });
  }
  transforms(document: DocumentView): Record<string, Transform> {
    const out: Record<string, Transform> = {};
    for (const card of Object.values(document.state.cards)) {
      if (card.locked) continue;
      const t = { ...card.transform };
      let changed = false;
      for (const f of FIELDS) {
        const item = this.field(key(card.id, f));
        const next = item?.get('value');
        if (item && valid(f, next) && next !== item.get('base')) { t[f] = next; changed = true; }
      }
      if (changed) out[card.id] = t;
    }
    return out;
  }
  apply(ops: unknown[], document: DocumentView): boolean {
    const list = ops as { op: string; id: string; transform?: Transform; layout_origin?: Transform; dx?: number; dy?: number }[];
    if (!list.length || list.some((op) => !['move_card', 'move_group'].includes(op.op))) return false;
    const staged = new Map<string, Transform>();
    const displayed = this.transforms(document);
    for (const op of list) {
      const ids = op.op === 'move_group' ? document.state.groups?.[op.id]?.card_ids : [op.id];
      if (!ids?.length) throw new Error('The shared group is no longer available.');
      for (const id of ids) {
        const card = document.state.cards[id];
        if (!card || card.locked) throw new Error('Locked or removed cards cannot enter a layout draft.');
        const before = staged.get(id) || displayed[id] || card.transform;
        let next = op.op === 'move_group' ? { ...before, x: before.x + Number(op.dx), y: before.y + Number(op.dy) } : op.transform!;
        if (!next || FIELDS.some((f) => !valid(f, value(next, f)))) throw new Error('The shared transform is outside the supported canvas bounds.');
        if (op.op === 'move_card' && op.layout_origin) {
          next = { ...before };
          for (const f of FIELDS) if (value(op.transform!, f) !== value(op.layout_origin, f)) next[f] = value(op.transform!, f);
        }
        staged.set(id, next);
      }
    }
    const changes: Change[] = [];
    for (const [id, next] of staged) for (const f of FIELDS) {
      const k = key(id, f), before = this.field(k)?.get('value') ?? value(document.state.cards[id].transform, f), after = value(next, f);
      if (before !== after) changes.push({ key: k, before, after });
    }
    this.batch(() => { for (const c of changes) {
      const item = this.field(c.key);
      if (item) item.set('value', c.after);
      else this.fields.set(c.key, new LiveObject({ base: c.before, value: c.after }));
    } });
    if (changes.length) { this.undo.push(changes); this.redo = []; }
    return true;
  }
  history(direction: 'undo' | 'redo') {
    const from = direction === 'undo' ? this.undo : this.redo, to = direction === 'undo' ? this.redo : this.undo;
    const changes = from.at(-1);
    if (!changes) return;
    const expected = direction === 'undo' ? 'after' : 'before', next = direction === 'undo' ? 'before' : 'after';
    if (changes.some((c) => this.field(c.key)?.get('value') !== c[expected])) throw new Error('A collaborator changed the same layout field. Your undo is retained; inspect the merged layout first.');
    this.batch(() => { for (const c of changes) this.field(c.key)!.set('value', c[next]); });
    from.pop(); to.push(changes);
  }
  checkpoint() { this.undo = []; this.redo = []; }
  projection(document: DocumentView) {
    const ops: { op: string; id: string; transform: Transform }[] = [];
    for (const card of Object.values(document.state.cards)) {
      const transform = { ...card.transform }; let changed = false;
      for (const f of FIELDS) {
        const item = this.field(key(card.id, f)); if (!item || item.get('base') === item.get('value')) continue;
        const desired = item.get('value'), current = value(card.transform, f);
        if (card.locked || !valid(f, desired)) throw new Error('A locked card or invalid shared field cannot be saved.');
        if (current !== item.get('base') && current !== desired) throw new Error('A saved layout changed the same field. The shared draft is retained for inspection.');
        if (current !== desired) { transform[f] = desired; changed = true; }
      }
      if (changed) ops.push({ op: 'move_card', id: card.id, transform });
    }
    if (ops.length > 50) throw new Error('Save at most 50 changed cards in a shared layout; no cards were sampled.');
    return ops;
  }
}
