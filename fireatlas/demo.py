"""Generate clearly labelled synthetic FIRMS-shaped records for a reproducible demo."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from .core import connect, ingest

BBOX = (-122.0, 39.0, -120.0, 41.0)
FIELDS = [
    "latitude", "longitude", "acq_date", "acq_time", "satellite",
    "instrument", "confidence", "version", "scan", "track", "frp", "daynight",
]


def make_demo(directory: Path, database: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    db = connect(database)
    try:
        for year in (2001, 2002, 2003, 2004, 2012, 2013, 2014, 2015):
            for source in (("MODIS_SP", "VIIRS_SNPP_SP") if year >= 2012 else ("MODIS_SP",)):
                rows = []
                sensor = "MODIS" if source == "MODIS_SP" else "VIIRS"
                for day in range(1, 2 + (year % 4)):
                    # Same location/day across sensors. VIIRS has extra pixels;
                    # joint cell-days still count each common cell once.
                    for pixel in range(1 if sensor == "MODIS" else 3):
                        rows.append({
                            "latitude": f"40.{12345 + pixel:05d}",
                            "longitude": f"-121.{12345 + pixel:05d}",
                            "acq_date": f"{year}-07-{day:02d}",
                            "acq_time": "1234",
                            "satellite": "T" if sensor == "MODIS" else "N",
                            "instrument": sensor,
                            "confidence": "80" if sensor == "MODIS" else "n",
                            "version": "6.1" if sensor == "MODIS" else "2.0",
                            "scan": "1.0" if sensor == "MODIS" else "0.38",
                            "track": "1.0" if sensor == "MODIS" else "0.38",
                            "frp": "12.4",
                            "daynight": "D",
                        })
                path = directory / f"SYNTHETIC_{source}_{year}_07.csv"
                with path.open("w", newline="") as output:
                    writer = csv.DictWriter(output, fieldnames=FIELDS)
                    writer.writeheader()
                    writer.writerows(rows)
                result = ingest(
                    db, path, source, source_uri=f"synthetic://fireatlas/{path.name}",
                    complete_month=f"{year}-07", bbox=BBOX, demo=True,
                )
                print(f"{path.name}: {result['rows_inserted']} inserted")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("data/demo"))
    parser.add_argument("--db", type=Path, default=Path("data/demo.sqlite3"))
    args = parser.parse_args()
    make_demo(args.directory, args.db)


if __name__ == "__main__":
    main()
