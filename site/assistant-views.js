/* Semantic page capabilities. Models never receive selectors or executable code. */
(() => {
  'use strict';
  const registry = new Map(), maps = new Map();
  const targets = {'overview-globe':'earth-frame-host','terrain-globe':'earth','source-catalog':'source-catalog','archive-ledger':'data-references','native-files':'native-mask-downloads','imports':'import-workflow','calculation-method':'data-flow','native-review':'sample-workspace','atlas-map':'atlas-section','raw-calendar':'calendar-section','harmonized-calendar':'harmonized-calendar','sensor-overlap':'overview-result','candidate-groups':'candidate-list','coverage-rates':'coverage-output','validation-gates':'validation-gates','replay-map':'replay-workspace','replay-timeline':'replay-timeline','replay-records':'source-records','assistant-map':'mission-map-stage','assistant-records':'mission-panel-evidence','assistant-sources':'mission-panel-network'};
  function registerMap(name,map){maps.set(name,map);}
  async function focusPlace(place){
    if(!place?.bbox)throw Error('A resolved place is required.');
    if(adapter()?.focusPlace){await adapter().focusPlace(place);window.dispatchEvent(new CustomEvent('fireatlas:place-focused',{detail:place}));return;}
    const entries=[...maps.values()].filter(m=>m?.fitBounds);
    if(!entries.length)throw Error('This page has no geographic map. Open Atlas or the assistant map.');
    for(const map of entries){const [w,s,e,n]=place.bbox;map.invalidateSize();map.fitBounds([[s,w],[n,e]],{animate:false,maxZoom:14,padding:[24,24]});if(map._assistantPlace)map._assistantPlace.remove();map._assistantPlace=L.circleMarker([place.latitude,place.longitude],{radius:9,color:'#fff',weight:3,fillColor:'#9bbd9f',fillOpacity:.6}).addTo(map).bindTooltip(place.title+' · geographic reference',{permanent:true,direction:'top'});}
    window.dispatchEvent(new CustomEvent('fireatlas:place-focused',{detail:place}));
  }
  function highlight(target,label){
    const node=document.getElementById(targets[target]);if(!node)throw Error('The requested visual target is unavailable on this page.');
    for(let p=node;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;
    window.dispatchEvent(new CustomEvent('fireatlas:highlight',{detail:{target}}));
    node.classList.add('assistant-annotated-target');node.setAttribute('tabindex','-1');node.scrollIntoView({behavior:'auto',block:'center'});node.focus({preventScroll:true});
    document.getElementById('assistant-visual-guide')?.remove();const guide=document.createElement('aside');guide.id='assistant-visual-guide';guide.className='assistant-visual-guide';guide.setAttribute('role','status');const title=document.createElement('strong');title.textContent=label||target.replaceAll('-',' ');const text=document.createElement('p');text.textContent='The outlined section is the requested evidence location. Its source values and download links remain authoritative.';const close=document.createElement('button');close.type='button';close.textContent='Dismiss highlight';close.onclick=()=>{guide.remove();node.classList.remove('assistant-annotated-target');};const exportButton=document.createElement('button');exportButton.type='button';exportButton.textContent='Save annotated evidence guide';exportButton.onclick=async()=>{exportButton.disabled=true;try{const figure=await captureGuide(target),api=window.FireAtlasAssistant.request,image=await api('images',{...figure,revision:window.FireAtlasAssistant.context().revision}),marked=await api('figures/annotate',{image_id:image.id,target});const a=document.createElement('a');a.href='data:image/png;base64,'+marked.data;a.download='fireatlas-'+target+'-guide.png';a.click();text.textContent='Annotated guide saved using OpenCV. Full source evidence remains in the outlined panel.';}catch(e){text.textContent=e.message;}finally{exportButton.disabled=false;}};guide.append(title,text,exportButton,close);document.body.append(guide);
  }

  const destinations = {overview:['',''],terrain:['terrain-earth.html','earth'],atlas:['atlas.html','atlas-section'],calendar:['atlas.html','calendar-section'],harmonized:['atlas.html','harmonized-calendar'],replay:['replay.html','replay-workspace'],timeline:['replay.html','replay-timeline'],records:['replay.html','source-records'],overlap:['research.html','overview-result'],candidates:['research-candidates.html','candidate-list'],exposure:['research-exposure.html','coverage-output'],validation:['research-validation.html','validation-gates'],sources:['data.html','main-content'],method:['method.html','data-flow'],review:['review.html','sample-workspace'],assistant:['assistant.html','assistant-workspace']};
  const id = sessionStorage.getItem('fireatlas-view-instance') || crypto.randomUUID();
  sessionStorage.setItem('fireatlas-view-instance',id);
  function register(name,adapter) { registry.set(name,adapter); window.dispatchEvent(new CustomEvent('fireatlas:adapter-ready')); }
  function adapter() { return registry.get(document.body.dataset.page) || registry.values().next().value; }
  function validAdapterContext(){const c={...(adapter()?.context?.()||{})};if(c.year!=null&&(!Number.isFinite(c.year)||c.year<2000))delete c.year;if(c.month!=null&&(!Number.isFinite(c.month)||c.month<1||c.month>12))delete c.month;if(c.start&&c.start.startsWith('0-'))delete c.start;for(const k of ['start','end','as_of','day'])if(c[k]==='')delete c[k];return c;}
  function context() {
    const params=new URLSearchParams(location.search),extended={};
    for(const key of ['case','start','end','source','metric','view','context','scale'])if(params.has(key))extended[key]=params.get(key);
    // The existing calendar context is month-scoped. Preserve replay intervals
    // on source/method/globe pages as well, including cases spanning two months.
    if(extended.end)extended.as_of=params.get('as_of')||extended.end;
    const value = {...(window.FireAtlasContext?.read() || {year:2024,month:7,bbox:'-122,39,-120,41',as_of:'2024-07-31',series:'joint',distance_km:2,gap_days:1,region:'norcal',layer:'ndvi'}),...extended,...validAdapterContext()};
    if(typeof value.bbox === 'string') value.bbox=value.bbox.split(',').map(Number);
    return value;
  }
  function state() { return {instance:id,page:document.body.dataset.page || 'overview',selection:adapter()?.selection?.() || null,capabilities:[...(adapter()?.capabilities || []),"semantic section highlighting"],visual_targets:Object.keys(targets).filter(k=>document.getElementById(targets[k])&&(k!=='replay-records'||document.body.dataset.page==='replay')),...(adapter()?.state?.() || {}),analysis_depth:document.getElementById('assistant-depth')?.value || 'efficient'}; }
  function link(destination,cfg) {
    const route=destinations[destination]; if(!route) throw Error('Unsupported destination.');
    const url=new URL(route[0] || './',location.href);
    Object.entries(cfg).forEach(([k,v])=>{if(!['revision','mask_id'].includes(k) && v !== '' && v != null)url.searchParams.set(k,Array.isArray(v)?v.join(','):v);});
    if(route[1])url.hash=route[1];return url;
  }
  async function apply(action) {
    const target=link(action.destination,action.context);
    if(target.pathname!==location.pathname) { sessionStorage.setItem('fireatlas-pending-action',JSON.stringify(action)); location.assign(target.href);return {navigating:true}; }
    const options=action.options||{};
    if(options.kind==='highlight'){highlight(options.target,action.place?.title);return {state:'applied',actual:{...context(),highlighted_target:options.target}};}
    // Await the actual study bundle, not just the controller's registration.
    let active=adapter(),until=Date.now()+45000;
    while((!active || active.state?.().ready===false) && Date.now()<until){await new Promise(r=>setTimeout(r,250));active=adapter();if(!active&&['data','method','review'].includes(document.body.dataset.page))break;}
    if(active?.state?.().ready===false)throw Error('The requested page is still loading its observations. Retry after its study is ready.');
    if(options.kind==='focus_place'){await focusPlace(action.place);return {state:'applied',actual:{...context(),camera_place:action.place.title,camera_bbox:action.place.bbox,study_unchanged:true}};}
    if(active?.apply) await active.apply(action.context,action);
    else {
      const original=context();
      if(JSON.stringify(original.bbox)!==JSON.stringify(action.context.bbox) || original.year!==action.context.year || original.month!==action.context.month) return {state:'failed',actual:{reason:'This page cannot change its study directly. Open the destination with study settings.'}};
    }
    const section=document.getElementById(destinations[action.destination][1]);
    if(section) { section.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});section.classList.add('assistant-focus');setTimeout(()=>section.classList.remove('assistant-focus'),4000);section.setAttribute('tabindex','-1');section.focus({preventScroll:true}); }
    return {state:'applied',actual:context()};
  }

  async function captureGuide(target){
    const node=document.getElementById(targets[target]);if(!node)throw Error('This panel is not available.');
    const canvas=document.createElement('canvas');canvas.width=1200;canvas.height=1000;const g=canvas.getContext('2d');g.fillStyle='#0c1b21';g.fillRect(0,0,1200,1000);g.fillStyle='#f0eee3';g.font='24px system-ui';g.fillText('Evidence panel / '+target.replaceAll('-',' '),32,38);g.fillStyle='#adc9c6';g.font='13px system-ui';g.fillText('Text captured from the actual page. This is an evidence guide, not a map screenshot.',32,64);
    let y=103;const lines=(node.innerText||node.textContent).split(/\n/).map(t=>t.trim()).filter(Boolean);g.font='15px system-ui';g.fillStyle='#e1ece8';for(const line of lines){const words=line.split(/\s+/);let row='';for(const word of words){if(g.measureText(row+' '+word).width>1100){g.fillText(row,40,y);y+=22;row=word;}else row+=(row?' ':'')+word;if(y>900)break;}if(y>900)break;g.fillText(row,40,y);y+=26;}
    g.fillStyle='#a5c991';g.font='12px system-ui';g.fillText('Open the live outlined section for full values, source fingerprints, and download links.',32,968);
    return {data:canvas.toDataURL('image/png').split(',')[1],mime:'image/png',caption:'Actual text evidence guide from '+location.pathname+' / '+target+'; lengthy content truncated; full values remain on the page.',regions:[{target,rect:[22,80,1156,858],label:target.replaceAll('-',' ')}]};
  }
  document.addEventListener('DOMContentLoaded',()=>{
    if(document.body.dataset.page==='overview')register('overview',{
      capabilities:['globe focus'],context:()=>({}),
      focusPlace:async place=>{const bridge=document.querySelector('iframe')?.contentWindow?.fireAtlasEarth;if(!bridge?.focus)throw Error('The globe is still loading.');bridge.cancelOrbit?.();if(bridge.focusBounds){if(await bridge.focusBounds(place.bbox)===false)throw Error('Globe navigation was interrupted. Try again.');}else{await bridge.focus(place.longitude,place.latitude);await bridge.zoom?.(-.5);}},
      apply:async cfg=>{const bridge=document.querySelector('iframe')?.contentWindow?.fireAtlasEarth;if(!bridge?.focus)throw Error('The existing Earth is still loading. Retry when it is ready.');const [w,s,e,n]=cfg.bbox;if(bridge.focusBounds){if(await bridge.focusBounds(cfg.bbox)===false)throw Error('Globe navigation was interrupted. Try again.');}else await bridge.focus((w+e)/2,(s+n)/2,{altitude:2000000});},
      state:()=>({ready:Boolean(document.querySelector('iframe')?.contentWindow?.fireAtlasEarth?.focus),meaning:'geographic globe; source records remain authoritative'})
    });
    if(document.body.dataset.page==='terrain'&&!new URLSearchParams(location.search).has('embed'))register('terrain',{
      capabilities:['terrain camera focus','geographic context'],context:()=>({}),state:()=>({ready:Boolean(window.fireAtlasEarth?.view),meaning:'Landscape context only; no active-fire observations on this globe'}),
      focusPlace:async place=>{const bridge=window.fireAtlasEarth;if(!bridge?.view)throw Error('Terrain imagery is still loading.');bridge.setPlaying(false);if(await bridge.focusBounds(place.bbox)===false)throw Error('Terrain navigation was interrupted. Try again.');},
      apply:async cfg=>{const [w,s,e,n]=cfg.bbox;await registry.get('terrain').focusPlace({longitude:(w+e)/2,latitude:(s+n)/2,bbox:cfg.bbox});}
    });
    if(['data','method','review'].includes(document.body.dataset.page))register(document.body.dataset.page,{capabilities:['source and method inspection','visual evidence guide'],state:()=>({ready:true}),apply:async()=>{}});
  });
  window.FireAtlasViews={register,adapter,context,state,link,apply,instance:id,destinations,registerMap,focusPlace,highlight,targets,captureGuide};
})();

