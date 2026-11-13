import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

vi.mock('@excalidraw/excalidraw', () => ({
  CaptureUpdateAction: { IMMEDIATELY: 'immediate', NEVER:'never' },
  convertToExcalidrawElements: (items: any[]) => items.map(item=>({...item,angle:item.angle ?? 0,...(item.type==='arrow'?{startBinding:{elementId:item.start?.id},endBinding:{elementId:item.end?.id}}:{})})),
  newElementWith: (item: any, updates: any) => ({...item,...updates}),
  getCommonBounds: () => [0,0,100,100],
  exportToSvg: async () => document.createElementNS('http://www.w3.org/2000/svg','svg'),
  exportToBlob: async () => new Blob(['test visual'],{type:'image/png'}),
}));
vi.mock('../api', () => ({ uid: () => crypto.randomUUID(), api: {
  getDocument: vi.fn(), jarvisStart: vi.fn(), jarvisRun: vi.fn(), jarvisCancel: vi.fn(), jarvisConversation:vi.fn(), jarvisPreserveClaims:vi.fn(), snapshotPreview: vi.fn(), snapshotReport:vi.fn(), snapshotHeat:vi.fn(), snapshotReceipt:vi.fn(), datasetScatter:vi.fn(), datasetGroups:vi.fn(), dataset:vi.fn(), sourceDocuments:vi.fn(),
} }));
vi.mock('../lib/mapPreview',()=>({renderMapPreview:async()=> 'data:image/png;base64,cG5n',renderHeatPreview:async()=>({dataURL:'data:image/png;base64,cG5n',background:'frame'})}));
vi.mock('../lib/csvScatter',()=>({renderScatter:()=> 'data:image/png;base64,cG5n'}));
import { api } from '../api';
import { WhiteboardAssistant, wrapExplanation, wrapEvidenceText, requestsGroupedChart, requestsDiagram, requestsOrganize, requestsWholeBoardOrganization, requestsConnectSelection, requestsVisualInspection } from './WhiteboardAssistant';

let host: HTMLDivElement, root: ReturnType<typeof createRoot>;
beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  host = document.createElement('div'); document.body.append(host); root = createRoot(host);
  vi.mocked(api.snapshotReceipt).mockResolvedValue({receipt:{operation:'replay',payload:{}}} as any);
  vi.mocked(api.jarvisPreserveClaims).mockResolvedValue({bindings:{}});
  vi.mocked(api.jarvisConversation).mockResolvedValue({turns:[]});
});
afterEach(() => { act(() => root.unmount()); host.remove(); vi.resetAllMocks(); });
const click = (label: string) => {
  const button = [...host.querySelectorAll('button')].find((item) => item.textContent === label)!;
  act(() => button.click());
};

it('closes the companion with Escape and returns keyboard focus to its launcher', async () => {
  act(()=>root.render(<WhiteboardAssistant editor={{} as any} documentId="board" flush={async()=>true} busy={false}/>));
  await act(async()=>{click('Ask AI');await Promise.resolve();});
  const launcher=host.querySelector<HTMLButtonElement>('.assistant-launcher')!;
  const question=host.querySelector<HTMLTextAreaElement>('#whiteboard-question')!;
  expect(launcher.getAttribute('aria-controls')).toBe('investigation-assistant-panel');
  question.focus();
  act(()=>question.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true})));
  expect(host.querySelector('.whiteboard-assistant-panel')).toBeNull();
  expect(document.activeElement).toBe(launcher);
  expect(launcher.getAttribute('aria-expanded')).toBe('false');
});

it('loads recent conversation and retries a failed request', async () => {
  vi.mocked(api.jarvisConversation).mockRejectedValueOnce(Error('offline')).mockResolvedValueOnce({turns:[{question:'Why?',title:'Result',summary:'A short answer.',claims:[{label:'Count',value:4,unit:'cells'}]}]});
  const editor:any={};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  await act(async()=>{click('Ask AI');await Promise.resolve();});
  expect(host.textContent).toContain('couldn’t load');
  await act(async()=>{click('Retry');await Promise.resolve();});
  expect(host.textContent).toContain('A short answer.');
  expect(host.textContent).toContain('Count: 4 cells');
  expect(api.jarvisConversation).toHaveBeenCalledTimes(2);
});

it('reconnects to the same assistant run after a temporary network failure',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockRejectedValueOnce(Object.assign(Error('offline'),{status:0})).mockResolvedValueOnce({status:'completed',body:{title:'Result',summary:'Recovered answer'}});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[]};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain the investigation');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(host.textContent).toContain('Reconnecting');
  await act(async()=>{await new Promise(resolve=>setTimeout(resolve,800));});
  expect(api.jarvisStart).toHaveBeenCalledTimes(1);
  expect(api.jarvisRun).toHaveBeenCalledTimes(2);
  expect(host.textContent).toContain('Recovered answer');
});

it('can stop a run while reconnecting without restarting it',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockRejectedValue(Object.assign(Error('offline'),{status:0}));
  vi.mocked(api.jarvisCancel).mockResolvedValue({} as any);
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[]};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain the investigation');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  click('Stop');
  await act(async()=>{await new Promise(resolve=>setTimeout(resolve,800));});
  expect(api.jarvisCancel).toHaveBeenCalledWith('board','run');
  expect(api.jarvisRun).toHaveBeenCalledTimes(1);
  expect(host.textContent).toContain('Stopped.');
});

it('stops tracking and cancels the run on a non-retryable polling error',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockRejectedValue(Object.assign(Error('Access denied'),{status:403}));
  vi.mocked(api.jarvisCancel).mockResolvedValue({} as any);
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[]};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain the investigation');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(api.jarvisCancel).toHaveBeenCalledWith('board','run');
  expect(api.jarvisRun).toHaveBeenCalledTimes(1);
  expect(host.textContent).toContain('Access denied');
});

it('aborts a stalled status check and reconnects to the same run',async()=>{
  vi.useFakeTimers();
  try{
    vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
    vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
    vi.mocked(api.jarvisRun).mockImplementationOnce((_board,_run,signal)=>new Promise((_resolve,reject)=>{
      signal!.addEventListener('abort',()=>reject(Object.assign(Error('timeout'),{status:0})),{once:true});
    })).mockResolvedValueOnce({status:'completed',body:{title:'Result',summary:'Recovered answer'}});
    const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[]};
    act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
    click('Ask AI');type('Explain the investigation');
    await act(async()=>{click('Ask');await Promise.resolve();await Promise.resolve();await Promise.resolve();});
    expect(api.jarvisRun).toHaveBeenCalledTimes(1);
    await act(async()=>{await vi.advanceTimersByTimeAsync(10_000);});
    expect(host.textContent).toContain('Reconnecting');
    await act(async()=>{await vi.advanceTimersByTimeAsync(700);});
    expect(api.jarvisStart).toHaveBeenCalledTimes(1);
    expect(api.jarvisRun).toHaveBeenCalledTimes(2);
    expect(host.textContent).toContain('Recovered answer');
  }finally{vi.useRealTimers();}
});

it('aborts a pending status check when the user stops',async()=>{
  let signal:AbortSignal | undefined;
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisCancel).mockResolvedValue({} as any);
  vi.mocked(api.jarvisRun).mockImplementation((_board,_run,current)=>new Promise((_resolve,reject)=>{
    signal=current;signal!.addEventListener('abort',()=>reject(Object.assign(Error('aborted'),{status:0})),{once:true});
  }));
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[]};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain the investigation');
  await act(async()=>{click('Ask');await Promise.resolve();await Promise.resolve();await Promise.resolve();});
  click('Stop');
  expect(signal?.aborted).toBe(true);
  expect(api.jarvisCancel).toHaveBeenCalledWith('board','run');
});

it('ignores a history response after switching boards', async () => {
  let finish!:(value:{turns:{question:string;title:string;summary:string}[]})=>void;
  vi.mocked(api.jarvisConversation).mockReturnValueOnce(new Promise(resolve=>{finish=resolve;})).mockResolvedValueOnce({turns:[{question:'New board',title:'New',summary:'New answer'}]});
  const editor:any={};
  act(()=>root.render(<WhiteboardAssistant key="one" editor={editor} documentId="one" flush={async()=>true} busy={false}/>));
  click('Ask AI');
  act(()=>root.render(<WhiteboardAssistant key="two" editor={editor} documentId="two" flush={async()=>true} busy={false}/>));
  await act(async()=>{click('Ask AI');await Promise.resolve();finish({turns:[{question:'Old board',title:'Old',summary:'Old answer'}]});await Promise.resolve();});
  expect(host.textContent).toContain('New answer');
  expect(host.textContent).not.toContain('Old answer');
});

it('lets users watch the board while a request runs and reopen its update',async()=>{
  let finish!:(value:any)=>void;
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  const note={id:'note',type:'text',text:'A note',x:0,y:0,width:20,height:20};
  const editor:any={getAppState:()=>({selectedElementIds:{note:true}}),getSceneElements:()=>[note]};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain this');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  click('Watch on board');
  expect(host.querySelector('.whiteboard-assistant-panel')).toBeNull();
  expect(document.activeElement?.textContent).toContain('Working');
  await act(async()=>{finish({status:'completed',body:{title:'Finding',summary:'A result.'}});await new Promise(resolve=>setTimeout(resolve,0));});
  expect(host.textContent).toContain('View update');
  click('View update');
  expect(host.textContent).toContain('A result.');
});

