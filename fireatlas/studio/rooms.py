"""Rooms, invites, comments and presenter state, plus the collaboration adapter boundary.

Studio does not implement its own unbounded synchronization engine. Documents synchronize through
revision-checked transactions; live presence and cursors go through an adapter. The loopback adapter is
deterministic and local. The Liveblocks adapter is available only when credentials are configured.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.request

from .errors import Conflict, Forbidden, LimitExceeded, NotFound, StudioError, Unavailable
from .store import RANK, dumps, token_hash

INVITE_MAX_SECONDS = 30 * 86400
INVITE_DEFAULT_SECONDS = 7 * 86400
PRESENCE_SECONDS = 30
MAX_MEMBERS = 25
MAX_COMMENTS = 500


class LoopbackAdapter:
    """In-process presence for tests and local development. No network, fully deterministic with an injected clock."""
    name = "loopback"

    def __init__(self, clock=time.time):
        self.clock, self._presence, self._lock = clock, {}, threading.RLock()

    def available(self):
        return True

    def describe(self):
        return {"adapter": self.name, "available": True, "scope": "this process only (local development and tests)"}

    def heartbeat(self, room_id, principal, role, cursor=None):
        with self._lock:
            members = self._presence.setdefault(room_id, {})
            members[principal] = {"role": role, "cursor": cursor if isinstance(cursor, dict) else None, "seen": self.clock()}
            return self.presence(room_id)

    def presence(self, room_id):
        now = self.clock()
        with self._lock:
            members = self._presence.get(room_id, {})
            for key in [k for k, v in members.items() if now - v["seen"] > PRESENCE_SECONDS]:
                del members[key]
            return [{"principal": key[-6:], "role": v["role"], "cursor": v["cursor"]} for key, v in sorted(members.items())]

    def authorize(self, room_id, principal, role):
        return {"adapter": self.name, "room": room_id, "role": role}


class LiveblocksAdapter:
    """Boundary for Liveblocks. Absent credentials mean collaboration is unavailable; single-user editing is unaffected."""
    name = "liveblocks"

    def __init__(self):
        self.secret = os.getenv("LIVEBLOCKS_SECRET_KEY", "")

    def available(self):
        return self.secret.startswith("sk_")

    def describe(self):
        return {"adapter": self.name, "available": self.available(),
                "reason": None if self.available() else "Set LIVEBLOCKS_SECRET_KEY (a server-side secret) to enable shared presence."}

    def heartbeat(self, room_id, principal, role, cursor=None):
        raise Unavailable("Liveblocks presence runs in the browser through an authorized session.")

    def presence(self, room_id):
        return []

    def authorize(self, room_id, principal, role):
        if not self.available():
            raise Unavailable("Liveblocks credentials are not configured.")
        permissions = ["*:write"] if RANK[role] >= RANK["editor"] else ["*:read"]
        body = json.dumps({"userId": principal, "permissions": {room_id: permissions}}).encode()
        request = urllib.request.Request("https://api.liveblocks.io/v2/authorize-user", data=body, method="POST",
                                         headers={"Authorization": "Bearer " + self.secret, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = response.read(65537)
                token = json.loads(data).get("token") if len(data) <= 65536 else None
                if not isinstance(token, str) or not token:
                    raise ValueError("missing authorization token")
                return {"adapter": self.name, "token": token}
        except (urllib.error.URLError, TimeoutError, ValueError):
            raise Unavailable("Liveblocks could not authorize this session; single-user editing continues.") from None


def choose_adapter(clock=time.time):
    """Liveblocks when configured, otherwise the loopback adapter is used only when explicitly allowed."""
    liveblocks = LiveblocksAdapter()
    if liveblocks.available():
        return liveblocks
    if os.getenv("FIREATLAS_STUDIO_COLLAB") == "loopback":
        return LoopbackAdapter(clock)
    return liveblocks


class Rooms:
    def __init__(self, store, adapter):
        self.store, self.adapter = store, adapter

    def _room(self, db, document_id):
        return db.execute("SELECT * FROM rooms WHERE document_id=?", (document_id,)).fetchone()

    def create(self, principal, document_id):
        if not self.adapter.available():
            raise Unavailable("Collaboration is unavailable: " + (self.adapter.describe().get("reason") or "no adapter configured") + " Single-user editing is unaffected.")
        with self.store.connection(write=True) as db:
            self.store.require(db, principal, document_id, "owner")
            room = self._room(db, document_id)
            if room:
                return self._view(db, room, principal)
            identifier = "room_" + secrets.token_urlsafe(12)
            db.execute("INSERT INTO rooms VALUES(?,?,?,?,?)", (identifier, document_id, principal, self.adapter.name, self.store.clock()))
            db.execute("INSERT INTO room_members VALUES(?,?,?,?)", (identifier, principal, "owner", self.store.clock()))
            db.execute("INSERT INTO presenter_state VALUES(?,?,?,?,?)", (identifier, None, "{}", 0, self.store.clock()))
            return self._view(db, self._room(db, document_id), principal)

    def _view(self, db, room, principal):
        members = [{"principal": r["principal_id"][-6:], "role": r["role"], "you": r["principal_id"] == principal}
                   for r in db.execute("SELECT principal_id,role FROM room_members WHERE room_id=? ORDER BY joined", (room["id"],))]
        return {"id": room["id"], "document_id": room["document_id"], "adapter": room["adapter"], "members": members}

    def _member_room(self, db, principal, room_id, minimum="viewer"):
        room = db.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
        member = db.execute("SELECT role FROM room_members WHERE room_id=? AND principal_id=?", (room_id, principal)).fetchone() if room else None
        if not room or not member:
            raise NotFound("Room not found.", code="room-not-found")
        if RANK[member["role"]] < RANK[minimum]:
            raise Forbidden(f"This action needs the {minimum} role; you are a {member['role']}.", code="insufficient-role")
        return room, member["role"]

    def view(self, principal, room_id):
        with self.store.connection() as db:
            room, _ = self._member_room(db, principal, room_id)
            return {**self._view(db, room, principal), "adapter_state": self.adapter.describe()}

    def invite(self, principal, room_id, role, ttl=INVITE_DEFAULT_SECONDS):
        if role not in ("editor", "viewer"):
            raise StudioError("Invites grant the editor or viewer role.", code="invalid-role")
        if isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or not 60 <= ttl <= INVITE_MAX_SECONDS:
            raise StudioError("An invite lasts from one minute to thirty days.", code="invalid-ttl")
        with self.store.connection(write=True) as db:
            room, _ = self._member_room(db, principal, room_id, "owner")
            token, now = "inv_" + secrets.token_urlsafe(24), self.store.clock()
            db.execute("INSERT INTO invites VALUES(?,?,?,?,?,?,NULL,NULL)", (token_hash(token), room["id"], role, principal, now, now + ttl))
        return {"token": token, "role": role, "expires": now + ttl, "room_id": room_id,
                "note": "Share this token privately. It works once and is stored only as a hash."}

    def redeem(self, principal, token):
        if not isinstance(token, str) or not token.startswith("inv_"):
            raise Forbidden("This invite is not valid.", code="invalid-invite")
        self.store.throttle("redeem:" + principal, 20, 60)
        with self.store.connection(write=True) as db:
            row = db.execute("SELECT * FROM invites WHERE token_hash=?", (token_hash(token),)).fetchone()
            if not row or row["redeemed_at"] is not None or row["expires"] < self.store.clock():
                raise Forbidden("This invite is invalid, expired or already used.", code="invalid-invite")
            current = db.execute("SELECT role FROM room_members WHERE room_id=? AND principal_id=?", (row["room_id"], principal)).fetchone()
            if not current:
                if db.execute("SELECT COUNT(*) FROM room_members WHERE room_id=?", (row["room_id"],)).fetchone()[0] >= MAX_MEMBERS:
                    raise LimitExceeded("This room is full.", code="room-full")
                db.execute("INSERT INTO room_members VALUES(?,?,?,?)", (row["room_id"], principal, row["role"], self.store.clock()))
            elif RANK[row["role"]] > RANK[current["role"]]:
                db.execute("UPDATE room_members SET role=? WHERE room_id=? AND principal_id=?", (row["role"], row["room_id"], principal))
            db.execute("UPDATE invites SET redeemed_by=?,redeemed_at=? WHERE token_hash=?", (principal, self.store.clock(), token_hash(token)))
            room = db.execute("SELECT * FROM rooms WHERE id=?", (row["room_id"],)).fetchone()
            return {"room_id": room["id"], "document_id": room["document_id"], "role": row["role"] if not current or RANK[row["role"]] > RANK[current["role"]] else current["role"]}

    def comment(self, principal, room_id, body, card_id=None, chapter=None):
        if not isinstance(body, str) or not 1 <= len(body.strip()) <= 1000:
            raise StudioError("A comment has 1–1,000 characters.", code="invalid-comment")
        with self.store.connection(write=True) as db:
            room, _ = self._member_room(db, principal, room_id, "editor")
            if db.execute("SELECT COUNT(*) FROM comments WHERE room_id=?", (room_id,)).fetchone()[0] >= MAX_COMMENTS:
                raise LimitExceeded("This room holds at most 500 comments.", code="comment-limit")
            document = db.execute("SELECT revision,state FROM documents WHERE id=?", (room["document_id"],)).fetchone()
            if card_id is not None and (not isinstance(card_id, str) or card_id not in json.loads(document["state"])["cards"]):
                raise StudioError("Comments attach to a card on the board.", code="invalid-comment")
            if chapter is not None:
                if card_id is not None or not isinstance(chapter, dict) or set(chapter) != {"story_id", "story_revision", "chapter_id"} or type(chapter.get("story_revision")) is not int or chapter["story_revision"] < 1 or any(not isinstance(chapter.get(field), str) or not 1 <= len(chapter[field]) <= 100 for field in ("story_id", "chapter_id")):
                    raise StudioError("Choose one card or a chapter in a saved story revision.", code="invalid-comment")
                saved = db.execute("SELECT r.body FROM story_revisions r JOIN stories s ON s.id=r.story_id WHERE s.id=? AND s.document_id=? AND r.revision=?",
                                   (chapter["story_id"], room["document_id"], chapter["story_revision"])).fetchone()
                if not saved or not any(c["id"] == chapter["chapter_id"] for c in json.loads(saved["body"])["chapters"]):
                    raise StudioError("Chapter comments must cite this room's saved story revision.", code="invalid-comment")
            identifier = "cm_" + secrets.token_urlsafe(10)
            db.execute("INSERT INTO comments(id,room_id,card_id,author_id,body,created,resolved,document_revision,chapter_ref) VALUES(?,?,?,?,?,?,0,?,?)",
                       (identifier, room_id, card_id, principal, body.strip(), self.store.clock(), document["revision"], dumps(chapter) if chapter else None))
            return {"id": identifier, "card_id": card_id, "chapter": chapter, "body": body.strip(), "document_revision": document["revision"]}

    def comments(self, principal, room_id):
        with self.store.connection() as db:
            self._member_room(db, principal, room_id)
            return [{"id": r["id"], "card_id": r["card_id"], "author": r["author_id"][-6:], "mine": r["author_id"] == principal, "body": r["body"],
                     "created": r["created"], "resolved": bool(r["resolved"]), "document_revision": r["document_revision"],
                     "chapter": json.loads(r["chapter_ref"]) if r["chapter_ref"] else None}
                    for r in db.execute("SELECT * FROM comments WHERE room_id=? ORDER BY created", (room_id,))]

    def present(self, principal, room_id, state, expected_epoch):
        """Only the owner or an editor presents; followers read ``presenter`` with the epoch they last saw."""
        if not isinstance(state, dict) or len(dumps(state)) > 4000 or set(state) - {"scene", "card_id", "playing", "position_seconds", "viewer_state", "story_id", "story_revision"}:
            raise StudioError("Presenter state holds scene, card_id, playing, position_seconds and viewer_state.", code="invalid-presenter")
        with self.store.connection(write=True) as db:
            room, role = self._member_room(db, principal, room_id, "editor")
            if state.get("story_id"):
                revision = state.get("story_revision")
                if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
                    raise StudioError("Choose a saved story revision to present.", code="invalid-presenter")
                saved = db.execute("SELECT r.body FROM story_revisions r JOIN stories s ON s.id=r.story_id WHERE s.id=? AND s.document_id=? AND r.revision=?", (state["story_id"], room["document_id"], revision)).fetchone()
                if not saved or not any(c["id"] == state.get("scene") for c in json.loads(saved["body"])["chapters"]):
                    raise StudioError("Presenter chapter must belong to the room’s saved story revision.", code="invalid-presenter")
            current = db.execute("SELECT * FROM presenter_state WHERE room_id=?", (room_id,)).fetchone()
            if current["presenter_id"] not in (None, principal) and expected_epoch != current["epoch"] and role != "owner":
                raise Conflict("Another member is presenting.", code="presenter-conflict", details={"epoch": current["epoch"]})
            epoch = current["epoch"] + 1
            db.execute("UPDATE presenter_state SET presenter_id=?,state=?,epoch=?,updated=? WHERE room_id=?", (principal, dumps(state), epoch, self.store.clock(), room_id))
            return {"epoch": epoch, "presenter": principal[-6:], "state": state}

    def presenter(self, principal, room_id, after_epoch=0):
        with self.store.connection() as db:
            self._member_room(db, principal, room_id)
            row = db.execute("SELECT * FROM presenter_state WHERE room_id=?", (room_id,)).fetchone()
        return {"epoch": row["epoch"], "changed": row["epoch"] > after_epoch, "presenter": (row["presenter_id"] or "")[-6:] or None, "state": json.loads(row["state"])}

    def heartbeat(self, principal, room_id, cursor=None):
        with self.store.connection() as db:
            _, role = self._member_room(db, principal, room_id)
        return {"presence": self.adapter.heartbeat(room_id, principal, role, cursor)}

    def authorize(self, principal, room_id):
        with self.store.connection() as db:
            _, role = self._member_room(db, principal, room_id)
        return self.adapter.authorize(room_id, principal, role)