/* Location presentation is separate from observation evidence and query settings. */
(() => {
  const modes=new Map(),listeners=new Set();let current=null;
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const validPoint=p=>Array.isArray(p)&&p.length===2&&p.every(Number.isFinite);
  const point=(p,digits=5)=>validPoint(p)?`Latitude ${p[1].toFixed(digits)}° · Longitude ${p[0].toFixed(digits)}°`:'Coordinates unavailable';
  const bounds=b=>Array.isArray(b)&&b.length===4&&b.every(Number.isFinite)?`W ${b[0].toFixed(4)}° · S ${b[1].toFixed(4)}° · E ${b[2].toFixed(4)}° · N ${b[3].toFixed(4)}°`:'Boundary unavailable';
  function area(b){if(!Array.isArray(b))return 'Custom study area';if(b[0]>=-122.2&&b[2]<=-120&&b[1]>=38.8&&b[3]<=41)return 'Northern California, United States';if(b[0]>=73.8&&b[2]<=77.6&&b[1]>=29.5&&b[3]<=32.6)return 'Punjab–Haryana, India';return 'Custom study area';}
  function set(value){current=value;listeners.forEach(fn=>fn(value));}
  function detail(key,name,coordinateText,kind){
    const wrap=node('div',null,'location-detail'),text=node('span'),button=node('button');button.type='button';
    function paint(){const coords=modes.get(key)||false;text.textContent=coords?`${kind}: ${coordinateText}`:name;button.textContent=coords?'Show location':'Show coordinates';button.setAttribute('aria-pressed',String(coords));button.setAttribute('aria-label',`${coords?'Show location name':'Show coordinates'} for ${name}`);}
    button.addEventListener('click',()=>{modes.set(key,!modes.get(key));paint();});wrap.append(text,button);paint();return wrap;
  }
  function strip(){
    const wrap=node('div',null,'assistant-location-context'),title=node('strong'),text=node('span'),copy=node('button','Copy coordinates'),notice=node('span',null,'location-copy-status');copy.type='button';text.tabIndex=0;notice.setAttribute('role','status');notice.setAttribute('aria-live','polite');
    const render=v=>{v=v||{label:'Current study boundary',bbox:window.FireAtlasViews.context()?.bbox};title.textContent=v.label+(v.date?` · ${v.date} UTC`:'');text.textContent=v.point?point(v.point,v.digits??5):bounds(v.bbox);copy.disabled=!validPoint(v.point)&&!(Array.isArray(v.bbox)&&v.bbox.length===4&&v.bbox.every(Number.isFinite));notice.textContent='';};
    copy.addEventListener('click',async()=>{try{if(!navigator.clipboard?.writeText)throw Error();await navigator.clipboard.writeText(text.textContent);notice.textContent='Coordinates copied.';}catch{const range=document.createRange();range.selectNodeContents(text);const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);text.focus();notice.textContent='Coordinates selected. Use your device’s copy command.';}});
    wrap.append(title,text,copy,notice);listeners.add(render);window.addEventListener('fireatlas:selection-changed',e=>{if(e.detail?.label)notice.textContent=e.detail.label+' selected. Coordinates updated.';});render(current);return wrap;
  }
  window.addEventListener('fireatlas:selection-changed',e=>{if(e.detail?.label)set(e.detail);});
  window.addEventListener('fireatlas:place-focused',e=>set({label:`Geographic reference · ${e.detail.title}`,point:[e.detail.longitude,e.detail.latitude]}));
  window.addEventListener('fireatlas:study-changed',e=>set({label:'Current study boundary',bbox:e.detail?.bbox||window.FireAtlasViews.context()?.bbox}));
  window.FireAtlasLocation={point,bounds,area,detail,strip,set,get current(){return current;}};
})();
