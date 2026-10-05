import { JarvisPanel } from './JarvisPanel';
import { useEffect, useMemo, useRef, useState } from 'react';
import { ReactFlow, Background, Controls, Handle, Position, applyNodeChanges, type Node, type NodeProps, type Connection, type Edge, type ReactFlowInstance } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { api, uid } from '../api';
import { useStudio } from '../store';
import { connect, outputType, PORTS, removeNodes, parseDraft } from '../lib/workflow';
import type { WorkflowDefinition, WorkflowNode, WorkflowRun } from '../types';

type FlowNode = Node<{ definition: WorkflowNode; done: boolean }, 'operation'>;
function OperationNode({ data, selected }: NodeProps<FlowNode>) {
  const node = data.definition;
  return <div className={`wf-block${selected ? ' selected' : ''}`}>
    <span className="card-type">{node.type.replaceAll('_', ' ')}</span><strong>{node.label || node.id}</strong>
    <span>{node.params?.operation ? String(node.params.operation) : node.params?.path ? String(node.params.path) : outputType(node)}</span>
    <span className={`chip ${data.done ? 'ok' : 'off'}`}>{data.done ? 'Output saved' : 'Not run'}</span>
    {Object.keys(PORTS[node.type] || {}).map((port, index, all) => <Handle key={port} id={port} type="target" position={Position.Left} style={{ top: `${(index + 1) * 100 / (all.length + 1)}%` }} aria-label={`Input ${port}`} />)}
    <Handle type="source" position={Position.Right} id="output" aria-label={`Output ${outputType(node)}`} />
  </div>;
}
const nodeTypes = { operation: OperationNode };
const message = (error: unknown) => error instanceof Error ? error.message : 'The workflow request failed. Your draft is retained.';
const initial: WorkflowDefinition = { nodes: [{ id: 'method', type: 'operation', label: 'Inspect study method', params: { operation: 'method', arguments: {} } }] };
export function WorkflowPanel() {
  const { doc, canEdit, open, isCurrent } = useStudio();
  const boardId = doc!.id;
  const live = useRef(true);
  const timer = useRef<number | undefined>(undefined);
  const [definition, setDefinition] = useState<WorkflowDefinition>(initial);
  const [saved, setSaved] = useState<{ id: string; revision: number; definition: WorkflowDefinition } | null>(null);
  const [templates, setTemplates] = useState<{ id: string; title: string; definition: WorkflowDefinition }[]>([]);
  const [status, setStatus] = useState('Opening saved workflow…');
  const [busy, setBusy] = useState(false);
  const [restored, setRestored] = useState(false);
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [flow, setFlow] = useState<ReactFlowInstance<FlowNode, Edge> | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [jsonDraft, setJsonDraft] = useState('');
  const [paramsDraft, setParamsDraft] = useState('');
  const dirty = !saved || JSON.stringify(saved.definition) !== JSON.stringify(definition);
  const selectedNode = definition.nodes.find((n) => n.id === selected);
  useEffect(() => {
    live.current = true;
    api.workflowTemplates().then((result) => live.current && setTemplates(result.templates)).catch((error) => live.current && setStatus(message(error)));
    api.projects(boardId).then((projects) => {
      if (!live.current) return;
      setSaved(projects.workflow);
      if (projects.workflow) { setDefinition(projects.workflow.definition); setStatus(`Restored workflow revision ${projects.workflow.revision}.`); }
      else setStatus('Choose a template or connect typed blocks. Saving or editing never runs an export.');
      try { const draft = JSON.parse(localStorage.getItem(`fireatlas-workflow-draft:${boardId}`) || 'null'); if (draft && draft.baseRevision === (projects.workflow?.revision || 0)) { setDefinition(parseDraft(draft.definition)); setStatus('Recovered your unsaved workflow draft.'); } } catch { /* only compatible local drafts are restored */ }
      setRestored(true);
    }).catch((error) => live.current && setStatus(message(error)));
    return () => { live.current = false; window.clearTimeout(timer.current); };
  }, [boardId]);
  useEffect(() => {
    setJsonDraft(JSON.stringify(definition, null, 2));
    try { if (restored) { if (dirty) localStorage.setItem(`fireatlas-workflow-draft:${boardId}`, JSON.stringify({ baseRevision: saved?.revision || 0, definition })); else localStorage.removeItem(`fireatlas-workflow-draft:${boardId}`); } } catch { /* explicit save remains usable */ }
  }, [definition, saved, dirty, boardId, restored]);
  useEffect(() => { setParamsDraft(JSON.stringify(selectedNode?.params || {}, null, 2)); }, [selectedNode]);
  const edges = useMemo<Edge[]>(() => definition.nodes.flatMap((node) => Object.entries(node.inputs || {}).flatMap(([port, sources]) => [sources].flat().map((source) => ({ id: `${source}:${node.id}:${port}`, source, target: node.id, sourceHandle: 'output', targetHandle: port, label: port })))), [definition]);
  const nodes: FlowNode[] = definition.nodes.map((node, index) => ({ id: node.id, type: 'operation', position: node.position || { x: (index % 3) * 280, y: Math.floor(index / 3) * 210 }, selected: selected === node.id, data: { definition: node, done: Boolean(run?.outputs[node.id]) } }));
  useEffect(() => { if (!flow || !restored) return; const fit = window.setTimeout(() => void flow.fitView({ padding: 0.18, duration: 0 }), 150); return () => window.clearTimeout(fit); }, [flow, restored, definition.nodes.map((n) => n.id).join(',')]);
  const onConnect = (edge: Connection) => {
    if (!edge.source || !edge.target || !edge.targetHandle) return;
    try { setDefinition(connect(definition, edge.source, edge.target, edge.targetHandle)); setStatus('Connection added. Validate the complete graph before saving.'); }
    catch (error) { setStatus(message(error)); }
  };
  const poll = async (id: string) => {
    try { const next = await api.getRun(id); if (!live.current) return; setRun(next); if (['running', 'queued'].includes(next.status)) timer.current = window.setTimeout(() => void poll(id), 600); else setStatus(next.error || `Run ${next.status}; ${next.receipts.length} checked node receipts.`); }
    catch (error) { if (live.current) setStatus(message(error)); }
  };
  const task = async (action: 'validate' | 'save' | 'run') => {
    setBusy(true);
    try {
      if (action === 'validate') { const result = await api.validateWorkflow(definition); if (live.current) setStatus(`Valid graph: ${result.order.length} typed nodes.`); }
      if (action === 'save') { const result = await api.saveWorkflow(boardId, definition, saved?.revision); if (live.current) { setSaved({ ...result, definition: structuredClone(definition) }); setStatus(`Saved workflow revision ${result.revision}.`); } }
      if (action === 'run' && saved) { const next = await api.runWorkflow(saved.id); if (live.current) { setRun(next); setStatus('Running this saved workflow revision.'); void poll(next.id); } }
    } catch (error) { if (live.current) setStatus(message(error)); }
    finally { if (live.current) setBusy(false); }
  };
  return <section className="panel" aria-label="Workflow Composer"><div className="row"><h2>Workflow Composer</h2><span className="chip off">{saved ? `revision ${saved.revision}` : 'new workflow'} · {dirty ? 'unsaved draft' : 'saved'}</span></div><p role="status">{status}</p>
    <div className="row"><label className="field">Starter recipe<select disabled={!canEdit || busy} defaultValue="" onChange={(e) => { const next = templates.find((t) => t.id === e.target.value); if (next) { setDefinition(structuredClone(next.definition)); setRun(null); setSelected(null); } }}><option value="">Choose a recipe</option>{templates.map((t) => <option value={t.id} key={t.id}>{t.title}</option>)}</select></label><label className="field">Add block<select value="" disabled={!canEdit || definition.nodes.length >= 40} onChange={(e) => { if (!e.target.value) return; const type = e.target.value, id = uid('node'); setDefinition({ nodes: [...definition.nodes, { id, type, label: type.replaceAll('_', ' '), params: type === 'operation' ? { operation: 'method', arguments: {} } : type === 'pick' ? { path: '/summary/joint_cell_days' } : {} }] }); setSelected(id); }}><option value="">Select a node type</option>{Object.keys(PORTS).map((type) => <option key={type} value={type}>{type.replaceAll('_', ' ')}</option>)}</select></label></div>
    <div className="row"><button className="btn" disabled={busy} onClick={() => void task('validate')}>Validate graph</button><button className="btn primary" disabled={busy || !canEdit} onClick={() => void task('save')}>Save workflow</button><button className="btn" disabled={busy || !canEdit || !saved || dirty || run?.status === 'running'} onClick={() => void task('run')}>Run saved revision</button>{run?.status === 'running' ? <button className="btn danger" onClick={() => api.cancelRun(run.id).then((next) => live.current && setRun(next)).catch((error) => setStatus(message(error)))}>Cancel run</button> : null}</div>
    <button className="btn small" onClick={() => void flow?.fitView({ padding: 0.18, duration: 0 })}>Fit entire workflow</button><div className="wf-flow" role="region" aria-label="Typed workflow diagram"><ReactFlow<FlowNode> onInit={setFlow} nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView nodesDraggable={canEdit} nodesConnectable={canEdit} onNodeClick={(_, node) => setSelected(node.id)} onNodesChange={(changes) => {
      if (!canEdit || !changes.some((change) => ['position', 'remove'].includes(change.type))) return;
      const next = applyNodeChanges(changes, nodes);
      const removed = changes.filter((c) => c.type === 'remove').map((c) => c.id);
      const base = removed.length ? removeNodes(definition, removed) : definition;
      setDefinition({ nodes: base.nodes.map((node) => ({ ...node, position: next.find((n) => n.id === node.id)?.position || node.position })) });
    }} onEdgesChange={(changes) => {
      if (!canEdit) return;
      const removed = changes.filter((c) => c.type === 'remove').map((c) => edges.find((e) => e.id === c.id)).filter(Boolean);
      if (!removed.length) return;
      setDefinition({ nodes: definition.nodes.map((node) => ({ ...node, inputs: Object.fromEntries(Object.entries(node.inputs || {}).flatMap(([port, sources]) => { const left = [sources].flat().filter((source) => !removed.some((edge) => edge!.source === source && edge!.target === node.id && edge!.targetHandle === port)); return left.length ? [[port, Array.isArray(sources) ? left : left[0]]] : []; })) })) });
    }} onConnect={onConnect} deleteKeyCode={canEdit ? ['Backspace', 'Delete'] : null}><Background /><Controls showInteractive={false} /></ReactFlow></div>
    <details open className="workflow-outline"><summary>Keyboard and table editor</summary><table className="facts"><thead><tr><th>Node</th><th>Output</th><th>Inputs</th><th>Status</th><th>Edit</th></tr></thead><tbody>{definition.nodes.map((n) => <tr key={n.id}><td>{n.label || n.id}</td><td>{outputType(n)}</td><td>{Object.entries(n.inputs || {}).map(([port, from]) => `${port}: ${[from].flat().join(', ')}`).join('; ') || 'Study input'}</td><td>{run?.outputs[n.id] ? 'Saved output' : 'Not run'}</td><td><button className="btn small" onClick={() => setSelected(n.id)}>Edit {n.label || n.type}</button></td></tr>)}</tbody></table></details>
    {selectedNode ? <div className="wf-inspector"><h3>Edit {selectedNode.label || selectedNode.id}</h3><label className="field">Node label<input value={selectedNode.label || ''} disabled={!canEdit} onChange={(e) => setDefinition({ nodes: definition.nodes.map((n) => n.id === selected ? { ...n, label: e.target.value } : n) })} /></label><label className="field">Parameters (JSON)<textarea value={paramsDraft} disabled={!canEdit} onChange={(e) => setParamsDraft(e.target.value)} /></label><button className="btn" disabled={!canEdit} onClick={() => { try { const params = JSON.parse(paramsDraft); if (!params || Array.isArray(params) || typeof params !== 'object') throw new Error('Parameters must be an object.'); setDefinition({ nodes: definition.nodes.map((n) => n.id === selected ? { ...n, params } : n) }); } catch (error) { setStatus(message(error)); } }}>Apply parameters</button>
      {Object.keys(PORTS[selectedNode.type] || {}).map((port) => <label className="field" key={port}>Input {port}<select disabled={!canEdit} value={typeof selectedNode.inputs?.[port] === 'string' ? selectedNode.inputs[port] as string : ''} onChange={(e) => { try { setDefinition(connect(definition, e.target.value, selectedNode.id, port)); } catch (error) { setStatus(message(error)); } }}><option value="">Choose a compatible source</option>{definition.nodes.filter((n) => n.id !== selectedNode.id && PORTS[selectedNode.type][port].types.includes(outputType(n))).map((n) => <option value={n.id} key={n.id}>{n.label || n.id}</option>)}</select></label>)}<button className="btn danger" disabled={!canEdit} onClick={() => { setDefinition(removeNodes(definition, [selectedNode.id])); setSelected(null); }}>Delete block</button></div> : null}
    <details><summary>Complete graph JSON</summary><label className="field">Workflow definition<textarea value={jsonDraft} disabled={!canEdit} onChange={(e) => setJsonDraft(e.target.value)} /></label><button className="btn" disabled={!canEdit} onClick={() => { try { const next = parseDraft(JSON.parse(jsonDraft)); setDefinition(next); } catch (error) { setStatus(message(error)); } }}>Apply JSON draft</button></details>
    {run?.status === 'completed' ? <div className="row">{Object.entries(run.outputs).filter(([, value]) => ['card_draft', 'story_draft', 'export_manifest'].includes(value.type)).map(([id, value]) => <button key={id} className="btn" disabled={!canEdit || busy} onClick={async () => { setBusy(true); try { const result = await api.applyRun(run.id, id, doc!.revision); if (live.current && isCurrent(boardId)) { open(result.document); setStatus(result.story ? 'Editable story draft created. Open Story to resolve its scenes and explicitly export or render.' : 'Frozen evidence cards added to the board.'); } } catch (error) { if (live.current) setStatus(message(error)); } finally { if (live.current) setBusy(false); } }}>{value.type === 'story_draft' ? 'Create story draft' : 'Add frozen cards'} · {id}</button>)}</div> : null}
    {saved && selected && !dirty ? <JarvisPanel workflow={{ workflow_id: saved.id, workflow_revision: saved.revision, node_id: selected }} /> : null}
    {run ? <details><summary>Run {run.status} · {run.receipts.length} node receipts</summary><pre>{JSON.stringify(run.receipts, null, 2)}</pre>{run.error ? <p role="alert">{run.error}</p> : null}</details> : null}<p className="muted">Scientific blocks use the applied board context and existing method limits. Eight scientific calls, 40 nodes and 120 seconds per run. Exports require an explicit action after preparation.</p>
  </section>;
}
