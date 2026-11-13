import { expect, it, vi } from 'vitest';
vi.mock('@excalidraw/excalidraw',()=>({
  newElementWith:(item:any,updates:any)=>({...item,...updates}),
  convertToExcalidrawElements:(items:any[])=>{
    if(items.some(item=>item.type==='arrow') && items.some(item=>item.type==='image'))throw Error('Converter cannot bind images');
    return items.map(item=>item.type==='arrow'
      ? {...item,startBinding:{elementId:item.start.id},endBinding:{elementId:item.end.id}} : item);
  },
}));
import { convertToExcalidrawElements } from '@excalidraw/excalidraw';
import { connectSelection } from './connectSelection';

it('connects two existing objects with reciprocal native bindings',()=>{
  const source=convertToExcalidrawElements([{id:'a',type:'rectangle',x:0,y:0,width:100,height:60,angle:0},{id:'b',type:'rectangle',x:300,y:0,width:100,height:60,angle:0}],{regenerateIds:false});
  const result=connectSelection(source,{a:true,b:true},'board','edge');
  const arrow:any=result.find(item=>item.id==='edge');
  expect(arrow.startBinding.elementId).toBe('a');
  expect(arrow.endBinding.elementId).toBe('b');
  for(const id of ['a','b'])expect(result.find(item=>item.id===id)?.boundElements).toContainEqual({id:'edge',type:'arrow'});
  expect(arrow.customData.fireatlas).toMatchObject({documentId:'board',relation:'related',originalElementIds:['a','b']});
});

it('rejects incomplete or overlapping selections',()=>{
  const source=convertToExcalidrawElements([{id:'a',type:'rectangle',x:0,y:0,width:100,height:60,angle:0},{id:'b',type:'rectangle',x:10,y:0,width:100,height:60,angle:0}],{regenerateIds:false});
  expect(()=>connectSelection(source,{a:true},'board','edge')).toThrow('two objects');
  expect(()=>connectSelection(source,{a:true,b:true},'board','edge')).toThrow('apart');
});

it('preserves existing bindings and refuses locked objects',()=>{
  const source:any=convertToExcalidrawElements([{id:'a',type:'rectangle',x:0,y:0,width:100,height:60,angle:0,boundElements:[{id:'old',type:'arrow'}]},{id:'b',type:'rectangle',x:300,y:0,width:100,height:60,angle:0}],{regenerateIds:false});
  const result=connectSelection(source,{a:true,b:true},'board','edge');
  expect(result.find(item=>item.id==='a')?.boundElements).toEqual([{id:'old',type:'arrow'},{id:'edge',type:'arrow'}]);
  expect(()=>connectSelection([source[0],{...source[1],locked:true}],{a:true,b:true},'board','edge')).toThrow('unlocked');
});

it('treats a selected bound label as part of its selected source card',()=>{
  const source:any=[
    {id:'card',type:'rectangle',x:0,y:0,width:100,height:60,angle:0,boundElements:[{id:'label',type:'text'}]},
    {id:'label',type:'text',text:'Source',containerId:'card',x:10,y:10,width:50,height:20,angle:0},
    {id:'chart',type:'image',x:300,y:0,width:100,height:60,angle:0,fileId:'file'},
  ];
  const result=connectSelection(source,{card:true,label:true,chart:true},'board','edge');
  const arrow:any=result.find(item=>item.id==='edge');
  expect(arrow.startBinding.elementId).toBe('card');
  expect(arrow.endBinding.elementId).toBe('chart');
  expect(result.find(item=>item.id==='card')?.boundElements).toEqual([{id:'label',type:'text'},{id:'edge',type:'arrow'}]);
});

it('treats an existing dataset card and its unbound caption as one endpoint',()=>{
  const ref={documentId:'board',kind:'csv-dataset',datasetId:'data',datasetHash:'hash'};
  const source:any=[
    {id:'card',type:'rectangle',x:0,y:0,width:380,height:150,angle:0,customData:{fireatlas:ref}},
    {id:'caption',type:'text',text:'Source',x:18,y:18,width:200,height:60,angle:0,customData:{fireatlas:ref}},
    {id:'chart',type:'image',x:480,y:0,width:300,height:200,angle:0,fileId:'file'},
  ];
  const result=connectSelection(source,{card:true,caption:true,chart:true},'board','edge');
  const arrow:any=result.find(item=>item.id==='edge');
  expect(arrow.startBinding.elementId).toBe('card');
  expect(arrow.endBinding.elementId).toBe('chart');
  expect(result.find(item=>item.id==='caption')).toBe(source[1]);
});
