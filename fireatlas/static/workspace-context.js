/* Analytical superset of FireAtlasContext. The landing retains its original lab.js. */
(() => {
  'use strict';
  const DEFAULTS=Object.freeze({year:2026,month:6,bbox:'-122.2,38.8,-120,41',as_of:'2026-06-30',series:'joint',day:'',distance_km:2,gap_days:1,region:'norcal',layer:'none',calendar_metric:'harmonized',metric:'density',scope:'daily',view:'2d',scale:'study'});
  const KEYS=['year','month','bbox','start','end','as_of','day','case','region','series','source','distance_km','gap_days','layer','calendar_metric','metric','scope','view','split','scale','tab','section','analysis_month','guide','guide_step','method_id','unit','release_id','result_sha256','origin_region','origin_year','origin_month','origin_start','origin_end','origin_metric','origin_method_id','origin_unit','origin_result_sha256','origin_route','geometry'];
  const validDate=s=>/^\d{4}-\d{2}-\d{2}$/.test(s||'')&&Number.isFinite(Date.parse(s+'T00:00:00Z'))&&new Date(s+'T00:00:00Z').toISOString().slice(0,10)===s;
  const monthEnd=(year,month)=>new Date(Date.UTC(year,month,0)).toISOString().slice(0,10);
  function validBBox(value,strict=false){const a=String(value??'').split(',').map(x=>x.trim()?Number(x):NaN),valid=a.length===4&&a.every(Number.isFinite)&&a[0]>=-180&&a[2]<=180&&a[1]>=-90&&a[3]<=90&&a[0]<a[2]&&a[1]<a[3];if(!valid&&strict)throw Error('Enter west, south, east, north within longitude ±180 and latitude ±90, in increasing order.');return valid?a.join(','):DEFAULTS.bbox;}
  function normalize(value){
    const c={...DEFAULTS,...value},errors=[];
    for(const k of ['year','month','distance_km','gap_days'])c[k]=Number(c[k]);
    if(!Number.isInteger(c.year)||c.year<2000||c.year>2100)errors.push('Invalid year');
    if(!Number.isInteger(c.month)||c.month<1||c.month>12)errors.push('Invalid month');
    try{c.bbox=validBBox(c.bbox,true);}catch(e){errors.push(e.message);}
    if(!(c.distance_km>=.5&&c.distance_km<=10)||!Number.isInteger(c.gap_days)||c.gap_days<0||c.gap_days>7)errors.push('Grouping requires 0.5–10 km and a 0–7 integer day gap');
    const ym=`${c.year}-${String(c.month).padStart(2,'0')}`;
    c.start=c.start||ym+'-01';c.end=c.end||c.as_of||(errors.length?'':monthEnd(c.year,c.month));
    if(!validDate(c.start)||!validDate(c.end)||c.start>c.end)errors.push('Invalid ordered UTC interval');
    c.as_of=c.as_of||c.end;
    if(c.day&&(!validDate(c.day)||c.day<c.start||c.day>c.end))errors.push('Selected day is outside the study interval');
    if(c.region&&!['norcal','punjab-haryana'].includes(c.region))errors.push('Unknown regional study');
    if(c.case&&!['park-2024','camp-2018','grove-2025','custom'].includes(c.case))errors.push('Unknown named study');
    if(!['harmonized','combined'].includes(c.calendar_metric))errors.push('Unknown calendar metric');
    if(!['joint','modis','viirs-snpp','hms-viirs','viirs-noaa20','viirs-noaa20-nrt','viirs-noaa21-nrt','viirs-snpp-nrt','modis-nrt'].includes(c.series))errors.push('Unknown processing cohort');
    if(!['study','relative'].includes(c.scale))errors.push('Unknown comparison scale');
    if(c.geometry){try{const g=typeof c.geometry==='string'?JSON.parse(c.geometry):c.geometry;const ring=g.coordinates?.[0],box=c.bbox.split(',').map(Number);if(g.type!=='Polygon'||g.coordinates?.length!==1||!Array.isArray(ring)||ring.length<4||ring.length>100||JSON.stringify(ring[0])!==JSON.stringify(ring.at(-1))||ring.some(p=>!Array.isArray(p)||p.length!==2||!p.every(Number.isFinite)||p[0]<box[0]||p[0]>box[2]||p[1]<box[1]||p[1]>box[3]))throw Error();c.geometry=JSON.stringify(g);}catch{errors.push('Invalid polygon selection');}}
    c.errors=errors;return c;
  }
  function read(search=location.search){const p=new URLSearchParams(search),v={};for(const k of KEYS)if(p.has(k))v[k]=p.get(k);if(v.start&&!v.year)v.year=v.start.slice(0,4);if(v.start&&!v.month)v.month=v.start.slice(5,7);if(!v.bbox&&v.region==='punjab-haryana')v.bbox='73.8,29.5,77.6,32.6';if(!v.as_of&&v.year&&v.month&&Number(v.month)>=1&&Number(v.month)<=12)v.as_of=monthEnd(Number(v.year),Number(v.month));return normalize(v);}
  function write(context,options={}){const merged={...read(),...context};const p=new URLSearchParams();for(const k of KEYS)if(merged[k]!=null&&merged[k]!=='')p.set(k,k==='geometry'&&typeof merged[k]!=='string'?JSON.stringify(merged[k]):String(merged[k]));p.set('context_version','2');return options.path?`${options.path}?${p}${options.hash||''}`:'?'+p;}
  function api(context,keys=['year','month','bbox','as_of','series','day','distance_km','gap_days']){const p=new URLSearchParams();for(const k of keys)if(context[k]!=null&&context[k]!=='')p.set(k,Array.isArray(context[k])?context[k].join(','):context[k]);return p;}
  const base=()=>new URL('./',document.baseURI);
  const url=path=>new URL(path.replace(/^\//,''),base()).href;
  function link(path,overrides={}){const target=new URL(path.replace(/^\//,''),base()),p=new URLSearchParams(write({...read(),...overrides}));if(target.pathname!==location.pathname&&!target.searchParams.has('tab'))p.delete('tab');for(const [k,v]of target.searchParams)p.set(k,v);target.search=p.toString();return target.pathname+target.search+target.hash;}
  function nav(){const current=document.body.dataset.workspace||document.body.dataset.page,aliases={atlas:'explore',assistant:'investigate',research:'research',data:'evidence',method:'evidence',review:'evidence'};document.querySelectorAll('#site-navigation [data-destination]').forEach(a=>{const active=a.dataset.destination===(aliases[current]||current);a.classList.toggle('active',active);if(active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});}
  function apply(root=document,context=read()){root.querySelectorAll('[data-context-field]').forEach(n=>{if(context[n.dataset.contextField]!=null)n.value=context[n.dataset.contextField];});root.querySelectorAll('[data-context-link]').forEach(n=>n.href=link(n.dataset.contextLink||n.getAttribute('href')||'./',context));nav();return context;}
  function status(node,message,kind='unknown'){if(!node)return;node.textContent=message;node.classList.remove('available','partial','unavailable','unknown');node.classList.add(kind);}
  let revision=0;
  function update(value,{history:mode='replace',reason='selection'}={}){const c=normalize({...read(),...value});if(c.errors.length)throw Error(c.errors.join('. '));const target=new URL(location.href);target.search=write(c);if(target.href!==location.href)window.history[mode==='push'?'pushState':'replaceState'](null,'',target);revision++;apply(document,c);window.dispatchEvent(new CustomEvent('fireatlas:context-changed',{detail:{context:c,revision,reason}}));return c;}
  function toReplayRequest(value=read()){const c=normalize(value);if(c.errors.length)throw Error(c.errors.join('. '));return {bbox:c.bbox.split(',').map(Number),start:c.start,end:c.end,day:c.day||c.start,source:c.source||(c.series==='modis'?'MODIS_SP':c.series==='viirs-snpp'?'VIIRS_SNPP_SP':'joint'),...(c.case?{case:c.case}:{})};}
  function toAssistantContext(value=read()){const c=toReplayRequest(value),v=normalize(value);return {...c,year:v.year,month:v.month,as_of:c.end,series:v.series,metric:v.metric,distance_km:v.distance_km,gap_days:v.gap_days};}
  function toResearchRequest(value=read(),explicitMonth){const c=normalize(value),ym=explicitMonth||c.analysis_month;if(!ym||!/^\d{4}-\d{2}$/.test(ym))throw Error('Choose a UTC month intersection explicitly.');const [year,month]=ym.split('-').map(Number),start=[c.start,ym+'-01'].sort().at(-1),end=[c.end,monthEnd(year,month)].sort()[0];if(start>end)throw Error('This month does not intersect the originating study.');return {year,month,start_date:start,as_of:end,bbox:validBBox(c.bbox,true).split(',').map(Number),distance_km:c.distance_km,gap_days:c.gap_days};}
  function researchSelection(){const c=read();const ym=c.analysis_month||c.start.slice(0,7),r=toResearchRequest(c,ym);return {...c,...r,bbox:r.bbox.join(','),as_of:r.as_of,year:r.year,month:r.month};}
  window.FireAtlasContext={DEFAULTS,read,write,api,link,apply,nav,status,validBBox,validDate,normalize,update,url,monthEnd,toReplayRequest,toAssistantContext,toResearchRequest,researchSelection,toCalendarRequest:c=>({region:c.region,year:c.year,month:c.month}),toShareURL:(path,c)=>link(path,c),get revision(){return revision;}};
  document.addEventListener('DOMContentLoaded',()=>{apply();const c=read();if(c.errors.length){const notice=document.createElement('p');notice.className='notice-panel';notice.setAttribute('role','alert');notice.textContent='Selection unavailable: '+c.errors.join('. ')+'. Edit the selection; it has not been replaced.';document.querySelector('main')?.prepend(notice);}document.dispatchEvent(new CustomEvent('fireatlas:context-ready',{detail:c}));});
  addEventListener('popstate',()=>{apply();window.dispatchEvent(new CustomEvent('fireatlas:context-restore',{detail:read()}));});
})();
