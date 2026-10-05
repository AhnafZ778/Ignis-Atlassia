import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { InvestigationActions } from '../components/InvestigationActions';
import { api } from '../api';
vi.mock('../api', () => ({ uid: () => 'destination-instance', idempotencyKey: () => 'request', api: { projects: vi.fn(), getCommand: vi.fn(), commandAction: vi.fn(), registerContext: vi.fn() } }));
const state=vi.hoisted(() => ({ value: null as any }));
vi.mock('../store', () => ({ useStudio: () => state.value }));
let host: HTMLDivElement, root: ReturnType<typeof createRoot>;
const saved={ id:'cmd', status:'awaiting_view_ack', message:'Saved; open board to continue.', outputs:{ document_id:'board',object_ids:['map'] } };
beforeEach(() => {
  vi.resetAllMocks();(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
  history.replaceState({},'', '/studio.html?board=board&command=cmd');
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => { cb(0); return 0; });
  state.value={doc:{id:'board',revision:3,context_revision:2,state:{cards:{map:{title:'Captured map',type:'map',display:{},provenance:{}}},order:['map'],groups:{},study:{context:{day:'2024-07-25'}}}},caps:{},selected:null,busy:false,canEdit:true,isCurrent:vi.fn(() => true)};
  vi.mocked(api.projects).mockResolvedValue({imported_annotations:[]} as any);
  vi.mocked(api.getCommand).mockResolvedValue(saved);
  vi.mocked(api.commandAction).mockResolvedValue({...saved,status:'completed'});
  vi.mocked(api.registerContext).mockResolvedValue({});
  host=document.createElement('div');document.body.append(host);root=createRoot(host);
});
afterEach(() => {act(() => root.unmount());host.remove();vi.unstubAllGlobals();});
describe('Canvas acknowledgment binds actual destination objects', () => {
  it('acknowledges loaded cards and the actual applied revision', async () => {
    await act(async () => root.render(<InvestigationActions />));
    expect(api.commandAction).toHaveBeenCalledWith('cmd','ack',{instance_id:'destination-instance',document_id:'board',revision:3,object_ids:['map']});
    expect(host.textContent).toContain('completed:');
  });
  it('keeps a saved command unopened when an affected object is absent', async () => {
    state.value.doc.state.cards={};await act(async () => root.render(<InvestigationActions />));
    expect(api.commandAction).not.toHaveBeenCalled();expect(host.textContent).toContain('Saved; open board');
  });
  it('does not acknowledge a late response after a different board mounts', async () => {
    let resolve: (v:any) => void=()=>{};
    vi.mocked(api.getCommand).mockImplementationOnce(() => new Promise(r => {resolve=r;}));
    act(() => root.render(<InvestigationActions />));
    state.value={...state.value,doc:{...state.value.doc,id:'new-board'}};
    await act(async () => root.render(<InvestigationActions />));
    await act(async () => resolve(saved));expect(api.commandAction).not.toHaveBeenCalled();
  });
});
