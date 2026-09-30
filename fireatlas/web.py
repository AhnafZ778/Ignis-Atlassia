"""Local FireAtlas web MVP. Serves the existing, sensor-aware SQLite data."""

from __future__ import annotations

import argparse
import csv
import io
import hashlib
import zipfile
import json
import math
import ipaddress
import sqlite3
import threading
import contextlib
import tempfile
import time
from collections import defaultdict
from datetime import date, timedelta, datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .core import SERIES, _complete_month, calendar, connect, ingest, validate_bbox
from .fetch import FIRMS_SOURCES
from .research import report as research_report
from .study import build_bundle
from .pilots import PilotSync, PILOTS
from .bootstrap import populate_showcase
from .archive import BBOX as NASA_ARCHIVE_BBOX, SAMPLE as NASA_ARCHIVE_SAMPLE, import_bundle as import_nasa_archive
from .archive_overview import archive_overview
from .globe import snapshot as globe_snapshot, detail as globe_detail
from .briefing import responder_briefing
from .harmonization import month_audit
from .validity import CASES as VALIDITY_CASES, report as validity_report, build_evidence as build_validity_evidence
from .calendar_v2 import calendar_v2, prepare_calendar_v2, region_status
from .regions import REGIONS

STATIC = Path(__file__).with_name("static")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
EARTH_MODEL = PROJECT_ROOT / "earth.html"
DOC_ASSETS = {
    "/docs/NASA_DATA_IMPORT.md": (PROJECT_ROOT / "docs" / "NASA_DATA_IMPORT.md", "text/markdown; charset=utf-8"),
    "/docs/DATA.md": (PROJECT_ROOT / "docs" / "DATA.md", "text/markdown; charset=utf-8"),
    "/docs/AI_USE.md": (PROJECT_ROOT / "docs" / "AI_USE.md", "text/markdown; charset=utf-8"),
}
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/design.css": ("design.css", "text/css; charset=utf-8"),
    "/ui.js": ("ui.js", "text/javascript; charset=utf-8"),
    "/landing.css": ("landing.css", "text/css; charset=utf-8"),
    "/harmonized.css": ("harmonized.css", "text/css; charset=utf-8"),
    "/harmonized.js": ("harmonized.js", "text/javascript; charset=utf-8"),
    "/landing.js": ("landing.js", "text/javascript; charset=utf-8"),
    "/archive-hero.js": ("archive-hero.js", "text/javascript; charset=utf-8"),
    "/tour.css": ("tour.css", "text/css; charset=utf-8"),
    "/tour.js": ("tour.js", "text/javascript; charset=utf-8"),
    "/validity.css": ("validity.css", "text/css; charset=utf-8"),
    "/validity.js": ("validity.js", "text/javascript; charset=utf-8"),
    "/method.html": ("method.html", "text/html; charset=utf-8"),
    "/method.css": ("method.css", "text/css; charset=utf-8"),
    "/method.js": ("method.js", "text/javascript; charset=utf-8"),
    "/review.html": ("review.html", "text/html; charset=utf-8"),
    "/review.css": ("review.css", "text/css; charset=utf-8"),
    "/review.js": ("review.js", "text/javascript; charset=utf-8"),
    "/calibration-validation.js": ("calibration-validation.js", "text/javascript; charset=utf-8"),
    "/incident-media/park-fire-flames.jpg": ("incident-media/park-fire-flames.jpg", "image/jpeg"),
    "/incident-media/park-fire-02.jpg": ("incident-media/park-fire-02.jpg", "image/jpeg"),
    "/incident-media/park-fire-04.jpg": ("incident-media/park-fire-04.jpg", "image/jpeg"),
    "/incident-media/park-fire-05.jpg": ("incident-media/park-fire-05.jpg", "image/jpeg"),
    "/incident-media/park-fire-06.jpg": ("incident-media/park-fire-06.jpg", "image/jpeg"),
    "/incident-media/park-fire.jpg": ("incident-media/park-fire.jpg", "image/jpeg"),
    "/vendor/lucide-icons.svg": ("vendor/lucide-icons.svg", "image/svg+xml"),
    "/vendor/ui-primitives.css": ("vendor/ui-primitives.css", "text/css; charset=utf-8"),
    "/vendor/LUCIDE_LICENSE.txt": ("vendor/LUCIDE_LICENSE.txt", "text/plain; charset=utf-8"),
    "/vendor/SHADCN_UI_LICENSE.txt": ("vendor/SHADCN_UI_LICENSE.txt", "text/plain; charset=utf-8"),
    "/data.html": ("data.html", "text/html; charset=utf-8"),
    "/data.js": ("data.js", "text/javascript; charset=utf-8"),
    "/data.css": ("data.css", "text/css; charset=utf-8"),
    "/fonts/dm-sans.ttf": ("fonts/dm-sans.ttf", "font/ttf"),
    "/fonts/space-grotesk.ttf": ("fonts/space-grotesk.ttf", "font/ttf"),
    "/study-ui.js": ("study-ui.js", "text/javascript; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/earth-embed.js": ("earth-embed.js", "text/javascript; charset=utf-8"),
    "/terrain-earth.html": ("terrain-earth.html", "text/html; charset=utf-8"),
    "/globe.js": ("globe.js", "text/javascript; charset=utf-8"),
    "/documented-fires.json": ("documented-fires.json", "application/json; charset=utf-8"),
    "/assets/documented-fires.json": ("documented-fires.json", "application/json; charset=utf-8"),
    "/samples/aggregates/norcal.json.gz": ("../samples/aggregates/norcal.json.gz", "application/gzip"),
    "/samples/aggregates/punjab-haryana.json.gz": ("../samples/aggregates/punjab-haryana.json.gz", "application/gzip"),
    "/samples/calibration/norcal.json": ("../samples/calibration/norcal.json", "application/json; charset=utf-8"),
    "/samples/calibration/punjab-haryana.json": ("../samples/calibration/punjab-haryana.json", "application/json; charset=utf-8"),
    "/globe-math.js": ("globe-math.js", "text/javascript; charset=utf-8"),
    "/globe.css": ("globe.css", "text/css; charset=utf-8"),
    "/earth-poster-1440.webp": ("earth-poster-1440.webp", "image/webp"),
    "/earth-poster-820.webp": ("earth-poster-820.webp", "image/webp"),
    "/earth-poster-390.webp": ("earth-poster-390.webp", "image/webp"),
    "/research.html": ("research.html", "text/html; charset=utf-8"),
    "/research.css": ("research.css", "text/css; charset=utf-8"),
    "/research.js": ("research.js", "text/javascript; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
    "/vendor/leaflet.js": ("vendor/leaflet.js", "text/javascript; charset=utf-8"),
    "/vendor/leaflet.css": ("vendor/leaflet.css", "text/css; charset=utf-8"),
}


def _bbox(params: dict[str, list[str]]) -> tuple[float, float, float, float]:
    values = params.get("bbox", ["-122,39,-120,41"])[0].split(",")
    if len(values) != 4:
        raise ValueError("bbox needs west,south,east,north")
    bbox = tuple(float(value) for value in values)
    validate_bbox(bbox)
    return bbox


def _request_context(params):
    year = int(params.get("year", ["2015"])[0])
    month = int(params.get("month", ["7"])[0])
    series = params.get("series", ["joint"])[0]
    if not 2000 <= year <= 2100 or not 1 <= month <= 12 or series not in SERIES:
        raise ValueError("invalid year, month, or series")
    return year, month, series, _bbox(params)


def _research_context(params):
    return {"year": int(params.get("year", ["2015"])[0]),
            "month": int(params.get("month", ["7"])[0]), "bbox": _bbox(params),
            "as_of": params.get("as_of", [None])[0],
            "distance_km": float(params.get("distance_km", ["2"])[0]),
            "gap_days": int(params.get("gap_days", ["1"])[0])}


def _records(db, sources, bbox, start, end, limit):
    placeholders = ",".join("?" for _ in sources)
    return db.execute(f"""
        SELECT o.*,b.demo,b.file_sha256 FROM observations o
        JOIN batches b ON b.id=o.batch_id
        WHERE o.source_id IN ({placeholders})
          AND o.acquisition_utc>=? AND o.acquisition_utc<?
          AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=?
        ORDER BY o.acquisition_utc LIMIT ?
    """, (*sources, start, end, bbox[0], bbox[2], bbox[1], bbox[3], limit)).fetchall()


def handler_factory(database: Path):
    database = Path(database)
    globe_lock = threading.Lock()
    globe_cache = {}
    calendar_cache_lock = threading.Lock()
    calendar_cache = {}
    calendar_prepared_cache = {}
    pilot_sync = PilotSync(database)
    class Handler(BaseHTTPRequestHandler):
        def _local_data_action(self, content_type):
            host = self.headers.get("Host", "")
            hostname = urlsplit("//" + host).hostname
            return (ipaddress.ip_address(self.client_address[0]).is_loopback
                    and hostname in ("localhost", "127.0.0.1", "::1")
                    and self.headers.get("Origin") == f"http://{host}"
                    and self.headers.get("Content-Type") == content_type)

        def _respond(self, content: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK, filename=None):
            try:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                if filename:
                    self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.end_headers()
                self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _json(self, value, status: HTTPStatus = HTTPStatus.OK):
            self._respond(json.dumps(value).encode(), "application/json; charset=utf-8", status)

        def do_POST(self):
            path = urlsplit(self.path).path
            if path == "/api/data/sync":
                # A browser can start ingestion only through the local app, never cross-site.
                if not self._local_data_action("application/json"):
                    self._json({"error": "Pilot sync is available only from this local application's Data page."}, HTTPStatus.FORBIDDEN)
                    return
                if not pilot_sync.start():
                    self._json({"error": "A pilot sync is already running."}, HTTPStatus.CONFLICT)
                else:
                    self._json({"started": True}, HTTPStatus.ACCEPTED)
                return
            if path == "/api/data/import":
                if not self._local_data_action("text/csv"):
                    self._json({"error": "CSV import is available only from this local application's Data page."}, HTTPStatus.FORBIDDEN)
                    return
                if pilot_sync.running:
                    self._json({"error": "Wait for the current pilot sync before importing a file."}, HTTPStatus.CONFLICT)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 25_000_000:
                        self._json({"error": "CSV must contain 1–25,000,000 bytes."}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                        return
                    params = parse_qs(urlsplit(self.path).query)
                    source = params.get("source", [""])[0]
                    if source not in FIRMS_SOURCES:
                        raise ValueError("Choose a supported NASA FIRMS source.")
                    month = params.get("complete_month", [None])[0]
                    if month and "bbox" not in params:
                        raise ValueError("A complete month requires its exact export bounding box.")
                    bbox = _bbox(params) if month else None
                    with connect(database) as db:
                        if db.execute("SELECT 1 FROM batches WHERE demo=1 LIMIT 1").fetchone():
                            raise ValueError("Synthetic data cannot be mixed with an authentic NASA import.")
                        with tempfile.TemporaryDirectory() as temporary:
                            uploaded = Path(temporary) / "uploaded.csv"
                            uploaded.write_bytes(self.rfile.read(length))
                            result = ingest(db, uploaded, source, source_uri="user-supplied:FIRMS CSV",
                                            complete_month=month, bbox=bbox)
                    pilot_sync.reconcile_imports()
                    self._json({"import": result, "source": source, "complete_month": month,
                                "message": "CSV imported. View the source ledger and pilot matrix below."})
                except (ValueError, UnicodeError, TypeError) as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                except (OSError, sqlite3.Error):
                    self._json({"error": "CSV import could not finish; no unverified completion was recorded."}, HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            if path != "/api/research":
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 3_000_000:
                    self._json({"error": "research request must contain 1–3,000,000 bytes"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                    return
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or not isinstance(payload.get("config"), dict):
                    raise ValueError("request requires a config object and optional mask")
                allowed = {"year", "month", "bbox", "as_of", "distance_km", "gap_days"}
                if set(payload["config"]) - allowed:
                    raise ValueError("unknown research configuration field")
                params = parse_qs(urlsplit(self.path).query)
                if "demo" in params:
                    raise ValueError("The synthetic showcase has been retired; remove the demo parameter.")
                with connect(database) as db:
                    self._json(research_report(db, **payload["config"], mask=payload.get("mask")))
            except (ValueError, TypeError, OverflowError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except sqlite3.Error:
                self._json({"error": "database unavailable"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == "/earth.html":
                if EARTH_MODEL.is_file():
                    self._respond(EARTH_MODEL.read_bytes(), "text/html; charset=utf-8")
                else:
                    self._json({"error": "Earth model file not found"}, HTTPStatus.NOT_FOUND)
                return
            if url.path in DOC_ASSETS:
                path, content_type = DOC_ASSETS[url.path]
                if path.is_file():
                    self._respond(path.read_bytes(), content_type)
                else:
                    self._json({"error": "document not found"}, HTTPStatus.NOT_FOUND)
                return
            if url.path in ASSETS:
                file, kind = ASSETS[url.path]
                self._respond((STATIC / file).read_bytes(), kind)
                return
            if not url.path.startswith("/api/"):
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            try:
                params = parse_qs(url.query)
                if "demo" in params:
                    raise ValueError("The synthetic showcase has been retired; remove the demo parameter.")
                if url.path in ("/api/globe", "/api/globe/detail"):
                    source, day = params.get("source", ["all"])[0], params.get("date", ["all"])[0]
                    # Bound both cache size and age; database/WAL changes invalidate the snapshot.
                    stamps = tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None
                                   for p in (database, Path(str(database) + "-wal")))
                    cell = params.get("cell", [""])[0]
                    key = (url.path, source, day, cell, stamps)
                    with globe_lock:
                        cached = globe_cache.get(key)
                        if cached and time.monotonic() - cached[0] < 300:
                            body = cached[1]
                        else:
                            with contextlib.closing(connect(database)) as db:
                                body = globe_detail(db, cell=cell, source=source, day=day) if url.path.endswith("/detail") else globe_snapshot(db, source=source, day=day)
                            if len(globe_cache) >= 24:
                                globe_cache.pop(next(iter(globe_cache)))
                            globe_cache[key] = (time.monotonic(), body)
                    self._json(body)
                    return
                if url.path == "/api/data/status":
                    self._json(pilot_sync.status())
                    return
                with connect(database) as db:
                    if url.path == "/api/v2/regions":
                        self._json(region_status(db))
                    elif url.path == "/api/v2/calendar":
                        region = params.get("region", [""])[0]
                        year = int(params.get("year", ["2024"])[0])
                        month = int(params.get("month", ["7"])[0])
                        history = params.get("history", ["0"])[0] == "1"
                        stamps = tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None
                                       for p in (database, Path(str(database) + "-wal")))
                        key = (region, year, month, history, stamps)
                        with calendar_cache_lock:
                            cached = calendar_cache.get(key)
                            if cached and time.monotonic() - cached[0] < 300:
                                result = cached[1]
                            else:
                                if (region not in REGIONS or not 2006 <= year <= 2026
                                        or not 1 <= month <= 12):
                                    result = calendar_v2(db, region=region, year=year, month=month,
                                                         include_history=history)
                                else:
                                    prepared_key = (region, stamps)
                                    prepared_item = calendar_prepared_cache.get(prepared_key)
                                    if prepared_item is None:
                                        prepared_item = prepare_calendar_v2(db, region=region,
                                                                           fallback_year=2026)
                                        if len(calendar_prepared_cache) >= 2:
                                            calendar_prepared_cache.pop(next(iter(calendar_prepared_cache)))
                                        calendar_prepared_cache[prepared_key] = prepared_item
                                    result = calendar_v2(db, region=region, year=year, month=month,
                                                         include_history=history, prepared=prepared_item)
                                if len(calendar_cache) >= 8:
                                    calendar_cache.pop(next(iter(calendar_cache)))
                                calendar_cache[key] = (time.monotonic(), result)
                        self._json(result)
                    elif url.path == "/api/validity":
                        self._json(validity_report(db, case_id=params.get("case", ["park-2024"])[0],
                                                   selected_date=params.get("date", [None])[0]))
                    elif url.path == "/api/validity/check":
                        from .validation_check import check as analytical_check
                        case_id = params.get("case", ["park-2024"])[0]
                        evidence = build_validity_evidence(db, case_id)
                        checked = analytical_check(io.BytesIO(evidence))
                        checked["checked_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                        with zipfile.ZipFile(io.BytesIO(evidence)) as archive:
                            checked["manifest_sha256"] = hashlib.sha256(archive.read("manifest.json")).hexdigest()
                        self._json(checked)
                    elif url.path == "/api/validity/export":
                        case_id = params.get("case", ["park-2024"])[0]
                        self._respond(build_validity_evidence(db, case_id), "application/zip",
                                      filename=f"fireatlas_validity_{case_id}.zip")
                    elif url.path == "/api/validity/review-template":
                        from .mask_review import make_template
                        from .masks import read_evidence
                        case_id = params.get("case", ["park-2024"])[0]
                        if case_id not in VALIDITY_CASES:
                            raise ValueError("case must be park-2024 or grove-2025")
                        template = make_template(case_id, read_evidence(case_id))
                        self._respond(json.dumps(template, sort_keys=True, indent=2).encode(),
                                      "application/json; charset=utf-8",
                                      filename=f"fireatlas_{case_id}_native_mask_review_template.json")
                    elif url.path == "/api/research":
                        self._json(research_report(db, **_research_context(params)))
                    elif url.path == "/api/archive-overview":
                        self._json(archive_overview(db))
                    elif url.path == "/api/meta":
                        rows = db.execute("""
                            SELECT DISTINCT year FROM (
                              SELECT CAST(substr(month,1,4) AS INTEGER) AS year FROM export_windows
                              UNION SELECT CAST(substr(acquisition_utc,1,4) AS INTEGER) AS year FROM observations
                            ) ORDER BY year
                        """).fetchall()
                        latest = db.execute("SELECT * FROM export_windows ORDER BY month DESC,batch_id LIMIT 1").fetchone()
                        default_view = {"year": int(latest["month"][:4]) if latest else 2024,
                                        "month": int(latest["month"][5:]) if latest else 7,
                                        "bbox": [latest[k] for k in ("west", "south", "east", "north")] if latest else PILOTS[0]["bbox"]}
                        default_series = next((name for name, sources in SERIES.items()
                                               if latest and sources == (latest["source_id"],)), "joint")
                        standard_pair_ready = _complete_month(db, "2025-07", SERIES["joint"], NASA_ARCHIVE_BBOX)
                        archive_status = region_status(db)
                        if standard_pair_ready:
                            default_view = {"year": 2024, "month": 7, "bbox": VALIDITY_CASES["park-2024"]["bbox"]}
                            default_series = "joint"
                        self._json({"years": [row["year"] for row in rows], "series": list(SERIES),
                                    "default_view": default_view, "pilots": PILOTS,
                                    "default_series": default_series,
                                    "standard_pair_ready": standard_pair_ready,
                                    "archive_status": archive_status,
                                    "available_sources": [row[0] for row in db.execute("SELECT DISTINCT source_id FROM batches ORDER BY source_id")],
                                    "source_counts": {row[0]: row[1] for row in db.execute("SELECT source_id,COUNT(*) FROM observations GROUP BY source_id")},
                                    "synthetic": bool(db.execute("SELECT 1 FROM batches WHERE demo=1 LIMIT 1").fetchone())})
                    elif url.path == "/api/calendar":
                        year = int(params.get("year", ["2015"])[0])
                        series = params.get("series", ["joint"])[0]
                        self._json(calendar(db, bbox=_bbox(params), year=year, series=series))
                    elif url.path == "/api/briefing":
                        year, month, series, bbox = _request_context(params)
                        self._json(responder_briefing(db, year=year, month=month,
                                                      series=series, bbox=bbox))
                    elif url.path == "/api/harmonization":
                        year, month, series, bbox = _request_context(params)
                        self._json(month_audit(db, year=year, month=month,
                                               series=series, bbox=bbox))
                    elif url.path == "/api/study":
                        year, month, series, bbox = _request_context(params)
                        db.execute("BEGIN")
                        bundle = build_bundle(db, year=year, month=month, series=series, bbox=bbox,
                                              day=params.get("day", [None])[0], layer=params.get("layer", ["none"])[0])
                        self._respond(bundle, "application/zip", filename=f"fireatlas_study_{series}_{year}.zip")
                    elif url.path == "/api/observations":
                        stamp = params.get("date", [""])[0]
                        selected_date = date.fromisoformat(stamp)
                        series = params.get("series", ["joint"])[0]
                        if series not in SERIES:
                            raise ValueError("invalid series")
                        bbox = _bbox(params)
                        rows = _records(db, SERIES[series], bbox, stamp,
                                        (selected_date + timedelta(days=1)).isoformat(), 201)
                        observations = []
                        for row in rows[:200]:
                            entry = dict(row)
                            entry["raw"] = json.loads(entry.pop("raw_json"))
                            observations.append(entry)
                        self._json({"date_utc": stamp, "observations": observations, "truncated": len(rows) > 200})
                    elif url.path == "/api/map":
                        year, month, series, bbox = _request_context(params)
                        zoom = float(params.get("zoom", ["7"])[0])
                        if not math.isfinite(zoom) or not 0 <= zoom <= 20:
                            raise ValueError("invalid zoom")
                        start = f"{year}-{month:02d}-01"
                        end = (date(year, month, 1) + timedelta(days=32)).replace(day=1).isoformat()
                        selected_day = params.get("day", [None])[0]
                        if selected_day is not None:
                            selected = date(year, month, int(selected_day))
                            start = selected.isoformat()
                            end = (selected + timedelta(days=1)).isoformat()
                        sources = SERIES[series]
                        source_sql = ",".join("?" for _ in sources)
                        where = f"source_id IN ({source_sql}) AND acquisition_utc>=? AND acquisition_utc<? AND lon>=? AND lon<=? AND lat>=? AND lat<=?"
                        scope = (*sources, start, end, bbox[0], bbox[2], bbox[1], bbox[3])
                        totals = db.execute(f"SELECT count(*) AS total,min(lon) AS west,min(lat) AS south,max(lon) AS east,max(lat) AS north FROM observations WHERE {where}", scope).fetchone()
                        total = totals["total"]
                        point_bounds = [totals[k] for k in ("west", "south", "east", "north")] if total else None
                        if zoom < 6:
                            step = 4 if zoom < 4 else 1
                            bins = db.execute(f"""
                                SELECT CAST((lat+90)/? AS INTEGER) AS y,CAST((lon+180)/? AS INTEGER) AS x,
                                       count(*) AS count,group_concat(DISTINCT sensor) AS sensors
                                FROM observations WHERE {where} GROUP BY y,x
                            """, (step, step, *scope))
                            features = [{"lat": (row["y"] + .5) * step - 90, "lon": (row["x"] + .5) * step - 180,
                                         "count": row["count"], "sensors": row["sensors"].split(",")} for row in bins]
                            mode = "aggregates"
                            displayed = total
                        else:
                            stride = max(1, math.ceil(total / 1000))
                            raw = db.execute(f"""
                                WITH ranked AS (
                                    SELECT detection_id,row_number() OVER (ORDER BY acquisition_utc,detection_id) AS position
                                    FROM observations WHERE {where}
                                )
                                SELECT o.*,b.demo FROM ranked r JOIN observations o ON o.detection_id=r.detection_id
                                JOIN batches b ON b.id=o.batch_id WHERE (r.position-1) % ? = 0
                                ORDER BY r.position LIMIT 1000
                            """, (*scope, stride)).fetchall()
                            features = [{"lat": row["lat"], "lon": row["lon"],
                                         "sensor": row["sensor"], "platform": row["platform"],
                                         "acquisition_utc": row["acquisition_utc"],
                                         "confidence_raw": row["confidence_raw"],
                                         "product_version": row["product_version"],
                                         "demo": bool(row["demo"])} for row in raw]
                            mode = "points"
                            displayed = len(raw)
                        self._json({"mode": mode, "features": features, "truncated": mode == "points" and total > displayed,
                                    "records_in_sample": total, "total_records": total, "displayed_points": displayed,
                                    "point_bounds": point_bounds, "month": start[:7],
                                    "scope_date": start if selected_day is not None else None,
                                    "record_scope": "imported records only"})
                    elif url.path == "/api/export":
                        year, month, series, bbox = _request_context(params)
                        kind = params.get("kind", ["calendar"])[0]
                        output = io.StringIO()
                        if kind == "calendar":
                            summary = calendar(db, bbox=bbox, year=year, series=series)
                            fields = ["date_utc", "detected_cell_days", "partial_import_detected_cell_days",
                                      "raw_modis_pixels", "raw_viirs_pixels", "export_window_complete",
                                      "satellite_observation_coverage", "baseline_median", "baseline_years",
                                      "anomaly_cell_days", "series", "sources", "grid", "metric", "demo_data",
                                      "source_file_sha256"]
                            writer = csv.DictWriter(output, fieldnames=fields)
                            writer.writeheader()
                            hashes = ";".join(item["file_sha256"] for item in summary["provenance"])
                            for day in summary["daily"]:
                                month_info = summary["monthly"][int(day["date_utc"][5:7]) - 1]
                                writer.writerow({
                                    "date_utc": day["date_utc"],
                                    "detected_cell_days": day["detected_cell_days"],
                                    "partial_import_detected_cell_days": day["partial_import_detected_cell_days"],
                                    "raw_modis_pixels": day["raw_pixels_by_sensor"].get("MODIS", 0),
                                    "raw_viirs_pixels": day["raw_pixels_by_sensor"].get("VIIRS", 0),
                                    "export_window_complete": day["export_window_complete"],
                                    "satellite_observation_coverage": day["satellite_observation_coverage"],
                                    "baseline_median": month_info["baseline_median"],
                                    "baseline_years": ";".join(map(str, month_info["baseline_years"])),
                                    "anomaly_cell_days": month_info["anomaly_cell_days"],
                                    "series": series, "sources": ";".join(summary["sources"]),
                                    "grid": summary["grid"], "metric": summary["metric"],
                                    "demo_data": summary["demo_data"], "source_file_sha256": hashes,
                                })
                        elif kind == "observations":
                            raw = _records(db, SERIES[series], bbox, f"{year}-01-01", f"{year+1}-01-01", 50001)
                            if len(raw) > 50000:
                                self._json({"error": "export exceeds 50,000 rows; narrow the AOI"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                                return
                            fields = ["detection_id", "source_id", "platform", "sensor", "product_version",
                                      "processing_level", "acquisition_utc", "retrieval_time_utc", "lon", "lat",
                                      "scan_m", "track_m", "confidence_raw", "frp_raw", "daynight",
                                      "thermal_anomaly_flag", "source_uri", "file_sha256", "demo", "raw_json"]
                            writer = csv.DictWriter(output, fieldnames=fields)
                            writer.writeheader()
                            for row in raw:
                                writer.writerow({field: row[field] for field in fields})
                        else:
                            raise ValueError("kind must be calendar or observations")
                        self._respond(output.getvalue().encode(), "text/csv; charset=utf-8",
                                      filename=f"fireatlas_{kind}_{series}_{year}.csv")
                    else:
                        self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            except (ValueError, TypeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except sqlite3.Error:
                self._json({"error": "database unavailable"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/fireatlas.sqlite3"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-showcase", action="store_true", help="leave the default authentic database empty on first launch")
    args = parser.parse_args()
    if args.db == Path("data/fireatlas.sqlite3") and not args.no_showcase:
        result = populate_showcase(args.db)
        if result["loaded"]:
            print("Loaded verified NOAA HMS historical showcase into the authentic database.", flush=True)
        if NASA_ARCHIVE_SAMPLE.exists():
            nasa_result = import_nasa_archive(args.db)
            if nasa_result["imported_rows"]:
                PilotSync(args.db).reconcile_imports()
                print(f"Loaded {nasa_result['imported_rows']} regional NASA FIRMS archive detections.", flush=True)
    if args.db.exists():
        with connect(args.db) as db:
            if db.execute("SELECT 1 FROM batches WHERE demo=1 LIMIT 1").fetchone():
                raise SystemExit("Refusing to serve a database containing synthetic demonstration records.")
    server = ThreadingHTTPServer((args.host, args.port), handler_factory(args.db))
    print(f"FireAtlas web MVP: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
