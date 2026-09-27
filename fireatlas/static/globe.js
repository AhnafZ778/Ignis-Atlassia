/* Authentic NASA observations on the existing analytic Earth renderer. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const format = value => new Intl.NumberFormat("en", {maximumFractionDigits:1}).format(value);
  const stamp = value => value ? value.replace("T", " · ").replace(":00Z", " UTC") : "Unknown";
  const coords = (lon, lat) => `${Math.abs(lat).toFixed(2)}°${lat < 0 ? "S" : "N"} / ${Math.abs(lon).toFixed(2)}°${lon < 0 ? "W" : "E"}`;
  const state = {data:null, points:[], visible:[], selected:null, details:null, bridge:null, canvas:null, context:null, request:0, detailRequest:0, controller:null, detailController:null, failedEarth:false};
  function element(tag, text, className) {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (className) el.className = className;
    return el;
  }
  function setRotationUI(playing) {
    $("globe-rotate").textContent = playing ? "Pause rotation" : "Resume rotation";
    $("globe-rotate").setAttribute("aria-pressed", String(!playing));
  }
  function focus(lon, lat) {
    state.bridge?.focus(lon, lat);
    setRotationUI(false);
  }
  function draw(view) {
    const canvas = state.canvas, ctx = state.context;
    if (!canvas || !ctx || !view) return;
    const dpr = Math.min(devicePixelRatio || 1, 1.5);
    const width = Math.round(view.width*dpr), height = Math.round(view.height*dpr);
    if (canvas.width !== width || canvas.height !== height) {canvas.width = width;canvas.height = height;}
    ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,view.width,view.height);
    state.visible = [];
    if (!$("globe-markers").checked) {canvas.dataset.visible="0";return;}
    const markerScale=Math.min(1,Math.max(.58,view.width/1000));
    const latest = state.data?.daily.at(-1)?.date;
    for (const item of state.points) {
      const point = FireGlobeMath.project(item.vector, view);
      if (!point) continue;
      const radius = Math.min(3.7, 1.2+Math.log10(item.count+1)*.72)*markerScale;
      const recent = item.last.slice(0,10) === latest;
      ctx.beginPath();ctx.arc(point.x,point.y,radius,0,Math.PI*2);
      ctx.fillStyle = recent ? "rgba(255,198,118,.90)" : "rgba(220,105,49,.72)";ctx.fill();
      if (item.count > 300 && view.width>700) {
        ctx.beginPath();ctx.arc(point.x,point.y,radius+2.4,0,Math.PI*2);ctx.fillStyle="rgba(255,112,47,.10)";ctx.fill();
      }
      if (item.id === state.selected) {
        ctx.beginPath();ctx.arc(point.x,point.y,9,0,Math.PI*2);ctx.strokeStyle="#fff0d6";ctx.lineWidth=1.5;ctx.stroke();
      }
      state.visible.push({x:point.x,y:point.y,radius,id:item.id});
    }
    // Exact coordinates from the selected cell's latest observation sample.
    for (const row of state.details?.observations || []) {
      const p = FireGlobeMath.project(FireGlobeMath.vector(row.lon,row.lat),view);
      if (!p) continue;
      ctx.beginPath();ctx.arc(p.x,p.y,2,0,Math.PI*2);ctx.fillStyle="#baf2ed";ctx.fill();
    }
    canvas.dataset.visible = String(state.visible.length);
    setRotationUI(view.playing);
  }
  function attach(frame) {
    const doc = frame.contentDocument, bridge = frame.contentWindow.fireAtlasEarth;
    if (!doc || !bridge || state.bridge === bridge) return;
    state.bridge = bridge;
    const overlay = doc.createElement("canvas");
    overlay.id="fire-observations";overlay.setAttribute("aria-hidden","true");
    overlay.style.cssText="position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:2";
    doc.body.append(overlay);state.canvas=overlay;state.context=overlay.getContext("2d");
    bridge.onFrame=draw;
    const visibility=new IntersectionObserver(entries=>bridge.setVisible(entries[0].isIntersecting),{rootMargin:"80px"});
    visibility.observe(frame);
    const surface=doc.getElementById("earth");
    surface.setAttribute("aria-label","Earth with NASA thermal detection clusters. Drag or use arrow keys to rotate. Click a point to inspect it, or use Browse detection clusters on the page.");
    let down=null;const pointers=new Set();
    surface.addEventListener("pointerdown", e => {pointers.add(e.pointerId);down={x:e.clientX,y:e.clientY,id:e.pointerId,moved:pointers.size>1};});
    surface.addEventListener("pointermove", e => {
      if (down && Math.hypot(e.clientX-down.x,e.clientY-down.y)>6) down.moved=true;
      if (!down) surface.style.cursor=state.visible.some(p=>Math.hypot(p.x-e.clientX,p.y-e.clientY)<Math.max(p.radius+3,6))?"pointer":"grab";
    });
    surface.addEventListener("pointercancel",e=>{pointers.delete(e.pointerId);down=null;});
    surface.addEventListener("pointerup",e=>{
      pointers.delete(e.pointerId);
      if (!down || down.id!==e.pointerId || down.moved) {down=null;return;}
      down=null;
      const target=state.visible.map(p=>({...p,d:Math.hypot(p.x-e.clientX,p.y-e.clientY)}))
        .filter(p=>p.d <= (e.pointerType==="touch"?13:8)).sort((a,b)=>a.d-b.d)[0];
      if(target) select(target.id);
    });
    draw(bridge.view);
  }
  async function json(url, signal) {
    const response=await fetch(url,{signal});const body=await response.json();
    if(!response.ok) throw new Error(body.error || "NASA snapshot could not load.");return body;
  }
  function clearSelection() {
    state.detailController?.abort();state.detailRequest++;state.selected=null;state.details=null;
    $("globe-selection").hidden=true;$("globe-location").value="";
  }
  async function load() {
    const request=++state.request;state.controller?.abort();state.controller=new AbortController();
    clearSelection();state.points=[];state.visible=[];
    const source=$("globe-source").value, day=$("globe-date").value;
    $("globe-source").disabled=true;$("globe-date").disabled=true;$("globe-location").disabled=true;
    $("globe-total").textContent="—";$("globe-retry").hidden=true;$("globe-status").textContent="Loading the selected observation snapshot…";
    try {
      const data=await json(`/api/globe?${new URLSearchParams({source,date:day})}`,AbortSignal.any([state.controller.signal,AbortSignal.timeout(45000)]));
      if(request!==state.request)return;
      state.data=data;state.points=data.clusters.map(item=>({...item,vector:FireGlobeMath.vector(item.lon,item.lat)}));
      $("globe-total").textContent=format(data.total);
      $("globe-cell-count").textContent=`${format(data.clusters.length)} geographic clusters`;
      $("globe-period").textContent=data.latest_observation ? `${data.window_start} → ${data.window_end} · UTC\nLatest observation ${stamp(data.latest_observation)}` : "No NASA FIRMS snapshot imported on this server.";
      $("globe-stamp").textContent=data.latest_observation ? `${day==="all"?data.window_start+" → "+data.window_end:day} · IMPORTED SNAPSHOT` : "NO NASA OBSERVATIONS IMPORTED";
      const sourceOptions=[new Option("All satellites · observations","all"),...data.sources.map(s=>new Option(s.label,s.source_id))];
      $("globe-source").replaceChildren(...sourceOptions);$("globe-source").value=source;
      const dates=[new Option("Entire imported snapshot","all")];
      if(data.window_start) {
        const d=new Date(data.window_start+"T00:00:00Z"),end=new Date(data.window_end+"T00:00:00Z");
        for(;d<=end;d.setUTCDate(d.getUTCDate()+1)) dates.push(new Option(d.toISOString().slice(0,10),d.toISOString().slice(0,10)));
      }
      $("globe-date").replaceChildren(...dates);$("globe-date").value=day;
      $("globe-location").replaceChildren(new Option("Select a point, or browse…",""),...data.clusters.slice(0,40).map(c=>new Option(`${coords(c.lon,c.lat)} · ${format(c.count)}`,c.id)));
      $("globe-status").textContent=data.total ? `${day==="all"?"Snapshot loaded":"Selected day loaded"} · grouped in 1° cells. Select a point or browse the 40 largest clusters.${state.failedEarth?" 3D unavailable; the list and evidence remain accessible.":""}` : "No detections imported for this selection. This does not establish fire-free conditions. Open Data sources to inspect coverage.";
      $("globe-source").disabled=!data.sources.length;$("globe-date").disabled=!data.sources.length;$("globe-location").disabled=!data.total;
    } catch(error) {
      if(request!==state.request)return;
      $("globe-status").textContent=error.name==="TimeoutError"?"Snapshot request timed out. Retry loading the imported data.":error.message;
      $("globe-stamp").textContent="OBSERVATION DATA UNAVAILABLE";
      $("globe-cell-count").textContent="Snapshot unavailable";$("globe-retry").hidden=false;
      $("globe-source").disabled=false;$("globe-date").disabled=false;
    }
  }
  async function select(id) {
    const item=state.points.find(c=>c.id===id);if(!item)return;
    const request=++state.detailRequest;state.detailController?.abort();state.detailController=new AbortController();
    state.selected=id;state.details=null;focus(item.lon,item.lat);
    if(![...$("globe-location").options].some(o=>o.value===id))$("globe-location").add(new Option(coords(item.lon,item.lat),id));
    $("globe-location").value=id;
    const panel=$("globe-selection");panel.hidden=false;panel.replaceChildren(element("p","Loading source evidence…"));
    try {
      const data=await json(`/api/globe/detail?${new URLSearchParams({cell:id,source:state.data.source,date:state.data.date})}`,AbortSignal.any([state.detailController.signal,AbortSignal.timeout(30000)]));
      if(request!==state.detailRequest)return;
      state.details=data;panel.replaceChildren();
      const close=element("button","×","globe-close");close.type="button";close.setAttribute("aria-label","Close selected cluster");close.addEventListener("click",clearSelection);
      panel.append(close,element("span","SELECTED OBSERVATIONS","globe-kicker"),element("h3",coords(item.lon,item.lat)));
      const facts=element("dl");
      for(const [key,value] of [["Detections",format(data.total)],["Peak pixel FRP",item.max_frp_mw==null?"Unknown":`${format(item.max_frp_mw)} MW`],["Cell extent","1° × 1°"]])facts.append(element("dt",key),element("dd",value));
      panel.append(facts,element("p",`First in selection: ${stamp(item.first)}\nLast in selection: ${stamp(item.last)}`));
      panel.append(element("p",data.condition));
      panel.append(element("p","FRP measures radiative power of an observed pixel. It is not a wildfire severity score. Cyan points show the latest record sample at its original coordinates."));
      const links=element("div",undefined,"globe-atlas-links");
      const series={MODIS_NRT:"modis-nrt",VIIRS_NOAA20_NRT:"viirs-noaa20-nrt",VIIRS_NOAA21_NRT:"viirs-noaa21-nrt",VIIRS_SNPP_NRT:"viirs-snpp-nrt"};
      for(const src of data.sources) {
        const name=state.data.sources.find(s=>s.source_id===src.source_id)?.label || src.source_id;
        const link=element("a",`${name} · ${format(src.count)} ↗`);
        const bbox=[data.bbox[0],Math.max(-86,data.bbox[1]),data.bbox[2],Math.min(86,data.bbox[3])];
        link.href=`/?${new URLSearchParams({demo:0,series:series[src.source_id],year:src.last.slice(0,4),month:Number(src.last.slice(5,7)),bbox:bbox.join(",")})}#atlas-section`;
        link.title="Inspect this satellite and area in the atlas";links.append(link);
      }
      panel.append(links);
      const details=element("details"),list=element("ol");details.append(element("summary",`Inspect ${data.observations.length} latest source records`));
      for(const row of data.observations) {
        const li=element("li");li.append(element("strong",coords(row.lon,row.lat)),element("div",stamp(row.acquisition_utc)),element("div",`${row.source_id} · ${row.frp_mw==null?"FRP unknown":format(row.frp_mw)+" MW"} · confidence ${row.confidence_raw}`));list.append(li);
      }
      details.append(list);panel.append(details);
      panel.scrollIntoView({behavior:matchMedia("(prefers-reduced-motion: reduce)").matches?"instant":"smooth",block:"nearest"});
    } catch(error) {if(request===state.detailRequest)panel.replaceChildren(element("p",`Evidence unavailable: ${error.message}. Select the cluster again to retry.`));}
  }
  window.addEventListener("earth-ready",event=>attach(event.detail.frame));
  window.addEventListener("earth-unavailable",()=>{
    state.failedEarth=true;
    $("globe-status").textContent+=" 3D unavailable; use Browse detection clusters to inspect the same data.";
    document.querySelectorAll("[data-globe-region],#globe-rotate,#globe-zoom-in,#globe-zoom-out").forEach(b=>b.disabled=true);
  });
  document.addEventListener("DOMContentLoaded",()=>{
    $("globe-date").addEventListener("change",load);$("globe-source").addEventListener("change",load);$("globe-retry").addEventListener("click",load);
    $("globe-location").addEventListener("change",e=>e.target.value?select(e.target.value):clearSelection());
    $("globe-rotate").addEventListener("click",()=>{state.bridge?.setPlaying(!state.bridge.view.playing);});
    $("globe-zoom-in").addEventListener("click",()=>state.bridge?.zoom(-.3));$("globe-zoom-out").addEventListener("click",()=>state.bridge?.zoom(.3));
    document.querySelectorAll("[data-globe-region]").forEach(button=>button.addEventListener("click",()=>{clearSelection();focus(...button.dataset.globeRegion.split(",").map(Number));}));
    load();
  });
})();
