"""Download a full AOI month from NASA FIRMS in documented 1-5 day windows."""

from __future__ import annotations

import calendar
import csv
import hashlib
import io
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen

from .core import REQUIRED_COLUMNS, SOURCES, ingest, validate_bbox
from .settings import firms_key

API_HOSTS = (
    "https://firms.modaps.eosdis.nasa.gov",
    "https://firms2.modaps.eosdis.nasa.gov",
)
BASE_URL = API_HOSTS[0] + "/api/area/csv"
AVAILABILITY_URL = API_HOSTS[0] + "/api/data_availability/csv"
FIRMS_SOURCES = {source for source in SOURCES if source != "NOAA_HMS_VIIRS"}


def _download(url: str, label: str) -> str:
    """Try NASA's documented secondary server for transport and server failures."""
    for index, host in enumerate(API_HOSTS):
        candidate = url.replace(API_HOSTS[0], host, 1)
        try:
            with urlopen(candidate, timeout=15) as response:
                return response.read().decode("utf-8-sig")
        except HTTPError as exc:
            # A rejected key, bad request or rate limit will not improve by
            # repeating the same request on another server.
            if exc.code < 500 or index == len(API_HOSTS) - 1:
                raise ValueError(f"FIRMS request failed for {label}: HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError):
            if index == len(API_HOSTS) - 1:
                raise ValueError(f"FIRMS request failed for {label}: primary and secondary servers unreachable") from None
    raise ValueError(f"FIRMS request failed for {label}: primary and secondary servers unavailable")


def availability(source_id="ALL"):
    if source_id != "ALL" and source_id not in FIRMS_SOURCES:
        raise ValueError("unsupported FIRMS source")
    key = firms_key()
    if not key:
        raise ValueError("Configure FIRMS_MAP_KEY or a local FIRMS key file first")
    url = "/".join((AVAILABILITY_URL, quote(key, safe=""), source_id))
    reader = csv.DictReader(io.StringIO(_download(url, "availability")))
    if not {"data_id", "min_date", "max_date"}.issubset(reader.fieldnames or []):
        raise ValueError("FIRMS did not accept the availability request; check key activation and service status")
    rows = []
    for row in reader:
        try:
            rows.append({"data_id": row["data_id"], "min_date": date.fromisoformat(row["min_date"]).isoformat(),
                         "max_date": date.fromisoformat(row["max_date"]).isoformat()})
        except (TypeError, ValueError):
            raise ValueError("FIRMS returned an invalid availability date") from None
    return rows


def fetch_month(db, *, month: str, source_id: str, bbox: tuple[float, float, float, float], directory: Path, refresh: bool = False, available_sources=None) -> dict:
    """Fetch/ingest one complete month. The MAP_KEY remains only in the request URL."""
    if source_id not in FIRMS_SOURCES:
        raise ValueError(f"unsupported source: {source_id}")
    validate_bbox(bbox)
    start = date.fromisoformat(month + "-01")
    days = calendar.monthrange(start.year, start.month)[1]
    key = firms_key()
    if not key and refresh:
        raise ValueError("FIRMS_MAP_KEY is required for a fresh download")
    label = hashlib.sha256(str(bbox).encode()).hexdigest()[:12]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{source_id}_{month}_{label}.csv"
    if not path.exists() or refresh:
        if not key:
            raise ValueError("FIRMS_MAP_KEY is required; obtain a free key from NASA FIRMS")
        availability_rows = availability(source_id) if available_sources is None else available_sources
        available = next((entry for entry in availability_rows if entry.get("data_id") == source_id), None)
        last_day = start + timedelta(days=days - 1)
        if not available or not (available["min_date"] <= start.isoformat() and
                                 available["max_date"] >= last_day.isoformat()):
            raise ValueError(f"{source_id} is not available for the full {month} month")
        coords = ",".join(str(number) for number in bbox)
        all_rows = []
        fieldnames = None
        for offset in range(0, days, 5):
            day = start + timedelta(days=offset)
            span = min(5, days - offset)
            url = "/".join((BASE_URL, quote(key, safe=""), source_id, coords, str(span), day.isoformat()))
            body = _download(url, str(day))
            reader = csv.DictReader(io.StringIO(body))
            if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
                raise ValueError(f"FIRMS did not return expected CSV fields for {day}; month was not imported")
            if fieldnames is None:
                fieldnames = reader.fieldnames
            elif fieldnames != reader.fieldnames:
                raise ValueError("FIRMS field set changed during monthly download")
            all_rows.extend(reader)
        temporary = path.with_suffix(".tmp")
        try:
            with temporary.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_rows)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    # A source URI with a literal placeholder keeps the private key out of SQLite.
    with db:
        if refresh:
            old_batches = db.execute("""
                SELECT batch_id FROM export_windows
                WHERE source_id=? AND month=? AND west=? AND south=? AND east=? AND north=?
            """, (source_id, month, *bbox)).fetchall()
            for old in old_batches:
                db.execute("DELETE FROM observations WHERE batch_id=?", (old["batch_id"],))
                db.execute("DELETE FROM export_windows WHERE batch_id=?", (old["batch_id"],))
                db.execute("DELETE FROM batches WHERE id=?", (old["batch_id"],))
        return ingest(
            db, path, source_id,
            source_uri=f"{BASE_URL}/[MAP_KEY]/{source_id}/{','.join(map(str, bbox))}/1..5/{month}",
            complete_month=month, bbox=bbox,
        )
