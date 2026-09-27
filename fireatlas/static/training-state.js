/* Pure exercise rules, shared by the UI and the offline-state tests. */
(function (root) {
  "use strict";
  const age = (now, value) => Math.max(0, (now - Date.parse(value)) / 1000);
  const cross = (a, b, c) => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
  function onSegment(a, b, p) {
    return Math.abs(cross(a, b, p)) < 1e-12 && p[0] >= Math.min(a[0], b[0]) - 1e-12 &&
      p[0] <= Math.max(a[0], b[0]) + 1e-12 && p[1] >= Math.min(a[1], b[1]) - 1e-12 && p[1] <= Math.max(a[1], b[1]) + 1e-12;
  }
  function inside(point, ring) {
    let result = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const a = ring[i], b = ring[j];
      if (onSegment(a, b, point)) return true;
      if ((a[1] > point[1]) !== (b[1] > point[1]) && point[0] < (b[0] - a[0]) * (point[1] - a[1]) / (b[1] - a[1]) + a[0]) result = !result;
    }
    return result;
  }
  function intersects(a, b, c, d) {
    return (cross(a, b, c) * cross(a, b, d) < 0 && cross(c, d, a) * cross(c, d, b) < 0) ||
      onSegment(a, b, c) || onSegment(a, b, d) || onSegment(c, d, a) || onSegment(c, d, b);
  }
  function routeOverlaps(line, ring) {
    if (line.some(p => inside(p, ring))) return true;
    for (let i = 1; i < line.length; i++) {
      for (let j = 1; j < ring.length; j++) if (intersects(line[i - 1], line[i], ring[j - 1], ring[j])) return true;
    }
    return false;
  }
  function nearZone(point, ring, radius) {
    // Local, synthetic exercise only: equirectangular distances in meters.
    const project = p => [(p[0] - point[0]) * 111320 * Math.cos(point[1] * Math.PI / 180), (p[1] - point[1]) * 111320];
    for (let i = 1; i < ring.length; i++) {
      const a = project(ring[i - 1]), b = project(ring[i]);
      const dx = b[0] - a[0], dy = b[1] - a[1];
      const t = Math.max(0, Math.min(1, -(a[0] * dx + a[1] * dy) / (dx * dx + dy * dy || 1)));
      if (Math.hypot(a[0] + t * dx, a[1] + t * dy) <= radius) return true;
    }
    return false;
  }
  function assess(snapshot, now, options = {}) {
    const rules = snapshot.rules, ring = snapshot.zone.geometry.coordinates[0];
    const expiredSnapshot = now >= Date.parse(snapshot.valid_until_utc);
    const alerts = [];
    const crews = snapshot.crews.map(report => {
      const crew = {...report, ...(options.heldGps?.[report.id] || {})};
      const gpsAge = age(now, crew.position_utc), heartbeatAge = age(now, crew.heartbeat_utc);
      const reasons = [];
      if (options.offline) reasons.push("Connection unavailable");
      if (!crew.connected || heartbeatAge > rules.heartbeat_max_age_seconds) reasons.push("Crew heartbeat unavailable");
      if (expiredSnapshot) reasons.push("Snapshot expired");
      if (gpsAge > rules.gps_max_age_seconds) reasons.push("GPS fix is stale");
      if (crew.accuracy_m > rules.accuracy_max_m) reasons.push("Location accuracy is insufficient");
      let status = "observed", label = "No zone overlap", detail = "Latest position is outside the scripted zone. Conditions along the route are unverified.";
      if (reasons.length) { status = "unknown"; label = "Status unknown"; detail = reasons.join(" · "); }
      else if (inside(crew.position, ring)) { status = "critical"; label = "Inside exercise zone"; detail = "A fresh simulated position intersects the published zone. Acknowledge and review with the exercise commander."; }
      else if (nearZone(crew.position, ring, crew.accuracy_m)) { status = "caution"; label = "Accuracy overlaps zone"; detail = "The reported accuracy circle overlaps the zone. The exact position is uncertain."; }
      if (status !== "observed") alerts.push({
        id: `${crew.id}:${status}:${snapshot.zone.id}:${reasons.join("|")}`,
        crew_id: crew.id, severity: status, title: `${crew.name}: ${label.toLowerCase()}`, detail,
      });
      return {...crew, status, label, detail, gpsAge, heartbeatAge};
    });
    const route = snapshot.route;
    let routeStatus = "current", routeLabel = "Current exercise route";
    if (now >= Date.parse(route.expires_utc)) { routeStatus = "expired"; routeLabel = "Route expired"; }
    else if (!route.approved) { routeStatus = "unapproved"; routeLabel = "Awaiting exercise approval"; }
    else if (options.offline || expiredSnapshot) { routeStatus = "unknown"; routeLabel = "Route status unknown"; }
    else if (routeOverlaps(route.geometry.coordinates, ring)) { routeStatus = "conflict"; routeLabel = "Route intersects exercise zone"; }
    if (routeStatus !== "current") alerts.push({
      id: `${route.id}:${snapshot.zone.id}:${routeStatus}`, crew_id: null,
      severity: routeStatus === "conflict" ? "critical" : routeStatus === "unknown" ? "unknown" : "caution",
      title: routeLabel, detail: routeStatus === "expired" ? "The published validity time has passed. The route is retained only as historical context."
        : routeStatus === "conflict" ? "The published zone crosses the route. Its previous approval does not resolve this conflict."
        : routeStatus === "unapproved" ? "This route has no exercise commander approval."
        : "A current route cannot be confirmed from this connection or snapshot.",
    });
    return {crews, alerts, routeStatus, routeLabel, expiredSnapshot, snapshotAge: age(now, snapshot.as_of_utc)};
  }
  const api = {assess, inside, routeOverlaps, nearZone};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TrainingState = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
