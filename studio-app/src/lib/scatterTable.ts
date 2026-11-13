import type { Scatter } from './csvScatter';

/** A bounded, editable snapshot of one page of plotted values. */
export function scatterTable(data:Scatter, ref:{documentId:string;datasetId:string;datasetHash:string}, page:number, x:number, y:number):any[] {
  const start=page*10, points=data.points.slice(start,start+10);
  if(!points.length)throw Error('There are no plotted values on this page.');
  const meta={...ref,kind:'scatter-values-table',xColumn:data.x_column,yColumn:data.y_column};
  const make=(text:string,offset:number,extra:Record<string,unknown>={})=>({type:'text',x,y:y+offset,text,fontSize:16,fontFamily:2,strokeColor:'#183149',customData:{fireatlas:{...meta,...extra}}});
  return [make(`Plotted values · ${data.name}\n${data.x_column} × ${data.y_column}\nPairs ${start+1}–${start+points.length} of ${data.points.length} · ${data.skipped_rows} skipped`,0),
    ...points.map((point,index)=>make(`Record ${point.row}   |   ${point.x}   |   ${point.y}`,84+index*25,{rowOffset:point.row-2}))];
}
