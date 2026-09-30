"""Check that the native-mask ledger and displayed validation gates agree.

This is a consistency check, not a scientific review.  It deliberately accepts
incomplete cases and reports their pending gates instead of turning missing
inputs into a pass or a no-fire result.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from fireatlas.granules import load as load_granule_inventory
from fireatlas.validity import report

ROOT = Path(__file__).resolve().parent.parent


def case_summary(db: sqlite3.Connection, case_id: str) -> dict:
    result = report(db, case_id=case_id)
    native = result.get("native_masks") or {}
    reconciliation = native.get("reconciliation") or {}
    paired = native.get("paired_observations") or {}
    gates = result.get("validation_gates") or []
    return {
        "case_id": case_id,
        "native_status": native.get("status"),
        "processed_fire_granules": native.get("processed_fire_granules", 0),
        "expected_fire_granules": native.get("expected_fire_granules", 0),
        "clipped_native_pixels": native.get("clipped_native_pixels", 0),
        "firms_rows_matched": reconciliation.get("matched", 0),
        "firms_rows_total": reconciliation.get("total_firms_pixels", 0),
        "reconciliation_fraction": reconciliation.get("fraction"),
        "reconciliation_passes_target": reconciliation.get("passes_target", False),
        "paired_observation_sample_size": paired.get("sample_size", 0),
        "validation_gates": [
            {"id": gate.get("id"), "status": gate.get("status"),
             "actual": gate.get("actual"), "required": gate.get("required")}
            for gate in gates
        ],
    }


def validate(summary: list[dict], inventory: dict) -> list[str]:
    errors: list[str] = []
    interpretation = str(inventory.get("interpretation", ""))
    if "not been downloaded" not in interpretation:
        errors.append("CMR inventory no longer distinguishes metadata from native downloads")
    for item in summary:
        processed = item["processed_fire_granules"]
        expected = item["expected_fire_granules"]
        matched = item["firms_rows_matched"]
        total = item["firms_rows_total"]
        if processed < 0 or expected < 0 or processed > expected:
            errors.append(f"{item['case_id']}: native granule count is outside 0..expected")
        if matched < 0 or total < 0 or matched > total:
            errors.append(f"{item['case_id']}: reconciliation count is outside 0..total")
        expected_pass = bool(total) and matched / total >= 0.98
        if item["reconciliation_passes_target"] != expected_pass:
            errors.append(f"{item['case_id']}: reconciliation gate does not match its counts")
        gate_ids = {gate["id"] for gate in item["validation_gates"]}
        if gate_ids != {"inventory", "reconciliation", "samples", "review"}:
            errors.append(f"{item['case_id']}: validation-gate IDs are incomplete")
        if processed == 0 and item["reconciliation_passes_target"]:
            errors.append(f"{item['case_id']}: unloaded native masks cannot pass reconciliation")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "fireatlas.sqlite3")
    parser.add_argument("--json", action="store_true", help="print only the JSON report")
    args = parser.parse_args()
    if not args.db.is_file():
        raise SystemExit(f"database not found: {args.db}")
    with sqlite3.connect(args.db) as db:
        db.row_factory = sqlite3.Row
        cases = [case_summary(db, case_id) for case_id in ("grove-2025", "park-2024")]
    payload = {"schema": "fireatlas-native-mask-status-check-v1", "cases": cases}
    errors = validate(cases, load_granule_inventory())
    payload["errors"] = errors
    payload["status"] = "passed" if not errors else "failed"
    print(json.dumps(payload, indent=2, sort_keys=True))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
