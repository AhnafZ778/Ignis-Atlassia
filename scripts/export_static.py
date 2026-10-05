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
import zipfile
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
from fireatlas.globe import static_bundle as static_globe_bundle
from fireatlas.provenance import public_source_reference, sanitize_public_payload
from fireatlas.replay import CASES as REPLAY_CASES, build_case as build_replay_case, build_catalog as build_replay_catalog

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "fireatlas" / "static"
SAMPLES = ROOT / "fireatlas" / "samples"
DOCS = ROOT / "docs"
FIRST_YEAR = 2006
SOURCES = ("MODIS_SP", "VIIRS_SNPP_SP")
TEXT_SUFFIXES = {".html", ".css", ".js", ".webmanifest"}


def _write_json(path: Path, value: object, root: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(sanitize_public_payload(value), sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")
    path.write_bytes(body)
    return {"path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}


def _write_bundle_json(path: Path, value: object, root: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(sanitize_public_payload(value), sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")
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
        if path.relative_to(site).parts[0] in ('studio-assets', 'studio-mcp'):
            # SDK builds already use relative imports. Preserve their exact
            # allowlisted bytes and content hashes when refreshing the site.
            continue
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        def rebase_quoted(match):
            # A bare slash in JavaScript/JSON is commonly a separator or JSON
            # pointer escape, not a homepage URL. Rewriting it corrupts exact
            # evidence lookup. Mark homepage links explicitly as ./ in scripts.
            if match['url']=='/':
                # HTML also contains inline scripts. Only an actual link/form
                # attribute establishes that a bare slash is a homepage route.
                attribute=path.suffix=='.html' and re.search(r'(?:href|action|src)\s*=\s*$',text[max(0,match.start()-40):match.start()],re.I)
                if not attribute and path.suffix!='.css':return match[0]
            return f"{match['q']}{_relative_static_path(match['url'], routes)}{match['q']}"
        text = quoted.sub(rebase_quoted, text)
        text = unquoted_css.sub(lambda match: f"url({_relative_static_path(match['url'], routes)})", text)
        path.write_text(text, encoding="utf-8")


def _copy_site_assets(site: Path, static_source: Path = STATIC, *, snapshot_date: str | None = None) -> None:
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
    for relative in ("DATA.md", "NASA_DATA_IMPORT.md", "AI_USE.md", "NATIVE_MASK_VALIDATION.md", "SCIENTIFIC_ASSISTANT_PLAN.md", "SCIENTIFIC_ASSISTANT_SETUP.md"):
        source = DOCS / relative
        if source.is_file():
            target = site / "docs" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    license_file = ROOT / "LICENSE"
    if license_file.is_file():
        shutil.copy2(license_file, site / "LICENSE")
    snapshot = snapshot_date or datetime.now(timezone.utc).date().isoformat()
    metadata = (f'<meta name="fireatlas-static-data" content="./data/v2/">\n'
                f'<meta name="fireatlas-static-snapshot" content="{snapshot}">\n')
    # Static data links are relative to the page, so every top-level page that
    # can load bundled evidence needs the same export metadata.
    for page in site.glob("*.html"):
        text = page.read_text(encoding="utf-8")
        if 'name="fireatlas-static-data"' not in text:
            text = text.replace("</head>", metadata + "</head>", 1)
        page.write_text(text, encoding="utf-8")


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


def _complete_observation_archive(db: sqlite3.Connection, site: Path, region_id: str,
                                 input_hashes: set[str]) -> dict:
    """Write every imported, non-demo observation as deterministic JSONL.GZ parts.

    GitHub rejects individual objects above 100 MiB.  The Punjab–Haryana
    archive is larger than that limit, so the public static release keeps the
    complete row-level evidence but splits it into bounded, independently
    checksummed parts.  A row-count boundary (rather than a byte boundary)
    keeps exports deterministic across machines and Python versions.
    """
    west, south, east, north = REGIONS[region_id]["bbox"]
    rows = db.execute("""
        SELECT o.detection_id,o.source_id,o.platform,o.sensor,o.product_version,
               o.processing_level,o.acquisition_utc,o.retrieval_time_utc,o.lon,o.lat,
               o.scan_m,o.track_m,o.grid_x,o.grid_y,o.frp_raw,o.confidence_raw,
               o.daynight,o.thermal_anomaly_flag,o.source_uri,o.raw_json,
               b.file_sha256,b.source_uri AS batch_source_uri,b.retrieved_utc
        FROM observations o JOIN batches b ON b.id=o.batch_id
        WHERE b.demo=0 AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=?
        ORDER BY o.acquisition_utc,o.source_id,o.grid_y,o.grid_x,o.detection_id
    """, (west, east, south, north))
    target_root = site / "data" / "v2" / "observations-full"
    target_root.mkdir(parents=True, exist_ok=True)
    for stale in target_root.glob(f"{region_id}.jsonl.gz"):
        stale.unlink()
    for stale in target_root.glob(f"{region_id}.part-*.jsonl.gz"):
        stale.unlink()

    rows_per_part = 400_000
    parts: list[dict] = []
    row_count = 0
    part_row_count = 0
    part_number = 0
    compressed = None
    raw_stream = None

    def open_part() -> None:
        nonlocal compressed, raw_stream, part_number, part_row_count
        part_number += 1
        part_row_count = 0
        target = target_root / f"{region_id}.part-{part_number:02d}.jsonl.gz"
        raw_stream = target.open("wb")
        compressed = gzip.GzipFile(fileobj=raw_stream, mode="wb", mtime=0, compresslevel=6)

    def close_part() -> None:
        nonlocal compressed, raw_stream
        if compressed is None or raw_stream is None:
            return
        compressed.close()
        raw_stream.close()
        target = target_root / f"{region_id}.part-{part_number:02d}.jsonl.gz"
        body = target.read_bytes()
        parts.append({"path": target.relative_to(site).as_posix(),
                      "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
                      "row_count": part_row_count})
        compressed = None
        raw_stream = None

    for row in rows:
        if compressed is None or part_row_count >= rows_per_part:
            close_part()
            open_part()
        record = {
            "detection_id": row["detection_id"], "source_id": row["source_id"],
            "platform": row["platform"], "sensor": row["sensor"],
            "product_version": row["product_version"],
            "processing_level": row["processing_level"],
            "acquisition_utc": row["acquisition_utc"],
            "retrieval_time_utc": row["retrieval_time_utc"],
            "lon": row["lon"], "lat": row["lat"],
            "scan_m": row["scan_m"], "track_m": row["track_m"],
            "grid_x": row["grid_x"], "grid_y": row["grid_y"],
            "frp_raw": row["frp_raw"], "confidence_raw": row["confidence_raw"],
            "daynight": row["daynight"],
            "thermal_anomaly_flag": row["thermal_anomaly_flag"],
            "source_file_sha256": row["file_sha256"],
            "source_uri": public_source_reference(row["source_uri"]),
            "batch_source_uri": public_source_reference(row["batch_source_uri"]),
            "retrieved_utc": row["retrieved_utc"],
        }
        try:
            record["raw"] = json.loads(row["raw_json"])
        except (TypeError, json.JSONDecodeError):
            record["raw"] = row["raw_json"]
        compressed.write(json.dumps(record, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n")
        if row["file_sha256"]:
            input_hashes.add(row["file_sha256"])
        row_count += 1
        part_row_count += 1
    close_part()
    if not parts:
        open_part()
        close_part()
    return {"parts": parts, "row_count": row_count,
            "format": "gzip-compressed JSON Lines; deterministic row-count parts",
            "scope": "all imported non-demo observation rows inside this region bbox; all source IDs"}


def _bundle_mcd64_sources(site: Path, file_inventory: list[dict]) -> None:
    source_root = ROOT / "NASA_data" / "mcd64a1"
    source_files = sorted(source_root.rglob("*.tif")) if source_root.is_dir() else []
    if source_files:
        target = site / "data" / "v2" / "validity" / "mcd64-inputs.zip"
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
            for source in source_files:
                archive.write(source, Path("mcd64a1") / source.relative_to(source_root))
        body = target.read_bytes()
        file_inventory.append({"path": target.relative_to(site).as_posix(),
                               "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
                               "input_files": len(source_files),
                               "description": "All locally supplied MCD64A1 Burn Date and QA GeoTIFFs."})
    checklist = ROOT / "NASA_data" / "fire_masks" / "download_checklist.csv"
    if checklist.is_file():
        target = site / "data" / "v2" / "validity" / "fire-mask-download-checklist.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        # Keep generated text artifacts diff-friendly while preserving every
        # checklist field and URL from the supplied source file. The source has
        # a whitespace-only final row, so discard only blank records.
        lines = checklist.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n").splitlines()
        lines = [line for line in lines if line.strip()]
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        body = target.read_bytes()
        file_inventory.append({"path": target.relative_to(site).as_posix(),
                               "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
                               "description": "NASA native fire-mask/geolocation source checklist with source URLs."})
    local_inventory = ROOT / "NASA_data" / "fire_masks" / "local_asset_inventory.csv"
    if local_inventory.is_file():
        target = site / "data" / "v2" / "validity" / "fire-mask-local-inventory.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = local_inventory.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n").splitlines()
        lines = [line for line in lines if line.strip()]
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        body = target.read_bytes()
        file_inventory.append({"path": target.relative_to(site).as_posix(),
                               "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
                               "description": "Complete SHA-256 inventory of local fire-mask/geolocation files; source metadata is included where the NASA checklist has a matching filename."})


def _export_static_into(database: Path, site: Path, *, static_source: Path,
                        first_year: int, last_year: int | None,
                        reuse_validity_from: Path | None = None) -> dict:
    _copy_site_assets(site, Path(static_source))
    site_data = site / "data" / "v2"
    file_inventory = []
    complete_observation_exports = []
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
            archive = _complete_observation_archive(db, site, region_id, source_hashes)
            file_inventory.extend(archive["parts"])
            complete_observation_exports.append({
                "region": region_id,
                "parts": archive["parts"],
                "row_count": archive["row_count"],
                "format": archive["format"],
                "scope": archive["scope"],
            })

        # The landing globe's recent view remains interactive in a static
        # checkout. Keep per-source/day/cell aggregates and bounded detail
        # samples, with input hashes, rather than copying the whole database.
        globe = static_globe_bundle(db)
        source_hashes.update(globe["input_file_sha256"])
        file_inventory.append(_write_bundle_json(
            site_data / "globe" / "recent.json.gz", globe, site))

        # The standalone historical replay uses the full local case windows,
        # packaged as compressed browser bundles. This avoids shipping the
        # database or making a static visitor infer missing days are zero.
        replay_cases = {}
        replay_root = site / "data" / "replay"
        for replay_case_id in REPLAY_CASES:
            replay_case = build_replay_case(db, replay_case_id)
            replay_cases[replay_case_id] = replay_case
            for source in replay_case["summary"]["sources"].values():
                source_hashes.update(source["source_file_hashes"])
            file_inventory.append(_write_bundle_json(
                replay_root / "cases" / f"{replay_case_id}.json.gz", replay_case, site))
        file_inventory.append(_write_json(
            replay_root / "catalog.json", build_replay_catalog(db, replay_cases), site))

        # Keep the dated evidence story usable from a static checkout too.  Each
        # case/date report is generated from the same database snapshot as the
        # calendar, so the method page can still scrub a day and open its
        # provenance when no Python API is running.  Native-mask summaries are
        # compact; raw inputs remain outside the export and are referenced by
        # their hashes in the report and downloadable evidence ZIP.
        validity_root = site / "data" / "v2" / "validity"
        reusable_validity = (reuse_validity_from / "data" / "v2" / "validity"
                             if reuse_validity_from else None)
        if reusable_validity and reusable_validity.is_dir():
            shutil.copytree(reusable_validity, validity_root, dirs_exist_ok=True)
        has_authentic_rows = db.execute(
            "SELECT 1 FROM observations o JOIN batches b ON b.id=o.batch_id "
            "WHERE b.demo=0 AND o.source_id IN (?,?) LIMIT 1", SOURCES).fetchone()
        if has_authentic_rows and not (reusable_validity and reusable_validity.is_dir()):
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
            if corroboration.get("schema") in {
                    "fireatlas-mcd64-corroboration-v1", "fireatlas-mcd64-corroboration-v2"}:
                file_inventory.append(_write_json(validity_root / "mcd64-corroboration.json",
                                                  corroboration, site))

    _bundle_mcd64_sources(site, file_inventory)

    # Include reused validity files in the new manifest and avoid duplicating
    # entries already produced during a full evidence rebuild.
    validity_root = site / "data" / "v2" / "validity"
    indexed_paths = {item["path"] for item in file_inventory}
    if validity_root.is_dir():
        for path in sorted(validity_root.rglob("*")):
            if path.is_file():
                relative = path.relative_to(site).as_posix()
                if relative not in indexed_paths:
                    body = path.read_bytes()
                    file_inventory.append({"path": relative,
                                           "sha256": hashlib.sha256(body).hexdigest(),
                                           "bytes": len(body),
                                           "description": "Reused dated validity evidence from the existing local site export."})

    # Rebase only after generated data files exist. Pages may link to evidence
    # written during this export, and those routes must work under a project
    # prefix such as GitHub Pages' /<repository>/ path.
    _rebase_local_asset_urls(site)

    manifest = {
        "schema": "fireatlas-static-site-v1",
        "snapshot_utc_date": datetime.now(timezone.utc).date().isoformat(),
        "calendar_start_year": first_year,
        "calendar_end_year": end_year,
        "regions": [{"id": key, "name": value["name"], "bbox": list(value["bbox"])}
                    for key, value in REGIONS.items()],
        "input_file_sha256": sorted(source_hashes),
        "complete_observation_exports": complete_observation_exports,
        "limitations": [
            "This is a dated static export from the local imported FIRMS archive.",
            "Older reconstructed-row periods remain partial; missing dates are unknown.",
            "Detection export completeness does not establish pass, cloud, or fire-free coverage.",
            "The static globe is a checksummed eight-day imported snapshot, not a live FIRMS feed.",
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
                  last_year: int | None = None,
                  reuse_validity_from: str | Path | None = None) -> dict:
    """Export to a fresh directory; existing output is never deleted or overwritten."""
    database, destination = Path(database), Path(output).resolve()
    if Path(static_source).resolve() == STATIC.resolve() and (ROOT / 'docs/implementation/landing-baseline.json').exists():
        from scripts.check_landing_preservation import check
        check()
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing export directory: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{destination.name}-", dir=destination.parent) as temporary:
        workdir = Path(temporary) / "site"
        result = _export_static_into(database, workdir, static_source=Path(static_source),
                                     first_year=first_year, last_year=last_year,
                                     reuse_validity_from=(Path(reuse_validity_from)
                                                          if reuse_validity_from else None))
        workdir.rename(destination)
        result["output"] = str(destination)
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "fireatlas.sqlite3")
    parser.add_argument("--output", type=Path, default=ROOT / "site")
    parser.add_argument("--first-year", type=int, default=FIRST_YEAR)
    parser.add_argument("--last-year", type=int)
    parser.add_argument("--reuse-validity-from", type=Path,
                        help="Reuse dated evidence files from an existing local site export.")
    args = parser.parse_args()
    print(json.dumps(export_static(args.db, args.output, first_year=args.first_year,
                                   last_year=args.last_year,
                                   reuse_validity_from=args.reuse_validity_from), indent=2))


if __name__ == "__main__":
    main()
