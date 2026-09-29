"""Freeze a rule-based CAL FIRE July incident ledger for external context checks.

This is a published-incident association exercise, not a complete fire truth
set or a test of satellite sensitivity when pass/cloud coverage is unknown.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sqlite3
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .archive import BBOX
from .core import connect
from .validity import _km

SAMPLE = Path(__file__).with_name("samples") / "validity_incident_cohort.json"
BASE = "https://www.fire.ca.gov"
SELECTED = {"/incidents/2024/7/24/park-fire", "/incidents/2025/7/4/grove-fire"}
OFFICIAL_PAGE_FALLBACK = {
    "/incidents/2024/7/14/five-fire": {
        "lat": 35.3858693, "lon": -119.367525,
        "published_start_local": "07/14/2024 1:17 PM",
        "verification_note": "CAL FIRE public incident page was readable through the official page index on 2026-09-29; direct bulk fetch returned HTTP 403. Location is outside the archive area; no evaluation outcome depends on this fallback.",
    },
}
LINK = re.compile(r'<a\s+href="(/incidents/(?:2024|2025)/7/\d+/[^\"]+)"[^>]*>(.*?)</a>', re.I | re.S)
START = re.compile(r'Date Started</strong>\s*<br\s*/?>\s*([^<]+)', re.I)
COORD = re.compile(r'factoid__label"[^>]*>\s*\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]', re.I)


def _read(url: str) -> bytes:
    last = None
    for attempt in range(3):
        try:
            result = subprocess.run(["curl", "--location", "--fail", "--silent", "--show-error",
                                     "--max-time", "25", url], capture_output=True, timeout=30)
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode(errors="replace").strip()[:180])
            return result.stdout
        except Exception as error:
            last = error
            if attempt < 2:
                time.sleep(0.7 * (attempt + 1))
    raise RuntimeError(f"could not retrieve {url}: {last}") from last


def _incident(path: str, name: str) -> dict:
    url = BASE + path.rstrip("/") + "/"
    result = {"name": name, "url": url, "archive_path": path}
    try:
        body = _read(url)
    except RuntimeError as error:
        return {**result, "status": "unavailable-page", "error": str(error)}
    text = body.decode("utf-8", errors="replace")
    result["page_sha256"] = hashlib.sha256(body).hexdigest()
    coordinate = COORD.search(text)
    if not coordinate:
        return {**result, "status": "excluded-no-published-coordinate"}
    lat, lon = float(coordinate.group(1)), float(coordinate.group(2))
    result.update({"lat": lat, "lon": lon})
    west, south, east, north = BBOX
    if not (west <= lon <= east and south <= lat <= north):
        return {**result, "status": "excluded-outside-archive-area"}
    if path in SELECTED:
        result["status"] = "selected-illustration-excluded-from-evaluation"
    else:
        result["status"] = "eligible"
    started = START.search(text)
    if not started:
        return {**result, "status": "excluded-no-published-start-time"}
    local_text = html.unescape(started.group(1)).strip()
    try:
        local = datetime.strptime(local_text, "%m/%d/%Y %I:%M %p").replace(tzinfo=ZoneInfo("America/Los_Angeles"))
    except ValueError:
        return {**result, "status": "excluded-unparseable-start-time", "published_start": local_text}
    result["published_start_local"] = local_text
    result["start_utc_interpreted"] = local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return result


def refresh(existing: dict | None = None) -> dict:
    if existing and existing.get("schema") == "fireatlas-calfire-july-cohort-v1":
        indexes = existing["year_indexes"]
        incidents = {row["archive_path"]: row["name"] for row in existing["incidents"]}
    else:
        indexes = []
        incidents = {}
        for year in (2024, 2025):
            url = f"{BASE}/incidents/{year}"
            body = _read(url)
            text = body.decode("utf-8", errors="replace")
            links = [(path, html.unescape(re.sub(r"<[^>]+>", "", title)).strip())
                     for path, title in LINK.findall(text) if path.startswith(f"/incidents/{year}/7/")]
            for path, name in links:
                incidents[path] = name
            indexes.append({"url": url, "sha256": hashlib.sha256(body).hexdigest(),
                            "july_incident_links": len({path for path, _ in links})})
    prior = {row["archive_path"]: row for row in (existing or {}).get("incidents", [])
             if row["status"] != "unavailable-page"}
    rows = [prior[path] for path in incidents if path in prior]
    remaining = sum(path not in prior for path in incidents)
    with ThreadPoolExecutor(max_workers=1 if remaining < 25 else 4) as pool:
        tasks = {pool.submit(_incident, path, name): path for path, name in incidents.items() if path not in prior}
        for future in as_completed(tasks):
            rows.append(future.result())
    for index, row in enumerate(rows):
        fallback = OFFICIAL_PAGE_FALLBACK.get(row["archive_path"])
        if row["status"] == "unavailable-page" and fallback:
            rows[index] = {"name": row["name"], "url": row["url"],
                           "archive_path": row["archive_path"],
                           "status": "excluded-outside-archive-area",
                           "source_verification": "official-page-index-fallback",
                           **fallback}
    rows.sort(key=lambda row: row["archive_path"])
    failures = sum(row["status"] == "unavailable-page" for row in rows)
    return {"schema": "fireatlas-calfire-july-cohort-v1",
            "retrieved_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "archive_bbox": list(BBOX), "years": [2024, 2025],
            "rule": "Every July link on CAL FIRE's 2024 and 2025 year archive pages; published start coordinate inside archive_bbox; Park and Grove selected cases excluded; first standard FIRMS detection within 5 km and 48 hours after published start.",
            "year_indexes": indexes, "pages_complete": failures == 0,
            "failed_pages": failures,
            "official_page_index_fallbacks": sum(row.get("source_verification") == "official-page-index-fallback" for row in rows),
            "incidents": rows}


def candidate_rows(cohort: dict, db: sqlite3.Connection) -> dict[str, list[dict]]:
    """Freeze every point in the rectangular prefilter for each eligible incident."""
    candidates = {}
    for incident in cohort["incidents"]:
        if incident["status"] != "eligible":
            continue
        start = datetime.fromisoformat(incident["start_utc_interpreted"].replace("Z", "+00:00"))
        end = start + timedelta(hours=48)
        records = db.execute("""
            SELECT o.detection_id,o.source_id,o.acquisition_utc,o.lat,o.lon,
                   o.product_version,o.source_uri,b.file_sha256
            FROM observations o JOIN batches b ON b.id=o.batch_id
            WHERE o.source_id IN ('MODIS_SP','VIIRS_SNPP_SP') AND o.processing_level='SP' AND b.demo=0
              AND o.acquisition_utc>=? AND o.acquisition_utc<?
              AND o.lon BETWEEN ? AND ? AND o.lat BETWEEN ? AND ?
            ORDER BY o.acquisition_utc,o.detection_id
        """, (start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z"),
              incident["lon"] - .1, incident["lon"] + .1,
              incident["lat"] - .1, incident["lat"] + .1)).fetchall()
        candidates[incident["archive_path"]] = [dict(row) for row in records]
    return candidates


def evaluate(cohort: dict, db: sqlite3.Connection | None = None,
             *, candidates: dict[str, list[dict]] | None = None) -> dict:
    if candidates is None:
        if db is None:
            raise ValueError("candidate rows or a database are required")
        candidates = candidate_rows(cohort, db)
    evaluated = []
    for incident in cohort["incidents"]:
        if incident["status"] != "eligible":
            continue
        start = datetime.fromisoformat(incident["start_utc_interpreted"].replace("Z", "+00:00"))
        end = start + timedelta(hours=48)
        nearby = candidates[incident["archive_path"]]
        for row in nearby:
            if row["source_id"] not in ("MODIS_SP", "VIIRS_SNPP_SP") or not (
                    start <= datetime.fromisoformat(row["acquisition_utc"].replace("Z", "+00:00")) < end
                    and incident["lon"] - .1 <= row["lon"] <= incident["lon"] + .1
                    and incident["lat"] - .1 <= row["lat"] <= incident["lat"] + .1):
                raise ValueError("incident candidate row outside the frozen search rule")
        first = next(({"detection_id": row["detection_id"], "source_id": row["source_id"],
                       "acquisition_utc": row["acquisition_utc"],
                       "distance_km": round(_km(incident["lat"], incident["lon"], row["lat"], row["lon"]), 2)}
                      for row in sorted(nearby, key=lambda item: (item["acquisition_utc"], item["detection_id"]))
                      if _km(incident["lat"], incident["lon"], row["lat"], row["lon"]) <= 5), None)
        evaluated.append({"name": incident["name"], "url": incident["url"],
                          "published_start_local": incident["published_start_local"],
                          "lat": incident["lat"], "lon": incident["lon"],
                          "status": "nearby-detection" if first else "miss",
                          "first_detection": first})
    return {"schema": "fireatlas-calfire-association-v1",
            "cohort_complete": cohort["pages_complete"],
            "published_july_links": len(cohort["incidents"]),
            "eligible_additional_incidents": len(evaluated),
            "nearby_detections": sum(item["status"] == "nearby-detection" for item in evaluated),
            "misses": sum(item["status"] == "miss" for item in evaluated),
            "interpretation": "Temporal-spatial association only. Unknown pass/cloud coverage, false positives, and incomplete official incident publication prevent a satellite detection-rate claim.",
            "results": evaluated}


def load(path: str | Path = SAMPLE) -> dict:
    return json.loads(Path(path).read_text())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Freeze public CAL FIRE July 2024–25 cohort")
    parser.add_argument("--output", type=Path, default=SAMPLE)
    args = parser.parse_args()
    cohort = refresh(load(args.output) if args.output.exists() else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(cohort, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"published_july_links": len(cohort["incidents"]),
                      "eligible": sum(row["status"] == "eligible" for row in cohort["incidents"]),
                      "failed_pages": cohort["failed_pages"]}, indent=2))
