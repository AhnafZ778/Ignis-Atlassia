(() => {
  const legacy = new Set(["#atlas-section", "#calendar-section", "#harmonized-calendar", "#study-workspace"]);
  if ((location.pathname === "/" || location.pathname === "/index.html") && legacy.has(location.hash)) {
    location.replace(`/atlas.html${location.search}${location.hash}`);
  }
})();