it('organizes selected notes directly as one reversible scene update', async () => {
  const base={type:'text',width:100,height:50,angle:0,groupIds:[],frameId:null,containerId:null,locked:false,isDeleted:false};
  const items=[{...base,id:'a',x:0,y:0},{...base,id:'b',x:300,y:100}];
  const editor:any={getAppState:()=>({selectedElementIds:{a:true,b:true}}),getSceneElements:()=>items,updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Organize these notes');
  await act(async()=>{click('Ask');await Promise.resolve();});
  expect(api.jarvisStart).not.toHaveBeenCalled();
  expect(editor.updateScene,host.textContent || '').toHaveBeenCalledOnce();
  expect(editor.updateScene.mock.calls[0][0].elements[1]).toMatchObject({id:'b',x:140,y:0});
  expect(host.textContent).toContain('Use Undo');
  expect(host.querySelector('.assistant-canvas-cue--moved')?.textContent).toContain('Moved');
});

it('only treats an explicit organize request as a board action',()=>{
  expect(requestsOrganize('Please organize these notes')).toBe(true);
  expect(requestsOrganize('How should I organize these notes?')).toBe(false);
  expect(requestsOrganize('Organize these notes but do not move them')).toBe(false);
  expect(requestsWholeBoardOrganization('Organize the board')).toBe(true);
  expect(requestsWholeBoardOrganization('Please arrange everything')).toBe(true);
  expect(requestsWholeBoardOrganization('Organize these notes on the board')).toBe(false);
  expect(requestsWholeBoardOrganization('How should I organize the board?')).toBe(false);
});

it('recognizes an explicit connection request without interpreting a question as an action',()=>{
  expect(requestsConnectSelection('Connect these objects')).toBe(true);
  expect(requestsConnectSelection('Please link the selected notes')).toBe(true);
  expect(requestsConnectSelection('How should I connect these objects?')).toBe(false);
  expect(requestsConnectSelection('Connect these but do not move them')).toBe(false);
});
it('recognizes requests to inspect a visual without treating every diagram request as image inspection',()=>{
  expect(requestsVisualInspection('Describe this chart')).toBe(true);
  expect(requestsVisualInspection('What does this image show?')).toBe(true);
  expect(requestsVisualInspection('Draw a diagram of these notes')).toBe(false);
  expect(requestsVisualInspection('Explain and create a grouped chart')).toBe(false);
  expect(requestsVisualInspection('Explain and diagram this')).toBe(false);
});

it('organizes unlocked board objects even when only one item is selected',async()=>{
  const base={type:'rectangle',width:100,height:50,angle:0,groupIds:[],frameId:null,locked:false,isDeleted:false};
  const items=[{...base,id:'a',x:0,y:0},{...base,id:'b',x:300,y:100},{...base,id:'locked',x:700,y:400,locked:true}];
  const editor:any={getAppState:()=>({selectedElementIds:{a:true}}),getSceneElements:()=>items,updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Organize the board');
  await act(async()=>{click('Ask');await Promise.resolve();});
  expect(api.jarvisStart).not.toHaveBeenCalled();
  expect(editor.updateScene).toHaveBeenCalledOnce();
  const arranged=editor.updateScene.mock.calls[0][0].elements;
  expect(arranged.find((item:any)=>item.id==='b')).toMatchObject({x:140,y:0});
  expect(arranged.find((item:any)=>item.id==='locked')).toBe(items[2]);
  expect(host.textContent).toContain('Board organized');
});
const type = (value: string) => {
  const area = host.querySelector('textarea')!;
  act(() => { Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(area, value); area.dispatchEvent(new Event('input', { bubbles: true })); });
};

it('passes a selected labeled shape as a saved board note', async () => {
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Note',summary:'Compare the sensors.'}});
  const editor:any={getAppState:()=>({selectedElementIds:{shape:true}}),getSceneElements:()=>[
    {id:'shape',type:'rectangle'}, {id:'label',type:'text',containerId:'shape',text:'Compare the sensors'}
  ],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain this note');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(api.jarvisStart).toHaveBeenCalledWith('board',expect.objectContaining({selected_note_elements:['shape']}));
  expect(host.textContent).toContain('Compare the sensors.');
});

it('rejects a whole-board answer if board text changes while it is running', async () => {
  let finish!:(value:any)=>void;
  const items:any[]=[{id:'note',type:'text',text:'Original note'}];
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>items,updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain the investigation');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  items[0]={...items[0],text:'Edited note'};
  await act(async()=>{finish({status:'completed',body:{title:'Answer',summary:'Old answer'}});await new Promise(resolve=>setTimeout(resolve,0));});
  expect(host.textContent).toContain('board text changed');
  expect(host.textContent).not.toContain('Old answer');
});

it('keeps the single board table linked to an unselected explanation',async()=>{
  const chart={id:'chart',type:'frame',x:0,y:50,width:300,height:200,customData:{fireatlas:{documentId:'board',datasetId:'table',datasetHash:'hash'}}};
  const note={id:'note',type:'text',text:'Compare these readings',x:0,y:0,width:100,height:20};
  const items:any[]=[chart,note];
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Result',summary:'The table compares readings.'}});
  vi.mocked(api.dataset).mockResolvedValue({id:'table',sha256:'hash'} as any);
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>items,updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain the board');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(api.jarvisStart).toHaveBeenCalledWith('board',expect.objectContaining({selected_dataset_elements:[],selected_note_elements:[]}));
  click('Add explanation to board');
  const added=editor.updateScene.mock.calls[0][0].elements;
  expect(added.some((item:any)=>item.customData?.fireatlas?.datasetId==='table' && item.customData.fireatlas.datasetHash==='hash')).toBe(true);
});

it('rejects a changed selection during the pending board save', async () => {
  let finish!:(value:boolean)=>void;let selected:Record<string,boolean>={a:true};
  const editor:any={getAppState:()=>({selectedElementIds:selected}),getSceneElements:()=>[{id:'a',type:'text',text:'First'},{id:'b',type:'text',text:'Second'}]};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={()=>new Promise(resolve=>{finish=resolve;})} busy={false}/>));
  click('Ask AI');type('Explain this');click('Ask');
  selected={b:true};await act(async()=>{finish(true);await Promise.resolve();});
  expect(api.jarvisStart).not.toHaveBeenCalled();expect(host.textContent).toContain('selection changed');
});

it('rejects a source changed while the assistant is responding', async () => {
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  let finish!:(value:any)=>void;vi.mocked(api.jarvisRun).mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  const item={id:'note',type:'text',text:'Original'};
  const editor:any={getAppState:()=>({selectedElementIds:{note:true}}),getSceneElements:()=>[item]};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain this');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  item.text='Changed';await act(async()=>{finish({status:'completed',body:{title:'Answer',summary:'Old text'}});await Promise.resolve();});
  expect(host.textContent).toContain('source changed');expect(host.textContent).not.toContain('Old text');
});

it('refuses to focus or attach an answer after its source changes', async () => {
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Answer',summary:'Original source'}});
  const item={id:'note',type:'text',text:'Original'};
  const editor:any={getAppState:()=>({selectedElementIds:{note:true}}),getSceneElements:()=>[item],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain this');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  item.text='Changed';click('Show selected source');expect(host.textContent).toContain('source changed');
  click('Add explanation to board');expect(editor.updateScene).not.toHaveBeenCalled();
});

it('rejects source edits while saving a claim receipt', async () => {
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Answer',claims:[{label:'Count',value:3,result_id:'receipt',path:'/count'}]}});
  let finish!:(value:any)=>void;vi.mocked(api.jarvisPreserveClaims).mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  const item={id:'note',type:'text',text:'Original'};
  const editor:any={getAppState:()=>({selectedElementIds:{note:true}}),getSceneElements:()=>[item]};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain this');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  item.text='Changed';await act(async()=>{finish({bindings:{}});await Promise.resolve();});
  expect(host.textContent).toContain('source changed');expect(host.textContent).not.toContain('Count: 3');
});

it('rejects newly added text inside a selected shape while waiting', async () => {
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  let finish!:(value:any)=>void;vi.mocked(api.jarvisRun).mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  const items:any[]=[{id:'shape',type:'rectangle'},{id:'label',type:'text',containerId:'shape',text:'Original'}];
  const editor:any={getAppState:()=>({selectedElementIds:{shape:true}}),getSceneElements:()=>items};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain this');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  items.push({id:'new',type:'text',containerId:'shape',text:'Added'});
  await act(async()=>{finish({status:'completed',body:{title:'Answer',summary:'Old context'}});await Promise.resolve();});
  expect(host.textContent).toContain('source changed');expect(host.textContent).not.toContain('Old context');
});

it('does not offer to add an unavailable response as an explanation', async () => {
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Unable to finish the request',kind:'Assistant unavailable',summary:'Try asking again.',ai_wording_unavailable:true}});
  const note={id:'note',type:'text',text:'An observation',x:0,y:0,width:100,height:20};
  const editor:any={getAppState:()=>({selectedElementIds:{note:true}}),getSceneElements:()=>[note],updateScene:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('What does this suggest?');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(host.textContent).toContain('Try asking again.');
  expect(host.textContent).not.toContain('Add explanation to board');
  expect(editor.updateScene).not.toHaveBeenCalled();
});

it('passes selected owned evidence to the assistant and adds its answer as editable text', async () => {
  vi.mocked(api.getDocument).mockResolvedValue({ revision: 7, state: { cards: { card: { snapshot_id: 'snapshot' } } }, snapshots: { snapshot: { snapshot_sha256: 'hash' } } } as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({ id: 'run-1', status: 'queued' });
  vi.mocked(api.jarvisRun).mockResolvedValue({ status: 'completed', body: { title: 'Finding', summary: 'A supported summary.', claims: [{ label: 'Count', value: 3, unit: 'cells', result_id: 'evidence', path: '/count' }] } });
  const editor: any = { getAppState: () => ({ selectedElementIds: { box: true } }), getSceneElements: () => [{ id: 'box', x: 0, y: 0, width: 20, customData: { fireatlas: { documentId: 'board', cardId: 'card', snapshotId: 'snapshot', snapshotHash: 'hash' } } }], updateScene: vi.fn(), scrollToContent: vi.fn() };
  act(() => root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async () => true} busy={false} />));
  click('Ask AI'); type('Explain this');
  await act(async () => { click('Ask'); await new Promise((resolve) => setTimeout(resolve, 0)); });
  expect(api.jarvisStart).toHaveBeenCalledWith('board', expect.objectContaining({ base_revision: 7, selected_cards: ['card'], message: 'Explain this' }));
  expect(host.textContent).toContain('A supported summary.');
  click('Add explanation to board');
  expect(editor.updateScene).toHaveBeenCalledWith(expect.objectContaining({ elements: expect.arrayContaining([expect.objectContaining({ text: expect.stringContaining('Count: 3 cells'), customData: expect.objectContaining({ fireatlas: expect.objectContaining({ sourceCardIds: ['card'] }) }) })]) }));
  expect(editor.updateScene).toHaveBeenCalledWith(expect.objectContaining({ elements: expect.arrayContaining([expect.objectContaining({customData:expect.objectContaining({fireatlas:expect.objectContaining({originalElementIds:['box']})})})]) }));
  await act(async()=>{click('Show selected source');await new Promise(resolve=>setTimeout(resolve,80));});
  expect(editor.updateScene).toHaveBeenCalledWith(expect.objectContaining({appState:{selectedElementIds:{box:true}},captureUpdate:'never'}));
  expect(editor.scrollToContent).toHaveBeenCalledWith(expect.arrayContaining([expect.objectContaining({id:'box'})]),{fitToContent:true});
});

it('attaches preserved scientific evidence to an assistant claim', async () => {
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Finding',claims:[{label:'Count',value:3,unit:'cells',result_id:'temporary',path:'/count'}]}});
  vi.mocked(api.jarvisPreserveClaims).mockResolvedValue({bindings:{temporary:{documentId:'board',snapshotId:'snapshot',snapshotHash:'hash',resultId:'saved'}}});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Calculate the count');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(api.jarvisPreserveClaims).toHaveBeenCalledWith('board','run');
  click('Add explanation to board');
  expect(editor.updateScene).toHaveBeenCalledWith(expect.objectContaining({elements:expect.arrayContaining([expect.objectContaining({customData:{fireatlas:expect.objectContaining({snapshotId:'snapshot',snapshotHash:'hash',claims:[expect.objectContaining({result_id:'saved',value:3})]})}})])}));
});

it('submits a selected snapshot-only claim as saved evidence', async () => {
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{snapshot:{snapshot_sha256:'hash'}}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Saved result',summary:'The result can be compared.'}});
  const item={id:'claim',type:'text',text:'Count: 3',customData:{fireatlas:{documentId:'board',snapshotId:'snapshot',snapshotHash:'hash'}}};
  const editor:any={getAppState:()=>({selectedElementIds:{claim:true}}),getSceneElements:()=>[item],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain this result');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(api.jarvisStart).toHaveBeenCalledWith('board',expect.objectContaining({selected_snapshot_elements:['claim'],selected_cards:[]}));
});

it('passes the selected comparison view for server-side source verification', async () => {
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{card:{snapshot_id:'snapshot'}}},snapshots:{snapshot:{snapshot_sha256:'hash'}}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Comparison',summary:'Compare the selected view.'}});
  const ref={documentId:'board',cardId:'card',snapshotId:'snapshot',snapshotHash:'hash',kind:'finding-alternative',comparisonSeries:'viirs'};
  const editor:any={getAppState:()=>({selectedElementIds:{frame:true,label:true}}),getSceneElements:()=>[{id:'frame',customData:{fireatlas:ref}},{id:'label',customData:{fireatlas:ref}}],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain this view');
  await act(async()=>{click('Ask');await new Promise((resolve)=>setTimeout(resolve,0));});
  expect(api.jarvisStart).toHaveBeenCalledWith('board',expect.objectContaining({selected_cards:['card'],selected_comparison_elements:['frame']}));
});

it('places a challenge beside the selected finding in one scene update', async () => {
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{card:{snapshot_id:'snapshot'}}},snapshots:{snapshot:{snapshot_sha256:'hash'}}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Question',summary:'What else could explain the difference?'}});
  const selected={id:'finding',type:'rectangle',x:0,y:0,width:20,height:20,customData:{fireatlas:{documentId:'board',cardId:'card',snapshotId:'snapshot',snapshotHash:'hash'}}};
  const editor:any={getAppState:()=>({selectedElementIds:{finding:true}}),getSceneElements:()=>[selected],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');
  await act(async()=>{click('Challenge selection');await new Promise((resolve)=>setTimeout(resolve,0));});
  expect(api.jarvisStart).toHaveBeenCalledWith('board',expect.objectContaining({selected_cards:['card'],message:expect.stringContaining('Challenge the selected finding')}));
  expect(editor.updateScene).toHaveBeenCalledOnce();
  expect(editor.updateScene).toHaveBeenCalledWith(expect.objectContaining({elements:expect.arrayContaining([expect.objectContaining({type:'frame',name:'Challenge'})])}));
});

it('asks a relevant question when a Park timeline challenge falls back',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Fallback',ai_wording_unavailable:true,claims:[{label:'Fallback',value:2,unit:'records',result_id:'result',path:'/value'}]}});
  vi.mocked(api.dataset).mockResolvedValue({id:'park',sha256:'hash'} as any);
  const selected={id:'timeline',type:'text',text:'Park timeline',x:0,y:0,width:20,height:20,customData:{fireatlas:{documentId:'board',datasetId:'park',datasetHash:'hash',kind:'park-platform-chart'}}};
  const editor:any={getAppState:()=>({selectedElementIds:{timeline:true}}),getSceneElements:()=>[selected],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');await act(async()=>{click('Challenge selection');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).toHaveBeenCalledOnce();
  expect(api.jarvisPreserveClaims).not.toHaveBeenCalled();
  expect(JSON.stringify(editor.updateScene.mock.calls[0][0].elements)).toContain('How do the satellite observations compare');
  expect(JSON.stringify(editor.updateScene.mock.calls[0][0].elements)).not.toContain('What additional evidence could challenge');
  expect(host.textContent).not.toContain('Fallback: 2');
  click('Add explanation to board');
  expect(JSON.stringify(editor.updateScene.mock.calls[1][0].elements)).not.toContain('Fallback: 2');
});

it('keeps checked selected-table values in a Park challenge fallback',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Fallback',ai_wording_unavailable:true,claims:[{label:'MODIS',value:'348',unit:'reported value',result_id:'r',path:'/rows/0/0',source_binding:{documentId:'board',datasetId:'park',datasetHash:'hash',rowOffset:0}}]}});
  vi.mocked(api.dataset).mockResolvedValue({id:'park',sha256:'hash'} as any);
  const selected={id:'timeline',type:'text',text:'Park timeline',x:0,y:0,width:20,height:20,customData:{fireatlas:{documentId:'board',datasetId:'park',datasetHash:'hash',kind:'park-platform-chart'}}};
  const editor:any={getAppState:()=>({selectedElementIds:{timeline:true}}),getSceneElements:()=>[selected],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');await act(async()=>{click('Challenge selection');await new Promise(resolve=>setTimeout(resolve,0));});
  const elements=editor.updateScene.mock.calls[0][0].elements;
  expect(elements.some((item:any)=>item.text?.includes('MODIS: 348') && item.customData.fireatlas.datasetId==='park')).toBe(true);
  expect(elements.some((item:any)=>item.text?.includes('How do the satellite observations compare'))).toBe(true);
});

it('keeps the selected group values when challenge wording is unavailable',async()=>{
  const ref={documentId:'board',datasetId:'data',datasetHash:'hash',groupColumn:'area',valueColumn:'count',groupName:'A',groupMetric:'mean'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Fallback',ai_wording_unavailable:true,claims:[{label:'A mean',value:4,source_binding:ref}]}});
  vi.mocked(api.dataset).mockResolvedValue({id:'data',sha256:'hash'} as any);
  vi.mocked(api.datasetGroups).mockResolvedValue({dataset_id:'data',sha256:'hash',group_column:'area',value_column:'count',total_rows:2,groups:[{group:'A',rows:2,numeric_count:2,missing_count:0,non_numeric_count:0,mean:4}]});
  const selected={id:'bar',type:'rectangle',x:0,y:0,width:20,height:20,customData:{fireatlas:{...ref,kind:'dataset-group-chart'}}};
  const editor:any={getAppState:()=>({selectedElementIds:{bar:true}}),getSceneElements:()=>[selected],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');await act(async()=>{click('Challenge selection');await new Promise(resolve=>setTimeout(resolve,0));});
  const elements=editor.updateScene.mock.calls[0][0].elements;
  expect(elements.some((item:any)=>item.text?.includes('A mean: 4') && item.customData?.fireatlas?.groupName==='A')).toBe(true);
});

it('adds a verified grouped chart with the challenge in one board edit',async()=>{
  const binding={documentId:'board',datasetId:'data',datasetHash:'hash',groupColumn:'area',valueColumn:'count'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Challenge',summary:'What differs?',visualizations:[{kind:'csv-groups',binding}]}});
  vi.mocked(api.dataset).mockResolvedValue({id:'data',sha256:'hash'} as any);
  vi.mocked(api.datasetGroups).mockResolvedValue({dataset_id:'data',sha256:'hash',group_column:'area',value_column:'count',total_rows:1,groups:[{group:'A',rows:1,numeric_count:1,missing_count:0,non_numeric_count:0,mean:4}]});
  const selected={id:'bar',type:'rectangle',x:0,y:0,width:20,height:20,customData:{fireatlas:{...binding,kind:'dataset-group-chart'}}};
  const editor:any={getAppState:()=>({selectedElementIds:{bar:true}}),getSceneElements:()=>[selected],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');await act(async()=>{click('Challenge selection');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).toHaveBeenCalledOnce();
  const elements=editor.updateScene.mock.calls[0][0].elements;
  expect(elements.some((item:any)=>item.type==='frame' && item.customData?.fireatlas?.kind==='assistant-challenge')).toBe(true);
  expect(elements.some((item:any)=>item.type==='frame' && item.customData?.fireatlas?.kind==='dataset-group-chart')).toBe(true);
  expect(host.textContent).not.toContain('Add grouped chart');
});

it('does not place a challenge if the returned chart belongs to another table',async()=>{
  const binding={documentId:'board',datasetId:'other',datasetHash:'hash',groupColumn:'area',valueColumn:'count'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Challenge',summary:'What differs?',visualizations:[{kind:'csv-groups',binding}]}});
  vi.mocked(api.dataset).mockResolvedValue({id:'data',sha256:'hash'} as any);
  const selected={id:'bar',type:'rectangle',x:0,y:0,width:20,height:20,customData:{fireatlas:{documentId:'board',datasetId:'data',datasetHash:'hash'}}};
  const editor:any={getAppState:()=>({selectedElementIds:{bar:true}}),getSceneElements:()=>[selected],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');await act(async()=>{click('Challenge selection');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).not.toHaveBeenCalled();
  expect(host.textContent).toContain('challenge chart source changed');
});

it('does not attach a Park-specific question to a mixed selection',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{card:{snapshot_id:'snap'}}},snapshots:{snap:{snapshot_sha256:'hash'}}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Fallback',ai_wording_unavailable:true}});
  vi.mocked(api.dataset).mockResolvedValue({id:'park',sha256:'hash'} as any);
  const items=[{id:'timeline',type:'text',text:'Park',x:0,y:0,width:20,height:20,customData:{fireatlas:{documentId:'board',datasetId:'park',datasetHash:'hash',kind:'park-platform-chart'}}},{id:'other',type:'rectangle',x:50,y:0,width:20,height:20,customData:{fireatlas:{documentId:'board',cardId:'card',snapshotId:'snap',snapshotHash:'hash'}}}];
  const editor:any={getAppState:()=>({selectedElementIds:{timeline:true,other:true}}),getSceneElements:()=>items,updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');await act(async()=>{click('Challenge selection');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).toHaveBeenCalledOnce();expect(JSON.stringify(editor.updateScene.mock.calls[0][0].elements)).not.toContain('How do the satellite observations compare');
});

it('adds two exact saved sensor views along with the challenge', async () => {
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{card:{snapshot_id:'snapshot'}}},snapshots:{snapshot:{snapshot_sha256:'hash'}}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Question',summary:'How do sensors compare?'}});
  const measure=(first:number,second:number)=>({first,second,difference:second-first,percent:100,direction:'increase'});
  vi.mocked(api.snapshotReceipt).mockResolvedValue({receipt:{operation:'finding_comparison',payload:{schema:'fireatlas-finding-investigation-v1',selected_series:'modis',unit:'cell-days',comparison:{dates:['2024-05','2025-05'],series:{modis:measure(1,2),viirs:measure(3,6),adjusted:measure(2,4)}}}}} as any);
  const editor:any={getAppState:()=>({selectedElementIds:{finding:true}}),getSceneElements:()=>[{id:'finding',type:'rectangle',x:0,y:0,width:20,height:20,customData:{fireatlas:{documentId:'board',cardId:'card',snapshotId:'snapshot',snapshotHash:'hash'}}}],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');await act(async()=>{click('Challenge selection');await new Promise(resolve=>setTimeout(resolve,0));});
  const elements=editor.updateScene.mock.calls[0][0].elements;
  expect(elements.filter((item:any)=>item.type==='frame' && item.customData.fireatlas.kind==='finding-alternative')).toHaveLength(2);
  expect(elements.some((item:any)=>item.text==='6')).toBe(true);
  expect(elements.some((item:any)=>item.text?.includes('size of the change'))).toBe(true);
  expect(api.jarvisStart).toHaveBeenCalledWith('board',expect.objectContaining({whiteboard_challenge:true}));
});

it('does not place a challenge if the selected finding changes during the run', async () => {
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{card:{snapshot_id:'snapshot'}}},snapshots:{snapshot:{snapshot_sha256:'hash'}}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  let complete:(value:any)=>void=()=>{};
  vi.mocked(api.jarvisRun).mockImplementation(()=>new Promise(resolve=>{complete=resolve;}));
  const selected:any={id:'finding',type:'rectangle',x:0,y:0,width:20,height:20,customData:{fireatlas:{documentId:'board',cardId:'card',snapshotId:'snapshot',snapshotHash:'hash'}}};
  const editor:any={getAppState:()=>({selectedElementIds:{finding:true}}),getSceneElements:()=>[selected],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');await act(async()=>{click('Challenge selection');await new Promise(resolve=>setTimeout(resolve,0));});
  selected.customData.fireatlas.snapshotHash='changed';
  await act(async()=>{complete({status:'completed',body:{title:'Question',summary:'What else?'}});await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).not.toHaveBeenCalled();expect(host.textContent).toContain('selected finding changed');
});

it('allows moving a source without changing its meaning', async () => {
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  let finish!:(value:any)=>void;vi.mocked(api.jarvisRun).mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  const item={id:'note',type:'text',text:'Original',x:0};
  const editor:any={getAppState:()=>({selectedElementIds:{note:true}}),getSceneElements:()=>[item],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain this');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  item.x=100;await act(async()=>{finish({status:'completed',body:{title:'Answer',summary:'Original source'}});await Promise.resolve();});
  expect(host.textContent).toContain('Original source');await act(async()=>{click('Show selected source');await new Promise(resolve=>setTimeout(resolve,80));});expect(editor.scrollToContent).toHaveBeenCalled();
});

it('adds a searched table excerpt with its exact source row', async () => {
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Match',source_matches:[{kind:'csv',name:'weather.csv',source_id:'data',source_sha256:'hash',row_offset:3,column:'condition',excerpt:'smoke'}]}});
  vi.mocked(api.dataset).mockResolvedValue({id:'data',name:'weather.csv',sha256:'hash',columns:['condition'],row_count:4,offset:3,preview:[['smoke plume']]});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Find smoke');
  await act(async()=>{click('Ask');await new Promise((resolve)=>setTimeout(resolve,0));});
  expect(host.textContent).toContain('weather.csv · CSV record 5');
  await act(async()=>{click('Add source excerpt');await new Promise((resolve)=>setTimeout(resolve,0));});
  expect(api.dataset).toHaveBeenCalledWith('board','data',3);
  expect(editor.updateScene).toHaveBeenCalledWith(expect.objectContaining({elements:expect.arrayContaining([expect.objectContaining({customData:{fireatlas:expect.objectContaining({datasetId:'data',datasetHash:'hash',rowOffset:3})}})])}));
  expect(editor.updateScene.mock.calls[0][0].elements[0].text).toContain('CSV record 5 · condition');
});

it('opens the exact matched source from an assistant result', async () => {
  const match={kind:'pdf',name:'notes.pdf',source_id:'pdf',source_sha256:'hash',page:4,excerpt:'smoke'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Match',source_matches:[match]}});
  const openSource=vi.fn();
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false} onOpenSource={openSource}/>));
  click('Ask AI');type('Find smoke');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  click('Open original');
  expect(openSource).toHaveBeenCalledWith(match);
  expect(host.querySelector('[aria-label="Investigation assistant"]')).toBeNull();
});

it('does not start a request if pending board changes cannot be saved', async () => {
  const editor: any = {getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[]};
  act(() => root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async () => false} busy={false} />));
  click('Ask AI'); type('Explain');
  await act(async () => { click('Ask'); await Promise.resolve(); });
  expect(api.jarvisStart).not.toHaveBeenCalled();
  expect(host.textContent).toContain('Save your drawing');
});

it('passes a selected saved table to the assistant and keeps its source on the explanation', async () => {
  vi.mocked(api.getDocument).mockResolvedValue({ revision: 7, state: { cards: {} }, snapshots: {} } as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({ id:'run', status:'queued' });
  vi.mocked(api.jarvisRun).mockResolvedValue({ status:'completed', body:{ title:'Table', summary:'Inspect the readings.' } });
  const editor:any={getAppState:()=>({selectedElementIds:{box:true}}),getSceneElements:()=>[{id:'box',x:0,y:0,width:20,customData:{fireatlas:{documentId:'board',datasetId:'data',datasetHash:'hash'}}}],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain the table');
  await act(async()=>{click('Ask');await new Promise((resolve)=>setTimeout(resolve,0));});
  expect(api.jarvisStart).toHaveBeenCalledWith('board',expect.objectContaining({selected_dataset_elements:['box']}));
  click('Add explanation to board');
  expect(editor.updateScene).toHaveBeenCalledWith(expect.objectContaining({elements:expect.arrayContaining([expect.objectContaining({customData:{fireatlas:expect.objectContaining({datasetId:'data',datasetHash:'hash'})}})])}));
});

it('rechecks the table and adds an assistant-prepared grouped chart',async()=>{
  const binding={documentId:'board',datasetId:'data',datasetHash:'hash',groupColumn:'area',valueColumn:'value'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Groups',visualizations:[{kind:'csv-groups',binding}]}});
  vi.mocked(api.datasetGroups).mockResolvedValue({dataset_id:'data',sha256:'hash',group_column:'area',value_column:'value',total_rows:2,groups:[{group:'A',rows:2,numeric_count:2,missing_count:0,non_numeric_count:0,mean:3}]});
  const editor:any={getAppState:()=>({selectedElementIds:{box:true}}),getSceneElements:()=>[{id:'box',x:0,y:0,width:20,customData:{fireatlas:{documentId:'board',datasetId:'data',datasetHash:'hash'}}}],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Compare averages by area');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  await act(async()=>{click('Add grouped chart');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(api.datasetGroups).toHaveBeenCalledWith('board','data','area','value');
  expect(editor.updateScene).toHaveBeenCalledWith(expect.objectContaining({elements:expect.arrayContaining([expect.objectContaining({type:'frame',customData:{fireatlas:expect.objectContaining({kind:'dataset-group-chart',datasetId:'data'})}})])}));
});

it('automatically places a requested grouped chart once',async()=>{
  const binding={documentId:'board',datasetId:'data',datasetHash:'hash',groupColumn:'area',valueColumn:'value'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Groups',visualizations:[{kind:'csv-groups',binding}]}});
  vi.mocked(api.datasetGroups).mockResolvedValue({dataset_id:'data',sha256:'hash',group_column:'area',value_column:'value',total_rows:1,groups:[{group:'A',rows:1,numeric_count:1,missing_count:0,non_numeric_count:0,mean:3}]});
  const editor:any={getAppState:()=>({selectedElementIds:{box:true}}),getSceneElements:()=>[{id:'box',x:0,y:0,width:20,customData:{fireatlas:{documentId:'board',datasetId:'data',datasetHash:'hash'}}}],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Create a grouped chart by area');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).toHaveBeenCalledOnce();expect(host.textContent).toContain('Grouped chart added');expect(host.textContent).not.toContain('Add grouped chart');
  expect(requestsGroupedChart('Do not create a chart')).toBe(false);
});

it('creates a requested chart from the unselected board table',async()=>{
  const binding={documentId:'board',datasetId:'data',datasetHash:'hash',groupColumn:'UTC date',valueColumn:'MODIS_SP'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.dataset).mockResolvedValue({id:'data',sha256:'hash'} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Groups',summary:'The readings vary.',visualizations:[{kind:'csv-groups',binding}]}});
  vi.mocked(api.datasetGroups).mockResolvedValue({dataset_id:'data',sha256:'hash',group_column:'UTC date',value_column:'MODIS_SP',total_rows:1,groups:[{group:'2024-07-25',rows:1,numeric_count:1,missing_count:0,non_numeric_count:0,mean:603}]});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[{id:'frame',type:'frame',x:0,y:0,width:200,height:100,customData:{fireatlas:{documentId:'board',datasetId:'data',datasetHash:'hash'}}}],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Create a grouped chart by UTC date and explain');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).toHaveBeenCalledOnce();
  expect(editor.updateScene.mock.calls[0][0].elements).toEqual(expect.arrayContaining([expect.objectContaining({type:'frame',customData:{fireatlas:expect.objectContaining({kind:'dataset-group-chart',datasetId:'data'})}})]));
  expect(host.textContent).toContain('Explanation and grouped chart added');
});

it('places a table explanation and grouped chart in one edit',async()=>{
  const binding={documentId:'board',datasetId:'data',datasetHash:'hash',groupColumn:'area',valueColumn:'value'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Groups',summary:'Compare the groups.',visualizations:[{kind:'csv-groups',binding}]}});
  vi.mocked(api.datasetGroups).mockResolvedValue({dataset_id:'data',sha256:'hash',group_column:'area',value_column:'value',total_rows:1,groups:[{group:'A',rows:1,numeric_count:1,missing_count:0,non_numeric_count:0,mean:3}]});
  const editor:any={getAppState:()=>({selectedElementIds:{box:true}}),getSceneElements:()=>[{id:'box',x:0,y:0,width:20,customData:{fireatlas:{documentId:'board',datasetId:'data',datasetHash:'hash'}}}],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain and create a grouped chart');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).toHaveBeenCalledOnce();
  expect(editor.updateScene.mock.calls[0][0].elements).toEqual(expect.arrayContaining([expect.objectContaining({text:expect.stringContaining('Compare the groups.')}),expect.objectContaining({type:'frame',customData:{fireatlas:expect.objectContaining({kind:'dataset-group-chart'})}})]));
  expect(host.textContent).toContain('Explanation and grouped chart added');expect(host.textContent).not.toContain('Add explanation to board');
});

it('places a source-linked diagram with a grouped table chart in one edit',async()=>{
  const binding={documentId:'board',datasetId:'data',datasetHash:'hash',groupColumn:'area',valueColumn:'value'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Groups',summary:'Compare groups.',diagram:{nodes:[{id:'q',kind:'question',label:'What is supported?'}],edges:[]},visualizations:[{kind:'csv-groups',binding},{kind:'monthly-comparison',binding:{documentId:'board',snapshotId:'other',snapshotHash:'other'}}]}});
  vi.mocked(api.datasetGroups).mockResolvedValue({dataset_id:'data',sha256:'hash',group_column:'area',value_column:'value',total_rows:1,groups:[{group:'A',rows:1,numeric_count:1,missing_count:0,non_numeric_count:0,mean:3}]});
  const editor:any={getAppState:()=>({selectedElementIds:{box:true}}),getSceneElements:()=>[{id:'box',x:0,y:0,width:20,customData:{fireatlas:{documentId:'board',datasetId:'data',datasetHash:'hash'}}}],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain and draw a diagram and grouped chart');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).toHaveBeenCalledOnce();expect(editor.updateScene.mock.calls[0][0].elements).toEqual(expect.arrayContaining([
    expect.objectContaining({type:'frame',customData:{fireatlas:expect.objectContaining({kind:'dataset-group-chart'})}}),
    expect.objectContaining({type:'rectangle',customData:{fireatlas:expect.objectContaining({kind:'assistant-diagram',datasetId:'data',datasetHash:'hash'})}}),
    expect.objectContaining({type:'rectangle',label:expect.objectContaining({text:expect.stringContaining('Mean value by')}),customData:{fireatlas:expect.objectContaining({datasetId:'data'})}}),
    expect.objectContaining({text:expect.stringContaining('Compare groups.')})]));
  expect(host.textContent).toContain('Diagram and chart added');expect(host.textContent).not.toContain('Add diagram to board');
});

it('places the model diagram only when its table and columns match the chart',async()=>{
  const binding={documentId:'board',datasetId:'data',datasetHash:'hash',groupColumn:'area',valueColumn:'value'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Groups',diagram:{nodes:[{id:'source',kind:'evidence',label:'Selected table',binding},{id:'q',kind:'question',label:'Is this seasonal?'}],edges:[{source:'source',target:'q',relation:'question'}]},visualizations:[{kind:'csv-groups',binding}]}});
  vi.mocked(api.datasetGroups).mockResolvedValue({dataset_id:'data',sha256:'hash',group_column:'area',value_column:'value',total_rows:1,groups:[{group:'A',rows:1,numeric_count:1,missing_count:0,non_numeric_count:0,mean:3}]});
  const editor:any={getAppState:()=>({selectedElementIds:{box:true}}),getSceneElements:()=>[{id:'box',x:0,y:0,width:20,customData:{fireatlas:{documentId:'board',datasetId:'data',datasetHash:'hash'}}}],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Draw a diagram and grouped chart');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene.mock.calls[0][0].elements).toEqual(expect.arrayContaining([expect.objectContaining({type:'rectangle',label:expect.objectContaining({text:expect.stringContaining('Is this')}),customData:{fireatlas:expect.objectContaining(binding)}})]));
});

it('does not attach a diagram from different table columns to the chart',async()=>{
  const binding={documentId:'board',datasetId:'data',datasetHash:'hash',groupColumn:'area',valueColumn:'value'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Groups',diagram:{nodes:[{id:'source',kind:'evidence',label:'Selected table',binding:{...binding,valueColumn:'other'}},{id:'q',kind:'question',label:'Wrong question?'}],edges:[]},visualizations:[{kind:'csv-groups',binding}]}});
  vi.mocked(api.datasetGroups).mockResolvedValue({dataset_id:'data',sha256:'hash',group_column:'area',value_column:'value',total_rows:1,groups:[{group:'A',rows:1,numeric_count:1,missing_count:0,non_numeric_count:0,mean:3}]});
  const editor:any={getAppState:()=>({selectedElementIds:{box:true}}),getSceneElements:()=>[{id:'box',x:0,y:0,width:20,customData:{fireatlas:{documentId:'board',datasetId:'data',datasetHash:'hash'}}}],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Draw a diagram and grouped chart');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).toHaveBeenCalledOnce();expect(JSON.stringify(editor.updateScene.mock.calls[0][0].elements)).not.toContain('Wrong question?');
});

it('rejects a stale table source in a standalone diagram',async()=>{
  const binding={documentId:'board',datasetId:'data',datasetHash:'old',groupColumn:'area',valueColumn:'value'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Diagram',diagram:{nodes:[{id:'source',kind:'evidence',label:'Selected table',binding}],edges:[]}}});
  vi.mocked(api.dataset).mockResolvedValue({sha256:'new'} as any);
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Draw a diagram');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).not.toHaveBeenCalled();expect(host.textContent).toContain('diagram table changed');
});

it('does not place a standalone table diagram after switching boards',async()=>{
  const binding={documentId:'board',datasetId:'data',datasetHash:'hash',groupColumn:'area',valueColumn:'value'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Diagram',diagram:{nodes:[{id:'source',kind:'evidence',label:'Selected table',binding}],edges:[]}}});
  let finish!:(value:any)=>void;vi.mocked(api.dataset).mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Draw a diagram');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="other" flush={async()=>true} busy={false}/>));
  await act(async()=>{finish({sha256:'hash'});await Promise.resolve();});expect(editor.updateScene).not.toHaveBeenCalled();
});

it('rejects a changed explanation source before placing a grouped chart',async()=>{
  const binding={documentId:'board',datasetId:'data',datasetHash:'hash',groupColumn:'area',valueColumn:'value'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Groups',summary:'Compare the groups.',claims:[{label:'Value',value:3,source_binding:{documentId:'board',datasetId:'other',datasetHash:'old'}}],visualizations:[{kind:'csv-groups',binding}]}});
  vi.mocked(api.datasetGroups).mockResolvedValue({dataset_id:'data',sha256:'hash',group_column:'area',value_column:'value',total_rows:1,groups:[{group:'A',rows:1,numeric_count:1,missing_count:0,non_numeric_count:0,mean:3}]});
  vi.mocked(api.dataset).mockResolvedValue({sha256:'new'} as any);
  const editor:any={getAppState:()=>({selectedElementIds:{box:true}}),getSceneElements:()=>[{id:'box',x:0,y:0,width:20,customData:{fireatlas:{documentId:'board',datasetId:'data',datasetHash:'hash'}}}],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain and create a grouped chart');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).not.toHaveBeenCalled();expect(host.textContent).toContain('explanation table changed');
});

it('does not place table explanation after a board switch during verification',async()=>{
  const binding={documentId:'board',datasetId:'data',datasetHash:'hash',groupColumn:'area',valueColumn:'value'};
  let finish!:(value:any)=>void;
  vi.mocked(api.getDocument).mockResolvedValueOnce({revision:7,state:{cards:{}},snapshots:{}} as any).mockReturnValueOnce(new Promise(resolve=>{finish=resolve;}));
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Groups',summary:'Compare groups.',visualizations:[{kind:'csv-groups',binding}]}});
  vi.mocked(api.datasetGroups).mockResolvedValue({dataset_id:'data',sha256:'hash',group_column:'area',value_column:'value',total_rows:1,groups:[{group:'A',rows:1,numeric_count:1,missing_count:0,non_numeric_count:0,mean:3}]});
  const editor:any={getAppState:()=>({selectedElementIds:{box:true}}),getSceneElements:()=>[{id:'box',x:0,y:0,width:20,customData:{fireatlas:{documentId:'board',datasetId:'data',datasetHash:'hash'}}}],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain and create a grouped chart');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="other" flush={async()=>true} busy={false}/>));
  await act(async()=>{finish({revision:7,state:{cards:{}},snapshots:{}});await Promise.resolve();});
  expect(editor.updateScene).not.toHaveBeenCalled();
});

it('automatically draws a requested evidence-linked diagram',async()=>{
  const binding={documentId:'board',cardId:'card',snapshotId:'snap',snapshotHash:'hash'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{card:{snapshot_id:'snap'}}},snapshots:{snap:{snapshot_sha256:'hash'}}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Diagram',diagram:{nodes:[{id:'a',label:'Evidence',kind:'evidence',binding}],edges:[]}}});
  const selected={id:'box',x:0,y:0,width:20,customData:{fireatlas:binding}};
  const editor:any={getAppState:()=>({selectedElementIds:{box:true}}),getSceneElements:()=>[selected],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Draw a diagram of this evidence');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).toHaveBeenCalledOnce();expect(host.textContent).toContain('Diagram added');expect(host.textContent).not.toContain('Add diagram to board');
  expect(requestsDiagram('Do not draw a diagram')).toBe(false);
});

it('draws a note-only diagram without altering the original note',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Board',summary:'Compare sensors.',diagram:{nodes:[{id:'a',label:'Compare sensors.',kind:'interpretation'},{id:'b',label:'What differs?',kind:'question'}],edges:[{source:'a',target:'b',relation:'question'}]}}});
  const note={id:'note',type:'text',text:'Compare sensors',x:0,y:0,width:100,height:20};
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[note],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Draw a diagram of the investigation');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).toHaveBeenCalledOnce();
  expect(editor.updateScene.mock.calls[0][0].elements).toEqual(expect.arrayContaining([note,expect.objectContaining({type:'arrow'})]));
  expect(editor.updateScene.mock.calls[0][0].elements).toEqual(expect.arrayContaining([expect.objectContaining({customData:expect.objectContaining({fireatlas:expect.objectContaining({kind:'assistant-diagram',originalElementIds:['note']})})})]));
  expect(host.textContent).toContain('Diagram added');
});

it('links a whole-board explanation to the same prioritized notes as its diagram',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Board',summary:'Compare sensors.',diagram:{nodes:[{id:'a',label:'Compare sensors.',kind:'interpretation'}],edges:[]}}});
  const generated=Array.from({length:20},(_,i)=>({id:`ai-${i}`,type:'text',text:'Earlier output',x:i*20,y:0,width:10,height:10,customData:{fireatlas:{documentId:'board',kind:'assistant-explanation'}}}));
  const note={id:'new-note',type:'text',text:'New observation',x:0,y:30,width:100,height:20};
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[...generated,note],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain and draw a diagram of the investigation');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  const items=editor.updateScene.mock.calls[0][0].elements;
  const diagram=items.find((item:any)=>item.customData?.fireatlas?.kind==='assistant-diagram');
  const explanation=items.find((item:any)=>item.customData?.fireatlas?.kind==='assistant-explanation' && item.id!=='ai-0' && !item.id?.startsWith('ai-'));
  expect(diagram.customData.fireatlas.originalElementIds[0]).toBe('new-note');
  expect(explanation.customData.fireatlas.originalElementIds).toEqual(diagram.customData.fireatlas.originalElementIds);
  expect(diagram.customData.fireatlas.originalElementIds).toHaveLength(20);
});

it('opens the newly created diagram on the canvas without losing the answer',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Board',summary:'Compare sensors.',diagram:{nodes:[{id:'a',label:'Compare sensors.',kind:'interpretation'}],edges:[]}}});
  let items:any[]=[{id:'note',type:'text',text:'Compare sensors',x:0,y:0,width:100,height:20}];
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>items,updateScene:vi.fn(update=>{if(update.elements)items=update.elements;}),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Draw a diagram of the investigation');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(host.textContent).toContain('View diagram');
  await act(async()=>{click('View diagram');await new Promise(resolve=>setTimeout(resolve,80));});
  expect(editor.scrollToContent).toHaveBeenCalledTimes(2);
  click('Ask AI');
  expect(host.textContent).toContain('Compare sensors.');
  await act(async()=>{click('Read key idea');await new Promise(resolve=>setTimeout(resolve,80));});
  expect(editor.scrollToContent.mock.calls.at(-1)[0]).toEqual([expect.objectContaining({customData:{fireatlas:expect.objectContaining({nodeKind:'interpretation'})}})]);
  expect(editor.scrollToContent.mock.calls.at(-1)[1]).toMatchObject({fitToContent:true,minZoom:.8,maxZoom:1});
});

it('focuses diagram nodes separately from the explanation card',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Finding',summary:'Compare the sensors.',diagram:{nodes:[{id:'a',label:'Evidence',kind:'evidence'},{id:'b',label:'Question',kind:'question'}],edges:[{source:'a',target:'b',relation:'question'}]}}});
  let items:any[]=[{id:'note',type:'text',text:'Compare sensors',x:0,y:0,width:100,height:20}];
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>items,updateScene:vi.fn(update=>{if(update.elements)items=update.elements;}),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain and draw a diagram');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(host.textContent).toContain('View explanation');
  await act(async()=>{click('View diagram');await new Promise(resolve=>setTimeout(resolve,80));});
  const nodes=editor.scrollToContent.mock.calls.at(-1)[0];
  expect(nodes.length).toBeGreaterThan(0);
  expect(nodes.every((item:any)=>item.customData?.fireatlas?.kind==='assistant-diagram')).toBe(true);
  expect(editor.scrollToContent.mock.calls.at(-1)[1]).toMatchObject({fitToContent:true,viewportZoomFactor:.95});
  click('Ask AI');
  await act(async()=>{click('View explanation');await new Promise(resolve=>setTimeout(resolve,80));});
  const explanation=editor.scrollToContent.mock.calls.at(-1)[0];
  expect(explanation).toHaveLength(1);
  expect(explanation[0].customData.fireatlas.kind).toBe('assistant-explanation');
});

it('adds an explanation and diagram together for the planned combined request',async()=>{
  const binding={documentId:'board',cardId:'card',snapshotId:'snapshot',snapshotHash:'hash'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{card:{snapshot_id:'snapshot'}}},snapshots:{snapshot:{snapshot_sha256:'hash'}}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Finding',summary:'Compare the sensors.',diagram:{nodes:[{id:'a',label:'Evidence',kind:'evidence',binding},{id:'b',label:'Question',kind:'question'}],edges:[{source:'a',target:'b',relation:'question'}]}}});
  const source={id:'source',type:'text',text:'Selected finding',x:0,y:0,width:100,customData:{fireatlas:binding}};
  const editor:any={getAppState:()=>({selectedElementIds:{source:true}}),getSceneElements:()=>[source],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain and diagram this');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene,host.textContent || '').toHaveBeenCalledOnce();
  const added=editor.updateScene.mock.calls[0][0].elements;
  expect(added).toEqual(expect.arrayContaining([expect.objectContaining({type:'arrow'}),expect.objectContaining({text:expect.stringContaining('Compare the sensors.'),customData:expect.objectContaining({fireatlas:expect.objectContaining({originalElementIds:['source']})})})]));
  expect(host.textContent).toContain('Explanation and diagram added');
  expect(host.textContent).not.toContain('Add explanation to board');
  expect(requestsDiagram('Explain and diagram this')).toBe(true);
  expect(requestsDiagram('Explain this but do not draw a diagram')).toBe(false);
});

it('places a requested comparison chart and diagram in one board edit',async()=>{
  const binding={documentId:'board',cardId:'card',snapshotId:'snapshot',snapshotHash:'hash',title:'Comparison'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{card:{snapshot_id:'snapshot'}}},snapshots:{snapshot:{snapshot_sha256:'hash'}}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Finding',summary:'Compare the sensors.',diagram:{nodes:[{id:'a',label:'Evidence',kind:'evidence',binding}],edges:[]},visualizations:[{kind:'monthly-comparison',binding}]}});
  vi.mocked(api.snapshotPreview).mockResolvedValue({snapshot_sha256:'hash',svg:'',visual:{kind:'monthly-comparison',unit:'cell-days',rows:[{date:'2020-01',modis:1,reference:2,prediction:1.5}]}});
  const source={id:'source',type:'text',text:'Selected finding',x:0,y:0,width:100,customData:{fireatlas:binding}};
  const editor:any={getAppState:()=>({selectedElementIds:{source:true}}),getSceneElements:()=>[source],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain and draw a diagram and a chart');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).toHaveBeenCalledOnce();
  expect(editor.updateScene.mock.calls[0][0].elements).toEqual(expect.arrayContaining([
    expect.objectContaining({text:expect.stringContaining('Compare the sensors.')}),
    expect.objectContaining({text:expect.stringContaining('2020-01  |  1  |  2  |  1.5')})]));
  expect(host.textContent).toContain('Diagram and chart added');expect(host.textContent).not.toContain('Add comparison chart');
});

it('retains a retry action when the automatic comparison preview fails',async()=>{
  const binding={documentId:'board',cardId:'card',snapshotId:'snapshot',snapshotHash:'hash',title:'Comparison'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{card:{snapshot_id:'snapshot'}}},snapshots:{snapshot:{snapshot_sha256:'hash'}}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Finding',diagram:{nodes:[{id:'a',label:'Evidence',kind:'evidence',binding}],edges:[]},visualizations:[{kind:'monthly-comparison',binding}]}});
  vi.mocked(api.snapshotPreview).mockRejectedValue(Error('offline'));
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Draw a diagram and a chart');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).toHaveBeenCalledOnce();expect(host.textContent).toContain('chart could not be added');expect(host.textContent).toContain('Add comparison chart');
});

it('does not apply a pending automatic chart after switching boards',async()=>{
  const binding={documentId:'board',cardId:'card',snapshotId:'snapshot',snapshotHash:'hash',title:'Comparison'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{card:{snapshot_id:'snapshot'}}},snapshots:{snapshot:{snapshot_sha256:'hash'}}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Finding',diagram:{nodes:[{id:'a',label:'Evidence',kind:'evidence',binding}],edges:[]},visualizations:[{kind:'monthly-comparison',binding}]}});
  let finish!:(value:any)=>void;vi.mocked(api.snapshotPreview).mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Draw a diagram and a chart');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(api.snapshotPreview).toHaveBeenCalledOnce();
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="other" flush={async()=>true} busy={false}/>));
  await act(async()=>{finish({snapshot_sha256:'hash',svg:'',visual:{kind:'monthly-comparison',rows:[]}});await Promise.resolve();});
  expect(editor.updateScene).not.toHaveBeenCalled();
});

it('never adds a stale comparison chart automatically',async()=>{
  const binding={documentId:'board',cardId:'card',snapshotId:'snapshot',snapshotHash:'hash',title:'Comparison'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{card:{snapshot_id:'snapshot'}}},snapshots:{snapshot:{snapshot_sha256:'hash'}}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Finding',diagram:{nodes:[{id:'a',label:'Evidence',kind:'evidence',binding}],edges:[]},visualizations:[{kind:'monthly-comparison',binding}]}});
  vi.mocked(api.snapshotPreview).mockResolvedValue({snapshot_sha256:'changed',svg:'',visual:{kind:'monthly-comparison',unit:'cell-days',rows:[{date:'2020-01',modis:999,reference:2,prediction:1.5}]}});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Draw a diagram and a chart');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).toHaveBeenCalledOnce();expect(host.textContent).toContain('chart could not be added');
  expect(editor.updateScene.mock.calls[0][0].elements.every((item:any)=>item.customData?.fireatlas?.kind!=='comparison-chart')).toBe(true);
});

it('prevents duplicate explanation while the combined placement is saving',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Answer',summary:'A finding',diagram:{nodes:[{id:'a',label:'Question',kind:'question'}],edges:[]}}});
  let finish!:(value:boolean)=>void;let calls=0;
  const flush=()=>++calls===1?Promise.resolve(true):new Promise<boolean>(resolve=>{finish=resolve;});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={flush} busy={false}/>));
  click('Ask AI');type('Explain and diagram this');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect([...host.querySelectorAll('button')].find(button=>button.textContent==='Add explanation to board')?.disabled).toBe(true);
  click('Add explanation to board');expect(editor.updateScene).not.toHaveBeenCalled();
  await act(async()=>{finish(true);await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).toHaveBeenCalledOnce();
});

it('clears pending manual diagram loading when the board becomes busy',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Answer',diagram:{nodes:[{id:'a',label:'Question',kind:'question'}],edges:[]}}});
  let finish!:(value:boolean)=>void;let calls=0;
  const flush=()=>++calls===1?Promise.resolve(true):new Promise<boolean>(resolve=>{finish=resolve;});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={flush} busy={false}/>));
  click('Ask AI');type('Explain this');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  await act(async()=>{click('Add diagram to board');await Promise.resolve();});
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={flush} busy={true}/>));
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={flush} busy={false}/>));
  await act(async()=>{finish(true);await Promise.resolve();});
  expect(editor.updateScene).not.toHaveBeenCalled();
  expect([...host.querySelectorAll('button')].find(button=>button.textContent==='Add diagram to board')?.disabled).toBe(false);
});

it('offers the explanation when the requested diagram is unavailable',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Answer',summary:'A finding'}});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain and diagram this');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(host.textContent).toContain('diagram is unavailable');expect(host.textContent).toContain('Add explanation to board');
});

it('rejects a changed claim source before placing a combined explanation',async()=>{
  vi.mocked(api.getDocument).mockResolvedValueOnce({revision:1,state:{cards:{}},snapshots:{}} as any)
    .mockResolvedValueOnce({revision:2,state:{cards:{card:{snapshot_id:'changed'}}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Answer',summary:'A finding',claims:[{label:'Count',value:3,binding:{documentId:'board',cardId:'card',snapshotId:'original',snapshotHash:'hash'}}],diagram:{nodes:[{id:'a',label:'Question',kind:'question'}],edges:[]}}});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain and diagram this');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).not.toHaveBeenCalled();expect(host.textContent).toContain('explanation source changed');
});

it('refuses a diagram when a cited source has changed',async()=>{
  const binding={documentId:'board',cardId:'card',snapshotId:'snap',snapshotHash:'old'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{card:{snapshot_id:'snap'}}},snapshots:{snap:{snapshot_sha256:'new'}}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Diagram',diagram:{nodes:[{id:'a',label:'Evidence',kind:'evidence',binding}],edges:[]}}});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Draw a diagram');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).not.toHaveBeenCalled();expect(host.textContent).toContain('diagram source changed');
});

it('asks about a selected PDF page and keeps its page reference', async () => {
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Paper',summary:'The page describes an observation.'}});
  const editor:any={getAppState:()=>({selectedElementIds:{paper:true}}),getSceneElements:()=>[{id:'paper',x:0,y:0,width:20,customData:{fireatlas:{documentId:'board',sourceDocumentId:'source',sourceDocumentHash:'hash',page:2}}}],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain this page');
  await act(async()=>{click('Ask');await new Promise((resolve)=>setTimeout(resolve,0));});
  expect(api.jarvisStart).toHaveBeenCalledWith('board',expect.objectContaining({selected_source_elements:['paper']}));
  click('Add explanation to board');
  expect(editor.updateScene).toHaveBeenCalledWith(expect.objectContaining({elements:expect.arrayContaining([expect.objectContaining({customData:{fireatlas:expect.objectContaining({sourceDocumentId:'source',sourceDocumentHash:'hash',page:2})}})])}));
});

it('rechecks the selected table and automatically places a requested scatter plot', async () => {
  const binding={documentId:'board',datasetId:'data',datasetHash:'hash',xColumn:'x',yColumn:'y'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Plot',visualizations:[{kind:'csv-scatter',binding}]}});
  vi.mocked(api.datasetScatter).mockResolvedValue({dataset_id:'data',sha256:'hash',name:'data.csv',x_column:'x',y_column:'y',points:[{row:2,x:0,y:1}],skipped_rows:0,total_rows:1});
  const editor:any={getAppState:()=>({selectedElementIds:{box:true}}),getSceneElements:()=>[{id:'box',x:0,y:0,width:20,customData:{fireatlas:{documentId:'board',datasetId:'data',datasetHash:'hash'}}}],addFiles:vi.fn(),updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Plot x against y');
  await act(async()=>{click('Ask');await new Promise((resolve)=>setTimeout(resolve,0));});
  expect(api.datasetScatter).toHaveBeenCalledWith('board','data','x','y');
  expect(editor.addFiles).toHaveBeenCalledOnce();
  expect(host.textContent).not.toContain('Add scatter plot');
  expect(editor.updateScene).toHaveBeenCalledWith(expect.objectContaining({elements:expect.arrayContaining([expect.objectContaining({customData:{fireatlas:expect.objectContaining({datasetId:'data',datasetHash:'hash',xColumn:'x',yColumn:'y'})}})])}));
});

it('places a scatter plot and its requested explanation in one edit',async()=>{
  const binding={documentId:'board',datasetId:'data',datasetHash:'hash',xColumn:'x',yColumn:'y'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Plot',summary:'Compare the columns.',visualizations:[{kind:'csv-scatter',binding}]}});
  vi.mocked(api.datasetScatter).mockResolvedValue({dataset_id:'data',sha256:'hash',name:'data.csv',x_column:'x',y_column:'y',points:[{row:2,x:0,y:1}],skipped_rows:0,total_rows:1});
  const editor:any={getAppState:()=>({selectedElementIds:{box:true}}),getSceneElements:()=>[{id:'box',x:0,y:0,width:20,customData:{fireatlas:{documentId:'board',datasetId:'data',datasetHash:'hash'}}}],addFiles:vi.fn(),updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain and plot x against y');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).toHaveBeenCalledOnce();expect(editor.updateScene.mock.calls[0][0].elements).toEqual(expect.arrayContaining([expect.objectContaining({type:'image'}),expect.objectContaining({text:expect.stringContaining('Compare the columns.')})]));
  expect(host.textContent).toContain('Explanation and chart added');
});

it('adds the selected table diagram alongside a scatter plot',async()=>{
  const binding={documentId:'board',datasetId:'data',datasetHash:'hash',xColumn:'x',yColumn:'y'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Plot',visualizations:[{kind:'csv-scatter',binding}]}});
  vi.mocked(api.datasetScatter).mockResolvedValue({dataset_id:'data',sha256:'hash',name:'data.csv',x_column:'x',y_column:'y',points:[{row:2,x:0,y:1}],skipped_rows:0,total_rows:1});
  const editor:any={getAppState:()=>({selectedElementIds:{box:true}}),getSceneElements:()=>[{id:'box',x:0,y:0,width:20,customData:{fireatlas:{documentId:'board',datasetId:'data',datasetHash:'hash'}}}],addFiles:vi.fn(),updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Draw a diagram and plot x against y');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).toHaveBeenCalledOnce();expect(editor.updateScene.mock.calls[0][0].elements).toEqual(expect.arrayContaining([expect.objectContaining({type:'image'}),expect.objectContaining({type:'rectangle',label:expect.objectContaining({text:expect.stringContaining('y versus x')}),customData:{fireatlas:expect.objectContaining({kind:'assistant-diagram',datasetId:'data'})}})]));
});

it('refuses an assistant scatter plot if the saved source hash changed', async () => {
  const binding={documentId:'board',datasetId:'data',datasetHash:'old',xColumn:'x',yColumn:'y'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Plot',visualizations:[{kind:'csv-scatter',binding}]}});
  vi.mocked(api.datasetScatter).mockResolvedValue({dataset_id:'data',sha256:'new',name:'data.csv',x_column:'x',y_column:'y',points:[{row:2,x:0,y:1}],skipped_rows:0,total_rows:1});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],addFiles:vi.fn(),updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Plot x against y');
  await act(async()=>{click('Ask');await new Promise((resolve)=>setTimeout(resolve,0));});
  await act(async()=>{click('Add scatter plot');await new Promise((resolve)=>setTimeout(resolve,0));});
  expect(editor.addFiles).not.toHaveBeenCalled();
  expect(host.textContent).toContain('table source changed');
});

it('adds a chart from the saved preview selected by the assistant', async () => {
  const binding={documentId:'board',cardId:'card',snapshotId:'snapshot',snapshotHash:'hash',title:'Comparison'};
  vi.mocked(api.getDocument).mockResolvedValue({ revision: 7, state: { cards: { card: { snapshot_id:'snapshot' } } }, snapshots:{snapshot:{snapshot_sha256:'hash'}} } as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({ id:'run', status:'queued' });
  vi.mocked(api.jarvisRun).mockResolvedValue({ status:'completed', body:{ title:'Comparison', visualizations:[{kind:'monthly-comparison',binding}] } });
  vi.mocked(api.snapshotPreview).mockResolvedValue({ snapshot_sha256:'hash', svg:'', visual:{kind:'monthly-comparison', unit:'cell-days', rows:[{date:'2020-01',modis:1,reference:2,prediction:1.5}]}});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(() => root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Show chart');
  await act(async()=>{click('Ask');await new Promise((resolve)=>setTimeout(resolve,0));});
  await act(async()=>{click('Add comparison chart');await new Promise((resolve)=>setTimeout(resolve,0));});
  expect(api.snapshotPreview).toHaveBeenCalledWith('board','snapshot','chart');
  expect(editor.updateScene).toHaveBeenCalledWith(expect.objectContaining({elements:expect.arrayContaining([expect.objectContaining({text:expect.stringContaining('2020-01  |  1  |  2  |  1.5')})])}));
});

it('automatically creates a requested saved comparison chart',async()=>{
  const binding={documentId:'board',cardId:'card',snapshotId:'snapshot',snapshotHash:'hash',title:'Comparison'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{card:{snapshot_id:'snapshot'}}},snapshots:{snapshot:{snapshot_sha256:'hash'}}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Finding',summary:'Compare the sensors.',visualizations:[{kind:'monthly-comparison',binding}]}});
  vi.mocked(api.snapshotPreview).mockResolvedValue({snapshot_sha256:'hash',svg:'',visual:{kind:'monthly-comparison',rows:[{date:'2020-01',modis:1,reference:2,prediction:1.5}]}});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain and chart this');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).toHaveBeenCalledOnce();expect(host.textContent).toContain('Explanation and chart added');expect(host.textContent).not.toContain('Add comparison chart');
  expect(editor.updateScene.mock.calls[0][0].elements).toEqual(expect.arrayContaining([expect.objectContaining({text:expect.stringContaining('Compare the sensors.')})]));
});

it('retains the chart action if automatic placement finds a changed snapshot',async()=>{
  const binding={documentId:'board',cardId:'card',snapshotId:'snapshot',snapshotHash:'hash',title:'Comparison'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{card:{snapshot_id:'snapshot'}}},snapshots:{snapshot:{snapshot_sha256:'changed'}}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Finding',visualizations:[{kind:'monthly-comparison',binding}]}});
  vi.mocked(api.snapshotPreview).mockResolvedValue({snapshot_sha256:'hash',svg:'',visual:{kind:'monthly-comparison',rows:[{date:'2020-01',modis:1,reference:2,prediction:1.5}]}});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Create a chart');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).not.toHaveBeenCalled();expect(host.textContent).toContain('source changed');expect(host.textContent).toContain('Add comparison chart');
});

it('does not place an automatic chart after the board changes',async()=>{
  const binding={documentId:'board',cardId:'card',snapshotId:'snapshot',snapshotHash:'hash',title:'Comparison'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Finding',visualizations:[{kind:'monthly-comparison',binding}]}});
  let finish!:(value:any)=>void;vi.mocked(api.snapshotPreview).mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Create a chart');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="other" flush={async()=>true} busy={false}/>));
  await act(async()=>{finish({snapshot_sha256:'hash',svg:'',visual:{kind:'monthly-comparison',rows:[]}});await Promise.resolve();});
  expect(editor.updateScene).not.toHaveBeenCalled();
});

it('allows retry after an automatic chart preview fails',async()=>{
  const binding={documentId:'board',cardId:'card',snapshotId:'snapshot',snapshotHash:'hash',title:'Comparison'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{card:{snapshot_id:'snapshot'}}},snapshots:{snapshot:{snapshot_sha256:'hash'}}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Finding',visualizations:[{kind:'monthly-comparison',binding}]}});
  vi.mocked(api.snapshotPreview).mockRejectedValueOnce(Error('offline')).mockResolvedValueOnce({snapshot_sha256:'hash',svg:'',visual:{kind:'monthly-comparison',rows:[{date:'2020-01',modis:1,reference:2,prediction:1.5}]}});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Create a chart');await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).not.toHaveBeenCalled();expect(host.textContent).toContain('offline');
  await act(async()=>{click('Add comparison chart');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).toHaveBeenCalledOnce();
});

it('refuses an evidence preview after the underlying card changes', async () => {
  vi.mocked(api.getDocument).mockResolvedValue({ revision: 8, state: { cards: { card: { snapshot_id: 'new' } } }, snapshots: {} } as any);
  const editor: any = { getAppState: () => ({ selectedElementIds: { box: true } }), getSceneElements: () => [{ id: 'box', customData: { fireatlas: { documentId: 'board', cardId: 'card', snapshotId: 'old', snapshotHash: 'hash' } } }] };
  act(() => root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async () => true} busy={false} />));
  click('Ask AI'); type('Explain');
  await act(async () => { click('Ask'); await new Promise((resolve) => setTimeout(resolve, 0)); });
  expect(api.jarvisStart).not.toHaveBeenCalled();
  expect(host.textContent).toContain('no longer matches');
});

it('sends an unrelated selected drawing as visual context, not whole-board notes', async () => {
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Visual',summary:'A drawing.'}});
  const editor: any = { getAppState: () => ({ selectedElementIds: { drawing: true } }), getSceneElements: () => [{ id: 'drawing',type:'rectangle',x:0,y:0,width:100,height:100 }],getFiles:()=>({}) };
  act(() => root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async () => true} busy={false} />));
  click('Ask AI'); type('Explain');
  await act(async () => { click('Ask'); await new Promise((resolve) => setTimeout(resolve, 30)); });
  expect(api.jarvisStart).toHaveBeenCalledWith('board',expect.objectContaining({selected_note_elements:[],visual_capture:{element_ids:['drawing'],png:btoa('test visual')}}));
  expect(host.textContent).toContain('A drawing.');
});

it('rejects a visual answer if its image file changes during the request',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  let finish!:(value:any)=>void;
  vi.mocked(api.jarvisRun).mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  const files:any={file:{dataURL:'data:image/png;base64,b2xk'}};
  const editor:any={getAppState:()=>({selectedElementIds:{image:true}}),getSceneElements:()=>[{id:'image',type:'image',fileId:'file',x:0,y:0,width:100,height:100}],getFiles:()=>files};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Describe this');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,30));});
  files.file.dataURL='data:image/png;base64,bmV3';
  await act(async()=>{finish({status:'completed',body:{title:'Visual',summary:'Old image.'}});await Promise.resolve();});
  expect(host.textContent).toContain('selected source changed');
  expect(host.textContent).not.toContain('Old image.');
});

it('rejects a visual answer if a selected drawing changes appearance',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  let finish!:(value:any)=>void;
  vi.mocked(api.jarvisRun).mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  const shape:any={id:'shape',type:'rectangle',x:0,y:0,width:100,height:100,backgroundColor:'red'};
  const editor:any={getAppState:()=>({selectedElementIds:{shape:true}}),getSceneElements:()=>[shape],getFiles:()=>({})};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Describe this');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,30));});
  shape.backgroundColor='blue';
  await act(async()=>{finish({status:'completed',body:{title:'Visual',summary:'Red shape.'}});await Promise.resolve();});
  expect(host.textContent).toContain('selected source changed');
  expect(host.textContent).not.toContain('Red shape.');
});

it('retains long source identifiers in an explanation', () => {
  const identifier = 'x'.repeat(130);
  expect(wrapExplanation(`Source ${identifier}`).replace(/\s/g, '')).toBe(`Source${identifier}`);
});

it('wraps an unbroken evidence-card value without dropping its characters',()=>{
  const value='x'.repeat(130);const lines=wrapEvidenceText(value).split('\n');
  expect(lines.every(line=>line.length<=33)).toBe(true);expect(lines.join('')).toBe(value);
});

it('opens the companion directly when entering from first-use guidance',async()=>{
  await act(async()=>{root.render(<WhiteboardAssistant editor={{} as any} documentId="board" initialOpen flush={async()=>true} busy={false}/>);await Promise.resolve();});
  expect(host.querySelector('.whiteboard-assistant-panel')).not.toBeNull();
  expect(host.querySelector('.assistant-launcher')?.getAttribute('aria-expanded')).toBe('true');
  expect(host.textContent).toContain('Explain and diagram this');
  expect(document.activeElement).toBe(host.querySelector('#whiteboard-question'));
});
it('opens the evidence picker from the companion guide without starting an AI request',async()=>{
  const onAddEvidence=vi.fn();
  await act(async()=>{root.render(<WhiteboardAssistant editor={{} as any} documentId="board" initialOpen flush={async()=>true} busy={false} onAddEvidence={onAddEvidence}/>);await Promise.resolve();});
  click('Add evidence');
  expect(onAddEvidence).toHaveBeenCalledOnce();
  expect(host.querySelector('.whiteboard-assistant-panel')).toBeNull();
  expect(api.jarvisStart).not.toHaveBeenCalled();
});

it('places a requested scientific coordinate figure with a durable source instead of a text diagram',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Coordinates',summary:'Original source coordinates.',claims:[],data_views:[{kind:'coordinates',result_id:'evidence'}]}});
  vi.mocked(api.jarvisPreserveClaims).mockResolvedValue({bindings:{evidence:{documentId:'board',snapshotId:'snapshot',snapshotHash:'hash',resultId:'saved'}}});
  vi.mocked(api.snapshotReport).mockResolvedValue({verification:{verified:true},snapshot:{id:'snapshot',snapshot_sha256:'hash',method:{id:'original-records'},scope:{start:'2024-07-27',end:'2024-07-27',source:'MODIS_SP'}}} as any);
  vi.mocked(api.snapshotPreview).mockResolvedValue({svg:'<svg/>',visual:{kind:'coordinates'},snapshot_sha256:'hash'});
  const updateScene=vi.fn(),addFiles=vi.fn();
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],addFiles,updateScene,scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Show Park Fire coordinates');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(api.snapshotPreview).toHaveBeenCalledWith('board','snapshot','coordinates',undefined,'MODIS_SP');
  expect(addFiles).toHaveBeenCalledOnce();
  const elements=updateScene.mock.calls[0][0].elements;
  expect(elements.filter((item:any)=>item.type==='image')).toHaveLength(1);
  expect(elements.find((item:any)=>item.type==='image').customData.fireatlas).toMatchObject({documentId:'board',snapshotId:'snapshot',snapshotHash:'hash',viewKind:'coordinates'});
  expect(elements.some((item:any)=>item.customData?.fireatlas?.kind==='assistant-diagram')).toBe(false);
  expect(host.querySelector('.whiteboard-assistant-panel')).toBeNull();
});

it('refuses to place a scientific view when its saved receipt hash has changed',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Calendar',claims:[],data_views:[{kind:'calendar',result_id:'evidence'}]}});
  vi.mocked(api.jarvisPreserveClaims).mockResolvedValue({bindings:{evidence:{documentId:'board',snapshotId:'snapshot',snapshotHash:'hash',resultId:'saved'}}});
  vi.mocked(api.snapshotReport).mockResolvedValue({verification:{verified:true},snapshot:{snapshot_sha256:'changed'}} as any);
  const updateScene=vi.fn(),addFiles=vi.fn();
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],addFiles,updateScene,scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Show Park calendar');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(updateScene).not.toHaveBeenCalled();expect(addFiles).not.toHaveBeenCalled();
  expect(host.textContent).toContain('scientific view source changed');
});

it('keeps drawings and movements made while a scientific figure is rendering',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Coordinates',claims:[],data_views:[{kind:'coordinates',result_id:'evidence'}]}});
  vi.mocked(api.jarvisPreserveClaims).mockResolvedValue({bindings:{evidence:{documentId:'board',snapshotId:'snapshot',snapshotHash:'hash',resultId:'saved'}}});
  vi.mocked(api.snapshotReport).mockResolvedValue({verification:{verified:true},snapshot:{id:'snapshot',snapshot_sha256:'hash',method:{id:'original-records'},scope:{start:'2024-07-27',end:'2024-07-27',source:'MODIS_SP'}}} as any);
  let resolvePreview!:(value:any)=>void;
  vi.mocked(api.snapshotPreview).mockImplementation(()=>new Promise(resolve=>{resolvePreview=resolve;}));
  let scene:any[]=[{id:'existing',type:'rectangle',x:0,y:0,width:100,height:100,angle:0}];
  const updateScene=vi.fn(),editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>scene,addFiles:vi.fn(),updateScene,scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Show Park Fire coordinates');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  scene=[{...scene[0],x:5000},{id:'manual-new',type:'ellipse',x:5200,y:40,width:100,height:100,angle:0}];
  await act(async()=>{resolvePreview({svg:'<svg/>',visual:{kind:'coordinates'},snapshot_sha256:'hash'});await new Promise(resolve=>setTimeout(resolve,0));});
  const placed=updateScene.mock.calls[0][0].elements;
  expect(placed.find((item:any)=>item.id==='existing').x).toBe(5000);
  expect(placed.some((item:any)=>item.id==='manual-new')).toBe(true);
  expect(placed.find((item:any)=>item.type==='image').x).toBeGreaterThan(5300);
});

it('adds a source-linked editable pin and neutral connections for related scientific views',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Candidates',summary:'Temporal profiles do not establish shared causes.',claims:[],data_views:[{kind:'similar',result_id:'profiles'},{kind:'coordinates',result_id:'candidate'}]}});
  const binding={documentId:'board',snapshotId:'snapshot',snapshotHash:'hash',resultId:'saved'};
  vi.mocked(api.jarvisPreserveClaims).mockResolvedValue({bindings:{profiles:binding,candidate:binding}});
  vi.mocked(api.snapshotReport).mockResolvedValue({verification:{verified:true},snapshot:{id:'snapshot',snapshot_sha256:'hash',method:{id:'records'},scope:{start:'2012-03-23',end:'2012-03-23',source:'MODIS_SP'}}} as any);
  vi.mocked(api.snapshotPreview).mockResolvedValue({svg:'<svg/>',visual:{kind:'coordinates'},snapshot_sha256:'hash'});
  let scene:any[]=[];
  const updateScene=vi.fn((update:any)=>{scene=update.elements;});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>scene,addFiles:vi.fn(),updateScene,scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Find similar thermal profiles, connect the views, and add a pinned note');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  const pin=scene.find(item=>item.customData?.fireatlas?.kind==='assistant-analysis-note');
  expect(pin.type).toBe('rectangle');expect(pin.locked).not.toBe(true);
  expect(pin.label.text.replace(/\s+/g,' ')).toContain('do not establish shared causes');
  expect(pin.customData.fireatlas.sourceBindings).toEqual([expect.objectContaining({documentId:'board',snapshotId:'snapshot',snapshotHash:'hash'}),expect.objectContaining({snapshotId:'snapshot'})]);
  expect(scene.filter(item=>item.type==='arrow')).toHaveLength(2);
  expect(updateScene).toHaveBeenCalledOnce();
});

it('keeps source notes available without appending them to the main answer',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Comparison',summary:'Compare the same sensor across nearby dates.',limitations:['Source method details remain available.']}});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Explain the pattern');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  const notes=host.querySelector<HTMLDetailsElement>('.assistant-source-notes');
  expect(notes).not.toBeNull();expect(notes!.open).toBe(false);
  expect(notes!.textContent).toContain('Source method details remain available.');
  expect([...host.querySelectorAll('article > p')].some(item=>item.textContent==='Source method details remain available.')).toBe(false);
});

it('exposes real-data starters when the island opens',async()=>{
  act(()=>root.render(<WhiteboardAssistant editor={{} as any} documentId="board" flush={async()=>true} busy={false}/>));
  await act(async()=>{click('Ask AI');await Promise.resolve();});
  expect(host.querySelector<HTMLDetailsElement>('.assistant-data-starters')?.open).toBe(true);
  expect([...host.querySelectorAll('.assistant-data-starters button')].map(item=>item.textContent)).toContain('Park heatmap');
});

it('challenges a selected analysis note using its frozen source bindings',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{snapshot:{snapshot_sha256:'hash'}}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Alternative',summary:'Repeated observations could explain the pattern. Check acquisition times.'}});
  const note={id:'note',type:'text',text:'Thermal detection pattern',x:0,y:0,width:200,height:40,customData:{fireatlas:{documentId:'board',kind:'assistant-analysis-note',sourceBindings:[{documentId:'board',snapshotId:'snapshot',snapshotHash:'hash'}]}}};
  const editor:any={getAppState:()=>({selectedElementIds:{note:true}}),getSceneElements:()=>[note],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');await act(async()=>{click('Challenge selection');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(api.jarvisStart).toHaveBeenCalledWith('board',expect.objectContaining({selected_snapshot_elements:['note'],selected_note_elements:['note'],whiteboard_challenge:true}));
  expect(JSON.stringify(editor.updateScene.mock.calls[0][0].elements)).toContain('Repeated observations could explain');
});

it('routes a typed challenge through frozen evidence and preserves the actual question',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:7,state:{cards:{}},snapshots:{snapshot:{snapshot_sha256:'hash'}}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Alternative',summary:'Repeated observations could explain the pattern. Compare grid cells and acquisition times.'}});
  const note={id:'note',type:'text',text:'Detection totals',x:0,y:0,width:100,height:30,customData:{fireatlas:{documentId:'board',sourceBindings:[{documentId:'board',snapshotId:'snapshot',snapshotHash:'hash'}]}}};
  const editor:any={getAppState:()=>({selectedElementIds:{note:true}}),getSceneElements:()=>[note],updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Challenge this: could repeated overpasses explain the count?');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(api.jarvisStart).toHaveBeenCalledWith('board',expect.objectContaining({whiteboard_challenge:true,message:'Challenge this: could repeated overpasses explain the count?',selected_snapshot_elements:['note']}));
  expect(JSON.stringify(editor.updateScene.mock.calls[0][0].elements)).toContain('Compare grid cells');
});

it.each(['commit','stop','concurrent edit'])('animates a scientific view before its atomic %s outcome',async outcome=>{
  vi.stubGlobal('matchMedia',()=>({matches:true}));
  let frameId=0;
  const frames=new Map<number,FrameRequestCallback>();
  vi.stubGlobal('requestAnimationFrame',(callback:FrameRequestCallback)=>{frames.set(++frameId,callback);return frameId;});
  vi.stubGlobal('cancelAnimationFrame',(id:number)=>frames.delete(id));
  const step=async (time:number)=>act(async()=>{
    const callbacks=[...frames.values()];frames.clear();
    for(const callback of callbacks)callback(time);
  });
  const canvas=document.createElement('div');
  canvas.className='whiteboard-canvas';
  Object.defineProperties(canvas,{clientWidth:{value:390},clientHeight:{value:500}});
  canvas.getBoundingClientRect=()=>new DOMRect(0,140,390,500);
  host.append(canvas);
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Calendar',claims:[],data_views:[{kind:'calendar',result_id:'evidence'}]}});
  vi.mocked(api.jarvisPreserveClaims).mockResolvedValue({bindings:{evidence:{documentId:'board',snapshotId:'snapshot',snapshotHash:'hash',resultId:'saved'}}});
  vi.mocked(api.snapshotReport).mockResolvedValue({verification:{verified:true},snapshot:{id:'snapshot',snapshot_sha256:'hash',method:{id:'records'},scope:{start:'2024-07-25',end:'2024-07-28',source:'MODIS'}}} as any);
  vi.mocked(api.snapshotPreview).mockResolvedValue({svg:'<svg/>',visual:{kind:'calendar'},snapshot_sha256:'hash'});
  const scene:any[]=[];
  const editor:any={
    getAppState:()=>({selectedElementIds:{},zoom:{value:1},scrollX:80,scrollY:60}),
    getSceneElements:()=>scene,getFiles:()=>({}),addFiles:vi.fn(),updateScene:vi.fn(),scrollToContent:vi.fn(),
  };
  try {
    // Keep the canvas mounted beside the React tree, as it is in the real board.
    const wrapper=document.createElement('div');
    host.before(wrapper);wrapper.className='whiteboard-shell';wrapper.append(host,canvas);
    try {
      act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
      click('Ask AI');type('Show Park calendar');
      await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
      const stage=document.querySelector<HTMLElement>('.assistant-placement')!;
      expect(stage,host.textContent || '').toBeTruthy();
      expect(editor.scrollToContent).toHaveBeenCalledWith(expect.any(Array),expect.objectContaining({animate:true}));
      await step(0);
      const pointer=stage.querySelector<HTMLElement>('.assistant-placement-cursor')!;
      const start=pointer.style.transform;
      await step(730);
      expect(pointer.style.transform).not.toBe(start);
      expect(stage.querySelector<HTMLElement>('.assistant-placement-art')?.style.clipPath).toContain('%');
      expect(editor.addFiles).not.toHaveBeenCalled();
      expect(editor.updateScene).not.toHaveBeenCalled();
      if(outcome==='stop')click('Stop');
      if(outcome==='concurrent edit')scene.push({id:'owner-edit'});
      await step(1200);
      expect(document.querySelector('.assistant-placement')).toBeNull();
      if(outcome==='commit'){
        expect(editor.addFiles).toHaveBeenCalledOnce();
        expect(editor.updateScene).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({
          captureUpdate:'immediate',elements:expect.arrayContaining([expect.objectContaining({type:'image',customData:{fireatlas:expect.objectContaining({snapshotId:'snapshot',snapshotHash:'hash'})}})]),
        }));
      }else{
        expect(editor.addFiles).not.toHaveBeenCalled();
        expect(editor.updateScene).not.toHaveBeenCalled();
        if(outcome==='concurrent edit')expect(host.textContent).toContain('The board changed while drawing');
      }
    } finally {
      wrapper.before(host);wrapper.remove();
    }
  } finally {
    vi.unstubAllGlobals();
  }
});

it('lists catalog heatmaps as separate Add buttons and submits the chosen scope',async()=>{
  const option={label:'Camp Fire',detail:'2018-11-09 UTC · detection density',question:'Show a heatmap of Camp Fire on 2018-11-09.'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValueOnce({status:'completed',body:{title:'Available heatmaps',kind:'View catalog',view_options:[option]}})
    .mockResolvedValueOnce({status:'completed',body:{title:'Saved heatmap',kind:'Saved scientific view'}});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[]};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('What heatmaps can you bring?');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  const row=host.querySelector('.assistant-view-options li')!;
  expect(row.textContent).toContain('2018-11-09 UTC');
  const add=row.querySelector<HTMLButtonElement>('button[aria-label="Add Camp Fire heatmap"]')!;
  await act(async()=>{add.click();await new Promise(resolve=>setTimeout(resolve,0));});
  expect(api.jarvisStart).toHaveBeenLastCalledWith('board',expect.objectContaining({message:option.question}));
});


it('places the archive-selected close-up with the returned case name and source',async()=>{
  const title='Park Fire · California close-up';
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title,data_views:[{kind:'heatmap',result_id:'archive',title}]}});
  vi.mocked(api.jarvisPreserveClaims).mockResolvedValue({bindings:{archive:{documentId:'board',snapshotId:'snapshot',snapshotHash:'hash',resultId:'saved'}}});
  vi.mocked(api.snapshotReport).mockResolvedValue({verification:{verified:true},snapshot:{
    id:'snapshot',snapshot_sha256:'hash',method:{id:'replay'},scope:{start:'2024-07-25',end:'2024-07-25',day:'2024-07-25',source:'MODIS_SP'},
  }} as any);
  vi.mocked(api.snapshotHeat).mockResolvedValue({snapshot_sha256:'hash',visual:{day:'2024-07-25'}});
  const updateScene=vi.fn();
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],addFiles:vi.fn(),updateScene,scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Show a closeup heatmap of a wildfire that happened in california');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(api.snapshotHeat).toHaveBeenCalledWith('board','snapshot','2024-07-25','MODIS_SP');
  expect(updateScene).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({elements:expect.arrayContaining([
    expect.objectContaining({type:'image',customData:{fireatlas:expect.objectContaining({snapshotId:'snapshot',source:'MODIS_SP',title})}}),
  ])}));
});


