import { describe, expect, it, vi } from 'vitest';
vi.mock('@excalidraw/excalidraw', () => ({newElementWith:(e:any, updates:any)=>({...e,...updates,version:e.version+1})}));
import { arrangeSelection } from './arrangeSelection';
import { parkTimeline } from './parkTimeline';

const item=(id:string,x:number,y:number,extra:any={})=>({id,type:'rectangle',x,y,width:100,height:50,angle:0,groupIds:[],frameId:null,locked:false,isDeleted:false,boundElements:null,version:1,...extra});

describe('organize selection',()=>{
  it('arranges items and moves attached labels together',()=>{
    const input:any=[item('a',0,0),item('label',10,10,{type:'text',containerId:'a',width:60,height:20}),item('b',300,100)];
    const output=arrangeSelection(input,{a:true,b:true}) as any[];
    expect(output.find(e=>e.id==='b')).toMatchObject({x:140,y:0,version:2});
    expect(output.find(e=>e.id==='label')).toMatchObject({x:10,y:10});
    expect(input[2].x).toBe(300);
  });
  it('refuses locked and connected items',()=>{
    for(const extra of [{locked:true},{boundElements:[{type:'arrow',id:'arrow'}]}]) {
      expect(()=>arrangeSelection([item('a',0,0,extra),item('b',300,100)] as any,{a:true,b:true})).toThrow();
    }
  });
  it('moves every member of a selected group as one unit',()=>{
    const input:any=[item('a',0,0),item('b',300,100,{groupIds:['g']}),item('c',420,100,{groupIds:['g']})];
    const out=arrangeSelection(input,{a:true,b:true}) as any[];
    expect(out.find(e=>e.id==='b')).toMatchObject({x:260,y:0});
    expect(out.find(e=>e.id==='c')).toMatchObject({x:380,y:0});
  });
  it('refuses a group containing a locked member',()=>{
    const input:any=[item('a',0,0),item('b',300,100,{groupIds:['g']}),item('c',420,100,{groupIds:['g'],locked:true})];
    expect(()=>arrangeSelection(input,{a:true,b:true})).toThrow('unlocked');
  });
  it('preserves nested groups and refuses an attached arrow',()=>{
    const input:any=[item('a',0,0),item('b',300,100,{groupIds:['outer']}),item('c',420,100,{groupIds:['inner','outer']}),item('d',540,100,{groupIds:['inner']})];
    const out=arrangeSelection(input,{a:true,b:true}) as any[];
    expect(out.find(e=>e.id==='d').x-out.find(e=>e.id==='b').x).toBe(240);
    input.push(item('link',0,0,{type:'arrow',startBinding:{elementId:'d'},endBinding:null}));
    expect(()=>arrangeSelection(input,{a:true,b:true})).toThrow('both ends');
  });
  it('moves a fully selected connected diagram as one unit',()=>{
    const input:any=[item('a',0,0),item('b',400,100,{boundElements:[{id:'edge',type:'arrow'}]}),item('c',600,100,{boundElements:[{id:'edge',type:'arrow'}]}),
      item('edge',500,120,{type:'arrow',width:100,height:0,startBinding:{elementId:'b'},endBinding:{elementId:'c'}}),
      item('caption',525,110,{type:'text',containerId:'edge',width:40,height:20})];
    const out=arrangeSelection(input,{a:true,b:true,c:true}) as any[];
    const before=input.find((e:any)=>e.id==='b'), after=out.find(e=>e.id==='b');
    for(const id of ['c','edge','caption']) {
      const original=input.find((e:any)=>e.id===id), moved=out.find(e=>e.id===id);
      expect([moved.x-original.x,moved.y-original.y]).toEqual([after.x-before.x,after.y-before.y]);
    }
    expect(out.find(e=>e.id==='edge').startBinding.elementId).toBe('b');
  });
  it('refuses to move a diagram with an unselected endpoint',()=>{
    const input:any=[item('a',0,0),item('b',300,100),item('c',500,100),item('edge',400,120,{type:'arrow',startBinding:{elementId:'b'},endBinding:{elementId:'c'}})];
    expect(()=>arrangeSelection(input,{a:true,b:true})).toThrow('both ends');
  });
  it('moves a frame and all its contents as one unit',()=>{
    const input:any=[item('note',0,0),item('frame',400,100,{type:'frame',width:250,height:180}),
      item('inside',420,120,{frameId:'frame'}),item('line',430,200,{type:'line',frameId:'frame',width:80,height:0}),
      item('label',430,130,{type:'text',frameId:'frame',containerId:'inside',width:60,height:20})];
    const out=arrangeSelection(input,{note:true,frame:true}) as any[];
    const frameBefore=input[1],frameAfter=out.find(e=>e.id==='frame');
    for(const id of ['inside','line','label']){
      const before=input.find((e:any)=>e.id===id),after=out.find(e=>e.id===id);
      expect([after.x-before.x,after.y-before.y]).toEqual([frameAfter.x-frameBefore.x,frameAfter.y-frameBefore.y]);
      expect(after.frameId).toBe('frame');
    }
    expect(frameAfter.x).not.toBe(frameBefore.x);
  });
  it('keeps an actual Park chart together while preserving its point record links',()=>{
    const rows=Array.from({length:4},(_,i)=>({date:`2024-07-${25+i}`,values:{MODIS_SP:i+1,VIIRS_SNPP_SP:null,VIIRS_NOAA20_SP:2,VIIRS_NOAA21_SP:3},states:{MODIS_SP:'complete_export',VIIRS_SNPP_SP:'unknown',VIIRS_NOAA20_SP:'complete_export',VIIRS_NOAA21_SP:'complete_export'}}));
    let n=0;
    const skeleton=parkTimeline(rows,{documentId:'board',datasetId:'data',datasetHash:'hash'},400,100,()=>`chart-${++n}`);
    const frame=skeleton.at(-1);
    // Model the frame and child bindings created by Excalidraw's converter.
    const chart=skeleton.map((shape:any)=>item(shape.id,shape.x ?? 390,shape.y ?? 90,{...shape,width:shape.width ?? 720,height:shape.height ?? 600,frameId:shape.type==='frame'?null:frame.id}));
    const before=[item('note',0,0),...chart];
    const after=arrangeSelection(before,{note:true,[frame.id]:true}) as any[];
    const movedFrame=after.find(e=>e.id===frame.id),originalFrame=before.find(e=>e.id===frame.id);
    const dx=movedFrame.x-originalFrame.x,dy=movedFrame.y-originalFrame.y;
    expect(dx!==0 || dy!==0).toBe(true);
    for(const point of before.filter(e=>e.type==='ellipse')){
      const moved=after.find(e=>e.id===point.id);
      expect(moved.x-point.x).toBeCloseTo(dx);
      expect(moved.y-point.y).toBeCloseTo(dy);
      expect(moved.customData.fireatlas.rowOffset).toBe(point.customData.fireatlas.rowOffset);
    }
  });
  it('refuses an isolated framed child and a frame with locked contents',()=>{
    const frame=item('frame',300,100,{type:'frame',width:250,height:180});
    const child=item('child',320,120,{frameId:'frame'});
    expect(()=>arrangeSelection([item('note',0,0),frame,child] as any,{note:true,child:true})).toThrow('whole frame');
    expect(()=>arrangeSelection([item('note',0,0),frame,{...child,locked:true}] as any,{note:true,frame:true})).toThrow('unlocked');
  });
  it('refuses a frame connected to an unselected external object',()=>{
    const input:any=[item('note',0,0),item('frame',300,100,{type:'frame',width:200,height:150}),
      item('inside',320,120,{frameId:'frame'}),item('outside',700,100),
      item('edge',420,140,{type:'arrow',startBinding:{elementId:'inside'},endBinding:{elementId:'outside'}})];
    expect(()=>arrangeSelection(input,{note:true,frame:true})).toThrow('both ends');
  });
  it('does not cover unrelated objects',()=>{
    expect(()=>arrangeSelection([item('a',0,0),item('b',300,100),item('other',140,0)] as any,{a:true,b:true})).toThrow('clear space');
  });
  it('arranges free lines and unbound arrows without changing their points',()=>{
    const input:any=[item('line',0,0,{type:'line',height:30,points:[[0,0],[100,30]],startBinding:null,endBinding:null}),
      item('arrow',300,100,{type:'arrow',height:50,points:[[0,0],[100,50]],startBinding:null,endBinding:null})];
    const out=arrangeSelection(input,{line:true,arrow:true}) as any[];
    expect(out.find(e=>e.id==='arrow')).toMatchObject({x:140,y:0,points:[[0,0],[100,50]]});
    expect(out.find(e=>e.id==='line').points).toEqual(input[0].points);
  });
  it('refuses a linear object with only one connected end',()=>{
    const input:any=[item('a',0,0),item('b',300,100),item('line',150,0,{type:'line',startBinding:{elementId:'a'},endBinding:null})];
    expect(()=>arrangeSelection(input,{a:true,b:true,line:true})).toThrow('both ends');
  });
  it('keeps both endpoints and a fully bound line together',()=>{
    const input:any=[item('other',0,0),item('a',400,100),item('b',600,100),
      item('line',500,120,{type:'line',width:100,height:0,points:[[0,0],[100,0]],startBinding:{elementId:'a'},endBinding:{elementId:'b'}})];
    const out=arrangeSelection(input,{other:true,a:true,b:true}) as any[];
    const delta=out.find(e=>e.id==='a').x-input[1].x;
    expect(out.find(e=>e.id==='b').x-input[2].x).toBe(delta);
    expect(out.find(e=>e.id==='line').x-input[3].x).toBe(delta);
  });
});
