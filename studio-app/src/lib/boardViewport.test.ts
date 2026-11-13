import {beforeEach,expect,it} from 'vitest';
import {readBoardViewport,saveBoardViewport} from './boardViewport';

beforeEach(()=>localStorage.clear());
it('remembers independent views per board and rejects malformed data',()=>{
  saveBoardViewport('a',{scrollX:12,scrollY:-40,zoom:{value:.8}});
  saveBoardViewport('b',{scrollX:5,scrollY:6,zoom:{value:1.2}});
  expect(readBoardViewport('a')).toEqual({scrollX:12,scrollY:-40,zoom:{value:.8}});
  expect(readBoardViewport('b')?.zoom.value).toBe(1.2);
  localStorage.setItem('fireatlas-board-viewport:a','{"scrollX":0,"scrollY":0,"zoom":999}');
  expect(readBoardViewport('a')).toBeNull();
  saveBoardViewport('b',{scrollX:NaN,scrollY:0,zoom:{value:1}});
  expect(readBoardViewport('b')?.scrollX).toBe(5);
});
