import { expect,it } from 'vitest';
import { groupChart } from './groupChart';
it('plots positive, negative, zero and unknown means with a shared baseline',()=>{
 let n=0;const data={group_column:'region',value_column:'reading',groups:[{group:'A',rows:2,numeric_count:2,mean:-4},{group:'B',rows:2,numeric_count:2,mean:8},{group:'C',rows:1,numeric_count:1,mean:0},{group:null,rows:1,numeric_count:0,mean:null}]};
 const items=groupChart(data,{datasetId:'data'},0,0,()=>`id${++n}`);
 const bars=items.filter(item=>item.type==='rectangle' && item.height===17);
 expect(bars).toHaveLength(2);expect(bars[0].x).toBeLessThan(500);expect(bars[1].x).toBe(500);
 expect(bars.map(bar=>bar.customData.fireatlas.groupName)).toEqual(['A','B']);
 expect(bars.every(bar=>bar.customData.fireatlas.groupMetric==='mean')).toBe(true);
 const blank=items.find(item=>item.text==='(blank group)');expect(blank.customData.fireatlas.groupName).toBeNull();
 expect(items.some(item=>item.text?.includes('unavailable'))).toBe(true);expect(items.at(-1).children.length).toBe(items.length-1);
});

it('keeps long category names distinct and reserves space for each label',()=>{
 let n=0;const names=['Northern California observation category alpha','Northern California observation category beta'];
 const items=groupChart({group_column:'region',value_column:'count',groups:names.map(group=>({group,rows:1,numeric_count:1,mean:2}))},{datasetId:'data'},0,0,()=>`id${++n}`);
 const labels=items.filter(item=>item.type==='text' && names.some(name=>item.text?.replaceAll('\n',' ')===name));
 expect(labels).toHaveLength(2);
 expect(labels[0].text).not.toBe(labels[1].text);
 expect(labels[1].y).toBeGreaterThanOrEqual(labels[0].y+labels[0].text.split('\n').length*19);
});
