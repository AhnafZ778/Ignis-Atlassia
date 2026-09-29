"""Evidence-first responder briefings derived from the harmonized calendar.

This module deliberately produces a historical review brief, not a live
incident assessment, route, dispatch instruction, or fire forecast.  It only
summarizes values already exposed by :func:`fireatlas.core.calendar` and
points the user back to the source records.
"""

from __future__ import annotations

from .core import SERIES, calendar, validate_bbox


def responder_briefing(db, *, year: int, month: int, series: str,
                       bbox: tuple[float, float, float, float]) -> dict:
    """Return a bounded historical review brief for one calendar month."""
    if series not in SERIES:
        raise ValueError("invalid series")
    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    validate_bbox(bbox)
    summary = calendar(db, bbox=bbox, year=year, series=series)
    selected = summary["monthly"][month - 1]
    daily = [item for item in summary["daily"] if item["date_utc"].startswith(f"{year}-{month:02d}")]
    observed = [item for item in daily if item["detected_cell_days"] is not None]
    active = [item for item in observed if item["detected_cell_days"] > 0]
    ranked = sorted(active, key=lambda item: (-item["detected_cell_days"], item["date_utc"]))[:5]
    unknown_days = sum(item["detected_cell_days"] is None for item in daily)
    complete = bool(selected["export_window_complete"])
    baseline = selected["baseline_median"]
    anomaly = selected["anomaly_cell_days"]
    demo = bool(summary["demo_data"])

    if not complete:
        status = "insufficient-evidence"
        headline = "This period is incomplete."
        action = "Do not rank it against historical activity until the source export is complete."
    elif baseline is None:
        status = "baseline-unavailable"
        headline = "This period has observations but no comparable baseline."
        action = "Use the source evidence for review and avoid an unusual-activity claim."
    elif anomaly is not None and anomaly > 0:
        status = "historical-review-candidate"
        headline = f"Observed activity is {anomaly:,} cell-days above the prior median."
        action = "Invite a human analyst to inspect the dates and source records behind this signal."
    elif anomaly is not None and anomaly < 0:
        status = "below-baseline"
        headline = f"Observed activity is {abs(anomaly):,} cell-days below the prior median."
        action = "Review the source and coverage evidence before interpreting the decrease."
    else:
        status = "within-baseline"
        headline = "Observed activity is near the prior median."
        action = "Use the calendar and evidence records for historical comparison."

    return {
        "schema": "fireatlas-responder-briefing-v1",
        "classification": "synthetic" if demo else "authentic-imported",
        "historical_only": True,
        "operational": False,
        "year": year,
        "month": month,
        "series": series,
        "bbox": list(bbox),
        "calendar_timezone": summary["calendar_timezone"],
        "grid": summary["grid"],
        "metric": summary["metric"],
        "status": status,
        "headline": headline,
        "action": action,
        "selected_month": selected,
        "active_days": [{"date_utc": item["date_utc"], "detected_cell_days": item["detected_cell_days"]}
                        for item in ranked],
        "active_days_count": len(active),
        "observed_days": len(observed),
        "unknown_days": unknown_days,
        "context": {
            "terrain": "not integrated",
            "fuels": "not integrated",
            "measured_weather": "not integrated",
            "official_incident_context": "not integrated",
        },
        "limitations": [
            "A detected centroid cell-day is a sampling proxy, not a fire count, perimeter, or burned area.",
            "Satellite observation coverage remains unknown without pass and cloud masks.",
            "This brief does not issue an evacuation order, flight plan, dispatch instruction, or containment advice.",
        ],
        "provenance": summary["provenance"],
    }
