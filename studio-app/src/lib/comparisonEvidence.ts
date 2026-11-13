/** Resolve display scope only from the owned frozen receipt, never canvas labels. */
export function comparisonEvidence(receipt:any,index:unknown){
  if(receipt.operation!=='regional_comparison')return undefined;
  const panels=receipt.payload?.panels;
  if(!Array.isArray(panels) || !panels.length)throw Error('The saved comparison has no panels.');
  if(index!==undefined && (!Number.isInteger(index) || (index as number)<0 || (index as number)>=panels.length))throw Error('The selected comparison panel changed. Select it again.');
  const selected=index===undefined?panels:[panels[index as number]];
  const weatherUrl=(value:unknown)=>{try{const url=new URL(String(value));return url.protocol==='https:' && url.hostname==='archive-api.open-meteo.com' && !url.username && !url.password && !url.port && url.pathname==='/v1/archive'?url.href:undefined;}catch{return undefined;}};
  return selected.map((panel:any)=>({
    title:panel.label, start:panel.start,end:panel.end,searchStart:panel.search_start,searchEnd:panel.search_end,
    product:panel.product, rank:panel.rank, rankMetric:receipt.payload?.mode==='annual_peaks'?(receipt.payload.rank_by==='detections'?'returned detection records':'occupied 1 km cells'):undefined, tiedDates:panel.tied_dates || [],
    cells:panel.occupied_cells, records:panel.detections, delta:panel.cell_delta,
    weather:panel.weather?.status==='available'?{source:panel.weather.source,url:weatherUrl(panel.weather.url),
      start:panel.weather.start,end:panel.weather.end,sha256:panel.weather.sha256,
      latitude:panel.weather.original_response?.latitude ?? panel.weather.latitude,
      longitude:panel.weather.original_response?.longitude ?? panel.weather.longitude,note:panel.weather.note}:undefined
  }));
}
