/* Small research and acquisition tools inside the existing workspaces. */
(() => {
function mount({document:doc,window:win,fetch:fetcher}){
 const $=id=>doc.getElementById(id),read=name=>win.FireAtlasQualification.read(name,fetcher),n=v=>v===null||v===undefined?'—':Number(v).toLocaleString('en',{maximumFractionDigits:2});
 let monthlySerial=0,caseSerial=0,acquisitions=[],caseArtifact,coverageSummary,conditionSummary,contextSummary,footprintArtifact,transferArtifact,transferCounts=new Map();
 function table(host,heads,rows,caption){const t=doc.createElement('table'),c=doc.createElement('caption');c.textContent=caption;t.append(c);const h=doc.createElement('thead'),tr=doc.createElement('tr');heads.forEach(v=>{const th=doc.createElement('th');th.scope='col';th.textContent=v;tr.append(th);});h.append(tr);t.append(h);const b=doc.createElement('tbody');rows.forEach(row=>{const r=doc.createElement('tr');row.forEach(v=>{const d=doc.createElement('td');d.textContent=v??'—';r.append(d);});b.append(r);});t.append(b);host.replaceChildren(t);}
 function link(id,artifact){const a=$(id);if(a){a.href=artifact.url;a.download=artifact.url.split('/').at(-1);a.hidden=false;}}
 const cohortLabel=c=>c.source+' / '+c.version;
 function collectionChart(host,days){
  if(!host)return;host.replaceChildren();const ns='http://www.w3.org/2000/svg';
  const add=(tag,attrs,text,parent=host)=>{const node=doc.createElementNS(ns,tag);for(const [key,value] of Object.entries(attrs))node.setAttribute(key,value);if(text!==undefined)node.textContent=text;parent.append(node);return node;};
  const parts=['both_cells','c6_only_cells','c61_only_cells'],colors=['#287446','#a75500','#2457d6'];
  for(const day of days)for(const key of parts)if(!Number.isSafeInteger(day[key])||day[key]<0)throw Error('Invalid daily cell count.');
  const max=Math.max(1,...days.map(day=>parts.reduce((sum,key)=>sum+day[key],0))),width=800/Math.max(days.length,1),height=150;
  add('title',{},'Daily MODIS collection overlap');add('desc',{},'Stacked bars show shared cells, collection 006 only, and collection 061 only for each UTC day. Exact counts follow in the table.');
  add('line',{x1:50,y1:180,x2:850,y2:180,stroke:'#9babb2'});add('text',{x:45,y:35,'text-anchor':'end','font-size':12,fill:'#4d6575'},n(max));
  days.forEach((day,i)=>{let offset=0;const x=50+i*width+width*.15;
   parts.forEach((key,j)=>{const barHeight=height*day[key]/max;const rect=add('rect',{x,y:180-offset-barHeight,width:Math.max(1,width*.7),height:barHeight,fill:colors[j]});add('title',{},day.date+' · '+['Shared','006 only','061 only'][j]+': '+n(day[key])+' cells',rect);offset+=barHeight;});
   if(i%5===0||i===days.length-1)add('text',{x:x+width*.35,y:201,'text-anchor':'middle','font-size':11,fill:'#4d6575'},day.date.slice(-2));
  });
 }
 async function collectionPilot(region,token,release){
  const section=$('qualification-collection-pilot');if(!section)return;
  const ratio=(value,shared,union)=>value===null||value===undefined||!union?'—':Number(value).toLocaleString('en',{maximumFractionDigits:4})+' ('+n(shared)+' / '+n(union)+')';
  try{const a=await read('collection-pilot.json');if(token!==monthlySerial)return;
   const v=a.value,selected=v.regions?.[region],m=selected?.month_cell_days;
   if(a.release_id!==release||v.schema!=='fireatlas-modis-collection-pilot-v1'||v.transfer_qualified!==false||!m||!Array.isArray(selected.days))throw Error('Collection evidence differs from the selected release.');
   collectionChart($('qualification-collection-pilot-chart'),selected.days);
   table($('qualification-collection-pilot-summary'),['Collection 006','Collection 061','Shared','006 only','061 only','Union','Jaccard'],[[n(m.c6),n(m.c61),n(m.both),n(m.c6_only),n(m.c61_only),n(m.union),ratio(m.jaccard,m.both,m.union)]],'January 2023 · occupied centroid cell-days · '+region);
   const platform=$('qualification-collection-pilot-platform');if(platform){const count=(source,sat)=>selected.days.reduce((sum,d)=>{const row=d[source];if(!row||typeof row!=='object'||Array.isArray(row))throw Error('Platform counts are unavailable.');const value=Object.prototype.hasOwnProperty.call(row,sat)?row[sat]:0;if(!Number.isSafeInteger(value)||value<0)throw Error('Platform count is invalid.');return sum+value;},0);table(platform,['Platform','Collection 006 rows','Collection 061 rows'],[['Terra',n(count('c6_rows','T')),n(count('c61_rows','T'))],['Aqua',n(count('c6_rows','A')),n(count('c61_rows','A'))]],'Type 0 source rows · January 2023');}
   table($('qualification-collection-pilot-days'),['UTC date','Collection 006','Collection 061','Shared','006 only','061 only','Jaccard'],selected.days.map(d=>[d.date,n(d.c6_cells),n(d.c61_cells),n(d.both_cells),n(d.c6_only_cells),n(d.c61_only_cells),ratio(d.jaccard,d.both_cells,d.both_cells+d.c6_only_cells+d.c61_only_cells)]),'Daily occupied centroid cells.');
   const download=$('qualification-collection-pilot-download');download.href=a.url;download.download='modis-collection-pilot.json';download.hidden=false;if($('qualification-collection-pilot-visual'))$('qualification-collection-pilot-visual').hidden=false;$('qualification-collection-pilot-status').textContent='January 2023 · original collection files';
  }catch(e){if(token===monthlySerial){for(const id of ['qualification-collection-pilot-chart','qualification-collection-pilot-summary','qualification-collection-pilot-platform','qualification-collection-pilot-days'])$(id)?.replaceChildren();const download=$('qualification-collection-pilot-download');if(download){download.hidden=true;download.removeAttribute('href');}if($('qualification-collection-pilot-visual'))$('qualification-collection-pilot-visual').hidden=true;$('qualification-collection-pilot-status').textContent='Collection comparison unavailable. Use Retry evidence.';}}
 }
 function hybridChart(host,h,names){
  if(!host)return;host.replaceChildren();
  const order=['no_harmonization','annual_ratio','monthly_ratio','hurdle_poisson','zero_hurdle_annual','zero_hurdle_monthly'];
  for(const [title,source] of [['Overall median log error',h.metrics],['Zero-MODIS / positive-VIIRS median log error',h.zero_modis_positive_viirs]]){
   const panel=doc.createElement('section'),heading=doc.createElement('h4');heading.textContent=title+' · lower is better';panel.append(heading);
   const values=order.map(id=>source[id]?.median_absolute_log_error),max=Math.max(0,...values.filter(v=>typeof v==='number'&&Number.isFinite(v)));
   order.forEach((id,i)=>{const row=doc.createElement('div'),label=doc.createElement('span'),track=doc.createElement('span'),bar=doc.createElement('span'),value=doc.createElement('span');row.className='qualification-bar-row';track.className='qualification-bar-track';bar.className=id.startsWith('zero_hurdle_')?'qualification-bar candidate':'qualification-bar';label.textContent=names[id];const valid=typeof values[i]==='number'&&Number.isFinite(values[i])&&values[i]>=0;value.textContent=valid?n(values[i]):'—';bar.setAttribute('style','width:'+(valid&&max?100*values[i]/max:0)+'%');bar.setAttribute('aria-hidden','true');track.append(bar);row.append(label,track,value);panel.append(row);});host.append(panel);
  }
 }
 function resetSupport(kind){
  for(const suffix of ['table','platforms','downloads'])$('qualification-'+kind+'-'+suffix)?.replaceChildren();
  const control=$('qualification-'+kind+'-select');if(control){control.replaceChildren();control.disabled=true;}
  const status=$('qualification-'+kind+'-status');if(status)status.textContent='Loading exact support evidence…';
  const source=$('qualification-'+kind+'-source');if(source)source.textContent='';
 }
 function transferSupport(){
  const a=transferArtifact,v=a?.value.entries.find(v=>v.id===$('qualification-transfer-support-select')?.value);if(!v)return;
  $('qualification-transfer-support-status').textContent=n(v.eligible_months)+' complete overlap months · '+n(v.opportunity_represented_pairs)+' of '+n(v.opportunity_required_dates*2)+' required UTC date/cohort pairs represented. '+(v.admitted?'Reviewed overlap admitted.':'Overlap qualification pending.')+' ';
  const performanceOutcome=()=>{
   const count=transferCounts.get(v.id),groups=count?.test_groups;
   if(!count||count.result_sha256!==v.count_evidence_sha256||!Number.isInteger(groups?.forward)||!Number.isInteger(groups?.backward))return 'Not evaluated · test support unavailable; qualification gate not met';
   if(!groups.forward&&!groups.backward)return 'Not evaluated · no supported test years';
   if(!groups.forward||!groups.backward)return 'Not evaluated in '+(!groups.forward?'forward':'backward')+' direction · qualification gate not met';
   return 'Not met · '+n(groups.forward)+' forward and '+n(groups.backward)+' backward test groups';
  };
  table($('qualification-transfer-support-table'),['Required transfer check','Outcome'],Object.entries(v.checks).map(([key,passed])=>[key.replaceAll('_',' '),passed?'Met':key==='forward_and_backward_performance'?performanceOutcome():'Not met']),'Checks based on the selected count, opportunity and review evidence.');
  table($('qualification-transfer-support-platforms'),['Cohort','Platform','Season','Acquisition groups','Sampled area · km²','Known area · km²','Usable area · km²','Groups with geometry gaps'],v.platform_acquisition_support.map(p=>[cohortLabel(p.cohort),p.platform,p.season,n(p.groups),n(p.sampled_area_m2/1e6),n(p.known_area_m2/1e6),n(p.usable_area_m2/1e6),n(p.geometry_failure_groups)]),'Area summed across acquisition and cell samples; unique regional area and observation status are unavailable.');
  const host=$('qualification-transfer-support-downloads'),l=doc.createElement('a');l.textContent='Download exact transfer checks, inputs and review references';l.href=new URL('../'+v.full_evidence,a.url).href;l.download=v.full_evidence.split('/').at(-1);host.replaceChildren(l);
  const p=v.source_provenance,source=$('qualification-transfer-support-source');
  if(source)source.textContent=p?.status==='verified'?'Original request files, merged records and captured cells checked for this input.':p?.status==='partial'?'Source-file checks are incomplete.':'Source-file checks pending.';
  if(p?.full_evidence){const download=doc.createElement('a');download.textContent='Download source verification receipt';download.href=new URL('../'+p.full_evidence,a.url).href;download.download=p.full_evidence.split('/').at(-1);host.append(download);}
 }
 async function loadTransferSupport(region,token,release){
  if(!$('qualification-transfer-support-select'))return;
  try{const a=await read('transfer-opportunity-summary/'+region+'.json');if(token!==monthlySerial)return;if(a.release_id!==release||a.value.region!==region)throw Error('Publication changed; retry for one release.');
   transferArtifact=a;const control=$('qualification-transfer-support-select');control.replaceChildren(...a.value.entries.map(v=>new Option(cohortLabel(v.source_cohort)+' → '+cohortLabel(v.target_cohort),v.id)));control.disabled=!a.value.entries.length;if(a.value.entries.length){control.value=a.value.entries[0].id;transferSupport();}else $('qualification-transfer-support-status').textContent='No exact transfer experiment available for this region.';
  }catch(e){if(token===monthlySerial)$('qualification-transfer-support-status').textContent='Transfer support unavailable. '+e.message+' Use Retry evidence.';}
 }
 function footprintSupport(){
  const a=footprintArtifact,v=a?.value.cohorts[Number($('qualification-footprint-select')?.value)];if(!v)return;
  table($('qualification-footprint-table'),['UTC date','Candidate groups','Candidate granules','Expected cells','Represented cells','Validated usable cells','Unknown cells','Boundary pixels'],v.days.map(d=>[d.date,n(d.acquisition_groups),n(d.candidate_granules),n(d.expected_cells),n(d.represented_cells),n(d.usable_cells),n(d.unknown_cells),n(d.boundary_pixels)]),'Clipped common-grid cells per UTC date. Represented cells are bookkeeping support; validated usable cells require native boundaries, quality and independent review. Candidate groups are not verified complete passes.');
  const links=$('qualification-footprint-downloads');links.replaceChildren();
  for(const p of a.value.parts||[]){if(!p.cohorts.some(c=>c.source===v.cohort.source&&c.version===v.cohort.version))continue;const l=doc.createElement('a');l.textContent=p.start+' → '+p.end+' · exact footprint evidence';l.href=new URL('../'+p.artifact,a.url).href;l.download=p.artifact.split('/').at(-1);links.append(l);}
 }
 async function loadFootprints(id,token,release){
  if(!$('qualification-footprint-select'))return;
  try{const a=await read('footprint-summary/'+id+'.json');if(token!==caseSerial)return;if(a.release_id!==release||a.value.case_id!==id)throw Error('Publication changed; retry for one release.');
   footprintArtifact=a;const control=$('qualification-footprint-select');control.replaceChildren(...a.value.cohorts.map((v,i)=>new Option(cohortLabel(v.cohort),String(i))));control.disabled=!a.value.cohorts.length;
   $('qualification-footprint-status').textContent=a.value.reason||((a.value.validated_observation_opportunity?'Reviewed opportunity':'Pending native geometry and independent review')+' · '+(a.value.scope_complete?'all pilot date/cells represented':'partial pilot support')+'. Unknown support does not mean no fire or no pass.');
   if(a.value.cohorts.length){control.value='0';footprintSupport();}
  }catch(e){if(token===caseSerial)$('qualification-footprint-status').textContent='Footprint support unavailable. '+e.message+' Use Retry; no coverage has been inferred.';}
 }
 async function dailyEvidence(region,cohort,token,release){
  if(!$('qualification-daily-status'))return;
  try{const a=await read(cohort==='recent'?'daily/'+region+'.json':'daily-cohorts/'+region+'.json');if(token!==monthlySerial)return;if(a.release_id!==release||a.value.region!==region)throw Error('Publication or region changed; retry to use one release.');
   const r=cohort==='recent'?a.value.result:a.value.entries.find(r=>r.id===cohort);
   if(r&&r.region!==region)throw Error('Daily cohort region does not match the selected region.');
   if(!r?.metrics){$('qualification-daily-status').textContent='No supported daily model evaluation for this exact cohort. Daily reconstruction is unavailable.';if($('qualification-diagnostic-status'))$('qualification-diagnostic-status').textContent='No exact-cohort daily diagnostics are available in this release.';if($('qualification-neighbors-status'))$('qualification-neighbors-status').textContent='No similar-day evaluation is available for this cohort.';if($('qualification-hybrid-status'))$('qualification-hybrid-status').textContent='No follow-up evidence is available for this cohort.';return;}
   const years=r.test_years||r.folds.map(f=>f.test_year),dates=r.test_dates??r.rows.length,labels={no_harmonization:'Raw identity',annual_ratio:'Annual ratio',monthly_ratio:'Month-specific ratio',hurdle_poisson:'Two-part count model'},pct=v=>v===null||v===undefined?'—':n(v*100)+'%';
   $('qualification-daily-status').textContent='Daily evaluation · '+n(dates)+' test dates · '+years.length+' test-year groups ('+years.join(', ')+') · '+r.versions.join(' / ')+'. Daily reconstruction unavailable.';
   table($('qualification-daily-table'),['Model','Test dates','Median log error ↓','Weighted error ↓','Interval coverage','Interval score ↓','Zero-MODIS positive-VIIRS dates','Zero-recovery log error ↓'],Object.entries(r.metrics).map(([model,m])=>{const z=r.zero_modis_positive_viirs[model];return[labels[model]||model,n(m.n_utc_days),n(m.median_absolute_log_error),pct(m.weighted_absolute_percentage_error),pct(m.coverage),n(m.interval_score),n(z.n_utc_days),n(z.median_absolute_log_error)];}),'Same exact cohort and chronological test dates. Lower error/interval score is better; nominal interval coverage is 90%, not a guarantee. Target: observed S-NPP centroid cell-days per UTC day.');
   table($('qualification-daily-checks'),['Declared check','Measured outcome'],Object.entries(r.checks).map(([key,passed])=>[key.replaceAll('_',' '),passed?'Numerical check met':'Not passed']),'Prespecified daily evaluation checks.');
   table($('qualification-daily-seasons'),['Season','Model','Test dates','Weighted error','Median log error'],Object.entries(r.seasonal).flatMap(([season,models])=>Object.entries(models).map(([model,m])=>[season,labels[model]||model,n(m.n_utc_days),pct(m.weighted_absolute_percentage_error),n(m.median_absolute_log_error)])),'Season-specific errors are retained, including degradation.');
   const diagnostic=r.diagnostics,diagnosticStatus=$('qualification-diagnostic-status'),diagnosticHost=$('qualification-diagnostic-table'),diagnosticLink=$('qualification-diagnostic-download');
   if(diagnosticStatus){
    if(diagnostic?.state==='experimental'){
     if(diagnostic.scientific_admission!==false)throw Error('Diagnostic admission state is invalid.');
     diagnosticStatus.textContent='Held-out S-NPP cell-day diagnostics. The outcome-selected zero-MODIS/positive-VIIRS subset has a descriptive Brier score, not an occurrence calibration score.';
     const groups=[['All test dates',diagnostic.overall],...Object.entries(diagnostic.by_test_year).map(([k,v])=>['Year '+k,v]),...Object.entries(diagnostic.by_season).map(([k,v])=>['Season '+k,v]),['MODIS zero / VIIRS positive',diagnostic.by_modis_state.zero_modis_positive_viirs]];
     table(diagnosticHost,['Group','UTC days','Test-year groups','Mean signed error','Occurrence Brier score','Interval covered / available','Mean interval width'],groups.map(([name,v])=>[name,n(v.n_utc_days),n(v.test_year_groups),n(v.mean_signed_error),n(v.occurrence_brier),n(v.interval_covered_days)+' / '+n(v.interval_days),n(v.interval_mean_width)]),'Two-part daily model · observed sensor activity and empirical interval coverage.');
     diagnosticLink.href=new URL('../'+diagnostic.reproduction_artifact,a.url).href;diagnosticLink.download=diagnostic.reproduction_artifact.split('/').at(-1);diagnosticLink.hidden=false;
    }else diagnosticStatus.textContent='No exact-cohort daily diagnostics are available in this release.';
   }
   const link=$('qualification-daily-download');link.href=r.reproduction_artifact?new URL('../'+r.reproduction_artifact,a.url).href:a.url;link.download=link.href.split('/').at(-1);link.hidden=false;
   const neighborStatus=$('qualification-neighbors-status'),neighbor=r.neighbors;
   if(neighborStatus){
    if(neighbor?.state==='experimental'){
     if(neighbor.estimates_admitted!==false)throw Error('Similar-day admission state is invalid.');
     neighborStatus.textContent='Similar-day retrospective follow-up · '+n(neighbor.test_dates)+' test dates across '+neighbor.test_years.length+' years · daily reconstruction unavailable.';
     const names={...labels,zero_hurdle_annual:'Zero-day hurdle + annual ratio',zero_hurdle_monthly:'Zero-day hurdle + monthly ratio',similar_day_mean:'Similar-day mean'};
     table($('qualification-neighbors-table'),['Model','Test dates','Median log error ↓','Weighted error ↓','Interval coverage','Interval score ↓','Zero-MODIS positive-VIIRS dates','Zero-recovery log error ↓'],Object.entries(neighbor.metrics).map(([model,m])=>{const z=neighbor.zero_modis_positive_viirs[model];return[names[model]||model,n(m.n_utc_days),n(m.median_absolute_log_error),pct(m.weighted_absolute_percentage_error),pct(m.coverage),n(m.interval_score),n(z.n_utc_days),n(z.median_absolute_log_error)];}),'Same cohort and chronological test dates; observed S-NPP cell-days are the reference.');
     table($('qualification-neighbors-checks'),['Screening check','Outcome'],Object.entries(neighbor.checks).map(([key,passed])=>[key.replaceAll('_',' '),passed?'Met':'Not met']),'Project research checks.');
     table($('qualification-neighbors-calibration'),['Probability range','UTC dates','Mean predicted probability','Observed positive fraction'],neighbor.occurrence_calibration.map(v=>[v.probability_bin.map(pct).join(' – '),n(v.n),pct(v.mean_probability),pct(v.observed_positive_fraction)]),'Held-out occurrence calibration · Brier score '+n(neighbor.occurrence_brier));
     const download=$('qualification-neighbors-download');download.href=new URL('../'+neighbor.reproduction_artifact,a.url).href;download.download=download.href.split('/').at(-1);download.hidden=false;
    }else neighborStatus.textContent='No similar-day evaluation is available for this cohort.';
   }
   const status=$('qualification-hybrid-status'),h=r.hybrid;
   if(status){
    if(h?.state!=='experimental'){status.textContent=h?.reason||'No exact-input hybrid experiment is available for this cohort.';return;}
    if(h.estimates_admitted!==false)throw Error('Follow-up admission state is invalid.');
    status.textContent='Retrospective follow-up · '+n(h.test_dates)+' test dates across '+h.test_years.length+' years. The method was proposed after earlier results were inspected.';
    const names={...labels,zero_hurdle_annual:'Zero-day hurdle + annual ratio',zero_hurdle_monthly:'Zero-day hurdle + monthly ratio'};
    hybridChart($('qualification-hybrid-chart'),h,names);
    table($('qualification-hybrid-table'),['Model','Test dates','Median log error ↓','Weighted error ↓','Interval coverage','Interval score ↓','Zero-recovery dates','Zero-recovery log error ↓'],Object.entries(h.metrics).map(([model,m])=>{const z=h.zero_modis_positive_viirs[model];return[names[model]||model,n(m.n_utc_days),n(m.median_absolute_log_error),pct(m.weighted_absolute_percentage_error),pct(m.coverage),n(m.interval_score),n(z.n_utc_days),n(z.median_absolute_log_error)];}),'All models use the same exact cohort and chronological test dates. Intervals use separate zero and positive MODIS calibration; nominal 90% coverage is not guaranteed.');
    table($('qualification-hybrid-checks'),['Candidate','Declared check','Outcome'],Object.entries(h.checks).flatMap(([model,checks])=>Object.entries(checks).map(([key,passed])=>[names[model]||model,key.replaceAll('_',' '),passed?'Numerical check met':'Not passed'])),'Project screening checks for each candidate.');
    const download=$('qualification-hybrid-download');download.href=new URL('../'+h.reproduction_artifact,a.url).href;download.download=download.href.split('/').at(-1);download.hidden=false;
   }
  }catch(e){if(token===monthlySerial){for(const id of ['qualification-daily-table','qualification-daily-checks','qualification-daily-seasons','qualification-diagnostic-table','qualification-hybrid-table','qualification-hybrid-checks','qualification-hybrid-chart','qualification-neighbors-table','qualification-neighbors-checks','qualification-neighbors-calibration'])$(id)?.replaceChildren();for(const id of ['qualification-daily-download','qualification-diagnostic-download','qualification-hybrid-download','qualification-neighbors-download'])if($(id))$(id).hidden=true;$('qualification-daily-status').textContent='Daily research evidence unavailable. '+e.message;if($('qualification-diagnostic-status'))$('qualification-diagnostic-status').textContent='Diagnostics unavailable. Use Retry evidence.';if($('qualification-neighbors-status'))$('qualification-neighbors-status').textContent='Similar-day evidence unavailable. Use Retry evidence.';if($('qualification-hybrid-status'))$('qualification-hybrid-status').textContent='Follow-up evidence unavailable. Use Retry evidence.';}}
 }
 async function transfers(region,token,release){
  loadTransferSupport(region,token,release);
  const host=$('qualification-transfer-table');if(!host)return;host.replaceChildren();$('qualification-transfer-status').textContent='Loading exact collection overlap…';$('qualification-transfer-download').hidden=true;
  $('qualification-platform-downloads')?.replaceChildren();
  try{const [a,b]=await Promise.all([read('transfer-summary/'+region+'.json').catch(()=>null),read('transfer-cohorts/'+region+'.json').catch(()=>null)]);if(token!==monthlySerial)return;if(!a&&!b)throw Error('Transfer evidence unavailable.');if((a&&(a.release_id!==release||a.value.region!==region))||(b&&(b.release_id!==release||b.value.region!==region)))throw Error('Publication or region changed; retry evidence.');
   transferCounts=new Map((b?.value.entries||[]).map(v=>[v.id,v]));if(transferArtifact)transferSupport();
   const records=new Map(),key=v=>JSON.stringify([v.source_cohort,v.target_cohort]);if(a)records.set(key(a.value),a.value);for(const v of b?.value.entries||[])records.set(key(v),v);const label=c=>c.source+' / '+c.version;
   const rows=[...records.values()].map(v=>[label(v.source_cohort),label(v.target_cohort),n(v.eligible_months),n(v.test_groups.forward),n(v.test_groups.backward)]);for(const v of b?.value.unresolved||[])rows.push([v.source+' / pending',v.target+' / pending','—','—','—']);
   table(host,['Source product/version','Target product/version','Complete overlap months','Forward test groups','Backward test groups'],rows,'Direct collection and platform experiments; unavailable standard cohorts remain unknown.');$('qualification-transfer-status').textContent='Compare collection overlap and chronological test support by platform.';
   if(a){$('qualification-transfer-download').href=new URL('../'+a.value.full_evidence,a.url).href;$('qualification-transfer-download').hidden=false;}
   const downloads=$('qualification-platform-downloads');if(downloads&&b)for(const v of b.value.entries){const link=doc.createElement('a');link.textContent=label(v.source_cohort)+' → '+label(v.target_cohort)+' · exact transfer evidence';link.href=new URL('../'+v.full_evidence,b.url).href;link.download=v.full_evidence.split('/').at(-1);downloads.append(link);}
  }catch(e){if(token===monthlySerial)$('qualification-transfer-status').textContent=e.message;}
 }
 async function monthly(){
  if(!$('qualification-monthly'))return;const token=++monthlySerial,region=$('compare-region')?.value||'norcal';
  $('qualification-monthly-metrics')?.replaceChildren();$('qualification-monthly-checks')?.replaceChildren();
  for(const id of ['qualification-daily-table','qualification-daily-checks','qualification-daily-seasons','qualification-diagnostic-table','qualification-hybrid-table','qualification-hybrid-checks','qualification-hybrid-chart','qualification-neighbors-table','qualification-neighbors-checks','qualification-neighbors-calibration'])$(id)?.replaceChildren();if($('qualification-daily-download'))$('qualification-daily-download').hidden=true;if($('qualification-diagnostic-download'))$('qualification-diagnostic-download').hidden=true;if($('qualification-diagnostic-status'))$('qualification-diagnostic-status').textContent='Loading the selected exact-cohort diagnostics…';if($('qualification-hybrid-download'))$('qualification-hybrid-download').hidden=true;if($('qualification-neighbors-download'))$('qualification-neighbors-download').hidden=true;if($('qualification-neighbors-status'))$('qualification-neighbors-status').textContent='Loading the selected similar-day evaluation…';if($('qualification-hybrid-status'))$('qualification-hybrid-status').textContent='Loading the selected exact-cohort follow-up…';if($('qualification-daily-status'))$('qualification-daily-status').textContent='Loading the selected exact-cohort daily evaluation…';
  transferArtifact=null;transferCounts=new Map();resetSupport('transfer-support');$('qualification-transfer-table')?.replaceChildren();if($('qualification-transfer-status'))$('qualification-transfer-status').textContent='';if($('qualification-transfer-download'))$('qualification-transfer-download').hidden=true;
  if($('qualification-collection-pilot-status'))$('qualification-collection-pilot-status').textContent='Loading collection comparison…';if($('qualification-collection-pilot-visual'))$('qualification-collection-pilot-visual').hidden=true;$('qualification-collection-pilot-chart')?.replaceChildren();$('qualification-collection-pilot-summary')?.replaceChildren();$('qualification-collection-pilot-platform')?.replaceChildren();$('qualification-collection-pilot-days')?.replaceChildren();if($('qualification-collection-pilot-download')){$('qualification-collection-pilot-download').removeAttribute('href');$('qualification-collection-pilot-download').hidden=true;}
  $('qualification-platform-downloads')?.replaceChildren();
  $('qualification-monthly-status').textContent='Checking the current qualification evidence…';$('qualification-monthly-support').textContent='';$('qualification-monthly-table').replaceChildren();$('qualification-monthly-values').replaceChildren();$('qualification-monthly-chart').replaceChildren();$('qualification-monthly-chart').setAttribute('hidden','');$('qualification-monthly-download').hidden=true;$('qualification-readiness-download').hidden=true;$('qualification-input-download').hidden=true;
  if($('qualification-monthly-source'))$('qualification-monthly-source').textContent='';if($('qualification-monthly-source-download'))$('qualification-monthly-source-download').hidden=true;
  try{let [a,b,c]=await Promise.all([read('monthly/'+region+'.json'),read('readiness.json'),$('qualification-cohort')?read('monthly-cohorts/'+region+'.json').catch(()=>null):Promise.resolve(null)]);if(token!==monthlySerial)return;if(a.release_id!==b.release_id||(c&&c.release_id!==a.release_id))throw Error('Publication changed while loading; retry to use one release.');let value=a.value;const r=b.value.regions[region],control=$('qualification-cohort');
   if(control){const previous=control.value,entries=c?.value.entries||[];control.replaceChildren(new Option('Recent cohort · 61.03 / 2','recent'),...entries.map(entry=>new Option('Archive cohort · '+entry.cohorts[0].versions.join(' / '),entry.id)));control.value=entries.some(e=>e.id===previous)?previous:'recent';const chosen=entries.find(e=>e.id===control.value);if(chosen){value=chosen;a=c;}}
   $('qualification-monthly-status').textContent=value.state==='protocol-approval-pending'?'Monthly comparison: predictions unavailable for this cohort.':value.state==='experimental-ai-reviewed'?'Retrospective monthly comparison.':'Monthly comparison evidence.';
   table($('qualification-monthly-table'),['Readiness','Evidence'],Object.entries(value.cohort_readiness||r.states).map(([k,v])=>[k.replaceAll('_',' '),(v.passed?'Passed: ':'Pending: ')+v.reason]),region+' · selected exact-cohort readiness states');
   $('qualification-monthly-support').textContent=(value.cohorts||[]).map(c=>c.versions.join(' / ')+': '+c.complete_months+' complete months').join(' · ')+' · 36 training months, 18 calibration months, and three later test years required for each exact cohort.';
   const source=value.source_provenance,sourceText=$('qualification-monthly-source'),sourceLink=$('qualification-monthly-source-download');
   if(sourceText)sourceText.textContent=source?.status==='verified'?'Original request files and eligible daily cell counts checked for this exact cohort · '+n(source.eligible_months)+' months and '+n(source.eligible_utc_days_checked)+' UTC days.':source?.status==='partial'?'Original-file checks are incomplete for this cohort.':'Original-file checks are pending for this cohort.';
   if(sourceLink&&source?.full_evidence){sourceLink.href=new URL('../'+source.full_evidence,a.url).href;sourceLink.download=source.full_evidence.split('/').at(-1);sourceLink.hidden=false;}
   link('qualification-monthly-download',a);link('qualification-readiness-download',b);transfers(region,token,a.release_id);collectionPilot(region,token,a.release_id);dailyEvidence(region,control?.value||'recent',token,a.release_id);if(value.reproduction_artifact){const url=new URL('../'+value.reproduction_artifact,a.url);$('qualification-input-download').href=url.href;$('qualification-input-download').hidden=false;if(value!==a.value){$('qualification-monthly-download').href=url.href;$('qualification-monthly-download').download=url.pathname.split('/').at(-1);}}
   const ev=value.result?.evaluation?.forward;
   if(ev?.raw&&ev?.adjusted&&$('qualification-monthly-metrics')){
    const pct=v=>v===null||v===undefined?'—':n(v*100)+'%',raw=ev.raw,adjusted=ev.adjusted,
     metrics=[['Median absolute log error ↓',n(raw.median_absolute_log_error),n(adjusted.median_absolute_log_error)],['Weighted absolute percentage error ↓',pct(raw.weighted_absolute_percentage_error),pct(adjusted.weighted_absolute_percentage_error)],['Signed error · centroid cell-days',n(raw.signed_error),n(adjusted.signed_error)],['Nominal 90% interval coverage',pct(raw.coverage),pct(adjusted.coverage)],['Mean interval width · centroid cell-days ↓',n(raw.mean_interval_width),n(adjusted.mean_interval_width)],['Interval score ↓',n(raw.interval_score),n(adjusted.interval_score)]];
    table($('qualification-monthly-metrics'),['Chronological monthly test metric','Raw MODIS baseline','Selected adjustment'],metrics,n(ev.rows.length)+' test months across '+n(ev.folds?.length||0)+' later-year groups · same observed VIIRS reference and calibrated baseline. Lower errors and interval score are better; coverage is empirical, not guaranteed.');
    const labels={test_support:'At least three supported test-year groups',log_error_improvement:'At least 10% lower median log error',wape:'Weighted error no worse than raw',interval_coverage:'At least 85% empirical coverage',interval_score:'Interval score no worse than raw'};
    table($('qualification-monthly-checks'),['Proposed project research gate','Numerical outcome'],Object.entries(ev.checks).map(([key,passed])=>[labels[key]||key,passed?'Met':'Not met']),'Earlier-year training, two calibration years and later test years.');
   }
   if(ev && !ev.rows.length){
    $('qualification-monthly-support').textContent+=' No supported test-year predictions for this cohort.';
    table($('qualification-monthly-values'),['Test year','Why unavailable'],ev.skipped.map(r=>[r.year,r.reasons.join(', ').replaceAll('-',' ')]),'Chronological evaluation support.');
   }
   if(ev?.rows?.length){
    const svg=$('qualification-monthly-chart'),ns='http://www.w3.org/2000/svg',rows=ev.rows;svg.removeAttribute('hidden');
    const add=(tag,attrs,text)=>{const e=doc.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;svg.append(e);return e;};
    const max=Math.max(1,...rows.flatMap(r=>[r.interval[1],r.reference,r.prediction,r.modis]))*1.1,x=i=>60+i*800/Math.max(1,rows.length-1),y=v=>265-v/max*230;
    add('title',{},'Chronological test predictions and calibrated nominal 90% intervals; VIIRS is an observed reference, not fire truth.');
    for(let i=0;i<=4;i++){const v=max*i/4;add('line',{x1:60,x2:860,y1:y(v),y2:y(v),stroke:'#ccd9df'});add('text',{x:52,y:y(v)+4,'text-anchor':'end',fill:'#31536a','font-size':12},n(v));}
    rows.forEach((r,i)=>{add('line',{x1:x(i),x2:x(i),y1:y(r.interval[0]),y2:y(r.interval[1]),stroke:'#287446','stroke-width':4,opacity:.35});for(const[field,color]of [['modis','#687c88'],['reference','#2457d6'],['prediction','#287446']]){const c=add('circle',{cx:x(i),cy:y(r[field]),r:3,fill:color});const title=doc.createElementNS(ns,'title');title.textContent=r.date+' · '+field+' '+n(r[field])+(field==='prediction'?' · 90% interval '+r.interval.map(n).join(' – '):'');c.append(title);}if(i===0||i===rows.length-1||r.month===1)add('text',{x:x(i),y:287,'text-anchor':'middle',fill:'#31536a','font-size':11},r.date);});
    add('text',{x:60,y:312,fill:'#31536a','font-size':12},'Gray: raw MODIS · Blue: observed VIIRS · Green: estimated monthly cell-days · bars: nominal 90% intervals');
    table($('qualification-monthly-values'),['Month','Raw MODIS','Observed VIIRS','Estimate','90% interval'],ev.rows.map(r=>[r.date,n(r.modis),n(r.reference),n(r.prediction),r.interval.map(n).join(' – ')]),'Exact chronological v2 predictions and evaluated intervals');
   }
  }catch(e){if(token===monthlySerial){$('qualification-monthly-status').textContent=e.message+' Use Retry to check again; existing v1 evidence is separate.';if($('qualification-collection-pilot-status'))$('qualification-collection-pilot-status').textContent='Collection comparison unavailable. Use Retry evidence.';}}
 }
 function step(){
  const i=Number($('qualification-acquisition').value),g=acquisitions[i];if(!g)return;
  $('qualification-prev').disabled=i===0;$('qualification-next').disabled=i===acquisitions.length-1;
  $('qualification-acquisition-detail').textContent=g.start_utc+' → '+(g.end_utc||'unknown end')+' · '+g.product+' '+g.version+' · '+g.group_kind+' · native '+g.native_status+' · opportunity '+g.opportunity_state+'. '+(g.missing_reasons.length?'Missing: '+g.missing_reasons.join(', ')+'. ':'');
  $('qualification-acquisition-hashes').textContent='Native SHA-256 '+(g.file_sha256||'missing')+' · Geolocation SHA-256 '+(g.geolocation_sha256||'missing')+'.';
  const coverage=coverageSummary?.acquisitions.find(a=>a.producer_id===g.producer_id),host=$('qualification-envelope-detail');
  if(host)host.textContent=coverage?n(coverage.intersected_cells)+' of '+n(coverageSummary.n_cells)+' fully interior pilot cells intersect this candidate granule envelope. Pixel quality and usable observation opportunity remain unknown.':'No supported candidate-envelope geometry for this acquisition. Observation opportunity remains unknown.';
  contextAcquisition();
  const svg=$('qualification-timeline'),ns='http://www.w3.org/2000/svg';svg.replaceChildren();
  const el=(tag,attrs,text)=>{const x=doc.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))x.setAttribute(k,v);if(text!==undefined)x.textContent=text;svg.append(x);return x;};
  el('title',{},'Candidate acquisitions; intervals between candidates remain unknown');
  const first=Math.min(...acquisitions.map(x=>Date.parse(x.start_utc))),last=Math.max(...acquisitions.map(x=>Date.parse(x.end_utc||x.start_utc))),width=Math.max(1,last-first),x=t=>120+(Date.parse(t)-first)/width*730;
  ['MOD14','MYD14','VNP14IMG'].forEach((p,row)=>{const y=35+row*42;el('text',{x:5,y:y+5,fill:'#31536a','font-size':14},p);el('line',{x1:120,x2:860,y1:y,y2:y,stroke:'#d2dade','stroke-width':10});acquisitions.forEach((a,index)=>{if(a.product!==p)return;const bar=el('line',{x1:x(a.start_utc),x2:Math.max(x(a.end_utc||a.start_utc),x(a.start_utc)+2),y1:y,y2:y,stroke:index===i?'#a75500':'#136a7c','stroke-width':index===i?16:10});const title=doc.createElementNS(ns,'title');title.textContent=a.start_utc+' · '+a.product+' · native '+a.native_status;bar.append(title);});});
  el('text',{x:120,y:172,fill:'#31536a','font-size':12},new Date(first).toISOString().slice(0,10)+' UTC');el('text',{x:860,y:172,fill:'#31536a','font-size':12,'text-anchor':'end'},new Date(last).toISOString().slice(0,10)+' UTC');
 }
 function conditions(){
  const host=$('qualification-condition-table');if(!host)return;host.replaceChildren();
  const tolerance=$('qualification-condition-threshold')?.value||'90',ev=conditionSummary?.experiments[tolerance];if(!ev)return;
  table(host,['Matched sampled states','Cell/acquisition pairs'],Object.entries(ev.sampled_state_matrix).map(([k,v])=>[k,n(v)]),'All-state matching · '+tolerance+' minute endpoint limit · '+n(ev.positive_pairs_with_cloud_sample)+' positive pairs have a cloud sample; '+n(ev.positive_pairs_with_unknown_sample)+' have an unknown sample. Conditions do not establish physical causes.');
 }
 function contextAcquisition(){
  const host=$('qualification-context-acquisition');if(!host)return;
  const g=acquisitions[Number($('qualification-acquisition')?.value)],item=contextSummary?.acquisitions.find(a=>a.producer_id===g?.producer_id);
  host.textContent=item?(item.status==='extracted'?'Selected acquisition: '+n(item.extracted_samples)+' native pixels · '+n(item.illumination_samples.day||0)+' day · '+n(item.illumination_samples.night||0)+' night · '+n(item.illumination_samples.unknown||0)+' unknown solar angle.':'Selected acquisition: '+(item.unavailable_reason||'Native angle evidence unavailable.')):'';
 }
 function nativeContext(){
  const host=$('qualification-context-table'),svg=$('qualification-context-chart');if(!host||!svg||!contextSummary)return;
  const subset=$('qualification-context-subset').value,tolerance=$('qualification-context-threshold').value,
   selected=contextSummary.subsets[subset],ev=selected?.thresholds[tolerance];
  svg.replaceChildren();svg.setAttribute('hidden','');host.replaceChildren();if(!ev)return;
  const m=ev.metrics,u=ev.group_uncertainty,percent=v=>v===null||v===undefined?'Undefined':n(v*100)+'%';
  $('qualification-context-status').textContent=selected.label+' · '+n(selected.pixel_samples)+' native pixel samples · '+n(m.n_pairs)+' usable cell/acquisition pairs · '+n(m.positive_union_pairs)+' positive union pairs · '+n(u.independent_groups)+' connected acquisition groups. '+(m.positive_union_pairs?'Positive Jaccard '+percent(m.positive_jaccard)+'.':'Positive overlap is undefined because there are no positive pairs.');
  table(host,['Observed sampled-state comparison','Pairs'],[['Both detected',n(m.both_detected)],['MODIS detected only',n(m.modis_only)],['VIIRS detected only',n(m.viirs_only)],['Both without detection',n(m.both_without_detection)],['Positive Jaccard',percent(m.positive_jaccard)],['VIIRS overlap of MODIS',n(m.viirs_overlap_of_modis.numerator)+' / '+n(m.viirs_overlap_of_modis.denominator)],['MODIS overlap of VIIRS',n(m.modis_overlap_of_viirs.numerator)+' / '+n(m.modis_overlap_of_viirs.denominator)],['Connected-group Jaccard interval',u.positive_jaccard_interval?u.positive_jaccard_interval.map(percent).join(' – '):'Unavailable: '+(u.reason||'no supported positive bootstrap samples')]],selected.label+' · '+tolerance+' minute endpoint limit · sampled agreement, not fire-truth accuracy');
  table($('qualification-context-comparison'),['Subset','Native pixels','Paired cells/acquisitions','Positive union','Positive Jaccard','Acquisition groups'],Object.values(contextSummary.subsets).map(s=>{const e=s.thresholds[tolerance];return[s.label,n(s.pixel_samples),n(e.metrics.n_pairs),n(e.metrics.positive_union_pairs),percent(e.metrics.positive_jaccard),n(e.group_uncertainty.independent_groups)];}),'Each subset is independently reaggregated and rematched. Pixel and pair counts are dependent; groups describe shared acquisition support.');
  if(m.n_pairs){
   const ns='http://www.w3.org/2000/svg',add=(tag,attrs,text)=>{const el=doc.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))el.setAttribute(k,v);if(text!==undefined)el.textContent=text;svg.append(el);return el;};
   const bars=[['Both detected',m.both_detected,'#276b81'],['MODIS only',m.modis_only,'#a75500'],['VIIRS only',m.viirs_only,'#6952a2'],['Both without detection',m.both_without_detection,'#687c88']],max=Math.max(1,...bars.map(b=>b[1]));
   add('title',{},selected.label+' · sampled pair counts at '+tolerance+' minutes; zero-based count scale.');
   bars.forEach(([label,value,color],i)=>{const y=28+i*55;add('text',{x:8,y:y+18,fill:'#15354b','font-size':15},label);add('rect',{x:225,y,width:value/max*570,height:28,fill:color});add('text',{x:Math.min(820,235+value/max*570),y:y+19,fill:'#15354b','font-size':15},n(value));});
   add('text',{x:225,y:263,fill:'#31536a','font-size':13},'Paired sampled cell/acquisitions · zero-based scale · '+n(u.independent_groups)+' acquisition groups');svg.removeAttribute('hidden');
  }
  contextAcquisition();
 }
 async function loadNativeContext(id,token,release){
  if(!$('qualification-context-status'))return;
  try{const a=await read('native-context-summary/'+id+'.json');if(token!==caseSerial)return;if(a.release_id!==release)throw Error('Publication changed; retry for one release.');contextSummary=a.value;nativeContext();const link=$('qualification-context-download');link.href=new URL('../'+a.value.full_evidence,a.url).href;link.hidden=false;}
  catch(e){if(token===caseSerial)$('qualification-context-status').textContent='Native angle evidence unavailable. '+e.message+' Use Retry; no day/night values have been inferred.';}
 }
 async function candidates(){
  footprintArtifact=null;resetSupport('footprint');
  contextSummary=null;for(const id of ['qualification-context-table','qualification-context-comparison','qualification-context-chart'])$(id)?.replaceChildren();$('qualification-context-chart')?.setAttribute('hidden','');if($('qualification-context-download'))$('qualification-context-download').hidden=true;if($('qualification-context-status'))$('qualification-context-status').textContent='Loading native solar/viewing angles and raw geolocation flags…';if($('qualification-context-acquisition'))$('qualification-context-acquisition').textContent='';
  if(!$('qualification-acquisitions'))return;const token=++caseSerial,id=$('qualification-case').value;acquisitions=[];coverageSummary=null;conditionSummary=null;$('qualification-condition-table')?.replaceChildren();if($('qualification-envelope-detail'))$('qualification-envelope-detail').textContent='';for(const key of ['qualification-coverage-download','qualification-condition-download'])if($(key))$(key).hidden=true;$('qualification-acquisition-table').replaceChildren();$('qualification-prev').disabled=true;$('qualification-next').disabled=true;$('qualification-acquisition').replaceChildren();$('qualification-acquisition-detail').textContent='';$('qualification-acquisition-hashes').textContent='';$('qualification-timeline').replaceChildren();$('qualification-opportunity-download').hidden=true;
  $('qualification-candidate-status').textContent='Loading candidate acquisitions, including those without FIRMS detections…';
  try{const a=await read('opportunity/'+id+'.json');if(token!==caseSerial)return;caseArtifact=a;acquisitions=a.value.acquisitions.slice().sort((a,b)=>a.start_utc.localeCompare(b.start_utc)||a.product.localeCompare(b.product));
   $('qualification-candidate-status').textContent=acquisitions.length+' candidate acquisitions · inventory '+(a.value.inventory_complete?'complete':'incomplete')+' · full-cell opportunity unknown · no-pass disabled.';
   loadNativeContext(id,token,a.release_id);
   loadFootprints(id,token,a.release_id);
   $('qualification-acquisition').replaceChildren(...acquisitions.map((a,i)=>new Option(a.start_utc+' · '+a.product+' · '+a.native_status,String(i))));
   table($('qualification-acquisition-table'),['UTC interval','Product/version','Native file','Group','Opportunity'],acquisitions.map(a=>[a.start_utc+' → '+(a.end_utc||'unknown'),a.product+' / '+a.version,a.native_status,a.group_kind,a.opportunity_state]),'Candidate inventory, including acquisitions without recorded fire detections. Gray gaps are unknown.');link('qualification-opportunity-download',a);step();
   try{const [c,d]=await Promise.all([read('coverage-summary/'+id+'.json'),read('disagreement-summary/'+id+'.json')]);if(token!==caseSerial)return;if(c.release_id!==a.release_id||d.release_id!==a.release_id)throw Error('Publication changed; retry for one release.');coverageSummary=c.value;conditionSummary=d.value;
    for(const[key,artifact]of [['qualification-coverage-download',c],['qualification-condition-download',d]])if($(key)){$(key).href=new URL('../'+artifact.value.full_evidence,artifact.url).href;$(key).hidden=false;}step();conditions();
   }catch(e){if(token===caseSerial&&$('qualification-envelope-detail'))$('qualification-envelope-detail').textContent='Additional geometry or condition evidence unavailable. '+e.message;}
  }catch(e){if(token===caseSerial)$('qualification-candidate-status').textContent=e.message+' No absence or coverage classification has been substituted.';}
 }
 async function readiness(){if(!$('qualification-criteria'))return;try{const a=await read('readiness.json');table($('qualification-criteria'),['Criterion','Status','Still required'],a.value.criteria.map(c=>[c.criterion_id+' · '+c.title,c.status,c.unresolved_requirements]),'Mentor criteria: engineering completion does not certify scientific acceptance.');link('qualification-criteria-download',a);}catch(e){$('qualification-criteria').textContent=e.message;}}
 $('qualification-monthly-retry')?.addEventListener('click',monthly);$('compare-region')?.addEventListener('change',monthly);
 $('qualification-cohort')?.addEventListener('change',monthly);
 const caseControl=$('qualification-case');
 if(caseControl){
  const initial=new URLSearchParams(location.search).get('native_case')||$('native-case-select')?.value;
  if(['park-2024','grove-2025'].includes(initial))caseControl.value=initial;
  const synchronize=id=>{if(['park-2024','grove-2025'].includes(id)&&caseControl.value!==id){caseControl.value=id;candidates();}};
  win.addEventListener('fireatlas:select-validity-case',e=>synchronize(e.detail.id));
  win.addEventListener('fireatlas:validity-report',e=>synchronize(e.detail.case_id||e.detail.id));
  caseControl.addEventListener('change',()=>{candidates();const control=$('native-case-select');if(control&&control.value!==caseControl.value){control.value=caseControl.value;control.dispatchEvent(new Event('change',{bubbles:true}));}else{const url=new URL(location.href);url.searchParams.set('native_case',caseControl.value);history.replaceState(null,'',url);win.FireAtlasContext?.apply();}});
 }
 $('qualification-candidate-retry')?.addEventListener('click',candidates);$('qualification-acquisition')?.addEventListener('change',step);
 $('qualification-condition-threshold')?.addEventListener('change',conditions);
 $('qualification-context-subset')?.addEventListener('change',nativeContext);$('qualification-context-threshold')?.addEventListener('change',nativeContext);
 if($('qualification-condition-threshold')&&$('native-threshold'))$('qualification-condition-threshold').value=$('native-threshold').value;
 $('native-threshold')?.addEventListener('change',()=>{if($('qualification-condition-threshold'))$('qualification-condition-threshold').value=$('native-threshold').value;conditions();});
 for(const[id,delta]of [['qualification-prev',-1],['qualification-next',1]])$(id)?.addEventListener('click',()=>{$('qualification-acquisition').value=String(Number($('qualification-acquisition').value)+delta);step();});
 $('qualification-footprint-select')?.addEventListener('change',footprintSupport);
 $('qualification-transfer-support-select')?.addEventListener('change',transferSupport);
 monthly();candidates();readiness();
}
if(window.FireAtlasPanels)window.FireAtlasPanels.define('qualification',mount);
if(!document.body.dataset.workspace)document.addEventListener('DOMContentLoaded',()=>mount({document,window,fetch:window.fetch.bind(window)}));
})();
