"""Bounded, authentic FIRMS snapshots for the landing globe."""

from datetime import date, timedelta
import math

SOURCES = {
    "MODIS_NRT": "MODIS · Terra / Aqua",
    "VIIRS_NOAA20_NRT": "VIIRS · NOAA-20",
    "VIIRS_NOAA21_NRT": "VIIRS · NOAA-21",
    "VIIRS_SNPP_NRT": "VIIRS · Suomi NPP",
}
BIN_X = "MIN(359,CAST(o.lon+180 AS INTEGER))"
BIN_Y = "MIN(179,CAST(o.lat+90 AS INTEGER))"


def frp_number(raw):
    try:
        value = float(raw)
        return value if math.isfinite(value) and value >= 0 else None
    except (ValueError, TypeError):
        return None


def selection(db, source="all", day="all"):
    if source != "all" and source not in SOURCES:
        raise ValueError("unsupported globe satellite")
    if day != "all":
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError("use a YYYY-MM-DD observation date")
    sources = tuple(SOURCES) if source == "all" else (source,)
    # Each lookup can stop at the newest row in the source/date index.
    latest_rows = [db.execute("""SELECT o.acquisition_utc FROM observations o
        JOIN batches b ON b.id=o.batch_id WHERE b.demo=0 AND o.source_id=?
        ORDER BY o.acquisition_utc DESC LIMIT 1""", (name,)).fetchone() for name in SOURCES]
    latest = max((r[0] for r in latest_rows if r), default=None)
    end = date.fromisoformat(latest[:10]) if latest else None
    start = end - timedelta(days=7) if end else None
    if day != "all" and end and not start <= date.fromisoformat(day) <= end:
        raise ValueError("date outside the imported globe snapshot")
    begin = day if day != "all" else str(start) if start else "2000-01-01"
    stop = str(date.fromisoformat(day) + timedelta(days=1)) if day != "all" else str(end + timedelta(days=1)) if end else "2000-01-02"
    where = f"b.demo=0 AND o.source_id IN ({','.join('?' for _ in sources)}) AND o.acquisition_utc>=? AND o.acquisition_utc<?"
    return where, (*sources, begin, stop), latest, start, end


def snapshot(db, *, source="all", day="all"):
    where, args, latest, start, end = selection(db, source, day)
    db.create_function("valid_frp", 1, frp_number, deterministic=True)
    rows = db.execute(f"""SELECT {BIN_X} AS x,{BIN_Y} AS y,AVG(o.lon) AS lon,AVG(o.lat) AS lat,
        COUNT(*) AS count,MIN(o.acquisition_utc) AS first,MAX(o.acquisition_utc) AS last,
        MAX(valid_frp(o.frp_raw)) AS max_frp
        FROM observations o JOIN batches b ON b.id=o.batch_id WHERE {where}
        GROUP BY x,y ORDER BY count DESC,x,y""", args).fetchall()
    features = [{"id": f"{r['x']}:{r['y']}", "lon": round(r["lon"], 5), "lat": round(r["lat"], 5),
                 "count": r["count"], "first": r["first"], "last": r["last"], "max_frp_mw": r["max_frp"]} for r in rows]
    all_where, all_args, _, _, _ = selection(db, "all", "all")
    available = [dict(r) for r in db.execute(f"""SELECT o.source_id,COUNT(*) AS count,
        MIN(o.acquisition_utc) AS first,MAX(o.acquisition_utc) AS last
        FROM observations o JOIN batches b ON b.id=o.batch_id WHERE {all_where} GROUP BY o.source_id""", all_args)]
    for item in available:
        item["label"] = SOURCES[item["source_id"]]
    daily = [dict(r) for r in db.execute(f"""SELECT substr(o.acquisition_utc,1,10) AS date,COUNT(*) AS count
        FROM observations o JOIN batches b ON b.id=o.batch_id WHERE {where} GROUP BY date ORDER BY date""", args)]
    return {"data_class": "authentic", "kind": "imported-thermal-detections", "source": source, "date": day,
            "latest_observation": latest, "window_start": str(start) if start else None, "window_end": str(end) if end else None,
            "total": sum(r["count"] for r in features), "cluster_degrees": 1, "clusters": features,
            "sources": available, "daily": daily,
            "note": "Imported snapshot. Counts are satellite detections; multiple satellites can observe the same fire. First observation is not ignition time. Activity after the last observation is unknown. Markers group detections in 1° cells, not burned-area boundaries."}


def detail(db, *, cell, source="all", day="all"):
    try:
        x, y = map(int, cell.split(":"))
    except (ValueError, AttributeError):
        raise ValueError("invalid globe cell") from None
    if not 0 <= x < 360 or not 0 <= y < 180:
        raise ValueError("invalid globe cell")
    where, args, _, _, _ = selection(db, source, day)
    db.create_function("valid_frp", 1, frp_number, deterministic=True)
    west, south = x - 180, y - 90
    where += f" AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=? AND {BIN_X}=? AND {BIN_Y}=?"
    args = (*args, west, west + 1, south, south + 1, x, y)
    rows = db.execute(f"""SELECT o.detection_id,o.lon,o.lat,o.acquisition_utc,o.source_id,o.platform,
        valid_frp(o.frp_raw) AS frp_mw,o.confidence_raw,o.daynight,b.file_sha256
        FROM observations o JOIN batches b ON b.id=o.batch_id WHERE {where}
        ORDER BY o.acquisition_utc DESC,o.detection_id LIMIT 12""", args).fetchall()
    counts = [dict(r) for r in db.execute(f"""SELECT o.source_id,COUNT(*) AS count,MIN(o.acquisition_utc) AS first,
        MAX(o.acquisition_utc) AS last,MAX(valid_frp(o.frp_raw)) AS max_frp_mw
        FROM observations o JOIN batches b ON b.id=o.batch_id WHERE {where} GROUP BY o.source_id""", args)]
    return {"id": cell, "data_class": "authentic", "bbox": [west, south, west + 1, south + 1],
            "source": source, "date": day, "total": sum(r["count"] for r in counts), "sources": counts,
            "observations": [dict(r) for r in rows], "sample_order": "latest acquisition first; up to 12 records",
            "condition": "Thermal activity detected at the listed times. Current fire status, ignition time and perimeter are unknown."}
