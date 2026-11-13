/* Mount the existing investigation workspace, preserving its maps and replay. */
FireAtlasPanels.define('comparison-map', ({document,window}) => {
  const $ = id => document.getElementById(id);
  const frame=$('compare-original-map'), year=$('compare-map-year'), month=$('compare-map-month'), study=$('compare-map-study'), status=$('compare-map-status');
  const incoming=window.FireAtlasContext.read(); let selected=null, initial=true, chosen=!!incoming.map_year, cases=[], observer=null;
  ['January','February','March','April','May','June','July','August','September','October','November','December'].forEach((name,i)=>month.add(new Option(name,String(i+1))));
  month.value=String(incoming.map_month||incoming.month||7); if(!month.value) month.value='7';
  async function catalog(){try{let r=await fetch(window.FireAtlasContext.url('/api/replay/catalog'));if(!r.ok)throw Error();cases=(await r.json()).cases||[];}catch{try{const r=await fetch('./data/replay/catalog.json');if(r.ok)cases=(await r.json()).cases||[];}catch{}}
    cases.forEach(c=>study.add(new Option(c.title,c.id)));study.disabled=!selected;
  }
  study.disabled=true;
  void catalog();
  frame.addEventListener('load',()=>{observer?.disconnect();try{const doc=frame.contentDocument;if(!doc?.body)return;const resize=()=>{frame.style.height=Math.max(650,doc.documentElement.scrollHeight)+'px';};observer=new ResizeObserver(resize);observer.observe(doc.body);resize();}catch{}});
  function update(){
    if(!selected)return; const y=Number(year.value),m=Number(month.value);
    if(!Number.isInteger(y)||y<2000||y>2100){status.textContent='Choose a year between 2000 and 2100.';return;}
    const c=cases.find(v=>v.id===study.value),ym=`${y}-${String(m).padStart(2,'0')}`, end=window.FireAtlasContext.monthEnd(y,m),bbox=c?c.bbox:selected.bbox;
    const start=c?c.start:ym+'-01',last=c?c.end:end,day=c?(c.selected_day||c.start):start;
    const link=window.FireAtlasContext.link('investigate.html',{region:c?'norcal':selected.id,bbox:bbox.join(','),year:Number(start.slice(0,4)),month:Number(start.slice(5,7)),start,end:last,as_of:last,day,case:c?c.id:'',source:'joint',series:'joint',metric:'density',split:'true',scope:'daily',geometry:'',analysis_month:''});
    const embed=new URL(link,document.baseURI); embed.searchParams.set('embed','comparison'); frame.src=embed.href; $('compare-open-investigation').href=link;
    status.textContent=c?`${c.title} · ${start} to ${last}`:`${selected.name} · ${ym} · original daily investigation`;
  }
  function select(value){if(selected&&selected.id===value.id&&selected.year===value.year)return;selected=value;study.disabled=false;study.value='';year.value=String(initial&&incoming.map_year?incoming.map_year:!initial&&chosen?year.value:selected.year);initial=false;update();}
  window.addEventListener('fireatlas:comparison-map-selection',e=>select(e.detail));
  window.addEventListener('fireatlas:comparison-map-pending',()=>{selected=null;study.disabled=true;status.textContent='Loading the selected region…';});
  if(window.FireAtlasComparisonMapSelection)select(window.FireAtlasComparisonMapSelection);
  function dateChanged(){study.value='';const y=Number(year.value);if(Number.isInteger(y)&&y>=2000&&y<=2100){chosen=true;window.FireAtlasContext.update({map_year:y,map_month:Number(month.value)},{reason:'comparison-map-date'});}update();}
  study.addEventListener('change',update);year.addEventListener('change',dateChanged);month.addEventListener('change',dateChanged);
});
