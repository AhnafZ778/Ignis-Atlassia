"""Shared fixtures for the Research Studio tests: a temporary demonstration archive and a Studio service."""
from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from fireatlas import core
from fireatlas.demo import BBOX, make_demo
from fireatlas.studio.service import StudioService


class StudioCase(unittest.TestCase):
    """Builds a throwaway archive (marked as authentic so Science.call accepts it) plus an isolated Studio store."""

    study = {"context": {"year": 2015, "month": 7, "bbox": list(BBOX)}}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.database = self.root / "study.sqlite3"
        with contextlib.redirect_stdout(io.StringIO()):
            make_demo(self.root / "fixtures", self.database)
        with core.connect(self.database) as db:
            db.execute("UPDATE batches SET demo=0")
        self.service = StudioService(self.database)
        self.addCleanup(self.service.close)
        self.owner, self.token = self.service.store.create_principal()
        self.other, self.other_token = self.service.store.create_principal()

    def board(self, principal=None, title="Test board"):
        return self.service.create_document(principal or self.owner, {"title": title, "study": self.study})

    def add_card(self, document, card_id="c1", kind="chart", principal=None, **extra):
        return self.service.transact(principal or self.owner, document["id"], {
            "base_revision": document["revision"],
            "ops": [{"op": "add_card", "card": {"id": card_id, "type": kind, "title": card_id, **extra}}]})

    def bound_board(self, operation="research", kind="chart"):
        """A board with one evidence card bound to a frozen snapshot of ``operation``."""
        document = self.board()
        document = self.add_card(document, "c1", kind=kind)
        resolved = self.service.resolve_binding(self.owner, document["id"], {"operation": operation, "context": {}, "arguments": {}})
        snapshot = resolved["snapshot"]
        document = self.service.transact(self.owner, document["id"], {
            "base_revision": document["revision"],
            "ops": [{"op": "update_card", "id": "c1", "patch": {"snapshot_id": snapshot["id"], "binding": {"operation": operation, "context": {}, "arguments": {}}}}]})
        return document, snapshot
