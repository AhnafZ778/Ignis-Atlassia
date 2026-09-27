"""Resumable authentic-data pilot imports and reproducibility checks."""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Thread

from .core import SERIES, _complete_month, calendar, connect
from .fetch import availability, fetch_month
from .settings import firms_key
from .study import build_bundle, verify_bundle

# Geographic comparison areas, not validated vegetation or incident boundaries.
PILOTS = [
    {"id": "northern-california", "name": "Northern California", "bbox": [-122, 39, -120, 41],
     "description": "Regional pilot containing mixed land cover. No detections are attributed to an individual incident."},
    {"id": "sacramento-valley", "name": "Sacramento Valley", "bbox": [-122.2, 38.8, -121.5, 39.5],
     "description": "Contrasting geographic pilot. Agricultural-burning classification requires a validated land-cover mask."},
]
YEARS = [2021, 2022, 2023, 2024]


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n")
    temp.replace(path)


def validate_pilots(db):
    results = []
    for pilot in PILOTS:
        summary = calendar(db, bbox=tuple(pilot["bbox"]), year=2024)
        month = summary["monthly"][6]
        if summary["demo_data"]:
            raise ValueError("Authentic-data validation cannot include synthetic records")
        if not month["export_window_complete"] or month["baseline_years"] != YEARS[:-1]:
            # Extra qualifying years can be present in an existing real-data database.
            if not month["export_window_complete"] or not set(YEARS[:-1]).issubset(month["baseline_years"]):
                raise ValueError("Pilot validation requires both sources for July 2021–2024")
        bundle = build_bundle(db, year=2024, month=7, series="joint", bbox=tuple(pilot["bbox"]))
        verification = verify_bundle(io.BytesIO(bundle))
        results.append({"id": pilot["id"], "name": pilot["name"], "bbox": pilot["bbox"],
                        "month": "2024-07", "cell_days": month["detected_cell_days"],
                        "baseline_median": month["baseline_median"], "baseline_years": month["baseline_years"],
                        "anomaly_cell_days": month["anomaly_cell_days"], "product_versions": summary["product_versions"],
                        "bundle_verification": verification,
                        "scientific_validation": "Pending matched overpasses, land-cover and observation masks, reference labels and expert review."})
    return {"checked_utc": now(), "status": "reproduced", "pilots": results,
            "scope": "Pipeline reproducibility on authentic imports; not scientific calibration or field validation."}


