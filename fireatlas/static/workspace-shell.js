/* Shared analytical navigation; never loaded by the Earth overview. */
(() => {
  'use strict';
  const C=FireAtlasContext,V=FireAtlasViews;
  if(document.body?.dataset.page==='atlas'&&/harmonized-calendar|regional/.test(location.hash)){const target=new URL('./research.html?tab=comparison',location.href),region=new URL(location.href).searchParams.get('region');if(['norcal','punjab-haryana'].includes(region))target.searchParams.set('cmp_region',region);target.search=location.search;target.searchParams.set('tab','comparison');if(['norcal','punjab-haryana'].includes(region))target.searchParams.set('cmp_region',region);location.replace(target);return;}
  const allowed=new Set(['year','month','bbox','as_of','series','day','distance_km','gap_days','region','layer','case','start','end','source','metric','view','revision','mask_id','scale']);
  const originalContext=V.context;
  V.context=()=>Object.fromEntries(Object.entries(originalContext()).filter(([k,v])=>allowed.has(k)&&v!==''));
  Object.assign(V.destinations,{replay:['investigate.html','mission-map-stage'],timeline:['investigate.html','replay-timeline'],records:['investigate.html','mission-panel-evidence'],assistant:['investigate.html','assistant-workspace'],overlap:['research.html?tab=comparison','overview-result'],candidates:['research.html?tab=candidates','candidate-list'],exposure:['research.html?tab=exposure','coverage-output'],validation:['evidence.html?tab=method','research-validation'],sources:['evidence.html?tab=sources','source-catalog'],method:['evidence.html?tab=method','data-flow'],review:['evidence.html?tab=reproduce','sample-workspace']});
  V.targets['replay-map']='mission-map-stage';V.targets['replay-records']='mission-panel-evidence';
  const apply=V.apply;
  V.apply=async action=>{const route=V.destinations[action.destination],target=new URL(route?.[0]||'./',location.href),tab=target.searchParams.get('tab');if(target.pathname===location.pathname&&tab&&window.FireAtlasPanels)await FireAtlasPanels.select(tab,{history:'push'});return apply(action);};
  window.FireAtlasOnReady=fn=>document.readyState==='loading'?document.addEventListener('DOMContentLoaded',fn):queueMicrotask(fn);
  if(document.body?.dataset.page==='atlas'&&!location.hash)history.replaceState(null,'',location.pathname+location.search+('#atlas-section'));
  if(document.body?.dataset.page==='atlas')C.update({calendar_metric:'combined'},{reason:'incoming-metric'});
  let generic;
  function loadScript(name){return new Promise((resolve,reject)=>{const s=document.createElement('script');s.src=C.url(name);s.onload=resolve;s.onerror=()=>reject(Error('Unable to load '+name));document.head.append(s);});}
  async function combined(){if(!generic)generic=(async()=>{if(document.querySelector('meta[name="fireatlas-static-data"]')){await loadScript('explore-static.js?v=20261101-maps4');return;}await loadScript('study-ui.js?v=20261101-simple');await loadScript('app.js?v=20261101-maps5');})();await generic;}
  function heading(){const c=C.read(),n=document.getElementById('workspace-selection');if(n)n.textContent=`${c.case||c.region||'Custom area'} · ${c.start} → ${c.end} UTC · ${c.bbox}`;}
  FireAtlasOnReady(()=>{
    heading();
    if(document.body.dataset.page==='assistant' && location.hash==='#inspect-selection'){document.body.classList.add('inspection-mode');const back=document.getElementById('return-to-explore');if(back)back.hidden=false;const title=document.querySelector('.mission-heading h1');if(title)title.textContent='Inspect your selection.';}
    if(document.body.dataset.workspace==='research'&&!C.read().errors.length){
      const c=C.read(),label=document.createElement('label');label.dataset.researchIntersection='';label.textContent='Research UTC month intersection ';const select=document.createElement('select');select.setAttribute('aria-label','Research UTC month intersection');const choice=document.createElement('option');choice.value='';choice.textContent='Choose a month';select.append(choice);const date=new Date(c.start+'T00:00:00Z');date.setUTCDate(1);while(date.toISOString().slice(0,7)<=c.end.slice(0,7)){const ym=date.toISOString().slice(0,7);select.add(new Option(ym,ym));date.setUTCMonth(date.getUTCMonth()+1);}select.value=c.analysis_month||(c.start.slice(0,7)===c.end.slice(0,7)?c.start.slice(0,7):'');select.addEventListener('change',()=>{if(!select.value)return;C.update({analysis_month:select.value},{history:'push'});FireAtlasPanels.select(new URLSearchParams(location.search).get('tab')||'comparison');});label.append(select);document.querySelector('.workspace-heading').append(label);
    }

    document.querySelectorAll('[data-atlas-scope]').forEach(b=>b.addEventListener('click',()=>{C.update({calendar_metric:b.dataset.atlasScope==='regional'?'harmonized':'combined'},{history:'push'});if(b.dataset.atlasScope==='study')combined();}));
    if(document.body.dataset.page==='atlas')combined();
    document.querySelectorAll('[data-guide-step]').forEach(b=>b.href=C.link(b.getAttribute('href'),{guide:'authentic',...JSON.parse(b.dataset.guideStep)}));
    document.getElementById('workspace-open-jarvis')?.addEventListener('click',()=>{document.body.classList.toggle('jarvis-open');const n=document.getElementById('workspace-open-jarvis');n.setAttribute('aria-expanded',String(document.body.classList.contains('jarvis-open')));if(document.body.classList.contains('jarvis-open'))document.getElementById('assistant-question')?.focus();});
    document.getElementById('workspace-notebook')?.addEventListener('click',()=>{document.body.classList.toggle('notebook-expanded');document.body.classList.add('jarvis-open');document.getElementById('workspace-open-jarvis')?.setAttribute('aria-expanded','true');});
    document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.body.classList.contains('jarvis-open')){document.body.classList.remove('jarvis-open','notebook-expanded');document.getElementById('workspace-open-jarvis')?.setAttribute('aria-expanded','false');document.getElementById('workspace-open-jarvis')?.focus();}});
  });
  addEventListener('fireatlas:context-changed',heading);addEventListener('fireatlas:context-restore',()=>{heading();if(document.body.dataset.page==='atlas'){window.dispatchEvent(new Event('hashchange'));if(FireAtlasContext.read().calendar_metric==='combined')combined();}});
  addEventListener('fireatlas:harmonized-result',e=>{const r=e.detail.result,m=e.detail.month;if(C.read().calendar_metric==='combined')return;C.update({case:'',region:r.meta.region.id,bbox:r.meta.bbox.join(','),year:Number(m.month.slice(0,4)),month:Number(m.month.slice(5,7)),start:m.month+'-01',end:C.monthEnd(Number(m.month.slice(0,4)),Number(m.month.slice(5,7))),as_of:C.monthEnd(Number(m.month.slice(0,4)),Number(m.month.slice(5,7))),calendar_metric:'harmonized',method_id:r.schema,unit:r.meta.unit,release_id:r.meta.release_id,result_sha256:r.meta.result_sha256},{reason:'result'});});
})();
