(() => {
  const $ = (selector) => document.querySelector(selector);
  const regionSelect = $("#harm-region"), yearSelect = $("#harm-year"), monthSelect = $("#harm-month");
  const staticDataRoot = document.querySelector('meta[name="fireatlas-static-data"]')?.content;
  const staticSnapshot = document.querySelector('meta[name="fireatlas-static-snapshot"]')?.content;
  const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  let regions = [], current = null, selectedDate = null, requestToken = 0;
  const staticCache = new Map();

  async function getJson(url) {
    if (staticDataRoot) {
      const request = new URL(url, document.baseURI);
      let file;
      if (request.pathname.endsWith("/api/v2/regions")) {
        file = "regions.json";
      } else if (request.pathname.endsWith("/api/v2/calendar")) {
        const region = request.searchParams.get("region"), year = request.searchParams.get("year");
        if (!/^(norcal|punjab-haryana)$/.test(region || "") || !/^20\d{2}$/.test(year || "")) {
          throw new Error("This static calendar selection is unavailable.");
        }
        file = `calendar/${region}/${year}.json`;
      } else if (request.pathname.endsWith("/api/observations")) {
        const region = regionSelect.value, stamp = request.searchParams.get("date") || "";
        if (!/^\d{4}-\d{2}-\d{2}$/.test(stamp)) throw new Error("A UTC date is required.");
        file = `observations/${region}/${stamp.slice(0, 4)}.json.gz`;
      } else {
        throw new Error("This endpoint is not included in the static study bundle.");
      }
      const root = new URL(staticDataRoot, document.baseURI);
      const target = new URL(file, root);
      if (!staticCache.has(target.href)) {
        const response = await fetch(target);
        if (!response.ok) throw new Error(`Static study file unavailable (${response.status}).`);
        let payload;
        if (file.endsWith(".gz")) {
          if (typeof DecompressionStream !== "function") throw new Error("This browser cannot open the compressed source-row bundle.");
          const stream = response.body.pipeThrough(new DecompressionStream("gzip"));
          payload = JSON.parse(await new Response(stream).text());
        } else {
          payload = await response.json();
        }
        staticCache.set(target.href, payload);
      }
      const payload = structuredClone(staticCache.get(target.href));
      if (file === "regions.json") return payload;
      if (file.startsWith("observations/")) {
        return payload.days[request.searchParams.get("date")] || {
          date_utc: request.searchParams.get("date"), observations: [], truncated: false,
        };
      }
      if (request.searchParams.get("history") === "1") {
        const historyUrl = new URL(`history/${request.searchParams.get("region")}.json`, root);
        if (!staticCache.has(historyUrl.href)) {
          const response = await fetch(historyUrl);
          if (!response.ok) throw new Error(`Static history file unavailable (${response.status}).`);
          staticCache.set(historyUrl.href, await response.json());
        }
        payload.history = staticCache.get(historyUrl.href);
      }
      if(file.startsWith('calendar/')) {
        const key=`${request.searchParams.get('region')}/${request.searchParams.get('year')}/${request.searchParams.get('month')}`;
        const manifestUrl=new URL('manifest.json',root);
        if(!staticCache.has(manifestUrl.href)){const response=await fetch(manifestUrl);if(!response.ok)throw Error('Analytical release manifest unavailable.');staticCache.set(manifestUrl.href,await response.json());}
        const release=staticCache.get(manifestUrl.href),identity=release.results?.[key];
        if(identity){Object.assign(payload.meta,identity);payload.meta.period.selected_month=identity.selected_month;payload.meta.bundle=release.bundles?.[key]||{status:'unavailable'};}
      }
      return payload;
    }
    const response = await fetch(FireAtlasContext.url(url));
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
    return data;
  }

  function n(value, digits = 1) {
    return value === null || value === undefined ? "—" : Number(value).toLocaleString(undefined, {maximumFractionDigits: digits});
  }

  function corroborationFor(monthKey) {
    const byMonth = current?.meta?.corroboration_by_month?.[monthKey];
    if (byMonth) return byMonth;
    const selected = current?.meta?.corroboration;
    return selected?.month === monthKey ? selected : {};
  }

  function ordinal(value) {
    const number = Math.round(Number(value));
    const suffix = number % 100 >= 11 && number % 100 <= 13 ? "th" : ({1: "st", 2: "nd", 3: "rd"}[number % 10] || "th");
    return `${number}${suffix}`;
  }

  function setStatus(message) { $("#harm-status").textContent = message; }

  function sourceHashSummary() {
    const hashes = new Set();
    for (const input of current?.meta?.inputs || []) {
      const digest = input.file_sha256 || input.parent_sha256 || input.sha256;
      if (typeof digest === "string" && /^[a-f0-9]{64}$/i.test(digest)) hashes.add(digest.toLowerCase());
    }
    const values = [...hashes].sort();
    return {count: values.length, sample: values.slice(0, 2).map(value => value.slice(0, 10)).join(" / ")};
  }

  function renderBuildMeta() {
    const target = $("#harm-build-meta");
    if (!target || !current) return;
    const hashes = sourceHashSummary();
    const snapshot = staticSnapshot ? `bundle built ${staticSnapshot}` : "live API ledger";
    const method = current.meta.bridge_method_version || "common-grid method version unavailable";
    target.textContent = `${snapshot} · ${hashes.count || "no"} SHA-256 source hash${hashes.count === 1 ? "" : "es"} · ${method}`;
    target.title = hashes.sample ? `Source hash sample: ${hashes.sample}` : "Source hashes are unavailable for this selection.";
  }

  function monthBridge(monthKey) {
    const days = current?.days?.filter((item) => item.date.startsWith(monthKey)) || [];
    const availability = new Map((current?.availability || []).filter((item) => item.date.startsWith(monthKey)).map((item) => [item.date, item.sources || {}]));
    const matchedTotals = {};
    const paired = days.filter((day) => {
      if (day.sensor_bridge?.status !== "complete" || day.viirs_status === "documented_processing_gap") return false;
      const sources = availability.get(day.date) || {};
      return ["MODIS_SP", "VIIRS_SNPP_SP"].every((source) =>
        sources[source]?.export_complete && sources[source]?.availability?.status !== "documented_processing_gap");
    });
    for (const source of ["MODIS_SP", "VIIRS_SNPP_SP"]) {
      const values = paired.map((day) => availability.get(day.date)?.[source]).filter(Boolean);
      matchedTotals[source] = {
        rows: values.reduce((sum, item) => sum + (item.raw_pixel_count || 0), 0),
        cells: values.reduce((sum, item) => sum + (item.detected_cell_days || 0), 0),
        excluded: values.reduce((sum, item) => sum + (item.excluded_row_count || 0), 0),
        pairedDays: values.length,
      };
    }
    const gaps = days.length - paired.length;
    const mismatch = paired.reduce((sum, item) => {
      const bridge = item.sensor_bridge || {};
      sum.modis += Number(bridge.modis_only_cell_days) || 0;
      sum.both += Number(bridge.co_detected_cell_days) || 0;
      sum.viirs += Number(bridge.viirs_only_cell_days) || 0;
      return sum;
    }, {modis: 0, both: 0, viirs: 0});
    const frpPairs = paired.map((day) => {
      const sources = availability.get(day.date) || {};
      return {MODIS_SP: sources.MODIS_SP?.frp_sum_mw, VIIRS_SNPP_SP: sources.VIIRS_SNPP_SP?.frp_sum_mw};
    }).filter((pair) => [pair.MODIS_SP, pair.VIIRS_SNPP_SP].every((value) =>
      value !== null && value !== undefined && Number.isFinite(Number(value))));
    const frp = {};
    for (const source of ["MODIS_SP", "VIIRS_SNPP_SP"]) {
      frp[source] = frpPairs.length
        ? frpPairs.reduce((sum, pair) => sum + Number(pair[source]), 0) / frpPairs.length
        : null;
    }
    return {days, matchedTotals, pairedDays: paired.length,
      frp, frpSampleDays: frpPairs.length, frpMissingDays: paired.length - frpPairs.length,
      bridgedDays: paired.length, gaps, mismatch, month: monthKey};
  }

  function renderBridge(month) {
    const key = month?.month;
    if (!key || !current) return;
    const bridge = monthBridge(key), modis = bridge.matchedTotals.MODIS_SP, viirs = bridge.matchedTotals.VIIRS_SNPP_SP;
    const max = Math.max(modis.cells, viirs.cells, Number(month.value) || 0, 1);
    const set = (id, value) => { const element = $(id); if (element) element.textContent = value; };
    set("#harm-bridge-modis", bridge.bridgedDays ? n(modis.cells, 0) : "—");
    set("#harm-bridge-viirs", bridge.bridgedDays ? n(viirs.cells, 0) : "—");
    set("#harm-bridge-result", month.value === null ? "UNKNOWN" : n(month.value, 1));
    const excludedNote = (value) => value.excluded ? ` · ${n(value.excluded, 0)} filtered` : "";
    set("#harm-bridge-modis-note", `${n(modis.rows, 0)} eligible rows${excludedNote(modis)} · ${modis.pairedDays} matched UTC dates`);
    set("#harm-bridge-viirs-note", `${n(viirs.rows, 0)} eligible rows${excludedNote(viirs)} · ${viirs.pairedDays} matched UTC dates`);
    const resultState = month.estimate_type === "observed" ? "Observed VIIRS"
      : month.estimate_type === "scaled" ? "MODIS-scaled estimate · prediction interval withheld"
        : month.estimate_type === "mixed" ? "Observed + estimated days · prediction interval withheld"
          : "State unknown";
    set("#harm-bridge-result-note", month.value === null ? "No complete reference value" : `${resultState} · never summed`);
    [["#harm-bridge-modis-bar", modis.cells], ["#harm-bridge-viirs-bar", viirs.cells], ["#harm-bridge-result-bar", month.value || 0]].forEach(([id, value]) => $(id)?.style.setProperty("--bridge-fill", String(Math.min(1, Number(value || 0) / max))));
    const gapLabel = bridge.gaps ? `${bridge.pairedDays}/${bridge.days.length} paired UTC dates · ${bridge.gaps} gap/unknown` : `${bridge.pairedDays} paired UTC dates`;
    set("#harm-bridge-state", gapLabel);
    set("#harm-bridge-days", `${bridge.days.length} days`);
    const bridgeMethod = current.meta.bridge_method_version;
    const bridgeLabel = bridgeMethod === "common-1km-bridge-frp-v1"
      ? "Common 1 km EASE-Grid · raw FRP separate"
      : bridgeMethod
        ? bridgeMethod.replaceAll("-", " ")
        : "Common-grid transform";
    set("#harm-bridge-method", `${bridgeLabel} · centroids grouped once per UTC day`);
    const mismatchTotal = bridge.mismatch.modis + bridge.mismatch.both + bridge.mismatch.viirs;
    const barMax = Math.max(mismatchTotal, 1);
    [["#harm-mismatch-modis", bridge.mismatch.modis], ["#harm-mismatch-both", bridge.mismatch.both], ["#harm-mismatch-viirs", bridge.mismatch.viirs]].forEach(([id, value]) => set(id, bridge.bridgedDays ? n(value, 0) : "—"));
    [["#harm-mismatch-modis-bar", bridge.mismatch.modis], ["#harm-mismatch-both-bar", bridge.mismatch.both], ["#harm-mismatch-viirs-bar", bridge.mismatch.viirs]].forEach(([id, value]) => $(id)?.style.setProperty("--mismatch-size", `${Math.max(4, Math.round(48 * Number(value || 0) / barMax))}px`));
    set("#harm-mismatch-gap", bridge.gaps ? n(bridge.gaps, 0) : "0");
    $("#harm-mismatch-gap-bar")?.style.setProperty("--mismatch-size", `${Math.max(4, Math.round(48 * bridge.gaps / Math.max(bridge.days.length, 1)))}px`);
    set("#harm-bridge-note", bridge.pairedDays
      ? `${n(bridge.mismatch.both, 0)} common-grid cell-days were reported by both sensors; ${n(bridge.mismatch.modis + bridge.mismatch.viirs, 0)} were sensor-specific. Raw pixels are never added together.`
      : "No paired clear export is available for this month; mismatch values stay unknown.");
    const frpValue = (value) => value === null ? "unknown" : n(value, 1);
    set("#harm-frp-value", `${frpValue(bridge.frp.MODIS_SP)} / ${frpValue(bridge.frp.VIIRS_SNPP_SP)}`);
    set("#harm-frp-unit", "mean MW · paired UTC dates");
    set("#harm-frp-note", bridge.pairedDays
      ? `Mean of daily source FRP sums on ${bridge.frpSampleDays} matched dates · MODIS / VIIRS; ${bridge.frpMissingDays} paired dates have unknown FRP.`
      : "No matched UTC dates; source FRP comparison is unknown.");
    const corroboration = corroborationFor(key);
    set("#harm-corroboration-state", corroboration.status === "loaded" ? "MCD64A1 LAGGED" : "ACTIVE FIRE ONLY");
    const qaSupported = corroboration.qa_supported_burned_pixels;
    const firstBurnDoy = corroboration.qa_supported_burn_date_min;
    const lastBurnDoy = corroboration.qa_supported_burn_date_max;
    const overlap = corroboration.same_day_spatial_comparison?.shared_1km_cell_days_by_source || {};
    const overlapSummary = Object.keys(overlap).length
      ? ` · same-date shared 1 km cell-days: MODIS ${n(overlap.MODIS_SP || 0, 0)}, S-NPP ${n(overlap.VIIRS_SNPP_SP || 0, 0)}` : "";
    set("#harm-corroboration-note", corroboration.status === "loaded"
      ? `${n(qaSupported ?? corroboration.burned_pixels_in_bbox, 0)} QA-supported burned pixels${firstBurnDoy ? ` · day ${firstBurnDoy}–${lastBurnDoy}` : ""}${overlapSummary}. Same-date matches are descriptive, not independent validation; no match does not mean no fire.`
      : "No dated MCD64A1 check is bundled for this month; the calendar uses active-fire detections only.");
    updateShareCard(month, bridge);
    renderBuildMeta();
  }

  function updateShareCard(month, bridge) {
    if (!month || !current || !$("#harm-share-card")) return;
    const sourceVersions = new Set();
    for (const item of current.availability || []) {
      if (!item.date.startsWith(month.month)) continue;
      for (const source of Object.values(item.sources || {})) for (const version of source.product_versions || []) sourceVersions.add(version);
    }
    const state = month.value === null ? "UNKNOWN"
      : month.estimate_type === "observed" ? "OBSERVED"
        : month.estimate_type === "mixed" ? "MIXED" : month.estimate_type === "scaled" ? "ESTIMATED" : "UNKNOWN STATE";
    const readable = (value) => String(value || "unknown").replaceAll("_", " ");
    const evidenceStates = [...new Set(bridge.days.map((day) => day.evidence_state).filter(Boolean))];
    const coverageStates = [...new Set(bridge.days.map((day) => day.coverage_state).filter(Boolean))];
    $("#harm-share-card-case").textContent = current.meta.region.name.toUpperCase();
    $("#harm-share-card-title").textContent = `${monthNames[Number(month.month.slice(5, 7)) - 1]} ${month.month.slice(0, 4)} · ${state}`;
    $("#harm-share-card-subtitle").textContent = "VIIRS-equivalent activity on a common 1 km grid · UTC";
    $("#harm-share-card-value").textContent = month.value === null ? "Unknown" : `${n(month.value, 1)} cell-days`;
    $("#harm-share-card-state").textContent = `${state} · ${bridge.gaps} gap/unknown day(s)`;
    $("#harm-share-card-quality").textContent = `${evidenceStates.map(readable).join(" / ") || "unknown"} · coverage ${coverageStates.map(readable).join(" / ") || "unknown"}`;
    const hashes = sourceHashSummary();
    const hashText = hashes.count ? `${hashes.count} SHA-256 · ${hashes.sample}` : "hash unavailable";
    $("#harm-share-card-inputs").textContent = `${sourceVersions.size ? [...sourceVersions].join(" / ") : "versions unknown"} · ${current.meta.inputs?.length || 0} ledger inputs · ${hashText}`;
    const corroboration = corroborationFor(month.month);
    const estimateLimit = ["scaled", "mixed"].includes(month.estimate_type)
      ? "Prediction interval withheld · " : "";
    const coverageLimit = corroboration.status === "loaded"
      ? "MCD64A1 lagged context · pass/cloud coverage unknown"
      : "ACTIVE FIRE ONLY · pass/cloud coverage unknown";
    $("#harm-share-card-limit").textContent = `${estimateLimit}${coverageLimit}`;
    const url = evidenceHref();
    const urlElement = $("#harm-share-card-url");
    urlElement.href = url;
    urlElement.textContent = url;
    urlElement.title = url;
  }

  function evidenceHref() {
    const url = new URL(location.href);
    const context = window.FireAtlasContext?.read() || {};
    const year = Number(yearSelect.value), month = Number(monthSelect.value);
    url.search = window.FireAtlasContext?.write({...context, region: regionSelect.value, year, month,
      as_of: new Date(Date.UTC(year, month, 0)).toISOString().slice(0, 10), day: ""}) ||
      new URLSearchParams({region: regionSelect.value, year, month}).toString();
    url.hash = "harmonized-calendar";
    return url.href;
  }

  function syncCanonicalContext() {
    const year=Number(yearSelect.value),month=Number(monthSelect.value),end=FireAtlasContext.monthEnd(year,month),region=regions.find(r=>r.id===regionSelect.value);
    FireAtlasContext.update({region:regionSelect.value,bbox:region.bbox.join(','),year,month,start:`${year}-${String(month).padStart(2,'0')}-01`,end,as_of:end,day:'',case:'',calendar_metric:'harmonized'},{history:'push'});
  }

  async function shareEvidence() {
    if (!current) return;
    const href = evidenceHref();
    $("#harm-share-card").hidden = false;
    try {
      if (navigator.share) await navigator.share({title: "FireAtlas evidence", text: `${current.meta.region.name} · ${monthNames[Number(monthSelect.value) - 1]} ${yearSelect.value}`, url: href});
      else if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(href);
      else { const input = document.createElement("textarea"); input.value = href; document.body.append(input); input.select(); document.execCommand("copy"); input.remove(); }
      $("#harm-share-status").textContent = "Evidence link copied · card below is ready to brief or review.";
    } catch (error) { $("#harm-share-status").textContent = error.name === "AbortError" ? "Share cancelled." : "Evidence card ready below; copy the URL from your browser."; }
  }

  function renderOfficialLinks() {
    const region = regionSelect.value;
    const links = $("#harm-official-links");
    links.replaceChildren();
    const sources = region === "norcal"
      ? [
          ["CAL FIRE incident records", "https://www.fire.ca.gov/incidents"],
          ["InciWeb incident records", "https://inciweb.wildfire.gov"],
        ]
      : [["NASA FIRMS observations", "https://firms.modaps.eosdis.nasa.gov/"]];
    for (const [label, href] of sources) {
      const link = document.createElement("a");
      link.href = href; link.target = "_blank"; link.rel = "noopener noreferrer";
      link.textContent = `${label} ↗`; links.append(link);
    }
    const note = document.createElement("span");
    note.textContent = region === "norcal"
      ? "Thermal detections are not a fire perimeter."
      : "No verified official local source listed. Thermal detections do not identify crop-burning cause.";
    links.append(note);
    renderSeasonContext();
  }

  function renderSeasonContext() {
    const context = $("#harm-season-context");
    if (!context) return;
    context.replaceChildren();
    const paddyWindow = regionSelect.value === "punjab-haryana"
      && yearSelect.value === "2024"
      && [10, 11].includes(Number(monthSelect.value));
    context.hidden = !paddyWindow;
    if (!paddyWindow) return;

    const label = document.createElement("strong");
    label.textContent = "2024 paddy-harvest monitoring";
    const dates = document.createElement("span");
    dates.textContent = "1 Oct–30 Nov";
    const source = document.createElement("a");
    source.href = "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2060764&lang=2&reg=48";
    source.target = "_blank";
    source.rel = "noopener noreferrer";
    source.textContent = "Official context ↗";
    const limit = document.createElement("small");
    limit.textContent = "Hotspots show heat; they do not confirm crop-residue fires.";
    context.append(label, dates, source, limit);
  }

  function fillMonths() {
    monthSelect.replaceChildren(...monthNames.map((label, index) => new Option(label, String(index + 1))));
    monthSelect.value = "7";
  }

  function fillYears() {
    const region = regions.find((item) => item.id === regionSelect.value);
    const latest = Math.max(2025, ...((region?.products ? Object.values(region.products) : [])
      .map((item) => item.last_complete_month ? Number(item.last_complete_month.slice(0, 4)) : 0)));
    yearSelect.replaceChildren();
    const firstYear = Number(region?.history_start?.slice(0, 4) || 2010);
    for (let year = firstYear; year <= latest; year += 1) yearSelect.add(new Option(String(year), String(year)));
    yearSelect.value = "2024";
  }

  function displaySourceStatus() {
    const region = regions.find((item) => item.id === regionSelect.value);
    const container = $("#harm-source-status");
    container.replaceChildren();
    if (!region) return;
    const labels = {MODIS_SP: "MODIS · Terra + Aqua", VIIRS_SNPP_SP: "VIIRS · Suomi NPP"};
    for (const source of ["MODIS_SP", "VIIRS_SNPP_SP"]) {
      const product = region.products[source];
      const row = document.createElement("article"); row.className = "harm-source-row";
      const title = document.createElement("strong"); title.textContent = labels[source];
      const state = document.createElement("span");
      state.textContent = product.complete_month_count
        ? `${product.first_complete_month} → ${product.last_complete_month}` : "AWAITING EXPORTS";
      const note = document.createElement("small");
      const firstDetection = product.first_detection_utc
        ? ` · detections from ${product.first_detection_utc.slice(0, 10)}` : "";
      const reconstructed = product.reconstructed_row_only_month_count
        ? ` · ${product.reconstructed_row_only_month_count.toLocaleString()} months contain detections from date-reconstructed files; other days remain unknown`
        : "";
      note.textContent = product.complete_month_count
        ? `${product.complete_month_count.toLocaleString()} complete source-months · ${product.imported_detection_rows.toLocaleString()} imported rows${firstDetection}${reconstructed} · target window begins ${product.planned_start}`
        : `${product.imported_detection_rows.toLocaleString()} imported rows, but no complete source-month yet${firstDetection}${reconstructed}. Target window begins ${product.planned_start}.`;
      row.append(title, state, note); container.append(row);
    }
  }

  function setValueSummary(month) {
    $("#harm-value").textContent = month.value === null ? "Unknown" : n(month.value);
    const baselineCard = $("#harm-percentile")?.closest(".harm-summary-card");
    if (baselineCard) {
      baselineCard.dataset.activity = month.flag || "unknown-month";
      baselineCard.setAttribute("aria-label", month.flag === "unusually-high"
        ? "Monthly activity is unusually high compared with the comparable baseline"
        : month.flag === "unusually-low"
          ? "Monthly activity is unusually low compared with the comparable baseline"
          : month.flag === "typical"
            ? "Monthly activity is typical compared with the comparable baseline"
            : "Monthly activity baseline is insufficient or unknown");
    }
    const partialDays = month.partial_detection_days || 0;
    const partialModis = month.partial_modis_cell_days || 0;
    const partialViirs = month.partial_viirs_cell_days || 0;
    $("#harm-value-note").textContent = month.value === null
      ? partialDays ? `${partialDays} UTC dates · partial source counts: MODIS ${n(partialModis, 0)} cell-days, S-NPP ${n(partialViirs, 0)} · ${month.unknown_days ?? "Other"} dates unknown`
        : `No complete harmonized month · ${month.unknown_days ?? "All"} UTC dates unknown, not zero`
      : `${month.observed_days} VIIRS-observed days · ${month.estimated_days} MODIS-estimated days · ${month.unknown_days} unknown days`;
    $("#harm-years").textContent = String(month.n_years);
    const composition = n(month.observed_days, 0) + " VIIRS-observed days · "
      + n(month.estimated_days, 0) + " MODIS-estimated days · "
      + n(month.unknown_days, 0) + " unknown UTC dates";
    const partialNote = partialDays
      ? "Partial source detections on " + n(partialDays, 0) + " UTC dates: MODIS "
        + n(partialModis, 0) + " cell-days, S-NPP " + n(partialViirs, 0)
        + " cell-days (not included in the month total)"
      : "No complete harmonized month";
    $("#harm-value-note").textContent = month.value === null
      ? partialNote + " · " + composition + " · total unknown, not zero"
      : composition;
    if (month.estimated_days > 0) {
      $("#harm-value-note").textContent += " · "
        + (month.uncertainty_note || "Prediction interval withheld; prediction error is not independently calibrated.");
    }
    $("#harm-percentile").textContent = month.percentile_rank === null
      ? "Percentile withheld" : `${ordinal(month.percentile_rank)} percentile · ${month.flag.replaceAll("-", " ")}`;
    const season = current.meta.season || {};
    $("#harm-season").textContent = season.season_status === "available"
      ? `${season.season_start?.slice(5)} · ${season.season_peak?.slice(5)} · ${season.season_end?.slice(5)}`
      : season.season_status === "no-detected-activity" ? "No detections" : "Unavailable";
    $("#harm-season-note").textContent = season.season_status === "available"
      ? `Start · 15-day peak center · end · ${yearSelect.value} UTC` : `${season.missing_days ?? "—"} unknown days; season dates withheld`;
    const calibration = current.meta.calibration_status;
    const model = current.meta.calibration_model;
    $("#harm-model").textContent = model ? model.replaceAll("_", " ") : "Not validated";
    const validation = current.meta.calibration_validation || {};
    const nested = validation.nested_selected_pipeline;
    const fixed = validation.models?.[model];
    const daily = validation.daily_gap_benchmark?.daily_metrics?.selected_pipeline;
    const pairedNote = daily?.median_absolute_log_error === null || daily?.median_absolute_log_error === undefined
      ? "daily gap benchmark unavailable"
      : `${daily.n_days} paired daily checks · median log error ${n(daily.median_absolute_log_error, 3)}`;
    $("#harm-model-note").textContent = nested?.median_absolute_log_error !== null && nested?.median_absolute_log_error !== undefined
      ? `Nested selected-method outer holdout · monthly log error ${n(nested.median_absolute_log_error, 3)} · ${pairedNote}`
      : fixed?.median_absolute_log_error !== null && fixed?.median_absolute_log_error !== undefined
        ? `Fixed ${model.replaceAll("_", " ")} outer holdout · monthly log error ${n(fixed.median_absolute_log_error, 3)} · ${pairedNote}`
        : `${calibration.replaceAll("-", " ")} · no held-out comparison supports scaling`;
    $("#harm-verdict").textContent = month.verdict;
    $("#harm-month-total").textContent = month.value === null ? "UNKNOWN MONTH" : `${n(month.value)} VIIRS-equivalent cell-days`;
    renderBridge(month);
  }

  function dayClass(item) {
    if (!item) return "unknown";
    if (item.coverage_state === "documented_processing_gap") return item.viirs_gap_partial_day ? "documented-gap partial-gap-day" : "documented-gap";
    if (item.evidence_state === "complete_zero_export") return "zero";
    if (item.evidence_state === "scaled") return "estimated";
    if (item.evidence_state === "observed") return "observed";
    if (item.viirs_status === "documented_processing_gap") return item.viirs_gap_partial_day ? "documented-gap partial-gap-day" : "documented-gap";
    if (item.quality === "degraded") return "estimated";
    if (item.quality === "good" && item.value === 0) return "zero";
    if (item.quality === "good") return "observed";
    if ((item.partial_modis_cell_days || 0) > 0 || (item.partial_viirs_cell_days || 0) > 0) return "partial-observations";
    return "unknown";
  }

  function renderCalendar() {
    if (!current) return;
    const year = Number(yearSelect.value), month = Number(monthSelect.value);
    const monthKey = `${year}-${String(month).padStart(2, "0")}`;
    const summary = current.months.find((item) => item.month === monthKey);
    if (!summary) return;
    setValueSummary(summary);
    const grid = $("#harm-day-grid"); grid.replaceChildren();
    const firstWeekday = (new Date(Date.UTC(year, month - 1, 1)).getUTCDay() + 6) % 7;
    const dayCount = new Date(Date.UTC(year, month, 0)).getUTCDate();
    const byDate = new Map(current.days.map((item) => [item.date, item]));
    const values = Array.from({length: dayCount}, (_, index) => byDate.get(`${monthKey}-${String(index + 1).padStart(2, "0")}`));
    const maximum = Math.max(0, ...values.map((item) => item?.value ?? 0));
    for (let i = 0; i < firstWeekday; i += 1) {
      const blank = document.createElement("span"); blank.className = "harm-day blank"; blank.setAttribute("aria-hidden", "true"); grid.append(blank);
    }
    values.forEach((item, index) => {
      const number = index + 1, stamp = `${monthKey}-${String(number).padStart(2, "0")}`;
      const button = document.createElement("button"); button.type = "button";
      button.className = `harm-day ${dayClass(item)}`; button.dataset.date = stamp;
      button.setAttribute("aria-pressed", String(stamp === selectedDate));
      const partialModis = item?.partial_modis_cell_days || 0;
      const partialViirs = item?.partial_viirs_cell_days || 0;
      const hasPartial = (item?.value === null || !item) && (partialModis > 0 || partialViirs > 0);
      const count = item?.value === null || !item ? hasPartial ? "+" : "—" : n(item.value, 1);
      const label = hasPartial ? "partial detections" : item?.coverage_state === "documented_processing_gap" ? (item.viirs_gap_partial_day ? `partial gap · ${item.evidence_state === "scaled" ? "scaled estimate" : "unknown"}` : `gap · ${item.evidence_state === "scaled" ? "scaled estimate" : "unknown"}`)
        : item?.evidence_state === "complete_zero_export" ? "complete zero"
        : item?.evidence_state === "observed" ? "observed VIIRS" : item?.evidence_state === "scaled" ? "scaled estimate"
        : item?.quality === "good" ? item.value === 0 ? "zero" : "VIIRS"
        : item?.quality === "degraded" ? item.reason === "documented-processing-gap" ? (item.viirs_gap_partial_day ? "partial gap · MODIS" : "gap · MODIS") : "MODIS est."
          : item?.viirs_status === "documented_processing_gap" ? (item.viirs_gap_partial_day ? "partial gap · unknown" : "gap · unknown") : "unknown";
      const dateNode = document.createElement("span"); dateNode.className = "harm-date"; dateNode.textContent = String(number);
      const countNode = document.createElement("strong"); countNode.className = "harm-count"; countNode.textContent = count;
      const kindNode = document.createElement("small"); kindNode.className = "harm-kind"; kindNode.textContent = label;
      button.append(dateNode, countNode, kindNode);
      const aria = hasPartial
        ? `${stamp} UTC · partial detections: MODIS ${n(partialModis, 0)} centroid cell-days, VIIRS S-NPP ${n(partialViirs, 0)} centroid cell-days · harmonized total unknown because archive coverage is incomplete · pass and cloud coverage unknown`
        : `${stamp} UTC · ${count} VIIRS-equivalent cell-days · ${label}${item?.reason ? ` · ${item.reason.replaceAll("-", " ")}` : ""} · pass and cloud coverage unknown`;
      button.setAttribute("aria-label", aria); button.title = aria;
      if (item?.value > 0 && maximum > 0) {
        const t = Math.log1p(item.value) / Math.log1p(maximum);
        const heat = window.FireAtlasPalette.heat(t);
        button.style.setProperty("--harm-heat", heat.color);
        button.style.setProperty("--harm-ink", heat.dark ? "#000000" : "#FFFFFF");
      }
      button.addEventListener("click", () => { selectedDate = stamp; FireAtlasContext.update({day:stamp},{history:"replace",reason:"day"}); renderCalendar(); loadEvidence(stamp); });
      button.addEventListener("keydown", (event) => {
        const delta = {ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7}[event.key];
        if (!delta) return;
        event.preventDefault();
        const next = Math.min(dayCount, Math.max(1, number + delta));
        grid.querySelector(`[data-date="${monthKey}-${String(next).padStart(2, "0")}"]`)?.focus();
      });
      grid.append(button);
    });
    $("#harm-days-title").textContent = `${monthNames[month - 1]} ${year} · select a UTC day`;
    const download = $("#harm-download");
    const matching=current.meta.bundle;
    download.textContent='Download this harmonized result';
    if(staticDataRoot){
      const available=matching?.status==='verified'&&matching.result_sha256===current.meta.result_sha256;
      download.href=available?new URL(matching.path,new URL(staticDataRoot,document.baseURI)).href:'#';
      download.setAttribute('aria-disabled',String(!available));
      download.title=available?`Exact frozen result · ${(matching.bytes/1024/1024).toFixed(1)} MiB`:'Exact regional bundle unavailable for this static selection';
      download.onclick=event=>{if(!available){event.preventDefault();setStatus('Exact regional bundle unavailable for this static selection. Start the local service for a current export.');}};
    }else{
      download.href=FireAtlasContext.url(`api/v2/study?${new URLSearchParams({region:regionSelect.value,year,month,expected_result_sha256:current.meta.result_sha256,...(selectedDate?{day:selectedDate}:{})})}`);
      download.removeAttribute('aria-disabled');
    }
    download.download=`ignis-${regionSelect.value}-${year}-${String(month).padStart(2,'0')}-harmonized.zip`;
    window.dispatchEvent(new CustomEvent('fireatlas:harmonized-result',{detail:{result:current,month:current.months.find(m=>m.month===monthKey)}}));
    if (!selectedDate || !selectedDate.startsWith(monthKey)) {
      selectedDate = null;
      $("#harm-day-title").textContent = "Choose a day to inspect its evidence.";
      $("#harm-day-summary").textContent = "The raw NASA record will be shown separately from the harmonized estimate.";
      $("#harm-day-source-status").replaceChildren();
      $("#harm-records").replaceChildren();
    }
  }

  function historyClass(item) {
    if (item?.coverage_state === "documented_processing_gap") return item.partial_gap_day ? "documented-gap partial-gap-day" : "documented-gap";
    if (item?.evidence_state === "scaled") return "estimated";
    if (item?.evidence_state === "complete_zero_export") return "zero";
    if (item?.evidence_state === "observed") return "observed";
    if (item?.viirs_status === "documented_processing_gap") return item.partial_gap_day ? "documented-gap partial-gap-day" : "documented-gap";
    if (!item) return "unknown";
    if (item.quality === "degraded") return "estimated";
    if (item.quality === "good" && Number(item.value) === 0) return "zero";
    if ((item.partial_modis_cell_days || 0) > 0 || (item.partial_viirs_cell_days || 0) > 0) return "partial-observations";
    if (item.quality === "unknown" || item.value === null) return "unknown";
    return "observed";
  }

  function selectHistoryDay(stamp) {
    const [year, month] = stamp.split("-").map(Number);
    if (Number(yearSelect.value) !== year) {
      yearSelect.value = String(year);
      monthSelect.value = String(month);
      loadCalendar({includeHistory: Boolean($("#harm-history-details")?.open), selectDate: stamp});
      return;
    }
    monthSelect.value = String(month);
    selectedDate = stamp;
    renderHistory(current?.history);
    renderCalendar();
    loadEvidence(stamp);
    $("#harm-day-title").scrollIntoView({block: "nearest", behavior: "smooth"});
  }

  function renderHistory(history) {
    const grid = $("#harm-history-grid");
    if (!grid) return;
    grid.replaceChildren();
    if (!history?.days?.length) {
      grid.append(Object.assign(document.createElement("p"), {
        className: "harm-history-loading", textContent: "No dated history is available for this selection.",
      }));
      $("#harm-history-range").textContent = "History unavailable";
      return;
    }
    const firstDate = history.start || "2010-01-01";
    const lastDate = history.end || `${yearSelect.value}-12-31`;
    const latestYear = Math.max(2006, Number(lastDate.slice(0, 4)));
    const firstYear = Number(firstDate.slice(0, 4));
    const byDate = new Map(history.days.map((item) => [item.date, item]));
    const buttonByDate = new Map();
    const rows = [];
    let maximum = 0;
    for (const item of history.days) {
      if (item.value !== null && Number(item.value) > maximum) maximum = Number(item.value);
    }
    for (let year = firstYear; year <= latestYear; year += 1) {
      const row = document.createElement("div"); row.className = "harm-history-year-row"; row.setAttribute("role", "row");
      const yearLabel = document.createElement("span"); yearLabel.className = "harm-history-year";
      yearLabel.setAttribute("role", "rowheader"); yearLabel.textContent = String(year);
      const monthJump=document.createElement('div');monthJump.className='harm-history-month-jump';monthJump.setAttribute('aria-label',`Open readable monthly dates for ${year}`);
      for(let month=1;month<=12;month++){
        const stamp=`${year}-${String(month).padStart(2,'0')}-01`;
        const end=new Date(Date.UTC(year,month,0)).toISOString().slice(0,10);
        const button=document.createElement('button');button.type='button';button.textContent=monthNames[month-1].slice(0,3);button.disabled=end<firstDate||stamp>lastDate;
        button.setAttribute('aria-label',`Open ${monthNames[month-1]} ${year} daily calendar; missing dates remain unknown`);
        button.addEventListener('click',()=>selectHistoryDay(stamp<firstDate?firstDate:stamp));monthJump.append(button);
      }
      const days = document.createElement("div"); days.className = "harm-history-days";
      let cursor = new Date(Date.UTC(year, 0, 1));
      for (let position = 0; position < 366; position += 1) {
        const stamp = cursor.toISOString().slice(0, 10);
        const leapSlot = stamp.slice(5) === "02-29";
        if (cursor.getUTCFullYear() !== year) {
          const blank = document.createElement("span"); blank.className = "harm-history-empty"; blank.setAttribute("aria-hidden", "true"); days.append(blank);
          continue;
        }
        if (leapSlot && !((year % 4 === 0 && year % 100 !== 0) || year % 400 === 0)) {
          const blank = document.createElement("span"); blank.className = "harm-history-empty"; blank.setAttribute("aria-hidden", "true"); days.append(blank);
          cursor = new Date(Date.UTC(year, 2, 1));
          continue;
        }
        if (stamp < firstDate || stamp > lastDate) {
          const blank = document.createElement("span"); blank.className = "harm-history-empty outside-window"; blank.setAttribute("aria-hidden", "true"); days.append(blank);
          cursor = new Date(Date.UTC(year, cursor.getUTCMonth(), cursor.getUTCDate() + 1));
          continue;
        }
        const item = byDate.get(stamp);
        const button = document.createElement("button"); button.type = "button"; button.className = `harm-history-day ${historyClass(item)}`;
        button.dataset.date = stamp; button.setAttribute("role", "gridcell");
        button.tabIndex = stamp === firstDate ? 0 : -1;
        button.setAttribute("aria-pressed", String(stamp === selectedDate));
        const partialModis = item?.partial_modis_cell_days || 0;
        const partialViirs = item?.partial_viirs_cell_days || 0;
        const hasPartial = (item?.value === null || !item) && (partialModis > 0 || partialViirs > 0);
        const label = hasPartial ? `Partial detections · MODIS ${n(partialModis, 0)} · S-NPP ${n(partialViirs, 0)}` : item?.value === null || !item ? "Unknown" : item.coverage_state === "documented_processing_gap"
          ? `Documented processing gap${item.evidence_state === "scaled" ? " · MODIS estimate" : ""}` : item.evidence_state === "complete_zero_export"
            ? "Complete export, zero detections" : item.evidence_state === "observed" ? "VIIRS observed" : item.evidence_state === "scaled" ? "MODIS estimate"
            : item.quality === "good" ? "Observed" : "Unknown";
        const value = hasPartial ? "incomplete archive coverage" : item?.value === null || !item ? "no value" : `${n(item.value, 1)} VIIRS-equivalent cell-days`;
        const reason = item?.reason ? ` · ${item.reason.replaceAll("-", " ")}` : "";
        const accessible = `${stamp} UTC · ${label} · ${value}${reason} · pass, cloud and no-fire status unknown`;
        button.setAttribute("aria-label", accessible); button.title = accessible;
        if (item?.quality === "good" && item.value > 0 && maximum > 0) {
          const t = Math.log1p(item.value) / Math.log1p(maximum);
          button.style.setProperty("--history-color", window.FireAtlasPalette.heat(t).color);
        }
        button.addEventListener("click", () => selectHistoryDay(stamp));
        button.addEventListener("keydown", (event) => {
          if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
          event.preventDefault();
          let next = stamp;
          const day = new Date(`${stamp}T00:00:00Z`);
          if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            day.setUTCDate(day.getUTCDate() + (event.key === "ArrowLeft" ? -1 : 1)); next = day.toISOString().slice(0, 10);
          } else if (event.key === "ArrowUp" || event.key === "ArrowDown") {
            const nextYear = year + (event.key === "ArrowUp" ? -1 : 1);
            const lastDay = new Date(Date.UTC(nextYear, Number(stamp.slice(5, 7)), 0)).getUTCDate();
            next = `${nextYear}-${stamp.slice(5, 7)}-${String(Math.min(Number(stamp.slice(8, 10)), lastDay)).padStart(2, "0")}`;
          } else {
            next = `${year}-${event.key === "Home" ? "01-01" : "12-31"}`;
          }
          const target = buttonByDate.get(next);
          if (target) { button.tabIndex = -1; target.tabIndex = 0; target.focus(); }
        });
        buttonByDate.set(stamp, button); days.append(button);
        cursor = new Date(Date.UTC(year, cursor.getUTCMonth(), cursor.getUTCDate() + 1));
      }
      const dailyStrip=document.createElement('details');dailyStrip.className='harm-history-exact-strip';const dailySummary=document.createElement('summary');dailySummary.textContent=`${year} daily overview · expand for exact dates`;dailyStrip.append(dailySummary,days);
      row.append(yearLabel, monthJump,dailyStrip); rows.push(row); grid.append(row);
    }
    const earliestAvailable = history.days.find((item) => item.quality !== "unknown")?.date;
    const earliestPartial = history.days.find((item) => item.partial_modis_cell_days > 0 || item.partial_viirs_cell_days > 0)?.date;
    const selectedRegion = regions.find((item) => item.id === regionSelect.value);
    const exportEnd = ["MODIS_SP", "VIIRS_SNPP_SP"]
      .map((source) => `${source} ${selectedRegion?.products?.[source]?.last_complete_month || "awaiting exports"}`)
      .join(" · ");
    $("#harm-history-range").textContent = `Window starts ${firstDate} · ${exportEnd} · year rows ${firstYear}–${latestYear}`;
    $("#harm-history-note").textContent = earliestAvailable
      ? `Earliest day with a complete source value: ${earliestAvailable}${earliestPartial ? ` · reconstructed-file detections also begin ${earliestPartial}` : ""}. Arrow keys move by day or year; press Enter to open a date. Blank periods remain unknown, not fire-free.`
      : earliestPartial
        ? `Dated detections from files with reconstructed coverage begin ${earliestPartial}; hatched days show positive rows only. Other dates stay unknown. No complete source values are present in this loaded history.`
        : "No complete source values are present in the loaded history. Blank periods remain unknown, not fire-free.";
  }

  function availabilityMessage(item) {
    const status = item.availability?.status;
    if (status === "documented_processing_gap") return "NASA notice documents a product outage during this UTC day; pass/cloud conditions remain unknown.";
    if (status === "unknown_export") {
      const cells = item.partial_detected_cell_days || 0, rows = item.partial_raw_pixel_count || 0;
      const reconstructed = item.coverage_basis?.includes("reconstructed-rows-only");
      const excluded = item.partial_excluded_row_count || 0;
      return cells || rows || excluded
        ? `${n(cells, 0)} detected 1 km centroid cell-day(s) from ${n(rows, 0)} eligible rows${excluded ? ` · ${n(excluded, 0)} filtered` : ""}${reconstructed ? " in a file with reconstructed date coverage" : " in an incomplete source export"}; other observations are unknown.`
        : "No complete source-month export is loaded; zero detections cannot be inferred.";
    }
    if (status === "zero_detections_exported") return "Complete export has zero eligible detection rows; satellite pass and cloud coverage remain unknown.";
    const excluded = item.excluded_row_count || 0;
    return `${item.raw_pixel_count ?? 0} eligible FIRMS row(s) in the complete export${excluded ? ` · ${excluded} filtered by type` : ""} · version ${item.product_versions.join(", ") || "unknown"}.`;
  }

  async function loadEvidence(stamp) {
    if (!current) return;
    const item = current.days.find((row) => row.date === stamp);
    const detail = current.availability.find((row) => row.date === stamp)?.sources || {};
    const verdict = item?.value === null || !item ? "Harmonized value unknown. The product export does not cover this date." : item.estimate_type === "observed"
      ? `${n(item.value)} observed VIIRS cell-days; no scaling was applied.`
      : `${n(item.value)} estimated VIIRS-equivalent cell-days from ${n(item.modis_cell_days)} MODIS common-grid cell-days × ${n(item.scale_factor, 3)}. The year-bootstrap 95% range describes the fitted factor only, not prediction uncertainty; a reliable prediction interval is withheld.`;
    $("#harm-day-title").textContent = `${stamp} UTC · ${item?.quality || "unknown"}`;
    $("#harm-day-summary").textContent = `${verdict} Satellite pass, cloud and fire-free status are not inferred.`;
    const sourceContainer = $("#harm-day-source-status");
    sourceContainer.replaceChildren();
    for (const [source, title] of [["MODIS_SP", "MODIS · Terra + Aqua"], ["VIIRS_SNPP_SP", "VIIRS · Suomi NPP"]]) {
      const state = detail[source];
      const row = document.createElement("article"); row.className = "harm-source-row";
      const name = document.createElement("strong"); name.textContent = title;
      const status = document.createElement("span"); status.textContent = (state?.availability?.status || "unknown").replaceAll("_", " ").toUpperCase();
      const note = document.createElement("small"); note.textContent = state ? availabilityMessage(state) : "No daily source record is available.";
      row.append(name, status, note); sourceContainer.append(row);
      for (const notice of state?.availability?.notices || []) {
        if (!notice.url?.startsWith("https://")) continue;
        const link = document.createElement("a");
        link.className = "harm-source-notice";
        link.href = notice.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "Open NASA product notice ↗";
        link.setAttribute("aria-label", `${notice.published_by || "NASA"} product notice (opens in a new tab)`);
        row.append(link);
      }
    }
    try {
      const region = regions.find((entry) => entry.id === regionSelect.value);
      const bbox = region.bbox.join(",");
      const params = new URLSearchParams({date: stamp, series: "joint", bbox});
      const result = await getJson(`/api/observations?${params}`);
      if (selectedDate !== stamp) return;
      const container = $("#harm-records"); container.replaceChildren();
      if (!result.observations.length) {
        const note = document.createElement("small"); note.textContent = "No eligible source rows returned for this UTC day. This does not establish no fire, no pass, or clear sky."; container.append(note);
      }
      for (const observation of result.observations) {
        const details = document.createElement("details");
        const summary = document.createElement("summary");
        const type = String(observation.raw?.type ?? "").trim();
        const included = !type || type === "0";
        const name = document.createElement("strong"); name.textContent = `${observation.sensor} · ${observation.platform} · ${included ? "included in calendar" : `excluded type ${type}`}`;
        const time = document.createElement("span"); time.textContent = observation.acquisition_utc.slice(11, 16) + " UTC";
        summary.append(name, time);
        const pre = document.createElement("pre"); pre.textContent = JSON.stringify(observation.raw, null, 2);
        details.append(summary, pre); container.append(details);
      }
      if (result.truncated) {
        const note = document.createElement("small"); note.textContent = "More than 200 records matched; narrow the day or review the source export."; container.append(note);
      }
    } catch (error) {
      if (selectedDate !== stamp) return;
      const container = $("#harm-records"); container.textContent = `Source records unavailable: ${error.message}`;
    }
  }

  async function loadCalendar({includeHistory = false, selectDate = null} = {}) {
    const token = ++requestToken;
    selectedDate = selectDate;
    renderSeasonContext();
    displaySourceStatus();
    setStatus("Loading the selected authentic archive window…");
    $("#harm-records").replaceChildren();
    try {
      const params = new URLSearchParams({region: regionSelect.value, year: yearSelect.value, month: monthSelect.value});
      if (includeHistory) params.set("history", "1");
      const data = await getJson(`/api/v2/calendar?${params}`);
      if (token !== requestToken) return;
      current = data;
      setStatus(data.meta.data_class === "no-authentic-imports"
        ? "No authentic records imported for this region yet; values stay unknown."
        : `Imported FIRMS archive · latest detection ${data.meta.period.actual_latest_detection || "not present"} · UTC${staticSnapshot ? ` · static snapshot ${staticSnapshot}` : ""}`);
      if (includeHistory || data.history) renderHistory(data.history);
      renderCalendar();
      renderBuildMeta();
      if (selectedDate) loadEvidence(selectedDate);
    } catch (error) {
      if (token === requestToken) setStatus(`Calendar unavailable: ${error.message}`);
    }
  }

  async function init() {
    if (!regionSelect) return;
    fillMonths();
    monthSelect.value=String(FireAtlasContext.read().month);
    renderOfficialLinks();
    try {
      const status = await getJson("/api/v2/regions");
      regions = status.regions;
      const params = new URLSearchParams(location.search);
      const sharedRegion = params.get("region") || params.get("harm_region");
      if (regions.some((item) => item.id === sharedRegion)) regionSelect.value = sharedRegion;
      fillYears();
      const sharedYear = Number(params.get("year") || params.get("harm_year") || FireAtlasContext.read().year);
      const sharedMonth = Number(params.get("month") || params.get("harm_month") || FireAtlasContext.read().month);
      if (sharedYear >= 2006 && sharedYear <= 2026 && [...yearSelect.options].some((option) => Number(option.value) === sharedYear)) yearSelect.value = String(sharedYear);
      if (sharedMonth >= 1 && sharedMonth <= 12) monthSelect.value = String(sharedMonth);
      renderOfficialLinks();
      displaySourceStatus();
      const incoming=FireAtlasContext.read(),requested=regions.find(r=>r.id===incoming.region);
      if(incoming.errors.length||!requested||incoming.geometry||(params.has('bbox')&&incoming.bbox!==requested.bbox.join(','))||sharedYear<2006||sharedYear>2026)throw Error('The incoming selection is retained in the URL. Harmonized activity requires an exact supported regional box, no polygon subset, and a supported year. Choose a region/month explicitly or use Combined detections.');
      await loadCalendar({includeHistory: Boolean($("#harm-history-details")?.open),selectDate:incoming.day||null});
    } catch (error) { setStatus(`Archive status unavailable: ${error.message}`); }
    regionSelect.addEventListener("change", () => { fillYears(); renderOfficialLinks(); displaySourceStatus(); syncCanonicalContext(); loadCalendar({includeHistory: Boolean($("#harm-history-details")?.open)}); });
    yearSelect.addEventListener("change", () => { syncCanonicalContext(); loadCalendar({includeHistory: Boolean($("#harm-history-details")?.open)}); });
    monthSelect.addEventListener("change", () => { selectedDate = null; syncCanonicalContext(); loadCalendar({includeHistory:Boolean($("#harm-history-details")?.open)}); });
    $("#harm-share")?.addEventListener("click", shareEvidence);
  }

  addEventListener('fireatlas:context-restore',()=>{const c=FireAtlasContext.read();regionSelect.value=c.region;fillYears();yearSelect.value=c.year;monthSelect.value=c.month;selectedDate=c.day||null;loadCalendar({includeHistory:Boolean($("#harm-history-details")?.open)});});
  $("#harm-history-details")?.addEventListener('toggle',()=>{if($("#harm-history-details").open)loadCalendar({includeHistory:true});});
  window.FireAtlasAtlasCapture=()=>{if(!current)throw Error('Wait for the selected calendar.');const c=FireAtlasContext.read();return {study:FireAtlasContext.toAssistantContext(c),view:{kind:'calendar',operation:'harmonized',calculation_contract:'harmonized',day:selectedDate||c.start,metric:'harmonized',arguments:{expected_result_sha256:current.meta.result_sha256},caption:'Harmonized activity · '+c.region+' · '+c.year+'-'+String(c.month).padStart(2,'0')+' UTC; source visibility does not change the headline.'},result_sha256:current.meta.result_sha256};};
  init();
})();
