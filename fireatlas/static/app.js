const state = { year: 2015, series: "joint", bbox: "-122,39,-120,41", month: 6, day: null, data: null, demo: true };
let map, markers, aoiOutline, contextLayer, contextChoice = "ndvi", mapRequest = 0, contextRequest = 0, briefingRequest = 0, auditRequest = 0, replayFeatures = [], replayMode = "";
let mapDay = null, mapPlayback = null, mapInputTimer = null, focusMapOnDay = false;
const monthNames = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const shortMonths = monthNames.map(name => name.slice(0, 3).toUpperCase());
const $ = selector => document.querySelector(selector);
const jointCache = new Map();
let offlineExampleNotified = false;

function toast(message) {
  const el = $("#toast"); el.textContent = message; el.classList.add("visible");
  clearTimeout(toast.timer); toast.timer = setTimeout(() => el.classList.remove("visible"), 4500);
}

async function getJson(path) {
  const response = await fetch(path);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Could not load data");
  if (response.headers.get("X-FireAtlas-Offline-Example") === "1" && !offlineExampleNotified) {
    offlineExampleNotified = true;
    toast("Offline: showing a cached synthetic example. Reconnect for current data.");
  }
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
  state.series = meta.default_series || "joint";
  yearSelect.value = String(state.year);
  const status = $("#dataset-status");
  status.textContent = meta.synthetic ? "Guided demo · generated example data" : meta.standard_pair_ready ? "NASA FIRMS MODIS + VIIRS · authentic archive ↗" : meta.available_sources?.includes("NOAA_HMS_VIIRS") ? "NOAA HMS VIIRS · authentic archive ↗" : meta.years.length ? "Authentic imports · view source status ↗" : "Authentic data · awaiting first import ↗";
  const showRealProof = !state.demo && (meta.standard_pair_ready || meta.available_sources?.includes("NOAA_HMS_VIIRS"));
  $("#demo-source-note").hidden = showRealProof;
  $("#real-source-note").hidden = !showRealProof;
  if (!showRealProof) {
    const note = $("#demo-source-note");
    note.querySelector(".orbital-kicker").textContent = state.demo ? "SYNTHETIC WORKSPACE EXAMPLE" : "HISTORICAL SENSOR PAIR";
    note.querySelector("p").textContent = state.demo
      ? "Generated MODIS + VIIRS examples below. The globe uses separate NASA NRT imports."
      : "The standard MODIS + VIIRS pair has not been imported here.";
  }
  if (showRealProof) {
    const note = $("#real-source-note");
    note.querySelector(".orbital-kicker").textContent = meta.standard_pair_ready ? "NASA FIRMS / REGIONAL ARCHIVE" : "VERIFIED ARCHIVE / NOAA";
    $("#hero-real-count").textContent = meta.standard_pair_ready
      ? ((meta.source_counts?.MODIS_SP || 0) + (meta.source_counts?.VIIRS_SNPP_SP || 0)).toLocaleString()
      : (meta.source_counts?.NOAA_HMS_VIIRS || 0).toLocaleString();
    note.querySelector(".real-source-unit").textContent = meta.standard_pair_ready ? "IMPORTED DETECTIONS" : "VIIRS FIRE POINTS";
    note.querySelector("p").textContent = meta.standard_pair_ready ? "July 2022–June 2026 regional archive. 2026 imports are partial." : "Four complete July archives. One Northern California window.";
  }
  document.querySelectorAll("[data-demo]").forEach(button => {
    const active = button.dataset.demo === String(Number(state.demo));
    button.classList.toggle("selected", active);
    button.setAttribute("aria-pressed", String(active));
  });
  document.querySelectorAll('[data-series="hms-viirs"]').forEach(button => { button.hidden = state.demo || !meta.available_sources?.includes("NOAA_HMS_VIIRS"); });
  const extraSources = {"viirs-noaa20": ["VIIRS_NOAA20_SP", "VIIRS NOAA-20 · standard"], "viirs-noaa20-nrt": ["VIIRS_NOAA20_NRT", "VIIRS NOAA-20 · near real time"], "viirs-noaa21-nrt": ["VIIRS_NOAA21_NRT", "VIIRS NOAA-21 · near real time"], "viirs-snpp-nrt": ["VIIRS_SNPP_NRT", "VIIRS S-NPP · near real time"], "modis-nrt": ["MODIS_NRT", "MODIS · near real time"]};
  const extraSelect = $("#additional-source");
  extraSelect.replaceChildren(new Option("Choose product…", ""));
  for (const [series, [source, label]] of Object.entries(extraSources)) {
    if (meta.available_sources?.includes(source)) extraSelect.add(new Option(label, series));
  }
  $("#additional-source-label").hidden = extraSelect.options.length === 1;
  const historicalSources = {modis: ["MODIS_SP"], "viirs-snpp": ["VIIRS_SNPP_SP"], joint: ["MODIS_SP", "VIIRS_SNPP_SP"]};
  for (const [series, sources] of Object.entries(historicalSources)) {
    const available = sources.every(source => meta.available_sources?.includes(source));
    const hint = available ? "Imported product available. Check month and area export completeness below."
      : "Standard product not imported. Select to inspect its missing-data state and source requirements.";
    document.querySelectorAll(`[data-series="${series}"], [data-source-target="${series}"]`).forEach(button => {
      button.hidden = false;
      button.disabled = false;
      button.title = hint;
    });
  }
  $(".series-row p").textContent = state.demo ? "Separate series preserve the sensor transition." : "Select an imported product to inspect its observations.";
  const weatherButton = $('[data-layer="fwi"]');
  weatherButton.setAttribute("aria-disabled", String(!state.demo));
  weatherButton.textContent = state.demo ? "Fire weather" : "Fire weather · unavailable";
  weatherButton.dataset.tooltip = state.demo
    ? "Synthetic weather illustration for the example study; not measured weather or a forecast."
    : "Measured fire-weather data have not been imported. A synthetic illustration is available in example mode.";
  $("#mode-description").textContent = state.demo
    ? "Generated seasonal examples and context layers. Dates and locations are synthetic; these controls apply to the study tools below."
    : meta.standard_pair_ready ? "Study authentic NASA MODIS and VIIRS standard records by year, product and region. The calendar, audit and original evidence below use the same selection."
    : meta.available_sources?.includes("NOAA_HMS_VIIRS") ? "Study imported satellite archives by year, product and region. This selection applies to the atlas, calendar and evidence below."
    : meta.years.length ? "Browsing imported source records. Check the source ledger for retrieval and coverage details."
      : "NASA imports have not arrived on this server. Try the guided demo while the connection is restored.";
}

