"""FIRMS CSV ingestion and honest, sensor-aware calendar summaries.

Common 1 km EASE-Grid 2.0 (EPSG:6933) cells are assigned by detection
centroid. This is a sampling proxy, not an estimate of burned area or a
pixel-footprint intersection algorithm.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from urllib.parse import urlsplit, urlunsplit

from pyproj import Transformer

GRID_METERS = 1000
GRID_VERSION = "ease6933-centroid-1km-v1"
TO_GRID = Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True)
SOURCES = {
    "MODIS_SP": ("MODIS", "SP"),
    "MODIS_NRT": ("MODIS", "NRT"),
    "VIIRS_SNPP_SP": ("VIIRS", "SP"),
    "VIIRS_SNPP_NRT": ("VIIRS", "NRT"),
    "VIIRS_NOAA20_SP": ("VIIRS", "SP"),
    "VIIRS_NOAA20_NRT": ("VIIRS", "NRT"),
    "VIIRS_NOAA21_NRT": ("VIIRS", "NRT"),
    "NOAA_HMS_VIIRS": ("VIIRS", "NOAA HMS"),
}
SERIES = {
    "modis": ("MODIS_SP",),
    "viirs-snpp": ("VIIRS_SNPP_SP",),
    "joint": ("MODIS_SP", "VIIRS_SNPP_SP"),
    "hms-viirs": ("NOAA_HMS_VIIRS",),
    "viirs-noaa20": ("VIIRS_NOAA20_SP",),
    "viirs-noaa20-nrt": ("VIIRS_NOAA20_NRT",),
    "viirs-noaa21-nrt": ("VIIRS_NOAA21_NRT",),
    "viirs-snpp-nrt": ("VIIRS_SNPP_NRT",),
    "modis-nrt": ("MODIS_NRT",),
}
REQUIRED_COLUMNS = {
    "latitude", "longitude", "acq_date", "acq_time", "satellite",
    "instrument", "confidence", "version", "scan", "track", "frp", "daynight",
}


class Connection(sqlite3.Connection):
    def __enter__(self):
        super().__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            super().__exit__(exc_type, exc_val, exc_tb)
        finally:
            self.close()

    def transaction(self):
        class _Tx:
            def __init__(self, conn):
                self.conn = conn
            def __enter__(self):
                sqlite3.Connection.__enter__(self.conn)
                return self.conn
            def __exit__(self, exc_type, exc_val, exc_tb):
                return sqlite3.Connection.__exit__(self.conn, exc_type, exc_val, exc_tb)
        return _Tx(self)


def connect(path: str | Path) -> Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, factory=Connection)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS batches (
            id INTEGER PRIMARY KEY,
            source_id TEXT NOT NULL,
            source_uri TEXT NOT NULL,
            file_sha256 TEXT NOT NULL,
            retrieved_utc TEXT NOT NULL,
            demo INTEGER NOT NULL DEFAULT 0,
            row_count INTEGER NOT NULL,
            window_key TEXT NOT NULL,
            UNIQUE(source_id, file_sha256, window_key)
        );
        CREATE TABLE IF NOT EXISTS observations (
            detection_id TEXT PRIMARY KEY,
            batch_id INTEGER NOT NULL REFERENCES batches(id),
            source_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            sensor TEXT NOT NULL,
            product_version TEXT NOT NULL,
            processing_level TEXT NOT NULL,
            acquisition_utc TEXT NOT NULL,
            retrieval_time_utc TEXT NOT NULL,
            lon REAL NOT NULL,
            lat REAL NOT NULL,
            scan_m REAL NOT NULL,
            track_m REAL NOT NULL,
            confidence_raw TEXT NOT NULL,
            frp_raw TEXT,
            daynight TEXT NOT NULL,
            thermal_anomaly_flag TEXT,
            source_uri TEXT NOT NULL,
            grid_x INTEGER NOT NULL,
            grid_y INTEGER NOT NULL,
            raw_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS excluded_rows (
            batch_id INTEGER NOT NULL REFERENCES batches(id),
            line_number INTEGER NOT NULL, reason TEXT NOT NULL, raw_json TEXT NOT NULL,
            PRIMARY KEY(batch_id,line_number)
        );
        CREATE INDEX IF NOT EXISTS observations_lookup
            ON observations(source_id, acquisition_utc, lon, lat);
        CREATE INDEX IF NOT EXISTS observations_batch ON observations(batch_id);
        CREATE TABLE IF NOT EXISTS export_windows (
            batch_id INTEGER PRIMARY KEY REFERENCES batches(id),
            source_id TEXT NOT NULL,
            month TEXT NOT NULL,
            west REAL NOT NULL, south REAL NOT NULL,
            east REAL NOT NULL, north REAL NOT NULL
        );
    """)
    return db


