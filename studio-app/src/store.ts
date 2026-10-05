import { createContext, createElement, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import { api, ApiError } from './api';
import type { Capabilities, DocumentView, Snapshot, SnapshotReport, DisplaySelection, Transform, Card } from './types';
import type { LayoutBridge } from './lib/sharedLayout';
import { selectionTargets } from './lib/graph';

export interface Conflict { message: string; ops: unknown[]; currentRevision?: number }
export interface StudioValue {
  doc: DocumentView | null; caps: Capabilities | null; selected: string | null; reports: Record<string, SnapshotReport>;
  notice: string | null; busy: boolean; conflict: Conflict | null; canEdit: boolean;
  displaySelections: Record<string, DisplaySelection>;
  canvasCards: Record<string, Card>;
  setSharedGeometry(documentId: string, transforms: Record<string, Transform>): void;
  registerLayoutBridge(bridge: LayoutBridge | null): void;
  publishSelection(origin: string, selection: DisplaySelection, contextRevision: number, documentId: string): void;
  open(doc: DocumentView): void; setCaps(caps: Capabilities): void; isCurrent(id: string, contextRevision?: number): boolean;
  transact(ops: unknown[], extra?: Record<string, unknown>): Promise<DocumentView | null>;
  undo(): Promise<void>; redo(): Promise<void>; reload(): Promise<boolean>; resolveConflict(choice: 'reload' | 'retry'): Promise<void>;
  select(id: string | null): void; notify(message: string | null): void; addSnapshot(snapshot: Snapshot): void; loadReport(id: string): Promise<SnapshotReport | null>;
}

const Context = createContext<StudioValue | null>(null);
export const useStudio = (): StudioValue => {
  const value = useContext(Context);
  if (!value) throw new Error('Studio state is not available.');
  return value;
};

/** Transactions never return the snapshot index; keep what we have and merge anything new. */
export function mergeDocument(previous: DocumentView | null, next: DocumentView): DocumentView {
  return { ...next, room: next.room === undefined && previous?.id === next.id ? previous.room : next.room, snapshots: { ...(previous && previous.id === next.id ? previous.snapshots : {}), ...(next.snapshots || {}) } };
}

export function StudioProvider({ children }: { children: ReactNode }) {
  const [doc, setDoc] = useState<DocumentView | null>(null);
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [reports, setReports] = useState<Record<string, SnapshotReport>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState<Conflict | null>(null);
  const [displaySelections, setDisplaySelections] = useState<Record<string, DisplaySelection>>({});
  const [sharedGeometry, setGeometry] = useState<Record<string, Transform>>({});
  const layoutBridge = useRef<LayoutBridge | null>(null);
  const docRef = useRef<DocumentView | null>(null);
  const epoch = useRef(0);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const timer = useRef<number | undefined>(undefined);

  const commit = useCallback((next: DocumentView | null) => {
    if (docRef.current?.id !== next?.id) { setGeometry({}); layoutBridge.current = null; }
    if (docRef.current?.id !== next?.id || docRef.current?.context_revision !== next?.context_revision) setDisplaySelections({});
    docRef.current = next; setDoc(next);
  }, []);
  const setSharedGeometry = useCallback((documentId: string, transforms: Record<string, Transform>) => {
    if (docRef.current?.id === documentId) setGeometry(transforms);
  }, []);
  const registerLayoutBridge = useCallback((bridge: LayoutBridge | null) => { layoutBridge.current = bridge; }, []);
  const publishSelection = useCallback((origin: string, selection: DisplaySelection, contextRevision: number, documentId: string) => {
    const current = docRef.current;
    if (!current || current.id !== documentId || current.context_revision !== contextRevision || !current.state.cards[origin]) return;
    const ids = selectionTargets(current.state, origin, current.snapshots);
    setDisplaySelections((previous) => ({ ...previous, ...Object.fromEntries(ids.map((id) => [id, { ...selection }])) }));
  }, []);
  const notify = useCallback((message: string | null) => {
    setNotice(message);
    window.clearTimeout(timer.current);
    if (message) timer.current = window.setTimeout(() => setNotice(null), 6000);
  }, []);

  const fillSnapshots = useCallback(async (next: DocumentView): Promise<DocumentView> => {
    const have = next.snapshots || {};
    const missing = Object.values(next.state.cards).some((c) => c.snapshot_id && !have[c.snapshot_id]);
    if (!missing) return next;
    try { return mergeDocument(next, await api.getDocument(next.id)); } catch { return next; }
  }, []);

  const isCurrent = useCallback((id: string, contextRevision?: number) => docRef.current?.id === id && (contextRevision === undefined || docRef.current?.context_revision === contextRevision), []);
  const open = useCallback((next: DocumentView) => { epoch.current++; setReports({}); setBusy(false); setConflict(null); setSelected(next.selection?.card_id ?? null); commit(mergeDocument(docRef.current, next)); }, [commit]);

  const run = useCallback(async (ops: unknown[], extra: Record<string, unknown>, target: string, requestEpoch: number): Promise<DocumentView | null> => {
    const current = docRef.current;
    if (!current || current.id !== target || epoch.current !== requestEpoch) return null;
    try {
      const next = await api.transact(current.id, current.revision, ops, extra);
      if (epoch.current !== requestEpoch) return null;
      const merged = await fillSnapshots(mergeDocument(docRef.current, next));
      if (epoch.current !== requestEpoch) return null;
      commit(merged);
      return merged;
    } catch (error) {
      if (epoch.current !== requestEpoch) return null;
      if (error instanceof ApiError && error.isConflict && error.details?.current_revision !== undefined) {
        setConflict({ message: error.message, ops, currentRevision: error.details.current_revision });
      } else if (error instanceof ApiError) {
        setConflict({ message: error.message + ' Your edit is retained for retry.', ops });
        notify(error.message);
      } else {
        setConflict({ message: 'The save failed. Your edit is retained for retry.', ops });
        notify('Something went wrong while saving.');
      }
      return null;
    }
  }, [commit, fillSnapshots, notify]);

  const transact = useCallback((ops: unknown[], extra: Record<string, unknown> = {}) => {
    const target = docRef.current?.id;
    if (!target) return Promise.resolve(null);
    const current = docRef.current!;
    if (layoutBridge.current && (current.role === 'owner' || current.role === 'editor')) {
      try { if (layoutBridge.current.apply(ops, current)) return Promise.resolve(current); }
      catch (error) { notify(error instanceof Error ? error.message : 'Shared layout edit failed.'); return Promise.resolve(null); }
    }
    const requestEpoch = epoch.current;
    setBusy(true);
    // The gesture origin is a presentation-only merge hint, never part of the domain API.
    const cleanOps = ops.map((raw) => { const op = { ...(raw as Record<string, unknown>) }; delete op.layout_origin; return op; });
    const job = queue.current.then(() => run(cleanOps, extra, target, requestEpoch));
    const completed = job.catch(() => null).finally(() => { if (epoch.current === requestEpoch && queue.current === completed) setBusy(false); });
    queue.current = completed;
    return job;
  }, [run, notify]);

  const reload = useCallback(async () => {
    const current = docRef.current;
    if (!current) return false;
    const requestEpoch = epoch.current;
    try { const next = await api.getDocument(current.id); if (epoch.current === requestEpoch) { commit(mergeDocument(null, next)); setConflict(null); return true; } } catch (error) { if (epoch.current === requestEpoch) notify(error instanceof ApiError ? error.message : 'Could not reload the board.'); }
    return false;
  }, [commit, notify]);

  const history = useCallback((action: 'undo' | 'redo'): Promise<void> => {
    const target = docRef.current?.id;
    if (!target) return Promise.resolve();
    if (layoutBridge.current) {
      try { layoutBridge.current.history(action); } catch (error) { notify(error instanceof Error ? error.message : 'Shared layout history failed.'); }
      return Promise.resolve();
    }
    const requestEpoch = epoch.current;
    setBusy(true);
    const job = queue.current.then(async () => {
      const current = docRef.current;
      if (!current || current.id !== target || epoch.current !== requestEpoch) return;
      try {
        const result = await api[action](target);
        if (epoch.current !== requestEpoch) return;
        const next = await fillSnapshots(mergeDocument(docRef.current, result));
        if (epoch.current === requestEpoch) commit(next);
      } catch (error) { if (epoch.current === requestEpoch) notify(error instanceof ApiError ? error.message : `Nothing to ${action}.`); }
    });
    const completed = job.finally(() => { if (epoch.current === requestEpoch && queue.current === completed) setBusy(false); });
    queue.current = completed;
    return job;
  }, [commit, fillSnapshots, notify]);
  const undo = useCallback(() => history('undo'), [history]);

  const resolveConflict = useCallback(async (choice: 'reload' | 'retry') => {
    const pending = conflict;
    if (!pending) return;
    const requestEpoch = epoch.current;
    const refreshed = await reload();
    if (!refreshed || epoch.current !== requestEpoch) return;
    if (choice === 'retry') await transact(pending.ops, { allow_merge: true });
  }, [conflict, reload, transact]);
  const redo = useCallback(() => history('redo'), [history]);

  const select = useCallback((id: string | null) => {
    setSelected(id);
    const current = docRef.current;
    if (current) { const selection = { ...current.selection, document_revision: current.revision, card_id: id }; commit({ ...current, selection }); api.patchDocument(current.id, { selection: { document_revision: current.revision, card_id: id } }).catch(() => undefined); }
  }, [commit]);

  const addSnapshot = useCallback((snapshot: Snapshot) => {
    const current = docRef.current;
    if (current) commit({ ...current, snapshots: { ...(current.snapshots || {}), [snapshot.id]: snapshot } });
  }, [commit]);

  const loadReport = useCallback(async (id: string) => {
    const current = docRef.current;
    if (!current) return null;
    const requestEpoch = epoch.current;
    try {
      const report = await api.snapshotReport(current.id, id);
      if (epoch.current !== requestEpoch) return null;
      setReports((all) => ({ ...all, [id]: report }));
      return report;
    } catch { return null; }
  }, []);

  const value = useMemo<StudioValue>(() => ({
    doc, caps, selected, reports, notice, busy, conflict, canEdit: doc?.role === 'owner' || doc?.role === 'editor',
    open, setCaps, isCurrent, transact, undo, redo, reload, resolveConflict, select, notify, addSnapshot, loadReport, displaySelections, publishSelection,
    canvasCards: Object.fromEntries(Object.entries(doc?.state.cards || {}).map(([id, card]) => [id, sharedGeometry[id] ? { ...card, transform: sharedGeometry[id] } : card])),
    setSharedGeometry, registerLayoutBridge
  }), [doc, caps, selected, reports, notice, busy, conflict, open, transact, undo, redo, reload, resolveConflict, select, notify, addSnapshot, loadReport, displaySelections, publishSelection, sharedGeometry, setSharedGeometry, registerLayoutBridge]);

  return createElement(Context.Provider, { value }, children);
}
