"""Portable atlas evidence bundles with independently verifiable cell-day totals."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import median

from .core import GRID_VERSION, SERIES, SOURCES, calendar, calendar_row_included
from .harmonization import month_audit

SCHEMA = "fireatlas-study-v2"
LEGACY_SCHEMA = "fireatlas-study-v1"
MAX_ROWS = 50_000


def selection(year, month, series, bbox, day=None, layer="none"):
    if not 1 <= month <= 12 or layer not in ("none", "ndvi", "landcover", "fwi"):
        raise ValueError("invalid study month or context layer")
    if day:
        from datetime import date
        parsed = date.fromisoformat(day)
        if parsed.isoformat() != day or parsed.year != year or parsed.month != month:
            raise ValueError("selected day must belong to the selected year and month")
    return dict(year=year, month=month, series=series, bbox=list(bbox), day=day, layer=layer)


def build_bundle(db, *, year, month, series, bbox, day=None, layer="none"):
    config = selection(year, month, series, bbox, day, layer)
    summary = calendar(db, bbox=bbox, year=year, series=series)
    # Include every qualifying baseline month, even if fewer than three exist.
    months = {item["month"] for item in summary["monthly"]}
    months.update(f"{prior}-{index:02d}" for index, item in enumerate(summary["monthly"], 1)
                  for prior in item["baseline_years"])
    sources = SERIES[series]
    source_sql = ",".join("?" for _ in sources)
    month_sql = ",".join("?" for _ in months)
    scope = (*sources, *sorted(months))
    rows = db.execute(f"""
        SELECT o.*, b.file_sha256,b.demo FROM observations o JOIN batches b ON b.id=o.batch_id
        WHERE o.source_id IN ({source_sql}) AND substr(o.acquisition_utc,1,7) IN ({month_sql})
          AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=?
        ORDER BY o.acquisition_utc,o.detection_id LIMIT ?
    """, (*scope, bbox[0], bbox[2], bbox[1], bbox[3], MAX_ROWS + 1)).fetchall()
    if len(rows) > MAX_ROWS:
        raise ValueError("Study exceeds 50,000 observations including baseline inputs. Narrow the AOI.")
    observations = []
    for row in rows:
        item = dict(row)
        item["raw"] = json.loads(item.pop("raw_json"))
        observations.append(item)
    windows = [dict(row) for row in db.execute(f"""
        SELECT * FROM export_windows WHERE source_id IN ({source_sql})
          AND month IN ({month_sql}) AND west<=? AND south<=? AND east>=? AND north>=?
        ORDER BY month,source_id,batch_id
    """, (*scope, *bbox))]
    batch_ids = {row["batch_id"] for row in observations + windows}
    batches = [dict(row) for row in db.execute("SELECT * FROM batches ORDER BY id") if row["id"] in batch_ids]
    # The study's classification includes the baseline inputs, not only the display year.
    classes = {bool(row["demo"]) for row in batches}
    data_class = "mixed" if len(classes) > 1 else "synthetic" if True in classes else "authentic" if classes else "empty"
    payloads = {
        "selection.json": config,
        "calendar.json": summary,
        "harmonization.json": month_audit(db, year=year, month=month, series=series, bbox=bbox),
        "observations.json": observations,
        "export-windows.json": windows,
        "batches.json": batches,
    }
    from .presentation import PREFIX, YEARS, provenance, context_fixture
    if data_class == "synthetic" and any(b["source_uri"].startswith(PREFIX) for b in batches):
        payloads["presentation-provenance.json"] = provenance()
        if layer != "none" and year in YEARS:
            payloads["synthetic-context.geojson"] = context_fixture(year=year, month=month, bbox=bbox, layer=layer)
    files = {name: json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode() for name, value in payloads.items()}
    files["README.txt"] = (
        "FireAtlas study bundle v2\n\n"
        "selection.json restores the AOI, year, month, sensor series, day and context layer.\n"
        "calendar.json contains the full selected-year UTC calendar. harmonization.json records\n"
        "the selected month raw-pixel, common-grid and overlap audit. observations.json includes\n"
        "the selected year and all qualifying prior same-month baseline inputs, with untouched\n"
        "source rows, normalized fields and assigned grid cells. export-windows.json records\n"
        "complete source exports covering this AOI. batches.json retains file hashes and provenance.\n\n"
        "Count distinct (grid_x, grid_y) per UTC date across type-0-or-missing FIRMS records. Sum daily\n"
        "counts by month; use the median of at least three prior complete same-month years.\n"
        "An incomplete month has a null official count. Verify with the project command:\n"
        "  uv run python -m fireatlas.study path/to/study.zip\n\n"
        "SHA-256 checks detect changes; they are not signatures or proof of source authenticity.\n"
        "Source file hashes identify original imports; those entire files are not embedded.\n"
        "Synthetic presentation studies include seed provenance and, when selected, synthetic context GeoJSON.\n"
        "Map tiles, satellite context images, coverage masks and research outputs are not included.\n"
        "Cell-days are a sampling proxy, not fire counts or burned area. Observation coverage is\n"
        "unknown. Synthetic or mixed data are not regional scientific validation. Shared URLs\n"
        "restore a view against the recipient's current server data; this bundle freezes its inputs.\n"
    ).encode()
    manifest = {
        "schema": SCHEMA, "created_utc": datetime.now(timezone.utc).isoformat(),
        "data_class": data_class, "grid": summary["grid"],
        "observation_count": len(observations), "input_months": sorted(months),
        "files": {name: hashlib.sha256(body).hexdigest() for name, body in files.items()},
    }
    files["manifest.json"] = json.dumps(manifest, indent=2).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in files.items():
            archive.writestr(name, body)
    return buffer.getvalue()


def _verify_harmonization(audit, selection, summary, rows, windows):
    """Recompute the month audit from the frozen rows, independent of its hash."""
    year, month = selection["year"], selection["month"]
    sources = SERIES[selection["series"]]
    bbox = selection["bbox"]
    stamp = f"{year}-{month:02d}"
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    selected = summary["monthly"][month - 1]
    raw = Counter()
    raw_by_day = Counter()
    marks = {source: defaultdict(set) for source in sources}
    versions = {source: set() for source in sources}
    for row in rows:
        day = row["acquisition_utc"][:10]
        if not day.startswith(stamp):
            continue
        source = row["source_id"]
        if source not in sources:
            raise ValueError("harmonization audit contains an unexpected source")
        versions[source].add(row["product_version"])
        if not calendar_row_included(row["raw"]):
            continue
        raw[source] += 1
        raw_by_day[(source, day)] += 1
        marks[source][day].add((row["grid_x"], row["grid_y"]))

    by_source = [{"source_id": source, "sensor": SOURCES[source][0],
                  "processing_level": SOURCES[source][1], "raw_pixels": raw[source],
                  "detected_cell_days": sum(len(cells) for cells in marks[source].values()),
                  "product_versions": sorted(versions[source]),
                  "full_month_export": any(w["source_id"] == source and w["month"] == stamp
                       and w["west"] <= bbox[0] and w["south"] <= bbox[1]
                       and w["east"] >= bbox[2] and w["north"] >= bbox[3] for w in windows)}
                 for source in sources]
    baseline_versions = {}
    for prior in selected["baseline_years"]:
        prior_versions = {source: set() for source in sources}
        prior_stamp = f"{prior}-{month:02d}"
        for row in rows:
            if row["acquisition_utc"].startswith(prior_stamp) and row["source_id"] in sources:
                prior_versions[row["source_id"]].add(row["product_version"])
        baseline_versions[str(prior)] = {source: sorted(prior_versions[source]) for source in sources}
    if not baseline_versions:
        baseline_version_status = "no-qualifying-baseline-years"
    elif any(not values[source] for values in baseline_versions.values() for source in sources):
        baseline_version_status = "unknown-where-source-has-no-detections"
    elif all(values[source] == sorted(versions[source])
             for values in baseline_versions.values() for source in sources):
        baseline_version_status = "same-observed-product-versions"
    else:
        baseline_version_status = "mixed-product-versions-across-years"
    complete = all(item["full_month_export"] for item in by_source)
    expected_days = []
    day = start
    while day < end:
        key = day.isoformat()
        cells = {source: marks[source][key] for source in sources}
        union = set().union(*cells.values())
        overlap = len(set.intersection(*cells.values())) if len(sources) == 2 else None
        expected_days.append({"date_utc": key,
                              "raw_pixels_by_source": {source: raw_by_day[(source, key)] for source in sources},
                              "cell_days_by_source": {source: len(cells[source]) for source in sources},
                              "joint_cell_days": len(union) if complete else None,
                              "partial_joint_cell_days": None if complete else len(union),
                              "co_detected_cell_days": overlap,
                              "export_window_complete": complete,
                              "satellite_observation_coverage": "unknown"})
        day += timedelta(days=1)
    standard_pair = sources == SERIES["joint"]
    if not standard_pair:
        status = "outside-standard-modis-viirs-pair"
    elif not complete:
        status = "missing-complete-source-export"
    elif any(len(item["product_versions"]) > 1 for item in by_source):
        status = "mixed-product-versions"
    elif not all(item["raw_pixels"] for item in by_source):
        status = "complete-export-with-zero-detections-in-one-source"
    else:
        status = "descriptive-pair-available"
    expected = {
        "status": status,
        "data_class": "synthetic" if summary["demo_data"] else "authentic-imported",
        "calendar_timezone": "UTC", "grid": GRID_VERSION,
        "sources": by_source, "raw_pixels_total": sum(raw.values()),
        "detected_cell_days": sum(item["joint_cell_days"] for item in expected_days) if complete else None,
        "partial_detected_cell_days": None if complete else sum(item["partial_joint_cell_days"] for item in expected_days),
        "co_detected_cell_days": sum(item["co_detected_cell_days"] for item in expected_days) if len(sources) == 2 else None,
        "days": expected_days, "baseline_median": selected["baseline_median"],
        "baseline_years": selected["baseline_years"],
        "baseline_product_versions": baseline_versions,
        "baseline_version_status": baseline_version_status,
        "provenance": summary["provenance"],
    }
    if any(audit.get(key) != value for key, value in expected.items()):
        raise ValueError("harmonization audit does not reproduce from bundled observations")


def verify_bundle(path):
    """Verify hashes and recompute the calendar from bundled normalized inputs."""
    with zipfile.ZipFile(path) as archive:
        if sum(info.file_size for info in archive.infolist()) > 150_000_000:
            raise ValueError("bundle exceeds verification size limit")
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError("duplicate bundle entries")
        manifest = json.loads(archive.read("manifest.json"))
        schema = manifest.get("schema")
        required = {"selection.json", "calendar.json", "observations.json", "export-windows.json", "batches.json", "README.txt"}
        if schema == SCHEMA:
            required.add("harmonization.json")
        optional = {"presentation-provenance.json", "synthetic-context.geojson"}
        included = set(manifest.get("files", {}))
        if schema not in (SCHEMA, LEGACY_SCHEMA) or not required <= included or included - required - optional:
            raise ValueError("unsupported or incomplete study bundle")
        if included & optional and manifest.get("data_class") != "synthetic":
            raise ValueError("synthetic presentation inputs require a synthetic study")
        for name, checksum in manifest["files"].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != checksum:
                raise ValueError(f"checksum mismatch: {name}")
        summary = json.loads(archive.read("calendar.json"))
        audit = json.loads(archive.read("harmonization.json")) if schema == SCHEMA else None
        selection = json.loads(archive.read("selection.json"))
        if (audit is not None and (audit.get("schema") != "fireatlas-harmonization-audit-v1"
                or audit.get("year") != selection.get("year")
                or audit.get("month") != selection.get("month")
                or audit.get("series") != selection.get("series")
                or audit.get("bbox") != selection.get("bbox"))):
            raise ValueError("harmonization audit does not match selection")
        rows = json.loads(archive.read("observations.json"))
        windows = json.loads(archive.read("export-windows.json"))
    cells = defaultdict(set)
    for row in rows:
        if not calendar_row_included(row.get("raw")):
            continue
        cells[row["acquisition_utc"][:10]].add((row["grid_x"], row["grid_y"]))
    totals = defaultdict(int)
    for stamp, marks in cells.items():
        totals[stamp[:7]] += len(marks)
    def complete_month(stamp):
        return all(any(w["month"] == stamp and w["source_id"] == source for w in windows) for source in summary["sources"])

    for item in summary["monthly"]:
        stamp = item["month"]
        complete = complete_month(stamp)
        expected = totals[stamp] if complete else None
        years = [year for year in range(2000, summary["year"]) if complete_month(f"{year}-{stamp[5:]}")]
        baseline = median(totals[f"{year}-{stamp[5:]}"] for year in years) if len(years) >= 3 else None
        anomaly = expected - baseline if expected is not None and baseline is not None else None
        partial = None if complete else totals[stamp]
        if (item["detected_cell_days"] != expected or item["baseline_median"] != baseline
                or item["baseline_years"] != years or item["anomaly_cell_days"] != anomaly
                or item["export_window_complete"] != complete or item["partial_import_detected_cell_days"] != partial):
            raise ValueError(f"calendar does not reproduce: {stamp}")
    for item in summary["daily"]:
        complete = complete_month(item["date_utc"][:7])
        count = len(cells[item["date_utc"]])
        expected = count if complete else None
        if (item["detected_cell_days"] != expected or item["export_window_complete"] != complete
                or item["partial_import_detected_cell_days"] != (None if complete else count)):
            raise ValueError(f"daily count does not reproduce: {item['date_utc']}")
    if audit is not None:
        _verify_harmonization(audit, selection, summary, rows, windows)
    return {"schema": schema, "data_class": manifest["data_class"], "observations": len(rows), "verified": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle")
    args = parser.parse_args()
    try:
        print(json.dumps(verify_bundle(args.bundle), indent=2))
    except (ValueError, KeyError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Verification failed: {exc}\n")
