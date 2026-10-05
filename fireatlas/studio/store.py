"""Durable Studio persistence, separate from the scientific database and the expiring assistant workspace.

Every mutation is atomic (``BEGIN IMMEDIATE``), idempotent by key, role-checked, revision-checked and
recorded with an inverse so it can be undone. Principals are pseudonymous browser identities.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import secrets
import sqlite3
import time
from pathlib import Path

from . import graph
from .errors import Conflict, Forbidden, LimitExceeded, NotFound, StoreVersionError, StudioError, Throttled, Unauthorized

STORE_VERSION = 7
SESSION_SECONDS = 365 * 86400
MAX_STATE_BYTES = 1_000_000
ROLES = ("viewer", "editor", "owner")
RANK = {role: index for index, role in enumerate(ROLES)}

MIGRATIONS = [
    (1, "core", """
    CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE principals(id TEXT PRIMARY KEY, created REAL NOT NULL, last_seen REAL NOT NULL, recovery_hash TEXT);
    CREATE TABLE sessions(token_hash TEXT PRIMARY KEY, principal_id TEXT NOT NULL REFERENCES principals(id), created REAL NOT NULL, expires REAL NOT NULL);
    CREATE TABLE documents(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES principals(id), title TEXT NOT NULL,
        revision INTEGER NOT NULL, object_revs TEXT NOT NULL, state TEXT NOT NULL, selection TEXT NOT NULL,
        created REAL NOT NULL, updated REAL NOT NULL, deleted INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE revisions(document_id TEXT NOT NULL REFERENCES documents(id), revision INTEGER NOT NULL, author_id TEXT NOT NULL,
        tx_id TEXT, state_sha256 TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(document_id, revision));
    CREATE TABLE transactions(id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), author_id TEXT NOT NULL,
        base_revision INTEGER NOT NULL, revision INTEGER NOT NULL, group_id TEXT NOT NULL, ops TEXT NOT NULL, inverse TEXT NOT NULL,
        touched TEXT NOT NULL, undoes TEXT, undone INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
    CREATE INDEX transaction_document ON transactions(document_id, revision);
    CREATE TABLE idempotency(principal_id TEXT NOT NULL, scope TEXT NOT NULL, key TEXT NOT NULL, response TEXT NOT NULL,
        created REAL NOT NULL, PRIMARY KEY(principal_id, scope, key));
    CREATE TABLE snapshots(id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), owner_id TEXT NOT NULL,
        sha256 TEXT NOT NULL, body TEXT NOT NULL, created REAL NOT NULL);
    CREATE TABLE science_results(id TEXT PRIMARY KEY, principal_id TEXT NOT NULL, kind TEXT NOT NULL, sha256 TEXT NOT NULL,
        body TEXT NOT NULL, created REAL NOT NULL);
    CREATE TABLE assets(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, document_id TEXT NOT NULL, sha256 TEXT NOT NULL, mime TEXT NOT NULL,
        bytes INTEGER NOT NULL, license TEXT NOT NULL, attribution TEXT NOT NULL, path TEXT NOT NULL, created REAL NOT NULL);
    """),
    (2, "stories-workflows-renders-rooms", """
    CREATE TABLE stories(id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), owner_id TEXT NOT NULL,
        title TEXT NOT NULL, revision INTEGER NOT NULL, created REAL NOT NULL, updated REAL NOT NULL);
    CREATE TABLE story_revisions(story_id TEXT NOT NULL REFERENCES stories(id), revision INTEGER NOT NULL, document_revision INTEGER NOT NULL,
        body TEXT NOT NULL, resolved TEXT, resolved_sha256 TEXT, author_id TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(story_id, revision));
    CREATE TABLE workflows(id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), owner_id TEXT NOT NULL,
        revision INTEGER NOT NULL, definition TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL);
    CREATE TABLE workflow_runs(id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL REFERENCES workflows(id), owner_id TEXT NOT NULL,
        document_revision INTEGER NOT NULL, workflow_revision INTEGER NOT NULL, status TEXT NOT NULL, definition_sha256 TEXT NOT NULL,
        outputs TEXT NOT NULL, receipts TEXT NOT NULL, error TEXT, cancel INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, finished REAL);
    CREATE TABLE node_cache(key TEXT PRIMARY KEY, output TEXT NOT NULL, created REAL NOT NULL);
    CREATE TABLE renders(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, document_id TEXT NOT NULL, story_id TEXT NOT NULL,
        story_revision INTEGER NOT NULL, status TEXT NOT NULL, profile TEXT NOT NULL, manifest TEXT, artifact TEXT, error TEXT,
        cancel INTEGER NOT NULL DEFAULT 0, progress REAL NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL);
    CREATE TABLE rooms(id TEXT PRIMARY KEY, document_id TEXT NOT NULL UNIQUE REFERENCES documents(id), owner_id TEXT NOT NULL,
        adapter TEXT NOT NULL, created REAL NOT NULL);
    CREATE TABLE room_members(room_id TEXT NOT NULL REFERENCES rooms(id), principal_id TEXT NOT NULL, role TEXT NOT NULL,
        joined REAL NOT NULL, PRIMARY KEY(room_id, principal_id));
    CREATE TABLE invites(token_hash TEXT PRIMARY KEY, room_id TEXT NOT NULL REFERENCES rooms(id), role TEXT NOT NULL, created_by TEXT NOT NULL,
        created REAL NOT NULL, expires REAL NOT NULL, redeemed_by TEXT, redeemed_at REAL);
    CREATE TABLE comments(id TEXT PRIMARY KEY, room_id TEXT NOT NULL REFERENCES rooms(id), card_id TEXT, author_id TEXT NOT NULL,
        body TEXT NOT NULL, created REAL NOT NULL, resolved INTEGER NOT NULL DEFAULT 0, document_revision INTEGER NOT NULL);
    CREATE TABLE presenter_state(room_id TEXT PRIMARY KEY REFERENCES rooms(id), presenter_id TEXT, state TEXT NOT NULL,
        epoch INTEGER NOT NULL, updated REAL NOT NULL);
    CREATE TABLE exports(id TEXT PRIMARY KEY, story_id TEXT NOT NULL, story_revision INTEGER NOT NULL, manifest_sha256 TEXT NOT NULL,
        created REAL NOT NULL);
    """),
    (3, "chapter-comments", "ALTER TABLE comments ADD COLUMN chapter_ref TEXT;"),
    (4, "render-phases", """
    ALTER TABLE renders ADD COLUMN phase TEXT NOT NULL DEFAULT 'queued';
    UPDATE renders SET phase=CASE WHEN status='running' THEN 'preparing-assets' ELSE status END;
    """),
    (5, "orchestration-portability", """
    CREATE TABLE studio_contexts(principal_id TEXT NOT NULL, instance_id TEXT NOT NULL, tab_id TEXT NOT NULL,
        revision INTEGER NOT NULL, body TEXT NOT NULL, updated REAL NOT NULL, PRIMARY KEY(principal_id,instance_id));
    CREATE TABLE commands(id TEXT PRIMARY KEY, principal_id TEXT NOT NULL, request_key TEXT NOT NULL,
        request_hash TEXT NOT NULL, recipe TEXT NOT NULL, context TEXT NOT NULL, arguments TEXT NOT NULL,
        status TEXT NOT NULL, phase TEXT NOT NULL, outputs TEXT NOT NULL, error TEXT, cancel INTEGER NOT NULL DEFAULT 0,
        created REAL NOT NULL, updated REAL NOT NULL, UNIQUE(principal_id,request_key));
    CREATE TABLE command_steps(command_id TEXT NOT NULL REFERENCES commands(id), name TEXT NOT NULL,
        input_hash TEXT NOT NULL, output TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(command_id,name));
    CREATE TABLE investigation_packages(id TEXT PRIMARY KEY, command_id TEXT NOT NULL UNIQUE REFERENCES commands(id),
        principal_id TEXT NOT NULL, document_id TEXT NOT NULL, body TEXT NOT NULL, created REAL NOT NULL);
    CREATE TABLE export_jobs(id TEXT PRIMARY KEY, principal_id TEXT NOT NULL, document_id TEXT NOT NULL,
        revision INTEGER NOT NULL, format TEXT NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL, path TEXT,
        error TEXT, created REAL NOT NULL, updated REAL NOT NULL);
    CREATE TABLE remote_items(job_id TEXT NOT NULL, local_id TEXT NOT NULL, remote_id TEXT,
        status TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(job_id,local_id));
    CREATE TABLE imported_annotations(document_id TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL,
        PRIMARY KEY(document_id,id));
    """),
    (6, "imported-frozen-projects", """
    CREATE TABLE imported_projects(document_id TEXT NOT NULL, body TEXT NOT NULL);
    """),
    (7, "ai-story-generation", """
    CREATE TABLE story_generations(id TEXT PRIMARY KEY, principal_id TEXT NOT NULL,
        document_id TEXT NOT NULL REFERENCES documents(id), document_revision INTEGER NOT NULL,
        status TEXT NOT NULL, phase TEXT NOT NULL, progress REAL NOT NULL, capture TEXT NOT NULL,
        story_id TEXT, render_id TEXT, receipt TEXT, error TEXT, cancel INTEGER NOT NULL DEFAULT 0,
        created REAL NOT NULL, updated REAL NOT NULL);
    """),
]


def dumps(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


def token_hash(token):
    return hashlib.sha256(("fireatlas-studio:" + token).encode()).hexdigest()


class StudioStore:
    def __init__(self, path, clock=time.time):
        self.path = Path(path)
        self.root = self.path.parent
        self.root.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self._throttles = {}
        self.migrate()

    # -- connection and migration -------------------------------------------------
    @contextlib.contextmanager
    def connection(self, write=False):
        db = sqlite3.connect(self.path, timeout=20, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            try:
                yield db
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
            else:
                if db.in_transaction:
                    db.execute("COMMIT")
        finally:
            db.close()

    def migrate(self):
        with self.connection(write=True) as db:
            have = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meta'").fetchone()
            version = 0
            if have:
                row = db.execute("SELECT value FROM meta WHERE key='store_version'").fetchone()
                version = int(row["value"]) if row else 0
            if version > STORE_VERSION:
                raise StoreVersionError(f"Studio store version {version} is newer than this application ({STORE_VERSION}).")
            for number, name, script in MIGRATIONS:
                if number <= version:
                    continue
                for statement in [part.strip() for part in script.split(";") if part.strip()]:
                    db.execute(statement)
                db.execute("INSERT OR REPLACE INTO meta VALUES('store_version',?)", (str(number),))
                db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (f"migration_{number}", f"{name}@{self.clock():.0f}"))

    def version(self):
        with self.connection() as db:
            return int(db.execute("SELECT value FROM meta WHERE key='store_version'").fetchone()["value"])

    def throttle(self, key, limit=120, seconds=60):
        now = self.clock()
        start, count = self._throttles.get(key, (now, 0))
        if now - start >= seconds:
            start, count = now, 0
        if count >= limit:
            raise Throttled("Request allowance reached. Wait briefly before trying again.")
        self._throttles[key] = (start, count + 1)
        if len(self._throttles) > 5000:
            self._throttles = {k: v for k, v in self._throttles.items() if now - v[0] < seconds}

    # -- principals ---------------------------------------------------------------
    def create_principal(self):
        principal, token, now = "p_" + secrets.token_urlsafe(12), secrets.token_urlsafe(32), self.clock()
        with self.connection(write=True) as db:
            db.execute("INSERT INTO principals VALUES(?,?,?,NULL)", (principal, now, now))
            db.execute("INSERT INTO sessions VALUES(?,?,?,?)", (token_hash(token), principal, now, now + SESSION_SECONDS))
        return principal, token

    def principal(self, token, required=True):
        if token:
            with self.connection() as db:
                row = db.execute("SELECT principal_id,expires FROM sessions WHERE token_hash=?", (token_hash(token),)).fetchone()
            if row and row["expires"] > self.clock():
                return row["principal_id"]
        if required:
            raise Unauthorized("This browser has no Studio identity yet. Open Studio to create one.")
        return None

    def issue_recovery(self, principal):
        token = "rec_" + secrets.token_urlsafe(32)
        with self.connection(write=True) as db:
            db.execute("UPDATE principals SET recovery_hash=? WHERE id=?", (token_hash(token), principal))
        return token

    def recover(self, recovery):
        if not isinstance(recovery, str) or not recovery.startswith("rec_"):
            raise Forbidden("Recovery token is not valid.", code="invalid-recovery")
        self.throttle("recover", 20, 60)
        with self.connection(write=True) as db:
            row = db.execute("SELECT id FROM principals WHERE recovery_hash=?", (token_hash(recovery),)).fetchone()
            if not row:
                raise Forbidden("Recovery token is not valid.", code="invalid-recovery")
            token, now = secrets.token_urlsafe(32), self.clock()
            db.execute("INSERT INTO sessions VALUES(?,?,?,?)", (token_hash(token), row["id"], now, now + SESSION_SECONDS))
        return row["id"], token

    # -- access -------------------------------------------------------------------
    def role(self, db, principal, document_id):
        row = db.execute("SELECT owner_id,deleted FROM documents WHERE id=?", (document_id,)).fetchone()
        if not row or row["deleted"]:
            return None
        if row["owner_id"] == principal:
            return "owner"
        member = db.execute("SELECT m.role FROM room_members m JOIN rooms r ON r.id=m.room_id WHERE r.document_id=? AND m.principal_id=?",
                            (document_id, principal)).fetchone()
        return member["role"] if member else None

    def require(self, db, principal, document_id, minimum="viewer"):
        role = self.role(db, principal, document_id)
        if role is None:
            raise NotFound("Document not found.", code="document-not-found")
        if RANK[role] < RANK[minimum]:
            raise Forbidden(f"This action needs the {minimum} role; you are a {role}.", code="insufficient-role")
        return role

    # -- idempotency --------------------------------------------------------------
    def replay(self, db, principal, scope, key):
        if key is None:
            return None
        if not isinstance(key, str) or not 8 <= len(key) <= 100:
            raise StudioError("An idempotency key is 8–100 characters.", code="invalid-idempotency-key")
        row = db.execute("SELECT response FROM idempotency WHERE principal_id=? AND scope=? AND key=?", (principal, scope, key)).fetchone()
        return json.loads(row["response"]) if row else None

    def remember(self, db, principal, scope, key, response):
        if key is not None:
            db.execute("INSERT OR REPLACE INTO idempotency VALUES(?,?,?,?,?)", (principal, scope, key, dumps(response), self.clock()))
            db.execute("DELETE FROM idempotency WHERE created<?", (self.clock() - 30 * 86400,))

    # -- documents ----------------------------------------------------------------
    def create_document(self, principal, title="Untitled board", study=None, key=None):
        if not isinstance(title, str) or not 1 <= len(title) <= 120:
            raise StudioError("A title has 1–120 characters.", code="invalid-title")
        with self.connection(write=True) as db:
            replayed = self.replay(db, principal, "create-document", key)
            if replayed:
                return {**replayed, "idempotent_replay": True}
            state = graph.empty_state(title, study)
            document, now = "doc_" + secrets.token_urlsafe(12), self.clock()
            selection = {"board_id": document, "document_revision": 1, "epoch": 0, "card_id": None}
            db.execute("INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?,0)",
                       (document, principal, title, 1, dumps({"study": 1, "title": 1}), dumps(state), dumps(selection), now, now))
            db.execute("INSERT INTO revisions VALUES(?,?,?,?,?,?,?)", (document, 1, principal, None, sha256_text(dumps(state)), dumps(state), now))
            response = self._view(db, document, principal)
            self.remember(db, principal, "create-document", key, response)
            return response

    def _view(self, db, document_id, principal):
        row = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        revs = json.loads(row["object_revs"])
        return {"id": row["id"], "title": row["title"], "revision": row["revision"], "context_revision": revs.get("study", 1),
                "state": graph.upgrade_state(json.loads(row["state"])), "selection": json.loads(row["selection"]), "object_revisions": revs,
                "role": self.role(db, principal, document_id), "owner": row["owner_id"] == principal,
                "created": row["created"], "updated": row["updated"]}

    def get_document(self, principal, document_id):
        with self.connection() as db:
            self.require(db, principal, document_id)
            return self._view(db, document_id, principal)

    def list_documents(self, principal):
        with self.connection() as db:
            rows = db.execute("""SELECT d.id,d.title,d.revision,d.updated,d.owner_id FROM documents d WHERE d.deleted=0 AND (d.owner_id=? OR EXISTS
                (SELECT 1 FROM rooms r JOIN room_members m ON m.room_id=r.id WHERE r.document_id=d.id AND m.principal_id=?)) ORDER BY d.updated DESC LIMIT 200""",
                              (principal, principal)).fetchall()
        return [{"id": r["id"], "title": r["title"], "revision": r["revision"], "updated": r["updated"], "owner": r["owner_id"] == principal} for r in rows]

    def delete_document(self, principal, document_id, expected_revision, key=None):
        with self.connection(write=True) as db:
            replayed = self.replay(db, principal, 'delete-document:' + document_id, key)
            if replayed:
                return {**replayed, 'idempotent_replay': True}
            self.require(db, principal, document_id, 'owner')
            row = db.execute('SELECT revision FROM documents WHERE id=?', (document_id,)).fetchone()
            if type(expected_revision) is not int or expected_revision != row['revision']:
                raise Conflict('This investigation changed. Reload it before deleting.', code='revision-conflict')
            db.execute('UPDATE documents SET deleted=1,updated=? WHERE id=?', (self.clock(), document_id))
            db.execute("UPDATE workflow_runs SET cancel=1 WHERE workflow_id IN (SELECT id FROM workflows WHERE document_id=?) AND status IN ('queued','running')", (document_id,))
            db.execute("UPDATE renders SET cancel=1 WHERE document_id=? AND status IN ('queued','running')", (document_id,))
            response = {'id': document_id, 'deleted': True}
            self.remember(db, principal, 'delete-document:' + document_id, key, response)
            return response

    def revision_state(self, principal, document_id, revision):
        with self.connection() as db:
            self.require(db, principal, document_id)
            row = db.execute("SELECT state,state_sha256 FROM revisions WHERE document_id=? AND revision=?", (document_id, revision)).fetchone()
            if not row:
                raise NotFound("Revision not found.", code="revision-not-found")
            return json.loads(row["state"]), row["state_sha256"]

    def update_selection(self, principal, document_id, selection):
        if not isinstance(selection, dict) or set(selection) - {"document_revision", "card_id"}:
            raise StudioError("A selection has document_revision and card_id.", code="invalid-selection")
        with self.connection(write=True) as db:
            self.require(db, principal, document_id)
            row = db.execute("SELECT revision,selection,state FROM documents WHERE id=?", (document_id,)).fetchone()
            current = json.loads(row["selection"])
            state = json.loads(row["state"])
            card = selection.get("card_id")
            if card is not None and card not in state["cards"]:
                raise StudioError("The selected card is not on this board.", code="invalid-selection")
            if selection.get("document_revision") != row["revision"]:
                raise Conflict("The board changed. Your selection was preserved; reload to continue.", code="stale-selection",
                               details={"current_revision": row["revision"], "server_selection": current, "submitted_selection": selection})
            value = {"board_id": document_id, "document_revision": row["revision"], "epoch": current["epoch"] + 1, "card_id": card}
            db.execute("UPDATE documents SET selection=? WHERE id=?", (dumps(value), document_id))
            return value

    # -- transactions -------------------------------------------------------------
    def apply_transaction(self, principal, document_id, request, key=None, _internal=None, _command=None, _workflow=None):
        if not isinstance(request, dict) or not isinstance(request.get("ops"), list) or not 1 <= len(request["ops"]) <= 50:
            raise StudioError("A transaction has 1–50 operations and a base_revision.", code="invalid-transaction")
        base = request.get("base_revision")
        if type(base) is not int or base < 1:
            raise StudioError("A transaction needs the integer base_revision it was authored against.", code="invalid-transaction")
        with self.connection(write=True) as db:
            self.require(db, principal, document_id, "editor")
            if _workflow:
                run=db.execute('SELECT owner_id,cancel,status FROM workflow_runs WHERE id=?',(_workflow,)).fetchone()
                if not run or run['owner_id']!=principal or run['cancel'] or run['status']!='running':raise Conflict('Workflow stopped before insertion.')
            if _command:
                command = db.execute('SELECT * FROM commands WHERE id=? AND principal_id=?', (_command, principal)).fetchone()
                if not command or command['cancel']:
                    raise Conflict('This command was cancelled before insertion.', code='command-cancelled')
            replayed = self.replay(db, principal, "tx:" + document_id, key)
            if replayed:
                return {**replayed, "idempotent_replay": True}
            row = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
            state, revs = graph.upgrade_state(json.loads(row["state"])), json.loads(row["object_revs"])
            ops = request["ops"]
            before = copy.deepcopy(state)
            work = copy.deepcopy(state)
            touched, inverse = [], []
            for op in ops:
                self._apply(work, op, touched, inverse, internal=_internal is not None, principal=principal, db=db, document_id=document_id)
            touched = sorted(set(touched))
            if base != row["revision"]:
                stale = [obj for obj in touched if revs.get(obj, 1) > base]
                if base > row["revision"] or not request.get("allow_merge") or stale:
                    raise Conflict("The board has a newer revision. Your draft and selection were preserved.", details={
                        "current_revision": row["revision"], "base_revision": base, "conflicts": stale,
                        "mergeable": base < row["revision"] and not stale,
                        "server_objects": {obj: self._object(state, obj) for obj in touched}})
            if len(work["cards"]) > graph.MAX_CARDS:
                raise LimitExceeded(f"A board holds at most {graph.MAX_CARDS} cards.", code="card-limit")
            if len(work["connections"]) > graph.MAX_CONNECTIONS:
                raise LimitExceeded("A board holds at most 300 connections.", code="connection-limit")
            graph.topological_order(work["cards"], work["connections"])
            graph.validate_follow(work["cards"])
            graph.validate_groups(work)
            self._check_snapshots(db, work, document_id)
            encoded = dumps(work)
            if len(encoded) > MAX_STATE_BYTES:
                raise LimitExceeded("The board is larger than 1 MB.", code="document-too-large")
            if work == before:
                response = self._view(db, document_id, principal)
                return {**response, "transaction_id": None, "changed": False}
            revision, now, tx = row["revision"] + 1, self.clock(), "tx_" + secrets.token_urlsafe(12)
            for obj in touched:
                revs[obj] = revision
            title = work["title"]
            db.execute("UPDATE documents SET title=?,revision=?,object_revs=?,state=?,updated=? WHERE id=?",
                       (title, revision, dumps(revs), encoded, now, document_id))
            sel = json.loads(row["selection"])
            if sel["card_id"] and sel["card_id"] not in work["cards"]:
                sel["card_id"] = None
            sel["document_revision"] = revision
            db.execute("UPDATE documents SET selection=? WHERE id=?", (dumps(sel), document_id))
            db.execute("INSERT INTO revisions VALUES(?,?,?,?,?,?,?)", (document_id, revision, principal, tx, sha256_text(encoded), encoded, now))
            group = request.get("group_id") if isinstance(request.get("group_id"), str) else tx
            db.execute("INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,0,?)",
                       (tx, document_id, principal, base, revision, group[:100], dumps(ops), dumps(list(reversed(inverse))), dumps(touched),
                        _internal, now))
            response = {**self._view(db, document_id, principal), "transaction_id": tx, "changed": True,
                        "merged": base != row["revision"], "touched": touched}
            self.remember(db, principal, "tx:" + document_id, key, response)
            if _command:
                output = {'document_id': document_id, 'revision': revision, 'transaction_id': tx,
                          'object_ids': [op['card']['id'] for op in ops if op.get('op') == 'add_card']}
                db.execute('INSERT OR REPLACE INTO command_steps VALUES(?,?,?,?,?)',
                           (_command, 'insertion', sha256_text(dumps(ops)), dumps(output), now))
                db.execute("UPDATE commands SET status='saved',phase='saved',outputs=?,updated=? WHERE id=?",
                           (dumps({**json.loads(command['outputs']), **output}), now, _command))
            return response

    @staticmethod
    def _object(state, obj):
        kind, _, name = obj.partition(":")
        if kind == "card":
            return state["cards"].get(name)
        if kind == "conn":
            return state["connections"].get(name)
        if kind == "group":
            return state.get("groups", {}).get(name)
        return state.get(obj)

    def _check_snapshots(self, db, state, document_id):
        for card in state["cards"].values():
            if card.get("snapshot_id"):
                row = db.execute("SELECT 1 FROM snapshots WHERE id=? AND document_id=?", (card["snapshot_id"], document_id)).fetchone()
                if not row:
                    raise StudioError("A card refers to an evidence snapshot that does not belong to this board.", code="unknown-snapshot")

    def _apply(self, state, op, touched, inverse, internal, principal, db, document_id):
        if not isinstance(op, dict) or not isinstance(op.get("op"), str):
            raise StudioError("An operation needs an op name.", code="invalid-operation")
        name, cards, conns = op["op"], state["cards"], state["connections"]
        restore = {"restore_card", "restore_connection", "restore_field", "restore_order", "restore_group"}
        if name in restore and not internal:
            raise StudioError("Restore operations are reserved for undo.", code="invalid-operation")
        if name == "add_card":
            card = graph.clean_card(op.get("card"))
            if card["id"] in cards:
                raise StudioError("A card with that ID already exists.", code="duplicate-card")
            if card.get("follow") == "selected" and card.get("follow_card_id") not in cards:
                raise StudioError("A selected-follow card needs an existing source card.", code="invalid-card")
            cards[card["id"]] = card
            state["order"].append(card["id"])
            touched.append("card:" + card["id"])
            inverse.append({"op": "restore_card", "id": card["id"], "card": None, "index": None})
        elif name in ("update_card", "move_card"):
            cid = graph.check_id(op.get("id"), "card ID")
            if cid not in cards:
                raise StudioError("Card not found.", code="card-not-found")
            unlock = name == "update_card" and op.get("patch") == {"locked": False}
            if cards[cid].get("locked") and not internal and not unlock:
                raise Forbidden("This card is locked by the board owner or collaborator.", code="card-locked")
            patch = op.get("patch") if name == "update_card" else {"transform": op.get("transform")}
            if not isinstance(patch, dict) or "id" in patch or "type" in patch:
                raise StudioError("A card patch cannot change its ID or type.", code="invalid-card")
            previous = copy.deepcopy(cards[cid])
            cards[cid] = graph.clean_card(patch, previous)
            if cards[cid].get("follow") == "selected" and cards[cid].get("follow_card_id") not in cards:
                raise StudioError("A selected-follow card needs an existing source card.", code="invalid-card")
            touched.append("card:" + cid)
            inverse.append({"op": "restore_card", "id": cid, "card": previous, "index": state["order"].index(cid)})
        elif name == "remove_card":
            cid = graph.check_id(op.get("id"), "card ID")
            if cid not in cards:
                raise StudioError("Card not found.", code="card-not-found")
            if cards[cid].get("locked") and not internal:
                raise Forbidden("This card is locked by the board owner or collaborator.", code="card-locked")
            index = state["order"].index(cid)
            inverse.append({"op": "restore_card", "id": cid, "card": copy.deepcopy(cards[cid]), "index": index})
            for connection_id in [c for c, v in conns.items() if cid in (v["source"], v["target"])]:
                inverse.append({"op": "restore_connection", "id": connection_id, "connection": copy.deepcopy(conns[connection_id])})
                del conns[connection_id]
                touched.append("conn:" + connection_id)
            del cards[cid]
            state["order"].remove(cid)
            touched.append("card:" + cid)
            for gid, group in list(state["groups"].items()):
                if cid in group["card_ids"]:
                    inverse.append({"op": "restore_group", "id": gid, "group": copy.deepcopy(group)})
                    remaining = [member for member in group["card_ids"] if member != cid]
                    if len(remaining) < 2:
                        del state["groups"][gid]
                    else:
                        group["card_ids"] = remaining
                    touched.append("group:" + gid)
        elif name == "set_group":
            group = graph.clean_group(op.get("group"))
            gid = group["id"]
            inverse.append({"op": "restore_group", "id": gid, "group": copy.deepcopy(state["groups"].get(gid))})
            state["groups"][gid] = group
            touched.extend(["group:" + gid, *("card:" + cid for cid in group["card_ids"])])
        elif name in ("remove_group", "restore_group"):
            gid = graph.check_id(op.get("id"), "group ID")
            previous = state["groups"].get(gid)
            if name == "remove_group":
                if not previous:
                    raise StudioError("Group not found.", code="group-not-found")
                inverse.append({"op": "restore_group", "id": gid, "group": copy.deepcopy(previous)})
            value = op.get("group") if name == "restore_group" else None
            if value is None:
                state["groups"].pop(gid, None)
            else:
                state["groups"][gid] = graph.clean_group(value)
            touched.append("group:" + gid)
        elif name == "move_group":
            gid = graph.check_id(op.get("id"), "group ID")
            group = state["groups"].get(gid)
            if not group:
                raise StudioError("Group not found.", code="group-not-found")
            dx, dy = graph.finite(op.get("dx"), -100000, 100000, "dx"), graph.finite(op.get("dy"), -100000, 100000, "dy")
            for cid in group["card_ids"]:
                transform = {**cards[cid]["transform"], "x": cards[cid]["transform"]["x"] + dx, "y": cards[cid]["transform"]["y"] + dy}
                self._apply(state, {"op": "move_card", "id": cid, "transform": transform}, touched, inverse, internal, principal, db, document_id)
            touched.append("group:" + gid)
        elif name == "set_viewport":
            inverse.append({"op": "restore_field", "field": "viewport", "value": copy.deepcopy(state["viewport"])})
            state["viewport"] = graph.clean_viewport(op.get("viewport"))
            touched.append("viewport")
        elif name == "connect":
            connection = graph.clean_connection(op.get("connection"))
            if connection["id"] in conns:
                raise StudioError("A connection with that ID already exists.", code="duplicate-connection")
            if connection["source"] not in cards or connection["target"] not in cards or connection["source"] == connection["target"]:
                raise StudioError("A connection joins two different cards on this board.", code="invalid-connection")
            snapshots = self._snapshot_index(db, document_id, cards)
            reasons = graph.compatibility(cards[connection["source"]], cards[connection["target"]], connection["kind"], state, snapshots)
            if reasons:
                raise Conflict("These cards cannot be linked: " + " ".join(reasons), code="incompatible-link", details={"reasons": reasons})
            conns[connection["id"]] = connection
            touched.append("conn:" + connection["id"])
            inverse.append({"op": "restore_connection", "id": connection["id"], "connection": None})
        elif name == "disconnect":
            connection_id = graph.check_id(op.get("id"), "connection ID")
            if connection_id not in conns:
                raise StudioError("Connection not found.", code="connection-not-found")
            inverse.append({"op": "restore_connection", "id": connection_id, "connection": copy.deepcopy(conns[connection_id])})
            del conns[connection_id]
            touched.append("conn:" + connection_id)
        elif name == "set_study":
            inverse.append({"op": "restore_field", "field": "study", "value": copy.deepcopy(state["study"])})
            state["study"] = graph.clean_study(op.get("study"))
            touched.append("study")
        elif name == "set_title":
            title = op.get("title")
            if not isinstance(title, str) or not 1 <= len(title) <= 120:
                raise StudioError("A title has 1–120 characters.", code="invalid-title")
            inverse.append({"op": "restore_field", "field": "title", "value": state["title"]})
            state["title"] = title
            touched.append("title")
        elif name in ("set_story", "set_workflow"):
            field = name[4:] + "_id"
            value = op.get("id")
            if value is not None:
                graph.check_id(value, "reference")
                table = "stories" if name == "set_story" else "workflows"
                if not db.execute(f"SELECT 1 FROM {table} WHERE id=? AND document_id=?", (value, document_id)).fetchone():
                    raise StudioError("This saved object does not belong to the board.", code="invalid-reference")
            inverse.append({"op": "restore_field", "field": field, "value": state.get(field)})
            state[field] = value
            touched.append(name[4:])
        elif name == "restore_card":
            cid, card = op["id"], op.get("card")
            if card is None:
                cards.pop(cid, None)
                if cid in state["order"]:
                    state["order"].remove(cid)
            else:
                existed = cid in cards
                cards[cid] = card
                if not existed:
                    state["order"].insert(min(op.get("index") or 0, len(state["order"])), cid)
            touched.append("card:" + cid)
        elif name == "restore_connection":
            connection = op.get("connection")
            if connection is None:
                conns.pop(op["id"], None)
            else:
                conns[op["id"]] = connection
            touched.append("conn:" + op["id"])
        elif name == "restore_field":
            state[op["field"]] = op["value"]
            touched.append(op["field"].replace("_id", "") if op["field"] in ("story_id", "workflow_id") else op["field"])
        else:
            raise StudioError("Unsupported operation: " + name[:40], code="invalid-operation")

    def _snapshot_index(self, db, document_id, cards):
        ids = [c["snapshot_id"] for c in cards.values() if c.get("snapshot_id")]
        index = {}
        for identifier in ids:
            row = db.execute("SELECT body FROM snapshots WHERE id=? AND document_id=?", (identifier, document_id)).fetchone()
            if row:
                index[identifier] = json.loads(row["body"])
        return index

    def undo(self, principal, document_id, key=None, transaction_id=None):
        with self.connection(write=True) as db:
            self.require(db, principal, document_id, "editor")
            replayed = self.replay(db, principal, "undo:" + document_id, key)
            if replayed:
                return {**replayed, "idempotent_replay": True}
            row = db.execute("""SELECT * FROM transactions WHERE document_id=? AND author_id=? AND undone=0 AND undoes IS NULL
                AND (? IS NULL OR id=?) ORDER BY revision DESC LIMIT 1""", (document_id, principal, transaction_id, transaction_id)).fetchone()
            if not row:
                raise StudioError("There is nothing of yours to undo.", code="nothing-to-undo")
            checked_revision = db.execute("SELECT revision FROM documents WHERE id=?", (document_id,)).fetchone()["revision"]
            touched = json.loads(row["touched"])
            later = db.execute("SELECT touched,author_id FROM transactions WHERE document_id=? AND revision>?", (document_id, row["revision"])).fetchall()
            blocked = sorted({obj for item in later for obj in json.loads(item["touched"]) if obj in touched})
            if blocked:
                raise Conflict("Another change touched the same objects after yours.", code="undo-conflict", details={"conflicts": blocked})
        # The inverse is applied as a new transaction group so history stays append-only.
        current = self.get_document(principal, document_id)
        result = self.apply_transaction(principal, document_id, {"base_revision": checked_revision, "ops": json.loads(row["inverse"]),
                                                               "group_id": row["group_id"]}, None, _internal=row["id"])
        with self.connection(write=True) as db:
            db.execute("UPDATE transactions SET undone=1 WHERE id=?", (row["id"],))
            result = {**result, "undid": row["id"]}
            self.remember(db, principal, "undo:" + document_id, key, result)
        return result

    def redo(self, principal, document_id, key=None):
        with self.connection() as db:
            self.require(db, principal, document_id, "editor")
            replayed = self.replay(db, principal, "redo:" + document_id, key)
            if replayed:
                return {**replayed, "idempotent_replay": True}
            row = db.execute("""SELECT u.id,u.revision,t.ops,t.group_id FROM transactions u
                JOIN transactions t ON t.id=u.undoes WHERE u.document_id=? AND u.author_id=?
                AND u.undone=0 AND t.undone=1 ORDER BY u.revision DESC LIMIT 1""", (document_id, principal)).fetchone()
            if not row:
                raise StudioError("There is nothing of yours to redo.", code="nothing-to-redo")
            if db.execute("SELECT 1 FROM transactions WHERE document_id=? AND revision>?", (document_id, row["revision"])).fetchone():
                raise Conflict("The board changed after undo. Redo would overwrite a newer edit.", code="redo-conflict")
        current = self.get_document(principal, document_id)
        result = self.apply_transaction(principal, document_id, {"base_revision": row["revision"], "ops": json.loads(row["ops"]), "group_id": row["group_id"]})
        with self.connection(write=True) as db:
            db.execute("UPDATE transactions SET undone=1 WHERE id=?", (row["id"],))
            self.remember(db, principal, "redo:" + document_id, key, result)
        return result

    # -- snapshots, results and assets ----------------------------------------------
    def add_snapshot(self, principal, document_id, snapshot, identifier=None):
        with self.connection(write=True) as db:
            self.require(db, principal, document_id, "editor")
            identifier = identifier or "snap_" + secrets.token_urlsafe(12)
            existing = db.execute("SELECT body FROM snapshots WHERE id=? AND document_id=?", (identifier, document_id)).fetchone()
            if existing:
                return json.loads(existing['body'])
            body = {**snapshot, "id": identifier}
            body["snapshot_sha256"] = sha256_text(dumps({k: v for k, v in body.items() if k != "snapshot_sha256"}))
            db.execute("INSERT INTO snapshots VALUES(?,?,?,?,?,?)",
                       (identifier, document_id, principal, body["snapshot_sha256"], dumps(body), self.clock()))
            return body

    def get_snapshot(self, principal, document_id, identifier):
        with self.connection() as db:
            self.require(db, principal, document_id)
            row = db.execute("SELECT body FROM snapshots WHERE id=? AND document_id=?", (identifier, document_id)).fetchone()
            if not row:
                raise NotFound("Evidence snapshot not found.", code="snapshot-not-found")
            return json.loads(row["body"])

    def snapshots(self, principal, document_id):
        with self.connection() as db:
            self.require(db, principal, document_id)
            return {r["id"]: json.loads(r["body"]) for r in db.execute("SELECT id,body FROM snapshots WHERE document_id=?", (document_id,))}

    # ``Science.call`` needs an artifact store keyed by an owner. Studio results never touch the assistant database.
    def artifact(self, owner, kind, body):
        identifier = "res_" + secrets.token_urlsafe(16)
        with self.connection(write=True) as db:
            db.execute("INSERT INTO science_results VALUES(?,?,?,?,?,?)", (identifier, owner, kind, body.get("sha256", ""), dumps(body), self.clock()))
        return identifier

    def get_artifact(self, owner, identifier, kind=None):
        with self.connection() as db:
            row = db.execute("SELECT * FROM science_results WHERE id=? AND principal_id=?", (identifier, owner)).fetchone()
        if not row or (kind and row["kind"] != kind):
            raise PermissionError("Evidence is unavailable in this Studio identity.")
        return {"id": identifier, "kind": row["kind"], "body": json.loads(row["body"])}

    def result_for_document(self, principal, document_id, identifier):
        """Full stored science result used to verify a frozen snapshot after the live database changes."""
        with self.connection() as db:
            self.require(db, principal, document_id)
            row = db.execute("""SELECT body FROM science_results WHERE id=? AND (principal_id=? OR EXISTS
                (SELECT 1 FROM snapshots WHERE document_id=? AND json_extract(body,'$.result_id')=?))""",
                (identifier, principal, document_id, identifier)).fetchone()
        if not row:
            raise NotFound("Stored evidence receipt not found.", code="receipt-not-found")
        return json.loads(row["body"])
