import {expect,it} from 'vitest';
import {mergeDrawing} from './mergeDrawing';

it('remaps objects, connectors, groups and images without modifying the source',()=>{
  let n=0;const source=[
    {id:'a',type:'rectangle',x:0,y:0,width:100,height:100,groupIds:['g'],boundElements:[{id:'arrow',type:'arrow'}],customData:{fireatlas:{documentId:'old',snapshotId:'old'},other:'kept'},link:'https://example.org'},
    {id:'b',type:'image',x:300,y:0,width:100,height:100,groupIds:['g'],fileId:'file'},
    {id:'arrow',type:'arrow',x:100,y:50,width:200,height:0,groupIds:[],startBinding:{elementId:'a'},endBinding:{elementId:'b'}},
  ];
  const result=mergeDrawing(source,[{id:'file',dataURL:'data:image/png;base64,AA=='}],[{x:500,width:100}],()=>`new-${++n}`);
  expect(result.elements[0].x).toBe(760);
  expect(result.elements[0].boundElements[0].id).toBe(result.elements[2].id);
  expect(result.elements[2].startBinding.elementId).toBe(result.elements[0].id);
  expect(result.elements[2].endBinding.elementId).toBe(result.elements[1].id);
  expect(result.elements[0].groupIds).toEqual(result.elements[1].groupIds);
  expect(result.elements[1].fileId).toBe(result.files[0].id);
  expect(result.elements[0].customData).toEqual({other:'kept'});
  expect(result.elements[0].link).toBeNull();
  expect(source[0].id).toBe('a');
});

it('rejects incomplete connections and missing embedded images',()=>{
  const base={id:'a',type:'arrow',x:0,y:0,width:10,height:10,groupIds:[]};
  expect(()=>mergeDrawing([{...base,startBinding:{elementId:'missing'}}],[],[],()=>crypto.randomUUID())).toThrow('missing object');
  expect(()=>mergeDrawing([{...base,type:'image',fileId:'missing'}],[],[],()=>crypto.randomUUID())).toThrow('missing an embedded image');
});

it('retains imported frame and text bindings with new identifiers',()=>{
  let n=0;
  const items=[{id:'frame',type:'frame',x:0,y:0,width:300,height:200},
    {id:'box',type:'rectangle',x:20,y:20,width:100,height:80,frameId:'frame',boundElements:[{id:'label',type:'text'}]},
    {id:'label',type:'text',x:30,y:30,width:80,height:20,frameId:'frame',containerId:'box'}];
  const result=mergeDrawing(items,[],[],()=>`new-${++n}`).elements;
  expect(result[1].frameId).toBe(result[0].id);
  expect(result[2].frameId).toBe(result[0].id);
  expect(result[2].containerId).toBe(result[1].id);
  expect(result[1].boundElements[0].id).toBe(result[2].id);
});
