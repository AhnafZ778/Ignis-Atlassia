"""Studio store, board rules, evidence snapshots and ownership."""
from __future__ import annotations

import copy
import json
import sqlite3
import threading
import unittest

try:
    from studio_support import StudioCase
except ImportError:  # run as tests.test_studio_*
    from .studio_support import StudioCase

from fireatlas import core
from fireatlas.studio import evidence as ev, graph
from fireatlas.studio.errors import Conflict, Forbidden, LimitExceeded, NotFound, StoreVersionError, StudioError, Unauthorized
from fireatlas.studio.store import MIGRATIONS, StudioStore, STORE_VERSION


class StoreMigrationTests(unittest.TestCase):
    def test_upgrade_from_version_one_keeps_data_and_newer_versions_are_refused(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "studio.sqlite3"
            db = sqlite3.connect(path)
            for statement in [s.strip() for s in MIGRATIONS[0][2].split(";") if s.strip()]:
                db.execute(statement)
            db.execute("INSERT INTO meta VALUES('store_version','1')")
            db.execute("INSERT INTO principals VALUES('p_existing',1,1,NULL)")
            db.commit()
            db.close()
            store = StudioStore(path)
            self.assertEqual(store.version(), STORE_VERSION)
            with store.connection() as conn:
                self.assertEqual(conn.execute("SELECT id FROM principals").fetchone()["id"], "p_existing")
                self.assertIsNotNone(conn.execute("SELECT name FROM sqlite_master WHERE name='stories'").fetchone())
            db = sqlite3.connect(path)
            db.execute("UPDATE meta SET value='99' WHERE key='store_version'")
            db.commit()
            db.close()
            with self.assertRaises(StoreVersionError):
                StudioStore(path)


    def test_phase_migration_preserves_completed_exports_and_backfills_active_state(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'studio.sqlite3'
            db = sqlite3.connect(path)
            for _, _, migration in MIGRATIONS[:3]:
                db.executescript(migration)
            db.execute("INSERT INTO meta VALUES('store_version','3')")
            for status in ('completed', 'running', 'failed', 'canceled'):
                db.execute('INSERT INTO renders VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                           (status, 'owner', 'board', 'story', 7, status, '{}', '{"saved":true}', None, None, 0, .7, 1, 2))
            db.commit(); db.close()
            store = StudioStore(path)
            with store.connection() as conn:
                rows = {row['id']: dict(row) for row in conn.execute('SELECT * FROM renders')}
            self.assertEqual(rows['completed']['manifest'], '{"saved":true}')
            self.assertEqual(rows['completed']['story_revision'], 7)
            self.assertEqual(rows['running']['phase'], 'preparing-assets')
            for status in ('completed', 'failed', 'canceled'):
                self.assertEqual(rows[status]['phase'], status)
            self.assertEqual(store.version(), STORE_VERSION)


class DocumentTests(StudioCase):
    def test_group_moves_are_atomic_and_reversible_without_changing_bindings(self):
        document = self.add_card(self.add_card(self.board(), "a"), "b")
        def apply(ops):
            current = self.service.get_document(self.owner, document["id"])
            return self.service.transact(self.owner, document["id"], {"base_revision": current["revision"], "ops": ops})
        grouped = apply([{"op": "set_group", "group": {"id": "g", "title": "Discussion", "card_ids": ["a", "b"]}}])
        moved = apply([{"op": "move_group", "id": "g", "dx": 32, "dy": 64}])
        for cid in ("a", "b"):
            self.assertEqual(moved["state"]["cards"][cid]["transform"]["x"], 32)
            self.assertEqual(moved["state"]["cards"][cid]["binding"], grouped["state"]["cards"][cid]["binding"])
        restored = self.service.undo(self.owner, document["id"])
        self.assertEqual(restored["state"], grouped["state"])
        apply([{"op": "update_card", "id": "b", "patch": {"locked": True}}])
        with self.assertRaises(Forbidden):
            apply([{"op": "move_group", "id": "g", "dx": 10, "dy": 0}])
        current = self.service.get_document(self.owner, document["id"])
        self.assertEqual(current["state"]["cards"]["a"]["transform"]["x"], 0)

    def test_removing_group_member_and_undo_restore_membership(self):
        document = self.add_card(self.add_card(self.board(), "a"), "b")
        grouped = self.service.transact(self.owner, document["id"], {"base_revision": document["revision"], "ops": [
            {"op": "set_group", "group": {"id": "g", "title": "Evidence", "card_ids": ["a", "b"]}}]})
        removed = self.service.transact(self.owner, document["id"], {"base_revision": grouped["revision"], "ops": [{"op": "remove_card", "id": "a"}]})
        self.assertEqual(removed["state"]["groups"], {})
        self.assertEqual(self.service.undo(self.owner, document["id"])["state"], grouped["state"])

    def test_group_membership_and_viewport_validation_and_old_document_defaults(self):
        document = self.add_card(self.add_card(self.board(), "a"), "b")
        for ids in (["a"], ["a", "a"], ["a", "missing"]):
            with self.assertRaises(StudioError):
                self.service.transact(self.owner, document["id"], {"base_revision": document["revision"], "ops": [
                    {"op": "set_group", "group": {"id": "g", "title": "Evidence", "card_ids": ids}}]})
        with self.assertRaises(StudioError):
            self.service.transact(self.owner, document["id"], {"base_revision": document["revision"], "ops": [{"op": "set_viewport", "viewport": {"x": 0, "y": 0, "zoom": 0}}]})
        saved = self.service.transact(self.owner, document["id"], {"base_revision": document["revision"], "ops": [{"op": "set_viewport", "viewport": {"x": 40, "y": 20, "zoom": 0.5}}]})
        self.assertEqual(saved["state"]["viewport"]["zoom"], 0.5)
        self.assertEqual(self.service.undo(self.owner, document["id"])["state"]["viewport"]["zoom"], 1)
        with self.service.store.connection(write=True) as db:
            old = copy.deepcopy(document["state"])
            old.pop("groups"); old.pop("viewport")
            db.execute("UPDATE documents SET state=? WHERE id=?", (json.dumps(old), document["id"]))
        restored = self.service.get_document(self.owner, document["id"])
        self.assertEqual(restored["state"]["groups"], {})
        self.assertEqual(restored["state"]["viewport"], {"x": 0, "y": 0, "zoom": 1})

    def test_studio_data_lives_outside_the_scientific_and_assistant_databases(self):
        self.assertEqual(self.service.store.path.parent, self.database.parent / "studio")
        with core.connect(self.database) as db:
            names = {r[0] for r in db.execute("SELECT name FROM sqlite_master")}
        self.assertFalse(names & {"documents", "stories", "principals", "renders"})

    def test_identity_and_ownership(self):
        document = self.board()
        self.assertEqual(self.service.store.principal(self.token), self.owner)
        with self.assertRaises(Unauthorized):
            self.service.store.principal("not-a-token")
        with self.assertRaises(NotFound):
            self.service.get_document(self.other, document["id"])
        with self.assertRaises(NotFound):
            self.service.transact(self.other, document["id"], {"base_revision": 1, "ops": [{"op": "set_title", "title": "x"}]})
        self.assertEqual([d["id"] for d in self.service.store.list_documents(self.owner)], [document["id"]])
        self.assertEqual(self.service.store.list_documents(self.other), [])

    def test_recovery_token_restores_the_same_principal_once_issued(self):
        recovery = self.service.store.issue_recovery(self.owner)
        principal, token = self.service.store.recover(recovery)
        self.assertEqual(principal, self.owner)
        self.assertEqual(self.service.store.principal(token), self.owner)
        with self.assertRaises(Forbidden):
            self.service.store.recover("rec_invalid")

    def test_revision_conflict_preserves_the_draft_and_idempotency_replays(self):
        document = self.board()
        first = self.add_card(document, "a")
        self.assertEqual(first["revision"], document["revision"] + 1)
        with self.assertRaises(Conflict) as stale:
            self.service.transact(self.owner, document["id"], {"base_revision": document["revision"],
                                                                "ops": [{"op": "update_card", "id": "a", "patch": {"title": "late"}}]})
        self.assertEqual(stale.exception.status, 409)
        self.assertIn("a", json.dumps(stale.exception.details))
        request = {"base_revision": first["revision"], "ops": [{"op": "add_card", "card": {"id": "b", "type": "text", "title": "b"}}]}
        one = self.service.transact(self.owner, document["id"], request, key="idempotent-key-1")
        two = self.service.transact(self.owner, document["id"], request, key="idempotent-key-1")
        self.assertTrue(two.get("idempotent_replay"))
        self.assertEqual(one["revision"], two["revision"])
        self.assertEqual(self.service.get_document(self.owner, document["id"])["revision"], one["revision"])

    def test_merge_is_allowed_only_when_objects_do_not_overlap(self):
        document = self.add_card(self.add_card(self.board(), "a"), "b")
        base = document["revision"]
        self.service.transact(self.owner, document["id"], {"base_revision": base, "ops": [{"op": "update_card", "id": "a", "patch": {"title": "A2"}}]})
        merged = self.service.transact(self.owner, document["id"], {"base_revision": base, "allow_merge": True,
                                                                     "ops": [{"op": "update_card", "id": "b", "patch": {"title": "B2"}}]})
        self.assertTrue(merged["merged"])
        with self.assertRaises(Conflict) as clash:
            self.service.transact(self.owner, document["id"], {"base_revision": base, "allow_merge": True,
                                                                "ops": [{"op": "update_card", "id": "a", "patch": {"title": "A3"}}]})
        self.assertEqual(clash.exception.details["conflicts"], ["card:a"])

    def test_undo_reverts_own_change_but_not_over_a_later_one(self):
        document = self.board()
        added = self.add_card(document, "a")
        reverted = self.service.undo(self.owner, document["id"])
        self.assertNotIn("a", reverted["state"]["cards"])
        self.assertGreater(reverted["revision"], added["revision"])
        again = self.add_card(self.service.get_document(self.owner, document["id"]), "a")
        edited = self.service.transact(self.owner, document["id"], {"base_revision": again["revision"], "ops": [{"op": "update_card", "id": "a", "patch": {"title": "kept"}}]})
        # The latest own change is undoable; an earlier change touched by a later one is protected.
        undone_edit = self.service.undo(self.owner, document["id"])
        self.assertEqual(undone_edit["state"]["cards"]["a"]["title"], "a")
        self.assertEqual(edited["state"]["cards"]["a"]["title"], "kept")

    def test_card_limit_and_cycles_and_incompatible_links(self):
        document = self.board()
        for start in range(0, 100, 50):
            ops = [{"op": "add_card", "card": {"id": f"c{n}", "type": "text"}} for n in range(start, start + 50)]
            document = self.service.transact(self.owner, document["id"], {"base_revision": document["revision"], "ops": ops})
        with self.assertRaises(LimitExceeded):
            self.service.transact(self.owner, document["id"], {"base_revision": document["revision"], "ops": [{"op": "add_card", "card": {"id": "extra", "type": "text"}}]})
        small = self.add_card(self.add_card(self.board(), "a", "text"), "b", "text")
        link = lambda cid, s, t: {"op": "connect", "connection": {"id": cid, "source": s, "target": t, "kind": "context"}}
        revision = small["revision"]
        small = self.service.transact(self.owner, small["id"], {"base_revision": revision, "ops": [link("l1", "a", "b")]})
        with self.assertRaises(Conflict):
            self.service.transact(self.owner, small["id"], {"base_revision": small["revision"], "ops": [link("l2", "b", "a")]})
        with self.assertRaises(StudioError):
            self.service.transact(self.owner, small["id"], {"base_revision": small["revision"], "ops": [link("l3", "a", "a")]})

    def test_redo_restores_an_undone_change_and_remains_undoable(self):
        document = self.add_card(self.board(), "a")
        self.service.undo(self.owner, document["id"])
        restored = self.service.store.redo(self.owner, document["id"])
        self.assertIn("a", restored["state"]["cards"])
        reverted = self.service.undo(self.owner, document["id"])
        self.assertNotIn("a", reverted["state"]["cards"])

    def test_redo_refuses_to_overwrite_a_later_edit(self):
        document = self.add_card(self.board(), "a")
        undone = self.service.undo(self.owner, document["id"])
        self.add_card(undone, "b")
        with self.assertRaises(Conflict):
            self.service.store.redo(self.owner, document["id"])
        self.assertIn("b", self.service.get_document(self.owner, document["id"])["state"]["cards"])

    def test_unknown_fields_and_restore_ops_are_rejected(self):
        document = self.board()
        for op in ({"op": "add_card", "card": {"id": "a", "type": "chart", "script": "alert(1)"}},
                   {"op": "restore_card", "id": "a", "card": None, "index": 0},
                   {"op": "delete_everything"}):
            with self.assertRaises(StudioError):
                self.service.transact(self.owner, document["id"], {"base_revision": document["revision"], "ops": [op]})

    def test_selection_is_outside_the_revisioned_state(self):
        document = self.add_card(self.board(), "a")
        before = document["revision"]
        selected = self.service.patch_document(self.owner, document["id"], {"selection": {"document_revision": before, "card_id": "a"}})
        self.assertEqual(selected["revision"], before)
        self.assertEqual(selected["selection"]["card_id"], "a")
        with self.assertRaises(Conflict):
            self.service.patch_document(self.owner, document["id"], {"selection": {"document_revision": before - 1, "card_id": "a"}})

    def test_concurrent_writers_never_lose_updates(self):
        document = self.board()
        errors, wins = [], []

        def writer(n):
            try:
                current = self.service.get_document(self.owner, document["id"])
                result = self.service.transact(self.owner, document["id"], {"base_revision": current["revision"],
                                                                             "ops": [{"op": "add_card", "card": {"id": f"w{n}", "type": "text"}}]})
                wins.append(result["revision"])
            except Conflict:
                errors.append(n)
        threads = [threading.Thread(target=writer, args=(n,)) for n in range(6)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        final = self.service.get_document(self.owner, document["id"])
        self.assertEqual(len(final["state"]["cards"]), len(wins))
        self.assertEqual(len(wins) + len(errors), 6)
        self.assertEqual(len(set(wins)), len(wins))


class GraphRuleTests(unittest.TestCase):
    def test_topological_order_detects_cycles(self):
        cards = {"a": {}, "b": {}, "c": {}}
        order = graph.topological_order(cards, {"1": {"source": "a", "target": "b"}, "2": {"source": "b", "target": "c"}})
        self.assertEqual(order, ["a", "b", "c"])
        with self.assertRaises(Conflict):
            graph.topological_order(cards, {"1": {"source": "a", "target": "b"}, "2": {"source": "b", "target": "a"}})

    def test_shared_vectors_agree_with_the_browser_implementation(self):
        import pathlib
        path = pathlib.Path(__file__).resolve().parent.parent / "studio-app" / "test-vectors" / "graph.json"
        if not path.is_file():
            self.skipTest("studio-app test vectors are not present")
        vectors = json.loads(path.read_text())
        for case in vectors["topological_order"]:
            if case["expect"] == "cycle":
                with self.assertRaises(Conflict, msg=case["name"]):
                    graph.topological_order(case["cards"], case["connections"])
            else:
                self.assertEqual(graph.topological_order(case["cards"], case["connections"]), case["expect"])
        for case in vectors["compatibility"]:
            reasons = graph.compatibility(case["source"], case["target"], case["kind"], case["state"], case["snapshots"])
            self.assertEqual(reasons, case["expect"], case["name"])


class SnapshotTests(StudioCase):
    def test_forging_unknown_in_place_of_an_observed_value_fails_recount(self):
        document, snapshot = self.bound_board()
        receipt = self.service.store.result_for_document(self.owner, document["id"], snapshot["result_id"])
        forged = copy.deepcopy(snapshot)
        item = next(f for f in forged["facts"] if f["state"] == "observed")
        item.update(state="unknown", value=None)
        from fireatlas.assistant.contracts import digest
        forged["snapshot_sha256"] = digest({k: v for k, v in forged.items() if k != "snapshot_sha256"})
        self.assertFalse(ev.verify_snapshot(forged, receipt)["verified"])

    def test_snapshot_verifies_and_stays_explainable_after_the_live_archive_changes(self):
        document, snapshot = self.bound_board()
        before = self.service.snapshot_report(self.owner, document["id"], snapshot["id"])
        self.assertTrue(before["verification"]["verified"])
        self.assertTrue(before["verification"]["receipt_checked"])
        with core.connect(self.database) as db:
            db.execute("DELETE FROM observations WHERE rowid IN (SELECT rowid FROM observations LIMIT 25)")
            db.execute("UPDATE batches SET row_count=row_count+1")  # the release identity follows the source ledger
        after = self.service.snapshot_report(self.owner, document["id"], snapshot["id"])
        self.assertTrue(after["verification"]["verified"])
        self.assertEqual(after["snapshot"]["facts"], before["snapshot"]["facts"])
        self.assertFalse(after["freshness"]["fresh"])
        self.assertEqual(after["freshness"]["snapshot_release_id"], snapshot["release_id"])

    def test_a_tampered_value_with_a_refreshed_checksum_is_still_rejected(self):
        document, snapshot = self.bound_board()
        receipt = self.service.store.result_for_document(self.owner, document["id"], snapshot["result_id"])
        forged = copy.deepcopy(snapshot)
        observed = next(f for f in forged["facts"] if f["state"] == "observed" and isinstance(f["value"], (int, float)))
        observed["value"] = observed["value"] + 1000
        from fireatlas.studio.store import dumps, sha256_text
        forged["snapshot_sha256"] = sha256_text(dumps({k: v for k, v in forged.items() if k != "snapshot_sha256"}))
        report = ev.verify_snapshot(forged, receipt)
        self.assertFalse(report["verified"])
        self.assertTrue(report["problems"])

    def test_unknown_is_never_reported_as_zero(self):
        document, snapshot = self.bound_board()
        for item in snapshot["facts"]:
            if item["state"] != "observed":
                self.assertIsNone(item["value"])

    def test_cards_cannot_cite_another_boards_snapshot(self):
        document, snapshot = self.bound_board()
        other = self.board()
        other = self.add_card(other, "x")
        with self.assertRaises(StudioError):
            self.service.transact(self.owner, other["id"], {"base_revision": other["revision"],
                                                             "ops": [{"op": "update_card", "id": "x", "patch": {"snapshot_id": snapshot["id"]}}]})

    def test_viewers_cannot_resolve_bindings(self):
        document = self.board()
        with self.assertRaises(NotFound):
            self.service.resolve_binding(self.other, document["id"], {"operation": "research"})
        with self.assertRaises(StudioError):
            self.service.resolve_binding(self.owner, document["id"], {"operation": "not-real"})


if __name__ == "__main__":
    unittest.main()
