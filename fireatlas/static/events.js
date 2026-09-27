// NASA EONET reported events are a separate visual feed, never calendar pixels.
(() => {
  const $ = id => document.getElementById(id);
  const formatDate = stamp => new Intl.DateTimeFormat("en", {timeZone:"UTC",month:"short",day:"numeric",year:"numeric"}).format(new Date(stamp));
  let map, points, eventMarkers = new Map(), selectedId, overview = [23,0];

  function resetView() { if (map) map.flyTo(overview, matchMedia("(max-width:760px)").matches ? 3 : 4, {duration:1}); }

  function initMap() {
    if (typeof L === "undefined") {
      $("events-status").textContent = "Map tiles are unavailable; event links remain accessible.";
      return;
    }
    map = L.map("event-map", {scrollWheelZoom:false, worldCopyJump:true, minZoom:2}).setView(overview, 2);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution:"&copy; OpenStreetMap contributors", maxZoom:18, className:"atlas-basemap",
    }).addTo(map);
    points = L.layerGroup().addTo(map);
  }

  function select(event, focusMap = true) {
    selectedId = event.id;
    document.querySelectorAll(".event-card").forEach(card => {
      const active = card.dataset.eventId === selectedId;
      card.classList.toggle("selected", active);
      card.setAttribute("aria-pressed", String(active));
    });
    const marker = eventMarkers.get(event.id);
    if (marker && map) {
      if (focusMap) {
        map.once("moveend", () => marker.openPopup());
        map.flyTo([event.lat, event.lon], 6, {duration:1.1});
        $("event-map").scrollIntoView({behavior:"smooth",block:"center"});
      } else marker.openPopup();
    }
  }

  function render(data) {
    $("event-count").textContent = data.count.toLocaleString();
    $("event-updated").textContent = `Fetched ${formatDate(data.fetched_utc)} · ${data.stale ? "cached copy" : "NASA EONET"}`;
    $("events-status").textContent = data.stale
      ? "NASA is temporarily unreachable. Showing the last cached event snapshot."
      : data.count ? "Recent reported event locations · select one to explore." : "No point locations in NASA’s current event sample.";
    const list = $("event-list"); list.replaceChildren();
    eventMarkers.clear();
    if (points) points.clearLayers();
    for (const event of data.events) {
      if (!map || !points) continue;
      const marker = L.circleMarker([event.lat,event.lon], {
        radius:5, color:"#d4ede8", weight:1.3, fillColor:"#8bc5bc", fillOpacity:.85,
      }).addTo(points);
      const popup = document.createElement("div");
      const title = document.createElement("strong"); title.textContent = event.title;
      const detail = document.createElement("p"); detail.textContent = `${formatDate(event.date_utc)} · ${event.source_names.join(" + ") || "Reported event"}`;
      const link = document.createElement("a"); link.href = event.url; link.target = "_blank"; link.rel = "noopener noreferrer"; link.textContent = "NASA event record ↗";
      popup.append(title,detail,link); marker.bindPopup(popup, {minWidth:170,maxWidth:matchMedia("(max-width:760px)").matches ? 205 : 245,autoPanPadding:[18,18]});
      marker.on("click", () => select(event, false));
      eventMarkers.set(event.id, marker);
    }
    if (map && data.events.length) {
      const midpoint = values => { const ordered = [...values].sort((a,b) => a-b); return ordered[Math.floor(ordered.length / 2)]; };
      overview = [midpoint(data.events.map(event => event.lat)), midpoint(data.events.map(event => event.lon))];
      resetView();
    }
    for (const event of data.events.slice(0, 8)) {
      const card = document.createElement("button"); card.type = "button"; card.className = "event-card"; card.dataset.eventId = event.id;
      const eyebrow = document.createElement("span"); eyebrow.textContent = `${formatDate(event.date_utc).toUpperCase()} / ${event.source_names[0] || "EONET"}`;
      const name = document.createElement("strong"); name.textContent = event.title;
      const coords = document.createElement("small"); coords.textContent = `${Math.abs(event.lat).toFixed(2)}° ${event.lat < 0 ? "S" : "N"} · ${Math.abs(event.lon).toFixed(2)}° ${event.lon < 0 ? "W" : "E"}`;
      card.append(eyebrow,name,coords);
      card.addEventListener("click", () => select(event));
      list.append(card);
    }
    if (map) setTimeout(() => map.invalidateSize(), 0);
  }

  async function load(refresh = false) {
    $("event-refresh").disabled = true;
    $("events-status").textContent = refresh ? "Checking NASA for newer reports…" : "Loading recent events…";
    try {
      const response = await fetch(`/api/events${refresh ? "?refresh=1" : ""}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "NASA event feed unavailable");
      render(data);
    } catch (error) {
      $("events-status").textContent = `${error.message}. Try Refresh later.`;
      $("event-updated").textContent = "Feed unavailable";
    } finally { $("event-refresh").disabled = false; }
  }

  document.addEventListener("DOMContentLoaded", () => {
    initMap();
    $("event-refresh").addEventListener("click", () => load(true));
    $("event-reset").addEventListener("click", resetView);
    load();
  });
})();
