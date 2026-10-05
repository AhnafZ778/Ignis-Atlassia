import type { Card, Connection, DocState, Snapshot } from '../types';

export const MAX_CARDS = 100;
export const MAX_CONNECTIONS = 300;

const FAMILY: Record<string, string> = {
  replay: 'daily', persistence: 'daily', compare: 'daily', missingness: 'daily', calendar: 'daily', harmonized: 'daily', observations: 'daily',
  research: 'research', exposure: 'research', sensitivity: 'research'
};

export class CycleError extends Error {}

const sorted = (values: string[]) => [...values].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));

/** Kahn ordering with the same tie-breaking as fireatlas/studio/graph.py::topological_order. */
export function topologicalOrder(cards: Record<string, unknown>, connections: Record<string, Pick<Connection, 'source' | 'target'> | undefined>): string[] {
  const indegree: Record<string, number> = {};
  const outgoing: Record<string, string[]> = {};
  for (const id of Object.keys(cards)) { indegree[id] = 0; outgoing[id] = []; }
  for (const item of Object.values(connections)) {
    if (!item) continue;
    if (!(item.source in cards) || !(item.target in cards)) throw new Error('A connection refers to a missing card.');
    outgoing[item.source].push(item.target);
    indegree[item.target] += 1;
  }
  const ready = sorted(Object.keys(indegree).filter((id) => indegree[id] === 0));
  const order: string[] = [];
  while (ready.length) {
    const current = ready.shift() as string;
    order.push(current);
    for (const target of sorted(outgoing[current])) {
      indegree[target] -= 1;
      if (indegree[target] === 0) ready.push(target);
    }
  }
  if (order.length !== Object.keys(cards).length) throw new CycleError('Card connections must not form a cycle.');
  return order;
}

export const effectiveStudy = (card: Partial<Card>, state: Pick<DocState, 'study' | 'cards'>, seen = new Set<string>()): DocState['study'] => {
  if (card.id && seen.has(card.id)) return state.study || {};
  if (card.id) seen.add(card.id);
  if (card.follow === 'pinned' && card.pinned_study) return card.pinned_study;
  if (card.follow === 'selected' && card.follow_card_id && state.cards?.[card.follow_card_id]) return effectiveStudy(state.cards[card.follow_card_id], state, seen);
  return state.study || {};
};
const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

/** Reasons a link is incompatible; mirrors fireatlas/studio/graph.py::compatibility. Empty means valid. */
export function compatibility(source: Partial<Card>, target: Partial<Card>, kind: Connection['kind'], state: Pick<DocState, 'study' | 'cards'>, snapshots: Record<string, Pick<Snapshot, 'release_id' | 'unit'>> = {}): string[] {
  const reasons: string[] = [];
  const ca = effectiveStudy(source, state).context || {};
  const cb = effectiveStudy(target, state).context || {};
  if (Object.keys(ca).length && Object.keys(cb).length) {
    if (!same(ca.region, cb.region)) reasons.push('Regions differ.');
    if (!same(ca.bbox, cb.bbox)) reasons.push('Study bounding boxes differ.');
    const [a0, a1, b0, b1] = [ca.start as string | undefined, ca.end as string | undefined, cb.start as string | undefined, cb.end as string | undefined];
    if (a0 && b0 && ((a1 as string) < b0 || (b1 as string) < a0)) reasons.push('UTC date ranges do not overlap.');
  }
  const sa = source.snapshot_id ? snapshots[source.snapshot_id] : undefined;
  const sb = target.snapshot_id ? snapshots[target.snapshot_id] : undefined;
  if (sa && sb && sa.release_id !== sb.release_id) reasons.push('Evidence comes from different releases.');
  const opa = source.binding?.operation;
  const opb = target.binding?.operation;
  if (opa && opb) {
    if (FAMILY[opa] !== FAMILY[opb]) reasons.push('Operations belong to incompatible scientific families.');
    if (kind === 'scale' && opa !== opb) reasons.push('A shared scale needs the same operation.');
  }
  if ((kind === 'scale' || kind === 'compare') && sa && sb && sa.unit !== sb.unit) reasons.push(`Units differ: ${sa.unit} and ${sb.unit}.`);
  return reasons;
}

/** Cards reachable from ``origin`` in one topological pass, skipping (and reporting) incompatible links. */
export function propagate(state: DocState, origin: string, snapshots: Record<string, Pick<Snapshot, 'release_id' | 'unit'>> = {}) {
  const order = topologicalOrder(state.cards, state.connections);
  const reached = new Set([origin]);
  const skipped: { connection: string; reasons: string[] }[] = [];
  for (const id of order) {
    if (!reached.has(id)) continue;
    const outgoing = Object.values(state.connections).filter((c) => c.source === id).sort((a, b) => (a.id < b.id ? -1 : 1));
    for (const link of outgoing) {
      const reasons = compatibility(state.cards[id], state.cards[link.target], link.kind, state, snapshots);
      if (reasons.length) skipped.push({ connection: link.id, reasons });
      else reached.add(link.target);
    }
  }
  return { reached: order.filter((id) => reached.has(id)), skipped };
}

/** One event, one propagation pass. Pinned displays and incompatible receipts stay independent. */
export function selectionTargets(state: DocState, origin: string, snapshots: Record<string, Pick<Snapshot, 'release_id' | 'unit'>> = {}) {
  const reached = new Set([origin]), queue = [origin];
  while (queue.length) {
    const source = queue.shift()!;
    const targets = [...Object.values(state.connections).filter((c) => c.source === source).map((c) => ({ id: c.target, kind: c.kind })),
      ...Object.values(state.cards).filter((c) => c.follow === 'selected' && c.follow_card_id === source).map((c) => ({ id: c.id, kind: 'context' as const }))];
    for (const target of targets) {
      const card = state.cards[target.id];
      if (!card || reached.has(card.id) || card.follow === 'pinned') continue;
      if (compatibility(state.cards[source], card, target.kind, state, snapshots).length || compatibility(state.cards[origin], card, 'context', state, snapshots).length) continue;
      reached.add(card.id); queue.push(card.id);
    }
  }
  return state.order.filter((id) => reached.has(id));
}
