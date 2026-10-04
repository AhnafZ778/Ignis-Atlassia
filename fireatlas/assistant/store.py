"""Owner-checked sessions, durable run receipts and atomic cost reservations."""
from __future__ import annotations

import contextlib
import json
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path


def dumps(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False)


class Store:
    def __init__(self, path, daily_limit=4_500_000, session_limit=250_000):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.daily_limit, self.session_limit = daily_limit, session_limit
        with self.connection() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, created REAL, touched REAL, context TEXT, view TEXT);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, session TEXT, nonce TEXT, created REAL, status TEXT, body TEXT, UNIQUE(session,nonce));
            CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY, session TEXT, kind TEXT, created REAL, body TEXT);
            CREATE TABLE IF NOT EXISTS reservations(id TEXT PRIMARY KEY, session TEXT, day TEXT, amount INTEGER, spent INTEGER, state TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, run TEXT, session TEXT, body TEXT);
            CREATE INDEX IF NOT EXISTS artifact_owner ON artifacts(session,kind);
            CREATE TABLE IF NOT EXISTS throttles(key TEXT PRIMARY KEY,started REAL,count INTEGER);
            """)
            # Never replay a possibly billed model request after a crash.
            db.execute("UPDATE runs SET status='failed',body=? WHERE status IN ('queued','running')", (dumps({"error": "Service restarted. Completed evidence remains available; the interrupted provider call was not retried."}),))

    @contextlib.contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def session(self, identifier, touch=True):
        with self.connection() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (identifier,)).fetchone()
            now = time.time()
            if not row or now-row["touched"] > 86400 or now-row["created"] > 604800:
                raise PermissionError("Temporary workspace expired or is unavailable.")
            if touch:
                db.execute("UPDATE sessions SET touched=? WHERE id=?", (now, identifier))
            return {"id": row["id"], "context": json.loads(row["context"]), "view": json.loads(row["view"])}

    def create_session(self, context):
        identifier, now = secrets.token_urlsafe(32), time.time()
        with self.connection() as db:
            db.execute("INSERT INTO sessions VALUES(?,?,?,?,?)", (identifier, now, now, dumps(context), "{}"))
        return identifier

    def update_session(self, identifier, context, view):
        self.session(identifier)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT context,view FROM sessions WHERE id=?", (identifier,)).fetchone()
            old = json.loads(current["view"])
            previous = json.loads(current["context"])
            if context["revision"] < previous["revision"]:
                raise ValueError("Study settings changed in another view. Take control with the latest revision.")
            if old.get("instance") and old.get("instance") != view.get("instance") and time.time()-old.get("updated", 0) < 30 and not view.get("take_control"):
                raise ValueError("This session is active in another view. Choose Control here to transfer it.")
            view["updated"] = time.time()
            db.execute("UPDATE sessions SET context=?,view=? WHERE id=?", (dumps(context), dumps(view), identifier))

    def throttle(self, key, limit=60, seconds=60):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            now=time.time()
            row=db.execute("SELECT * FROM throttles WHERE key=?", (key,)).fetchone()
            if row and now-row["started"]<seconds and row["count"]>=limit:
                raise ValueError("Request allowance reached. Wait briefly before trying again.")
            if not row or now-row["started"]>=seconds:
                db.execute("INSERT OR REPLACE INTO throttles VALUES(?,?,1)",(key,now))
            else: db.execute("UPDATE throttles SET count=count+1 WHERE key=?",(key,))
            db.execute("DELETE FROM throttles WHERE started<?",(now-86400,))

    def update_artifact(self, owner, identifier, kind, value):
        self.get_artifact(owner,identifier,kind)
        with self.connection() as db:
            db.execute("UPDATE artifacts SET body=? WHERE id=? AND session=? AND kind=?",(dumps(value),identifier,owner,kind))

    def purge_expired(self):
        with self.connection() as db:
            ids=[r[0] for r in db.execute("SELECT id FROM sessions WHERE touched<? OR created<?",(time.time()-86400,time.time()-604800))]
            for owner in ids:
                for table in ("artifacts","events","runs"):
                    db.execute(f"DELETE FROM {table} WHERE session=?",(owner,))
                db.execute("DELETE FROM sessions WHERE id=?",(owner,))

    def artifact(self, owner, kind, body):
        self.session(owner)
        identifier = secrets.token_urlsafe(18)
        with self.connection() as db:
            db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?)", (identifier, owner, kind, time.time(), dumps(body)))
        return identifier

    def get_artifact(self, owner, identifier, kind=None):
        self.session(owner)
        with self.connection() as db:
            row = db.execute("SELECT * FROM artifacts WHERE id=? AND session=?", (identifier, owner)).fetchone()
        if not row or (kind and row["kind"] != kind):
            raise PermissionError("Evidence is unavailable in this workspace.")
        return {"id": identifier, "kind": row["kind"], "body": json.loads(row["body"])}

    def artifacts(self, owner, kind=None, limit=100):
        self.session(owner)
        with self.connection() as db:
            rows = db.execute("SELECT * FROM artifacts WHERE session=? AND (? IS NULL OR kind=?) ORDER BY created DESC LIMIT ?", (owner, kind, kind,limit)).fetchall()
        return [{"id": r["id"], "kind": r["kind"], "body": json.loads(r["body"])} for r in rows]

    def delete_artifact(self, owner, identifier):
        self.get_artifact(owner, identifier)
        with self.connection() as db:
            db.execute("DELETE FROM artifacts WHERE session=? AND id=?", (owner, identifier))

    def create_run(self, owner, nonce, request):
        self.session(owner)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT id FROM runs WHERE session=? AND nonce=?", (owner, nonce)).fetchone()
            if existing:
                return existing["id"], False
            if db.execute("SELECT 1 FROM runs WHERE session=? AND status IN ('queued','running')", (owner,)).fetchone():
                raise ValueError("An investigation is already running. Stop it first.")
            if db.execute("SELECT COUNT(*) FROM runs WHERE created>? AND session=?", (time.time()-86400, owner)).fetchone()[0] >= 20:
                raise ValueError("Temporary workspace turn limit reached. Existing results remain available.")
            if db.execute("SELECT COUNT(*) FROM runs WHERE status IN ('queued','running')").fetchone()[0] >= 2:
                raise ValueError("Both analysis slots are busy. Retry after a current investigation finishes.")
            identifier = secrets.token_urlsafe(18)
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?)", (identifier, owner, nonce, time.time(), "queued", dumps(request)))
        return identifier, True

    def run(self, owner, identifier):
        self.session(owner)
        with self.connection() as db:
            row = db.execute("SELECT * FROM runs WHERE id=? AND session=?", (identifier, owner)).fetchone()
        if not row:
            raise PermissionError("Investigation is unavailable in this workspace.")
        return {"id": identifier, "status": row["status"], "body": json.loads(row["body"])}

    def finish(self, owner, identifier, status, body):
        with self.connection() as db:
            db.execute("UPDATE runs SET status=?,body=? WHERE id=? AND session=? AND status!='cancelled'", (status, dumps(body), identifier, owner))

    def cancel(self, owner, identifier):
        self.run(owner, identifier)
        with self.connection() as db:
            db.execute("UPDATE runs SET status='cancelled' WHERE id=? AND session=? AND status IN ('queued','running')", (identifier, owner))

    def event(self, owner, run, value):
        with self.connection() as db:
            db.execute("INSERT INTO events(run,session,body) VALUES(?,?,?)", (run, owner, dumps(value)))

    def events(self, owner, run, after=0):
        self.run(owner, run)
        with self.connection() as db:
            rows = db.execute("SELECT id,body FROM events WHERE run=? AND session=? AND id>? ORDER BY id LIMIT 100", (run, owner, after)).fetchall()
        return [{"id": r["id"], **json.loads(r["body"])} for r in rows]

    def reserve(self, owner, amount):
        if type(amount) is not int or amount <= 0:
            raise ValueError("Provider maximum cost is not configured.")
        self.session(owner)
        today = datetime.now(timezone.utc).date().isoformat()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM reservations WHERE state='overrun'").fetchone():
                raise ValueError('Provider usage exceeded its configured cost ceiling. AI is paused pending operator pricing review; stored-data tools remain available.')
            rows = db.execute("SELECT session,amount,spent,state FROM reservations WHERE day=? OR state='reserved'", (today,)).fetchall()
            total = sum(r["amount"] if r["state"] == "reserved" else r["spent"] for r in rows)
            session = sum(r["amount"] if r["state"] == "reserved" else r["spent"] for r in rows if r["session"] == owner)
            if total+amount > self.daily_limit or session+amount > self.session_limit:
                raise ValueError("AI demo allowance reached. Manual tools and saved evidence remain available.")
            identifier = secrets.token_urlsafe(18)
            db.execute("INSERT INTO reservations VALUES(?,?,?,?,?,?,?)", (identifier, owner, today, amount, 0, "reserved", time.time()))
        return identifier

    def reconcile(self, owner, identifier, actual):
        if actual is None:
            return  # Keep the pessimistic reservation if provider usage is unknown.
        with self.connection() as db:
            row = db.execute("SELECT amount FROM reservations WHERE id=? AND session=? AND state='reserved'", (identifier, owner)).fetchone()
            if not row:
                raise PermissionError("Cost receipt is unavailable.")
            state='overrun' if int(actual)>row['amount'] else 'settled'
            db.execute("UPDATE reservations SET spent=?,state=? WHERE id=?", (max(0, int(actual)),state,identifier))

    def budget(self, owner):
        today = datetime.now(timezone.utc).date().isoformat()
        with self.connection() as db:
            rows = db.execute("SELECT * FROM reservations WHERE day=? OR state='reserved'", (today,)).fetchall()
        cost = lambda r: r["amount"] if r["state"] == "reserved" else r["spent"]
        return {"currency": "USD", "daily_allowance": 5, "executable_limit": self.daily_limit/1e6, "used_or_reserved": sum(map(cost, rows))/1e6, "session_remaining": max(0, self.session_limit-sum(cost(r) for r in rows if r["session"] == owner))/1e6}

    def delete_session(self, owner):
        self.session(owner)
        with self.connection() as db:
            for table in ("artifacts", "events", "runs"):
                db.execute(f"DELETE FROM {table} WHERE session=?", (owner,))
            db.execute("DELETE FROM sessions WHERE id=?", (owner,))