def validate_bbox(bbox: tuple[float, float, float, float]) -> None:
    w, s, e, n = bbox
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise ValueError("bbox must be west,south,east,north without date-line crossing")


def _safe_source_uri(uri: str) -> str:
    """Preserve traceability without storing a FIRMS MAP_KEY or URL credentials."""
    parts = urlsplit(uri)
    if parts.scheme not in ("http", "https"):
        return uri
    path = re.sub(r"(/api/area/csv/)[^/]+", r"\1[MAP_KEY]", parts.path)
    return urlunsplit((parts.scheme, parts.netloc.split("@")[-1], path, "", ""))


def _normalized_row(row: dict[str, str], source_id: str, retrieved: str, uri: str) -> dict:
    sensor, level = SOURCES[source_id]
    lon, lat = float(row["longitude"]), float(row["latitude"])
    if not (-180 <= lon <= 180 and -86 <= lat <= 86):
        raise ValueError("coordinates outside supported EPSG:6933 region")
    instrument = row.get("instrument", sensor).strip().upper()
    # FIRMS Archive Download labels its Suomi-NPP Collection 2 files with
    # instrument=SNPP; recent area CSVs use instrument=VIIRS. Preserve the
    # original field in raw_json while normalizing both to the VIIRS sensor.
    accepted_instruments = {sensor}
    if source_id in ("VIIRS_SNPP_SP", "VIIRS_SNPP_NRT"):
        accepted_instruments.add("SNPP")
    if instrument not in accepted_instruments:
        raise ValueError(f"instrument does not match {source_id}")
    if source_id != "NOAA_HMS_VIIRS":
        platforms = {"MODIS": {"T", "A", "TERRA", "AQUA"}, "SNPP": {"N", "SNPP", "SUOMI NPP", "S-NPP"},
                     "NOAA20": {"1", "N20", "NOAA-20", "NOAA20"}, "NOAA21": {"2", "N21", "NOAA-21", "NOAA21"}}
        platform_key = "MODIS" if sensor == "MODIS" else source_id.split("_")[1]
        if row["satellite"].strip().upper() not in platforms[platform_key]:
            raise ValueError(f"satellite does not match {source_id}")
        version = row["version"].strip().upper()
        if ("NRT" in version or "URT" in version or version.endswith("RT")) and level == "SP":
            raise ValueError("near real-time rows cannot be imported as standard processing")
    hhmm = row["acq_time"].strip().zfill(4)
    if len(hhmm) != 4 or not hhmm.isdigit():
        raise ValueError("invalid FIRMS acq_time")
    acquired = datetime.strptime(row["acq_date"] + hhmm, "%Y-%m-%d%H%M").replace(tzinfo=timezone.utc)
    scan_m, track_m = float(row["scan"]) * 1000, float(row["track"]) * 1000
    if not (math.isfinite(scan_m) and math.isfinite(track_m)) or scan_m <= 0 or track_m <= 0:
        raise ValueError("scan and track must be positive")
    x, y = TO_GRID.transform(lon, lat)
    # Latitude constraints above keep the transform within the projection domain.
    gx, gy = math.floor(x / GRID_METERS), math.floor(y / GRID_METERS)
    normalized = {
        "source_id": source_id,
        "platform": row["satellite"].strip(),
        "sensor": sensor,
        "product_version": row["version"].strip(),
        "processing_level": level,
        "acquisition_utc": acquired.isoformat().replace("+00:00", "Z"),
        "retrieval_time_utc": retrieved,
        "lon": lon, "lat": lat,
        "scan_m": scan_m, "track_m": track_m,
        "confidence_raw": row["confidence"].strip(),
        "frp_raw": row["frp"].strip() or None,
        "daynight": row["daynight"].strip(),
        "thermal_anomaly_flag": row.get("type") or None,
        "source_uri": uri,
        "grid_x": gx, "grid_y": gy,
        "raw_json": json.dumps(row, sort_keys=True),
    }
    # Content identity survives repeated downloads. Distinct processing levels
    # remain distinct and should never be mixed in one historical series.
    fingerprint = {k: normalized[k] for k in (
        "source_id", "platform", "acquisition_utc", "lon", "lat",
        "scan_m", "track_m", "confidence_raw", "frp_raw", "product_version",
    )}
    normalized["detection_id"] = hashlib.sha256(
        json.dumps(fingerprint, sort_keys=True).encode()
    ).hexdigest()
    return normalized


