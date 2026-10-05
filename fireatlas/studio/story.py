"""Story Director: validation, the single ``ResolvedStory`` representation, captions and the static reader.

The browser player and the Remotion renderer both consume ``resolve_story`` output, so a scene can never
mean one thing on screen and another in the exported film.
"""
from __future__ import annotations

import datetime
import gzip
import hashlib
import html
import json
import math
import re
import shutil
from pathlib import Path

from ..assistant.contracts import digest
from . import evidence as ev, visuals, context_layers, narrative
from .errors import LimitExceeded, StudioError
from .graph import canonical, check_id

MAX_CHAPTERS = 24
MAX_TOTAL_SECONDS = 600
TRANSITIONS = ("cut", "fade", "slide")
PROFILES = {"briefing-1080p-landscape": {"id": "briefing-1080p-landscape", "width": 1920, "height": 1080, "fps": 30,
                                         "duration_seconds": 120, "aspect": "landscape"}}
AUDIENCE_PROFILES = {
    "public": {"max_visible_cards": 2, "source_detail": "summary", "reading_note": "Plain-language overview with a compact evidence gallery."},
    "student": {"max_visible_cards": 3, "source_detail": "definitions", "reading_note": "Definitions and state labels stay visible for guided learning."},
    "researcher": {"max_visible_cards": 6, "source_detail": "full", "reading_note": "Full cited evidence and method detail remain available."},
    "reviewer": {"max_visible_cards": 8, "source_detail": "provenance", "reading_note": "Provenance and source-state detail are prioritized."},
    "presenter": {"max_visible_cards": 3, "source_detail": "summary", "reading_note": "A compact gallery keeps the selected conclusion legible while retaining citations."},
}
DEFAULT_PROFILE = "briefing-1080p-landscape"
RESOLVED_SCHEMA = "fireatlas-resolved-story-v1"
READER_SCHEMA = "fireatlas-studio-reader-v1"
VIEWER_STATES = ("reading", "question-paused", "exploring", "returning")
RECEIPT_LIMIT = 8_000_000
PRIVATE = re.compile(r"\b(?:p|doc|tx|rec|inv|room)_[A-Za-z0-9_-]{8,}\b")
TEMPLATE = (("The study boundary", "map", "The map shows recorded observations inside the selected geographic and UTC window. Nearby detections are not a validated assignment to an incident."),
            ("Activity through time", "chart", "The timeline compares recorded activity within the study. An occupied cell-day counts one detected common cell on one UTC date."),
            ("The observation record", "timeline", "These source states distinguish collected records from unknown evidence and processing gaps. An empty record does not establish a fire-free day."),
            ("A finding to inspect", "finding", "The cited result comes from frozen evidence. Its interpretation remains editable and does not change the source measurements."),
            ("Behind the result", "observation", "Original satellite observations retain native source fields and acquisition time. Those rows and common-cell counts answer different questions."),
            ("What we can conclude", "note-question", "The study supports inspection of dated thermal observations. It does not establish ignition, continuous spread, a perimeter, or a forecast."))
AUDIENCE_PROSE = json.loads(Path(__file__).with_name("audience_templates.json").read_text())["profiles"]
NARRATIVE_PURPOSES = ("orientation", "activity", "states", "finding", "rows", "closing")


def adapt_narration(chapter, audience):
    """Adapt marked starter prose only; manual text and checked segments remain authored evidence."""
    purpose = chapter.get("narration_template")
    if purpose is None:
        return chapter
    known = {profile[purpose] for profile in AUDIENCE_PROSE.values()}
    if chapter.get("narration_segments") or chapter.get("narration") not in known:
        return {**chapter, "narration_template": None}
    return {**chapter, "narration": AUDIENCE_PROSE[audience][purpose]}


