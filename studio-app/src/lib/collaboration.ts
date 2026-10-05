/** Managed presence and field-level CRDT canvas layout. Scientific values stay on the owned server. */
import { createClient, LiveMap } from '@liveblocks/client';
import { SharedLayout, type LayoutFields } from './sharedLayout';
import type { DocumentView } from '../types';
export type Presence = { card: string | null; cursor: { x: number; y: number } | null; chapter: string | null };
export async function connectRoom(id: string, authorize: () => Promise<{ token: string }>, callbacks: {
  status(value: string): void; others(value: { user: string; presence: Presence }[]): void; changed(): void;
  layout(layout: SharedLayout): void;
}) {
  const client = createClient({ authEndpoint: async (requested) => {
    if (requested !== id) throw new Error('Only the applied owned room can be authorized.');
    return authorize();
  } });
  const { room, leave } = client.enterRoom<Presence, { revisions: LiveMap<string, number>; layout: LayoutFields }>(id, {
    initialPresence: { card: null, cursor: null, chapter: null }, initialStorage: { revisions: new LiveMap(), layout: new LiveMap() }
  });
  let closed = false; let layout: SharedLayout | null = null; let revisions: LiveMap<string, number> | null = null;
  const unsubscribers = [
    room.subscribe('status', (status) => { callbacks.status(status); if (status === 'connected') callbacks.changed(); }),
    room.subscribe('others', (others) => callbacks.others(others.map((user) => ({ user: String(user.id || user.connectionId).slice(-6), presence: user.presence })))),
    room.subscribe('event', () => callbacks.changed()),
    room.subscribe('error', () => callbacks.status('Authorization or transport failed; saved editing remains available.'))
  ];
  void room.getStorage().then(({ root }) => {
    if (closed) return;
    revisions = root.get('revisions');
    if (!root.get('layout')) root.set('layout', new LiveMap());
    layout = new SharedLayout(root.get('layout'), (fn) => room.batch(fn));
    callbacks.layout(layout);
    unsubscribers.push(room.subscribe(root.get('layout'), () => { if (!closed && layout) callbacks.layout(layout); }, { isDeep: true }));
    unsubscribers.push(room.subscribe(revisions, () => callbacks.changed()));
  }).catch(() => callbacks.status('Shared layout unavailable; saved editing remains usable.'));
  return {
    reconcile(document: DocumentView, writable: boolean) { if (!closed) layout?.reconcile(document, writable); },
    presence(value: Partial<Presence>) { if (!closed) room.updatePresence(value); },
    changed(documentId: string, revision: number, writable: boolean) {
      if (closed || !writable) return;
      // Only monotonically increasing revision hints enter the shared CRDT, never rows, receipts or tokens.
      if (revisions && (revisions.get(documentId) || 0) < revision) revisions.set(documentId, revision);
      room.broadcastEvent({ type: 'revision', document: documentId, revision });
    },
    close() { closed = true; unsubscribers.forEach((off) => off()); leave(); }
  };
}