async function selectDataset(demo) {
  if (state.demo === demo && state.data) return;
  const previous = state.demo;
  stopMapPlayback(); mapDay = null;
  state.demo = demo;
  state.data = null;
  state.comparison = null;
  try {
    await loadMeta();
    state.day = null; contextChoice = "ndvi";
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
  if (state.data && (config.year !== state.year || config.month !== state.month || config.series !== state.series || config.bbox !== state.bbox || config.demo !== state.demo)) {
    stopMapPlayback(); mapDay = null;
  }
  const params = new URLSearchParams({ year: config.year, series: config.series, bbox: config.bbox, demo: config.demo ? 1 : 0 });
  const data = await getJson(`/api/calendar?${params}`);
  const key = `${Number(config.demo)}:${config.year}:${config.bbox}`;
  let comparison = !["joint", "modis", "viirs-snpp"].includes(config.series) ? data : jointCache.get(key);
  if (!comparison && config.series !== "hms-viirs") {
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
  loadBriefing();
  loadHarmonizationAudit();
  $("#start-tour").disabled = false;
  if ($("#hero-start-tour")) $("#hero-start-tour").disabled = false;
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
  renderInsight(month);
}

function renderInsight(month) {
  const card = $("#insight-card");
  if (!card || !month) return;
  const title = $("#insight-title"), body = $("#insight-body"), source = $("#insight-source");
  const comparison = state.comparison?.monthly?.[state.month];
  const daily = state.comparison?.daily?.filter(item => Number(item.date_utc.slice(5, 7)) === state.month + 1) || [];
  const rawModis = daily.reduce((sum, item) => sum + (item.raw_pixels_by_sensor?.MODIS || 0), 0);
  const rawViirs = daily.reduce((sum, item) => sum + (item.raw_pixels_by_sensor?.VIIRS || 0), 0);
  const monthName = monthNames[state.month];
  if (month.export_window_complete && rawModis && rawViirs && comparison?.detected_cell_days) {
    const ratio = rawViirs / rawModis;
    title.textContent = `${monthName} shows why FireAtlas compares sensors.`;
    body.textContent = `VIIRS recorded ${ratio.toFixed(1)}× as many raw pixels as MODIS (${rawViirs.toLocaleString()} vs ${rawModis.toLocaleString()}). Grouping their detection centroids by UTC day and shared 1 km cell yields ${comparison.detected_cell_days.toLocaleString()} joint cell-days. This removes repeat counts in a cell; it does not equalize sensor sensitivity.`;
    source.textContent = `${state.demo ? "Synthetic teaching example" : "Imported source records"} · ${monthName} ${state.year} · same AOI and UTC window`;
  } else if (month.anomaly_cell_days !== null && month.baseline_median !== null) {
    const direction = month.anomaly_cell_days >= 0 ? "above" : "below";
    title.textContent = `${monthName} sits ${Math.abs(month.anomaly_cell_days).toLocaleString()} cell-days ${direction} its prior-year median.`;
    body.textContent = "This compares observed satellite activity, not fire risk. Open a day to trace the number back to original sensor records.";
    source.textContent = `Baseline years: ${month.baseline_years.join(", ") || "not available"} · coverage remains unknown`;
  } else {
    title.textContent = "Start with a complete observation window.";
    body.textContent = "Choose a loaded month to compare sensors and trace a finding to its original records. Gray means the source export is incomplete, not that burning was absent.";
    source.textContent = `${state.demo ? "Synthetic teaching example" : "Imported observations"} · source completeness is shown in the calendar`;
  }
  card.hidden = false;
}

function renderBriefing(data) {
  const card = $("#responder-briefing");
  if (!card || !data) return;
  const selected = data.selected_month || {};
  $("#briefing-title").textContent = data.headline || "Historical review brief";
  $("#briefing-status").textContent = data.classification === "synthetic" ? "Synthetic example" : "Historical only";
  $("#briefing-action").textContent = data.action || "Use the evidence panel for review.";
  $("#briefing-active-days").textContent = String(data.active_days_count ?? data.active_days?.length ?? "—");
  $("#briefing-unknown-days").textContent = String(data.unknown_days ?? "—");
  $("#briefing-baseline").textContent = selected.baseline_median == null ? "—" : Number(selected.baseline_median).toLocaleString();
  const dates = $("#briefing-dates"); dates.replaceChildren();
  for (const item of data.active_days || []) {
    const button = document.createElement("button"); button.type = "button";
    button.textContent = `${item.date_utc} · ${Number(item.detected_cell_days).toLocaleString()} cells`;
    button.addEventListener("click", async () => {
      state.day = item.date_utc; mapDay = Number(item.date_utc.slice(8));
      renderDays(); renderTimeline(); syncView(); updateMap();
      await loadDay(item.date_utc);
      $("#evidence-section")?.scrollIntoView({behavior:"smooth",block:"start"});
    });
    dates.append(button);
  }
  card.hidden = false;
}

function renderHarmonizationAudit(data) {
  state.audit = data;
  if (!$("#audit-status")) {
    if (data.baseline_version_status === "mixed-product-versions-across-years") {
      $("#baseline-years").textContent = `Based on ${data.baseline_years.join(", ")} · versions differ`;
    }
    return;
  }
  const pair = data.series === "joint";
  const messages = {
    "outside-standard-modis-viirs-pair": "This is one source or a different product cohort. Select Joint to assess the standard MODIS and VIIRS S-NPP pair.",
    "missing-complete-source-export": "A full-month standard export is missing for MODIS, VIIRS S-NPP, or both. Partial detections are visible, but full-month activity is unknown.",
    "mixed-product-versions": "Both exports cover this month, but multiple product versions occur within a source. Review version changes before interpreting a comparison.",
    "complete-export-with-zero-detections-in-one-source": "Both source exports are complete, but one source has zero detections in this area and month. Satellite pass and cloud coverage remain unknown.",
    "descriptive-pair-available": "Both standard-product exports cover this area and month. The shared-grid comparison is descriptive; it is not a calibrated sensitivity estimate."
  };
  $("#audit-status").textContent = `${data.data_class === "synthetic" ? "SYNTHETIC EXAMPLE · " : "IMPORTED RECORDS · "}${messages[data.status] || data.status}`;
  $("#audit-raw").textContent = Number(data.raw_pixels_total).toLocaleString();
  $("#audit-cells").textContent = data.detected_cell_days == null ? "Unknown" : Number(data.detected_cell_days).toLocaleString();
  $("#audit-overlap").textContent = pair ? Number(data.co_detected_cell_days || 0).toLocaleString() : "Not a pair";
  const container = $("#audit-sources"); container.replaceChildren();
  for (const source of data.sources) {
    const row = document.createElement("article");
    const title = document.createElement("strong"); title.textContent = source.source_id.replaceAll("_", " ");
    const details = document.createElement("span");
    details.textContent = `${source.processing_level} · ${Number(source.raw_pixels).toLocaleString()} raw pixels · ${Number(source.detected_cell_days).toLocaleString()} source cell-days · ${source.full_month_export ? "complete export" : "incomplete export"} · version ${source.product_versions.join(", ") || "unknown"}`;
    row.append(title, details); container.append(row);
  }
  const versionReading = {
    "mixed-product-versions-across-years": "Baseline caution: one or more source product versions differ across the selected month and its prior years. The cell-day difference is descriptive, not a calibrated change in burning.",
    "same-observed-product-versions": "The selected month and qualifying baseline months use the same observed product versions. Sensor availability and sensitivity still need separate checks.",
    "unknown-where-source-has-no-detections": "Baseline version check is incomplete because a source has no detections in one or more prior months.",
    "no-qualifying-baseline-years": "No qualifying prior-year baseline is available for this selection."
  };
  $("#audit-baseline-versions").textContent = versionReading[data.baseline_version_status] || "Baseline product-version comparison unavailable.";
  if (data.baseline_version_status === "mixed-product-versions-across-years") {
    $("#baseline-years").textContent = `Based on ${data.baseline_years.join(", ")} · versions differ`;
  }
  $("#download-audit").disabled = false;
}

async function loadHarmonizationAudit() {
  const request = ++auditRequest;
  state.audit = null;
  if ($("#download-audit")) $("#download-audit").disabled = true;
  if ($("#audit-status")) $("#audit-status").textContent = "Checking the selected month and source exports…";
  if ($("#audit-baseline-versions")) $("#audit-baseline-versions").textContent = "Checking baseline product versions…";
  const params = new URLSearchParams({year: state.year, month: state.month + 1, series: state.series, bbox: state.bbox, demo: state.demo ? 1 : 0});
  try {
    const data = await getJson(`/api/harmonization?${params}`);
    if (request === auditRequest) renderHarmonizationAudit(data);
  } catch (error) {
    if (request === auditRequest && $("#audit-status")) $("#audit-status").textContent = `Method audit unavailable: ${error.message}`;
  }
}

async function loadBriefing() {
  const request = ++briefingRequest;
  const params = new URLSearchParams({year: state.year, month: state.month + 1, series: state.series, bbox: state.bbox, demo: state.demo ? 1 : 0});
  try {
    const data = await getJson(`/api/briefing?${params}`);
    if (request === briefingRequest) renderBriefing(data);
  } catch (error) {
    if (request === briefingRequest) {
      const card = $("#responder-briefing");
      if (card) { card.hidden = false; $("#briefing-title").textContent = "Historical brief unavailable"; $("#briefing-action").textContent = error.message; }
    }
  }
}

function renderSourceComparison() {
  const isHms = !["joint", "modis", "viirs-snpp"].includes(state.series);
  $("#additional-source").value = state.series;
  const archive = state.series === "hms-viirs";
  const summary = $("#hms-source-compare");
  summary.querySelector("div > span").textContent = archive ? "NOAA HISTORICAL FIRE ARCHIVE" : "NASA FIRMS · IMPORTED PRODUCT";
  summary.querySelector("h3").textContent = archive ? "Real VIIRS detections. A visible fire season." : state.series.toUpperCase().replaceAll("-", " ");
  summary.querySelector("p").textContent = archive ? "NOAA HMS points from Suomi NPP, NOAA-20 and NOAA-21. Every day in a complete month is checked before the calendar is marked loaded." : "This product is displayed separately from the historical MODIS / Suomi NPP comparison. Imported detections remain visible when a month's export is partial.";
  $("#hms-raw").nextElementSibling.textContent = "IMPORTED DETECTIONS";
  $("#hms-source-compare").hidden = !isHms;
  $("#firms-source-compare").hidden = isHms;
  $("#source-compare-note").hidden = isHms;
  const reading = $("#sensor-study-reading");
  if (isHms) {
    const month = state.data.monthly[state.month];
    const records = state.data.daily.filter(day => Number(day.date_utc.slice(5,7)) === state.month + 1);
    const pixels = records.reduce((sum, day) => sum + (Object.values(day.raw_pixels_by_sensor).reduce((a,b) => a+b, 0)), 0);
    $("#hms-raw").textContent = pixels.toLocaleString();
    $("#hms-cells").textContent = month.detected_cell_days === null ? "—" : month.detected_cell_days.toLocaleString();
    $("#hms-period").textContent = `${monthNames[state.month]} ${state.year} · ${month.export_window_complete ? "complete export" : "partial / no complete export"}`;
    if (reading) reading.textContent = "This view is the NOAA HMS VIIRS archive, so it cannot be compared pixel-for-pixel with MODIS here. Select Joint, MODIS, or VIIRS S-NPP to compare the matched NASA source products.";
    return;
  }
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
  const sensorTips = {
    modis: `MODIS (Terra & Aqua) · 1 km thermal pixels. ${known ? modis.toLocaleString() + " raw pixels this month." : "Complete export needed."} Click to view MODIS only.`,
    "viirs-snpp": `VIIRS (Suomi NPP) · 375 m pixels, detects smaller hotspots. ${known ? viirs.toLocaleString() + " raw pixels this month." : "Complete export needed."} Click to view VIIRS only.`,
    joint: `Joint view · Both sensors on a shared 1 km grid. Each cell counted once per UTC day. ${known ? (month.detected_cell_days || 0).toLocaleString() + " cell-days." : "Complete export needed."} Not a sensitivity ranking.`
  };
  $("#source-compare-note").textContent = known
    ? `${monthNames[state.month]} ${state.year} · Raw pixels retain each sensor’s detections; joint cell-days count each shared grid cell once per UTC day. These are different measures, not a sensitivity ranking.`
    : `${monthNames[state.month]} ${state.year} · A complete export for both sources is needed before comparing the raw pixels with joint cell-days.`;
  if (reading) {
    reading.textContent = known && modis && viirs
      ? `This selection contains ${modis.toLocaleString()} MODIS and ${viirs.toLocaleString()} VIIRS raw pixels. VIIRS is ${(viirs / modis).toFixed(1)}× higher in raw detections here; pixel scale and overpasses differ, so this is not a ratio of fires. The joint grouping yields ${month.detected_cell_days?.toLocaleString() || "—"} shared 1 km cell-days, without calibrating sensor sensitivity.`
      : "The source export is incomplete, so the sensor counts cannot support a like-for-like interpretation yet. Gray or missing days mean unknown coverage, not zero fire.";
  }
  document.querySelectorAll("[data-source-target]").forEach(button => {
    const key = button.dataset.sourceTarget;
    if (sensorTips[key]) button.title = sensorTips[key];
    button.classList.toggle("active", key === state.series);
    button.setAttribute("aria-pressed", String(key === state.series));
  });
}

function selectCalendarMonth(index) {
  if (index < 0 || index > 11) return;
  stopMapPlayback(); mapDay = null; state.month = index; state.day = null;
  render(); clearDay(); loadBriefing(); loadHarmonizationAudit();
}

function renderMonths() {
  const container = $("#monthly-bars"); container.replaceChildren();
  const completeMonths = state.data.monthly.filter(item => item.export_window_complete);
  $("#month-completeness").textContent = `${completeMonths.length} / 12 complete month exports · ${state.year}`;
  const max = Math.max(1, ...state.data.monthly.map(item => item.detected_cell_days || 0));
  state.data.monthly.forEach((item, index) => {
    const button = document.createElement("button");
    const partial = item.detected_cell_days === null && item.partial_import_detected_cell_days > 0;
    const isPeak = item.detected_cell_days !== null && item.detected_cell_days > 0 && item.detected_cell_days === max;
    button.type = "button"; button.className = "month-row" + (index === state.month ? " chosen" : "") + (isPeak ? " peak" : "");
    button.setAttribute("aria-pressed", String(index === state.month));
    const tooltipText = item.detected_cell_days === null
      ? `${monthNames[index]} ${state.year}: ${partial ? "At least " + item.partial_import_detected_cell_days.toLocaleString() + " imported cell-days; partial export." : "Source export not loaded; activity unknown."}`
      : `${monthNames[index]} ${state.year}: ${item.detected_cell_days.toLocaleString()} detected cell-days${isPeak ? " · highest among complete loaded months" : ""}. Open the daily calendar.`;
    button.setAttribute("aria-label", tooltipText); button.title = tooltipText;
    const label = document.createElement("span"); label.className = "month-label"; label.textContent = shortMonths[index];
    const track = document.createElement("span"); track.className = "month-track";
    const fill = document.createElement("span"); fill.className = "month-fill" + (item.detected_cell_days === null ? " missing" : "");
    fill.style.width = item.detected_cell_days === null ? "100%" : `${item.detected_cell_days / max * 100}%`;
    fill.style.setProperty("--activity", item.detected_cell_days === null ? "100%" : `${item.detected_cell_days / max * 100}%`);
    track.append(fill);
    const count = document.createElement("span"); count.className = "month-count";
    count.textContent = item.detected_cell_days === null ? partial ? `≥${item.partial_import_detected_cell_days.toLocaleString()}` : "—" : item.detected_cell_days.toLocaleString();
    button.append(label, track, count);
    button.addEventListener("click", () => selectCalendarMonth(index)); container.append(button);
  });
}

function calendarHeat(value, maximum) {
  const t = Math.log1p(value) / Math.log1p(Math.max(1, maximum));
  const low = [35, 58, 65], high = [255, 177, 99];
  return {color: `rgb(${low.map((channel, i) => Math.round(channel + (high[i] - channel) * t)).join(",")})`, dark: t > .58};
}

function renderDays() {
  const data = state.data, month = data.monthly[state.month];
  const snppGapMonth = !state.demo && state.year === 2024 && state.month === 6 && data.sources.includes("VIIRS_SNPP_SP");
  const days = new Date(Date.UTC(state.year, state.month + 1, 0)).getUTCDate();
  const rows = data.daily.filter(row => Number(row.date_utc.slice(5, 7)) === state.month + 1);
  const byDate = new Map(rows.map(row => [row.date_utc, row]));
  const positive = rows.filter(row => row.detected_cell_days > 0);
  const maximum = Math.max(0, ...positive.map(row => row.detected_cell_days));
  const scaleMaximum = Math.max(0, ...data.daily.map(row => row.detected_cell_days || 0));
  $("#days-title").textContent = `${monthNames[state.month]} ${state.year}`;
  $("#calendar-prev").disabled = state.month === 0; $("#calendar-next").disabled = state.month === 11;
  $("#calendar-context").textContent = `${state.demo || data.demo_data ? "SYNTHETIC EXAMPLE" : "IMPORTED OBSERVATIONS"} · ${data.sources.join(" + ").replaceAll("_", " ")} · AOI ${data.bbox.map((value, i) => ["W", "S", "E", "N"][i] + " " + value + "°").join(", ")} · UTC`;
  if ($("#calendar-grid-version")) $("#calendar-grid-version").textContent = `Method: ${data.grid}`;
  const peakDates = positive.filter(row => row.detected_cell_days === maximum).map(row => Number(row.date_utc.slice(8)));
  $("#calendar-month-summary").textContent = month.export_window_complete
    ? `${days}/${days} export days complete · ${positive.length} days with detections${maximum ? ` · Peak ${maximum.toLocaleString()} cells on ${(peakDates.length > 3 ? peakDates.length + " dates" : peakDates.map(day => day + " " + shortMonths[state.month]).join(", "))}` : ""}`
    : `${month.partial_import_detected_cell_days > 0 ? "Partial records available" : "No complete export loaded"} · Full-month activity unknown`;
  if (snppGapMonth) $("#calendar-month-summary").textContent += " · NASA S-NPP processing gap 24–28 Jul; pass/cloud unknown";
  const grid = $("#day-grid"); grid.replaceChildren();
  const offset = (new Date(Date.UTC(state.year, state.month, 1)).getUTCDay() + 6) % 7;
  for (let i = 0; i < offset; i++) {const blank = document.createElement("span"); blank.className = "day blank"; blank.setAttribute("aria-hidden", "true"); grid.append(blank);}
  for (let dayNumber = 1; dayNumber <= days; dayNumber++) {
    const stamp = `${state.year}-${String(state.month + 1).padStart(2,"0")}-${String(dayNumber).padStart(2,"0")}`;
    const item = byDate.get(stamp) || {detected_cell_days: null, partial_import_detected_cell_days: 0, raw_pixels_by_sensor: {}};
    const value = item.detected_cell_days, partial = value === null && item.partial_import_detected_cell_days > 0;
    const countValue = value ?? (partial ? item.partial_import_detected_cell_days : null);
    const peak = value !== null && value === maximum && maximum > 0;
    const button = document.createElement("button"); button.type = "button";
    button.dataset.date = stamp;
    button.className = `day ${partial ? "partial-export" : value === null ? "unloaded" : value > 0 ? "detected" : "clear-export"}${stamp === state.day ? " chosen" : ""}${peak ? " day-peak" : ""}`;
    const snppGapDay = snppGapMonth && dayNumber >= 24 && dayNumber <= 28;
    if (snppGapDay) button.classList.add("source-gap");
    button.tabIndex = stamp === (state.day || `${state.year}-${String(state.month + 1).padStart(2,"0")}-01`) ? 0 : -1;
    button.setAttribute("aria-pressed", String(stamp === state.day));
    const raw = Object.entries(item.raw_pixels_by_sensor || {}).map(([sensor, count]) => `${sensor}: ${count.toLocaleString()} raw pixels`).join("; ");
    const status = partial ? `At least ${countValue.toLocaleString()} detected cells, partial export` : value === null ? "Activity unknown, source export incomplete" : `${value.toLocaleString()} detected ${value === 1 ? "cell" : "cells"}, complete export`;
    button.setAttribute("aria-label", `${stamp} UTC · ${status}${raw ? " · " + raw : ""}${peak ? " · Highest count this month" : ""}${snppGapDay ? " · NASA S-NPP processing gap; observation coverage unknown" : ""}. Inspect source records.`);
    button.title = button.getAttribute("aria-label");
    if (value > 0) {const heat = calendarHeat(value, scaleMaximum); button.style.setProperty("--day-heat", heat.color); button.classList.toggle("dark-ink", heat.dark);}
    const number = document.createElement("span"); number.className = "day-number"; number.textContent = dayNumber;
    const count = document.createElement("strong"); count.className = "day-count"; count.textContent = countValue === null ? "—" : `${partial ? "≥" : ""}${countValue.toLocaleString()}`;
    button.style.setProperty("--count-size", `${Math.max(10, 18 - Math.max(0, count.textContent.length - 3) * 1.5)}px`);
    const unit = document.createElement("small"); unit.className = "day-unit"; unit.textContent = value === null ? partial ? "partial" : "unknown" : value === 1 ? "cell" : "cells";
    button.append(number, count, unit);
    button.addEventListener("keydown", event => {
      const steps = {ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7};
      let target = steps[event.key] === undefined ? null : dayNumber + steps[event.key];
      if (event.key === "Home") target = Math.max(1, dayNumber - (offset + dayNumber - 1) % 7);
      if (event.key === "End") target = Math.min(days, dayNumber + 6 - (offset + dayNumber - 1) % 7);
      if (target === null) return;
      event.preventDefault();
      const next = grid.querySelector(`[data-date$="-${String(Math.max(1, Math.min(days, target))).padStart(2,"0")}"]`);
      if (next) {grid.querySelectorAll("button").forEach(node => node.tabIndex = -1); next.tabIndex = 0; next.focus();}
    });
    button.addEventListener("click", async () => {
      state.day = stamp;
      mapDay = dayNumber;
      renderDays(); renderTimeline(); syncView(); updateContextLayer(); updateMap();
      await loadDay(stamp);
      if (state.day === stamp) document.querySelector("#evidence-section")?.scrollIntoView({behavior:"smooth",block:"start"});
    });
    grid.append(button);
  }
  const scale = $("#calendar-scale"); scale.replaceChildren();
  if (maximum) {
    const label = document.createElement("span"); label.textContent = "Cells per day · year-wide logarithmic scale"; scale.append(label);
    const values = [...new Set([1, ...Array.from({length: 4}, (_, i) => Math.round(Math.expm1(Math.log1p(scaleMaximum) * (i + 1) / 4)))])].filter(value => value > 0);
    for (const value of values) {const tick = document.createElement("span"), swatch = document.createElement("i"); swatch.style.background = calendarHeat(value, scaleMaximum).color; tick.append(swatch, document.createTextNode(value.toLocaleString())); scale.append(tick);}
  }
  const selected = state.day && byDate.get(state.day), summary = $("#calendar-day-summary");
  summary.hidden = !selected;
  if (selected) {
    const count = selected.detected_cell_days;
    const sensors = Object.entries(selected.raw_pixels_by_sensor || {}).map(([sensor, n]) => `${sensor}: ${n.toLocaleString()} pixels`).join(" · ");
    summary.textContent = `${state.day} UTC · ${count === null ? selected.partial_import_detected_cell_days > 0 ? "≥" + selected.partial_import_detected_cell_days.toLocaleString() + " cells (partial export)" : "Unknown activity (incomplete export)" : count.toLocaleString() + ` distinct detected ${count === 1 ? "cell" : "cells"}`}${sensors ? " · " + sensors : ""}`;
    if (snppGapMonth && Number(state.day.slice(8)) >= 24 && Number(state.day.slice(8)) <= 28) summary.textContent += " · NASA S-NPP processing gap; pass/cloud unknown";
    const link = document.createElement("a");
    link.href = methodUrl(); link.textContent = "Inspect this day’s source records ↗";
    link.className = "calendar-evidence-link"; summary.append(link);
  }
}

function clearDay() {
  ++dayRequest;
  if (!$("#evidence-section")) return;
  $("#evidence-section").hidden = true;
  $("#evidence-date").textContent = "SELECT A DAY";
  $("#record-count").textContent = "—";
  $("#records").replaceChildren();
  const note = document.createElement("p"); note.className = "empty-message"; note.textContent = "Choose a calendar day to see its source observations.";
  $("#records").append(note);
}

async function loadDay(stamp) {
  if (!$("#evidence-section")) return;
  const request = ++dayRequest;
  const params = new URLSearchParams({date: stamp, series: state.series, bbox: state.bbox, demo: state.demo ? 1 : 0});
  try {
    const data = await getJson(`/api/observations?${params}`);
    if (request !== dayRequest) return;
    $("#evidence-section").hidden = false;
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
      const frp = item.frp_raw ?? null;
      const meta = document.createElement("span"); meta.textContent = `confidence ${item.confidence_raw} · FRP ${frp === null || frp === "" ? "unknown" : `${frp} MW`}`;
      summary.dataset.tooltip = "Confidence uses the source product's native scale. FRP is observed fire radiative power in megawatts, not burned area or fire severity.";
      summary.append(name, time, meta);
      const pre = document.createElement("pre"); pre.textContent = JSON.stringify(item.raw, null, 2);
      details.append(summary, pre); container.append(details);
    }
  } catch (error) { toast(error.message); }
}

function renderProvenance() {
  const container = $("#provenance");
  if (!container || !state.data) return;
  container.replaceChildren();
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
  map = L.map("map", {scrollWheelZoom: false, worldCopyJump: true, preferCanvas: true, minZoom: 0, zoomSnap: 0.25}).setView([39.8, -121.1], 8);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors", maxZoom: 18, className: "atlas-basemap",
  }).addTo(map);
  markers = L.layerGroup().addTo(map);
  map.on("moveend", () => { if (state.data) updateMap(); });
  map.on("zoomend moveend", renderReplayAnnotations);
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

