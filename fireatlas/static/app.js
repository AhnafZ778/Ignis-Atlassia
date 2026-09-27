const state = { year: 2015, series: "joint", bbox: "-122,39,-120,41", month: 6, day: null, data: null, demo: true };
let map, markers, aoiOutline, contextLayer, contextChoice = "none", mapRequest = 0;
const monthNames = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const shortMonths = monthNames.map(name => name.slice(0, 3).toUpperCase());
const $ = selector => document.querySelector(selector);
const jointCache = new Map();

function toast(message) {
  const el = $("#toast"); el.textContent = message; el.classList.add("visible");
  clearTimeout(toast.timer); toast.timer = setTimeout(() => el.classList.remove("visible"), 4500);
}

async function getJson(path) {
  const response = await fetch(path);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Could not load data");
  return data;
}

function showValue(value) { return value === null || value === undefined ? "—" : String(value); }

async function loadMeta() {
  const meta = await getJson(`/api/meta?demo=${state.demo ? 1 : 0}`);
  const yearSelect = $("#year"); yearSelect.replaceChildren();
  const defaultView = meta.default_view || {year:2015,month:7,bbox:[-122,39,-120,41]};
  const years = [...new Set([...meta.years, defaultView.year])].sort((a,b) => a-b);
  for (const year of years) {
    const option = document.createElement("option"); option.value = year; option.textContent = year;
    yearSelect.append(option);
  }
  state.year = defaultView.year; state.month = defaultView.month - 1; state.bbox = defaultView.bbox.join(",");
  yearSelect.value = String(state.year);
  const status = $("#dataset-status");
  status.textContent = meta.synthetic ? "Guided demo · generated example data" : meta.years.length ? "Authentic imports · view source status ↗" : "Authentic data · awaiting first import ↗";
  document.querySelectorAll("[data-demo]").forEach(button => {
    const active = button.dataset.demo === String(Number(state.demo));
    button.classList.toggle("selected", active);
    button.setAttribute("aria-pressed", String(active));
  });
  $("#mode-description").textContent = state.demo
    ? "Explore generated observations that demonstrate the complete workflow. Every example is marked synthetic."
    : meta.years.length ? "Browsing imported source records. Check the source ledger for retrieval and coverage details."
      : "NASA imports have not arrived on this server. Try the guided demo while the connection is restored.";
}

async function selectDataset(demo) {
  if (state.demo === demo && state.data) return;
  const previous = state.demo;
  state.demo = demo;
  state.data = null;
  state.comparison = null;
  try {
    await loadMeta();
    state.series = "joint"; state.day = null; contextChoice = "none";
    await loadCalendar();
    drawAoi(true);
  } catch (error) {
    state.demo = previous;
    await loadMeta(); await loadCalendar();
    toast(error.message);
  }
}

async function loadCalendar(next = {}) {
  const request = ++calendarRequest;
  const config = {...state, ...next};
  const params = new URLSearchParams({ year: config.year, series: config.series, bbox: config.bbox, demo: config.demo ? 1 : 0 });
  const data = await getJson(`/api/calendar?${params}`);
  const key = `${Number(config.demo)}:${config.year}:${config.bbox}`;
  let comparison = jointCache.get(key);
  if (!comparison) {
    comparison = config.series === "joint" ? data : await getJson(`/api/calendar?${new URLSearchParams({year:config.year,series:"joint",bbox:config.bbox,demo:config.demo ? 1 : 0})}`);
    jointCache.set(key, comparison);
  }
  if (request !== calendarRequest) return;
  Object.assign(state, config, {data, comparison});
  if (next.layer) contextChoice = next.layer;
  clearDay();
  const complete = data.monthly.some(item => item.export_window_complete);
  const banner = $("#data-alert");
  banner.style.display = data.demo_data || !complete ? "flex" : "none";
  banner.querySelector("strong").textContent = data.demo_data ? "● SYNTHETIC DEMO DATA" : "● DATA GAP";
  banner.querySelector("span").textContent = data.demo_data
    ? "This preview shows generated FIRMS-shaped records. It is not a live fire map or a safety tool."
    : "No complete source export covers this AOI, year and sensor series. Open Data sources to check the import status. Empty cells remain unknown.";
  $("#aoi-status").textContent = `Selected AOI: ${state.bbox}${complete ? "" : " · no complete export"}`;
  render();
  $("#start-tour").disabled = false;
  $("#hero-start-tour").disabled = false;
  if (state.day) await loadDay(state.day);
}

