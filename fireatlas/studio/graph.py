"""Pure board rules: card validation, connection compatibility and one-pass context propagation.

These functions mirror ``studio-app/src/lib/graph.ts``; both are exercised against the shared
vectors in ``studio-app/test-vectors/graph.json`` so the browser and server cannot drift.
"""
from __future__ import annotations

import json
import math
import re

from .errors import Conflict, LimitExceeded, StudioError

MAX_CARDS = 100
MAX_CONNECTIONS = 300
CARD_TYPES = ("map", "chart", "timeline", "calendar", "finding", "observation", "table", "source-evidence",
              "method-note", "note-question", "chapter-frame", "image", "quote", "text")
CARD_KEYS = {"id", "type", "title", "binding", "snapshot_id", "display", "provenance", "transform", "follow",
             "follow_card_id", "pinned_study", "text", "asset_id", "locked"}
CONNECTION_KINDS = ("context", "scale", "compare")
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
FAMILY = {"replay": "daily", "persistence": "daily", "compare": "daily", "missingness": "daily",
          "calendar": "daily", "harmonized": "daily", "observations": "daily",
          "research": "research", "exposure": "research", "sensitivity": "research"}
UI_KEYS = {"origin_route", "tab", "section", "return_destination", "scope", "view", "split", "geometry",
           "calendar_metric", "analysis_month", "method_id", "unit", "release_id", "result_sha256",
           "pending_action", "fragment", "origin"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def check_id(value, what="identifier"):
    if not isinstance(value, str) or not ID_PATTERN.match(value):
        raise StudioError(f"A {what} uses 1–64 letters, digits, underscores or hyphens.", code="invalid-id")
    return value


def finite(value, low, high, what):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise StudioError(f"{what} must be a finite number from {low} to {high}.", code="invalid-transform")
    return float(value)


def small_json(value, what, limit=8192):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise StudioError(f"{what} must be an object.", code="invalid-card")
    if len(canonical(value)) > limit:
        raise LimitExceeded(f"{what} is larger than {limit} bytes.", code="card-too-large")
    return value


def clean_transform(value):
    value = value or {}
    if not isinstance(value, dict) or set(value) - {"x", "y", "w", "h", "rotation"}:
        raise StudioError("Card transform accepts x, y, w, h and rotation only.", code="invalid-transform")
    return {"x": finite(value.get("x", 0), -100000, 100000, "x"), "y": finite(value.get("y", 0), -100000, 100000, "y"),
            "w": finite(value.get("w", 360), 40, 4000, "w"), "h": finite(value.get("h", 240), 40, 4000, "h"),
            **({"rotation": finite(value["rotation"], -360, 360, "rotation")} if "rotation" in value else {})}


def clean_study(value):
    """Normalize a board study with the same validator used by Investigate and the assistant."""
    from ..assistant.contracts import normalize_context
    if value in (None, {}):
        return {}
    if not isinstance(value, dict):
        raise StudioError("A study must be an object.", code="invalid-study")
    ui = value.get("ui") or {}
    if not isinstance(ui, dict) or set(ui) - UI_KEYS:
        raise StudioError("Unknown study navigation field.", code="invalid-study")
    for item in ui.values():
        if not isinstance(item, (str, int, float, bool, type(None))) or (isinstance(item, str) and len(item) > 4000):
            raise StudioError("Study navigation values must be short scalars.", code="invalid-study")
    try:
        context = normalize_context(value.get("context", {k: v for k, v in value.items() if k != "ui"}))
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        raise StudioError(str(error) or "Invalid study context.", code="invalid-study") from None
    return {"context": context, "ui": dict(ui)}


def clean_card(card, existing=None):
    if not isinstance(card, dict):
        raise StudioError("A card must be an object.", code="invalid-card")
    unknown = set(card) - CARD_KEYS
    if unknown:
        raise StudioError("Unknown card field: " + ", ".join(sorted(unknown)), code="invalid-card")
    merged = {**(existing or {}), **card}
    check_id(merged.get("id"), "card ID")
    if merged.get("type") not in CARD_TYPES:
        raise StudioError("Choose a supported card type.", code="invalid-card")
    title = merged.get("title", "")
    text = merged.get("text", "")
    if not isinstance(title, str) or len(title) > 120 or not isinstance(text, str) or len(text) > 4000:
        raise StudioError("Card title is limited to 120 characters and text to 4,000.", code="invalid-card")
    binding = small_json(merged.get("binding"), "Card binding", 6000)
    if binding is not None:
        from ..assistant.science import OPERATIONS
        if binding.get("operation") not in OPERATIONS:
            raise StudioError("A card binding needs a supported scientific operation.", code="invalid-binding")
        if not isinstance(binding.get("arguments", {}), dict) or not isinstance(binding.get("context", {}), dict):
            raise StudioError("Binding arguments and context must be objects.", code="invalid-binding")
        path = binding.get("path")
        if path is not None and (not isinstance(path, str) or len(path) > 300 or not path.startswith("/")):
            raise StudioError("A binding path is a JSON pointer beginning with /.", code="invalid-binding")
    follow = merged.get("follow", "board")
    if follow not in ("board", "pinned", "selected"):
        raise StudioError("A card follows the board, a pinned study, or another selected card.", code="invalid-card")
    if follow == "pinned" and not merged.get("pinned_study"):
        raise StudioError("A pinned card needs its own study.", code="invalid-card")
    follow_card_id = merged.get("follow_card_id")
    if follow == "selected":
        check_id(follow_card_id, "source card ID")
    elif follow_card_id is not None:
        check_id(follow_card_id, "source card ID")
    snapshot_id = merged.get("snapshot_id")
    if snapshot_id is not None:
        check_id(snapshot_id, "snapshot ID")
    asset_id = merged.get("asset_id")
    if asset_id is not None:
        check_id(asset_id, "asset ID")
    locked = merged.get("locked", False)
    if not isinstance(locked, bool):
        raise StudioError("A card lock must be boolean.", code="invalid-card")
    return {"id": merged["id"], "type": merged["type"], "title": title, "text": text, "binding": binding,
            "snapshot_id": snapshot_id, "asset_id": asset_id, "display": small_json(merged.get("display"), "Card display") or {},
            "provenance": small_json(merged.get("provenance"), "Card provenance") or {},
            "transform": clean_transform(merged.get("transform")), "follow": follow, "follow_card_id": follow_card_id,
            "locked": locked, "pinned_study": clean_study(merged["pinned_study"]) if merged.get("pinned_study") else None}


def clean_connection(value):
    if not isinstance(value, dict) or set(value) - {"id", "source", "target", "kind"}:
        raise StudioError("A connection has id, source, target and kind.", code="invalid-connection")
    kind = value.get("kind", "context")
    if kind not in CONNECTION_KINDS:
        raise StudioError("Unsupported connection kind.", code="invalid-connection")
    return {"id": check_id(value.get("id"), "connection ID"), "source": check_id(value.get("source"), "card ID"),
            "target": check_id(value.get("target"), "card ID"), "kind": kind}


def empty_state(title="Untitled board", study=None):
    return {"schema": "fireatlas-studio-document-v1", "title": title, "study": clean_study(study), "cards": {},
            "order": [], "connections": {}, "groups": {}, "viewport": {"x": 0, "y": 0, "zoom": 1},
            "story_id": None, "workflow_id": None}


def upgrade_state(state):
    """Add presentation defaults to older documents without rewriting frozen revisions."""
    state.setdefault("groups", {})
    state.setdefault("viewport", {"x": 0, "y": 0, "zoom": 1})
    return state


def clean_viewport(value):
    if not isinstance(value, dict) or set(value) != {"x", "y", "zoom"}:
        raise StudioError("A saved viewport has x, y and zoom.", code="invalid-viewport")
    return {"x": finite(value["x"], -100000, 100000, "viewport x"),
            "y": finite(value["y"], -100000, 100000, "viewport y"),
            "zoom": finite(value["zoom"], 0.1, 4, "viewport zoom")}


def clean_group(value):
    if not isinstance(value, dict) or set(value) != {"id", "title", "card_ids"}:
        raise StudioError("A group has id, title and card_ids.", code="invalid-group")
    ids, title = value["card_ids"], value["title"]
    if not isinstance(title, str) or not 1 <= len(title) <= 120:
        raise StudioError("A group title has 1–120 characters.", code="invalid-group")
    if not isinstance(ids, list) or not 2 <= len(ids) <= MAX_CARDS or any(not isinstance(cid, str) for cid in ids) or len(set(ids)) != len(ids):
        raise StudioError("A group needs 2–100 different card IDs.", code="invalid-group")
    return {"id": check_id(value["id"], "group ID"), "title": title,
            "card_ids": [check_id(cid, "card ID") for cid in ids]}


def validate_groups(state):
    members = set()
    for group in state.get("groups", {}).values():
        clean_group(group)
        ids = set(group["card_ids"])
        if ids - state["cards"].keys() or ids & members:
            raise StudioError("Groups need existing cards; each card belongs to at most one group.", code="invalid-group")
        members.update(ids)


def effective_study(card, state, _seen=None):
    _seen = set() if _seen is None else _seen
    identifier = card.get("id")
    if identifier and identifier in _seen:
        return state.get("study") or {}
    if identifier:
        _seen = {*_seen, identifier}
    if card.get("follow") == "pinned":
        return card.get("pinned_study") or {}
    if card.get("follow") == "selected" and card.get("follow_card_id") in state.get("cards", {}):
        source = state["cards"][card["follow_card_id"]]
        return effective_study(source, state, _seen)
    return state.get("study") or {}


def validate_follow(cards):
    """Follow links are explicit dependencies, not a way to bypass cycle checks."""
    for identifier, card in cards.items():
        seen = {identifier}
        cursor = card
        while cursor.get("follow") == "selected":
            source = cursor.get("follow_card_id")
            if source not in cards:
                raise StudioError("A following card needs an existing source card.", code="invalid-card")
            if source in seen:
                raise StudioError("Card selection dependencies must not form a cycle.", code="cycle")
            seen.add(source)
            cursor = cards[source]


def _interval(study):
    context = (study or {}).get("context") or {}
    return context.get("start"), context.get("end")


def compatibility(source, target, kind, state, snapshots=None):
    """Return a list of human-readable reasons a connection is incompatible (empty means valid)."""
    snapshots = snapshots or {}
    reasons = []
    a, b = effective_study(source, state), effective_study(target, state)
    ca, cb = (a.get("context") or {}), (b.get("context") or {})
    if ca and cb:
        if ca.get("region") != cb.get("region"):
            reasons.append("Regions differ.")
        if ca.get("bbox") != cb.get("bbox"):
            reasons.append("Study bounding boxes differ.")
        (a0, a1), (b0, b1) = _interval(a), _interval(b)
        if a0 and b0 and (a1 < b0 or b1 < a0):
            reasons.append("UTC date ranges do not overlap.")
    sa, sb = snapshots.get(source.get("snapshot_id")), snapshots.get(target.get("snapshot_id"))
    if sa and sb and sa["release_id"] != sb["release_id"]:
        reasons.append("Evidence comes from different releases.")
    opa = (source.get("binding") or {}).get("operation")
    opb = (target.get("binding") or {}).get("operation")
    if opa and opb:
        if FAMILY.get(opa) != FAMILY.get(opb):
            reasons.append("Operations belong to incompatible scientific families.")
        if kind == "scale" and opa != opb:
            reasons.append("A shared scale needs the same operation.")
    if kind in ("scale", "compare") and sa and sb and sa["unit"] != sb["unit"]:
        reasons.append("Units differ: " + sa["unit"] + " and " + sb["unit"] + ".")
    return reasons


def topological_order(cards, connections):
    """Kahn ordering. Raises ``Conflict`` when connections form a cycle."""
    indegree = {cid: 0 for cid in cards}
    outgoing = {cid: [] for cid in cards}
    for item in connections.values():
        if item["source"] not in cards or item["target"] not in cards:
            raise StudioError("A connection refers to a missing card.", code="invalid-connection")
        outgoing[item["source"]].append(item["target"])
        indegree[item["target"]] += 1
    ready = sorted(cid for cid, count in indegree.items() if count == 0)
    order = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for target in sorted(outgoing[current]):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    if len(order) != len(cards):
        raise Conflict("Card connections must not form a cycle.", code="cycle")
    return order


def propagate(state, origin, selection, snapshots=None):
    """One topological pass of a selection from ``origin``; incompatible links are reported, never applied."""
    cards, connections = state["cards"], state["connections"]
    order = topological_order(cards, connections)
    reached, skipped = {origin: selection}, []
    for cid in order:
        if cid not in reached:
            continue
        for item in sorted((c for c in connections.values() if c["source"] == cid), key=lambda c: c["id"]):
            reasons = compatibility(cards[cid], cards[item["target"]], item["kind"], state, snapshots)
            if reasons:
                skipped.append({"connection": item["id"], "reasons": reasons})
            elif item["target"] not in reached:
                reached[item["target"]] = selection
    return {"reached": [cid for cid in order if cid in reached], "skipped": skipped}
