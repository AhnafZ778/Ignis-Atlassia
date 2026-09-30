"""Create clearly marked row-only metadata for supplied legacy FIRMS exports.

The older download folders do not include their original FIRMS request forms.
Their year windows are inferred from archive dates and neighboring exports,
so these sidecars intentionally cannot certify complete months.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path


# (folder name, product, request ID, July start year, standard CSV filename)
LEGACY = [
    # These newer additions were supplied without the original FIRMS request
    # JSON.  Keep them row-only until the request metadata can be recovered;
    # the inferred July boundaries are useful for indexing but cannot certify
    # complete monthly coverage.
    ("DL_FIRE_M-C61_814851", "MODIS_SP", "814851", 2006, "fire_archive_M-C61_814851.csv"),
    ("DL_FIRE_M-C61_814850", "MODIS_SP", "814850", 2007, "fire_archive_M-C61_814850.csv"),
    ("DL_FIRE_M-C61_814849", "MODIS_SP", "814849", 2008, "fire_archive_M-C61_814849.csv"),
    ("DL_FIRE_M-C61_814847", "MODIS_SP", "814847", 2009, "fire_archive_M-C61_814847.csv"),
    ("DL_FIRE_M-C61_814374", "MODIS_SP", "814374", 2010, "fire_archive_M-C61_814374.csv"),
    ("DL_FIRE_M-C61_814365", "MODIS_SP", "814365", 2011, "fire_archive_M-C61_814365.csv"),
    ("DL_FIRE_M-C61_814363", "MODIS_SP", "814363", 2012, "fire_archive_M-C61_814363.csv"),
    ("DL_FIRE_M-C61_814361", "MODIS_SP", "814361", 2013, "fire_archive_M-C61_814361.csv"),
    ("DL_FIRE_M-C61_814359", "MODIS_SP", "814359", 2014, "fire_archive_M-C61_814359.csv"),
    ("DL_FIRE_M-C61_814355", "MODIS_SP", "814355", 2015, "fire_archive_M-C61_814355.csv"),
    ("DL_FIRE_M-C61_814357", "MODIS_SP", "814357", 2016, "fire_archive_M-C61_814357.csv"),
    ("DL_FIRE_M-C61_814353", "MODIS_SP", "814353", 2017, "fire_archive_M-C61_814353.csv"),
    ("DL_FIRE_M-C61_814351", "MODIS_SP", "814351", 2018, "fire_archive_M-C61_814351.csv"),
    ("DL_FIRE_M-C61_814347", "MODIS_SP", "814347", 2020, "fire_archive_M-C61_814347.csv"),
    ("DL_FIRE_M-C61_814831", "MODIS_SP", "814831", 2019, "fire_archive_M-C61_814831.csv"),
    ("DL_FIRE_M-C61_814832", "MODIS_SP", "814832", 2021, "fire_archive_M-C61_814832.csv"),
    ("DL_FIRE_SV-C2_814364", "VIIRS_SNPP_SP", "814364", 2012, "fire_archive_SV-C2_814364.csv"),
    ("DL_FIRE_SV-C2_814362 (2)", "VIIRS_SNPP_SP", "814362", 2013, "fire_archive_SV-C2_814362.csv"),
    ("DL_FIRE_SV-C2_814360", "VIIRS_SNPP_SP", "814360", 2014, "fire_archive_SV-C2_814360.csv"),
    ("DL_FIRE_SV-C2_814356", "VIIRS_SNPP_SP", "814356", 2015, "fire_archive_SV-C2_814356.csv"),
    ("DL_FIRE_SV-C2_814358", "VIIRS_SNPP_SP", "814358", 2016, "fire_archive_SV-C2_814358.csv"),
    ("DL_FIRE_SV-C2_814354", "VIIRS_SNPP_SP", "814354", 2017, "fire_archive_SV-C2_814354.csv"),
    ("DL_FIRE_SV-C2_814352", "VIIRS_SNPP_SP", "814352", 2018, "fire_archive_SV-C2_814352.csv"),
    ("DL_FIRE_SV-C2_814350", "VIIRS_SNPP_SP", "814350", 2019, "fire_archive_SV-C2_814350.csv"),
    ("DL_FIRE_SV-C2_814348", "VIIRS_SNPP_SP", "814348", 2020, "fire_archive_SV-C2_814348.csv"),
]


def prepare(root: Path) -> list[Path]:
    created = []
    for folder, product, request_id, start_year, filename in LEGACY:
        directory = root / folder
        source = directory / filename
        sidecar = directory / "request.json"
        if not source.is_file():
            print(f"SKIP missing source: {folder}/{filename}")
            continue
        if sidecar.exists():
            print(f"SKIP existing request metadata: {folder}")
            continue
        # Check the file is a readable FIRMS table before writing any metadata.
        with source.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or not {"latitude", "longitude", "acq_date", "version"}.issubset(reader.fieldnames):
                raise ValueError(f"{source}: not a recognizable FIRMS archive CSV")
        payload = {
            "product": product,
            "start_date": date(start_year, 7, 1).isoformat(),
            "end_date": date(start_year + 1, 7, 2).isoformat(),
            "bbox": [-180, -90, 180, 90],
            "request_id": request_id,
            "csv_filename": filename,
            "coverage_basis": "reconstructed-rows-only",
            "note": "Exact original request dates and area were not retained. July archive bounds are reconstructed for row import only; the application must not record complete monthly export coverage from this sidecar.",
        }
        sidecar.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        created.append(sidecar)
        print(f"CREATED row-only metadata: {folder}")
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path("NASA_data"))
    args = parser.parse_args()
    if not args.root.is_dir():
        raise SystemExit(f"NASA archive folder not found: {args.root}")
    prepared = prepare(args.root)
    print(f"Prepared {len(prepared)} reconstructed row-only request sidecar(s).")


if __name__ == "__main__":
    main()
