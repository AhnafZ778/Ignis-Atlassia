"""Prepare and import the user-supplied FIRMS Archive Download CSVs.

The downloaded files are world-wide, roughly year-long products. A compact
regional bundle retains the original row fields and parent-file hashes. A
complete export window is asserted only for full months through 2025; 2026
rows are retained as partial evidence because the supplied S-NPP archive has
an entire missing May and its recent availability needs separate review.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import tempfile
import zipfile
from calendar import monthrange
from contextlib import ExitStack
from datetime import date
from pathlib import Path

from .core import REQUIRED_COLUMNS, SERIES, connect, ingest, validate_bbox
from .regions import PRODUCTS, REGIONS, contains_bbox, intersects_bbox

SCHEMA = "fireatlas-firms-archive-slice-v1"
SAMPLE = Path(__file__).with_name("samples") / "nasa_firms_northern_california_2022_2026.zip"
BBOX = (-122.2, 38.8, -120.0, 41.0)
SOURCE_CODES = {"M-C61": "MODIS_SP", "SV-C2": "VIIRS_SNPP_SP"}
EXPECTED_YEARS = (2022, 2023, 2024, 2025)
MAX_UNCOMPRESSED = 100_000_000


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _months(start_year: int):
    return [f"{start_year + (month > 12):04d}-{((month - 1) % 12) + 1:02d}"
            for month in range(7, 19)]


def _source_file(path: Path):
    match = re.fullmatch(r"fire_archive_(M-C61|SV-C2)_(\d+)\.csv", path.name)
    if not match or path.parent.name != f"DL_FIRE_{match.group(1)}_{match.group(2)}":
        raise ValueError(f"unexpected FIRMS archive filename: {path}")
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.reader(stream)
        header = next(reader)
        first = next(reader, None)
    if first is None or first[header.index("acq_date")][5:] != "07-01":
        raise ValueError(f"archive does not start on July 1: {path}")
    start_year = int(first[header.index("acq_date")][:4])
    if start_year not in EXPECTED_YEARS:
        raise ValueError(f"archive year outside the selected historical window: {path}")
    return SOURCE_CODES[match.group(1)], match.group(2), start_year


def build_bundle(archive_root: str | Path, output: str | Path, *, bbox=BBOX) -> dict:
    """Stream eight original world archives into dated, regional CSV slices."""
    validate_bbox(bbox)
    root, output = Path(archive_root), Path(output)
    files = sorted(root.glob("DL_FIRE_*/*archive*.csv"))
    if len(files) != 8:
        raise ValueError(f"expected eight world archive CSVs, found {len(files)}")
    inventory = {}
    for path in files:
        source, request_id, year = _source_file(path)
        if (source, year) in inventory:
            raise ValueError(f"duplicate {source} archive year {year}")
        inventory[(source, year)] = (path, request_id)
    if set(inventory) != {(source, year) for source in SERIES["joint"] for year in EXPECTED_YEARS}:
        raise ValueError("missing a MODIS or Suomi NPP archive year")

    sources, slices = [], []
    with tempfile.TemporaryDirectory(prefix="fireatlas-firms-slices-") as directory:
        temporary = Path(directory)
        for (source, start_year), (path, request_id) in sorted(inventory.items()):
            months = _months(start_year)
            counts = {month: 0 for month in months}
            selected = {month: 0 for month in months}
            versions = {month: set() for month in months}
            extra = 0
            with path.open(newline="", encoding="utf-8-sig") as stream, ExitStack() as stack:
                reader = csv.reader(stream)
                header = next(reader)
                required = {"latitude", "longitude", "acq_date", "acq_time", "satellite",
                            "instrument", "confidence", "version", "scan", "track", "frp", "daynight"}
                if not required <= set(header):
                    raise ValueError(f"missing FIRMS columns in {path.name}")
                index = {name: header.index(name) for name in required}
                writers = {}
                for month in months:
                    output_path = temporary / f"{source}_{month}.csv"
                    writer = csv.writer(stack.enter_context(output_path.open("w", newline="", encoding="utf-8")))
                    writer.writerow(header)
                    writers[month] = writer
                for line_number, row in enumerate(reader, 2):
                    if len(row) != len(header):
                        raise ValueError(f"bad CSV width in {path.name} line {line_number}")
                    month = row[index["acq_date"]][:7]
                    if month not in counts:
                        # The request's inclusive end date can add a July 1
                        # spillover; the next archive owns that full month.
                        if row[index["acq_date"]] == f"{start_year + 1}-07-01":
                            extra += 1
                            continue
                        raise ValueError(f"unexpected date in {path.name} line {line_number}")
                    if "NRT" in row[index["version"]].upper() or "URT" in row[index["version"]].upper():
                        raise ValueError(f"near-real-time row in standard archive {path.name}")
                    counts[month] += 1
                    lat, lon = float(row[index["latitude"]]), float(row[index["longitude"]])
                    if bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]:
                        writers[month].writerow(row)
                        selected[month] += 1
                        versions[month].add(row[index["version"]])
            original_hash = _sha256(path)
            sources.append({"request_id": request_id, "source_id": source,
                            "filename": path.name, "original_sha256": original_hash,
                            "period_start": months[0] + "-01", "period_end_exclusive": f"{start_year + 1}-07-01",
                            "worldwide_rows_by_month": counts, "spillover_rows_skipped": extra,
                            "scope_basis": "user-supplied FIRMS world archive request"})
            for month in months:
                if month[:4] <= "2025" and counts[month] == 0:
                    raise ValueError(f"historical world archive has no records for {source} {month}")
                if counts[month] == 0:
                    continue
                slice_path = temporary / f"{source}_{month}.csv"
                slices.append({"path": slice_path.name, "source_id": source, "month": month,
                               "rows": selected[month], "sha256": _sha256(slice_path),
                               "request_id": request_id, "original_sha256": original_hash,
                               "product_versions_in_aoi": sorted(versions[month]),
                               "complete_export": month[:4] <= "2025"})
        manifest = {"schema": SCHEMA, "bbox": list(bbox),
                    "source_page": "https://firms.modaps.eosdis.nasa.gov/download/",
                    "source_files": sources, "slices": slices,
                    "interpretation": "Complete means the supplied world export covers the month and this AOI; satellite pass and cloud coverage remain unknown. The original NASA request metadata is user supplied, not independently authenticated. 2026 slices remain partial."}
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=7) as bundle:
            for item in slices:
                bundle.write(temporary / item["path"], item["path"])
            bundle.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    return {"bundle": str(output), "sources": len(sources), "slices": len(slices),
            "selected_rows": sum(item["rows"] for item in slices),
            "complete_month_slices": sum(item["complete_export"] for item in slices)}


def import_bundle(database: str | Path, bundle_path: str | Path = SAMPLE) -> dict:
    """Check bundled hashes and import all slices without an API key."""
    with zipfile.ZipFile(bundle_path) as bundle:
        if sum(info.file_size for info in bundle.infolist()) > MAX_UNCOMPRESSED:
            raise ValueError("FIRMS archive bundle exceeds size limit")
        if len(bundle.namelist()) != len(set(bundle.namelist())):
            raise ValueError("duplicate FIRMS bundle entries")
        manifest = json.loads(bundle.read("manifest.json"))
        if manifest.get("schema") != SCHEMA or tuple(manifest.get("bbox", ())) != BBOX:
            raise ValueError("unsupported FIRMS archive bundle")
        if {item["path"] for item in manifest["slices"]} | {"manifest.json"} != set(bundle.namelist()):
            raise ValueError("FIRMS archive bundle inventory mismatch")
        if len(manifest["slices"]) != len({(item["source_id"], item["month"]) for item in manifest["slices"]}):
            raise ValueError("duplicate FIRMS source-month slice")
        parents = {(item["source_id"], item["request_id"]): item for item in manifest["source_files"]}
        if len(parents) != 8:
            raise ValueError("FIRMS parent archive inventory is incomplete")
        for item in manifest["slices"]:
            parent = parents.get((item["source_id"], item["request_id"]))
            if (item["source_id"] not in SERIES["joint"] or
                    item["path"] != f"{item['source_id']}_{item['month']}.csv" or
                    not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", item["month"]) or
                    not "2022-07" <= item["month"] <= "2026-06" or
                    item["complete_export"] != (item["month"][:4] <= "2025") or
                    not parent or parent["original_sha256"] != item["original_sha256"] or
                    not parent["period_start"][:7] <= item["month"] < parent["period_end_exclusive"][:7] or
                    hashlib.sha256(bundle.read(item["path"])).hexdigest() != item["sha256"]):
                raise ValueError(f"invalid FIRMS archive slice {item['path']}")
        imported = skipped = 0
        with connect(database) as db, tempfile.TemporaryDirectory(prefix="fireatlas-firms-import-") as directory:
            if db.execute("SELECT 1 FROM batches WHERE demo=1 LIMIT 1").fetchone():
                raise ValueError("FIRMS archive cannot be imported into a synthetic database")
            for item in manifest["slices"]:
                path = Path(directory) / item["path"]
                path.write_bytes(bundle.read(item["path"]))
                provenance = f"urn:fireatlas:nasa-firms-archive:{item['request_id']}:sha256:{item['original_sha256']}"
                result = ingest(db, path, item["source_id"], source_uri=provenance,
                                complete_month=item["month"] if item["complete_export"] else None,
                                bbox=BBOX if item["complete_export"] else None)
                if result["rows_read"] != item["rows"]:
                    raise ValueError(f"slice row count mismatch: {item['path']}")
                imported += result["rows_inserted"]
                skipped += int(result["already_imported"])
        return {"imported_rows": imported, "already_imported_slices": skipped,
                "slices": len(manifest["slices"]), "complete_month_slices": sum(item["complete_export"] for item in manifest["slices"])}


def _month_ids(start: date, end: date):
    month = date(start.year, start.month, 1)
    while month <= end:
        yield f"{month.year:04d}-{month.month:02d}"
        month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)


def import_requests(database: str | Path, request_root: str | Path) -> dict:
    """Import FIRMS archive CSVs accompanied by explicit request metadata.

    Each input directory must contain one ``request.json`` and one CSV, or
    ``request.json`` may name the standard CSV with ``csv_filename`` when an
    NRT companion is beside it. The CSV stays outside the repository; this
    routine clips it into the two declared study regions, records parent and
    request hashes in provenance, and records a complete month only when the
    requested date range and bbox fully contain that month and region. Empty
    months are retained as valid zero-detection exports when covered.
    """
    root, database = Path(request_root), Path(database)
    request_files = sorted(root.rglob("request.json"))
    if not request_files:
        raise ValueError(f"no request.json files found under {root}")
    imported_rows = skipped_slices = complete_month_slices = unverified_month_slices = request_count = 0
    with connect(database) as db:
        if db.execute("SELECT 1 FROM batches WHERE demo=1 LIMIT 1").fetchone():
            raise ValueError("FIRMS archive cannot be imported into a synthetic database")
        with tempfile.TemporaryDirectory(prefix="fireatlas-request-import-") as temporary:
            temp_root = Path(temporary)
            for request_path in request_files:
                folder = request_path.parent
                csv_files = sorted(path for path in folder.glob("*.csv") if path.is_file())
                try:
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    source = request["product"]
                    start = date.fromisoformat(request["start_date"])
                    end = date.fromisoformat(request["end_date"])
                    bbox = tuple(float(value) for value in request["bbox"])
                    coverage_basis = request.get("coverage_basis", "request-metadata")
                except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    raise ValueError(f"invalid FIRMS request metadata in {request_path}") from exc
                if not isinstance(coverage_basis, str) or coverage_basis not in {"request-metadata", "reconstructed-rows-only"}:
                    raise ValueError(f"{request_path}: unsupported coverage_basis")
                named_csv = request.get("csv_filename")
                if named_csv is not None:
                    if not isinstance(named_csv, str) or Path(named_csv).name != named_csv or Path(named_csv).suffix.lower() != ".csv":
                        raise ValueError(f"{request_path}: csv_filename must be a local CSV basename")
                    csv_path = folder / named_csv
                    if not csv_path.is_file():
                        raise ValueError(f"{request_path}: selected CSV does not exist")
                elif len(csv_files) == 1:
                    csv_path = csv_files[0]
                else:
                    raise ValueError(f"{folder} must contain exactly one FIRMS CSV or name csv_filename")
                if source not in PRODUCTS:
                    raise ValueError(f"{request_path}: product must be MODIS_SP or VIIRS_SNPP_SP; NRT is not accepted")
                request_id = request.get("request_id")
                if request_id is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", str(request_id)):
                    raise ValueError(f"{request_path}: request_id must be a short identifier")
                if end < start:
                    raise ValueError(f"{request_path}: end_date precedes start_date")
                validate_bbox(bbox)
                parent_hash, request_hash = _sha256(csv_path), _sha256(request_path)
                touched = list(_month_ids(start, end))
                selected_regions = [item for item in REGIONS.values() if intersects_bbox(bbox, item["bbox"])]
                if not selected_regions:
                    raise ValueError(f"{request_path}: request area does not intersect either study region")
                request_count += 1
                with csv_path.open(newline="", encoding="utf-8-sig") as stream:
                    reader = csv.DictReader(stream)
                    if reader.fieldnames is None or not set(REQUIRED_COLUMNS - {"instrument"}).issubset(reader.fieldnames):
                        raise ValueError(f"{csv_path}: missing required FIRMS columns")
                    writers = {}
                    output_paths = {}
                    versions_by_month = {month: set() for month in touched}
                    row_counts_by_month = {month: 0 for month in touched}
                    for region in selected_regions:
                        for month in touched:
                            key = (region["id"], month)
                            path = temp_root / f"{request_count}_{region['id']}_{month}.csv"
                            output_paths[key] = path
                            output = path.open("w", newline="", encoding="utf-8")
                            writer = csv.DictWriter(output, fieldnames=reader.fieldnames)
                            writer.writeheader()
                            writers[key] = (output, writer)
                    rows_read = 0
                    try:
                        for line_number, row in enumerate(reader, 2):
                            rows_read += 1
                            try:
                                observed_day = date.fromisoformat(row["acq_date"])
                                lat, lon = float(row["latitude"]), float(row["longitude"])
                            except (KeyError, TypeError, ValueError) as exc:
                                raise ValueError(f"{csv_path}: invalid date or coordinates on line {line_number}") from exc
                            if not start <= observed_day <= end:
                                raise ValueError(f"{csv_path}: row date falls outside request window on line {line_number}")
                            if not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]):
                                raise ValueError(f"{csv_path}: row falls outside declared request bbox on line {line_number}")
                            if "NRT" in row.get("version", "").upper() or "URT" in row.get("version", "").upper():
                                raise ValueError(f"{csv_path}: near-real-time row on line {line_number}; standard archive required")
                            month = f"{observed_day.year:04d}-{observed_day.month:02d}"
                            row_counts_by_month[month] += 1
                            if row.get("version", "").strip():
                                versions_by_month[month].add(row["version"].strip())
                            for region in selected_regions:
                                w, south, east, north = region["bbox"]
                                if w <= lon <= east and south <= lat <= north:
                                    writers[(region["id"], month)][1].writerow(row)
                    finally:
                        for stream, _writer in writers.values():
                            stream.close()
                for region in selected_regions:
                    for month in touched:
                        month_start = date.fromisoformat(month + "-01")
                        month_end = date(month_start.year, month_start.month, monthrange(month_start.year, month_start.month)[1])
                        worldwide_empty_month = (bbox == (-180.0, -90.0, 180.0, 90.0)
                                                  and row_counts_by_month[month] == 0)
                        full_request = (coverage_basis == "request-metadata"
                                        and start <= month_start and end >= month_end
                                        and contains_bbox(bbox, region["bbox"])
                                        and not worldwide_empty_month)
                        path = output_paths[(region["id"], month)]
                        versions = sorted(versions_by_month[month])
                        if not versions and request.get("product_version"):
                            declared = request["product_version"]
                            versions = sorted({str(item).strip() for item in declared}) if isinstance(declared, list) else [str(declared).strip()]
                        uri = (f"urn:fireatlas:firms-archive:{source}:request-id:{request_id or 'unspecified'}"
                               f":parent-sha256:{parent_hash}"
                               f":request-sha256:{request_hash}:region:{region['id']}")
                        result = ingest(db, path, source, source_uri=uri,
                                        complete_month=month if full_request else None,
                                        bbox=region["bbox"] if full_request else None,
                                        batch_key=f"{region['id']}:{month}:{request_hash}")
                        db.execute("""
                            INSERT OR REPLACE INTO source_exports(
                              batch_id,region_id,source_id,month,request_start,request_end,
                              west,south,east,north,complete_export,coverage_basis,product_versions_json,
                              parent_sha256,request_sha256)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (result["batch_id"], region["id"], source, month,
                              start.isoformat(), end.isoformat(), *bbox, int(full_request), coverage_basis,
                              json.dumps(versions), parent_hash, request_hash))
                        imported_rows += result["rows_inserted"]
                        skipped_slices += int(result["already_imported"])
                        complete_month_slices += int(full_request)
                        unverified_month_slices += int(coverage_basis == "reconstructed-rows-only")
    return {"requests": request_count, "imported_rows": imported_rows,
            "already_imported_slices": skipped_slices,
            "complete_month_slices": complete_month_slices,
            "reconstructed_row_only_month_slices": unverified_month_slices,
            "regions": [item["id"] for item in REGIONS.values()],
            "note": "Complete means request date and bbox cover the region; satellite pass and cloud coverage remain unknown."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="derive a compact bundle from the original world archives")
    build.add_argument("archive_root", type=Path)
    build.add_argument("--output", type=Path, default=SAMPLE)
    ingest_command = commands.add_parser("import", help="import a verified compact bundle")
    ingest_command.add_argument("--db", type=Path, default=Path("data/fireatlas.sqlite3"))
    ingest_command.add_argument("--bundle", type=Path, default=SAMPLE)
    requests = commands.add_parser("import-requests", help="import user-downloaded archive CSVs with request.json sidecars")
    requests.add_argument("request_root", type=Path)
    requests.add_argument("--db", type=Path, default=Path("data/fireatlas.sqlite3"))
    args = parser.parse_args()
    if args.command == "build":
        result = build_bundle(args.archive_root, args.output)
    elif args.command == "import":
        result = import_bundle(args.db, args.bundle)
    else:
        result = import_requests(args.db, args.request_root)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
