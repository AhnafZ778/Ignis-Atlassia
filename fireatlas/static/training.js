(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const state = {scenario: null, snapshot: null, elapsed: 0, view: "commander", selected: "alpha",
    manualOffline: false, browserOffline: !navigator.onLine, failed: false, heldGps: {},
    playing: false, speed: 60, loading: false, generation: 0, controller: null,
    acknowledgments: [], sound: false, seenAlerts: new Set(), lastAnnouncement: "", restored: false};
  let map, sceneLayers, audioContext;
  const offline = () => state.manualOffline || state.browserOffline || state.failed;
  const now = () => Date.parse(state.scenario.start_utc) + state.elapsed * 1000;
  const isoNow = () => new Date(now()).toISOString();
  const time = value => new Date(value).toISOString().slice(11, 19);
  const latlng = point => [point[1], point[0]];
  const ageLabel = seconds => seconds < 60 ? `${Math.floor(seconds)} s` : `${Math.floor(seconds / 60)} min`;
  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function notify(message) {
    $("training-toast").textContent = message;
    $("training-toast").classList.add("visible");
    clearTimeout(notify.timer);
    notify.timer = setTimeout(() => $("training-toast").classList.remove("visible"), 3500);
  }
  async function request(path, signal) {
    const response = await fetch(path, {signal: signal || AbortSignal.timeout(8000), cache: "no-store"});
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || "The exercise could not be loaded.");
    return body;
  }
  function cancelRequest() {
    state.generation++;
    state.controller?.abort();
    state.loading = false;
  }
  function pause() {
    state.playing = false;
    $("play-replay").textContent = "▶ Play replay";
  }
  function resetFutureRecords(target) {
    state.acknowledgments = state.acknowledgments.filter(a => a.elapsed_seconds <= target);
    state.heldGps = {};
    $("gps-drill").checked = false;
    state.seenAlerts.clear();
  }
  async function seek(target) {
    target = Math.max(0, Math.min(state.scenario.duration_seconds, Math.round(target)));
    const previous = state.elapsed;
    if (offline()) {
      if (!state.snapshot || target < state.snapshot.elapsed_seconds) {
        notify("Reconnect before rewinding beyond the last received snapshot.");
        $("replay-timeline").value = state.elapsed / 60;
        return;
      }
      if (target < previous) resetFutureRecords(target);
      state.elapsed = target;
      render();
      return true;
    }
    cancelRequest();
    const generation = state.generation;
    const controller = new AbortController();
    state.controller = controller;
    state.loading = true;
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const snapshot = await request(`/api/training/snapshot?elapsed=${target}`, controller.signal);
      if (generation !== state.generation) return;
      if (target < previous) resetFutureRecords(target);
      state.snapshot = snapshot;
      state.elapsed = target;
      state.failed = false;
      $("training-error").hidden = true;
      render();
      return true;
    } catch (error) {
      if (generation !== state.generation) return;
      state.failed = true;
      pause();
      if (state.snapshot) {
        state.elapsed = target >= state.snapshot.elapsed_seconds ? target : previous;
        render();
      } else {
        $("training-error").hidden = false;
        $("training-error").textContent = "No snapshot received. Restore the connection and use Retry connection to load the exercise.";
        $("connection-banner").hidden = false;
        $("connection-message").textContent = "Exercise connection unavailable.";
      }
    } finally {
      clearTimeout(timeout);
      if (generation === state.generation) state.loading = false;
    }
  }
  function initMap() {
    if (typeof L === "undefined") {
      $("training-map").textContent = "The map is unavailable. Crew statuses, replay and evidence remain available below.";
      return;
    }
    map = L.map("training-map", {zoomControl: false, scrollWheelZoom: false, minZoom: 11, maxZoom: 17, attributionControl: false});
    L.control.zoom({position: "bottomleft"}).addTo(map);
    // Decorative synthetic contour lines; no external tiles or future incident data.
    for (const [lat, lon, stretch] of [[39.811, -121.133, 1.5], [39.826, -121.098, 1]]) {
      for (let ring = 0; ring < 9; ring++) {
        const coordinates = Array.from({length: 70}, (_, i) => {
          const angle = i / 69 * Math.PI * 2, radius = .0015 + ring * .0013;
          return [lat + Math.sin(angle) * radius * (1 + .12 * Math.sin(angle * 3)),
            lon + Math.cos(angle) * radius * stretch * (1 + .12 * Math.cos(angle * 4))];
        });
        L.polygon(coordinates, {color: "#50716b", weight: .7, opacity: .27, fillColor: "#446a5b", fillOpacity: ring === 8 ? .05 : 0, interactive: false}).addTo(map);
      }
    }
    L.polyline([[39.828,-121.117],[39.821,-121.118],[39.818,-121.123],[39.810,-121.122],[39.806,-121.125],[39.800,-121.121],[39.788,-121.123]],
      {color: "#4f8c9e", weight: 2, opacity: .3, interactive: false}).addTo(map);
    for (const [point, label] of [[[39.818,-121.135],"WEST RIDGE"], [[39.795,-121.117],"ALDER CREEK"], [[39.823,-121.106],"EAST RIDGE"]]) {
      L.marker(point, {interactive: false, icon: L.divIcon({className: "terrain-label", html: element("span", "", label), iconSize: [90, 12]})}).addTo(map);
    }
    L.circleMarker(state.scenario.staging, {radius: 5, color: "#9ebcc5", fillColor: "#314a55", fillOpacity: 1, weight: 2}).addTo(map);
    L.marker(state.scenario.staging, {interactive: false, icon: L.divIcon({className: "staging-label", html: "STAGING A", iconSize: [100, 13], iconAnchor: [-5, 6]})}).addTo(map);
    sceneLayers = L.layerGroup().addTo(map);
    fitScene();
  }
  function fitScene() { if (map) map.fitBounds(state.scenario.bounds, {padding: [25, 30]}); }
  function drawMap(assessment) {
    if (!map) return;
    sceneLayers.clearLayers();
    L.geoJSON(state.snapshot.zone.geometry, {style: {color: "#e7a06f", weight: 1.5, fillColor: "#d48d59", fillOpacity: .14}})
      .bindTooltip(element("span", "", `${state.snapshot.zone.id} · published ${time(state.snapshot.zone.published_utc)} UTC`)).addTo(sceneLayers);
    const routeColor = assessment.routeStatus === "current" ? "#91ced4" : assessment.routeStatus === "conflict" ? "#f2a074" : "#82909a";
    L.geoJSON(state.snapshot.route.geometry, {style: {color: routeColor, weight: 3, dashArray: assessment.routeStatus === "current" ? "8 5" : "3 8", opacity: .85}})
      .bindTooltip(element("span", "", `${state.snapshot.route.name} · ${assessment.routeLabel}`)).addTo(sceneLayers);
    for (const observation of state.snapshot.observations) {
      const tip = `${observation.sensor} · acquired ${time(observation.acquisition_utc)} · available ${time(observation.available_utc)} UTC`;
      L.circleMarker(latlng(observation.coordinates), {radius: 4, color: "#f7d7a4", weight: 1, fillColor: "#e9a468", fillOpacity: 1})
        .bindTooltip(element("span", "", tip)).addTo(sceneLayers);
    }
    for (const crew of assessment.crews) {
      L.circle(latlng(crew.position), {radius: crew.accuracy_m, color: crew.status === "unknown" ? "#9aa5ae" : "#a4cfd5", weight: 1, fillOpacity: .08, opacity: .45}).addTo(sceneLayers);
      L.marker(latlng(crew.position), {icon: L.divIcon({className: "", html: element("span", `crew-pin ${crew.status}`, crew.id[0].toUpperCase()), iconSize: [29, 29], iconAnchor: [14, 14]})})
        .bindTooltip(element("span", "", `${crew.name} · ${crew.label} · GPS ${ageLabel(crew.gpsAge)} old · ±${crew.accuracy_m} m`))
        .on("click", () => { state.selected = crew.id; setView("crew"); }).addTo(sceneLayers);
    }
  }
  function setView(view) {
    state.view = view;
    $("commander-screen").hidden = view !== "commander";
    $("crew-screen").hidden = view !== "crew";
    for (const name of ["commander", "crew"]) {
      $(`${name}-view`).classList.toggle("selected", view === name);
      $(`${name}-view`).setAttribute("aria-pressed", String(view === name));
    }
    if (state.snapshot) render();
  }
  function currentAcks() { return state.acknowledgments.filter(a => a.elapsed_seconds <= state.elapsed); }
  function isAcknowledged(kind, id, crewId) { return currentAcks().some(a => a.kind === kind && a.target_id === id && a.crew_id === crewId); }
  function acknowledge(kind, id, crewId, title) {
    if (isAcknowledged(kind, id, crewId)) return;
    state.acknowledgments.push({kind, target_id: id, crew_id: crewId, title,
      elapsed_seconds: state.elapsed, replay_utc: isoNow(), snapshot_id: state.snapshot.snapshot_id,
      delivery: "local browser exercise record", connection: offline() ? "offline" : "connected"});
    notify("Acknowledgment recorded locally. The underlying condition remains active.");
    render();
  }
  function renderCrews(assessment) {
    $("crew-list").replaceChildren();
    for (const crew of assessment.crews) {
      const button = element("button", `crew-row ${crew.status}`); button.type = "button";
      const info = element("span"); info.append(element("strong", "", crew.name), element("small", "", crew.label));
      button.append(element("span", "crew-avatar", crew.id[0].toUpperCase()), info, element("span", "status-dot"));
      button.addEventListener("click", () => { state.selected = crew.id; setView("crew"); });
      $("crew-list").append(button);
    }
    const crew = assessment.crews.find(c => c.id === state.selected);
    $("selected-crew").value = state.selected;
    $("device-state").className = `device-state ${crew.status}`;
    $("device-label").textContent = crew.label;
    $("device-detail").textContent = crew.detail;
    $("device-meta").textContent = `GPS ${ageLabel(crew.gpsAge)} old · ±${crew.accuracy_m} m · heartbeat ${ageLabel(crew.heartbeatAge)} old`;
    $("gps-drill-label").textContent = `Freeze ${crew.name}'s location`;
    $("gps-drill").checked = !!state.heldGps[crew.id];
    $("route-version").textContent = state.snapshot.route.id.toUpperCase();
    $("route-status").textContent = assessment.routeLabel;
    $("route-status").dataset.state = assessment.routeStatus;
    $("route-detail").textContent = `${state.snapshot.route.name} · ${state.snapshot.route.approved_by}. Conditions along this route are unverified.`;
    $("route-validity").textContent = `Published ${time(state.snapshot.route.published_utc)} · expires ${time(state.snapshot.route.expires_utc)} UTC`;
    const acked = isAcknowledged("route", state.snapshot.route.id, state.selected);
    const button = $("ack-route");
    button.disabled = state.view === "crew" && (acked || assessment.routeStatus !== "current");
    button.textContent = state.view === "commander" ? "Review on crew device ↗" : acked ? "Briefing acknowledged locally" : assessment.routeStatus === "current" ? "Acknowledge route briefing" : "Current route cannot be acknowledged";
    const acknowledgments = currentAcks().filter(a => a.kind === "route" && a.target_id === state.snapshot.route.id);
    $("route-ack-status").textContent = acknowledgments.length ? `Local acknowledgments: ${acknowledgments.map(a => a.crew_id).join(", ")}` : "Acknowledgments are local exercise records.";
  }
  function beep() {
    if (!state.sound || !audioContext) return;
    const oscillator = audioContext.createOscillator(), gain = audioContext.createGain();
    oscillator.type = "sine"; oscillator.frequency.value = 580;
    gain.gain.setValueAtTime(.035, audioContext.currentTime);
    gain.gain.exponentialRampToValueAtTime(.001, audioContext.currentTime + .18);
    oscillator.connect(gain); gain.connect(audioContext.destination);
    oscillator.start(); oscillator.stop(audioContext.currentTime + .2);
  }
  function renderAlerts(assessment) {
    const alerts = assessment.alerts.filter(a => state.view === "commander" || !a.crew_id || a.crew_id === state.selected);
    const priority = {critical: 0, unknown: 1, caution: 2};
    alerts.sort((a, b) => priority[a.severity] - priority[b.severity]);
    $("alert-count").textContent = alerts.length;
    $("alert-list").replaceChildren();
    if (!alerts.length) {
      const row = element("div", "clear-check"), content = element("div");
      content.append(element("strong", "", "No active exercise alerts"), element("p", "", "The current checks have no exceptions. This does not establish route safety. Advance the replay to review new evidence."));
      row.append(element("span", "", "✓"), content); $("alert-list").append(row);
    }
    for (const alert of alerts) {
      const card = element("article", `alert-card ${alert.severity}`);
      card.append(element("h3", "", alert.title), element("p", "", alert.detail));
      const actor = state.view === "crew" ? state.selected : "commander";
      const acked = isAcknowledged("alert", alert.id, actor);
      const button = element("button", "", acked ? "Acknowledged locally · condition active" : "Acknowledge alert");
      button.type = "button"; button.disabled = acked;
      button.addEventListener("click", () => acknowledge("alert", alert.id, actor, alert.title));
      card.append(button); $("alert-list").append(card);
    }
    const signature = alerts.map(a => a.id).join(";");
    if (signature !== state.lastAnnouncement) {
      $("alert-announcement").textContent = alerts.length ? `${alerts.length} exercise alerts. ${alerts.map(a => a.title).join(". ")}` : "No active exercise alerts.";
      state.lastAnnouncement = signature;
    }
    if (assessment.alerts.some(a => !state.seenAlerts.has(a.id))) beep();
    state.seenAlerts = new Set(assessment.alerts.map(a => a.id));
  }
  function renderEvents() {
    const entries = state.snapshot.events.map(event => ({time: event.published_utc, title: event.title, detail: event.detail}));
    for (const ack of currentAcks()) entries.push({time: ack.replay_utc, title: `Local acknowledgment · ${ack.crew_id}`, detail: ack.title});
    entries.sort((a, b) => Date.parse(b.time) - Date.parse(a.time));
    $("event-log").replaceChildren();
    for (const item of entries) {
      const row = element("li"), stamp = element("time", "", `${time(item.time)} UTC`); stamp.dateTime = item.time;
      row.append(stamp, element("strong", "", item.title), element("p", "", item.detail));
      $("event-log").append(row);
    }
  }
  function render() {
    if (!state.snapshot) return;
    const assessment = TrainingState.assess(state.snapshot, now(), {offline: offline(), heldGps: state.heldGps});
    $("replay-clock").textContent = time(now());
    $("clock-detail").textContent = state.elapsed === state.scenario.duration_seconds ? "Replay complete · review your record" : state.playing ? "Playing the exercise timeline" : "Paused · choose your next step";
    $("crew-summary").textContent = `${assessment.crews.filter(c => c.status !== "unknown").length} / 3 fresh`;
    $("evidence-count").textContent = `${state.snapshot.observations.length} pixels`;
    $("snapshot-revision").textContent = `${state.snapshot.zone.id} · ${state.snapshot.route.id}`;
    $("scene-version").textContent = `${offline() ? "CACHED" : "PUBLISHED"} · ${time(state.snapshot.as_of_utc)} UTC · REV ${state.snapshot.revision}`;
    $("replay-timeline").value = state.elapsed / 60;
    $("elapsed-label").textContent = `${String(Math.floor(state.elapsed / 60)).padStart(2, "0")} / 60 MIN`;
    $("connection-banner").hidden = !offline();
    $("connection-message").textContent = `${state.manualOffline ? "Airplane-mode drill" : "Connection unavailable"}. Last snapshot: ${time(state.snapshot.as_of_utc)} UTC (${ageLabel(assessment.snapshotAge)} old). Crew status is unknown; the replay clock still ages GPS and route validity.`;
    $("retry-connection").disabled = state.manualOffline;
    $("snapshot-short-id").textContent = state.snapshot.snapshot_id.slice(0, 12);
    $("snapshot-hash").textContent = state.snapshot.snapshot_id;
    $("snapshot-time").textContent = `${state.snapshot.as_of_utc} · expires ${state.snapshot.valid_until_utc}`;
    $("scenario-provenance").textContent = `${state.scenario.name} v${state.snapshot.scenario_version} · synthetic`;
    for (const id of ["play-replay", "step-replay", "restart-replay", "replay-timeline", "export-exercise"]) $(id).disabled = false;
    if (state.elapsed >= state.scenario.duration_seconds) { pause(); $("play-replay").disabled = true; $("step-replay").disabled = true; }
    renderCrews(assessment); drawMap(assessment); renderAlerts(assessment); renderEvents();
    persist();
  }
  function persist() {
    if (!state.snapshot || !state.scenario) return;
    try {
      TrainingStore.save(sessionStorage, state);
      $("recovery-status").textContent = `${state.restored ? "Exercise restored · " : ""}Progress saved in this tab · ${currentAcks().length} local acknowledgments`;
    } catch {
      $("recovery-status").textContent = "Progress could not be saved in this browser. Export your record before reloading.";
    }
  }
  async function reconnect() {
    if (state.manualOffline) return;
    state.browserOffline = !navigator.onLine;
    if (state.browserOffline) { render(); return; }
    try {
      const scenario = await request("/api/training/scenario");
      const changed = state.scenario && (scenario.id !== state.scenario.id || scenario.version !== state.scenario.version);
      state.scenario = scenario;
      if (changed) {
        pause(); state.snapshot = null; state.elapsed = 0; resetFutureRecords(-1);
        try { TrainingStore.clear(sessionStorage); } catch { /* Storage may be disabled. */ }
        if (map) { map.remove(); map = null; }
        initMap(); notify("The exercise version changed. Starting a new briefing.");
      } else if (!map) initMap();
      state.failed = false;
      await seek(state.elapsed);
    } catch {
      state.failed = true; pause(); render();
      if (!state.snapshot) {
        $("training-error").hidden = false;
        $("training-error").textContent = "No saved exercise is available in this tab. Connect once to receive a briefing, then offline recovery can be used.";
        $("connection-banner").hidden = false;
        $("connection-message").textContent = "Exercise connection unavailable.";
        $("recovery-status").textContent = "No exercise saved in this tab.";
      }
    }
  }
  function exportRecord() {
    if (!state.snapshot) return;
    const record = {format: "fireatlas-training-record-v1", synthetic: true, scenario: state.scenario,
      replay_utc: isoNow(), elapsed_seconds: state.elapsed, view: state.view, selected_crew: state.selected,
      drills: {offline: offline(), held_gps: state.heldGps}, received_snapshot: state.snapshot,
      local_assessment: TrainingState.assess(state.snapshot, now(), {offline: offline(), heldGps: state.heldGps}),
      acknowledgments: currentAcks(), note: "Local exercise record. No acknowledgment was delivered to a remote commander."};
    const url = URL.createObjectURL(new Blob([JSON.stringify(record, null, 2)], {type: "application/json"}));
    const link = element("a"); link.href = url; link.download = `fireatlas-alder-creek-${time(now()).replaceAll(":", "")}.json`;
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  document.addEventListener("DOMContentLoaded", async () => {
    $("commander-view").addEventListener("click", () => setView("commander"));
    $("crew-view").addEventListener("click", () => setView("crew"));
    $("selected-crew").addEventListener("change", event => { state.selected = event.target.value; render(); });
    $("fit-scene").addEventListener("click", fitScene);
    $("play-replay").addEventListener("click", () => {
      state.playing = !state.playing;
      $("play-replay").textContent = state.playing ? "Ⅱ Pause replay" : "▶ Play replay";
      render();
    });
    $("replay-speed").addEventListener("change", event => { state.speed = Number(event.target.value); persist(); });
    $("step-replay").addEventListener("click", () => { pause(); seek(state.elapsed + 300); });
    $("replay-timeline").addEventListener("input", event => { pause(); seek(Number(event.target.value) * 60); });
    $("restart-replay").addEventListener("click", async () => {
      pause();
      if (offline()) { notify("Reconnect before starting a new replay."); return; }
      if (await seek(0)) { resetFutureRecords(-1); state.restored = false; render(); }
    });
    $("offline-drill").addEventListener("change", async event => {
      cancelRequest(); state.manualOffline = event.target.checked;
      if (state.manualOffline) render(); else await reconnect();
    });
    $("gps-drill").addEventListener("change", event => {
      if (!state.snapshot) return;
      if (event.target.checked) {
        const crew = state.snapshot.crews.find(c => c.id === state.selected);
        state.heldGps[crew.id] = {position: [...crew.position], accuracy_m: crew.accuracy_m,
          position_utc: new Date(now() - (state.snapshot.rules.gps_max_age_seconds + 60) * 1000).toISOString()};
      } else delete state.heldGps[state.selected];
      render();
    });
    $("retry-connection").addEventListener("click", reconnect);
    $("ack-route").addEventListener("click", () => {
      if (state.view === "commander") { setView("crew"); return; }
      const assessment = TrainingState.assess(state.snapshot, now(), {offline: offline(), heldGps: state.heldGps});
      if (assessment.routeStatus !== "current") return;
      acknowledge("route", state.snapshot.route.id, state.selected, `${state.snapshot.route.name} briefing received`);
    });
    $("sound-cues").addEventListener("click", async () => {
      try {
        if (!audioContext) audioContext = new (window.AudioContext || window.webkitAudioContext)();
        await audioContext.resume(); state.sound = !state.sound;
        $("sound-cues").textContent = state.sound ? "Sound on" : "Sound off";
        $("sound-cues").setAttribute("aria-pressed", String(state.sound));
        if (state.sound) beep();
      } catch { notify("Audio is unavailable in this browser. Visual alerts remain active."); }
    });
    $("export-exercise").addEventListener("click", exportRecord);
    window.addEventListener("offline", () => { cancelRequest(); state.browserOffline = true; render(); });
    window.addEventListener("online", () => { state.browserOffline = false; reconnect(); });
    window.addEventListener("pagehide", () => { pause(); persist(); });
    document.addEventListener("visibilitychange", () => { if (document.hidden) { pause(); if (state.snapshot) render(); } });
    setInterval(() => { if (state.playing && !state.loading) seek(state.elapsed + state.speed); }, 1000);
    try {
      const saved = TrainingStore.read(sessionStorage);
      if (saved) {
        for (const key of ["scenario", "snapshot", "elapsed", "view", "selected", "speed", "manualOffline", "heldGps", "acknowledgments"]) state[key] = saved[key];
        state.failed = true; state.restored = true;
        $("offline-drill").checked = state.manualOffline;
        $("replay-speed").value = state.speed;
        initMap(); setView(state.view);
        notify("Your exercise was restored and paused at the saved replay time.");
      }
    } catch {
      try { TrainingStore.clear(sessionStorage); } catch { /* Online exercise still works. */ }
      notify("The saved exercise could not be restored. A new briefing needs a connection.");
    }
    if (!state.manualOffline) await reconnect();
    if (!state.snapshot && !navigator.onLine) {
      $("training-error").hidden = false;
      $("training-error").textContent = "No saved exercise is available in this tab. Reconnect and use Retry connection to receive the briefing.";
      $("connection-banner").hidden = false;
      $("connection-message").textContent = "No cached briefing received.";
    }
  });
})();
