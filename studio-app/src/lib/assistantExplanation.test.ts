import {expect,it} from 'vitest';
import {explanationElements} from './assistantExplanation';

it('keeps each checked claim separately linked to its own source',()=>{
  const result=explanationElements({title:'Summary',summary:'Compare the sources.',claims:[
    {label:'Observed',value:12,unit:'cells',result_id:'receipt',path:'/count',binding:{documentId:'board',cardId:'card',snapshotId:'snapshot',snapshotHash:'hash'}},
    {label:'Mean',value:4,result_id:'table-receipt',path:'/columns/0/mean',source_binding:{documentId:'board',datasetId:'table',datasetHash:'table-hash',summaryColumn:'value',summaryMetric:'mean'}}
  ]},'board',['card'],{datasetId:'unrelated',datasetHash:'other'},100,100,'./studio.html');
  expect(result).toHaveLength(6);
  expect(result[0]).toMatchObject({type:'rectangle',locked:true});
  expect(result[1]).toMatchObject({text:'Summary',fontSize:24});
  const claims=result.filter(item=>item.customData.fireatlas.kind==='assistant-explanation-claim');
  expect(claims[0].customData.fireatlas).toMatchObject({cardId:'card',snapshotId:'snapshot',claims:[{value:12,path:'/count'}]});
  expect(claims[0].customData.fireatlas.datasetId).toBeUndefined();
  expect(claims[1].customData.fireatlas).toMatchObject({datasetId:'table',datasetHash:'table-hash',summaryColumn:'value',claims:[{value:4}]});
  expect(claims[1].y).toBeGreaterThan(claims[0].y);
});

it('keeps real units while omitting the generic table-value placeholder',()=>{
  const result=explanationElements({claims:[{label:'MODIS',value:'348',unit:'reported value'},{label:'Area',value:12,unit:'cells'}]},'board',[],{},0,0,'');
  const claims=result.filter(item=>item.customData.fireatlas.kind==='assistant-explanation-claim');
  expect(claims[0].text).toBe('MODIS: 348');
  expect(claims[1].text).toBe('Area: 12 cells');
  expect(claims[0].customData.fireatlas.claims[0].unit).toBe('reported value');
});
