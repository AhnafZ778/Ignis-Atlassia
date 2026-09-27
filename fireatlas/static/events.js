// Global FIRMS snapshot, historical reports and EONET remain distinct layers.
(() => {
  const $ = id => document.getElementById(id);
  const regions = window.FireAtlasRegions = {
    world: {name:"Worldwide", bounds:[[-60,-180],[80,180]]},
    africa: {name:"Africa", bounds:[[-35,-20],[38,52]]},
    asia: {name:"Asia", bounds:[[0,52],[80,180]]},
    europe: {name:"Europe", bounds:[[38,-25],[75,52]]},
    "north-america": {name:"North America", bounds:[[7,-170],[80,-50]]},
    "south-america": {name:"South America", bounds:[[-56,-82],[13,-34]]},
    oceania: {name:"Oceania", bounds:[[-50,110],[0,180]]}
  };
  const number = n => new Intl.NumberFormat("en").format(n);
  const coordinate = p => `${Math.abs(p.lat).toFixed(2)}°${p.lat<0?"S":"N"} / ${Math.abs(p.lon).toFixed(2)}°${p.lon<0?"W":"E"}`;
  const date = stamp => new Intl.DateTimeFormat("en",{timeZone:"UTC",month:"short",day:"numeric",year:"numeric"}).format(new Date(stamp));
  const el = (tag,text) => {const node=document.createElement(tag);node.textContent=text;return node;};
  let map,points,layer="thermal",records=[],request=0,shown=30;
  const cache={},markers=new Map();
  function regionalRecords() {
    const key=$("event-region").value;
    if(key==="world")return records;
    const [[south,west],[north,east]]=regions[key].bounds;
    return records.filter(p=>p.lat>=south&&p.lat<=north&&p.lon>=west&&p.lon<=east);
  }
  function resetView(){if(map)map.fitBounds(regions[$("event-region").value].bounds,{padding:[20,20],maxZoom:5,animate:false});}
  function initMap(){
    if(typeof L==="undefined")return;
    map=L.map("event-map",{scrollWheelZoom:false,worldCopyJump:true,minZoom:0,zoomSnap:0.25,preferCanvas:true}).setView([15,0],1);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{attribution:"&copy; OpenStreetMap contributors",maxZoom:18,className:"atlas-basemap"}).addTo(map);
    points=L.layerGroup().addTo(map);resetView();
    map.on("zoomend",()=>{
      if(layer!=="thermal")return;
      for(const marker of markers.values())marker.setRadius(marker.options.baseRadius*Math.min(1.2,Math.max(.4,map.getZoom()/4)));
    });
    let width=0;
    new ResizeObserver(entries=>{const next=entries[0].contentRect.width;if(next!==width){width=next;map.invalidateSize();resetView();}}).observe($("event-map"));
  }
  function globeButton(record){
    const button=el("button","Explore on 3D Earth →");button.type="button";button.className="event-globe-link";
    button.addEventListener("click",()=>{
      window.dispatchEvent(new CustomEvent("fireatlas-map-selection",{detail:{layer,id:record.id}}));
      document.querySelector(".globe-hero").scrollIntoView({behavior:matchMedia("(prefers-reduced-motion:reduce)").matches?"auto":"smooth",block:"start"});
    });return button;
  }
  function popup(record){
    const box=el("div","");
    box.append(el("strong",layer==="thermal"?coordinate(record):record.name||record.title));
    if(layer==="thermal"){
      box.append(el("p",`${number(record.count)} satellite detections · 1° cell`),el("p",`Last observed ${record.last.replace("T"," ").replace("Z"," UTC")}`),el("p",record.max_frp_mw==null?"Peak pixel FRP unknown":`Peak pixel FRP: ${number(record.max_frp_mw)} MW`),globeButton(record));
    }else if(layer==="documented"){
      box.append(el("p",`${record.place} · ${record.period}`),el("p",record.summary));
      for(const source of record.sources){const a=el("a",`${source.publisher} report ↗`);a.href=source.url;a.target="_blank";a.rel="noopener noreferrer";box.append(a,el("br",""));}
      box.append(globeButton(record));
    }else{
      box.append(el("p",`${date(record.date_utc)} · ${record.source_names.join(" + ")}`));
      const a=el("a","NASA event record ↗");a.href=record.url;a.target="_blank";a.rel="noopener noreferrer";box.append(a);
    }return box;
  }
  function select(record,fly=true){
    document.querySelectorAll(".event-card").forEach(card=>{const active=card.dataset.eventId===record.id;card.classList.toggle("selected",active);card.setAttribute("aria-pressed",String(active));});
    const marker=markers.get(record.id);
    if(!marker)return;
    if(fly){map.setView([record.lat,record.lon],5);}
    marker.openPopup();
  }
  function renderList(){
    const filtered=regionalRecords(),list=$("event-list");list.replaceChildren();
    const title=layer==="thermal"?"detection groups":layer==="documented"?"historical cases":"reported locations";
    $("events-status").textContent=`${regions[$("event-region").value].name} · ${number(filtered.length)} ${title}${filtered.length?` · showing ${Math.min(shown,filtered.length)}`:" in this dataset"}.`;
    if(!filtered.length)list.append(el("p","No records here in this layer. Try Satellite detections or another region."));
    for(const record of filtered.slice(0,shown)){
      const card=el("button","");card.type="button";card.className="event-card";card.dataset.eventId=record.id;card.setAttribute("aria-pressed","false");
      const heading=layer==="thermal"?`${number(record.count)} satellite detections`:record.name||record.title;
      const caption=layer==="thermal"?`LAST OBSERVED ${record.last.slice(0,10)}`:layer==="documented"?record.period:`${date(record.date_utc)} / ${record.source_names[0]||"EONET"}`;
      card.append(el("span",caption),el("strong",heading),el("small",layer==="documented"?record.place:coordinate(record)));
      card.addEventListener("click",()=>select(record));list.append(card);
    }
    $("event-more").hidden=shown>=filtered.length;
  }
  function render(data){
    records=layer==="thermal"?data.clusters:data.events;
    $("event-map").dataset.layer=layer;$("event-map").dataset.points=records.length;
    $("event-count").textContent=number(layer==="thermal"?data.total:records.length);
    const thermal=layer==="thermal",documented=layer==="documented";
    $("event-count-label").textContent=thermal?"SATELLITE DETECTIONS · WORLDWIDE":documented?"HISTORICAL CASES":"REPORTED EVENTS · SAMPLE";
    $("event-updated").textContent=thermal?`${data.window_start||"No imported data"} → ${data.window_end||"—"} · imported snapshot`:documented?"Published historical reports · not live activity":`Fetched ${date(data.fetched_utc)} · ${data.stale?"cached copy":"NASA EONET"}`;
    $("event-legend").textContent=thermal?"● THERMAL DETECTION GROUPS":documented?"◆ DOCUMENTED HISTORICAL FIRES":"● REPORTED EVENTS · SAMPLE";
    $("event-legend").dataset.layer=layer;
    $("event-list-heading").textContent=thermal?"LARGEST DETECTION GROUPS":documented?"EXPLORE FIRE STORIES":"REPORTED LOCATIONS";
    $("event-layer-note").textContent=thermal?"Same global FIRMS snapshot as the 3D Earth. Points group satellite detections in 1° cells; they are not fire boundaries or a count of wildfires. Thermal signals include agricultural burning. Current fire status is unknown.":documented?"Selected historical cases with published reports. Locations mark approximate affected communities, not ignition points or boundaries. This collection is not a global inventory.":`${data.stale?"NASA could not be reached; showing a cached sample. ":""}EONET is a curated event feed, not global satellite coverage. This sample is limited to ${data.sample_limit||data.count} events and may be dominated by US sources; its wildfire category includes prescribed fires. Use Satellite detections for worldwide observations.`;
    const source=$("event-source-link");source.href=thermal?"https://firms.modaps.eosdis.nasa.gov/active_fire/":documented?"/documented-fires.json":"https://eonet.gsfc.nasa.gov/docs/v3";
    source.textContent=thermal?"About NASA FIRMS ↗":documented?"View source collection ↗":"About NASA EONET ↗";
    markers.clear();points?.clearLayers();
    for(const record of records){
      if(!map)break;
      const color=thermal?(record.last.slice(0,10)===data.window_end?"#ffc676":"#dc6931"):documented?"#83cfff":"#8bc5bc";
      const baseRadius=thermal?Math.min(4,1.3+Math.log10(record.count+1)*.7):7;
      const marker=L.circleMarker([record.lat,record.lon],{baseRadius,radius:thermal?baseRadius*Math.min(1.2,Math.max(.4,map.getZoom()/4)):7,color,weight:thermal?0:2,fillColor:color,fillOpacity:thermal?.8:.9}).addTo(points);
      marker.bindPopup(()=>popup(record),{minWidth:170,maxWidth:250});marker.on("click",()=>select(record,false));markers.set(record.id,marker);
    }
    renderList();if(map){map.invalidateSize();resetView();}
  }
  async function load(refresh=false){
    const token=++request,current=layer;$("event-refresh").disabled=true;$("events-status").textContent="Loading selected layer…";
    try{
      let data=cache[current];
      if(!data||refresh){
        const url=current==="thermal"?"/api/globe?source=all&date=all":current==="documented"?"/documented-fires.json":`/api/events${refresh?"?refresh=1":""}`;
        const response=await fetch(url,{signal:AbortSignal.timeout(45000)});data=await response.json();if(!response.ok)throw new Error(data.error||"Data unavailable");cache[current]=data;
      }
      if(token===request)render(data);
    }catch(error){if(token===request){$("events-status").textContent=`Could not load this layer. ${error.message}. Use Reload to retry.`;$("event-updated").textContent="Layer unavailable";}}
    finally{if(token===request)$("event-refresh").disabled=false;}
  }
  document.addEventListener("DOMContentLoaded",()=>{
    initMap();
    document.querySelectorAll("[data-event-layer]").forEach(button=>button.addEventListener("click",()=>{
      layer=button.dataset.eventLayer;shown=30;records=[];points?.clearLayers();markers.clear();$("event-list").replaceChildren();$("event-more").hidden=true;$("event-count").textContent="—";
      document.querySelectorAll("[data-event-layer]").forEach(b=>b.setAttribute("aria-pressed",String(b===button)));load();
    }));
    $("event-region").addEventListener("change",()=>{shown=30;renderList();resetView();});
    $("event-more").addEventListener("click",()=>{shown+=30;renderList();});
    $("event-refresh").addEventListener("click",()=>load(true));
    $("event-reset").addEventListener("click",()=>{$("event-region").value="world";shown=30;renderList();resetView();});
    // Preserve the landing globe's lazy data load until this map approaches view.
    const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){observer.disconnect();load();}},{rootMargin:"200px"});observer.observe($("live-events"));
  });
})();