function renderMapLegend() {
  const legend = $("#map-legend");
  if (!legend) return;
  const context = {
    none: {title: "No context overlay", range: "Only satellite detections", note: "Hotspots are dated thermal observations. They do not show a fire perimeter."},
    ndvi: {title: "Vegetation condition (NDVI)", range: "lower signal → higher signal", note: state.demo ? "Synthetic monthly illustration; it is not measured fuel moisture or fire risk." : "NASA MODIS 16-day composite; vegetation context only."},
    landcover: {title: "Broad land-cover class", range: "forest · shrubland · grassland · cropland", note: state.demo ? "Synthetic class illustration for the Northern California showcase." : "NASA MODIS annual class context; it does not identify current fuels."},
    fwi: {title: "Fire-weather index illustration", range: "lower index → higher index", note: state.demo ? "Synthetic monthly illustration in arbitrary units; it is not measured weather or a forecast." : "Measured fire-weather data have not been imported. No weather risk is shown."},
  }[contextChoice] || {title: "No context overlay", range: "Only satellite detections", note: "Hotspots are dated thermal observations. They do not show a fire perimeter."};
  const badge = $("#map-legend-badge");
  badge.textContent = state.demo ? "SYNTHETIC" : "IMPORTED";
  const title = $("#map-legend-context-title");
  title.textContent = context.title;
  const swatch = $("#map-legend-context-swatch");
  swatch.className = `map-legend-swatch ${contextChoice}`;
  const scale = $("#map-legend-context-range");
  scale.className = `map-legend-context-range ${contextChoice}`;
  scale.querySelector("span").textContent = context.range;
  const observationNote = $("#map-legend-observation-note");
  if (observationNote) observationNote.textContent = state.demo
    ? "Synthetic FIRMS-shaped example points; positions are illustrative."
    : "Imported NASA FIRMS standard-product detection records.";
  $("#map-legend-note").textContent = context.note;
}

