const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');

// SVG deliberately has no reflected HTMLElement.hidden property. This models
// the browser distinction that previously left supported uncertainty charts hidden.
class Element {
  constructor(svg=false) { this.svg=svg;this.attrs=new Map();this.children=[];this.listeners={};this.value='norcal'; }
  setAttribute(k,v) { this.attrs.set(k,String(v)); }
  removeAttribute(k) { this.attrs.delete(k); }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children=items; }
  addEventListener(k,fn) { this.listeners[k]=fn; }
  set hidden(value) { if(this.svg){this.svgHiddenProperty=value;return;} if(value)this.attrs.set('hidden','');else this.attrs.delete('hidden'); }
  get hidden() { return this.svg ? this.svgHiddenProperty : this.attrs.has('hidden'); }
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));

test('supported interval SVG becomes visible; new request clears and hides stale estimates',async()=>{
  const ids=['qualification-monthly','compare-region','qualification-monthly-status','qualification-monthly-support','qualification-monthly-table','qualification-monthly-values','qualification-monthly-chart','qualification-monthly-download','qualification-readiness-download','qualification-input-download','qualification-monthly-retry','qualification-monthly-metrics','qualification-monthly-checks'];
  const elements=Object.fromEntries(ids.map(id=>[id,new Element(id==='qualification-monthly-chart')]));
  const svg=elements['qualification-monthly-chart'];svg.setAttribute('hidden','');
  const doc={body:{dataset:{workspace:'research'}},getElementById:id=>elements[id]||null,createElement:()=>new Element(),createElementNS:()=>new Element(true)};
  const row={date:'2019-01',month:1,modis:100,reference:50,prediction:4,interval:[1,8]};
  let pending=false,resolvers=[];
  const metric={median_absolute_log_error:0,weighted_absolute_percentage_error:0,signed_error:0,coverage:1,mean_interval_width:7,interval_score:8};
  const payload=name=>({release_id:'test-only',url:'http://fixture.invalid/'+name,value:name==='readiness.json'?{regions:{norcal:{states:{model_fitted:{passed:false,reason:'Isolated synthetic UI fixture'}}}}}:{state:'experimental-ai-reviewed',cohorts:[{versions:['fixture','fixture'],complete_months:96}],result:{synthetic:true,evaluation:{forward:{rows:[row],skipped:[],folds:[{test_year:2019}],raw:metric,adjusted:metric,checks:{test_support:false,interval_coverage:true}}}}}});
  const win={FireAtlasQualification:{read:name=>pending?new Promise(resolve=>resolvers.push(()=>resolve(payload(name)))):Promise.resolve(payload(name))},FireAtlasPanels:{define:(_name,mount)=>mount({document:doc,window:win,fetch:()=>{throw Error('No provider request allowed in UI fixture');}})}};
  vm.runInNewContext(fs.readFileSync('fireatlas/static/qualification.js','utf8'),{window:win,document:doc,URL,Option:class{},Event:class{}});
  await flush();
  assert.equal(svg.attrs.has('hidden'),false,'Supported interval chart must remove the SVG hidden attribute');
  assert.ok(svg.children.length>0,'Predictions and uncertainty marks must render');
  const points=svg.children.filter(child=>child.attrs.has('cy'));
  assert.equal(points.length,3,'Raw baseline, observed reference and estimate must all be shown');
  assert.ok(points.every(point=>Number(point.attrs.get('cy'))>=0),'Out-of-interval observations must stay inside the chart scale');
  assert.ok(elements['qualification-monthly-values'].children.length,'Exact table accompanies the chart');
  const text=node=>(node.textContent||'')+(node.children||[]).map(text).join(' ');
  assert.match(text(elements['qualification-monthly-metrics']),/Raw MODIS baseline/);
  assert.match(text(elements['qualification-monthly-checks']),/Not met/,'Insufficient test groups remain visibly unmet');
  assert.match(text(elements['qualification-monthly-checks']),/two calibration years/);
  pending=true;elements['compare-region'].listeners.change();
  assert.equal(svg.attrs.has('hidden'),true,'Hide the old chart immediately while another selection loads');
  assert.equal(svg.children.length,0,'Stale predictions must be removed before a new response');
  assert.equal(elements['qualification-monthly-metrics'].children.length,0,'Metrics clear with the selected result');
  assert.equal(elements['qualification-monthly-checks'].children.length,0,'Numerical checks cannot outlive their cohort');
  resolvers.forEach(resolve=>resolve());await flush();
  assert.equal(svg.attrs.has('hidden'),false);
});

