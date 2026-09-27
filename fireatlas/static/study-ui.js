// A shared view carries a selection; a study bundle freezes its evidence.
const savedViewsKey = "fireatlas.views.v1";
let calendarRequest = 0, dayRequest = 0;

function validateView(input) {
  const year = Number(input.year), month = Number(input.month);
  const bbox = String(input.bbox).split(",").map(value => value.trim() === "" ? NaN : Number(value));
  const [w, s, e, n] = bbox;
  if (!Number.isInteger(year) || year < 2000 || year > 2100 || !Number.isInteger(month) || month < 1 || month > 12 ||
      !["joint", "modis", "viirs-snpp", "hms-viirs", "viirs-noaa20", "viirs-noaa20-nrt", "viirs-noaa21-nrt", "viirs-snpp-nrt", "modis-nrt"].includes(input.series) || bbox.length !== 4 || bbox.some(v => !Number.isFinite(v)) ||
      !(w >= -180 && w < e && e <= 180 && s >= -90 && s < n && n <= 90)) throw new Error("This view has an invalid year, month, sensor series or area.");
  const day = input.day || null, layer = input.layer || "none";
  if (!["none", "ndvi", "landcover", "fwi"].includes(layer)) throw new Error("Unknown context layer in this view.");
  if (day && (!/^\d{4}-\d{2}-\d{2}$/.test(day) || Number(day.slice(0,4)) !== year || Number(day.slice(5,7)) !== month ||
      Number(day.slice(8)) < 1 || Number(day.slice(8)) > new Date(Date.UTC(year,month,0)).getUTCDate())) throw new Error("The selected day does not belong to this month.");
  if (input.demo != null && !["0", "1"].includes(String(input.demo))) throw new Error("Unknown data mode in this view.");
  return {year, month: month - 1, series: input.series, bbox: bbox.join(","), day, layer,
    demo: input.demo == null ? false : String(input.demo) === "1"};
}

function viewConfig() {
  return {year: state.year, month: state.month + 1, series: state.series, bbox: state.bbox, day: state.day || "", layer: contextChoice, demo: state.demo ? "1" : "0"};
}

function viewUrl() {
  const url = new URL("/", location.origin);
  url.search = new URLSearchParams(viewConfig()); url.hash = state.day ? "evidence-section" : "calendar-section";
  return url.href;
}

function syncView() {
  if (!state.data) return;
  const url = new URL(viewUrl()); url.hash = location.hash;
  history.replaceState(null, "", url);
  if (!$("#share-fallback").hidden) $("#share-url").value = viewUrl();
  document.querySelectorAll("[data-series]").forEach(el => el.classList.toggle("selected", el.dataset.series === state.series));
  document.querySelectorAll("[data-layer]").forEach(el => el.classList.toggle("selected", el.dataset.layer === contextChoice));
  $("#bbox").value = state.bbox;
  if (![...$("#year").options].some(option => Number(option.value) === state.year)) {
    const option = new Option(String(state.year), String(state.year)); $("#year").add(option);
  }
  $("#year").value = state.year;
}

function renderStudySources() {
  const container = $("#study-sources"); container.replaceChildren();
  const sources = state.data.provenance;
  $("#study-source-count").textContent = `${sources.length} source imports · ${state.data.monthly.filter(m => m.export_window_complete).length}/12 complete months`;
  if (!sources.length) { container.textContent = "No imported sources match this view."; return; }
  for (const source of sources) {
    const row = document.createElement("article");
    const title = document.createElement("strong"); title.textContent = `${source.source_id} · ${source.demo ? "Synthetic" : "Imported"}`;
    const origin = document.createElement("p"); origin.textContent = source.source_uri;
    const retrieved = document.createElement("p"); retrieved.textContent = `Retrieved ${source.retrieved_utc}`;
    const hash = document.createElement("code"); hash.textContent = `SHA-256 ${source.file_sha256}`;
    row.append(title, origin, retrieved, hash); container.append(row);
  }
}

function readSavedViews() {
  const views = JSON.parse(localStorage.getItem(savedViewsKey) || "[]");
  if (!Array.isArray(views)) throw new Error("Saved views could not be read.");
  return views.filter(view => { try { validateView(view.config); return typeof view.name === "string" && typeof view.id === "string"; } catch { return false; } }).slice(0, 20);
}

function renderSavedViews() {
  const select = $("#saved-views"); select.replaceChildren(new Option("Choose a saved view", ""));
  try {
    for (const view of readSavedViews()) select.add(new Option(view.name, view.id));
    $("#saved-note").textContent = "Saved on this browser only. Links use the receiving server’s current data.";
  } catch { $("#saved-note").textContent = "Browser storage is unavailable. You can still copy links and download studies."; }
  $("#restore-view").disabled = true; $("#delete-view").disabled = true;
}

function initStudyTools() {
  renderSavedViews();
  $("#saved-views").addEventListener("change", () => {
    $("#restore-view").disabled = !$("#saved-views").value; $("#delete-view").disabled = !$("#saved-views").value;
  });
  $("#save-view").addEventListener("click", () => {
    if (!state.data) return toast("Wait for the atlas to load.");
    const name = $("#view-name").value.trim();
    if (!name) { $("#view-name").focus(); return toast("Give this view a name first."); }
    try {
      const views = readSavedViews();
      if (views.length >= 20) return toast("You have 20 saved views. Remove one before saving another.");
      views.push({id: crypto.randomUUID(), name: name.slice(0,80), config: viewConfig()});
      localStorage.setItem(savedViewsKey, JSON.stringify(views)); renderSavedViews(); $("#view-name").value = ""; toast("View saved on this browser.");
    } catch { toast("Could not save in this browser. Copy a link or download the study instead."); }
  });
  $("#restore-view").addEventListener("click", async () => {
    try {
      const view = readSavedViews().find(v => v.id === $("#saved-views").value);
      if (view) {
        const next = validateView(view.config);
        if (state.demo !== next.demo) await selectDataset(next.demo);
        await loadCalendar(next); drawAoi(true); toast(`Opened ${view.name}`);
      }
    } catch (error) { toast(error.message); }
  });
  $("#delete-view").addEventListener("click", () => {
    try { localStorage.setItem(savedViewsKey, JSON.stringify(readSavedViews().filter(v => v.id !== $("#saved-views").value))); renderSavedViews(); toast("Saved view removed."); }
    catch { toast("Could not update browser storage."); }
  });
  $("#copy-view").addEventListener("click", async () => {
    if (!state.data) return toast("Wait for the atlas to load.");
    const url = viewUrl();
    $("#share-url").value = url; $("#share-fallback").hidden = false;
    try { await navigator.clipboard.writeText(url); toast("View link copied. It restores this selection on the same server."); }
    catch { $("#share-url").focus(); $("#share-url").select(); toast("Select and copy the view link below."); }
  });
  $("#download-study").addEventListener("click", async () => {
    if (!state.data) return toast("Wait for the atlas to load.");
    const button = $("#download-study"); button.disabled = true; button.textContent = "Preparing study…";
    const config = viewConfig();
    try {
      const response = await fetch(`/api/study?${new URLSearchParams(config)}`);
      if (!response.ok) throw new Error((await response.json()).error || "Study download failed.");
      const url = URL.createObjectURL(await response.blob()), link = document.createElement("a");
      link.href = url; link.download = `fireatlas_study_${config.series}_${config.year}.zip`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000); toast("Study downloaded with baseline inputs and provenance.");
    } catch (error) { toast(error.message); }
    finally { button.disabled = false; button.textContent = "↓ Download study"; }
  });
}