it('places a place heatmap and calendar in one board update from the same receipt',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  const kinds=['firms-region-heatmap','firms-region-calendar'];
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{
    title:'Rajshahi',summary:'Three UTC days checked.',
    data_views:kinds.map(kind=>({kind,result_id:'same-receipt'})),
  }});
  vi.mocked(api.jarvisPreserveClaims).mockResolvedValue({bindings:{
    'same-receipt':{documentId:'board',snapshotId:'snapshot',snapshotHash:'hash',resultId:'saved'},
  }});
  vi.mocked(api.snapshotReport).mockResolvedValue({verification:{verified:true},snapshot:{
    id:'snapshot',snapshot_sha256:'hash',method:{id:'firms'},scope:{start:'2026-11-08',end:'2026-11-10'},
  }} as any);
  vi.mocked(api.snapshotPreview).mockImplementation(async (_document,_snapshot,kind)=>({
    snapshot_sha256:'hash',svg:'<svg/>',visual:{kind,title:'Rajshahi'},
  }));
  vi.mocked(api.snapshotHeat).mockResolvedValue({snapshot_sha256:'hash',visual:{title:'Rajshahi',source:'VIIRS_NOAA20_NRT',interval:{start:'2026-11-08',end:'2026-11-10'}}});
  const updateScene=vi.fn();
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],addFiles:vi.fn(),updateScene,scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Provide heatmap and reading calendar for Rajshahi');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(api.snapshotHeat).toHaveBeenCalledWith('board','snapshot');
  expect(updateScene.mock.calls[0][0].elements[0].customData.fireatlas.source).toBe('VIIRS_NOAA20_NRT');
  expect(vi.mocked(api.snapshotPreview).mock.calls.map(call=>call[2])).toEqual(['firms-region-calendar']);
  expect(updateScene).toHaveBeenCalledOnce();
  expect(updateScene.mock.calls[0][0].elements.map((item:any)=>[
    item.type,item.customData.fireatlas.viewKind,item.customData.fireatlas.snapshotId,
  ])).toEqual(kinds.map(kind=>['image',kind,'snapshot']));
});

