"""Evidence-aware product availability labels for FIRMS archive exports."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path

NOTICE_FILE = Path(__file__).with_name("samples") / "sensor_notices.json"


@lru_cache(maxsize=8)
def _notice_cache(path: str, stamp=None) -> tuple[dict, ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != "fireatlas-sensor-notices-v1" or not isinstance(data.get("notices"), list):
        raise ValueError("unsupported sensor notice ledger")
    checked = []
    for item in data["notices"]:
        start = datetime.fromisoformat(item["start_utc"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(item["end_utc"].replace("Z", "+00:00"))
        if start.tzinfo != timezone.utc or end.tzinfo != timezone.utc or end < start:
            raise ValueError(f"invalid UTC interval in sensor notice {item.get('id')}")
        if not item.get("url", "").startswith("https://") or not item.get("quote", "").strip():
            raise ValueError(f"sensor notice {item.get('id')} needs a source URL and quoted evidence")
        if len(item["quote"].split()) > 25:
            raise ValueError(f"sensor notice {item.get('id')} quote exceeds 25 words")
        checked.append({**item, "_start": start, "_end": end})
    return tuple(checked)


def notices(path: str | Path = NOTICE_FILE) -> list[dict]:
    file=Path(path).resolve();info=file.stat()
    return list(_notice_cache(str(file),(info.st_mtime_ns,info.st_size)))


def notices_for_day(day: str | date, source_id: str, *, path: str | Path = NOTICE_FILE) -> list[dict]:
    selected = date.fromisoformat(day) if isinstance(day, str) else day
    start = datetime.combine(selected, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    result = []
    for item in notices(path):
        if item["source_id"] == source_id and item["_start"] < end and item["_end"] >= start:
            result.append({key: value for key, value in item.items() if not key.startswith("_")})
    return result


def source_status(day: str | date, source_id: str, *, complete_export: bool,
                  detection_count: int | None, path: str | Path = NOTICE_FILE) -> dict:
    """Classify export evidence without guessing overpass/cloud coverage.

    A complete export with no points is a zero-detection export. It never means
    that the satellite passed, saw clear sky, or observed a fire-free area.
    """
    matched = notices_for_day(day, source_id, path=path)
    selected = date.fromisoformat(day) if isinstance(day, str) else day
    day_start = datetime.combine(selected, time.min, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    partial_notice_day = any(
        item["_start"] > day_start or item["_end"] < day_end
        for item in notices(path) if item["source_id"] == source_id
        and item["_start"] < day_end and item["_end"] >= day_start
    )
    if matched:
        status = "documented_processing_gap"
    elif not complete_export:
        status = "unknown_export"
    elif detection_count:
        status = "detections_in_export"
    else:
        status = "zero_detections_exported"
    return {
        "source_id": source_id,
        "status": status,
        "complete_export": bool(complete_export),
        "detection_count": detection_count if complete_export else None,
        "observation_opportunity": "unknown",
        "notice_ids": [item["id"] for item in matched],
        "notices": matched,
        "notice_day_scope": "partial-utc-day" if matched and partial_notice_day else "full-utc-day" if matched else None,
    }
