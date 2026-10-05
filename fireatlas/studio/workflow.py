"""Typed workflow graphs (at most 40 nodes) executed without model-generated code.

Nodes only select and bound existing scientific results; calculations remain in ``Science.call``.
"""
from __future__ import annotations

import threading
import time

from ..assistant.agent import fact
from ..assistant.contracts import digest, pointer
from .errors import Conflict, LimitExceeded, StudioError

MAX_NODES = 40
MAX_RECORDS = 5000
MAX_TOOL_CALLS = 8
MAX_SECONDS = 120

# type -> (input ports: {name: (accepted types, multiple)}, output type)
NODE_TYPES = {
    "operation": ({}, "result"),
    "evidence_input": ({}, "result"),
    "pick": ({"source": (("result",), False)}, "series"),
    "filter": ({"data": (("series",), False)}, "series"),
    "compare": ({"left": (("scalar",), False), "right": (("scalar",), False)}, "table"),
    "visualize": ({"data": (("series", "table", "scalar"), False)}, "visual"),
    "card_output": ({"content": (("visual", "scalar", "table", "result"), False)}, "card_draft"),
    "board_insert": ({"items": (("card_draft",), True)}, "board_result"),
    "portable_export": ({"board": (("board_result",), False)}, "export_job"),
    "export_prep": ({"items": (("card_draft",), True)}, "export_manifest"),
    "story_output": ({"items": (("card_draft",), True)}, "story_draft"),
}
DETERMINISTIC = set(NODE_TYPES) - {"board_insert", "portable_export"}
CARD_TYPES = ("map", "chart", "timeline", "calendar", "finding", "observation", "table", "source-evidence", "method-note", "note-question", "chapter-frame", "image", "quote", "text")


def templates():
    """Deterministic starter recipes; they reference existing operations and never contain code."""
    return [
        {"id": "study-to-board", "title": "Study to investigation board", "definition": {"nodes": [
            {"id": "study", "type": "operation", "label": "Load exact study replay", "params": {"operation": "replay", "arguments": {}}},
            {"id": "value", "type": "pick", "label": "Select recorded daily occupied cells", "params": {"path": "/frames/*/joint_cell_days"}, "inputs": {"source": "study"}},
            {"id": "visual", "type": "visualize", "label": "Prepare checked preview", "params": {"kind": "table"}, "inputs": {"data": "value"}},
            {"id": "card", "type": "card_output", "label": "Create evidence card", "params": {"card_type": "observation", "title": "Study evidence"}, "inputs": {"content": "visual"}}
        ]}},
        {"id": "findings-to-story", "title": "Selected findings to story and video", "definition": {"nodes": [
            {"id": "study", "type": "operation", "label": "Load exact study replay", "params": {"operation": "replay", "arguments": {}}},
            {"id": "value", "type": "pick", "label": "Select recorded daily occupied cells", "params": {"path": "/frames/*/joint_cell_days"}, "inputs": {"source": "study"}},
            {"id": "visual", "type": "visualize", "label": "Prepare story values", "params": {"kind": "bars"}, "inputs": {"data": "value"}},
            {"id": "card", "type": "card_output", "label": "Select finding", "params": {"card_type": "finding", "title": "Selected finding"}, "inputs": {"content": "visual"}},
            {"id": "story", "type": "story_output", "label": "Prepare editable six-chapter story", "params": {"title": "Checked study briefing"}, "inputs": {"items": ["card"]}},
            {"id": "export", "type": "export_prep", "label": "Prepare checked export inventory", "inputs": {"items": ["card"]}}
        ]}}
    ]


def _ids(inputs, port):
    value = inputs.get(port)
    return value if isinstance(value, list) else ([value] if value else [])


def produced_type(node):
    """A pick yields a scalar for one concrete path and a series when its path uses a wildcard."""
    if node["type"] == "pick":
        return "series" if "*" in str(node.get("params", {}).get("path", "")).split("/") else "scalar"
    return NODE_TYPES[node["type"]][1]