def ingest(
    db: sqlite3.Connection,
    csv_path: str | Path,
    source_id: str,
    *,
    source_uri: str | None = None,
    complete_month: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    demo: bool = False,
    exclude_outside_grid: bool = False,
) -> dict:
    if source_id not in SOURCES:
        raise ValueError(f"unsupported source: {source_id}")
    if (complete_month is None) != (bbox is None):
        raise ValueError("complete_month and bbox must be provided together")
    if exclude_outside_grid and complete_month:
        raise ValueError("Excluded rows cannot establish a complete monthly export")
    if bbox:
        validate_bbox(bbox)
        date.fromisoformat(complete_month + "-01")
    csv_path = Path(csv_path)
    with csv_path.open("rb") as binary:
        digest = hashlib.sha256()
        for chunk in iter(lambda: binary.read(1024 * 1024), b""):
            digest.update(chunk)
        file_hash = digest.hexdigest()
    window_key = json.dumps([complete_month, bbox])
    uri = _safe_source_uri(source_uri or csv_path.resolve().as_uri())
    retrieved = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    tx = db.transaction() if hasattr(db, "transaction") else db
    with tx, csv_path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        required = REQUIRED_COLUMNS - {"instrument"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"FIRMS CSV missing columns: {sorted(required - set(reader.fieldnames or []))}")
        existing = db.execute(
            "SELECT id, row_count FROM batches WHERE source_id=? AND file_sha256=? AND window_key=?",
            (source_id, file_hash, window_key),
        ).fetchone()
        if existing:
            excluded = db.execute("SELECT count(*) FROM excluded_rows WHERE batch_id=?", (existing["id"],)).fetchone()[0]
            return {"batch_id": existing["id"], "rows_read": existing["row_count"], "rows_inserted": 0,
                    "rows_excluded": excluded, "already_imported": True}
        cursor = db.execute(
            "INSERT INTO batches(source_id,source_uri,file_sha256,retrieved_utc,demo,row_count,window_key) VALUES (?,?,?,?,?,?,?)",
            (source_id, uri, file_hash, retrieved, int(demo), 0, window_key),
        )
        batch_id = cursor.lastrowid
        count = inserted = excluded = 0
        for line_number, row in enumerate(reader, 2):
            count += 1
            try:
                latitude, longitude = float(row["latitude"]), float(row["longitude"])
                if exclude_outside_grid and -90 <= latitude <= 90 and -180 <= longitude <= 180 and abs(latitude) > 86:
                    db.execute("INSERT INTO excluded_rows VALUES (?,?,?,?)",
                               (batch_id, line_number, "Outside EPSG:6933 supported latitude [-86,86]", json.dumps(row, sort_keys=True)))
                    excluded += 1
                    continue
                normalized = _normalized_row(row, source_id, retrieved, uri)
                if complete_month:
                    w, south, e, n = bbox
                    if normalized["acquisition_utc"][:7] != complete_month or not (
                        w <= normalized["lon"] <= e and south <= normalized["lat"] <= n
                    ):
                        raise ValueError("row outside declared complete export window")
                keys = list(normalized)
                cursor = db.execute(
                    f"INSERT OR IGNORE INTO observations(batch_id,{','.join(keys)}) VALUES (?{',?' * len(keys)})",
                    (batch_id, *(normalized[key] for key in keys)),
                )
                inserted += cursor.rowcount
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"CSV line {line_number}: {exc}") from exc
        db.execute("UPDATE batches SET row_count=? WHERE id=?", (count, batch_id))
        if complete_month:
            db.execute(
                "INSERT INTO export_windows(batch_id,source_id,month,west,south,east,north) VALUES (?,?,?,?,?,?,?)",
                (batch_id, source_id, complete_month, *bbox),
            )
    return {"batch_id": batch_id, "rows_read": count, "rows_inserted": inserted,
            "rows_excluded": excluded, "already_imported": False}