const comparisonFixture=()=>({kind:'regional-comparison',title:'Peak days across years',mode:'annual_peaks',rank_by:'occupied_cells',domain:[0,2],note:'Synthetic test',panels:[2023,2024,2025].map((year,i)=>({
  label:'Synthetic area',year,day:`${year}-05-01`,start:`${year}-05-01`,end:`${year}-05-01`,search_start:`${year}-01-01`,search_end:`${year}-12-31`,
  product:'VIIRS_NOAA20_SP',sensor:'NOAA-20 VIIRS',occupied_cells:i+1,detections:i+2,cell_delta:i,record_delta:i,state:'queried',tied_dates:[],
  hotspots:[{longitude:88.6,latitude:24.4,detections:2}],weather:{status:'unavailable'},heat:{scope:{bbox:[88,24,89,25]},domain:[0,2]},
}))});
function mockComparison(){
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Comparison',summary:'A model interpretation.',data_views:[{kind:'regional-comparison',result_id:'r'}]}});
  vi.mocked(api.jarvisPreserveClaims).mockResolvedValue({bindings:{r:{documentId:'board',snapshotId:'s',snapshotHash:'h',resultId:'saved'}}});
  vi.mocked(api.snapshotReport).mockResolvedValue({verification:{verified:true},snapshot:{id:'s',snapshot_sha256:'h'}} as any);
  vi.mocked(api.snapshotPreview).mockResolvedValue({snapshot_sha256:'h',svg:'<svg/>',visual:comparisonFixture()});
}
it('places all comparison maps, native annotations and model interpretation as one reversible edit',async()=>{
  mockComparison();
  const manual={id:'manual',type:'text',text:'Keep my research note',x:0,y:0,width:50,height:30};
  const updateScene=vi.fn(),addFiles=vi.fn();
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[manual],addFiles,updateScene,scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Compare peak days across three years for Synthetic area.');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(updateScene).toHaveBeenCalledOnce();expect(addFiles.mock.calls[0][0]).toHaveLength(3);
  const scene=updateScene.mock.calls[0][0];expect(scene.captureUpdate).toBe('immediate');expect(scene.elements[0]).toEqual(manual);
  expect(scene.elements.filter((item:any)=>item.type==='image')).toHaveLength(3);
  expect(scene.elements.filter((item:any)=>item.type==='ellipse')).toHaveLength(3);
  expect(scene.elements.some((item:any)=>item.text==='A model interpretation.')).toBe(true);
});
it('refuses a stale comparison source before placing any files or elements',async()=>{
  mockComparison();vi.mocked(api.snapshotPreview).mockResolvedValue({snapshot_sha256:'wrong',svg:'<svg/>',visual:comparisonFixture()});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],addFiles:vi.fn(),updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Compare heatmaps for Synthetic area.');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.addFiles).not.toHaveBeenCalled();expect(editor.updateScene).not.toHaveBeenCalled();
  expect(host.textContent).toContain('could not be verified');
});
it('retries saved comparison placement without repeating research and retains the interpretation',async()=>{
  mockComparison();vi.mocked(api.snapshotPreview).mockRejectedValueOnce(Error('Temporary preview failure')).mockResolvedValue({snapshot_sha256:'h',svg:'<svg/>',visual:comparisonFixture()});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],addFiles:vi.fn(),updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Compare heatmaps for Synthetic area.');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(editor.updateScene).not.toHaveBeenCalled();expect(host.textContent).toContain('Temporary preview failure');
  await act(async()=>{click('Add scientific views');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(api.jarvisStart).toHaveBeenCalledOnce();expect(editor.updateScene).toHaveBeenCalledOnce();
  expect(editor.updateScene.mock.calls[0][0].elements.some((item:any)=>item.text==='A model interpretation.')).toBe(true);
});
it('never places a comparison after switching boards during preview preparation',async()=>{
  mockComparison();let finish:(value:any)=>void=()=>{};
  vi.mocked(api.snapshotPreview).mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],addFiles:vi.fn(),updateScene:vi.fn(),scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Compare heatmaps for Synthetic area.');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="another-board" flush={async()=>true} busy={false}/>));
  await act(async()=>{finish({snapshot_sha256:'h',svg:'<svg/>',visual:comparisonFixture()});await Promise.resolve();});
  expect(editor.addFiles).not.toHaveBeenCalled();expect(editor.updateScene).not.toHaveBeenCalled();
});

