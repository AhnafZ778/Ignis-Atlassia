"""Deterministic, synthetic training fixtures. Only published evidence leaves the server."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json

SCENARIO_ID = "alder-creek-01"
SCENARIO_VERSION = "1.0"
START = datetime(2024, 7, 1, 12, tzinfo=timezone.utc)
DURATION = 3600


def stamp(seconds: int) -> str:
    return (START + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def public_scenario() -> dict:
    return {
        "id": SCENARIO_ID, "version": SCENARIO_VERSION, "name": "Alder Creek",
        "subtitle": "A fictional incident, one decision at a time.", "synthetic": True,
        "start_utc": stamp(0), "duration_seconds": DURATION,
        "bounds": [[39.790, -121.136], [39.826, -121.090]],
        "staging": [39.794, -121.126],
        "rules": {"gps_max_age_seconds": 120, "heartbeat_max_age_seconds": 90,
                  "accuracy_max_m": 100, "snapshot_ttl_seconds": 300},
        "rules_note": "Thresholds are exercise parameters, not operational guidance.",
    }


# GeoJSON coordinate order: longitude, latitude. These are scripted exercise zones.
ZONES = [
    {"id": "zone-1", "published": 0, "observed": 0,
     "ring": [[-121.106, 39.811], [-121.097, 39.810], [-121.094, 39.819],
              [-121.103, 39.822], [-121.109, 39.817], [-121.106, 39.811]]},
    {"id": "zone-2", "published": 1200, "observed": 1020,
     "ring": [[-121.114, 39.800], [-121.098, 39.802], [-121.092, 39.819],
              [-121.105, 39.824], [-121.117, 39.814], [-121.114, 39.800]]},
    {"id": "zone-3", "published": 2400, "observed": 2100,
     "ring": [[-121.120, 39.798], [-121.096, 39.800], [-121.091, 39.820],
              [-121.110, 39.825], [-121.123, 39.815], [-121.120, 39.798]]},
]
ROUTES = [
    {"id": "route-1", "name": "East ridge", "published": 0, "expires": 1500,
     "coordinates": [[-121.126, 39.794], [-121.120, 39.800], [-121.112, 39.808], [-121.110, 39.814]]},
    {"id": "route-2", "name": "West staging loop", "published": 1800, "expires": 3000,
     "coordinates": [[-121.126, 39.794], [-121.130, 39.800], [-121.132, 39.810], [-121.129, 39.819]]},
]
OBSERVATIONS = [
    {"id": "pixel-1", "acquired": 420, "published": 600, "sensor": "MODIS", "point": [-121.102, 39.815]},
    {"id": "pixel-2", "acquired": 1020, "published": 1200, "sensor": "VIIRS", "point": [-121.110, 39.807]},
    {"id": "pixel-3", "acquired": 1740, "published": 2100, "sensor": "VIIRS", "point": [-121.112, 39.803]},
    {"id": "pixel-4", "acquired": 2100, "published": 2400, "sensor": "MODIS", "point": [-121.117, 39.808]},
]
EVENTS = [
    (0, "briefing", "Exercise opened", "Zone 1 and route 1 are published. Three simulated crews have checked in."),
    (600, "observation", "First observation received", "A synthetic MODIS pixel is now available. Acquisition and availability times differ."),
    (1200, "zone", "Zone revised", "Zone 2 and a VIIRS observation are published. Review the east ridge route."),
    (1500, "route", "Route validity ended", "Route 1 has expired. A previous approval does not extend its validity."),
    (1800, "route", "Route revision received", "The scripted commander has approved route 2 for this exercise."),
    (2100, "observation", "Observation received", "A later VIIRS pixel is now available."),
    (2400, "zone", "Zone revised", "Zone 3 and another synthetic MODIS pixel are published."),
    (3000, "route", "Route validity ended", "Route 2 has expired. Its line remains visible as historical context."),
    (3600, "complete", "Replay complete", "Export the exercise record to review evidence and acknowledgments."),
]


def crew_reports(elapsed: int) -> list[dict]:
    tick = elapsed // 60 * 60
    positions = {
        "alpha": ([-121.125, 39.796] if tick < 600 else [-121.118, 39.802] if tick < 1200
                  else [-121.1115, 39.806] if tick < 1800 else [-121.130, 39.805]),
        "bravo": ([-121.123, 39.795] if tick < 900 else [-121.115, 39.809]
                  if tick < 1680 else [-121.124, 39.807]),
        "delta": ([-121.127, 39.796] if tick < 900 else [-121.128, 39.802]
                  if tick < 1920 else [-121.129, 39.808]),
    }
    reports = []
    for index, (crew_id, point) in enumerate(positions.items()):
        connected = not (crew_id == "delta" and 2100 <= tick < 2760)
        gps_time = 1020 if crew_id == "bravo" and 1080 <= tick < 1680 else tick
        heartbeat = tick if connected else 2040
        if not connected:
            gps_time = 2040
        reports.append({
            "id": crew_id, "name": f"Crew {crew_id.title()}", "position": point,
            "accuracy_m": [18, 35, 22][index], "position_utc": stamp(gps_time),
            "heartbeat_utc": stamp(heartbeat), "connected": connected,
        })
    return reports


def snapshot(elapsed: int) -> dict:
    if isinstance(elapsed, bool) or not isinstance(elapsed, int) or not 0 <= elapsed <= DURATION:
        raise ValueError(f"elapsed must be an integer from 0 to {DURATION}")
    zone = max((z for z in ZONES if z["published"] <= elapsed and z["observed"] <= elapsed),
               key=lambda z: z["published"])
    route = max((r for r in ROUTES if r["published"] <= elapsed), key=lambda r: r["published"])
    events = [{"id": f"event-{offset}", "kind": kind, "published_utc": stamp(offset),
               "title": title, "detail": detail}
              for offset, kind, title, detail in EVENTS if offset <= elapsed]
    result = {
        "scenario_id": SCENARIO_ID, "scenario_version": SCENARIO_VERSION, "synthetic": True,
        "elapsed_seconds": elapsed, "as_of_utc": stamp(elapsed),
        "valid_until_utc": stamp(elapsed + public_scenario()["rules"]["snapshot_ttl_seconds"]),
        "revision": len(events), "rules": public_scenario()["rules"],
        "zone": {"id": zone["id"], "published_utc": stamp(zone["published"]),
                 "observed_utc": stamp(zone["observed"]),
                 "geometry": {"type": "Polygon", "coordinates": [deepcopy(zone["ring"])]}},
        "route": {"id": route["id"], "name": route["name"], "approved": True,
                  "approved_by": "Scripted exercise commander", "published_utc": stamp(route["published"]),
                  "expires_utc": stamp(route["expires"]),
                  "geometry": {"type": "LineString", "coordinates": deepcopy(route["coordinates"])}},
        "observations": [{"id": o["id"], "sensor": o["sensor"], "coordinates": o["point"],
                          "acquisition_utc": stamp(o["acquired"]), "available_utc": stamp(o["published"])}
                         for o in OBSERVATIONS if o["acquired"] <= elapsed and o["published"] <= elapsed],
        "crews": crew_reports(elapsed), "events": events,
    }
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"))
    result["snapshot_id"] = hashlib.sha256(canonical.encode()).hexdigest()
    return result
