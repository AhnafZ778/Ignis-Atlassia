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
    visible: [],
    selected: null,
    details: null,
    bridge: null,
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
    documented: false,
    fires: null,
    firesLoading: null,
    casebookYears: "2016–2026",
    region: "world",
    panelView: "cases",
    casePage: 0,
    caseQuery: "",
    selectedFire: null,
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
    $("globe-layer-label").textContent = state.documented ? "HISTORICAL WILDFIRES" : "NASA SATELLITE EVIDENCE";
    $("globe-layer-icon").setAttribute("href", `/vendor/lucide-icons.svg#${state.documented ? "book-open" : "satellite"}`);
    const data = state.data;
    $("globe-stamp").textContent = state.documented
      ? `${state.casebookYears} · ${state.failedEarth ? "browse the sourced archive" : "illustrative fire effects"}`
      : data?.latest_observation ? `${data.date === "all" ? data.window_start + " → " + data.window_end : data.date} · IMPORTED SNAPSHOT`
      : "NASA observation snapshot loading";
  }

  // Cached, seamless texture sequences keep turbulent fire out of the frame loop.
  // Footprints are illustrative areas around sourced locations, not burn perimeters.
  let wildfireTextures;
  function buildWildfireTextures() {
    const width = 128, height = 160, frames = 24;
    let seed = 712367;
    const random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; };
    const lattice = Float32Array.from({length: 128 * 128}, random);
    const noise = (x, y) => {
      const ix = Math.floor(x), iy = Math.floor(y);
      let fx = x - ix, fy = y - iy;
      fx = fx * fx * (3 - 2 * fx); fy = fy * fy * (3 - 2 * fy);
      const n = (a, b) => lattice[(b & 127) * 128 + (a & 127)];
      return (n(ix, iy) * (1 - fx) + n(ix + 1, iy) * fx) * (1 - fy)
        + (n(ix, iy + 1) * (1 - fx) + n(ix + 1, iy + 1) * fx) * fy;
    };
    const turbulence = (x, y) => noise(x, y) * .55 + noise(x * 2.03, y * 2.03) * .3 + noise(x * 4.11, y * 4.11) * .15;
    const clamp = x => Math.max(0, Math.min(1, x));
    const texture = (w, h, paint) => {
      const canvas = document.createElement("canvas"); canvas.width = w; canvas.height = h;
      const context = canvas.getContext("2d"), pixels = context.createImageData(w, h);
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
        const rgba = paint(x, y), offset = (y * w + x) * 4;
        for (let c = 0; c < 4; c++) pixels.data[offset + c] = rgba[c];
      }
      context.putImageData(pixels, 0, 0); return canvas;
    };
    return Array.from({length: 2}, (_, variant) => {
      const shift = variant * 37;
      const footprint = (x, y) => {
        const u = (x - 48) / 40, v = (y - 48) / 35;
        const n = turbulence(x * .11 + shift, y * .11);
        return {n, edge: clamp((1 - Math.hypot(u, v) + (n - .5) * .65) * 5)};
      };
      const ground = texture(96, 96, (x, y) => {
        const {n, edge} = footprint(x, y);
        return [30 + n * 24, 16 + n * 12, 12 + n * 8, edge * 100];
      });
      const embers = texture(96, 96, (x, y) => {
        const {n, edge} = footprint(x, y);
        const vein = Math.pow(clamp(1 - Math.abs(n - .54) * 17), 3);
        const grain = noise(x * 1.7 + shift, y * 1.7);
        const heat = clamp(vein * .85 + Math.pow(grain, 9));
        return [255, 65 + heat * 160, 10 + heat * heat * 125, edge * (heat * 210 + n * 25)];
      });
      const sequence = Array.from({length: frames}, (_, frame) => {
        const angle = frame / frames * Math.PI * 2;
        const ox = Math.cos(angle) * 2.8 + shift, oy = Math.sin(angle) * 2.8;
        const fire = texture(width, height, (x, y) => {
          const u = (x / width - .5) * 2, rise = 1 - y / height;
          const n = turbulence(x * .055 + ox, y * .042 + oy);
          const warp = (noise(x * .032 + ox, y * .028 + oy) - .5) * .55 * rise;
          const spread = Math.pow(clamp(1 - Math.abs(u + warp)), .65);
          const tongues = .52 + .24 * Math.sin((u + warp) * 13 + shift) + .16 * Math.sin(u * 27 - shift);
          const envelope = spread * (.48 + tongues * .4) - rise;
          const density = clamp((envelope + (n - .48) * .44) * 9);
          const heat = clamp((1 - rise) * .6 + n * .55 - Math.abs(u) * .18);
          const fine = noise(x * .46 + ox, y * .34 + oy);
          const baseFade = clamp((height - y - 1) / 15 + (n - .5) * .7);
          const alpha = density * clamp(y / 12) * baseFade * (.65 + fine * .35);
          return [255, 45 + Math.pow(heat, 1.8) * 210, 5 + Math.pow(heat, 5) * 210, alpha * 245];
        });
        const smoke = texture(width, height, (x, y) => {
          const u = (x / width - .5) * 2, rise = 1 - y / height;
          const n = turbulence(x * .045 + ox * .5, y * .05 + oy * .5);
          const drift = Math.sin(rise * 6 + angle) * .15;
          const body = clamp(1 - Math.abs(u + drift) / (.23 + rise * .6));
          const alpha = body * clamp((n - .34) * 2.6) * Math.sin(rise * Math.PI) * .23;
          return [95 + n * 55, 88 + n * 47, 79 + n * 42, alpha * 255];
        });
        return {fire, smoke};
      });
      return {ground, embers, sequence};
    });
  }

  function drawWildfire(ctx, fire, point, view, time) {
    wildfireTextures ||= buildWildfireTextures();
    const diameter = view.globe?.diameter || Math.min(view.width, view.height) * 2.4 / Math.sqrt(view.distance ** 2 - 1);
    const z = view.rotation[6] * fire.vector[0] + view.rotation[7] * fire.vector[1] + view.rotation[8] * fire.vector[2];
    const perspective = (view.distance - 1) / (view.distance - z);
    const size = Math.max(3, Math.min(11, diameter * .013 * perspective));
    const phase = fire.effectPhase;
    const textures = wildfireTextures[Math.round(phase / 2.39996) % wildfireTextures.length];
    const progress = (time * 9 + phase * 3) % textures.sequence.length;
    const index = Math.floor(progress), blend = progress - index;
    const facing = Math.max(0, Math.min(1, (z * view.distance - 1) / (view.distance - 1)));
    const scale = Math.min(view.width, view.height) / 2;
    ctx.save();
    if (!view.globe || view.globe.clip) {
      ctx.beginPath();
      if (view.globe) ctx.ellipse(view.globe.x, view.globe.y, view.globe.rx, view.globe.ry, 0, 0, Math.PI * 2);
      else ctx.arc(view.width / 2 + view.framing * scale, view.height / 2 - view.vertical * scale, diameter / 2, 0, Math.PI * 2);
      ctx.clip();
    }
    // Project an east/north tangent basis so the textured ground tilts with Earth.
    const lon = fire.lon * Math.PI / 180, lat = fire.lat * Math.PI / 180;
    const east = [Math.cos(lon), 0, -Math.sin(lon)];
    const north = [-Math.sin(lat) * Math.sin(lon), Math.cos(lat), -Math.sin(lat) * Math.cos(lon)];
    const offsetStep = view.renderer === "arcgis-terrain"
      ? Math.max(.00001, Math.min(.012, (view.distance - z) * size / view.focal)) : .012;
    const projectOffset = axis => {
      const v = fire.vector.map((value, i) => value + axis[i] * offsetStep);
      const length = Math.hypot(...v);
      return FireGlobeMath.project(v.map(value => value / length), view);
    };
    const e = projectOffset(east), n = projectOffset(north);
    if (e && n) {
      const normalization = offsetStep * (view.focal || scale * 2.4) / (view.distance - z);
      ctx.save();
      ctx.transform((e.x - point.x) / normalization, (e.y - point.y) / normalization,
        (n.x - point.x) / normalization, (n.y - point.y) / normalization, point.x, point.y);
      ctx.drawImage(textures.ground, -size * 1.65, -size * 1.65, size * 3.3, size * 3.3);
      ctx.globalCompositeOperation = "screen";
      ctx.globalAlpha = .8 + .2 * Math.sin(time * 5 + phase);
      ctx.drawImage(textures.embers, -size * 1.65, -size * 1.65, size * 3.3, size * 3.3);
      ctx.restore();
    }
    ctx.translate(point.x, point.y);
    ctx.globalAlpha = .3 + facing * .7;
    const opacity = ctx.globalAlpha;
    const glow = ctx.createRadialGradient(0, -size * .25, 0, 0, -size * .25, size * 1.9);
    glow.addColorStop(0, "rgba(255,128,32,.25)"); glow.addColorStop(1, "rgba(235,55,10,0)");
    ctx.globalCompositeOperation = "screen";
    ctx.fillStyle = glow; ctx.fillRect(-size * 2, -size * 2.2, size * 4, size * 3.5);
    // Blend neighboring cached frames; fine turbulent filaments replace vector icons.
    for (const [offset, weight] of [[0, 1 - blend], [1, blend]]) {
      if (!weight) continue;
      const frame = textures.sequence[(index + offset) % textures.sequence.length];
      ctx.globalAlpha = opacity * weight;
      ctx.globalCompositeOperation = "source-over";
      ctx.drawImage(frame.smoke, -size * 1.6, -size * 4.1, size * 3.2, size * 4);
      ctx.globalCompositeOperation = "screen";
      ctx.drawImage(frame.fire, -size * 1.35, -size * 2.45, size * 2.7, size * 2.6);
    }
    ctx.globalAlpha = opacity;
    for (let i = 0; i < 9; i++) {
      const travel = (time * (.24 + i * .014) + phase * .13 + i * .117) % 1;
      const x = Math.sin(phase + i * 2.4 + travel * 3) * size * (.45 + travel * .4);
      const y = -size * (.2 + travel * 3.4);
      ctx.fillStyle = `rgba(255,${170 + i * 8},95,${(1 - travel) * .7})`;
      ctx.fillRect(x, y, .7, 1.1 + (1 - travel));
    }
    if (fire.id === state.selectedFire) {
      ctx.globalCompositeOperation = "source-over"; ctx.globalAlpha = .85;
      ctx.strokeStyle = "#ffe9ba"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.ellipse(0, 0, size * 1.8, size * (.35 + facing * .65), 0, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.restore(); return size;
  }

  function revealStatus(text) {
    $("globe-reveal-status").textContent = text;
    $("globe-reveal-status").hidden = !text;
  }

  function syncControls() {
    document.querySelectorAll("[data-globe-region],#globe-rotate,#globe-zoom-in,#globe-zoom-out,#globe-reset").forEach(b => b.disabled = state.revealing || state.failedEarth);
    $("globe-source").disabled = state.revealing || !!state.loading || !state.data?.sources.length;
    $("globe-date").disabled = $("globe-source").disabled;
    $("globe-location").disabled = state.revealing || !!state.loading || !state.data?.total;
    document.querySelectorAll(".imprint-bar,#imprint-reset").forEach(b => b.disabled = state.revealing || !!state.loading);
    $("globe-documented-toggle").disabled = state.revealing;
    document.querySelectorAll(".documented-list button").forEach(b => b.disabled = state.revealing);
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
    if (!dialog.open) dialog.showModal();
    document.documentElement.classList.add("earth-details-visible");
  }

  function closeEarthDetails() {
    const dialog = $("earth-details-dialog");
    if (dialog.open) dialog.close();
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
    reset.addEventListener("click", () => {state.pendingZoom = null;state.bridge?.reset();setRotationUI(false);closeEarthDetails();});
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
    const showDetections = $("globe-markers").checked && state.revealed;
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
    let fireCount = 0;
    const effectTime = motionPreference.matches ? 0 : performance.now() / 1000;
    for (const fire of state.documented && !state.revealing ? state.fires || [] : []) {
      const p = FireGlobeMath.project(fire.vector, view);
      if (!p) continue;
      const size = drawWildfire(ctx, fire, p, view, effectTime);
      state.visible.push({x:p.x,y:p.y-size*.6,radius:size*1.5,id:fire.id,kind:"documented"});
      fireCount++;
    }
    canvas.dataset.documentedVisible = String(fireCount);
    canvas.dataset.wildfireEffects = state.documented ? "historical" : "off";
    canvas.dataset.effectMotion = motionPreference.matches ? "static" : "animated";
  }

  function attach(frame) {
    const doc = frame.contentDocument, bridge = frame.contentWindow.fireAtlasEarth;
    if (!doc || !bridge || state.bridge === bridge) return;
    state.bridge = bridge;
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
    surface.setAttribute("aria-label", "Interactive Earth with documented wildfire sites and optional NASA satellite evidence. Fire effects illustrate historical case locations. Drag or use arrow keys to rotate. Select a fire or browse the wildfire casebook on the page.");
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
        .filter(p => p.d <= (p.kind === "documented" ? Math.max(16,p.radius) : e.pointerType === "touch" ? 13 : 8)).sort((a, b) => Number(b.kind === "documented") - Number(a.kind === "documented") || a.d - b.d)[0];
      if (target) target.kind === "documented" ? selectFire(target.id) : select(target.id);
    });
    draw(bridge.view);
    const selectedFire = state.documented && state.fires?.find(fire => fire.id === state.selectedFire);
    const pendingZoom = state.pendingZoom;
    if (selectedFire) focus(selectedFire.lon, selectedFire.lat);
    else if(state.selected){const selected=state.points.find(p=>p.id===state.selected);if(selected)focus(selected.lon,selected.lat);}
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
    state.details = null;
    state.selectedFire = null;
    $("documented-detail").hidden = true;
    $("documented-list").hidden = false;
    if (state.fires) $("documented-status").textContent = `${state.fires.length} sourced case files · select one to explore`;
    $("globe-selection").hidden = true;
    $("globe-overview").hidden = state.panelView !== "cases";
    $("globe-documented").hidden = state.panelView !== "cases";
    $("globe-console-title").textContent = state.panelView === "cases" ? "Wildfire atlas" : "Satellite evidence";
    $("globe-source-label").textContent = state.panelView === "cases" ? "FIREATLAS ARCHIVE" : "NASA FIRMS";
    $("globe-data-kind").textContent = state.panelView === "cases" ? state.casebookYears : "Imported snapshot";
    const archiveLink = document.querySelector(".globe-console-head > a");
    archiveLink.href = state.panelView === "cases" ? "/documented-fires.json" : "/data.html";
    const linkLabel = state.panelView === "cases" ? "Inspect wildfire archive and sources" : "Inspect NASA data sources";
    archiveLink.setAttribute("aria-label", linkLabel);
    archiveLink.title = linkLabel;
    document.querySelector(".globe-console").classList.toggle("documented-view", state.documented);
    document.querySelector(".globe-console").classList.remove("has-selection", "documented-reading");
    $("globe-location").value = "";
    renderCasePage();
    updateLayerStamp();
  }

  async function toggleDocumented() {
    state.documented = !state.documented;
    $("globe-documented-toggle").setAttribute("aria-pressed", String(state.documented));
    document.querySelector(".documented-toggle-state").textContent = state.documented ? "On" : "Off";
    clearSelection();
    document.querySelector(".globe-console-body").scrollTop = 0;
    if (!state.documented) {
      state.selectedFire = null;
      $("documented-detail").hidden = true;
      $("documented-list").hidden = false;
      renderCasePage();
      draw(state.bridge?.view);
      return;
    }
    await loadCasebook();
    draw(state.bridge?.view);
  }

  function loadCasebook() {
    if (state.fires) return Promise.resolve(true);
    if (state.firesLoading) return state.firesLoading;
    state.firesLoading = fetchCasebook().finally(() => { state.firesLoading = null; });
    return state.firesLoading;
  }

  async function fetchCasebook() {
    $("documented-status").textContent = "Loading sourced wildfire cases…";
    $("casebook-retry").hidden = true;
    try {
      const data = await json("/documented-fires.json", AbortSignal.timeout(15000));
      state.casebookYears = `${data.period_start.slice(0,4)}–${data.period_end.slice(0,4)}`;
      state.fires = data.events.map((fire,index) => ({...fire,vector:FireGlobeMath.vector(fire.lon,fire.lat),effectPhase:index * 2.39996}));
      $("wildfire-case-count").textContent = format(state.fires.length);
      const sources = new Set(data.events.flatMap(fire => fire.sources.map(source => source.url)));
      $("wildfire-archive-note").textContent = `${sources.size} source links · selected cases, not exhaustive`;
      $("globe-data-kind").textContent = state.casebookYears;
      $("documented-status").textContent = `${state.fires.length} sourced case files · select one to explore`;
      renderCasePage();
      syncControls();updateLayerStamp();draw(state.bridge?.view);
      return true;
    } catch {
      $("documented-status").textContent = "Wildfire cases could not load. Retry the archive.";
      $("wildfire-archive-note").textContent = "Wildfire archive unavailable";
      $("casebook-retry").hidden = false;
      return false;
    }
  }

  function renderCasePage() {
    if (!state.fires) return;
    const query = state.caseQuery.trim().toLowerCase();
    const matches = state.fires.filter(fire => `${fire.name} ${fire.place} ${fire.period}`.toLowerCase().includes(query));
    const pages = Math.max(1, Math.ceil(matches.length / 4));
    state.casePage = Math.max(0, Math.min(state.casePage, pages - 1));
    $("casebook-prev").disabled = state.casePage === 0;
    $("casebook-next").disabled = state.casePage >= pages - 1;
    $("casebook-page").textContent = matches.length ? `${state.casePage + 1} / ${pages} · ${matches.length} cases` : "No matching cases";
    $("documented-status").textContent = matches.length ? "" : "Try another name, place or year.";
    $("documented-list").replaceChildren(...matches.slice(state.casePage * 4, state.casePage * 4 + 4).map(fire => {
        const index = state.fires.indexOf(fire);
        const button = element("button");button.type="button";button.dataset.fireId=fire.id;
        const number = element("span",String(index + 1).padStart(2,"0"),"documented-number");
        number.setAttribute("aria-hidden","true");
        const copy = element("span",undefined,"documented-card-copy");
        const toll=element("small",fire.period,"documented-case-date");
        copy.append(element("strong",fire.name),element("span",fire.place),toll);
        const arrow = element("span","↗","documented-card-arrow");arrow.setAttribute("aria-hidden","true");
        button.append(number,copy,arrow);
        button.addEventListener("click",()=>selectFire(fire.id));return button;
      }));
  }

  function setPanelView(view) {
    state.panelView = view;
    clearSelection();
    const satellite = view === "satellite";
    $("globe-evidence-tools").hidden = !satellite;
    $("globe-evidence-tools").open = satellite;
    $("wildfire-archive-note").hidden = satellite;
    document.querySelectorAll("[data-console-view]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.consoleView === view)));
    renderCasePage();
    document.querySelector(".globe-console-body").scrollTop = 0;
  }

  function selectFire(id) {
    if (state.revealing) return;
    if (state.panelView !== "cases") setPanelView("cases");
    if (!state.documented) toggleDocumented();
    const fire = state.fires?.find(item => item.id === id);
    if (!fire) return;
    clearSelection();state.selectedFire=id;
    document.querySelector(".globe-console").classList.add("documented-reading");
    focus(fire.lon,fire.lat);
    $("documented-list").hidden=true;
    $("documented-status").textContent="";
    const detail=$("documented-detail");detail.hidden=false;detail.replaceChildren();
    const back=element("button","← Layer details","documented-back");back.type="button";
    back.addEventListener("click",()=>{
      document.querySelector(".globe-console").classList.remove("documented-reading");
      state.selectedFire=null;detail.hidden=true;$("documented-list").hidden=false;
      renderCasePage();
      $("earth-details-close").focus({preventScroll: true});
    });
    detail.append(back,element("span",`${fire.period} · ${fire.unit||"Wildfire"}`,"globe-kicker"),element("h3",fire.name),element("p",fire.place,"documented-place"),element("p",fire.summary,"documented-summary"));
    detail.insertBefore(locationActions(fire.lon, fire.lat), detail.querySelector(".documented-summary"));
    const fatalityGrid=element("div",undefined,"documented-fatalities");
    const deathRows=[
      ["Direct deaths",fire.deaths?.direct],
      ["First responders",fire.deaths?.responders],
      ["Smoke-related estimate",fire.deaths?.smoke]
    ];
    for(const [label,death] of deathRows){
      if(!death)continue;
      const card=element("section",undefined,"documented-fatality");
      card.append(element("span",label),element("strong",death.label),element("small",death.detail));
      fatalityGrid.append(card);
    }
    detail.append(fatalityGrid);
    const scope=element("p","Counts follow the linked source and may use different definitions. ‘Not separately reported’ does not mean zero. Smoke estimates are modeled indirect impacts, separate from direct deaths.","documented-death-note");
    detail.append(scope);
    const links=element("div",undefined,"documented-sources");
    for(const source of fire.sources){
      const link=element("a");link.href=source.url;link.target="_blank";link.rel="noopener noreferrer";
      link.dataset.kind=source.kind||"news";
      link.append(element("strong",`${source.publisher} ↗`),element("span",source.label),element("small",`Published ${source.published}`));
      links.append(link);
    }
    const navigation=element("nav",undefined,"documented-navigation");
    navigation.setAttribute("aria-label","Browse wildfire stories");
    const index=state.fires.indexOf(fire);
    const previous=element("button","← Previous");previous.type="button";
    const next=element("button","Next case →");next.type="button";
    previous.disabled=index===0;next.disabled=index===state.fires.length-1;
    previous.addEventListener("click",()=>selectFire(state.fires[index-1].id));
    next.addEventListener("click",()=>selectFire(state.fires[index+1].id));
    navigation.append(previous,element("span",`${index+1} / ${state.fires.length}`),next);
    detail.append(element("h4","News coverage & supporting sources"),links,navigation);
    document.querySelector(".globe-console-body").scrollTop=0;
    openEarthDetails();
    back.focus({preventScroll:true});
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
      if (!state.documented) $("globe-stamp").textContent = "SATELLITE EVIDENCE UNAVAILABLE";
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
    if (state.panelView !== "satellite") setPanelView("satellite");
    const item = state.points.find(c => c.id === id);
    if (!item) return;
    const request = ++state.detailRequest;
    state.detailController?.abort();
    state.detailController = new AbortController();
    state.selected = id;
    state.details = null;
    focus(item.lon, item.lat);
    if (![...$("globe-location").options].some(o => o.value === id)) $("globe-location").add(new Option(coords(item.lon, item.lat), id));
    $("globe-location").value = id;
    const panel = $("globe-selection");
    panel.hidden = false;
    $("globe-overview").hidden = true;
    $("globe-documented").hidden = true;
    state.selectedFire=null;
    $("documented-detail").hidden=true;$("documented-list").hidden=false;
    if(state.fires) $("documented-status").textContent=`${state.fires.length} sourced case files · select one to explore`;
    $("globe-console-title").textContent="Satellite evidence";
    $("globe-source-label").textContent="NASA FIRMS";
    $("globe-data-kind").textContent="Imported snapshot";
    const sourceLink = document.querySelector(".globe-console-head > a");
    sourceLink.href="/data.html";
    sourceLink.setAttribute("aria-label", "Inspect NASA data sources");
    sourceLink.title="Inspect NASA data sources";
    document.querySelector(".globe-console").classList.remove("documented-view", "documented-reading");
    document.querySelector(".globe-console").classList.add("has-selection");
    panel.replaceChildren(element("p", "Loading source evidence…"));
    const close = element("button", "← Back to satellite data", "globe-close");
    close.type = "button";
    close.addEventListener("click", () => { clearSelection(); $("globe-location").focus(); });
    panel.prepend(close);
    openEarthDetails();
    try {
      const data = await json(`/api/globe/detail?${new URLSearchParams({cell: id, source: state.data.source, date: state.data.date})}`, AbortSignal.any([state.detailController.signal, AbortSignal.timeout(30000)]));
      if (request !== state.detailRequest) return;
      state.details = data;
      panel.replaceChildren();
      panel.append(close, element("span", "1° GEOGRAPHIC GROUP", "globe-kicker"), element("h3", coords(item.lon, item.lat)));
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
        link.href = `/?${new URLSearchParams({demo: 0, series: series[src.source_id], year: src.last.slice(0, 4), month: Number(src.last.slice(5, 7)), bbox: bbox.join(",")})}#atlas-section`;
        link.title = "Inspect this satellite and area in the atlas";
        links.append(link);
      }
      const atlas = element("details");
      atlas.append(element("summary", "Explore this area in the atlas"), links);
      panel.append(atlas);
      const details = element("details"), list = element("ol");
      details.append(element("summary", `${data.observations.length} latest source records`));
      for (const row of data.observations) {
        const li = element("li");
        li.append(element("strong", coords(row.lon, row.lat)), element("div", stamp(row.acquisition_utc)), element("div", `${row.source_id} · ${row.frp_mw == null ? "FRP unknown" : format(row.frp_mw) + " MW"} · confidence ${row.confidence_raw}`));
        list.append(li);
      }
      details.append(list);
      panel.append(details, interpretation);
    } catch (error) {
      if (request === state.detailRequest) panel.replaceChildren(close, element("p", `Evidence unavailable: ${error.message}. Return to the overview to retry.`));
    }
  }

  window.addEventListener("earth-ready", event => attach(event.detail.frame));
  window.addEventListener("earth-unavailable", () => {
    state.failedEarth = true;
    state.bridge?.cancelOrbit();state.bridge = null;
    updateLayerStamp();
    $("globe-status").textContent = "3D unavailable · browse locations below.";
    if ($("globe-markers").checked) revealDetections();
    else scheduleLoad();
    syncControls();
  });

  window.addEventListener("fireatlas-map-selection", async event => {
    const {layer,id} = event.detail || {};
    if(!["thermal","documented"].includes(layer))return;
    if(state.revealing){cancelReveal();$("globe-markers").checked=false;}
    if(layer === "documented") {
      if(!state.documented) await toggleDocumented();
      else if(state.firesLoading) await state.firesLoading.catch(()=>{});
      selectFire(id);
      const fire = state.fires?.find(item => item.id === id);
      if (fire) zoomToLocation(fire.lon, fire.lat);
      return;
    }
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
    const dialog = $("earth-details-dialog");
    $("earth-details-open").addEventListener("click", () => {
      if (!state.selectedFire && !state.selected) setPanelView(state.documented ? "cases" : $("globe-markers").checked ? "satellite" : state.panelView);
      openEarthDetails();
    });
    $("earth-details-close").addEventListener("click", closeEarthDetails);
    dialog.addEventListener("close", () => {document.documentElement.classList.remove("earth-details-visible");$("earth-details-open").focus({preventScroll:true});});
    dialog.addEventListener("click", event => {if(event.target===dialog){const box=dialog.getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)closeEarthDetails();}});
    document.querySelector(".browse-map-cases").addEventListener("click", () => {closeEarthDetails();document.querySelector('[data-event-layer="documented"]').click();});
    document.querySelectorAll("[data-console-view]").forEach(button => button.addEventListener("click", () => setPanelView(button.dataset.consoleView)));
    $("casebook-search").addEventListener("input", e => { state.caseQuery = e.target.value; state.casePage = 0; renderCasePage(); });
    for (const [id, step] of [["casebook-prev", -1], ["casebook-next", 1]]) $(id).addEventListener("click", () => { state.casePage += step; renderCasePage(); });
    $("globe-markers").checked = false;
    $("globe-markers").addEventListener("change", revealDetections);
    $("globe-documented-toggle").addEventListener("click", toggleDocumented);
    $("casebook-retry").addEventListener("click", loadCasebook);
    loadCasebook();
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
    $("globe-reset").addEventListener("click", () => {state.pendingZoom=null;state.bridge?.reset();setRotationUI(false);});
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
