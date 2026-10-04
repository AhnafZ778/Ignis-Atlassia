"""Read-only, bounded adapters around authoritative FireAtlas calculations."""
from __future__ import annotations

import contextlib
import json
import math
import sqlite3
import threading
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from ..core import Connection, SERIES, GRID_VERSION, calendar
from ..provenance import sanitize_public_payload
from ..replay import CASES, SOURCES, build_case
from ..research import report, context as research_context
from .contracts import METHODS, LIMITATION, digest, normalize_context

ROOT = Path(__file__).resolve().parents[2]
HEAVY = threading.Semaphore(1)
OPERATIONS = ("archive_search", "availability", "observations", "replay", "research", "calendar", "harmonized", "persistence", "missingness", "compare", "sensitivity", "exposure", "validation", "method", "sources")


def readonly(path):
    db = sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro", uri=True, factory=Connection, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


class Science:
    def __init__(self, database, store):
        self.database, self.store = Path(database), store
        self._release = None
        self._stamp = None
        self._lock = threading.Lock()

    def release(self):
        paths = [self.database, Path(str(self.database)+"-wal"), ROOT/"data/validity_masks.sqlite3", ROOT/"data/validity_masks.sqlite3-wal", ROOT/"fireatlas/static/replay-context/manifest.json", ROOT/"fireatlas/samples/sensor_notices.json", ROOT/"fireatlas/samples/validity_incident_cohort.json", ROOT/"fireatlas/samples/validity_cmr_inventory.json", *sorted((ROOT/"fireatlas/samples/calibration").glob('*.json'))]
        stamp = tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None for p in paths)
        with self._lock:
            if stamp != self._stamp:
                with readonly(self.database) as db:
                    ledger = [dict(r) for r in db.execute("SELECT source_id,file_sha256,window_key,row_count,demo FROM batches ORDER BY source_id,file_sha256,window_key")]
                    schema = [r[0] for r in db.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name")]
                    exports=[dict(r) for r in db.execute("SELECT * FROM source_exports ORDER BY source_id,month")]
                files = {}
                for path in paths[2:]:
                    if path.is_file():
                        import hashlib
                        hashed=hashlib.sha256()
                        with path.open('rb') as stream:
                            while chunk:=stream.read(8*1024*1024):hashed.update(chunk)
                        files[path.name] = hashed.hexdigest()
                value = {"source_ledger": ledger, "export_inventory":sanitize_public_payload(exports), "schema": schema, "supporting_files": files}
                self._release = {"id": digest(value), "basis": "source ledger and supporting manifest; live database stamp checked for each result", "frozen": False, "manifest": value}
                frozen = self.database.parent/"assistant-release.json"
                if frozen.is_file():
                    saved = json.loads(frozen.read_text())
                    if saved.get("database") == self.database.name and saved.get("source_basis_hash")==digest(value) and saved.get("database_stamp")==list(stamp[0]) and not paths[1].exists():
                        self._release = saved
                self._stamp = stamp
            return self._release

    def call(self, owner, operation, context, arguments=None, cancel=None, deadline=None):
        if operation not in OPERATIONS:
            raise ValueError("Unsupported scientific operation.")
        config, args = normalize_context(context), arguments or {}
        if not isinstance(args, dict):
            raise ValueError("Tool arguments must be an object.")
        if args.get('study_month') is not None:
            # Explicit month selection reuses the existing research calculation;
            # its returned evidence records the actual intersected interval.
            from calendar import monthrange
            month = args['study_month']
            if operation not in {'research','exposure','sensitivity'} or not isinstance(month,str):
                raise ValueError('A study month is supported only for monthly research tools.')
            try:
                first = date.fromisoformat(month+'-01')
                last = date(first.year,first.month,monthrange(first.year,first.month)[1])
                start,end=max(config['start'],first.isoformat()),min(config['end'],last.isoformat())
                if start>end:raise ValueError()
            except (ValueError,TypeError):
                raise ValueError('Choose a YYYY-MM month inside the current study interval.') from None
            config=normalize_context({**config,'start':start,'end':end,'day':config['day'] if start<=config['day']<=end else start,
                'as_of':end,'year':first.year,'month':first.month})
        cancel = cancel or threading.Event()
        deadline = deadline or time.monotonic()+120
        release = self.release()
        heavy = operation in {"research", "sensitivity", "validation", "harmonized", "calendar", "exposure"}
        with contextlib.ExitStack() as stack:
            if heavy:
                while not HEAVY.acquire(timeout=.2):
                    if cancel.is_set() or time.monotonic() > deadline:
                        raise TimeoutError("Analysis cancelled or timed out while waiting for its calculation slot.")
                stack.callback(HEAVY.release)
            db = stack.enter_context(readonly(self.database))
            db.set_progress_handler(lambda: int(cancel.is_set() or time.monotonic() > deadline), 10000)
            start_stamp = self._stamp
            if cancel.is_set():
                raise InterruptedError("Investigation stopped.")
            payload, method = self._execute(db, operation, config, args, cancel, deadline, owner)
        if cancel.is_set() or time.monotonic() > deadline:
            raise InterruptedError("Investigation stopped or timed out.")
        self.release()
        if start_stamp != self._stamp:
            raise ValueError("Scientific data changed during the calculation. Retry against the current release.")
        method_info=dict(METHODS.get(method, {"id": method, "unit": "descriptive evidence"}))
        if operation in {'research','exposure'}:method_info['id']=payload.get('method_version',method_info['id'])
        body = {"schema": "fireatlas-assistant-evidence-v1", "release_id": release["id"], "release_frozen": release.get("frozen", False), "operation": operation, "method": method_info, "context": config, "grid": GRID_VERSION, "payload": sanitize_public_payload(payload), "limitations": [LIMITATION]}
        body["sha256"] = digest(body)
        identifier = self.store.artifact(owner, "evidence", body)
        return {"id": identifier, **body}

    def _replay(self, db, cfg):
        if cfg['series'] not in {'joint','modis','viirs-snpp'}:
            raise ValueError('Replay supports standard MODIS and VIIRS S-NPP. This selected stream remains inspectable as original records or raw calendar data.')
        if cfg.get("case"):
            full = CASES[cfg["case"]]
            if cfg["start"] == full["start"] and cfg["end"] == full["end"] and cfg["bbox"] == full["bbox"]:
                return build_case(db, cfg["case"], max_records=10000)
        return build_case(db, "custom-observation-study", max_records=10000, study={"title": "Custom observation study", "subtitle": "Stored observation records; incident membership unverified", "start": cfg["start"], "end": cfg["end"], "selected_day": cfg["day"] or cfg["start"], "bbox": cfg["bbox"], "notes": [LIMITATION]})

    def _research(self, db, cfg, mask=None):
        if cfg["start"][:7] != cfg["end"][:7]:
            raise ValueError("Research windows must stay within one UTC month. Use replay across months or select each monthly analysis explicitly.")
        return report(db, year=int(cfg["start"][:4]), month=int(cfg["start"][5:7]), bbox=cfg["bbox"], as_of=cfg["end"], distance_km=cfg["distance_km"], gap_days=cfg["gap_days"], mask=mask, start_date=cfg["start"] if cfg["start"][8:] != "01" else None)

    def _execute(self, db, op, cfg, args, cancel, deadline, owner):
        if op == "archive_search":
            return self.archive_search(db, cfg, args), "archive_search"
        if op == "method":
            return {"methods": METHODS, "differences": "Research does not apply replay's vegetation-type eligibility or exact-alias deduplication. Calendar estimates and original detection counts have different units.", "coverage": "Coverage rates require a compatible source/cell/day observation mask. A complete export does not prove clear satellite coverage.", "review": "Independent native-mask review must be performed and signed by a human reviewer."}, "research"
        if op == "sources":
            from .references import search
            return search(str(args.get("query", "MODIS VIIRS"))[:300]), "sources"
        if op == "availability":
            rows = [dict(r) for r in db.execute("SELECT o.source_id,COUNT(*) AS imported_records,MIN(o.acquisition_utc) AS first_utc,MAX(o.acquisition_utc) AS last_utc FROM observations o JOIN batches b ON o.batch_id=b.id WHERE b.demo=0 GROUP BY o.source_id")]
            windows = [dict(r) for r in db.execute("SELECT source_id,MIN(month) AS first_month,MAX(month) AS last_month,COUNT(*) AS export_requests FROM source_exports GROUP BY source_id")]
            return {"sources": rows, "export_inventory": windows, "cases": [{"id": k, **{n: v[n] for n in ("title", "start", "end", "bbox")}} for k, v in CASES.items()], "context_layers": json.loads((ROOT/"fireatlas/static/replay-context/manifest.json").read_text()), "note": "Historical rows do not establish complete monthly coverage. NRT and other imported streams remain separate."}, "availability"
        if op == "observations":
            return self.observations(db, cfg, args), "observations"
        if op == "calendar":
            return calendar(db, year=cfg["year"], series=cfg["series"], bbox=tuple(cfg["bbox"])), "calendar"
        if op == "harmonized":
            from ..calendar_v2 import calendar_v2
            from ..regions import REGIONS
            region = cfg["region"]
            if region not in REGIONS or list(REGIONS[region]["bbox"]) != cfg["bbox"]:
                raise ValueError("Harmonization requires the exact calibrated regional bounds. Custom areas have no local calibration; raw observation analysis remains available.")
            return calendar_v2(db, region=region, year=cfg["year"], month=cfg["month"]), "harmonized"
        if op in {"research", "exposure"}:
            mask = None
            if op == "exposure" and cfg.get("mask_id"):
                mask = self.store.get_artifact(owner, cfg["mask_id"], "mask")["body"]
            return self._research(db, cfg, mask), "research"
        if op == "sensitivity":
            distances = sorted({max(.5, min(10, cfg["distance_km"]*factor)) for factor in (.5, 1, 2)})
            gaps = sorted({max(0, min(7, cfg["gap_days"]+offset)) for offset in (-1, 0, 1)})
            outputs = []
            for distance in distances:
                for gap in gaps:
                    if cancel.is_set() or time.monotonic() > deadline:
                        raise InterruptedError("Sensitivity investigation stopped.")
                    result = self._research(db, {**cfg, "distance_km": distance, "gap_days": gap})
                    outputs.append({"distance_km": distance, "gap_days": gap, "count": result["candidates"]["count"], "report_id": result["report_id"], "groups": [{"id": g["id"], "cell_days": g["cell_days"], "detection_ids": g["detection_ids"]} for g in result["candidates"]["groups"]]})
            return {"configurations": outputs, "note": "Group identity is result-specific. Compare memberships and mergers, not group labels alone. Connected detections are not confirmed incidents."}, "research"
        if op == "validation":
            from ..validity import report as validity_report
            if cfg.get("case") not in {"park-2024", "grove-2025"}:
                raise ValueError("Native validity evidence is available for Park and Grove. No gate was inferred for this study.")
            return validity_report(db, case_id=cfg["case"], selected_date=cfg.get("day") or None), "validation"
        if op in {"replay", "persistence", "missingness", "compare"}:
            bundle = self._replay(db, cfg)
            if op == "replay":
                return bundle, "replay"
            frames = bundle["frames"]
            if op == "missingness":
                days=[{"date": f["date_utc"], "products": f["products"]} for f in frames]
                summaries={}
                for source in SOURCES:
                    incomplete=[d['date'] for d in days if d['products'][source]['state']!='complete_export']
                    empty=[d['date'] for d in days if d['products'][source]['detections']==0]
                    summaries[source]={'incomplete_export_days':len(incomplete),'incomplete_export_dates':', '.join(incomplete) or 'None in this study',
                        'no_imported_record_days':len(empty),'no_imported_record_dates':', '.join(empty) or 'None in this study',
                        'imported_records':sum(d['products'][source]['detections'] for d in days)}
                notices=[n for n in self._notices() if n['start_utc'][:10]<=cfg['end'] and n['end_utc'][:10]>=cfg['start']]
                return {"days": days, "summary":summaries,"notes": bundle["case"]["notes"], "availability_notices": notices, "note": "No imported records and incomplete exports are different states. A complete export request does not establish clear satellite coverage or no fire. Only notices intersecting this study are shown."}, "replay"
            if op == "persistence":
                cells = {}
                for frame in frames:
                    if cfg["day"] and frame["date_utc"] > cfg["day"]:
                        continue
                    for cell in frame["cells"]:
                        if cfg["source"] != "joint" and cfg["source"] not in cell["sources"]:
                            continue
                        key = f'{cell["grid_x"]},{cell["grid_y"]}'
                        entry = cells.setdefault(key, {"cell_id": key, "grid_x": cell["grid_x"], "grid_y": cell["grid_y"], "longitude": cell["longitude"], "latitude": cell["latitude"], "ring": cell["ring"], "sources":[], "dates": []})
                        entry["sources"]=sorted(set(entry["sources"])|set(cell["sources"]))
                        entry["dates"].append(frame["date_utc"])
                for cell in cells.values():
                    cell["observed_days"] = len(cell["dates"])
                return {"cells": sorted(cells.values(), key=lambda c: (-c["observed_days"], c["cell_id"])), "total_cells": len(cells), "source": cfg["source"], "note": "Distinct observed UTC dates; absence on another date does not establish extinction."}, "replay"
            first = args.get("first", cfg["day"] or cfg["start"])
            second = args.get("second", cfg["end"])
            by_date = {f["date_utc"]: f for f in frames}
            if first not in by_date or second not in by_date:
                raise ValueError("Both comparison dates must belong to the selected study.")
            def cells(frame):
                return {f'{c["grid_x"]},{c["grid_y"]}': c for c in frame["cells"] if cfg["source"] == "joint" or cfg["source"] in c["sources"]}
            a, b = cells(by_date[first]), cells(by_date[second])
            return {"first": by_date[first], "second": by_date[second], "newly_observed": [b[k] for k in sorted(b.keys()-a.keys())], "repeated": [b[k] for k in sorted(b.keys() & a.keys())], "not_observed_again": [a[k] for k in sorted(a.keys()-b.keys())], "counts": {"first_cells": len(a), "second_cells": len(b), "newly_observed": len(b.keys()-a.keys()), "repeated": len(b.keys() & a.keys()), "not_observed_again": len(a.keys()-b.keys())}, "note": "This describes observation distribution, not physical spread or extinguishment. Compare exact values, not frame-relative brightness."}, "replay"
        raise ValueError("Operation not implemented.")

    def archive_search(self, db, cfg, args):
        """Find real historical observation windows without inventing incidents."""
        from calendar import monthrange
        first, last = args.get("first_year", 2006), args.get("last_year", date.today().year)
        if type(first) is not int or type(last) is not int or not 2000 <= first <= last <= 2100 or last-first > 25:
            raise ValueError("Choose an ordered archive search range of at most 26 years.")
        query = args.get("query", "")
        if not isinstance(query, str) or len(query) > 120:
            raise ValueError("Archive search text must be at most 120 characters.")
        sources = SOURCES if cfg["source"] == "joint" else (cfg["source"],)
        w, s, e, n = cfg["bbox"]
        rows = db.execute("""
            SELECT substr(o.acquisition_utc,1,10) AS day, o.source_id, COUNT(*) AS records
            FROM observations o JOIN batches b ON b.id=o.batch_id
            WHERE b.demo=0 AND o.processing_level='SP'
              AND o.source_id IN ("""+",".join("?" for _ in sources)+""")
              AND o.acquisition_utc>=? AND o.acquisition_utc<?
              AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=?
            GROUP BY day,o.source_id ORDER BY day
        """, (*sources, f"{first}-01-01", f"{last+1}-01-01", w, e, s, n)).fetchall()
        windows = {}
        for row in rows:
            month = row["day"][:7]
            window = windows.setdefault(month, {"month": month, "sources": {s: 0 for s in SOURCES}, "days": {}, "first_detection": row["day"], "last_detection": row["day"]})
            window["sources"][row["source_id"]] += row["records"]
            window["days"][row["day"]] = window["days"].get(row["day"], 0)+row["records"]
            window["last_detection"] = row["day"]
        output = []
        for month, window in windows.items():
            year, number = map(int, month.split("-"))
            peak = max(window["days"], key=lambda day: (window["days"][day], day))
            output.append({"month": month, "start": month+"-01", "end": f"{month}-{monthrange(year, number)[1]:02}", "bbox": cfg["bbox"], "imported_records": sum(window["sources"].values()), "modis_records": window["sources"]["MODIS_SP"], "viirs_records": window["sources"]["VIIRS_SNPP_SP"], "detected_days": len(window["days"]), "peak_day": peak, "peak_day_records": window["days"][peak], "first_detection": window["first_detection"], "last_detection": window["last_detection"]})
        named = [{"id": k, **{n: v[n] for n in ("title", "start", "end", "bbox", "incident")}} for k, v in CASES.items() if not query or query.lower() in (k+" "+v["title"]).lower()]
        return {"query": query, "bbox": cfg["bbox"], "first_year": first, "last_year": last, "source": cfg["source"], "named_studies": named, "windows": sorted(output, key=lambda x: (-x["imported_records"], x["month"])), "total_windows": len(output), "total_imported_records": sum(x["imported_records"] for x in output), "note": "Monthly windows contain imported thermal detections before replay filtering and deduplication; they are not confirmed wildfire incidents. The name search filters the incident catalog only. Historical windows use the displayed bbox, year range and sensor selection. Missing windows do not establish no fire."}

    def _notices(self):
        from ..availability import notices
        return [{k:v for k,v in n.items() if not k.startswith("_")} for n in notices()]

    def observations(self, db, cfg, args):
        limit = int(args.get("limit", 100))
        if not 1 <= limit <= 200:
            raise ValueError("Observation pages contain 1–200 rows.")
        sources = SERIES[cfg["series"]]
        stop = (date.fromisoformat(cfg["end"])+timedelta(days=1)).isoformat()
        where = "b.demo=0 AND o.source_id IN ("+",".join("?" for _ in sources)+") AND o.acquisition_utc>=? AND o.acquisition_utc<? AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=?"
        w,s,e,n = cfg["bbox"]
        params = (*sources, cfg["start"], stop, w,e,s,n)
        polygon = args.get("polygon")
        if polygon is not None:
            if not isinstance(polygon, list) or not 4 <= len(polygon) <= 100 or polygon[0] != polygon[-1]:
                raise ValueError("Selection polygon must be closed and contain 4–100 coordinates.")
            for point in polygon:
                if not isinstance(point,list) or len(point)!=2 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in point) or not w<=point[0]<=e or not s<=point[1]<=n:
                    raise ValueError("Selection polygon must lie inside the selected study area.")
        total = db.execute("SELECT COUNT(*) FROM observations o JOIN batches b ON b.id=o.batch_id WHERE "+where, params).fetchone()[0]
        fields = "o.detection_id,o.source_id,o.platform,o.product_version,o.acquisition_utc,o.lon,o.lat,o.grid_x,o.grid_y,o.frp_raw,o.confidence_raw,o.source_uri,b.file_sha256"
        if polygon:
            if total > 10000:
                raise ValueError("Polygon investigation exceeds 10,000 records. Narrow the bbox first.")
            rows = [dict(r) for r in db.execute("SELECT "+fields+" FROM observations o JOIN batches b ON b.id=o.batch_id WHERE "+where+" ORDER BY o.acquisition_utc,o.detection_id", params)]
            from .geometry import contains
            rows = [r for r in rows if contains(polygon,r["lon"],r["lat"])]
            selected_total=len(rows)
            cursor=args.get('cursor')
            if cursor:
                if not isinstance(cursor,list) or len(cursor)!=2 or not all(isinstance(v,str) for v in cursor):raise ValueError('Invalid observation cursor.')
                rows=[r for r in rows if (r['acquisition_utc'],r['detection_id'])>tuple(cursor)]
            more=len(rows)>limit
            selected=rows[:limit]
            return {"total": selected_total, "records": selected, "returned": len(selected), "truncated": more, "selection": "Detection centroid inside or on polygon boundary", "polygon": polygon, "next_cursor": [selected[-1]['acquisition_utc'],selected[-1]['detection_id']] if more else None, "note": "Polygon observations do not establish a coverage denominator."}
        cursor = args.get("cursor")
        extra, pagination = "", ()
        if cursor:
            if not isinstance(cursor,list) or len(cursor)!=2 or not all(isinstance(v,str) and len(v)<150 for v in cursor):
                raise ValueError("Invalid observation cursor.")
            extra = " AND (o.acquisition_utc>? OR (o.acquisition_utc=? AND o.detection_id>?))"
            pagination = (cursor[0],cursor[0],cursor[1])
        rows = [dict(r) for r in db.execute("SELECT "+fields+" FROM observations o JOIN batches b ON b.id=o.batch_id WHERE "+where+extra+" ORDER BY o.acquisition_utc,o.detection_id LIMIT ?", (*params,*pagination,limit+1))]
        more = len(rows)>limit
        rows=rows[:limit]
        return {"total": total, "records": rows, "returned": len(rows), "truncated": more, "next_cursor": [rows[-1]["acquisition_utc"],rows[-1]["detection_id"]] if more else None, "note": "Full matching original-record count; table is paginated. Replay uses a different deduplication/eligibility method."}