def clean_story(value):
    if not isinstance(value, dict):
        raise StudioError("A story must be an object.", code="invalid-story")
    unknown = set(value) - {"title", "profile", "chapters", "author_note", "audience", "target_duration_seconds", "style"}
    if unknown:
        raise StudioError("Unknown story field: " + ", ".join(sorted(unknown)), code="invalid-story")
    title = value.get("title", "Untitled briefing")
    if not isinstance(title, str) or not 1 <= len(title) <= 120:
        raise StudioError("A story title has 1–120 characters.", code="invalid-story")
    profile = value.get("profile", DEFAULT_PROFILE)
    if profile not in PROFILES:
        raise StudioError("Unsupported render profile.", code="invalid-story")
    chapters = value.get("chapters", [])
    if not isinstance(chapters, list) or len(chapters) > MAX_CHAPTERS:
        raise LimitExceeded(f"A story holds at most {MAX_CHAPTERS} chapters.", code="chapter-limit")
    clean, seen, total = [], set(), 0.0
    for item in chapters:
        if not isinstance(item, dict) or set(item) - {"id", "title", "caption", "narration", "narration_segments", "narration_template", "card_id", "duration_seconds", "transition", "question", "evidence_cards", "visible_cards", "study", "selection", "camera", "layers", "source_filter"}:
            raise StudioError("A chapter accepts identity, timing, selection, camera, layers, narration and evidence fields.", code="invalid-chapter")
        cid = check_id(item.get("id"), "chapter ID")
        if cid in seen:
            raise StudioError("Chapter IDs must be unique.", code="invalid-chapter")
        seen.add(cid)
        purpose = item.get("narration_template")
        if purpose is not None and (not isinstance(purpose, str) or purpose not in NARRATIVE_PURPOSES):
            raise StudioError("Narration templates must use a supported chapter purpose.", code="invalid-chapter")
        for key, limit in (("title", 120), ("caption", 300), ("narration", 1200)):
            if not isinstance(item.get(key, ""), str) or len(item.get(key, "")) > limit:
                raise StudioError(f"Chapter {key} is limited to {limit} characters.", code="invalid-chapter")
        duration = item.get("duration_seconds", 20)
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 2 <= duration <= 300:
            raise StudioError("A chapter lasts 2–300 seconds.", code="invalid-chapter")
        if item.get("transition", "fade") not in TRANSITIONS:
            raise StudioError("Unsupported chapter transition.", code="invalid-chapter")
        question = item.get("question")
        if question is not None and (not isinstance(question, dict) or set(question) - {"prompt", "answer"}
                                     or not isinstance(question.get("prompt"), str) or not 1 <= len(question["prompt"]) <= 300
                                     or not isinstance(question.get("answer", ""), str) or len(question.get("answer", "")) > 600):
            raise StudioError("A question has a prompt of up to 300 characters and an optional answer.", code="invalid-chapter")
        cards = item.get("evidence_cards", [])
        if not isinstance(cards, list) or len(cards) > 6 or not all(isinstance(c, str) for c in cards):
            raise StudioError("A chapter cites up to six cards.", code="invalid-chapter")
        visible = item.get("visible_cards", cards)
        if not isinstance(visible, list) or len(visible) > 12 or not all(isinstance(c, str) for c in visible):
            raise StudioError("A chapter shows at most twelve cards.", code="invalid-chapter")
        segments = item.get("narration_segments", [])
        narrative.validate_segments(segments)
        layers = item.get("layers", [])
        if not isinstance(layers, list) or len(layers) > 12 or not all(isinstance(layer, str) and len(layer) <= 80 for layer in layers):
            raise StudioError("A chapter has at most twelve named context layers.", code="invalid-chapter")
        camera = item.get("camera") or {}
        if not isinstance(camera, dict) or len(canonical(camera)) > 4000:
            raise StudioError("A chapter camera must be a bounded object.", code="invalid-chapter")
        chapter_study = item.get("study")
        if chapter_study is not None and (not isinstance(chapter_study, dict) or len(canonical(chapter_study)) > 8000):
            raise StudioError("A chapter study override must be a bounded object.", code="invalid-chapter")
        selection = item.get("selection")
        if selection is not None and (not isinstance(selection, dict) or len(canonical(selection)) > 4000):
            raise StudioError("A chapter selection must be a bounded object.", code="invalid-chapter")
        if isinstance(selection, dict):
            allowed_selection = {"day", "start", "end", "highlight_cells", "highlight_dates"}
            unknown_selection = set(selection) - allowed_selection
            if unknown_selection:
                raise StudioError("A chapter selection accepts UTC dates and bounded cell highlights only.", code="invalid-chapter")
            for key in ("day", "start", "end"):
                if key in selection and selection[key] is not None:
                    if not isinstance(selection[key], str):
                        raise StudioError("Chapter selection dates must be UTC ISO dates.", code="invalid-chapter")
                    try:
                        datetime.date.fromisoformat(selection[key])
                    except ValueError:
                        raise StudioError("Chapter selection dates must be valid UTC ISO dates.", code="invalid-chapter") from None
            if selection.get("highlight_cells") is not None:
                cells = selection["highlight_cells"]
                if not isinstance(cells, list) or len(cells) > 500 or not all(isinstance(cell, str) and 1 <= len(cell) <= 80 for cell in cells):
                    raise StudioError("A chapter may highlight at most 500 frozen common cells.", code="invalid-chapter")
            if selection.get("highlight_dates") is not None:
                dates = selection["highlight_dates"]
                if not isinstance(dates, list) or len(dates) > 31 or not all(isinstance(day, str) for day in dates):
                    raise StudioError("A chapter may highlight at most 31 UTC dates.", code="invalid-chapter")
        source_filter = item.get("source_filter")
        if source_filter is not None and (not isinstance(source_filter, (str, list, dict)) or len(canonical(source_filter)) > 2000):
            raise StudioError("A chapter source filter must be bounded.", code="invalid-chapter")
        total += duration
        clean.append({"id": cid, "title": item.get("title", ""), "caption": item.get("caption", ""), "narration": item.get("narration", ""),
                      "narration_segments": segments,
                      "card_id": check_id(item["card_id"], "card ID") if item.get("card_id") else None, "duration_seconds": duration, "transition": item.get("transition", "fade"),
                      "question": question, "evidence_cards": [check_id(c, "card ID") for c in cards],
                      "visible_cards": [check_id(c, "card ID") for c in visible], "study": chapter_study, "selection": selection,
                      "camera": camera, "layers": layers, "source_filter": source_filter,
                      **({"narration_template": purpose} if "narration_template" in item else {})})
    if total > MAX_TOTAL_SECONDS:
        raise LimitExceeded("A story lasts at most ten minutes.", code="story-too-long")
    audience = value.get("audience", "researcher")
    if audience not in ("public", "student", "researcher", "reviewer", "presenter"):
        raise StudioError("Choose a supported story audience.", code="invalid-story")
    clean = [adapt_narration(chapter, audience) for chapter in clean]
    target = value.get("target_duration_seconds", PROFILES[profile]["duration_seconds"])
    if isinstance(target, bool) or not isinstance(target, (int, float)) or not 10 <= target <= MAX_TOTAL_SECONDS:
        raise StudioError("Target duration must be between 10 seconds and ten minutes.", code="invalid-story")
    style = value.get("style", {})
    if not isinstance(style, dict) or len(canonical(style)) > 4000:
        raise StudioError("Story style must be a bounded object.", code="invalid-story")
    return {"title": title, "profile": profile, "chapters": clean, "author_note": str(value.get("author_note", ""))[:500],
            "audience": audience, "target_duration_seconds": target, "style": style}


