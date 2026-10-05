import { describe, expect, it } from 'vitest';
import { LiveMap } from '@liveblocks/client';
import { SharedLayout, type LayoutFields } from './sharedLayout';
import type { DocumentView } from '../types';
const t = { x: 20, y: 40, w: 360, h: 240 };
const board = (): DocumentView => ({ id: 'one', revision: 1, state: { cards: { a: { id: 'a', transform: { ...t } }, b: { id: 'b', transform: { ...t } } }, groups: { g: { card_ids: ['a', 'b'] } } } } as unknown as DocumentView);
const setup = () => { const fields: LayoutFields = new LiveMap(); const one = new SharedLayout(fields, (fn) => fn()), two = new SharedLayout(fields, (fn) => fn()); const doc = board(); one.reconcile(doc, true); return { one, two, doc, fields }; };
describe('official LiveMap/LiveObject layout projection (no managed transport)', () => {
  it('merges different fields on one card from two gesture origins without modifying evidence', () => {
    const { one, two, doc } = setup(); const before = structuredClone(doc);
    one.apply([{ op: 'move_card', id: 'a', layout_origin: t, transform: { ...t, x: 100 } }], doc);
    two.apply([{ op: 'move_card', id: 'a', layout_origin: t, transform: { ...t, w: 500 } }], doc);
    expect(one.transforms(doc).a).toMatchObject({ x: 100, w: 500 });
    expect(two.projection(doc)[0].transform).toMatchObject({ x: 100, w: 500 });
    expect(doc).toEqual(before);
    one.history('undo'); expect(two.transforms(doc).a).toMatchObject({ x: 20, w: 500 });
    one.history('redo'); expect(two.transforms(doc).a.x).toBe(100);
  });
  it('refuses undo that would overwrite another editor and preserves the draft', () => {
    const { one, two, doc } = setup();
    one.apply([{ op: 'move_card', id: 'a', transform: { ...t, x: 100 } }], doc);
    two.apply([{ op: 'move_card', id: 'a', transform: { ...t, x: 200 } }], doc);
    expect(() => one.history('undo')).toThrow('collaborator');
    expect(one.transforms(doc).a.x).toBe(200);
  });
  it('rebases independent saved fields but refuses conflicts with saved geometry', () => {
    const { one, doc } = setup();
    one.apply([{ op: 'move_card', id: 'a', transform: { ...t, x: 100 } }], doc);
    const fresh = board(); fresh.state.cards.a.transform.h = 300;
    expect(one.projection(fresh)[0].transform).toMatchObject({ x: 100, h: 300 });
    fresh.state.cards.a.transform.x = 150;
    expect(() => one.projection(fresh)).toThrow('same field');
  });
  it('moves groups atomically and rejects locked, invalid or unknown members', () => {
    const { one, doc, fields } = setup();
    doc.state.cards.b.locked = true;
    expect(() => one.apply([{ op: 'move_group', id: 'g', dx: 50, dy: 20 }], doc)).toThrow('Locked');
    expect(fields.get('a:x')?.get('value')).toBe(20);
    doc.state.cards.b.locked = false;
    one.apply([{ op: 'move_group', id: 'g', dx: 50, dy: 20 }], doc);
    expect(one.transforms(doc).b).toMatchObject({ x: 70, y: 60 });
    expect(() => one.apply([{ op: 'move_card', id: 'a', transform: { ...t, x: Infinity } }], doc)).toThrow('bounds');
    expect(one.apply([{ op: 'set_study' }], doc)).toBe(false);
  });
  it('checkpoint/reconnect retain pending edits while deleting removed-card coordinates', () => {
    const { one, doc, fields } = setup();
    one.apply([{ op: 'move_card', id: 'a', transform: { ...t, x: 100 } }], doc);
    const reconnect = new SharedLayout(fields, (fn) => fn()); reconnect.reconcile(doc, true);
    expect(reconnect.transforms(doc).a.x).toBe(100);
    doc.state.cards.a.transform.x = 100; delete doc.state.cards.b;
    one.reconcile(doc, true); one.checkpoint();
    expect(one.transforms(doc)).toEqual({}); expect(fields.has('b:x')).toBe(false);
    one.history('undo'); expect(fields.get('a:x')?.get('value')).toBe(100);
  });
  it('read-only reconciliation does not seed provider storage', () => {
    const fields: LayoutFields = new LiveMap(); const viewer = new SharedLayout(fields, (fn) => fn());
    viewer.reconcile(board(), false); expect(fields.size).toBe(0);
  });
});
