"""Refresh the published UI while preserving the existing observation snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.export_static import STATIC, _copy_site_assets, _rebase_local_asset_urls


def refresh(site: Path) -> None:
    manifest_path = site / "data" / "v2" / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("No observation manifest found. Build the static data export first.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot = manifest.get("snapshot_utc_date")
    if not snapshot:
        raise ValueError("The data manifest has no snapshot date; refusing to relabel its observations.")
    _copy_site_assets(site, STATIC, snapshot_date=snapshot)
    _rebase_local_asset_urls(site)
    print(f"Updated website assets in {site}; observation snapshot remains {snapshot}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    args = parser.parse_args()
    refresh(args.site.resolve())
