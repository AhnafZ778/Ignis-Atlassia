import { expect, it } from 'vitest';
import { diagramShapes } from './whiteboardDiagram';

it('creates editable nodes and bound, labeled arrows with source context', () => {
  let count = 0;
  const shapes = diagramShapes({ nodes: [{ id: 'e', label: 'Observations', kind: 'evidence', evidence_id: 'receipt' }, { id: 'q', label: 'Compare sensors', kind: 'question' }], edges: [{ source: 'e', target: 'q', relation: 'question' }] }, 'board', ['card'], 10, 20, () => `element${++count}`);
  expect(shapes[0].customData.fireatlas).toMatchObject({ documentId: 'board', sourceCardIds: ['card'], evidenceId: 'receipt' });
  expect(shapes[2]).toMatchObject({ type: 'arrow', start: { id: 'element1' }, end: { id: 'element2' }, label: { text: 'question' } });
  expect(shapes[2].points).toEqual([[0,0],[95,0]]);
});
it('rejects references to missing nodes', () => {
  expect(() => diagramShapes({ nodes: [{ id: 'a', label: 'Source', kind: 'evidence' }], edges: [{ source: 'a', target: 'missing', relation: 'context' }] }, 'board', [], 0, 0, () => 'new')).toThrow();
});

it('routes a connection around an intervening card',()=>{
  let count=0;
  const shapes=diagramShapes({nodes:[
    {id:'a',kind:'evidence',label:'Source'},
    {id:'wide',kind:'interpretation',label:'A longer interpretation. '.repeat(8)},
    {id:'q',kind:'question',label:'What is missing?'},
  ],edges:[{source:'a',target:'q',relation:'question'}]},'board',[],0,0,()=>`node${++count}`);
  const arrow=shapes.find(shape=>shape.type==='arrow');
  expect(arrow.points).toHaveLength(4);
  expect(arrow.x+arrow.points[1][0]).toBeGreaterThan(shapes[1].x+shapes[1].width);
});

it('visibly labels an AI context card and keeps it editable',()=>{
  const [shape]=diagramShapes({nodes:[{id:'context',kind:'context',label:'Cloud cover'}],edges:[]},'board',[],0,0,()=> 'context-node');
  expect(shape.type).toBe('rectangle');
  expect(shape.label.text).toBe('AI context\nCloud cover');
  expect(shape.customData.fireatlas.evidenceId).toBeNull();
});

it('wraps a long label and reserves room before the next row',()=>{
  let count=0;const label='W'.repeat(70);
  const shapes=diagramShapes({nodes:[{id:'a',label,kind:'evidence'},{id:'b',label:'Second',kind:'question'},{id:'c',label:'Third',kind:'question'}],edges:[]},'board',[],0,0,()=>`node${++count}`);
  expect(shapes[0].label.text.replaceAll('\n','')).toBe(label);
  expect(shapes[0].label.text.split('\n').every((line:string)=>line.length<=18)).toBe(true);
  expect(shapes[1].height).toBeLessThan(shapes[0].height);
  expect(shapes[2].y).toBeGreaterThan(shapes[0].y+shapes[0].height);
});

it('gives a long interpretation its own wide row without losing its full text',()=>{
  let count=0;
  const interpretation='Cloud cover and differing acquisition times may affect what the sensors observe. '.repeat(4).trim();
  const shapes=diagramShapes({nodes:[
    {id:'a',kind:'context',label:'Cloud cover'},
    {id:'i',kind:'interpretation',label:interpretation},
    {id:'q',kind:'question',label:'When were the observations made?'},
  ],edges:[{source:'a',target:'i',relation:'context'},{source:'i',target:'q',relation:'question'}]},'board',[],0,0,()=>`node${++count}`);
  expect(shapes[1].width).toBe(775);
  expect(shapes[1].label.text.replaceAll('\n',' ').replace(/\s+/g,' ')).toBe(`AI interpretation ${interpretation}`);
  expect(shapes[1].label.text.split('\n').every((line:string)=>line.length<=40)).toBe(true);
  expect(shapes[1].y).toBeGreaterThan(shapes[0].y+shapes[0].height);
  expect(shapes[2].y).toBeGreaterThan(shapes[1].y+shapes[1].height);
  expect(shapes[3].points[1][1]).toBeGreaterThan(0);
  expect(shapes[4].points[1][1]).toBeGreaterThan(0);
});
