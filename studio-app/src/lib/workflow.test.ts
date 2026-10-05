import { describe, expect, it } from 'vitest';
import { connect, outputType, removeNodes, parseDraft } from './workflow';
import type { WorkflowDefinition } from '../types';
describe('typed workflow edits', () => {
  const graph: WorkflowDefinition = { nodes: [{ id: 'a', type: 'operation' }, { id: 'b', type: 'pick', params: { path: '/dates/*/value' }, inputs: { source: 'a' } }, { id: 'c', type: 'filter' }] };
  it('preserves wildcard series typing and rejects incompatible ports', () => {
    expect(outputType(graph.nodes[1])).toBe('series');
    expect(connect(graph, 'b', 'c', 'data').nodes[2].inputs).toEqual({ data: 'b' });
    expect(() => connect(graph, 'a', 'c', 'data')).toThrow('incompatible');
  });
  it('rejects cycles before saving and leaves the source graph intact', () => {
    const linked = connect(graph, 'b', 'c', 'data');
    linked.nodes.push({ id: 'd', type: 'filter', inputs: { data: 'c' } });
    expect(() => connect(linked, 'd', 'c', 'data')).toThrow('cycle');
    expect(linked.nodes[2].inputs).toEqual({ data: 'b' });
  });
  it('removes dangling inputs without changing unrelated nodes', () => {
    expect(removeNodes(graph, ['a']).nodes[0].inputs).toEqual({});
    expect(graph.nodes[1].inputs).toEqual({ source: 'a' });
  });
  it('rejects malformed editor drafts before they reach the canvas', () => {
    expect(parseDraft(graph).nodes.length).toBe(3);
    for (const value of [null, { nodes: [null] }, { nodes: [{ id: 'a', type: 'shell' }] }, { nodes: [{ id: 'a', type: 'pick', inputs: { source: 123 } }] }]) expect(() => parseDraft(value)).toThrow();
  });
});
