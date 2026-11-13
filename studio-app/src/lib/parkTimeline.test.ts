import { expect, it } from 'vitest';
import { parkTimeline } from './parkTimeline';
let next=0;
const unique=()=>`shape-${++next}`;
it('keeps outage values unavailable and retains the source table identity',()=>{
  const rows=Array.from({length:4},(_,i)=>({date:`2024-07-${25+i}`,values:{MODIS_SP:10,VIIRS_SNPP_SP:null,VIIRS_NOAA20_SP:20,VIIRS_NOAA21_SP:30},states:{MODIS_SP:'complete_export',VIIRS_SNPP_SP:'documented_product_gap',VIIRS_NOAA20_SP:'complete_export',VIIRS_NOAA21_SP:'complete_export'}}));
  const objects=parkTimeline(rows,{documentId:'board',datasetId:'data',datasetHash:'hash'},0,0,unique);
  expect(objects.filter(o=>o.type==='ellipse')).toHaveLength(12);
  expect(objects.some(o=>o.text?.includes('unavailable'))).toBe(true);
  expect(objects.every(o=>o.customData.fireatlas.datasetId==='data')).toBe(true);
  const frame=objects.at(-1);
  expect(frame.type).toBe('frame');
  expect(frame.children).toEqual(objects.slice(0,-1).map(o=>o.id));
  expect(new Set(objects.map(o=>o.id)).size).toBe(objects.length);
  const points=objects.filter(o=>o.type==='ellipse');
  expect(points.map(o=>o.customData.fireatlas.rowOffset)).toEqual([0,0,0,1,1,1,2,2,2,3,3,3]);
  expect(objects.filter(o=>o.type==='line')).toHaveLength(9);
  for(let i=0;i<4;i++){
    const day=objects.find(o=>o.text===`2024-07-${25+i}`);
    expect(day.customData.fireatlas.rowOffset).toBe(i);
  }
});

it('breaks a series at unavailable days without changing the point dates',()=>{
  const rows=Array.from({length:4},(_,i)=>({date:`2024-07-${25+i}`,values:{MODIS_SP:i===1?null:10+i,VIIRS_SNPP_SP:null,VIIRS_NOAA20_SP:null,VIIRS_NOAA21_SP:null},states:{MODIS_SP:'unknown',VIIRS_SNPP_SP:'unknown',VIIRS_NOAA20_SP:'unknown',VIIRS_NOAA21_SP:'unknown'}}));
  const objects=parkTimeline(rows,{documentId:'board',datasetId:'data',datasetHash:'hash'},100,100,unique);
  expect(objects.filter(o=>o.type==='line')).toHaveLength(1);
  const segment=objects.find(o=>o.type==='line');
  expect(segment.points[1][0]).toBeCloseTo(500/3);
  expect(segment.width).toBeCloseTo(segment.points[1][0]);
  expect(segment.height).toBeCloseTo(Math.abs(segment.points[1][1]));
  expect(segment.customData.fireatlas).toMatchObject({datasetId:'data',datasetHash:'hash'});
  expect(objects.filter(o=>o.type==='ellipse').map(o=>o.customData.fireatlas.rowOffset)).toEqual([0,2,3]);
  expect(objects.some(o=>o.text?.includes('processing gap'))).toBe(false);
});

it('provides correct bounds for both flat and falling lines',()=>{
  const values=[20,20,10,5];
  const rows=values.map((n,i)=>({date:`2024-07-${25+i}`,values:{MODIS_SP:n,VIIRS_SNPP_SP:null,VIIRS_NOAA20_SP:null,VIIRS_NOAA21_SP:null},states:{MODIS_SP:'complete_export',VIIRS_SNPP_SP:'unknown',VIIRS_NOAA20_SP:'unknown',VIIRS_NOAA21_SP:'unknown'}}));
  const segments=parkTimeline(rows,{documentId:'board',datasetId:'data',datasetHash:'hash'},0,0,unique).filter(o=>o.type==='line');
  expect(segments[0].height).toBe(0);
  expect(segments[1].height).toBeCloseTo(Math.abs(segments[1].points[1][1]));
  expect(segments[1].points[1][1]).toBeGreaterThan(0);
});
