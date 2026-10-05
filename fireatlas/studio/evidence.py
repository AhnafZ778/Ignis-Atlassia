"""Evidence bindings: freeze existing scientific results into immutable, verifiable snapshots.

No calculation lives here. ``Science.call`` produces every result, and ``assistant.agent.fact`` is the
only scalar resolver, so units, methods, grids, releases and receipt hashes flow through unchanged.
"""
from __future__ import annotations

import datetime
import math
import re

from ..assistant.agent import fact, guided_answer
from ..assistant.contracts import digest, normalize_context, pointer
from .errors import StudioError

SNAPSHOT_SCHEMA = "fireatlas-studio-evidence-snapshot-v1"
MAX_FACTS = 40


def _state_of(evidence, path, label=None):
    """Resolve one fact without weakening the existing scalar contract: unknown stays unknown, never zero."""
    try:
        raw = pointer(evidence["payload"], path)
    except (KeyError, IndexError, ValueError, TypeError):
        return {"path": path, "state": "unavailable", "value": None, "unit": evidence["method"]["unit"],
                "label": label or path.rsplit("/", 1)[-1], "reason": "The path does not exist in this result."}
    if raw is None:
        return {"path": path, "state": "unknown", "value": None, "unit": evidence["method"]["unit"],
                "label": label or path.rsplit("/", 1)[-1], "reason": "The result reports this value as unknown; it is not zero."}
    try:
        card = fact(evidence, path, label)
    except ValueError as error:
        return {"path": path, "state": "unavailable", "value": None, "unit": evidence["method"]["unit"],
                "label": label or path.rsplit("/", 1)[-1], "reason": str(error)}
    # Guided results carry operation-specific units (for example replay's
    # aggregate cell-days and missingness's explicit UTC date lists). Freeze
    # and verify the same authoritative presentation contract.
    guided = next((c for c in guided_answer(evidence)['claims'] if c['path'] == path), None)
    if guided:
        card['unit'] = guided['unit']
    return {"path": path, "state": "observed", "value": card["value"], "unit": card["unit"], "label": card["label"],
            "method_id": card["method_id"]}


def default_facts(evidence):
    claims = guided_answer(evidence)["claims"]
    return [_state_of(evidence, c['path'], c['label']) for c in claims][:MAX_FACTS]


