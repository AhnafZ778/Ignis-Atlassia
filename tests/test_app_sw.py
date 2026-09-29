"""Exercise the app service worker's online/offline data boundary."""

import subprocess
import unittest
from pathlib import Path


class AppServiceWorkerTests(unittest.TestCase):
    def test_only_explicit_synthetic_api_responses_replay_offline(self):
        script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const listeners = {};
const entries = new Map();
let online = true;
const cache = {
  put: async (request, response) => { entries.set(request.url, response); },
  match: async request => entries.get(request.url) || null
};
const context = {
  URL, Response, Headers, Set, JSON,
  self: {location:{origin:'https://fireatlas.test'}, addEventListener:(type, listener) => {listeners[type]=listener;}},
  caches: {open:async () => cache},
  fetch:async request => {
    if (!online) throw Error('disconnected');
    return new Response(JSON.stringify({source:request.url}), {headers:{'Content-Type':'application/json'}});
  }
};
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), context);
async function request(path) {
  const pending = [];
  let response;
  const event = {
    request:{url:'https://fireatlas.test'+path, method:'GET'},
    waitUntil:promise => pending.push(promise),
    respondWith:promise => {response=promise;}
  };
  listeners.fetch(event);
  assert.ok(response, 'service worker handled API request');
  const result = await response;
  await Promise.all(pending);
  return result;
}
(async () => {
  assert.equal((await request('/api/calendar?demo=1')).status, 200);
  assert.equal((await request('/api/calendar?demo=0')).status, 200);
  assert.equal((await request('/api/events?demo=1')).status, 200);
  online = false;
  const demo = await request('/api/calendar?demo=1');
  assert.equal(demo.status, 200);
  assert.equal(demo.headers.get('X-FireAtlas-Offline-Example'), '1');
  assert.equal((await request('/api/calendar?demo=0')).status, 503);
  assert.equal((await request('/api/events?demo=1')).status, 503);
  assert.equal((await request('/api/harmonization?demo=1')).status, 503);
})().catch(error => {console.error(error); process.exitCode=1;});
"""
        worker = Path(__file__).resolve().parents[1] / "fireatlas/static/app-sw.js"
        result = subprocess.run(["node", "-e", script, str(worker)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
