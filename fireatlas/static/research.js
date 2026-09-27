(() => {
  "use strict";
  const initialParams = new URLSearchParams(location.search);
  const demo = initialParams.has("demo") ? initialParams.get("demo") !== "0"
    : !(initialParams.has("year") || initialParams.has("bbox"));
  const $ = id => document.getElementById(id);
  const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const colors = ["#e9ad80", "#8cc5c9", "#bbc6a0", "#b5a2ca", "#d8c287", "#93b3d4"];
  const state = {report: null, mask: null, selected: null, busy: false, map: null, layer: null};
  const number = value => value == null ? "—" : new Intl.NumberFormat("en", {maximumFractionDigits: 2}).format(value);
  function el(tag, className, text) {
    const node = document.createElement(tag); if (className) node.className = className;
    if (text !== undefined) node.textContent = text; return node;
  }
  function svg(tag, attributes) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
    return node;
  }
  async function json(path, options) {
    const url = new URL(path, location.origin);
    if (url.pathname === "/api/meta" || url.pathname.startsWith("/api/research")) url.searchParams.set("demo", demo ? "1" : "0");
    const response = await fetch(url, {...options, signal: AbortSignal.timeout(30000)});
    const body = await response.json(); if (!response.ok) throw new Error(body.error || "The study could not be loaded.");
    return body;
  }
  function showError(message) { $("research-error").hidden = false; $("research-error").textContent = message; }
  function config() {
    return {year: Number($("research-year").value), month: Number($("research-month").value),
      bbox: $("research-bbox").value.split(",").map(v => Number(v.trim())), as_of: $("research-cutoff").value,
      distance_km: Number($("candidate-distance").value), gap_days: Number($("candidate-gap").value)};
  }
  function scope(config) { return JSON.stringify([config.year, config.month, config.bbox, config.as_of]); }
  function query(config) { return new URLSearchParams({...config, bbox: config.bbox.join(",")}); }
  function setBusy(value) {
    state.busy = value; $("study-results").setAttribute("aria-busy", String(value));
    for (const input of document.querySelectorAll(".study-controls input,.study-controls select,.study-controls button,.candidate-controls select,.candidate-controls button,.coverage-input button,.coverage-input input")) input.disabled = value;
    $("export-study").disabled = value || !state.report;
    $("run-study").textContent = value ? "Analyzing…" : "Run analysis ↗";
    if (!value) {
      $("example-mask").disabled = !state.report?.demo_data || !state.report.raw_pixels;
      $("clear-mask").disabled = !state.mask;
      $("download-mask").disabled = !state.mask;
    }
  }
  async function run(proposedMask, explicitMask = false) {
    if (state.busy) return false;
    const selection = config();
    let mask = explicitMask ? proposedMask : state.mask;
    if (!explicitMask && state.report && scope(selection) !== scope(state.report.config)) mask = null;
    setBusy(true); $("research-error").hidden = true;
    try {
      const report = await json("/api/research", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({config: selection, mask})});
      state.report = report; state.mask = mask; state.selected = report.candidates.groups[0]?.id || null;
      $("study-results").hidden = false;
      render();
      return true;
    } catch (error) {
      showError(error.name === "TimeoutError" ? "The study timed out. Narrow the AOI and try again." : error.message);
      $("study-kind").textContent = "ANALYSIS NOT UPDATED";
      $("study-status-text").textContent = "Correct the study inputs and run again. No new result has been produced.";
      $("study-results").hidden = true;
      return false;
    } finally { setBusy(false); $("export-study").disabled = $("study-results").hidden || !state.report; }
  }
  function dateRange() {
    const year = Number($("research-year").value), month = Number($("research-month").value);
    const start = `${year}-${String(month).padStart(2, "0")}-01`;
    const end = `${year}-${String(month).padStart(2, "0")}-${new Date(Date.UTC(year, month, 0)).getUTCDate()}`;
    $("research-cutoff").min = start; $("research-cutoff").max = end; $("research-cutoff").value = end;
  }
  function renderChart() {
    const days = state.report.overlap.daily, width = 760, height = 240, left = 35, top = 18, bottom = 28;
    const plotH = height - top - bottom, max = Math.max(1, ...days.map(d => d.union)), step = (width - left - 8) / days.length;
    const chart = svg("svg", {viewBox: `0 0 ${width} ${height}`, preserveAspectRatio: "none", "aria-hidden": "true"});
    for (let tick = 0; tick <= 4; tick++) {
      const y = top + plotH - plotH * tick / 4;
      chart.append(svg("line", {x1: left, x2: width, y1: y, y2: y, stroke: "#2c414e", "stroke-width": 1, "stroke-dasharray": tick ? "3 5" : "0"}));
      const text = svg("text", {x: left - 9, y: y + 3, fill: "#6f8d9e", "font-size": 10, "text-anchor": "end"}); text.textContent = number(max * tick / 4); chart.append(text);
    }
    days.forEach((day, index) => {
      let y = top + plotH;
      for (const [key, color] of [["modis_only", "#edaa78"], ["both", "#adc5a3"], ["viirs_only", "#6cb6c7"]]) {
        const h = day[key] / max * plotH;
        const bar = svg("rect", {x: left + index * step + 2, y: y - h, width: Math.max(1, step - 4), height: h, rx: 1, fill: color});
        const title = svg("title", {}); title.textContent = `${day.date}: MODIS ${day.modis}, VIIRS ${day.viirs}, both ${day.both}`; bar.append(title); chart.append(bar); y -= h;
      }
      if (index === 0 || (index + 1) % 5 === 0 || index === days.length - 1) {
        const text = svg("text", {x: left + index * step + step / 2, y: height - 7, fill: "#7894a5", "font-size": 10, "text-anchor": "middle"});
        text.textContent = day.date.slice(8); chart.append(text);
      }
    });
    $("daily-chart").replaceChildren(chart);
    $("daily-chart").setAttribute("aria-label", `${days.length} UTC days; ${state.report.overlap.totals.modis_only} MODIS-only, ${state.report.overlap.totals.both} shared and ${state.report.overlap.totals.viirs_only} VIIRS-only cell-days. Exact counts are in the daily table.`);
    $("daily-table").replaceChildren();
    for (const day of days) {
      const row = el("tr"); for (const key of ["date", "modis", "viirs", "both", "union"]) row.append(el("td", "", day[key])); $("daily-table").append(row);
    }
  }
  function initMap() {
    if (typeof L === "undefined") { $("candidate-map").textContent = "Map unavailable. Inspect candidate membership in the list."; return; }
    state.map = L.map("candidate-map", {scrollWheelZoom: false, attributionControl: false, maxZoom: 13, minZoom: 2});
    state.layer = L.layerGroup().addTo(state.map); state.map.setView([40.12, -121.12], 9);
  }
  function fitMap() {
    if (!state.map || !state.report) return;
    state.map.invalidateSize();
    const points = state.report.candidates.groups.flatMap(g => g.points.map(p => [p.coordinates[1], p.coordinates[0]]));
    if (points.length) state.map.fitBounds(L.latLngBounds(points).pad(.25), {padding: [45, 45], maxZoom: 11});
    else { const [w,s,e,n] = state.report.config.bbox; state.map.fitBounds([[s,w],[n,e]], {padding: [20, 20]}); }
  }
  function drawCandidates() {
    $("candidate-list").replaceChildren();
    if (state.layer) state.layer.clearLayers();
    const groups = state.report.candidates.groups;
    $("candidate-count").textContent = `${groups.length} groups`;
    if (!groups.length) $("candidate-list").append(el("p", "empty-research", "No imported detections in this selection. An empty result does not establish fire-free conditions."));
    groups.forEach((group, index) => {
      const selected = group.id === state.selected, color = colors[index % colors.length];
      const button = el("button", selected ? "selected" : ""); button.type = "button"; button.setAttribute("aria-pressed", String(selected));
      const dot = el("span", "group-dot"); dot.style.background = color;
      const text = el("span"); text.append(el("strong", "", `Candidate ${String(index + 1).padStart(2, "0")}`), el("small", "", `${group.cell_days} cell-days · ${group.raw_pixels} pixels`), el("small", "", `${group.first_utc.slice(5,10)} → ${group.last_utc.slice(5,10)} · ${group.days} days`));
      button.append(dot, text); button.addEventListener("click", () => { state.selected = group.id; drawCandidates(); renderCandidateDetail(); }); $("candidate-list").append(button);
      if (!state.map) return;
      const unique = new Map();
      for (const point of group.points) {
        const key = `${point.grid_x},${point.grid_y}`;
        if (!unique.has(key)) unique.set(key, {point, days: []}); unique.get(key).days.push(point.date);
      }
      for (const {point, days} of unique.values()) {
        L.circleMarker([point.coordinates[1], point.coordinates[0]], {radius: selected ? 11 : 7, color, weight: selected ? 2 : 1, fillColor: color, fillOpacity: selected ? .65 : .22})
          .bindTooltip(el("span", "", `Candidate ${index + 1} · ${days.length} detected days · grid ${point.grid_x}, ${point.grid_y}`))
          .on("click", () => { state.selected = group.id; drawCandidates(); renderCandidateDetail(); }).addTo(state.layer);
      }
    });
  }
  function renderCandidateDetail() {
    const group = state.report.candidates.groups.find(g => g.id === state.selected);
    const target = $("candidate-detail"); target.replaceChildren();
    if (!group) { target.textContent = "No candidate membership to inspect."; return; }
    target.append(el("strong", "", group.id), el("div", "", `First ${group.first_utc} · latest ${group.last_utc} · ${group.sources.join(" + ")}`));
    const details = el("details"), summary = el("summary", "", `Inspect ${group.cell_days} cell-days and original detection IDs`), list = el("ul");
    for (const point of group.points) list.append(el("li", "", `${point.date} · grid ${point.grid_x}, ${point.grid_y} · ${point.coordinates.map(v => v.toFixed(5)).join(", ")}`));
    details.append(summary, list, el("p", "", `Detection IDs: ${group.detection_ids.join(", ")}`)); target.append(details);
  }
  function renderCoverage() {
    const coverage = state.report.coverage;
    $("coverage-state").textContent = coverage.status === "unavailable" ? "MASK REQUIRED" : coverage.status === "synthetic" ? "SYNTHETIC EXPOSURE" : "USER MASK · UNVALIDATED";
    $("mask-message").textContent = state.mask ? `${state.mask.synthetic ? "Synthetic demonstration" : "User-supplied mask"} · ${state.mask.cells.length} source/cell/day rows. ${coverage.provenance}` : "No mask supplied. Observation coverage remains unknown. Changing the AOI or date range clears the mask.";
    const target = $("coverage-output"); target.replaceChildren();
    if (coverage.status === "unavailable") {
      const empty = el("div", "coverage-empty"); empty.append(el("span", "", "—"), el("h3", "", "Exposure is unknown"), el("p", "", coverage.note)); target.append(empty); return;
    }
    for (const source of coverage.sources) {
      const row = el("div", "coverage-sensor"), header = el("div", "rate-heading");
      header.append(el("h3", "", source.source_id), el("strong", "", number(source.per_100_observed_cell_days)));
      row.append(header, el("small", "", "detected cell-days / 100 supplied observed cell-days"));
      const track = el("div", "exposure-track"), fill = el("span"); fill.style.width = `${source.per_100_observed_cell_days || 0}%`; track.append(fill); row.append(track);
      row.append(el("p", "", `${source.detected_in_mask} detected / ${source.observed_cell_days} observed · ${source.detections_without_mask} detected cell-days without a mask.`));
      row.append(el("p", "", Object.entries(source.mask_counts).map(([k,v]) => `${k}: ${v}`).join(" · ")));
      if (source.status !== "available") row.append(el("p", "", source.status === "incomplete_export" ? "Rate withheld: the source export is incomplete." : "Rate withheld: no observed exposure supplied."));
      target.append(row);
    }
    target.append(el("p", "", coverage.note));
  }
  function render() {
    const report = state.report, overlap = report.overlap, complete = Object.values(report.complete_exports).every(Boolean);
    $("study-kind").textContent = report.demo_data ? "SYNTHETIC DEMO DATA" : report.raw_pixels ? "IMPORTED OBSERVATIONS" : "NO IMPORTED PIXELS";
    $("study-status-text").textContent = `${report.config.year}-${String(report.config.month).padStart(2,"0")} through ${report.config.as_of} · ${complete ? "Both source exports complete" : "Incomplete source exports; descriptive imported counts only"} · No calibrated sensitivity estimate.`;
    $("research-pixels").textContent = number(report.raw_pixels);
    $("research-shared").textContent = number(overlap.totals.both);
    $("research-ratio").textContent = overlap.ratio == null ? "—" : `${number(overlap.ratio)}×`;
    $("research-groups").textContent = number(report.candidates.count);
    $("comparison-status").textContent = complete ? "COMPLETE SOURCE EXPORTS" : "PARTIAL IMPORTS";
    $("overlap-percent").textContent = overlap.jaccard == null ? "—" : `${number(overlap.jaccard * 100)}%`;
    $("overlap-breakdown").replaceChildren();
    for (const [name, key] of [["MODIS only", "modis_only"], ["Both sensors", "both"], ["VIIRS only", "viirs_only"]]) {
      const row = el("div"); row.append(el("span", "", name), el("b", "", number(overlap.totals[key]))); $("overlap-breakdown").append(row);
    }
    $("ratio-band").textContent = overlap.ratio_band ? `${number(overlap.ratio_band[0])}–${number(overlap.ratio_band[1])}×` : "Not estimated";
    const reasons = {insufficient_active_days: `${overlap.active_days} active days available; at least 10 are required for the exploratory band.`, incomplete_exports: "Complete exports from both sources are required.", mixed_product_versions: "Mixed product versions require a collection-equivalence review.", zero_modis_denominator: "No MODIS cell-days: the ratio has no denominator.", unstable_denominator: "Resampling produced too many zero denominators.", exploratory: "Paired-day percentile range. This is descriptive variability, not calibrated sensor sensitivity."};
    $("band-reason").textContent = reasons[overlap.band_status];
    $("source-versions").textContent = Object.entries(overlap.product_versions).map(([source, versions]) => `${source}: ${versions.length ? versions.join(", ") : "no records"} · ${overlap.raw_pixels[source] || 0} raw pixels`).join(" | ");
    $("study-hash-short").textContent = report.report_id.slice(0,12);
    $("study-hash").textContent = `Study SHA-256: ${report.report_id} · method ${report.method_version}`;
    $("study-temporal-note").textContent = report.temporal_scope;
    $("study-provenance").replaceChildren();
    for (const source of report.provenance) $("study-provenance").append(el("div", "provenance-file", `${source.source_id} · ${source.source_uri} · SHA-256 ${source.file_sha256}`));
    renderChart(); drawCandidates(); renderCandidateDetail(); renderCoverage(); fitMap();
  }
  function download(value, name) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {type: "application/json"}));
    const link = el("a"); link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  document.addEventListener("DOMContentLoaded", async () => {
    months.forEach((name, i) => { const option = el("option", "", name); option.value = i + 1; $("research-month").append(option); });
    $("research-month").value = "7";
    $("research-form").addEventListener("submit", event => { event.preventDefault(); run(); });
    for (const id of ["research-year", "research-month"]) $(id).addEventListener("change", dateRange);
    $("rebuild-candidates").addEventListener("click", () => { if ($("research-form").reportValidity()) run(); });
    $("fit-candidates").addEventListener("click", fitMap);
    $("export-study").addEventListener("click", () => download({format: "fireatlas-study-export-v1", report: state.report, input_mask: state.mask}, `fireatlas-research-${state.report.config.as_of}.json`));
    $("download-mask").addEventListener("click", () => download(state.mask, "fireatlas-coverage-mask.json"));
    $("clear-mask").addEventListener("click", async () => { if (await run(null, true)) $("coverage-file").value = ""; });
    $("coverage-file").addEventListener("change", async event => {
      const file = event.target.files[0]; if (!file) return;
      try {
        if (file.size > 2_900_000) throw new Error("Mask files must be smaller than 2.9 MB.");
        const mask = JSON.parse(await file.text()); await run(mask, true);
      } catch (error) { showError(error instanceof SyntaxError ? "This file is not valid JSON." : error.message); }
    });
    $("example-mask").addEventListener("click", async () => {
      if (state.busy) return;
      setBusy(true);
      try {
        const mask = await json(`/api/research/coverage-example?${query(config())}`);
        setBusy(false); await run(mask, true);
      } catch (error) { setBusy(false); showError(error.message); }
    });
    try {
      const meta = await json("/api/meta");
      const defaults = meta.default_view || {year:2015,month:7,bbox:[-122,39,-120,41]};
      const years = [...new Set([...meta.years, defaults.year])];
      $("research-year").replaceChildren(...years.map(year => { const option = el("option", "", year); option.value = year; return option; }));
      $("research-year").value = String(defaults.year);
      $("research-month").value = String(defaults.month);
      $("research-bbox").value = defaults.bbox.join(",");
      const params = new URLSearchParams(location.search);
      if (years.includes(Number(params.get("year")))) $("research-year").value = params.get("year");
      if (Number(params.get("month")) >= 1 && Number(params.get("month")) <= 12) $("research-month").value = params.get("month");
      if (params.has("bbox")) $("research-bbox").value = params.get("bbox");
      dateRange(); initMap(); await run();
      // Populate the optional exposure demonstration only on an explicit showcase link.
      if (demo && params.get("exposure") === "synthetic" && state.report?.raw_pixels) {
        const mask = await json(`/api/research/coverage-example?${query(config())}`);
        await run(mask, true);
      }
    } catch (error) { showError(error.message); $("study-results").hidden = true; }
  });
})();
