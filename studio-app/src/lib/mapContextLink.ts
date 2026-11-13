type MapScope={bbox:number[];start:string;end:string};

/** Construct a current map view only for a date and sensor present in the saved replay. */
export function mapContextLink(scope:MapScope,day:unknown,source:unknown,receipt:any):string|null {
  if(!Array.isArray(scope.bbox) || scope.bbox.length!==4 || !scope.bbox.every(Number.isFinite))return null;
  if(typeof day!=='string' || !/^\d{4}-\d{2}-\d{2}$/.test(day) || day<scope.start || day>scope.end)return null;
  if(source!=='joint' && source!=='MODIS_SP' && source!=='VIIRS_SNPP_SP')return null;
  if(receipt?.operation!=='replay' || !Array.isArray(receipt.payload?.frames) || !receipt.payload.frames.some((frame:any)=>frame.date_utc===day))return null;
  const series=source==='MODIS_SP'?'modis':source==='VIIRS_SNPP_SP'?'viirs-snpp':'joint';
  const query=new URLSearchParams({year:scope.start.slice(0,4),month:String(Number(scope.start.slice(5,7))),bbox:scope.bbox.join(','),start:scope.start,end:scope.end,as_of:scope.end,day,source,series,region:'',scope:'daily',metric:'density',split:'true',context_version:'2'});
  return './investigate.html?'+query.toString();
}
