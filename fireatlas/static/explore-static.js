/* Explore renders authoritative raw calendars and separately labelled point samples. */
(() => {
'use strict';
const C=FireAtlasContext,$=id=>document.getElementById(id),meta=document.querySelector('meta[name="fireatlas-static-data"]');
if(!meta||!$('static-atlas'))return;
document.body.classList.add('explore-static-mode');document.querySelector('.atlas-intro').hidden=true;document.querySelectorAll('[data-context-link=\"\"]').forEach(a=>{const u=new URL(a.href,document.baseURI);a.dataset.contextLink=u.pathname.split('/').pop()+u.hash;});$('study-workspace').hidden=true;$('static-atlas').hidden=false;
const dataRoot=new URL(meta.content,document.baseURI),countRoot=new URL('./data/explore/',document.baseURI),names=['January','February','March','April','May','June','July','August','September','October','November','December'];
const seriesNames={joint:'MODIS + S-NPP VIIRS',modis:'MODIS', 'viirs-snpp':'S-NPP VIIRS'},fmt=v=>v==null?'Unknown':Number(v).toLocaleString('en');
let regions,manifest,applied,result,retrySelection,rows=[],map,marks,outline,background,overlay,playback,serial=0,selectedDay='',draft=false;
const cache=new Map();
const node=(tag,text,cls)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;};
const analysis=node('section',undefined,'explore-analysis lab-shell');analysis.id='explore-analysis';analysis.setAttribute('aria-label','Observation calendar and activity charts');$('static-atlas').after(analysis);
analysis.innerHTML='<div class="explore-analysis-head"><div><p class="eyebrow">OBSERVATION ACTIVITY · UTC</p><h2>Read the pattern across time.</h2></div><a id="explore-download">Download exact calendar JSON ↓</a></div><p id="explore-status" role="status">Loading archive totals…</p><button id="explore-retry" hidden type="button">Retry archive</button><button id="explore-reset" hidden type="button">Use full regional archive</button><div id="explore-results" hidden><div class="explore-metrics" id="explore-metrics"></div><div class="explore-views"><section><h3>Months in this study year</h3><p class="explore-caption">Occupied 1 km cell-days · select a month</p><div id="explore-months" class="explore-months"></div></section><section><h3 id="explore-days-title">UTC calendar</h3><p class="explore-caption">Select a date to update the map</p><div class="explore-weekdays" aria-hidden="true"><span>M</span><span>T</span><span>W</span><span>T</span><span>F</span><span>S</span><span>S</span></div><div id="explore-days" class="explore-days"></div><div id="explore-colors" class="explore-colors" aria-label="Calendar color scale"></div><p class="explore-caption">Solid = complete export · striped / ≥ = partial · ? = unknown</p></section></div><p id="explore-day-detail" role="status"></p><details><summary>Exact daily counts and source states</summary><div class="explore-table" tabindex="0" aria-label="Exact daily observation totals"><table><thead><tr><th>UTC date</th><th>Occupied cell-days</th><th>Partial count</th><th>Export state</th></tr></thead><tbody id="explore-records"></tbody></table></div></details></div>';
const sourceLabel=node('label','Satellite source'),source=node('select');source.id='static-source';source.setAttribute('aria-label','Satellite source');Object.entries(seriesNames).forEach(([v,n])=>source.add(new Option(n,v)));sourceLabel.append(source);$('static-atlas-form').insertBefore(sourceLabel,$('static-atlas-form').querySelector('button'));
function stop(){clearInterval(playback);playback=null;$('static-play').textContent='▶ Play month';}
async function json(url,gzip=false){const r=await fetch(url,{signal:AbortSignal.timeout(45000)});if(!r.ok)throw Error('Archive file unavailable ('+r.status+'). Retry this view.');return gzip?JSON.parse(await new Response(r.body.pipeThrough(new DecompressionStream('gzip'))).text()):r.json();}
async function cached(url,gzip=false){const key=String(url);if(!cache.has(key))cache.set(key,json(url,gzip).catch(e=>{cache.delete(key);throw e;}));return cache.get(key);}
function period(c){const start=`${c.year}-${String(c.month).padStart(2,'0')}-01`,end=C.monthEnd(c.year,c.month);return {...c,start,end,as_of:end,case:'',calendar_metric:'combined',geometry:'',source:'',method_id:'fireatlas-raw-calendar-v1',unit:'observed occupied 1 km cell-days',release_id:'',result_sha256:'',metric:'density',scope:'daily'};}
function bounds(text){const b=String(text).split(',').map(v=>v.trim()===''?NaN:Number(v));if(b.length!==4||b.some(v=>!Number.isFinite(v))||b[0]>=b[2]||b[1]>=b[3])throw Error('Enter a valid west,south,east,north area.');return b;}
function controls(c){$('static-region').value=c.region;source.value=c.series;$('static-year').value=String(c.year);$('static-month').value=String(c.month);$('static-bbox').value=c.bbox;$('static-day').max=String(new Date(Date.UTC(c.year,c.month,0)).getUTCDate());$('static-day').value=c.day?String(Number(c.day.slice(8))):'1';$('static-day-label').value=c.day||'All dates';$('static-all').setAttribute('aria-pressed',String(!c.day));}
function busy(on){$('static-atlas-form').querySelector('button').disabled=on;['static-play','static-all','static-day','static-fit'].forEach(id=>$(id).disabled=on||draft||!result);document.querySelectorAll('[data-static-layer],#explore-months button,#explore-days button').forEach(b=>b.disabled=on||draft||!result);}
function baseMap(){
 if(typeof L==='undefined'){$('static-map-status').textContent='Map library unavailable. Exact calendars and downloads remain available.';return;}
 map=L.map('static-map',{scrollWheelZoom:true,minZoom:2,maxZoom:14,attributionControl:false});L.control.attribution({prefix:false}).addTo(map);
 background=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors',maxZoom:18}).addTo(map);
 marks=L.layerGroup().addTo(map);outline=L.rectangle([[0,0],[0,0]],{color:'#2457D6',weight:2,dashArray:'7 6',fillOpacity:0}).addTo(map);
 background.on('tileerror',()=>{$('static-context-status').textContent='Basemap imagery unavailable. Dated observation markers and archive totals remain usable.';});
}
function layer(name){
 if(!map||!applied||draft)return;
 document.querySelectorAll('[data-static-layer]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.staticLayer===name)));
 $('static-display-label').textContent='Map display · '+({ndvi:'Vegetation NDVI',landcover:'Land cover',none:'Hotspots only'}[name]||'Hotspots only');
 if(overlay){map.removeLayer(overlay);overlay=null;}
 if(name==='ndvi'||name==='landcover'){
  const d=new Date(applied.end+'T00:00:00Z'),first=Date.UTC(d.getUTCFullYear(),0,1),composite=new Date(first+Math.floor((d-first)/86400000/16)*16*86400000).toISOString().slice(0,10);const ndvi=name==='ndvi',z=ndvi?9:8,date=ndvi?composite:`${Math.min(2024,applied.year)}-01-01`,product=ndvi?'MODIS_Terra_L3_NDVI_16Day':'MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual';
  overlay=L.tileLayer(`https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${product}/default/${date}/GoogleMapsCompatible_Level${z}/{z}/{y}/{x}.png`,{attribution:'NASA GIBS / MODIS',maxNativeZoom:z,maxZoom:14,opacity:.82}).addTo(map);
  $('static-context-status').textContent=(ndvi?'NASA MODIS NDVI composite':'NASA MODIS annual land cover')+' · '+date+' · landscape context.';
  const active=overlay;overlay.on('tileerror',()=>{if(overlay===active)$('static-context-status').textContent='Some landscape imagery is unavailable. Observation markers and exact counts remain usable.';});
 }else $('static-context-status').textContent='Geographic basemap · observation markers remain available if background imagery fails.';
 applied={...applied,layer:name};C.update(applied,{reason:'explore-layer'});
}
function fit(){if(!map||!applied)return;const [w,s,e,n]=bounds(applied.bbox);map.fitBounds([[s,w],[n,e]],{padding:[24,24]});}
function mapRows(){
 if(!applied)return;
 if(!marks){$('static-map-status').textContent='Map library unavailable. Exact calendars and downloads remain available.';return;}
 const [w,s,e,n]=bounds(applied.bbox),sourceId=applied.series==='modis'?'MODIS_SP':applied.series==='viirs-snpp'?'VIIRS_SNPP_SP':null;
 const days=selectedDay?rows.filter(d=>d.date_utc===selectedDay):rows;
 const visible=days.flatMap(d=>d.observations||[]).filter(o=>{const r=o.raw||{};return (!sourceId||o.source_id===sourceId)&&Number(r.longitude)>=w&&Number(r.longitude)<=e&&Number(r.latitude)>=s&&Number(r.latitude)<=n;});
 marks?.clearLayers();
 if(marks)visible.forEach(o=>{const r=o.raw||{},modis=o.sensor==='MODIS',marker=L.marker([Number(r.latitude),Number(r.longitude)],{icon:L.divIcon({className:'static-observation-marker',html:`<span class="${modis?'modis':'viirs'}" aria-hidden="true"></span>`,iconSize:[12,12],iconAnchor:[6,6]}),title:`${o.sensor} · ${o.platform} · ${o.acquisition_utc}`,alt:o.sensor+' observation'}),popup=node('div');popup.append(node('strong',o.sensor+' · '+o.platform),node('p',o.acquisition_utc+' UTC · confidence '+(r.confidence??'unknown')+' · FRP '+(r.frp??'unknown')+' MW'));marker.bindPopup(popup);marks.addLayer(marker);});
 const capped=days.some(d=>d.truncated);$('static-map-status').textContent=fmt(visible.length)+' bundled point samples shown · '+(selectedDay||names[applied.month-1]+' '+applied.year)+(capped?' · capped at 200 records per day':'')+'. Exact totals are shown in the calendar.';
}
function selectDay(day,{history=false,playing=false}={}){
 if(!applied||draft)return;if(!playing)stop();selectedDay=day||'';$('static-all').setAttribute('aria-pressed',String(!day));if(day)$('static-day').value=String(Number(day.slice(8)));$('static-day-label').value=day||'All dates';applied={...applied,day:selectedDay};C.update(applied,{history:history?'push':'replace',reason:'explore-day'});mapRows();renderDays();
}
function value(item){return item.detected_cell_days==null?(item.partial_import_detected_cell_days>0?'≥ '+fmt(item.partial_import_detected_cell_days):'Unknown'):fmt(item.detected_cell_days);}
function renderDays(){
 if(!result||!applied)return;
 const ym=`${applied.year}-${String(applied.month).padStart(2,'0')}`,days=result.daily.filter(d=>d.date_utc.startsWith(ym)),grid=$('explore-days');grid.replaceChildren();$('explore-days-title').textContent=names[applied.month-1]+' '+applied.year+' · UTC';
 const offset=(new Date(ym+'-01T00:00:00Z').getUTCDay()+6)%7;for(let i=0;i<offset;i++)grid.append(node('span'));
 const max=Math.max(1,...result.daily.map(d=>d.detected_cell_days??0));
 const legend=$('explore-colors');legend.replaceChildren(node('span','Cells/day · year-wide logarithmic scale'));const ticks=[...new Set([1,...Array.from({length:4},(_,i)=>Math.max(1,Math.round(Math.expm1(Math.log1p(max)*(i+1)/4))))])];for(const value of ticks){const tick=node('span'),swatch=node('i');swatch.style.background=FireAtlasPalette.heat(Math.log1p(value)/Math.log1p(max)).color;tick.append(swatch,document.createTextNode(fmt(value)));legend.append(tick);}
 for(const d of days){const b=node('button',undefined,d.detected_cell_days==null?'partial':d.detected_cell_days===0?'zero':'known');b.type='button';b.dataset.day=d.date_utc;if(d.detected_cell_days>0){const heat=FireAtlasPalette.heat(Math.log1p(d.detected_cell_days)/Math.log1p(max));b.style.setProperty('--day-heat',heat.color);b.style.setProperty('--day-ink',heat.dark?'#000':'#fff');}b.append(node('span',String(Number(d.date_utc.slice(8)))),node('strong',value(d)==='Unknown'?'?':value(d)));const gap=Object.values(d.availability_by_source||{}).some(v=>v.status==='documented_processing_gap');if(gap){b.classList.add('processing-gap');b.append(node('small','gap'));}b.setAttribute('aria-label',d.date_utc+' UTC'+(gap?' · documented processing gap':'')+': '+value(d)+' occupied cell-days; '+(d.export_window_complete?'complete export':'partial or unknown export'));b.setAttribute('aria-pressed',String(selectedDay===d.date_utc));b.onclick=()=>selectDay(d.date_utc,{history:true});b.onkeydown=e=>{const step={ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7}[e.key];if(!step)return;e.preventDefault();const index=days.indexOf(d),next=days[index+step];if(next){selectDay(next.date_utc);grid.querySelector('[data-day=\"'+next.date_utc+'\"]')?.focus();}};grid.append(b);}
 const day=days.find(d=>d.date_utc===selectedDay);$('explore-day-detail').textContent=day?day.date_utc+' UTC · '+value(day)+' occupied cell-days · '+(Object.values(day.availability_by_source||{}).some(s=>s.status==='documented_processing_gap')?'documented processing gap · ':'')+'satellite pass/cloud coverage unknown.':'Month view · choose a date to inspect its points and exact count.';
 const tbody=$('explore-records');tbody.replaceChildren(...days.map(d=>{const tr=node('tr');[d.date_utc,d.detected_cell_days==null?'Unknown':fmt(d.detected_cell_days),d.partial_import_detected_cell_days==null?'—':fmt(d.partial_import_detected_cell_days),Object.values(d.availability_by_source||{}).some(s=>s.status==='documented_processing_gap')?'Complete export · documented product gap':d.export_window_complete?'Complete export':'Partial / unknown'].forEach(v=>tr.append(node('td',v)));return tr;}));
}
function render(){
 if(!result)return;const month=result.monthly[applied.month-1];$('explore-results').hidden=false;
 $('explore-status').textContent=regions.get(applied.region).name+' · '+names[applied.month-1]+' '+applied.year+' · '+seriesNames[applied.series]+' · exact full-region calendar';
 const metrics=[['Occupied cell-days',value(month),month.export_window_complete?'Complete collected export':'Partial evidence; total unknown'],['MODIS imported rows',fmt(month.source_raw_rows.MODIS),'Eligible observations in this month'],['VIIRS imported rows',fmt(month.source_raw_rows.VIIRS),'Eligible observations in this month'],['Prior-year median',fmt(month.baseline_median),month.baseline_years.length+' comparable prior years']];
 $('explore-metrics').replaceChildren(...metrics.map(([l,v,n])=>{const a=node('article');a.append(node('span',l),node('strong',v),node('small',n));return a;}));
 const max=Math.max(1,...result.monthly.map(m=>m.detected_cell_days??m.partial_import_detected_cell_days??0));
 $('explore-months').replaceChildren(...result.monthly.map((m,i)=>{const b=node('button',undefined,'explore-month'+(m.export_window_complete?'':' partial'));b.type='button';b.setAttribute('aria-pressed',String(applied.month===i+1));b.setAttribute('aria-label',names[i]+': '+value(m)+' occupied cell-days');b.append(node('span',names[i].slice(0,3)),node('span',undefined,'explore-bar'),node('strong',value(m)));b.children[1].style.setProperty('--bar-width',Math.max(1,Number(m.detected_cell_days??m.partial_import_detected_cell_days??0)/max*100)+'%');b.onclick=()=>load(period({...applied,month:i+1,day:''}),true);return b;}));
 $('static-map-coverage').textContent=month.export_window_complete?'Selected source export is complete. Satellite pass and cloud coverage remain unknown.':'Selected source export is partial or unknown. Positive detections are retained; missing dates are not zeros.';
 C.status($('static-atlas-status'),month.export_window_complete?'COMPLETE EXPORT':'PARTIAL / UNKNOWN',month.export_window_complete?'available':'partial');renderDays();
}
async function load(cfg,push=false){
 const token=++serial;window.FireAtlasAreaAvailability.cancel($('static-area-availability'));retrySelection={...cfg};stop();result=null;rows=[];selectedDay=cfg.day||'';draft=false;$('explore-results').hidden=true;$('explore-retry').hidden=true;$('explore-reset').hidden=true;$('explore-download').hidden=true;marks?.clearLayers();$('explore-status').textContent='Loading exact calendar…';$('static-map-status').textContent='Loading point samples…';busy(true);
 try{
  if(cfg.errors?.length)throw Error(cfg.errors.join('. '));if(cfg.geometry){$('explore-reset').hidden=false;throw Error('Polygon selections require the local analysis service. Use the full regional archive to browse these frozen totals.');}const full=period(cfg);if(cfg.start!==full.start||cfg.end!==full.end){$('explore-reset').hidden=false;throw Error('This frozen calendar covers a full UTC month. Use the full regional archive or the local service for a shorter interval.');}if(cfg.source){$('explore-reset').hidden=false;throw Error('Apply an explicit satellite-source selection to use the raw archive.');}if(!regions.has(cfg.region))throw Error('Choose a supported archived region.');
  const b=bounds(cfg.bbox),r=regions.get(cfg.region).bbox;if(b.some((v,i)=>v!==r[i])){$('explore-reset').hidden=false;throw Error('This area has no exact frozen calendar. Use the full regional archive, or use the local service for a custom study.');}
  const entry=manifest.files[[cfg.region,cfg.series,cfg.year].join('/')];if(!entry)throw Error('This source or year is not present in the frozen archive. Choose another selection.');
  applied=period(cfg);controls(applied);C.update(applied,{history:push?'push':'replace',reason:'explore-study'});fit();layer(applied.layer);
  const [cal,points]=await Promise.allSettled([cached(new URL(entry.path,countRoot)),cached(new URL(`observations/${cfg.region}/${cfg.year}.json.gz`,dataRoot),true)]);
  if(token!==serial)return;
  if(points.status==='fulfilled')rows=Object.entries(points.value.days||{}).filter(([d])=>Number(d.slice(5,7))===cfg.month).map(([date_utc,v])=>({date_utc,...v}));
  mapRows();if(points.status==='rejected'){$('static-map-status').textContent='Point samples unavailable. The exact calendar remains independent of this map.';$('explore-retry').hidden=false;}
  if(cal.status==='rejected')throw cal.reason;
  if(cal.value.series!==cfg.series||cal.value.year!==cfg.year||cal.value.bbox.join(',')!==cfg.bbox)throw Error('The returned calendar does not match this selection.');
  result=cal.value;applied={...applied,release_id:manifest.release_id,result_sha256:entry.sha256};C.update(applied,{reason:'explore-result'});render();$('explore-download').href=new URL(entry.path,countRoot);$('explore-download').download=`explore-${cfg.region}-${cfg.series}-${cfg.year}.json`;$('explore-download').hidden=false;
  $('static-selection-title').textContent=regions.get(cfg.region).name+' · '+names[cfg.month-1]+' '+cfg.year;$('static-selection-meta').textContent=seriesNames[cfg.series]+' · '+cfg.bbox+' · UTC';$('static-study-link').href=C.link('research.html');document.querySelector('.static-study-editor').open=false;
 }catch(e){if(token!==serial)return;draft=true;$('explore-status').textContent=e.message;$('explore-retry').hidden=false;C.status($('static-atlas-status'),'VIEW UNAVAILABLE','unavailable');$('static-map-status').textContent='This selection is unavailable. Update the study or retry.';document.querySelector('.static-study-editor').open=true;}
 finally{if(token===serial)busy(false);}
}
async function init(){
 try{
  const [r,m]=await Promise.all([cached(new URL('regions.json',dataRoot)),cached(new URL('manifest.json',countRoot))]);regions=new Map(r.regions.map(v=>[v.id,v]));manifest=m;
  $('static-region').replaceChildren(...r.regions.map(v=>new Option(v.name,v.id)));$('static-month').replaceChildren(...names.map((n,i)=>new Option(n,i+1)));$('static-year').replaceChildren(...Array.from({length:m.calendar_end_year-m.calendar_start_year+1},(_,i)=>new Option(String(m.calendar_start_year+i),m.calendar_start_year+i)));
  baseMap();await load(C.read());
 }catch(e){$('explore-status').textContent=e.message;$('static-map-status').textContent='Archive could not initialize.';$('explore-retry').hidden=false;busy(false);}
}
$('static-atlas-form').onsubmit=e=>{e.preventDefault();load(period({...C.read(),region:$('static-region').value,year:Number($('static-year').value),month:Number($('static-month').value),series:source.value,bbox:$('static-bbox').value,day:''}),true);};
$('static-atlas-form').oninput=()=>{++serial;draft=true;stop();$('static-selection-meta').textContent='Draft settings changed. Apply view to update the map and calendar.';if(!result)$('explore-status').textContent='Draft settings changed. Apply view to load this selection.';busy(false);};
$('static-region').onchange=()=>{if(regions?.has($('static-region').value))$('static-bbox').value=regions.get($('static-region').value).bbox.join(',');};
$('static-available-data').onclick=()=>{if(applied&&!draft)window.FireAtlasAreaAvailability.show($('static-area-availability'),{bbox:applied.bbox,year:applied.year,region:applied.region,staticMode:true});};
$('static-day').oninput=()=>selectDay(`${applied.year}-${String(applied.month).padStart(2,'0')}-${String($('static-day').value).padStart(2,'0')}`);
$('static-all').onclick=()=>selectDay('');$('static-fit').onclick=fit;
$('static-play').onclick=()=>{if(playback){stop();return;}if(draft||!result)return;$('static-play').textContent='Ⅱ Pause';playback=setInterval(()=>{const next=selectedDay?Number(selectedDay.slice(8))%Number($('static-day').max)+1:1;selectDay(`${applied.year}-${String(applied.month).padStart(2,'0')}-${String(next).padStart(2,'0')}`,{playing:true});$('static-play').textContent='Ⅱ Pause';},900);};
$('explore-retry').onclick=()=>manifest?load(retrySelection||C.read()):init();$('explore-reset').onclick=()=>{const c=C.read(),region=regions.has(c.region)?c.region:'norcal';load(period({...c,region,bbox:regions.get(region).bbox.join(','),series:manifest.series.includes(c.series)?c.series:'joint',year:Math.max(manifest.calendar_start_year,Math.min(manifest.calendar_end_year,c.year)),day:'',errors:[]}),true);};
document.querySelectorAll('[data-static-layer]').forEach(b=>b.onclick=()=>layer(b.dataset.staticLayer));
window.addEventListener('fireatlas:context-restore',()=>{if(manifest)load(C.read());});window.addEventListener('beforeunload',stop);
init();
})();
