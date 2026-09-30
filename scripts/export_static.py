"""Build a no-database static FireAtlas calendar from the local authentic archive."""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import io
import json
import re
import shutil
import sqlite3
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from fireatlas.calendar_v2 import calendar_v2, prepare_calendar_v2
from fireatlas.core import connect
from fireatlas.regions import REGIONS
from fireatlas.calendar_v2 import region_status
from fireatlas.validity import CASES as VALIDITY_CASES, report as validity_report, build_evidence as build_validity_evidence
from fireatlas.validation_check import check as analytical_validity_check
from fireatlas.mask_review import make_template
from fireatlas.masks import read_evidence

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "fireatlas" / "static"
SAMPLES = ROOT / "fireatlas" / "samples"
DOCS = ROOT / "docs"
FIRST_YEAR = 2006
SOURCES = ("MODIS_SP", "VIIRS_SNPP_SP")
TEXT_SUFFIXES = {".html", ".css", ".js", ".webmanifest"}


def _write_json(path: Path, value: object, root: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    path.write_bytes(body)
    return {"path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}


def _write_bundle_json(path: Path, value: object, root: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            compressed.write(body)
    encoded = path.read_bytes()
    return {"path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(encoded).hexdigest(), "bytes": len(encoded),
            "uncompressed_bytes": len(body)}


def compact_static_validity_report(report: dict) -> dict:
    """Return the browser-safe summary of a validity report.

    The full report is still written into the evidence ZIP.  A static browser
    only needs the selected-day cells, summary gates, ledgers and provenance;
    shipping every paired native observation and every row-level reconciliation
    result in every day snapshot made the public bundle needlessly enormous.
    Keeping the omission explicit prevents a compact snapshot from being
    mistaken for a replacement for the hash-bound evidence archive.
    """
    compact = copy.deepcopy(report)
    compact["static_export"] = {
        "schema": "fireatlas-validity-static-summary-v1",
        "detail": "summary-only browser snapshot",
        "full_evidence": "same-case ZIP contains the complete native and row-level evidence",
    }
    native = compact.get("native_masks")
    if not isinstance(native, dict):
        return compact

    paired = native.get("paired_observations")
    if isinstance(paired, dict) and "pairs" in paired:
        paired.pop("pairs", None)
        paired["pairs_omitted_for_static_export"] = True

    reconciliation = native.get("reconciliation")
    if isinstance(reconciliation, dict) and "results" in reconciliation:
        reconciliation.pop("results", None)
        reconciliation["results_omitted_for_static_export"] = True

    review = native.get("raw_mask_review")
    if isinstance(review, dict) and "samples" in review:
        review.pop("samples", None)
        review["samples_omitted_for_static_export"] = True

    native["static_export_note"] = (
        "Summary fields and selected-day native cells are bundled for the UI; "
        "paired observations, row-level reconciliation results and review queue "
        "details remain in the downloadable evidence ZIP."
    )
    return compact


def _relative_static_path(value: str, routes: set[str]) -> str:
    if not value.startswith("/") or value.startswith("//"):
        return value
    parsed = urlsplit(value)
    route = parsed.path
    if route not in routes:
        return value
    relative = "./" if route == "/" else f"./{route.lstrip('/')}"
    return urlunsplit(("", "", relative, parsed.query, parsed.fragment))


def _rebase_local_asset_urls(site: Path) -> None:
    routes = {"/"}
    routes.update("/" + path.relative_to(site).as_posix()
                  for path in site.rglob("*") if path.is_file())
    quoted = re.compile(r"(?P<q>['\"`])(?P<url>/[^'\"`\s]*)(?P=q)")
    unquoted_css = re.compile(r"url\(\s*(?P<url>/[^)'\"\s]+)\s*\)")
    for path in site.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        text = quoted.sub(lambda match: f"{match['q']}{_relative_static_path(match['url'], routes)}{match['q']}", text)
        text = unquoted_css.sub(lambda match: f"url({_relative_static_path(match['url'], routes)})", text)
        path.write_text(text, encoding="utf-8")


def _copy_site_assets(site: Path, static_source: Path = STATIC) -> None:
    site.mkdir(parents=True, exist_ok=True)
    shutil.copytree(static_source, site, dirs_exist_ok=True)
    earth_model = ROOT / "earth.html"
    if earth_model.is_file():
        shutil.copy2(earth_model, site / "earth.html")
    for relative in ("aggregates/norcal.json.gz", "aggregates/punjab-haryana.json.gz",
                     "calibration/norcal.json", "calibration/punjab-haryana.json"):
        source = SAMPLES / relative
        if source.is_file():
            target = site / "samples" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    for relative in ("DATA.md", "NASA_DATA_IMPORT.md", "AI_USE.md", "NATIVE_MASK_VALIDATION.md"):
        source = DOCS / relative
        if source.is_file():
            target = site / "docs" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    license_file = ROOT / "LICENSE"
    if license_file.is_file():
        shutil.copy2(license_file, site / "LICENSE")
    snapshot = datetime.now(timezone.utc).date().isoformat()
    metadata = (f'<meta name="fireatlas-static-data" content="./data/v2/">\n'
                f'<meta name="fireatlas-static-snapshot" content="{snapshot}">\n')
    # Static data links are relative to the page, so every top-level page that
    # can load bundled evidence needs the same export metadata.
    for page in site.glob("*.html"):
        text = page.read_text(encoding="utf-8")
        if 'name="fireatlas-static-data"' not in text:
            text = text.replace("</head>", metadata + "</head>", 1)
        page.write_text(text, encoding="utf-8")
    _rebase_local_asset_urls(site)


def _latest_year(status: dict, db: sqlite3.Connection) -> int:
    latest = db.execute("""
        SELECT max(substr(acquisition_utc,1,4)) FROM observations o
        JOIN batches b ON b.id=o.batch_id
        WHERE o.source_id IN (?,?) AND b.demo=0
    """, SOURCES).fetchone()[0]
    status_years = [int(item["last_complete_month"][:4])
                    for region in status["regions"]
                    for item in region["products"].values() if item["last_complete_month"]]
    available = [int(latest)] if latest else []
    available.extend(status_years)
    return max([2025, *available])


def _observations_for_region(db: sqlite3.Connection, site: Path, region_id: str,
                             first_year: int, last_year: int) -> list[dict]:
    west, south, east, north = REGIONS[region_id]["bbox"]
    rows = db.execute("""
        SELECT o.source_id,o.sensor,o.platform,o.acquisition_utc,o.raw_json
        FROM observations o JOIN batches b ON b.id=o.batch_id
        WHERE o.source_id IN (?,?) AND b.demo=0
          AND o.acquisition_utc>=? AND o.acquisition_utc<?
          AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=?
        ORDER BY o.acquisition_utc
    """, (*SOURCES, f"{first_year}-01-01", f"{last_year + 1}-01-01",
          west, east, south, north))

    output, current_year, current_day = [], None, None
    current_count, current_observations, days = 0, [], {}

    def flush_day():
        if current_day is None:
            return
        days[current_day] = {"date_utc": current_day,
                             "observations": current_observations,
                             "truncated": current_count > 200}

    def flush_year():
        if current_year is None:
            return
        document = {"schema": "fireatlas-static-observations-v1",
                    "region": region_id, "year": current_year, "days": days}
        output.append(_write_bundle_json(site / "data" / "v2" / "observations" /
                                         region_id / f"{current_year}.json.gz", document, site))

    for row in rows:
        stamp = row["acquisition_utc"][:10]
        year = int(stamp[:4])
        if current_year != year:
            flush_day()
            flush_year()
            days = {}
            current_year, current_day = year, None
            current_count, current_observations = 0, []
        if current_day != stamp:
            flush_day()
            current_day = stamp
            current_count, current_observations = 0, []
        current_count += 1
        if current_count <= 200:
            current_observations.append({"source_id": row["source_id"], "sensor": row["sensor"],
                                         "platform": row["platform"],
                                         "acquisition_utc": row["acquisition_utc"],
                                         "raw": json.loads(row["raw_json"])})
    flush_day()
    flush_year()
    written_years = {int(Path(item["path"]).stem.split(".")[0]) for item in output}
    for year in range(first_year, last_year + 1):
        if year not in written_years:
            document = {"schema": "fireatlas-static-observations-v1",
                        "region": region_id, "year": year, "days": {}}
            output.append(_write_bundle_json(site / "data" / "v2" / "observations" /
                                             region_id / f"{year}.json.gz", document, site))
    return output


def _export_static_into(database: Path, site: Path, *, static_source: Path,
                        first_year: int, last_year: int | None) -> dict:
    _copy_site_assets(site, Path(static_source))
    site_data = site / "data" / "v2"
    file_inventory = []
    with connect(database) as db:
        status = region_status(db)
        end_year = last_year or _latest_year(status, db)
        if not FIRST_YEAR <= first_year <= end_year <= 2026:
            raise ValueError("static export years must be within 2006–2026")
        file_inventory.append(_write_json(site_data / "regions.json", status, site))
        source_hashes = set()
        for region_id in REGIONS:
            prepared = prepare_calendar_v2(db, region=region_id, fallback_year=end_year)
            for year in range(first_year, end_year + 1):
                result = calendar_v2(db, region=region_id, year=year, prepared=prepared)
                for item in result["meta"].get("inputs", []):
                    digest = item.get("file_sha256") or item.get("parent_sha256")
                    if digest:
                        source_hashes.add(digest)
                file_inventory.append(_write_json(site_data / "calendar" / region_id / f"{year}.json", result, site))
            latest_result = calendar_v2(db, region=region_id, year=end_year,
                                        include_history=True, prepared=prepared)
            file_inventory.append(_write_json(site_data / "history" / f"{region_id}.json",
                                              latest_result["history"], site))
            file_inventory.extend(_observations_for_region(db, site, region_id, first_year, end_year))

        # Keep the dated evidence story usable from a static checkout too.  Each
        # case/date report is generated from the same database snapshot as the
        # calendar, so the method page can still scrub a day and open its
        # provenance when no Python API is running.  Native-mask summaries are
        # compact; raw inputs remain outside the export and are referenced by
        # their hashes in the report and downloadable evidence ZIP.
        validity_root = site / "data" / "v2" / "validity"
        has_authentic_rows = db.execute(
            "SELECT 1 FROM observations o JOIN batches b ON b.id=o.batch_id "
            "WHERE b.demo=0 AND o.source_id IN (?,?) LIMIT 1", SOURCES).fetchone()
        if has_authentic_rows:
            for case_id, case in VALIDITY_CASES.items():
                default = compact_static_validity_report(validity_report(db, case_id=case_id))
                file_inventory.append(_write_json(validity_root / f"{case_id}.json", default, site))
                current = date.fromisoformat(case["start"])
                last = date.fromisoformat(case["end"])
                while current <= last:
                    dated = compact_static_validity_report(
                        validity_report(db, case_id=case_id, selected_date=current.isoformat()))
                    file_inventory.append(_write_json(validity_root / case_id / f"{current.isoformat()}.json", dated, site))
                    current += timedelta(days=1)
                evidence = build_validity_evidence(db, case_id)
                zip_path = validity_root / f"{case_id}.zip"
                zip_path.parent.mkdir(parents=True, exist_ok=True)
                zip_path.write_bytes(evidence)
                file_inventory.append({"path": zip_path.relative_to(site).as_posix(),
                                       "sha256": hashlib.sha256(evidence).hexdigest(),
                                       "bytes": len(evidence)})
                checked = analytical_validity_check(io.BytesIO(evidence))
                checked["checked_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                check_path = validity_root / f"{case_id}-check.json"
                file_inventory.append(_write_json(check_path, checked, site))
                # Keep the blank, hash-bound review form directly beside the
                # evidence bundle.  A reviewer can download it without
                # unpacking the ZIP; it is deliberately not a sign-off.
                template = make_template(case_id, read_evidence(case_id))
                file_inventory.append(_write_json(
                    validity_root / f"{case_id}-review-template.json", template, site))

        mcd64_report = SAMPLES / "mcd64_corroboration.json"
        if has_authentic_rows and mcd64_report.is_file():
            corroboration = json.loads(mcd64_report.read_text(encoding="utf-8"))
            if corroboration.get("schema") == "fireatlas-mcd64-corroboration-v1":
                file_inventory.append(_write_json(validity_root / "mcd64-corroboration.json",
                                                  corroboration, site))

    manifest = {
        "schema": "fireatlas-static-site-v1",
        "snapshot_utc_date": datetime.now(timezone.utc).date().isoformat(),
        "calendar_start_year": first_year,
        "calendar_end_year": end_year,
        "regions": [{"id": key, "name": value["name"], "bbox": list(value["bbox"])}
                    for key, value in REGIONS.items()],
        "input_file_sha256": sorted(source_hashes),
        "limitations": [
            "This is a dated static export from the local imported FIRMS archive.",
            "Older reconstructed-row periods remain partial; missing dates are unknown.",
            "Detection export completeness does not establish pass, cloud, or fire-free coverage.",
            "A static calendar does not provide live FIRMS updates or the local research API.",
            "Static validity reports are summary-only dated snapshots; the downloadable ZIP references the complete raw inputs and row-level evidence by hash.",
        ],
        "files": sorted(file_inventory, key=lambda item: item["path"]),
    }
    manifest_record = _write_json(site_data / "manifest.json", manifest, site)
    return {"output": str(site), "regions": len(REGIONS), "first_year": first_year,
            "last_year": end_year, "calendar_count": 2 * (end_year - first_year + 1),
            "data_files": len(file_inventory) + 1,
            "manifest_sha256": manifest_record["sha256"],
            "input_hash_count": len(source_hashes), "manifest": manifest_record}


def export_static(database: str | Path, output: str | Path, *,
                  static_source: str | Path = STATIC, first_year: int = FIRST_YEAR,
                  last_year: int | None = None) -> dict:
    """Export to a fresh directory; existing output is never deleted or overwritten."""
    database, destination = Path(database), Path(output).resolve()
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing export directory: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{destination.name}-", dir=destination.parent) as temporary:
        workdir = Path(temporary) / "site"
        result = _export_static_into(database, workdir, static_source=Path(static_source),
                                     first_year=first_year, last_year=last_year)
        workdir.rename(destination)
        result["output"] = str(destination)
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "fireatlas.sqlite3")
    parser.add_argument("--output", type=Path, default=ROOT / "site")
    parser.add_argument("--first-year", type=int, default=FIRST_YEAR)
    parser.add_argument("--last-year", type=int)
    args = parser.parse_args()
    print(json.dumps(export_static(args.db, args.output, first_year=args.first_year,
                                   last_year=args.last_year), indent=2))


if __name__ == "__main__":
    main()
