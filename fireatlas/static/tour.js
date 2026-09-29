(() => {
  const startButton = document.querySelector("#start-calendar-tour");
  const panel = document.querySelector("#calendar-tour");
  if (!startButton || !panel) return;

  const title = document.querySelector("#calendar-tour-title");
  const copy = document.querySelector("#calendar-tour-copy");
  const counter = document.querySelector("#calendar-tour-count");
  const back = document.querySelector("#calendar-tour-back");
  const next = document.querySelector("#calendar-tour-next");
  const progress = [...panel.querySelectorAll(".calendar-tour-progress i")];
  let active = false;
  let step = 0;
  let highlighted = null;
  let selectedEvidence = null;

  const waitFrame = () => new Promise(resolve => requestAnimationFrame(resolve));
  const reduceMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

  document.addEventListener("fireatlas:study-ready", () => {
    startButton.disabled = false;
    startButton.textContent = "Take the data tour";
  }, {once: true});

  function setHighlight(element) {
    highlighted?.classList.remove("tour-target");
    highlighted = element || null;
    if (!highlighted) return;
    highlighted.classList.add("tour-target");
    highlighted.scrollIntoView({behavior: reduceMotion() ? "auto" : "smooth", block: "center"});
    const target = highlighted;
    setTimeout(() => {
      if (!active || highlighted !== target) return;
      const targetRect = target.getBoundingClientRect();
      const panelRect = panel.getBoundingClientRect();
      if (targetRect.bottom > panelRect.top - 18 && targetRect.top < panelRect.bottom) {
        window.scrollBy({top: Math.min(targetRect.bottom - panelRect.top + 30, innerHeight * 0.35),
          behavior: reduceMotion() ? "auto" : "smooth"});
      }
    }, reduceMotion() ? 0 : 420);
  }

  async function openAuthenticObservation() {
    selectedEvidence = null;
    const view = new URLSearchParams(location.search);
    const year = Number(view.get("year"));
    const series = view.get("series") || "joint";
    const bbox = view.get("bbox") || "-122,39.5,-121.3,40.5";
    const preferredMonth = Number(view.get("month")) || 7;
    if (!Number.isInteger(year) || year < 2000 || year > 2100) return null;

    const params = new URLSearchParams({year: String(year), series, bbox});
    const response = await fetch(`/api/calendar?${params}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "The selected calendar is unavailable.");
    const hits = (data.daily || []).filter(item => Number(item.detected_cell_days) > 0)
      .sort((a, b) => {
        const monthA = Number(a.date_utc.slice(5, 7));
        const monthB = Number(b.date_utc.slice(5, 7));
        return Math.abs(monthA - preferredMonth) - Math.abs(monthB - preferredMonth)
          || Number(b.detected_cell_days) - Number(a.detected_cell_days)
          || a.date_utc.localeCompare(b.date_utc);
      });
    if (!hits.length) return null;

    const normalizedBbox = bbox.replace(/\s/g, "");
    const parkCaseDate = year === 2024 && preferredMonth === 7
      && normalizedBbox === "-122,39.5,-121.3,40.5" ? "2024-07-25" : null;
    const observation = (parkCaseDate && hits.find(item => item.date_utc === parkCaseDate)) || hits[0];
    const observationMonth = Number(observation.date_utc.slice(5, 7));
    if (observationMonth !== preferredMonth) {
      document.querySelectorAll("#monthly-bars .month-row")[observationMonth - 1]?.click();
      await waitFrame();
    }
    const dayButton = document.querySelector(`#day-grid [data-date="${observation.date_utc}"]`);
    if (!dayButton) return null;
    dayButton.click();
    const evidenceParams = new URLSearchParams({date: observation.date_utc, series, bbox});
    const evidenceResponse = await fetch(`/api/observations?${evidenceParams}`);
    const evidenceData = await evidenceResponse.json();
    if (!evidenceResponse.ok) throw new Error(evidenceData.error || "The selected source records are unavailable.");
    const deadline = Date.now() + 9000;
    while (Date.now() < deadline) {
      const sourceLink = document.querySelector("#calendar-day-summary .calendar-evidence-link");
      if (sourceLink && sourceLink.href.includes("/method.html")) {
        selectedEvidence = {
          date: observation.date_utc,
          count: Number(observation.detected_cell_days),
          sensorCounts: observation.raw_pixels_by_sensor || {},
          rows: (evidenceData.observations || []).length,
          truncated: Boolean(evidenceData.truncated),
          href: sourceLink.href
        };
        return selectedEvidence;
      }
      await new Promise(resolve => setTimeout(resolve, 80));
    }
    return null;
  }

  const steps = [
    {
      target: "#calendar-section .controls",
      title: "Choose an area and year",
      text: () => {
        const bbox = document.querySelector("#bbox")?.value || "the current area";
        const year = document.querySelector("#year")?.value || "the selected year";
        return `This calendar queries imported records inside ${bbox} for ${year}. The rectangle defines an area of interest; it is not a fire boundary.`;
      }
    },
    {
      target: "#firms-source-compare",
      title: "Compare the two sensors",
      text: () => {
        const modis = document.querySelector("#compare-modis")?.textContent || "—";
        const viirs = document.querySelector("#compare-viirs")?.textContent || "—";
        const joint = document.querySelector("#compare-joint")?.textContent || "—";
        return `This view shows ${modis} MODIS pixels and ${viirs} VIIRS S-NPP pixels; the joint result is ${joint} detected cell-days. Shared cells deduplicate same-day hits; this does not calibrate sensor sensitivity.`;
      }
    },
    {
      target: ".calendar-status-legend",
      title: "Read detections and gaps",
      text: () => "Each dated value is a detected 1 km cell-day in UTC. Incomplete or hatched dates are unknown, not evidence that no fire occurred. Satellite pass and cloud masks are not included."
    },
    {
      target: "#calendar-day-summary",
      title: "Inspect an original record",
      text: () => selectedEvidence
        ? selectedEvidence.rows
          ? `${selectedEvidence.date} has ${selectedEvidence.count.toLocaleString()} detected cell-days (${Object.entries(selectedEvidence.sensorCounts).map(([sensor, count]) => `${sensor}: ${Number(count).toLocaleString()} pixels`).join(" · ") || "source-specific count unavailable"}). ${selectedEvidence.rows.toLocaleString()}${selectedEvidence.truncated ? "+" : ""} original rows are available in the source inspector. Any source with no displayed detections still has unknown pass/cloud coverage.`
          : `${selectedEvidence.date} has ${selectedEvidence.count.toLocaleString()} calendar cell-days, but its source lookup returned no rows. Treat this as a data mismatch and do not infer more from the calendar.`
        : "No positive detected cell-day was available in this selection, so there is no source row to open. Missing observations remain unknown."
    }
  ];

  async function showStep(index) {
    step = Math.max(0, Math.min(steps.length - 1, index));
    const currentStep = step;
    back.disabled = step === 0;
    next.disabled = false;
    next.textContent = step === steps.length - 1 ? "Finish" : "Next →";
    counter.textContent = `${String(step + 1).padStart(2, "0")} / ${String(steps.length).padStart(2, "0")}`;
    progress.forEach((item, i) => item.classList.toggle("complete", i <= step));
    title.textContent = steps[step].title;
    copy.textContent = "Loading the current study…";

    let errorCopy = "";
    if (step === steps.length - 1) {
      next.disabled = true;
      try {
        await openAuthenticObservation();
      } catch (error) {
        errorCopy = `Source evidence could not be loaded: ${error.message}`;
      }
      if (!active || step !== currentStep) return;
      next.disabled = false;
      next.textContent = selectedEvidence?.rows ? "Open source rows ↗" : "Finish";
    }
    copy.textContent = errorCopy || steps[step].text();
    const target = step === steps.length - 1 && !selectedEvidence
      ? "#calendar-section .days-panel" : steps[step].target;
    setHighlight(document.querySelector(target));
    title.focus({preventScroll: true});
  }

  function closeTour(returnFocus = true) {
    active = false;
    panel.hidden = true;
    setHighlight(null);
    if (returnFocus) startButton.focus();
  }

  startButton.addEventListener("click", async () => {
    if (startButton.disabled) return;
    active = true;
    panel.hidden = false;
    panel.scrollIntoView({behavior: reduceMotion() ? "auto" : "smooth", block: "nearest"});
    await showStep(0);
  });
  back.addEventListener("click", () => { if (active && step > 0) showStep(step - 1); });
  next.addEventListener("click", () => {
    if (!active) return;
    if (step === steps.length - 1 && selectedEvidence?.rows && selectedEvidence.href) location.assign(selectedEvidence.href);
    else if (step === steps.length - 1) closeTour();
    else showStep(step + 1);
  });
  document.querySelector("#calendar-tour-skip").addEventListener("click", () => closeTour());
  document.querySelector("#calendar-tour-close").addEventListener("click", () => closeTour());
  document.addEventListener("keydown", event => {
    if (active && event.key === "Escape") closeTour();
  });
})();