async function updateContextLayer() {
  const request = ++contextRequest;
  if (!map) return;
  renderMapLegend();
  if (contextLayer) { map.removeLayer(contextLayer); contextLayer = null; }
  if (state.demo && contextChoice !== "none") {
    if (state.year < 2023 || state.year > 2026) {
      $("#layer-status").textContent = "Synthetic context is available only for the 2023–2026 showcase years; the selected 2015 study remains satellite evidence only.";
      return;
    }
    $("#layer-status").textContent = "Loading synthetic context…";
    try {
      const fixture = await getJson(`/api/context?${new URLSearchParams({demo:1,year:state.year,month:state.month+1,bbox:state.bbox,layer:contextChoice})}`);
      if (request !== contextRequest) return;
      contextLayer = L.geoJSON(fixture, {
        style: feature => ({color:feature.properties.color,weight:.5,fillColor:feature.properties.color,fillOpacity:.4}),
        onEachFeature: (feature, layer) => {
          const label = document.createElement("span");
          label.textContent = `SYNTHETIC · ${feature.properties.label} · ${fixture.year}-${String(fixture.month).padStart(2,"0")} monthly illustration`;
          layer.bindTooltip(label);
        }
      }).addTo(map);
      contextLayer.bringToBack();
      $("#layer-status").textContent = fixture.features.length ? fixture.note : "No synthetic context outside the Northern California showcase AOI.";
    } catch (error) {
      if (request === contextRequest) $("#layer-status").textContent = `Context unavailable: ${error.message}`;
    }
    return;
  }
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

function stopMapPlayback() {
  if (mapPlayback) clearTimeout(mapPlayback);
  mapPlayback = null;
  const button = $("#map-play");
  if (button) button.textContent = "▶ Play month";
}

function updateReplayGuide() {
  const guide = $("#map-replay-guide");
  if (!guide) return;
  const day = mapDay || 1;
  const total = Number($("#map-day")?.max || 31);
  guide.hidden = false;
  guide.dataset.phase = day <= 1 ? "map" : day >= total ? "bars" : "timeline";
  const targets = {
    map: $("#map"),
    timeline: $("#map-day"),
    bars: $("#map-timeline-bars"),
  };
  Object.entries(targets).forEach(([name, node]) => node?.classList.toggle("replay-guide-target", guide.dataset.phase === name));
}

function renderReplayAnnotations(features = replayFeatures, mode = replayMode) {
  const layer = $("#map-replay-annotations");
  const guide = $("#map-replay-guide");
  if (!layer || !map || !guide || guide.hidden) return;
  layer.replaceChildren();
  if (!features?.length) { layer.hidden = true; return; }
  layer.hidden = false;
  const ranked = [...features].sort((a, b) => (b.count ?? 1) - (a.count ?? 1)).slice(0, 3);
  const seen = new Set();
  ranked.forEach((feature, index) => {
    const point = map.latLngToContainerPoint([feature.lat, feature.lon]);
    const box = document.createElement("span");
    box.className = "replay-map-box";
    box.style.left = `${point.x}px`; box.style.top = `${point.y}px`;
    const card = document.createElement("span");
    card.className = "replay-map-label";
    card.style.left = `${Math.min(Math.max(point.x + 24, 12), Math.max(12, map.getSize().x - 242))}px`;
    card.style.top = `${Math.max(10, point.y - 42 - index * 4)}px`;
    const nearby = index > 0 && ranked.slice(0, index).some(previous => Math.hypot((feature.lat - previous.lat) * 111, (feature.lon - previous.lon) * 90) < 35);
    let title, detail;
    if (mode === "aggregates") {
      title = index === 0 ? "Largest observed cluster" : `Observed cluster ${index + 1}`;
      detail = `${feature.count} satellite pixels share this grid cell. ${feature.count > 2 ? "A concentrated group suggests sustained or intense thermal activity." : "This is a small localized heat signal."} It is not a mapped fire boundary.`;
    } else if (nearby) {
      title = "Clustered heat signals";
      detail = `${feature.sensor || "Satellite"} is close to another observation. Several nearby signals suggest concentrated thermal activity, but they do not define the fire's size or perimeter.`;
    } else {
      title = index === 0 ? "Satellite heat observation" : `Separate heat observation ${index + 1}`;
      detail = `${feature.sensor || "Satellite"} detected thermal energy at this place and time. It is an observation signal, not a confirmed fire perimeter.`;
    }
    const messageKey = `${title}|${detail}`;
    if (seen.has(messageKey)) return;
    seen.add(messageKey);
    card.innerHTML = `<b>${title}</b><span>${detail}</span>`;
    layer.append(box, card);
  });
}

function renderTimeline() {
  if (!state.data) return;
  const month = state.month + 1;
  const days = new Date(Date.UTC(state.year, month, 0)).getUTCDate();
  const entries = state.data.daily.filter(item => Number(item.date_utc.slice(5, 7)) === month);
  const counts = entries.map(item => item.detected_cell_days ?? item.partial_import_detected_cell_days ?? 0);
  const max = Math.max(1, ...counts);
  const peakDay = counts.reduce((best, c, i) => c > (counts[best] || 0) ? i : best, 0);
  const bars = $("#map-timeline-bars"); bars.replaceChildren();
  counts.forEach((count, index) => {
    const button = document.createElement("button"); button.type = "button";
    const isPeak = count > 0 && index === peakDay;
    button.className = "map-timeline-bar" + (mapDay === index + 1 ? " active" : "") + (isPeak ? " peak" : "");
    const partial = !entries[index]?.export_window_complete;
    const label = partial ? (count ? `${count} imported cell-days · partial export` : "No imported detections · coverage unknown") : `${count} detected cell-days`;
    button.setAttribute("aria-label", `${monthNames[state.month]} ${index + 1}, ${state.year}: ${label}${isPeak ? " · PEAK DAY" : ""}`);
    button.title = `Day ${index + 1} · ${label}${isPeak ? " · Peak" : ""}`;
    const fill = document.createElement("span"); fill.style.height = `${Math.max(5, count / max * 100)}%`;
    button.append(fill); button.addEventListener("click", () => { stopMapPlayback(); setMapDay(index + 1, true); });
    bars.append(button);
  });
  const dateText = mapDay ? `Day ${mapDay} of ${days} · ${monthNames[state.month]} ${mapDay}, ${state.year}` : `${monthNames[state.month]} ${state.year} · all ${days} days`;
  $("#map-timeline-title").textContent = dateText;
  $("#map-day").max = String(days); $("#map-day").value = String(mapDay || 1);
  $("#map-all").disabled = mapDay === null;
}

function setMapDay(day, focus = false) {
  mapDay = day;
  focusMapOnDay = focus;
  renderTimeline();
  updateMap();
}

function playMapMonth() {
  if (mapPlayback) { stopMapPlayback(); return; }
  if (mapDay === null || mapDay >= Number($("#map-day").max)) mapDay = 0;
  const totalDays = Number($("#map-day").max);
  updateReplayGuide();
  $("#map-play").textContent = `⏸ Pause (${mapDay}/${totalDays})`;
  const step = () => {
    mapDay += 1;
    updateReplayGuide();
    $("#map-play").textContent = `⏸ Pause (${mapDay}/${totalDays})`;
    renderTimeline(); updateMap();
    if (mapDay >= totalDays) { stopMapPlayback(); return; }
    mapPlayback = setTimeout(step, 950);
  };
  step();
}

async function updateMap() {
  if (!map || !state.data) return;
  const request = ++mapRequest;
  const params = new URLSearchParams({
    year: state.year, month: state.month + 1, series: state.series,
    bbox: mapViewport(), zoom: map.getZoom(),
    demo: state.demo ? 1 : 0,
  });
  if (mapDay !== null) params.set("day", String(mapDay));
  try {
    const result = await getJson(`/api/map?${params}`);
    if (request !== mapRequest) return;
    replayFeatures = result.features || []; replayMode = result.mode || "";
    markers.clearLayers();
    for (const feature of result.features) {
      if (result.mode === "aggregates") {
        const radius = Math.max(1.5, Math.min(map.getZoom() < 3 ? 5 : 11, 1 + Math.log2(feature.count + 1) * (map.getZoom() < 3 ? .35 : .65)));
        const marker = L.circleMarker([feature.lat, feature.lon], {radius, color: "#ffc28c", weight: .5, fillColor: "#ff944e", fillOpacity: .72});
        const body = document.createElement("div");
        const title = document.createElement("strong"); title.textContent = `${feature.count} imported pixels`;
        const note = document.createElement("p"); note.textContent = `All imported points in this grid bin · ${feature.sensors.join(" + ")}. Zoom in to inspect detections.`;
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
          render();
          await loadDay(state.day);
          $("#evidence-section")?.scrollIntoView({behavior: "smooth", block: "start"});
        });
        body.append(title, line, action); marker.bindPopup(body); markers.addLayer(marker);
      }
    }
    const scope = result.scope_date || result.month;
    $("#map-status").textContent = result.mode === "aggregates"
      ? `${result.features.length} map groups from ${result.records_in_sample.toLocaleString()} imported ${scope} points`
      : `${result.features.length.toLocaleString()} displayed across ${result.records_in_sample.toLocaleString()} imported ${scope} points · ${state.series}`;
    if (focusMapOnDay && mapDay !== null && result.features.length) {
      focusMapOnDay = false;
      const [west, south, east, north] = result.point_bounds;
      const bounds = L.latLngBounds([[south, west], [north, east]]);
      map.fitBounds(bounds.pad(.25), {padding: [45, 45], maxZoom: 11});
    }
    if (result.truncated) $("#map-status").textContent += " · sampled across all imported dates";
    renderReplayAnnotations();
  } catch (error) { if (request === mapRequest) $("#map-status").textContent = error.message; }
}

