"""Build a compact, hash-bound MCD64A1 corroboration report.

The report is deliberately a lagged burned-area check. It never merges burned
area into the active-fire calendar and never treats an empty Burn Date raster
as evidence that a satellite passed or that no fire occurred.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
from collections import Counter
from datetime import datetime, timezone
import calendar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "fireatlas.sqlite3"

CASES = {
    "park-2024": {
        "region": "norcal", "bbox": (-122.0, 39.5, -121.3, 40.5),
        "active_start": "2024-07-17", "active_end": "2024-07-31",
        "months": [("2024-07", "Win03", "A2024183"), ("2024-08", "Win03", "A2024214")],
    },
    "grove-2025": {
        "region": "norcal", "bbox": (-121.55, 39.25, -121.28, 39.48),
        "active_start": "2025-07-04", "active_end": "2025-07-06",
        "months": [("2025-07", "Win03", "A2025182"), ("2025-08", "Win03", "A2025213")],
    },
}

REGIONAL_CHECKS = {
    "punjab-haryana": {
        "bbox": (73.8, 29.5, 77.6, 32.6),
        "months": [("2024-07", "Win18", "A2024183"), ("2025-07", "Win18", "A2025182")],
    }
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def raster_counts(path: Path, bbox: tuple[float, float, float, float]) -> dict:
    west, south, east, north = bbox
    command = [
        "gdal_translate", "-q", "-projwin", str(west), str(north), str(east), str(south),
        "-of", "XYZ", str(path), "/vsistdout/",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True, bufsize=1)
    counts = Counter()
    for line in process.stdout or ():
        fields = line.split()
        if len(fields) == 3:
            try:
                counts[int(float(fields[2]))] += 1
            except ValueError:
                continue
    if process.wait() != 0:
        raise RuntimeError(f"gdal_translate failed for {path}")
    valid = {str(day): count for day, count in sorted(counts.items()) if 1 <= day <= 366}
    return {
        "pixel_count": sum(counts.values()),
        "burned_pixels": sum(valid.values()),
        "burn_date_counts": valid,
        "unburned_pixels": counts.get(0, 0),
        "unmapped_pixels": counts.get(-1, 0),
        "water_or_invalid_pixels": counts.get(-2, 0),
        "other_values": {str(value): count for value, count in sorted(counts.items())
                         if value not in {-2, -1, 0} and not 1 <= value <= 366},
        "burn_date_min": min((int(day) for day in valid), default=None),
        "burn_date_max": max((int(day) for day in valid), default=None),
    }


def active_fire_summary(db: Path, bbox: tuple[float, float, float, float], start: str, end: str) -> dict:
    west, south, east, north = bbox
    with sqlite3.connect(db) as connection:
        rows = connection.execute(
            """SELECT o.source_id, COUNT(*), COUNT(DISTINCT o.grid_x || ':' || o.grid_y)
               FROM observations o JOIN batches b ON b.id=o.batch_id
               WHERE b.demo=0 AND o.source_id IN ('MODIS_SP','VIIRS_SNPP_SP')
                 AND o.acquisition_utc>=? AND o.acquisition_utc<?
                 AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=?
               GROUP BY o.source_id ORDER BY o.source_id""",
            (start, end + "T23:59:59.999999Z", west, east, south, north),
        ).fetchall()
    return {
        "utc_start": start, "utc_end": end,
        "rows_by_source": {row[0]: row[1] for row in rows},
        "unique_common_grid_cells_by_source": {row[0]: row[2] for row in rows},
    }


def one_check(*, label: str, bbox: tuple[float, float, float, float], month: str,
              window: str, doy: str, db: Path, active_fire: dict | None = None) -> dict:
    folder = ROOT / "NASA_data" / "mcd64a1" / month
    path = folder / f"MCD64monthly.{doy}.{window}.061.burndate.tif"
    qa_path = folder / f"MCD64monthly.{doy}.{window}.061.ba_qa.tif"
    if not path.exists():
        raise FileNotFoundError(path)
    if not qa_path.exists():
        raise FileNotFoundError(qa_path)
    return {
        "label": label, "month": month, "product": "MCD64A1", "collection": "6.1",
        "window": window, "source_filename": path.name, "source_sha256": sha256(path),
        "qa_source_filename": qa_path.name, "qa_source_sha256": sha256(qa_path),
        "bbox": list(bbox), "burn_date": raster_counts(path, bbox),
        "active_fire": active_fire or {},
    }


def build(db: Path) -> dict:
    cases = {}
    for case_id, spec in CASES.items():
        checks = []
        for month, window, doy in spec["months"]:
            year, month_number = (int(part) for part in month.split("-"))
            start = f"{month}-01"
            end = f"{month}-{calendar.monthrange(year, month_number)[1]:02d}"
            checks.append(one_check(label=case_id, bbox=spec["bbox"], month=month,
                                    window=window, doy=doy, db=db,
                                    active_fire=active_fire_summary(db, spec["bbox"], start, end)))
        cases[case_id] = {
            "region": spec["region"], "bbox": list(spec["bbox"]),
            "active_fire": active_fire_summary(db, spec["bbox"], spec["active_start"], spec["active_end"]),
            "checks": checks,
        }
    regional = {}
    for region, spec in REGIONAL_CHECKS.items():
        checks = []
        for month, window, doy in spec["months"]:
            year, month_number = (int(part) for part in month.split("-"))
            start = f"{month}-01"
            end = f"{month}-{calendar.monthrange(year, month_number)[1]:02d}"
            checks.append(one_check(label=region, bbox=spec["bbox"], month=month,
                                    window=window, doy=doy, db=db,
                                    active_fire=active_fire_summary(db, spec["bbox"], start, end)))
        regional[region] = {"bbox": list(spec["bbox"]), "checks": checks}
    return {
        "schema": "fireatlas-mcd64-corroboration-v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "loaded",
        "product": "MCD64A1 Collection 6.1 monthly burned area",
        "product_url": "https://doi.org/10.5067/MODIS/MCD64A1.061",
        "archive_url": "https://modis-fire.umd.edu/files/MODIS_C61_BA_User_Guide_1.1.pdf",
        "distribution": "University of Maryland fuoco SFTP; official guide section 4",
        "interpretation": "Lagged burned-area context only. Burn Date values 1–366 are mapped burned pixels; 0 is unburned, -1 unmapped, and -2 water/invalid. This is not active-fire truth, an overpass mask, cloud mask, or a fire perimeter.",
        "cases": cases,
        "regional_checks": regional,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--output", type=Path, default=ROOT / "fireatlas" / "samples" / "mcd64_corroboration.json")
    args = parser.parse_args()
    report = build(args.db)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "status": report["status"], "cases": list(report["cases"])}))


if __name__ == "__main__":
    main()
