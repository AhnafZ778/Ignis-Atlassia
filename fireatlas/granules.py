"""Public NASA CMR metadata inventory for the fixed validity cases.

CMR granule footprints identify candidate fire-mask and geolocation files.
Metadata alone cannot classify ground cells as clear, cloudy, or observed.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from .validity import CASES

SAMPLE = Path(__file__).with_name("samples") / "validity_cmr_inventory.json"
PRODUCTS = (
    ("MOD14", "061", "fire-mask"), ("MYD14", "061", "fire-mask"),
    ("VNP14IMG", "002", "fire-mask"),
    ("MOD03", "6.1", "geolocation"), ("MYD03", "6.1", "geolocation"),
    ("VNP03IMG", "2", "geolocation"),
)


def query(case_id: str, product: str, version: str, role: str) -> dict:
    case = CASES[case_id]
    end = (date.fromisoformat(case["end"]) + timedelta(days=1)).isoformat()
    params = {"short_name": product, "version": version,
              "temporal": f'{case["start"]}T00:00:00Z,{end}T00:00:00Z',
              "bounding_box": ",".join(map(str, case["bbox"])), "page_size": "2000"}
    url = "https://cmr.earthdata.nasa.gov/search/granules.json?" + urlencode(params)
    with urlopen(url, timeout=30) as response:
        hits = int(response.headers["CMR-Hits"])
        entries = json.load(response)["feed"]["entry"]
    if len(entries) != hits:
        raise ValueError(f"CMR returned {len(entries)} of {hits} {product} granules; pagination required")
    granules = []
    for entry in entries:
        download = next((link["href"] for link in entry.get("links", [])
                         if link.get("rel", "").endswith("/data#")
                         and link.get("href", "").startswith("https://")), None)
        granules.append({"cmr_id": entry["id"], "producer_id": entry.get("producer_granule_id"),
                         "start_utc": entry["time_start"], "end_utc": entry.get("time_end"),
                         "download_url": download})
    return {"product": product, "version": version, "role": role, "cmr_query": url,
            "cmr_hits": hits, "granules": sorted(granules, key=lambda g: (g["start_utc"], g["cmr_id"]))}


def refresh() -> dict:
    result = {"schema": "fireatlas-cmr-inventory-v1",
              "retrieved_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
              "interpretation": "Public CMR candidate granule metadata only; raw files and geolocation have not been downloaded, matched, or decoded. No ground-cell pass/cloud state follows from this list.",
              "cases": {}}
    for case_id in CASES:
        result["cases"][case_id] = {"bbox": CASES[case_id]["bbox"],
                                    "start_utc": CASES[case_id]["start"],
                                    "end_utc": CASES[case_id]["end"],
                                    "products": [query(case_id, *product) for product in PRODUCTS]}
    return result


def load(path: str | Path = SAMPLE) -> dict:
    return json.loads(Path(path).read_text())


def summary(inventory: dict, case_id: str) -> dict:
    case = inventory["cases"][case_id]
    by_product = {item["product"]: item for item in case["products"]}
    companion = {"MOD14": "MOD03", "MYD14": "MYD03", "VNP14IMG": "VNP03IMG"}
    geolocation_times = {product: {granule["start_utc"] for granule in by_product[product]["granules"]}
                         for product in companion.values()}
    return {"status": "metadata-only", "retrieved_utc": inventory["retrieved_utc"],
            "products": [{"product": item["product"], "role": item["role"],
                          "version": item["version"], "cmr_hits": item["cmr_hits"],
                          "companion_geolocation_time_matches": sum(
                              1 for granule in item["granules"]
                              if granule["start_utc"] in geolocation_times[companion[item["product"]]])
                              if item["role"] == "fire-mask" else None}
                         for item in case["products"]],
            "interpretation": inventory["interpretation"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Refresh public NASA CMR pilot granule metadata")
    parser.add_argument("--output", type=Path, default=SAMPLE)
    args = parser.parse_args()
    inventory = refresh()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(inventory, sort_keys=True, indent=2) + "\n")
    print(json.dumps({case_id: summary(inventory, case_id)["products"]
                      for case_id in CASES}, indent=2))
