(() => {
  const $ = id => document.getElementById(id);
  const number = value => Number(value || 0).toLocaleString();
  async function staticMeta() {
    const root = document.querySelector('meta[name="fireatlas-static-data"]')?.content;
    if (!root) return null;
    const base = new URL(root, document.baseURI);
    const [regionsResponse, manifestResponse] = await Promise.all([
      fetch(new URL("regions.json", base)), fetch(new URL("manifest.json", base))
    ]);
    if (!regionsResponse.ok || !manifestResponse.ok) throw new Error("bundled archive metadata unavailable");
    const regionData = await regionsResponse.json(), manifest = await manifestResponse.json();
    const regions = regionData.regions || [];
    const sourceCounts = {};
    let paired = false;
    for (const region of regions) {
      const products = region.products || {};
      for (const [source, product] of Object.entries(products)) {
        sourceCounts[source] = (sourceCounts[source] || 0) + Number(product.imported_detection_rows || 0);
      }
      const modis = new Set(products.MODIS_SP?.complete_months || []);
      paired ||= (products.VIIRS_SNPP_SP?.complete_months || []).some(month => modis.has(month));
    }
    return {source_counts: sourceCounts, years: [Number(manifest.calendar_start_year), Number(manifest.calendar_end_year)], standard_pair_ready: paired};
  }
  function render(meta) {
    const counts = meta.source_counts || {};
    const imported = Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0);
    $("landing-detections").textContent = imported ? number(imported) : "—";
    const years = (meta.years || []).filter(Number.isFinite);
    $("landing-period").textContent = years.length ? `${Math.min(...years)}–${Math.max(...years)}` : "—";
    const complete = meta.standard_pair_ready;
    $("landing-archive-status").textContent = complete ? "Paired archive ready" : (years.length ? "Partial archive" : "Awaiting import");
    $("landing-detections-note").textContent = complete ? "MODIS + VIIRS records in the available archive" : "Imported source rows currently available";
    $("landing-period-note").textContent = years.length ? "Years represented by the archive" : "No archive years reported";
    $("landing-status-note").textContent = complete ? "Comparable MODIS and VIIRS archive windows are available" : "Open Data sources to inspect gaps";
  }
  document.addEventListener("DOMContentLoaded", async () => {
    try {
      if (document.querySelector('meta[name="fireatlas-static-data"]')) {
        render(await staticMeta());
        return;
      }
      const response = await fetch("/api/meta", {signal: AbortSignal.timeout(12000)});
      if (!response.ok) throw new Error("archive unavailable");
      render(await response.json());
    } catch (_) {
      $("landing-archive-status").textContent = "Status unavailable";
      $("landing-status-note").textContent = "The local analysis service is unavailable";
    }
  });
})();