def default_story(state, title=None, selected_cards=None):
    """Two-minute starter built from the board: six 20-second chapters, evidence cards assigned in order."""
    ordered = selected_cards if selected_cards is not None else sorted(state["order"], key=lambda cid: (state["cards"][cid].get("binding") is None, state["order"].index(cid)))
    if not isinstance(ordered, list) or any(cid not in state["cards"] for cid in ordered):
        raise StudioError("Choose story cards from this board.", code="invalid-story")
    checked_cards = [cid for cid in ordered if state["cards"][cid].get("snapshot_id") or state["cards"][cid].get("binding")]
    chapters = []
    for index, (name, kind, narration) in enumerate(TEMPLATE):
        card = next((cid for cid in ordered if state["cards"][cid]["type"] == kind), ordered[index % len(ordered)] if ordered else None)
        evidence = [card] if card else []
        if card and not state["cards"][card].get("binding") and checked_cards:
            evidence += [checked_cards[0]]
        chapters.append({"id": f"chapter-{index + 1}", "title": name, "caption": name, "narration": narration, "card_id": card,
                         "narration_template": NARRATIVE_PURPOSES[index],
                         "duration_seconds": 20, "transition": "fade", "evidence_cards": evidence,
                         "visible_cards": [card] if card else [], "question": {"prompt": "What remains unknown in this study?", "answer": "Inspect source states and the original rows. Missing detections alone cannot establish no fire."} if index == 2 else None})
    return clean_story({"title": title or state["title"], "profile": DEFAULT_PROFILE, "chapters": chapters,
                        "audience": "researcher", "target_duration_seconds": 120,
                        "style": {"theme": "ignis-atlassia", "motion": "reduced-motion-safe"}})


def schematic(card, snapshots):
    """Bounded fallback: a table or bar list made only from frozen evidence, never from live data."""
    facts = [f for s in snapshots for f in s["facts"]]
    observed = [f for f in facts if f["state"] == "observed" and isinstance(f["value"], (int, float))]
    units = {f["unit"] for f in observed}
    first = snapshots[0] if snapshots else None
    base = {"scope": first["scope"] if first else None, "unit": first["unit"] if first else None}
    if observed and len(units) == 1 and card and card["type"] in ("chart", "calendar", "map", "table"):
        top = max(f["value"] for f in observed)
        return {**base, "kind": "bars", "domain": [0, top], "bars": [{"label": f["label"], "value": f["value"], "state": f["state"]} for f in observed[:12]]}
    return {**base, "kind": "table", "rows": [{"label": f["label"], "value": f["value"], "unit": f["unit"], "state": f["state"]} for f in facts[:20]]}


