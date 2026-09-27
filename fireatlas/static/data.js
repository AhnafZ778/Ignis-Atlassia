(() => {
  const $ = id => document.getElementById(id);
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
  async function eventStatus() {
    try {
      const response = await fetch("/api/events");
      const feed = await response.json();
      if (!response.ok) throw new Error(feed.error || "Event feed unavailable");
      $("eonet-count").textContent = feed.count.toLocaleString();
      $("eonet-state").textContent = `${feed.stale ? "Cached copy" : "NASA EONET connected"} · ${new Date(feed.fetched_utc).toLocaleString()}`;
    } catch (error) { $("eonet-state").textContent = error.message; }
  }
  function pilotLink(pilot) {
    return `/?${new URLSearchParams({year:2024,month:7,series:"joint",bbox:pilot.bbox.join(","),demo:0})}#calendar-section`;
  }
  async function refresh() {
    if (busy) return;
    busy = true; clearTimeout(timer);
    try {
      const response = await fetch("/api/data/status");
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not read source status.");
      $("data-error").hidden = true;
      const noaa = data.sources.find(source => source.source_id === "NOAA_HMS_VIIRS");
      $("noaa-count").textContent = noaa ? noaa.observations.toLocaleString() : "0";
      $("noaa-state").textContent = noaa ? "AUTHENTIC ARCHIVE LOADED" : "ARCHIVE READY TO IMPORT";
      $("noaa-open").hidden = !noaa;
      $("noaa-years").replaceChildren(...(data.hms_windows || []).map(item => node("span", `${item.year} ${item.complete ? "✓" : "·"}`, item.complete ? "ready" : "")));
      $("credential-state").textContent = data.credential_configured ? "KEY CONFIGURED ON SERVER" : "KEY NOT CONFIGURED";
      const sync = data.sync;
      const running = ["checking", "downloading", "validating"].includes(sync.status);
      $("sync-state").textContent = sync.status.toUpperCase();
      $("sync-state").dataset.status = sync.status;
      $("sync-message").textContent = sync.message;
      $("connection-time").textContent = sync.connection_verified_utc
        ? `Last accepted NASA availability request: ${new Date(sync.connection_verified_utc).toLocaleString()}. ${sync.updated_utc ? "Status updated " + new Date(sync.updated_utc).toLocaleString() + "." : ""}`
        : "Server connection pending. No successful FIRMS availability response has been recorded yet.";
      $("sync-progress").value = sync.completed || 0;
      $("sync-progress").max = sync.total || 16;
      $("sync-count").textContent = `${sync.completed || 0} / ${sync.total || 16} source-months`;
      $("sync-pilots").disabled = running || !data.credential_configured || data.synthetic;
      $("sync-pilots").textContent = running ? "Sync in progress…" : sync.status === "failed" || sync.status === "interrupted" ? "Retry pilot sync ↗" : "Sync pilot data ↗";
      if (data.synthetic) {
        $("data-error").hidden = false;
        $("data-error").textContent = "This server is using synthetic data. Start the app with a separate authentic-data database to enable NASA imports.";
      }
      $("csv-import").querySelectorAll("input, select, button").forEach(control => { control.disabled = data.synthetic; });
      if (data.synthetic) $("import-result").textContent = "Import needs an authentic-data database.";
      $("pilot-list").replaceChildren();
      for (const pilot of data.pilots) {
        const card = node("article", "", "pilot-card");
        card.append(node("p", "JULY 2021–2024", "eyebrow"), node("h3", pilot.name), node("p", pilot.description), node("code", pilot.bbox.join(", ")));
        const grid = node("div", "", "window-grid");
        grid.append(node("span", "YEAR"), node("span", "MODIS"), node("span", "VIIRS"));
        for (const year of [2021,2022,2023,2024]) {
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
        if (source.first_observation) {
          card.append(node("p", `Observed ${source.first_observation.slice(0,10)} – ${source.last_observation.slice(0,10)}`));
          if (source.series) {
            const link = node("a", "Explore these detections ↗");
            const window = source.latest_window;
            const bbox = window ? [window.west,window.south,window.east,window.north] : [Math.max(-180,source.west-.05),Math.max(-86,source.south-.05),Math.min(180,source.east+.05),Math.min(86,source.north+.05)];
            const date = window?.month || source.last_observation;
            link.href = `/?${new URLSearchParams({demo:source.demo ? 1 : 0, series:source.series, year:date.slice(0,4), month:Number(date.slice(5,7)), bbox:bbox.join(",")})}#atlas-section`;
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
  refresh();
  eventStatus();
})();
