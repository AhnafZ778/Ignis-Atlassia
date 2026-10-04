/* Scientific conversation and private notebook; never injects model HTML or executes model code. */
(() => {
  'use strict';
  let busy=false,generation=0,registerQueue=Promise.resolve();
  let root,ready=false,caps=null,revision=0,activeRun=null,resultIds=[],attachments=[],lastAnswer=null,lastEvidence=null,audio=null,recorder=null,recordTimeout=null,viewTimer=null,registerTimer=null,applying=false;
  const page=()=>document.body.dataset.page==='assistant';
  const $=id=>document.getElementById(id),V=()=>window.FireAtlasViews;
  const element=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=String(text);if(cls)n.className=cls;return n;};
  async function api(path,body,method=body===undefined?'GET':'POST'){
    const timeout=AbortSignal.timeout(20000),r=await fetch(new URL('./api/assistant/'+path,document.baseURI),{method,credentials:'same-origin',cache:'no-store',signal:timeout,headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
    let value;try{value=await r.json();}catch{throw Error('Local assistant service required. This static page retains the scientific visualizations but cannot run private investigations.');}
    if(!r.ok)throw Error(value.error||'Assistant request failed.');return value;
  }
  function context(){const c={...V().context(),revision};Object.keys(c).forEach(k=>{if(c[k]===undefined)delete c[k];});return c;}
  function status(text){$('assistant-turn-status').textContent=text;const pending=$('assistant-pending');if(pending)pending.textContent=text;}
  function scrollConversation(){const list=$('assistant-messages');list.scrollTop=list.scrollHeight;}
  function message(text,type='note'){const n=element('article',null,'assistant-message '+type);n.append(element('p',text));$('assistant-messages').append(n);scrollConversation();return n;}
  function controls(busy){if($('assistant-depth'))$('assistant-depth').disabled=busy||!ready;$('assistant-stop').disabled=!busy;$('assistant-send').disabled=busy||!caps?.ai_available||!ready;root.querySelectorAll('[data-investigation]').forEach(b=>b.disabled=busy||!ready);if(page()){$('assistant-capture').disabled=busy||!ready||!V().adapter()?.state?.().figure_ready;for(const id of ['mission-search-archive','mission-compare','mission-finish'])if($(id))$(id).disabled=busy||!ready;}}
  async function register(take=false){
    if(!ready)return;const snapshot=context(),view={...V().state(),take_control:take};
    const task=async()=>{if(snapshot.revision!==revision)return;const response=await api('views',{context:snapshot,view});if(snapshot.revision===revision)revision=Math.max(revision,response.context.revision);return response;};
    const queued=registerQueue.catch(()=>{}).then(task);registerQueue=queued;return queued;
  }
  async function stop(){generation++;busy=false;if(audio){audio.pause();audio=null;}const cancelled=activeRun;activeRun=null;document.getElementById('assistant-pending')?.remove();controls(false);status('Stopped; completed evidence remains saved.');if(cancelled)await api('runs/'+encodeURIComponent(cancelled)+'/cancel',{}).catch(()=>{});}
  function fail(error){
    const raw=error.message||String(error);
    let title='The investigation could not finish',explanation=raw,task='availability',action='Check imported data';
    if(/Request allowance reached/i.test(raw)){title='This workspace is temporarily limited';explanation='Too many workspace requests were made in a short period. Wait before trying again. The observation map and existing records remain readable.';task=null;action=null;}
    else if(/JSON pointer|concrete scalar|unavailable evidence|verify its|validate its/i.test(raw)){title='The AI could not verify its answer';explanation='A source reference could not be checked, so that answer was not published. Ask a narrower question or open a stored-data task to inspect the records directly.';task='missingness';action='Check observation gaps';}
    else if(/before capturing|before attaching|no registered figure/i.test(raw)){title='Open a map before attaching a figure';explanation='Choose “Open daily map” to calculate an observation map. You can then attach its cell schematic to your next question.';task='replay';action='Open daily map';}
    else if(/one UTC month/i.test(raw)){title='This comparison needs one calendar month';explanation='Your study spans more than one UTC month. Select “Limit to first month”, then run the comparison again. The daily replay can still use the full study window.';action='Limit to first month';task=null;}
    else if(/quota|free model capacity|rate limit|throttle|AI provider could not/i.test(raw)){title=caps?.free_only?'Free AI is temporarily unavailable':'AI is temporarily unavailable';explanation='The provider could not complete this request. Try the AI later. Maps, record tables and observation-gap tasks still work directly from the archive.';task='replay';action='Open daily map without AI';}
    const card=element('article',null,'assistant-message error');card.append(element('h3',title),element('p',explanation));
    if(page()&&ready&&action){const b=element('button',action,'assistant-error-action');b.type='button';b.addEventListener('click',()=>task?investigate(task):$('assistant-month-window').click());card.append(b);}
    if(lastEvidence&&window.FireAtlasVisuals){const b=element('button','View last checked calculation ↗');b.type='button';b.onclick=()=>window.FireAtlasVisuals.open(lastEvidence);card.append(b);}
    $('assistant-messages').append(card);scrollConversation();status(title+'. See the explanation above.');
  }
  async function investigate(operation,args={},text,options={}){
    if(!ready){fail(Error('Connect to the local analysis service before investigating.'));return;}
    if(busy){status('An investigation is already running. Select Stop before starting another.');return;}
    if(audio){audio.pause();audio=null;}
    const taskLabels={replay:'Show daily detections for the selected study.',missingness:'Check missing records in the selected study.',research:'Compare MODIS and VIIRS within this study.',availability:'Show the project’s imported data inventory.'};
    const question=text|| (operation?taskLabels[operation]||'Run stored-data task: '+operation.replaceAll('_',' '):$('assistant-question').value.trim());
    if(!question)return;
    if(!options.quiet&&$('assistant-chat-welcome'))$('assistant-chat-welcome').hidden=true;
    window.dispatchEvent(new CustomEvent('fireatlas:investigation-start'));
    let cfg=context();busy=true;const turn=++generation;controls(true);status(operation?'Reading stored evidence…':'Preparing your investigation…');if(!options.quiet){message(question,'question');const pending=element('article',operation?'Reading the archive…':'Checking the selected study and evidence…','mission-pending');pending.id='assistant-pending';pending.setAttribute('role','status');$('assistant-messages').append(pending);scrollConversation();}

    try{
      await register();if(turn!==generation)return;cfg=context();
      const run=await api('runs',{nonce:crypto.randomUUID(),context:cfg,view:V().state(),message:question,operation,arguments:args,image_ids:attachments});
      if(turn!==generation){await api('runs/'+run.id+'/cancel',{}).catch(()=>{});return;}activeRun=run.id;let after=0;
      while(activeRun===run.id&&turn===generation){
        const [receipt,events]=await Promise.all([api('runs/'+run.id),api('runs/'+run.id+'/events?after='+after)]);
        if(turn!==generation)return;
        for(const e of events.events){after=e.id;if(e.message)status(e.message);}
        if(receipt.status==='completed'){
          activeRun=null;attachments=[];$('assistant-pending')?.remove();
          if(revision!==cfg.revision){message('The result belongs to earlier study settings. It is saved in the notebook; the current map was not changed.');break;}
          await answer(receipt.body,false,options.quiet,operation?'task':'conversation');status('Evidence ready');await notebook();break;
        }
        if(['failed','cancelled'].includes(receipt.status)){activeRun=null;window.dispatchEvent(new CustomEvent('fireatlas:investigation-failed',{detail:receipt}));if(receipt.status==='failed')throw Error(receipt.body.error||'Investigation failed.');status('Investigation stopped.');break;}
        await new Promise(resolve=>setTimeout(resolve,1000));
      }
    }catch(e){if(turn!==generation)return;activeRun=null;$('assistant-pending')?.remove();window.dispatchEvent(new CustomEvent('fireatlas:investigation-failed',{detail:{operation,context:cfg,error:e.message}}));fail(e);}finally{if(turn===generation){busy=false;$('assistant-pending')?.remove();controls(false);refreshBudget();}}
  }
  async function showEvidence(id,presentation='inspect'){const r=await api('evidence/'+encodeURIComponent(id));if(r.kind!=='evidence')throw Error('This item is not a scientific calculation.');lastEvidence={id:r.id,...r.body,presentation};window.dispatchEvent(new CustomEvent('fireatlas:evidence',{detail:lastEvidence}));return lastEvidence;}
  async function answer(a,fromHistory=false,quiet=false,presentation='conversation'){
    lastAnswer=a;
    const m=element('article',null,'assistant-message');m.append(element('span',fromHistory?'Saved finding · previous investigation':a.kind,'assistant-kicker'),element('h3',a.title),element('p',a.summary));if(fromHistory&&a.context)m.append(element('p',`${a.context.start} → ${a.context.end} UTC · area ${a.context.bbox?.join(', ')}`,'assistant-help'));if(a.model)m.append(element('p',`${a.provider==='aiand'?'AI&':a.provider} · ${a.model}${a.free_only?' · free-only':''}${a.analysis_depth?' · '+a.analysis_depth:''}${typeof a.estimated_cost_usd==='number'?' · estimated $'+a.estimated_cost_usd.toFixed(4):''}`,'assistant-help'));
    if(a.claims?.length){const grid=element('div',null,'assistant-claim-grid');a.claims.forEach(c=>{const card=element('div',null,'assistant-claim');card.append(element('span',c.label),element('strong',typeof c.value==='number'?c.value.toLocaleString():c.value),element('span',c.unit));const b=element('button','Inspect source value');b.type='button';b.addEventListener('click',()=>inspect(c.result_id,c.path,m));card.append(b);if(c.denominator)card.append(element('span',`Denominator: ${c.denominator.observed_cell_days} observed cell-days · ${c.denominator.mask_status}`));grid.append(card);});m.append(grid);}
    const actions=element('div',null,'assistant-message-actions');
    if(window.FireAtlasVisuals)for(const id of a.evidence_ids||[]){const button=element('button','Explain visually ↗');button.type='button';button.addEventListener('click',async()=>{try{const r=await api('evidence/'+encodeURIComponent(id));if(r.kind!=='evidence')throw Error('This item has no scientific calculation.');window.FireAtlasVisuals.open({id:r.id,...r.body});}catch(e){fail(e);}});actions.append(button);}
    for(const id of a.evidence_ids||[]){const button=element('button','Open calculation');button.addEventListener('click',()=>showEvidence(id).catch(fail));actions.append(button);}
    if(!fromHistory)for(const action of a.actions||[]){const button=element('button','Show '+action.destination);button.addEventListener('click',()=>applyAction(action).catch(fail));actions.append(button);}
    if(caps.voice?.available){const speak=element('button','Read checked summary');speak.addEventListener('click',async()=>{try{if(audio)audio.pause();const turn=revision;const out=await api('voice/synthesize',{answer_id:a.notebook_id});if(turn!==revision)return;audio=new Audio('data:audio/mpeg;base64,'+out.data);await audio.play();}catch(e){fail(e);}});actions.append(speak);}
    if(page()){for(const destination of ['replay','overlap','candidates','sources']){const link=element('button','Go to '+destination);link.addEventListener('click',()=>navigate(destination,a.evidence_ids?.[0]).catch(fail));actions.append(link);}}
    if(a.places?.length)placeChoices({choices:a.places},m);
    for(const id of a.figure_ids||[]){const record=await api('evidence/'+encodeURIComponent(id));if(record.kind==='annotated_figure'){const img=element('img',null,'assistant-figure');img.src='data:image/png;base64,'+record.body.data;img.alt=record.body.caption;const link=element('a','Download annotated figure');link.href=img.src;link.download='fireatlas-evidence-callout.png';m.append(img,element('p',record.body.caption,'assistant-help'),link);}}
    m.append(actions);
    if(a.limitations?.length){const d=element('details');d.append(element('summary','Interpretation limits'),element('p',a.limitations.join(' ')));m.append(d);}
    if(!quiet){const list=$('assistant-messages');list.append(m);list.scrollTop+=m.getBoundingClientRect().top-list.getBoundingClientRect().top-12;}
    if(!fromHistory&&a.evidence_ids?.length){resultIds=a.evidence_ids;await showEvidence(a.evidence_ids.at(-1),presentation);}
    if(!fromHistory&&a.visualizations?.length&&window.FireAtlasVisuals){const visual=a.visualizations[0],r=await api('evidence/'+encodeURIComponent(visual.result_id));if(r.kind==='evidence')window.FireAtlasVisuals.open({id:r.id,...r.body},visual.kind==='workflow'?'workflow':'auto');}
    if(!fromHistory&&a.actions?.length){for(let i=0;i<a.actions.length;i++){sessionStorage.setItem('fireatlas-action-queue',JSON.stringify(a.actions.slice(i+1)));const outcome=await applyAction(a.actions[i]);if(outcome?.navigating)return;}sessionStorage.removeItem('fireatlas-action-queue');}
  }
  async function inspect(id,path,parent){try{const value=await showEvidence(id);let scalar=value.payload;if(path)for(const key of path.slice(1).split('/'))scalar=scalar[key.replaceAll('~1','/').replaceAll('~0','~')];const d=element('details');d.open=true;d.append(element('summary','Checked evidence'),element('pre',JSON.stringify({value:scalar,path,method:value.method,context:value.context,release:value.release_id,result_hash:value.sha256},null,2)));parent.append(d);}catch(e){fail(e);}}
  async function navigate(destination,result){const action=await api('actions',{destination,context:context(),result_id:result});await applyAction(action);}
  async function applyAction(action){
    if(activeRun)await stop();if(action.expected_revision!==revision)throw Error('This action belongs to older study settings. Ask again with the current study.');
    applying=true;clearTimeout(registerTimer);
    try{
      let result;try{result=await V().apply(action);}catch(error){await api('actions/'+action.id+'/ack',{revision:action.expected_revision,instance:V().instance,state:'failed',actual:{reason:error.message}}).catch(()=>{});throw error;}if(result.navigating)return result;
      await api('actions/'+action.id+'/ack',{revision:action.expected_revision,instance:V().instance,...result});
      if(result.state!=='applied')throw Error(result.actual.reason);
      await register();status('View updated and acknowledged.');return result;
    }finally{applying=false;}
  }
  async function notebook(){
    const n=await api('notebook');if(!page())return n;
    const list=$('assistant-notes'),findings=$('mission-findings');list.replaceChildren();if(findings)findings.replaceChildren();
    const items=n.items.filter(r=>['note','annotation','answer'].includes(r.kind));
    for(const r of items){const card=element('article',null,'assistant-note');card.dataset.artifactId=r.id;card.append(element('strong',r.kind==='answer'?r.body.title:r.kind==='annotation'?'Map annotation':'Scientist note'),element('p',r.body.text||r.body.summary));const del=element('button','Delete');del.addEventListener('click',async()=>{await api('artifacts/'+r.id,undefined,'DELETE');await notebook();});card.append(del);if(r.kind==='answer'){const open=element('button','Read finding');open.addEventListener('click',()=>answer({...r.body,notebook_id:r.id},true));card.append(open);}(r.kind==='answer'&&findings?findings:list).append(card);}
    const annotations=n.items.filter(r=>r.kind==='annotation');V().adapter()?.annotate?.(annotations);return n;
  }
  function placeChoices(value,parent){
    const choices=element('div',null,'assistant-place-choices');
    for(const place of value.choices||[]){const card=element('article',null,'assistant-place-card'),b=element('button','Show '+place.title,'assistant-place-open');b.type='button';b.addEventListener('click',async()=>{try{await register();const current=V().state().page,destination=current==='overview'?'overview':current==='terrain'?'terrain':current==='atlas'?'atlas':current==='replay'?'replay':current==='assistant'?'assistant':current==='research-candidates'?'candidates':'assistant';const action=await api('actions',{destination,context:context(),options:{kind:'focus_place',place_id:place.place_id}});await applyAction(action);status('Geographic location shown. Study dates and evidence are unchanged.');}catch(e){fail(e);}});card.append(b,window.FireAtlasLocation.detail('place:'+place.place_id,place.title,window.FireAtlasLocation.point([place.longitude,place.latitude]),'Geographic reference'));choices.append(card);if(place.source_url){const a=element('a','OpenStreetMap source ↗');a.href=place.source_url;a.target='_blank';a.rel='noopener';choices.append(a);}}
    choices.append(element('small','Geographic reference only. The camera can move beyond the imported study; it does not create fire readings or change the selected boundary.'));parent.append(choices);return choices;
  }
  async function locatePlace(query){try{window.dispatchEvent(new CustomEvent('fireatlas:show-assistant-chat'));if(!ready)throw Error('Place lookup requires the local assistant service.');const value=await api('places',{query});const m=message(value.status==='resolved'?'Place found.':value.status==='choose_place'?'Choose the geographic place you mean.':'No place matched. Add a country or use study coordinates.');const choices=placeChoices(value,m);if(value.status==='resolved')choices.querySelector('.assistant-place-open')?.click();scrollConversation();}catch(e){fail(e);}}
  function placeSearch(){const form=element('form',null,'assistant-place-search');const label=element('label','Find a place on the map');label.htmlFor='assistant-place-query';const input=element('input');input.id='assistant-place-query';input.type='search';input.required=true;input.maxLength=180;input.placeholder='City, region, country, or saved fire';const button=element('button','Locate');button.type='submit';form.append(window.FireAtlasLocation.strip(),label,input,button);form.addEventListener('submit',async e=>{e.preventDefault();button.disabled=true;await locatePlace(input.value);button.disabled=false;});if(page())document.querySelector('.mission-map-toolbar').after(form);else document.querySelector('#assistant-dock .assistant-panel-head').after(form);}
  async function refreshBudget(){if(!ready)return;if(caps.free_only){if($('assistant-budget'))$('assistant-budget').textContent='Free models only · paid fallbacks and speech disabled · provider quotas apply';return;}try{const s=await api('sessions');if($('assistant-budget'))$('assistant-budget').textContent=`AI allowance: $${s.budget.session_remaining.toFixed(2)} remaining here · $${s.budget.used_or_reserved.toFixed(2)} used/reserved globally today`;}catch{} }
  async function capture(){try{if(busy)throw Error('Wait for the active investigation before attaching a figure.');window.dispatchEvent(new CustomEvent('fireatlas:figure-capture-start'));if(!ready)throw Error('Figure attachments require the local assistant service.');await register();const turn=revision,adapter=V().adapter();const target=V().state().visual_targets?.[0];if(!adapter?.capture&&!target)throw Error('No scientific panel is ready to capture.');const figure=adapter?.capture?await adapter.capture():await V().captureGuide(target);if(turn!==revision)throw Error('Study settings changed during capture. Attach the current figure again.');const saved=await api('images',{...figure,revision:turn});attachments=[saved.id];const m=message('Attached selected figure: '+figure.caption+'. The assistant will use calculation results for numbers.');const img=element('img',null,'assistant-figure');img.src='data:image/png;base64,'+figure.data;img.alt=figure.caption;m.append(img);if(figure.regions?.length){const callout=element('button','Outline evidence in this figure');callout.type='button';callout.addEventListener('click',async()=>{try{const marked=await api('figures/annotate',{image_id:saved.id,target:figure.regions[0].target});img.src='data:image/png;base64,'+marked.data;img.alt=marked.caption;callout.textContent='OpenCV evidence callout applied';}catch(e){fail(e);}});m.append(callout);}status('Selected figure attached to next question.');}catch(e){fail(e);}}
  function makeDock(){
    const launch=element('button',null,'assistant-launch');
    launch.append(element('span','✦','assistant-launch-icon'),element('span','Scientific assistant','assistant-launch-label'));
    launch.querySelector('.assistant-launch-icon').setAttribute('aria-hidden','true');
    launch.setAttribute('aria-label','Open scientific assistant');launch.title='Open scientific assistant';
    launch.setAttribute('aria-expanded','false');launch.setAttribute('aria-controls','assistant-dock');document.body.append(launch);
    const dock=element('aside',null,'assistant-dock');dock.id='assistant-dock';dock.hidden=true;dock.setAttribute('aria-label','Scientific assistant');
    dock.innerHTML='<div class="assistant-panel-head"><h2>Scientific assistant</h2><button id="assistant-close" type="button" aria-label="Close assistant">Close</button></div><div class="assistant-service-note" id="assistant-service-note" hidden></div><div class="assistant-tools"><button data-investigation="missingness">Explain gaps</button><button data-investigation="method">Explain this method</button><a id="assistant-workspace-link" href="./assistant.html">Open workspace ↗</a></div><div id="assistant-messages" class="assistant-messages" aria-live="polite" aria-label="Scientific conversation"></div><form id="assistant-question-form" class="assistant-composer"><label for="assistant-question">Ask about this study</label><textarea id="assistant-question" maxlength="3000" required placeholder="What can this view tell me about the fire?"></textarea><div class="assistant-compose-actions"><button type="submit" id="assistant-send" class="assistant-primary">Investigate</button><button type="button" id="assistant-stop" disabled>Stop</button><button type="button" id="assistant-mic" disabled>Record</button><button type="button" id="assistant-capture">Attach figure</button><span id="assistant-turn-status" class="assistant-turn-status" role="status">Ready</span></div></form>';
    document.body.append(dock);const close=()=>{dock.hidden=true;launch.setAttribute('aria-expanded','false');launch.focus();};launch.setAttribute('aria-haspopup','dialog');launch.setAttribute('aria-controls','assistant-theater');launch.addEventListener('click',()=>{if(window.FireAtlasVisuals){window.FireAtlasVisuals.open();launch.setAttribute('aria-expanded','true');}else{dock.hidden=!dock.hidden;launch.setAttribute('aria-expanded',String(!dock.hidden));if(!dock.hidden)$('assistant-question').focus();}});$('assistant-close').addEventListener('click',close);dock.addEventListener('keydown',e=>{if(e.key==='Escape')close();});return dock;
  }
  async function record(){
    if(recorder){recorder.stop();return;}
    try{
      if(!caps.voice?.available)throw Error('Voice is not configured. Typed scientific questions remain available.');
      const stream=await navigator.mediaDevices.getUserMedia({audio:true});const ac=new AudioContext({sampleRate:16000});const source=ac.createMediaStreamSource(stream),processor=ac.createScriptProcessor(4096,1,1),chunks=[];let samples=0;source.connect(processor);processor.connect(ac.destination);processor.onaudioprocess=e=>{if(samples<ac.sampleRate*20){const data=new Float32Array(e.inputBuffer.getChannelData(0));chunks.push(data);samples+=data.length;}};
      recorder={stop:async()=>{clearTimeout(recordTimeout);processor.disconnect();source.disconnect();stream.getTracks().forEach(t=>t.stop());await ac.close();recorder=null;$('assistant-mic').setAttribute('aria-pressed','false');$('assistant-mic').textContent='Record question';status('Transcribing…');const pcm=new Int16Array(samples);let offset=0;chunks.forEach(chunk=>{for(const v of chunk)pcm[offset++]=Math.max(-1,Math.min(1,v))*32767;});const wav=new ArrayBuffer(44+pcm.byteLength),dv=new DataView(wav);const chars=(off,s)=>[...s].forEach((c,i)=>dv.setUint8(off+i,c.charCodeAt(0)));chars(0,'RIFF');dv.setUint32(4,36+pcm.byteLength,true);chars(8,'WAVEfmt ');dv.setUint32(16,16,true);dv.setUint16(20,1,true);dv.setUint16(22,1,true);dv.setUint32(24,ac.sampleRate,true);dv.setUint32(28,ac.sampleRate*2,true);dv.setUint16(32,2,true);dv.setUint16(34,16,true);chars(36,'data');dv.setUint32(40,pcm.byteLength,true);for(let i=0;i<pcm.length;i++)dv.setInt16(44+i*2,pcm[i],true);const blob=new Blob([wav],{type:'audio/wav'}),reader=new FileReader();reader.onload=async()=>{try{const out=await api('voice/transcribe',{data:reader.result.split(',')[1],mime:'audio/wav'});$('assistant-question').value=out.transcript;status('Transcript ready. Review it, then select Investigate.');}catch(e){fail(e);}};reader.readAsDataURL(blob);}};
      $('assistant-mic').setAttribute('aria-pressed','true');$('assistant-mic').textContent='Stop recording';status('Recording one question · maximum 20 seconds');recordTimeout=setTimeout(()=>recorder?.stop(),20000);
    }catch(e){fail(e);}
  }
  async function init(){
    if(document.body.dataset.page==='terrain'&&new URLSearchParams(location.search).has('embed'))return;
    if(!V())return;
    if(page()&&window.FireAtlasStudyReady)await window.FireAtlasStudyReady;
    root=page()?document.querySelector('.assistant-shell'):makeDock();
    window.dispatchEvent(new CustomEvent('fireatlas:assistant-ui-ready'));
    const depthField=element('div',null,'assistant-depth-field');depthField.id='assistant-depth-field';depthField.hidden=true;
    const depthLabel=element('label','Analysis mode');depthLabel.htmlFor='assistant-depth';
    const depth=element('select');depth.id='assistant-depth';depth.setAttribute('aria-describedby','assistant-depth-help');
    for(const [value,label] of [['efficient','Efficient · everyday questions'],['deep','Deep · complex comparisons']]){const option=element('option',label);option.value=value;depth.append(option);}
    const depthHelp=element('p','Efficient for routine questions; Deep for complex comparisons.','assistant-help');depthHelp.id='assistant-depth-help';depthField.append(depthLabel,depth,depthHelp);$('assistant-question-form').prepend(depthField);

    const nav=document.getElementById('site-navigation');if(nav&&!nav.querySelector('[data-page-link="assistant"]')){const link=element('a','Assistant');link.dataset.pageLink='assistant';link.href=V().link('assistant',context()).href;nav.append(link);}
    root.querySelectorAll('[data-investigation]').forEach(button=>button.addEventListener('click',()=>investigate(button.dataset.investigation)));
    root.querySelectorAll('[data-question]').forEach(button=>button.addEventListener('click',()=>{$('assistant-question').value=button.dataset.question;$('assistant-question').focus();status('Example selected. Review it, then select “Ask assistant”.');}));
    window.addEventListener('fireatlas:figure-ready',e=>{if(page()){$('assistant-capture').disabled=!ready||!e.detail.available;$('assistant-capture').title=e.detail.available?'Attach a schematic of the current observation cells; background imagery is omitted':'Open an observation map first';}});
    $('assistant-question-form').addEventListener('submit',e=>{e.preventDefault();investigate();});$('assistant-stop').addEventListener('click',stop);$('assistant-capture').addEventListener('click',capture);$('assistant-mic').addEventListener('click',record);
    if(page()){
      $('assistant-control').addEventListener('click',()=>register(true).then(()=>status('This view now controls the workspace.')).catch(fail));
      $('assistant-note-form').addEventListener('submit',async e=>{e.preventDefault();try{await api('notebook',{text:$('assistant-note').value,context:context(),result_id:lastEvidence?.id});$('assistant-note').value='';await notebook();}catch(e){fail(e);}});
      $('assistant-pin').addEventListener('click',async()=>{try{const selection=V().state().selection;if(!selection?.geometry)throw Error('Select a cell or map location before pinning a note.');if(!$('assistant-note').value.trim())throw Error('Write the annotation first.');await api('annotations',{text:$('assistant-note').value,context:context(),geometry:selection.geometry,result_id:selection.result_id||lastEvidence?.id,target:selection.target||'observation-cell',path:selection.path});$('assistant-note').value='';status('Annotation saved and linked to the geographic selection.');await notebook();}catch(e){fail(e);}});
      $('assistant-clear').addEventListener('click',async()=>{await stop();await api('sessions',undefined,'DELETE');location.reload();});
      $('assistant-mask').addEventListener('change',async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>2_900_000)throw Error('Coverage file must be smaller than 2.9 MB.');const r=await api('masks',{mask:JSON.parse(await file.text()),context:context()});V().adapter()?.apply({...context(),mask_id:r.id});$('assistant-mask-status').textContent=r.status;revision++;await register();}catch(e){fail(e);}});
    }
    placeSearch();controls(false);
    try{
      caps=await api('capabilities');const s=await api('sessions',{context:context()});revision=s.context.revision+(sessionStorage.getItem('fireatlas-pending-action')?0:1);ready=true;
      try{await register();}catch(e){message(e.message,'error');}
      const note=$('assistant-service-note');note.hidden=caps.ai_available;note.textContent='Conversational AI is currently unavailable. You can still load observations, compare sensors, search the archive and annotate the map.';
      if(!caps.ai_available && caps.reason){const diagnostics=document.createElement('details');diagnostics.className='assistant-service-diagnostics';const summary=document.createElement('summary');summary.textContent='Connection details';const text=document.createElement('p');text.textContent=caps.reason;diagnostics.append(summary,text);note.after(diagnostics);}
      if($('assistant-ai-state')){$('assistant-ai-state').textContent=caps.ai_available?(caps.free_only?'Free AI available':caps.provider==='aiand'?'AI& available':'AI available'):'Stored-data tools available';}
      depthField.hidden=!caps.analysis_modes?.includes('deep');
      const welcome=$('assistant-chat-welcome')?.querySelector('.mission-small');if(welcome)welcome.textContent=caps.free_only?'Map and archive tools work independently of AI. Free AI capacity varies.':'Map and archive tools use stored data without AI charges. Questions use bounded AI analysis; each answer shows its model and estimated cost.';
      $('assistant-mic').disabled=!caps.voice.available;
      if($('assistant-voice-help'))$('assistant-voice-help').hidden=caps.voice.available;
      status(caps.ai_available?'Ready. Choose a study task or ask about the selected area and dates.':'Stored-data tasks are ready. Conversational AI is unavailable.');
      controls(false);await refreshBudget();const n=await notebook();
      // Earlier findings remain in the notebook; do not mix prior studies into the new-study conversation.
      window.dispatchEvent(new CustomEvent('fireatlas:assistant-ready',{detail:caps}));
      const pending=sessionStorage.getItem('fireatlas-pending-action');
      if(pending){sessionStorage.removeItem('fireatlas-pending-action');const action=JSON.parse(pending);revision=action.expected_revision;await api('views',{context:{...action.context,revision},view:{...V().state(),take_control:true}});let tries=0;while(tries++<30&&!V().adapter())await new Promise(r=>setTimeout(r,300));await applyAction(action);const queue=JSON.parse(sessionStorage.getItem('fireatlas-action-queue')||'[]');sessionStorage.removeItem('fireatlas-action-queue');for(let i=0;i<queue.length;i++){sessionStorage.setItem('fireatlas-action-queue',JSON.stringify(queue.slice(i+1)));const outcome=await applyAction(queue[i]);if(outcome?.navigating)return;}sessionStorage.removeItem('fireatlas-action-queue');}
    }catch(e){ready=false;window.dispatchEvent(new CustomEvent('fireatlas:assistant-unavailable',{detail:{message:e.message}}));const note=$('assistant-service-note');note.hidden=false;note.textContent=e.message;if($('assistant-ai-state'))$('assistant-ai-state').textContent='Local service required';controls(false);for(const id of ['assistant-capture','assistant-mic','assistant-pin','assistant-control','assistant-clear','assistant-mask'])if($(id))$(id).disabled=true;root.querySelectorAll('.assistant-note-entry button').forEach(b=>b.disabled=true);root.querySelectorAll('.assistant-export a').forEach(a=>{a.removeAttribute('href');a.setAttribute('aria-disabled','true');a.title='A local analysis service is required to save and export private investigations.';});}
    function sync(){if(applying)return;revision++;attachments=[];if(page()){$('assistant-capture').disabled=!ready||!V().adapter()?.state?.().figure_ready;$('assistant-capture').title=$('assistant-capture').disabled?'Open a map for the current study before attaching a figure':'Attach the current observation cell schematic';}if(audio){audio.pause();audio=null;}if(busy||activeRun){message('Study or frame changed. The previous investigation was stopped so findings cannot be applied to a different view.');stop();}clearTimeout(registerTimer);registerTimer=setTimeout(()=>{if(!ready)return;register().catch(fail);if($('assistant-workspace-link'))$('assistant-workspace-link').href=V().link('assistant',context()).href;},350);}
    window.addEventListener('fireatlas:study-changed',sync);window.addEventListener('fireatlas:selection-changed',sync);
    document.querySelectorAll('[data-context-field],#case-select,#source-select,#metric-select,#day-slider').forEach(control=>control.addEventListener('change',sync));
    viewTimer=setInterval(()=>{if(ready&&!document.hidden)register().catch(()=>{});},15000);
    window.addEventListener('pagehide',()=>{clearInterval(viewTimer);if(recorder)recorder.stop();if(audio)audio.pause();});
  }
  window.FireAtlasAssistant={isBusy:()=>busy,investigate,showEvidence,navigate,context,request:api,refreshNotebook:notebook,isReady:()=>ready,stop,notify:message};
  document.addEventListener('DOMContentLoaded',init);
})();