def resolve_story(body, state, snapshots, release, *, story_id, story_revision, document_id, document_revision, receipts=None, assets=None, asset_data=None):
    """Resolve once. Every scene carries the evidence, scale contract, caption and fallback it will be played with."""
    profile = dict(PROFILES[body["profile"]])
    cards, scenes, cursor, warnings = state["cards"], [], 0.0, []
    used, methods, units = {}, {}, set()
    # Target duration is an authored reading goal. Resolve it into scene timing
    # once, so the browser reader, Remotion and the local renderer share the
    # same actual duration. Explicit chapter durations remain the proportions.
    requested_durations = [float(chapter["duration_seconds"]) for chapter in body["chapters"]]
    requested_total = sum(requested_durations)
    target_duration = float(body.get("target_duration_seconds", requested_total))
    duration_scale = target_duration / requested_total if requested_total and abs(target_duration - requested_total) > 0.001 else 1.0
    resolved_durations = [max(2.0, min(300.0, duration * duration_scale)) for duration in requested_durations]
    # Redistribute rounding/clamping residue deterministically while respecting
    # the chapter bounds. This keeps the requested target exact when feasible.
    residue = target_duration - sum(resolved_durations)
    for index in range(len(resolved_durations) - 1, -1, -1):
        if abs(residue) <= 0.000001:
            break
        candidate = max(2.0, min(300.0, resolved_durations[index] + residue))
        residue -= candidate - resolved_durations[index]
        resolved_durations[index] = candidate
    for chapter_index, chapter in enumerate(body["chapters"]):
        card = cards.get(chapter["card_id"]) if chapter.get("card_id") else None
        if chapter.get("card_id") and card is None:
            warnings.append({"chapter": chapter["id"], "problem": "card-missing", "message": "The referenced card is no longer on the board."})
        visible = chapter.get("visible_cards", chapter["evidence_cards"])[:AUDIENCE_PROFILES[body.get("audience", "researcher")]["max_visible_cards"]]
        cited = list(dict.fromkeys(([chapter["card_id"]] if chapter.get("card_id") else []) + chapter["evidence_cards"] + visible))
        evidence_ids, frozen = [], []
        for card_id in cited:
            source = cards.get(card_id)
            if not source:
                continue
            if source.get("binding") and not source.get("snapshot_id"):
                warnings.append({"chapter": chapter["id"], "problem": "evidence-unfrozen", "card": card_id,
                                 "message": "This evidence card has no frozen snapshot; bind it before exporting."})
                continue
            snapshot = snapshots.get(source.get("snapshot_id"))
            if snapshot:
                evidence_ids.append(snapshot["id"])
                frozen.append(snapshot)
                used[snapshot["id"]] = snapshot
                methods[snapshot["method"]["id"]] = snapshot["method"]
                units.add(snapshot["unit"])
        scale = None
        if frozen and receipts:
            first = next((f for f in frozen[0]["facts"] if f["state"] == "observed"), None)
            receipt = receipts.get(frozen[0]["id"])
            if first and receipt:
                mode = "relative" if (frozen[0]["context"] or {}).get("scale") == "relative" else "study"
                try:
                    scale = ev.scale_contract({**receipt, "id": frozen[0]["result_id"]}, first["path"], mode)
                except (ValueError, KeyError, IndexError, TypeError):
                    scale = None
        spoken = narrative.resolve(chapter['narration'], chapter.get('narration_segments', []), frozen, receipts or {})
        narration_text, resolved_fields = spoken['text'], spoken['fields']
        checked = {'checked': spoken['checked'], 'unmatched_numbers': spoken['unmatched_numbers']}
        for path in spoken['missing']:
            warnings.append({'chapter': chapter['id'], 'problem': 'checked-field-unavailable',
                             'message': f'Narration pointer {path} did not resolve unambiguously to a cited scalar.'})
        audience = body.get("audience", "researcher")
        audience_profile = AUDIENCE_PROFILES[audience]
        authored_visible_cards = chapter.get("visible_cards", chapter.get("evidence_cards", []))
        visible_cards = authored_visible_cards[:audience_profile["max_visible_cards"]]
        visible_views = []
        for visible_id in visible_cards:
            visible_source = cards.get(visible_id)
            if not visible_source:
                continue
            visible_snapshot = snapshots.get(visible_source.get('snapshot_id'))
            visible_receipt = (receipts or {}).get(visible_source.get('snapshot_id'))
            try:
                visible_views.append(visuals.gallery_view(visible_source, visible_snapshot, visible_receipt, chapter))
            except StudioError as error:
                warnings.append({'chapter': chapter['id'], 'problem': 'scene-context', 'card': visible_id, 'message': str(error)})
        scenes.append({"chapter_id": chapter["id"], "title": chapter["title"], "start_seconds": cursor, "duration_seconds": resolved_durations[chapter_index],
                       "figure_version": 2, "gallery_version": 2,
                       "transition": chapter["transition"], "caption": chapter["caption"] or chapter["title"], "narration_text": narration_text,
                       "narration_input": {'schema': narrative.SCHEMA, 'authored_text': chapter['narration'], 'segments': chapter.get('narration_segments', [])},
                       "narration_grounding": spoken['grounding'], "narration_checked": checked["checked"], "narration_unmatched_numbers": checked["unmatched_numbers"],
                       "question": chapter["question"], "study": chapter.get("study"), "selection": chapter.get("selection"),
                       "camera": chapter.get("camera", {}), "layers": chapter.get("layers", []), "source_filter": chapter.get("source_filter"),
                       "visible_cards": visible_cards, "visible_card_views": visible_views, "authored_visible_cards": authored_visible_cards,
                       "audience": audience, "audience_profile": audience_profile, "resolved_fields": resolved_fields,
                       "card": ({"id": card["id"], "type": card["type"], "title": card["title"], "display": card["display"], "text": card["text"],
                                 "asset_id": card["asset_id"]} if card else None),
                       "evidence": evidence_ids, "scale": scale, "fallback": schematic(card, frozen)})
        scene = scenes[-1]
        try:
            # Camera transition metadata belongs to the resolved timeline. Pass
            # the adapted chapter duration into the visual builder so the reader,
            # verifier and both renderers see the same duration after an audience
            # target has rescaled authored chapter timings.
            visual_chapter = {**chapter, "duration_seconds": resolved_durations[chapter_index]}
            scene["visual"] = visuals.prepared(card, frozen, receipts, visual_chapter)
            if chapter.get('layers'):
                if not scene['visual'] or scene['visual']['kind'] != 'map':
                    raise StudioError('Supplied landscape layers require a frozen map chapter.', code='scene-context')
                scene['visual']['context_layers'] = context_layers.freeze(scene['visual']['scope'], chapter['layers'])
            if card and card['type'] == 'image':
                prepared_image = (asset_data or {}).get(card.get('asset_id'))
                if not prepared_image:
                    raise StudioError('This image needs owned, hash-verified bytes before resolution.', code='missing-image')
                scene['visual'] = {'kind': 'image', **prepared_image}
        except StudioError as error:
            scene["visual"] = None
            warnings.append({"chapter": chapter["id"], "problem": "scene-context", "message": str(error)})
        scene["visual_svg"] = visuals.svg(scene)
        cursor += resolved_durations[chapter_index]
    profile["duration_seconds"] = cursor
    if abs(cursor - target_duration) > 0.001:
        warnings.append({"problem": "duration", "message": f"The requested {target_duration:g}-second target could not be met within chapter limits; resolved duration is {cursor:g} seconds."})
    for scene in scenes:
        if not scene["narration_checked"]:
            warnings.append({"chapter": scene["chapter_id"], "problem": "narration-unchecked",
                             "message": "Narration includes numbers not found in cited evidence: " + ", ".join(scene["narration_unmatched_numbers"])})
    resolved = {"schema": RESOLVED_SCHEMA, "story_id": story_id, "story_revision": story_revision, "document_id": document_id,
                "document_revision": document_revision, "title": body["title"], "profile": profile, "scenes": scenes, "caption_version": 2,
                "snapshots": used, "method": sorted(methods.values(), key=lambda m: m["id"]), "units": sorted(units),
                "release": {"ids": sorted({s["release_id"] for s in used.values()}), "frozen": all(s["release_frozen"] for s in used.values()) if used else False},
                "assets": list((assets or {}).values()), "warnings": warnings, "viewer_states": list(VIEWER_STATES),
                "audience": body.get("audience", "researcher"), "audience_profile": AUDIENCE_PROFILES[body.get("audience", "researcher")], "target_duration_seconds": target_duration,
                "duration_adapted": abs(duration_scale - 1.0) > 0.001,
                "limitations": sorted({text for s in used.values() for text in s["limitations"]}) or
                               ["Satellite detections are observations, not fire perimeters or forecasts. Missing observations do not establish no fire."]}
    resolved["sha256"] = digest(resolved)
    return resolved


