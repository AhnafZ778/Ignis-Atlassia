import type { Binding, Capabilities, DocumentView, RenderJob, RoomView, SnapshotReport, StoryBody, StoryView, WorkflowDefinition, WorkflowRun, Snapshot } from './types';

export class ApiError extends Error {
  status: number; code: string; details: Record<string, any>;
  constructor(status: number, body: any) {
    super(body?.error || `Request failed (${status})`);
    this.status = status; this.code = body?.code || 'error'; this.details = body?.details || {};
  }
  get isConflict() { return this.status === 409; }
}

const base = () => new URL('api/studio/', document.baseURI).href;
export const uid = (prefix: string) => `${prefix}-${crypto.randomUUID().replace(/-/g, '').slice(0, 12)}`;
export const idempotencyKey = () => 'k-' + crypto.randomUUID();

async function request<T>(method: string, path: string, body?: unknown, key?: string): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (key) headers['Idempotency-Key'] = key;
  let response: Response;
  try {
    response = await fetch(base() + path, { method, headers, credentials: 'same-origin', body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, { error: 'Studio is not reachable. Your last saved board is kept on the server.', code: 'offline' });
  }
  const text = await response.text();
  let parsed: any = null;
  try { parsed = text ? JSON.parse(text) : null; } catch { parsed = { error: 'Unexpected response from Studio.' }; }
  if (!response.ok) throw new ApiError(response.status, parsed);
  return parsed as T;
}