it('labels the only saved heatmap from its verified coordinates without invoking inference',async()=>{
  const target={id:'map',type:'image',x:10,y:20,width:960,height:540,angle:0,scale:[1,1],groupIds:[],
    customData:{fireatlas:{documentId:'board',snapshotId:'s',snapshotHash:'h',kind:'assistant-data-view',viewKind:'firms-region-heatmap'}}};
  const updateScene=vi.fn();
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[target],updateScene,scrollToContent:vi.fn()};
  vi.mocked(api.snapshotReport).mockResolvedValue({verification:{verified:true},snapshot:{snapshot_sha256:'h'}} as any);
  vi.mocked(api.snapshotHeat).mockResolvedValue({snapshot_sha256:'h',visual:{scope:{bbox:[88,21,90,23]},
    points:[{longitude:89,latitude:22},{longitude:120,latitude:22}]}});
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Can you add labelings to the places where the thermal readings were found?');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(api.jarvisStart).not.toHaveBeenCalled();
  expect(updateScene).toHaveBeenCalledOnce();
  const placed=updateScene.mock.calls[0][0].elements;
  expect(placed[2].label.text).toBe('22.000°, 89.000°');
  expect(placed[2].customData.fireatlas.snapshotHash).toBe('h');
  expect(placed[2].groupIds).toContain(placed[0].groupIds[0]);
});

