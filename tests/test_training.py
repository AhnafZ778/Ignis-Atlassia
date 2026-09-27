import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from fireatlas.training import public_scenario, snapshot, stamp


class TrainingTests(unittest.TestCase):
    def test_publication_boundaries_and_rewind(self):
        self.assertEqual(snapshot(599)["observations"], [])
        self.assertEqual(len(snapshot(600)["observations"]), 1)
        self.assertEqual(snapshot(1199)["zone"]["id"], "zone-1")
        self.assertEqual(snapshot(1200)["zone"]["id"], "zone-2")
        self.assertEqual(snapshot(1799)["route"]["id"], "route-1")
        self.assertEqual(snapshot(1800)["route"]["id"], "route-2")
        snapshot(3600)
        self.assertEqual(snapshot(0)["observations"], [])
        self.assertEqual(len(snapshot(0)["events"]), 1)
        for offset in range(0, 3601, 30):
            data = snapshot(offset)
            for item in data["observations"]:
                self.assertLessEqual(item["acquisition_utc"], stamp(offset))
                self.assertLessEqual(item["available_utc"], stamp(offset))
            for item in data["events"]:
                self.assertLessEqual(item["published_utc"], stamp(offset))

    def test_deterministic_hash_and_invalid_time(self):
        data = snapshot(1200)
        expected = data.pop("snapshot_id")
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        self.assertEqual(hashlib.sha256(canonical.encode()).hexdigest(), expected)
        self.assertEqual(snapshot(1200)["snapshot_id"], expected)
        for value in [-1, 3601, 1.5, True]:
            with self.assertRaises(ValueError):
                snapshot(value)

    def test_client_rules_for_offline_gps_and_route_transitions(self):
        root = Path(__file__).resolve().parent.parent
        fixtures = {str(t): snapshot(t) for t in [0, 1200, 1320, 1500, 1800, 2100, 2760, 3000]}
        script = r"""
const assert = require('node:assert/strict');
const {assess, routeOverlaps, inside} = require('./fireatlas/static/training-state.js');
const fixtures = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const at = (time, options={}) => assess(fixtures[time], Date.parse(fixtures[time].as_of_utc), options);
assert.equal(at(0).routeStatus, 'current');
assert.equal(at(1200).routeStatus, 'conflict');
assert.equal(at(1200).crews.find(c => c.id === 'alpha').status, 'critical');
assert.equal(at(1320).crews.find(c => c.id === 'bravo').status, 'unknown');
assert.equal(at(1500).routeStatus, 'expired');
assert.equal(at(1800).routeStatus, 'current');
assert.equal(at(2100).crews.find(c => c.id === 'delta').status, 'unknown');
assert.equal(at(2760).crews.find(c => c.id === 'delta').status, 'observed');
assert.equal(at(3000).routeStatus, 'expired');
assert(at(0, {offline: true}).crews.every(c => c.status === 'unknown'));
assert.equal(at(0, {offline: true}).routeStatus, 'unknown');
const old = fixtures[0], future = Date.parse(old.as_of_utc) + 1500 * 1000;
const cached = assess(old, future, {offline: true});
assert.equal(cached.routeStatus, 'expired');
assert.equal(cached.expiredSnapshot, true);
assert(cached.crews.every(c => c.status === 'unknown'));
const stale = at(1800, {heldGps: {alpha: {position_utc: fixtures[0].as_of_utc}}});
assert.equal(stale.crews.find(c => c.id === 'alpha').status, 'unknown');
const ring = [[0,0],[1,0],[1,1],[0,1],[0,0]];
assert(routeOverlaps([[-1,.5],[2,.5]], ring), 'Crossing segments with exterior endpoints must overlap');
assert(inside([0,.5], ring), 'Boundary is included');
assert(!routeOverlaps([[-1,-1],[-1,2]], ring));
console.log('Replay state rules passed');
"""
        result = subprocess.run(["node", "-e", script], input=json.dumps(fixtures), text=True,
                                cwd=root, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_recovery_preserves_state_and_rejects_future_or_corrupt_evidence(self):
        root = Path(__file__).resolve().parent.parent
        fixtures = {"scenario": public_scenario(), "snapshot": snapshot(1200)}
        script = r"""
const assert = require('node:assert/strict');
const store = require('./fireatlas/static/training-store.js');
const fixtures = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const data = new Map();
const storage = {getItem:key=>data.get(key)||null,setItem:(key,value)=>data.set(key,value),removeItem:key=>data.delete(key)};
const state = {...fixtures,elapsed:1500,view:'crew',selected:'alpha',speed:300,manualOffline:true,heldGps:{},
  acknowledgments:[{kind:'alert',target_id:'test',crew_id:'alpha',title:'Local test',elapsed_seconds:1200,replay_utc:fixtures.snapshot.as_of_utc}]};
store.save(storage,state);
const restored = store.read(storage);
assert.equal(restored.elapsed,1500);
assert.equal(restored.snapshot.elapsed_seconds,1200);
assert.equal(restored.acknowledgments.length,1);
assert.equal(restored.manualOffline,true);
assert.equal(restored.playing,undefined);
assert.equal(restored.sound,undefined);
for (const mutate of [
  r=>r.elapsed=1199,
  r=>r.scenario.version='incompatible',
  r=>r.snapshot.events[0].published_utc='2024-07-01T13:00:00Z',
  r=>r.snapshot.observations[0].available_utc='2024-07-01T13:00:00Z',
  r=>r.acknowledgments[0].elapsed_seconds=1600,
  r=>r.snapshot.crews[0].heartbeat_utc='2024-07-01T13:00:00Z',
  r=>r.snapshot.zone.geometry=null,
  r=>r.selected='missing'
]) {
 const altered=structuredClone(restored);mutate(altered);assert.equal(store.validate(altered),false);
}
data.set(store.KEY,'{broken');assert.throws(()=>store.read(storage));
assert.throws(()=>store.save({setItem(){throw new Error('blocked')}},state));
store.clear(storage);assert.equal(store.read(storage),null);
console.log('Training recovery checks passed');
"""
        result = subprocess.run(["node", "-e", script], input=json.dumps(fixtures), text=True,
                                cwd=root, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
