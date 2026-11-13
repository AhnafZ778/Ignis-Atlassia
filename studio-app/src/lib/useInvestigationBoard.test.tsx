import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
vi.mock('@excalidraw/excalidraw',()=>({restoreElements:(elements:any[])=>elements,serializeAsJSON:(elements:any[],_appState:any,files:any)=>JSON.stringify({elements,files})}));
vi.mock('../api',()=>({api:{ensurePrincipal:vi.fn(),listDocuments:vi.fn(),getWhiteboard:vi.fn(),transact:vi.fn()}}));
import {api} from '../api';
import {useInvestigationBoard} from './useInvestigationBoard';
let root:ReturnType<typeof createRoot>,host:HTMLDivElement,board:ReturnType<typeof useInvestigationBoard>,editor:any;
const element={id:'note',type:'text',text:'Saved observation',version:1};
beforeEach(async()=>{
 (globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;vi.useFakeTimers();localStorage.clear();history.replaceState(null,'','?board=board');
 host=document.createElement('div');document.body.append(host);root=createRoot(host);
 let elements=[element];editor={resetScene:vi.fn(),addFiles:vi.fn(),getAppState:()=>({zoom:{value:1}}),getFiles:()=>({}),getSceneElements:()=>elements,updateScene:vi.fn((value:any)=>{if(value.elements)elements=value.elements;}),scrollToContent:vi.fn(),history:{clear:vi.fn()}};
 vi.mocked(api.ensurePrincipal).mockResolvedValue({} as any);vi.mocked(api.listDocuments).mockResolvedValue({documents:[{id:'board',title:'Study'}]} as any);
 vi.mocked(api.getWhiteboard).mockResolvedValue({document:{id:'board',revision:1},elements:[element],files:{}} as any);
 vi.mocked(api.transact).mockResolvedValue({id:'board',revision:2} as any);
 function Capture(){board=useInvestigationBoard(editor);return null;}
 await act(async()=>{root.render(<Capture/>);await Promise.resolve();});
 await act(async()=>{await vi.advanceTimersByTimeAsync(151);});
 expect(board.document?.id).toBe('board');
});
afterEach(()=>{act(()=>root.unmount());host.remove();vi.restoreAllMocks();vi.resetAllMocks();vi.useRealTimers();});
it('does not create recovery writes or save transactions for unchanged camera updates under storage exhaustion',async()=>{
 localStorage.setItem('fireatlas-whiteboard-draft:board:older','older draft');
 const writes=vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new DOMException('Full','QuotaExceededError');});
 await act(async()=>{board.onScene({elements:[{...element}],files:{}},false,{scrollX:4,scrollY:7,zoom:{value:1}});await vi.advanceTimersByTimeAsync(900);});
 expect(writes.mock.calls.filter(([key])=>key.startsWith('fireatlas-whiteboard-draft:'))).toHaveLength(0);
 expect(api.transact).not.toHaveBeenCalled();expect(board.status).toBe('Saved');
 expect(localStorage.getItem('fireatlas-whiteboard-draft:board:older')).toBe('older draft');
});
it('still saves a genuine edit when recovery storage is full and preserves earlier recoverable drafts',async()=>{
 localStorage.setItem('fireatlas-whiteboard-draft:board:older','older draft');
 vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new DOMException('Full','QuotaExceededError');});
 await act(async()=>{board.onScene({elements:[{...element,text:'Updated observation',version:2}],files:{}});});
 expect(board.status).toContain('Browser draft is full');
 await act(async()=>{await board.flush();});
 expect(api.transact).toHaveBeenCalledExactlyOnceWith('board',1,[{op:'patch_whiteboard',changes:[expect.objectContaining({id:'note',value:expect.objectContaining({text:'Updated observation'})})]}]);
 expect(board.status).toBe('Saved');expect(localStorage.getItem('fireatlas-whiteboard-draft:board:older')).toBe('older draft');
});
