/* Exact exported-calendar summaries for a selected area and UTC year. */
(() => {
  'use strict';
  const pending = new WeakMap();
  const element = (tag, text) => { const n = document.createElement(tag); if (text != null) n.textContent = String(text); return n; };
  const fmt = new Intl.NumberFormat('en');
  async function get(url, signal) { const r = await fetch(url, { signal }); if (!r.ok) throw Error('Data could not be loaded (' + r.status + ').'); return r.json(); }
  async function show(host, options) {
    const prior = pending.get(host); if (prior) prior.abort();
    const request = new AbortController(); pending.set(host, request);
    host.hidden = false; host.replaceChildren();
    const heading = element('h3', 'Available data · ' + options.year);
    const scope = element('p', options.staticMode ? 'Full selected region · MODIS and VIIRS · UTC' : 'Visible map area · ' + options.bbox + ' · UTC');
    const status = element('p', 'Loading the selected area…'); status.setAttribute('role', 'status');
    const close = element('button', 'Close'); close.type='button'; close.addEventListener('click', () => { request.abort(); host.hidden = true; });
    host.append(heading, scope, status, close);
    try {
      const sources = ['modis', 'viirs-snpp']; let values;
      if (options.staticMode) {
        const root = new URL('./data/explore/', document.baseURI);
        const manifest = await get(new URL('manifest.json', root), request.signal);
        values = await Promise.all(sources.map(source => {
          const entry = manifest.files[[options.region, source, options.year].join('/')];
          if (!entry) throw Error('This region and year are not in the published archive.');
          return get(new URL(entry.path, root), request.signal);
        }));
      } else {
        values = await Promise.all(sources.map(source => {
          const url = new URL('./api/calendar', document.baseURI);
          url.search = new URLSearchParams({year:String(options.year), series:source, bbox:options.bbox});
          return get(url, request.signal);
        }));
      }
      if (pending.get(host) !== request || request.signal.aborted) return;
      if (values.some((v, i) => v.year !== Number(options.year) || v.series !== sources[i] || v.bbox.join(',') !== options.bbox.split(',').map(Number).join(','))) throw Error('Returned data do not match the selected area.');
      const table = element('table'); table.className = 'area-availability-table';
      const caption = element('caption', 'Occupied 1 km cell-days by month'); table.append(caption);
      const head = element('thead'), tr = element('tr'); ['Month','MODIS','VIIRS S-NPP'].forEach(v => tr.append(element('th',v))); head.append(tr); table.append(head);
      const body = element('tbody');
      const value = m => m.detected_cell_days != null ? fmt.format(m.detected_cell_days) : (m.partial_import_detected_cell_days > 0 ? '≥ ' + fmt.format(m.partial_import_detected_cell_days) : '—');
      for (let i=0; i<12; i++) { const row=element('tr'); const month=element('th', values[0].monthly[i].month); month.scope='row'; row.append(month,element('td',value(values[0].monthly[i])),element('td',value(values[1].monthly[i]))); body.append(row); }
      table.append(body); const wrap=element('div'); wrap.className='area-availability-scroll'; wrap.append(table); host.insertBefore(wrap,close);
      status.textContent='Complete totals are shown as numbers; ≥ indicates imported observations from a partial export. — means the total is unknown.';
    } catch (error) { if (!request.signal.aborted && pending.get(host) === request) status.textContent=error.message + ' Try again or choose another area.'; }
  }
  function cancel(host) { if (!host) return; pending.get(host)?.abort(); pending.delete(host); host.hidden=true; }
  window.FireAtlasAreaAvailability = {show,cancel};
})();
