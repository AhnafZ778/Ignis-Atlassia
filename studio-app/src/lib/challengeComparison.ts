export type SeriesName='modis'|'viirs'|'adjusted';
type Measure={first:number|null;second:number|null;difference:number|null;percent:number|null;direction:string};
type Pair={dates:string[];series:Record<SeriesName,Measure>};
const seriesInfo:Record<SeriesName,{label:string;color:string}>={modis:{label:'MODIS observed',color:'#b2680a'},viirs:{label:'S-NPP observed',color:'#087b99'},adjusted:{label:'Adjusted MODIS estimate',color:'#7155c3'}};

/** Render two independent, editable source-linked frames on a shared scale. */
export function challengeComparison(pair:Pair,original:SeriesName,alternative:SeriesName,unit:string,ref:Record<string,string>,x:number,y:number,unique:()=>string):any[] {
  if(!pair || !Array.isArray(pair.dates) || pair.dates.length!==2 || pair.dates.some(d=>!/^\d{4}-\d{2}$/.test(d)) || !(original in seriesInfo) || !(alternative in seriesInfo) || original===alternative)throw Error('This comparison is unavailable.');
  const chosen=[original,alternative].map(key=>pair.series?.[key]);
  for(const row of chosen){
    if(!row || !['increase','decrease','unchanged','unavailable'].includes(row.direction))throw Error('The saved comparison is incomplete.');
    for(const value of [row.first,row.second])if(value!==null && (typeof value!=='number' || !Number.isFinite(value) || value<0))throw Error('The saved comparison contains invalid values.');
    for(const value of [row.difference,row.percent])if(value!==null && (typeof value!=='number' || !Number.isFinite(value)))throw Error('The saved comparison contains invalid changes.');
  }
  const max=Math.max(1,...chosen.flatMap(row=>[row.first ?? 0,row.second ?? 0]));
  const output:any[]=[];
  [original,alternative].forEach((key,index)=>{
    const info=seriesInfo[key],row=pair.series[key],left=x+index*510,ids:string[]=[];
    const metadata={fireatlas:{...ref,kind:'finding-alternative',comparisonSeries:key,comparisonRole:index?'alternative':'original'}};
    const text=(dx:number,dy:number,value:string,size=16)=>{const id=unique();ids.push(id);output.push({id,type:'text',x:left+dx,y:y+dy,text:value,fontSize:size,fontFamily:2,strokeColor:'#183149',customData:metadata});};
    const rect=(dx:number,dy:number,width:number,height:number,color:string)=>{const id=unique();ids.push(id);output.push({id,type:'rectangle',x:left+dx,y:y+dy,width,height,strokeColor:color,backgroundColor:color,fillStyle:'solid',customData:metadata});};
    text(18,20,index?'Alternative view':'Original view',14);text(18,45,info.label,20);
    unit.split(';').map(part=>part.trim()).filter(Boolean).slice(0,2).forEach((part,i)=>text(18,78+i*16,part,13));
    rect(20,330,400,1,'#aabac5');
    [row.first,row.second].forEach((value,i)=>{
      const px=90+i*190;
      if(value!==null && value>0){const height=Math.max(1,value/max*170);rect(px,330-height,54,height,info.color);}
      text(px-20,340,pair.dates[i],14);text(px-20,306-(value ?? 0)/max*170,value===null?'unavailable':String(value),14);
    });
    const direction=row.direction==='unavailable'?'Change unavailable':`Direction: ${row.direction}`;
    text(18,376,direction,16);
    text(18,403,row.difference===null?'Difference: unavailable':`Difference: ${row.difference}`,14);
    if(row.first===0 && row.second!==null)text(18,427,'Starting value is zero; use the absolute difference.',13);
    const frameId=unique();output.push({id:frameId,type:'frame',name:index?'Alternative interpretation':'Original interpretation',children:ids,customData:metadata});
  });
  return output;
}
