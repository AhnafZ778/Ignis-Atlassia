"""Small dependency-free contracts shared by HTTP, MCP and model adapters."""
from __future__ import annotations

import calendar
import hashlib
import json
import math
from datetime import date

from ..core import SERIES, validate_bbox
from ..replay import CASES

METHODS = {
    "archive_search": {"id": "assistant-historical-window-search-v1", "unit": "imported records", "filter": "Authentic standard MODIS and VIIRS S-NPP rows inside the requested bbox and explicit year range. Monthly windows are retrieval shortcuts, not confirmed incidents. Counts precede replay eligibility and alias deduplication."},
    "observations": {"id": "assistant-original-records-v1", "unit": "imported records", "filter": "Authentic batches; requested sources; UTC acquisition interval; inclusive bbox. No replay deduplication."},
    "replay": {"id": "fireatlas-observation-replay-v1", "unit": "observed cell-days", "filter": "Standard MODIS/S-NPP; vegetation type 0 or missing; alias-aware exact-repeat deduplication."},
    "research": {"id": "fireatlas-research-v1", "unit": "cell-days", "filter": "Existing research eligibility; source/cell/UTC-date union. Research filtering differs from replay."},
    "calendar": {"id": "fireatlas-raw-calendar-v1", "unit": "observed cell-days", "filter": "Existing calendar eligibility. Official incomplete totals withheld; partial imported values separate."},
    "harmonized": {"id": "fireatlas-calendar-v2", "unit": "VIIRS-equivalent cell-days", "filter": "Version-matched regional calibration; observed/scaled/mixed/unknown states preserved."},
    "availability": {"id": "assistant-source-inventory-v1", "unit": "imported records", "filter": "Authentic batches only; catalog counts do not establish complete export coverage."},
    "validation": {"id": "fireatlas-validity-v1", "unit": "evidence gates", "filter": "Existing native-mask and independent-reference requirements; no assistant signoff."},
    "sources": {"id": "assistant-curated-reference-v1", "unit": "reference passages", "filter": "Project documentation and operator-approved official references; not local measurements."},
}

LIMITATION = "Satellite detections are observations, not fire perimeters or forecasts. Missing observations do not establish no fire."


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def normalize_context(value=None):
    value = value or {}
    if not isinstance(value, dict):
        raise ValueError("Study context must be an object.")
    allowed = {"year", "month", "bbox", "as_of", "series", "day", "distance_km", "gap_days", "region", "layer", "case", "start", "end", "source", "metric", "view", "context", "revision", "mask_id", "scale"}
    if set(value) - allowed:
        raise ValueError("Unknown study setting.")
    result = dict(value)
    case_id = value.get("case")
    if case_id:
        if case_id not in CASES:
            raise ValueError("Choose Park, Camp, Grove, or a custom observation study.")
        case = CASES[case_id]
        result.setdefault("bbox", case["bbox"])
        result.setdefault("start", case["start"])
        result.setdefault("end", case["end"])
        result.setdefault("year", int(case["start"][:4]))
        result.setdefault("month", int(case["start"][5:7]))
    year, month = int(result.get("year", 2024)), int(result.get("month", 7))
    if not 2000 <= year <= 2100 or not 1 <= month <= 12:
        raise ValueError("Choose a valid year and month.")
    bbox = result.get("bbox", [-122, 39, -120, 41])
    if isinstance(bbox, str):
        bbox = bbox.split(",")
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        raise ValueError("Study area needs west, south, east, north.")
    bbox = tuple(float(v) for v in bbox)
    if not all(math.isfinite(v) for v in bbox):
        raise ValueError("Coordinates must be finite.")
    validate_bbox(bbox)
    if bbox[1] < -86 or bbox[3] > 86:
        raise ValueError("The research grid supports latitudes from −86 to 86.")
    start = result.get("start", f"{year:04}-{month:02}-01")
    end = result.get("end", result.get("as_of", f"{year:04}-{month:02}-{calendar.monthrange(year, month)[1]:02}"))
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last or (last-first).days > 365:
        raise ValueError("Use an ordered UTC interval of at most one year; detailed replay is limited to 31 days.")
    series = result.get("series", "joint")
    if series not in SERIES:
        raise ValueError("Unsupported observation series.")
    distance = float(result.get("distance_km", 2))
    gap = result.get("gap_days", 1)
    if isinstance(gap, bool) or int(gap) != float(gap) or not 0 <= int(gap) <= 7 or not math.isfinite(distance) or not .5 <= distance <= 10:
        raise ValueError("Distance must be 0.5–10 km and day gap an integer 0–7.")
    metric = result.get("metric", "density")
    source = result.get("source", "MODIS_SP" if series == "modis" else "VIIRS_SNPP_SP" if series == "viirs-snpp" else "joint")
    if source not in {"joint", "MODIS_SP", "VIIRS_SNPP_SP"} or metric not in {"density", "persistence", "frp"}:
        raise ValueError("Unsupported replay source or metric.")
    if source == "joint" and metric == "frp":
        raise ValueError("Choose a single sensor for FRP; joint FRP is unsupported.")
    day = result.get("day", "")
    if day and not first <= date.fromisoformat(day) <= last:
        raise ValueError("Selected day must be inside the study interval.")
    date.fromisoformat(result.get('as_of',last.isoformat()))
    if result.get('region','norcal') not in {'norcal','punjab-haryana'}:raise ValueError('Unknown calibrated region. Custom studies use a bounding box.')
    if result.get('layer','ndvi') not in {'none','ndvi','landcover','fwi','terrain','burned-area'}:raise ValueError('Unsupported map context layer.')
    if type(result.get('revision',0)) is not int or result.get('revision',0)<0:raise ValueError('Study revision must be a nonnegative integer.')
    return {**result, "year": year, "month": month, "bbox": list(bbox), "start": first.isoformat(), "end": last.isoformat(), "as_of": result.get("as_of", last.isoformat()), "series": series, "source": source, "metric": metric, "day": day, "distance_km": distance, "gap_days": int(gap), "region": result.get("region", "norcal"), "layer": result.get("layer", "ndvi"), "revision": int(result.get("revision", 0))}


def pointer(value, path):
    if path == "":
        return value
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("Evidence value needs a JSON pointer.")
    for part in path[1:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


DESTINATIONS = {
    "overview": ("/", ""), "atlas": ("/atlas.html", "atlas-section"),
    "calendar": ("/atlas.html", "calendar-section"), "harmonized": ("/atlas.html", "harmonized-calendar"),
    "replay": ("/replay.html", "replay-workspace"), "timeline": ("/replay.html", "replay-timeline"),
    "records": ("/replay.html", "source-records"), "overlap": ("/research.html", "overview-result"),
    "candidates": ("/research-candidates.html", "candidate-list"),
    "exposure": ("/research-exposure.html", "coverage-output"),
    "validation": ("/research-validation.html", "validation-gates"),
    "sources": ("/data.html", "main-content"), "method": ("/method.html", "data-flow"),
    "review": ("/review.html", "sample-workspace"), "assistant": ("/assistant.html", "assistant-workspace"),
    "terrain": ("/terrain-earth.html", "earth"),
}
