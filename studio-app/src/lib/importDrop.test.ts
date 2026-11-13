import {expect,it} from 'vitest';
import {sourceFileKind,mightContainSources} from './importDrop';

it('recognizes CSV and PDF names without intercepting images or scenes',()=>{
  expect(sourceFileKind({name:'Data.CSV',type:''})).toBe('csv');
  expect(sourceFileKind({name:'paper.pdf',type:'application/octet-stream'})).toBe('pdf');
  expect(sourceFileKind({name:'image.png',type:'image/png'})).toBeNull();
  expect(sourceFileKind({name:'board.excalidraw',type:'application/json'})).toBeNull();
});
it('accepts source drag types while leaving known image drags alone',()=>{
  expect(mightContainSources([{kind:'file',type:'application/pdf'}] as any)).toBe(true);
  expect(mightContainSources([{kind:'file',type:''}] as any)).toBe(true);
  expect(mightContainSources([{kind:'file',type:'image/png'}] as any)).toBe(false);
  expect(mightContainSources([{kind:'string',type:'text/csv'}] as any)).toBe(false);
});
