import { expect, it } from 'vitest';
import { boardNoteIds } from './boardNoteIds';

it('uses the same bounded priority as the server, including bound labels', () => {
  const ai = Array.from({length:20},(_,index)=>({id:`ai-${index}`,type:'text',text:`AI ${index}`,
    customData:{fireatlas:{documentId:'board',kind:'assistant-explanation'}}}));
  const items = [
    {id:'box',type:'rectangle',customData:{fireatlas:{documentId:'board',kind:'assistant-diagram'}}},
    {id:'label',type:'text',text:'Generated label',containerId:'box'},
    ...ai,
    {id:'new-note',type:'text',text:'Research note'},
    {id:'deleted',type:'text',text:'Deleted',isDeleted:true},
  ];
  expect(boardNoteIds(items,'board')).toEqual(['new-note','label',...ai.slice(0,18).map(item=>item.id)]);
  expect(boardNoteIds(items,'another-board')[0]).toBe('label');
});

it('keeps authored notes ahead of earlier generated chart labels',()=>{
  const chart=Array.from({length:25},(_,index)=>({id:`chart-${index}`,type:'text',text:`Value ${index}`,
    customData:{fireatlas:{documentId:'board',kind:'park-platform-chart'}}}));
  const notes=[...chart,{id:'question',type:'text',text:'Why did the readings differ?'},
    {id:'ai',type:'text',text:'Earlier output',customData:{fireatlas:{documentId:'board',kind:'assistant-explanation'}}}];
  const chosen=boardNoteIds(notes,'board');
  expect(chosen[0]).toBe('question');
  expect(chosen).toHaveLength(20);
  expect(chosen).not.toContain('ai');
});
