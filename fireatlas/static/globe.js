/* Authentic NASA observations on the existing analytic Earth renderer. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const format = value => new Intl.NumberFormat("en", {maximumFractionDigits:1}).format(value);
  const stamp = value => value ? value.replace("T", " · ").replace(":00Z", " UTC") : "Unknown";
  const coords = (lon, lat) => `${Math.abs(lat).toFixed(2)}°${lat < 0 ? "S" : "N"} / ${Math.abs(lon).toFixed(2)}°${lon < 0 ? "W" : "E"}`;
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
    region: "world",
    selectedFire: null
  };

  function element(tag, text, className) {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (className) el.className = className;
    return el;
  }

  function setRotationUI(playing) {
    const btn = $("globe-rotate");
    if (!btn) return;
    const label = playing ? "Pause rotation" : "Resume rotation";
    if (btn.textContent !== label) btn.textContent = label;
    if (btn.getAttribute("aria-pressed") !== String(!playing)) btn.setAttribute("aria-pressed", String(!playing));
  }

  function revealStatus(text) {
    $("globe-reveal-status").textContent = text;
    $("globe-reveal-status").hidden = !text;
  }

  function syncControls() {
    document.querySelectorAll("[data-globe-region],#globe-rotate,#globe-zoom-in,#globe-zoom-out").forEach(b => b.disabled = state.revealing || state.failedEarth);
    $("globe-source").disabled = state.revealing || !!state.loading || !state.data?.sources.length;
    $("globe-date").disabled = $("globe-source").disabled;
    $("globe-location").disabled = state.revealing || !!state.loading || !state.data?.total;
    document.querySelectorAll(".imprint-bar,#imprint-reset").forEach(b => b.disabled = state.revealing || !!state.loading);
    $("globe-documented-toggle").disabled = state.revealing;
    document.querySelectorAll(".documented-list button").forEach(b => b.disabled = state.revealing);
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
    state.bridge?.focus(lon, lat);
    setRotationUI(false);
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
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, view.width, view.height);
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
      // Place label on large clusters when view is wide enough
      if (item.count > 400 && view.width > 900) {
        ctx.save();
        ctx.font = `500 ${9 * markerScale}px Inter, system-ui, sans-serif`;
        ctx.fillStyle = "rgba(220, 232, 236, 0.65)";
        ctx.textAlign = "center";
        const labelY = point.y + radius + 11 * markerScale;
        const label = `${Math.abs(item.lat).toFixed(0)}°${item.lat < 0 ? "S" : "N"} ${Math.abs(item.lon).toFixed(0)}°${item.lon < 0 ? "W" : "E"}`;
        ctx.fillText(label, point.x, labelY);
        ctx.restore();
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
    for (const fire of state.documented && !state.revealing ? state.fires || [] : []) {
      const p = FireGlobeMath.project(fire.vector, view);
      if (!p) continue;
      const size = view.width < 600 ? 9 : 10;
      ctx.beginPath();ctx.arc(p.x,p.y,size+5,0,Math.PI*2);ctx.fillStyle="#08171ff5";ctx.fill();
      ctx.lineWidth=2;ctx.strokeStyle="#83cfff";ctx.stroke();
      ctx.beginPath();ctx.moveTo(p.x,p.y-size);ctx.lineTo(p.x+size,p.y);ctx.lineTo(p.x,p.y+size);ctx.lineTo(p.x-size,p.y);ctx.closePath();
      ctx.fillStyle = fire.id === state.selectedFire ? "#def6ff" : "#83cfff";
      ctx.fill();ctx.lineWidth=1.5;ctx.strokeStyle="#2d6f9d";ctx.stroke();
      if (fire.id === state.selectedFire) {
        ctx.beginPath();ctx.arc(p.x,p.y,size+9,0,Math.PI*2);ctx.strokeStyle="#a6dfff";ctx.stroke();
      }
      state.visible.push({x:p.x,y:p.y,radius:size,id:fire.id,kind:"documented"});
      fireCount++;
    }
    canvas.dataset.documentedVisible = String(fireCount);
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
    surface.setAttribute("aria-label", "Earth with NASA thermal detection clusters. Drag or use arrow keys to rotate. Click a point to inspect it, or use Browse detection clusters on the page.");
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
        .filter(p => p.d <= (p.kind === "documented" ? 20 : e.pointerType === "touch" ? 13 : 8)).sort((a, b) => Number(b.kind === "documented") - Number(a.kind === "documented") || a.d - b.d)[0];
      if (target) target.kind === "documented" ? selectFire(target.id) : select(target.id);
    });
    draw(bridge.view);
    const selectedFire = state.documented && state.fires?.find(fire => fire.id === state.selectedFire);
    if (selectedFire) focus(selectedFire.lon, selectedFire.lat);
    else if(state.selected){const selected=state.points.find(p=>p.id===state.selected);if(selected)focus(selected.lon,selected.lat);}
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
    $("globe-selection").hidden = true;
    $("globe-overview").hidden = state.documented;
    $("globe-documented").hidden = !state.documented;
    $("globe-console-title").textContent = state.documented ? "Historical casebook" : "Observation snapshot";
    document.querySelector(".globe-console").classList.toggle("documented-view", state.documented);
    document.querySelector(".globe-console").classList.remove("has-selection", "documented-reading");
    $("globe-location").value = "";
  }

  async function toggleDocumented() {
    state.documented = !state.documented;
    $("globe-documented-toggle").setAttribute("aria-pressed", String(state.documented));
    document.querySelector(".documented-toggle-state").textContent = state.documented ? "Hide" : "Show";
    clearSelection();
    document.querySelector(".globe-console").scrollTop = 0;
    if (!state.documented) {
      state.selectedFire = null;
      $("documented-detail").hidden = true;
      $("documented-list").hidden = false;
      if (state.fires) $("documented-status").textContent = `${state.fires.length} sourced case files · select one to explore`;
      draw(state.bridge?.view);
      return;
    }
    if (state.fires) { draw(state.bridge?.view);return; }
    if (state.firesLoading) return;
    $("documented-status").textContent = "Loading sourced case files…";
    state.firesLoading = json("/documented-fires.json", AbortSignal.timeout(15000));
    try {
      const data = await state.firesLoading;
      state.fires = data.events.map(fire => ({...fire,vector:FireGlobeMath.vector(fire.lon,fire.lat)}));
      $("documented-status").textContent = `${state.fires.length} sourced case files · select one to explore`;
      $("documented-list").replaceChildren(...state.fires.map((fire, index) => {
        const button = element("button");button.type="button";button.dataset.fireId=fire.id;
        const number = element("span",String(index + 1).padStart(2,"0"),"documented-number");
        number.setAttribute("aria-hidden","true");
        const copy = element("span",undefined,"documented-card-copy");
        const toll=element("small",`${fire.period} · ${fire.deaths?.direct?.label||"Fatality count unavailable"}`,"documented-case-toll");
        copy.append(element("strong",fire.name),element("span",fire.place),toll);
        const arrow = element("span","↗","documented-card-arrow");arrow.setAttribute("aria-hidden","true");
        button.append(number,copy,arrow);
        button.addEventListener("click",()=>selectFire(fire.id));return button;
      }));
      syncControls();draw(state.bridge?.view);
    } catch {
      $("documented-status").textContent = "Reports could not load.";
      const retry = element("button","Retry reports");retry.type="button";
      retry.addEventListener("click",()=>{state.documented=false;toggleDocumented();});
      $("documented-list").replaceChildren(retry);
    } finally {state.firesLoading=null;}
  }

  function selectFire(id) {
    if (!state.documented || state.revealing) return;
    const fire = state.fires?.find(item => item.id === id);
    if (!fire) return;
    clearSelection();state.selectedFire=id;
    document.querySelector(".globe-console").classList.add("documented-reading");
    focus(fire.lon,fire.lat);
    $("documented-list").hidden=true;
    $("documented-status").textContent="";
    const detail=$("documented-detail");detail.hidden=false;detail.replaceChildren();
    const back=element("button","← Back to casebook","documented-back");back.type="button";
    back.addEventListener("click",()=>{
      document.querySelector(".globe-console").classList.remove("documented-reading");
      state.selectedFire=null;detail.hidden=true;$("documented-list").hidden=false;
      $("documented-status").textContent=`${state.fires.length} sourced case files · select one to explore`;
      document.querySelector(`[data-fire-id="${fire.id}"]`)?.focus();
    });
    detail.append(back,element("span",`${fire.period} · ${fire.unit||"Wildfire"}`,"globe-kicker"),element("h3",fire.name),element("p",fire.place,"documented-place"),element("p",fire.summary,"documented-summary"));
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
    document.querySelector(".globe-console").scrollTop=0;
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
      $("globe-cell-count").textContent = `${format(data.clusters.length)} geographic groups`;
      $("globe-period").textContent = data.latest_observation ? `${data.window_start} → ${data.window_end} · UTC\nLatest observation ${stamp(data.latest_observation)}` : "No NASA FIRMS snapshot imported on this server.";
      $("globe-stamp").textContent = data.latest_observation ? `${day === "all" ? data.window_start + " → " + data.window_end : day} · IMPORTED SNAPSHOT` : "NO NASA OBSERVATIONS IMPORTED";
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
      $("globe-stamp").textContent = "OBSERVATION DATA UNAVAILABLE";
      $("globe-cell-count").textContent = "Snapshot unavailable";
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
    $("globe-console-title").textContent="Observation snapshot";
    document.querySelector(".globe-console").classList.remove("documented-view", "documented-reading");
    document.querySelector(".globe-console").classList.add("has-selection");
    panel.replaceChildren(element("p", "Loading source evidence…"));
    const close = element("button", state.documented ? "← Back to fire casebook" : "← Back to observations", "globe-close");
    close.type = "button";
    close.addEventListener("click", () => { clearSelection(); (state.documented ? $("globe-documented-toggle") : $("globe-location")).focus(); });
    panel.prepend(close);
    try {
      const data = await json(`/api/globe/detail?${new URLSearchParams({cell: id, source: state.data.source, date: state.data.date})}`, AbortSignal.any([state.detailController.signal, AbortSignal.timeout(30000)]));
      if (request !== state.detailRequest) return;
      state.details = data;
      panel.replaceChildren();
      panel.append(close, element("span", "1° GEOGRAPHIC GROUP", "globe-kicker"), element("h3", coords(item.lon, item.lat)));
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
    $("globe-markers").checked = false;
    $("globe-markers").addEventListener("change", revealDetections);
    $("globe-documented-toggle").addEventListener("click", toggleDocumented);
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
    document.querySelectorAll("[data-globe-region]").forEach(button => button.addEventListener("click", () => {
      clearSelection();
      state.region=button.dataset.regionKey;updateLocations();
      focus(...button.dataset.globeRegion.split(",").map(Number));
    }));
    // Fetch after the Earth becomes visible, or immediately on an explicit request.
    updateLocations();
    syncControls();
  });
})();