test('archive cohort selection retains its own values and reproduction file',async()=>{
  const ids=['qualification-monthly','compare-region','qualification-cohort','qualification-monthly-status','qualification-monthly-support','qualification-monthly-source','qualification-monthly-source-download','qualification-monthly-table','qualification-monthly-values','qualification-monthly-chart','qualification-monthly-download','qualification-readiness-download','qualification-input-download','qualification-monthly-retry','qualification-daily-status','qualification-daily-table','qualification-daily-checks','qualification-daily-seasons','qualification-daily-download','qualification-hybrid-status','qualification-hybrid-chart','qualification-hybrid-table','qualification-hybrid-checks','qualification-hybrid-download'];
  ids.push('qualification-diagnostic-status','qualification-diagnostic-table','qualification-diagnostic-download');
  ids.push('qualification-neighbors-status','qualification-neighbors-table','qualification-neighbors-checks','qualification-neighbors-calibration','qualification-neighbors-download');
  const elements=Object.fromEntries(ids.map(id=>[id,new Element(id==='qualification-monthly-chart')]));elements['qualification-cohort'].value='recent';
  const doc={body:{dataset:{workspace:'research'}},getElementById:id=>elements[id]||null,createElement:()=>new Element(),createElementNS:()=>new Element(true)};
  const row={date:'2019-01',month:1,modis:3,reference:9,prediction:8,interval:[5,12]};
  const recent={region:'norcal',state:'experimental-ai-reviewed',cohorts:[{versions:['61.03','2'],complete_months:40}],result:{evaluation:{forward:{rows:[],skipped:[]}}}};
  const archive={id:'archive-scope',state:'experimental-ai-reviewed',cohorts:[{versions:['6.03','2'],complete_months:96}],result:{evaluation:{forward:{rows:[row],skipped:[]}}},reproduction_artifact:'cohort-monthly/archive-scope.json.gz',source_provenance:{status:'verified',eligible_months:96,eligible_utc_days_checked:2922,full_evidence:'monthly-provenance/archive-scope.json'},cohort_readiness:{model_fitted:{passed:true,reason:'Isolated synthetic UI fixture'}}};
  const m={n_utc_days:10,median_absolute_log_error:1,weighted_absolute_percentage_error:.5,coverage:.9,interval_score:5};
  const daily={id:'archive-scope',region:'norcal',versions:['6.03','2'],test_dates:10,test_years:[2019],metrics:{hurdle_poisson:m,no_harmonization:m},zero_modis_positive_viirs:{hurdle_poisson:m,no_harmonization:m},seasonal:{DJF:{hurdle_poisson:m}},checks:{three_test_groups:false,interval_coverage:true},reproduction_artifact:'cohort-daily/archive-scope.json.gz',hybrid:{state:'experimental',estimates_admitted:false,test_dates:10,test_years:[2019],metrics:{zero_hurdle_annual:m},zero_modis_positive_viirs:{zero_hurdle_annual:m},checks:{zero_hurdle_annual:{annual_ratio_log_improvement:false}},reproduction_artifact:'daily-hybrid/archive-scope.json.gz'}};
  daily.neighbors={state:'experimental',estimates_admitted:false,test_dates:10,test_years:[2019],metrics:{similar_day_mean:m},zero_modis_positive_viirs:{similar_day_mean:m},checks:{annual_ratio_wape:false},occurrence_brier:.2,occurrence_calibration:[{probability_bin:[0,1],n:10,mean_probability:.4,observed_positive_fraction:.5}],reproduction_artifact:'daily-neighbors/archive-scope.json.gz'};
  const diagnostic={n_utc_days:10,test_year_groups:1,mean_signed_error:1,occurrence_brier:.2,interval_covered_days:9,interval_days:10,interval_mean_width:3};
  daily.diagnostics={state:'experimental',scientific_admission:false,overall:diagnostic,by_test_year:{2019:diagnostic},by_season:{DJF:diagnostic},by_modis_state:{zero_modis_positive_viirs:diagnostic},reproduction_artifact:'daily-diagnostics/archive-scope.json'};
  const payload=name=>({release_id:'test-only',url:'http://fixture.invalid/releases/test/'+name,value:name==='readiness.json'?{regions:{norcal:{states:{model_fitted:{passed:false,reason:'Recent fixture unsupported'}}}}}:name.startsWith('monthly-cohorts/')?{entries:[archive]}:name.startsWith('daily-cohorts/')?{region:'norcal',entries:[daily]}:recent});
  const win={FireAtlasQualification:{read:name=>Promise.resolve(payload(name))},FireAtlasPanels:{define:(_name,mount)=>mount({document:doc,window:win,fetch:()=>{throw Error('No provider calls');}})}};
  vm.runInNewContext(fs.readFileSync('fireatlas/static/qualification.js','utf8'),{window:win,document:doc,URL,Option:class{constructor(text,value){this.text=text;this.value=value;}},Event:class{}});
  await flush();assert.equal(elements['qualification-monthly-chart'].attrs.has('hidden'),true);
  elements['qualification-cohort'].value='archive-scope';elements['qualification-cohort'].listeners.change();await flush();
  assert.equal(elements['qualification-monthly-chart'].attrs.has('hidden'),false);
  assert.equal(elements['qualification-input-download'].href,'http://fixture.invalid/releases/test/cohort-monthly/archive-scope.json.gz');
  assert.equal(elements['qualification-monthly-download'].href,elements['qualification-input-download'].href);
  assert.match(elements['qualification-monthly-source'].textContent,/96 months and 2,922 UTC days/);
  assert.equal(elements['qualification-monthly-source-download'].href,'http://fixture.invalid/releases/test/monthly-provenance/archive-scope.json');
  assert.match(elements['qualification-monthly-support'].textContent,/6.03 \/ 2: 96 complete months/);
  assert.match(elements['qualification-daily-status'].textContent,/Daily evaluation/);
  assert.equal(elements['qualification-daily-download'].href,'http://fixture.invalid/releases/test/cohort-daily/archive-scope.json.gz');
  assert.ok(elements['qualification-daily-checks'].children.length);
  assert.match(elements['qualification-diagnostic-status'].textContent,/S-NPP cell-day diagnostics/);
  assert.ok(elements['qualification-diagnostic-table'].children.length);
  assert.equal(elements['qualification-diagnostic-download'].href,'http://fixture.invalid/releases/test/daily-diagnostics/archive-scope.json');
  assert.match(elements['qualification-neighbors-status'].textContent,/Similar-day retrospective follow-up/);
  assert.ok(elements['qualification-neighbors-table'].children.length);
  assert.equal(elements['qualification-neighbors-download'].href,'http://fixture.invalid/releases/test/daily-neighbors/archive-scope.json.gz');
  assert.match(elements['qualification-hybrid-status'].textContent,/after earlier results were inspected/);
  assert.equal(elements['qualification-hybrid-download'].href,'http://fixture.invalid/releases/test/daily-hybrid/archive-scope.json.gz');
  assert.ok(elements['qualification-hybrid-checks'].children.length);
  assert.equal(elements['qualification-hybrid-chart'].children.length,2,'Both overall and zero-recovery comparisons render');
  daily.region='punjab-haryana';elements['qualification-monthly-retry'].listeners.click();await flush();
  assert.match(elements['qualification-daily-status'].textContent,/region does not match/);
  assert.match(elements['qualification-hybrid-status'].textContent,/unavailable/);
  assert.equal(elements['qualification-hybrid-download'].hidden,true);
  daily.region='norcal';const savedMetrics=daily.metrics;daily.metrics=null;
  elements['qualification-monthly-retry'].listeners.click();await flush();
  assert.match(elements['qualification-hybrid-status'].textContent,/No follow-up evidence/);
  assert.equal(elements['qualification-hybrid-download'].hidden,true);daily.metrics=savedMetrics;
  const savedChecks=daily.hybrid.checks;daily.hybrid.checks=null;
  elements['qualification-monthly-retry'].listeners.click();await flush();
  assert.match(elements['qualification-hybrid-status'].textContent,/unavailable/);
  assert.equal(elements['qualification-hybrid-table'].children.length,0);
  assert.equal(elements['qualification-hybrid-chart'].children.length,0);
  assert.equal(elements['qualification-daily-table'].children.length,0);
  assert.equal(elements['qualification-daily-download'].hidden,true);
  assert.equal(elements['qualification-neighbors-download'].hidden,true);
  assert.equal(elements['qualification-neighbors-table'].children.length,0);
  assert.equal(elements['qualification-diagnostic-download'].hidden,true);
  assert.equal(elements['qualification-diagnostic-table'].children.length,0);
  assert.equal(elements['qualification-hybrid-download'].hidden,true);daily.hybrid.checks=savedChecks;
  elements['qualification-cohort'].value='recent';elements['qualification-cohort'].listeners.change();assert.equal(elements['qualification-monthly-chart'].children.length,0);assert.equal(elements['qualification-monthly-source-download'].hidden,true);await flush();
  assert.match(elements['qualification-monthly-source'].textContent,/checks are pending/);
  assert.equal(elements['qualification-monthly-chart'].attrs.has('hidden'),true);
  assert.equal(elements['qualification-daily-table'].children.length,0);
  assert.equal(elements['qualification-daily-download'].hidden,true);
  assert.equal(elements['qualification-hybrid-table'].children.length,0);
  assert.equal(elements['qualification-hybrid-chart'].children.length,0);
  assert.equal(elements['qualification-hybrid-download'].hidden,true);
});

