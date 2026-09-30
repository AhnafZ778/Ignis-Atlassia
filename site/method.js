/* Actual records and calculations from the existing local NASA archive. */
document.addEventListener('DOMContentLoaded', () => {
  const $ = s => document.querySelector(s), NS = 'http://www.w3.org/2000/svg';
  const params = new URLSearchParams(location.search), names = {MODIS_SP:'MODIS',VIIRS_SNPP_SP:'VIIRS S-NPP'};
  const fmt = n => Number(n).toLocaleString('en-US');
  const liteEarth = params.get('lite') === '1';
  const explicitContext = params.get('context') === 'calendar';
  let report = null, recordRequest = 0, checkRequest = 0, auditUrl = null, selectedCell = null;
  let context = explicitContext ? {year:params.get('year'),month:params.get('month'),series:params.get('series')||'joint',bbox:params.get('bbox'),day:params.get('day')||''} : null;
  const archiveCache = new Map();
  const staticDataRoot = document.querySelector('meta[name="fireatlas-static-data"]')?.content;
  const staticCache = new Map();
  function node(tag, attrs, parent, text) { const n=document.createElementNS(NS,tag); for(const [k,v] of Object.entries(attrs||{})) n.setAttribute(k,v); if(text!==undefined)n.textContent=text; parent.append(n); return n; }
  function svgText(parent,x,y,text,size=11,color='#b6cdd1') {return node('text',{x,y,fill:color,'font-family':'DM, sans-serif','font-size':size,'text-anchor':'middle'},parent,text);}
  function calendarUrl(c) { const q=new URLSearchParams(c); if(liteEarth)q.set('lite','1');else q.delete('lite'); return `./?${q}#calendar-section`; }
  if(liteEarth)for(const selector of ['#method-calendar','#context-calendar','#flow-calendar-link']){const link=$(selector);if(link)link.href='./?lite=1#calendar-section';}
  async function json(url) { const r=await fetch(url); const data=await r.json(); if(!r.ok)throw Error(data.error||`Request failed (${r.status})`); return data; }
  async function staticFile(path) {
    const target=new URL(path,new URL(staticDataRoot,document.baseURI));
    if(!staticCache.has(target.href)){
      const response=await fetch(target);if(!response.ok)throw Error(`Bundled evidence unavailable (${response.status})`);
      let value;
      if(path.endsWith('.gz')){
        if(typeof DecompressionStream!=='function')throw Error('This browser cannot open the compressed source-row bundle.');
        value=JSON.parse(await new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).text());
      }else value=await response.json();
      staticCache.set(target.href,value);
    }
    return staticCache.get(target.href);
  }
  function inside(bbox,outer){return bbox.every((value,index)=>Math.abs(Number(value)-Number(outer[index]))<1e-5);}
  async function staticCaseFor(contextValue,dateValue){
    if(report&&report.selected_date_utc===dateValue&&inside(contextValue.bbox.split(','),report.bbox))return report;
    const requested=params.get('case');
    const candidates=requested? [requested] : ['park-2024','grove-2025'];
    for(const id of candidates){
      if(!['park-2024','grove-2025'].includes(id))continue;
      const summary=await staticFile(`validity/${id}.json`);
      if(inside(contextValue.bbox.split(','),summary.bbox)&&dateValue>=summary.start_utc.slice(0,10)&&dateValue<=summary.end_utc.slice(0,10))
        return dateValue===summary.selected_date_utc?summary:await staticFile(`validity/${id}/${dateValue}.json`);
    }
    return null;
  }
  function rowsFromCase(caseReport,series){
    const allowed=series==='modis'?['MODIS_SP']:series==='viirs-snpp'?['VIIRS_SNPP_SP']:['MODIS_SP','VIIRS_SNPP_SP'];
    return caseReport.selected_day_cells.flatMap(cell=>cell.records).filter(row=>allowed.includes(row.source_id)).map(row=>({
      ...row,sensor:row.source_id==='MODIS_SP'?'MODIS':'VIIRS',processing_level:'SP',demo:0,
    }));
  }
  async function loadStaticRecords(contextValue,dateValue){
    const caseReport=await staticCaseFor(contextValue,dateValue);
    if(caseReport){
      const allowed=contextValue.series==='modis'?['MODIS_SP']:contextValue.series==='viirs-snpp'?['VIIRS_SNPP_SP']:['MODIS_SP','VIIRS_SNPP_SP'];
      const selectedRows=rowsFromCase(caseReport,contextValue.series);
      const sources=caseReport.sources.filter(source=>allowed.includes(source.source_id)).map(source=>{
        const raw=caseReport.days.reduce((sum,day)=>sum+(day.raw_pixels[source.source_id]||0),0);
        const cells=caseReport.days.reduce((sum,day)=>sum+(day.detected_cell_days[source.source_id]||0),0);
        return {...source,raw_pixels:raw,detected_cell_days:cells};
      });
      const detectedCellDays=caseReport.days.reduce((sum,day)=>sum+(allowed.length===2?day.joint_detected_cell_days:day.detected_cell_days[allowed[0]]||0),0);
      const audit={schema:'fireatlas-static-case-audit-v1',scope_label:`${caseReport.title} case window`,year:Number(dateValue.slice(0,4)),month:Number(dateValue.slice(5,7)),
        raw_pixels_total:sources.reduce((sum,item)=>sum+item.raw_pixels,0),
        detected_cell_days:detectedCellDays,
        sources,baseline_version_status:'Historical event case; this is not a seasonal baseline.',provenance:caseReport.provenance};
      return {observations:selectedRows,truncated:false,audit,provenance:caseReport.provenance,caseId:caseReport.case_id};
    }
    const regionData=await staticFile('regions.json');
    const bbox=contextValue.bbox.split(',').map(Number);
    const region=regionData.regions.find(item=>bbox[0]>=item.bbox[0]&&bbox[1]>=item.bbox[1]&&bbox[2]<=item.bbox[2]&&bbox[3]<=item.bbox[3]);
    if(!region)throw Error('This area is not included in the bundled historical regions.');
    const archive=await staticFile(`observations/${region.id}/${dateValue.slice(0,4)}.json.gz`);
    const day=archive.days[dateValue]||{observations:[],truncated:false};
    const allowed=contextValue.series==='modis'?['MODIS_SP']:contextValue.series==='viirs-snpp'?['VIIRS_SNPP_SP']:['MODIS_SP','VIIRS_SNPP_SP'];
    const observations=day.observations.filter(item=>{
      const lon=Number(item.raw.longitude),lat=Number(item.raw.latitude);
      return allowed.includes(item.source_id)&&lon>=bbox[0]&&lon<=bbox[2]&&lat>=bbox[1]&&lat<=bbox[3];
    }).map(item=>({source_id:item.source_id,sensor:item.sensor,platform:item.platform,acquisition_utc:item.acquisition_utc,
      confidence_raw:item.raw.confidence??'unknown',product_version:item.raw.version??'unknown',lon:Number(item.raw.longitude),lat:Number(item.raw.latitude),raw:item.raw,demo:0}));
    const sourceIds=allowed.filter(id=>observations.some(item=>item.source_id===id));
    const provenance=(await staticFile(`calendar/${region.id}/${dateValue.slice(0,4)}.json`)).meta.inputs||[];
    const audit={schema:'fireatlas-static-source-audit-v1',scope_label:`${region.name} source rows`,year:Number(dateValue.slice(0,4)),month:Number(dateValue.slice(5,7)),
      raw_pixels_total:null,detected_cell_days:null,baseline_version_status:'A selected-area monthly audit is not included in the static bundle.',
      sources:sourceIds.map(source_id=>({source_id,raw_pixels:null,detected_cell_days:null,product_versions:[],full_month_export:false})),provenance};
    return {observations,truncated:day.truncated,audit,provenance,caseId:null};
  }
  function stateClear() {
    report=null;++checkRequest; $('#run-recount').disabled=true;$('#trace-cell').disabled=true;
    for(const id of ['flow-pixels','flow-cells','flow-date','hero-day','union-modis','union-viirs','union-overlap','union-total','proof-app','proof-check'])$('#'+id).textContent='—';
    $('#flow-day').disabled=true;$('#flow-context').textContent='Source data unavailable';$('#flow-calendar').replaceChildren();$('#flow-grid').replaceChildren();$('#trace-lane').hidden=true;$('#trace-empty').hidden=false;$('#trace-empty').textContent='Source data unavailable. Retry to load the historical case.';
    $('#trace-original').textContent='Source data unavailable.';$('#trace-rows').replaceChildren();$('#proof-state').textContent='Source data unavailable';$('#proof-pixels').textContent='No current result';$('#proof-label').textContent='Source data unavailable';$('#proof-symbol').textContent='?';$('.proof-result').removeAttribute('data-status');
    $('#recount-status').textContent='A recount requires available source records.';
    if(!explicitContext){++recordRequest;$('#method-source-rows').replaceChildren();$('#method-ledger').replaceChildren();$('#method-source-table').replaceChildren();$('#record-status').textContent='Source data unavailable.';}
  }
  function drawFlow(day) {
    $('#hero-day').textContent=day.date_utc.slice(8);
    $('#flow-context').textContent=report.title;const dateSelect=$('#flow-day');dateSelect.replaceChildren();for(const d of report.days)dateSelect.add(new Option(d.date_utc,d.date_utc,false,d.date_utc===day.date_utc));dateSelect.disabled=false;
    $('#flow-pixels').textContent=fmt(Object.values(day.raw_pixels).reduce((a,b)=>a+b,0));
    $('#flow-cells').textContent=fmt(day.joint_detected_cell_days);$('#flow-date').textContent=day.date_utc+' UTC';
    $('#flow-calendar-link').href=calendarUrl({series:'joint',year:day.date_utc.slice(0,4),month:Number(day.date_utc.slice(5,7)),day:day.date_utc,bbox:report.bbox.join(',')});
    const svg=$('#flow-calendar');svg.replaceChildren();node('title',{},svg,'Actual counts for days in the selected historical case');
    const maximum=Math.max(1,...report.days.map(d=>d.joint_detected_cell_days));
    report.days.forEach((d,i)=>{const x=9+(i%5)*38,y=18+Math.floor(i/5)*43,active=d.date_utc===day.date_utc;
      node('rect',{x,y,width:33,height:37,rx:4,fill:d.joint_detected_cell_days?`rgba(139,211,202,${.12+.65*d.joint_detected_cell_days/maximum})`:'#13252e',stroke:active?'#ffaf7c':'#47616b','stroke-width':active?2:1},svg);
      svgText(svg,x+16.5,y+12,d.date_utc.slice(8),8,'#c4d8dc');svgText(svg,x+16.5,y+27,d.joint_detected_cell_days,10,'#f3f6f3');
    });
    const g=$('#flow-grid');g.replaceChildren();node('title',{},g,'Schematic of records grouped into a common grid; the detailed example below uses actual source rows');
    for(let x=0;x<4;x++)for(let y=0;y<3;y++)node('rect',{x:27+x*36,y:20+y*36,width:36,height:36,fill:x===1&&y===1?'#6aaf9c44':'#11242d',stroke:'#51727c'},g);
    svgText(g,100,148,'1 km × 1 km · schematic',10);
    $('#union-modis').textContent=fmt(day.detected_cell_days.MODIS_SP);$('#union-viirs').textContent=fmt(day.detected_cell_days.VIIRS_SNPP_SP);$('#union-overlap').textContent=fmt(day.co_detected_cell_days);$('#union-total').textContent=fmt(day.joint_detected_cell_days);
    const picker=$('#trace-cell');picker.replaceChildren();
    const cells=[...report.selected_day_cells].sort((a,b)=>b.raw_pixels-a.raw_pixels);
    for(const c of cells)picker.add(new Option(`${c.grid_x}, ${c.grid_y} · ${c.raw_pixels} ${c.raw_pixels===1?'record':'records'}`,`${c.grid_x}:${c.grid_y}`));
    picker.disabled=!cells.length;$('#trace-lane').hidden=!cells.length;$('#trace-empty').hidden=!!cells.length;
    $('#trace-empty').textContent="No detections in this day's imported records. Observation coverage remains unknown.";
    selectedCell=cells[0]||null;renderCell();
  }
  function renderCell() {
    const holder=$('#trace-rows');holder.replaceChildren();
    if(!selectedCell){$('#trace-original').textContent='No source rows for this day.';return;}
    $('#trace-coordinates').textContent=`Cell ${selectedCell.grid_x}, ${selectedCell.grid_y}`;$('#trace-date').textContent=report.selected_date_utc+' UTC';
    const rows=selectedCell.records,shown=rows.slice(0,5);
    $('#trace-record-caption').textContent=`${shown.length} of ${rows.length} original observations`;
    for(const row of shown){const b=document.createElement('button');b.type='button';b.setAttribute('aria-pressed','false');
      const dot=document.createElement('i');dot.className='dot '+(row.source_id==='MODIS_SP'?'modis':'viirs');
      const name=document.createElement('span');name.textContent=names[row.source_id]||row.source_id;
      const time=document.createElement('span');time.textContent=row.acquisition_utc.slice(11,16)+' UTC';
      b.append(dot,name,time);b.addEventListener('click',()=>{holder.querySelectorAll('button').forEach(n=>n.setAttribute('aria-pressed',String(n===b)));$('#trace-original').textContent=JSON.stringify(row,null,2);});holder.append(b);
    }
    holder.querySelector('button')?.click();
    const square=$('.trace-grid-cell svg');square.querySelectorAll('circle').forEach(n=>n.remove());
    shown.forEach((row,i)=>node('circle',{cx:53+(i%3)*10,cy:54+Math.floor(i/3)*15,r:3,style:`fill:${row.source_id==='MODIS_SP'?'#ffaf7c':'#f4d49d'}`},square));
  }
  $('#flow-day').addEventListener('change',event=>window.dispatchEvent(new CustomEvent('fireatlas:select-validity-day',{detail:{date:event.target.value}})));
  $('#trace-cell').addEventListener('change',e=>{selectedCell=report.selected_day_cells.find(c=>`${c.grid_x}:${c.grid_y}`===e.target.value);renderCell();});
  function resetProof() {
    ++checkRequest;$('#run-recount').disabled=false;$('#run-recount').textContent='Run the recount ↗';
    $('#proof-app').textContent=fmt(report.days.reduce((a,d)=>a+d.joint_detected_cell_days,0));$('#proof-check').textContent='—';$('#proof-state').textContent='Ready to run';$('#proof-symbol').textContent='?';$('#proof-label').textContent='Not run in this view';$('.proof-result').removeAttribute('data-status');
    $('#proof-pixels').textContent='Source pixels + grid + daily union';$('#recount-status').textContent='Recomputes the exported rows using a separate implementation. Human scientific review is still pending.';$('#recount-result').textContent='No check has been run in this view.';
    $('#recount-scope').textContent=`${report.title} · ${report.start_utc} → ${report.end_utc} · whole case, all confidence classes`;
    $('#method-download').href=staticDataRoot
      ?new URL(`validity/${report.case_id}.zip`,new URL(staticDataRoot,document.baseURI)).href
      :`/api/validity/export?case=${report.case_id}`;
    $('#recount-command').textContent=`python3 -m fireatlas.validation_check fireatlas_validity_${report.case_id}.zip`;
  }
  $('#run-recount').addEventListener('click',async()=>{
    if(!report)return;const generation=++checkRequest,id=report.case_id;const button=$('#run-recount');button.disabled=true;button.textContent='Recounting…';$('#proof-state').textContent='Reading frozen rows…';
    try{const data=staticDataRoot
        ?await staticFile(`validity/${id}-check.json`)
        :await json(`/api/validity/check?case=${encodeURIComponent(id)}`);if(generation!==checkRequest)return;
      $('#proof-check').textContent=fmt(data.joint_cell_days);$('#proof-state').textContent='Recomputed from source rows';$('#proof-symbol').textContent=data.calculations_reproduce?'=':'≠';$('#proof-label').textContent=data.calculations_reproduce?'All plotted totals reproduce':'Recount differs';$('.proof-result').dataset.status=data.calculations_reproduce?'passed':'failed';$('#proof-pixels').textContent=`${fmt(data.original_pixels)} source pixels checked`;
      $('#recount-status').textContent=`Calculated ${data.checked_at_utc} · checksums, coordinates, daily counts and sensitivity trials. Human scientific review remains pending.`;$('#recount-result').textContent=JSON.stringify(data,null,2);
    }catch(e){if(generation!==checkRequest)return;$('#proof-check').textContent='—';$('#proof-state').textContent='Check failed';$('#proof-symbol').textContent='!';$('#proof-label').textContent='Could not verify';$('.proof-result').dataset.status='failed';$('#recount-status').textContent=e.message;$('#recount-result').textContent='No successful recount result.';}
    finally{if(generation===checkRequest){button.disabled=false;button.textContent='Run again ↗';}}
  });
  window.addEventListener('fireatlas:validity-report',event=>{
    const next=event.detail,changed=report?.case_id!==next.case_id;report=next;
    const day=report.days.find(d=>d.date_utc===report.selected_date_utc);drawFlow(day);if(changed)resetProof();
    if(!context||!explicitContext)context={year:day.date_utc.slice(0,4),month:Number(day.date_utc.slice(5,7)),series:'joint',bbox:report.bbox.join(','),day:day.date_utc};
    $('#method-calendar').href=calendarUrl(context);
    if(!explicitContext||!$('#record-day').value){$('#record-day').value=context.day||`${context.year}-${String(context.month).padStart(2,'0')}-01`;loadRecords();}
  });
  window.addEventListener('fireatlas:validity-error',stateClear);
  async function loadRecords() {
    if(!context)return;const generation=++recordRequest,selected=$('#record-day').value;
    if(!/^\d{4}-\d{2}-\d{2}$/.test(selected)){$('#record-status').textContent='Choose a valid UTC date.';return;}
    context={...context,day:selected,year:selected.slice(0,4),month:Number(selected.slice(5,7))};
    const c={...context};$('#context-calendar').href=calendarUrl(c);$('#method-calendar').href=calendarUrl(c);
    $('#record-context').textContent=`${explicitContext?'Your calendar selection':selected===report?.selected_date_utc?'Historical case':'Source inspection'} · Imported archive · ${c.series} · ${selected} UTC · AOI ${c.bbox}`;
    $('#record-status').textContent='Loading original source rows…';$('#method-source-rows').replaceChildren();$('#method-source-table').replaceChildren();$('#method-ledger').replaceChildren();$('#method-version-note').textContent='';$('#method-audit-status').textContent='Loading monthly comparison…';$('#method-audit-download').removeAttribute('href');
    const query=new URLSearchParams(c);const monthKey=new URLSearchParams({year:c.year,month:c.month,series:c.series,bbox:c.bbox}).toString();
    try{
      let obs,audit,calendar;
      if(staticDataRoot){
        const bundled=await loadStaticRecords(c,selected);obs={observations:bundled.observations,truncated:bundled.truncated};audit=bundled.audit;calendar={provenance:bundled.provenance};
        const evidenceCase=bundled.caseId||report?.case_id;
        if(evidenceCase){const href=new URL(`validity/${evidenceCase}.zip`,new URL(staticDataRoot,document.baseURI)).href;$('#method-study-download').href=href;$('#method-download').href=href;}
        else $('#method-study-download').removeAttribute('href');
      }else{
        const cached=archiveCache.get(monthKey);
        [obs,[audit,calendar]]=await Promise.all([json(`/api/observations?${new URLSearchParams({date:selected,series:c.series,bbox:c.bbox})}`),cached?Promise.resolve(cached):Promise.all([json(`/api/harmonization?${query}`),json(`/api/calendar?${query}`)])]);
        archiveCache.set(monthKey,[audit,calendar]);$('#method-study-download').href=`/api/study?${query}`;
      }
      if(generation!==recordRequest)return;
      const sourceScope=staticDataRoot?`${audit.scope_label||'Bundled regional archive'} · `:'';
      $('#record-status').textContent=`${sourceScope}${fmt(obs.observations.length)} ${obs.truncated?'displayed source rows · this daily bundle is capped':'source rows'} · ${selected} UTC`;
      if(!obs.observations.length)$('#record-status').textContent='No imported detections on this day. Pass and cloud coverage remain unknown.';
      const fragment=document.createDocumentFragment();
      for(const row of obs.observations){const d=document.createElement('details'),s=document.createElement('summary'),title=document.createElement('strong'),time=document.createElement('span'),confidence=document.createElement('span'),pre=document.createElement('pre');title.textContent=`${row.sensor} · ${row.platform}`;time.textContent=row.acquisition_utc.slice(11,16)+' UTC';confidence.textContent=`Native confidence ${row.confidence_raw} · version ${row.product_version}`;s.append(title,time,confidence);pre.textContent=JSON.stringify(row,null,2);d.append(s,pre);fragment.append(d);}
      $('#method-source-rows').append(fragment);
      $('#method-audit-status').textContent=staticDataRoot
        ?`${audit.scope_label||'Bundled source rows'} · ${audit.raw_pixels_total===null?'monthly row total unavailable':`${fmt(audit.raw_pixels_total)} eligible rows`} → ${audit.detected_cell_days===null?'monthly cell-day total unavailable':`${fmt(audit.detected_cell_days)} detected cell-days`}`
        :`${audit.year}-${String(audit.month).padStart(2,'0')} · whole month · ${fmt(audit.raw_pixels_total)} eligible FIRMS rows → ${audit.detected_cell_days===null?'unknown':fmt(audit.detected_cell_days)} detected cell-days`;
      const table=document.createElement('table');table.innerHTML='<thead><tr><th>Source</th><th>Version</th><th>Eligible rows</th><th>Cell-days</th><th>Export</th></tr></thead>';const body=document.createElement('tbody');
      for(const s of audit.sources){const tr=document.createElement('tr');for(const value of [s.source_id,s.product_versions?.join(', ')||'Unknown',s.raw_pixels===null?'Unknown':fmt(s.raw_pixels),s.detected_cell_days===null?'Unknown':fmt(s.detected_cell_days),s.full_month_export?'Complete':'Not certified']){const td=document.createElement('td');td.textContent=value;tr.append(td);}body.append(tr);}table.append(body);$('#method-source-table').append(table);
      const readings={'mixed-product-versions-across-years':'Product versions differ across years. Historical comparisons are descriptive.','same-observed-product-versions':'Observed product versions match. Observation opportunities remain unknown.','no-qualifying-baseline-years':'No qualifying historical baseline.','unknown-where-source-has-no-detections':'Historical version comparison incomplete where no source rows exist.'};$('#method-version-note').textContent=readings[audit.baseline_version_status]||audit.baseline_version_status;
      if(auditUrl)URL.revokeObjectURL(auditUrl);auditUrl=URL.createObjectURL(new Blob([JSON.stringify(audit,null,2)],{type:'application/json'}));const link=$('#method-audit-download');link.href=auditUrl;link.download=`fireatlas_method_audit_${c.year}_${c.month}.json`;
      for(const source of calendar.provenance||[]){const item=document.createElement('article');item.className='method-ledger-item';const title=document.createElement('strong'),uri=document.createElement('p'),hash=document.createElement('code');title.textContent=`${source.source_id} · Imported${source.retrieved_utc?` · retrieved ${source.retrieved_utc}`:''}`;uri.textContent=source.source_uri;hash.textContent='SHA-256 '+(source.file_sha256||source.parent_sha256||'not provided');item.append(title,uri,hash);$('#method-ledger').append(item);}
      if(!calendar.provenance?.length)$('#method-ledger').textContent='No source imports for this selection.';
    }catch(e){if(generation!==recordRequest)return;$('#record-status').textContent=`Evidence unavailable: ${e.message}`;$('#method-audit-status').textContent='Monthly audit unavailable.';}
  }
  $('#load-records').addEventListener('click',loadRecords);
  if(explicitContext){$('#record-day').value=context.day||`${context.year}-${String(context.month).padStart(2,'0')}-01`;$('#method-calendar').href=calendarUrl(context);loadRecords();}
});
