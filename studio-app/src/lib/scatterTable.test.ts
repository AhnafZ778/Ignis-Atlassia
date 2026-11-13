import {expect,it} from 'vitest';
import {scatterTable} from './scatterTable';

it('places the selected page with exact values and individual source record links',()=>{
  const points=Array.from({length:11},(_,i)=>({row:i+3,x:i+0.25,y:i*2}));
  const rows=scatterTable({name:'data.csv',x_column:'x',y_column:'y',points,skipped_rows:1,total_rows:12},
    {documentId:'board',datasetId:'data',datasetHash:'hash'},1,20,30);
  expect(rows).toHaveLength(2);expect(rows[0].text).toContain('Pairs 11–11 of 11');
  expect(rows[1].text).toContain('Record 13   |   10.25   |   20');
  expect(rows[1].customData.fireatlas).toMatchObject({datasetId:'data',datasetHash:'hash',rowOffset:11});
});