test('native angle subset controls preserve undefined overlap, exact tables and clear stale case evidence',async()=>{
  const ids=['qualification-acquisitions','qualification-case','qualification-acquisition','qualification-prev','qualification-next','qualification-candidate-retry','qualification-candidate-status','qualification-acquisition-detail','qualification-acquisition-hashes','qualification-acquisition-table','qualification-envelope-detail','qualification-timeline','qualification-opportunity-download','qualification-condition-table','qualification-condition-threshold','qualification-coverage-download','qualification-condition-download','qualification-context-status','qualification-context-chart','qualification-context-table','qualification-context-comparison','qualification-context-subset','qualification-context-threshold','qualification-context-download','qualification-context-acquisition'];
  const elements=Object.fromEntries(ids.map(id=>[id,new Element(id.endsWith('-chart')||id.endsWith('-timeline'))]));
  for(const[id,value]of [['qualification-case','park-2024'],['qualification-acquisition','0'],['qualification-context-subset','all'],['qualification-context-threshold','90'],['qualification-condition-threshold','90']])elements[id].value=value;
  const doc={body:{dataset:{workspace:'evidence'}},getElementById:id=>elements[id]||null,createElement:()=>new Element(),createElementNS:()=>new Element(true)};
  const metric=positive=>({n_pairs:12,both_detected:positive?1:0,modis_only:positive?2:0,viirs_only:0,both_without_detection:positive?9:12,positive_union_pairs:positive?3:0,positive_jaccard:positive?1/3:null,viirs_overlap_of_modis:{numerator:positive?1:0,denominator:positive?3:0},modis_overlap_of_viirs:{numerator:positive?1:0,denominator:positive?1:0}});
  const subset=(label,positive)=>({label,pixel_samples:24,thresholds:Object.fromEntries(['30','60','90'].map(t=>[t,{metrics:metric(positive),group_uncertainty:{independent_groups:1,positive_jaccard_interval:null,reason:'fewer-than-three-acquisition-groups'}}]))});
  const g={producer_id:'mask-fixture',start_utc:'2024-07-24T10:00:00Z',end_utc:'2024-07-24T10:05:00Z',product:'MOD14',version:'061',native_status:'processed',group_kind:'acquisition-group',opportunity_state:'unknown',missing_reasons:[]};
  let pending=false;const waiting=[];
  const payload=name=>({release_id:'test-release',url:'http://fixture.invalid/releases/test/'+name,value:name.startsWith('opportunity/')?{acquisitions:[g],inventory_complete:true}:name.startsWith('coverage-summary/')?{acquisitions:[],n_cells:2,full_evidence:'coverage/fixture.json.gz'}:name.startsWith('disagreement-summary/')?{experiments:{},full_evidence:'disagreement/fixture.json.gz'}:{case_id:name.includes('grove')?'grove-2025':'park-2024',full_evidence:'native-context/'+(name.includes('grove')?'grove-2025':'park-2024')+'.json.gz',acquisitions:[{producer_id:g.producer_id,status:'extracted',extracted_samples:24,illumination_samples:{day:12,night:12}}],subsets:{all:subset('All sampled centres',true),night:subset('Night · solar zenith above 85°',false)}}});
  const win={addEventListener(){},FireAtlasQualification:{read:name=>pending&&name.startsWith('native-context-summary/')?new Promise(resolve=>waiting.push(()=>resolve(payload(name)))):Promise.resolve(payload(name))},FireAtlasPanels:{define:(_name,mount)=>mount({document:doc,window:win,fetch:()=>{throw Error('No provider calls');}})}};
  vm.runInNewContext(fs.readFileSync('fireatlas/static/qualification.js','utf8'),{window:win,document:doc,URL,URLSearchParams,Option:class{},Event:class{},location:{search:'',href:'http://fixture.invalid/evidence.html'},history:{replaceState(){}}});
  await flush();await flush();
  assert.equal(elements['qualification-context-chart'].attrs.has('hidden'),false);
  assert.match(elements['qualification-context-status'].textContent,/3 positive union pairs/);
  assert.equal(elements['qualification-context-download'].href,'http://fixture.invalid/releases/test/native-context/park-2024.json.gz');
  elements['qualification-context-subset'].value='night';elements['qualification-context-subset'].listeners.change();
  assert.match(elements['qualification-context-status'].textContent,/undefined because there are no positive pairs/);
  assert.ok(elements['qualification-context-table'].children.length);
  pending=true;elements['qualification-case'].value='grove-2025';elements['qualification-case'].listeners.change();
  assert.equal(elements['qualification-context-chart'].attrs.has('hidden'),true);
  assert.equal(elements['qualification-context-chart'].children.length,0);
  assert.equal(elements['qualification-context-download'].hidden,true);
  await flush();elements['qualification-case'].value='park-2024';elements['qualification-case'].listeners.change();await flush();
  waiting[1]();await flush();
  assert.match(elements['qualification-context-download'].href,/park-2024/);
  waiting[0]();await flush();
  assert.match(elements['qualification-context-download'].href,/park-2024/,'Late previous-case response cannot replace the active selection');
});

