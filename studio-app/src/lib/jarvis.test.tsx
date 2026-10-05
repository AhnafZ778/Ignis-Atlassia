import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StudioProvider, useStudio, type StudioValue } from '../store';
import { JarvisPanel } from '../components/JarvisPanel';
import { api } from '../api';
import type { DocumentView } from '../types';
vi.mock('../api', () => ({ uid: () => 'jarvis-test-instance', api: { instanceCommands: vi.fn(), getCommand: vi.fn(), jarvisCancel: vi.fn(), jarvisStart: vi.fn(), jarvisRun: vi.fn(), jarvisApply: vi.fn(), projects: vi.fn(), saveWorkflow: vi.fn(), runWorkflow: vi.fn() } }));
let value: StudioValue, root: ReturnType<typeof createRoot>, host: HTMLDivElement;
const doc = (): DocumentView => ({ id: 'board', revision: 1, context_revision: 1, role: 'owner', state: { cards: {}, connections: {}, order: [], study: {} }, selection: { card_id: null } } as unknown as DocumentView);
function Probe() { value = useStudio(); return value.doc ? <JarvisPanel /> : null; }
const click = async (label: string) => { const btn = [...host.querySelectorAll('button')].find((b) => b.textContent === label)!; expect(btn).toBeTruthy(); await act(async () => btn.click()); };
beforeEach(async () => {
  vi.resetAllMocks(); localStorage.clear(); (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  host = document.createElement('div'); document.body.append(host); root = createRoot(host);
  act(() => root.render(<StudioProvider><Probe /></StudioProvider>)); act(() => value.open(doc()));
  vi.mocked(api.instanceCommands).mockResolvedValue({ commands: [] });
  vi.mocked(api.jarvisCancel).mockResolvedValue({} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({ id: 'run', status: 'queued' });
  vi.mocked(api.jarvisRun).mockResolvedValue({ status: 'completed', body: {}, proposals: [{ id: 'proposal', base_revision: 1, summary: 'Checked workflow draft', body: { action: 'create_workflow_draft' } }] } as any);
  vi.mocked(api.projects).mockResolvedValue({ workflow: { revision: 3 }, stories: [] } as any);
});
afterEach(() => { act(() => root.unmount()); host.remove(); });
describe('JARVIS draft application with mocked inference transport', () => {
  it('displays the actual saved command status and outputs after the assistant completes', async () => {
    vi.mocked(api.jarvisRun).mockResolvedValue({ status: 'completed', body: { title: 'Canvas command saved', summary: 'Saved for preparation.', studio_commands: [{ id: 'cmd-1', status: 'accepted' }] }, proposals: [] } as any);
    vi.mocked(api.getCommand).mockResolvedValue({ id: 'cmd-1', status: 'partial', message: 'Saved; resume the command.', outputs: { document_id: 'board', object_ids: ['map-card'] } } as any);
    await click('Check source states');
    expect(api.getCommand).toHaveBeenCalledWith('cmd-1');
    expect(host.textContent).toContain('partial: Saved; resume the command.');
    expect(host.querySelector('a')?.getAttribute('href')).toBe('./studio.html?board=board&command=cmd-1');
    expect(host.textContent).toContain('map-card');
  });
  it('ignores a command poll arriving after the source study changes', async () => {
    let finish: (v: any) => void = () => undefined;
    vi.mocked(api.jarvisRun).mockResolvedValue({ status: 'completed', body: { studio_commands: [{ id: 'cmd-1' }] }, proposals: [] } as any);
    vi.mocked(api.getCommand).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    await click('Check source states');
    act(() => value.open({ ...doc(), context_revision: 2, revision: 2 }));
    await act(async () => finish({ id: 'cmd-1', status: 'partial', message: 'Old scope', outputs: {} }));
    expect(host.textContent).not.toContain('Old scope');
  });

  it('loads a workflow into the editor draft without saving or executing it', async () => {
    const definition = { nodes: [{ id: 'study', type: 'operation', params: { operation: 'replay' } }] };
    vi.mocked(api.jarvisApply).mockResolvedValue({ workflow_draft: { id: 'draft', definition } } as any);
    await click('Check source states'); await click('Apply presentation draft');
    expect(JSON.parse(localStorage.getItem('fireatlas-workflow-draft:board')!)).toEqual({ baseRevision: 3, definition });
    expect(host.textContent).toContain('explicitly save and run');
    expect(api.saveWorkflow).not.toHaveBeenCalled(); expect(api.runWorkflow).not.toHaveBeenCalled();
    expect(value.doc?.revision).toBe(1);
  });
  it('rejects an apply response arriving after the applied study changed', async () => {
    let finish: (v: any) => void = () => undefined;
    vi.mocked(api.jarvisApply).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    await click('Check source states');
    act(() => [...host.querySelectorAll('button')].find((b) => b.textContent === 'Apply presentation draft')!.click());
    act(() => value.open({ ...doc(), context_revision: 2, revision: 2 }));
    await act(async () => finish({ workflow_draft: { definition: { nodes: [] } } }));
    expect(localStorage.getItem('fireatlas-workflow-draft:board')).toBeNull();
    expect(api.projects).not.toHaveBeenCalled();
  });
});
