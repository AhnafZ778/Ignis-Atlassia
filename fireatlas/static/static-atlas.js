/* Static Atlas viewer backed by the compact daily observation bundles. */
(() => {
  const rootMeta = document.querySelector('meta[name="fireatlas-static-data"]');
  const section = document.getElementById("static-atlas");
  if (!rootMeta || !section) return;
  const $ = id => document.getElementById(id);
  const root = new URL(rootMeta.content, document.baseURI);
  const context = window.FireAtlasContext;
  const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  let regions = new Map(), manifest = {}, observations = [], calendar = null, map, markers, outline, layer, playback = null;
  const addDays = (year, month) => new Date(Date.UTC(year, month, 0)).getUTCDate();
  const endDate = (year, month) => `${year}-${String(month).padStart(2, "0")}-${String(addDays(year, month)).padStart(2, "0")}`;
  function compositeDate(date) {
    const selected = new Date(`${date}T00:00:00.000Z`);
    if (Number.isNaN(selected.getTime())) return date;
    const first = Date.UTC(selected.getUTCFullYear(), 0, 1);
    const elapsed = Math.floor((selected.getTime() - first) / 86400000);
    return new Date(first + Math.floor(elapsed / 16) * 16 * 86400000).toISOString().slice(0, 10);
  }
  const getJson = async path => {
    const response = await fetch(new URL(path, root));
    if (!response.ok) throw new Error(`Bundled archive unavailable (${response.status}).`);
    return response.json();
  };
  async function getGzipJson(path) {
    const response = await fetch(new URL(path, root));
    if (!response.ok) throw new Error(`Observation bundle unavailable (${response.status}).`);
    if (typeof DecompressionStream !== "function") throw new Error("This browser cannot open the compressed daily observation bundle.");
    return JSON.parse(await new Response(response.body.pipeThrough(new DecompressionStream("gzip"))).text());
  }
  function mapBase() {
    map = L.map("static-map", {scrollWheelZoom: true, attributionControl: false, minZoom: 2, maxZoom: 14});
    L.control.attribution({prefix: false, position: "bottomright"}).addTo(map);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom: 18, attribution: "© OpenStreetMap contributors"}).addTo(map);
    markers = L.layerGroup().addTo(map); outline = L.rectangle([[0, 0], [0, 0]], {color: "#ff9d63", weight: 2, dashArray: "7 6", fillOpacity: 0}).addTo(map);
  }
  function bboxValues(value) {
    const parts = String(value).split(",").map(Number);
    if (parts.length !== 4 || parts.some(v => !Number.isFinite(v)) || parts[0] < -180 || parts[2] > 180 || parts[1] < -90 || parts[3] > 90 || parts[0] >= parts[2] || parts[1] >= parts[3]) throw new Error("Enter a valid west,south,east,north bounding box.");
    return parts;
  }
  function selectedBounds() {
    const bounds = regions.get($("static-region").value)?.bbox;
    const values = bboxValues($("static-bbox").value);
    if (!bounds || values[0] < bounds[0] || values[1] < bounds[1] || values[2] > bounds[2] || values[3] > bounds[3]) throw new Error("The selected area must stay inside the region’s bundled archive boundary.");
    return values;
  }
  function renderCoverage() {
    const months = calendar?.months || [];
    const month = months.find(item => item.month === `${$("static-year").value}-${String($("static-month").value).padStart(2, "0")}`);
    if (!month) { $("static-map-coverage").textContent = "No completeness record is bundled for this month; activity remains unknown."; context.status($("static-atlas-status"), "UNKNOWN / UNAVAILABLE", "unknown"); return; }
    const unknown = Number(month.unknown_days || 0), partial = Number(month.degraded_days || month.estimated_days || 0);
    const status = unknown >= Number(month.day_count || 31) ? ["UNKNOWN / UNAVAILABLE", "unknown"] : unknown || partial ? ["PARTIAL / ESTIMATED", "partial"] : ["COMPLETE EXPORT", "available"];
    context.status($("static-atlas-status"), status[0], status[1]);
    $("static-map-coverage").textContent = `${month.observed_days ?? 0} observed days · ${month.estimated_days ?? month.degraded_days ?? 0} partial or estimated days · ${month.unknown_days ?? 0} unknown days. A complete export is not pass or cloud coverage.`;
  }
  function currentDay() { return $("static-all").getAttribute("aria-pressed") === "true" ? "" : `${$("static-year").value}-${String($("static-month").value).padStart(2, "0")}-${String($("static-day").value).padStart(2, "0")}`; }
  function renderMap() {
    if (!map) return;
    let bounds;
    try { bounds = selectedBounds(); }
    catch (error) { context.status($("static-atlas-status"), "INVALID AREA", "unavailable"); $("static-map-status").textContent = error.message; return; }
    const [west, south, east, north] = bounds;
    const stamp = currentDay();
    const available = stamp ? (observations.find(day => day.date_utc === stamp)?.observations || []) : observations.flatMap(day => day.observations || []);
    const visible = available.filter(item => {
      const lon = Number(item.raw?.longitude), lat = Number(item.raw?.latitude);
      return Number.isFinite(lon) && Number.isFinite(lat) && lon >= west && lon <= east && lat >= south && lat <= north;
    });
    markers.clearLayers();
    visible.forEach(item => {
      const raw = item.raw || {}, sensor = item.sensor || "Unknown";
      const marker = L.circleMarker([Number(raw.latitude), Number(raw.longitude)], {radius: sensor === "MODIS" ? 5 : 4, color: "#fff1df", weight: 1, fillColor: sensor === "MODIS" ? "#e8a85c" : "#67c7d0", fillOpacity: .84});
      marker.bindTooltip(`${sensor} · ${item.platform} · ${item.acquisition_utc} UTC`);
      const popup = document.createElement("div"), title = document.createElement("strong"), detail = document.createElement("p");
      title.textContent = `${sensor} · ${item.platform}`;
      detail.textContent = `${item.acquisition_utc} UTC · confidence ${raw.confidence ?? "unknown"} · FRP ${raw.frp ?? "unknown"} MW`;
      popup.append(title, detail); marker.bindPopup(popup);
      markers.addLayer(marker);
    });
    outline.setBounds([[south, west], [north, east]]);
    const truncated = stamp ? Boolean(observations.find(day => day.date_utc === stamp)?.truncated) : observations.some(day => day.truncated);
    const dayText = stamp ? `${stamp} UTC` : `${monthNames[Number($("static-month").value) - 1]} ${$("static-year").value} · month view`;
    $("static-map-status").textContent = `${visible.length.toLocaleString()} bundled detections shown · ${dayText}${truncated ? " · sample capped at 200 records per day" : ""}. Absence of points does not show that an area was continuously observed.`;
    if (truncated) $("static-map-coverage").textContent += " The map point bundle is capped at 200 sample records per day.";
  }
  function updateLayer(name) {
    document.querySelectorAll("[data-static-layer]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.staticLayer === name)));
    if (layer) { map.removeLayer(layer); layer = null; }
    if (name === "ndvi" || name === "landcover") {
      const isNdvi = name === "ndvi";
      const nativeZoom = isNdvi ? 9 : 8;
      const date = isNdvi ? compositeDate(endDate(Number($("static-year").value), Number($("static-month").value))) : `${Math.min(2024, Number($("static-year").value))}-01-01`;
      const layerName = isNdvi ? "MODIS_Terra_L3_NDVI_16Day" : "MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual";
      const url = `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${layerName}/default/${date}/GoogleMapsCompatible_Level${nativeZoom}/{z}/{y}/{x}.png`;
      layer = L.tileLayer(url, {maxNativeZoom: nativeZoom, maxZoom: 14, attribution: "NASA GIBS / MODIS", opacity: .82, keepBuffer: 3}).addTo(map);
    }
    const next = {...context.read(), layer: name, region: $("static-region").value, year: Number($("static-year").value), month: Number($("static-month").value)};
    const url = new URL(location.href); url.search = context.write(next); history.replaceState(null, "", url); context.apply(document, next);
  }
  function fillControls(ctx) {
    $("static-month").replaceChildren(...monthNames.map((name, i) => new Option(name, i + 1)));
    $("static-year").replaceChildren(...Array.from({length: manifest.calendar_end_year - manifest.calendar_start_year + 1}, (_, i) => manifest.calendar_start_year + i).map(year => new Option(String(year), year)));
    const region = regions.get(ctx.region) ? ctx.region : "norcal";
    $("static-region").value = region; $("static-year").value = String(Math.min(manifest.calendar_end_year, Math.max(manifest.calendar_start_year, ctx.year)));
    $("static-month").value = String(ctx.month);
    const [w, s, e, n] = regions.get(region).bbox;
    const requested = bboxValues(ctx.bbox);
    $("static-bbox").value = requested[0] >= w && requested[1] >= s && requested[2] <= e && requested[3] <= n ? requested.join(",") : [w, s, e, n].join(",");
    $("static-day").max = String(addDays(Number($("static-year").value), Number($("static-month").value)));
  }
  async function loadSelection() {
    const region = $("static-region").value, year = Number($("static-year").value), month = Number($("static-month").value);
    const base = `calendar/${region}/${year}.json`;
    const [observationsForYear, calendarForYear] = await Promise.all([
      getGzipJson(`observations/${region}/${year}.json.gz`), getJson(base),
    ]);
    observations = Object.entries(observationsForYear.days || {}).filter(([stamp]) => Number(stamp.slice(5, 7)) === month).map(([date_utc, value]) => ({date_utc, ...value}));
    calendar = calendarForYear;
    $("static-day").max = String(addDays(year, month));
    if (Number($("static-day").value) > addDays(year, month)) $("static-day").value = "1";
    renderCoverage(); renderMap();
    const selected = {...context.read(), region, year, month, bbox: $("static-bbox").value, as_of: endDate(year, month)};
    const url = new URL(location.href); url.search = context.write(selected); history.replaceState(null, "", url); context.apply(document, selected);
    const query = context.write(selected, {path: "/research.html"}); $("static-study-link").href = query;
    if (layer) updateLayer(document.querySelector('[data-static-layer][aria-pressed="true"]')?.dataset.staticLayer || "ndvi");
  }
  function fit() {
    try { const [west, south, east, north] = selectedBounds(); map.fitBounds([[south, west], [north, east]], {padding: [24, 24]}); }
    catch (error) { $("static-map-status").textContent = error.message; }
  }
  function play() {
    if (playback) { clearInterval(playback); playback = null; $("static-play").textContent = "▶ Play month"; return; }
    $("static-all").setAttribute("aria-pressed", "false"); $("static-play").textContent = "Ⅱ Pause";
    playback = setInterval(() => {
      let day = Number($("static-day").value) + 1;
      if (day > Number($("static-day").max)) day = 1;
      $("static-day").value = String(day); $("static-day-label").value = `${$("static-year").value}-${String($("static-month").value).padStart(2, "0")}-${String(day).padStart(2, "0")}`; renderMap();
    }, 900);
  }
  async function init() {
    section.hidden = false; mapBase();
    try {
      const [regionDocument, siteManifest] = await Promise.all([getJson("regions.json"), getJson("manifest.json")]);
      regions = new Map(regionDocument.regions.map(region => [region.id, region])); manifest = siteManifest;
      const ctx = context.read(); fillControls(ctx);
      if (ctx.day) { $("static-all").setAttribute("aria-pressed", "false"); $("static-day").value = ctx.day.slice(8); }
      const [west, south, east, north] = regions.get($("static-region").value).bbox;
      map.fitBounds([[south, west], [north, east]]);
      updateLayer(ctx.layer === "landcover" ? "landcover" : ctx.layer === "none" ? "none" : "ndvi");
      await loadSelection();
      $("static-atlas-form").addEventListener("submit", async event => { event.preventDefault(); $("static-day-label").value = "All dates"; $("static-all").setAttribute("aria-pressed", "true"); await loadSelection(); fit(); });
      $("static-region").addEventListener("change", () => { const b = regions.get($("static-region").value).bbox; $("static-bbox").value = b.join(","); });
      $("static-month").addEventListener("change", () => { $("static-day").max = String(addDays(Number($("static-year").value), Number($("static-month").value))); });
      $("static-year").addEventListener("change", () => { $("static-day").max = String(addDays(Number($("static-year").value), Number($("static-month").value))); });
      $("static-day").addEventListener("input", () => { $("static-all").setAttribute("aria-pressed", "false"); $("static-day-label").value = `${$("static-year").value}-${String($("static-month").value).padStart(2, "0")}-${String($("static-day").value).padStart(2, "0")}`; renderMap(); });
      $("static-all").addEventListener("click", () => { $("static-all").setAttribute("aria-pressed", "true"); $("static-day-label").value = "All dates"; renderMap(); });
      $("static-play").addEventListener("click", play); $("static-fit").addEventListener("click", fit);
      document.querySelectorAll("[data-static-layer]").forEach(button => button.addEventListener("click", () => updateLayer(button.dataset.staticLayer)));
      window.addEventListener("beforeunload", () => playback && clearInterval(playback));
    } catch (error) { context.status($("static-atlas-status"), "BUNDLE UNAVAILABLE", "unavailable"); $("static-map-status").textContent = error.message; }
  }
  document.addEventListener("DOMContentLoaded", init);
})();
