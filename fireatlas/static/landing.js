/* Page orientation and concise, progressively disclosed explanations. */
document.addEventListener("DOMContentLoaded",()=>{
  const icon='<svg class="ui-icon" aria-hidden="true"><use href="/vendor/lucide-icons.svg#info"></use></svg>';
  const explanations={
    '[data-layer="ndvi"]':'NDVI describes vegetation greenness. Synthetic mode uses generated context; imported mode requests dated NASA imagery when available. It does not establish fuel moisture or fire risk.',
    '[data-layer="landcover"]':'Land cover describes surface categories such as forest or cropland. Check the layer status for its source and date; synthetic context is illustrative.',
    '[data-series="joint"]':'The joint series counts each 1 km cell once per UTC day across the historic MODIS and VIIRS S-NPP records. It requires both source products.',
    '#use-map-aoi':'Uses the current map bounds as your study area for the calendar and evidence. It does not change the global snapshot.',
    '[data-event-layer="reported"]':'NASA EONET curates reported events. Its sample may be dominated by US sources and can include prescribed fires; it is not global satellite coverage.',
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
  let scheduled=false;
  function update(){
    scheduled=false;
    let current=sections[0];
    for(const section of sections)if(section.getBoundingClientRect().top<=170)current=section;
    for(const link of links){const active=link.hash==='#'+current?.id;link.classList.toggle('active',active);if(active)link.setAttribute('aria-current','location');else link.removeAttribute('aria-current');}
  }
  window.addEventListener('scroll',()=>{if(!scheduled){scheduled=true;requestAnimationFrame(update);}},{passive:true});update();
  const resources=document.querySelector('.nav-resources');
  document.addEventListener('click',e=>{if(resources&&!resources.contains(e.target))resources.open=false;});
  resources?.addEventListener('click',e=>{if(e.target.closest('a'))resources.open=false;});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&resources?.open){resources.open=false;resources.querySelector('summary').focus();}});
  // Provide help on touch and keyboard as well as hover through the shared tooltip.
  document.querySelectorAll('.info-help').forEach(node=>{if(!node.innerHTML.trim())node.innerHTML=icon;});
});
