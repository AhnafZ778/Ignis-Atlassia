import { heatMapProjection } from './heatMapGeometry';
import { wrapCardText } from './wrapCardText';

type Binding = {documentId:string;snapshotId:string;snapshotHash:string};
export type ComparisonPanel = {label:string;year:number;day:string|null;start:string;end:string;search_start:string;search_end:string;
  product:string;sensor:string;occupied_cells:number;detections:number;cell_delta:number|null;record_delta:number|null;state:string;
  tied_dates:string[];hotspots:{longitude:number;latitude:number;detections:number}[];
  weather:{status:string;air_temperature_max_c?:number|null;rainfall_7d_mm?:number|null;wind_max_kmh?:number|null;note?:string};
  heat:{scope:{bbox:number[]};domain:number[];[key:string]:any}};
export type ComparisonVisual = {kind:'regional-comparison';title:string;mode:string;rank_by:string;domain:number[];panels:ComparisonPanel[];note:string};

/** Editable, source-bound comparison instruments around frozen map pixels. */
export function comparisonBoard(visual:ComparisonVisual,binding:Binding,fileIds:string[],x:number,y:number,unique:()=>string,interpretation?:string) {
  if(visual.kind!=='regional-comparison' || visual.panels.length<1 || visual.panels.length>6 || fileIds.length!==visual.panels.length)throw Error('The comparison panels are unavailable.');
  if(!visual.panels.every(panel=>panel.heat.domain[0]===visual.domain[0] && panel.heat.domain[1]===visual.domain[1]))throw Error('The comparison heatmaps do not share one scale.');
  const shapes:any[]=[],imageIds:string[]=[],frameId=unique();
  const columns=Math.min(3,visual.panels.length),width=columns*1040-80;
  const base={...binding,kind:'assistant-comparison',viewKind:'regional-comparison'};
  let currentPanel:number|undefined;
  const meta=(extra:Record<string,unknown>={})=>({fireatlas:{...base,...(currentPanel===undefined?{}:{comparisonPanel:currentPanel}),...extra}});
  const text=(value:string,tx:number,ty:number,size=20,color='#193e35',extra:Record<string,unknown>={})=>{
    const id=unique();shapes.push({id,type:'text',x:tx,y:ty,text:value,fontSize:size,fontFamily:2,strokeColor:color,frameId,customData:meta(extra)});return id;
  };
  const claim=(i:number,key:string,value:number,label:string,tx:number,ty:number,unit:string,size=22)=>text(label,tx,ty,size,'#193e35',{
    kind:'assistant-explanation-claim',comparisonPanel:i,claims:[{label,value,unit,path:`/panels/${i}/${key}`}],
  });
  text('FIELDNOTES  /  THERMAL COMPARISON',x,y,16,'#687b6b');
  text(visual.title,x,y+36,42);
  const ranking=visual.rank_by==='detections'?'returned detection records':'occupied 1 km cells';
  text(wrapCardText(`${visual.panels[0].sensor} · shared heat scale · ${visual.mode==='annual_peaks'?`peak UTC days ranked by ${ranking}; complete years`:'exact frozen source windows'}`,columns===1?90:180),x,y+99,18,'#687b6b');
  visual.panels.forEach((panel,i)=>{
    currentPanel=i;
    const left=x+(i%columns)*1040,top=y+160+Math.floor(i/columns)*1060;
    const imageId=unique();imageIds.push(imageId);
    text(visual.mode==='annual_peaks'?String(panel.year):String(i+1).padStart(2,'0')+' / '+panel.label,left,top,30);
    text(panel.day || `${panel.start} – ${panel.end}`,left,top+45,18,'#687b6b');
    shapes.push({id:imageId,type:'image',x:left,y:top+84,width:960,height:540,fileId:fileIds[i],status:'saved',scale:[1,1],frameId,
      customData:meta({kind:'assistant-data-view',comparisonPanel:i,title:panel.label,viewStart:panel.start,viewEnd:panel.end,day:panel.day,source:panel.product})});
    const delta=panel.cell_delta;
    const deltaText=panel.state!=='queried'?'No positive peak day':i===0?'Reference panel':delta===null?'Comparison unavailable':`${delta>0?'+':''}${delta} occupied cells vs reference`;
    if(delta!==null)claim(i,'cell_delta',delta,deltaText,left,top+646,'cells');
    else text(deltaText,left,top+646,22,'#687b6b');
    const hot=panel.hotspots[0];
    if(hot && panel.state==='queried'){
      const [west,south,east,north]=panel.heat.scope.bbox;
      if(hot.longitude>=west && hot.longitude<=east && hot.latitude>=south && hot.latitude<=north){
        const [px,py]=heatMapProjection(panel.heat.scope.bbox).project(hot.longitude,hot.latitude);
        const ring=unique();
        shapes.push({id:ring,type:'ellipse',x:left+px-14,y:top+84+py-14,width:28,height:28,strokeColor:'#e5a338',strokeWidth:3,backgroundColor:'transparent',frameId,
          customData:meta({comparisonPanel:i,kind:'assistant-explanation-claim',claims:[{label:'Most repeated occupied cell',value:hot.detections,unit:'records',path:`/panels/${i}/hotspots/0/detections`}]})});
        claim(i,'hotspots/0/detections',hot.detections,`${hot.detections} detections in this 1 km cell · check repeated passes`,left+32,top+700,'records',18);
        shapes.push({id:unique(),type:'arrow',x:left+px,y:top+84+py+14,points:[[0,0],[0,540-py+50],[32-px,540-py+48]],
          start:{id:ring},strokeColor:'#c18c31',strokeWidth:2,frameId,customData:meta({comparisonPanel:i})});
      }
    }
    const w=panel.weather;
    shapes.push({id:unique(),type:'rectangle',x:left,y:top+770,width:960,height:190,backgroundColor:'#eaf0e7',fillStyle:'solid',strokeColor:'#d0dbca',roundness:{type:3},frameId,customData:meta({comparisonPanel:i})});
    text('WEATHER CONTEXT  /  7 UTC DAYS THROUGH END DATE',left+24,top+790,15,'#64765b');
    if(w.status==='available'){
      const metrics:[string,string,string,number|null|undefined][]=[['air_temperature_max_c','Maximum air temperature','°C',w.air_temperature_max_c],['rainfall_7d_mm','Total precipitation','mm',w.rainfall_7d_mm],['wind_max_kmh','Maximum wind speed','km/h',w.wind_max_kmh]];
      metrics.forEach(([key,label,unit,value],j)=>{
        const mx=left+24+j*308;
        if(value===null || value===undefined)text('Unavailable',mx,top+829,27,'#687b6b');
        else claim(i,`weather/${key}`,value,`${value.toLocaleString('en-US',{maximumFractionDigits:2})} ${unit}`,mx,top+829,unit,30);
        text(label,mx,top+875,15,'#64765b');
      });
      text('ERA5 point reanalysis at area center · context, not a demonstrated cause',left+24,top+920,14,'#64765b');
    }else text(w.status==='not_requested'?'Weather not requested. Ask to add environmental context.':'Weather unavailable. The thermal evidence remains inspectable.',left+24,top+841,20,'#64765b');
    if(panel.tied_dates.length>1)text(`${panel.tied_dates.length} tied dates · inspect source for all ties`,left,top+981,16,'#687b6b');
  });
  currentPanel=undefined;
  const bottom=y+160+Math.ceil(visual.panels.length/columns)*1060;
  text('WHAT COULD EXPLAIN THE DIFFERENCE?',x,bottom,25);
  text(wrapCardText('Compare sampling and acquisition times first. Discuss rainfall, wind, temperature, vegetation or land use as hypotheses; use additional evidence to test them.',105),x,bottom+48,20,'#687b6b');
  const explanation=interpretation?.trim() ? wrapCardText(interpretation.trim(),105) : '';
  if(explanation){
    text('AI INTERPRETATION',x,bottom+146,16,'#687b6b');
    text(explanation,x,bottom+181,22,'#193e35',{kind:'assistant-explanation'});
  }
  const children=shapes.map(item=>item.id);
  shapes.push({id:frameId,type:'frame',name:visual.title,children,customData:meta(),x:x-32,y:y-32,width:width+64,height:bottom-y+(explanation?240+explanation.split('\n').length*30:180)});
  return {shapes,imageIds,frameId};
}