def validate(definition):
    """Reject cycles, unknown nodes and incompatible port types before anything runs."""
    if not isinstance(definition, dict) or not isinstance(definition.get("nodes"), list):
        raise StudioError("A workflow has a nodes list.", code="invalid-workflow")
    nodes = definition["nodes"]
    if len(nodes) > MAX_NODES:
        raise LimitExceeded(f"A workflow holds at most {MAX_NODES} nodes.", code="node-limit")
    if not nodes:
        raise StudioError("A workflow needs at least one node.", code="invalid-workflow")
    index = {}
    for node in nodes:
        if not isinstance(node, dict) or set(node) - {"id", "type", "params", "inputs", "label", "position"}:
            raise StudioError("A node has id, type, params and inputs.", code="invalid-node")
        if not isinstance(node.get("id"), str) or not node["id"] or len(node["id"]) > 64 or node["id"] in index:
            raise StudioError("Node IDs are unique strings of up to 64 characters.", code="invalid-node")
        if node.get("type") not in NODE_TYPES:
            raise StudioError(f"Unknown node type {str(node.get('type'))[:30]}.", code="invalid-node")
        if not isinstance(node.get("params", {}), dict) or not isinstance(node.get("inputs", {}), dict):
            raise StudioError("Node params and inputs must be objects.", code="invalid-node")
        index[node["id"]] = node
    incoming = {nid: [] for nid in index}
    for node in nodes:
        ports, _ = NODE_TYPES[node["type"]]
        inputs = node.get("inputs", {})
        if set(inputs) - set(ports):
            raise StudioError(f"Node {node['id']} has an input port that {node['type']} does not define.", code="invalid-node")
        for port, (accepted, multiple) in ports.items():
            sources = _ids(inputs, port)
            if not sources or (len(sources) > 1 and not multiple) or len(sources) > 8:
                raise StudioError(f"Node {node['id']} needs {'one or more' if multiple else 'exactly one'} input on {port}.", code="missing-input")
            for source in sources:
                if source not in index:
                    raise StudioError(f"Node {node['id']} reads missing node {source}.", code="missing-input")
                produced = produced_type(index[source])
                if produced not in accepted:
                    raise StudioError(f"Node {node['id']} cannot read a {produced} on {port}; it needs {' or '.join(accepted)}.", code="incompatible-types")
                incoming[node["id"]].append(source)
        _check_params(node)
    order, seen = [], set()
    indegree = {nid: len(set(src)) for nid, src in incoming.items()}
    ready = sorted(nid for nid, d in indegree.items() if d == 0)
    consumers = {nid: [] for nid in index}
    for target, sources in incoming.items():
        for source in set(sources):
            consumers[source].append(target)
    while ready:
        current = ready.pop(0)
        order.append(current)
        seen.add(current)
        for target in sorted(consumers[current]):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    if len(order) != len(index):
        raise Conflict("A workflow must not contain a cycle.", code="cycle")
    return order


def _check_params(node):
    from ..assistant.science import OPERATIONS
    params, kind = node.get("params", {}), node["type"]
    if kind == "operation":
        if params.get("operation") not in OPERATIONS or not isinstance(params.get("arguments", {}), dict):
            raise StudioError("An operation node names a supported scientific operation.", code="invalid-node")
    elif kind == "evidence_input" and not isinstance(params.get("snapshot_id"), str):
        raise StudioError("An evidence input names a frozen snapshot.", code="invalid-node")
    elif kind == "pick" and (not isinstance(params.get("path"), str) or not params["path"].startswith("/") or len(params["path"]) > 300):
        raise StudioError("A pick node needs a JSON pointer path.", code="invalid-node")
    elif kind == "filter" and any(k in params and not isinstance(params[k], (int, float)) for k in ("min", "max")):
        raise StudioError("Filter limits are numbers.", code="invalid-node")
    elif kind == "compare" and params.get("mode", "difference") not in ("difference", "ratio"):
        raise StudioError("Compare mode is difference or ratio.", code="invalid-node")
    elif kind == "visualize" and params.get("kind", "bars") not in ("bars", "table"):
        raise StudioError("Visualization kind is bars or table.", code="invalid-node")
    elif kind == "portable_export" and params.get("format","native") not in {"native","excalidraw","svg","png","pdf"}:
        raise StudioError("Choose a supported local export format.",code="invalid-node")
    elif kind == "card_output" and params.get("card_type", "chart") not in CARD_TYPES:
        raise StudioError("Choose a supported card type.", code="invalid-node")


