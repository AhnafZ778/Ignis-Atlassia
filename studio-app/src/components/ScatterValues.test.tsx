import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach,expect,it,vi} from 'vitest';
vi.mock('../api',()=>({api:{datasetScatter:vi.fn()}}));
import {api} from '../api';
import {ScatterValues} from './ScatterValues';

afterEach(()=>vi.resetAllMocks());
it('shows plotted rows, excludes skipped rows and pages through numeric pairs',async()=>{
  const host=document.createElement('div');document.body.append(host);const root=createRoot(host);
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
  vi.mocked(api.datasetScatter).mockResolvedValue({dataset_id:'data',sha256:'hash',name:'test',x_column:'x',y_column:'y',points:Array.from({length:11},(_,i)=>({row:i+2,x:i,y:i*2})),skipped_rows:2,total_rows:13});
  const showRecord=vi.fn();
  await act(async()=>{root.render(<ScatterValues documentId="board" datasetId="data" hash="hash" x="x" y="y" onShowRecord={showRecord} onAddPage={()=>{}}/>);await Promise.resolve();});
  expect(host.textContent).toContain('11 pairs · 2 rows skipped');
  expect(host.querySelectorAll('tbody tr')).toHaveLength(10);
  act(()=>[...host.querySelectorAll('button')].find(b=>b.textContent==='Next plotted values')!.click());
  expect(host.querySelectorAll('tbody tr')).toHaveLength(1);expect(host.textContent).toContain('11–11 of 11');
  act(()=>host.querySelector<HTMLButtonElement>('[aria-label="Show CSV record 12"]')!.click());expect(showRecord).toHaveBeenCalledWith(10);
  act(()=>root.unmount());host.remove();
});
it('refuses to display values when the source hash differs',async()=>{
  const host=document.createElement('div');document.body.append(host);const root=createRoot(host);
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
  vi.mocked(api.datasetScatter).mockResolvedValue({dataset_id:'data',sha256:'changed',name:'test',x_column:'x',y_column:'y',points:[],skipped_rows:0,total_rows:0});
  await act(async()=>{root.render(<ScatterValues documentId="board" datasetId="data" hash="hash" x="x" y="y" onShowRecord={()=>{}} onAddPage={()=>{}}/>);await Promise.resolve();await Promise.resolve();});
  expect(host.getAttribute('role')).not.toBe('table');expect(host.textContent).toContain('no longer matches');
  act(()=>root.unmount());host.remove();
});
