(() => {
  const C = window.FireAtlasContext;
  const $ = id => document.getElementById(id);
  const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const n = value => value == null ? "—" : Number(value).toLocaleString();
  let report = null, requestVersion=0,scopeStart=new URLSearchParams(location.search).get("start")||null;
  function monthEnd(year, month) { return new Date(Date.UTC(year, month, 0)).toISOString().slice(0, 10); }
  function setCutoff() { $("overview-as-of").value = monthEnd(Number($("overview-year").value), Number($("overview-month").value)); }
  function context() {
    return {year: Number($("overview-year").value), month: Number($("overview-month").value), bbox: C.validBBox($("overview-bbox").value, true), as_of: $("overview-as-of").value, series: "joint", distance_km: Number($("overview-distance").value), gap_days: Number($("overview-gap").value), region: C.read().region, layer: "ndvi",...(scopeStart&&scopeStart.startsWith(`${$("overview-year").value}-${$("overview-month").value.padStart(2,"0")}`)?{start_date:scopeStart}:{})};
  }
  function syncContext() {
    let selected; try { selected = context(); $("overview-bbox").removeAttribute("aria-invalid"); } catch (_) { $("overview-bbox").setAttribute("aria-invalid","true"); return; }
    const url = new URL(location.href);
    url.search = C.write(selected);if(selected.start_date)url.searchParams.set("start",selected.start_date);
    history.replaceState(null, "", url);
    C.apply(document, selected);
  }
  function showError(message) {
    $("overview-error").hidden = false; $("overview-error").textContent = message;
    $("overview-result").setAttribute("aria-busy", "false");
    C.status($("overview-state"), "RESULT UNAVAILABLE", "unavailable");
    $("overview-status").textContent = "No result was returned for this request. Change the study settings or retry the analysis.";
    $("overview-chart").innerHTML = '<div class="empty-state">Daily counts are unavailable. No missing result is treated as zero activity.</div>';
    document.querySelector('[data-study-editor]').open = true;
  }
  function chart(days) {
    const target = $("overview-chart"); target.replaceChildren();
    if (!days?.length) { target.innerHTML = '<div class="empty-state">No daily records were returned. This is not evidence of zero activity.</div>'; return; }
    const max = Math.max(1, ...days.map(day => Number(day.union || 0)));
    const width=1080,height=320,left=62,top=28,bottom=40,plotHeight=height-top-bottom,step=(width-left-18)/days.length;
    const NS='http://www.w3.org/2000/svg';
    const make=(name,attrs,text)=>{const node=document.createElementNS(NS,name);Object.entries(attrs).forEach(([key,value])=>node.setAttribute(key,value));if(text!=null)node.textContent=text;return node;};
    const svg=make('svg',{viewBox:`0 0 ${width} ${height}`,role:'group','aria-label':'Daily source cell-day counts. Select a bar for exact values.'});
    svg.append(make('text',{x:left,y:15,fill:'#4D6575','font-size':12},'Detected 1 km cell-days'));
    for(let tick=0;tick<=4;tick++){
      const value=max*tick/4,y=top+plotHeight*(1-tick/4);
      svg.append(make('line',{x1:left,y1:y,x2:width-16,y2:y,stroke:'#D8DED8','stroke-width':1}));
      svg.append(make('text',{x:left-10,y:y+4,fill:'#4D6575','font-size':12,'text-anchor':'end'},Math.round(value).toLocaleString()));
    }
    const inspector=$("overview-chart-inspector");
    const inspect=(day)=>{if(inspector)inspector.textContent=`${day.date} UTC · MODIS ${n(day.modis)} cell-days · VIIRS ${n(day.viirs)} cell-days · Shared ${n(day.both)} · Distinct union ${n(day.union)}. Source export completeness is shown above.`;};
    days.forEach((day,index)=>{
      let y=top+plotHeight;
      [["modis_only","#A75500"],["both","#287446"],["viirs_only","#006E86"]].forEach(([key,color])=>{
        const h=Number(day[key]||0)/max*plotHeight;
        svg.append(make('rect',{x:left+index*step+3,y:y-h,width:Math.max(2,step-6),height:h,fill:color,rx:2}));y-=h;
      });
      const group=make('g',{role:'button',tabindex:0,'aria-label':`${day.date}: MODIS ${day.modis}, VIIRS ${day.viirs}, shared ${day.both}, union ${day.union}`});
      const hit=make('rect',{x:left+index*step,y:top,width:step,height:plotHeight,fill:'transparent',stroke:'transparent','stroke-width':2});
      group.append(make('title',{},group.getAttribute('aria-label')),hit);
      group.addEventListener('click',()=>inspect(day));group.addEventListener('focus',()=>{hit.setAttribute('stroke','#2457D6');inspect(day);});group.addEventListener('blur',()=>hit.setAttribute('stroke','transparent'));
      group.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();inspect(day);}else if(event.key==='ArrowRight'){event.preventDefault();svg.querySelectorAll('g[role=button]')[Math.min(days.length-1,index+1)]?.focus();}else if(event.key==='ArrowLeft'){event.preventDefault();svg.querySelectorAll('g[role=button]')[Math.max(0,index-1)]?.focus();}});
      svg.append(group);
      if(index===0||index===days.length-1||(index+1)%5===0)svg.append(make('text',{x:left+index*step+step/2,y:height-16,fill:'#4D6575','font-size':12,'text-anchor':'middle'},day.date.slice(8)));
    });
    svg.append(make('text',{x:width-20,y:height-3,fill:'#4D6575','font-size':11,'text-anchor':'end'},'UTC day'));
    target.append(svg);
  }
  function render() {
    const overlap = report.overlap || {}; const totals = overlap.totals || {};
    $("overview-union").textContent = n(totals.union); $("overview-both").textContent = n(totals.both); $("overview-groups").textContent = n(report.candidates?.count);
    $("overview-status").textContent = `${report.config.start_date||`${report.config.year}-${String(report.config.month).padStart(2, "0")}-01`} through ${report.config.as_of} · ${report.data_status === "empty" ? "No imported pixels" : report.demo_data ? "Synthetic demonstration data" : "Imported observations"}.`;
    C.status($("overview-state"), report.data_status === "empty" ? "NO IMPORTED PIXELS" : "RESULT READY", report.data_status === "empty" ? "unknown" : "available");
    const complete = Object.values(report.complete_exports || {}).length > 0 && Object.values(report.complete_exports || {}).every(value => value === true);
    C.status($("overview-completeness"), complete ? "STUDY EXPORTS COMPLETE" : "STUDY EXPORTS PARTIAL / UNKNOWN", complete ? "available" : "partial");
    chart(overlap.daily);
    $("overview-table").replaceChildren(...(overlap.daily || []).map(day => { const row = document.createElement("tr"); [day.date, day.modis, day.viirs, day.both, day.union].forEach(value => { const cell = document.createElement("td"); cell.textContent = value; row.append(cell); }); return row; }));
    $("overview-versions").textContent = Object.entries(overlap.product_versions || {}).map(([source, versions]) => `${source}: ${versions.length ? versions.join(", ") : "no records"}`).join(" · ") || "No source versions returned.";
    $("overview-result").setAttribute("aria-busy", "false");
    C.apply(document, context());
    document.dispatchEvent(new CustomEvent('fireatlas:study-applied',{detail:report.config}));
  }
  async function run(event) {
    event?.preventDefault();
    const request=++requestVersion;
    report=null;
    for(const id of ['overview-union','overview-both','overview-groups'])$(id).textContent='—';
    $("overview-error").hidden = true; $("overview-result").setAttribute("aria-busy", "true"); $("overview-run").disabled = true; $("overview-run").textContent = "Analyzing…";
    C.status($("overview-state"),"CALCULATING","unknown");
    $("overview-status").textContent="Loading imported records for the selected area and dates…";
    $("overview-chart").innerHTML='<div class="empty-state">Calculating daily sensor counts…</div>';
    try {
      if (!$("overview-as-of").value) setCutoff();
      const selected = context();
      const query=C.api(selected);if(selected.start_date)query.set("start_date",selected.start_date);const response = await fetch(`/api/research?${query.toString()}`, {signal: AbortSignal.timeout(30000)});
      const body = await response.json(); if (!response.ok) throw new Error(body.error || "The local analysis service rejected this study.");
      if(request!==requestVersion)return;
      // Apply the actual request scope even if controls were edited while it loaded.
      C.apply(document,selected);
      report = body; syncContext(); render();
    } catch (error) { if(request===requestVersion)showError(error.name === "TimeoutError" ? "The local analysis timed out. Narrow the AOI or cutoff and try again." : `Local analysis service required: ${error.message}`); }
    finally { if(request===requestVersion){$("overview-run").disabled = false; $("overview-run").textContent = "Run analysis ↗";} }
  }
  async function init() {
    months.forEach((name, index) => { const option = new Option(name, index + 1); $("overview-month").add(option); });
    const selected = C.read(); $("overview-month").value = String(selected.month); $("overview-distance").value = String(selected.distance_km); $("overview-gap").value = String(selected.gap_days);
    $("overview-year").replaceChildren(new Option(selected.year,selected.year));
    $("overview-bbox").value = selected.bbox; $("overview-as-of").value = selected.as_of;
    $("overview-month").addEventListener("change", () => { setCutoff(); syncContext(); }); $("overview-year").addEventListener("change", () => { setCutoff(); syncContext(); }); $("overview-controls").addEventListener("input", syncContext); $("overview-controls").addEventListener("submit", run);
    if (document.querySelector('meta[name="fireatlas-static-data"]')) {
      $("overview-year").replaceChildren(new Option(selected.year,selected.year));
      C.apply(document,selected);
      showError("Research calculations require the local analysis service. The Atlas and Fire replay can explore the observations bundled in this release.");
      C.status($("overview-state"),"SERVICE REQUIRED","unavailable");
      $("overview-run").disabled=true; $("overview-run").textContent="Analysis service required";
      $("overview-chart").innerHTML='<div class="empty-state">Daily comparison results are unavailable here. No missing result is treated as zero activity.</div>';
      return;
    }
    // The year inventory is optional. It must not delay the selected study.
    fetch("/api/meta", {signal:AbortSignal.timeout(12000)}).then(r=>r.ok?r.json():Promise.reject()).then(meta=>{
      const current=Number($("overview-year").value), years=[...new Set([...(meta.years||[]),current])].sort((a,b)=>a-b);
      $("overview-year").replaceChildren(...years.map(year=>new Option(year,year)));$("overview-year").value=String(current);
    }).catch(()=>{});
    await run();
  }

  document.addEventListener('DOMContentLoaded', () => window.FireAtlasViews?.register('research', {
    capabilities:['study controls','sensor overlap','exact daily table'],
    context: () => { try{const {start_date,...c}=context();return {...c,start:start_date||`${c.year}-${String(c.month).padStart(2,'0')}-01`,end:c.as_of};}catch{return {};} },
    state: () => ({ready:Boolean(report),report_id:report?.report_id,method:report?.method_version}),
    apply: async cfg => { if(cfg.start?.slice(0,7)!==cfg.end?.slice(0,7))throw Error('Choose a single UTC month for sensor overlap.');scopeStart=cfg.start; const values={year:cfg.year,month:cfg.month,bbox:cfg.bbox.join(','),'as-of':cfg.end,distance:cfg.distance_km,gap:cfg.gap_days};for(const [key,value]of Object.entries(values)){const n=$('overview-'+key);if(n){if(key==='year'&&![...n.options].some(o=>o.value==value))n.add(new Option(value,value));n.value=value;}}await run();if(!report||report.config.as_of!==cfg.end)throw Error('The requested analysis was not loaded.'); },
    capture: async () => { const svg=$('overview-chart').querySelector('svg');if(!svg)throw Error('Run sensor comparison first.');const image=new Image(),serialized=new XMLSerializer().serializeToString(svg);image.src='data:image/svg+xml;base64,'+btoa(unescape(encodeURIComponent(serialized)));await image.decode();const c=document.createElement('canvas');c.width=1080;c.height=320;c.getContext('2d').drawImage(image,0,0);return {data:c.toDataURL('image/png').split(',')[1],mime:'image/png',caption:'Source-specific overlap chart · '+report.report_id+' · observed cell-days'}; }
  }));

  document.addEventListener("DOMContentLoaded", init);
})();
