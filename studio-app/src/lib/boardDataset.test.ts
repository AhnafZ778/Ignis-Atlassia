import { expect,it } from 'vitest';
import { boardDataset } from './boardDataset';

it('finds one linked table, preferring its frame over individual rows',()=>{
  const ref={documentId:'board',datasetId:'table',datasetHash:'hash'};
  const rows=[{id:'row',type:'text',customData:{fireatlas:{...ref,rowOffset:1}}},
    {id:'frame',type:'frame',customData:{fireatlas:ref}}];
  expect(boardDataset(rows,'board')?.id).toBe('frame');
  expect(boardDataset(rows,'other')).toBeNull();
  expect(boardDataset([...rows,{id:'other',customData:{fireatlas:{...ref,datasetId:'other'}}}],'board')).toBeNull();
  expect(boardDataset([...rows,{id:'bad-hash',customData:{fireatlas:{...ref,datasetHash:'different'}}}],'board')).toBeNull();
});