def vtt_time(seconds):
    millis = int(round(seconds * 1000))
    return f"{millis // 3600000:02}:{millis // 60000 % 60:02}:{millis // 1000 % 60:02}.{millis % 1000:03}"


def captions(resolved):
    cues = ["WEBVTT", ""]
    version = resolved.get('caption_version', 1)
    if version not in (1, 2):
        raise StudioError('Unsupported frozen caption version.', code='invalid-captions')
    index = 0
    for scene in resolved["scenes"]:
        text = scene["narration_text"] or scene["caption"] or scene["title"]
        if version == 1:
            chunks = [text]
        else:
            # Short cues retain every word and follow the saved chapter timing.
            # This is display pagination, never a summary or a numeric rewrite.
            chunks, current = [], ''
            for word in text.split():
                if current and len(current) + len(word) + 1 > 88:
                    chunks.append(current)
                    current = ''
                current = (current + ' ' + word).strip()
            chunks.append(current)
        total = sum(max(1, len(chunk)) for chunk in chunks)
        consumed = 0
        for chunk in chunks:
            index += 1
            begin = scene['start_seconds'] + scene['duration_seconds'] * consumed / total
            consumed += max(1, len(chunk))
            end = scene['start_seconds'] + scene['duration_seconds'] * consumed / total
            cues += [str(index), f"{vtt_time(begin)} --> {vtt_time(end)}", html.escape(chunk, quote=False) if version == 2 else chunk, '']
    return "\n".join(cues)


def transcript(resolved, narration_label="Narration text (AI voice only when generated and labelled)"):
    lines = [resolved["title"], "=" * len(resolved["title"]), narration_label, ""]
    for scene in resolved["scenes"]:
        lines.append(f"[{vtt_time(scene['start_seconds'])}] {scene['title']}")
        if scene["narration_text"]:
            lines.append(scene["narration_text"])
        for sid in scene["evidence"]:
            snapshot = resolved["snapshots"][sid]
            for item in snapshot["facts"]:
                value = "unknown" if item["value"] is None else f"{item['value']} {item['unit']}"
                lines.append(f"  - {item['label']}: {value} ({item['state']}; receipt {snapshot['receipt_sha256'][:12]}, release {snapshot['release_id'][:12]})")
        lines.append("")
    lines += ["Limitations:"] + [f"- {text}" for text in resolved["limitations"]]
    return "\n".join(lines)


def schematic_svg(scene):
    return scene.get("visual_svg") or visuals.svg(scene)


def public_copy(resolved):
    """Strip every owner/workspace identifier. A static reader holds the story and its frozen evidence only."""
    value = json.loads(canonical(resolved))
    for key in ("document_id", "story_id", "document_revision"):
        value.pop(key, None)
    value["story_ref"] = hashlib.sha256((resolved["story_id"] + ":" + str(resolved["story_revision"])).encode()).hexdigest()[:16]
    value["sha256"] = digest({k: v for k, v in value.items() if k != "sha256"})
    return value


def slug(title, sha):
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "story"
    return f"{base}-{sha[:8]}"


