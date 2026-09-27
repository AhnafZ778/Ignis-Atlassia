from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from fireatlas.events import harvest, latest


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class EventHarvestTests(unittest.TestCase):
    def test_harvest_preserves_reported_events_without_creating_sensor_records(self):
        payload = {"type": "FeatureCollection", "features": [
            {"properties": {"id": "EONET_123", "title": "Reported wildfire", "date": "2026-09-27T01:00:00Z",
                            "categories": [{"id": "wildfires"}], "sources": [{"id": "IRWIN"}]},
             "geometry": {"type": "Point", "coordinates": [-121.5, 40.1]}},
            {"properties": {"id": "EONET_124", "title": "Storm", "date": "2026-09-27T02:00:00Z",
                            "categories": [{"id": "severeStorms"}]},
             "geometry": {"type": "Point", "coordinates": [-120, 39]}},
        ]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.json"
            called = []
            def opener(request, timeout):
                called.append((request.full_url, timeout))
                return _Response(json.dumps(payload).encode())
            snapshot = harvest(path, opener=opener)
            self.assertEqual(snapshot["count"], 1)
            self.assertEqual(snapshot["kind"], "reported-wildfire-events")
            self.assertEqual(snapshot["events"][0]["source_names"], ["IRWIN"])
            self.assertEqual(snapshot["events"][0]["lon"], -121.5)
            self.assertEqual(len(called), 1)
            self.assertEqual(latest(path, opener=lambda *_a, **_k: self.fail("fresh cache should be used"))["count"], 1)

    def test_stale_cache_survives_connection_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.json"
            path.write_text(json.dumps({"kind": "reported-wildfire-events", "fetched_utc": "2020-01-01T00:00:00Z",
                                        "count": 1, "events": [{"id": "EONET_123"}]}))
            def failure(*_args, **_kwargs):
                raise OSError("connection failed")
            self.assertTrue(latest(path, opener=failure)["stale"])
            with self.assertRaisesRegex(ValueError, "EONET could not be reached"):
                latest(Path(directory) / "missing.json", opener=failure)

    def test_invalid_nasa_response_does_not_replace_cached_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.json"
            path.write_text('{"kind":"reported-wildfire-events","events":[{"id":"EONET_123"}]}')
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "unexpected event format"):
                harvest(path, opener=lambda *_a, **_k: _Response(b'{"not":"geojson"}'))
            self.assertEqual(path.read_bytes(), before)

    def test_empty_event_sample_is_a_valid_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.json"
            snapshot = harvest(path, opener=lambda *_a, **_k: _Response(b'{"type":"FeatureCollection","features":[]}'))
            self.assertEqual(snapshot["count"], 0)
            self.assertFalse(latest(path)["stale"])


if __name__ == "__main__":
    unittest.main()
