import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { LiveMap } from '@liveblocks/client';
import { SharedLayout } from './sharedLayout';
import { StudioProvider, useStudio, type StudioValue } from '../store';
import { RoomPanel } from '../components/RoomPanel';
import { api } from '../api';
import type { DocumentView } from '../types';
const transport = vi.hoisted(() => ({ callback: null as ((x: any) => void) | null, shared: null as any, close: vi.fn() }));
vi.mock('./collaboration', () => ({ connectRoom: vi.fn(async (_id, _auth, callbacks) => {
  transport.callback = callbacks.layout; callbacks.layout(transport.shared);
  return { reconcile: (doc: DocumentView, writable: boolean) => { transport.shared.reconcile(doc, writable); callbacks.layout(transport.shared); }, close: transport.close, presence: vi.fn(), changed: vi.fn() };
}) }));
vi.mock('../api', () => ({ api: { getDocument: vi.fn(), comments: vi.fn(), presenter: vi.fn(), authorizeRoom: vi.fn(), transact: vi.fn() } }));
let value: StudioValue, root: ReturnType<typeof createRoot>, host: HTMLDivElement;
const board = (): DocumentView => ({ id: 'board', revision: 1, context_revision: 1, role: 'owner', owner: true, state: { cards: { card: { id: 'card', transform: { x: 20, y: 40, w: 360, h: 240 } } }, connections: {}, order: ['card'], study: {} }, selection: { card_id: null }, room: { id: 'room', document_id: 'board', adapter: 'liveblocks', members: [{ principal: 'owner', role: 'owner', you: true }] } } as unknown as DocumentView);
function Probe() { value = useStudio(); return value.doc ? <RoomPanel expanded /> : null; }
beforeEach(async () => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true; vi.resetAllMocks();
  const doc = board(); transport.shared = new SharedLayout(new LiveMap(), (fn) => { fn(); transport.callback?.(transport.shared); }); transport.shared.reconcile(doc, true);
  vi.mocked(api.getDocument).mockResolvedValue(doc); vi.mocked(api.comments).mockResolvedValue({ comments: [] }); vi.mocked(api.presenter).mockResolvedValue({ changed: false } as any);
  host = document.createElement('div'); document.body.append(host); root = createRoot(host);
  act(() => root.render(<StudioProvider><Probe /></StudioProvider>)); await act(async () => value.open(doc));
});
afterEach(() => { act(() => root.unmount()); host.remove(); transport.callback = null; });
it('managed layout controls route gesture drafts through Storage and save one checked checkpoint (mocked transport)', async () => {
  const mode = host.querySelector('input[type=checkbox]') as HTMLInputElement; // Follow-presenter precedes edit mode.
  expect(mode).toBeTruthy();
  const edit = [...host.querySelectorAll('label')].find((x) => x.textContent?.includes('Edit shared layout draft'))!.querySelector('input')!;
  await act(async () => edit.click());
  await act(async () => { await value.transact([{ op: 'move_card', id: 'card', transform: { x: 100, y: 40, w: 360, h: 240 } }]); });
  expect(value.canvasCards.card.transform.x).toBe(100); expect(value.doc?.state.cards.card.transform.x).toBe(20); expect(api.transact).not.toHaveBeenCalled();
  vi.mocked(api.transact).mockImplementation(async (_id, revision, ops) => { const fresh = board(); fresh.revision = revision + 1; fresh.state.cards.card.transform = (ops[0] as any).transform; return fresh; });
  await act(async () => [...host.querySelectorAll('button')].find((b) => b.textContent === 'Save merged layout')!.click());
  expect(api.transact).toHaveBeenCalledOnce(); expect(value.doc?.revision).toBe(2); expect(value.doc?.state.cards.card.transform.x).toBe(100);
  expect(host.textContent).toContain('one reversible document transaction');
});
it('viewer has no layout write controls and stale room callbacks cannot repaint another board', async () => {
  await act(async () => value.open({ ...board(), role: 'viewer', owner: false }));
  expect([...host.querySelectorAll('label')].some((x) => x.textContent?.includes('Edit shared layout draft'))).toBe(false);
  const save = [...host.querySelectorAll('button')].find((b) => b.textContent === 'Save merged layout')!; expect(save.disabled).toBe(true);
  const old = transport.callback;
  await act(async () => value.open({ ...board(), id: 'other', room: null }));
  act(() => old?.(transport.shared)); expect(value.doc?.id).toBe('other'); expect(transport.close).toHaveBeenCalled();
  expect(value.canvasCards.card.transform.x).toBe(20);
});