def file_record(path, root):
    data = Path(path).read_bytes()
    return {"path": str(Path(path).relative_to(root).as_posix()), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def export_reader(resolved, receipts, output, *, asset_files=None, now=None):
    """Write one story namespace under ``output`` (normally ``site/data/studio``). Relative paths only."""
    public = public_copy(resolved)
    name = slug(public["title"], public["sha256"])
    root = Path(output) / name
    if root.exists():
        shutil.rmtree(root)
    (root / "evidence").mkdir(parents=True)
    (root / "fallbacks").mkdir()
    (root / "assets").mkdir()
    bundled = {}
    for sid, snapshot in public["snapshots"].items():
        receipt = receipts.get(sid)
        encoded = canonical(receipt).encode() if receipt else b""
        entry = {"snapshot": f"evidence/{sid}.snapshot.json", "receipt": None, "receipt_bundled": False}
        (root / entry["snapshot"]).write_text(json.dumps(snapshot, indent=2, sort_keys=True))
        if receipt and len(encoded) <= RECEIPT_LIMIT:
            entry["receipt"] = f"evidence/{sid}.receipt.json.gz"
            (root / entry["receipt"]).write_bytes(gzip.compress(encoded, mtime=0))
            entry["receipt_bundled"] = True
        bundled[sid] = entry
    for scene in public["scenes"]:
        (root / "fallbacks" / f"{scene['chapter_id']}.svg").write_text(schematic_svg(scene))
    assets = []
    for asset in public["assets"]:
        source = (asset_files or {}).get(asset["id"])
        if not source or not asset.get("license") or not asset.get("attribution"):
            raise StudioError("Every exported image needs prepared bytes, a license and attribution.", code="asset-metadata")
        target = root / "assets" / f"{asset['sha256']}{Path(source).suffix}"
        shutil.copyfile(source, target)
        assets.append({"sha256": asset["sha256"], "mime": asset["mime"], "license": asset["license"], "attribution": asset["attribution"],
                       "file": target.relative_to(root).as_posix()})
    story = {"schema": READER_SCHEMA, "resolved": public, "assets": assets, "evidence_files": bundled,
             "story_files": {"captions": "captions.vtt", "transcript": "transcript.txt",
                             "fallbacks": {s["chapter_id"]: f"fallbacks/{s['chapter_id']}.svg" for s in public["scenes"]}}}
    encoded = json.dumps(story, indent=2, sort_keys=True)
    if PRIVATE.search(encoded):
        raise StudioError("The reader export still contains a private identifier.", code="private-identifier")
    (root / "story.json").write_text(encoded)
    (root / "captions.vtt").write_text(captions(public))
    (root / "transcript.txt").write_text(transcript(public))
    (root / "README.txt").write_text("Ignis-Atlassia frozen story\n\nServe this folder over HTTP (for example: python3 -m http.server 8000), then open index.html.\nNo private cookie, model key, scientific database or external imagery is required.\nThe prepared maps are schematics, not incident perimeters or coverage footprints.\nFull receipts are bundled when below the export limit; omitted receipts are explicitly listed in story.json.\nVerify this extracted story directory with: python -m fireatlas.studio.story verify-reader path/to/story.\nThe verifier recounts bundled receipt scalars, figures, structured narration, captions and transcript. Legacy narration is reported separately. Omitted receipts remain explicitly unchecked. This is a consistency check, not independent scientific review.\n")
    # The reader bundle is independently portable: it can be opened from a
    # file server or project subpath without the scientific service.
    (root / "index.html").write_text("""<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>FireAtlas story</title><link rel=\"stylesheet\" href=\"reader.css\"></head><body class=\"reader-page\"><main id=\"reader-root\"><p>Loading the frozen story…</p></main><script defer src=\"reader.js\"></script></body></html>""")
    static_root = Path(__file__).resolve().parents[1] / "static"
    for source_name, target_name in (("studio-reader.css", "reader.css"), ("studio-reader.js", "reader.js")):
        source = static_root / source_name
        if source.is_file():
            shutil.copyfile(source, root / target_name)
    (root / "attribution.json").write_text(json.dumps({"assets": assets, "data": "NASA FIRMS standard products via the local FireAtlas release; see the evidence snapshots.",
                                                       "software": "Apache-2.0 code; NASA data are not covered by the repository license."}, indent=2))
    files = [file_record(p, root) for p in sorted(root.rglob("*")) if p.is_file() and p.name != "manifest.json"]
    manifest = {"schema": READER_SCHEMA, "slug": name, "title": public["title"], "story_sha256": public["sha256"], "files": files,
                "generated_utc": (now or datetime.datetime.now(datetime.timezone.utc)).isoformat(timespec="seconds"),
                "requires_backend": False, "private_identifiers": False}
    manifest["manifest_sha256"] = digest({k: v for k, v in manifest.items() if k != "manifest_sha256"})
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    index_path = Path(output) / "index.json"
    index = json.loads(index_path.read_text()) if index_path.is_file() else {"schema": "fireatlas-studio-catalog-v1", "stories": []}
    index["stories"] = [s for s in index["stories"] if s["slug"] != name] + [
        {"slug": name, "title": public["title"], "manifest": f"{name}/manifest.json", "manifest_sha256": manifest["manifest_sha256"],
         "duration_seconds": public["profile"]["duration_seconds"], "scenes": len(public["scenes"])}]
    index["stories"].sort(key=lambda s: s["slug"])
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True))
    return manifest


