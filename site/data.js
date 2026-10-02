(() => {
  const $ = id => document.getElementById(id);
  const staticDataRoot = document.querySelector('meta[name="fireatlas-static-data"]')?.content;
  const staticSnapshot = document.querySelector('meta[name="fireatlas-static-snapshot"]')?.content || 'static snapshot';
  const staticCache = new Map();
  let timer, busy = false;
  if (new Date() >= new Date("2026-10-01T04:00:00Z")) {
    $("maintenance-title").textContent = "September maintenance window has passed";
    $("maintenance-copy").textContent = "The September 25–30 FIRMS2 advisory is historical. It does not confirm a current outage or recovery. Use the connection status below and NASA’s latest notice to check service availability.";
  }
  function node(tag, text, className) {
    const el = document.createElement(tag); el.textContent = text;
    if (className) el.className = className;
    return el;
  }
  async function loadNativeMaskDownloads() {
    const panel = $("native-mask-downloads");
    if (!panel) return;
    const summary = panel.querySelector("summary");
    const status = $("native-mask-status");
    const list = $("native-mask-file-list");
    if (staticDataRoot) {
      summary.textContent = "Native files in the local project (8.7 GiB)";
      status.textContent = "The static release provides the full file inventory and NASA source links where recorded. Native binaries stay in the local project folder; run the local FireAtlas server to download each file directly from this page.";
      return;
    }
    try {
      const response = await fetch("/api/native-masks");
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Local asset list unavailable.");
      const formatSize = bytes => bytes >= 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(1)} GiB`
        : bytes >= 1024 ** 2 ? `${(bytes / 1024 ** 2).toFixed(1)} MiB` : `${(bytes / 1024).toFixed(0)} KiB`;
      summary.textContent = `Download ${result.asset_count.toLocaleString()} native files · ${formatSize(result.total_bytes)} total`;
      status.textContent = "Original local NASA HDF and NetCDF files. Each link streams the source file; SHA-256 values are in the inventory download above.";
      list.replaceChildren(...result.assets.map(asset => {
        const item = document.createElement("li");
        const link = node("a", `${asset.filename} · ${formatSize(asset.bytes)}`);
        link.href = asset.download_url;
        link.download = asset.filename;
        item.append(link);
        return item;
      }));
    } catch (error) {
      summary.textContent = "Native files are available from the local project folder";
      status.textContent = `Direct downloads are unavailable on this static page. ${error.message} The complete fingerprint inventory and recorded NASA source URLs remain downloadable above.`;
    }
  }
  async function staticFile(path) {
    const target = new URL(path, new URL(staticDataRoot, document.baseURI));
    if (!staticCache.has(target.href)) {
      const response = await fetch(target);
      if (!response.ok) throw new Error(`Static archive file unavailable (${response.status}).`);
      staticCache.set(target.href, await response.json());
    }
    return staticCache.get(target.href);
  }
  function staticStatus(regions, manifest) {
    const products = ['MODIS_SP', 'VIIRS_SNPP_SP'];
    const sources = products.map(source_id => {
      const items = regions.flatMap(region => region.products?.[source_id] ? [region.products[source_id]] : []);
      const boxes = regions.map(region => region.bbox).filter(Boolean);
      return {
        source_id, demo: false,
        observations: items.reduce((sum, item) => sum + Number(item.imported_detection_rows || 0), 0),
        imports: items.reduce((sum, item) => sum + Number(item.complete_month_count || 0), 0),
        first_observation: items.map(item => item.planned_start).sort()[0] || null,
        last_observation: items.map(item => item.last_complete_month).filter(Boolean).sort().at(-1) || null,
        retrieved_utc: `${staticSnapshot}T00:00:00Z`,
        series: source_id === 'MODIS_SP' ? 'modis' : 'viirs-snpp',
        west: Math.min(...boxes.map(box => box[0])), south: Math.min(...boxes.map(box => box[1])),
        east: Math.max(...boxes.map(box => box[2])), north: Math.max(...boxes.map(box => box[3])),
      };
    });
    const pilots = regions.map(region => {
      const years = new Set();
      for (const source of products) for (const month of region.products?.[source]?.complete_months || []) years.add(month.slice(0, 4));
      const windows = [...years].sort().flatMap(year => products.map(source => ({
        year: Number(year), source, complete: (region.products?.[source]?.complete_months || []).some(month => month.startsWith(`${year}-`)),
      })));
      return {id: region.id, name: region.name, description: region.description, bbox: region.bbox, windows};
    });
    return {
      schema: 'fireatlas-static-data-status-v1', static: true, synthetic: false,
      regions, sources, pilots, available_sources: products,
      standard_pair_ready: sources.every(source => source.observations > 0),
      years: [manifest.calendar_start_year, manifest.calendar_end_year],
      default_view: {year: Number(manifest.calendar_end_year), month: 7, bbox: regions[0]?.bbox || [-122, 39, -120, 41]},
      default_series: 'joint', credential_configured: false,
      sync: {status: 'static', message: 'Read-only static archive snapshot', updated_utc: `${staticSnapshot}T00:00:00Z`, completed: 0, total: 0},
      hms_windows: [], hms_validation: null,
    };
  }
  function pilotLink(pilot) {
    return `/atlas.html?${new URLSearchParams({year:2025,month:7,series:"joint",bbox:pilot.bbox.join(",")})}#calendar-section`;
  }
  function renderArchiveCoverage(payload) {
    const holder = $("archive-region-list");
    const sources = [
      ["MODIS_SP", "MODIS · Terra + Aqua"],
      ["VIIRS_SNPP_SP", "VIIRS · Suomi NPP"],
    ];
    holder.replaceChildren();
    for (const region of payload.regions || []) {
      const card = node("article", "", "archive-region-card");
      const heading = node("div", "", "archive-region-heading");
      heading.append(node("h3", region.name), node("small", `W ${region.bbox[0]} · S ${region.bbox[1]} · E ${region.bbox[2]} · N ${region.bbox[3]}`));
      card.append(heading);
      for (const [source, label] of sources) {
        const item = region.products[source];
        const row = node("div", "", "archive-product-row");
        const product = node("div", "", "archive-product-name");
        product.append(node("strong", label), node("small", `Expected archive starts ${item.planned_start}`));
        const metrics = node("div", "", "archive-product-metrics");
        const coverage = item.complete_month_count
          ? `${item.first_complete_month} → ${item.last_complete_month}` : "No complete month imported";
        metrics.append(node("strong", `${item.complete_month_count.toLocaleString()} complete months`), node("span", coverage));
        const count = item.imported_detection_rows.toLocaleString();
        metrics.append(node("small", `${count} clipped source rows · imported records, not fire counts`));
        row.append(product, metrics);
        if (item.reconstructed_row_only_month_count) {
          row.append(node("small", `${item.reconstructed_row_only_month_count.toLocaleString()} month(s) also contain detections from files with reconstructed date windows. Those rows are visible as partial evidence; missing dates are unknown.`, "archive-missing-note"));
        }
        if (item.missing_months?.length) {
          const missing = item.missing_months;
          const list = node("small", `${missing.length.toLocaleString()} target month(s) before the latest imported month have no complete export; ${missing[0]} … ${missing.at(-1)}.`, "archive-missing-note");
          row.append(list);
        }
        card.append(row);
      }
      holder.append(card);
    }
    const complete = (payload.regions || []).reduce((sum, region) => sum + Object.values(region.products)
      .reduce((subtotal, product) => subtotal + product.complete_month_count, 0), 0);
    $("archive-coverage-status").textContent = `${(payload.regions || []).length} study areas · ${complete.toLocaleString()} complete region-product-month exports recorded. Reconstructed archive rows are labeled partial; missing dates remain unknown. Export completeness is not a pass or cloud mask.`;
  }
  async function getJson(path) {
    if (!staticDataRoot) {
      const response = await fetch(path); const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not load data");
      return data;
    }
    if (path === "/api/v2/regions") return staticFile("regions.json");
    if (path === "/api/data/status") {
      const [regions, manifest] = await Promise.all([staticFile("regions.json"), staticFile("manifest.json")]);
      return staticStatus(regions.regions || [], manifest);
    }
    throw new Error("This read-only static page does not include that server action.");
  }
  async function refreshArchiveCoverage() {
    try {
      const payload = await getJson("/api/v2/regions");
      renderArchiveCoverage(payload);
    } catch (error) {
      $("archive-region-list").replaceChildren(node("p", `Could not load the regional archive ledger: ${error.message}`, "data-empty"));
      $("archive-coverage-status").textContent = "Check this server’s database and try again.";
    }
  }
  async function refresh() {
    if (busy) return;
    busy = true; clearTimeout(timer);
    try {
      const data = await getJson("/api/data/status");
      $("data-error").hidden = true;
      const recent = data.sources.filter(source => !source.demo && source.source_id.endsWith("_NRT") && source.observations);
      $("recent-imports").hidden = !recent.length;
      if (recent.length) {
        $("recent-count").textContent = recent.reduce((sum,source) => sum + source.observations, 0).toLocaleString();
        const first = recent.map(s => s.first_observation).sort()[0];
        const last = recent.map(s => s.last_observation).sort().at(-1);
        $("recent-dates").textContent = `${first.slice(0,10)} → ${last.slice(0,10)} · UTC acquisition dates`;
        $("recent-links").replaceChildren(...recent.map(source => {
          const link = node("a", source.source_id.replace("VIIRS_", "VIIRS ").replace("_NRT", "") + " ↗");
          link.href = `/atlas.html?${new URLSearchParams({series:source.series,year:source.last_observation.slice(0,4),month:Number(source.last_observation.slice(5,7)),bbox:"-180,-86,180,86"})}#atlas-section`;
          return link;
        }));
        const excluded = recent.reduce((sum,source) => sum + (source.excluded_rows || 0), 0);
        $("recent-exclusions").textContent = excluded ? `${excluded} polar source row retained in the exclusion ledger outside the ±86° atlas grid.` : "Original CSV rows and file hashes preserved.";
      }
      const noaa = data.sources.find(source => source.source_id === "NOAA_HMS_VIIRS");
      $("noaa-count").textContent = noaa ? noaa.observations.toLocaleString() : "0";
      $("noaa-state").textContent = noaa ? "AUTHENTIC ARCHIVE LOADED" : "ARCHIVE READY TO IMPORT";
      $("noaa-open").hidden = !noaa;
      $("noaa-years").replaceChildren(...(data.hms_windows || []).map(item => node("span", `${item.year} ${item.complete ? "✓" : "·"}`, item.complete ? "ready" : "")));
      const nasaReady = data.pilots?.length && data.pilots.every(pilot => pilot.windows.every(window => window.complete));
      $("nasa-archive").hidden = !nasaReady;
      $("nasa-archive-count").textContent = data.sources.filter(source => !source.demo && ["MODIS_SP", "VIIRS_SNPP_SP"].includes(source.source_id))
        .reduce((sum, source) => sum + source.observations, 0).toLocaleString();
      $("credential-state").textContent = data.credential_configured ? "KEY CONFIGURED ON SERVER" : "KEY NOT CONFIGURED";
      const sync = data.sync;
      const running = ["checking", "downloading", "validating"].includes(sync.status);
      $("sync-state").textContent = sync.status.toUpperCase();
      $("sync-state").dataset.status = sync.status;
      $("sync-message").textContent = sync.message;
      $("connection-time").textContent = sync.connection_verified_utc
        ? `Last accepted NASA availability request: ${new Date(sync.connection_verified_utc).toLocaleString()}. ${sync.updated_utc ? "Status updated " + new Date(sync.updated_utc).toLocaleString() + "." : ""}`
        : "NASA API connection unverified. Bundled historical archives remain available locally without an API key.";
      $("sync-progress").value = sync.completed || 0;
      $("sync-progress").max = sync.total || 16;
      $("sync-count").textContent = `${sync.completed || 0} / ${sync.total || 16} source-months`;
      $("sync-pilots").disabled = running || sync.status === "complete" || !data.credential_configured || data.synthetic;
      $("sync-pilots").textContent = running ? "Sync in progress…" : sync.status === "complete" ? "Pilot verified ✓" : sync.status === "failed" || sync.status === "interrupted" ? "Retry pilot sync ↗" : "Sync pilot data ↗";
      if (data.synthetic) {
        $("data-error").hidden = false;
        $("data-error").textContent = "This server is using synthetic data. Start the app with a separate authentic-data database to enable NASA imports.";
      }
      if (staticDataRoot) {
        $("sync-pilots").disabled = true;
        $("sync-pilots").textContent = "Static snapshot · read only";
        $("credential-state").textContent = "STATIC SNAPSHOT";
        $("connection-time").textContent = "This release contains a dated local archive. Server imports and NASA credentials are disabled in the static copy.";
        $("csv-import").querySelectorAll("input, select, button").forEach(control => { control.disabled = true; });
        $("import-result").textContent = "Read-only static bundle; use the local Python server to import a new CSV.";
      }
      $("csv-import").querySelectorAll("input, select, button").forEach(control => { control.disabled = data.synthetic || Boolean(staticDataRoot); });
      if (data.synthetic) $("import-result").textContent = "Import needs an authentic-data database.";
      $("pilot-list").replaceChildren();
      for (const pilot of data.pilots) {
        const card = node("article", "", "pilot-card");
        card.append(node("p", "JULY 2022–2025", "eyebrow"), node("h3", pilot.name), node("p", pilot.description), node("code", pilot.bbox.join(", ")));
        const grid = node("div", "", "window-grid");
        grid.append(node("span", "YEAR"), node("span", "MODIS"), node("span", "VIIRS"));
        for (const year of [...new Set(pilot.windows.map(window => window.year))].sort()) {
          grid.append(node("strong", year));
          for (const source of ["MODIS_SP", "VIIRS_SNPP_SP"]) {
            const complete = pilot.windows.find(w => w.year === year && w.source === source)?.complete;
            grid.append(node("span", complete ? "Imported" : "Awaiting data", complete ? "imported" : "pending"));
          }
        }
        const link = node("a", "Explore this area ↗"); link.href = pilotLink(pilot);
        card.append(grid, link); $("pilot-list").append(card);
      }
      $("source-list").replaceChildren();
      if (!data.sources.length) $("source-list").append(node("p", "No source observations have been imported into this dataset yet.", "data-empty"));
      for (const source of data.sources) {
        const card = node("article", "", "source-card");
        card.append(node("p", source.demo ? "SYNTHETIC" : "IMPORTED", "eyebrow"), node("h3", source.source_id === "NOAA_HMS_VIIRS" ? "NOAA HMS · VIIRS" : source.source_id),
          node("strong", source.observations.toLocaleString()), node("p", `${source.imports} imports · ${source.observations.toLocaleString()} observations`),
          node("small", `Latest retrieval ${new Date(source.retrieved_utc).toLocaleString()}`));
        if (source.excluded_rows) card.append(node("p", `${source.excluded_rows} source row outside the atlas grid, preserved separately.`));
        if (source.first_observation) {
          card.append(node("p", `Observed ${source.first_observation.slice(0,10)} – ${source.last_observation.slice(0,10)}`));
          if (source.series) {
            const link = node("a", "Explore these detections ↗");
            const window = source.latest_window;
            const bbox = window ? [window.west,window.south,window.east,window.north] : [Math.max(-180,source.west-.05),Math.max(-86,source.south-.05),Math.min(180,source.east+.05),Math.min(86,source.north+.05)];
            const date = window?.month || source.last_observation;
            link.href = `/atlas.html?${new URLSearchParams({series:source.series, year:date.slice(0,4), month:Number(date.slice(5,7)), bbox:bbox.join(",")})}#atlas-section`;
            card.append(link);
          }
        }
        $("source-list").append(card);
      }
      $("pilot-validation").replaceChildren();
      if (data.hms_validation?.status === "reproduced") {
        const line = node("article", "", "validation-pilot");
        line.append(node("h3", "NOAA HMS · Northern California"),
          node("p", `${data.hms_validation.cell_days.toLocaleString()} detected cell-days in July 2024 · prior-year median ${data.hms_validation.baseline_median.toLocaleString()} from ${data.hms_validation.baseline_years.join(", ")}`),
          node("strong", `${data.hms_validation.observations_verified.toLocaleString()} observations verified against study checksums and calendar totals`));
        $("pilot-validation").append(line);
      }
      if (sync.validation?.status === "reproduced") {
        for (const pilot of sync.validation.pilots) {
          const line = node("article", "", "validation-pilot");
          line.append(node("h3", pilot.name), node("p", `${pilot.cell_days.toLocaleString()} detected cell-days · prior-year median ${pilot.baseline_median.toLocaleString()} · baseline years ${pilot.baseline_years.join(", ")}`), node("strong", "Bundle checksums and calendar totals reproduced"));
          $("pilot-validation").append(line);
        }
      } else $("pilot-validation").append(node("p", "NASA FIRMS MODIS/VIIRS pilot validation awaits complete source imports."));
      if (running) timer = setTimeout(refresh, 2500);
    } catch (error) {
      $("data-error").hidden = false; $("data-error").textContent = error.message;
      $("sync-pilots").disabled = true;
    } finally { busy = false; }
  }
  $("refresh-data").addEventListener("click", refresh);
  $("import-complete").addEventListener("change", () => {
    $("import-window").hidden = !$("import-complete").checked;
    $("import-month").required = $("import-complete").checked;
    $("import-bbox").required = $("import-complete").checked;
  });
  $("csv-import").addEventListener("submit", async event => {
    event.preventDefault();
    const file = $("import-file").files[0];
    if (!file) return;
    if (file.size > 25_000_000) { $("import-result").textContent = "Choose a CSV smaller than 25 MB."; return; }
    const params = new URLSearchParams({source: $("import-source").value});
    if ($("import-complete").checked) {
      params.set("complete_month", $("import-month").value);
      params.set("bbox", $("import-bbox").value.trim());
    }
    $("import-submit").disabled = true;
    $("import-result").textContent = `Importing ${file.name}…`;
    try {
      const response = await fetch(`/api/data/import?${params}`, {method:"POST", headers:{"Content-Type":"text/csv"}, body:file});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Import failed.");
      $("import-result").textContent = result.import.already_imported
        ? "This exact source file was already imported."
        : `${result.import.rows_inserted.toLocaleString()} detections added · ${result.complete_month ? "complete month recorded" : "partial file"}.`;
      $("csv-import").reset();
      $("import-window").hidden = true;
      $("import-month").required = false;
      $("import-bbox").required = false;
      await refresh();
      await refreshArchiveCoverage();
    } catch (error) { $("import-result").textContent = error.message; }
    finally { $("import-submit").disabled = false; }
  });
  $("sync-pilots").addEventListener("click", async () => {
    $("sync-pilots").disabled = true;
    try {
      const response = await fetch("/api/data/sync", {method:"POST", headers:{"Content-Type":"application/json"}, body:"{}"});
      if (!response.ok) throw new Error((await response.json()).error || "Could not start sync.");
      await refresh(); timer = setTimeout(refresh, 1000);
    } catch (error) { $("data-error").hidden = false; $("data-error").textContent = error.message; $("sync-pilots").disabled = false; }
  });
  refreshArchiveCoverage();
  loadNativeMaskDownloads();
  refresh();
})();