it('pins returned public references as an undoable linked board action',async()=>{
  const source={title:'VIIRS fire observations',url:'https://doi.org/10.1234/reference',snippet:'Journal',provider:'Crossref'};
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Public reference search',web_sources:[source]}});
  const updateScene=vi.fn();
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[],updateScene,scrollToContent:vi.fn()};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Find papers on VIIRS fire detection and pin the results');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(updateScene).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({captureUpdate:'immediate',
    elements:[expect.objectContaining({link:source.url,label:expect.objectContaining({text:expect.stringContaining(source.title)})})]}));
});

it('keeps team billing opt-in, submits the explicit choice, and resets it on board changes',async()=>{
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Result',summary:'Checked evidence.'}});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[]};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');
  const team=host.querySelectorAll<HTMLButtonElement>('.research-mode button')[1];
  expect(team.getAttribute('aria-pressed')).toBe('false');
  act(()=>team.click());expect(host.textContent).toContain('Up to $0.02 extra');
  type('Review the existing evidence.');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  expect(vi.mocked(api.jarvisStart).mock.calls[0][1]).toMatchObject({research_team:true});
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="another-board" flush={async()=>true} busy={false}/>));
  expect(host.querySelectorAll<HTMLButtonElement>('.research-mode button')[1].getAttribute('aria-pressed')).toBe('false');
});

