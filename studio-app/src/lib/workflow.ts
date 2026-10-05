import type { WorkflowDefinition, WorkflowNode } from '../types';

export const PORTS: Record<string, Record<string, { types: string[]; multiple?: boolean }>> = {
  operation: {}, evidence_input: {}, pick: { source: { types: ['result'] } }, filter: { data: { types: ['series'] } },
  compare: { left: { types: ['scalar'] }, right: { types: ['scalar'] } }, visualize: { data: { types: ['series', 'table', 'scalar'] } },
  board_insert: { items: { types: ['card_draft'], multiple: true } }, portable_export: { board: { types: ['board_result'] } },
  card_output: { content: { types: ['visual', 'scalar', 'table', 'result'] } }, export_prep: { items: { types: ['card_draft'], multiple: true } }, story_output: { items: { types: ['card_draft'], multiple: true } }
};
const OUTPUT: Record<string, string> = { operation: 'result', evidence_input: 'result', filter: 'series', compare: 'table', visualize: 'visual', card_output: 'card_draft', board_insert: 'board_result', portable_export: 'export_job', export_prep: 'export_manifest', story_output: 'story_draft' };
/** Check editor structure before mounting it; the backend validates the full executable contract. */
export function parseDraft(value: unknown): WorkflowDefinition {
  const nodes = (value as WorkflowDefinition)?.nodes;
  if (!Array.isArray(nodes) || !nodes.length || nodes.length > 40) throw new Error('Provide a graph with 1–40 nodes.');
  const ids = new Set<string>();
  for (const node of nodes) {
    if (!node || typeof node.id !== 'string' || !node.id || ids.has(node.id) || !Object.hasOwn(PORTS, node.type)) throw new Error('Every node needs a unique ID and supported type.');
    ids.add(node.id);
    if (node.inputs && (Array.isArray(node.inputs) || typeof node.inputs !== 'object')) throw new Error('Node inputs must be a typed port object.');
    for (const input of Object.values(node.inputs || {})) if (!(typeof input === 'string' || Array.isArray(input) && input.every((id) => typeof id === 'string'))) throw new Error('Inputs refer to node IDs.');
    if (node.position && (!Number.isFinite(node.position.x) || !Number.isFinite(node.position.y))) throw new Error('Node positions must be finite coordinates.');
  }
  for (const node of nodes) for (const input of Object.values(node.inputs || {}).flat()) if (!ids.has(input)) throw new Error('A referenced input node is missing.');
  return { nodes };
}
export const outputType = (node: WorkflowNode) => node.type === 'pick' ? String(node.params?.path || '').split('/').includes('*') ? 'series' : 'scalar' : OUTPUT[node.type];
export function connect(definition: WorkflowDefinition, source: string, target: string, port: string): WorkflowDefinition {
  const a = definition.nodes.find((n) => n.id === source), b = definition.nodes.find((n) => n.id === target);
  const input = b && PORTS[b.type]?.[port];
  if (!a || !b || !input || !input.types.includes(outputType(a))) throw new Error('These ports carry incompatible values.');
  const reaches = (id: string, seen = new Set<string>()): boolean => {
    if (id === target) return true;
    if (seen.has(id)) return false;
    seen.add(id);
    const node = definition.nodes.find((n) => n.id === id);
    return Object.values(node?.inputs || {}).flat().some((from) => reaches(from, seen));
  };
  if (reaches(source)) throw new Error('This connection would create a cycle.');
  return { nodes: definition.nodes.map((n) => n.id === target ? { ...n, inputs: { ...n.inputs, [port]: input.multiple ? [...new Set([...([n.inputs?.[port]].flat().filter(Boolean) as string[]), source])] : source } } : n) };
}
export function removeNodes(definition: WorkflowDefinition, ids: string[]): WorkflowDefinition {
  return { nodes: definition.nodes.filter((n) => !ids.includes(n.id)).map((n) => ({ ...n, inputs: Object.fromEntries(Object.entries(n.inputs || {}).flatMap(([port, from]) => {
    const left = [from].flat().filter((id) => !ids.includes(id));
    return left.length ? [[port, Array.isArray(from) ? left : left[0]]] : [];
  })) })) };
}
