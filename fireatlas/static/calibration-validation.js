(() => {
  const $ = (selector) => document.querySelector(selector);
  const regionSelect = $("#calibration-region");
  if (!regionSelect) return;

  const labels = {
    monthly_ratio: "Month-specific ratio",
    annual_ratio: "One annual ratio",
    no_harmonization: "No scaling · factor 1",
  };
  const format = (value, digits = 3) => value === null || value === undefined
    ? "—" : Number(value).toLocaleString("en-US", {minimumFractionDigits: digits, maximumFractionDigits: digits});
  const percent = (value) => value === null || value === undefined ? "—" : `${format(value * 100, 1)}%`;

  function appendModelRow(holder, name, model, {nested = false, maxError = 1} = {}) {
    if (!model) return;
    const row = document.createElement("article");
    row.className = `calibration-model${nested ? " nested" : ""}`;
    const heading = document.createElement("div");
    heading.className = "calibration-model-name";
    const title = document.createElement("strong");
    title.textContent = nested ? "Nested selected pipeline" : labels[name];
    heading.append(title);
    const badge = document.createElement("span");
    badge.textContent = nested ? "NESTED HELD-OUT ESTIMATE" : "FIXED CANDIDATE REFERENCE";
    heading.append(badge);

    const track = document.createElement("div");
    track.className = "calibration-bar-track";
    track.setAttribute("role", "img");
    track.setAttribute("aria-label", `${title.textContent} median absolute log error ${format(model.median_absolute_log_error)}`);
    const fill = document.createElement("span");
    fill.className = "calibration-bar-fill";
    const value = Number(model.median_absolute_log_error);
    fill.style.width = `${Math.max(0, Math.min(100, value / maxError * 100))}%`;
    track.append(fill);

    const error = document.createElement("div");
    error.className = "calibration-model-stat";
    const errorValue = document.createElement("strong");
    errorValue.textContent = format(model.median_absolute_log_error);
    const errorLabel = document.createElement("small");
    errorLabel.textContent = "median absolute log error · lower is better";
    error.append(errorValue, errorLabel);

    const annual = document.createElement("div");
    annual.className = "calibration-model-stat annual";
    const annualValue = document.createElement("strong");
    annualValue.textContent = percent(model.median_annual_absolute_percent_error);
    const annualLabel = document.createElement("small");
    annualLabel.textContent = `median full-year absolute error · ${(model.annual_error_years || []).length} complete held-out years`;
    annual.append(annualValue, annualLabel);
    row.append(heading, track, error, annual);
    holder.append(row);
  }

  function modelRows(calibration) {
    const holder = $("#calibration-models");
    holder.replaceChildren();
    const validation = calibration.validation || {};
    const models = validation.models || {};
    const nested = validation.nested_selected_pipeline;
    const order = ["monthly_ratio", "annual_ratio", "no_harmonization"];
    const maxError = Math.max(0.001, ...[
      ...order.map((key) => Number(models[key]?.median_absolute_log_error || 0)),
      Number(nested?.median_absolute_log_error || 0),
    ]);
    appendModelRow(holder, "selected_pipeline", nested, {nested: true, maxError});
    for (const key of order) appendModelRow(holder, key, models[key], {maxError});
  }

  function gapTable(benchmark) {
    const holder = $("#calibration-gap-table");
    holder.replaceChildren();
    const groups = new Map();
    for (const item of benchmark?.contiguous_gap_contribution_metrics || []) {
      const key = `${item.gap_duration_days}:${item.season}`;
      if (!groups.has(key)) groups.set(key, {gap_duration_days: item.gap_duration_days, season: item.season});
      groups.get(key)[item.model] = item;
    }
    const rows = [...groups.values()]
      .sort((a, b) => a.gap_duration_days - b.gap_duration_days || a.season.localeCompare(b.season));
    if (!rows.length) {
      holder.textContent = "No compatible held-out gap windows are available.";
      return;
    }

    const table = document.createElement("table");
    table.className = "calibration-gap-table";
    const caption = document.createElement("caption");
    caption.textContent = "Median absolute log error on withheld window totals; lower is better.";
    table.append(caption);
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    for (const label of ["Synthetic gap", "Held-out windows", "Nested selection", "Fixed month ratio", "Fixed annual ratio", "No scaling"]) {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = label;
      headRow.append(th);
    }
    head.append(headRow);
    const body = document.createElement("tbody");
    for (const item of rows) {
      const tr = document.createElement("tr");
      const selected = item.selected_pipeline;
      const countSource = selected || item.monthly_ratio || item.annual_ratio || item.no_harmonization;
      const cells = [
        `${item.gap_duration_days} day${item.gap_duration_days === 1 ? "" : "s"} · ${item.season}`,
        Number(countSource?.window_count || 0).toLocaleString("en-US"),
        format(selected?.median_absolute_log_error),
        format(item.monthly_ratio?.median_absolute_log_error),
        format(item.annual_ratio?.median_absolute_log_error),
        format(item.no_harmonization?.median_absolute_log_error),
      ];
      for (const value of cells) {
        const td = document.createElement("td");
        td.textContent = value;
        tr.append(td);
      }
      body.append(tr);
    }
    table.append(head, body);
    holder.append(table);
  }

  function render(data) {
    const calibration = data.calibration || {};
    const validation = calibration.validation || {};
    const years = validation.years_held_out || [];
    const yearLabel = years.length ? `${years[0]}–${years[years.length - 1]}` : "none";
    const pair = calibration.versions || {};
    const selected = calibration.selected_model;
    $("#calibration-context").hidden = false;
    $("#calibration-context").textContent = `${data.region.name} · nested outer evaluation ${yearLabel} (${validation.nested_selected_pipeline?.outer_evaluation_folds || 0} folds) · production calendar choice: ${labels[selected] || "no method selected"} · ${pair.MODIS_SP || "MODIS version unknown"} / ${pair.VIIRS_SNPP_SP || "VIIRS version unknown"}`;
    const version = calibration.method_version?.match(/v(\d+)$/)?.[1];
    $("#calibration-status").textContent = calibration.status === "calibrated"
      ? `${calibration.overlap_months?.length || 0} matched complete months · ${validation.nested_selected_pipeline?.outer_evaluation_folds || 0} nested held-out year folds · calibration method ${version ? `v${version}` : "version unknown"}`
      : `Scaling is not available: ${calibration.status || "no calibration result"}.`;
    const provenance = data.provenance || {};
    const parents = provenance.parent_files || [];
    $("#calibration-provenance").textContent = `${parents.length} hash-identified NASA source files · ${provenance.paired_complete_months?.length || 0} paired source-bundle months (${calibration.overlap_months?.length || 0} eligible for this calibration) · input manifest ${provenance.input_manifest_sha256 || "unavailable"}`;
    modelRows(calibration);

    const benchmark = validation.daily_gap_benchmark || {};
    const daily = benchmark.daily_metrics?.selected_pipeline;
    const dailyModels = benchmark.daily_metrics || {};
    $("#calibration-daily-value").textContent = daily
      ? `${format(daily.median_absolute_log_error)} median log error · ${percent(daily.median_absolute_percent_error_nonzero)} median nonzero-day absolute percentage error`
      : "Not evaluated";
    $("#calibration-daily-note").textContent = daily
      ? `${Number(daily.n_days).toLocaleString("en-US")} held-out days; ${Number(daily.n_nonzero_viirs_days).toLocaleString("en-US")} with nonzero VIIRS detections. Fixed-reference median log errors: month ratio ${format(dailyModels.monthly_ratio?.median_absolute_log_error)}, annual ratio ${format(dailyModels.annual_ratio?.median_absolute_log_error)}, no scaling ${format(dailyModels.no_harmonization?.median_absolute_log_error)}. Candidate selection was nested within each held-out year.`
      : "No compatible held-out daily observations are available.";
    gapTable(benchmark);

    const interval = validation.prediction_interval || {};
    const withheld = interval.status === "withheld-not-independently-calibrated";
    $("#calibration-coverage-value").textContent = withheld
      ? "Withheld" : interval.held_out_coverage === null || interval.held_out_coverage === undefined
        ? "Not measured" : percent(interval.held_out_coverage);
    $("#calibration-coverage-note").textContent = withheld
      ? `${interval.reason || "Independent held-out prediction-interval calibration is unavailable."} No coverage or interval width is claimed.`
      : interval.held_out_coverage === null || interval.held_out_coverage === undefined
        ? "No held-out interval results are available."
        : `${interval.evaluated_pairs || 0} independently evaluated held-out pairs; median width ${format(interval.median_width)}.`;
    $("#calibration-coverage").dataset.undercovered = String(
      !withheld && interval.held_out_coverage !== null && interval.held_out_coverage !== undefined
      && interval.held_out_coverage < 0.90
    );

    const step = calibration.step_2012 || {};
    if (step.status === "evaluated") {
      $("#calibration-step-value").textContent = step.within_interval ? "Inside reference interval" : "Outside reference interval";
      $("#calibration-step-value").dataset.result = step.within_interval ? "inside" : "outside";
      $("#calibration-step-note").textContent = `2012 ratio ${format(step.ratio)} from ${step.months_used?.length || 0} complete months; later-year 95% interval ${format(step.interval_95?.[0])}–${format(step.interval_95?.[1])} (${step.reference_years?.length || 0} reference years).`;
    } else {
      $("#calibration-step-value").textContent = "Not tested";
      $("#calibration-step-value").removeAttribute("data-result");
      $("#calibration-step-note").textContent = step.status === "insufficient-reference-years"
        ? "The 2012 rows exist, but fewer than two later complete overlap years are available for the reference interval."
        : "2012 detections are present as partial evidence, but the saved request metadata do not establish complete source exports.";
    }
  }

  let request = 0;
  async function load() {
    const token = ++request;
    const region = regionSelect.value;
    const artifactUrl = new URL(`samples/calibration/${encodeURIComponent(region)}.json`, document.baseURI);
    $("#calibration-status").textContent = "Loading the source-attributed calibration artifact…";
    $("#calibration-models").replaceChildren();
    $("#calibration-download").href = artifactUrl.href;
    try {
      const response = await fetch(artifactUrl);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
      if (data.schema !== "fireatlas-calibration-artifact-v1" || data.region?.id !== region) {
        throw new Error("Calibration artifact does not match the selected region.");
      }
      if (token === request) render(data);
    } catch (error) {
      if (token !== request) return;
      $("#calibration-status").textContent = `Comparison unavailable: ${error.message}`;
      $("#calibration-context").hidden = true;
      $("#calibration-models").replaceChildren();
      $("#calibration-provenance").textContent = "No source manifest loaded.";
      $("#calibration-daily-value").textContent = "—";
      $("#calibration-daily-note").textContent = "No comparison loaded.";
      $("#calibration-gap-table").textContent = "No comparison loaded.";
      $("#calibration-coverage-value").textContent = "—";
      $("#calibration-coverage-note").textContent = "No comparison loaded.";
      $("#calibration-step-value").textContent = "Unavailable";
      $("#calibration-step-note").textContent = "No 2012 test result was loaded.";
    }
  }
  regionSelect.addEventListener("change", load);
  load();
})();