it('makes saved public references and specialist reviews accessible in recent conversation',async()=>{
  vi.mocked(api.jarvisConversation).mockResolvedValue({turns:[{question:'Which sources?',title:'Research',summary:'The references are ready.',
    web_sources:[{title:'Actual retrieved paper',url:'https://doi.org/10.1234/fire',snippet:'Metadata',provider:'Crossref'}],
    research_team:{status:'partial',specialists:[{role:'skeptic',label:'Scientific skeptic',status:'completed',insight:'Check acquisition opportunities.',next_test:'Match satellite overpasses.'}]}}]});
  act(()=>root.render(<WhiteboardAssistant editor={{} as any} documentId="board" flush={async()=>true} busy={false}/>));
  await act(async()=>{click('Ask AI');await Promise.resolve();});
  expect(host.querySelector<HTMLAnchorElement>('.whiteboard-conversation a')?.href).toBe('https://doi.org/10.1234/fire');
  expect(host.querySelector('.whiteboard-conversation [aria-label="Research team review"]')?.textContent).toContain('Match satellite overpasses.');
});

it('shows a source-linked research proposal distinctly from measured findings and retains it in history',async()=>{
  const source={id:'R1',title:'Original fuel methods',url:'https://doi.org/10.1234/fuel',snippet:'Metadata only',provider:'Crossref'};
  const brief={synthesis:'The metadata points to fuel and detection methods.',hypothesis:'Dryness may affect thermal detectability.',proposed_test:'Match fuel measurements with overpass conditions.',source_ids:['R1']};
  vi.mocked(api.jarvisConversation).mockResolvedValue({turns:[{question:'Which test?',title:'Research',summary:'A proposed comparison.',web_sources:[source],research_answer:brief}]});
  vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
  vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
  vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Fuel study',summary:'A proposed comparison.',web_sources:[source],research_answer:brief}});
  const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[]};
  act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
  click('Ask AI');type('Investigate fuel-moisture references and propose a test.');
  await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
  const reports=host.querySelectorAll<HTMLElement>('[aria-label="Public research brief"]');
  expect(reports).toHaveLength(2);
  for(const report of reports){expect(report.textContent).toContain('Working hypothesis');expect(report.textContent).toContain(brief.proposed_test);expect(report.textContent).toContain('search metadata');expect(report.querySelector('a')?.href).toBe(source.url);}
  expect(host.querySelector('.research-reference-id')?.textContent).toBe('R1');
  expect(host.querySelector('.whiteboard-conversation')?.textContent).not.toContain('A proposed comparison.');
});

