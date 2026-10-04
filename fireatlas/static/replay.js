(() => {
  "use strict";

  const $ = id => document.getElementById(id);
  const SOURCES = ["MODIS_SP", "VIIRS_SNPP_SP"];
  const SOURCE_LABELS = {MODIS_SP: "MODIS · Terra + Aqua", VIIRS_SNPP_SP: "VIIRS · Suomi-NPP"};
  const STATE_LABELS = {
    complete_export: "COMPLETE EXPORT", partial_export: "PARTIAL EXPORT", unknown: "UNKNOWN",
    documented_product_gap: "DOCUMENTED PRODUCT GAP", partial_product_gap: "PARTIAL PRODUCT GAP",
  };
  const stateKind = state => state === "complete_export" ? "available" :
    state === "partial_export" || state.includes("gap") ? "partial" : "unknown";
  const number = value => Number(value || 0).toLocaleString();
  const round = (value, places = 3) => Number.isFinite(Number(value)) ? Number(value).toFixed(places) : "—";
  const caseSelect = $("case-select");
  let catalog = null, bundle = null, contextManifest = null, selectedCase = null, frameIndex = 0;
  let selectedSource = "joint", selectedMetric = "density", selectedContext = "terrain";
  let requestedMapMode = "3d";
  let playTimer = null, mapMode = "3d", sceneView = null, sceneMap = null, heatLayer = null,
    contextLayer3d = null, outlineLayer = null, leafletMap = null, leafletBase = null,
    leafletContext = null, leafletHeat = null, leafletOutline = null, heatUrl = null;
  let visibleCells = [], visibleByCell = new Map(), contextAssets = {};
  let sdkPromise = null, requestSerial = 0;

  function requestOptions(ms = 18000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), ms);
    return {signal: controller.signal, done: () => clearTimeout(timer)};
  }

  async function getJson(url, ms = 18000) {
    const request = requestOptions(ms);
    try {
      const response = await fetch(url, {signal: request.signal, cache: "no-store"});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } finally { request.done(); }
  }

  async function fetchCatalog() {
    try { return await getJson("/api/replay/catalog", 20000); }
    catch (_) { return await getJson("./data/replay/catalog.json", 12000); }
  }

  async function fetchStaticCase(path) {
    const response = await fetch(`./data/replay/${path}`, {cache: "no-store"});
    if (!response.ok) throw new Error(`Bundled case data returned HTTP ${response.status}.`);
    if (!window.DecompressionStream) throw new Error("This browser cannot open the compressed case bundle. Use the local analysis service or a current browser.");
    const stream = response.body.pipeThrough(new DecompressionStream("gzip"));
    return JSON.parse(await new Response(stream).text());
  }

  async function fetchCase(caseId, path) {
    try { return await getJson(`/api/replay?case=${encodeURIComponent(caseId)}`, 30000); }
    catch (_) { return await fetchStaticCase(path); }
  }

  function status(node, message, kind = "unknown") {
    if (!node) return;
    node.textContent = message;
    node.classList.remove("available", "partial", "unknown", "unavailable");
    node.classList.add(kind);
  }

  function syncUrl() {
    if (!bundle) return;
    const frame = bundle.frames[frameIndex];
    const context = window.FireAtlasContext?.read() || {};
    const standard = window.FireAtlasContext?.write({
      ...context, year: Number(frame.date_utc.slice(0, 4)), month: Number(frame.date_utc.slice(5, 7)),
      day: frame.date_utc, as_of: frame.date_utc, bbox: bundle.case.bbox.join(","),
      region: "norcal", layer: selectedContext === "terrain" ? "none" : selectedContext,
    }) || "";
    const params = new URLSearchParams(standard);
    params.set("case", selectedCase);
    params.set("source", selectedSource);
    params.set("metric", selectedMetric);
    params.set("context", selectedContext);
    params.set("view", requestedMapMode);
    const query = params.toString();
    history.replaceState(null, "", `${location.pathname}${query ? `?${query}` : ""}`);
    document.querySelectorAll("[data-context-link]").forEach(link => {
      const destination = new URL(link.getAttribute("href") || "./", location.href);
      const contextParams = new URLSearchParams(standard);
      const contextQuery = contextParams.toString();
      link.href = `${destination.pathname}${contextQuery ? `?${contextQuery}` : ""}${destination.hash}`;
    });
  }

  function contextFromUrl() {
    const params = new URLSearchParams(location.search);
    const id = params.get("case");
    const source = params.get("source");
    const metric = params.get("metric");
    const context = params.get("context");
    const view = params.get("view");
    if (SOURCES.includes(source) || source === "joint") selectedSource = source;
    if (["density", "persistence", "frp"].includes(metric)) selectedMetric = metric;
    if (["terrain", "ndvi", "landcover", "burned-area"].includes(context)) selectedContext = context;
    if (view === "2d" || view === "3d") mapMode = requestedMapMode = view;
    return id;
  }

  function frameForDay(day) {
    const index = bundle.frames.findIndex(frame => frame.date_utc === day);
    return index >= 0 ? index : bundle.frames.findIndex(frame => frame.date_utc === bundle.case.selected_day);
  }

  function currentFrame() { return bundle?.frames?.[frameIndex] || null; }

  function cellKey(cell) { return `${cell.grid_x}:${cell.grid_y}`; }

  function sensorPresence(cell, source = selectedSource) {
    if (source === "MODIS_SP") return cell.modis_detections > 0;
    if (source === "VIIRS_SNPP_SP") return cell.viirs_detections > 0;
    return cell.modis_detections > 0 || cell.viirs_detections > 0;
  }

  function buildVisibleCells() {
    const frame = currentFrame();
    if (!frame) return [];
    const cells = new Map();
    const from = selectedMetric === "persistence" ? bundle.frames.slice(0, frameIndex + 1) : [frame];
    for (const day of from) {
      for (const item of day.cells) {
        if (!sensorPresence(item)) continue;
        const key = cellKey(item);
        let entry = cells.get(key);
        if (!entry) {
          entry = {...item, observed_days: 0, modis_detection_count: 0, viirs_detection_count: 0,
                   modis_frp_max_mw: null, viirs_frp_max_mw: null};
          cells.set(key, entry);
        }
        entry.observed_days += 1;
        entry.modis_detection_count += item.modis_detections;
        entry.viirs_detection_count += item.viirs_detections;
        if (item.modis_frp_max_mw != null) entry.modis_frp_max_mw = Math.max(entry.modis_frp_max_mw ?? -Infinity, item.modis_frp_max_mw);
        if (item.viirs_frp_max_mw != null) entry.viirs_frp_max_mw = Math.max(entry.viirs_frp_max_mw ?? -Infinity, item.viirs_frp_max_mw);
      }
    }
    return [...cells.values()];
  }

  function heatValue(cell) {
    if (selectedMetric === "persistence") return cell.observed_days;
    if (selectedMetric === "frp") return selectedSource === "MODIS_SP" ? cell.modis_frp_max_mw : cell.viirs_frp_max_mw;
    return 1;
  }

  function drawHeatmap() {
    const canvas = document.createElement("canvas");
    canvas.width = 760; canvas.height = 560;
    const context = canvas.getContext("2d");
    const bbox = bundle.case.bbox;
    visibleCells = buildVisibleCells();
    visibleByCell = new Map(visibleCells.map(cell => [cellKey(cell), cell]));
    const items = visibleCells.map(cell => ({cell, value: heatValue(cell)}))
      .filter(item => Number.isFinite(item.value) && item.value > 0);
    const max = Math.max(1, ...items.map(item => item.value));
    // Accumulate one scalar field, then apply the same magnitude ramp as the legend.
    // Frame-relative normalization and eligible cell values remain unchanged.
    const width=canvas.width,height=canvas.height,field=new Float32Array(width*height);
    const rx=width*.016;
    for(const {cell,value} of items){
      const x=((cell.longitude-bbox[0])/(bbox[2]-bbox[0]))*width;
      const y=((bbox[3]-cell.latitude)/(bbox[3]-bbox[1]))*height;
      const intensity=Math.max(.12,Math.min(1,value/max));
      const sigma=rx*(.72+.42*Math.sqrt(intensity))/2;
      const radius=3*sigma;
      for(let py=Math.max(0,Math.floor(y-radius));py<Math.min(height,Math.ceil(y+radius));py++){
        for(let px=Math.max(0,Math.floor(x-radius));px<Math.min(width,Math.ceil(x+radius));px++){
          const d=((px-x)**2+(py-y)**2)/(sigma*sigma);
          if(d<=9)field[py*width+px]+=intensity*Math.exp(-d/2);
        }
      }
    }
    let fieldMax=0;for(const value of field)fieldMax=Math.max(fieldMax,value);
    const pixels=context.createImageData(width,height);
    if(fieldMax>0)for(let i=0;i<field.length;i++){
      const t=field[i]/fieldMax;if(t<.008)continue;
      const color=heatColor(t);const p=i*4;
      pixels.data[p]=color[0];pixels.data[p+1]=color[1];pixels.data[p+2]=color[2];pixels.data[p+3]=Math.round(215*Math.min(1,Math.sqrt(t)));
    }
    context.putImageData(pixels,0,0);
    const url = canvas.toDataURL("image/png");
    heatUrl = url;
    if (mapMode === "2d" && leafletMap) updateLeafletHeat();
    if (sceneView && heatLayer) setArcgisHeat(canvas);
    updateHeatLegend();
  }

  function updateHeatLegend() {
    const label = $("heat-legend-label");
    if (!label) return;
    if (selectedMetric === "density") label.textContent = selectedSource === "joint" ? "Lower → higher relative cell-day concentration" : "Lower → higher relative source-specific cell-day concentration";
    else if (selectedMetric === "persistence") label.textContent = "Lower → higher local observed-day persistence";
    else label.textContent = `Lower → higher relative local ${selectedSource === "MODIS_SP" ? "MODIS" : "VIIRS"} peak FRP`;
  }

  function updateMetricControls() {
    const frp = $("metric-select").querySelector('option[value="frp"]');
    frp.disabled = selectedSource === "joint";
    if (selectedMetric === "frp" && selectedSource === "joint") {
      selectedMetric = "density";
      $("metric-select").value = selectedMetric;
    }
    const text = selectedMetric === "density"
      ? "Each occupied 1 km cell contributes once to the smoothed daily view. The heat color is relative concentration, not fire intensity."
      : selectedMetric === "persistence"
        ? "Each cell contributes its distinct observed dates through the selected day. Heat is locally smoothed and frame-relative; it is not continuous fire duration."
        : "Each source-specific cell contributes its highest reported FRP value in MW for this UTC day. Heat is locally smoothed and frame-relative; FRP is not temperature or severity.";
    $("metric-help").textContent = selectedSource === "joint" && selectedMetric !== "frp" ? text : text;
    $("heat-legend-label").textContent = selectedMetric === "frp" && selectedSource === "joint" ? "Choose one sensor to display FRP" : $("heat-legend-label").textContent;
  }

  function createSvgRing(bbox) {
    const ring = [[bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]],
                  [bbox[0], bbox[3]], [bbox[0], bbox[1]]];
    return ring;
  }

  function updateArcgisBoundary(sdk = window.replayArcgis) {
    if (!outlineLayer || !sdk || !bundle) return;
    outlineLayer.removeAll();
    const polygon = new sdk.Polygon({rings: [createSvgRing(bundle.case.bbox)], spatialReference: {wkid: 4326}});
    outlineLayer.add(new sdk.Graphic({geometry: polygon, symbol: {type: "simple-fill", color: [0, 0, 0, 0],
      outline: {type: "simple-line", color: [227, 166, 104, 225], width: 2, style: "dash"}}}));
  }

  function fitSceneToCase(duration = 0) {
    if (!sceneView || !window.replayArcgis || !bundle) return Promise.resolve();
    const polygon = new window.replayArcgis.Polygon({rings: [createSvgRing(bundle.case.bbox)],
      spatialReference: {wkid: 4326}});
    return sceneView.goTo({target: polygon, heading: 0, tilt: 55}, {duration});
  }

  function contextAsset(layer = selectedContext) {
    return contextManifest?.layers?.[selectedCase]?.[layer] || null;
  }

  function layerUrl(asset) {
    return asset?.path ? new URL(asset.path, location.href).href : null;
  }

  function setContextAvailability() {
    const supported = ["terrain", "ndvi", "landcover", "burned-area"];
    for (const button of document.querySelectorAll("[data-context-layer]")) {
      const layer = button.dataset.contextLayer;
      const asset = contextAsset(layer);
      const available = supported.includes(layer) && asset?.status === "available";
      button.disabled = !available;
      button.title = available ? asset.product || "Local NASA context layer" : asset?.reason || "No local raster for this case and date.";
      button.setAttribute("aria-pressed", String(layer === selectedContext && available));
    }
    if (contextAsset(selectedContext)?.status !== "available") selectedContext = "terrain";
    const asset = contextAsset(selectedContext);
    $("context-help").textContent = asset?.status === "available"
      ? selectedContext === "ndvi" ? "Local MOD13Q1 Version 061, 16-day NDVI composite beginning 2024-07-11. Its compositing window is not an instantaneous fire-day measurement."
        : selectedContext === "landcover" ? "Local MCD12Q1 Version 061, annual 2024 IGBP land-cover classes. It provides landscape context, not a fuel survey."
          : selectedContext === "burned-area" ? "Local MCD64A1 Version 061 July–August 2024 Burn Date. This later, MODIS-dependent layer is contextual, not independent validation."
            : "Locally prepared NASADEM hillshade. The 3D view uses satellite imagery over the streamed World Elevation surface already used by the globe."
      : "No matching local raster is available for this case. The supplied input archive has not been extended.";
    if (mapMode === "2d" && leafletMap) updateLeafletContext();
    if (sceneView && contextLayer3d) updateArcgisContext();
  }

  function updateLeafletContext() {
    if (!leafletMap) return;
    if (leafletContext) { leafletMap.removeLayer(leafletContext); leafletContext = null; }
    const asset = contextAsset();
    const url = layerUrl(asset);
    if (url && asset?.status === "available") {
      leafletContext = L.imageOverlay(url, [[bundle.case.bbox[1], bundle.case.bbox[0]], [bundle.case.bbox[3], bundle.case.bbox[2]]], {opacity: selectedContext === "terrain" ? .62 : .8, interactive: false}).addTo(leafletMap);
    }
  }

  function updateLeafletHeat() {
    if (!leafletMap || !heatUrl) return;
    if (leafletHeat) leafletMap.removeLayer(leafletHeat);
    leafletHeat = L.imageOverlay(heatUrl, [[bundle.case.bbox[1], bundle.case.bbox[0]], [bundle.case.bbox[3], bundle.case.bbox[2]]], {opacity: .92, interactive: false}).addTo(leafletMap);
    leafletHeat.bringToFront();
  }

  function initLeaflet() {
    if (leafletMap || typeof window.L === "undefined") return Boolean(leafletMap);
    if (!bundle) return false;
    const [west, south, east, north] = bundle.case.bbox;
    const container = $("replay-map");
    const map = document.createElement("div"); map.id = "replay-map-2d";
    map.setAttribute("aria-label", "Two-dimensional satellite map fallback with the same selected date heatmap");
    container.insertBefore(map, $("replay-loading"));
    leafletMap = L.map(map, {zoomControl: true, scrollWheelZoom: true, preferCanvas: true, attributionControl: true});window.FireAtlasViews?.registerMap("replay",leafletMap);
    leafletMap.setView([(south + north) / 2, (west + east) / 2], 9);
    leafletBase = L.tileLayer("https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
      maxNativeZoom: 19, maxZoom: 19, attribution: "Imagery © Esri", keepBuffer: 2,
    }).addTo(leafletMap);
    leafletOutline = L.rectangle([[south, west], [north, east]], {color: "#e4a86b", weight: 2, opacity: .9, dashArray: "8 7", fillOpacity: 0}).addTo(leafletMap);
    leafletMap.on("click", event => inspectLocation(event.latlng.lng, event.latlng.lat));
    updateLeafletContext();
    if (heatUrl) updateLeafletHeat();
    return true;
  }

  function loadArcgis() {
    if (sdkPromise) return sdkPromise;
    sdkPromise = new Promise((resolve, reject) => {
      const style = document.createElement("link");
      style.rel = "stylesheet"; style.href = "https://js.arcgis.com/4.32/esri/themes/light/main.css";
      document.head.append(style);
      const script = document.createElement("script"); script.src = "https://js.arcgis.com/4.32/";
      script.async = true;
      const timeout = setTimeout(() => reject(new Error("Terrain service took too long to start.")), 12000);
      script.onerror = () => { clearTimeout(timeout); reject(new Error("Terrain SDK could not be reached.")); };
      script.onload = () => {
        clearTimeout(timeout);
        if (typeof window.require !== "function") return reject(new Error("Terrain SDK did not initialize."));
        window.require(["esri/Map", "esri/views/SceneView", "esri/geometry/Extent", "esri/geometry/Polygon",
          "esri/Graphic", "esri/layers/GraphicsLayer", "esri/layers/MediaLayer",
          "esri/layers/support/ImageElement", "esri/layers/support/ExtentAndRotationGeoreference"],
          (Map, SceneView, Extent, Polygon, Graphic, GraphicsLayer, MediaLayer, ImageElement, ExtentAndRotationGeoreference) =>
            resolve({Map, SceneView, Extent, Polygon, Graphic, GraphicsLayer, MediaLayer, ImageElement, ExtentAndRotationGeoreference}));
      };
      document.head.append(script);
    });
    return sdkPromise;
  }

  function heatColor(intensity) {
    const stops = [[0, [255, 242, 178]], [.25, [254, 196, 79]], [.5, [252, 141, 60]], [.75, [227, 74, 51]], [1, [179, 0, 0]]];
    let low = stops[0], high = stops[stops.length - 1];
    for (let index = 1; index < stops.length; index += 1) {
      if (intensity <= stops[index][0]) { low = stops[index - 1]; high = stops[index]; break; }
    }
    const mix = Math.max(0, Math.min(1, (intensity - low[0]) / (high[0] - low[0])));
    const rgb = low[1].map((channel, index) => Math.round(channel + (high[1][index] - channel) * mix));
    return [...rgb, .14 + .68 * Math.pow(intensity, .72)];
  }

  function setArcgisHeat(_canvas, sdk = window.replayArcgis) {
    if (!sceneView || !heatLayer || !sdk || !bundle) return;
    heatLayer.removeAll();
    const candidates = visibleCells.map(cell => ({cell, value: heatValue(cell)}))
      .filter(item => Number.isFinite(item.value) && item.value > 0 && Array.isArray(item.cell.ring));
    if (!candidates.length) return;
    const maxValue = Math.max(1, ...candidates.map(item => item.value));
    const byGrid = new Map(candidates.map(item => [`${item.cell.grid_x}:${item.cell.grid_y}`, item.value / maxValue]));
    const radius = 3, sigma = 1.25;
    const scores = candidates.map(({cell}) => {
      let score = 0;
      for (let dx = -radius; dx <= radius; dx += 1) {
        for (let dy = -radius; dy <= radius; dy += 1) {
          const distanceSquared = dx * dx + dy * dy;
          if (distanceSquared > radius * radius) continue;
          const neighbor = byGrid.get(`${cell.grid_x + dx}:${cell.grid_y + dy}`);
          if (neighbor != null) score += neighbor * Math.exp(-distanceSquared / (2 * sigma * sigma));
        }
      }
      return score;
    });
    const maxScore = Math.max(1e-9, ...scores);
    candidates.forEach(({cell}, index) => {
      const polygon = new sdk.Polygon({rings: [cell.ring], spatialReference: {wkid: 4326}});
      heatLayer.add(new sdk.Graphic({geometry: polygon, symbol: {type: "simple-fill",
        color: heatColor(Math.max(.04, scores[index] / maxScore)),
        outline: {type: "simple-line", color: [0, 0, 0, 0], width: 0}}}));
    });
  }

  function webMercatorExtent(sdk, bbox) {
    const radius = 6378137, radians = Math.PI / 180;
    const projectX = longitude => radius * longitude * radians;
    const projectY = latitude => radius * Math.log(Math.tan(Math.PI / 4 + latitude * radians / 2));
    return new sdk.Extent({xmin: projectX(bbox[0]), ymin: projectY(bbox[1]),
      xmax: projectX(bbox[2]), ymax: projectY(bbox[3]), spatialReference: {wkid: 3857}});
  }

  function updateArcgisContext(sdk = window.replayArcgis) {
    if (!sceneView || !contextLayer3d || !sdk) return;
    const asset = contextAsset();
    const url = layerUrl(asset);
    contextLayer3d.visible = Boolean(url && asset?.status === "available");
    if (!contextLayer3d.visible) return;
    const extent = webMercatorExtent(sdk, bundle.case.bbox);
    contextLayer3d.source = [new sdk.ImageElement({image: url,
      georeference: new sdk.ExtentAndRotationGeoreference({extent})})];
  }

  async function initArcgis() {
    const caseAtStart = selectedCase;
    const sdk = await loadArcgis();
    window.replayArcgis = sdk;
    const bbox = bundle.case.bbox, center = [bundle.case.incident.longitude, bundle.case.incident.latitude];
    const map = new sdk.Map({basemap: "satellite", ground: "world-elevation"});
    const boundary = new sdk.GraphicsLayer({title: "Study area boundary", listMode: "hide"});
    const heat = new sdk.GraphicsLayer({title: "Smoothed observation cell-days", listMode: "hide",
      elevationInfo: {mode: "on-the-ground"}});
    const context = new sdk.MediaLayer({title: "Local NASA context", opacity: selectedContext === "terrain" ? .66 : .82, listMode: "hide"});
    map.addMany([context, heat, boundary]);
    const ring = createSvgRing(bbox);
    const polygon = new sdk.Polygon({rings: [ring], spatialReference: {wkid: 4326}});
    boundary.add(new sdk.Graphic({geometry: polygon, symbol: {type: "simple-fill", color: [0, 0, 0, 0],
      outline: {type: "simple-line", color: [227, 166, 104, 225], width: 2, style: "dash"}}}));
    const host = $("replay-map");
    let viewNode = $("replay-map-3d");
    if (!viewNode) { viewNode = document.createElement("div"); viewNode.id = "replay-map-3d"; host.insertBefore(viewNode, $("replay-loading")); }
    const view = new sdk.SceneView({container: viewNode, map, viewingMode: "local", qualityProfile: innerWidth < 701 ? "low" : "medium",
      camera: {position: {longitude: center[0], latitude: center[1], z: 55000, spatialReference: {wkid: 4326}}, heading: 0, tilt: 58},
      environment: {background: {type: "color", color: [7, 17, 21, 1]}, starsEnabled: false,
        atmosphereEnabled: false, lighting: {type: "virtual", directShadowsEnabled: false}},
      ui: {components: ["attribution", "zoom"]}, popupEnabled: false});
    await view.when();
    sceneView = view; sceneMap = map; heatLayer = heat; contextLayer3d = context; outlineLayer = boundary;
    updateArcgisBoundary(sdk);
    updateArcgisContext(sdk);
    await fitSceneToCase();
    if (heatUrl) {
      setArcgisHeat(null, sdk);
    }
    view.on("click", event => {
      const point = view.toMap(event);
      if (point) inspectLocation(point.longitude, point.latitude);
    });
    if (caseAtStart !== selectedCase) {
      await fitSceneToCase();
    }
    if (mapMode === "2d") setMapMode("2d"); else setMapMode("3d");
    $("replay-loading").hidden = true;
  }

  function setMapMode(mode) {
    mapMode = mode === "2d" ? "2d" : "3d";
    $("view-3d").setAttribute("aria-pressed", String(mapMode === "3d"));
    $("view-2d").setAttribute("aria-pressed", String(mapMode === "2d"));
    const sceneNode = $("replay-map-3d"), twoDNode = $("replay-map-2d");
    if (mapMode === "2d") {
      initLeaflet();
      if (sceneNode) sceneNode.hidden = true;
      if (twoDNode) twoDNode.hidden = false;
      if (leafletMap) setTimeout(() => leafletMap.invalidateSize({pan: false}), 30);
    } else if (sceneView && sceneNode) {
      if (twoDNode) twoDNode.hidden = true;
      sceneNode.hidden = false;
      // SceneView observes its container size when it becomes visible.
    } else {
      initLeaflet();
      if (twoDNode) twoDNode.hidden = false;
      if (sceneNode) sceneNode.hidden = true;
      mapMode = "2d";
      $("view-3d").setAttribute("aria-pressed", "false");
      $("view-2d").setAttribute("aria-pressed", "true");
    }
    syncUrl();
  }

  function statusText(state) { return STATE_LABELS[state] || "UNKNOWN"; }

  function renderTimeline() {
    const slider = $("day-slider");
    slider.max = String(Math.max(0, bundle.frames.length - 1));
    slider.value = String(frameIndex);
    slider.disabled = bundle.frames.length < 2;
    const group = $("day-buttons"); group.replaceChildren();
    bundle.frames.forEach((frame, index) => {
      const button = document.createElement("button");
      button.type = "button";
      const dateLabel = document.createElement("strong"); dateLabel.textContent = new Intl.DateTimeFormat("en", {month:"short",day:"numeric",timeZone:"UTC"}).format(new Date(`${frame.date_utc}T00:00:00Z`));
      const state = document.createElement("small");
      const complete = SOURCES.every(source => frame.products[source].state === "complete_export");
      const unknown = SOURCES.every(source => frame.products[source].state === "unknown");
      state.textContent = complete ? "Complete" : unknown ? "Unknown" : "Partial";
      button.append(dateLabel, state);
      button.title = `${frame.date_utc} UTC · ${frame.observed ? `${frame.joint_cell_days} distinct cells observed` : "no detections in local rows; coverage remains unknown unless export status says otherwise"}`;
      button.setAttribute("aria-label", `${frame.date_utc} UTC${frame.observed ? `, ${frame.joint_cell_days} distinct cell-days` : ", no imported detections"}`);
      button.setAttribute("aria-pressed", String(index === frameIndex));
      if (frame.observed) button.classList.add("has-observations");
      if (!frame.observed && SOURCES.every(source => frame.products[source].state === "unknown")) button.classList.add("unknown-day");
      button.addEventListener("click", () => selectFrame(index));
      group.append(button);
    });
  }

  function sourceCounts(frame) {
    const counts = frame.products;
    const modis = counts.MODIS_SP.detections;
    const viirs = counts.VIIRS_SNPP_SP.detections;
    return {modis, viirs, union: frame.joint_cell_days};
  }

  function renderDayStatus(frame) {
    const target = $("data-status-cards"); target.replaceChildren();
    for (const source of SOURCES) {
      const entry = frame.products[source];
      const card = document.createElement("article"); card.className = "source-status-card";
      const head = document.createElement("div"); head.className = "source-status-head";
      const title = document.createElement("strong"); title.textContent = SOURCE_LABELS[source];
      const badge = document.createElement("span"); badge.className = `status-tag ${stateKind(entry.state)}`; badge.textContent = statusText(entry.state);
      head.append(title, badge);
      const detail = document.createElement("p");
      const versions = entry.product_versions?.length ? entry.product_versions.join(", ") : "product version not recorded for this day";
      const hashes = entry.request_hashes?.length ? ` · ${entry.request_hashes.length} request provenance hash(es)` : "";
      detail.textContent = `${entry.label}. ${number(entry.detections)} eligible rows; ${number(entry.cell_days)} source cell-days. ${versions}${hashes}. Pass/cloud opportunity: unknown.`;
      card.append(head, detail); target.append(card);
    }
  }

  function visibleRecords(date) {
    return bundle.observations.filter(record => record.date === date &&
      (selectedSource === "joint" || record.source_id === selectedSource));
  }

  function renderObservationTable(frame) {
    const rows = visibleRecords(frame.date_utc);
    const target = $("observation-rows"); target.replaceChildren();
    const caption = $("observations-caption"); caption.textContent = `${frame.date_utc} UTC · ${number(rows.length)} eligible detections in selected sensor view`;
    const max = 160;
    if (!rows.length) {
      const row = document.createElement("tr"), cell = document.createElement("td");
      cell.colSpan = 5; cell.textContent = "No eligible detections were imported for this sensor and UTC date. This does not establish no fire or a clear observation.";
      row.append(cell); target.append(row);
    } else {
      for (const record of rows.slice(0, max)) {
        const row = document.createElement("tr");
        const time = document.createElement("td"); time.textContent = record.acquisition_utc.slice(11, 16);
        const source = document.createElement("td"); source.className = record.source_id === "MODIS_SP" ? "modis-text" : "viirs-text";
        source.textContent = `${record.source_id === "MODIS_SP" ? "MODIS" : "VIIRS"} · ${record.platform}`;
        const frp = document.createElement("td"); frp.textContent = record.frp_mw == null ? "—" : `${round(record.frp_mw, 2)} MW`;
        const conf = document.createElement("td"); conf.textContent = record.confidence || "not reported";
        const coords = document.createElement("td"); coords.textContent = `${round(record.latitude, 4)}, ${round(record.longitude, 4)}`;
        row.append(time, source, frp, conf, coords); target.append(row);
      }
    }
    $("observation-count-note").textContent = rows.length > max
      ? `Showing ${max} of ${number(rows.length)} records. “Export this day” includes all eligible records for the selected date and sensor view.`
      : `Source rows include acquisition time, product version, FRP, confidence, source location and source-file hash in the downloadable case bundle.`;
  }

  function renderFrame() {
    assistantSelection = null;
    const frame = currentFrame(); if (!frame) return;
    const counts = sourceCounts(frame);
    $("day-modis").textContent = number(counts.modis);
    $("day-viirs").textContent = number(counts.viirs);
    $("day-joint").textContent = number(counts.union);
    $("day-modis-status").textContent = `${frame.products.MODIS_SP.label} · ${number(frame.products.MODIS_SP.cell_days)} cells`;
    $("day-viirs-status").textContent = `${frame.products.VIIRS_SNPP_SP.label} · ${number(frame.products.VIIRS_SNPP_SP.cell_days)} cells`;
    $("selected-date").textContent = `${frame.date_utc} UTC`;
    const statuses = SOURCES.map(source => frame.products[source].state);
    const dominant = statuses.includes("documented_product_gap") || statuses.includes("partial_product_gap")
      ? statuses.find(state => state.includes("gap"))
      : statuses.includes("partial_export") ? "partial_export"
        : statuses.every(state => state === "unknown") ? "unknown"
          : statuses.every(state => state === "complete_export") ? "complete_export" : "unknown";
    status($("selected-frame-status"), statusText(dominant), stateKind(dominant));
    $("map-frame-title").textContent = `${frame.date_utc} · ${selectedMetric === "density" ? "detection concentration" : selectedMetric === "persistence" ? "observed-day persistence" : "reported FRP · MW"}`;
    const dailyLine = frame.observed
      ? `<strong>${number(counts.union)} distinct 1 km cell-days</strong> · ${number(counts.modis)} MODIS and ${number(counts.viirs)} VIIRS detections across ${number(frame.products.MODIS_SP.cell_days)} MODIS and ${number(frame.products.VIIRS_SNPP_SP.cell_days)} VIIRS source cells.`
      : `<strong>No eligible detections are in the local rows for this date.</strong> The source statuses below show whether the export itself is complete, partial, or unknown. This does not establish a fire-free day.`;
    $("daily-summary").innerHTML = `<span>${dailyLine}</span>`;
    renderTimeline(); renderDayStatus(frame); renderObservationTable(frame); drawHeatmap(); syncUrl();
    $("export-frame").disabled = false; $("export-all").disabled = false;
    $("previous-frame").disabled = frameIndex === 0;
    $("next-frame").disabled = frameIndex >= bundle.frames.length - 1;
    $("play-replay").disabled = Boolean(playTimer) || bundle.frames.length < 2;
    $("stop-replay").disabled = !playTimer;
    window.dispatchEvent(new CustomEvent('fireatlas:study-changed'));
  }

  function renderCaseSummary(entry) {
    $("case-window").textContent = `${entry.start} → ${entry.end}`;
    $("case-area").textContent = entry.title.split(" · ").slice(1).join(" · ") || "Frozen study area";
    const notes = entry.notes || [];
    $("case-notes").textContent = notes.join(" ");
    const counts = entry.summary?.sources || {};
    const det = Object.values(counts).reduce((sum, value) => sum + Number(value.detections || 0), 0);
    status($("replay-case-state"), det ? `${number(det)} DETECTIONS` : "NO LOCAL ROWS", det ? "available" : "unknown");
    caseSelect.setAttribute("aria-label", `${entry.title}. ${number(det)} eligible standard-processing detections in the frozen study window.`);
    $("replay-workspace").setAttribute("aria-busy", "false");
  }

  async function loadCase(caseId) {
    const chosen = catalog.cases.find(item => item.id === caseId) || catalog.cases[0];
    if (!chosen) throw new Error("No replay cases are in the catalogue.");
    const requestId = ++requestSerial;
    stopPlayback();
    selectedCase = chosen.id;
    caseSelect.value = selectedCase;
    bundle = null;
    $("replay-workspace").setAttribute("aria-busy", "true");
    $("replay-loading").hidden = false;
    $("replay-loading").querySelector("strong").textContent = "Preparing the replay";
    $("replay-loading").querySelector("span").textContent = `Reading the full local ${chosen.title} observation rows…`;
    try {
      const [caseBundle, assets] = await Promise.all([fetchCase(chosen.id, chosen.bundle), getJson("./replay-context/manifest.json", 8000)]);
      if (requestId !== requestSerial) return;
      if (caseBundle.schema !== "fireatlas-observation-replay-v1") throw new Error("The case bundle does not match the replay schema.");
      bundle = caseBundle; contextManifest = assets;
      const desiredDate = new URLSearchParams(location.search).get("day");
      frameIndex = frameForDay(desiredDate || chosen.selected_day);
      if (frameIndex < 0) frameIndex = 0;
      renderCaseSummary(chosen);
      setContextAvailability();
      renderFrame();
      $("replay-loading").hidden = true;
      if (sceneView) {
        updateArcgisBoundary();
        await fitSceneToCase(500);
      } else if (leafletMap) {
        const [w, s, e, n] = bundle.case.bbox; leafletMap.fitBounds([[s, w], [n, e]], {padding: [20, 20], animate: false});
      }
    } catch (error) {
      if (requestId !== requestSerial) return;
      $("replay-loading").hidden = true;
      $("replay-map-error").hidden = false;
      $("replay-map-error").textContent = `Replay data could not load: ${error.message}`;
      status($("replay-case-state"), "DATA UNAVAILABLE", "unknown");
      $("replay-workspace").setAttribute("aria-busy", "false");
      initLeaflet(); setMapMode("2d");
    }
  }

  function selectFrame(index) {
    if (!bundle) return;
    frameIndex = Math.max(0, Math.min(bundle.frames.length - 1, Number(index) || 0));
    $("day-slider").value = String(frameIndex);
    renderFrame();
  }

  function startPlayback() {
    if (!bundle || playTimer) return;
    if (frameIndex >= bundle.frames.length - 1) selectFrame(0);
    $("play-replay").disabled = true; $("stop-replay").disabled = false;
    const delay = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? 1400 : 760;
    playTimer = setInterval(() => {
      if (frameIndex >= bundle.frames.length - 1) { stopPlayback(); return; }
      selectFrame(frameIndex + 1);
    }, delay);
  }

  function stopPlayback() {
    if (playTimer) clearInterval(playTimer);
    playTimer = null;
    $("play-replay").disabled = !bundle || bundle.frames.length < 2;
    $("stop-replay").disabled = true;
  }

  function haversine(lon1, lat1, lon2, lat2) {
    const rad = Math.PI / 180, dLat = (lat2 - lat1) * rad, dLon = (lon2 - lon1) * rad;
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
    return 6371.0088 * 2 * Math.asin(Math.min(1, Math.sqrt(a)));
  }

  function inspectLocation(lon, lat) {
    if (!visibleCells.length) {
      $("map-inspector").innerHTML = "<strong>Map inspector</strong><span>No cells are available in the selected frame and sensor view. Data status remains visible below.</span>";
      return;
    }
    let nearest = null, distance = Infinity;
    for (const cell of visibleCells) {
      const next = haversine(lon, lat, cell.longitude, cell.latitude);
      if (next < distance) { nearest = cell; distance = next; }
    }
    if (!nearest || distance > 2.5) {
      $("map-inspector").innerHTML = "<strong>Map inspector</strong><span>No reported cell is within 2.5 km of that location.</span>";
      return;
    }
    assistantSelection = {cell_id: cellKey(nearest), geometry:{type:'Polygon',coordinates:[nearest.ring]}, date:currentFrame().date_utc};
    window.dispatchEvent(new CustomEvent('fireatlas:selection-changed',{detail:{label:'Selected replay cell center',point:[nearest.longitude,nearest.latitude],digits:4,date:currentFrame().date_utc}}));
    const dates = selectedMetric === "persistence" ? `${number(nearest.observed_days)} distinct observed dates` : bundle.frames[frameIndex].date_utc;
    const frp = selectedSource === "MODIS_SP" ? nearest.modis_frp_max_mw : selectedSource === "VIIRS_SNPP_SP" ? nearest.viirs_frp_max_mw : null;
    const sensorLine = `${number(nearest.modis_detection_count)} MODIS / ${number(nearest.viirs_detection_count)} VIIRS detections in view`;
    const frpLine = frp != null ? ` · selected-source FRP max ${round(frp, 2)} MW` : "";
    $("map-inspector").innerHTML = `<strong>Cell inspector</strong><span>${dates} · ${sensorLine}${frpLine} · ${round(nearest.latitude, 4)}, ${round(nearest.longitude, 4)} · ${round(distance, 2)} km from click.</span>`;
  }

  function csvEscape(value) { return `"${String(value ?? "").replaceAll('"', '""')}"`; }

  function exportCsv(all = false) {
    if (!bundle) return;
    const rows = all ? bundle.observations.filter(record => selectedSource === "joint" || record.source_id === selectedSource)
      : visibleRecords(currentFrame().date_utc);
    const header = ["case_id", "date_utc", "acquisition_utc", "source_id", "platform", "product_version",
      "longitude", "latitude", "grid_x", "grid_y", "frp_mw", "confidence", "daynight", "source_file_sha256", "source_uri"];
    const lines = [header.map(csvEscape).join(","), ...rows.map(record => [selectedCase, record.date,
      record.acquisition_utc, record.source_id, record.platform, record.product_version,
      record.longitude, record.latitude, record.grid_x, record.grid_y, record.frp_mw,
      record.confidence, record.daynight, record.source_file_sha256, record.source_uri]
      .map(csvEscape).join(","))];
    const url = URL.createObjectURL(new Blob([lines.join("\r\n")], {type: "text/csv;charset=utf-8"}));
    const link = document.createElement("a"); link.href = url;
    link.download = `fireatlas_${selectedCase}_${all ? selectedSource : currentFrame().date_utc}_${selectedSource}.csv`;
    document.body.append(link); link.click(); link.remove(); URL.revokeObjectURL(url);
  }

  function bind() {
    caseSelect.addEventListener("change", event => loadCase(event.target.value));
    $("source-select").addEventListener("change", event => {
      selectedSource = event.target.value; updateMetricControls(); renderFrame();
    });
    $("metric-select").addEventListener("change", event => {
      selectedMetric = event.target.value; updateMetricControls(); renderFrame();
    });
    document.querySelectorAll("[data-context-layer]").forEach(button => button.addEventListener("click", () => {
      if (button.disabled) return;
      selectedContext = button.dataset.contextLayer;
      setContextAvailability(); syncUrl();
    }));
    $("day-slider").addEventListener("input", event => selectFrame(event.target.value));
    $("previous-frame").addEventListener("click", () => { stopPlayback(); selectFrame(frameIndex - 1); });
    $("next-frame").addEventListener("click", () => { stopPlayback(); selectFrame(frameIndex + 1); });
    $("play-replay").addEventListener("click", startPlayback);
    $("stop-replay").addEventListener("click", stopPlayback);
    $("view-3d").addEventListener("click", () => { requestedMapMode = "3d"; setMapMode("3d"); });
    $("view-2d").addEventListener("click", () => { requestedMapMode = "2d"; setMapMode("2d"); });
    $("map-fit").addEventListener("click", () => {
      if (mapMode === "2d" && leafletMap) {
        const [w, s, e, n] = bundle.case.bbox; leafletMap.fitBounds([[s, w], [n, e]], {padding: [20, 20]});
      } else if (sceneView) fitSceneToCase(500);
    });
    $("export-frame").addEventListener("click", () => exportCsv(false));
    $("export-all").addEventListener("click", () => exportCsv(true));
  }

  async function init() {
    bind();
    status($("replay-case-state"), "LOADING", "unknown");
    try {
      const [result, assets] = await Promise.all([fetchCatalog(), getJson("./replay-context/manifest.json", 8000)]);
      catalog = result; contextManifest = assets;
      if (catalog.schema !== "fireatlas-observation-replay-catalog-v1") throw new Error("The replay catalogue schema is not supported.");
      for (const entry of catalog.cases) caseSelect.add(new Option(entry.title, entry.id));
      const requestedCase = contextFromUrl();
      const first = catalog.cases.find(item => item.id === requestedCase) || catalog.cases.find(item => item.id === "park-2024") || catalog.cases[0];
      selectedCase = first.id; caseSelect.value = selectedCase; $("source-select").value = selectedSource; $("metric-select").value = selectedMetric;
      await loadCase(selectedCase);
      updateMetricControls();
      // Show a working imagery map and local heat layer before loading the optional 3D SDK.
      // Keep the requested view in the URL so 3D upgrades automatically when the terrain service is ready.
      initLeaflet();
      setMapMode("2d");
      $("replay-loading").hidden = true;
      // Build the interactive 3D map asynchronously. The 2D view remains usable throughout startup.
      initArcgis().then(() => {
        setMapMode(requestedMapMode);
      }).catch(error => {
        console.warn("3D terrain unavailable; using satellite imagery map fallback.", error);
        $("replay-loading").hidden = true;
        initLeaflet();
        setMapMode("2d");
        const errorNode = $("replay-map-error");
        errorNode.hidden = false;
        errorNode.textContent = `3D terrain is unavailable (${error.message}). The two-dimensional satellite map and replay remain available.`;
        setTimeout(() => { errorNode.hidden = true; }, 6500);
      });
    } catch (error) {
      $("replay-loading").hidden = true;
      $("replay-map-error").hidden = false;
      $("replay-map-error").textContent = `Replay catalogue unavailable: ${error.message}`;
      status($("replay-case-state"), "DATA UNAVAILABLE", "unknown");
      $("replay-workspace").setAttribute("aria-busy", "false");
    }
  }


  let assistantSelection = null, assistantAnnotations = null;
  async function awaitTerrain(){const until=Date.now()+45000;while(!sceneView&&Date.now()<until)await new Promise(resolve=>setTimeout(resolve,250));if(!sceneView)throw Error('The terrain scene is unavailable or still loading. The flat map remains usable; choose Flat view to focus it.');}
  document.addEventListener('DOMContentLoaded', () => window.FireAtlasViews?.register('replay', {
    capabilities: ['UTC day','sensor','heat metric','landscape','terrain view','cell inspection','heat figure'],
    context: () => bundle ? {case: selectedCase.startsWith('custom') ? undefined : selectedCase, bbox: bundle.case.bbox, start: bundle.case.start, end: bundle.case.end, as_of: bundle.case.end, day: currentFrame()?.date_utc || '', source: selectedSource, metric: selectedMetric, context: selectedContext, view: mapMode, series: selectedSource === 'MODIS_SP' ? 'modis' : selectedSource === 'VIIRS_SNPP_SP' ? 'viirs-snpp' : 'joint'} : {},
    state: () => ({ready: Boolean(bundle), method: bundle?.method, displayed_cells: visibleCells.length, totals_basis: 'full backend calculation; never visible marks', map_view: mapMode}),
    selection: () => assistantSelection,
    focusPlace:async place=>{
      if(requestedMapMode==='3d'&&!sceneView)await awaitTerrain();
      if(mapMode==='3d'&&sceneView){
        const sdk=window.replayArcgis;
        if(sceneView._assistantPlace)sceneView.graphics.remove(sceneView._assistantPlace);
        const point=new sdk.Graphic({geometry:{type:'point',longitude:place.longitude,latitude:place.latitude},symbol:{type:'simple-marker',color:[169,201,144],size:12,outline:{color:'white',width:2}}});
        sceneView.graphics.add(point);sceneView._assistantPlace=point;
        await sceneView.goTo({center:[place.longitude,place.latitude],zoom:Math.min(13,Math.max(4,Math.log2(360/Math.max(.01,place.bbox[2]-place.bbox[0])))),tilt:55},{animate:false});
      }else{
        const [w,s,e,n]=place.bbox;leafletMap.fitBounds([[s,w],[n,e]],{maxZoom:14,animate:false});
        leafletMap._assistantPlace?.remove();leafletMap._assistantPlace=L.circleMarker([place.latitude,place.longitude],{color:'#fff',radius:8}).addTo(leafletMap).bindTooltip(place.title+' · geographic reference',{permanent:true}).openTooltip();
      }
      let notice=$('replay-camera-note');if(!notice){notice=document.createElement('p');notice.id='replay-camera-note';notice.className='replay-help';notice.setAttribute('role','status');$('replay-workspace').append(notice);}
      notice.textContent='Camera at '+place.title+'. Geographic reference only; study boundary, dates and observation records are unchanged.';
    },
    apply: async (cfg, action) => {
      stopPlayback();
      if (cfg.case && cfg.case !== selectedCase) await loadCase(cfg.case);
      if (!cfg.case && action?.result_id) {
        const response = await getJson(`/api/assistant/evidence/${encodeURIComponent(action.result_id)}`);
        if (response.kind !== 'evidence' || response.body.operation !== 'replay') throw Error('A custom replay requires its complete replay result. Open it in the assistant workspace.');
        bundle = response.body.payload; selectedCase = bundle.case_id;
        if (![...caseSelect.options].some(o => o.value === selectedCase)) caseSelect.add(new Option('Custom observation study', selectedCase));
        caseSelect.value = selectedCase; frameIndex = 0; renderCaseSummary({...bundle.case, summary:bundle.summary}); setContextAvailability();
      }
      if (!bundle) throw Error('Replay is still loading. Retry after the observation bundle appears.');
      if (bundle.case.start !== cfg.start || bundle.case.end !== cfg.end || JSON.stringify(bundle.case.bbox) !== JSON.stringify(cfg.bbox)) throw Error('This replay does not match the requested study. Open the result in the assistant workspace.');
      selectedSource = cfg.source; selectedMetric = cfg.metric; $('source-select').value = selectedSource; $('metric-select').value = selectedMetric; updateMetricControls();
      if (cfg.context && ['terrain','ndvi','landcover','burned-area'].includes(cfg.context)) { selectedContext = cfg.context; setContextAvailability(); }
      const day = cfg.day || cfg.start; selectFrame(Math.max(0,bundle.frames.findIndex(f => f.date_utc === day)));
      if(cfg.view){requestedMapMode=cfg.view;if(cfg.view==='3d'&&!sceneView)await awaitTerrain();setMapMode(cfg.view);}
    },
    capture: async () => { if(mapMode==='3d' && sceneView){try{const figure=await sceneView.takeScreenshot({width:1200,height:800,format:'png'});return {data:figure.dataUrl.split(',')[1],mime:'image/png',caption:`Selected terrain scene · ${currentFrame().date_utc} · ${selectedSource} · ${selectedMetric}; streamed geographic context, frame-relative heat`};}catch{}} if (!heatUrl) throw Error('The heat layer is still loading.'); return {data:heatUrl.split(',')[1],mime:'image/png',caption:`Selected heat overlay only · ${currentFrame().date_utc} · ${selectedSource} · ${selectedMetric}; basemap omitted, frame-relative smoothing`}; },
    annotate: items => { if (!leafletMap) return; assistantAnnotations?.remove(); assistantAnnotations = L.layerGroup().addTo(leafletMap); items.forEach(item => { const g=item.body.geometry; if (!g) return; const c=item.body.context; if(c.start!==bundle.case.start || JSON.stringify(c.bbox)!==JSON.stringify(bundle.case.bbox))return; const feature=L.geoJSON(g,{style:{color:'#fff',weight:3,fill:false},pointToLayer:(_,point)=>L.circleMarker(point,{color:'#fff',radius:7,fill:false})}).addTo(assistantAnnotations); feature.bindTooltip(String(item.body.text)); }); }
  }));

  document.addEventListener("DOMContentLoaded", init);
})();