test('footprint cohort selection retains unknowns and immutable parts; stale and mixed-release replies cannot replace the active case',async()=>{
 const ids=['qualification-acquisitions','qualification-case','qualification-acquisition','qualification-prev','qualification-next','qualification-candidate-retry','qualification-candidate-status','qualification-acquisition-detail','qualification-acquisition-hashes','qualification-acquisition-table','qualification-timeline','qualification-opportunity-download','qualification-footprint-select','qualification-footprint-status','qualification-footprint-table','qualification-footprint-downloads'];
 const elements=Object.fromEntries(ids.map(id=>[id,new Element()]));elements['qualification-case'].value='park-2024';
 const doc={body:{dataset:{workspace:'evidence'}},getElementById:id=>elements[id]||null,createElement:()=>new Element()};
 const cohorts=[{source:'MODIS_SP',version:'61.03'},{source:'VIIRS_SNPP_SP',version:'2'}];
 let delayed=false,mixed=false;const waiting=[];
 const payload=name=>({release_id:mixed&&name.startsWith('footprint-summary/')?'changed-release':'test-release',url:'http://fixture.invalid/project/releases/test/'+name,value:name.startsWith('opportunity/')?{acquisitions:[],inventory_complete:true}:{case_id:name.includes('grove')?'grove-2025':'park-2024',scope_complete:false,validated_observation_opportunity:false,cohorts:cohorts.map(cohort=>({cohort,days:[{date:'2025-07-04',expected_cells:648,represented_cells:1,unknown_cells:648,usable_cells:0,acquisition_groups:0,candidate_granules:0,boundary_pixels:0}]})),parts:cohorts.map((cohort,i)=>({cohorts:[cohort],start:'2025-07-04',end:'2025-07-04',artifact:'footprint-part/'+String(i).repeat(64)+'.json.gz'}))}});
 const win={addEventListener(){},FireAtlasQualification:{read:name=>name.startsWith('coverage-')||name.startsWith('disagreement-')?Promise.reject(Error('No legacy geometry fixture')):delayed&&name.startsWith('footprint-summary/')?new Promise(resolve=>waiting.push(()=>resolve(payload(name)))):Promise.resolve(payload(name))},FireAtlasPanels:{define:(_name,mount)=>mount({document:doc,window:win,fetch:()=>{throw Error('No provider calls');}})}};
 vm.runInNewContext(fs.readFileSync('fireatlas/static/qualification.js','utf8'),{window:win,document:doc,URL,URLSearchParams,Option:class{constructor(text,value){this.textContent=text;this.value=value;}},Event:class{},location:{search:'',href:'http://fixture.invalid/evidence.html'},history:{replaceState(){}}});
 await flush();await flush();
 assert.equal(elements['qualification-footprint-select'].disabled,false);
 assert.match(elements['qualification-footprint-status'].textContent,/Unknown support does not mean no fire/);
 assert.match(elements['qualification-footprint-downloads'].children[0].href,/footprint-part\/0{64}\.json\.gz$/);
 elements['qualification-footprint-select'].value='1';elements['qualification-footprint-select'].listeners.change();
 assert.match(elements['qualification-footprint-downloads'].children[0].href,/footprint-part\/1{64}\.json\.gz$/);
 delayed=true;elements['qualification-case'].value='grove-2025';elements['qualification-case'].listeners.change();
 assert.equal(elements['qualification-footprint-table'].children.length,0);assert.equal(elements['qualification-footprint-downloads'].children.length,0);assert.equal(elements['qualification-footprint-select'].disabled,true);
 await flush();elements['qualification-case'].value='park-2024';elements['qualification-case'].listeners.change();await flush();waiting[1]();await flush();waiting[0]();await flush();
 assert.match(elements['qualification-footprint-status'].textContent,/partial pilot support/);
 mixed=true;elements['qualification-candidate-retry'].listeners.click();await flush();waiting[2]();await flush();
 assert.match(elements['qualification-footprint-status'].textContent,/Publication changed/);assert.equal(elements['qualification-footprint-downloads'].children.length,0);assert.equal(elements['qualification-footprint-select'].disabled,true);
});