const enc = encodeURIComponent;
export const api = {
  registerContext: (body: unknown) => request<any>('POST', 'contexts', body),
  submitCommand: (body: unknown, key = idempotencyKey()) => request<any>('POST', 'commands', body, key),
  instanceCommands: (instance: string) => request<{ commands: any[] }>('GET', `contexts/${enc(instance)}/commands`),
  getCommand: (id: string) => request<any>('GET', `commands/${enc(id)}`),
  commandAction: (id: string, action: string, body: unknown = {}) => request<any>('POST', `commands/${enc(id)}/${action}`, body),
  getPackage: (id: string) => request<any>('GET', `packages/${enc(id)}`),
  prepareExport: (id: string, body: unknown) => request<any>('POST', `documents/${enc(id)}/exports`, body, idempotencyKey()),
  getExport: (id: string) => request<any>('GET', `exports/${enc(id)}`),
  exportDownload: (id: string) => base() + `exports/${enc(id)}/download`,
  transferMiro: (id: string, body: unknown) => request<any>('POST', `documents/${enc(id)}/miro-transfers`, body, idempotencyKey()),
  getMiroTransfer: (id: string) => request<any>('GET', `miro-transfers/${enc(id)}`),
  restoreArchive: async (file: File) => {
    const response = await fetch(base() + 'imports', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/zip' }, body: file });
    const body = await response.json(); if (!response.ok) throw new ApiError(response.status, body); return body as { document: DocumentView; provenance: string; rerun: string };
  },
  capabilities: () => request<Capabilities>('GET', 'capabilities'),
  ensurePrincipal: () => request<{ principal: string; created: boolean }>('POST', 'principals', {}),
  recovery: () => request<{ recovery: string; note: string }>('POST', 'recovery', {}),
  recover: (recovery: string) => request<{ principal: string }>('POST', 'recover', { recovery }),
  listDocuments: () => request<{ documents: { id: string; title: string; revision: number; updated: number; owner: boolean }[] }>('GET', 'documents'),
  createDocument: (title: string, study?: unknown) => request<DocumentView>('POST', 'documents', { title, study }, idempotencyKey()),
  getDocument: (id: string) => request<DocumentView>('GET', `documents/${enc(id)}`),
  projects: (id: string) => request<{ stories: { id: string; title: string; revision: number }[]; workflow: { id: string; revision: number; definition: WorkflowDefinition } | null; renders?: import('./types').RenderSummary[]; renders_total?: number }>('GET', `documents/${enc(id)}/projects`),
  transact: (id: string, baseRevision: number, ops: unknown[], extra: Record<string, unknown> = {}) =>
    request<DocumentView>('POST', `documents/${enc(id)}/transactions`, { base_revision: baseRevision, ops, ...extra }, idempotencyKey()),
  undo: (id: string) => request<DocumentView>('POST', `documents/${enc(id)}/undo`, {}, idempotencyKey()),
  redo: (id: string) => request<DocumentView>('POST', `documents/${enc(id)}/redo`, {}, idempotencyKey()),
  patchDocument: (id: string, body: unknown) => request<DocumentView>('PATCH', `documents/${enc(id)}`, body),
  studioAction: (id: string, body: unknown) => request<{ action: string; document?: DocumentView; story?: StoryView; workflow_draft?: { id: string; definition: WorkflowDefinition; document_id: string; base_revision: number }; selection?: any; created?: boolean; message?: string }>('POST', `documents/${enc(id)}/actions`, body, idempotencyKey()),
  resolveBinding: (id: string, binding: Binding) => request<{ snapshot: Snapshot; freshness: { fresh: boolean } }>('POST', `documents/${enc(id)}/bindings/resolve`, { binding }),
  snapshotReport: (id: string, sid: string) => request<SnapshotReport>('GET', `documents/${enc(id)}/snapshots/${enc(sid)}`),
  snapshotReceipt: (id: string, sid: string) => request<{ receipt: { payload: any; operation: string } }>('GET', `documents/${enc(id)}/snapshots/${enc(sid)}/receipt`),
  snapshotPreview: (id: string, sid: string, type: string, day?: string, source = 'joint', selection: { start?: string; end?: string; cell?: string } = {}) => request<{ svg: string; visual: any; snapshot_sha256: string }>('GET', `documents/${enc(id)}/snapshots/${enc(sid)}/preview?${new URLSearchParams({ type, source, ...(day ? { day } : {}), ...selection })}`),
  uploadAsset: (id: string, data: string, license: string, attribution: string) =>
    request<{ id: string; sha256: string; mime: string }>('POST', `documents/${enc(id)}/assets`, { data, license, attribution }),
  assetUrl: (assetId: string) => base() + `assets/${enc(assetId)}`,
  createStory: (id: string, body: Partial<StoryBody> & { selected_cards?: string[] } = {}) => request<StoryView>('POST', `documents/${enc(id)}/stories`, body, idempotencyKey()),
  getStory: (id: string, revision?: number) => request<StoryView>('GET', `stories/${enc(id)}${revision ? `?revision=${revision}` : ''}`),
  updateStory: (id: string, expectedRevision: number, story: StoryBody) => request<StoryView>('PATCH', `stories/${enc(id)}`, { expected_revision: expectedRevision, story }, idempotencyKey()),
  resolveStory: (id: string) => request<{ resolved: StoryView['resolved']; document_revision: number }>('POST', `stories/${enc(id)}/resolve`, {}),
  exportUrl: (id: string) => base() + `stories/${enc(id)}/export`,
  startRender: (id: string, narration = false) => request<RenderJob>('POST', `stories/${enc(id)}/renders`, { narration }, idempotencyKey()),
  getRender: (id: string) => request<RenderJob>('GET', `renders/${enc(id)}`),
  cancelRender: (id: string) => request<RenderJob>('POST', `renders/${enc(id)}/cancel`, {}),
  artifactUrl: (id: string, name: string) => base() + `renders/${enc(id)}/artifact?name=${enc(name)}`,
  validateWorkflow: (definition: WorkflowDefinition) => request<{ valid: boolean; order: string[] }>('POST', 'workflows/validate', { definition }),
  workflowTemplates: () => request<{ templates: { id: string; title: string; definition: WorkflowDefinition }[] }>('GET', 'workflows/templates'),
  saveWorkflow: (id: string, definition: WorkflowDefinition, expectedRevision?: number) =>
    request<{ id: string; revision: number }>('POST', `documents/${enc(id)}/workflow`, { definition, expected_revision: expectedRevision }),
  getWorkflow: (id: string) => request<{ id: string; revision: number; definition: WorkflowDefinition }>('GET', `workflows/${enc(id)}`),
  runWorkflow: (id: string) => request<WorkflowRun>('POST', `workflows/${enc(id)}/run`, {}),
  getRun: (id: string) => request<WorkflowRun>('GET', `runs/${enc(id)}`),
  cancelRun: (id: string) => request<WorkflowRun>('POST', `runs/${enc(id)}/cancel`, {}),
  applyRun: (id: string, nodeId: string, expectedRevision: number) => request<{ document: DocumentView; story?: StoryView }>('POST', `runs/${enc(id)}/apply`, { node_id: nodeId, expected_revision: expectedRevision }),
  jarvisStart: (id: string, body: unknown) => request<{ id: string; status: string }>('POST', `documents/${enc(id)}/assistant/start`, body),
  jarvisRun: (id: string, run: string) => request<any>('GET', `documents/${enc(id)}/assistant/runs/${enc(run)}`),
  jarvisCancel: (id: string, run: string) => request<any>('POST', `documents/${enc(id)}/assistant/runs/${enc(run)}/cancel`, {}),
  jarvisApply: (id: string, proposal: string) => request<any>('POST', `documents/${enc(id)}/assistant/proposals/${enc(proposal)}/apply`, {}),
  createRoom: (id: string) => request<RoomView>('POST', `documents/${enc(id)}/room`, {}),
  getRoom: (id: string) => request<RoomView>('GET', `rooms/${enc(id)}`),
  authorizeRoom: (id: string) => request<{ token: string }>('POST', `rooms/${enc(id)}/authorize`, {}),
  invite: (room: string, role: 'editor' | 'viewer') => request<{ token: string; expires: number; note: string }>('POST', `rooms/${enc(room)}/invites`, { role }),
  redeem: (token: string) => request<{ room_id: string; document_id: string; role: string }>('POST', 'invites/redeem', { token }),
  comments: (room: string) => request<{ comments: { id: string; card_id: string | null; author: string; mine: boolean; body: string; document_revision: number; chapter?: { chapter_id: string; story_id: string; story_revision: number } | null }[] }>('GET', `rooms/${enc(room)}/comments`),
  comment: (room: string, body: string, cardId?: string | null, chapter?: { chapter_id: string; story_id: string; story_revision: number } | null) => request('POST', `rooms/${enc(room)}/comments`, { body, card_id: cardId ?? null, chapter: chapter ?? null }),
  heartbeat: (room: string) => request<{ presence: { principal: string; role: string }[] }>('POST', `rooms/${enc(room)}/heartbeat`, {}),
  presenter: (room: string, after = 0) => request<{ epoch: number; changed: boolean; presenter: string | null; state: Record<string, unknown> }>('GET', `rooms/${enc(room)}/presenter?after=${after}`),
  present: (room: string, state: Record<string, unknown>, epoch: number) => request('POST', `rooms/${enc(room)}/presenter`, { state, expected_epoch: epoch })
};

export function subscribeRender(id: string, onUpdate: (job: RenderJob) => void, onDone: () => void): () => void {
  const source = new EventSource(base() + `renders/${encodeURIComponent(id)}/events`);
  source.addEventListener('render', (event) => {
    const job = JSON.parse((event as MessageEvent).data) as RenderJob;
    onUpdate(job);
    if (['completed', 'failed', 'canceled'].includes(job.status)) { source.close(); onDone(); }
  });
  source.addEventListener('timeout', () => { source.close(); onDone(); });
  source.onerror = () => { source.close(); onDone(); };
  return () => source.close();
}
