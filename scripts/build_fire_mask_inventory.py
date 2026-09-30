"""Inventory every locally downloaded NASA fire-mask/geolocation asset."""

from __future__ import annotations

import csv
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "NASA_data" / "fire_masks"
CHECKLIST = ASSET_ROOT / "download_checklist.csv"
OUTPUT = ASSET_ROOT / "local_asset_inventory.csv"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build() -> dict:
    with CHECKLIST.open(newline="", encoding="utf-8") as handle:
        checklist: dict[str, list[dict[str, str]]] = {}
        for row in csv.DictReader(handle):
            checklist.setdefault(row["filename"], []).append(row)

    paths = sorted(path for path in ASSET_ROOT.iterdir()
                   if path.is_file() and path.suffix.lower() in {".hdf", ".nc"})
    with ThreadPoolExecutor(max_workers=4) as pool:
        hashes = list(pool.map(_sha256, paths))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "filename", "product", "version", "role", "bytes", "sha256",
            "local_project_path", "checklist_status", "checklist_matches_json",
        ])
        writer.writeheader()
        for path, digest in zip(paths, hashes):
            fields = path.name.split(".")
            product = fields[0]
            matches = checklist.get(path.name, [])
            writer.writerow({
                "filename": path.name,
                "product": product,
                "version": fields[3] if len(fields) > 3 else "",
                "role": "geolocation" if product.endswith("03") or product.endswith("03IMG") else "fire-mask",
                "bytes": path.stat().st_size,
                "sha256": digest,
                "local_project_path": path.relative_to(ROOT).as_posix(),
                "checklist_status": "source-url-recorded" if matches else "no-checklist-record",
                "checklist_matches_json": json.dumps(matches, sort_keys=True, separators=(",", ":")),
            })

    total_bytes = sum(path.stat().st_size for path in paths)
    return {
        "output": OUTPUT.relative_to(ROOT).as_posix(),
        "asset_count": len(paths),
        "checklist_matched_assets": sum(path.name in checklist for path in paths),
        "assets_without_checklist_record": sum(path.name not in checklist for path in paths),
        "total_bytes": total_bytes,
        "inventory_sha256": _sha256(OUTPUT),
    }


if __name__ == "__main__":
    print(json.dumps(build(), sort_keys=True))
