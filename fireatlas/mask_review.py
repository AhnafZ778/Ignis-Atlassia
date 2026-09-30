"""Create and validate the human review record for native mask samples.

The native-mask processor creates a deterministic queue of source pixels.  This
module gives a reviewer a small, hash-bound JSON record to fill after opening
the original NASA files.  It never infers a review from the processor output:
every sample needs an explicit outcome and the independent sign-off is an
explicit human attestation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

SCHEMA = "fireatlas-native-mask-review-v1"
OUTCOMES = {"agree", "disagree", "unresolved"}
REQUIRED_SAMPLES = 30


def _key(sample: dict) -> tuple[str, int, int]:
    try:
        return str(sample["producer_id"]), int(sample["line"]), int(sample["sample"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Each review sample needs producer_id, line and sample") from error


def sample_queue(evidence: dict, limit: int = REQUIRED_SAMPLES) -> list[dict]:
    """Return the same deterministic, stratified queue used by the evidence report."""
    records = {str(item["producer_id"]): item for item in evidence.get("inventory", [])}
    strata: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for pixel in evidence.get("pixels", []):
        producer = str(pixel.get("producer_id", ""))
        if producer not in records:
            raise ValueError(f"Native sample references unknown granule: {producer}")
        strata[(records[producer]["source_id"], int(pixel["mask_class"]))].append(dict(pixel))
    for bucket in strata.values():
        bucket.sort(key=lambda item: hashlib.sha256(
            f"{item['producer_id']}:{item['line']}:{item['sample']}".encode()
        ).hexdigest())
    samples: list[dict] = []
    while len(samples) < limit and any(strata.values()):
        for key in sorted(strata):
            if strata[key] and len(samples) < limit:
                samples.append(strata[key].pop())
    return samples


def expected_hashes(evidence: dict) -> dict[str, dict[str, str]]:
    """Return hashes for processed native inputs, in stable JSON form."""
    result = {}
    for item in evidence.get("inventory", []):
        if item.get("status") != "processed":
            continue
        result[str(item["producer_id"])] = {
            "file_sha256": item.get("file_sha256"),
            "geo_sha256": item.get("geo_sha256"),
        }
    return dict(sorted(result.items()))


def make_template(case_id: str, evidence: dict) -> dict:
    """Build a review form with immutable expected sample context."""
    queue = sample_queue(evidence)
    return {
        "schema": SCHEMA,
        "case_id": case_id,
        "reviewer": {
            "name": "",
            "affiliation": "",
            "role": "independent scientific reviewer",
            "independent": False,
            "reviewed_utc": "",
        },
        "input_hashes": expected_hashes(evidence),
        "interpretation": "",
        "samples": [
            {
                "producer_id": item["producer_id"],
                "line": item["line"],
                "sample": item["sample"],
                "expected_mask_class": item["mask_class"],
                "expected_lat": item["lat"],
                "expected_lon": item["lon"],
                "expected_grid_x": item["grid_x"],
                "expected_grid_y": item["grid_y"],
                "outcome": "",
                "observed_mask_class": None,
                "observed_lat": None,
                "observed_lon": None,
                "observed_grid_x": None,
                "observed_grid_y": None,
                "notes": "",
            }
            for item in queue
        ],
    }


def validate_review(review: dict, evidence: dict) -> dict:
    """Validate a completed review and return the report-safe summary.

    Validation is deliberately strict.  A disagreement is retained as evidence
    and does not invalidate the record; an unresolved sample keeps completion
    pending.  No field is allowed to change the expected native values.
    """
    if review.get("schema") != SCHEMA:
        raise ValueError("Review schema is not fireatlas-native-mask-review-v1")
    case_id = review.get("case_id")
    reviewer = review.get("reviewer")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("Review case_id is required")
    if case_id != evidence.get("case_id"):
        raise ValueError("Review case_id does not match the native evidence")
    if not isinstance(reviewer, dict):
        raise ValueError("Review reviewer metadata is required")
    for field in ("name", "affiliation", "role", "reviewed_utc"):
        if not str(reviewer.get(field, "")).strip():
            raise ValueError(f"Reviewer field is required: {field}")
    if not isinstance(reviewer.get("independent"), bool):
        raise ValueError("Reviewer independent must be true or false")
    try:
        datetime.fromisoformat(str(reviewer["reviewed_utc"]).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("reviewed_utc must be an ISO-8601 timestamp") from error
    interpretation = str(review.get("interpretation", "")).strip()
    if not interpretation:
        raise ValueError("Reviewer interpretation is required")

    expected = expected_hashes(evidence)
    for producer, hashes in expected.items():
        if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
               for value in hashes.values()):
            raise ValueError(f"Processed native input has incomplete hashes: {producer}")
    if review.get("input_hashes") != expected:
        raise ValueError("Review input hashes do not match the processed native files")

    queue = sample_queue(evidence)
    if len(queue) < REQUIRED_SAMPLES:
        raise ValueError(f"Only {len(queue)} native review samples are available; {REQUIRED_SAMPLES} are required")
    expected_by_key = {_key(item): item for item in queue}
    supplied = review.get("samples")
    if not isinstance(supplied, list) or len(supplied) != len(queue):
        raise ValueError(f"Review must contain exactly {len(queue)} sample records")
    seen = set()
    normalized = []
    disagreements = 0
    for item in supplied:
        key = _key(item)
        if key in seen:
            raise ValueError(f"Duplicate review sample: {key[0]}:{key[1]}:{key[2]}")
        seen.add(key)
        source = expected_by_key.get(key)
        if source is None:
            raise ValueError(f"Review sample is not in the deterministic queue: {key[0]}:{key[1]}:{key[2]}")
        immutable = {"expected_mask_class": "mask_class", "expected_lat": "lat",
                     "expected_lon": "lon", "expected_grid_x": "grid_x",
                     "expected_grid_y": "grid_y"}
        for field, source_field in immutable.items():
            if field in item and item[field] != source[source_field]:
                raise ValueError(f"Review changed immutable field: {field}")
        outcome = str(item.get("outcome", "")).strip().lower()
        if outcome not in OUTCOMES:
            raise ValueError(f"Invalid outcome for {key[0]}:{key[1]}:{key[2]}")
        observed = item.get("observed_mask_class")
        if isinstance(observed, bool) or not isinstance(observed, int) or not 0 <= observed <= 9:
            raise ValueError(f"Observed native class must be an integer 0–9 for {key[0]}:{key[1]}:{key[2]}")
        for field in ("observed_lat", "observed_lon"):
            value = item.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"Observed coordinate is required for {key[0]}:{key[1]}:{key[2]}: {field}")
        for field in ("observed_grid_x", "observed_grid_y"):
            value = item.get(field)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"Observed grid assignment is required for {key[0]}:{key[1]}:{key[2]}: {field}")
        notes = str(item.get("notes", "")).strip()
        if outcome in {"disagree", "unresolved"} and not notes:
            raise ValueError(f"Notes are required for {outcome} sample {key[0]}:{key[1]}:{key[2]}")
        if outcome == "disagree":
            disagreements += 1
        normalized.append({
            "producer_id": key[0], "line": key[1], "sample": key[2],
            "expected_mask_class": source["mask_class"],
            "observed_mask_class": observed,
            "observed_lat": item["observed_lat"], "observed_lon": item["observed_lon"],
            "observed_grid_x": item["observed_grid_x"], "observed_grid_y": item["observed_grid_y"],
            "outcome": outcome, "notes": notes,
        })
    if seen != set(expected_by_key):
        raise ValueError("Review does not cover every deterministic sample")
    return {
        "required_samples": REQUIRED_SAMPLES,
        "reviewed_samples": len(normalized),
        "status": "complete" if all(item["outcome"] != "unresolved" for item in normalized)
                   else "pending-independent-human-review",
        "independent_signoff": bool(reviewer["independent"]),
        "disagreements": disagreements,
        "reviewer": {
            "name": str(reviewer["name"]).strip(),
            "affiliation": str(reviewer["affiliation"]).strip(),
            "role": str(reviewer["role"]).strip(),
            "independent": bool(reviewer["independent"]),
            "reviewed_utc": str(reviewer["reviewed_utc"]).strip(),
        },
        "input_hashes": expected,
        "interpretation": interpretation,
        "samples": normalized,
    }


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read review JSON: {path}") from error
    if not isinstance(value, dict):
        raise ValueError("Review JSON must contain an object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or validate a native-mask human review record")
    parser.add_argument("--case", choices=("park-2024", "grove-2025"), required=True)
    parser.add_argument("--store", type=Path, default=Path("data/validity_masks.sqlite3"))
    parser.add_argument("--template", type=Path, help="write a blank review template to this path")
    parser.add_argument("--review", type=Path, help="validate a completed review JSON")
    parser.add_argument("--install", action="store_true", help="copy a validated review into the local ignored review store")
    args = parser.parse_args()
    if bool(args.template) == bool(args.review):
        parser.error("choose exactly one of --template or --review")
    from .masks import load_evidence
    evidence = load_evidence(args.case, str(args.store), Path(args.store).stat().st_mtime_ns) if args.store.exists() else {
        "inventory": [], "pixels": []
    }
    if args.template:
        if args.template.exists():
            parser.error(f"template already exists: {args.template} (choose a new path)")
        args.template.parent.mkdir(parents=True, exist_ok=True)
        args.template.write_text(json.dumps(make_template(args.case, evidence), indent=2, sort_keys=True) + "\n")
        print(json.dumps({"case_id": args.case, "template": str(args.template),
                          "samples": len(sample_queue(evidence))}, indent=2))
        return
    review = load_json(args.review)
    summary = validate_review(review, evidence)
    if args.install:
        destination = args.store.parent / "validity_mask_reviews" / f"{args.case}.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(review, indent=2, sort_keys=True) + "\n")
        summary["installed"] = str(destination)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
