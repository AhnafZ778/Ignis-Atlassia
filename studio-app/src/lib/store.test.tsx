import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StudioProvider, useStudio, type StudioValue } from '../store';
import type { DocumentView } from '../types';

let value: StudioValue;
let root: ReturnType<typeof createRoot>;
function Probe() { value = useStudio(); return null; }
const board = (id = 'one', revision = 1): DocumentView => ({ id, revision, context_revision: revision, role: 'owner', state: {
  study: {}, order: ['source', 'target'], cards: { source: { id: 'source', follow: 'board' }, target: { id: 'target', follow: 'selected', follow_card_id: 'source' } }, connections: {}
}, selection: { card_id: null }, snapshots: {} } as unknown as DocumentView);
beforeEach(() => { (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true; root = createRoot(document.createElement('div')); act(() => root.render(<StudioProvider><Probe /></StudioProvider>)); });
afterEach(() => act(() => root.unmount()));
describe('transient linked selection identity', () => {
  it('isolates provider layout from scientific state and discards delayed geometry after board switching', () => {
    const doc = board(); act(() => value.open(doc));
    const shape = { x: 20, y: 30, w: 360, h: 240 };
    act(() => value.setSharedGeometry('one', { source: shape }));
    expect(value.canvasCards.source.transform).toEqual(shape);
    expect(value.doc?.state).toEqual(doc.state);
    act(() => value.open(board('two')));
    act(() => value.setSharedGeometry('one', { source: shape }));
    expect(value.canvasCards.source.transform).toBeUndefined();
  });
  it('routes layout drafts and their history through the installed provider adapter', async () => {
    act(() => value.open(board()));
    const bridge = { apply: vi.fn(() => true), history: vi.fn() };
    act(() => value.registerLayoutBridge(bridge));
    await act(async () => { await value.transact([{ op: 'move_card', id: 'source' }]); await value.undo(); await value.redo(); });
    expect(bridge.apply).toHaveBeenCalledTimes(1);
    expect(bridge.history.mock.calls).toEqual([['undo'], ['redo']]);
    expect(value.doc?.revision).toBe(1);
    act(() => value.open(board('two')));
    expect(value.canvasCards.source.transform).toBeUndefined();
  });
  it('updates compatible displays without changing the scientific document', () => {
    const doc = board(); act(() => value.open(doc));
    act(() => value.publishSelection('source', { start: '2024-07-24', end: '2024-07-26', day: '2024-07-24' }, 1, 'one'));
    expect(value.displaySelections.target.end).toBe('2024-07-26');
    expect(value.doc?.state).toEqual(doc.state);
    expect(value.doc?.revision).toBe(1);
  });
  it('rejects delayed events from another board even when IDs and revisions coincide', () => {
    act(() => value.open(board())); const pending = value.publishSelection;
    act(() => value.open(board('two')));
    act(() => pending('source', { day: '2024-07-24' }, 1, 'one'));
    expect(value.displaySelections).toEqual({});
  });
  it('clears highlights on a changed applied context and rejects old context events', () => {
    act(() => value.open(board()));
    act(() => value.publishSelection('source', { cell: '1:2', day: '2024-07-24' }, 1, 'one'));
    expect(value.displaySelections.target.cell).toBe('1:2');
    act(() => value.open(board('one', 2)));
    act(() => value.publishSelection('source', { cell: '3:4' }, 1, 'one'));
    expect(value.displaySelections).toEqual({});
  });
});