function renderStats() {
  const month = state.data.monthly[state.month];
  $("#metric-count").textContent = showValue(month.detected_cell_days);
  $("#metric-month").textContent = `${monthNames[state.month]} ${state.year} · UTC`;
  $("#metric-baseline").textContent = showValue(month.baseline_median);
  $("#baseline-years").textContent = month.baseline_years.length ? `Based on ${month.baseline_years.join(", ")}` : "Needs 3 comparable prior years";
  $("#metric-change").textContent = month.anomaly_cell_days === null ? "—" : `${month.anomaly_cell_days > 0 ? "+" : ""}${month.anomaly_cell_days}`;
  $("#metric-coverage").textContent = "Unknown";
}

function renderSourceComparison() {
  const month = state.comparison.monthly[state.month];
  const known = month.export_window_complete;
  const records = state.comparison.daily.filter(day => Number(day.date_utc.slice(5,7)) === state.month + 1);
  const modis = records.reduce((sum, day) => sum + (day.raw_pixels_by_sensor.MODIS || 0), 0);
  const viirs = records.reduce((sum, day) => sum + (day.raw_pixels_by_sensor.VIIRS || 0), 0);
  const counts = {modis, viirs, joint:month.detected_cell_days};
  const scale = Math.max(1, modis, viirs, month.detected_cell_days || 0);
  for (const name of ["modis","viirs","joint"]) {
    $(`#compare-${name}`).textContent = known ? counts[name].toLocaleString() : "—";
    $(`#compare-${name}-bar`).style.width = known ? `${Math.max(6, counts[name] / scale * 100)}%` : "12%";
  }
  $("#source-compare-note").textContent = known
    ? `${monthNames[state.month]} ${state.year} · Raw pixels retain each sensor’s detections; joint cell-days count each shared grid cell once per UTC day. These are different measures, not a sensitivity ranking.`
    : `${monthNames[state.month]} ${state.year} · A complete export for both sources is needed before comparing the raw pixels with joint cell-days.`;
  document.querySelectorAll("[data-source-target]").forEach(button => {
    button.classList.toggle("active", button.dataset.sourceTarget === state.series);
    button.setAttribute("aria-pressed", String(button.dataset.sourceTarget === state.series));
  });
}

function renderMonths() {
  const container = $("#monthly-bars"); container.replaceChildren();
  const max = Math.max(1, ...state.data.monthly.map(item => item.detected_cell_days || 0));
  state.data.monthly.forEach((item, index) => {
    const button = document.createElement("button");
    button.type = "button"; button.className = "month-row" + (index === state.month ? " chosen" : "");
    button.setAttribute("aria-label", `${monthNames[index]}: ${item.detected_cell_days === null ? "not loaded" : item.detected_cell_days + " detected cell-days"}`);
    const label = document.createElement("span"); label.className = "month-label"; label.textContent = shortMonths[index];
    const track = document.createElement("span"); track.className = "month-track";
    const fill = document.createElement("span"); fill.className = "month-fill" + (item.detected_cell_days === null ? " missing" : "");
    fill.style.width = item.detected_cell_days === null ? "100%" : `${Math.max(4, item.detected_cell_days / max * 100)}%`;
    fill.style.setProperty("--activity", item.detected_cell_days === null ? "15%" : `${Math.max(2, item.detected_cell_days / max * 100)}%`);
    track.append(fill);
    const count = document.createElement("span"); count.className = "month-count"; count.textContent = showValue(item.detected_cell_days);
    button.append(label, track, count);
    button.addEventListener("click", () => { state.month = index; state.day = null; render(); clearDay(); });
    container.append(button);
  });
}

