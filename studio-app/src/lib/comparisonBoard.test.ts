import {describe,it,expect} from 'vitest';
import {comparisonBoard,type ComparisonVisual} from './comparisonBoard';

const visual:ComparisonVisual={kind:'regional-comparison',title:'Peak days across years',mode:'annual_peaks',rank_by:'occupied_cells',domain:[0,2],note:'Synthetic test',panels:[2023,2024,2025].map((year,i)=>({
  label:'Synthetic area',year,day:`${year}-05-01`,start:`${year}-05-01`,end:`${year}-05-01`,search_start:`${year}-01-01`,search_end:`${year}-12-31`,
  product:'VIIRS_NOAA20_SP',sensor:'NOAA-20 VIIRS',occupied_cells:i+1,detections:i+2,cell_delta:i,record_delta:i,state:'queried',tied_dates:[],
  hotspots:[{longitude:88.6,latitude:24.4,detections:2}],weather:{status:'available',air_temperature_max_c:31,rainfall_7d_mm:null,wind_max_kmh:12},
  heat:{scope:{bbox:[88,24,89,25]},domain:[0,2]},
}))};
describe('comparison board',()=>{
  it('keeps all native marks and measurements inside one frame with exact source pointers',()=>{
    let n=0;const binding={documentId:'board',snapshotId:'snapshot',snapshotHash:'hash'};
    const {shapes,imageIds,frameId}=comparisonBoard(visual,binding,['a','b','c'],100,100,()=>`item-${++n}`);
    expect(imageIds).toHaveLength(3);
    expect(shapes.filter(item=>item.type==='ellipse')).toHaveLength(3);
    for(const shape of shapes){expect(shape.customData.fireatlas.snapshotHash).toBe('hash');if(shape.id!==frameId)expect(shape.frameId).toBe(frameId);}
    const claims=shapes.flatMap(item=>item.customData.fireatlas.claims || []);
    expect(claims).toContainEqual(expect.objectContaining({path:'/panels/2/cell_delta',value:2,unit:'cells'}));
    expect(claims).toContainEqual(expect.objectContaining({path:'/panels/0/hotspots/0/detections',value:2}));
    expect(shapes.some(item=>item.text==='Unavailable')).toBe(true);
    expect(claims.some(item=>item.path.endsWith('rainfall_7d_mm'))).toBe(false);
  });
  it('refuses independently normalized heat panels',()=>{
    const changed=structuredClone(visual);changed.panels[1].heat.domain=[0,99];
    expect(()=>comparisonBoard(changed,{documentId:'b',snapshotId:'s',snapshotHash:'h'},['a','b','c'],0,0,()=>'' )).toThrow('one scale');
  });
  it('identifies detection-ranked peak days while retaining occupied-cell measurement units',()=>{
    const changed=structuredClone(visual);changed.rank_by='detections';let n=0;
    const {shapes}=comparisonBoard(changed,{documentId:'b',snapshotId:'s',snapshotHash:'h'},['a','b','c'],0,0,()=>`i-${++n}`);
    expect(shapes.some(item=>item.text?.includes('ranked by returned detection records'))).toBe(true);
    expect(shapes.some(item=>item.customData.fireatlas.claims?.some((c:any)=>c.path==='/panels/2/cell_delta' && c.unit==='cells'))).toBe(true);
  });
  it('never annotates an out-of-bounds location as if it were on the map',()=>{
    const changed=structuredClone(visual);changed.panels.forEach(panel=>panel.hotspots[0].longitude=90);
    let n=0;const {shapes}=comparisonBoard(changed,{documentId:'b',snapshotId:'s',snapshotHash:'h'},['a','b','c'],0,0,()=>`i-${++n}`);
    expect(shapes.some(item=>item.type==='ellipse')).toBe(false);
  });
});
