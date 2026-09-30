/* Authentic NASA observations on the existing analytic Earth renderer. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const format = value => new Intl.NumberFormat("en", {maximumFractionDigits:1}).format(value);
  const stamp = value => value ? value.replace("T", " · ").replace(":00Z", " UTC") : "Unknown";
  const coords = (lon, lat) => `${Math.abs(lat).toFixed(2)}°${lat < 0 ? "S" : "N"} / ${Math.abs(lon).toFixed(2)}°${lon < 0 ? "W" : "E"}`;
  const motionPreference = matchMedia("(prefers-reduced-motion: reduce)");
  const state = {
    data: null,
    points: [],
    wildfires: null,
    wildfireReviewedOn: null,
    wildfireLoading: null,
    visible: [],
    selected: null,
    selectedWildfire: null,
    details: null,
    bridge: null,
    frame: null,
    canvas: null,
    context: null,
    request: 0,
    detailRequest: 0,
    controller: null,
    detailController: null,
    failedEarth: false,
    fullDaily: null,
    windowStart: null,
    windowEnd: null,
    loading: null,
    revealed: false,
    revealRequest: 0,
    revealing: false,
    region: "world",
    pendingZoom: null
  };

  function element(tag, text, className) {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (className) el.className = className;
    return el;
  }

  function observationDate(value, includeTime = false) {
    if (!value) return "Unknown";
    const date = new Date(value.length === 10 ? value + "T00:00:00Z" : value);
    return new Intl.DateTimeFormat("en-GB", {
      day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
      ...(includeTime ? {hour: "2-digit", minute: "2-digit", hour12: false} : {})
    }).format(date) + (includeTime ? " UTC" : "");
  }

  function renderObservationPeriod(data) {
    const period = $("globe-period");
    const start = data.date === "all" ? data.window_start : data.date;
    const end = data.date === "all" ? data.window_end : data.date;
    const range = start === end || !start || !end ? observationDate(start) : new Intl.DateTimeFormat("en-GB", {
      day: "numeric", month: "short", year: "numeric", timeZone: "UTC"
    }).formatRange(new Date(start + "T00:00:00Z"), new Date(end + "T00:00:00Z"));
    const latest = data.clusters.reduce((last, group) => !last || group.last > last ? group.last : last, null);
    const values = data.latest_observation
      ? [["Observed", range], ["Last detected", latest ? observationDate(latest, true) : "None in selection"]]
      : [["Observed", "No snapshot imported"], ["Last detected", "Unavailable"]];
    period.replaceChildren(...values.map(([label, value]) => {
      const row = element("div");
      row.append(element("dt", label), element("dd", value));
      return row;
    }));
  }

  function setRotationUI(playing) {
    const btn = $("globe-rotate");
    if (!btn) return;
    const label = playing ? "Pause rotation" : "Resume rotation";
    const symbol = playing ? "Ⅱ" : "▷";
    if (btn.textContent !== symbol) btn.textContent = symbol;
    btn.setAttribute("aria-label", label);
    btn.title = label;
    if (btn.getAttribute("aria-pressed") !== String(!playing)) btn.setAttribute("aria-pressed", String(!playing));
  }

  function updateLayerStamp() {
    $("globe-layer-label").textContent = "NASA SATELLITE EVIDENCE";
    $("globe-layer-icon").setAttribute("href", "./vendor/lucide-icons.svg#satellite");
    const data = state.data;
    $("globe-stamp").textContent = data?.latest_observation
      ? `${data.date === "all" ? data.window_start + " → " + data.window_end : data.date} · IMPORTED SNAPSHOT`
      : "NASA observation snapshot loading";
  }

  function revealStatus(text) {
    $("globe-reveal-status").textContent = text;
    $("globe-reveal-status").hidden = !text;
  }

  async function toggleWildfires() {
    const toggle = $("globe-wildfires"), note = $("globe-wildfire-note");
    if (!toggle.checked) {
      note.hidden = true;
      $("globe-wildfire-browser").hidden = true;
      if (state.selectedWildfire) clearSelection();
      draw(state.bridge?.view);
      return;
    }
    note.hidden = false;
    note.textContent = "Loading selected historical examples…";
    try {
      if (!state.wildfires) {
        state.wildfireLoading ||= (async () => {
          const embedded = $("globe-wildfire-data")?.textContent.trim();
          let data;
          if (embedded) {
            data = JSON.parse(embedded);
          } else {
            const response = await fetch("./documented-fires.json");
            data = await response.json();
            if (!response.ok) throw new Error(data.error || "Historical casebook unavailable.");
          }
          if (data.kind !== "selected-global-wildfire-casebook" || !Array.isArray(data.events)) {
            throw new Error("Historical casebook format was not recognized.");
          }
          const safeSources = sources => (Array.isArray(sources) ? sources : []).filter(source => {
            if (!source || typeof source.publisher !== "string" || typeof source.label !== "string" || typeof source.url !== "string") return false;
            try { return ["https:", "http:"].includes(new URL(source.url).protocol); } catch { return false; }
          });
          const events = data.events.filter(event => event && typeof event.id === "string" &&
            typeof event.name === "string" && typeof event.place === "string" &&
            typeof event.period === "string" && typeof event.summary === "string" &&
            Number.isFinite(event.lat) && event.lat >= -90 && event.lat <= 90 &&
            Number.isFinite(event.lon) && event.lon >= -180 && event.lon <= 180 &&
            safeSources(event.sources).length > 0).map(event => ({...event, sources: safeSources(event.sources)}));
          if (!events.length) throw new Error("No valid historical locations were found.");
          return {events: events.map(event => ({...event, historicalCase: true, vector: FireGlobeMath.vector(event.lon, event.lat)})), reviewedOn: data.reviewed_on, excluded: data.events.length - events.length};
        })().catch(error => {
          state.wildfireLoading = null;
          throw error;
        });
        const loaded = await state.wildfireLoading;
        state.wildfires = loaded.events;
        state.wildfireReviewedOn = loaded.reviewedOn;
        const select = $("globe-wildfire-location");
        select.replaceChildren(new Option("Choose a case…", ""), ...state.wildfires.map(item => new Option(`${item.name} · ${item.period}`, item.id)));
        $("globe-wildfire-browser").hidden = false;
        $("globe-wildfire-browser").dataset.excluded = String(loaded.excluded);
        state.wildfireLoading = null;
      }
      const skipped = Number($("globe-wildfire-browser").dataset.excluded || 0);
      note.textContent = `${state.wildfires.length} sourced historical cases loaded${skipped ? ` · ${skipped} incomplete records skipped` : ""} · approximate locations, not live or perimeters.`;
      $("globe-wildfire-browser").hidden = false;
      draw(state.bridge?.view);
    } catch (error) {
      toggle.checked = false;
      note.textContent = `Historical wildfire examples unavailable: ${error.message}`;
      draw(state.bridge?.view);
    }
  }

  function syncControls() {
    document.querySelectorAll("[data-globe-region],#globe-rotate,#globe-zoom-in,#globe-zoom-out,#globe-reset").forEach(b => b.disabled = state.revealing || state.failedEarth);
    $("globe-source").disabled = state.revealing || !!state.loading || !state.data?.sources.length;
    $("globe-date").disabled = $("globe-source").disabled;
    $("globe-location").disabled = state.revealing || !!state.loading || !state.data?.total;
    document.querySelectorAll(".imprint-bar,#imprint-reset").forEach(b => b.disabled = state.revealing || !!state.loading);
    document.querySelectorAll(".globe-location-actions button").forEach(b => b.disabled = state.revealing || state.failedEarth);
  }

  function cancelReveal() {
    state.revealRequest++;
    state.bridge?.cancelOrbit();
    state.revealing = false;
    state.revealed = false;
    revealStatus("");
    syncControls();
  }

  async function revealDetections() {
    cancelReveal();
    const request = state.revealRequest;
    if (!$("globe-markers").checked) {
      clearSelection();
      $("globe-status").textContent = "Detections hidden.";
      return;
    }
    const needsData = !state.data || Boolean(state.loading);
    state.revealing = needsData;
    revealStatus(needsData ? "Loading data…" : "");
    syncControls();
    const dataReady = state.loading || (state.data ? Promise.resolve(true) : load());
    // The checkbox can be used before WebGL finishes initializing.
    if (needsData && !state.bridge && !state.failedEarth) return;
    const turn = needsData && state.bridge ? state.bridge.rotateOnce() : Promise.resolve(true);
    const [loaded, completed] = await Promise.all([dataReady, turn]);
    if (request !== state.revealRequest || !$("globe-markers").checked) return;
    state.revealing = false;
    state.revealed = Boolean(loaded && completed);
    revealStatus("");
    if (!state.revealed) $("globe-markers").checked = false;
    else $("globe-status").textContent = state.data.total ? (state.failedEarth ? "3D unavailable · browse locations below." : "Select a point to inspect.") : "No imported detections · coverage unknown.";
    syncControls();
    draw(state.bridge?.view);
  }

  function updateLocations() {
    const region = window.FireAtlasRegions?.[state.region];
    let points = state.data?.clusters || [];
    if(region && state.region !== "world") {
      const [[south,west],[north,east]] = region.bounds;
      points = points.filter(p => p.lat>=south && p.lat<=north && p.lon>=west && p.lon<=east);
    }
    $("globe-location").replaceChildren(new Option(`${region?.name || "Worldwide"} · ${points.length ? "largest groups…" : "no observations"}`, ""), ...points.slice(0,40).map(c => new Option(`${coords(c.lon,c.lat)} · ${format(c.count)}`, c.id)));
    document.querySelectorAll("[data-region-key]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.regionKey===state.region)));
  }

  function focus(lon, lat) {
    state.pendingZoom = null;
    state.bridge?.focus(lon, lat);
    setRotationUI(false);
  }

  function zoomToLocation(lon, lat, altitude = 180000) {
    if (state.failedEarth) return;
    if (state.bridge) state.bridge.focus(lon, lat, {altitude});
    else state.pendingZoom = {lon, lat, altitude};
    setRotationUI(false);
    closeEarthDetails();
    document.querySelector(".globe-hero").scrollIntoView({behavior: motionPreference.matches ? "auto" : "smooth", block: "start"});
  }

  function openEarthDetails() {
    const dialog = $("earth-details-dialog");
    const console = document.querySelector(".globe-console");
    const historical = Boolean(state.selectedWildfire);
    $("globe-evidence-tools").hidden = historical;
    $("globe-wildfire-browser").hidden = !state.wildfires?.length || !$("globe-wildfires").checked;
    if (historical) $("globe-evidence-tools").open = false;
    console.classList.toggle("has-historical-selection", historical);
    if (!dialog.open) dialog.showModal();
    document.documentElement.classList.add("earth-details-visible");
  }

  function selectedLocation() {
    return state.selectedWildfire
      ? state.wildfires?.find(item => item.id === state.selectedWildfire)
      : state.points.find(point => point.id === state.selected);
  }

  function showPointCallout(record) {
    closeEarthDetails();
    $("point-callout-kind").textContent = record.historicalCase ? "Historical wildfire case" : "NASA satellite group";
    $("point-callout-title").textContent = record.historicalCase ? record.name : `${format(record.count)} detections`;
    $("point-callout-meta").textContent = record.historicalCase
      ? `${record.place} · ${record.period} · approximate area`
      : `${coords(record.lon, record.lat)} · Last observed ${observationDate(record.last, true)}`;
    $("point-callout-zoom").disabled = state.failedEarth;
    positionPointCallout(state.bridge?.view);
  }

  function positionPointCallout(view) {
    const callout = $("globe-point-callout"), record = selectedLocation();
    const point = record && view && FireGlobeMath.project(record.vector, view);
    const visibleLayer = state.selectedWildfire
      ? $("globe-wildfires").checked
      : $("globe-markers").checked && state.revealed;
    if (!point || !state.frame || !visibleLayer) {
      callout.hidden = true;
      return;
    }
    const hero = document.querySelector(".globe-hero").getBoundingClientRect();
    const frame = state.frame.getBoundingClientRect();
    const scene = state.frame.contentWindow.fireAtlasTerrain;
    const x = frame.left - hero.left + point.x * frame.width / (scene?.width || view.width);
    const y = frame.top - hero.top + point.y * frame.height / (scene?.height || view.height);
    callout.hidden = false;
    const card = callout.querySelector(".point-callout-card");
    const width = card.offsetWidth, height = card.offsetHeight;
    const top = Math.max(12, frame.top - hero.top + 12);
    const bottom = Math.min(hero.height - 12, frame.bottom - hero.top - 12);
    const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
    let left, cardY, path;
    if (hero.width <= 600) {
      left = clamp(x - width / 2, 12, hero.width - width - 12);
      cardY = clamp(y + 58, top, Math.max(top, bottom - height));
      if (cardY < y + 8) cardY = clamp(y - height - 58, top, Math.max(top, bottom - height));
      const startX = clamp(x, left + 18, left + width - 18);
      const startY = cardY > y ? cardY : cardY + height;
      const elbowY = (startY + y) / 2;
      path = `M${startX},${startY} L${startX},${elbowY} L${x},${elbowY} L${x},${y}`;
    } else {
      const right = x + 64 + width <= hero.width - 16;
      left = clamp(right ? x + 64 : x - width - 64, 16, hero.width - width - 16);
      cardY = clamp(y - height / 2 - 35, top, Math.max(top, bottom - height));
      const startX = right ? left : left + width;
      const startY = cardY + Math.min(height - 22, 52);
      const elbowX = (startX + x) / 2;
      path = `M${startX},${startY} L${elbowX},${startY} L${elbowX},${y} L${x},${y}`;
    }
    card.style.setProperty("--point-callout-left", `${left}px`);
    card.style.setProperty("--point-callout-top", `${cardY}px`);
    $("point-callout-line").setAttribute("d", path);
    callout.dataset.anchorX = String(x);
    callout.dataset.anchorY = String(y);
  }

  function closeEarthDetails() {
    const dialog = $("earth-details-dialog");
    if (dialog.open) dialog.close();
  }

  function returnToFullEarth() {
    state.pendingZoom = null;
    state.bridge?.reset();
    setRotationUI(false);
    closeEarthDetails();
  }

  function updateZoomUI(view) {
    const zoomed = Boolean(view.zoomed), reset = $("globe-reset");
    $("point-callout-back").hidden = !zoomed;
    reset.classList.toggle("is-zoomed", zoomed);
    const label = zoomed ? "← Full Earth" : "↺";
    if (reset.textContent !== label) reset.textContent = label;
    reset.setAttribute("aria-label", zoomed ? "Back to full Earth" : "Return to full Earth");
  }

  function locationActions(lon, lat, altitude) {
    const actions = element("div", undefined, "globe-location-actions");
    const zoom = element("button", "Zoom to location ↗", "globe-location-zoom");
    zoom.type = "button";
    zoom.disabled = state.failedEarth;
    zoom.addEventListener("click", () => {
      zoomToLocation(lon, lat, altitude);
      document.querySelector(".globe-hero").scrollIntoView({behavior: motionPreference.matches ? "auto" : "smooth", block: "start"});
    });
    const reset = element("button", "Full Earth", "globe-location-reset");
    reset.type = "button";
    reset.disabled = state.failedEarth;
    reset.addEventListener("click", returnToFullEarth);
    actions.append(zoom, reset);
    return actions;
  }

  function draw(view) {
    const canvas = state.canvas, ctx = state.context;
    if (!canvas || !ctx || !view) return;
    const dpr = Math.min(devicePixelRatio || 1, 1.5);
    const width = Math.round(view.width * dpr), height = Math.round(view.height * dpr);
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    state.visible = [];
    setRotationUI(view.playing);
    updateZoomUI(view);
    const showDetections = $("globe-markers").checked && state.revealed;
    const showWildfires = $("globe-wildfires").checked;
    const markerScale = Math.min(1, Math.max(0.58, view.width / 1000));
    const latest = state.data?.daily.at(-1)?.date;
    for (const item of showDetections ? state.points : []) {
      const point = FireGlobeMath.project(item.vector, view);
      if (!point) continue;
      const radius = Math.min(3.7, 1.2 + Math.log10(item.count + 1) * 0.72) * markerScale;
      const recent = item.last.slice(0, 10) === latest;
      ctx.beginPath();
      ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
      ctx.fillStyle = recent ? "rgba(255,198,118,.90)" : "rgba(220,105,49,.72)";
      ctx.fill();
      // Outer glow halo for large clusters — premium visual
      if (item.count > 150 && view.width > 500) {
        const glowRadius = radius + (item.count > 500 ? 5 : 3);
        const glowAlpha = item.count > 500 ? 0.15 : 0.08;
        ctx.beginPath();
        ctx.arc(point.x, point.y, glowRadius, 0, Math.PI * 2);
        ctx.fillStyle = recent ? `rgba(255,198,118,${glowAlpha})` : `rgba(255,112,47,${glowAlpha})`;
        ctx.fill();
      }
      if (item.id === state.selected) {
        // Animated pulsing selection ring
        const pulseT = (Date.now() % 2000) / 2000;
        const pulseR = 9 + Math.sin(pulseT * Math.PI * 2) * 2;
        ctx.beginPath();
        ctx.arc(point.x, point.y, pulseR, 0, Math.PI * 2);
        ctx.strokeStyle = "#fff0d6";
        ctx.lineWidth = 1.5;
        ctx.stroke();
        // Outer soft ring
        ctx.beginPath();
        ctx.arc(point.x, point.y, pulseR + 4, 0, Math.PI * 2);
        ctx.strokeStyle = "rgba(255,240,214,0.25)";
        ctx.lineWidth = 1;
        ctx.stroke();
      }
      state.visible.push({x: point.x, y: point.y, radius, id: item.id});
    }
    // Historical case locations are independent of NASA signal filters.
    // Hotspot halos are approximate affected-area locations, never boundaries.
    for (const item of showWildfires ? state.wildfires || [] : []) {
      const point = FireGlobeMath.project(item.vector, view);
      if (!point) continue;
      const radius = 5.8 * markerScale;
      const glow = ctx.createRadialGradient(point.x, point.y, radius * 0.25, point.x, point.y, radius * 2.5);
      glow.addColorStop(0, "rgba(255, 214, 72, .52)");
      glow.addColorStop(0.42, "rgba(255, 82, 26, .35)");
      glow.addColorStop(1, "rgba(255, 54, 12, 0)");
      ctx.beginPath();
      ctx.arc(point.x, point.y, radius * 2.5, 0, Math.PI * 2);
      ctx.fillStyle = glow;
      ctx.fill();
      ctx.beginPath();
      ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
      ctx.fillStyle = "#e63b19";
      ctx.fill();
      ctx.lineWidth = 1.5 * markerScale;
      ctx.strokeStyle = "#ffd83e";
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(point.x, point.y, radius * 0.45, 0, Math.PI * 2);
      ctx.fillStyle = "#ffba28";
      ctx.fill();
      if (item.id === state.selectedWildfire) {
        ctx.beginPath();
        ctx.arc(point.x, point.y, radius + 4, 0, Math.PI * 2);
        ctx.strokeStyle = "#fff4b5";
        ctx.lineWidth = 1.4;
        ctx.stroke();
      }
      state.visible.push({x: point.x, y: point.y, radius: radius * 2, id: item.id, kind: "wildfire"});
    }
    // Exact coordinates from the selected cell's latest observation sample.
    for (const row of showDetections ? state.details?.observations || [] : []) {
      const p = FireGlobeMath.project(FireGlobeMath.vector(row.lon, row.lat), view);
      if (!p) continue;
      ctx.beginPath();
      ctx.arc(p.x, p.y, 2, 0, Math.PI * 2);
      ctx.fillStyle = "#baf2ed";
      ctx.fill();
    }
    canvas.dataset.visible = String(state.visible.length);
    positionPointCallout(view);
  }

  function attach(frame) {
    const doc = frame.contentDocument, bridge = frame.contentWindow.fireAtlasEarth;
    if (!doc || !bridge || state.bridge === bridge) return;
    state.bridge = bridge;
    state.frame = frame;
    const overlay = doc.createElement("canvas");
    overlay.id = "fire-observations";
    overlay.setAttribute("aria-hidden", "true");
    overlay.style.cssText = "position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:2";
    doc.body.append(overlay);
    state.canvas = overlay;
    state.context = overlay.getContext("2d");
    bridge.onFrame = draw;
    const visibility = new IntersectionObserver(entries => bridge.setVisible(entries[0].isIntersecting), {rootMargin: "80px"});
    visibility.observe(frame);
    const surface = doc.getElementById("earth");
    surface.addEventListener("webglcontextlost", () => window.dispatchEvent(new Event("earth-unavailable")));
    // Keep the starting pose stable throughout the complete reveal turn.
    for (const name of ["pointerdown", "pointermove", "pointerup", "dblclick", "wheel"]) {
      surface.addEventListener(name, e => {
        if (state.revealing) { e.preventDefault(); e.stopImmediatePropagation(); }
      }, {capture:true, passive:false});
    }
    doc.addEventListener("keydown", e => {
      if (state.revealing && (e.key.startsWith("Arrow") || [" ","r","+","-","="].includes(e.key))) {
        e.preventDefault(); e.stopImmediatePropagation();
      }
    }, true);
    surface.setAttribute("aria-label", "Interactive Earth. NASA satellite signals and selected historical wildfire cases have separate controls; historical markers are approximate locations. Drag or use arrow keys to rotate. Select a marker for details.");
    let down = null;
    const pointers = new Set();
    surface.addEventListener("pointerdown", e => {
      pointers.add(e.pointerId);
      down = {x: e.clientX, y: e.clientY, id: e.pointerId, moved: pointers.size > 1};
    });
    surface.addEventListener("pointermove", e => {
      if (down && Math.hypot(e.clientX - down.x, e.clientY - down.y) > 6) down.moved = true;
      if (!down) surface.style.cursor = state.visible.some(p => Math.hypot(p.x - e.clientX, p.y - e.clientY) < Math.max(p.radius + 3, 6)) ? "pointer" : "grab";
    });
    surface.addEventListener("pointercancel", e => {
      pointers.delete(e.pointerId);
      down = null;
    });
    surface.addEventListener("pointerup", e => {
      pointers.delete(e.pointerId);
      if (!down || down.id !== e.pointerId || down.moved) {
        down = null;
        return;
      }
      down = null;
      const target = state.visible.map(p => ({...p, d: Math.hypot(p.x - e.clientX, p.y - e.clientY)}))
        .filter(p => p.d <= (e.pointerType === "touch" ? 13 : 8)).sort((a, b) => a.d - b.d)[0];
      if (target) target.kind === "wildfire" ? selectWildfire(target.id) : select(target.id);
    });
    draw(bridge.view);
    const pendingZoom = state.pendingZoom;
    const selected = selectedLocation();
    if (selected) focus(selected.lon, selected.lat);
    if (pendingZoom) zoomToLocation(pendingZoom.lon, pendingZoom.lat, pendingZoom.altitude);
    state.pendingZoom = null;
    if ($("globe-markers").checked) revealDetections();
    else scheduleLoad();
  }

  async function json(url, signal) {
    const response = await fetch(url, {signal});
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || "NASA snapshot could not load.");
    return body;
  }

  function clearSelection() {
    state.detailController?.abort();
    state.detailRequest++;
    state.selected = null;
    state.selectedWildfire = null;
    state.details = null;
    $("globe-point-callout").hidden = true;
    $("globe-selection").hidden = true;
    $("globe-wildfire-location").value = "";
    $("globe-wildfire-browser").hidden = !state.wildfires?.length || !$("globe-wildfires").checked;
    $("globe-console-title").textContent = "Satellite evidence";
    $("globe-source-label").textContent = "NASA FIRMS";
    $("globe-data-kind").textContent = "Imported snapshot";
    $("globe-layer-label").textContent = "NASA SATELLITE EVIDENCE";
    $("globe-layer-icon").style.display = "";
    $("globe-evidence-tools").hidden = false;
    const sourceLink = document.querySelector(".globe-console-head > a");
    sourceLink.href = "./data.html";
    sourceLink.hidden = false;
    sourceLink.setAttribute("aria-label", "Inspect NASA data sources");
    sourceLink.title = "Inspect NASA data sources";
    document.querySelector(".globe-console").classList.remove("has-selection", "has-historical-selection");
    $("globe-location").value = "";
    updateLayerStamp();
  }

  function renderObservationImprint(data, currentDay) {
    const imprint = $("globe-imprint");
    const container = $("globe-imprint-bars");
    const resetBtn = $("imprint-reset");
    if (!imprint || !container) return;

    const sourceDaily = (state.fullDaily && state.fullDaily.length) ? state.fullDaily : (data.daily || []);
    const dailyMap = new Map(sourceDaily.map(d => [d.date, d.count]));
    const winStart = data.window_start || state.windowStart;
    const winEnd = data.window_end || state.windowEnd;

    if (!winStart || !winEnd) {
      container.replaceChildren();
      if (resetBtn) resetBtn.hidden = true;
      return;
    }

    if (resetBtn) {
      resetBtn.hidden = (currentDay === "all");
      resetBtn.onclick = () => {
        $("globe-date").value = "all";
        load();
      };
    }

    const days = [];
    const d = new Date(winStart + "T00:00:00Z");
    const end = new Date(winEnd + "T00:00:00Z");
    for (; d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
      days.push(d.toISOString().slice(0, 10));
    }

    const counts = days.map(dayStr => dailyMap.get(dayStr)).filter(c => c !== undefined && c > 0);
    const maxCount = Math.max(...counts, 1);

    const bars = days.map(dayStr => {
      const hasData = dailyMap.has(dayStr);
      const count = hasData ? dailyMap.get(dayStr) : 0;
      const isUnobserved = !hasData;
      const isZero = hasData && count === 0;
      const isActive = currentDay === dayStr;

      const bar = document.createElement("button");
      bar.type = "button";
      bar.className = `imprint-bar${isActive ? " is-active" : ""}${isUnobserved ? " is-unobserved" : ""}${isZero ? " is-zero" : ""}`;

      const titleText = isUnobserved
        ? `${dayStr} UTC\nNo imported records · coverage unknown.\nSelect to filter the globe.`
        : isZero
        ? `${dayStr} UTC\n0 imported detections · coverage unknown.`
        : `${dayStr} UTC\n${format(count)} thermal detections\nBar height shows count, not fire intensity. Select to filter.`;

      bar.dataset.tooltip = titleText;
      bar.setAttribute("aria-label", titleText);
      bar.setAttribute("aria-pressed", String(isActive));

      const fill = document.createElement("span");
      fill.className = "imprint-fill";
      if (!isUnobserved && !isZero) {
        const pct = Math.max(14, Math.round((count / maxCount) * 100));
        fill.style.height = `${pct}%`;
      }

      bar.append(fill);

      bar.addEventListener("click", () => {
        if (currentDay === dayStr) {
          $("globe-date").value = "all";
        } else {
          $("globe-date").value = dayStr;
        }
        load();
      });

      return bar;
    });

    container.replaceChildren(...bars);
  }

  function scheduleLoad() {
    const background = () => { if (!state.data && !state.loading) load(); };
    if ("requestIdleCallback" in window) requestIdleCallback(background, {timeout:1200});
    else setTimeout(background, 250);
  }

  function load() {
    const pending = fetchSnapshot();
    state.loading = pending;
    syncControls();
    pending.finally(() => {
      if (state.loading !== pending) return;
      state.loading = null;
      syncControls();
    });
    return pending;
  }

  async function fetchSnapshot() {
    const request = ++state.request;
    state.controller?.abort();
    state.controller = new AbortController();
    clearSelection();
    state.points = [];
    state.visible = [];
    state.data = null;
    const source = $("globe-source").value, day = $("globe-date").value;
    $("globe-source").disabled = true;
    $("globe-date").disabled = true;
    $("globe-location").disabled = true;
    $("globe-total").textContent = "—";
    $("globe-cell-count").textContent = "Loading mapped groups…";
    $("globe-period").replaceChildren();
    $("globe-retry").hidden = true;
    $("globe-status").textContent = "Loading data…";
    if ($("globe-markers").checked) revealStatus("Loading data…");
    try {
      const signal = AbortSignal.any([state.controller.signal, AbortSignal.timeout(45000)]);
      const [data, profile] = await Promise.all([
        json(`/api/globe?${new URLSearchParams({source, date: day})}`, signal),
        day === "all" ? Promise.resolve(null) : json(`/api/globe?${new URLSearchParams({source, date: "all"})}`, signal)
      ]);
      if (request !== state.request) return false;
      state.data = data;
      state.fullDaily = (profile || data).daily;
      state.windowStart = data.window_start;
      state.windowEnd = data.window_end;
      state.points = data.clusters.map(item => ({...item, vector: FireGlobeMath.vector(item.lon, item.lat)}));
      $("globe-total").textContent = format(data.total);
      $("globe-cell-count").textContent = `${format(data.clusters.length)} mapped groups · ${data.cluster_degrees}° cells`;
      renderObservationPeriod(data);
      updateLayerStamp();
      const sourceOptions = [new Option("All satellites", "all"), ...data.sources.map(s => new Option(s.label, s.source_id))];
      $("globe-source").replaceChildren(...sourceOptions);
      $("globe-source").value = source;
      const dates = [new Option("All dates", "all")];
      if (data.window_start) {
        const d = new Date(data.window_start + "T00:00:00Z"), end = new Date(data.window_end + "T00:00:00Z");
        for (; d <= end; d.setUTCDate(d.getUTCDate() + 1)) dates.push(new Option(d.toISOString().slice(0, 10), d.toISOString().slice(0, 10)));
      }
      $("globe-date").replaceChildren(...dates);
      $("globe-date").value = day;
      renderObservationImprint(data, day);
      updateLocations();
      $("globe-status").textContent = data.total ? (state.revealed ? "Select a point to inspect." : "Ready · turn on detections to explore.") : "No imported detections · coverage unknown.";
      const latest = data.daily.at(-1)?.date;
      $("globe-latest-key").dataset.tooltip = `${latest ? latest + " UTC\n" : ""}Gold marks groups observed on the latest day in this selection. It does not establish whether a fire is still burning.`;
      revealStatus(state.revealing ? "Returning to your view…" : "");
      $("globe-source").disabled = !data.sources.length;
      $("globe-date").disabled = !data.sources.length;
      $("globe-location").disabled = !data.total;
      return true;
    } catch (error) {
      if (request !== state.request) return false;
      $("globe-status").textContent = error.name === "TimeoutError" ? "Snapshot request timed out. Retry loading the imported data." : error.message;
      $("globe-stamp").textContent = "SATELLITE EVIDENCE UNAVAILABLE";
      $("globe-cell-count").textContent = "Snapshot unavailable";
      $("globe-period").replaceChildren();
      $("globe-retry").hidden = false;
      $("globe-source").disabled = false;
      $("globe-date").disabled = false;
      state.fullDaily = null;state.windowStart = null;state.windowEnd = null;
      renderObservationImprint({daily: []}, "all");
      if (state.revealing) cancelReveal();
      state.revealed = false;
      $("globe-markers").checked = false;
      revealStatus("");
      return false;
    }
  }

  async function select(id) {
    const item = state.points.find(c => c.id === id);
    if (!item) return;
    const request = ++state.detailRequest;
    state.detailController?.abort();
    state.detailController = new AbortController();
    state.selected = id;
    state.selectedWildfire = null;
    state.details = null;
    $("globe-wildfire-location").value = "";
    focus(item.lon, item.lat);
    if (![...$("globe-location").options].some(o => o.value === id)) $("globe-location").add(new Option(coords(item.lon, item.lat), id));
    $("globe-location").value = id;
    const panel = $("globe-selection");
    panel.hidden = false;
    $("globe-console-title").textContent="Satellite evidence";
    $("globe-source-label").textContent="NASA FIRMS";
    $("globe-data-kind").textContent="Imported snapshot";
    $("globe-layer-label").textContent = "NASA SATELLITE EVIDENCE";
    $("globe-layer-icon").style.display = "";
    $("globe-evidence-tools").hidden = false;
    const sourceLink = document.querySelector(".globe-console-head > a");
    sourceLink.href="./data.html";
    sourceLink.hidden = false;
    sourceLink.setAttribute("aria-label", "Inspect NASA data sources");
    sourceLink.title="Inspect NASA data sources";
    document.querySelector(".globe-console").classList.remove("has-historical-selection");
    document.querySelector(".globe-console").classList.add("has-selection");
    panel.replaceChildren(element("p", "Loading source evidence…"));
    showPointCallout(item);
    try {
      const data = await json(`/api/globe/detail?${new URLSearchParams({cell: id, source: state.data.source, date: state.data.date})}`, AbortSignal.any([state.detailController.signal, AbortSignal.timeout(30000)]));
      if (request !== state.detailRequest) return;
      state.details = data;
      panel.replaceChildren();
      panel.append(element("span", "1° GEOGRAPHIC GROUP", "globe-kicker"), element("h3", coords(item.lon, item.lat)));
      panel.append(locationActions(item.lon, item.lat, 350000));
      const facts = element("div", undefined, "globe-facts");
      for (const [key, value] of [["Detections", format(data.total)], ["Peak pixel FRP", item.max_frp_mw == null ? "Unknown" : `${format(item.max_frp_mw)} MW`]]) {
        const fact = element("div");fact.append(element("strong", value), element("span", key));facts.append(fact);
      }
      panel.append(facts, element("p", `First ${stamp(item.first)}\nLast ${stamp(item.last)}`, "globe-times"));
      panel.append(element("p", "Fire status and ignition time are unknown.", "globe-condition"));
      const interpretation = element("details");
      interpretation.append(element("summary", "What these measurements mean"), element("p", "FRP is a pixel’s radiative power, not fire severity. A group can contain repeated observations of the same fire. Cyan dots show up to 12 latest records at their original coordinates."));
      const links = element("div", undefined, "globe-atlas-links");
      const series = {MODIS_NRT: "modis-nrt", VIIRS_NOAA20_NRT: "viirs-noaa20-nrt", VIIRS_NOAA21_NRT: "viirs-noaa21-nrt", VIIRS_SNPP_NRT: "viirs-snpp-nrt"};
      for (const src of data.sources) {
        const name = state.data.sources.find(s => s.source_id === src.source_id)?.label || src.source_id;
        const link = element("a", `${name} ↗`);
        const bbox = [data.bbox[0], Math.max(-86, data.bbox[1]), data.bbox[2], Math.min(86, data.bbox[3])];
        link.href = `/?${new URLSearchParams({series: series[src.source_id], year: src.last.slice(0, 4), month: Number(src.last.slice(5, 7)), bbox: bbox.join(",")})}#atlas-section`;
        link.title = "Inspect this satellite and area in the atlas";
        links.append(link);
      }
      const atlas = element("details");
      atlas.append(element("summary", "Explore this area in the atlas"), links);
      panel.append(atlas);
      const list = element("ol");
      for (const row of data.observations) {
        const li = element("li");
        li.append(element("strong", coords(row.lon, row.lat)), element("div", stamp(row.acquisition_utc)), element("div", `${row.source_id} · ${row.frp_mw == null ? "FRP unknown" : format(row.frp_mw) + " MW"} · confidence ${row.confidence_raw}`));
        list.append(li);
      }
      const provenance=element("details",undefined,"selection-source-records");
      provenance.append(element("summary",`${data.observations.length} latest source records`),list,interpretation.querySelector("p"));
      panel.append(provenance);
    } catch (error) {
      if (request === state.detailRequest) panel.replaceChildren(element("p", `Evidence unavailable: ${error.message}. Close this view and select the group again to retry.`));
    }
  }

  function selectWildfire(id) {
    const item = state.wildfires?.find(event => event.id === id);
    if (!item) return;
    clearSelection();
    state.selectedWildfire = id;
    focus(item.lon, item.lat);
    $("globe-wildfire-location").value = id;
    $("globe-wildfire-browser").hidden = false;
    $("globe-selection").hidden = false;
    $("globe-console-title").textContent = "Historical wildfire context";
    $("globe-source-label").textContent = "Historical casebook";
    $("globe-data-kind").textContent = state.wildfireReviewedOn ? `Reviewed ${state.wildfireReviewedOn}` : "Selected examples";
    $("globe-layer-label").textContent = "HISTORICAL WILDFIRE CASE";
    $("globe-layer-icon").style.display = "none";
    $("globe-evidence-tools").hidden = true;
    const sourceLink = document.querySelector(".globe-console-head > a");
    sourceLink.hidden = true;
    const console = document.querySelector(".globe-console");
    console.classList.add("has-selection", "has-historical-selection");

    const panel = $("globe-selection");
    panel.replaceChildren(
      element("span", "HISTORICAL WILDFIRE CASE", "globe-kicker"),
      element("h3", item.name),
      locationActions(item.lon, item.lat, 450000),
      element("p", `${item.place} · ${item.period}`, "globe-times"),
      element("p", item.summary),
      element("p", "Approximate reported affected-area location. This record is not a live fire status, ignition point, or perimeter.", "globe-condition")
    );
    const sources = element("details", undefined, "globe-wildfire-sources");
    sources.append(element("summary", `${item.sources.length} linked source${item.sources.length === 1 ? "" : "s"}`));
    const list = element("ol");
    for (const source of item.sources) {
      const li = element("li");
      const link = element("a", `${source.publisher}: ${source.label} ↗`);
      link.href = source.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      li.append(link);
      if (source.published) li.append(element("small", `Published ${source.published}`));
      list.append(li);
    }
    sources.append(list);
    panel.append(sources);
    showPointCallout(item);
  }

  window.addEventListener("earth-ready", event => attach(event.detail.frame));
  window.addEventListener("earth-unavailable", () => {
    state.failedEarth = true;
    $("globe-point-callout").hidden = true;
    state.bridge?.cancelOrbit();state.bridge = null;
    updateLayerStamp();
    $("globe-status").textContent = "3D unavailable · browse locations below.";
    if ($("globe-markers").checked) revealDetections();
    else scheduleLoad();
    syncControls();
  });

  window.addEventListener("fireatlas-map-selection", async event => {
    const {layer,id} = event.detail || {};
    if(layer !== "thermal")return;
    if(state.revealing){cancelReveal();$("globe-markers").checked=false;}
    if(state.loading) await state.loading;
    if(!state.data || state.data.source!=="all" || state.data.date!=="all") {
      $("globe-source").value="all";$("globe-date").value="all";
      if(!await load())return;
    }
    state.region="world";updateLocations();
    $("globe-markers").checked=true;
    await revealDetections();
    select(id);
    const item = state.points.find(point => point.id === id);
    if (item) zoomToLocation(item.lon, item.lat, 350000);
  });

  function setupTooltips() {
    const tip = $("globe-tooltip");
    let owner = null, timer;
    function hide() {
      clearTimeout(timer);
      owner?.removeAttribute("aria-describedby");owner = null;tip.hidden = true;
    }
    function show(target) {
      hide();owner = target;
      tip.textContent = target.dataset.tooltip;tip.hidden = false;
      target.setAttribute("aria-describedby", tip.id);
      const rect = target.getBoundingClientRect(), box = tip.getBoundingClientRect();
      tip.style.left = `${Math.max(12, Math.min(innerWidth - box.width - 12, rect.left + rect.width / 2 - box.width / 2))}px`;
      tip.style.top = `${Math.max(12, rect.top > box.height + 16 ? rect.top - box.height - 10 : Math.min(innerHeight - box.height - 12, rect.bottom + 10))}px`;
    }
    document.addEventListener("pointerover", e => {
      const target = e.target.closest("[data-tooltip]");
      if (target) show(target);
    });
    document.addEventListener("pointerout", e => {
      if (e.target.closest("[data-tooltip]")) timer = setTimeout(hide, 160);
    });
    tip.addEventListener("pointerenter", () => clearTimeout(timer));
    tip.addEventListener("pointerleave", hide);
    document.addEventListener("focusin", e => { const target=e.target.closest("[data-tooltip]");if(target)show(target); });
    document.addEventListener("focusout", e => { if (e.target.matches("[data-tooltip]")) hide(); });
    document.addEventListener("click", e => { const target=e.target.closest("[data-tooltip]");if(target)show(target);else if(!tip.contains(e.target))hide(); });
    document.addEventListener("keydown", e => { if (e.key === "Escape") hide(); });
    window.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
  }

  document.addEventListener("DOMContentLoaded", () => {
    $("point-callout-details").addEventListener("click", openEarthDetails);
    $("point-callout-zoom").addEventListener("click", () => {const record=selectedLocation();if(record)zoomToLocation(record.lon, record.lat, 350000);});
    $("point-callout-back").addEventListener("click", returnToFullEarth);
    $("point-callout-close").addEventListener("click", () => {clearSelection();$("earth-details-open").focus({preventScroll:true});});
    window.addEventListener("scroll", () => positionPointCallout(state.bridge?.view), {passive:true});
    window.addEventListener("resize", () => positionPointCallout(state.bridge?.view));
    const dialog = $("earth-details-dialog");
    $("earth-details-open").addEventListener("click", () => {
      if (!state.selectedWildfire) {
        $("globe-evidence-tools").hidden = false;
        $("globe-evidence-tools").open = true;
      }
      openEarthDetails();
    });
    $("earth-details-close").addEventListener("click", closeEarthDetails);
    dialog.addEventListener("close", () => {document.documentElement.classList.remove("earth-details-visible");$("earth-details-open").focus({preventScroll:true});});
    dialog.addEventListener("click", event => {if(event.target===dialog){const box=dialog.getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)closeEarthDetails();}});
    $("globe-markers").checked = false;
    $("globe-markers").addEventListener("change", revealDetections);
    $("globe-wildfires").checked = false;
    $("globe-wildfires").addEventListener("change", toggleWildfires);
    $("globe-wildfire-location").addEventListener("change", event => {
      if (event.target.value) selectWildfire(event.target.value);
      else if (state.selectedWildfire) clearSelection();
    });
    setupTooltips();
    $("globe-date").addEventListener("change", load);
    $("globe-source").addEventListener("change", load);
    $("globe-retry").addEventListener("click", load);
    $("globe-location").addEventListener("change", e => e.target.value ? select(e.target.value) : clearSelection());
    $("globe-rotate").addEventListener("click", () => {
      state.bridge?.setPlaying(!state.bridge.view.playing);
    });
    $("globe-zoom-in").addEventListener("click", () => state.bridge?.zoom(-0.3));
    $("globe-zoom-out").addEventListener("click", () => state.bridge?.zoom(0.3));
    $("globe-reset").addEventListener("click", returnToFullEarth);
    document.querySelectorAll("[data-globe-region]").forEach(button => button.addEventListener("click", () => {
      clearSelection();
      state.region=button.dataset.regionKey;updateLocations();
      focus(...button.dataset.globeRegion.split(",").map(Number));
      closeEarthDetails();
    }));
    // Fetch after the Earth becomes visible, or immediately on an explicit request.
    updateLocations();
    syncControls();
  });
})();
