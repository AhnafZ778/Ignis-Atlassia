"""Small, cached NASA EONET wildfire-event feed.

EONET tracks reported events. Its locations are never treated as FIRMS pixels,
satellite coverage, or inputs to the sensor-aware calendar.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

EONET_URL = "https://eonet.gsfc.nasa.gov/api/v3/events/geojson?category=wildfires&status=open&limit=200"
CACHE_AGE = timedelta(hours=1)


def _utc(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("event timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize(payload: dict) -> list[dict]:
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
        raise ValueError("NASA EONET returned an unexpected event format")
    events = {}
    for feature in payload["features"]:
        if not isinstance(feature, dict) or not isinstance(feature.get("properties"), dict):
            continue
        props = feature["properties"]
        geometry = feature.get("geometry") or {}
        if not isinstance(geometry, dict):
            continue
        if geometry.get("type") != "Point" or not isinstance(geometry.get("coordinates"), list):
            continue
        try:
            lon, lat = map(float, geometry["coordinates"][:2])
            if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
                continue
            stamp = _utc(props["date"])
        except (KeyError, TypeError, ValueError):
            continue
        if not any(category.get("id") == "wildfires" for category in (props.get("categories") or []) if isinstance(category, dict)):
            continue
        event_id = str(props.get("id", ""))[:80]
        title = str(props.get("title", ""))[:180].strip()
        if not re.fullmatch(r"EONET_[A-Za-z0-9_-]+", event_id) or not title:
            continue
        sources = props.get("sources") or []
        source_names = [str(source.get("id", ""))[:35] for source in sources if isinstance(source, dict) and source.get("id")]
        events[event_id] = {
            "id": event_id, "title": title, "date_utc": stamp, "lon": lon, "lat": lat,
            "source_names": source_names[:3],
            "url": f"https://eonet.gsfc.nasa.gov/api/v3/events/{event_id}",
        }
    if not events and payload["features"]:
        raise ValueError("NASA EONET returned no usable wildfire event locations")
    return sorted(events.values(), key=lambda item: item["date_utc"], reverse=True)


def harvest(path: str | Path, *, opener=urlopen) -> dict:
    """Fetch a recent EONET sample, validate it, then replace the local cache."""
    request = Request(EONET_URL, headers={"User-Agent": "FireAtlas/1.0 (NASA Space Apps project)", "Accept": "application/geo+json, application/json"})
    try:
        with opener(request, timeout=15) as response:
            body = response.read(5_000_001)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ValueError("NASA EONET could not be reached; the last cached event feed is retained") from exc
    if len(body) > 5_000_000:
        raise ValueError("NASA EONET response exceeded the event-feed limit")
    try:
        events = _normalize(json.loads(body))
    except (UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError("NASA EONET returned invalid event data") from exc
    snapshot = {
        "source": "NASA EONET", "kind": "reported-wildfire-events", "fetched_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "count": len(events), "sample_limit": 200, "events": events,
        "note": "Reported wildfire events and locations, not FIRMS satellite detections or a complete global incident count.",
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(json.dumps(snapshot, separators=(",", ":")) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return snapshot


def latest(path: str | Path, *, refresh: bool = False, opener=urlopen) -> dict:
    """Serve a fresh snapshot; fall back to the last valid cache if NASA is down."""
    path = Path(path)
    cached = None
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(cached, dict) or cached.get("kind") != "reported-wildfire-events" or not isinstance(cached.get("events"), list):
            cached = None
    except (OSError, ValueError, TypeError):
        cached = None
    if cached and not refresh:
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(cached["fetched_utc"].replace("Z", "+00:00"))
            if timedelta(0) <= age < CACHE_AGE:
                return {**cached, "stale": False}
        except (KeyError, TypeError, ValueError):
            pass
    try:
        return {**harvest(path, opener=opener), "stale": False}
    except ValueError:
        if cached:
            return {**cached, "stale": True}
        raise