class WorkflowRunner:
    def __init__(self, science_call, load_result, load_snapshot, revision_of, cache_get, cache_put, release_id,
                 clock=time.monotonic, cancelled=lambda: False, deadline=None, progress=None, effects=None):
        self.science_call, self.load_result, self.load_snapshot = science_call, load_result, load_snapshot
        self.revision_of, self.cache_get, self.cache_put, self.release_id = revision_of, cache_get, cache_put, release_id
        self.clock, self.cancelled = clock, cancelled
        self.deadline = deadline or clock() + MAX_SECONDS
        self.effects = effects
        self.tool_calls = 0
        self.cancel_event = threading.Event()
        self.progress = progress or (lambda outputs, receipts: None)

    def run(self, definition, document_revision, board_context):
        order = validate(definition)
        index = {n["id"]: n for n in definition["nodes"]}
        outputs, receipts = {}, []
        release = self.release_id()
        for nid in order:
            if self.cancelled() or self.cancel_event.is_set():
                return {"status": "cancelled", "outputs": outputs, "receipts": receipts, "error": "Workflow stopped before finishing."}
            if self.clock() > self.deadline:
                return {"status": "failed", "outputs": outputs, "receipts": receipts, "error": f"Workflow exceeded {MAX_SECONDS} seconds."}
            if self.revision_of() != document_revision:
                return {"status": "stale", "outputs": {}, "receipts": receipts,
                        "error": "The board changed while this workflow ran; the late result was discarded."}
            self.expected_revision=document_revision
            node = index[nid]
            ports, _ = NODE_TYPES[node["type"]]
            inputs = {port: [outputs[s] for s in _ids(node.get("inputs", {}), port)] for port in ports}
            key = digest({"type": node["type"], "params": node.get("params", {}), "inputs": {p: [o["_hash"] for o in v] for p, v in inputs.items()},
                          "release": release, "context": board_context if node["type"] == "operation" else None})
            hit = self.cache_get(key) if node["type"] in DETERMINISTIC else None
            started = self.clock()
            try:
                value = hit if hit is not None else self._execute(node, inputs, board_context)
            except (StudioError, ValueError, KeyError, IndexError, TypeError, PermissionError, InterruptedError, TimeoutError) as error:
                return {"status": "failed", "outputs": outputs, "receipts": receipts, "error": f"{nid}: {error}", "failed_node": nid}
            value["_hash"] = digest({k: v for k, v in value.items() if k != "_hash"})
            if hit is None and node["type"] in DETERMINISTIC:
                self.cache_put(key, value)
            if node["type"]=="board_insert":document_revision=value["document_revision"]
            outputs[nid] = value
            receipts.append({"node": nid, "type": node["type"], "cache_hit": hit is not None, "output_sha256": value["_hash"],
                             "inputs": {p: [o["_hash"] for o in v] for p, v in inputs.items()}, "seconds": round(self.clock() - started, 4),
                             "provenance": value.get("provenance")})
            self.progress(outputs, receipts)
        if self.revision_of() != document_revision:
            return {"status": "stale", "outputs": {}, "receipts": receipts, "error": "The board changed while this workflow ran; the late result was discarded."}
        sinks = [o for nid, o in outputs.items() if not any(nid in _ids(n.get("inputs", {}), p) for n in definition["nodes"] for p in n.get("inputs", {}))]
        return {"status": "completed", "outputs": outputs, "receipts": receipts, "release_id": release,
                "provenance": [p for o in sinks for p in (o.get("lineage") or [])]}

    def _execute(self, node, inputs, board_context):
        kind, params = node["type"], node.get("params", {})
        if kind in {"board_insert","portable_export"}:
            if not self.effects:raise StudioError("This workflow host cannot apply board/output effects.")
            return self.effects(node,inputs,self.expected_revision)
        if kind == "operation":
            self.tool_calls += 1
            if self.tool_calls > MAX_TOOL_CALLS:
                raise LimitExceeded(f"A workflow makes at most {MAX_TOOL_CALLS} scientific calls.", code="tool-call-limit")
            context = params.get("context") or board_context
            result = self.science_call(params["operation"], context, params.get("arguments", {}))
            lineage = {"result_id": result["id"], "receipt_sha256": result["sha256"], "release_id": result["release_id"],
                       "method": result["method"], "unit": result["method"]["unit"]}
            return {"type": "result", "result_id": result["id"], "operation": result["operation"], "scope": _scope(result["context"]),
                    "provenance": lineage, "lineage": [lineage]}
        if kind == "evidence_input":
            snapshot = self.load_snapshot(params["snapshot_id"])
            lineage = {"result_id": snapshot["result_id"], "receipt_sha256": snapshot["receipt_sha256"], "release_id": snapshot["release_id"],
                       "method": snapshot["method"], "unit": snapshot["unit"], "frozen": True}
            return {"type": "result", "result_id": snapshot["result_id"], "operation": snapshot["operation"], "scope": snapshot["scope"],
                    "provenance": lineage, "lineage": [lineage]}
        if kind == "pick":
            source = inputs["source"][0]
            return self._pick(source, params)
        if kind == "filter":
            data = inputs["data"][0]
            low, high = params.get("min"), params.get("max")
            items = [i for i in data["items"] if i["state"] == "observed" and (low is None or i["value"] >= low) and (high is None or i["value"] <= high)]
            return {**{k: v for k, v in data.items() if k not in ("_hash", "items")}, "items": items}
        if kind == "compare":
            left, right = inputs["left"][0], inputs["right"][0]
            if left["unit"] != right["unit"]:
                raise StudioError(f"Incompatible units: {left['unit']} and {right['unit']}.", code="incompatible-units")
            if left["scope"]["bbox"] != right["scope"]["bbox"] or left["provenance"]["release_id"] != right["provenance"]["release_id"]:
                raise StudioError("Compared values need the same study boundary and release.", code="incompatible-scope")
            a, b = left["items"][0], right["items"][0]
            if a["state"] != "observed" or b["state"] != "observed":
                outcome = {"state": "unknown", "value": None}
            elif params.get("mode", "difference") == "ratio":
                outcome = {"state": "observed", "value": a["value"] / b["value"]} if b["value"] else {"state": "unavailable", "value": None}
            else:
                outcome = {"state": "observed", "value": a["value"] - b["value"]}
            unit = "ratio" if params.get("mode") == "ratio" else left["unit"]
            return {"type": "table", "unit": unit, "scope": left["scope"], "provenance": left["provenance"],
                    "lineage": left["lineage"] + right["lineage"],
                    "rows": [{"label": "first", "value": a["value"], "unit": left["unit"], "state": a["state"]},
                             {"label": "second", "value": b["value"], "unit": right["unit"], "state": b["state"]},
                             {"label": params.get("mode", "difference") + " (arithmetic on cited values, not a new estimate)", "value": outcome["value"],
                              "unit": unit, "state": outcome["state"]}]}
        if kind == "visualize":
            data = inputs["data"][0]
            rows = data.get("items") or data.get("rows") or []
            values = [r["value"] for r in rows if r["state"] == "observed"]
            return {"type": "visual", "kind": params.get("kind", "bars"), "unit": data["unit"], "scope": data["scope"], "provenance": data["provenance"],
                    "lineage": data["lineage"], "domain": [0, max(values)] if values else None, "rows": rows[:MAX_RECORDS]}
        if kind == "card_output":
            content = inputs["content"][0]
            draft = {"type": params.get("card_type", "chart"), "title": str(params.get("title", "Workflow output"))[:120],
                     "display": {"workflow_output": {k: content.get(k) for k in ("kind", "unit", "domain", "rows", "items") if content.get(k) is not None}}}
            return {"type": "card_draft", "draft": draft, "unit": content.get("unit"), "scope": content.get("scope"),
                    "provenance": content.get("provenance"), "lineage": content.get("lineage") or []}
        if kind in ("export_prep", "story_output"):
            items = inputs["items"]
            return {"type": NODE_TYPES[kind][1], "title": str(params.get("title", "Checked study briefing"))[:120],
                    "items": items, "cards": [i["draft"] for i in items], "lineage": [l for i in items for l in i["lineage"]],
                    "units": sorted({i["unit"] for i in items if i.get("unit")})}
        raise StudioError("Unsupported node.", code="invalid-node")

    def _pick(self, source, params):
        receipt = self.load_result(source["result_id"])
        evidence = {**receipt, "id": source["result_id"]}
        path = params["path"]
        parts = path[1:].split("/")
        cursor = [evidence["payload"]]
        paths = [[]]
        for part in parts:
            nodes, next_paths = [], []
            for node, trail in zip(cursor, paths):
                if part == "*":
                    if not isinstance(node, list):
                        raise StudioError("A wildcard needs a list in the result.", code="invalid-node")
                    for position, child in enumerate(node):
                        nodes.append(child)
                        next_paths.append(trail + [str(position)])
                        if len(next_paths) > MAX_RECORDS:
                            raise LimitExceeded(f"A node selects at most {MAX_RECORDS} records.", code="record-limit")
                else:
                    nodes.append(pointer(node, "/" + part))
                    next_paths.append(trail + [part])
            cursor, paths = nodes, next_paths
        items = []
        for value, trail in zip(cursor, paths):
            concrete = "/" + "/".join(trail)
            if value is None:
                items.append({"path": concrete, "value": None, "state": "unknown", "label": trail[-1]})
            else:
                card = fact(evidence, concrete, params.get("label"))
                items.append({"path": concrete, "value": card["value"], "state": "observed", "label": card["label"], "unit_hint": card["unit"]})
        unit = next((i["unit_hint"] for i in items if i["state"] == "observed"), source["provenance"]["unit"])
        for item in items:
            item.pop("unit_hint", None)
        kind = "series" if "*" in parts else "scalar"
        lineage = dict(source["provenance"], unit=unit, paths=[i["path"] for i in items])
        return {"type": kind, "items": items, "unit": unit, "scope": source["scope"], "provenance": lineage, "lineage": [lineage]}


def _scope(context):
    return {"bbox": context["bbox"], "start": context["start"], "end": context["end"], "day": context.get("day") or None,
            "region": context.get("region"), "case": context.get("case")}