function renderDays() {
  $("#days-title").textContent = `${monthNames[state.month]} ${state.year}`;
  const grid = $("#day-grid"); grid.replaceChildren();
  const first = new Date(Date.UTC(state.year, state.month, 1));
  const offset = (first.getUTCDay() + 6) % 7;
  for (let i = 0; i < offset; i++) {
    const blank = document.createElement("span"); blank.className = "day blank"; grid.append(blank);
  }
  const days = new Date(Date.UTC(state.year, state.month + 1, 0)).getUTCDate();
  for (let dayNumber = 1; dayNumber <= days; dayNumber++) {
    const stamp = `${state.year}-${String(state.month + 1).padStart(2,"0")}-${String(dayNumber).padStart(2,"0")}`;
    const item = state.data.daily.find(entry => entry.date_utc === stamp);
    const button = document.createElement("button"); button.type = "button";
    button.className = `day ${item.detected_cell_days === null ? "unloaded" : item.detected_cell_days > 0 ? "detected" : "clear-export"}` + (stamp === state.day ? " chosen" : "");
    button.setAttribute("aria-label", `${stamp}: ${item.detected_cell_days === null ? "export not loaded" : item.detected_cell_days + " detected cell-days"}`);
    const number = document.createElement("span"); number.textContent = dayNumber;
    const count = document.createElement("small"); count.textContent = item.detected_cell_days === null ? "·" : item.detected_cell_days > 0 ? `${item.detected_cell_days} cell` : "0";
    button.append(number, count);
    button.addEventListener("click", async () => { state.day = stamp; renderDays(); syncView(); updateContextLayer(); await loadDay(stamp); document.querySelector("#evidence-section").scrollIntoView({behavior:"smooth",block:"start"}); });
    grid.append(button);
  }
}

function clearDay() {
  ++dayRequest;
  $("#evidence-date").textContent = "SELECT A DAY";
  $("#record-count").textContent = "—";
  $("#records").replaceChildren();
  const note = document.createElement("p"); note.className = "empty-message"; note.textContent = "Choose a calendar day to see its source observations.";
  $("#records").append(note);
}

async function loadDay(stamp) {
  const request = ++dayRequest;
  const params = new URLSearchParams({date: stamp, series: state.series, bbox: state.bbox, demo: state.demo ? 1 : 0});
  try {
    const data = await getJson(`/api/observations?${params}`);
    if (request !== dayRequest) return;
    $("#evidence-date").textContent = stamp + " UTC";
    $("#record-count").textContent = `${data.observations.length}${data.truncated ? "+" : ""} RAW PIXELS`;
    const container = $("#records"); container.replaceChildren();
    if (!data.observations.length) {
      const note = document.createElement("p"); note.className = "empty-message";
      note.textContent = "No detections in the imported records for this day. Satellite pass and cloud coverage are still unknown.";
      container.append(note);
    }
    for (const item of data.observations) {
      const details = document.createElement("details"); details.className = "record";
      const summary = document.createElement("summary");
      const name = document.createElement("strong"); name.textContent = `${item.sensor} · ${item.platform}`;
      const time = document.createElement("span"); time.textContent = item.acquisition_utc.slice(11,16) + " UTC";
      const meta = document.createElement("span"); meta.textContent = `confidence ${item.confidence_raw} · FRP ${item.frp_raw || "—"}`;
      summary.append(name, time, meta);
      const pre = document.createElement("pre"); pre.textContent = JSON.stringify(item.raw, null, 2);
      details.append(summary, pre); container.append(details);
    }
  } catch (error) { toast(error.message); }
}

function renderProvenance() {
  const container = $("#provenance"); container.replaceChildren();
  const label = document.createElement("strong"); label.textContent = "SOURCE PROVENANCE"; container.append(label);
  const grid = document.createElement("p"); grid.textContent = state.data.grid; container.append(grid);
  for (const item of state.data.product_versions) {
    const line = document.createElement("p"); line.textContent = `${item.source_id} · version ${item.product_version}`; container.append(line);
  }
}

function parseAoi() {
  const parts = state.bbox.split(",").map(Number);
  if (parts.length !== 4 || parts.some(number => !Number.isFinite(number))) return null;
  return [[parts[1], parts[0]], [parts[3], parts[2]]];
}

