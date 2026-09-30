/* Hash-bound native-mask review form. It records human observations; it never
 * derives them from the processor's expected values. */
document.addEventListener('DOMContentLoaded', () => {
  const $ = selector => document.querySelector(selector);
  const params = new URLSearchParams(location.search);
  const staticRoot = document.querySelector('meta[name="fireatlas-static-data"]')?.content;
  const cases = new Map();
  let caseId = params.get('case') === 'park-2024' ? 'park-2024' : 'grove-2025';
  let template = null;
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
    const response = await fetch(url);
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
      const meta = document.createElement('div'); meta.className = 'review-sample-meta';
      const values = [
        ['Pixel', `${sample.line}, ${sample.sample}`],
        ['Expected class', sample.expected_mask_class],
        ['Expected location', `${Number(sample.expected_lat).toFixed(6)}, ${Number(sample.expected_lon).toFixed(6)}`],
        ['Expected cell', `${sample.expected_grid_x}, ${sample.expected_grid_y}`],
      ];
      values.forEach(([label, value]) => { const item = document.createElement('span'); item.innerHTML = `${label}: <b>${value}</b>`; meta.append(item); });
      card.append(meta);
      const controls = document.createElement('div'); controls.className = 'review-sample-fields';
      const outcome = document.createElement('label'); outcome.textContent = 'Outcome';
      const select = document.createElement('select'); select.dataset.field = 'outcome'; select.required = true;
      select.innerHTML = '<option value="">Choose…</option><option value="agree">Agree</option><option value="disagree">Disagree</option><option value="unresolved">Unresolved</option>';
      outcome.append(select); controls.append(outcome);
      [['Observed class','number','observed_mask_class',{'min':'0','max':'9','step':'1'}],['Observed lat','number','observed_lat',{'step':'any'}],['Observed lon','number','observed_lon',{'step':'any'}],['Grid X','number','observed_grid_x',{'step':'1'}],['Grid Y','number','observed_grid_y',{'step':'1'}]].forEach(([label, type, key, attrs]) => {
        const made = field(label, type, '', attrs); made.input.dataset.field = key; made.input.required = true; controls.append(made.wrapper);
      });
      const notes = document.createElement('label'); notes.className = 'wide'; notes.textContent = 'Notes (required for disagreement / unresolved)';
      const textarea = document.createElement('textarea'); textarea.dataset.field = 'notes'; textarea.placeholder = 'What did you see in the original file?'; notes.append(textarea); controls.append(notes);
      card.append(controls); target.append(card);
      controls.addEventListener('input', updateProgress); controls.addEventListener('change', updateProgress);
    });
    updateProgress();
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
    return { complete, cards, samples };
  }
  function isoTime() {
    const raw = $('#reviewer-time').value;
    if (!raw) return '';
    const value = new Date(raw);
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
    $('#review-form').reset(); $('#reviewer-role').value = 'independent scientific reviewer'; document.querySelectorAll('.review-sample').forEach(card => { card.dataset.complete = 'false'; delete card.dataset.error; }); $('#review-feedback').textContent = ''; updateProgress();
  }
  async function selectCase(id) {
    caseId = id; document.querySelectorAll('[data-case]').forEach(button => button.classList.toggle('active', button.dataset.case === id));
    $('#review-command').textContent = `python3 -m fireatlas.mask_review --case ${id} --review fireatlas_${id}_native_mask_review.json --install`;
    $('#review-download').disabled = true; $('#review-samples').innerHTML = '<div class="review-empty">Loading the case template…</div>';
    try { template = cases.get(id) || await loadTemplate(id); cases.set(id, template); const count = template.samples?.length || 0; $('#review-status-mark').textContent = count >= 30 ? '✓' : '?'; $('#review-status-title').textContent = count >= 30 ? `${id} review queue ready` : `${id} cannot pass the sample gate yet`; $('#review-status-copy').textContent = count >= 30 ? `Thirty samples are hash-bound to ${Object.keys(template.input_hashes || {}).length} processed native inputs. Review the original NASA files before signing.` : 'Native masks are missing or incomplete. This page will not create a passing record from detection rows.'; renderSamples(); }
    catch (error) { template = null; $('#review-status-mark').textContent = '!'; $('#review-status-title').textContent = 'Review queue unavailable'; $('#review-status-copy').textContent = error.message; $('#review-samples').innerHTML = `<div class="review-empty">${error.message}</div>`; updateProgress(); }
  }
  document.querySelectorAll('[data-case]').forEach(button => button.addEventListener('click', () => selectCase(button.dataset.case)));
  $('#review-download').addEventListener('click', download); $('#review-reset').addEventListener('click', clearForm);
  $('#review-form').addEventListener('input', updateProgress); $('#review-form').addEventListener('change', updateProgress);
  selectCase(caseId);
});
