"""Deterministic presentation fixtures, isolated from authentic observations."""

from __future__ import annotations

import contextlib
import csv
import hashlib
import json
from pathlib import Path

from .core import connect, ingest, validate_bbox
from .demo import BBOX, FIELDS

VERSION = "presentation-v1"
YEARS = (2023, 2024, 2025, 2026)
DEFAULT_VIEW = {"year": 2026, "month": 9, "bbox": list(BBOX)}
SEEDS = Path(__file__).with_name("samples") / "presentation_seeds.json"
SEASON = (2, 2, 3, 4, 6, 9, 13, 17, 20, 12, 5, 3)
PREFIX = f"synthetic://fireatlas/{VERSION}/"


def provenance():
    seed = json.loads(SEEDS.read_text())
    return {
        "version": VERSION, "synthetic": True, "years": list(YEARS),
        "default_view": DEFAULT_VIEW, "seed_sha256": hashlib.sha256(SEEDS.read_bytes()).hexdigest(),
        "seed_files": [{k: f[k] for k in ("filename", "sha256", "input_rows", "sample_scope")} for f in seed["files"]],
        "method": "FRP, scan, track, confidence and day/night attributes sampled from downloaded NASA CSV rows. All locations, dates, seasonal patterns and paired satellite scenarios are invented. MODIS_SP and VIIRS_SNPP_SP are synthetic comparison schemas, not recovered standard products or real S-NPP observations.",
        "context_method": "Vegetation, land cover and weather values are deterministic illustrations; they are not measured, forecast, or inferred from fire detections.",
    }


def ensure_presentation(directory: Path, database: Path):
    """Resume safely after interruption; never write fixtures into an authentic DB."""
    directory.mkdir(parents=True, exist_ok=True)
    seed = json.loads(SEEDS.read_text())
    with contextlib.closing(connect(database)) as db:
        if db.execute("SELECT 1 FROM batches WHERE demo=0 LIMIT 1").fetchone():
            raise ValueError("Presentation fixtures require a dedicated synthetic database")
        existing = {r[0] for r in db.execute("SELECT source_uri FROM batches WHERE source_uri LIKE ?", (PREFIX + "%",))}
        for year in YEARS:
            for month in range(1, 13):
                for sensor, source in (("MODIS", "MODIS_SP"), ("VIIRS", "VIIRS_SNPP_SP")):
                    name = f"{source}_{year}_{month:02d}.csv"
                    if PREFIX + name in existing:
                        continue
                    samples = [(f, r) for f in seed["files"] if f["sensor"] == sensor for r in f["samples"]]
                    rows = []
                    active_days = min(26, SEASON[month - 1] + (year - YEARS[0]) * 2)
                    for day in range(1, active_days + 1):
                        for group in range(3):
                            for cell in range(4):
                                # Shared cells plus sensor-only cells; connected groups evolve daily.
                                if (sensor == "MODIS" and cell == 3) or (sensor == "VIIRS" and cell == 0):
                                    continue
                                if (day + group + cell) % 5 == 0:
                                    continue
                                f, sample = samples[(day * 7 + group * 4 + cell + year) % len(samples)]
                                for pixel in range(1 if sensor == "MODIS" else 2):
                                    rows.append({
                                        "latitude": f"{39.55 + group * .38 + cell * .011:.5f}",
                                        "longitude": f"{-121.72 + group * .42 + (cell % 2) * .011:.5f}",
                                        "acq_date": f"{year}-{month:02d}-{day:02d}", "acq_time": "1230" if pixel == 0 else "1240",
                                        "satellite": "T" if sensor == "MODIS" else "N", "instrument": sensor,
                                        "version": VERSION,
                                        **{k: sample[k] for k in ("confidence", "scan", "track", "frp", "daynight")},
                                        "synthetic": "true", "seed_filename": f["filename"],
                                        "seed_file_sha256": f["sha256"], "seed_csv_line": sample["csv_line"],
                                        "derivation": "Measured attributes reused; invented position/date/platform scenario. Not a NASA observation.",
                                    })
                    path = directory / name
                    with path.open("w", newline="") as output:
                        writer = csv.DictWriter(output, fieldnames=FIELDS + ["synthetic", "seed_filename", "seed_file_sha256", "seed_csv_line", "derivation"])
                        writer.writeheader()
                        writer.writerows(rows)
                    ingest(db, path, source, source_uri=PREFIX + name, complete_month=f"{year}-{month:02d}", bbox=BBOX, demo=True)


def context_fixture(*, year, month, bbox, layer):
    """Coarse local GeoJSON, clipped to the fixture AOI; never global fabricated coverage."""
    validate_bbox(bbox)
    if year not in YEARS or not 1 <= month <= 12 or layer not in ("ndvi", "landcover", "fwi"):
        raise ValueError("Synthetic context supports 2023–2026 and ndvi, landcover, fwi")
    west, south, east, north = BBOX
    features = []
    classes = ("Forest", "Shrubland", "Grassland", "Cropland")
    for y in range(10):
        for x in range(10):
            w, s = max(west + x * .2, bbox[0]), max(south + y * .2, bbox[1])
            e, n = min(west + (x + 1) * .2, bbox[2]), min(south + (y + 1) * .2, bbox[3])
            if w >= e or s >= n:
                continue
            noise = ((x * 17 + y * 29 + year) % 31) / 30
            if layer == "ndvi":
                value = round(.28 + noise * .5 - SEASON[month - 1] / 100, 2)
                color = f"hsl({75 + value * 80:.0f}, 45%, {25 + value * 22:.0f}%)"
                label = f"Illustrative NDVI: {value}"
            elif layer == "landcover":
                value = classes[(x + 2 * y) % 4]
                color = ("#548d6c", "#b7a66c", "#99b871", "#d5bf83")[(x + 2 * y) % 4]
                label = f"Illustrative cover: {value}"
            else:
                value = round(8 + SEASON[month - 1] * 1.8 + noise * 20, 1)
                color = f"hsl({60 - value * .8:.0f}, 80%, 55%)"
                label = f"Illustrative weather index: {value} (arbitrary units; not FWI)"
            features.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[w,s],[e,s],[e,n],[w,n],[w,s]]]},
                             "properties": {"synthetic": True, "value": value, "color": color, "label": label}})
    return {"type": "FeatureCollection", "synthetic": True, "source_uri": PREFIX + "context",
            "year": year, "month": month, "layer": layer, "time_resolution": "illustrative monthly snapshot",
            "note": "SYNTHETIC illustration · Northern California only · not satellite imagery or a weather forecast",
            "features": features}
