/* Page orientation and concise, progressively disclosed explanations. */
document.addEventListener("DOMContentLoaded",()=>{
  const icon='<svg class="ui-icon" aria-hidden="true"><use href="/vendor/lucide-icons.svg#info"></use></svg>';
  const explanations={
    '[data-layer="ndvi"]':'NDVI describes vegetation greenness. The map requests dated NASA imagery when available. It does not establish fuel moisture or fire risk.',
    '[data-layer="landcover"]':'Land cover describes surface categories such as forest or cropland. Check the layer status for its source and date.',
    '[data-series="joint"]':'The joint series counts each 1 km cell once per UTC day across the historic MODIS and VIIRS S-NPP records. It requires both source products.',
    '#use-map-aoi':'Uses the current map bounds as your study area for the calendar and evidence. It does not change the global snapshot.',
    '#export-observations':'Downloads the original observations for this selection. Availability follows the source exports that have been imported.',
    '#download-study':'Downloads a ZIP containing the selected study, calendar, source ledger and checksums. Context map imagery is not included.'
  };
  for(const [selector,text] of Object.entries(explanations))document.querySelectorAll(selector).forEach(node=>node.dataset.tooltip=text);
  document.querySelectorAll('.legend>span').forEach(node=>{
    const text=node.textContent.trim();
    node.tabIndex=0;
    node.dataset.tooltip=text.includes('Not loaded')?'The complete source export has not been loaded. This is not evidence of zero burning.':text.includes('No detections')?'No detections occur in the loaded export for this date. Satellite pass and cloud coverage can still be unknown.':'A 1 km grid cell with a detection on that UTC day. It does not represent an individual wildfire.';
  });
  const links=[...document.querySelectorAll('.journey-nav a[href^="#"],#site-navigation>a[href^="#"]')];
  const sections=[...new Set(links.map(a=>document.querySelector(a.hash)).filter(Boolean))];
  // Move the entire Earth host so its embedded observation overlay stays aligned.
  const depthMedia=matchMedia('(min-width: 951px) and (prefers-reduced-motion: no-preference)');
  const depthLayers=[
    ...[...document.querySelectorAll('.globe-hero .hero-art')].map(node=>({node,anchor:node.closest('.globe-hero'),speed:.12,limit:72,hero:true})),
    ...[...document.querySelectorAll('.lab-art,.tour-orbit')].map(node=>({node,anchor:node.parentElement,speed:.045,limit:18,hero:false}))
  ];
  function updateDepth(){
    const height=window.innerHeight;
    for(const layer of depthLayers){
      if(!depthMedia.matches){layer.node.style.removeProperty('translate');continue;}
      const rect=layer.anchor.getBoundingClientRect();
      if(rect.bottom<0 || rect.top>height) continue;
      const distance=layer.hero?Math.max(0,-rect.top):height/2-(rect.top+rect.height/2);
      const offset=Math.max(-layer.limit,Math.min(layer.limit,distance*layer.speed));
      layer.node.style.translate=`0 ${offset.toFixed(2)}px`;
    }
  }
  let scheduled=false;
  function update(){
    scheduled=false;
    updateDepth();
    let current=sections[0];
    for(const section of sections)if(section.getBoundingClientRect().top<=170)current=section;
    for(const link of links){const active=link.hash==='#'+current?.id;link.classList.toggle('active',active);if(active)link.setAttribute('aria-current','location');else link.removeAttribute('aria-current');}
  }
  const schedule=()=>{if(!scheduled){scheduled=true;requestAnimationFrame(update);}};
  window.addEventListener('scroll',schedule,{passive:true});
  window.addEventListener('resize',schedule,{passive:true});
  depthMedia.addEventListener('change',schedule);
  update();
  const resources=document.querySelector('.nav-resources');
  document.addEventListener('click',e=>{if(resources&&!resources.contains(e.target))resources.open=false;});
  resources?.addEventListener('click',e=>{if(e.target.closest('a'))resources.open=false;});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&resources?.open){resources.open=false;resources.querySelector('summary').focus();}});
  // Provide help on touch and keyboard as well as hover through the shared tooltip.
  document.querySelectorAll('.info-help').forEach(node=>{if(!node.innerHTML.trim())node.innerHTML=icon;});
});
