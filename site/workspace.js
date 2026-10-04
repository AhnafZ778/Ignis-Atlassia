/* Shared presentation only. Scientific results remain owned by each page controller. */
window.FireAtlasPalette = {
  heat(value) {
    const stops = [[255,242,178],[254,196,79],[252,141,60],[227,74,51],[179,0,0]];
    const scaled = Math.max(0, Math.min(1, Number(value) || 0)) * (stops.length - 1);
    const index = Math.min(stops.length - 2, Math.floor(scaled)), fraction = scaled - index;
    const rgb = stops[index].map((channel, i) => Math.round(channel + (stops[index + 1][i] - channel) * fraction));
    const luminance = channels => channels.map(c => c / 255).map(c => c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4).reduce((sum,c,i) => sum + c * [.2126,.7152,.0722][i], 0);
    const light = luminance(rgb), ink = luminance([0,0,0]);
    return {color:`rgb(${rgb.join(',')})`, dark:(light + .05) / (ink + .05) >= 1.05 / (light + .05)};
  }
};
document.addEventListener('DOMContentLoaded', () => {
  // ui.js handles navigation where present; replay and review use this same behavior.
  if (!document.querySelector('script[src$="ui.js"]')) {
    const toggle = document.querySelector('.nav-toggle'), nav = document.getElementById('site-navigation');
    if (toggle && nav) {
      const close = () => { toggle.setAttribute('aria-expanded','false'); nav.classList.remove('is-open'); };
      toggle.addEventListener('click', () => { const open = toggle.getAttribute('aria-expanded') !== 'true'; toggle.setAttribute('aria-expanded',String(open)); nav.classList.toggle('is-open',open); });
      nav.addEventListener('click', e => { if(e.target.closest('a')) close(); });
      document.addEventListener('click', e => { if(!e.target.closest('.topbar')) close(); });
      document.addEventListener('keydown', e => { if(e.key==='Escape' && nav.classList.contains('is-open')) {close();toggle.focus();} });
    }
  }
  document.querySelectorAll('.table-scroll').forEach(node => { if(!node.hasAttribute('tabindex')) node.tabIndex=0; if(!node.hasAttribute('aria-label')) node.setAttribute('aria-label','Data table; scroll to view all columns'); });
  const links = [...document.querySelectorAll('.section-jump-nav a[href^="#"],.atlas-section-nav a[href^="#"],.replay-page-nav a[href^="#"]')];
  if(links.length && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => { const entry=entries.find(item=>item.isIntersecting); if(!entry)return; links.forEach(link=>{if(link.hash.slice(1)===entry.target.id)link.setAttribute('aria-current','location');else link.removeAttribute('aria-current');}); },{rootMargin:'-90px 0px -65% 0px'});
    links.forEach(link=>{const section=document.getElementById(link.hash.slice(1));if(section)observer.observe(section);});
  }
});

/* Presentation state only: page controllers remain the source of scientific values. */
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-mission-view]').forEach(button => button.addEventListener('click', () => {
    const view=button.dataset.missionView;
    document.querySelector('.mission-grid')?.setAttribute('data-mobile-view',view);
    document.querySelectorAll('[data-mission-view]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));
    const tab=document.querySelector(view==='evidence'?'#mission-tab-evidence':'#mission-tab-ask');
    tab?.click();
    // Leaflet must measure the now-visible map before it paints tiles.
    window.dispatchEvent(new Event('resize'));
  }));
  document.querySelectorAll('.nav-resources').forEach(menu => {
    if(menu.querySelector('a[aria-current="page"]'))menu.dataset.active='true';
    menu.addEventListener('keydown',event=>{if(event.key==='Escape'){menu.open=false;menu.querySelector('summary').focus();}});
  });
  const notice=document.getElementById('mask-handoff-notice');
  if(notice && document.referrer && new URL(document.referrer).origin===location.origin && !new URL(document.referrer).pathname.includes('exposure'))notice.hidden=false;
  // Charts retain legible labels on mobile; the exact values are in their adjacent tables.
  document.querySelectorAll('#overview-chart').forEach(chart=>{
    chart.tabIndex=0;chart.setAttribute('aria-label','Daily sensor comparison chart; scroll horizontally for all UTC dates. Exact values are in the daily table.');
  });
});

document.addEventListener('DOMContentLoaded', () => {
  const display=document.querySelector('.replay-display-settings');
  if(display){const phone=matchMedia('(max-width:760px)');const adjust=()=>{display.open=!phone.matches;};adjust();phone.addEventListener('change',adjust);}
});

document.addEventListener('DOMContentLoaded', () => {
  const editor=document.querySelector('[data-study-editor]');
  if(editor && window.FireAtlasContext){
    let applied=FireAtlasContext.read();
    const title=editor.querySelector('.study-summary-text strong');
    const meta=editor.querySelector('.study-summary-meta');
    const render=()=>{
      const month=new Intl.DateTimeFormat('en',{month:'long',timeZone:'UTC'}).format(new Date(Date.UTC(applied.year,applied.month-1,1)));
      title.textContent=`${month} ${applied.year} · MODIS + VIIRS`;
      meta.textContent=`Through ${applied.as_of} UTC · Area ${Array.isArray(applied.bbox)?applied.bbox.join(', '):applied.bbox}`;
    };
    render();
    editor.addEventListener('input',()=>{meta.textContent='Settings changed. Run the analysis to apply them to the displayed result.';});
    document.addEventListener('fireatlas:study-applied',event=>{applied=event.detail;render();editor.open=false;});
  }
  const scopeButtons=[...document.querySelectorAll('[data-atlas-scope]')];
  if(scopeButtons.length){
    const choose=value=>{
      for(const button of scopeButtons){const active=button.dataset.atlasScope===value;button.setAttribute('aria-pressed',String(active));document.getElementById(button.getAttribute('aria-controls')).hidden=!active;}
      window.dispatchEvent(new Event('resize'));
    };
    const hashScope=()=>choose(/harm|regional/.test(location.hash)?'regional':'study');
    scopeButtons.forEach(button=>button.addEventListener('click',()=>{
      choose(button.dataset.atlasScope);
      history.replaceState(null,'',`${location.pathname}${location.search}#${button.dataset.atlasScope==='regional'?'harmonized-calendar':'atlas-section'}`);
    }));
    addEventListener('hashchange',hashScope);hashScope();
  }
  // Keep the selected task visible within the mobile workflow strip.
  const activeTab=document.querySelector('.workspace-tabs [aria-current="page"]');
  if(activeTab)activeTab.parentElement.scrollLeft=Math.max(0,activeTab.offsetLeft-activeTab.parentElement.offsetLeft-12);
});

// Display tools remain a single row on desktop and an optional disclosure on mobile.
document.addEventListener('DOMContentLoaded',()=>{
 const settings=document.querySelector('.mission-display-settings');
 if(settings){const phone=matchMedia('(max-width:760px)');const apply=()=>{settings.open=!phone.matches;};apply();phone.addEventListener('change',apply);}
});

document.addEventListener('DOMContentLoaded',()=>{
 const display=document.querySelector('.static-map-display');
 if(display){const phone=matchMedia('(max-width:760px)');const apply=()=>{display.open=!phone.matches;};apply();phone.addEventListener('change',apply);}
});
