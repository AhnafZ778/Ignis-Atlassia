/* Analytical-only packaging adapter. Protected landing scripts remain unchanged. */
(() => {
  'use strict';
  const keys=new Set(['year','month','bbox','as_of','series','day','distance_km','gap_days','region','layer','case','start','end','source','metric','view','context','revision','mask_id','scale']);
  const uid=prefix=>prefix+'-'+crypto.randomUUID().replaceAll('-','').slice(0,20);
  const instance=uid('view');let tab=sessionStorage.getItem('fireatlas-jarvis-tab');if(!tab){tab=uid('tab');sessionStorage.setItem('fireatlas-jarvis-tab',tab);}
  let submitted=null,requestKey=null,pollTimer=null,watchTimer=null,revision=0,inactive=false,selectedPane=null,selectedBoard=null;
  const canonical=value=>JSON.stringify(value,Object.keys(value).sort());
  const root=new URL('./',document.baseURI);
  async function request(path,body,key){const response=await fetch(new URL('api/studio/'+path,root),{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:body===undefined?{}:{'Content-Type':'application/json',...(key?{'Idempotency-Key':key}:{})},body:body===undefined?undefined:JSON.stringify(body)});const result=await response.json();if(!response.ok)throw Error(result.error||'Studio request failed.');return result;}
  function source(){
    const adapter=window.FireAtlasViews?.adapter(),page=document.body.dataset.workspace||document.body.dataset.page;
    if(page==='atlas'&&window.FireAtlasAtlasCapture){const captured=FireAtlasAtlasCapture();return {...captured,view:{...captured.view,display_scope:{kind:'bounded text evidence guide',truncated:true}},refs:[],adapter:{capture:()=>FireAtlasViews.captureGuide('harmonized-calendar')}};}
    if(!adapter?.describeView)throw Error('This selected surface has no transportable visualization. Select a calculated map or calendar first.');
    const view=adapter.describeView(selectedPane),result=adapter.savedResult?.();
    return {study:adapter.context(),view,refs:result&&!result.static?[{id:result.id}]:[],release:result?.release_id||'',adapter};
  }
  function envelope(captured){const selected=Object.fromEntries(Object.entries(captured.study).filter(([k])=>keys.has(k)));if(typeof selected.bbox==='string')selected.bbox=selected.bbox.split(',').map(Number);const returnURL=new URL(location.href);for(const key of [...returnURL.searchParams.keys()])if(!keys.has(key)&&!['calendar_metric','scope','split','tab','section','context_version','analysis_month','guide','guide_step','origin_route','geometry'].includes(key))returnURL.searchParams.delete(key);return {schema:'fireatlas-jarvis-context-v1',surface:document.body.dataset.workspace|| (document.body.dataset.page==='assistant'?'investigate':document.body.dataset.page==='atlas'?'atlas':'research'),origin_instance_id:instance,origin_tab_id:tab,context_revision:++revision,study_selection:selected,active_view:captured.view,selected_object_ids:[],result_refs:captured.refs,destination:selectedBoard?{intent:'append',board_id:selectedBoard.id,revision:selectedBoard.revision}:{intent:'new-board'},release_identity:captured.release||'',return_destination:returnURL.pathname+returnURL.search+returnURL.hash};}
  function restoreNavigation(result){const url=new URL('studio.html',root);url.searchParams.set('board',result.outputs.document_id);url.searchParams.set('command',result.id);location.assign(url.href);}
  let status,send,resume,open,cancel,pane,attach,strip,exportToggle,choiceAction='package',attachment=null;
  function progress(result){clearTimeout(pollTimer);clearTimeout(watchTimer);cancel.onclick=async()=>{try{clearTimeout(pollTimer);progress(await request('commands/'+result.id+'/cancel',{}));}catch(e){status.textContent=e.message;}};status.textContent=result.message;cancel.hidden=['completed','failed','cancelled'].includes(result.status);if(result.outputs.document_id){open.hidden=false;open.onclick=()=>restoreNavigation(result);}resume.hidden=!['partial','failed'].includes(result.status);resume.onclick=async()=>{try{await request('commands/'+result.id+'/resume',{});void poll(result.id);}catch(e){status.textContent=e.message;}};
    if(result.status==='awaiting_view_ack'){sessionStorage.removeItem('fireatlas-command-pending');restoreNavigation(result);return;}
    if(!['completed','partial','failed','cancelled'].includes(result.status))pollTimer=setTimeout(()=>void poll(result.id),650);else send.disabled=false;
  }
  async function poll(id){try{progress(await request('commands/'+id));}catch(e){status.textContent=e.message+' The saved command can be resumed.';send.disabled=false;resume.hidden=false;resume.onclick=()=>void poll(id);}}
  async function packageView(){send.disabled=true;try{
      if(document.querySelector('meta[name="fireatlas-static-data"]'))throw Error('Saving investigations requires the local service. Frozen named studies and evidence downloads remain available.');
      const captured=source();if(captured.view.visible_sources?.length===2&&captured.view.source==='joint'&&!selectedPane){pane.hidden=false;status.textContent='Choose the MODIS or VIIRS pane to capture this heatmap.';send.disabled=false;return;}
      const ctx=envelope(captured),hash=canonical(captured.study),viewHash=JSON.stringify(captured.view),guard=window.FireAtlasContext?.revision;
      status.textContent='Capturing the selected view…';const preview=captured.adapter?.capture?await captured.adapter.capture(selectedPane||captured.view.source):null;
      if(guard!==window.FireAtlasContext?.revision||(captured.adapter&&(canonical(source().study)!==hash||JSON.stringify(source().view)!==viewHash)))throw Error('The source selection changed during capture. Capture the current view again.');
      await request('principals',{});await request('contexts',ctx);
      requestKey=uid('command');const prepared={key:requestKey,body:{recipe:'visualization_to_investigation',context:ctx,...(exportToggle.checked?{arguments:{export_formats:['native','excalidraw']}}:{}),...(preview?{preview}: {})}};sessionStorage.setItem('fireatlas-command-submission',JSON.stringify(prepared));submitted=await request('commands',prepared.body,prepared.key);sessionStorage.removeItem('fireatlas-command-submission');
      sessionStorage.setItem('fireatlas-command-pending',submitted.id);cancel.onclick=async()=>{clearTimeout(pollTimer);const done=await request('commands/'+submitted.id+'/cancel',{});progress(done);};progress(submitted);
    }catch(e){status.textContent=e.message;send.disabled=false;}}
  async function attachView(options={}){attach.disabled=true;try{
    const captured=source();if(captured.view.visible_sources?.length===2&&captured.view.source==='joint'&&!selectedPane&&!options.automatic){choiceAction='attach';pane.hidden=false;status.textContent='Choose the source pane to attach to JARVIS.';attach.disabled=false;return false;}
    const studyHash=canonical(captured.study),viewHash=JSON.stringify(captured.view);const ctx=envelope(captured);
    const preview=captured.adapter?.capture?await captured.adapter.capture(selectedPane||captured.view.source):null;
    if(canonical(source().study)!==studyHash||JSON.stringify(source().view)!==viewHash)throw Error('Source changed during capture. Attach the current frame again.');
    await request('principals',{});const result=await request('assistant-contexts',{context:ctx,...(preview?{preview}:{})});attachment={...result,studyHash,viewHash};
    status.textContent='This frozen view is attached to JARVIS. Ask to package it, add charts or create a workflow.';
    const V=window.FireAtlasViews;if(!V._jarvisSurfaceState){const original=V.state;V._jarvisSurfaceState=original;V.state=()=>{const state=original();if(attachment&&canonical(source().study)===attachment.studyHash&&JSON.stringify(source().view)===attachment.viewHash)return {...state,jarvis_attachment_id:attachment.attachment_id,jarvis_instance_id:instance};return state;};}
    clearTimeout(watchTimer);const watch=async()=>{if(!attachment||inactive)return;try{const saved=await request('contexts/'+instance+'/commands');const command=saved.commands.find(c=>!['cancelled','failed','completed'].includes(c.status));if(command){submitted=command;progress(command);return;}}catch(e){status.textContent=e.message;}watchTimer=setTimeout(watch,1200);};void watch();
    return true;
  }catch(e){status.textContent=e.message;return false;}finally{attach.disabled=false;}}
  function mount(){const main=document.querySelector('main');if(!main)return;const section=document.createElement('section');section.className='jarvis-transfer';section.setAttribute('aria-label','Capture investigation');const title=document.createElement('strong');title.textContent='From this evidence to your Canvas';send=document.createElement('button');send.type='button';send.textContent='Send to Canvas';send.onclick=()=>{choiceAction='package';void packageView();};exportToggle=document.createElement('input');exportToggle.type='checkbox';exportToggle.id='jarvis-include-exports';const choose=document.createElement('button');choose.type='button';choose.textContent='Choose canvas';const destination=document.createElement('select');destination.setAttribute('aria-label','Investigation destination');destination.hidden=true;destination.add(new Option('Create a new investigation board',''));let boards=[];choose.onclick=async()=>{try{await request('principals',{});const list=await request('documents');boards=list.documents;destination.replaceChildren(new Option('Create a new investigation board',''));for(const board of boards)destination.add(new Option(board.title,board.id));destination.hidden=false;}catch(e){status.textContent=e.message;}};destination.onchange=()=>{selectedBoard=boards.find(b=>b.id===destination.value)||null;updateStrip();status.textContent=selectedBoard?'Append frozen objects to '+selectedBoard.title+'. Existing content stays in place.':'Create a separate investigation board.';};const exportLabel=document.createElement('label');exportLabel.htmlFor=exportToggle.id;exportLabel.append(exportToggle,document.createTextNode(' Prepare native and editable exports'));attach=document.createElement('button');attach.type='button';attach.textContent='Attach this view to JARVIS';attach.onclick=attachView;strip=document.createElement('span');strip.className='jarvis-context-strip';strip.setAttribute('aria-label','Applied source context');const updateStrip=()=>{try{const c=source();strip.textContent=(c.study.case||c.study.region||'Applied study')+' · '+(c.study.day||c.study.start)+' UTC · '+c.view.metric+' · destination: '+(selectedBoard?.title||'a new Canvas');}catch{strip.textContent='Select calculated evidence to capture its exact scope.';}};for(const event of ['fireatlas:adapter-ready','fireatlas:figure-ready','fireatlas:study-changed','fireatlas:selection-changed'])window.addEventListener(event,updateStrip);updateStrip();status=document.createElement('span');status.setAttribute('role','status');status.textContent='Frozen view, compatible charts and a rerunnable workflow.';
    pane=document.createElement('span');pane.hidden=true;for(const [id,label]of [['MODIS_SP','MODIS pane'],['VIIRS_SNPP_SP','VIIRS pane']]){const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=()=>{selectedPane=id;pane.hidden=true;void (choiceAction==='attach'?attachView():packageView());};pane.append(b);}
    open=document.createElement('button');open.type='button';open.textContent='Open saved board';open.hidden=true;resume=document.createElement('button');resume.type='button';resume.textContent='Resume command';resume.hidden=true;cancel=document.createElement('button');cancel.type='button';cancel.textContent='Cancel';cancel.hidden=true;section.append(title,strip,send,choose,destination,exportLabel,attach,pane,status,open,resume,cancel);main.prepend(section);
    const uncertain=sessionStorage.getItem('fireatlas-command-submission');if(uncertain){status.textContent='An earlier submission may already be saved. Retry its original request safely.';send.disabled=true;resume.hidden=false;resume.textContent='Recover submission';resume.onclick=async()=>{try{const stored=JSON.parse(uncertain);const result=await request('commands',stored.body,stored.key);sessionStorage.removeItem('fireatlas-command-submission');sessionStorage.setItem('fireatlas-command-pending',result.id);progress(result);}catch(e){status.textContent=e.message;}};}else {const pending=sessionStorage.getItem('fireatlas-command-pending');if(pending)void poll(pending);}
  }
  // Capture the applied source before a requested Canvas operation reaches
  // JARVIS. The model still chooses the recipe; this only supplies its owned,
  // revision-checked context. Ordinary questions take the existing path.
  let preparingQuestion=false;
  document.addEventListener('submit',async event=>{
    if(event.target?.id!=='assistant-question-form')return;
    const question=document.getElementById('assistant-question')?.value.trim()||'';
    if(!/\b(canvas|whiteboard|package|workflow|export)\b/i.test(question))return;
    event.preventDefault();event.stopImmediatePropagation();
    if(preparingQuestion||!window.FireAtlasAssistant?.isReady()||FireAtlasAssistant.isBusy())return;
    preparingQuestion=true;
    try{
      if(document.querySelector('meta[name="fireatlas-static-data"]'))throw Error('Canvas persistence requires the local service. Frozen evidence remains available.');
      // Explicit single-source words resolve the pane; otherwise capture the
      // current joint view, preserving both sensors and the actual scale.
      const names=question.match(/\b(MODIS|VIIRS)\b/gi)||[];
      if(new Set(names.map(n=>n.toUpperCase())).size===1)selectedPane=names[0].toUpperCase()==='MODIS'?'MODIS_SP':'VIIRS_SNPP_SP';
      else selectedPane=null;
      const captured=await attachView({automatic:true});
      if(captured&&!inactive&&document.getElementById('assistant-question')?.value.trim()===question){
        await FireAtlasAssistant.investigate(undefined,{},question);
      }
    }catch(error){status.textContent=error.message;}
    finally{preparingQuestion=false;}
  },true);
  window.addEventListener('pagehide',()=>{inactive=true;clearTimeout(pollTimer);clearTimeout(watchTimer);});
  window.FireAtlasOrchestration={request,source,envelope,packageView};document.addEventListener('DOMContentLoaded',mount);
})();
