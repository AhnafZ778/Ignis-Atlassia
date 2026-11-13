import { expect, it } from 'vitest';
import { challengeComparison } from './challengeComparison';
const pair={dates:['2024-05','2025-05'],series:{modis:{first:0,second:2,difference:2,percent:null,direction:'increase'},viirs:{first:10,second:5,difference:-5,percent:-50,direction:'decrease'},adjusted:{first:null,second:null,difference:null,percent:null,direction:'unavailable'}}};
const ref={documentId:'board',cardId:'card',snapshotId:'snap',snapshotHash:'hash'};
it('makes two independently editable source-linked frames and preserves zero baseline',()=>{
 let n=0;const result=challengeComparison(pair,'modis','viirs','cell-days',ref,100,100,()=>`id-${++n}`);
 expect(result.filter(item=>item.type==='frame')).toHaveLength(2);
 expect(result.some(item=>item.text==='Direction: increase')).toBe(true);
 expect(result.some(item=>item.text==='Direction: decrease')).toBe(true);
 expect(result.some(item=>item.text?.includes('Starting value is zero'))).toBe(true);
 expect(result.every(item=>item.customData.fireatlas.snapshotHash==='hash')).toBe(true);
 expect(result.filter(item=>item.type==='frame').map(item=>item.customData.fireatlas.comparisonSeries)).toEqual(['modis','viirs']);
});
it('leaves unavailable values unavailable and refuses duplicate series',()=>{
 let n=0;const result=challengeComparison(pair,'modis','adjusted','cell-days',ref,0,0,()=>`id-${++n}`);
 expect(result.some(item=>item.text==='Change unavailable')).toBe(true);
 expect(()=>challengeComparison(pair,'modis','modis','cell-days',ref,0,0,()=>`id-${++n}`)).toThrow();
});