test('transfer checks own their selected experiment and reject mixed releases after retry',async()=>{
 const ids=['qualification-monthly','compare-region','qualification-monthly-status','qualification-monthly-support','qualification-monthly-table','qualification-monthly-values','qualification-monthly-chart','qualification-monthly-download','qualification-readiness-download','qualification-input-download','qualification-monthly-retry','qualification-transfer-table','qualification-transfer-status','qualification-transfer-download','qualification-transfer-support-select','qualification-transfer-support-status','qualification-transfer-support-source','qualification-transfer-support-table','qualification-transfer-support-platforms','qualification-transfer-support-downloads'];
 const elements=Object.fromEntries(ids.map(id=>[id,new Element()]));elements['compare-region'].value='norcal';
 const doc={body:{dataset:{workspace:'research'}},getElementById:id=>elements[id]||null,createElement:()=>new Element()};let mixed=false,wrongRegion=false;
 const entries=['a','b'].map((key,i)=>({id:key,source_cohort:{source:'MODIS_SP',version:String(i)},target_cohort:{source:'VIIRS_SNPP_SP',version:'2'},eligible_months:1,opportunity_represented_pairs:0,opportunity_required_dates:31,admitted:false,count_evidence_sha256:key,checks:{forward_and_backward_performance:false,full_dates:false,independent_review:false},platform_acquisition_support:[],source_provenance:i===0?{status:'verified',full_evidence:'transfer-provenance/'+key.repeat(16)+'.json'}:{status:'pending',full_evidence:null},full_evidence:'transfer-opportunity/'+key.repeat(16)+'.json.gz'}));
 const counts=entries.map((v,i)=>({...v,result_sha256:v.count_evidence_sha256,test_groups:i?{forward:2,backward:2}:{forward:0,backward:0}}));
 const payload=name=>({release_id:mixed&&name.startsWith('transfer-opportunity-summary/')?'changed-release':'test',url:'http://fixture.invalid/project/releases/test/'+name,value:name==='readiness.json'?{regions:{norcal:{states:{}}}}:name.startsWith('transfer-opportunity-summary/')?{region:'norcal',entries}:name.startsWith('transfer-cohorts/')?{region:wrongRegion?'punjab-haryana':'norcal',entries:counts,unresolved:[]}:name.startsWith('transfer-summary/')?{region:'norcal',source_cohort:entries[0].source_cohort,target_cohort:entries[0].target_cohort,eligible_months:0,test_groups:{forward:0,backward:0},full_evidence:'transfer/norcal.json.gz'}:{state:'protocol-approval-pending',cohorts:[]}});
 const win={FireAtlasQualification:{read:name=>Promise.resolve(payload(name))},FireAtlasPanels:{define:(_name,mount)=>mount({document:doc,window:win,fetch:()=>{throw Error('No provider calls');}})}};
 vm.runInNewContext(fs.readFileSync('fireatlas/static/qualification.js','utf8'),{window:win,document:doc,URL,Option:class{constructor(text,value){this.textContent=text;this.value=value;}},Event:class{}});
 await flush();await flush();
 const text=node=>(node.textContent||'')+(node.children||[]).map(text).join(' ');
 assert.match(text(elements['qualification-transfer-support-table']),/Not evaluated · no supported test years/);
 assert.match(elements['qualification-transfer-support-status'].textContent,/0 of 62 required/);
 assert.match(elements['qualification-transfer-support-status'].textContent,/Overlap qualification pending/);
 assert.match(elements['qualification-transfer-support-downloads'].children[0].href,/a{16}\.json\.gz$/);
 assert.match(elements['qualification-transfer-support-source'].textContent,/Original request files/);assert.match(elements['qualification-transfer-support-downloads'].children[1].href,/transfer-provenance\/a{16}\.json$/);
 elements['qualification-transfer-support-select'].value='b';elements['qualification-transfer-support-select'].listeners.change();
 assert.match(text(elements['qualification-transfer-support-table']),/Not met · 2 forward and 2 backward test groups/);
 assert.match(elements['qualification-transfer-support-downloads'].children[0].href,/b{16}\.json\.gz$/);assert.match(elements['qualification-transfer-support-source'].textContent,/pending/);assert.equal(elements['qualification-transfer-support-downloads'].children.length,1);
 counts[1].test_groups={forward:0,backward:2};elements['qualification-transfer-support-select'].listeners.change();assert.match(text(elements['qualification-transfer-support-table']),/Not evaluated in forward direction/);
 counts[1].result_sha256='different-input';elements['qualification-transfer-support-select'].listeners.change();assert.match(text(elements['qualification-transfer-support-table']),/test support unavailable/);
 wrongRegion=true;elements['qualification-monthly-retry'].listeners.click();await flush();await flush();assert.match(elements['qualification-transfer-status'].textContent,/region changed/);assert.match(text(elements['qualification-transfer-support-table']),/Not evaluated · test support unavailable/);wrongRegion=false;
 mixed=true;elements['qualification-monthly-retry'].listeners.click();
 assert.equal(elements['qualification-transfer-support-select'].disabled,true);assert.equal(elements['qualification-transfer-support-downloads'].children.length,0);
 await flush();await flush();assert.match(elements['qualification-transfer-support-status'].textContent,/Publication changed/);assert.equal(elements['qualification-transfer-support-select'].disabled,true);
});

