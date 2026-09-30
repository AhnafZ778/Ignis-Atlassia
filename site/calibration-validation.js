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

  function modelRows(calibration) {
    const holder = $("#calibration-models");
    holder.replaceChildren();
    const models = calibration.validation?.models || {};
    const order = ["monthly_ratio", "annual_ratio", "no_harmonization"];
    const maxError = Math.max(0.001, ...order.map((key) => Number(models[key]?.median_absolute_log_error || 0)));
    for (const key of order) {
      const model = models[key];
      if (!model) continue;
      const row = document.createElement("article");
      row.className = `calibration-model${calibration.selected_model === key ? " selected" : ""}`;
      const heading = document.createElement("div");
      heading.className = "calibration-model-name";
      const title = document.createElement("strong"); title.textContent = labels[key]; heading.append(title);
      const badge = document.createElement("span");
      badge.textContent = calibration.selected_model === key ? "USED BY CALENDAR" : "REFERENCE";
      heading.append(badge);

      const track = document.createElement("div"); track.className = "calibration-bar-track";
      track.setAttribute("role", "img");
      track.setAttribute("aria-label", `${labels[key]} median absolute log error ${format(model.median_absolute_log_error)}`);
      const fill = document.createElement("span"); fill.className = "calibration-bar-fill";
      const value = Number(model.median_absolute_log_error);
      fill.style.width = `${Math.max(0, Math.min(100, value / maxError * 100))}%`;
      track.append(fill);

      const error = document.createElement("div"); error.className = "calibration-model-stat";
      const errorValue = document.createElement("strong"); errorValue.textContent = format(model.median_absolute_log_error);
      const errorLabel = document.createElement("small"); errorLabel.textContent = "median log error · lower is better";
      error.append(errorValue, errorLabel);

      const annual = document.createElement("div"); annual.className = "calibration-model-stat annual";
      const annualValue = document.createElement("strong");
      annualValue.textContent = model.median_annual_absolute_percent_error === null
        ? "—" : `${format(100 * model.median_annual_absolute_percent_error, 1)}%`;
      const annualLabel = document.createElement("small");
      const fullYears = model.annual_error_years || [];
      annualLabel.textContent = `median full-year absolute error · ${fullYears.length} complete held-out years`;
      annual.append(annualValue, annualLabel);
      row.append(heading, track, error, annual);
      holder.append(row);
    }
  }

  function render(data) {
    const calibration = data.calibration || {};
    const validation = calibration.validation || {};
    const years = validation.years_held_out || [];
    const yearLabel = years.length ? `${years[0]}–${years[years.length - 1]}` : "none";
    const pair = calibration.versions || {};
    $("#calibration-context").hidden = false;
    $("#calibration-context").textContent = `${data.region.name} · held out ${yearLabel} · ${pair.MODIS_SP || "MODIS version unknown"} / ${pair.VIIRS_SNPP_SP || "VIIRS version unknown"} · ${validation.selected_model ? labels[validation.selected_model] : "no method selected"}`;
    const version = calibration.method_version?.match(/v(\d+)$/)?.[1];
    $("#calibration-status").textContent = calibration.status === "calibrated"
      ? `${validation.monthly_interval_pairs || 0} held-out month pairs · ${calibration.overlap_months?.length || 0} matched complete months · calibration method ${version ? `v${version}` : "version unknown"}`
      : `Scaling is not available: ${calibration.status || "no calibration result"}.`;
    const provenance = data.provenance || {};
    const parents = provenance.parent_files || [];
    $("#calibration-provenance").textContent = `${parents.length} hash-identified NASA source files · ${provenance.paired_complete_months?.length || 0} complete paired months · input manifest ${provenance.input_manifest_sha256 || "unavailable"}`;
    modelRows(calibration);

    const coverage = validation.monthly_interval_coverage;
    $("#calibration-coverage-value").textContent = coverage === null || coverage === undefined
      ? "Not measured" : `${format(coverage * 100, 1)}%`;
    const pairs = validation.monthly_interval_pairs || 0;
    $("#calibration-coverage-note").textContent = coverage === null || coverage === undefined
      ? "No held-out interval results are available."
      : `${Math.round(coverage * pairs)} of ${pairs} held-out month pairs fell inside the nominal 95% interval.`;
    $("#calibration-coverage").dataset.undercovered = String(coverage !== null && coverage !== undefined && coverage < 0.90);

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
    $("#calibration-status").textContent = "Loading the source-attributed calibration artifact…";
    $("#calibration-models").replaceChildren();
    $("#calibration-download").href = `/samples/calibration/${encodeURIComponent(region)}.json`;
    try {
      const response = await fetch(`/samples/calibration/${encodeURIComponent(region)}.json`);
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
      $("#calibration-coverage-value").textContent = "—";
      $("#calibration-coverage-note").textContent = "No comparison loaded.";
      $("#calibration-step-value").textContent = "Unavailable";
      $("#calibration-step-note").textContent = "No 2012 test result was loaded.";
    }
  }
  regionSelect.addEventListener("change", load);
  load();
})();
