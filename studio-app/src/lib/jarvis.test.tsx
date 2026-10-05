import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StudioProvider, useStudio, type StudioValue } from '../store';
import { JarvisPanel } from '../components/JarvisPanel';
import { api } from '../api';
import type { DocumentView } from '../types';
vi.mock('../api', () => ({ uid: () => 'jarvis-test-instance', idempotencyKey:()=> 'prompt-request-key', api: { promptPresets:vi.fn(),promptCommand:vi.fn(),commandAction:vi.fn(),instanceCommands: vi.fn(), getCommand: vi.fn(), jarvisCancel: vi.fn(), jarvisStart: vi.fn(), jarvisRun: vi.fn(), jarvisApply: vi.fn(), projects: vi.fn(), saveWorkflow: vi.fn(), runWorkflow: vi.fn() } }));
let value: StudioValue, root: ReturnType<typeof createRoot>, host: HTMLDivElement;
const doc = (): DocumentView => ({ id: 'board', revision: 1, context_revision: 1, role: 'owner', state: { cards: {}, connections: {}, order: [], study: {} }, selection: { card_id: null } } as unknown as DocumentView);
function Probe() { value = useStudio(); return value.doc ? <JarvisPanel /> : null; }
const click = async (label: string) => { const btn = [...host.querySelectorAll('button')].find((b) => b.textContent === label)!; expect(btn).toBeTruthy(); await act(async () => btn.click()); };
beforeEach(async () => {
  vi.resetAllMocks(); localStorage.clear(); (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  vi.mocked(api.promptPresets).mockResolvedValue({presets:[]});
  vi.mocked(api.promptCommand).mockResolvedValue({handled:false});
  host = document.createElement('div'); document.body.append(host); root = createRoot(host);
  act(() => root.render(<StudioProvider><Probe /></StudioProvider>)); act(() => value.open(doc()));
  vi.mocked(api.instanceCommands).mockResolvedValue({ commands: [] });
  vi.mocked(api.promptPresets).mockResolvedValue({presets:[]});
  vi.mocked(api.promptCommand).mockResolvedValue({handled:false});
  vi.mocked(api.jarvisCancel).mockResolvedValue({} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({ id: 'run', status: 'queued' });
  vi.mocked(api.jarvisRun).mockResolvedValue({ status: 'completed', body: {}, proposals: [{ id: 'proposal', base_revision: 1, summary: 'Checked workflow draft', body: { action: 'create_workflow_draft' } }] } as any);
  vi.mocked(api.projects).mockResolvedValue({ workflow: { revision: 3 }, stories: [] } as any);
});
afterEach(() => { act(() => root.unmount()); host.remove(); });
describe('JARVIS draft application with mocked inference transport', () => {
  it('captures the visible map day and source rather than its parent board defaults',async()=>{
    const board=doc();board.state.study={context:{case:'park-2024',day:'2024-07-24',source:'joint'}};
    board.state.cards.map={id:'map',type:'map',title:'Selected heat',display:{day:'2024-07-30',source:'VIIRS_SNPP_SP'},snapshot_id:'frozen',follow:'board'} as any;
    board.snapshots={frozen:{id:'frozen',operation:'replay'}} as any;
    board.selection={card_id:'map'} as any;
    await act(async()=>value.open(board));
    vi.mocked(api.promptCommand).mockResolvedValue({handled:true,status:'needs_destination',choices:[],question:'Choose Canvas'});
    const input=host.querySelector('textarea')!;
    await act(async()=>{Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value')!.set!.call(input,'Send this map to Canvas');input.dispatchEvent(new Event('input',{bubbles:true}));});
    await click('Ask JARVIS');
    expect(api.promptCommand).toHaveBeenCalledWith(expect.objectContaining({context:expect.objectContaining({study_selection:expect.objectContaining({day:'2024-07-30',source:'VIIRS_SNPP_SP'}),result_refs:[{document_id:'board',snapshot_id:'frozen'}]})}),'prompt-request-key');
  });
  it('asks for the Canvas before a presentation and submits the captured request without an AI call',async()=>{
    vi.mocked(api.promptCommand).mockResolvedValueOnce({handled:true,status:'needs_destination',question:'Which Canvas should receive this investigation?',choices:[{id:'other',title:'My presentation',revision:7}]}).mockResolvedValueOnce({handled:true,status:'submitted',command:{id:'command',status:'accepted',outputs:{}}});
    vi.mocked(api.getCommand).mockResolvedValue({id:'command',status:'partial',message:'Saved draft',outputs:{document_id:'other'}});
    const input=host.querySelector('textarea')!;
    await act(async()=>{Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value')!.set!.call(input,'Create a curated presentation on Canvas');input.dispatchEvent(new Event('input',{bubbles:true}));});
    await click('Ask JARVIS');
    expect(host.textContent).toContain('Which Canvas should receive this investigation?');
    expect(api.jarvisStart).not.toHaveBeenCalled();
    const select=host.querySelector<HTMLSelectElement>('.jarvis-destination select')!;
    await act(async()=>{select.value='other';select.dispatchEvent(new Event('change',{bubbles:true}));});
    await click('Create presentation on selected Canvas');
    expect(api.promptCommand).toHaveBeenLastCalledWith(expect.objectContaining({message:'Create a curated presentation on Canvas',destination:{intent:'append',board_id:'other',revision:7}}),'prompt-request-key');
    expect(api.jarvisStart).not.toHaveBeenCalled();
    expect(host.textContent).toContain('Saved draft');
  });
  it('canceling the destination selection inserts nothing and a source change clears the pending choice',async()=>{
    vi.mocked(api.promptCommand).mockResolvedValue({handled:true,status:'needs_destination',choices:[],question:'Which Canvas?'});
    const input=host.querySelector('textarea')!;
    await act(async()=>{Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value')!.set!.call(input,'Send this study to Canvas');input.dispatchEvent(new Event('input',{bubbles:true}));});
    await click('Ask JARVIS');await click('Cancel Canvas selection');
    expect(api.promptCommand).toHaveBeenCalledTimes(1);expect(host.querySelector('.jarvis-destination')).toBeNull();
    await click('Ask JARVIS');
    act(()=>value.open({...doc(),context_revision:2}));
    expect(host.querySelector('.jarvis-destination')).toBeNull();
  });
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
