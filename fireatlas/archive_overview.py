"""Evidence-backed metadata for the historical MODIS/VIIRS hero."""

from __future__ import annotations

from collections import defaultdict


ARCHIVE_SOURCES = (
    ("MODIS_SP", "MODIS", "Terra + Aqua", "#E69F00"),
    ("VIIRS_SNPP_SP", "VIIRS", "Suomi NPP", "#56B4E9"),
)


def archive_overview(db):
    """Return only complete, non-synthetic archive windows.

    The result describes imported FIRMS export scope. It deliberately does not
    call that scope satellite coverage: pass opportunities, cloud masks and
    no-detection conditions are not represented by ``export_windows``.
    """
    rows = db.execute(
        """
        SELECT ew.source_id, ew.month, ew.west, ew.south, ew.east, ew.north,
               ew.batch_id, b.row_count
        FROM export_windows ew
        JOIN batches b ON b.id = ew.batch_id
        WHERE ew.source_id IN (?, ?) AND b.demo = 0
        ORDER BY ew.source_id, ew.month
        """,
        tuple(source[0] for source in ARCHIVE_SOURCES),
    ).fetchall()

    grouped = defaultdict(list)
    for row in rows:
        grouped[row["source_id"]].append(row)

    sources = []
    for source_id, sensor, platform, color in ARCHIVE_SOURCES:
        windows = grouped[source_id]
        months = [row["month"] for row in windows]
        batch_ids = [row["batch_id"] for row in windows]
        if batch_ids:
            placeholders = ",".join("?" for _ in batch_ids)
            observed = db.execute(
                f"SELECT COUNT(*) FROM observations WHERE batch_id IN ({placeholders})",
                batch_ids,
            ).fetchone()[0]
        else:
            observed = 0
        archive_rows = db.execute(
            """
            SELECT COALESCE(SUM(row_count), 0) FROM batches
            WHERE source_id = ? AND demo = 0
              AND source_uri LIKE 'urn:fireatlas:nasa-firms-archive:%'
            """,
            (source_id,),
        ).fetchone()[0]
        sources.append(
            {
                "source_id": source_id,
                "sensor": sensor,
                "platform": platform,
                "color": color,
                "months": months,
                "month_count": len(months),
                "first_month": months[0] if months else None,
                "last_month": months[-1] if months else None,
                "observation_rows": observed,
                "archive_rows": archive_rows,
                "bbox": [
                    min((row["west"] for row in windows), default=None),
                    min((row["south"] for row in windows), default=None),
                    max((row["east"] for row in windows), default=None),
                    max((row["north"] for row in windows), default=None),
                ],
            }
        )

    month_sets = [set(item["months"]) for item in sources]
    paired_months = sorted(month_sets[0] & month_sets[1])
    all_months = sorted(month_sets[0] | month_sets[1])
    available = bool(all_months)
    paired = len(paired_months) == len(all_months) and available
    bboxes = [item["bbox"] for item in sources if item["bbox"][0] is not None]
    scope_bbox = (
        [
            min(box[0] for box in bboxes),
            min(box[1] for box in bboxes),
            max(box[2] for box in bboxes),
            max(box[3] for box in bboxes),
        ]
        if bboxes
        else None
    )
    timeline = [
        {
            "month": month,
            "modis": month in month_sets[0],
            "viirs_snpp": month in month_sets[1],
            "paired": month in paired_months,
        }
        for month in all_months
    ]
    return {
        "schema": "fireatlas-archive-overview-v1",
        "data_class": "authentic-imported" if available else "unavailable",
        "status": "verified-pair-windows" if paired else ("partial-windows" if available else "unavailable"),
        "sources": sources,
        "timeline": timeline,
        "paired_months": paired_months,
        "paired_month_count": len(paired_months),
        "scope_bbox": scope_bbox,
        "scope_label": "Imported regional FIRMS archive",
        "limitation": (
            "The footprint and months describe imported FIRMS records. "
            "Satellite pass opportunities, cloud masking and no-detection conditions remain unknown."
        ),
    }
