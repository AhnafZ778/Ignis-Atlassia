import { expect,it } from 'vitest';
import { selectedSource, sameSelectedSource } from './selectedSource';

it('identifies only an unambiguous source from the active board',()=>{
  const items=[{id:'table',customData:{fireatlas:{documentId:'one',datasetId:'d',datasetHash:'h'}}},
    {id:'pdf',customData:{fireatlas:{documentId:'one',sourceDocumentId:'p',sourceDocumentHash:'h'}}},
    {id:'evidence',customData:{fireatlas:{documentId:'one',snapshotId:'s',snapshotHash:'h'}}},
    {id:'note',customData:{}}];
  expect(selectedSource(items,{table:true},'one')).toBe('table');
  expect(selectedSource(items,{pdf:true},'one')).toBe('document');
  expect(selectedSource(items,{evidence:true},'one')).toBe('evidence');
  expect(selectedSource(items,{table:true,pdf:true},'one')).toBeNull();
  expect(selectedSource(items,{table:true,note:true},'one')).toBeNull();
  expect(selectedSource(items,{table:true},'other')).toBeNull();
});

it('rejects a source changed, deleted or deselected during a pending inspection',()=>{
  const ref={documentId:'board',datasetId:'d',datasetHash:'h',groupName:'A'};
  const item={id:'bar',customData:{fireatlas:ref}};
  const original=JSON.stringify(ref);
  expect(sameSelectedSource([item],{bar:true},'bar',original)).toBe(true);
  expect(sameSelectedSource([item],{},'bar',original)).toBe(false);
  expect(sameSelectedSource([{...item,isDeleted:true}],{bar:true},'bar',original)).toBe(false);
  expect(sameSelectedSource([{...item,customData:{fireatlas:{...ref,groupName:'B'}}}],{bar:true},'bar',original)).toBe(false);
  expect(sameSelectedSource([item,{id:'other'}],{bar:true,other:true},'bar',original)).toBe(false);
});
