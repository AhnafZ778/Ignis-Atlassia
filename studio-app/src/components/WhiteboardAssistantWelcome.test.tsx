import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { WhiteboardAssistantWelcome } from './WhiteboardAssistantWelcome';

let host:HTMLDivElement,root:ReturnType<typeof createRoot>;
beforeEach(()=>{(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;host=document.createElement('div');document.body.append(host);root=createRoot(host);});
afterEach(()=>{act(()=>root.unmount());host.remove();});
const props=()=>({ready:true,boards:[],status:'',onStart:vi.fn(),onOpen:vi.fn()});

it('shows Ask AI and practical instructions without an existing board',()=>{
  const p=props();act(()=>root.render(<WhiteboardAssistantWelcome {...p}/>));
  expect(host.querySelector('.assistant-launcher')?.textContent).toBe('Ask AI');
  expect(host.textContent).toContain('Explain and diagram this');
  expect(host.textContent).toContain('Park Fire');
  expect(p.onStart).not.toHaveBeenCalled();
  const start=[...host.querySelectorAll('button')].find(b=>b.textContent==='Start an investigation')!;
  act(()=>start.click());
  expect(p.onStart).toHaveBeenCalledOnce();
  expect(host.querySelector('section')).toBeNull();
  expect(host.querySelector('.assistant-launcher')).not.toBeNull();
});
it('keeps the launcher usable while the workspace is unavailable',()=>{
  const p={...props(),ready:false,status:'Studio is unavailable'};
  act(()=>root.render(<WhiteboardAssistantWelcome {...p}/>));
  const start=[...host.querySelectorAll('button')].find(b=>b.textContent==='Start an investigation')!;
  expect(start.disabled).toBe(true);
  expect(host.querySelector('[role="status"]')?.textContent).toBe('Studio is unavailable');
  expect(host.querySelector<HTMLButtonElement>('.assistant-launcher')?.disabled).toBe(false);
});
it('opens the chosen saved board and dismisses the welcome',()=>{
  const p={...props(),boards:[{id:'saved-board',title:'Park Fire'}]};
  act(()=>root.render(<WhiteboardAssistantWelcome {...p}/>));
  const select=host.querySelector('select')!;
  act(()=>{select.value='saved-board';select.dispatchEvent(new Event('change',{bubbles:true}));});
  expect(p.onOpen).toHaveBeenCalledWith('saved-board');
  expect(host.querySelector('section')).toBeNull();
});
it('closes with Escape and returns focus to the visible island',()=>{
  act(()=>root.render(<WhiteboardAssistantWelcome {...props()}/>));
  const panel=host.querySelector('section')!;
  act(()=>panel.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true})));
  expect(host.querySelector('section')).toBeNull();
  expect(document.activeElement).toBe(host.querySelector('.assistant-launcher'));
});
