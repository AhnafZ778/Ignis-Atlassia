/* Mounted by analytical-panels.js; original scientific controller retained. */
FireAtlasPanels.define('validity', ({document,window,fetch,setTimeout,clearTimeout}) => {
/* Visual account of two authentic historical FIRMS cases. No inferred coverage. */
document.addEventListener('DOMContentLoaded',()=>{
  const svg=document.querySelector('#validity-graphic');
  if(!svg)return;
  const captureFrame=new URLSearchParams(location.search).get('frame')==='1';
  if(captureFrame)document.body.classList.add('validity-frame');
  const NS='http://www.w3.org/2000/svg';
  const $=selector=>document.querySelector(selector);
  const sourceNames={MODIS_SP:'MODIS',VIIRS_SNPP_SP:'VIIRS S-NPP'};
  const sourceColors={MODIS_SP:'#f0b568',VIIRS_SNPP_SP:'#70cddd'};
  const scenes={
    sensors:['01 / TWO SENSORS','Different views of heat.','MODIS and VIIRS report original pixels at different native sizes. The daily calendar retains their identities.'],
    coverage:['02 / OBSERVATION GAPS','A blank is not a clear pass.','The FIRMS archive records detections. Clear, cloudy and missed satellite opportunities require separate fire-mask data.'],
    grid:['03 / DAILY GRID','Count a place once per day.','Detection centroids enter the same 1 km grid. Repeated hits in one UTC cell and day become one calendar cell-day.'],
    timeline:['04 / HISTORICAL TIMELINE','Follow the reported event.','The map plots actual dated NASA detections. The white diamond is a separate official incident report.'],
    proof:['05 / TRACE THE EVIDENCE','Check the misses too.','Source rows reproduce the calendar. A fixed CAL FIRE incident cohort shows both nearby detections and cases with no nearby point.']
  };
  /* Incident-context media is intentionally separate from NASA observations. */
  const incidentMedia={
    'park-2024':{
      eyebrow:'PARK FIRE · 24 JUL 2024',title:'Fireline activity and command context',
      description:'An AlertCalifornia camera records fire activity while the official briefing image shows the incident command view.',
      images:[
        {src:'./incident-media/park-fire-flames.jpg',alt:'AlertCalifornia camera view of active fire during the Park Fire on July 24, 2024.',label:'Active fire · 24 Jul 2024'},
        {src:'./incident-media/park-fire-02.jpg',alt:'AlertCalifornia camera view showing smoke over the Park Fire landscape on July 24, 2024.',label:'Smoke and landscape · 24 Jul 2024'},
        {src:'./incident-media/park-fire.jpg',alt:'Fire officials and responders review a Park Fire briefing map during a command briefing.',label:'Incident briefing · official context'},
        {src:'./incident-media/park-fire-04.jpg',alt:'AlertCalifornia camera view of flames during the Park Fire on July 24, 2024.',label:'Fireline frame · 24 Jul 2024'},
        {src:'./incident-media/park-fire-05.jpg',alt:'AlertCalifornia camera view of smoke and aircraft activity during the Park Fire on July 24, 2024.',label:'Smoke column · 24 Jul 2024'},
        {src:'./incident-media/park-fire-06.jpg',alt:'AlertCalifornia camera view of smoke over homes and grassland during the Park Fire on July 24, 2024.',label:'Smoke over landscape · 24 Jul 2024'}
      ],
      source:'ALERTCalifornia / CAL FIRE Flickr album',
      sourceUrl:'https://www.flickr.com/photos/calfire/albums/72177720319119550/',
      note:'Incident context only · these photographs are not NASA detections, perimeters, or model inputs.'
    },
    'grove-2025':{
      eyebrow:'GROVE FIRE · 04 JUL 2025',title:'CAL FIRE incident record',
      description:'The official record provides the dated start, location, acreage, and containment status used beside the NASA detections.',
      source:'CAL FIRE · Grove Fire incident page',
      sourceUrl:'https://www.fire.ca.gov/incidents/2025/7/4/grove-fire',
      note:'No incident photograph is published on the CAL FIRE record, so no unrelated image is substituted here.'
    }
  };
  const viewParams=new URLSearchParams(location.search);
  const liteEarth=viewParams.get('lite')==='1';
  let caseId=['park-2024','grove-2025'].includes(viewParams.get('case'))?viewParams.get('case'):'park-2024',scene=captureFrame?'timeline':'sensors',selectedDate=null,report=null,request=0,maskSource='all';
  const cache=new Map();
  const mobile=()=>matchMedia('(max-width: 760px)').matches;
  const staticDataRoot=(document.querySelector('meta[name="fireatlas-static-evidence"]')||document.querySelector('meta[name="fireatlas-static-data"]'))?.content;

  function el(tag,attrs={},parent=svg,content){
    const item=document.createElementNS(NS,tag);
    for(const [key,value] of Object.entries(attrs))item.setAttribute(key,String(value));
    if(content!==undefined)item.textContent=content;
    parent.append(item);
    return item;
  }
  function line(x1,y1,x2,y2,color='#496a73',width=1,dash){return el('line',{x1,y1,x2,y2,stroke:color,'stroke-width':width,...(dash?{'stroke-dasharray':dash}:{})});}
  function label(x,y,content,options={}){return el('text',{x,y,fill:options.fill||'#b2cbd3','font-size':options.size||16,'font-family':'DM Sans, sans-serif','font-weight':options.weight||500,'text-anchor':options.anchor||'start','letter-spacing':options.spacing||0},svg,content);}
  function rounded(x,y,w,h,fill,stroke='#4c6a74',radius=12){return el('rect',{x,y,width:w,height:h,rx:radius,fill,stroke,'stroke-width':1.5});}
  function base(title,description){
    svg.replaceChildren();
    svg.setAttribute('viewBox',mobile()?'0 0 390 360':'0 0 960 540');
    el('title',{id:'validity-graphic-title'},svg,title);
    el('desc',{id:'validity-graphic-desc'},svg,description);
    const defs=el('defs');
    const pat=el('pattern',{id:'validity-hatch',patternUnits:'userSpaceOnUse',width:12,height:12,patternTransform:'rotate(42)'},defs);
    el('rect',{width:12,height:12,fill:'#112734'},pat);
    el('rect',{width:3,height:12,fill:'#41616b'},pat);
    const glow=el('radialGradient',{id:'validity-glow',cx:'50%',cy:'50%',r:'65%'},defs);
    const cloud=el('pattern',{id:'validity-cloud',patternUnits:'userSpaceOnUse',width:8,height:8},defs);
    el('rect',{width:8,height:8,fill:'#38505a'},cloud);
    el('path',{d:'M0 0L8 8M8 0L0 8',stroke:'#acc3cf','stroke-width':1},cloud);
    const unknown=el('pattern',{id:'validity-unknown',patternUnits:'userSpaceOnUse',width:10,height:10},defs);
    el('rect',{width:10,height:10,fill:'#303943'},unknown);
    el('path',{d:'M0 0L10 10M10 0L0 10',stroke:'#68767d','stroke-width':1},unknown);
    el('stop',{offset:'0%','stop-color':'#21414a'},glow);el('stop',{offset:'100%','stop-color':'#081822'},glow);
    el('rect',{width:mobile()?390:960,height:mobile()?360:540,fill:'url(#validity-glow)'});
  }
  function selectedDay(){return report?.days.find(day=>day.date_utc===report.selected_date_utc);}
  function format(number){return Number(number||0).toLocaleString('en-US');}
  function footer(text){if(!mobile())label(45,501,text,{size:12,fill:'#819eaa',spacing:1.2});}

  function drawSensors(){
    base('Scale comparison of MODIS and VIIRS active-fire pixels','One MODIS one-kilometre pixel is compared with smaller VIIRS 375-metre pixels at the same drawing scale.');
    const day=selectedDay();
    if(mobile()){
      label(21,33,'NATIVE PIXEL WIDTH · SAME SCALE',{size:13,fill:'#f4c39a',weight:700});line(20,45,370,45);
      rounded(20,64,166,244,'#0d2430','#49646c',10);rounded(204,64,166,244,'#0d2430','#49646c',10);
      label(35,91,'MODIS',{size:16,fill:'#f0b568',weight:700});label(219,91,'VIIRS S-NPP',{size:16,fill:'#70cddd',weight:700});
      rounded(49,122,105,105,'#dc8c6150','#f0b568',3);
      for(let x=0;x<3;x++)for(let y=0;y<3;y++)rounded(219+x*41,123+y*41,39.375,39.375,'#70cddd50','#70cddd',2);
      label(35,255,'1 km',{size:17,fill:'#f8c6a3',weight:700});label(219,255,'375 m',{size:17,fill:'#70cddd',weight:700});
      label(35,286,`${format(day?.raw_pixels.MODIS_SP)} pixels`,{size:14,fill:'#dce9e8'});label(219,286,`${format(day?.raw_pixels.VIIRS_SNPP_SP)} pixels`,{size:14,fill:'#dce9e8'});
      label(20,340,'ACTUAL COUNTS · SELECTED UTC DAY',{size:12,fill:'#93afb9',weight:700});return;
    }
    label(46,80,'SAME LANDSCAPE · DIFFERENT PIXEL SCALE',{size:13,fill:'#f4c39a',weight:700,spacing:1.7});
    line(46,102,914,102);
    rounded(56,144,400,280,'#0d2430','#49646c',15);rounded(504,144,400,280,'#0d2430','#49646c',15);
    label(88,184,'MODIS',{size:19,fill:'#f0b568',weight:700});
    label(536,184,'VIIRS S-NPP',{size:19,fill:'#70cddd',weight:700});
    rounded(142,217,160,160,'#dc8c6150','#f0b568',4);
    for(let x=0;x<3;x++)for(let y=0;y<3;y++)rounded(571+x*64,218+y*64,60,60,'#70cddd50','#70cddd',3);
    label(341,304,'1 km',{size:25,fill:'#f8c6a3',weight:700});
    label(797,304,'375 m',{size:25,fill:'#70cddd',weight:700});
    label(88,399,`${format(day?.raw_pixels.MODIS_SP)} source pixels this day`,{size:16,fill:'#dce9e8'});
    label(536,399,`${format(day?.raw_pixels.VIIRS_SNPP_SP)} source pixels this day`,{size:16,fill:'#dce9e8'});
    footer('PIXEL WIDTHS ARE DRAWN AT THE SAME SCALE · COUNTS ARE FROM THE SELECTED UTC DAY');
  }
  function mapPosition(lon,lat){const [west,south,east,north]=report.bbox;return mobile()
    ?[36+(lon-west)/(east-west)*318,49+(north-lat)/(north-south)*264]
    :[100+(lon-west)/(east-west)*760,74+(north-lat)/(north-south)*390];}
  function mapFrame(unknown){
    if(mobile()){
      rounded(35,48,320,266,unknown?'url(#validity-unknown)':'#102a34','#54727c',7);
      for(let i=1;i<5;i++){const x=35+i*320/5,y=48+i*266/5;line(x,49,x,313,'#66838b55',1,'3 6');line(36,y,354,y,'#66838b55',1,'3 6');}
      label(35,35,`${report.bbox[0].toFixed(2)}° W`,{size:12,fill:'#a3bfca'});
      label(355,35,`${report.bbox[2].toFixed(2)}° W`,{size:12,fill:'#a3bfca',anchor:'end'});
      return;
    }
    rounded(94,68,772,401,unknown?'url(#validity-unknown)':'#102a34','#54727c',10);
    for(let i=1;i<5;i++){const x=94+i*772/5,y=68+i*401/5;line(x,69,x,468,'#66838b55',1,'4 7');line(95,y,865,y,'#66838b55',1,'4 7');}
    const [west,south,east,north]=report.bbox;
    label(98,52,`${west.toFixed(2)}° W`,{size:12,fill:'#85a9b5'});
    label(864,52,`${east.toFixed(2)}° W`,{size:12,fill:'#85a9b5',anchor:'end'});
    label(46,87,`${north.toFixed(2)}° N`,{size:11,fill:'#85a9b5'});
    label(46,466,`${south.toFixed(2)}° N`,{size:11,fill:'#85a9b5'});
  }
  function drawMap(unknown){
    base(unknown?'Detection map with unknown satellite pass and cloud coverage':'Map of dated NASA FIRMS detections and separate CAL FIRE start location',unknown?'Hatching denotes unknown observation opportunity; colored marks are authentic FIRMS detections.':'The colored circles are NASA detected grid cells; the white diamond marks the officially reported incident start.');
    mapFrame(unknown);
    if(unknown&&report.native_masks?.processed_fire_granules){
      for(const cell of report.native_masks.selected_day_cells){
        if(maskSource!=='all'&&cell.source_id!==maskSource)continue;
        const [x,y]=mapPosition(cell.lon,cell.lat);
        const fill=cell.state==='detected'?'#ef9f71':cell.state==='observed-without-detection'?'#77c8c0':cell.state==='cloud-obscured'?'url(#validity-cloud)':'url(#validity-unknown)';
        const mark=el('rect',{x:x-3,y:y-3,width:6,height:6,fill,stroke:'#93acb5','stroke-width':.35,tabindex:'0',role:'button','aria-label':`${sourceNames[cell.source_id]} native centroid samples: ${cell.state}. Inspect granule references.`});
        const inspect=()=>showMaskCell(cell);
        mark.addEventListener('click',inspect);
        mark.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();inspect();}});
      }
    }
    const cells=report.selected_day_cells;
    for(const cell of cells){
      const [x,y]=mapPosition(cell.lon,cell.lat);
      const both=cell.sources.length===2;
      const circle=el('circle',{cx:x,cy:y,r:both?(mobile()?3.5:5):(mobile()?2.5:3.8),fill:both?'#f9e4c4':sourceColors[cell.sources[0]],stroke:both?'#ef8557':'#13313a','stroke-width':both?1.4:.6,opacity:.82,tabindex:'0',role:'button','aria-label':`${cell.raw_pixels} satellite pixels in one kilometre grid cell. Inspect evidence.`});
      circle.addEventListener('click',()=>showCell(cell));
      circle.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();showCell(cell);}});
    }
    const official=report.official_reference,[ox,oy]=mapPosition(official.lon,official.lat);
    const diamond=mobile()?7:10;
    el('path',{d:`M${ox} ${oy-diamond}L${ox+diamond} ${oy}L${ox} ${oy+diamond}L${ox-diamond} ${oy}Z`,fill:'#f7fbf6',stroke:'#c7724f','stroke-width':mobile()?2:3});
    if(!mobile()){
      if(ox<630)label(ox+17,oy-16,'OFFICIAL REPORTED START',{size:13,fill:'#fff',weight:700});
      else label(ox-17,oy-16,'OFFICIAL REPORTED START',{size:13,fill:'#fff',weight:700,anchor:'end'});
    }
    if(!cells.length){label(mobile()?195:480,mobile()?177:275,mobile()?'No detections in this export':'No FIRMS detections in this export on this UTC day',{size:mobile()?17:21,fill:'#e6f1ed',weight:600,anchor:'middle'});}
    if(!unknown&&selectedDay()?.documented_source_notice){
      if(mobile()){
        rounded(46,259,299,43,'#381e20ed','#e3a57d',7);
        label(195,286,'NASA: S-NPP SOURCE GAP',{size:14,fill:'#ffe2c9',weight:700,anchor:'middle'});
      }else{
        rounded(235,393,490,54,'#381e20ed','#e3a57d',8);
        label(480,426,'NASA: S-NPP PROCESSING GAP',{size:15,fill:'#ffe2c9',weight:700,anchor:'middle',spacing:1.2});
      }
    }
    if(unknown){
      if(mobile()){
        rounded(46,259,299,43,'#081a22e8','#819da6',7);
        label(195,286,'PASS + CLOUD: UNKNOWN',{size:14,fill:'#f2d4bb',weight:700,anchor:'middle'});
      }else{
        rounded(250,393,460,54,'#081a22e8','#819da6',8);
        label(480,426,report.native_masks?.processed_fire_granules?'NATIVE CENTROID SAMPLES · REVIEW PENDING':'PASS + CLOUD EVIDENCE NOT LOADED',{size:15,fill:'#f2d4bb',weight:700,anchor:'middle',spacing:1.5});
      }
      footer('DETECTIONS ARE REAL · HATCHED BACKGROUND IS UNKNOWN, NOT CLOUD OR CLEAR LAND');
    }else footer('CIRCLES: NASA THERMAL DETECTIONS · DIAMOND: SEPARATE CAL FIRE INCIDENT REPORT');
    if(mobile())label(20,342,'● NASA DETECTION     ◇ OFFICIAL REPORT',{size:12,fill:'#bfd5d8',weight:700});
  }
  function drawGrid(){
    base('Schematic of detected pixel grouping into daily one-kilometre cells','The graphic illustrates the method; figures shown beside it are computed from the selected real day.');
    const day=selectedDay();
    if(mobile()){
      label(20,34,'ACTUAL COUNTS · SELECTED UTC DAY',{size:13,fill:'#f4c39a',weight:700});
      const rows=[['MODIS',day?.raw_pixels.MODIS_SP,'#f0b568'],['VIIRS S-NPP',day?.raw_pixels.VIIRS_SNPP_SP,'#70cddd'],['JOINT 1 KM CELLS',day?.joint_detected_cell_days,'#ffd1ab']];
      rows.forEach(([name,value,color],i)=>{const y=61+i*87;rounded(20,y,350,75,i===2?'#34332e':'#19323c',i===2?'#e5a479':'#5e7b83',9);label(37,y+30,name,{size:15,fill:color,weight:700});label(350,y+54,format(value),{size:37,fill:'#fff',weight:700,anchor:'end'});});
      label(20,342,`${format(day?.co_detected_cell_days)} CELLS DETECTED BY BOTH SOURCES`,{size:12,fill:'#afc7ce',weight:700});return;
    }
    label(42,77,'ACTUAL SELECTED-DAY COUNTS',{size:13,fill:'#f4c39a',weight:700,spacing:1.8});line(42,96,918,96);
    rounded(54,161,230,220,'#19323c','#5e7b83',12);rounded(365,161,230,220,'#19323c','#5e7b83',12);rounded(676,161,230,220,'#263137','#df9a71',12);
    label(169,215,'MODIS',{size:17,fill:'#f0b568',weight:700,anchor:'middle'});label(169,299,format(day?.raw_pixels.MODIS_SP),{size:56,fill:'#fff',weight:700,anchor:'middle'});label(169,339,'RAW PIXELS',{size:13,fill:'#9eb8c3',weight:700,anchor:'middle'});
    label(480,215,'VIIRS S-NPP',{size:17,fill:'#70cddd',weight:700,anchor:'middle'});label(480,299,format(day?.raw_pixels.VIIRS_SNPP_SP),{size:56,fill:'#fff',weight:700,anchor:'middle'});label(480,339,'RAW PIXELS',{size:13,fill:'#9eb8c3',weight:700,anchor:'middle'});
    label(791,215,'DAILY UNION',{size:17,fill:'#ffbd92',weight:700,anchor:'middle'});label(791,299,format(day?.joint_detected_cell_days),{size:56,fill:'#ffca9d',weight:700,anchor:'middle'});label(791,339,'DETECTED CELL-DAYS',{size:13,fill:'#cfb7a8',weight:700,anchor:'middle'});
    label(325,280,'+',{size:39,fill:'#a6c4cc',anchor:'middle'});label(636,280,'→',{size:41,fill:'#f6be9b',anchor:'middle'});
    label(480,426,`${format(day?.co_detected_cell_days)} cells have detections from both sources this day`,{size:18,fill:'#d3e5e7',anchor:'middle'});
    footer('RAW PIXELS REMAIN INSPECTABLE · ONE CELL CONTRIBUTES ONCE PER UTC DAY');
  }
  function drawProof(){
    const cross=report.independent_incidents;
    base('Provenance path and complete additional-incident association check','The path identifies supported checks. A row of dots shows all additional incidents, including those with no nearby FIRMS point. Pass and cloud masks remain unknown.');
    if(mobile()){
      label(20,30,'EVIDENCE PATH',{size:13,fill:'#f4c39a',weight:700});
      const entries=['NASA FIRMS · ORIGINAL ROWS','SHA-256 · FILE HASHES','1 KM GRID · DAILY COUNTS','CAL FIRE · REPORTED START','STUDY ZIP · RECOUNT'];
      entries.forEach((name,i)=>{const y=48+i*53;rounded(32,y,325,43,i===2?'#34332e':'#17313a',i===2?'#e5a479':'#67848d',7);label(48,y+28,name,{size:14,fill:'#f1f6f5',weight:700});if(i<4)line(195,y+44,195,y+52,'#e2a77e',2);});
      rounded(24,318,342,32,'#18232b','#7d8f93',5);label(195,340,'PASS / CLOUD MASKS: UNKNOWN',{size:12,fill:'#efc4a6',weight:700,anchor:'middle'});return;
    }
    label(50,76,'AN EVIDENCE CHAIN YOU CAN REPEAT',{size:13,fill:'#f4c39a',weight:700,spacing:1.8});
    const items=[['NASA FIRMS','ORIGINAL ROWS'],['SHA-256','SOURCE HASHES'],['1 KM GRID','DAILY COUNTS'],['CAL FIRE','DATED REPORT'],['STUDY ZIP','LOCAL RECOUNT']];
    items.forEach(([title,sub],index)=>{
      const x=53+index*181;
      rounded(x,172,154,149,index===2?'#34332e':'#17313a',index===2?'#e5a479':'#67848d',12);
      label(x+77,226,title,{size:17,fill:index===2?'#ffceaa':'#eff7f4',weight:700,anchor:'middle'});
      label(x+77,261,sub,{size:10,fill:'#9cb8c1',weight:700,anchor:'middle',spacing:.8});
      if(index<4)label(x+168,254,'→',{size:29,fill:'#d5a98d',anchor:'middle'});
    });
    line(208,381,752,381,'#75949b',2,'6 8');
    rounded(287,360,385,43,'#18232b','#7d8f93',6);
    label(480,388,'PASS / CLOUD MASKS: NOT YET VERIFIED',{size:14,fill:'#efc4a6',weight:700,anchor:'middle'});
    label(54,447,`${cross.eligible_additional_incidents} OTHER JULY INCIDENTS`,{size:13,fill:'#dbe7e8',weight:700,spacing:1.1});
    for(let index=0;index<cross.eligible_additional_incidents;index++){
      const x=397+index*20;
      el('circle',{cx:x,cy:440,r:6,fill:index<cross.nearby_detections?'#f3a676':'#172b35',stroke:index<cross.nearby_detections?'#f8d5aa':'#90a9b2','stroke-width':1.6});
    }
    label(397,472,`${cross.nearby_detections} NEARBY POINTS`,{size:11,fill:'#f5bd94',weight:700});
    label(894,472,`${cross.misses} WITHOUT`,{size:11,fill:'#adc4cd',weight:700,anchor:'end'});
    footer('ASSOCIATION WITHIN 5 KM / 48 H · UNKNOWN SATELLITE COVERAGE PREVENTS A DETECTION-RATE CLAIM');
  }
  function showCell(cell){
    const detail=$('#validity-record-detail');detail.replaceChildren();
    const heading=document.createElement('strong');heading.textContent=`Grid ${cell.grid_x}, ${cell.grid_y} · ${cell.raw_pixels} original pixels`;
    detail.append(heading);
    for(const record of cell.records){const p=document.createElement('p');p.textContent=`${sourceNames[record.source_id]} · ${record.platform} · ${record.acquisition_utc} · confidence ${record.confidence_raw} · version ${record.product_version} · ${record.lat.toFixed(5)}, ${record.lon.toFixed(5)} · source SHA-256 ${record.file_sha256.slice(0,12)}… · row ${record.detection_id.slice(0,12)}…`;detail.append(p);}
    $('#validity-inspect').open=true;
  }
  function showMaskCell(cell){
    const detail=$('#validity-record-detail');detail.replaceChildren();
    const heading=document.createElement('strong');heading.textContent=`${sourceNames[cell.source_id]} · grid ${cell.grid_x}, ${cell.grid_y} · ${cell.state}`;detail.append(heading);
    const counts=document.createElement('p');counts.textContent=`Native classes: ${Object.entries(cell.class_counts).map(([code,count])=>`${code}: ${count}`).join(' · ')}. Centroid sampling does not establish complete coverage of a cell.`;detail.append(counts);
    for(const identifier of cell.granules){const p=document.createElement('p');p.textContent=identifier;detail.append(p);}
    $('#validity-inspect').open=true;
  }
  function renderValidation(){
    const target=$('#validity-validation');if(!target)return;target.replaceChildren();
    const heading=document.createElement('h4');heading.textContent='From downloads to a checked result';target.append(heading);
    const path=document.createElement('ol');path.className='validity-validation-path';
    for(const gate of report.validation_gates||[]){
      const step=document.createElement('li');step.className=gate.status;
      const mark=document.createElement('span');mark.className='validation-step-mark';mark.textContent=gate.status==='passed'?'✓':'○';mark.setAttribute('aria-hidden','true');
      const name=document.createElement('strong');name.textContent=gate.label;
      const count=document.createElement('b');count.textContent=`${format(gate.actual)} / ${format(gate.required)}`;
      const state=document.createElement('small');state.textContent=`${gate.unit} · ${gate.status}${gate.target_fraction?' · target ≥98% of available rows':''}`;
      step.append(mark,name,count,state);path.append(step);
    }
    target.append(path);
    const masks=report.native_masks;
    const summary=document.createElement('p');summary.textContent=masks?.processed_fire_granules
      ?`${format(masks.clipped_native_pixels)} native centroid samples · ${format(masks.paired_observations.sample_size)} usable pairs within 90 minutes. Raw masks and interpretation still require independent review.`
      :'Native files are not loaded. Download the exact files from NASA with Earthdata Login; detection CSVs alone cannot establish clear or cloud observations.';
    target.append(summary);
    if(masks?.processed_fire_granules){
      const limits=document.createElement('p');limits.textContent=`${format(masks.reconciliation.total_firms_pixels-masks.reconciliation.matched)} unreconciled rows · ${format(masks.reconciliation.confidence_disagreements)} confidence disagreements. The match target applies only to available FIRMS rows; it is not a completeness claim. All exceptions and the 30-cell review queue are included in the ZIP. No-pass and full footprint coverage remain unknown.`;target.append(limits);
    }
    const legend=document.createElement('div');legend.className='validity-mask-legend';
    for(const [kind,text] of [['fire','Native fire'],['clear','Sampled non-fire'],['cloud','Cloud samples'],['unknown','Unknown']]){
      const item=document.createElement('span'),icon=document.createElement('i');icon.className=kind;icon.setAttribute('aria-hidden','true');item.append(icon,document.createTextNode(text));legend.append(item);
    }
    target.append(legend);
  }
  function renderSensitivity(){
    const target=$('#validity-sensitivity');target.replaceChildren();
    const title=document.createElement('strong');title.textContent='GRID + CONFIDENCE SENSITIVITY';target.append(title);
    const max=Math.max(1,...report.detection_sensitivity.map(item=>item.joint_detected_cell_days));
    for(const metres of [500,1000,2000]){
      const all=report.detection_sensitivity.find(item=>item.grid_metres===metres&&!item.exclude_low_confidence);
      const filtered=report.detection_sensitivity.find(item=>item.grid_metres===metres&&item.exclude_low_confidence);
      const row=document.createElement('div');row.className='validity-sensitivity-row';
      const label=document.createElement('span');label.textContent=`${metres.toLocaleString()} m`;
      const tracks=document.createElement('div');tracks.className='validity-sensitivity-tracks';
      for(const [item,kind] of [[all,'all'],[filtered,'filtered']]){
        const bar=document.createElement('i');bar.className=kind;bar.style.width=`${item.joint_detected_cell_days/max*100}%`;
        bar.setAttribute('aria-label',`${kind==='all'?'All confidence classes':'Low confidence excluded'}: ${format(item.joint_detected_cell_days)} detected cell-days`);
        tracks.append(bar);
      }
      const value=document.createElement('b');value.textContent=`${format(all.joint_detected_cell_days)} / ${format(filtered.joint_detected_cell_days)}`;
      row.append(label,tracks,value);target.append(row);
    }
    const note=document.createElement('small');note.textContent='All / low confidence excluded · whole case window · different grid sizes change counts, not burned area.';target.append(note);
  }
  function renderCmr(){
    const target=$('#validity-cmr');target.replaceChildren();
    const title=document.createElement('strong');title.textContent='NASA CMR · CANDIDATE SWATH METADATA';target.append(title);
    const list=document.createElement('div');list.className='validity-cmr-list';
    for(const item of report.cmr_inventory.products.filter(product=>product.role==='fire-mask')){
      const entry=document.createElement('span');
      const count=document.createElement('b');count.textContent=format(item.cmr_hits);
      const name=document.createElement('small');name.textContent=item.product;
      entry.append(count,name);list.append(entry);
    }
    target.append(list);
    const note=document.createElement('small');note.textContent='Intersecting product records found in public CMR metadata. Files and geolocation are not downloaded or decoded; these are not verified clear passes.';target.append(note);
  }
  function renderIncidents(){
    const target=$('#validity-incidents'),cross=report.independent_incidents;target.replaceChildren();
    const title=document.createElement('strong');title.textContent='ALL ADDITIONAL JULY INCIDENTS · FIXED RULE';target.append(title);
    const summary=document.createElement('div');summary.className='validity-incidents-summary';
    const counts=document.createElement('span');counts.innerHTML=`<b>${cross.nearby_detections}</b> nearby <i></i> <b>${cross.misses}</b> without a nearby point`;
    const strip=document.createElement('div');strip.className='validity-incidents-strip';
    for(const item of cross.results){const mark=document.createElement('i');mark.className=item.status==='nearby-detection'?'nearby':'miss';mark.title=`${item.name}: ${item.status==='nearby-detection'?'nearby point':'no nearby point'}`;strip.append(mark);}
    summary.append(counts,strip);target.append(summary);
    const rule=document.createElement('small');rule.textContent=`${cross.eligible_additional_incidents} eligible of ${cross.published_july_links} CAL FIRE July 2024–25 archive links; selected Park and Grove examples excluded. Nearby means first imported standard FIRMS point within 5 km and 48 hours after the interpreted reported start. No nearby point is not evidence of no fire. Satellite pass and cloud coverage remain unknown.`;target.append(rule);
    const list=document.createElement('div');list.className='validity-incidents-list';
    for(const item of cross.results){
      const link=document.createElement('a');link.href=item.url;link.target='_blank';link.rel='noopener noreferrer';
      const pip=document.createElement('i');pip.className=item.status==='nearby-detection'?'nearby':'miss';
      const name=document.createElement('span');name.textContent=item.name;
      const outcome=document.createElement('small');outcome.textContent=item.first_detection?`${item.first_detection.source_id==='MODIS_SP'?'MODIS':'VIIRS'} · ${item.first_detection.distance_km} km`:'NO NEARBY POINT';
      link.append(pip,name,outcome);list.append(link);
    }
    target.append(list);
    const foot=document.createElement('small');foot.textContent=cross.cohort_complete?'The downloaded ZIP includes the full incident ledger, candidate rows, and a reproducible recount.':'The CAL FIRE page ledger is incomplete; inspect unresolved entries in the downloaded ZIP.';target.append(foot);
  }
  function renderEvidenceMedia(){
    const target=$('#validity-evidence-media');
    if(!target)return;
    const inspect=$('#validity-inspect');
    target.hidden=Boolean(inspect&&!inspect.open);
    const media=incidentMedia[caseId]||incidentMedia['park-2024'];
    target.replaceChildren();
    if(media.images?.length){
      const gallery=document.createElement('div');gallery.className='validity-media-gallery';
      for(const item of media.images){
        const figure=document.createElement('figure');figure.className='validity-media-tile';
        // Evidence media is behind the deliberate "Inspect evidence" disclosure,
        // so load it eagerly once that panel is opened. Lazy loading leaves the
        // visible gallery as empty black tiles because the gallery is below the
        // fold and can be hidden when the method page first renders.
        const image=document.createElement('img');image.src=item.src;image.alt=item.alt;image.loading='eager';image.decoding='async';
        const caption=document.createElement('figcaption');caption.textContent=item.label||'Official incident context';
        figure.append(image,caption);gallery.append(figure);
      }
      target.append(gallery);
    }else{
      const empty=document.createElement('div');empty.className='validity-media-empty';empty.setAttribute('role','img');empty.setAttribute('aria-label','No incident photograph published on the official Grove Fire record');
      empty.innerHTML='<span class="validity-media-empty-mark" aria-hidden="true">◎</span><strong>NO PHOTO IN SOURCE RECORD</strong><small>CAL FIRE publishes the dated incident facts and location for this case.</small>';
      target.append(empty);
    }
    const context=$('#validity-incident-context');
    if(context){
      context.replaceChildren();
      const head=document.createElement('div');head.className='validity-media-head';
      const eyebrow=document.createElement('span');eyebrow.textContent=`INCIDENT CONTEXT · ${media.eyebrow}`;
      const badge=document.createElement('b');badge.textContent=media.images?'OFFICIAL PHOTOS':'OFFICIAL RECORD';
      head.append(eyebrow,badge);context.append(head);
      const body=document.createElement('div');body.className='validity-media-body';
      const title=document.createElement('h4');title.textContent=media.title;
      const description=document.createElement('p');description.textContent=media.description;
      const source=document.createElement('a');source.href=media.sourceUrl;source.target='_blank';source.rel='noopener noreferrer';source.textContent=`${media.source} ↗`;
      const note=document.createElement('small');note.textContent=media.note;
      body.append(title,description,source,note);context.append(body);
    }
  }
  function renderDays(){
    const holder=$('#validity-day-buttons');holder.replaceChildren();
    const days=report.days,highest=Math.max(1,...days.map(day=>day.detected_cell_days.MODIS_SP+day.detected_cell_days.VIIRS_SNPP_SP));
    const reportedDay=report.official_reference.start_local.slice(0,10);
    for(const day of days){
      const button=document.createElement('button');button.type='button';button.dataset.day=day.date_utc;
      button.className=(day.date_utc===report.selected_date_utc?'selected ':'')+(day.date_utc===reportedDay?'reported ':'')+(day.documented_source_notice?'source-gap':'');
      button.setAttribute('aria-pressed',String(day.date_utc===report.selected_date_utc));
      button.setAttribute('aria-label',`${day.date_utc} UTC, ${day.joint_detected_cell_days} detected grid cells, ${day.detected_cell_days.MODIS_SP} MODIS source cells, ${day.detected_cell_days.VIIRS_SNPP_SP} VIIRS source cells${day.date_utc===reportedDay?', official incident start date':''}${day.documented_source_notice?', NASA S-NPP processing gap notice':''}`);
      button.title=button.getAttribute('aria-label');
      const bar=document.createElement('span');bar.className='validity-bar';
      const modis=document.createElement('i'),viirs=document.createElement('i');
      modis.style.height=`${day.detected_cell_days.MODIS_SP/highest*66}px`;
      viirs.style.height=`${day.detected_cell_days.VIIRS_SNPP_SP/highest*66}px`;
      bar.append(modis,viirs);
      const text=document.createElement('span');text.textContent=day.date_utc.slice(8);
      button.append(bar,text);button.addEventListener('click',()=>load(caseId,day.date_utc,true));holder.append(button);
    }
  }
  function render(){
    if(!report)return;
    const day=selectedDay(),info=scenes[scene];
    $('#validity-scene-index').textContent=info[0];$('#validity-scene-title').textContent=info[1];$('#validity-scene-copy').textContent=info[2];
    $('#validity-graphic-kicker').textContent=`NASA FIRMS · ${report.title.toUpperCase()}`;
    $('#validity-graphic-date').textContent=`${report.selected_date_utc} UTC`;
    $('#validity-selected-day').textContent=`${report.selected_date_utc} · ${format(day.joint_detected_cell_days)} detected cells`;
    $('#validity-readout-value').textContent=scene==='sensors'?`${format(day.raw_pixels.MODIS_SP)} / ${format(day.raw_pixels.VIIRS_SNPP_SP)}`:scene==='proof'?`${report.independent_incidents.nearby_detections} / ${report.independent_incidents.misses}`:format(day.joint_detected_cell_days);
    $('#validity-readout-label').textContent=scene==='sensors'?'MODIS / VIIRS ORIGINAL PIXELS':scene==='proof'?'NEARBY / NO NEARBY POINT · ADDITIONAL INCIDENTS':'JOINT DETECTED CELL-DAYS · THIS DAY';
    $('#validity-status').textContent=day.documented_source_notice
      ?'NASA logged an S-NPP processing gap for this day. Pass/cloud coverage remains unknown.'
      :report.sources.every(source=>source.full_month_export)
        ?'Authentic standard FIRMS exports · pass/cloud coverage still unknown.'
        :'Selected month lacks a complete paired standard export; counts may be partial.';
    const c=new URLSearchParams({series:'joint',year:report.selected_date_utc.slice(0,4),month:String(Number(report.selected_date_utc.slice(5,7))),day:report.selected_date_utc,bbox:report.bbox.join(',')});
    if(liteEarth)c.set('lite','1');
    $('#validity-open-calendar').href=`./?${c}#calendar-section`;
    $('#validity-official-link').href=report.official_reference.url;
    $('#validity-source-notice').hidden=!report.source_notice;
    $('#validity-notice-link').hidden=!report.source_notice;
    if(report.source_notice){$('#validity-source-notice').textContent=report.source_notice.description;$('#validity-notice-link').href=report.source_notice.url;}
    $('#validity-download').href=staticDataRoot
      ? new URL(`validity/${caseId}.zip`,new URL(staticDataRoot,document.baseURI)).href
      : `/api/validity/export?case=${encodeURIComponent(caseId)}`;
    const reviewTemplate=$('#validity-review-template');
    if(reviewTemplate){
      reviewTemplate.href=staticDataRoot
        ? new URL(`validity/${caseId}-review-template.json`,new URL(staticDataRoot,document.baseURI)).href
        : `/api/validity/review-template?case=${encodeURIComponent(caseId)}`;
      reviewTemplate.download=`fireatlas_${caseId}_native_mask_review_template.json`;
    }
    const reviewUi=$('#validity-review-ui');
    if(reviewUi)reviewUi.href=`./review.html?case=${encodeURIComponent(caseId)}`;
    const first=report.first_detection_within_5km_after_reported_start;
    $('#validity-detail-summary').textContent=first
      ?`The official record gives a local start time of ${report.official_reference.start_local.replace('T',' ')}. The first imported detection within 5 km after that interpreted time was ${first.acquisition_utc} (${sourceNames[first.source_id]}, ${first.distance_km} km from the reported start). This is a spatial and temporal association, not proof of the fire perimeter.`
      :'No imported detection within 5 km after the interpreted official start was found in this fixed case window. This does not prove that no fire occurred.';
    const detail=$('#validity-record-detail');detail.replaceChildren();
    const p=document.createElement('p');p.textContent='Select a detection circle in the graphic to inspect its original acquisition times and source fields.';detail.append(p);
    renderSensitivity();
    renderCmr();
    renderIncidents();
    renderValidation();
    $('#validity-mask-controls').hidden=scene!=='coverage';
    renderEvidenceMedia();
    document.querySelectorAll('[data-validity-case]').forEach(button=>{const active=button.dataset.validityCase===caseId;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));});
    document.querySelectorAll('[data-validity-scene]').forEach(button=>{const active=button.dataset.validityScene===scene;button.classList.toggle('active',active);if(active)button.setAttribute('aria-current','step');else button.removeAttribute('aria-current');});
    renderDays();
    if(mobile()){
      const active=$('#validity-day-buttons .selected');
      if(active){const container=$('#validity-day-buttons');container.scrollLeft=Math.max(0,active.offsetLeft-container.offsetLeft-container.clientWidth/2+active.clientWidth/2);}
      const step=$('.validity-steps .active');
      if(step){const container=$('.validity-steps');container.scrollLeft=Math.max(0,step.offsetLeft-container.offsetLeft-container.clientWidth/2+step.clientWidth/2);}
    }
    if(scene==='sensors')drawSensors();else if(scene==='coverage')drawMap(true);else if(scene==='grid')drawGrid();else if(scene==='timeline')drawMap(false);else drawProof();
  }
  async function load(id,date=null,sync=false){
    const current=++request;caseId=id;
    $('#validity-status').textContent='Loading dated NASA FIRMS evidence…';
    const key=`${id}:${date||'default'}`;
    try{
      let next=cache.get(key);
      if(!next){
        const url=staticDataRoot
          ? new URL(`validity/${id}${date?`/${date}`:''}.json`,new URL(staticDataRoot,document.baseURI)).href
          : `/api/validity?${new URLSearchParams({case:id,...(date?{date}:{})})}`;
        const response=await fetch(url,{signal:AbortSignal.timeout(90000)});next=await response.json();if(!response.ok)throw new Error(next.error||'Study unavailable');cache.set(key,next);
      }
      if(current!==request)return;
      report=next;selectedDate=next.selected_date_utc;render();
      window.dispatchEvent(new CustomEvent('fireatlas:validity-report',{detail:next}));
      if(location.pathname==='./method.html'){const address=new URL(location.href);address.searchParams.set('case',id);address.searchParams.set('case_date',selectedDate);history.replaceState(null,'',address);}
      if(sync)window.dispatchEvent(new CustomEvent('fireatlas:validity-day',{detail:{date:selectedDate,bbox:next.bbox,year:Number(selectedDate.slice(0,4)),month:Number(selectedDate.slice(5,7))}}));
    }catch(error){if(current!==request)return;report=null;svg.replaceChildren();$('#validity-status').textContent=`Authentic case unavailable: ${error.message}. Select a case to retry.`;$('#validity-graphic-date').textContent='SOURCE DATA UNAVAILABLE';$('#validity-readout-value').textContent='—';$('#validity-day-buttons').replaceChildren();
      for(const id of ['validity-detail-summary','validity-record-detail','validity-sensitivity','validity-cmr','validity-incidents','validity-validation','validity-evidence-media','validity-incident-context'])$('#'+id)?.replaceChildren();
      $('#validity-source-notice').hidden=true;$('#validity-notice-link').hidden=true;$('#validity-selected-day').textContent='—';$('#validity-official-link').removeAttribute('href');$('#validity-download').removeAttribute('href');$('#validity-review-template').removeAttribute('href');$('#validity-review-ui').removeAttribute('href');
      window.dispatchEvent(new CustomEvent('fireatlas:validity-error',{detail:{message:error.message}}));
    }
  }
  document.querySelectorAll('[data-validity-case]').forEach(button=>button.addEventListener('click',()=>load(button.dataset.validityCase)));
  document.querySelectorAll('[data-validity-scene]').forEach(button=>button.addEventListener('click',()=>{scene=button.dataset.validityScene;render();}));
  window.addEventListener('fireatlas:select-validity-day',event=>load(caseId,event.detail.date,true));
  $('#validity-mask-source')?.addEventListener('change',event=>{maskSource=event.target.value;render();});
  const inspect=$('#validity-inspect'),media=$('#validity-evidence-media');
  if(inspect&&media){
    const syncMedia=()=>{
      media.hidden=!inspect.open;
      const cue=inspect.querySelector('.inspect-summary-cue');
      if(cue)cue.textContent=inspect.open?'CLOSE EVIDENCE −':'OPEN EVIDENCE ↗';
    };
    inspect.addEventListener('toggle',syncMedia);
    syncMedia();
  }
  window.addEventListener('resize',()=>{if(report)render();},{passive:true});
  load(caseId,viewParams.get('case_date'));
});

});