def _complete_month(db: sqlite3.Connection, month: str, sources: tuple[str, ...], bbox: tuple[float, ...]) -> bool:
    w, s, e, n = bbox
    for source in sources:
        found = db.execute("""
            SELECT 1 FROM export_windows WHERE source_id=? AND month=?
              AND west<=? AND south<=? AND east>=? AND north>=? LIMIT 1
        """, (source, month, w, s, e, n)).fetchone()
        if not found:
            return False
    return True


def _counts(db: sqlite3.Connection, year: int, sources: tuple[str, ...], bbox: tuple[float, ...]):
    w, s, e, n = bbox
    marks: dict[str, set[tuple[int, int]]] = defaultdict(set)
    raw_counts: dict[str, Counter] = defaultdict(Counter)
    placeholders = ",".join("?" for _ in sources)
    records = db.execute(f"""
        SELECT acquisition_utc, grid_x, grid_y, sensor, platform
        FROM observations
        WHERE source_id IN ({placeholders}) AND acquisition_utc>=? AND acquisition_utc<?
          AND lon>=? AND lon<=? AND lat>=? AND lat<=?
    """, (*sources, f"{year}-01-01", f"{year+1}-01-01", w, e, s, n))
    for row in records:
        day = row["acquisition_utc"][:10]
        marks[day].add((row["grid_x"], row["grid_y"]))
        raw_counts[day][row["sensor"]] += 1
    return marks, raw_counts


