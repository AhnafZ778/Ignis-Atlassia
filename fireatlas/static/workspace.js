/* Shared presentation only. Scientific results remain owned by each page controller. */
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
