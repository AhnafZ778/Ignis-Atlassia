(() => {
  const C = window.FireAtlasContext;
  const view = document.body.dataset.researchView;
  const $ = id => document.getElementById(id);
  const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  let report = null, mask = null, map = null, mapLayer = null, contextLayer = null, selectedId = null,requestVersion=0,scopeStart=new URLSearchParams(location.search).get("start")||null;
  let contextDate = null, contextErrors = 0;
  function contextStatus() {
    const target = $("candidate-context-status");
    if (!target || !contextDate) return;
    target.textContent = contextErrors
      ? `Some vegetation tiles could not load. The detections remain available over the base map. Requested NDVI composite: ${contextDate}.`
      : `NASA MODIS NDVI · requested 16-day composite starting ${contextDate}. Vegetation context has its own date; it is not a fire-day reading.`;
    target.dataset.status = contextErrors ? "partial" : "context";
  }
  const n = value => value == null ? "—" : Number(value).toLocaleString();
  function endDate(year, month) { return new Date(Date.UTC(year, month, 0)).toISOString().slice(0, 10); }
  function compositeDate(date) {
    const selected = new Date(`${date}T00:00:00.000Z`);
    const first = Date.UTC(selected.getUTCFullYear(), 0, 1);
    const elapsed = Math.floor((selected.getTime() - first) / 86400000);
    return new Date(first + Math.floor(elapsed / 16) * 16 * 86400000).toISOString().slice(0, 10);
  }
  function fields() {
    const context = C.read();
    const year = Number($("deep-year")?.value || context.year), month = Number($("deep-month")?.value || context.month);
    const output = {year, month, bbox: C.validBBox($("deep-bbox") ? $("deep-bbox").value : context.bbox, true).split(",").map(Number), as_of: $("deep-as-of")?.value || endDate(year, month), distance_km: Number($("deep-distance")?.value || context.distance_km), gap_days: Number($("deep-gap")?.value || context.gap_days)};
    if(scopeStart&&scopeStart.startsWith(`${year}-${String(month).padStart(2,"0")}`))output.start_date=scopeStart;return output;
  }
  function syncContext() {
    let config; try { config = fields(); $("deep-bbox")?.removeAttribute("aria-invalid"); } catch (_) { $("deep-bbox")?.setAttribute("aria-invalid","true"); return; }
    const url = new URL(location.href);
    url.search = C.write({...C.read(), ...config});if(config.start_date)url.searchParams.set("start",config.start_date);
    history.replaceState(null, "", url);
    C.apply(document, {...C.read(), ...config});
  }
  function showError(message) { const target = $("deep-error"); if (!target) return; target.hidden = false; target.textContent = message; }
  function setState(label, kind = "unknown") { C.status($("deep-state"), label, kind); }
  function renderStatus() { const cfg = report?.config; if ($("deep-status")) $("deep-status").textContent = cfg ? `${cfg.start_date||`${cfg.year}-${String(cfg.month).padStart(2, "0")}-01`} through ${cfg.as_of} · ${report.data_status === "empty" ? "No imported pixels" : "Imported study rows loaded"}.` : "No study loaded."; }
  async function getReport(nextMask = undefined,request) {
    const config = fields();
    const requestedMask = nextMask !== undefined ? nextMask : mask;
    const options = nextMask !== undefined || requestedMask ? {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({config, mask: requestedMask})} : {method: "GET"};
    const query=C.api(config);if(config.start_date)query.set("start_date",config.start_date);const response = await fetch(`/api/research${options.method === "GET" ? `?${query.toString()}` : ""}`, {...options, signal: AbortSignal.timeout(30000)});
    const body = await response.json(); if (!response.ok) { const error = new Error(body.error || "The local analysis service rejected this study."); error.status = response.status; throw error; }
    if(request!==requestVersion)return null;
    mask = requestedMask;
    C.apply(document, {...C.read(), ...config});
    report = body; syncContext(); renderStatus();
    document.dispatchEvent(new CustomEvent('fireatlas:study-applied',{detail:report.config}));
    return body;
  }
  function initMap() {
    if (view !== "candidates" || typeof L === "undefined" || !$("deep-map")) return;
    map = L.map("deep-map", {scrollWheelZoom: false, attributionControl: false, minZoom: 2, maxZoom: 14}); window.FireAtlasViews?.registerMap("candidates",map);
    L.control.attribution({prefix: false, position: "bottomright"}).addTo(map);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom: 18, attribution: "© OpenStreetMap contributors", keepBuffer: 2}).addTo(map);
    const date = compositeDate(C.read().as_of);
    contextDate = date;
    const url = `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_L3_NDVI_16Day/default/${date}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.png`;
    contextLayer = L.tileLayer(url, {attribution: "NASA GIBS / MODIS", opacity: .86, maxNativeZoom: 9, maxZoom: 18, keepBuffer: 3}).addTo(map);
    contextLayer.on("tileerror", () => { contextErrors++; contextStatus(); });
    contextLayer.on("load", contextStatus);
    contextStatus();
    map.setView([40.1, -121.1], 8); mapLayer = L.layerGroup().addTo(map);
  }
  function groupOrder(groups) {
    const sort = $("candidate-sort")?.value || "first";
    return [...groups].sort((a, b) => sort === "days" ? b.days - a.days || a.first_utc.localeCompare(b.first_utc) : sort === "cells" ? b.cell_days - a.cell_days || a.first_utc.localeCompare(b.first_utc) : sort === "pixels" ? b.raw_pixels - a.raw_pixels || a.first_utc.localeCompare(b.first_utc) : a.first_utc.localeCompare(b.first_utc));
  }
  function fitGroups(includeAll = true) {
    if (!map || !report) return;
    const selected = includeAll ? null : report.candidates.groups.find(group => group.id === selectedId);
    const groups = selected ? [selected] : report.candidates.groups;
    const points = groups.flatMap(group => group.points.map(point => [point.coordinates[1], point.coordinates[0]]));
    if (points.length) map.fitBounds(L.latLngBounds(points).pad(.2), {padding: [25, 25], maxZoom: 11});
    else { const [west, south, east, north] = report.config.bbox; map.fitBounds([[south, west], [north, east]], {padding: [20, 20]}); }
  }
  function drawGroups(fit = false) {
    if (view !== "candidates" || !report) return;
    if (contextLayer) {
      const date = compositeDate(report.config.as_of);
      if (date !== contextDate) {
        contextDate = date; contextErrors = 0;
        contextLayer.setUrl(`https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_L3_NDVI_16Day/default/${date}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.png`);
      }
      contextStatus();
    }
    const groups = groupOrder(report.candidates.groups || []); $("candidate-count").textContent = `${groups.length} groups`; $("candidate-list").replaceChildren(); $("candidate-table").replaceChildren(); mapLayer?.clearLayers();
    if (!groups.length) $("candidate-list").append(Object.assign(document.createElement("div"), {className: "empty-state", textContent: "No imported detections in this selection. An empty result does not establish fire-free conditions."}));
    groups.forEach((group, index) => {
      const selected = group.id === selectedId;
      const button = document.createElement("button"); button.type = "button"; button.className = selected ? "selected candidate-item" : "candidate-item"; button.setAttribute("aria-pressed", String(selected));
      const label = String(report.candidates.groups.findIndex(item => item.id === group.id) + 1).padStart(2, "0");
      button.innerHTML = `<span class="candidate-index">${label}</span><span><strong>Candidate ${label}</strong><small>${group.first_utc.slice(0, 10)} → ${group.last_utc.slice(0, 10)} · ${group.days} detected days</small><small>${group.cell_days} cell-days · ${group.raw_pixels} raw pixels</small><small>Sources: ${group.sources.map(source => source === "MODIS_SP" ? "MODIS" : source === "VIIRS_SNPP_SP" ? "VIIRS S-NPP" : source).join(" + ")}</small></span>`;
      button.addEventListener("click", () => { selectedId = group.id; drawGroups(true); renderDetail(); }); $("candidate-list").append(button);
      const row = document.createElement("tr"); [group.id, `${group.first_utc.slice(0, 10)} → ${group.last_utc.slice(0, 10)}`, group.days, group.cell_days, group.raw_pixels, group.sources.join(" + ")].forEach(value => { const cell = document.createElement("td"); cell.textContent = value; row.append(cell); }); $("candidate-table").append(row);
      if (!map) return;
      const unique = new Map(); group.points.forEach(point => { const key = `${point.grid_x},${point.grid_y}`; if (!unique.has(key)) unique.set(key, point); });
      unique.forEach(point => {
        const marker = L.circleMarker([point.coordinates[1], point.coordinates[0]], {radius: selected ? 10 : 6, color: selected ? "#2457D6" : "#ffffff", weight: selected ? 4 : 1.5, fillColor: "#53697A", fillOpacity: selected ? .9 : .62});
        marker.bindTooltip(`${group.id} · ${point.date} · grid ${point.grid_x}, ${point.grid_y}`, {direction: "top"}); marker.on("click", () => { selectedId = group.id; drawGroups(true); renderDetail(); }); marker.addTo(mapLayer);
      });
    });
    if (fit === true) fitGroups(false);
  }
  function renderDetail() {
    if (view !== "candidates" || !report) return;
    const group = report.candidates.groups.find(item => item.id === selectedId); const target = $("candidate-detail"); target.replaceChildren();
    if (!group) { target.innerHTML = '<div class="empty-state">Select a candidate to inspect its membership.</div>'; return; }
    const heading = document.createElement("div"); heading.className = "panel-heading"; heading.innerHTML = `<div><p class="eyebrow">SELECTED CANDIDATE</p><h3>Candidate ${String(report.candidates.groups.findIndex(item => item.id === group.id) + 1).padStart(2, "0")}</h3><p>${group.first_utc} → ${group.last_utc} · ${group.sources.map(source => source === "MODIS_SP" ? "MODIS" : source === "VIIRS_SNPP_SP" ? "VIIRS S-NPP" : source).join(" + ")}</p></div><span class="status-tag partial">CONNECTED SAMPLE</span>`; target.append(heading);
    const details = document.createElement("details"); const summary = document.createElement("summary"); summary.textContent = `Group ${group.id} · inspect ${group.cell_days} cell-days and original detection IDs`; const list = document.createElement("ul");
    group.points.forEach(point => { const item = document.createElement("li"); item.textContent = `${point.date} · grid ${point.grid_x}, ${point.grid_y} · ${point.coordinates.map(value => Number(value).toFixed(5)).join(", ")}`; list.append(item); }); details.append(summary, list); const ids = document.createElement("p"); ids.textContent = `Detection IDs: ${group.detection_ids.join(", ")}`; details.append(ids); target.append(details);
  }
  function renderCoverage() {
    if (view !== "exposure" || !report) return;
    $("exposure-detections").textContent = n(report.raw_pixels); const coverage = report.coverage || {status: "unavailable", sources: []};
    const statusLabels = {unavailable: ["Unavailable", "unavailable"], synthetic: ["Synthetic demonstration", "partial"], user_supplied_unvalidated: ["User-supplied · unvalidated", "partial"], validated: ["Validated", "available"]};
    const [label, kind] = statusLabels[coverage.status] || [coverage.status || "Unknown", "unknown"]; $("exposure-mask-status").textContent = label; C.status($("deep-state"), label.toUpperCase(), kind); $("exposure-mask-note").textContent = coverage.provenance || "No observation mask supplied."; $("mask-message").textContent = mask ? `${mask.synthetic ? "Synthetic demonstration" : "User-supplied unvalidated"} · ${mask.cells?.length || 0} rows. ${coverage.provenance || ""}` : coverage.note;
    const target = $("coverage-output"); target.replaceChildren();
    if (coverage.status === "unavailable" || !coverage.sources?.length) { target.innerHTML = `<div class="empty-state"><strong>Exposure is unknown.</strong><br>${coverage.note || "Upload an explicit observation mask to calculate a denominator."}</div>`; return; }
    coverage.sources.forEach(source => { const row = document.createElement("article"); row.className = "coverage-rate-card"; const hasRate = source.per_100_observed_cell_days != null && source.observed_cell_days > 0; row.innerHTML = `<div class="panel-heading"><div><h3>${source.source_id}</h3><p>${source.detected_in_mask} detected in mask · ${source.observed_cell_days} observed cell-days</p></div><span class="status-tag ${hasRate ? "available" : "partial"}">${source.status}</span></div><strong class="coverage-rate">${hasRate ? `${Number(source.per_100_observed_cell_days).toFixed(2)}%` : "Rate withheld"}</strong><p>${hasRate ? `${label} mask · denominator: ${source.observed_cell_days} observed cell-days · detected cell-days / observed cell-days × 100` : "A percentage is withheld until a non-zero denominator and a complete source export are available."}</p><p class="lab-muted">Mask rows: ${Object.entries(source.mask_counts || {}).map(([key, value]) => `${key}: ${value}`).join(" · ") || "none"}.</p>`; target.append(row); });
    const note = document.createElement("p"); note.className = "notice-panel"; note.textContent = coverage.note || "Rates apply only to supplied observed cell-days."; target.append(note);
  }
  function validationCards() {
    const target = $("study-requirement-gates") || $("validation-gates"); target.replaceChildren(); const gates = report?.gates || {};
    const items = [["calibration", "Sensor sensitivity calibration", "Requires matched overpasses, observation masks, reference labels, and independent holdout validation."], ["radar", "Radar cross-check", "Requires co-registered SAR before/after scenes, quality masks, and dated optical cross-check."], ["spread", "Spread model", "Requires a validated regional fuel/terrain model, weather ensemble, and held-out arrival observations."], ["independent", "Independent validation", "Requires an incident or perimeter reference set independent of the FIRMS rows."]];
    items.forEach(([key, title, description]) => { const card = document.createElement("article"); card.className = "validation-card"; card.innerHTML = `<span>${key === "independent" ? "04" : key === "calibration" ? "01" : key === "radar" ? "02" : "03"} / ${title.toUpperCase()}</span><strong>${key === "independent" ? "REQUIRES EXTERNAL EVIDENCE" : "NOT AVAILABLE"}</strong><p>${gates[key] || description}</p>`; target.append(card); });
  }
  function renderCaseGates(body) {
    const target = $("validation-gates"); target.replaceChildren();
    const scope = document.createElement("p"); scope.className="case-evidence-scope";
    scope.textContent=`Named case: ${body.title || body.case_id} · ${body.start_utc} → ${body.end_utc} UTC · AOI ${body.bbox?.join(", ")}. These gates apply to this case, independently of the study controls.`;
    target.append(scope);
    const grid=document.createElement("div");grid.className="validation-grid";
    for (const gate of body.validation_gates || []) {
      const card=document.createElement("article");card.className="validation-card";
      const title=document.createElement("h3");title.textContent=gate.label;
      const state=document.createElement("span");state.className=`status-tag ${gate.status === "passed" ? "available" : "partial"}`;state.textContent=gate.status === "passed" ? "Passed" : gate.status === "pending" ? "Pending review" : gate.status;
      const values=document.createElement("strong");values.className="case-gate-values";values.textContent=`${n(gate.actual)} / ${n(gate.required)} ${gate.unit || ""}`;
      card.append(title,state,values);grid.append(card);
    }
    target.append(grid);
    const note=document.createElement("p");note.className="notice-panel";note.textContent=`Native-mask status: ${body.native_masks?.status || "unknown"}. Processing and row matching do not establish independent review, complete spatial coverage or a validated spread model.`;target.append(note);
  }
  function schemaTemplate() {
    const config = fields(); return {format: "fireatlas-coverage-v1", grid: "ease6933-centroid-1km-v1", bbox: Array.isArray(config.bbox) ? config.bbox : config.bbox.split(",").map(Number), start_date: config.start_date||`${config.year}-${String(config.month).padStart(2, "0")}-01`, end_date: config.as_of, synthetic: false, provenance: "Describe the upstream observation-mask source.", method: "Describe how source/cell/day statuses were derived.", cells: []};
  }
  function download(value, name) { const href = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {type: "application/json"})); const link = document.createElement("a"); link.href = href; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(href), 1000); }
  async function run(event, suppliedMask) {
    event?.preventDefault();
    const request=++requestVersion;
    if (document.querySelector('meta[name="fireatlas-static-data"]')) {
      showError("Research calculations require the local analysis service. The Atlas and Fire replay can explore the observations bundled in this release.");
      setState("SERVICE REQUIRED","unavailable");
      if ($("deep-run")) { $("deep-run").disabled=true; $("deep-run").textContent="Analysis service required"; }
      if (view === "exposure") { $("coverage-file").disabled=true; $("coverage-output").innerHTML='<div class="empty-state">Exposure rates are unavailable without a connected analysis service and accepted coverage mask.</div>'; }
      if (view === "candidates") $("candidate-list").innerHTML='<div class="empty-state">Candidate results are unavailable in this static release. No candidate count has been calculated.</div>';
      if (view === "validation") $("validation-gates").innerHTML='<div class="empty-state">Live validation gates require the analysis service. Bundled evidence is available on the Method and Review pages.</div>';
      return false;
    }
    if ($("deep-error")) $("deep-error").hidden = true; if ($("deep-run")) { $("deep-run").disabled = true; $("deep-run").textContent = "Loading…"; }
    try {
      if(!await getReport(suppliedMask,request))return false;
      if (view === "candidates") { selectedId = report.candidates.groups[0]?.id || null; drawGroups(true); renderDetail(); setState(report.data_status === "empty" ? "NO IMPORTED PIXELS" : "RESULT READY", report.data_status === "empty" ? "unknown" : "available"); }
      if (view === "exposure") renderCoverage();
      if (view === "validation") {
        validationCards();
        const caseId = $("validation-case")?.value || "park-2024";
        document.querySelectorAll("[data-validity-case-link]").forEach(link=>{const url=new URL(link.href);url.searchParams.set("case",caseId);link.href=url;});
        setState("CHECKING EVIDENCE","unknown");
        $("validity-summary").textContent = `Checking the source-file evidence register for ${caseId}… Scientific gate results are available above.`;
        const response = await fetch(`/api/validity?case=${encodeURIComponent(caseId)}`, {signal: AbortSignal.timeout(90000)});
        const body = await response.json();
        if(request!==requestVersion)return false;
        if (response.ok) renderCaseGates(body);
        $("validity-summary").textContent = response.ok ? `Evidence register loaded for ${caseId}. Source records and processing checks remain distinct from independent scientific validation.` : "Validity report unavailable; the gate states above remain unchanged.";
        setState(response.ok ? "EVIDENCE LOADED" : "UNAVAILABLE",response.ok ? "available" : "unknown");
      }
      return true;
    } catch (error) { if(request===requestVersion){showError(error.name === "TimeoutError" ? view === "validation" ? "The source-file evidence check timed out. The scientific gate results above remain available; retry the evidence check." : "The local analysis timed out. Narrow the AOI or cutoff and try again." : `${error.status === 400 || error.status === 422 ? suppliedMask ? "Coverage mask rejected" : "Study settings rejected" : "Local analysis service required"}: ${error.message}`); setState(error.status === 400 || error.status === 422 ? "INPUT REJECTED" : "UNAVAILABLE", "unavailable");} return false; }
    finally { if (request===requestVersion && $("deep-run")) { $("deep-run").disabled = false; $("deep-run").textContent = view === "exposure" ? "Match study context ↗" : view === "validation" ? "Check study gates" : "Run candidate analysis ↗"; } }
  }
  async function init() {
    const context = C.read();
    if ($("deep-month")) months.forEach((name, index) => $("deep-month").add(new Option(name, index + 1)));
    if ($("deep-year")) {
      $("deep-year").replaceChildren(new Option(context.year,context.year));
      if(!document.querySelector('meta[name="fireatlas-static-data"]'))fetch("/api/meta",{signal:AbortSignal.timeout(12000)}).then(r=>r.ok?r.json():Promise.reject()).then(meta=>{const current=Number($("deep-year").value)||context.year,years=[...new Set([...(meta.years||[]),current])].sort((a,b)=>a-b);$("deep-year").replaceChildren(...years.map(year=>new Option(year,year)));$("deep-year").value=String(current);}).catch(()=>{});
    }
    C.apply(document, context); if ($("deep-as-of") && !$("deep-as-of").value) $("deep-as-of").value = endDate(context.year, context.month); if ($("deep-month")) $("deep-month").addEventListener("change", () => { $("deep-as-of").value = endDate(Number($("deep-year").value), Number($("deep-month").value)); });
    $("deep-form")?.addEventListener("submit", event => run(event)); $("deep-form")?.addEventListener("input", syncContext); $("deep-form")?.addEventListener("change", syncContext); $("candidate-sort")?.addEventListener("change", () => drawGroups(false)); $("candidate-fit")?.addEventListener("click", fitGroups); $("coverage-file")?.addEventListener("change", async event => { const file = event.target.files?.[0]; if (!file) return; try { if (file.size > 2_900_000) throw new Error("Mask files must be smaller than 2.9 MB."); const accepted = await run(null, JSON.parse(await file.text())); if (accepted && $("coverage-download")) $("coverage-download").disabled = false; } catch (error) { showError(error instanceof SyntaxError ? "This file is not valid JSON." : error.message); } }); $("coverage-example")?.addEventListener("click", () => download(schemaTemplate(), "fireatlas-coverage-mask-template.json")); $("coverage-download")?.addEventListener("click", () => { if (mask) download(mask, "fireatlas-coverage-mask.json"); }); $("validation-refresh")?.addEventListener("click", () => run()); $("validation-case")?.addEventListener("change", () => run());
    if (view === "candidates") initMap(); await run();
  }

  document.addEventListener('DOMContentLoaded', () => window.FireAtlasViews?.register(document.body.dataset.page, {
    capabilities:['study controls','candidate evidence','coverage status','scientific gates'],
    context:()=>{try{const {start_date,...c}=fields();return {...c,start:start_date||`${c.year}-${String(c.month).padStart(2,'0')}-01`,end:c.as_of,day:''};}catch{return {};}},
    state:()=>({ready:Boolean(report),report_id:report?.report_id,method:report?.method_version,coverage_mask:mask?'user-supplied; see validation status':'unavailable'}),
    selection:()=>selectedId?{candidate_id:selectedId,report_id:report?.report_id}:null,
    apply:async (cfg,action)=>{if(cfg.start?.slice(0,7)!==cfg.end?.slice(0,7))throw Error('Choose a single UTC month for this analysis.');scopeStart=cfg.start;if($('validation-case')&&cfg.case)$('validation-case').value=cfg.case;C.apply(document,{...cfg,bbox:cfg.bbox.join(','),as_of:cfg.end});if(!await run())throw Error('Study analysis could not be loaded.');if(action?.options?.candidate_id){const group=report.candidates.groups.find(g=>g.id===action.options.candidate_id);if(!group)throw Error('Candidate does not belong to this report.');selectedId=group.id;drawGroups();renderDetail();if(map&&group.points.length)map.fitBounds(group.points.map(p=>[p.coordinates[1],p.coordinates[0]]),{maxZoom:13});}}
  }));

  document.addEventListener("DOMContentLoaded", init);
})();
