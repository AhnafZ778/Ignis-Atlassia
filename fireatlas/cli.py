"""Command line interface for the Phase 1 pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import SERIES, SOURCES, calendar, connect, ingest
from .fetch import FIRMS_SOURCES, fetch_month
from .research import report as research_report
from .fetch import availability
from .pilots import PilotSync
from .events import harvest as harvest_events
from .hms import harvest_month as harvest_hms_month


def main() -> None:
    parser = argparse.ArgumentParser(prog="fireatlas")
    parser.add_argument("--db", default="data/fireatlas.sqlite3", help="SQLite database path")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="create the local database")
    commands.add_parser("firms-status", help="check NASA source availability using the server credential")
    commands.add_parser("sync-pilots", help="import July 2021–2024 standard-product pilots and verify totals")
    commands.add_parser("harvest-events", help="cache recent reported wildfire events from NASA EONET")
    hms_parser = commands.add_parser("harvest-hms", help="import a complete NOAA HMS VIIRS historical month")
    hms_parser.add_argument("--month", required=True, help="finished month, YYYY-MM")
    hms_parser.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("W", "S", "E", "N"))
    hms_parser.add_argument("--directory", type=Path, default=Path("data/downloads"))
    hms_parser.add_argument("--refresh", action="store_true")
    import_parser = commands.add_parser("ingest", help="import a NASA FIRMS CSV file")
    import_parser.add_argument("csv", type=Path)
    import_parser.add_argument("--source", choices=sorted(SOURCES), required=True)
    import_parser.add_argument("--source-uri", help="non-secret source identifier (do not include API keys)")
    import_parser.add_argument("--complete-month", help="YYYY-MM; assert the CSV is a complete AOI export")
    import_parser.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"))
    view_parser = commands.add_parser("calendar", help="export a sensor-aware UTC calendar")
    view_parser.add_argument("--year", type=int, required=True)
    view_parser.add_argument("--series", choices=sorted(SERIES), default="joint")
    view_parser.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("W", "S", "E", "N"))
    view_parser.add_argument("--output", type=Path, help="write JSON to this file")
    fetch_parser = commands.add_parser("fetch-month", help="download a complete AOI month from NASA FIRMS")
    fetch_parser.add_argument("--month", required=True, help="YYYY-MM")
    fetch_parser.add_argument("--source", choices=sorted(FIRMS_SOURCES), required=True)
    fetch_parser.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("W", "S", "E", "N"))
    fetch_parser.add_argument("--directory", type=Path, default=Path("data/downloads"))
    fetch_parser.add_argument("--refresh", action="store_true")
    research_parser = commands.add_parser("research", help="export a Phase 4 exploratory study")
    research_parser.add_argument("--year", type=int, required=True)
    research_parser.add_argument("--month", type=int, required=True)
    research_parser.add_argument("--bbox", nargs=4, type=float, required=True)
    research_parser.add_argument("--as-of", help="acquisition-date cutoff, YYYY-MM-DD")
    research_parser.add_argument("--distance-km", type=float, default=2)
    research_parser.add_argument("--gap-days", type=int, default=1)
    research_parser.add_argument("--mask", type=Path, help="observation-mask JSON using fireatlas-coverage-v1")
    research_parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    db = connect(args.db)
    if args.command == "firms-status":
        result = {"sources": availability()}
    elif args.command == "sync-pilots":
        sync = PilotSync(args.db)
        sync.run()
        result = sync.status()
    elif args.command == "harvest-events":
        snapshot = harvest_events(Path(args.db).with_suffix(".events.json"))
        result = {"source": snapshot["source"], "events_cached": snapshot["count"], "fetched_utc": snapshot["fetched_utc"]}
    elif args.command == "harvest-hms":
        result = harvest_hms_month(db, month=args.month, bbox=tuple(args.bbox),
                                   directory=args.directory, refresh=args.refresh)
    elif args.command == "init":
        result = {"database": str(Path(args.db).resolve()), "initialized": True}
    elif args.command == "ingest":
        result = ingest(
            db, args.csv, args.source, source_uri=args.source_uri,
            complete_month=args.complete_month,
            bbox=tuple(args.bbox) if args.bbox else None,
        )
    elif args.command == "fetch-month":
        result = fetch_month(
            db, month=args.month, source_id=args.source, bbox=tuple(args.bbox),
            directory=args.directory, refresh=args.refresh,
        )
    elif args.command == "research":
        result = research_report(db, year=args.year, month=args.month, bbox=args.bbox,
                                 as_of=args.as_of, distance_km=args.distance_km, gap_days=args.gap_days,
                                 mask=json.loads(args.mask.read_text()) if args.mask else None)
    else:
        result = calendar(db, bbox=tuple(args.bbox), year=args.year, series=args.series)
    output = json.dumps(result, indent=2)
    if args.command in ("calendar", "research") and args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n")
        print(json.dumps({"output": str(args.output.resolve()), "year": args.year, "command": args.command}))
    else:
        print(output)
    db.close()
    if args.command == "sync-pilots" and result["sync"]["status"] != "complete":
        parser.exit(1)


if __name__ == "__main__":
    main()