def verify_reader(root):
    """Bounded offline integrity and fact verification; never follows paths outside the export."""
    root = Path(root).resolve()
    problems, receipts_checked, snapshot_count, figures_checked = [], 0, 0, 0
    frozen_receipts, figures_unchecked = {}, []
    narrations_checked, narration_unchecked, legacy_narrations_checked = 0, [], 0
    captions_checked = transcript_checked = False
    maximum_file, maximum_total = 20_000_000, 250_000_000

    def safe(name):
        if not isinstance(name, str) or not name or "\\" in name:
            raise ValueError("invalid reader path")
        relative = Path(name)
        if relative.is_absolute() or any(part in ("..", ".") for part in relative.parts):
            raise ValueError("reader path leaves the export")
        path = root / relative
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            raise ValueError("reader path leaves the export or uses a symlink")
        return path

    def read(name, limit=maximum_file):
        path = safe(name)
        if not path.is_file() or path.stat().st_size > limit:
            raise ValueError("missing or oversized reader entry: " + name)
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("oversized reader entry: " + name)
        return data

    try:
        manifest = json.loads(read("manifest.json", 1_000_000))
        if manifest.get("schema") != READER_SCHEMA:
            raise ValueError("unsupported reader schema")
        if digest({k: v for k, v in manifest.items() if k != "manifest_sha256"}) != manifest.get("manifest_sha256"):
            problems.append("manifest checksum mismatch")
        entries = manifest["files"]
        if not isinstance(entries, list) or len(entries) > 400:
            raise ValueError("reader file inventory exceeds its limit")
        listed, accumulated = set(), 0
        for item in entries:
            name = item["path"]
            if name in listed:
                raise ValueError("duplicate reader entry")
            listed.add(name)
            data = read(name)
            accumulated += len(data)
            if accumulated > maximum_total:
                raise ValueError("reader expanded files exceed 250 MB")
            if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
                problems.append("changed or missing: " + name)
        story = json.loads(read("story.json"))
        if story.get("schema") != READER_SCHEMA:
            raise ValueError("unsupported story reader schema")
        resolved = story["resolved"]
        if digest({k: v for k, v in resolved.items() if k != "sha256"}) != resolved.get("sha256"):
            problems.append("resolved story checksum mismatch")
        if resolved["sha256"] != manifest["story_sha256"]:
            problems.append("manifest does not describe this story")
        snapshot_count = len(story["evidence_files"])
        if snapshot_count > 100:
            raise ValueError("too many reader snapshots")
        for sid, entry in story["evidence_files"].items():
            if entry["snapshot"] not in listed:
                raise ValueError("unlisted snapshot")
            snapshot = json.loads(read(entry["snapshot"]))
            if snapshot != resolved["snapshots"].get(sid):
                problems.append(f"{sid}: story and snapshot file disagree")
            receipt = None
            if entry["receipt_bundled"]:
                if entry["receipt"] not in listed:
                    raise ValueError("unlisted receipt")
                import io
                with gzip.GzipFile(fileobj=io.BytesIO(read(entry["receipt"]))) as stream:
                    expanded = stream.read(RECEIPT_LIMIT + 1)
                if len(expanded) > RECEIPT_LIMIT:
                    raise ValueError("receipt expansion exceeds 8 MB")
                receipt = json.loads(expanded)
                frozen_receipts[sid] = receipt
                receipts_checked += 1
            report = ev.verify_snapshot(snapshot, receipt)
            problems += [f"{sid}: {p}" for p in report["problems"]]
        if not isinstance(resolved.get("scenes"), list) or len(resolved["scenes"]) > MAX_CHAPTERS:
            raise ValueError("too many reader scenes")
        for scene in resolved["scenes"]:
            sid_list = scene["evidence"]
            if any(sid not in frozen_receipts for sid in sid_list):
                figures_unchecked.append(scene["chapter_id"])
                narration_unchecked.append(scene["chapter_id"])
                continue
            frozen = [resolved["snapshots"][sid] for sid in sid_list]
            supplied_input = scene.get('narration_input')
            if supplied_input is not None:
                if not isinstance(supplied_input, dict) or set(supplied_input) != {'schema', 'authored_text', 'segments'} or supplied_input['schema'] != narrative.SCHEMA:
                    raise ValueError('Unsupported frozen narration input')
                spoken = narrative.resolve(supplied_input['authored_text'], supplied_input['segments'], frozen, frozen_receipts)
                if (spoken['text'] != scene['narration_text'] or spoken['fields'] != scene.get('resolved_fields', []) or
                    spoken['checked'] != scene['narration_checked'] or spoken['unmatched_numbers'] != scene['narration_unmatched_numbers'] or
                    spoken['grounding'] != scene.get('narration_grounding')):
                    problems.append(scene['chapter_id'] + ': narration disagrees with cited frozen fields or authored input')
                if spoken['missing']:
                    problems.append(scene['chapter_id'] + ': narration contains unresolved checked fields')
                narrations_checked += 1
            else:
                # Older readers did not freeze the interpolation recipe. Check
                # their declared field scalars and numeric classification, and
                # report this limited scope without claiming reconstruction.
                expected_fields = []
                for field in scene.get('resolved_fields', []):
                    sid = field['snapshot_id']
                    if sid not in sid_list:
                        raise ValueError('Legacy narration references an uncited receipt')
                    snapshot = resolved['snapshots'][sid]
                    expected_fields.append({**ev._state_of({**frozen_receipts[sid], 'id': snapshot['result_id']}, field['path']), 'snapshot_id': sid})
                screened = ev.check_narration(scene['narration_text'], frozen + ([{'facts': expected_fields, 'scope': frozen[0]['scope']}] if expected_fields else []))
                if (expected_fields != scene.get('resolved_fields', []) or screened['checked'] != scene['narration_checked'] or
                    screened['unmatched_numbers'] != scene['narration_unmatched_numbers']):
                    problems.append(scene['chapter_id'] + ': legacy narration fields or numeric classification disagree')
                legacy_narrations_checked += 1
            expected_visual = visuals.prepared(scene.get("card"), frozen, frozen_receipts, scene)
            if scene.get('layers'):
                embedded = (scene.get('visual') or {}).get('context_layers') or []
                if [layer['name'] for layer in embedded] != scene['layers'] or not expected_visual or expected_visual['kind'] != 'map':
                    raise ValueError('Context layer selection disagrees with the frozen map scene')
                context_layers.verify(embedded, expected_visual['scope'])
                expected_visual['context_layers'] = embedded
            if scene.get('card', {}) and scene['card']['type'] == 'image':
                asset = next((a for a in story['assets'] if a['sha256'] == scene['visual']['sha256']), None)
                if not asset:
                    raise ValueError('image missing from the reader inventory')
                image_bytes = read(asset['file'], 1_500_000)
                if hashlib.sha256(image_bytes).hexdigest() != asset['sha256']:
                    problems.append(scene['chapter_id'] + ': image bytes changed')
                import base64
                expected_visual = {'kind': 'image', 'sha256': asset['sha256'], 'mime': asset['mime'], 'license': asset['license'],
                                   'attribution': asset['attribution'], 'data': base64.b64encode(image_bytes).decode()}
            expected_fallback = schematic(scene.get("card"), frozen)
            if expected_visual != scene.get("visual") or expected_fallback != scene.get("fallback"):
                problems.append(scene["chapter_id"] + ": prepared figure disagrees with frozen evidence")
            expected_views = scene.get('visible_card_views') or []
            if scene.get('gallery_version') is not None:
                if scene['gallery_version'] not in (1, 2) or len(expected_views) > 8:
                    raise ValueError('Unsupported or oversized frozen gallery')
                rebuilt = []
                for view in expected_views:
                    sid = view.get('snapshot_id')
                    if sid and sid not in sid_list:
                        raise ValueError('Gallery image refers to an uncited snapshot')
                    rebuilt.append(visuals.gallery_view(view, resolved['snapshots'].get(sid), frozen_receipts.get(sid),
                                   {'selection': view['selection'], 'source_filter': view['source_filter']}))
                if rebuilt != expected_views:
                    problems.append(scene['chapter_id'] + ': gallery visual disagrees with its frozen receipt')
                expected_views = rebuilt
            expected_svg = visuals.svg({**scene, "visual": expected_visual, "fallback": expected_fallback,
                                        'visible_card_views': expected_views})
            svg_file = story["story_files"]["fallbacks"][scene["chapter_id"]]
            if svg_file not in listed or read(svg_file).decode() != expected_svg or scene["visual_svg"] != expected_svg:
                problems.append(scene["chapter_id"] + ": SVG differs from the checked scene")
            figures_checked += 1
        for kind, expected in (('captions', captions(resolved)), ('transcript', transcript(resolved))):
            name = story['story_files'][kind]
            if name not in listed or read(name).decode() != expected:
                problems.append(kind + ': text differs from the frozen resolved story')
            elif kind == 'captions':
                captions_checked = True
            else:
                transcript_checked = True
    except (ValueError, KeyError, TypeError, OSError, EOFError, StudioError) as error:
        problems.append(str(error))
    return {"verified": not problems, "problems": problems, "receipts_checked": receipts_checked, "snapshots": snapshot_count,
            "figures_checked": figures_checked, "figures_unchecked": figures_unchecked,
            'narrations_checked': narrations_checked, 'legacy_narrations_checked': legacy_narrations_checked,
            'narrations_unchecked': narration_unchecked, 'captions_checked': captions_checked, 'transcript_checked': transcript_checked,
            'scope': 'Bundled receipt scalars, prepared figures and narrative representations; not source authentication or independent interpretation review.'}


def main(argv=None):
    """Verify an extracted reader without the scientific database or current support artifacts."""
    import argparse
    parser = argparse.ArgumentParser(description='Verify frozen story receipts, figures, narration, captions and transcript.')
    commands = parser.add_subparsers(dest='command', required=True)
    verify = commands.add_parser('verify-reader', help='Check a directory containing story.json and manifest.json.')
    verify.add_argument('directory', type=Path)
    args = parser.parse_args(argv)
    report = verify_reader(args.directory)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report['verified'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
