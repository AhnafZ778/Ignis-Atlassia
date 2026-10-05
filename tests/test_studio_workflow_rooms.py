"""Typed workflows, rooms and collaboration adapters."""
from __future__ import annotations

import copy
import json
import time
import unittest

try:
    from studio_support import StudioCase
except ImportError:  # run as tests.test_studio_*
    from .studio_support import StudioCase

from fireatlas import core
from fireatlas.studio import workflow
from fireatlas.studio.errors import Conflict, Forbidden, LimitExceeded, NotFound, StudioError, Unavailable
from fireatlas.studio.rooms import LoopbackAdapter, Rooms, LiveblocksAdapter


def definition(*extra):
    nodes = [{"id": "op", "type": "operation", "params": {"operation": "research", "arguments": {}}},
             {"id": "jac", "type": "pick", "params": {"path": "/overlap/jaccard"}, "inputs": {"source": "op"}},
             {"id": "pix", "type": "pick", "params": {"path": "/raw_pixels"}, "inputs": {"source": "op"}},
             {"id": "viz", "type": "visualize", "params": {"kind": "bars"}, "inputs": {"data": "jac"}},
             {"id": "card", "type": "card_output", "params": {"card_type": "chart", "title": "Overlap"}, "inputs": {"content": "viz"}}]
    return {"nodes": nodes + list(extra)}


class WorkflowValidationTests(StudioCase):
    def test_valid_workflow_orders_dependencies_first(self):
        order = workflow.validate(definition())
        self.assertLess(order.index("op"), order.index("jac"))
        self.assertLess(order.index("viz"), order.index("card"))

    def test_cycles_unknown_nodes_ports_types_and_size_are_rejected(self):
        cyclic = {"nodes": [{"id": "a", "type": "filter", "inputs": {"data": "b"}}, {"id": "b", "type": "filter", "inputs": {"data": "a"}}]}
        with self.assertRaises(Conflict) as cycle:
            workflow.validate(cyclic)
        self.assertEqual(cycle.exception.code, "cycle")
        for bad in ({"nodes": [{"id": "x", "type": "shell", "params": {}}]},
                    {"nodes": [{"id": "x", "type": "operation", "params": {"operation": "research"}, "inputs": {"bogus": "x"}}]},
                    {"nodes": [{"id": "op", "type": "operation", "params": {"operation": "research"}},
                               {"id": "bad", "type": "compare", "inputs": {"left": "op", "right": "op"}}]},
                    {"nodes": [{"id": "op", "type": "operation", "params": {"operation": "not-real"}}]}):
            with self.assertRaises(StudioError):
                workflow.validate(bad)
        many = {"nodes": [{"id": f"n{i}", "type": "operation", "params": {"operation": "research"}} for i in range(41)]}
        with self.assertRaises(LimitExceeded):
            workflow.validate(many)

    def test_wildcard_pick_is_a_series_and_a_concrete_pick_is_a_scalar(self):
        self.assertEqual(workflow.produced_type({"type": "pick", "params": {"path": "/a/*/b"}}), "series")
        self.assertEqual(workflow.produced_type({"type": "pick", "params": {"path": "/a/b"}}), "scalar")


