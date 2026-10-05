/* Mounted by analytical-panels.js; original scientific controller retained. */
FireAtlasPanels.define('review', ({document,window,fetch,setTimeout,clearTimeout}) => {
/* Hash-bound native-mask review form. It records human observations; it never
 * derives them from the processor's expected values. */
document.addEventListener('DOMContentLoaded', () => {
  const $ = selector => document.querySelector(selector);
  const params = new URLSearchParams(location.search);
  const staticRoot = (document.querySelector('meta[name="fireatlas-static-evidence"]')||document.querySelector('meta[name="fireatlas-static-data"]'))?.content;
  const cases = new Map();
  (async()=>{const c=window.FireAtlasContext.read(),a=$('#regional-download'),status=$('#regional-download-status');if(!a)return;try{if(staticRoot){const root=document.querySelector('meta[name="fireatlas-static-data"]').content,r=await fetch(new URL('manifest.json',new URL(root,document.baseURI))),m=await r.json(),b=m.bundles?.[`${c.region}/${c.year}/${c.month}`];if(!b||b.status!=='verified'){status.textContent='Exact regional bundle unavailable for this static selection.';return;}a.href=new URL(b.path,new URL(root,document.baseURI));status.textContent=`Frozen ${c.region} ${c.year}-${String(c.month).padStart(2,'0')} harmonized result · ${(b.bytes/1048576).toFixed(1)} MiB · ${b.result_sha256}`;}else{const r=await fetch(window.FireAtlasContext.url('api/v2/calendar?'+new URLSearchParams({region:c.region,year:c.year,month:c.month}))),m=await r.json();if(!r.ok)throw Error(m.error);a.href=window.FireAtlasContext.url('api/v2/study?'+new URLSearchParams({region:c.region,year:c.year,month:c.month,expected_result_sha256:m.meta.result_sha256}));status.textContent=`Current ${c.region} harmonized result · ${m.meta.result_sha256}`;}a.hidden=false;a.download='regional-result.zip';}catch(e){status.textContent='Exact download unavailable: '+e.message;}})();
  let nativeAssets=[];
  let caseId = params.get('case') === 'park-2024' ? 'park-2024' : 'grove-2025';
  let template = null;
  let activeSample = 0, caseRequest=0, restoringDraft=false;
  const draftKey=id=>`fireatlas-native-review-draft-v1:${id}`;
  const identity=()=>JSON.stringify(Object.entries(template?.input_hashes||{}).sort(([a],[b])=>a.localeCompare(b)));
  function saveDraft() {
    if(!template || restoringDraft)return;
    try {
      const fields={};document.querySelectorAll('#reviewer-details input,#reviewer-details textarea').forEach(input=>{fields[input.id]=input.type==='checkbox'?input.checked:input.value;});
      const samples=[...document.querySelectorAll('.review-sample')].map(card=>Object.fromEntries([...card.querySelectorAll('[data-field]')].map(input=>[input.dataset.field,input.value])));
      localStorage.setItem(draftKey(caseId),JSON.stringify({identity:identity(),fields,samples,activeSample,saved_at:new Date().toISOString()}));
      $('#review-draft-status').textContent=`Draft saved in this browser · ${caseId} · ${new Date().toLocaleTimeString()}. Original source hashes remain attached.`;
    } catch (_) { $('#review-draft-status').textContent='Browser draft storage is unavailable. Keep this page open or export the completed review.'; }
  }
  function restoreDraft() {
    restoringDraft=true;
    try {
      const draft=JSON.parse(localStorage.getItem(draftKey(caseId))||'null');
      if(!draft)return;
      if(draft.identity!==identity()){$('#review-draft-status').textContent='A saved draft uses different source hashes. It was not applied to this queue.';return;}
      for(const [id,value] of Object.entries(draft.fields||{})){const input=document.getElementById(id);if(input){if(input.type==='checkbox')input.checked=Boolean(value);else input.value=value;}}
      [...document.querySelectorAll('.review-sample')].forEach((card,index)=>{for(const [field,value] of Object.entries(draft.samples?.[index]||{})){const input=card.querySelector(`[data-field="${field}"]`);if(input)input.value=value;}});
      activeSample=draft.activeSample||0;updateProgress();
      $('#review-draft-status').textContent=`Restored the ${caseId} draft saved ${new Date(draft.saved_at).toLocaleString()}. Review source files before completing it.`;
    }catch (_){}finally{restoringDraft=false;}
  }
  const fmt = value => Number(value).toLocaleString('en-US');

  function setStatus(title, copy, mark = '…', tone = '') {
    $('#review-status-title').textContent = title;
    $('#review-status-copy').textContent = copy;
    $('#review-status-mark').textContent = mark;
    $('#review-status-card')?.setAttribute('data-tone', tone);
  }
  async function loadTemplate(id) {
    const url = staticRoot
      ? new URL(`validity/${id}-review-template.json`, new URL(staticRoot, document.baseURI)).href
      : `/api/validity/review-template?case=${encodeURIComponent(id)}`;
    const response = await fetch(url, {signal:AbortSignal.timeout(30000)});
    const value = await response.json();
    if (!response.ok) throw Error(value.error || `Template unavailable (${response.status})`);
    return value;
  }
  function field(label, type, value, attrs = {}) {
    const wrapper = document.createElement('label');
    wrapper.textContent = label;
    const input = document.createElement('input');
    input.type = type;
    if (value !== null && value !== undefined) input.value = value;
    Object.entries(attrs).forEach(([key, attrValue]) => input.setAttribute(key, attrValue));
    wrapper.append(input);
    return { wrapper, input };
  }
  function renderSamples() {
    const target = $('#review-samples');
    target.replaceChildren();
    const samples = template?.samples || [];
    $('#review-input-summary').textContent = samples.length
      ? `${fmt(samples.length)} immutable sample records · source hashes included`
      : 'Native sample queue unavailable';
    if (samples.length < 30) {
      const empty = document.createElement('div');
      empty.className = 'review-empty';
      empty.textContent = samples.length
        ? `Only ${samples.length} native samples are available. The gate requires 30; download the missing NASA files first.`
        : 'No native mask samples are loaded for this case. Detection CSVs cannot be reviewed as clear/cloud masks.';
      target.append(empty);
      updateProgress();
      return;
    }
    samples.forEach((sample, index) => {
      const card = document.createElement('article');
      card.className = 'review-sample';
      card.dataset.index = String(index);
      const head = document.createElement('div'); head.className = 'review-sample-head';
      const title = document.createElement('strong'); title.textContent = `Sample ${String(index + 1).padStart(2, '0')}`;
      const source = document.createElement('span'); source.textContent = sample.producer_id;
      head.append(title, source); card.append(head);
      const links=document.createElement('div');links.className='review-original-links';links.dataset.producer=sample.producer_id;card.append(links);
      const meta = document.createElement('div'); meta.className = 'review-sample-meta';
      const values = [
        ['Pixel', `${sample.line}, ${sample.sample}`],
        ['Expected class', sample.expected_mask_class],
        ['Expected location · lat, lon °', `${Number(sample.expected_lat).toFixed(6)}, ${Number(sample.expected_lon).toFixed(6)}`],
        ['Expected cell · EASE 6933 indices', `${sample.expected_grid_x}, ${sample.expected_grid_y}`],
      ];
      values.forEach(([label, value]) => { const item = document.createElement('span'); item.innerHTML = `${label}: <b>${value}</b>`; meta.append(item); });
      card.append(meta);
      const controls = document.createElement('div'); controls.className = 'review-sample-fields';
      const outcome = document.createElement('label'); outcome.textContent = 'Outcome';
      const select = document.createElement('select'); select.dataset.field = 'outcome'; select.required = true;
      select.innerHTML = '<option value="">Choose…</option><option value="agree">Agree</option><option value="disagree">Disagree</option><option value="unresolved">Unresolved</option>';
      outcome.append(select); controls.append(outcome);
      [['Observed class','number','observed_mask_class',{'min':'0','max':'9','step':'1'}],['Observed latitude · °','number','observed_lat',{'step':'any','min':'-90','max':'90'}],['Observed longitude · °','number','observed_lon',{'step':'any','min':'-180','max':'180'}],['Grid X','number','observed_grid_x',{'step':'1'}],['Grid Y','number','observed_grid_y',{'step':'1'}]].forEach(([label, type, key, attrs]) => {
        const made = field(label, type, '', attrs); made.input.dataset.field = key; made.input.required = true; controls.append(made.wrapper);
      });
      const notes = document.createElement('label'); notes.className = 'wide'; notes.textContent = 'Notes (required for disagreement / unresolved)';
      const textarea = document.createElement('textarea'); textarea.dataset.field = 'notes'; textarea.placeholder = 'What did you see in the original file?'; notes.append(textarea); controls.append(notes);
      card.append(controls); target.append(card);
      controls.addEventListener('input', updateProgress); controls.addEventListener('change', updateProgress);
    });
    activeSample = 0;
    renderSourceLinks();
    renderQueue();
    updateProgress();
  }
  function renderSourceLinks() {
    document.querySelectorAll('.review-original-links').forEach(target=>{
      target.replaceChildren();const id=target.dataset.producer;
      const parts=id.split('.'),geo={MOD14:'MOD03',MYD14:'MYD03',VNP14IMG:'VNP03IMG'}[parts[0]];
      const geoPrefix=geo?[geo,...parts.slice(1,4)].join('.')+'.':null;
      const files=[['Original mask ↓',nativeAssets.find(a=>a.filename.startsWith(id+'.'))],['Matching geolocation ↓',geoPrefix&&nativeAssets.find(a=>a.filename.startsWith(geoPrefix))]];
      for(const [label,file]of files){if(!file)continue;const link=document.createElement('a');link.href=file.download_url;link.textContent=label;link.setAttribute('download',file.filename);target.append(link);}
    });
  }
  function readSample(card, sample) {
    const read = key => card.querySelector(`[data-field="${key}"]`)?.value ?? '';
    const number = key => { const value = read(key); return value === '' ? null : Number(value); };
    return {
      producer_id: sample.producer_id, line: Number(sample.line), sample: Number(sample.sample),
      expected_mask_class: sample.expected_mask_class, expected_lat: sample.expected_lat, expected_lon: sample.expected_lon,
      expected_grid_x: sample.expected_grid_x, expected_grid_y: sample.expected_grid_y,
      outcome: read('outcome'), observed_mask_class: number('observed_mask_class'), observed_lat: number('observed_lat'), observed_lon: number('observed_lon'),
      observed_grid_x: number('observed_grid_x'), observed_grid_y: number('observed_grid_y'), notes: read('notes').trim(),
    };
  }
  function sampleComplete(value) {
    const numeric = ['observed_mask_class','observed_lat','observed_lon','observed_grid_x','observed_grid_y'];
    return Boolean(value.outcome && numeric.every(key => Number.isFinite(value[key])) && (value.outcome === 'agree' || value.notes));
  }
  function updateProgress() {
    const samples = template?.samples || [], cards = [...document.querySelectorAll('.review-sample')];
    let complete = 0;
    cards.forEach((card, index) => { const value = readSample(card, samples[index]); const ok = sampleComplete(value); card.dataset.complete = String(ok); if (value.outcome && !ok) card.dataset.error = 'true'; else delete card.dataset.error; if (ok) complete += 1; });
    $('#review-progress').textContent = `${fmt(complete)} / ${fmt(Math.max(30, samples.length))}`;
    $('#review-download').disabled = samples.length < 30 || complete !== samples.length;
    if ($('#review-progress-bar')) { $('#review-progress-bar').value=complete; $('#review-progress-bar').max=Math.max(30,samples.length); }
    selectSample(activeSample);
    return { complete, cards, samples };
  }
  function renderQueue() {
    const nav = $('#review-queue-nav'); if (!nav) return;
    nav.replaceChildren();
    document.querySelectorAll('.review-sample').forEach((card,index) => {
      const button = document.createElement('button'); button.type = 'button'; button.dataset.sampleIndex=String(index);
      button.addEventListener('click', () => selectSample(index)); nav.append(button);
    });
    selectSample(activeSample);
  }
  function selectSample(index) {
    const cards = [...document.querySelectorAll('.review-sample')];
    activeSample = Math.max(0, Math.min(cards.length-1,index));
    cards.forEach((card,i) => {card.hidden=i!==activeSample;});
    const label=$('#review-selected-sample'); if(label)label.textContent=cards.length ? `Sample ${String(activeSample+1).padStart(2,'0')} of ${cards.length}` : 'Sample queue unavailable';
    if($('#review-previous'))$('#review-previous').disabled=!cards.length||activeSample===0;
    if($('#review-next'))$('#review-next').disabled=!cards.length||activeSample===cards.length-1;
    if($('#review-next-pending'))$('#review-next-pending').disabled=!cards.length;
    document.querySelectorAll('[data-sample-index]').forEach((button,i) => {
      const complete=cards[i]?.dataset.complete==='true';button.dataset.complete=String(complete);
      button.textContent=`${complete?'✓':'○'} ${String(i+1).padStart(2,'0')}`;
      button.setAttribute('aria-pressed',String(i===activeSample));
      button.setAttribute('aria-label',`Sample ${i+1}, ${complete?'complete':'pending'}`);
    });
  }
  function isoTime() {
    const raw = $('#reviewer-time').value;
    if (!raw) return '';
    const value = new Date(`${raw}Z`);
    return Number.isNaN(value.valueOf()) ? '' : value.toISOString();
  }
  function buildReview() {
    const progress = updateProgress();
    const required = [['reviewer-name','Reviewer name'],['reviewer-affiliation','Affiliation'],['reviewer-role','Role'],['reviewer-interpretation','Interpretation']];
    for (const [id, label] of required) if (!$(('#' + id)).value.trim()) throw Error(`${label} is required.`);
    if (!isoTime()) throw Error('A valid reviewed-at UTC time is required.');
    if (!$('#reviewer-independent').checked) throw Error('The independent-review attestation must be checked.');
    if (progress.complete !== progress.samples.length) throw Error('Complete every sample before downloading.');
    return {
      schema: template.schema, case_id: template.case_id,
      reviewer: {name: $('#reviewer-name').value.trim(), affiliation: $('#reviewer-affiliation').value.trim(), role: $('#reviewer-role').value.trim(), independent: true, reviewed_utc: isoTime()},
      input_hashes: template.input_hashes, interpretation: $('#reviewer-interpretation').value.trim(),
      samples: progress.cards.map((card, index) => readSample(card, progress.samples[index])),
    };
  }
  function download() {
    try {
      const review = buildReview();
      const body = JSON.stringify(review, null, 2) + '\n';
      const blob = new Blob([body], {type:'application/json'});
      const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `fireatlas_${caseId}_native_mask_review.json`; link.click(); URL.revokeObjectURL(link.href);
      $('#review-feedback').textContent = 'Downloaded. Run the command below against the same evidence store; the validator will reject changed hashes or missing samples.';
    } catch (error) { $('#review-feedback').textContent = error.message; }
  }
  function clearForm() {
    if(!confirm("Clear the saved draft for this case? Other case drafts remain saved."))return;
    localStorage.removeItem(draftKey(caseId));
    $('#review-form').reset(); $('#reviewer-role').value = 'independent scientific reviewer'; document.querySelectorAll('.review-sample').forEach(card => { card.dataset.complete = 'false'; delete card.dataset.error; }); $('#review-feedback').textContent = ''; updateProgress();
  }
  async function selectCase(id) {
    const request=++caseRequest;saveDraft();template=null;
    $('#review-form').reset();$('#reviewer-role').value='independent scientific reviewer';
    activeSample=0; $('#review-queue-nav')?.replaceChildren();
    caseId = id; document.querySelectorAll('[data-case]').forEach(button => button.classList.toggle('active', button.dataset.case === id));
    $('#review-command').textContent = `python3 -m fireatlas.mask_review --case ${id} --review fireatlas_${id}_native_mask_review.json --install`;
    $('#review-download').disabled = true; $('#review-samples').innerHTML = '<div class="review-empty">Loading the case template…</div>';
    try { const loaded=cases.get(id)||await loadTemplate(id);if(request!==caseRequest)return;template=loaded;cases.set(id,template); const count = template.samples?.length || 0; $('#review-status-mark').textContent = count >= 30 ? '○' : '?'; $('#review-status-title').textContent = count >= 30 ? `${id} review queue ready` : `${id} cannot pass the sample gate yet`; $('#review-status-copy').textContent = count >= 30 ? `Thirty samples are hash-bound to ${Object.keys(template.input_hashes || {}).length} processed native inputs. Review the original NASA files before attesting.` : 'Native masks are missing or incomplete. This page will not create a passing record from detection rows.'; renderSamples(); restoreDraft(); }
    catch (error) { if(request!==caseRequest)return;template = null; $('#review-status-mark').textContent = '!'; $('#review-status-title').textContent = 'Review queue unavailable'; $('#review-status-copy').textContent = error.message; $('#review-samples').innerHTML = `<div class="review-empty">${error.message}</div>`; updateProgress(); }
  }
  document.querySelectorAll('[data-case]').forEach(button => button.addEventListener('click', () => selectCase(button.dataset.case)));
  $('#review-previous')?.addEventListener('click', () => selectSample(activeSample-1));
  $('#review-next')?.addEventListener('click', () => selectSample(activeSample+1));
  $('#review-next-pending')?.addEventListener('click', () => {
    const cards=[...document.querySelectorAll('.review-sample')];
    for(let offset=1;offset<=cards.length;offset++){const index=(activeSample+offset)%cards.length;if(cards[index].dataset.complete!=='true'){selectSample(index);cards[index].querySelector('select')?.focus();break;}}
  });
  $('#review-download').addEventListener('click', download); $('#review-reset').addEventListener('click', clearForm);
  $('#review-form').addEventListener('input',()=>{updateProgress();saveDraft();}); $('#review-form').addEventListener('change',()=>{updateProgress();saveDraft();});
  window.addEventListener('pagehide',saveDraft);
  if(!staticRoot)fetch('/api/native-masks',{signal:AbortSignal.timeout(15000)}).then(r=>r.ok?r.json():Promise.reject()).then(data=>{nativeAssets=data.assets||[];renderSourceLinks();}).catch(()=>{});
  selectCase(caseId);
});

});
