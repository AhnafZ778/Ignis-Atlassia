/* Shared study context, navigation and status helpers. */
(() => {
  const DEFAULTS = Object.freeze({
    year: 2024, month: 7, bbox: "-122,39,-120,41", as_of: "2024-07-31",
    series: "joint", day: "", distance_km: 2, gap_days: 1, region: "norcal", layer: "ndvi"
  });
  const allowedSeries = new Set(["joint", "modis", "viirs-snpp", "hms-viirs", "viirs-noaa20", "viirs-noaa20-nrt", "viirs-noaa21-nrt", "viirs-snpp-nrt", "modis-nrt"]);
  const allowedLayers = new Set(["none", "ndvi", "landcover", "fwi"]);
  const allowedRegions = new Set(["norcal", "punjab-haryana"]);
  const validBBox = (value, strict = false) => {
    const parts = String(value || "").split(",").map(item => item.trim() === "" ? NaN : Number(item));
    const valid = parts.length === 4 && parts.every(Number.isFinite) && parts[0] >= -180 && parts[2] <= 180 &&
      parts[1] >= -90 && parts[3] <= 90 && parts[0] < parts[2] && parts[1] < parts[3];
    if (!valid && strict) throw new Error("Enter four coordinates: west, south, east, north. West must be less than east; south must be less than north, within longitude ±180 and latitude ±90.");
    return valid ? parts.map(value => Number(value.toFixed(6))).join(",") : DEFAULTS.bbox;
  };
  const validDate = value => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return false;
    const parsed = new Date(`${value}T00:00:00Z`);
    return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
  };
  const integer = (value, fallback, min, max) => {
    if (value === null || value === undefined || value === "") return fallback;
    const number = Number(value);
    return Number.isInteger(number) && number >= min && number <= max ? number : fallback;
  };
  const number = (value, fallback, min, max) => {
    if (value === null || value === undefined || value === "") return fallback;
    const result = Number(value);
    return Number.isFinite(result) && result >= min && result <= max ? result : fallback;
  };
  function read(search = location.search) {
    const params = new URLSearchParams(search);
    const context = {...DEFAULTS};
    context.year = integer(params.get("year"), DEFAULTS.year, 2000, 2100);
    context.month = integer(params.get("month"), DEFAULTS.month, 1, 12);
    context.bbox = validBBox(params.get("bbox") || DEFAULTS.bbox);
    const lastDay = new Date(Date.UTC(context.year, context.month, 0)).getUTCDate();
    const monthEnd = `${context.year}-${String(context.month).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`;
    const asOf = params.get("as_of");
    context.as_of = validDate(asOf) && asOf.slice(0, 7) === `${context.year}-${String(context.month).padStart(2, "0")}` ? asOf : monthEnd;
    context.series = allowedSeries.has(params.get("series")) ? params.get("series") : DEFAULTS.series;
    const day = params.get("day");
    context.day = validDate(day) && day.slice(0, 7) === `${context.year}-${String(context.month).padStart(2, "0")}` ? day : "";
    context.distance_km = number(params.get("distance_km"), DEFAULTS.distance_km, .5, 10);
    context.gap_days = integer(params.get("gap_days"), DEFAULTS.gap_days, 0, 7);
    context.region = allowedRegions.has(params.get("region")) ? params.get("region") : DEFAULTS.region;
    context.layer = allowedLayers.has(params.get("layer")) ? params.get("layer") : DEFAULTS.layer;
    return context;
  }
  function write(context, options = {}) {
    const merged = {...DEFAULTS, ...context};
    const params = new URLSearchParams();
    for (const key of ["year", "month", "bbox", "as_of", "series", "day", "distance_km", "gap_days", "region", "layer"]) {
      const value = merged[key];
      if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
    }
    const query = params.toString();
    if (options.path) return `${options.path}${query ? `?${query}` : ""}${options.hash || ""}`;
    return query ? `?${query}` : "";
  }
  function api(context, keys = ["year", "month", "bbox", "as_of", "series", "day", "distance_km", "gap_days"]) {
    const params = new URLSearchParams();
    for (const key of keys) if (context[key] !== undefined && context[key] !== "") params.set(key, context[key]);
    if (context.bbox) params.set("bbox", context.bbox);
    return params;
  }
  function link(path, overrides = {}) {
    const target = new URL(path, location.href);
    const parameters = new URLSearchParams(write({...read(), ...overrides}));
    // Retain route-specific options without appending study parameters twice.
    for (const [key, value] of target.searchParams) if (!parameters.has(key)) parameters.set(key, value);
    target.search = parameters.toString();
    return `${target.pathname}${target.search}${target.hash}`;
  }
  function apply(root = document, context = read()) {
    root.querySelectorAll("[data-context-field]").forEach(node => {
      const key = node.dataset.contextField;
      if (context[key] === undefined) return;
      node.value = context[key];
    });
    root.querySelectorAll("[data-context-link]").forEach(node => {
      const path = node.dataset.contextLink || node.getAttribute("href") || "/";
      node.href = link(path, context);
    });
    root.querySelectorAll("#site-navigation a[data-page-link]").forEach(node => {
      const target = new URL(node.getAttribute("href") || "/", location.href);
      node.href = link(`${target.pathname}${target.hash}`, context);
    });
    return context;
  }
  function nav() {
    const page = document.body.dataset.page;
    if (!page) return;
    document.querySelectorAll("#site-navigation a[data-page-link]").forEach(node => {
      const active = node.dataset.pageLink === page;
      node.classList.toggle("active", active);
      if (active) node.setAttribute("aria-current", "page"); else node.removeAttribute("aria-current");
    });
  }
  function status(node, message, kind = "unknown") {
    if (!node) return;
    node.textContent = message;
    node.classList.remove("available", "partial", "unavailable", "unknown");
    node.classList.add(kind);
  }
  window.FireAtlasContext = {DEFAULTS, read, write, api, link, apply, nav, status, validBBox};
  document.addEventListener("DOMContentLoaded", () => {
    const context = apply();
    nav();
    if (document.body.classList.contains("scientific-workspace")) {
      const supplied = new URLSearchParams(location.search), invalid = [];
      for (const key of Object.keys(DEFAULTS)) {
        if (!supplied.has(key) || supplied.get(key) === "") continue;
        const raw = supplied.get(key);
        if (key === "bbox") { try { validBBox(raw, true); } catch (_) { invalid.push("study area"); } }
        else if (["year","month","distance_km","gap_days"].includes(key)) { if (Number(raw) !== context[key]) invalid.push(key.replaceAll("_"," ")); }
        else if (raw !== String(context[key])) invalid.push(key.replaceAll("_"," "));
      }
      if (invalid.length) {
        const notice = document.createElement("p"); notice.className = "notice-panel context-default-notice"; notice.setAttribute("role","status");
        notice.textContent = `This study link contained invalid settings (${invalid.join(", ")}). The controls show the defaults used for this page; check them before running analysis.`;
        document.querySelector("#main-content")?.prepend(notice);
      }
    }
    document.dispatchEvent(new CustomEvent("fireatlas:context-ready", {detail: context}));
  });
})();