def build_snapshot(evidence, release, binding):
    """Create the immutable evidence record for one binding from a fresh ``Science.call`` result."""
    paths = binding.get("paths") or ([binding["path"]] if binding.get("path") else [])
    if len(paths) > MAX_FACTS:
        raise StudioError("A binding resolves at most 40 facts.", code="invalid-binding")
    facts = [_state_of(evidence, path, binding.get("label") if len(paths) == 1 else None) for path in paths] if paths else default_facts(evidence)
    context = evidence["context"]
    manifest = release.get("manifest", {})
    dependency = {"source_ledger": digest(manifest.get("source_ledger", [])), "export_inventory": digest(manifest.get("export_inventory", [])),
                  "schema": digest(manifest.get("schema", [])), **{f"file:{k}": v for k, v in sorted(manifest.get("supporting_files", {}).items())}}
    units = {f["unit"] for f in facts}
    unit = "mixed units (see values)" if len(units) > 1 else next(iter(units), evidence["method"]["unit"])
    snapshot = {
        "schema": SNAPSHOT_SCHEMA, "result_id": evidence["id"], "receipt_sha256": evidence["sha256"], "release_id": evidence["release_id"],
        "release_frozen": bool(evidence.get("release_frozen")), "operation": evidence["operation"], "method": evidence["method"], "unit": unit,
        "grid": evidence["grid"], "facts": facts,
        "scope": {"bbox": context["bbox"], "start": context["start"], "end": context["end"], "day": context.get("day") or None,
                  "region": context.get("region"), "case": context.get("case"), "series": context.get("series"), "source": context.get("source"),
                  "geometry": binding.get("geometry")},
        "context": context, "dependency_hashes": dependency, "limitations": evidence["limitations"],
        "captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }
    return snapshot


def scale_contract(evidence, path, mode="study"):
    """A study-fixed display domain from every value the same statistic takes across the full study.

    List indexes in ``path`` become wildcards, so selecting a day or hiding a source never changes the
    domain. Occupied cells, persistence and single-source FRP keep distinct units through ``fact``.
    """
    if mode not in ("study", "relative"):
        raise StudioError("Scale mode is study or relative.", code="invalid-scale")
    parts, cursor, pattern = path[1:].split("/"), evidence["payload"], []
    for part in parts:
        key = part.replace("~1", "/").replace("~0", "~")
        if isinstance(cursor, list):
            pattern.append("*")
            cursor = cursor[int(key)]
        else:
            pattern.append(part)
            cursor = cursor[key]
    values = []

    def walk(node, index):
        if index == len(pattern):
            if isinstance(node, (int, float)) and not isinstance(node, bool) and math.isfinite(node):
                values.append(float(node))
            return
        step = pattern[index]
        if step == "*" and isinstance(node, list):
            for child in node:
                walk(child, index + 1)
        elif isinstance(node, dict) and step in node:
            walk(node[step], index + 1)
        elif isinstance(node, dict) and step.replace("~1", "/").replace("~0", "~") in node:
            walk(node[step.replace("~1", "/").replace("~0", "~")], index + 1)

    walk(evidence["payload"], 0)
    card = fact(evidence, path)
    contract = {"mode": mode, "statistic": "/" + "/".join(pattern), "unit": card["unit"], "basis": "full applicable study",
                "observed_values": len(values), "domain": [min(0.0, min(values)), max(values)] if values else None}
    if mode == "relative":
        contract["warning"] = "brightness not comparable across dates"
    return contract


def verify_snapshot(snapshot, receipt=None):
    """Return a verification report. A tampered number fails even if every checksum was refreshed."""
    problems = []
    if snapshot.get("schema") != SNAPSHOT_SCHEMA:
        problems.append("Unsupported snapshot schema.")
    expected = digest({k: v for k, v in snapshot.items() if k != "snapshot_sha256"})
    if snapshot.get("snapshot_sha256") != expected:
        problems.append("Snapshot checksum is missing or does not match its content.")
    receipt_checked = False
    if receipt is not None:
        receipt_checked = True
        recomputed = digest({k: v for k, v in receipt.items() if k not in ("sha256", "id")})
        if recomputed != receipt.get("sha256"):
            problems.append("Stored scientific receipt does not match its hash.")
        if receipt.get("sha256") != snapshot.get("receipt_sha256"):
            problems.append("Snapshot does not refer to this receipt.")
        if receipt.get("release_id") != snapshot.get("release_id"):
            problems.append("Release identity differs from the receipt.")
        if receipt.get("method") != snapshot.get("method"):
            problems.append("Method or unit differs from the receipt.")
        full = {**receipt, "id": snapshot.get("result_id")}
        for item in snapshot.get("facts", []):
            try:
                card = _state_of(full, item["path"])
            except (ValueError, KeyError, IndexError, TypeError):
                problems.append(f"{item['path']} no longer resolves in the receipt.")
                continue
            if any(card[k] != item.get(k) for k in ("state", "value", "unit")):
                problems.append(f"{item['path']}: scientific state, value or unit differs from the receipt ({card['state']}: {card['value']} {card['unit']}).")
    return {"verified": not problems, "problems": problems, "receipt_checked": receipt_checked,
            "snapshot_sha256": snapshot.get("snapshot_sha256"), "receipt_sha256": snapshot.get("receipt_sha256")}


NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _forms(value):
    forms = set()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return forms
    forms.add(str(value))
    forms.add(f"{value:,}")
    for digits in (0, 1, 2):
        rounded = round(float(value), digits)
        forms.add(f"{rounded:.{digits}f}")
        forms.add(f"{rounded:,.{digits}f}")
    if float(value).is_integer():
        forms.update({str(int(value)), f"{int(value):,}"})
    return forms


def allowed_numbers(snapshots):
    allowed = set()
    for snapshot in snapshots:
        for item in snapshot.get("facts", []):
            if item["state"] == "observed":
                allowed |= _forms(item["value"])
                # Guided date lists are checked strings, not numeric measurements.
                # Permit their genuine UTC components in readable narration.
                if isinstance(item['value'], str):
                    for token in re.findall(r'\b\d{4}-\d{2}-\d{2}\b', item['value']):
                        try:
                            date = datetime.date.fromisoformat(token)
                        except ValueError:
                            continue
                        allowed |= {str(date.year), f'{date.month:02}', str(date.month), f'{date.day:02}', str(date.day)}
        scope = snapshot.get("scope", {})
        for key in ("start", "end", "day"):
            if scope.get(key):
                year, month, day = scope[key].split("-")
                allowed |= {year, month, str(int(month)), day, str(int(day))}
        for number in scope.get("bbox") or []:
            allowed |= _forms(number)
    return allowed


def check_narration(text, snapshots, *, resolved_fields=()):
    """Every numeral in narration must come from cited evidence. Unsupported numerals mark it unchecked."""
    allowed = allowed_numbers(snapshots)
    # Explicitly resolved metadata/date fields may contain numerals outside
    # scope endpoints. These tokens come from scalars already checked against
    # a cited receipt, never from model-provided values.
    for field in resolved_fields:
        if field.get('state') == 'observed':
            allowed.update(NUMBER.findall(str(field['value'])))
    unmatched = sorted({m.rstrip(".,") for m in NUMBER.findall(text or "") if m.rstrip(".,") not in allowed})
    return {"checked": not unmatched, "unmatched_numbers": unmatched}