function render() {
  syncView();
  renderStudySources();
  renderStats(); renderSourceComparison(); renderMonths(); renderDays(); renderTimeline(); renderProvenance(); drawAoi(false); updateContextLayer(); updateMap();
  const research = $("#open-research-study");
  const researchUsesDemo = !["joint", "modis", "viirs-snpp"].includes(state.series);
  const researchContext = researchUsesDemo
    ? {year: 2026, month: 9, bbox: "-122,39,-120,41", demo: 1}
    : {year: state.year, month: state.month + 1, bbox: state.bbox, demo: state.demo ? 1 : 0};
  const researchUrl = `/research.html?${new URLSearchParams(researchContext)}`;
  if (research) research.href = researchUrl;
  if ($("#research-entry-copy")) $("#research-entry-copy").textContent = researchUsesDemo
    ? "Explore source overlap and candidate groups in a clearly labelled synthetic MODIS/VIIRS example. Your selected satellite product stays in the atlas."
    : "Compare source overlap, test candidate groups, and inspect observation-mask denominators.";
  document.querySelectorAll('a[href^="/research.html"]:not(#open-research-study)').forEach(link => { link.href = researchUrl; });
}

document.addEventListener("DOMContentLoaded", async () => {
  initMap();
  const workspace = document.getElementById("study-workspace");
  if (workspace?.tagName === "DETAILS") workspace.addEventListener("toggle", () => {
    if (workspace.open) requestAnimationFrame(() => map.invalidateSize({pan: false}));
  });
  $("#calendar-prev").addEventListener("click", () => selectCalendarMonth(state.month - 1));
  $("#calendar-next").addEventListener("click", () => selectCalendarMonth(state.month + 1));
  $("#additional-source").addEventListener("change", async event => {
    if (!event.target.value) return;
    try { await loadCalendar({series:event.target.value, day:null}); } catch (error) { toast(error.message); }
  });
  $("#map-play").addEventListener("click", playMapMonth);
  $("#map-all").addEventListener("click", () => { stopMapPlayback(); setMapDay(null); });
  $("#map-day").addEventListener("input", event => {
    stopMapPlayback(); mapDay = Number(event.target.value); renderTimeline();
    clearTimeout(mapInputTimer); mapInputTimer = setTimeout(updateMap, 120);
  });
  document.querySelectorAll("[data-demo]").forEach(button => button.addEventListener("click", () => selectDataset(button.dataset.demo === "1")));
  initStudyTools();
  $("#download-audit")?.addEventListener("click", () => {
    if (!state.audit) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(state.audit, null, 2)], {type: "application/json"}));
    const link = document.createElement("a"); link.href = url;
    link.download = `fireatlas_method_audit_${state.audit.series}_${state.audit.year}_${String(state.audit.month).padStart(2, "0")}.json`;
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
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
    if (button.getAttribute("aria-disabled") === "true") return toast("Measured fire-weather data have not been imported. Select the synthetic example to explore an illustration.");
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
  let calendarInitialized = false, pendingValidityDetail = null;
  async function applyValidityDay(detail) {
    const {date: stamp, bbox, year, month} = detail || {};
    if (!/^\d{4}-\d{2}-\d{2}$/.test(stamp || "") || !Array.isArray(bbox)) return;
    try {
      if (state.demo) { state.demo = false; await loadMeta(); }
      const area = bbox.join(","), index = month - 1;
      if (!state.data || state.year !== year || state.month !== index || state.bbox !== area || state.series !== "joint") {
        await loadCalendar({year, month:index, bbox:area, series:"joint", demo:false, day:stamp});
        drawAoi(true);
      } else {
        state.day = stamp; mapDay = Number(stamp.slice(8));
        renderDays(); renderTimeline(); syncView(); updateMap();
        await loadDay(stamp);
      }
    } catch (error) { toast(error.message); }
  }
  window.addEventListener("fireatlas:validity-day", event => {
    if (!calendarInitialized) {pendingValidityDetail = event.detail; return;}
    applyValidityDay(event.detail);
  });
  try {
    const initialParams = new URLSearchParams(location.search);
    const realMeta = !initialParams.has("demo") && !initialParams.has("year") && !initialParams.has("bbox") && !initialParams.has("series")
      ? await getJson("/api/meta?demo=0") : null;
    state.demo = initialParams.has("demo") ? initialParams.get("demo") !== "0"
      : initialParams.has("year") || initialParams.has("bbox") || initialParams.has("series") ? false
      : !realMeta?.available_sources?.includes("NOAA_HMS_VIIRS");
    await loadMeta();
    let next = {};
    if (location.search) {
      try { next = validateView({...viewConfig(), ...Object.fromEntries(new URLSearchParams(location.search))}); }
      catch (error) { toast(`${error.message} Showing the default view.`); }
    }
    await loadCalendar(next); drawAoi(true);
  } catch (error) { toast(error.message); }
  calendarInitialized = true;
  if (pendingValidityDetail) await applyValidityDay(pendingValidityDetail);
});
