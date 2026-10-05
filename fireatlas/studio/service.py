"""Studio application service: one place that ties the store, the science layer, stories, workflows, renders and rooms together."""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from pathlib import Path
from ..regions import REGIONS

from . import capabilities, evidence as ev, story as stories, visuals
from .errors import Conflict, Forbidden, LimitExceeded, NotFound, StudioError, Unavailable
from .render import RenderManager
from .rooms import Rooms, choose_adapter
from .store import StudioStore, dumps
from .workflow import WorkflowRunner, validate as validate_workflow

IMAGE_MAGIC = {b"\x89PNG\r\n\x1a\n": ("image/png", ".png"), b"\xff\xd8\xff": ("image/jpeg", ".jpg"), b"RIFF": ("image/webp", ".webp")}
MAX_ASSET_BYTES = 1_500_000
MAX_ASSETS = 40


class StudioService:
    def __init__(self, database, root=None, adapter=None, renders=None, clock=time.time, assistant=None):
        from ..assistant.science import Science, OPERATIONS
        self.database = Path(database)
        self.root = Path(root) if root else self.database.parent / "studio"
        self.store = StudioStore(self.root / "studio.sqlite3", clock=clock)
        self.science = Science(self.database, self.store)
        self.operations = OPERATIONS
        self.rooms = Rooms(self.store, adapter or choose_adapter(clock))
        self.assistant = assistant
        self.assistant_lock = threading.RLock()
        if assistant:
            from .assistant import StudioAssistant
            self.jarvis = StudioAssistant(self, assistant)
            assistant.studio_bridge = self.jarvis
        else:
            self.jarvis = None
        self.renders = renders or RenderManager(self.store, synthesize_factory=self._speech_factory if assistant else None)
        self.pool_lock = threading.Lock()
        self.run_flags = {}
        from .orchestration import Commands
        from .portability import Portability
        self.portability = Portability(self)
        self.commands = Commands(self)
        from .miro import Miro
        self.miro = Miro(self)

    def assistant_owner(self, principal):
        """Reuse one private assistant session per Studio principal, with its ordinary expiry and budgets."""
        if self.assistant is None:
            raise Unavailable("The existing assistant runtime is unavailable; deterministic Studio actions remain usable.")
        from ..assistant.contracts import normalize_context
        with self.assistant_lock:
            with self.store.connection() as db:
                row = db.execute("SELECT body FROM science_results WHERE principal_id=? AND kind='assistant_link' ORDER BY created DESC LIMIT 1", (principal,)).fetchone()
            if row:
                owner = json.loads(row["body"])["session"]
                try:
                    self.assistant.store.session(owner)
                    return owner
                except PermissionError:
                    pass
            owner = self.assistant.store.create_session(normalize_context())
            self.store.artifact(principal, "assistant_link", {"session": owner})
            return owner

    def _speech_factory(self, principal, reference, model, voice):
        from ..assistant.voice import synthesize_checked
        owner = self.assistant_owner(principal)
        return lambda text: synthesize_checked(self.assistant, owner, text, reference, model=model, voice=voice)

    # -- identity and capability ------------------------------------------------------
    def capabilities(self):
        try:
            release = {k: v for k, v in self.science.release().items() if k != "manifest"}
        except Exception:  # database absent: Studio still opens, evidence binding reports unavailable
            release = None
        result = capabilities.describe(self.rooms.adapter, self.store.version(), self.operations, release)
        if self.renders.recovery_error:
            result['video'] = {'available': False, 'reason': self.renders.recovery_error}
        result['assistant'] = self.assistant.capabilities() if self.assistant else {'ai_available': False, 'reason': 'The existing assistant runtime is unavailable.'}
        from .orchestration import RECIPES
        result['orchestration'] = {'available': True, 'recipes': RECIPES, 'context_schema': 'fireatlas-jarvis-context-v1'}
        result['portability'] = self.portability.capabilities()
        result['miro'] = self.miro.capabilities()
        if self.assistant is None:
            result['narration'] = {'available': False, 'reason': 'The existing assistant speech runtime is unavailable. Captions and transcript remain available.'}
        return result

    def release_id(self):
        return self.science.release()["id"]

    def envelope(self, document):
        """Document revision, context revision, capability state and release identity travel with every document response."""
        try:
            release = {"id": self.release_id()}
        except Exception:
            release = None
        caps = self.capabilities()
        return {**document, "capability_state": {k: caps[k] for k in ("canvas", "workflow", "video", "narration", "collaboration")}, "release": release}

    # -- documents --------------------------------------------------------------------
    def create_document(self, principal, body, key=None):
        self.store.throttle("mutate:" + principal, 120, 60)
        return self.envelope(self.store.create_document(principal, body.get("title", "Untitled board"), body.get("study"), key))

    def get_document(self, principal, document_id):
        document = self.store.get_document(principal, document_id)
        with self.store.connection() as db:
            room = db.execute("SELECT id FROM rooms WHERE document_id=?", (document_id,)).fetchone()
        room_view = self.rooms.view(principal, room['id']) if room else None
        return self.envelope({**document, "snapshots": self.store.snapshots(principal, document_id), "room": room_view})

    def transact(self, principal, document_id, body, key=None):
        self.store.throttle("mutate:" + principal, 120, 60)
        return self.envelope(self.store.apply_transaction(principal, document_id, body, key))

    def undo(self, principal, document_id, key=None):
        self.store.throttle("mutate:" + principal, 120, 60)
        return self.envelope(self.store.undo(principal, document_id, key))

    def patch_document(self, principal, document_id, body):
        # Resolve ownership before validating the patch payload.  This keeps
        # private document identifiers from being distinguishable by callers
        # who do not have access to the document.
        self.store.get_document(principal, document_id)
        if set(body) - {"selection", "title", "base_revision"}:
            raise StudioError("A document patch changes the selection or title.", code="invalid-patch")
        result = {}
        if "title" in body:
            result = self.store.apply_transaction(principal, document_id, {"base_revision": body.get("base_revision"), "ops": [{"op": "set_title", "title": body["title"]}]})
        if "selection" in body:
            result["selection"] = self.store.update_selection(principal, document_id, body["selection"])
        return self.envelope({**self.store.get_document(principal, document_id), **{k: v for k, v in result.items() if k == "selection"}})

    def presentation_action(self, principal, document_id, body, key=None):
        """Apply a small deterministic Studio/JARVIS presentation action.

        The action layer intentionally creates references and presentation state only. Scientific values
        still come from the existing binding resolver, and every mutation is one reversible transaction.
        """
        if not isinstance(body, dict) or body.get("action") not in {"build_investigation", "arrange_cards", "set_shared_selection", "create_story_draft", "create_workflow_draft"}:
            raise StudioError("Choose a supported Studio presentation action.", code="invalid-action")
        action = body["action"]
        document = self.store.get_document(principal, document_id)
        if body.get("base_revision") is not None and body["base_revision"] != document["revision"]:
            raise Conflict("This presentation action belongs to an older board revision.", code="stale-action", details={"current_revision": document["revision"]})
        if action == "set_shared_selection":
            selection = body.get("selection")
            return {"action": action, "selection": self.store.update_selection(principal, document_id, selection)}
        if action == "create_workflow_draft":
            definition = body.get('definition')
            validate_workflow(definition)
            with self.store.connection() as db:
                self.store.require(db, principal, document_id, 'editor')
            # Applying a proposal does not execute or overwrite a saved recipe.
            # Retain the owned draft on the server and load it into the editor;
            # existing workflow save/run contracts remain authoritative.
            draft = {'document_id': document_id, 'base_revision': document['revision'], 'definition': definition}
            identifier = self.store.artifact(principal, 'workflow_draft', draft)
            return {'action': action, 'workflow_draft': {'id': identifier, **draft}}
        if action == "create_story_draft":
            story = self.create_story(principal, document_id, body.get("story") or {}, key)
            return {"action": action, "story": story}
        if action == "arrange_cards":
            cards = body.get("cards")
            if not isinstance(cards, list) or len(cards) > 100:
                raise LimitExceeded("Arrange at most 100 cards.", code="card-limit")
            ops = [{"op": "move_card", "id": item.get("id"), "transform": item.get("transform")} for item in cards if isinstance(item, dict)]
            result = self.transact(principal, document_id, {"base_revision": body.get("base_revision", document["revision"]), "ops": ops, "group_id": body.get("group_id") or "studio-arrange"}, key)
            return {"action": action, "document": result}
        if document["state"]["order"]:
            return {"action": action, "document": document, "created": False, "message": "This board already has cards; add or arrange them explicitly."}
        context = ((document["state"].get("study") or {}).get("context")) or {}
        regional = context.get("bbox") in [list(r["bbox"]) for r in REGIONS.values()] and not context.get("case")
        activity = "harmonized" if regional else "replay"
        starter = [
            ("map", "Study map", "replay", "Recorded observations inside the applied study."),
            ("chart", "Activity chart", activity, "Checked activity values for the applied period."),
            ("timeline", "UTC timeline", "missingness", "Every date retains observed, unknown and gap states."),
            ("finding", "Selected finding", activity, "A checked value with an editable interpretation."),
            ("observation", "Source observation", "observations", "Original source rows remain inspectable."),
            ("note-question", "Question to investigate", None, "What does this evidence show, and what remains unknown?"),
            ("chapter-frame", "Story chapter frame", None, "Select cards here to build a chapter without duplicating data."),
        ]
        ops = []
        for index, (kind, title, operation, text_value) in enumerate(starter):
            cid = f"starter-{index + 1}"
            card = {"id": cid, "type": kind, "title": title, "text": text_value,
                    "binding": ({"operation": operation, "context": {}, "arguments": {}} if operation else None),
                    "snapshot_id": None, "asset_id": None, "display": {"template": "park-investigation" if context.get("case") == "park-2024" else "study-investigation"},
                    "provenance": {"created_by": "deterministic-studio-template"}, "transform": {"x": 40 + (index % 3) * 390, "y": 40 + (index // 3) * 280, "w": 360, "h": 240},
                    "follow": "board", "pinned_study": None, "locked": False}
            ops.append({"op": "add_card", "card": card})
        result = self.transact(principal, document_id, {"base_revision": document["revision"], "ops": ops, "group_id": "studio-template"}, key)
        return {"action": action, "document": result, "created": True, "message": "A deterministic evidence board was created. Freeze cards before citing them in a story."}

    # -- evidence bindings ------------------------------------------------------------
    def _context(self, principal, document_id, binding):
        document = self.store.get_document(principal, document_id)
        base = ((document["state"].get("study") or {}).get("context")) or {}
        context = {**base, **(binding.get("context") or {})}
        return context

    def resolve_binding(self, principal, document_id, binding):
        """Run the existing operation, then freeze the cited facts. ``Science.call`` remains the only calculator."""
        self.store.throttle("resolve:" + principal, 40, 60)
        with self.store.connection() as db:
            self.store.require(db, principal, document_id, "editor")
        if not isinstance(binding, dict) or binding.get("operation") not in self.operations:
            raise StudioError("A binding needs a supported scientific operation.", code="invalid-binding")
        try:
            evidence = self.science.call(principal, binding["operation"], self._context(principal, document_id, binding), binding.get("arguments") or {})
        except (ValueError, TypeError, KeyError) as error:
            raise StudioError(str(error), code="evidence-unavailable") from None
        except (TimeoutError, InterruptedError) as error:
            raise StudioError(str(error), code="evidence-timeout") from None
        snapshot = ev.build_snapshot(evidence, self.science.release(), binding)
        saved = self.store.add_snapshot(principal, document_id, snapshot)
        return {"snapshot": saved, "freshness": {"fresh": True, "release_id": evidence["release_id"]}}

    def snapshot_report(self, principal, document_id, snapshot_id):
        snapshot = self.store.get_snapshot(principal, document_id, snapshot_id)
        try:
            receipt = self.store.result_for_document(principal, document_id, snapshot["result_id"])
        except NotFound:
            receipt = None
        try:
            current = self.release_id()
        except Exception:
            current = None
        return {"snapshot": snapshot, "verification": ev.verify_snapshot(snapshot, receipt),
                "freshness": {"fresh": current == snapshot["release_id"], "snapshot_release_id": snapshot["release_id"], "current_release_id": current,
                              "note": "A frozen snapshot stays explainable after the live release changes; live Investigate results are rechecked on every call."}}

    def snapshot_receipt(self, principal, document_id, snapshot_id):
        """The frozen scientific result a snapshot cites, for map/table cards. Verified against the snapshot before it is returned."""
        snapshot = self.store.get_snapshot(principal, document_id, snapshot_id)
        receipt = self.store.result_for_document(principal, document_id, snapshot["result_id"])
        verification = ev.verify_snapshot(snapshot, receipt)
        if not verification["verified"]:
            raise StudioError("The stored receipt no longer matches this snapshot.", code="receipt-mismatch", details={"problems": verification["problems"]}, status=409)
        return {"snapshot_id": snapshot_id, "result_id": snapshot["result_id"], "receipt": {**receipt, "id": snapshot["result_id"]}}

    # -- stories ----------------------------------------------------------------------
    def snapshot_preview(self, principal, document_id, snapshot_id, kind, day=None, source="joint", start=None, end=None, cell=None):
        if kind not in ("map", "chart", "timeline", "observation", "finding", "calendar", "table"):
            raise StudioError("Choose a registered analytical preview.", code="invalid-preview")
        snapshot = self.store.get_snapshot(principal, document_id, snapshot_id)
        receipt = self.snapshot_receipt(principal, document_id, snapshot_id)["receipt"]
        card = {"type": kind}
        selection = {"day": day, **({"start": start, "end": end} if start or end else {})}
        if cell is not None:
            import re
            if not isinstance(cell, str) or not re.fullmatch(r"-?\d{1,8}:-?\d{1,8}", cell):
                raise StudioError("A selected common cell uses grid_x:grid_y.", code="invalid-selection")
            selection["cell"] = cell
        scene = {"title": kind.capitalize() + " · frozen evidence", "narration_text": "", "caption": "",
                 "figure_version": 2,
                 "fallback": stories.schematic(card, [snapshot]),
                 "visual": visuals.prepared(card, [snapshot], {snapshot_id: receipt}, {"selection": selection, "source_filter": source})}
        return {"svg": visuals.svg(scene), "visual": scene["visual"], "snapshot_sha256": snapshot["snapshot_sha256"]}

    def _story_row(self, db, principal, story_id, minimum="viewer"):
        row = db.execute("SELECT * FROM stories WHERE id=?", (story_id,)).fetchone()
        if not row:
            raise NotFound("Story not found.", code="story-not-found")
        self.store.require(db, principal, row["document_id"], minimum)
        return row

    def create_story(self, principal, document_id, body, key=None):
        self.store.throttle("mutate:" + principal, 120, 60)
        document = self.store.get_document(principal, document_id)
        with self.store.connection(write=True) as db:
            self.store.require(db, principal, document_id, "editor")
            replayed = self.store.replay(db, principal, "create-story", key)
            if replayed:
                return {**replayed, "idempotent_replay": True}
            if db.execute("SELECT COUNT(*) FROM stories WHERE document_id=?", (document_id,)).fetchone()[0] >= 10:
                raise LimitExceeded("A board holds at most ten stories.", code="story-limit")
            cleaned = stories.clean_story(body) if body.get("chapters") is not None else stories.default_story(document["state"], body.get("title"), body.get("selected_cards"))
            if body.get("chapters") is None and "audience" in body:
                cleaned = stories.clean_story({**cleaned, "audience": body["audience"]})
            identifier, now = "story_" + secrets.token_urlsafe(10), self.store.clock()
            db.execute("INSERT INTO stories VALUES(?,?,?,?,?,?,?)", (identifier, document_id, principal, cleaned["title"], 1, now, now))
            db.execute("INSERT INTO story_revisions VALUES(?,?,?,?,NULL,NULL,?,?)", (identifier, 1, document["revision"], dumps(cleaned), principal, now))
            response = self._story_view(db, identifier)
            self.store.remember(db, principal, "create-story", key, response)
        return response

    def _story_view(self, db, identifier, revision=None):
        row = db.execute("SELECT * FROM stories WHERE id=?", (identifier,)).fetchone()
        number = revision or row["revision"]
        item = db.execute("SELECT * FROM story_revisions WHERE story_id=? AND revision=?", (identifier, number)).fetchone()
        if not item:
            raise NotFound("Story revision not found.", code="story-revision-not-found")
        imported_scenes=[]
        for project in db.execute('SELECT body FROM imported_projects WHERE document_id=?',(row['document_id'],)):
            for saved in json.loads(project['body']).get('stories',[]):
                if saved['id']==identifier and number==saved.get('restored_revision',1):
                    imported_scenes=saved.get('frozen_scenes',[])
        return {"imported_frozen_scenes":imported_scenes, "id": identifier, "document_id": row["document_id"], "revision": number, "latest_revision": row["revision"], "title": row["title"],
                "body": json.loads(item["body"]), "document_revision": item["document_revision"], "resolved": json.loads(item["resolved"]) if item["resolved"] else None,
                "resolved_sha256": item["resolved_sha256"], "profile": stories.PROFILES[json.loads(item["body"])["profile"]]}

    def get_story(self, principal, story_id, revision=None):
        with self.store.connection() as db:
            self._story_row(db, principal, story_id)
            return self._story_view(db, story_id, revision)

    def update_story(self, principal, story_id, body, key=None):
        self.store.throttle("mutate:" + principal, 120, 60)
        expected = body.get("expected_revision")
        if type(expected) is not int:
            raise StudioError("A story update names the expected_revision it edits.", code="invalid-story")
        cleaned = stories.clean_story(body.get("story"))
        with self.store.connection(write=True) as db:
            row = self._story_row(db, principal, story_id, "editor")
            replayed = self.store.replay(db, principal, "story:" + story_id, key)
            if replayed:
                return {**replayed, "idempotent_replay": True}
            if row["revision"] != expected:
                raise Conflict("The story has a newer revision. Your draft was preserved.", details={"current_revision": row["revision"], "expected_revision": expected,
                                                                                                    "server_story": json.loads(db.execute("SELECT body FROM story_revisions WHERE story_id=? AND revision=?", (story_id, row["revision"])).fetchone()["body"])})
            document = db.execute("SELECT revision FROM documents WHERE id=?", (row["document_id"],)).fetchone()
            number, now = row["revision"] + 1, self.store.clock()
            db.execute("INSERT INTO story_revisions VALUES(?,?,?,?,NULL,NULL,?,?)", (story_id, number, document["revision"], dumps(cleaned), principal, now))
            db.execute("UPDATE stories SET revision=?,title=?,updated=? WHERE id=?", (number, cleaned["title"], now, story_id))
            response = self._story_view(db, story_id)
            self.store.remember(db, principal, "story:" + story_id, key, response)
        return response

    def _receipts(self, principal, document_id, snapshots):
        out = {}
        for sid, snapshot in snapshots.items():
            try:
                out[sid] = self.store.result_for_document(principal, document_id, snapshot["result_id"])
            except NotFound:
                pass
        return out

    def _assets(self, db, document_id):
        return {r["id"]: {"id": r["id"], "sha256": r["sha256"], "mime": r["mime"], "bytes": r["bytes"], "license": r["license"], "attribution": r["attribution"]}
                for r in db.execute("SELECT * FROM assets WHERE document_id=?", (document_id,))}

    def resolve_story(self, principal, story_id, revision=None):
        """Resolve once against the document's current revision; the result is stored with the story revision."""
        view = self.get_story(principal, story_id, revision)
        if view["resolved"] is not None:
            # A saved resolved revision is immutable even if its source board
            # is edited or rebound. Refreshing requires a new story revision.
            return {"resolved": view["resolved"], "document_revision": view["document_revision"]}
        document = self.store.get_document(principal, view["document_id"])
        snapshots = self.store.snapshots(principal, view["document_id"])
        with self.store.connection() as db:
            assets = self._assets(db, view["document_id"])
        cited_cards = {c for chapter in view['body']['chapters'] for c in
                       [chapter.get('card_id'), *chapter.get('evidence_cards', []), *chapter.get('visible_cards', [])] if c}
        cited_assets = {document['state']['cards'][c].get('asset_id') for c in cited_cards if c in document['state']['cards']}
        assets = {aid: meta for aid, meta in assets.items() if aid in cited_assets}
        import base64
        image_data = {}
        for aid, meta in assets.items():
            file, _ = self.asset_file(principal, aid)
            data = file.read_bytes()
            if len(data) > MAX_ASSET_BYTES or hashlib.sha256(data).hexdigest() != meta['sha256']:
                raise StudioError('Prepared image bytes no longer match their recorded hash.', code='asset-mismatch')
            image_data[aid] = {k: meta[k] for k in ('sha256', 'mime', 'license', 'attribution')}
            image_data[aid]['data'] = base64.b64encode(data).decode()
        resolved = stories.resolve_story(view["body"], document["state"], snapshots, self.science.release() if snapshots else {"id": "none"},
                                         story_id=story_id, story_revision=view["revision"], document_id=view["document_id"],
                                         document_revision=document["revision"], receipts=self._receipts(principal, view["document_id"], snapshots), assets=assets, asset_data=image_data)
        if len(dumps(resolved).encode()) > 20_000_000:
            raise LimitExceeded('The resolved story exceeds 20 MB. Reduce repeated image chapters.', code='story-too-large')
        with self.store.connection(write=True) as db:
            self._story_row(db, principal, story_id, "editor")
            frozen = db.execute("SELECT resolved FROM story_revisions WHERE story_id=? AND revision=?", (story_id, view["revision"])).fetchone()
            if frozen["resolved"]:
                original = json.loads(frozen["resolved"])
                return {"resolved": original, "document_revision": original["document_revision"]}
            db.execute("UPDATE story_revisions SET resolved=?,resolved_sha256=?,document_revision=? WHERE story_id=? AND revision=?",
                       (dumps(resolved), resolved["sha256"], document["revision"], story_id, view["revision"]))
        return {"resolved": resolved, "document_revision": document["revision"], "context_revision": document["context_revision"]}

    def export_story(self, principal, story_id, output, revision=None):
        """Write one selected story to a reader namespace (never the whole scientific archive)."""
        view = self.get_story(principal, story_id, revision)
        resolved = view["resolved"] or self.resolve_story(principal, story_id, revision)["resolved"]
        blocking = [w for w in resolved["warnings"] if w["problem"] in ("evidence-unfrozen", "card-missing", "checked-field-unavailable", "scene-context")]
        if blocking:
            raise StudioError("Bind every cited evidence card before export: " + blocking[0]["message"], code="story-not-ready", details={"warnings": blocking})
        snapshots = resolved["snapshots"]
        receipts = self._receipts(principal, view["document_id"], snapshots)
        files = {}
        with self.store.connection() as db:
            for asset in resolved["assets"]:
                row = db.execute("SELECT path FROM assets WHERE id=?", (asset["id"],)).fetchone()
                if row:
                    files[asset["id"]] = self.root / row["path"]
        manifest = stories.export_reader(resolved, receipts, output, asset_files=files)
        with self.store.connection(write=True) as db:
            db.execute("INSERT INTO exports VALUES(?,?,?,?,?)", ("exp_" + secrets.token_urlsafe(8), story_id, view["revision"], manifest["manifest_sha256"], self.store.clock()))
        return manifest

    # -- assets -----------------------------------------------------------------------
    def add_asset(self, principal, document_id, data, license_text, attribution, identifier=None):
        if not isinstance(license_text, str) or not 2 <= len(license_text) <= 200 or not isinstance(attribution, str) or not 2 <= len(attribution) <= 300:
            raise StudioError("Every image needs a license and attribution.", code="asset-metadata")
        if not 24 <= len(data) <= MAX_ASSET_BYTES:
            raise LimitExceeded("An image is at most 1.5 MB.", code="asset-too-large")
        mime = next((v for k, v in IMAGE_MAGIC.items() if data.startswith(k[:len(k)]) and (k != b"RIFF" or data[8:12] == b"WEBP")), None)
        if not mime:
            raise StudioError("Use a PNG, JPEG or WebP image.", code="asset-type")
        digest = hashlib.sha256(data).hexdigest()
        with self.store.connection(write=True) as db:
            self.store.require(db, principal, document_id, "editor")
            if identifier:
                existing = db.execute('SELECT * FROM assets WHERE id=? AND document_id=?', (identifier, document_id)).fetchone()
                if existing:
                    if existing['sha256'] != digest: raise Conflict('Stable image identity has different content.')
                    return {k: existing[k] for k in ('id','sha256','mime','bytes','license','attribution')}
            if db.execute("SELECT COUNT(*) FROM assets WHERE document_id=?", (document_id,)).fetchone()[0] >= MAX_ASSETS:
                raise LimitExceeded("A board holds at most 40 images.", code="asset-limit")
            relative = f"assets/{digest}{mime[1]}"
            (self.root / "assets").mkdir(parents=True, exist_ok=True)
            (self.root / relative).write_bytes(data)
            identifier = identifier or "asset_" + secrets.token_urlsafe(8)
            db.execute("INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?,?)", (identifier, principal, document_id, digest, mime[0], len(data), license_text, attribution, relative, self.store.clock()))
        return {"id": identifier, "sha256": digest, "mime": mime[0], "bytes": len(data), "license": license_text, "attribution": attribution}

    def asset_file(self, principal, asset_id):
        with self.store.connection() as db:
            row = db.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
            if not row:
                raise NotFound("Image not found.", code="asset-not-found")
            self.store.require(db, principal, row["document_id"])
        path = (self.root / row["path"]).resolve()
        if self.root.resolve() not in path.parents or not path.is_file():
            raise NotFound("Image not found.", code="asset-not-found")
        return path, row["mime"]

    def list_documents(self, principal):
        return {"documents": self.store.list_documents(principal)}

    def document_projects(self, principal, document_id):
        """Saved authoring objects belong to the board, independently of its current selection."""
        with self.store.connection() as db:
            self.store.require(db, principal, document_id)
            stories = [{"id": row["id"], "title": row["title"], "revision": row["revision"]}
                       for row in db.execute("SELECT id,title,revision FROM stories WHERE document_id=? ORDER BY updated DESC,id", (document_id,))]
            workflow = db.execute("SELECT id,revision,definition FROM workflows WHERE document_id=? ORDER BY CASE WHEN id=? THEN 0 ELSE 1 END,updated DESC", (document_id,json.loads(db.execute("SELECT state FROM documents WHERE id=?",(document_id,)).fetchone()[0]).get("workflow_id"))).fetchone()
            renders = [dict(row) for row in db.execute('SELECT id,story_id,story_revision,status,phase,created FROM renders WHERE document_id=? ORDER BY created DESC,id DESC LIMIT 30', (document_id,))]
            render_count = db.execute('SELECT COUNT(*) FROM renders WHERE document_id=?', (document_id,)).fetchone()[0]
            return {"stories": stories, "workflow": {"id": workflow["id"], "revision": workflow["revision"],
                    "definition": json.loads(workflow["definition"])} if workflow else None, 'renders': renders, 'renders_total': render_count, 'imported_annotations': [json.loads(r['body']) for r in db.execute('SELECT body FROM imported_annotations WHERE document_id=?', (document_id,))]}

    # -- workflows --------------------------------------------------------------------
    def validate_workflow(self, definition):
        order = validate_workflow(definition)
        return {"valid": True, "order": order, "nodes": len(definition["nodes"])}

    def save_workflow(self, principal, document_id, definition, expected_revision=None):
        self.store.throttle("mutate:" + principal, 120, 60)
        validate_workflow(definition)
        with self.store.connection(write=True) as db:
            self.store.require(db, principal, document_id, "editor")
            row = db.execute("SELECT * FROM workflows WHERE document_id=? ORDER BY CASE WHEN id=? THEN 0 ELSE 1 END,updated DESC", (document_id,json.loads(db.execute("SELECT state FROM documents WHERE id=?",(document_id,)).fetchone()[0]).get("workflow_id"))).fetchone()
            now = self.store.clock()
            if not row:
                identifier = "wf_" + secrets.token_urlsafe(10)
                db.execute("INSERT INTO workflows VALUES(?,?,?,?,?,?,?)", (identifier, document_id, principal, 1, dumps(definition), now, now))
                return {"id": identifier, "revision": 1, "definition": definition}
            if expected_revision != row["revision"]:
                raise Conflict("The workflow has a newer revision.", details={"current_revision": row["revision"]})
            db.execute("UPDATE workflows SET revision=revision+1,definition=?,updated=? WHERE id=?", (dumps(definition), now, row["id"]))
            return {"id": row["id"], "revision": row["revision"] + 1, "definition": definition}

    def get_workflow(self, principal, workflow_id):
        with self.store.connection() as db:
            row = db.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
            if not row:
                raise NotFound("Workflow not found.", code="workflow-not-found")
            self.store.require(db, principal, row["document_id"])
            return {"id": row["id"], "document_id": row["document_id"], "revision": row["revision"], "definition": json.loads(row["definition"])}

    def run_workflow(self, principal, workflow_id, background=True, run_id=None):
        workflow = self.get_workflow(principal, workflow_id)
        document = self.store.get_document(principal, workflow["document_id"])
        with self.store.connection(write=True) as db:
            self.store.require(db, principal, workflow["document_id"], "editor")
            if run_id and db.execute('SELECT 1 FROM workflow_runs WHERE id=? AND owner_id=? AND workflow_id=?', (run_id, principal, workflow_id)).fetchone():
                return self.get_run(principal, run_id)
            if db.execute("SELECT 1 FROM workflow_runs WHERE owner_id=? AND status='running'", (principal,)).fetchone():
                raise Conflict("A workflow is already running. Stop it first.", code="run-busy")
            run, now = run_id or "run_" + secrets.token_urlsafe(10), self.store.clock()
            db.execute("INSERT INTO workflow_runs VALUES(?,?,?,?,?,?,?,?,?,NULL,0,?,NULL)", (run, workflow_id, principal, document["revision"], workflow["revision"], "running",
                                                                                              ev_digest(workflow["definition"]), "{}", "[]", now))
        flag = threading.Event()
        self.run_flags[run] = flag
        job = (run, principal, workflow, document, flag)
        if background:
            threading.Thread(target=self._execute_run, args=job, daemon=True, name="studio-workflow").start()
        else:
            self._execute_run(*job)
        return self.get_run(principal, run)

    def _execute_run(self, run, principal, workflow, document, flag):
        document_id = workflow["document_id"]

        def revision_of():
            with self.store.connection() as db:
                return db.execute("SELECT revision FROM documents WHERE id=?", (document_id,)).fetchone()["revision"]

        def cancelled():
            with self.store.connection() as db:
                return bool(db.execute("SELECT cancel FROM workflow_runs WHERE id=?", (run,)).fetchone()["cancel"])

        def science(operation, context, arguments):
            return self.science.call(principal, operation, context, arguments, flag)

        def cache_get(key):
            key = ev_digest({"key": key, "document": document_id, "principal": principal})
            with self.store.connection() as db:
                row = db.execute("SELECT output FROM node_cache WHERE key=?", (key,)).fetchone()
            return json.loads(row["output"]) if row else None

        def cache_put(key, value):
            key = ev_digest({"key": key, "document": document_id, "principal": principal})
            with self.store.connection(write=True) as db:
                db.execute("INSERT OR REPLACE INTO node_cache VALUES(?,?,?)", (key, dumps(value), self.store.clock()))
                db.execute("DELETE FROM node_cache WHERE created<?", (self.store.clock() - 7 * 86400,))

        def progress(outputs, receipts):
            with self.store.connection(write=True) as db:
                db.execute("UPDATE workflow_runs SET outputs=?,receipts=? WHERE id=? AND status='running'",
                           (dumps(outputs), dumps(receipts), run))

        def effects(node,inputs,expected_revision):
            from .orchestration import stable
            if cancelled() or flag.is_set():raise InterruptedError('Workflow cancelled.')
            current=self.store.get_document(principal,document_id)
            if current['revision']!=expected_revision:raise Conflict('Board changed before the workflow output step.')
            if node['type']=='portable_export':
                prior=inputs['board'][0]
                job=self.portability.submit(principal,document_id,{'revision':prior['document_revision'],'format':node.get('params',{}).get('format','native')},key=run+':'+node['id'])
                return {'type':'export_job','job_id':job['id'],'status':job['status'],'document_revision':prior['document_revision'],'lineage':prior.get('lineage',[])}
            entries=inputs['items'];ops=[];lineage=[]
            top=max((c['transform']['y']+c['transform']['h'] for c in current['state']['cards'].values()),default=0)+60
            for i,item in enumerate(entries):
                snap_id=None
                for source in item.get('lineage',[]):
                    rid=source['result_id'];receipt=self.store.result_for_document(principal,document_id,rid)
                    release=self.science.release()
                    if release['id']!=receipt['release_id']:release={'manifest':{}}
                    snapshot=ev.build_snapshot(receipt|{'id':rid},release,{'operation':receipt['operation'],'context':receipt['context']})
                    if not release.get('manifest'):
                        snapshot['dependency_hashes']={};snapshot['dependency_status']='Original dependency manifest unavailable; frozen receipt retained.'
                    snap_id=self.store.add_snapshot(principal,document_id,snapshot,stable(run,node['id']+':snapshot:'+str(i)))['id'];break
                card={**item['draft'],'id':stable(run,node['id']+':card:'+str(i)), 'snapshot_id':snap_id,
                      'text':'New recorded workflow output. The captured investigation is unchanged.',
                      'provenance':{'workflow_id':workflow['id'],'run_id':run,'node_id':node['id']},
                      'follow':'pinned','pinned_study':{'context':board},'transform':{'x':40+i%3*410,'y':top+i//3*310,'w':380,'h':270}}
                ops.append({'op':'add_card','card':card});lineage.extend(item.get('lineage',[]))
            applied=self.store.apply_transaction(principal,document_id,{'base_revision':expected_revision,'ops':ops,'group_id':run+':'+node['id']},key=run+':'+node['id'],_workflow=run)
            return {'type':'board_result','document_id':document_id,'document_revision':applied['revision'],'object_ids':[o['card']['id'] for o in ops],'transaction_id':applied['transaction_id'],'lineage':lineage}

        runner = WorkflowRunner(science, lambda rid: self.store.result_for_document(principal, document_id, rid),
                                lambda sid: self.store.get_snapshot(principal, document_id, sid), revision_of, cache_get, cache_put,
                                self.release_id, cancelled=cancelled, progress=progress, effects=effects)
        runner.cancel_event = flag
        board = ((document["state"].get("study") or {}).get("context")) or {}
        try:
            result = runner.run(workflow["definition"], document["revision"], board)
        except StudioError as error:
            result = {"status": "failed", "outputs": {}, "receipts": [], "error": str(error)}
        except Exception as error:  # noqa: BLE001
            result = {"status": "failed", "outputs": {}, "receipts": [], "error": "Workflow failed: " + type(error).__name__}
        with self.store.connection(write=True) as db:
            current = db.execute("SELECT status FROM workflow_runs WHERE id=?", (run,)).fetchone()
            status = "cancelled" if current and current["status"] == "cancelled" else result["status"]
            db.execute("UPDATE workflow_runs SET status=?,outputs=?,receipts=?,error=?,finished=? WHERE id=?",
                       (status, dumps(result.get("outputs", {})), dumps(result.get("receipts", [])), result.get("error"), self.store.clock(), run))
        self.run_flags.pop(run, None)

    def get_run(self, principal, run):
        with self.store.connection() as db:
            row = db.execute("SELECT * FROM workflow_runs WHERE id=?", (run,)).fetchone()
            if not row:
                raise NotFound("Run not found.", code="run-not-found")
            workflow = db.execute("SELECT document_id FROM workflows WHERE id=?", (row["workflow_id"],)).fetchone()
            self.store.require(db, principal, workflow["document_id"])
        return {"id": row["id"], "workflow_id": row["workflow_id"], "status": row["status"], "document_revision": row["document_revision"],
                "outputs": json.loads(row["outputs"]), "receipts": json.loads(row["receipts"]), "error": row["error"], "definition_sha256": row["definition_sha256"]}

    def cancel_run(self, principal, run):
        view = self.get_run(principal, run)
        with self.store.connection(write=True) as db:
            workflow = db.execute("SELECT document_id FROM workflows WHERE id=?", (view["workflow_id"],)).fetchone()
            self.store.require(db, principal, workflow["document_id"], "editor")
            db.execute("UPDATE workflow_runs SET cancel=1,status=CASE WHEN status='running' THEN 'cancelled' ELSE status END WHERE id=?", (run,))
        flag = self.run_flags.get(run)
        if flag:
            flag.set()
        return self.get_run(principal, run)

    def apply_workflow_output(self, principal, run_id, node_id, expected_revision):
        """Apply one reviewed completed output. Receipts supply every snapshot; the graph cannot supply scalar facts."""
        run = self.get_run(principal, run_id)
        workflow = self.get_workflow(principal, run["workflow_id"])
        document_id = workflow["document_id"]
        with self.store.connection() as db:
            self.store.require(db, principal, document_id, "editor")
        document = self.store.get_document(principal, document_id)
        if expected_revision != document["revision"] or run["document_revision"] != expected_revision:
            raise Conflict("The board changed after this run. Run the workflow again before applying its output.", code="stale-workflow")
        output = run["outputs"].get(node_id)
        if run["status"] != "completed" or not output or output.get("type") not in ("card_draft", "story_draft", "export_manifest"):
            raise StudioError("Choose a card or story output from a completed run.", code="invalid-output")
        items = [output] if output["type"] == "card_draft" else output["items"]
        if len(items) + len(document["state"]["cards"]) > 100:
            raise LimitExceeded("A board holds at most 100 cards.", code="card-limit")
        release = self.science.release()
        ops, created = [], []
        for index, item in enumerate(items):
            lineage = item.get("lineage") or []
            if not lineage:
                raise StudioError("This output has no checked receipt.", code="missing-evidence")
            snapshots = []
            for origin in lineage:
                receipt = self.store.result_for_document(principal, document_id, origin["result_id"])
                if receipt["sha256"] != origin["receipt_sha256"]:
                    raise Conflict("A workflow receipt changed.", code="receipt-mismatch")
                # Retain the original frozen dependencies for evidence-input nodes.
                existing = next((s for s in self.store.snapshots(principal, document_id).values()
                                 if s["result_id"] == origin["result_id"] and not origin.get("paths")), None)
                if existing:
                    snapshots.append(existing)
                else:
                    if receipt["release_id"] != release["id"]:
                        raise Conflict("The input release changed. Freeze the original evidence or rerun this workflow.", code="stale-release")
                    binding = {"operation": receipt["operation"], "paths": origin.get("paths", []), "context": receipt["context"]}
                    snapshot = ev.build_snapshot({**receipt, "id": origin["result_id"]}, release, binding)
                    snapshots.append(self.store.add_snapshot(principal, document_id, snapshot))
            for offset, snapshot in enumerate(snapshots):
                cid = "wf-" + secrets.token_hex(8)
                created.append(cid)
                draft = item["draft"]
                card = {**draft, "id": cid, "snapshot_id": snapshot["id"], "follow": "pinned", "pinned_study": {"context": snapshot["context"]},
                        "transform": {"x": 40 + (index % 3) * 390, "y": 40 + (len(document["state"]["cards"]) // 3 + index // 3 + offset) * 280, "w": 360, "h": 240},
                        "provenance": {"workflow_run": run_id, "node": node_id, "output_sha256": output["_hash"],
                                       "note": "Checked source values; any comparison arithmetic is separately labeled in the workflow receipt."}}
                ops.append({"op": "add_card", "card": card})
        applied = self.transact(principal, document_id, {"base_revision": expected_revision, "ops": ops, "group_id": "workflow:" + run_id + ":" + node_id})
        result = {"document": applied, "created_cards": created}
        if output["type"] == "story_draft":
            result["story"] = self.create_story(principal, document_id, {"title": output["title"], "selected_cards": created})
        return result

    # -- renders ----------------------------------------------------------------------
    def start_render(self, principal, story_id, key=None, narration_requested=False):
        view = self.get_story(principal, story_id)
        resolved = view["resolved"] or self.resolve_story(principal, story_id)["resolved"]
        return self.renders.submit(principal, view["document_id"], story_id, resolved, key, narration_requested=narration_requested)

    def close(self):
        for flag in list(self.run_flags.values()):
            flag.set()
        for flag in list(self.commands.active.values()):
            flag.set()


def ev_digest(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()
