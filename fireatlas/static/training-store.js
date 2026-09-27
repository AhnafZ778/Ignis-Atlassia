/* Per-tab recovery. API responses are never placed in the service-worker cache. */
(function (root) {
  "use strict";
  const KEY = "fireatlas.training.tab.v1";
  const FORMAT = "fireatlas-training-recovery-v1";
  const finiteTime = value => typeof value === "string" && Number.isFinite(Date.parse(value));
  const point = p => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite);
  function validate(record) {
    try {
      const {scenario, snapshot, elapsed, acknowledgments, heldGps} = record;
      if (record.format !== FORMAT || scenario.synthetic !== true || snapshot.synthetic !== true ||
          scenario.id !== snapshot.scenario_id || scenario.version !== snapshot.scenario_version ||
          !Number.isInteger(elapsed) || elapsed < 0 || elapsed > scenario.duration_seconds ||
          !Number.isInteger(snapshot.elapsed_seconds) || snapshot.elapsed_seconds < 0 || snapshot.elapsed_seconds > elapsed ||
          !finiteTime(scenario.start_utc) || !finiteTime(snapshot.as_of_utc) || !finiteTime(snapshot.valid_until_utc) ||
          Date.parse(snapshot.as_of_utc) !== Date.parse(scenario.start_utc) + snapshot.elapsed_seconds * 1000 ||
          !/^[a-f0-9]{64}$/.test(snapshot.snapshot_id) || !["commander", "crew"].includes(record.view) ||
          ![60,300].includes(record.speed) || typeof record.manualOffline !== "boolean" ||
          !Array.isArray(scenario.bounds) || !scenario.bounds.every(point) || !point(scenario.staging)) return false;
      const known = time => finiteTime(time) && Date.parse(time) <= Date.parse(snapshot.as_of_utc);
      if (!known(snapshot.zone.published_utc) || !known(snapshot.zone.observed_utc) || !known(snapshot.route.published_utc) ||
          !finiteTime(snapshot.route.expires_utc) || !snapshot.zone.geometry.coordinates[0].every(point) ||
          !snapshot.route.geometry.coordinates.every(point) || !snapshot.events.every(e => known(e.published_utc)) ||
          !snapshot.observations.every(o => known(o.available_utc) && known(o.acquisition_utc) && point(o.coordinates)) ||
          !snapshot.crews.length || !snapshot.crews.every(c => point(c.position) && known(c.position_utc) && known(c.heartbeat_utc) && Number.isFinite(c.accuracy_m)) ||
          !snapshot.crews.some(c => c.id === record.selected) || !Object.values(snapshot.rules).every(Number.isFinite)) return false;
      const replayTime = Date.parse(scenario.start_utc) + elapsed * 1000;
      if (!Array.isArray(acknowledgments) || acknowledgments.length > 2000 || !acknowledgments.every(a =>
          ["route", "alert"].includes(a.kind) && typeof a.target_id === "string" && typeof a.crew_id === "string" &&
          typeof a.title === "string" && Number.isInteger(a.elapsed_seconds) && a.elapsed_seconds >= 0 && a.elapsed_seconds <= elapsed &&
          Date.parse(a.replay_utc) === Date.parse(scenario.start_utc) + a.elapsed_seconds * 1000)) return false;
      if (!heldGps || typeof heldGps !== "object" || !Object.entries(heldGps).every(([id, fix]) =>
          snapshot.crews.some(c => c.id === id) && point(fix.position) && Number.isFinite(fix.accuracy_m) &&
          finiteTime(fix.position_utc) && Date.parse(fix.position_utc) <= replayTime)) return false;
      return true;
    } catch { return false; }
  }
  function capture(state) {
    return {format: FORMAT, saved_utc: new Date().toISOString(), scenario: state.scenario, snapshot: state.snapshot,
      elapsed: state.elapsed, view: state.view, selected: state.selected, speed: state.speed,
      manualOffline: state.manualOffline, heldGps: state.heldGps, acknowledgments: state.acknowledgments};
  }
  function save(storage, state) {
    const record = capture(state);
    if (!validate(record)) throw new Error("Exercise recovery data could not be validated.");
    storage.setItem(KEY, JSON.stringify(record));
  }
  function read(storage) {
    const raw = storage.getItem(KEY);
    if (!raw) return null;
    const record = JSON.parse(raw);
    if (!validate(record)) throw new Error("The saved exercise is incomplete or incompatible.");
    return record;
  }
  function clear(storage) { storage.removeItem(KEY); }
  const api = {KEY, FORMAT, validate, capture, save, read, clear};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TrainingStore = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
