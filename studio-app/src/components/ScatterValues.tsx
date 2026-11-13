import { useEffect, useState } from 'react';
import { api } from '../api';

type ScatterResult = Awaited<ReturnType<typeof api.datasetScatter>>;

/** Display the exact numeric pairs used by the saved plot, ten at a time. */
export function ScatterValues({documentId,datasetId,hash,x,y,onShowRecord,onAddPage}: {documentId:string;datasetId:string;hash:string;x:string;y:string;onShowRecord:(offset:number)=>void;onAddPage:(data:ScatterResult,page:number)=>void}) {
  const [data,setData]=useState<ScatterResult|null>(null);
  const [error,setError]=useState('');
  const [page,setPage]=useState(0);
  useEffect(()=>{
    let active=true;setData(null);setError('');setPage(0);
    void api.datasetScatter(documentId,datasetId,x,y).then(result=>{
      if(!active)return;
      if(result.dataset_id!==datasetId || result.sha256!==hash || result.x_column!==x || result.y_column!==y)throw Error('The plotted data no longer matches this chart.');
      setData(result);
    }).catch(err=>{if(active)setError((err as Error).message);});
    return ()=>{active=false;};
  },[documentId,datasetId,hash,x,y]);
  if(error)return <p role="alert">{error}</p>;
  if(!data)return <p role="status">Loading plotted values…</p>;
  const start=page*10;
  return <section aria-label="Plotted values"><strong>Plotted values</strong>
    <p>{data.points.length} pairs · {data.skipped_rows} rows skipped</p>
    <div className="whiteboard-dataset-scroll"><table><thead><tr><th>CSV record</th><th>{data.x_column}</th><th>{data.y_column}</th><th>Source</th></tr></thead>
      <tbody>{data.points.slice(start,start+10).map(point=><tr key={point.row}><td>{point.row}</td><td>{point.x}</td><td>{point.y}</td><td><button type="button" aria-label={`Show CSV record ${point.row}`} onClick={()=>onShowRecord(point.row-2)}>Show record</button></td></tr>)}</tbody></table></div>
    <div><button type="button" disabled={!page} onClick={()=>setPage(p=>p-1)}>Previous plotted values</button>
      <span> {start+1}–{Math.min(start+10,data.points.length)} of {data.points.length} </span>
      <button type="button" disabled={start+10>=data.points.length} onClick={()=>setPage(p=>p+1)}>Next plotted values</button></div>
    <button type="button" onClick={()=>onAddPage(data,page)}>Add these values to board</button>
  </section>;
}