class WorkflowRunTests(StudioCase):
    def setUp(self):
        super().setUp()
        self.document = self.board()

    def saved(self, definition_value):
        return self.service.save_workflow(self.owner, self.document["id"], definition_value)

    def run_to_end(self, workflow_id):
        run = self.service.run_workflow(self.owner, workflow_id, background=False)
        return self.service.get_run(self.owner, run["id"])

    def test_run_produces_receipts_lineage_and_a_deterministic_cache(self):
        saved = self.saved(definition())
        first = self.run_to_end(saved["id"])
        self.assertEqual(first["status"], "completed", first)
        self.assertTrue(all(not r["cache_hit"] for r in first["receipts"]))
        draft = first["outputs"]["card"]["draft"]
        self.assertEqual(draft["type"], "chart")
        self.assertTrue(first["outputs"]["card"]["lineage"][0]["receipt_sha256"])
        second = self.run_to_end(saved["id"])
        self.assertTrue(all(r["cache_hit"] for r in second["receipts"]))
        self.assertEqual({r["node"]: r["output_sha256"] for r in first["receipts"]}, {r["node"]: r["output_sha256"] for r in second["receipts"]})

    def test_cache_is_invalidated_by_a_new_release(self):
        saved = self.saved(definition())
        self.run_to_end(saved["id"])
        with core.connect(self.database) as db:
            db.execute("UPDATE batches SET row_count=row_count+3")
        after = self.run_to_end(saved["id"])
        self.assertEqual(after["status"], "completed")
        self.assertFalse(any(r["cache_hit"] for r in after["receipts"]))

    def test_incompatible_units_fail_before_a_number_is_produced(self):
        extra = {"id": "cmp", "type": "compare", "params": {"mode": "difference"}, "inputs": {"left": "jac", "right": "pix"}}
        saved = self.saved(definition(extra))
        result = self.run_to_end(saved["id"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("Incompatible units", result["error"])
        same = {"id": "cmp", "type": "compare", "params": {"mode": "difference"}, "inputs": {"left": "jac", "right": "jac"}}
        ok = self.service.save_workflow(self.owner, self.document["id"], definition(same), expected_revision=1)
        completed = self.run_to_end(ok["id"])
        self.assertEqual(completed["status"], "completed", completed)
        self.assertEqual(completed["outputs"]["cmp"]["rows"][-1]["value"], 0)

    def test_workflow_saves_are_revision_checked(self):
        saved = self.saved(definition())
        self.service.save_workflow(self.owner, self.document["id"], definition(), expected_revision=1)
        with self.assertRaises(Conflict):
            self.service.save_workflow(self.owner, self.document["id"], definition(), expected_revision=1)

    def test_a_late_result_is_discarded_when_the_board_changed(self):
        saved = self.saved(definition())
        original = self.service.science.call
        document_id = self.document["id"]

        def changing(owner, operation, context, arguments=None, *rest, **kw):
            current = self.service.get_document(self.owner, document_id)
            self.service.transact(self.owner, document_id, {"base_revision": current["revision"], "ops": [{"op": "set_title", "title": "Changed while running"}]})
            return original(owner, operation, context, arguments, *rest, **kw)
        self.service.science.call = changing
        result = self.run_to_end(saved["id"])
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["outputs"], {})

    def test_a_workflow_cannot_exceed_eight_scientific_calls(self):
        nodes = [{"id": f"o{i}", "type": "operation", "params": {"operation": "observations", "arguments": {"limit": i + 1}}} for i in range(9)]
        saved = self.saved({"nodes": nodes})
        result = self.run_to_end(saved["id"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("at most 8", result["error"])

    def test_another_browser_cannot_read_or_run_a_workflow(self):
        saved = self.saved(definition())
        with self.assertRaises(NotFound):
            self.service.get_workflow(self.other, saved["id"])
        with self.assertRaises(NotFound):
            self.service.run_workflow(self.other, saved["id"], background=False)

    def test_completed_output_adds_checked_cards_and_is_undoable(self):
        saved = self.saved(definition())
        run = self.run_to_end(saved["id"])
        applied = self.service.apply_workflow_output(self.owner, run['id'], 'card', self.document['revision'])
        card = applied['document']['state']['cards'][applied['created_cards'][0]]
        report = self.service.snapshot_report(self.owner, self.document['id'], card['snapshot_id'])
        self.assertTrue(report['verification']['verified'])
        self.assertEqual(report['snapshot']['facts'][0]['path'], '/overlap/jaccard')
        self.assertEqual(report['snapshot']['facts'][0]['unit'], 'ratio')
        undone = self.service.store.undo(self.owner, self.document['id'])
        self.assertFalse(undone['state']['cards'])
        with self.assertRaises(Conflict):
            self.service.apply_workflow_output(self.owner, run['id'], 'card', undone['revision'])

    def test_findings_recipe_creates_real_editable_story_without_starting_video(self):
        recipe = next(t for t in workflow.templates() if t['id'] == 'findings-to-story')
        run = self.run_to_end(self.saved(recipe['definition'])['id'])
        self.assertEqual(run['status'], 'completed', run)
        applied = self.service.apply_workflow_output(self.owner, run['id'], 'story', self.document['revision'])
        self.assertEqual(len(applied['story']['body']['chapters']), 6)
        resolved = self.service.resolve_story(self.owner, applied['story']['id'])['resolved']
        self.assertTrue(resolved['snapshots'])
        self.assertFalse(any(w['problem'] == 'evidence-unfrozen' for w in resolved['warnings']))
        with self.service.store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM renders').fetchone()[0], 0)

    def test_live_progress_retains_completed_node_receipts(self):
        seen = []
        saved = self.saved(definition())
        original = workflow.WorkflowRunner.__init__
        def initialize(runner, *args, **kw):
            callback = kw['progress']
            kw['progress'] = lambda outputs, receipts: (seen.append(len(receipts)), callback(outputs, receipts))
            original(runner, *args, **kw)
        from unittest.mock import patch
        with patch.object(workflow.WorkflowRunner, '__init__', initialize):
            self.run_to_end(saved['id'])
        self.assertEqual(seen, [1, 2, 3, 4, 5])


class RoomTests(StudioCase):
    def setUp(self):
        super().setUp()
        self.clock = [1000.0]
        self.adapter = LoopbackAdapter(lambda: self.clock[0])
        self.service.rooms = Rooms(self.service.store, self.adapter)
        self.rooms = self.service.rooms
        self.document = self.add_card(self.board(), "a")
        self.room = self.rooms.create(self.owner, self.document["id"])

    def member(self, role):
        principal, _ = self.service.store.create_principal()
        invite = self.rooms.invite(self.owner, self.room["id"], role)
        self.rooms.redeem(principal, invite["token"])
        return principal

    def test_chapter_comments_remain_bound_to_an_owned_saved_revision(self):
        editor, viewer = self.member("editor"), self.member("viewer")
        story = self.service.create_story(self.owner, self.document["id"], {"title": "Review this chapter", "chapters": [
            {"id": "first", "title": "The evidence", "card_id": "a", "duration_seconds": 20}]})
        target = {"story_id": story["id"], "story_revision": story["revision"], "chapter_id": "first"}
        line = self.rooms.comment(editor, self.room["id"], "Inspect the frozen source states.", chapter=target)
        self.assertEqual(line["chapter"], target)
        self.assertEqual(self.rooms.comments(viewer, self.room["id"])[0]["chapter"], target)
        with self.assertRaises(Forbidden):
            self.rooms.comment(viewer, self.room["id"], "Not an editor.", chapter=target)
        for bad in ({**target, "chapter_id": "missing"}, {**target, "story_revision": True}, {**target, "story_id": {}}, {**target, "story_revision": 999}):
            with self.assertRaises(StudioError):
                self.rooms.comment(editor, self.room["id"], "Invalid chapter", chapter=bad)
        other = self.service.create_story(self.owner, self.board()["id"], {"title": "Another board", "chapters": [{"id": "first", "duration_seconds": 20}]})
        with self.assertRaises(StudioError):
            self.rooms.comment(editor, self.room["id"], "Cross-board chapter", chapter={**target, "story_id": other["id"]})
        with self.assertRaises(StudioError):
            self.rooms.comment(editor, self.room["id"], "Ambiguous target", card_id="a", chapter=target)

    def test_collaboration_is_unavailable_without_credentials(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"LIVEBLOCKS_SECRET_KEY": "", "FIREATLAS_STUDIO_COLLAB": ""}):
            rooms = Rooms(self.service.store, LiveblocksAdapter())
            document = self.board()
            with self.assertRaises(Unavailable):
                rooms.create(self.owner, document["id"])

    def test_invites_are_single_use_hashed_and_expire(self):
        invite = self.rooms.invite(self.owner, self.room["id"], "editor")
        self.assertTrue(invite["token"].startswith("inv_"))
        with self.service.store.connection() as db:
            stored = " ".join(str(v) for row in db.execute("SELECT * FROM invites") for v in tuple(row))
        self.assertNotIn(invite["token"], stored)
        joined = self.rooms.redeem(self.other, invite["token"])
        self.assertEqual(joined["role"], "editor")
        third, _ = self.service.store.create_principal()
        with self.assertRaises(Forbidden):
            self.rooms.redeem(third, invite["token"])
        with self.assertRaises(Forbidden):
            self.rooms.redeem(third, "inv_unknown")
        short = self.rooms.invite(self.owner, self.room["id"], "viewer", ttl=60)
        self.service.store.clock = lambda: time.time() + 3600
        with self.assertRaises(Forbidden):
            self.rooms.redeem(third, short["token"])
        with self.assertRaises(StudioError):
            self.rooms.invite(self.owner, self.room["id"], "owner")

    def test_roles_gate_editing_and_commenting(self):
        editor, viewer = self.member("editor"), self.member("viewer")
        edited = self.service.transact(editor, self.document["id"], {"base_revision": self.document["revision"],
                                                                      "ops": [{"op": "update_card", "id": "a", "patch": {"title": "by editor"}}]})
        self.assertEqual(edited["state"]["cards"]["a"]["title"], "by editor")
        self.assertEqual(self.service.get_document(viewer, self.document["id"])["role"], "viewer")
        with self.assertRaises(Forbidden):
            self.service.transact(viewer, self.document["id"], {"base_revision": edited["revision"], "ops": [{"op": "set_title", "title": "no"}]})
        with self.assertRaises(Forbidden):
            self.rooms.comment(viewer, self.room["id"], "viewers only read")
        with self.assertRaises(Forbidden):
            self.rooms.invite(editor, self.room["id"], "viewer")
        comment = self.rooms.comment(editor, self.room["id"], "Check this unit.", "a")
        self.assertEqual(comment["card_id"], "a")
        self.assertEqual(len(self.rooms.comments(viewer, self.room["id"])), 1)
        with self.assertRaises(StudioError):
            self.rooms.comment(editor, self.room["id"], "bad card", "missing")
        with self.assertRaises(NotFound):
            self.rooms.comments(self.other, self.room["id"])
        with self.assertRaises(NotFound):
            self.service.get_document(self.other, self.document["id"])

    def test_loopback_presence_expires_and_never_carries_full_identities(self):
        editor = self.member("editor")
        self.rooms.heartbeat(self.owner, self.room["id"], {"x": 1, "y": 2})
        seen = self.rooms.heartbeat(editor, self.room["id"])["presence"]
        self.assertEqual(len(seen), 2)
        self.assertNotIn(self.owner, json.dumps(seen))
        self.clock[0] += 120
        self.assertEqual(self.adapter.presence(self.room["id"]), [])

    def test_presenter_state_is_ordered_by_epoch_and_viewers_follow(self):
        editor, viewer = self.member("editor"), self.member("viewer")
        first = self.rooms.present(self.owner, self.room["id"], {"scene": "chapter-1", "playing": True}, 0)
        self.assertEqual(first["epoch"], 1)
        with self.assertRaises(Conflict):
            self.rooms.present(editor, self.room["id"], {"scene": "chapter-2"}, 0)
        with self.assertRaises(Forbidden):
            self.rooms.present(viewer, self.room["id"], {"scene": "chapter-3"}, 1)
        followed = self.rooms.presenter(viewer, self.room["id"], after_epoch=0)
        self.assertTrue(followed["changed"])
        self.assertEqual(followed["state"]["scene"], "chapter-1")
        self.assertFalse(self.rooms.presenter(viewer, self.room["id"], after_epoch=1)["changed"])
        with self.assertRaises(StudioError):
            self.rooms.present(self.owner, self.room["id"], {"script": "x"}, 1)

    def test_presented_chapter_is_bound_to_the_room_and_saved_story_revision(self):
        story = self.service.create_story(self.owner, self.document['id'], {})
        state = {'story_id': story['id'], 'story_revision': story['revision'], 'scene': story['body']['chapters'][0]['id'], 'viewer_state': 'story'}
        presented = self.rooms.present(self.owner, self.room['id'], state, 0)
        self.assertEqual(presented['state']['story_revision'], 1)
        for patch in ({'story_revision': 999}, {'scene': 'not-a-chapter'}, {'story_revision': True}):
            with self.subTest(patch=patch), self.assertRaises(StudioError):
                self.rooms.present(self.owner, self.room['id'], {**state, **patch}, 1)
        another = self.service.create_story(self.owner, self.board()['id'], {})
        with self.assertRaises(StudioError):
            self.rooms.present(self.owner, self.room['id'], {**state, 'story_id': another['id']}, 1)

    def test_room_membership_limits_and_authorization(self):
        for _ in range(24):
            self.member("viewer")
        extra, _ = self.service.store.create_principal()
        invite = self.rooms.invite(self.owner, self.room["id"], "viewer")
        with self.assertRaises(LimitExceeded):
            self.rooms.redeem(extra, invite["token"])
        self.assertEqual(self.rooms.authorize(self.owner, self.room["id"])["role"], "owner")


if __name__ == "__main__":
    unittest.main()

class LiveblocksAuthorizationTests(unittest.TestCase):
    def test_signed_authorization_scopes_roles_to_one_room_and_fails_closed(self):
        import os
        from unittest.mock import patch
        import io
        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *args): self.close()
        requests = []
        def transport(request, timeout):
            requests.append(request)
            return Response(b'{"token":"signed-test-token"}')
        with patch.dict(os.environ, {'LIVEBLOCKS_SECRET_KEY': 'sk_test_not_a_real_credential'}), patch('urllib.request.urlopen', side_effect=transport):
            adapter = LiveblocksAdapter()
            self.assertEqual(adapter.authorize('room-owned', 'principal-owned', 'viewer')['token'], 'signed-test-token')
            self.assertEqual(json.loads(requests[0].data)['permissions'], {'room-owned': ['*:read']})
            adapter.authorize('room-owned', 'principal-owned', 'editor')
            self.assertEqual(json.loads(requests[1].data)['permissions'], {'room-owned': ['*:write']})
        with patch.dict(os.environ, {'LIVEBLOCKS_SECRET_KEY': 'sk_test_not_a_real_credential'}), patch('urllib.request.urlopen', return_value=Response(b'{}')):
            with self.assertRaises(Unavailable): LiveblocksAdapter().authorize('room', 'principal', 'viewer')
