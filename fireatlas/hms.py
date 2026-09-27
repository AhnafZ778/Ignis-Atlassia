"""Import NOAA HMS historical VIIRS fire points from complete daily archives.

HMS is a North American satellite analysis product. Its VIIRS points are a
separate source cohort from NASA FIRMS and are never counted as FIRMS pixels.
"""

from __future__ import annotations

import calendar
import csv
import hashlib
import io
import json
import math
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import shapefile

from .core import REQUIRED_COLUMNS, ingest, validate_bbox

ARCHIVE = "https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/Fire_Points/Shapefile"
SOURCE = "NOAA_HMS_VIIRS"
PLATFORMS = {"SUOMI NPP", "NOAA 20", "NOAA 21"}
FIELDS = [*sorted(REQUIRED_COLUMNS), "hms_archive_date", "hms_archive_sha256",
          "hms_method", "hms_ecosystem", "hms_frp", "hms_resolution_note"]
MAX_ARCHIVE_BYTES = 15_000_000


def _archive_url(day: date) -> str:
    return f"{ARCHIVE}/{day:%Y/%m}/hms_fire{day:%Y%m%d}.zip"


def _download_day(day: date, directory: Path, *, refresh: bool = False) -> Path:
    path = directory / f"hms_fire{day:%Y%m%d}.zip"
    if path.exists() and path.stat().st_size <= MAX_ARCHIVE_BYTES and not refresh:
        try:
            with zipfile.ZipFile(path) as archive:
                if (all(f"hms_fire{day:%Y%m%d}.{ext}" in archive.namelist() for ext in ("shp", "shx", "dbf", "prj"))
                        and all(item.file_size <= 35_000_000 for item in archive.infolist())):
                    return path
        except zipfile.BadZipFile:
            pass
    request = Request(_archive_url(day), headers={"User-Agent": "FireAtlas/1.0 (NASA Space Apps project)"})
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read(MAX_ARCHIVE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ValueError(f"NOAA HMS archive unavailable for {day.isoformat()}") from exc
    if len(body) > MAX_ARCHIVE_BYTES:
        raise ValueError(f"NOAA HMS archive too large for {day.isoformat()}")
    temporary = path.with_suffix(".zip.tmp")
    try:
        temporary.write_bytes(body)
        with zipfile.ZipFile(temporary) as archive:
            stem = f"hms_fire{day:%Y%m%d}"
            if not all(f"{stem}.{ext}" in archive.namelist() for ext in ("shp", "shx", "dbf", "prj")):
                raise ValueError(f"NOAA HMS archive incomplete for {day.isoformat()}")
            if any(item.file_size > 35_000_000 for item in archive.infolist()):
                raise ValueError(f"NOAA HMS archive expanded size too large for {day.isoformat()}")
        temporary.replace(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError(f"NOAA HMS archive invalid for {day.isoformat()}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _rows(path: Path, day: date, bbox: tuple[float, float, float, float]):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    stem = f"hms_fire{day:%Y%m%d}"
    selected = 0
    with zipfile.ZipFile(path) as archive:
        with io.BytesIO(archive.read(stem + ".shp")) as shp, io.BytesIO(archive.read(stem + ".shx")) as shx, io.BytesIO(archive.read(stem + ".dbf")) as dbf:
            reader = shapefile.Reader(shp=shp, shx=shx, dbf=dbf)
            fields = {field[0] for field in reader.fields[1:]}
            required = {"Lon", "Lat", "YearDay", "Time", "Satellite", "Method", "Ecosystem", "FRP"}
            if reader.shapeType != shapefile.POINT or not required.issubset(fields):
                raise ValueError(f"NOAA HMS point schema changed for {day.isoformat()}")
            total = len(reader)
            for shape_record in reader.iterShapeRecords():
                record = shape_record.record.as_dict()
                if record["Method"] != "VIIRS" or record["Satellite"] not in PLATFORMS:
                    continue
                lon, lat = float(record["Lon"]), float(record["Lat"])
                if not (math.isfinite(lon) and math.isfinite(lat) and
                        abs(shape_record.shape.points[0][0] - lon) < 0.00001 and
                        abs(shape_record.shape.points[0][1] - lat) < 0.00001):
                    raise ValueError(f"NOAA HMS coordinate mismatch for {day.isoformat()}")
                if not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]):
                    continue
                if int(record["YearDay"]) != int(day.strftime("%Y%j")):
                    raise ValueError(f"NOAA HMS acquisition date mismatch for {day.isoformat()}")
                time = str(record["Time"]).strip().zfill(4)
                if not re.fullmatch(r"\d{4}", time) or int(time[:2]) > 23 or int(time[2:]) > 59:
                    raise ValueError(f"NOAA HMS acquisition time invalid for {day.isoformat()}")
                frp = record["FRP"]
                if frp is not None and not math.isfinite(float(frp)):
                    raise ValueError(f"NOAA HMS FRP invalid for {day.isoformat()}")
                selected += 1
                yield {
                    "latitude": lat, "longitude": lon, "acq_date": day.isoformat(), "acq_time": time,
                    "satellite": record["Satellite"], "instrument": "VIIRS", "confidence": "not provided",
                    "version": "NOAA HMS daily archive", "scan": "0.375", "track": "0.375",
                    "frp": "" if frp is None else frp, "daynight": "U",
                    "hms_archive_date": day.isoformat(), "hms_archive_sha256": digest,
                    "hms_method": record["Method"], "hms_ecosystem": record["Ecosystem"],
                    "hms_frp": frp, "hms_resolution_note": "375 m nominal VIIRS I-band resolution; not the measured pixel footprint",
                }
    return {"date": day.isoformat(), "url": _archive_url(day), "sha256": digest,
            "archive_points": total, "selected_viirs_points": selected}


def harvest_month(db, *, month: str, bbox: tuple[float, float, float, float], directory: Path,
                  refresh: bool = False, workers: int = 4) -> dict:
    """Fetch every daily ZIP before asserting a complete AOI/month source export."""
    validate_bbox(bbox)
    start = date.fromisoformat(month + "-01")
    days = [start + timedelta(days=index) for index in range(calendar.monthrange(start.year, start.month)[1])]
    if days[-1] >= date.today():
        raise ValueError("NOAA HMS complete-month imports require a finished historical month")
    if db.execute("SELECT 1 FROM batches WHERE demo=1 LIMIT 1").fetchone():
        raise ValueError("NOAA HMS authentic records require a separate database from the synthetic demo")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as pool:
        paths = list(pool.map(lambda day: _download_day(day, directory, refresh=refresh), days))
    label = hashlib.sha256(json.dumps(bbox).encode()).hexdigest()[:12]
    csv_path = directory / f"{SOURCE}_{month}_{label}.csv"
    manifest_path = csv_path.with_suffix(".manifest.json")
    temporary = csv_path.with_suffix(".csv.tmp")
    archives = []
    try:
        with temporary.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            for day, path in zip(days, paths):
                rows = _rows(path, day, bbox)
                while True:
                    try:
                        writer.writerow(next(rows))
                    except StopIteration as finished:
                        archives.append(finished.value)
                        break
        temporary.replace(csv_path)
    finally:
        temporary.unlink(missing_ok=True)
    result = ingest(db, csv_path, SOURCE, source_uri=f"{ARCHIVE}/{start:%Y/%m}/",
                    complete_month=month, bbox=bbox)
    manifest = {"source": SOURCE, "month": month, "bbox": bbox,
                "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(), "archives": archives,
                "selection": "VIIRS method; Suomi NPP, NOAA-20 and NOAA-21; acquisition centroids inside AOI",
                "limitations": "HMS covers North America. Scan/track use nominal 375 m, not individual pixel footprints. Confidence and day/night are not supplied."}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {**result, "source": SOURCE, "month": month, "bbox": bbox,
            "days_verified": len(archives), "selected_viirs_points": sum(item["selected_viirs_points"] for item in archives),
            "manifest": str(manifest_path)}