function initMap() {
  if (typeof L === "undefined") {
    $("#map-status").textContent = "Map library unavailable. The calendar remains available.";
    return;
  }
  map = L.map("map", {scrollWheelZoom: false, worldCopyJump: true, minZoom: 2}).setView([39.8, -121.1], 8);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors", maxZoom: 18, className: "atlas-basemap",
  }).addTo(map);
  markers = L.layerGroup().addTo(map);
  map.on("moveend", () => { if (state.data) updateMap(); });
  map.on("zoomend", () => { if (state.data) updateMap(); });
  drawAoi(false);
}

function drawAoi(fit) {
  if (!map) return;
  const bounds = parseAoi(); if (!bounds) return;
  if (aoiOutline) map.removeLayer(aoiOutline);
  aoiOutline = L.rectangle(bounds, {color: "#f49c68", weight: 2, fillOpacity: 0.04, dashArray: "6 5"}).addTo(map);
  if (fit) map.fitBounds(bounds, {padding: [22, 22], maxZoom: 10});
}

function compositeDate() {
  const selected = new Date(Date.UTC(state.year, state.month, state.day ? Number(state.day.slice(8)) : 1));
  const first = Date.UTC(state.year, 0, 1);
  const elapsed = Math.floor((selected.getTime() - first) / 86400000);
  return new Date(first + Math.floor(elapsed / 16) * 16 * 86400000).toISOString().slice(0, 10);
}

function updateContextLayer() {
  if (!map) return;
  if (contextLayer) { map.removeLayer(contextLayer); contextLayer = null; }
  if (contextChoice === "ndvi" || contextChoice === "landcover") {
    const ndvi = contextChoice === "ndvi";
    const time = ndvi ? compositeDate() : `${Math.min(state.year, 2024)}-01-01`;
    const layer = ndvi ? "MODIS_Terra_L3_NDVI_16Day" : "MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual";
    contextLayer = L.tileLayer.wms("https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi", {
      layers: layer, format: "image/png", transparent: true, version: "1.1.1", time,
      attribution: "NASA GIBS / MODIS", opacity: 0.72,
    }).addTo(map);
    contextLayer.on("tileerror", () => { $("#layer-status").textContent = "NASA imagery could not load for this date or connection."; });
    $("#layer-status").textContent = ndvi
      ? `NASA MODIS NDVI 16-day composite · requested ${time} · vegetation condition only`
      : `NASA MODIS annual land cover · ${time.slice(0,4)} · broad class context`;
  } else if (contextChoice === "fwi") {
    $("#layer-status").textContent = "GFWED fire-weather data have not been imported. No weather risk is shown.";
  } else {
    $("#layer-status").textContent = "Hotspots are thermal observations, not fire perimeters.";
  }
}

function mapViewport() {
  const bounds = map.getBounds();
  const west = Math.max(-180, bounds.getWest()), east = Math.min(180, bounds.getEast());
  const south = Math.max(-85.9, bounds.getSouth()), north = Math.min(85.9, bounds.getNorth());
  if (west >= east || south >= north) return "-180,-85.9,180,85.9";
  return [west, south, east, north].map(number => number.toFixed(4)).join(",");
}

async function updateMap() {
  if (!map || !state.data) return;
  const request = ++mapRequest;
  const params = new URLSearchParams({
    year: state.year, month: state.month + 1, series: state.series,
    bbox: mapViewport(), zoom: map.getZoom(),
    demo: state.demo ? 1 : 0,
  });
  try {
    const result = await getJson(`/api/map?${params}`);
    if (request !== mapRequest) return;
    markers.clearLayers();
    for (const feature of result.features) {
      if (result.mode === "aggregates") {
        const radius = Math.max(8, Math.min(30, 8 + Math.log2(feature.count + 1) * 3));
        const marker = L.circleMarker([feature.lat, feature.lon], {radius, color: "#ffe0b5", weight: 2, fillColor: "#e9905a", fillOpacity: .85});
        const body = document.createElement("div");
        const title = document.createElement("strong"); title.textContent = `${feature.count} imported pixels`;
        const note = document.createElement("p"); note.textContent = `Grouped map sample · ${feature.sensors.join(" + ")}. Zoom in to inspect detections.`;
        body.append(title, note); marker.bindPopup(body); markers.addLayer(marker);
      } else {
        const marker = L.circleMarker([feature.lat, feature.lon], {radius: 6, color: "#ffe1c2", weight: 1.5, fillColor: feature.sensor === "MODIS" ? "#ef8055" : "#edbd64", fillOpacity: .9});
        const body = document.createElement("div");
        const title = document.createElement("strong"); title.textContent = `${feature.sensor} · ${feature.platform}`;
        const line = document.createElement("p"); line.textContent = `${feature.acquisition_utc} · native confidence ${feature.confidence_raw} · version ${feature.product_version}`;
        const action = document.createElement("button"); action.type = "button"; action.textContent = "Inspect this day";
        action.addEventListener("click", async () => {
          state.day = feature.acquisition_utc.slice(0,10);
          state.month = Number(state.day.slice(5,7)) - 1;
          render(); await loadDay(state.day);
          $("#evidence-section").scrollIntoView({behavior: "smooth"});
        });
        body.append(title, line, action); marker.bindPopup(body); markers.addLayer(marker);
      }
    }
    $("#map-status").textContent = `${result.features.length}${result.truncated ? "+" : ""} ${result.mode === "aggregates" ? "groups" : "points"} from imported ${result.month} records · ${state.series}`;
    if (result.truncated) toast("Map sample capped. Zoom in for a smaller area.");
  } catch (error) { if (request === mapRequest) $("#map-status").textContent = error.message; }
}

