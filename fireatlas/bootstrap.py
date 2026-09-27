"""Load the small, verified NOAA HMS pilot slice bundled for first launch."""

from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from datetime import date, timedelta
from pathlib import Path

from .core import connect, ingest
from .hms import ARCHIVE, SOURCE

SAMPLE = Path(__file__).with_name("samples") / "noaa_hms_northern_california_july_2021_2024.zip"
BBOX = (-122.0, 39.0, -120.0, 41.0)


def populate_showcase(database: str | Path) -> dict:
    """Seed an empty authentic database; leave existing observations untouched."""
    with connect(database) as db:
        if db.execute("SELECT 1 FROM batches LIMIT 1").fetchone():
            return {"loaded": False, "reason": "database already contains imports"}
        with zipfile.ZipFile(SAMPLE) as archive:
            validated = []
            for year in (2021, 2022, 2023, 2024):
                csv_bytes = archive.read(f"{year}.csv")
                manifest = json.loads(archive.read(f"{year}.manifest.json"))
                if (manifest.get("source") != SOURCE or manifest.get("month") != f"{year}-07"
                        or tuple(manifest.get("bbox", ())) != BBOX or len(manifest.get("archives", ())) != 31
                        or manifest.get("csv_sha256") != hashlib.sha256(csv_bytes).hexdigest()
                        or {entry.get("date") for entry in manifest["archives"]}
                            != {(date(year, 7, 1) + timedelta(days=index)).isoformat() for index in range(31)}
                        or any(not entry.get("sha256") or not entry.get("url", "").startswith(ARCHIVE + "/")
                               for entry in manifest["archives"])):
                    raise ValueError(f"Bundled NOAA HMS showcase verification failed for July {year}")
                validated.append((year, csv_bytes))
        loaded = []
        with tempfile.TemporaryDirectory(prefix="fireatlas-showcase-") as temporary:
            for year, csv_bytes in validated:
                path = Path(temporary) / f"NOAA_HMS_VIIRS_{year}-07.csv"
                path.write_bytes(csv_bytes)
                result = ingest(db, path, SOURCE, source_uri=f"{ARCHIVE}/{year}/07/",
                                complete_month=f"{year}-07", bbox=BBOX)
                loaded.append({"year": year, "rows": result["rows_inserted"]})
        return {"loaded": True, "source": SOURCE, "months": loaded}