def calendar(db: sqlite3.Connection, *, bbox: tuple[float, float, float, float], year: int, series: str = "joint") -> dict:
    validate_bbox(bbox)
    if series not in SERIES:
        raise ValueError(f"series must be one of {', '.join(SERIES)}")
    if not 2000 <= year <= 2100:
        raise ValueError("year outside supported range")
    sources = SERIES[series]
    marks, raw_counts = _counts(db, year, sources, bbox)
    previous_counts = {}
    # Synthetic exercises sharing a sensor schema are still different scenarios.
    # Match the scenario URI directory before treating older months as baselines.
    cohorts = defaultdict(set)
    source_sql = ",".join("?" for _ in sources)
    for row in db.execute(f"""SELECT w.month,b.source_id,b.demo,b.source_uri
        FROM export_windows w JOIN batches b ON b.id=w.batch_id
        WHERE w.source_id IN ({source_sql}) AND w.west<=? AND w.south<=? AND w.east>=? AND w.north>=?""",
        (*sources, *bbox)):
        cohorts[row["month"]].add((row["source_id"], row["source_uri"].rsplit("/", 1)[0] if row["demo"] else "authentic"))
    monthly = []
    for month_number in range(1, 13):
        month = f"{year}-{month_number:02d}"
        complete = _complete_month(db, month, sources, bbox)
        observed_total = sum(len(cells) for day, cells in marks.items() if day.startswith(month))
        previous = []
        for previous_year in range(2000, year):
            old_month = f"{previous_year}-{month_number:02d}"
            comparable = not cohorts[month] or cohorts[month] == cohorts[old_month]
            if comparable and _complete_month(db, old_month, sources, bbox):
                if previous_year not in previous_counts:
                    previous_counts[previous_year], _ = _counts(db, previous_year, sources, bbox)
                old_marks = previous_counts[previous_year]
                previous.append({"year": previous_year, "cell_days": sum(
                    len(cells) for day, cells in old_marks.items() if day.startswith(old_month)
                )})
        baseline = median(item["cell_days"] for item in previous) if len(previous) >= 3 else None
        monthly.append({
            "month": month,
            "detected_cell_days": observed_total if complete else None,
            "partial_import_detected_cell_days": None if complete else observed_total,
            "export_window_complete": complete,
            "baseline_median": baseline,
            "baseline_years": [item["year"] for item in previous],
            "baseline_status": "available" if baseline is not None else "insufficient_comparable_years",
            "anomaly_cell_days": observed_total - baseline if complete and baseline is not None else None,
            "satellite_observation_coverage": "unknown",
        })
    daily = []
    day = date(year, 1, 1)
    while day.year == year:
        stamp = day.isoformat()
        complete = monthly[day.month - 1]["export_window_complete"]
        daily.append({
            "date_utc": stamp,
            "detected_cell_days": len(marks[stamp]) if complete else None,
            "partial_import_detected_cell_days": None if complete else len(marks[stamp]),
            "raw_pixels_by_sensor": dict(raw_counts[stamp]),
            "export_window_complete": complete,
            "satellite_observation_coverage": "unknown",
        })
        day += timedelta(days=1)
    placeholders = ",".join("?" for _ in sources)
    batch_rows = db.execute(f"""
        SELECT DISTINCT b.source_id,b.source_uri,b.file_sha256,b.retrieved_utc,b.demo
        FROM batches b
        LEFT JOIN export_windows ew ON ew.batch_id=b.id
        WHERE b.source_id IN ({placeholders}) AND (
          (ew.month>=? AND ew.month<? AND ew.west<=? AND ew.south<=?
             AND ew.east>=? AND ew.north>=?)
          OR EXISTS (
            SELECT 1 FROM observations o WHERE o.batch_id=b.id
              AND o.acquisition_utc>=? AND o.acquisition_utc<?
              AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=?
          )
        )
    """, (*sources, f"{year}-01", f"{year+1}-01", bbox[0], bbox[1], bbox[2], bbox[3],
          f"{year}-01-01", f"{year+1}-01-01", bbox[0], bbox[2], bbox[1], bbox[3])).fetchall()
    versions = db.execute(f"""
        SELECT DISTINCT source_id, product_version FROM observations
        WHERE source_id IN ({placeholders}) AND acquisition_utc>=? AND acquisition_utc<?
          AND lon>=? AND lon<=? AND lat>=? AND lat<=?
    """, (*sources, f"{year}-01-01", f"{year+1}-01-01", bbox[0], bbox[2], bbox[1], bbox[3])).fetchall()
    return {
        "bbox": bbox, "year": year, "series": series, "sources": sources,
        "calendar_timezone": "UTC", "grid": GRID_VERSION,
        "metric": "detected_centroid_cell_days",
        "interpretation": "sampling proxy; not distinct fires or burned area",
        "demo_data": any(row["demo"] for row in batch_rows),
        "product_versions": [dict(row) for row in versions],
        "monthly": monthly, "daily": daily,
        "provenance": [dict(row) for row in batch_rows],
    }