test('transfer performance support follows region and release despite response ordering',async()=>{
 const ids=['qualification-monthly','compare-region','qualification-monthly-status','qualification-monthly-support','qualification-monthly-table','qualification-monthly-values','qualification-monthly-chart','qualification-monthly-download','qualification-readiness-download','qualification-input-download','qualification-monthly-retry','qualification-transfer-table','qualification-transfer-status','qualification-transfer-download','qualification-transfer-support-select','qualification-transfer-support-status','qualification-transfer-support-source','qualification-transfer-support-table','qualification-transfer-support-platforms','qualification-transfer-support-downloads'];
 const elements=Object.fromEntries(ids.map(id=>[id,new Element()]));elements['compare-region'].value='norcal';
 const doc={body:{dataset:{workspace:'research'}},getElementById:id=>elements[id]||null,createElement:()=>new Element()};
 const entries=region=>[{id:region,source_cohort:{source:'MODIS_SP',version:'1'},target_cohort:{source:'VIIRS_SNPP_SP',version:'2'},eligible_months:1,opportunity_represented_pairs:0,opportunity_required_dates:1,admitted:false,count_evidence_sha256:region,checks:{forward_and_backward_performance:false},platform_acquisition_support:[],source_provenance:{status:'pending'},full_evidence:'transfer-opportunity/'+region+'.json.gz'}];
 let heldNorcal,heldSupport,delaySupport=false,badRelease=false;
 const artifact=(name,value,release='test')=>({release_id:release,url:'http://fixture.invalid/releases/test/'+name,value});
 const read=name=>{
  const region=name.includes('punjab-haryana')?'punjab-haryana':'norcal';
  if(name==='readiness.json')return Promise.resolve(artifact(name,{regions:{norcal:{states:{}},'punjab-haryana':{states:{}}}}));
  if(name.startsWith('transfer-summary/'))return Promise.reject(Error('No legacy summary'));
  if(name.startsWith('transfer-cohorts/')){
   const value={region,entries:entries(region).map(v=>({...v,result_sha256:region,test_groups:region==='norcal'?{forward:0,backward:0}:{forward:2,backward:2}})),unresolved:[]};
   if(region==='norcal')return new Promise(resolve=>{heldNorcal=()=>resolve(artifact(name,value));});
   return Promise.resolve(artifact(name,value,badRelease?'other-release':'test'));
  }
  if(name.startsWith('transfer-opportunity-summary/')){
   const value={region,entries:entries(region)};
   if(delaySupport)return new Promise(resolve=>{heldSupport=()=>resolve(artifact(name,value));});
   return Promise.resolve(artifact(name,value));
  }
  return Promise.resolve(artifact(name,{state:'protocol-approval-pending',cohorts:[]}));
 };
 const win={FireAtlasQualification:{read},FireAtlasPanels:{define:(_name,mount)=>mount({document:doc,window:win,fetch:()=>{throw Error('No provider calls');}})}};
 vm.runInNewContext(fs.readFileSync('fireatlas/static/qualification.js','utf8'),{window:win,document:doc,URL,Option:class{constructor(text,value){this.textContent=text;this.value=value;}},Event:class{}});
 const text=node=>(node.textContent||'')+(node.children||[]).map(text).join(' ');
 await flush();await flush();assert.match(text(elements['qualification-transfer-support-table']),/Not evaluated · test support unavailable/);
 elements['compare-region'].value='punjab-haryana';elements['compare-region'].listeners.change();await flush();await flush();
 assert.match(text(elements['qualification-transfer-support-table']),/Not met · 2 forward and 2 backward test groups/);
 heldNorcal();await flush();assert.match(text(elements['qualification-transfer-support-table']),/Not met · 2 forward and 2 backward test groups/);
 badRelease=true;elements['qualification-monthly-retry'].listeners.click();await flush();await flush();
 assert.match(elements['qualification-transfer-status'].textContent,/Publication or region changed/);assert.match(text(elements['qualification-transfer-support-table']),/test support unavailable/);
 badRelease=false;delaySupport=true;elements['qualification-monthly-retry'].listeners.click();await flush();await flush();
 assert.equal(elements['qualification-transfer-support-table'].children.length,0);heldSupport();await flush();
 assert.match(text(elements['qualification-transfer-support-table']),/Not met · 2 forward and 2 backward test groups/);
});