class PilotSync:
    def __init__(self, database):
        self.database = Path(database)
        self.status_path = self.database.with_suffix(".sync.json")
        self.directory = self.database.parent / "downloads"
        self.lock = Lock()
        self.running = False
        self.hms_validation_batch = None
        self.hms_validation = None
        try:
            self.state = json.loads(self.status_path.read_text())
        except (OSError, ValueError):
            self.state = {"status": "idle", "message": "Ready to check NASA FIRMS and import pilot records.", "completed": 0, "total": 16}
        if self.state.get("status") in ("checking", "downloading", "validating"):
            self.state.update(status="interrupted", message="The previous sync was interrupted. Retry to resume completed imports.")

    def update(self, **values):
        with self.lock:
            self.state.update(values, updated_utc=now())
            write_json(self.status_path, self.state)

    def status(self):
        with self.lock:
            state = dict(self.state)
        with connect(self.database) as db:
            sources = [dict(row) for row in db.execute("""
                SELECT b.source_id,b.demo,count(DISTINCT b.id) AS imports,
                       count(o.detection_id) AS observations,max(b.retrieved_utc) AS retrieved_utc,
                       min(o.acquisition_utc) AS first_observation,max(o.acquisition_utc) AS last_observation,
                       min(o.lon) AS west,min(o.lat) AS south,max(o.lon) AS east,max(o.lat) AS north
                FROM batches b LEFT JOIN observations o ON o.batch_id=b.id GROUP BY b.source_id,b.demo
                ORDER BY b.source_id,b.demo
            """)]
            for source in sources:
                source["series"] = next((name for name, ids in SERIES.items() if ids == (source["source_id"],)), None)
                window = db.execute("SELECT month,west,south,east,north FROM export_windows WHERE source_id=? ORDER BY month DESC LIMIT 1", (source["source_id"],)).fetchone()
                source["latest_window"] = dict(window) if window else None
            pilots = []
            for pilot in PILOTS:
                windows = [{"year": year, "source": source,
                            "complete": _complete_month(db, f"{year}-07", (source,), tuple(pilot["bbox"]))}
                           for year in YEARS for source in SERIES["joint"]]
                pilots.append({**pilot, "windows": windows})
            state["completed"] = sum(window["complete"] for pilot in pilots for window in pilot["windows"])
            hms_windows = [{"year": year, "complete": _complete_month(db, f"{year}-07", ("NOAA_HMS_VIIRS",), tuple(PILOTS[0]["bbox"]))}
                           for year in YEARS]
            hms_batch = db.execute("SELECT MAX(id) FROM batches WHERE source_id='NOAA_HMS_VIIRS'").fetchone()[0]
            if hms_batch != self.hms_validation_batch:
                self.hms_validation_batch = hms_batch
                self.hms_validation = None
                if hms_batch and all(item["complete"] for item in hms_windows):
                    try:
                        area = tuple(PILOTS[0]["bbox"])
                        july = calendar(db, bbox=area, year=2024, series="hms-viirs")["monthly"][6]
                        result = verify_bundle(io.BytesIO(build_bundle(db, year=2024, month=7, series="hms-viirs", bbox=area)))
                        self.hms_validation = {"status": "reproduced", "cell_days": july["detected_cell_days"],
                                               "baseline_median": july["baseline_median"],
                                               "baseline_years": july["baseline_years"],
                                               "observations_verified": result["observations"],
                                               "bundle_verified": result["verified"]}
                    except (ValueError, OSError, KeyError):
                        self.hms_validation = {"status": "failed"}
        return {"credential_configured": bool(firms_key()), "sync": state, "sources": sources, "pilots": pilots,
                "hms_windows": hms_windows, "hms_validation": self.hms_validation,
                "synthetic": any(row["demo"] for row in sources)}

    def start(self):
        with self.lock:
            if self.running:
                return False
            self.running = True
        Thread(target=self.run, daemon=True).start()
        return True

    def reconcile_imports(self):
        """Update the pilot matrix after a user-supplied CSV without contacting FIRMS."""
        with connect(self.database) as db:
            completed = sum(
                _complete_month(db, f"{year}-07", (source,), tuple(pilot["bbox"]))
                for pilot in PILOTS for year in YEARS for source in SERIES["joint"]
            )
            if completed == 16:
                validation = validate_pilots(db)
                write_json(self.database.with_suffix(".validation.json"), validation)
                self.update(status="complete", completed=completed, total=16, validation=validation,
                            message="All pilot exports imported. Calendar totals and baselines reproduced.")
            else:
                self.update(status="partial", completed=completed, total=16, validation=None,
                            message=f"{completed} of 16 complete pilot exports imported. Partial CSVs remain visible without a completeness claim.")
        return self.status()

    def run(self):
        try:
            with connect(self.database) as db:
                if db.execute("SELECT 1 FROM batches WHERE demo=1 LIMIT 1").fetchone():
                    raise ValueError("This server uses synthetic data. Start it with a separate authentic-data database before syncing.")
                if all(_complete_month(db, f"{year}-07", (source,), tuple(pilot["bbox"]))
                       for pilot in PILOTS for year in YEARS for source in SERIES["joint"]):
                    self.reconcile_imports()
                    return
                self.update(status="checking", message="Checking NASA source availability…", completed=0, validation=None)
                available = availability()
                for source in SERIES["joint"]:
                    row = next((r for r in available if r["data_id"] == source), None)
                    if not row or row["min_date"] > "2021-07-01" or row["max_date"] < "2024-07-31":
                        raise ValueError(f"{source} does not currently offer the entire pilot period")
                self.update(availability=available, connection_verified_utc=now())
                completed = 0
                for pilot in PILOTS:
                    for year in YEARS:
                        for source in SERIES["joint"]:
                            self.update(status="downloading", message=f"{pilot['name']} · July {year} · {source}", completed=completed)
                            # Completed months are reusable even if their temporary CSV cache was removed.
                            if not _complete_month(db, f"{year}-07", (source,), tuple(pilot["bbox"])):
                                fetch_month(db, month=f"{year}-07", source_id=source, bbox=tuple(pilot["bbox"]),
                                            directory=self.directory, available_sources=available)
                            completed += 1
                            self.update(completed=completed)
                self.update(status="validating", message="Reproducing cell-days and baseline totals from evidence bundles…")
                validation = validate_pilots(db)
                write_json(self.database.with_suffix(".validation.json"), validation)
                self.update(status="complete", message="Pilot imports complete. Calendar totals and baselines reproduced.", validation=validation)
        except (ValueError, OSError) as exc:
            # Download errors are already sanitized; never serialize an HTTP request URL.
            self.update(status="failed", message=str(exc))
        except Exception:
            self.update(status="failed", message="Pilot sync could not finish. Completed imports are retained; retry to resume.")
        finally:
            with self.lock:
                self.running = False
