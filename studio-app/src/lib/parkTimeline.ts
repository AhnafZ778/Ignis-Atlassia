type Row = { date:string; values:Record<string,number|null>; states:Record<string,string> };
const series=[
  {key:'MODIS_SP',label:'MODIS',color:'#b2680a'},
  {key:'VIIRS_SNPP_SP',label:'S-NPP',color:'#087b99'},
  {key:'VIIRS_NOAA20_SP',label:'NOAA-20',color:'#7452b8'},
  {key:'VIIRS_NOAA21_SP',label:'NOAA-21',color:'#318157'},
];

/** Points and a readable exact table use only the Python-produced case rows. */
export function parkTimeline(rows:Row[],ref:{documentId:string;datasetId:string;datasetHash:string},x:number,y:number,unique:()=>string):any[] {
  if(rows.length!==4 || rows.some((row,i)=>row.date!==`2024-07-${25+i}`))throw Error('The Park case dates are unavailable.');
  for(const row of rows)for(const item of series){const n=row.values[item.key];if(n!==null && (!Number.isSafeInteger(n) || n<0))throw Error('The Park case has an invalid count.');if(typeof row.states[item.key]!=='string')throw Error('The Park case has an invalid source state.');}
  const meta={fireatlas:{...ref,kind:'park-platform-chart'}};
  const result:any[]=[];
  const text=(dx:number,dy:number,value:string,size=16,color='#183149',rowOffset?:number)=>result.push({type:'text',x:x+dx,y:y+dy,text:value,fontSize:size,fontFamily:2,strokeColor:color,customData:rowOffset===undefined?meta:{fireatlas:{...meta.fireatlas,rowOffset}}});
  const line=(dx:number,dy:number,width:number,height:number,color='#d7e1e9')=>result.push({type:'rectangle',x:x+dx,y:y+dy,width,height,strokeColor:color,backgroundColor:color,fillStyle:'solid',customData:meta});
  text(0,0,'Park Fire · daily satellite detections',24);text(0,35,'July 25–28, 2024 UTC · Park study boundary · recorded detections',14);
  series.forEach((s,i)=>{line(i*170,70,12,12,s.color);text(i*170+18,67,s.label,14);});
  const max=Math.max(1,...rows.flatMap(row=>series.map(s=>row.values[s.key] ?? 0)));
  const left=85,top=115,width=600,height=240;
  for(let i=0;i<=4;i++){const py=top+height*i/4;line(left,py,width,1);text(0,py-8,String(Math.round(max*(1-i/4))),12);}
  // Draw only between consecutive available days. A missing observation is a
  // break in the series, not a zero or an invitation to interpolate over it.
  series.forEach(s=>{
    for(let i=1;i<rows.length;i++){
      const previous=rows[i-1].values[s.key],current=rows[i].values[s.key];
      if(previous===null || current===null)continue;
      const px=left+50+(i-1)*(width-100)/3,py=top+height-(previous/max)*height;
      const dx=(width-100)/3,dy=(previous-current)/max*height;
      // Excalidraw's line converter does not calculate its own bounds from
      // points. Accurate dimensions are needed for selection and fit-to-view.
      result.push({type:'line',x:x+px,y:y+py,width:dx,height:Math.abs(dy),points:[[0,0],[dx,dy]],strokeColor:s.color,strokeWidth:2,roughness:0,customData:meta});
    }
  });
  rows.forEach((row,i)=>{
    const px=left+50+i*(width-100)/3;
    text(px-30,top+height+12,row.date.slice(5),13,'#183149',i);
    series.forEach(s=>{const n=row.values[s.key];if(n===null)return;result.push({type:'ellipse',x:x+px-5,y:y+top+height-(n/max)*height-5,width:10,height:10,strokeColor:s.color,backgroundColor:s.color,fillStyle:'solid',customData:{fireatlas:{...meta.fireatlas,rowOffset:i}}});});
  });
  const fmt=(n:number|null)=>n===null?'unavailable':String(n);
  const columns=[0,150,265,390,515];
  ['UTC date',...series.map(s=>s.label)].forEach((label,i)=>text(columns[i],top+height+55,label,15));
  rows.forEach((row,i)=>[row.date,...series.map(s=>fmt(row.values[s.key]))].forEach((value,j)=>text(columns[j],top+height+85+i*25,value,14,'#183149',i)));
  text(0,top+height+205,rows.some(row=>row.states.VIIRS_SNPP_SP==='documented_product_gap')?'S-NPP processing gap · select a point or date to inspect the source record':'Select a point or date to inspect the source record',13);
  // A native frame keeps the complete figure together when it is moved or
  // organized, while its points and values remain individually selectable.
  const children=result.map(item=>{item.id=unique();return item.id;});
  result.push({id:unique(),type:'frame',name:'Park Fire satellite comparison',children,customData:meta});
  return result;
}
