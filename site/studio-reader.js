(function () {
  'use strict';
  const root = document.getElementById('reader-root');
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const source = new URL(new URLSearchParams(location.search).get('story') || './story.json', location.href);
  function asset(file) {
    if (typeof file !== 'string' || file.startsWith('/') || file.split('/').includes('..') || /^[a-z]+:/i.test(file)) throw new Error('The story contains an invalid relative asset.');
    const target = new URL(file, source);
    if (target.origin !== source.origin) throw new Error('Story assets must remain inside the exported site.');
    return target.href;
  }
  async function load() {
    if (source.origin !== location.origin || !/^https?:$/.test(source.protocol)) throw new Error('Serve the story from a local or static HTTP site. Cross-origin workspace loading is unavailable.');
    const response = await fetch(source, { credentials: 'omit' });
    if (!response.ok) throw new Error('No bundled story is available in this static release. Open Investigate to author one with the local service.');
    const text = await response.text();
    if (text.length > 20000000) throw new Error('The story exceeds the reader size limit.');
    const bundle = JSON.parse(text);
    if (bundle.schema !== 'fireatlas-studio-reader-v1' || !Array.isArray(bundle.resolved?.scenes) || bundle.resolved.scenes.length > 24) throw new Error('Unsupported or oversized story.');
    return bundle;
  }
  function render(bundle) {
    const story = bundle.resolved, scenes = story.scenes;
    let index = 0, resume = null;
    root.innerHTML = '<article class="reader"><header><span class="eyebrow">IGNIS-ATLASSIA / FROZEN STORY</span><h1></h1><p class="muted">Bundled evidence, prepared schematics and readable text. No scientific service or live tiles are required.</p></header><section class="scene" aria-live="polite" tabindex="0"><div class="scene-art"><img alt="" data-fallback></div><div><h2></h2><p class="caption"></p><p class="narration"></p><p class="muted" data-narration-grounding></p></div></section><section class="reader-note" data-heat-table hidden tabindex="0" aria-label="Frozen heat-image values"></section><div class="reader-controls"><button type="button" data-prev>Previous</button><button type="button" data-next>Next</button><button type="button" data-explore hidden>Explore chapter evidence</button><button type="button" data-resume hidden>Resume story</button><span class="muted" data-position></span></div><section data-question aria-label="Chapter question"></section><section data-exploration hidden aria-label="Frozen chapter exploration"></section><details class="reader-note"><summary>Current evidence and provenance</summary><div data-evidence></div></details><section class="reader-note"><h2>Read the chapters</h2><label><input type="checkbox" data-scroll> Follow chapters as I scroll</label><div data-transcript></div></section><details class="reader-note"><summary>Sources and limitations</summary><div data-limitations></div><a data-captions>Download captions</a> · <a data-text>Download transcript</a></details></article>';
    const find = (selector) => root.querySelector(selector);
    find('h1').textContent = story.title;
    find('header .muted').textContent = `Portable ${story.audience || 'researcher'} story · ${story.profile.duration_seconds} seconds · bundled evidence, prepared schematics and readable text. No scientific service or live tiles are required.`;
    find('[data-limitations]').innerHTML = story.limitations.map((line) => `<p>${esc(line)}</p>`).join('');
    find('[data-captions]').href = asset(bundle.story_files.captions);
    find('[data-text]').href = asset(bundle.story_files.transcript);
    find('[data-transcript]').innerHTML = scenes.map((scene, at) => `<section data-chapter="${at}" class="transcript-chapter"><h3>${at + 1}. ${esc(scene.title)}</h3><p>${esc(scene.narration_text || scene.caption)}</p><button type="button" data-open="${at}">View chapter ${at + 1}</button></section>`).join('');
    function facts(scene) {
      return scene.evidence.flatMap((id) => (story.snapshots[id]?.facts || []).map((fact) => ({ ...fact, snapshot: story.snapshots[id] })));
    }
    function factTable(scene) {
      const values = facts(scene);
      return values.length ? '<table><thead><tr><th>Field</th><th>Value</th><th>Unit / state</th></tr></thead><tbody>' + values.map((f) => `<tr><td>${esc(f.label)}</td><td>${esc(f.value === null ? f.state : f.value)}</td><td>${esc(f.unit)} · ${esc(f.state)}</td></tr>`).join('') + '</tbody></table>' : '<p>No measurement is cited in this text chapter.</p>';
    }
    function show() {
      const scene = scenes[index];
      if (!scene) return;
      find('.scene h2').textContent = scene.title;
      find('.caption').textContent = scene.caption;
      find('.narration').textContent = scene.narration_text;
      find('[data-narration-grounding]').textContent = scene.narration_grounding?.note || 'Legacy authored narration; interpret alongside its cited fields.';
      const interval = scene.visual?.interval;
      const intervalText = interval && interval.start !== interval.end ? ` · UTC ${interval.start}–${interval.end}` : '';
      const cards = (scene.visible_card_views || []).map((card) => card.title).join(' · ');
      find('[data-position]').textContent = `Chapter ${index + 1} of ${scenes.length} · ${scene.duration_seconds} seconds${intervalText} · ${resume === null ? 'reading' : 'exploring'}${cards ? ` · cards: ${cards}` : ''}`;
      const file = bundle.story_files.fallbacks[scene.chapter_id];
      const fallback = find('[data-fallback]');
      if (file) fallback.src = asset(file);
      fallback.hidden = !file;
      fallback.alt = scene.title + ' — prepared frozen-evidence schematic';
      const heat = (scene.visible_card_views || []).filter((view) => view.visual?.kind === 'heat');
      find('[data-heat-table]').hidden = !heat.length;
      find('[data-heat-table]').innerHTML = heat.length ? '<table><caption>Frozen heat-image values · recorded common cells</caption><thead><tr><th scope="col">Sensor</th><th scope="col">UTC date</th><th scope="col">Recorded common cells</th><th scope="col">Collected-export state</th><th scope="col">Concentration scale</th></tr></thead><tbody>' + heat.map(({visual: image}) => {
        const name = image.source === 'MODIS_SP' ? '● MODIS' : image.source === 'VIIRS_SNPP_SP' ? '◆ S-NPP VIIRS' : '■ Combined detections';
        const states = image.source === 'joint' ? Object.values(image.products || {}).map((p) => p.state).join(' / ') : image.products?.[image.source]?.state;
        const domain = image.domain ? `${image.domain[0]}–${image.domain[1].toFixed(2)} · study-fixed` : 'unknown';
        return `<tr><th scope="row">${esc(name)}</th><td>${esc(image.day)}</td><td>${esc(image.count == null ? 'unknown' : image.count)}</td><td>${esc(states?.replaceAll('_', ' ') || 'unknown')}</td><td>${esc(domain)}</td></tr>`;
      }).join('') + '</tbody></table><p>Heat shows smoothed recorded common-cell centers. Incomplete exports do not establish an observed zero or fire-free area.</p>' : '';
      find('[data-question]').innerHTML = scene.question ? `<p><strong>Chapter question:</strong> ${esc(scene.question.prompt)}</p><p><strong>Author’s interpretation:</strong> ${esc(scene.question.answer || 'Inspect the frozen evidence to explore this question.')}</p>` : '';
      find('[data-evidence]').innerHTML = factTable(scene) + scene.evidence.map((id) => {
        const snapshot = story.snapshots[id], entry = bundle.evidence_files[id];
        return `<p>Method ${esc(snapshot.method.id)} · receipt <code>${esc(snapshot.receipt_sha256)}</code> · release <code>${esc(snapshot.release_id)}</code> ${entry?.snapshot ? `<a href="${esc(asset(entry.snapshot))}">Snapshot</a>` : ''} ${entry?.receipt ? `<a href="${esc(asset(entry.receipt))}">Frozen receipt</a>` : '<span>Full receipt not bundled; snapshot and hashes are retained.</span>'}</p>`;
      }).join('');
      find('[data-prev]').disabled = resume !== null || index === 0;
      find('[data-next]').disabled = resume !== null || index === scenes.length - 1;
      find('[data-explore]').hidden = resume !== null;
      find('[data-resume]').hidden = resume === null;
      find('[data-exploration]').hidden = resume === null;
      root.querySelectorAll('[data-open]').forEach((button) => { button.disabled = resume !== null; });
    }
    function go(at) {
      if (resume !== null) return;
      index = Math.max(0, Math.min(scenes.length - 1, at)); show();
    }
    find('[data-prev]').addEventListener('click', () => go(index - 1));
    find('[data-next]').addEventListener('click', () => go(index + 1));
    find('[data-explore]').addEventListener('click', () => {
      resume = index;
      find('[data-exploration]').innerHTML = '<h3>Explore this frozen chapter</h3><p>This branch stays attached to the saved scene. It cannot change the authored story. Conversational JARVIS requires the private Studio service.</p>' + factTable(scenes[index]);
      show(); find('[data-resume]').focus();
    });
    find('[data-resume]').addEventListener('click', () => { index = resume ?? index; resume = null; show(); find('.scene').focus(); });
    root.querySelectorAll('[data-open]').forEach((button) => button.addEventListener('click', () => { go(Number(button.dataset.open)); find('.scene').focus(); }));
    root.addEventListener('keydown', (event) => {
      if (event.target.matches('input,textarea,select,button,a') || event.target.closest('[data-heat-table]')) return;
      if (event.key === 'ArrowLeft' || event.key === 'PageUp') { event.preventDefault(); go(index - 1); }
      if (event.key === 'ArrowRight' || event.key === 'PageDown') { event.preventDefault(); go(index + 1); }
      if (event.key === 'Home') { event.preventDefault(); go(0); }
      if (event.key === 'End') { event.preventDefault(); go(scenes.length - 1); }
    });
    if (typeof IntersectionObserver !== 'undefined') {
      const observer = new IntersectionObserver((entries) => {
        if (!find('[data-scroll]').checked || resume !== null) return;
        const current = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (current) go(Number(current.target.dataset.chapter));
      }, { threshold: [0.4, 0.7], rootMargin: '-10% 0px -30% 0px' });
      root.querySelectorAll('[data-chapter]').forEach((chapter) => observer.observe(chapter));
    }
    show();
  }
  load().then(render).catch((error) => { root.innerHTML = `<article class="reader"><h1>Story reader</h1><p>${esc(error.message)}</p><p><a href="./investigate.html">Open Investigate</a> to create a saved story, then export its portable reader ZIP.</p><p class="muted">A complete exported story bundle can be opened here without a backend or external imagery.</p></article>`; });
}());
