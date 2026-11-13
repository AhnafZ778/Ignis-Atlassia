/* Two-period values come from a separately verified Python publication. */
FireAtlasPanels.define('finding-comparison', ({document,window,fetch}) => {
  const $ = id => document.getElementById(id);
  const number = v => v == null ? '—' : new Intl.NumberFormat('en', {maximumFractionDigits: 2}).format(v);
  const names = {modis:'MODIS observed', viirs:'S-NPP VIIRS observed', adjusted:'Adjusted MODIS estimate'};
  let data = null, token = 0;
  const monthName = m => new Intl.DateTimeFormat('en', {month:'long',timeZone:'UTC'}).format(new Date(Date.UTC(2025,m-1,1)));
  function options(id, values, label, preferred) {
    const select=$(id); select.replaceChildren(...values.map(v => new Option(label(v), String(v))));
    if(values.map(String).includes(String(preferred))) select.value=String(preferred);
  }
  function matching(){return data?.pairs.filter(p=>p.protocol==='forward'&&p.month===Number($('finding-month').value))||[];}
  function choices(preferredA, preferredB){
    const pairs=matching(), years=[...new Set(pairs.map(p=>p.years[0]))].sort();
    options('finding-year-a',years,v=>v,preferredA);
    const end=[...new Set(pairs.filter(p=>String(p.years[0])===$('finding-year-a').value).map(p=>p.years[1]))].sort();
    options('finding-year-b',end,v=>v,preferredB); render();
  }
  function mapLink(date){
    const [year,month]=date.split('-').map(Number), last=new Date(Date.UTC(year,month,0)).getUTCDate();
    const start=date+'-01',end=date+'-'+String(last).padStart(2,'0');
    const query=new URLSearchParams({region:data.region.id,bbox:data.region.bbox.join(','),year:String(year),month:String(month),start,end,as_of:end,day:start,series:'joint',source:'joint',scope:'daily',split:'true'});
    return './investigate.html?'+query.toString();
  }
  function render(){
    const row=matching().find(p=>String(p.years[0])===$('finding-year-a').value&&String(p.years[1])===$('finding-year-b').value);
    if(!row){$('finding-content').hidden=true;$('finding-status').textContent='No comparison is available for these periods.';return;}
    $('finding-content').hidden=false;
    $('finding-status').textContent=row.direction_differs?'The selected series show different directions of change.':'The selected series show the same direction of change.';
    const svgNS='http://www.w3.org/2000/svg',svg=document.createElementNS(svgNS,'svg');svg.setAttribute('viewBox','0 0 600 200');svg.setAttribute('role','img');svg.setAttribute('aria-label','Monthly activity for '+row.dates.join(' and ')+'; values listed below.');
    const all=Object.values(row.series).flatMap(v=>[v.first,v.second]).filter(v=>v!=null),maximum=Math.max(1,...all),x=[85,525],y=v=>160-125*v/maximum;
    const make=(tag,attrs)=>{const el=document.createElementNS(svgNS,tag);for(const [k,v]of Object.entries(attrs))el.setAttribute(k,String(v));svg.append(el);return el;};
    make('line',{x1:85,y1:160,x2:525,y2:160,stroke:'#b7c8d5'});for(let i=0;i<2;i++){const label=make('text',{x:x[i],y:185,'text-anchor':'middle',fill:'#536d82','font-size':13});label.textContent=row.dates[i];}
    const top=make('text',{x:6,y:40,fill:'#536d82','font-size':12});top.textContent=number(maximum);const zero=make('text',{x:55,y:164,fill:'#536d82','font-size':12});zero.textContent='0';
    for(const [key,color] of [['modis','#c5792d'],['viirs','#087e88'],['adjusted','#5e5acb']]){const item=row.series[key];if(item.first==null||item.second==null)continue;make('line',{x1:x[0],y1:y(item.first),x2:x[1],y2:y(item.second),stroke:color,'stroke-width':3});for(const [i,value]of [item.first,item.second].entries())make('circle',{cx:x[i],cy:y(value),r:5,fill:color,stroke:'white','stroke-width':1});}
    $('finding-chart').replaceChildren(svg);
    const cards=$('finding-cards');cards.replaceChildren();
    const table=document.createElement('table'),caption=document.createElement('caption');caption.textContent='Monthly occupied 1 km centroid cell-days';table.append(caption);
    const head=document.createElement('thead'),tr=document.createElement('tr');['Series',row.dates[0],row.dates[1],'Change'].forEach(v=>{const th=document.createElement('th');th.scope='col';th.textContent=v;tr.append(th)});head.append(tr);table.append(head);const body=document.createElement('tbody');
    Object.entries(row.series).sort(([a],[b])=>['modis','viirs','adjusted'].indexOf(a)-['modis','viirs','adjusted'].indexOf(b)).forEach(([key,item])=>{
      const card=document.createElement('article');card.className='finding-card finding-'+key;
      const title=document.createElement('span');title.className='finding-series';title.textContent=names[key];
      const values=document.createElement('strong');values.textContent=number(item.first)+' → '+number(item.second);
      const change=document.createElement('span');change.className='finding-change';change.textContent=item.direction==='unavailable'?'Unavailable':item.direction+' · '+(item.difference>0?'+':'')+number(item.difference)+(item.percent==null?'':' ('+(item.percent>0?'+':'')+number(item.percent)+'%)');
      card.append(title,values,change);cards.append(card);
      const line=document.createElement('tr');[names[key],item.first == null ? '—' : String(item.first),item.second == null ? '—' : String(item.second),item.difference == null ? '—' : String(item.difference)].forEach(v=>{const td=document.createElement('td');td.textContent=v;line.append(td)});body.append(line);
    });table.append(body);$('finding-table').replaceChildren(table);
    $('finding-method').textContent='Region: '+data.region.name+' · bounds '+data.region.bbox.join(', ')+' · products '+row.versions.join(' / ')+' · models '+row.models.join(' / ')+' · source result '+data.parent_result_sha256+'. Each year’s estimate uses its own earlier-year training.';
    $('finding-map-a').href=mapLink(row.dates[0]);$('finding-map-a').textContent='Inspect '+row.dates[0]+' observations ↗';
    $('finding-map-b').href=mapLink(row.dates[1]);$('finding-map-b').textContent='Inspect '+row.dates[1]+' observations ↗';
    $('finding-explore-a').href=mapLink(row.dates[0]).replace('./investigate.html?','./atlas.html?');$('finding-explore-a').textContent='Explore '+row.dates[0]+' data ↗';
    $('finding-explore-b').href=mapLink(row.dates[1]).replace('./investigate.html?','./atlas.html?');$('finding-explore-b').textContent='Explore '+row.dates[1]+' data ↗';
  }
  async function load(){
    const seq=++token,region=$('finding-region').value;data=null;$('finding-content').hidden=true;$('finding-status').textContent='Loading the comparison…';
    try {const base='./data/finding-comparisons/v1/',name=encodeURIComponent(region)+'.json';const [response,receipt]=await Promise.all([fetch(base+name),fetch(base+'manifest.json')]);if(!response.ok||!receipt.ok)throw Error('Comparison data are unavailable.');const manifest=await receipt.json(),bytes=await response.arrayBuffer();if(!window.crypto?.subtle)throw Error('A secure browser context is required to load this comparison.');const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(v=>v.toString(16).padStart(2,'0')).join('');if(manifest.schema!=='fireatlas-finding-publication-v1'||manifest.files?.[name]?.sha256!==hash||manifest.files[name].bytes!==bytes.byteLength)throw Error('Comparison data failed the publication check.');const result=JSON.parse(new TextDecoder().decode(bytes));if(seq!==token)return;if(result.schema!=='fireatlas-finding-comparisons-v1'||result.region.id!==region)throw Error('Comparison data do not match this region.');data=result;
      const forward=data.pairs.filter(p=>p.protocol==='forward');if(!forward.length)throw Error('No two supported forward-evaluation years are available.');
      const example=forward.find(p=>p.direction_differs)||forward[0], months=[...new Set(forward.map(p=>p.month))].sort((a,b)=>a-b);
      options('finding-month',months,monthName,example.month);choices(example.years[0],example.years[1]);
    } catch(e){if(seq!==token)return;$('finding-status').textContent=e.message;}
  }
  $('finding-region').value=$('compare-region').value;
  $('finding-region').addEventListener('change',()=>{const main=$('compare-region');if(main.value!==$('finding-region').value){main.value=$('finding-region').value;main.dispatchEvent(new Event('change',{bubbles:true}));}else load();});
  $('compare-region').addEventListener('change',()=>{if($('finding-region').value!==$('compare-region').value)$('finding-region').value=$('compare-region').value;load();});
  $('finding-month').addEventListener('change',()=>choices($('finding-year-a').value,$('finding-year-b').value));
  $('finding-year-a').addEventListener('change',()=>choices($('finding-year-a').value,$('finding-year-b').value));
  $('finding-year-b').addEventListener('change',render);
  window.FireAtlasFindingCapture={active:false,source(){
    const pair=matching().find(p=>String(p.years[0])===$('finding-year-a').value&&String(p.years[1])===$('finding-year-b').value);
    if(!pair)throw Error('Select an available comparison.');
    const year=pair.years[1],month=pair.month,last=new Date(Date.UTC(year,month,0)).getUTCDate();
    const start=pair.dates[1]+'-01',end=pair.dates[1]+'-'+String(last).padStart(2,'0'),focus=$('finding-series').value;
    const study={year,month,bbox:data.region.bbox,region:data.region.id,start,end,as_of:end,day:start,series:'joint',source:'joint',metric:'density'};
    const args={finding_month:month,finding_first_year:pair.years[0],finding_second_year:year,expected_finding_sha256:data.result_sha256,finding_series:focus};
    const view={kind:'chart',operation:'finding_comparison',source:'joint',metric:'density',caption:'How did activity change? '+data.region.name+' · '+pair.dates.join(' → ')+' · '+names[focus]+' · '+data.unit,arguments:args};
    return {study,view,refs:[],release:'',adapter:{capture:async()=>{const c=document.createElement('canvas');c.width=1100;c.height=500;const g=c.getContext('2d');g.fillStyle='#fff';g.fillRect(0,0,c.width,c.height);g.fillStyle='#193c55';g.font='bold 25px sans-serif';g.fillText('How did observed activity change?',30,45);g.font='19px sans-serif';g.fillText(data.region.name+' · '+pair.dates.join(' → '),30,80);const maximum=Math.max(1,...Object.values(pair.series).flatMap(v=>[v.first,v.second]).filter(v=>v!=null));const X=[180,910],Y=v=>320-180*v/maximum;g.strokeStyle='#a8bac7';g.lineWidth=1;g.beginPath();g.moveTo(X[0],320);g.lineTo(X[1],320);g.stroke();g.font='15px sans-serif';g.fillText(pair.dates[0],X[0]-25,346);g.fillText(pair.dates[1],X[1]-25,346);for(const [key,color] of [['modis','#c5792d'],['viirs','#087e88'],['adjusted','#5e5acb']]){const v=pair.series[key];if(v.first==null||v.second==null)continue;g.globalAlpha=key===focus?1:.3;g.strokeStyle=color;g.fillStyle=color;g.lineWidth=key===focus?6:2;g.beginPath();g.moveTo(X[0],Y(v.first));g.lineTo(X[1],Y(v.second));g.stroke();for(const [i,val] of [v.first,v.second].entries()){g.beginPath();g.arc(X[i],Y(val),key===focus?7:4,0,2*Math.PI);g.fill();}}g.globalAlpha=1;g.fillStyle='#193c55';g.font='bold 19px sans-serif';const selected=pair.series[focus];g.fillText(names[focus]+' · '+number(selected.first)+' → '+number(selected.second)+' · '+selected.direction,30,397);g.font='15px sans-serif';g.fillText(data.unit+' · source '+data.parent_result_sha256.slice(0,16),30,450);return {mime:'image/png',data:c.toDataURL('image/png').split(',')[1],caption:view.caption,regions:[]};}}};
  }};
  $('finding-save').addEventListener('click',async()=>{
    if(document.querySelector('meta[name="fireatlas-static-data"]')){$('finding-status').textContent='Open the local Studio service to save investigations.';return;}
    if(!window.FireAtlasOrchestration){$('finding-status').textContent='Studio is not available. Open the local service to save this comparison.';return;}
    $('finding-save').disabled=true;window.FireAtlasFindingCapture.active=true;
    try{await window.FireAtlasOrchestration.packageView();const picker=document.querySelector('.jarvis-destination:not([hidden])');if(picker){$('finding-content').append(picker);picker.querySelector('select')?.focus();$('finding-status').textContent='Choose where to save this comparison.';}else $('finding-status').textContent='See the Studio save controls for progress.';}finally{window.FireAtlasFindingCapture.active=false;$('finding-save').disabled=false;}
  });
  load();
});