test('collection pilot follows region and rejects stale or mixed-release evidence',async()=>{
 const ids=['qualification-monthly','compare-region','qualification-monthly-status','qualification-monthly-support','qualification-monthly-table','qualification-monthly-values','qualification-monthly-chart','qualification-monthly-download','qualification-readiness-download','qualification-input-download','qualification-monthly-retry','qualification-collection-pilot','qualification-collection-pilot-status','qualification-collection-pilot-visual','qualification-collection-pilot-chart','qualification-collection-pilot-summary','qualification-collection-pilot-platform','qualification-collection-pilot-days','qualification-collection-pilot-download'];
 const elements=Object.fromEntries(ids.map(id=>[id,new Element(id==='qualification-monthly-chart')]));
 const doc={body:{dataset:{workspace:'research'}},getElementById:id=>elements[id]||null,createElement:()=>new Element(),createElementNS:()=>new Element(true)};
 const region=(count)=>({month_cell_days:{c6:count,c61:count,both:count,c6_only:0,c61_only:0,union:count,jaccard:1},days:[{date:'2023-01-01',c6_cells:count,c61_cells:count,both_cells:count,c6_only_cells:0,c61_only_cells:0,jaccard:1,c6_rows:{T:5,A:12},c61_rows:{T:6,A:13}}]});
 const pilot={schema:'fireatlas-modis-collection-pilot-v1',transfer_qualified:false,regions:{norcal:region(43),'punjab-haryana':region(79)}};
 pilot.regions['punjab-haryana'].month_cell_days={c6:500,c61:500,both:499,c6_only:1,c61_only:1,union:501,jaccard:499/501};
 pilot.regions['punjab-haryana'].days=[
  {date:'2023-01-01',c6_cells:101,c61_cells:101,both_cells:100,c6_only_cells:1,c61_only_cells:1,jaccard:100/102,c6_rows:{T:5,A:12},c61_rows:{T:6,A:13}},
  {date:'2023-01-02',c6_cells:399,c61_cells:399,both_cells:399,c6_only_cells:0,c61_only_cells:0,jaccard:1,c6_rows:{},c61_rows:{}},
  {date:'2023-01-03',c6_cells:0,c61_cells:0,both_cells:0,c6_only_cells:0,c61_only_cells:0,jaccard:null,c6_rows:{},c61_rows:{}}];
 let hold,first=true,bad=false,badMonthly=false;
 const artifact=(name,value,release='test')=>({release_id:release,url:'http://fixture.invalid/releases/test/'+name,value});
 const read=name=>{
  if(badMonthly&&name.startsWith('monthly/'))return Promise.reject(Error('Monthly unavailable'));
  if(name==='readiness.json')return Promise.resolve(artifact(name,{regions:{norcal:{states:{}},'punjab-haryana':{states:{}}}}));
  if(name==='collection-pilot.json'){
   if(first){first=false;return new Promise(resolve=>{hold=()=>resolve(artifact(name,pilot));});}
   return Promise.resolve(artifact(name,pilot,bad?'different':'test'));
  }
  return Promise.resolve(artifact(name,{state:'protocol-approval-pending',cohorts:[]}));
 };
 const win={FireAtlasQualification:{read},FireAtlasPanels:{define:(_name,mount)=>mount({document:doc,window:win,fetch:()=>{throw Error('No provider calls');}})}};
 vm.runInNewContext(fs.readFileSync('fireatlas/static/qualification.js','utf8'),{window:win,document:doc,URL,Option:class{},Event:class{}});
 const text=node=>(node.textContent||'')+(node.children||[]).map(text).join(' ');
 await flush();await flush();elements['compare-region'].value='punjab-haryana';elements['compare-region'].listeners.change();await flush();await flush();
 assert.match(elements['qualification-collection-pilot-status'].textContent,/original collection files/);
 assert.match(text(elements['qualification-collection-pilot-summary']),/0\.996 \(499 \/ 501\)/);
 assert.match(elements['qualification-collection-pilot-download'].href,/collection-pilot\.json$/);
 assert.match(text(elements['qualification-collection-pilot-platform']),/Terra 5 6 Aqua 12 13/);
 const chart=elements['qualification-collection-pilot-chart'],bars=chart.children.filter(child=>child.attrs.has('height'));
 assert.equal(bars.length,9);assert.deepEqual(bars.slice(0,3).map(b=>b.attrs.get('fill')),['#287446','#a75500','#2457d6']);
 assert.ok(Math.abs(Number(bars[0].attrs.get('height'))-150*100/399)<1e-8);assert.ok(Math.abs(Number(bars[1].attrs.get('y'))-(180-150*101/399))<1e-8);
 assert.equal(Number(bars[3].attrs.get('height')),150);assert.ok(bars.slice(6).every(b=>Number(b.attrs.get('height'))===0));
 assert.match(text(bars[1]),/2023-01-01 · 006 only: 1 cells/);
 assert.ok(chart.children.some(node=>node.textContent==='01'));assert.ok(chart.children.some(node=>node.textContent==='03'));
 assert.equal(elements['qualification-collection-pilot-visual'].hidden,false);
 hold();await flush();assert.match(text(elements['qualification-collection-pilot-summary']),/0\.996 \(499 \/ 501\)/);assert.equal(chart.children.filter(child=>child.attrs.has('height')).length,9);
 bad=true;elements['qualification-monthly-retry'].listeners.click();await flush();await flush();
 assert.match(elements['qualification-collection-pilot-status'].textContent,/unavailable/);
 assert.equal(elements['qualification-collection-pilot-download'].hidden,true);
 assert.equal(elements['qualification-collection-pilot-summary'].children.length,0);
 assert.equal(elements['qualification-collection-pilot-chart'].children.length,0);
 assert.equal(elements['qualification-collection-pilot-visual'].hidden,true);
 bad=false;badMonthly=true;elements['qualification-monthly-retry'].listeners.click();await flush();await flush();
 assert.match(elements['qualification-collection-pilot-status'].textContent,/unavailable/);
 badMonthly=false;pilot.regions['punjab-haryana'].days[0].c6_rows.T=-1;elements['qualification-monthly-retry'].listeners.click();await flush();await flush();
 assert.match(elements['qualification-collection-pilot-status'].textContent,/unavailable/);
 assert.equal(elements['qualification-collection-pilot-summary'].children.length,0);
 assert.equal(elements['qualification-collection-pilot-download'].hidden,true);
 for(const invalid of [null,[]]){pilot.regions['punjab-haryana'].days[0].c6_rows=invalid;elements['qualification-monthly-retry'].listeners.click();await flush();await flush();assert.match(elements['qualification-collection-pilot-status'].textContent,/unavailable/);}
 pilot.regions['punjab-haryana'].days[0].c6_rows={T:null};elements['qualification-monthly-retry'].listeners.click();await flush();await flush();assert.match(elements['qualification-collection-pilot-status'].textContent,/unavailable/);
 pilot.regions['punjab-haryana'].days[0].c6_rows={T:5};elements['qualification-monthly-retry'].listeners.click();await flush();await flush();assert.match(text(elements['qualification-collection-pilot-platform']),/Aqua 0 13/);
});
