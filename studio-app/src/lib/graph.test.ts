import { describe, expect, it } from 'vitest';
import vectors from '../../test-vectors/graph.json';
import { CycleError, compatibility, propagate, selectionTargets, topologicalOrder } from './graph';

describe('graph rules shared with the Python implementation', () => {
  it('display selections stop at pinned cards and incompatible releases and include explicit selected followers', () => {
    const state: any = { study: {}, order: ['a', 'pin', 'behind', 'follower', 'old'], cards: {
      a: { id: 'a', snapshot_id: 'new' }, pin: { id: 'pin', follow: 'pinned' }, behind: { id: 'behind' },
      follower: { id: 'follower', follow: 'selected', follow_card_id: 'a', snapshot_id: 'new' }, old: { id: 'old', snapshot_id: 'old' }
    }, connections: { pin: { source: 'a', target: 'pin', kind: 'context' }, behind: { source: 'pin', target: 'behind', kind: 'context' }, old: { source: 'a', target: 'old', kind: 'context' } } };
    expect(selectionTargets(state, 'a', { new: { release_id: 'r2', unit: 'records' }, old: { release_id: 'r1', unit: 'records' } })).toEqual(['a', 'follower']);
  });
  for (const item of vectors.topological_order) {
    it(`orders: ${item.name}`, () => {
      if (item.expect === 'cycle') expect(() => topologicalOrder(item.cards, item.connections)).toThrow(CycleError);
      else expect(topologicalOrder(item.cards, item.connections)).toEqual(item.expect);
    });
  }
  for (const item of vectors.compatibility) {
    it(`compatibility: ${item.name}`, () => {
      expect(compatibility(item.source as any, item.target as any, item.kind as any, item.state as any, item.snapshots as any)).toEqual(item.expect);
    });
  }
  it('propagation reports skipped links instead of applying them', () => {
    const state: any = {
      study: {}, order: ['a', 'b', 'c'],
      cards: {
        a: { id: 'a', binding: { operation: 'replay' }, snapshot_id: 's1' },
        b: { id: 'b', binding: { operation: 'replay' }, snapshot_id: 's2' },
        c: { id: 'c', binding: { operation: 'research' } }
      },
      connections: { l1: { id: 'l1', source: 'a', target: 'b', kind: 'scale' }, l2: { id: 'l2', source: 'a', target: 'c', kind: 'context' } }
    };
    const out = propagate(state, 'a', { s1: { release_id: 'r', unit: 'records' }, s2: { release_id: 'r', unit: 'records' } });
    expect(out.reached).toEqual(['a', 'b']);
    expect(out.skipped).toEqual([{ connection: 'l2', reasons: ['Operations belong to incompatible scientific families.'] }]);
  });
});