it('shows original passages and abstract scope in current and saved answers and binds reading actions to the exact DOI',async()=>{
 const source={id:'R1',title:'Original fuel methods',url:'https://doi.org/10.1234/fuel',snippet:'Metadata only',provider:'Crossref'};
 const reading={source_id:'R1',title:source.title,url:source.url,status:'abstract' as const,reason:'Only the abstract is available.',license:null,scope:'Only displayed passages were read.',passages:[{id:'P1',section:'Abstract',location:'metadata/abstractText',text:'Original abstract passage.',truncated:false,paragraph_sha256:'a'.repeat(64)}]};
 vi.mocked(api.jarvisConversation).mockResolvedValue({turns:[{question:'Read methods',title:'Original source',summary:'Selected passages.',web_sources:[source],public_readings:[reading]}]});
 vi.mocked(api.getDocument).mockResolvedValue({revision:1,state:{cards:{}},snapshots:{}} as any);
 vi.mocked(api.jarvisStart).mockResolvedValue({id:'run',status:'queued'});
 vi.mocked(api.jarvisRun).mockResolvedValue({status:'completed',body:{title:'Original source',summary:'Selected passages.',web_sources:[source],public_readings:[reading]}});
 const editor:any={getAppState:()=>({selectedElementIds:{}}),getSceneElements:()=>[]};
 act(()=>root.render(<WhiteboardAssistant editor={editor} documentId="board" flush={async()=>true} busy={false}/>));
 click('Ask AI');type('Read original methods.');
 await act(async()=>{click('Ask');await new Promise(resolve=>setTimeout(resolve,0));});
 const panels=host.querySelectorAll('[aria-label="Original source reading"]');expect(panels).toHaveLength(2);
 for(const panel of panels){expect(panel.textContent).toContain('Abstract only');expect(panel.textContent).toContain('Original abstract passage.');expect(panel.textContent).not.toContain('Article passages');expect(panel.querySelector('a')?.href).toBe(source.url);}
 await act(async()=>{click('Read original methods');await new Promise(resolve=>setTimeout(resolve,0));});
 expect(api.jarvisStart).toHaveBeenLastCalledWith('board',expect.objectContaining({message:expect.stringContaining('Source URL: '+source.url)}));
});