function render() {
  syncView(); renderStudySources();
  renderStats(); renderSourceComparison(); renderMonths(); renderDays(); renderProvenance(); drawAoi(false); updateContextLayer(); updateMap();
  const research = $("#open-research-study");
  const researchUrl = `/research.html?${new URLSearchParams({year: state.year, month: state.month + 1, bbox: state.bbox, demo: state.demo ? 1 : 0})}`;
  if (research) research.href = researchUrl;
  document.querySelectorAll('a[href^="/research.html"]:not(#open-research-study)').forEach(link => { link.href = researchUrl; });
}

document.addEventListener("DOMContentLoaded", async () => {
  initMap();
  initStudyTools();
  document.querySelectorAll("[data-demo]").forEach(button => button.addEventListener("click", () => selectDataset(button.dataset.demo === "1")));
  $("#analyze").addEventListener("click", async () => {
    try {
      const next = validateView({...viewConfig(), bbox: $("#bbox").value.trim(), year: $("#year").value, day: ""});
      await loadCalendar(next); drawAoi(true);
    } catch (error) { toast(error.message); }
  });
  $("#use-map-aoi").addEventListener("click", () => {
    if (!map) return;
    $("#bbox").value = mapViewport();
    $("#analyze").click();
  });
  document.querySelectorAll("[data-layer]").forEach(button => button.addEventListener("click", () => {
    contextChoice = button.dataset.layer;
    document.querySelectorAll("[data-layer]").forEach(other => other.classList.toggle("selected", other === button));
    updateContextLayer(); syncView();
  }));
  for (const kind of ["calendar", "observations"]) {
    $(`#export-${kind}`).addEventListener("click", () => {
      const params = new URLSearchParams({kind, year: state.year, month: state.month + 1, series: state.series, bbox: state.bbox, demo: state.demo ? 1 : 0});
      window.location.href = `/api/export?${params}`;
    });
  }
  $("#year").addEventListener("change", () => $("#analyze").click());
  document.querySelectorAll("[data-series]").forEach(button => button.addEventListener("click", async () => {
    try { await loadCalendar({series: button.dataset.series, day: null}); } catch (error) { toast(error.message); }
  }));
  document.querySelectorAll("[data-source-target]").forEach(button => button.addEventListener("click", async () => {
    try { await loadCalendar({series: button.dataset.sourceTarget, day: null}); } catch (error) { toast(error.message); }
  }));
  try {
    const initialParams = new URLSearchParams(location.search);
    state.demo = initialParams.has("demo") ? initialParams.get("demo") !== "0"
      : !(initialParams.has("year") || initialParams.has("bbox") || initialParams.has("series"));
    await loadMeta();
    let next = {};
    if (location.search) {
      try { next = validateView({...viewConfig(), ...Object.fromEntries(new URLSearchParams(location.search))}); }
      catch (error) { toast(`${error.message} Showing the default view.`); }
    }
    await loadCalendar(next); drawAoi(true);
  } catch (error) { toast(error.message); }
});
