import { expect, it } from 'vitest';
import { assistantChallenge } from './assistantChallenge';
it('preserves the full interpretation in the challenge frame',()=>{
  const summary=`${'Evidence suggests a difference. '.repeat(25)}A final source needs checking.`;
  let id=0;
  const elements=assistantChallenge({summary,claims:[{label:'Count',value:4}]},'board',['source'],{},[],0,0,()=>`id-${++id}`);
  const text=elements.find(item=>item.text?.startsWith('AI interpretation')).text.replace(/\n/g,' ');
  expect(text).toContain('A final source needs checking.');
});
it('retains source status alongside the first day of platform values',()=>{
  let id=0;const claims=['date','MODIS','NOAA-20','NOAA-21','MODIS status','S-NPP status'].map((label,i)=>({label,value:i===5?'gap':i}));
  const elements=assistantChallenge({summary:'What is missing?',claims},'board',['source'],{},[],0,0,()=>`id-${++id}`);
  expect(elements.some(item=>item.text?.includes('S-NPP status: gap'))).toBe(true);
});

it('creates an editable frame with checked claims and separately linked source excerpts',()=>{
  let id=0;
  const elements=assistantChallenge({summary:'The sensors can be compared.',claims:[{label:'Observed',value:7,unit:'cells',result_id:'result',path:'/count',binding:{documentId:'board',cardId:'other',snapshotId:'source-snap',snapshotHash:'source-hash'}}]},'board',['finding'],{cardId:'card',snapshotId:'snap',snapshotHash:'hash'},[{kind:'csv',name:'readings.csv',location:'Row 2',excerpt:'smoke',ref:{datasetId:'data',datasetHash:'hash2',rowOffset:1}}],100,100,()=>`id-${++id}`);
  expect(elements.filter(item=>item.type==='frame')).toHaveLength(1);
  expect(elements.some(item=>item.text?.includes('AI interpretation'))).toBe(true);
  expect(elements.find(item=>item.customData.fireatlas.kind==='assistant-challenge-claim').customData.fireatlas.claims[0].path).toBe('/count');
  expect(elements.find(item=>item.customData.fireatlas.kind==='assistant-challenge-claim').customData.fireatlas).toMatchObject({cardId:'other',snapshotId:'source-snap',snapshotHash:'source-hash'});
  expect(elements.find(item=>item.customData.fireatlas.kind==='assistant-challenge-source').customData.fireatlas).toMatchObject({datasetId:'data',rowOffset:1});
});
it('offers an open question rather than an unsupported interpretation',()=>{
  let id=0;const elements=assistantChallenge({summary:'This proves a cause.'},'board',['item'],{},[],0,0,()=>`id-${++id}`);
  expect(elements.some(item=>item.text?.includes('additional evidence'))).toBe(true);
  expect(elements.some(item=>item.text?.includes('proves a cause'))).toBe(false);
});
it('labels a question as a question when supporting sources are attached',()=>{
  let id=0;const elements=assistantChallenge({summary:'Which observations are unavailable?'},'board',['item'],{},[{kind:'csv',name:'table.csv',location:'Row 2',excerpt:'unavailable',ref:{datasetId:'data'}}],0,0,()=>`id-${++id}`);
  expect(elements.some(item=>item.text?.includes('Open question'))).toBe(true);
  expect(elements.some(item=>item.text?.includes('AI interpretation'))).toBe(false);
});
it('retains an imported table row on its individual claim',()=>{
  let id=0;const source={documentId:'board',datasetId:'data',datasetHash:'hash',rowOffset:3};
  const elements=assistantChallenge({claims:[{label:'Reading',value:'smoke',source_binding:source}]},'board',['item'],{},[],0,0,()=>`id-${++id}`);
  expect(elements.find(item=>item.customData.fireatlas.kind==='assistant-challenge-claim').customData.fireatlas).toMatchObject(source);
});
it('retains a blank group and its statistic on a grouped claim',()=>{
  let id=0;const source={documentId:'board',datasetId:'data',datasetHash:'hash',groupColumn:'region',valueColumn:'value',groupName:null,groupMetric:'mean'};
  const elements=assistantChallenge({claims:[{label:'Unknown · mean',value:3,source_binding:source}]},'board',['item'],{},[],0,0,()=>`id-${++id}`);
  expect(elements.find(item=>item.customData.fireatlas.kind==='assistant-challenge-claim').customData.fireatlas).toMatchObject(source);
});

it('retains a qualitative alternative grounded in the selected frozen source',()=>{
  let id=0;const summary='The pattern could reflect different overpass timing. Compare acquisition times before treating it as growth.';
  const elements=assistantChallenge({summary},'board',['map'],{snapshotId:'snap',snapshotHash:'hash'},[],0,0,()=> 'id-'+(++id));
  const interpretation=elements.find(item=>item.text?.startsWith('AI interpretation'));
  expect(interpretation.text.replace(/\n/g,' ')).toContain('Compare acquisition times');
  expect(interpretation.customData.fireatlas).toMatchObject({snapshotId:'snap',snapshotHash:'hash',originalElementIds:['map']});
});

it('retains both verified sources on a qualitative alternative from a connected pin',()=>{
  let id=0;const sourceBindings=[{documentId:'board',snapshotId:'one',snapshotHash:'hash-one'},{documentId:'board',snapshotId:'two',snapshotHash:'hash-two'}];
  const elements=assistantChallenge({summary:'Different sampling could explain the contrast. Compare acquisition times.'},'board',['pin'],{sourceBindings},[],0,0,()=> 'id-'+(++id));
  const interpretation=elements.find(item=>item.text?.startsWith('AI interpretation'));
  expect(interpretation.text.replace(/\n/g,' ')).toContain('Compare acquisition times');
  expect(interpretation.customData.fireatlas.sourceBindings).toEqual(sourceBindings);
});
