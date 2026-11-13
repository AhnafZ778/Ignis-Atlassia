"""Whiteboard drawing persistence shares Studio ownership and revision rules."""
import tempfile
import unittest
from pathlib import Path

from fireatlas.studio.errors import Conflict, NotFound, StudioError
from fireatlas.studio.store import StudioStore


def change(identifier, value, position=0):
    return {"kind": "element", "id": identifier, "value": value, "position": position}


class WhiteboardStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = StudioStore(Path(self.tmp.name) / "studio.sqlite3")
        self.owner, _ = self.store.create_principal()
        self.other, _ = self.store.create_principal()
        self.doc = self.store.create_document(self.owner, "Investigation")

    def patch(self, revision, changes, **extra):
        return self.store.apply_transaction(self.owner, self.doc["id"], {
            "base_revision": revision, "ops": [{"op": "patch_whiteboard", "changes": changes}], **extra,
        })

    def test_disjoint_edits_can_merge_and_undo_without_erasing_later_work(self):
        first = self.patch(1, [change("a", {"id": "a", "type": "rectangle", "x": 1})])
        second = self.patch(1, [change("b", {"id": "b", "type": "text", "text": "note"}, 1)], allow_merge=True)
        self.assertTrue(second["merged"])
        with self.assertRaises(Conflict):
            self.patch(1, [change("a", {"id": "a", "type": "rectangle", "x": 2})], allow_merge=True)
        self.store.undo(self.owner, self.doc["id"], transaction_id=first["transaction_id"])
        self.assertEqual([e["id"] for e in self.store.whiteboard(self.owner, self.doc["id"])["elements"]], ["b"])

    def test_undo_conflict_does_not_erase_later_changes_to_same_object(self):
        first = self.patch(1, [change("a", {"id": "a", "type": "text", "text": "first"})])
        self.patch(first["revision"], [change("a", {"id": "a", "type": "text", "text": "later"})])
        with self.assertRaises(Conflict):
            self.store.undo(self.owner, self.doc["id"], transaction_id=first["transaction_id"])
        self.assertEqual(self.store.whiteboard(self.owner, self.doc["id"])["elements"][0]["text"], "later")

    def test_successive_undo_of_the_same_object_skips_cancelled_edit_pairs(self):
        first=self.patch(1,[change('a',{'id':'a','type':'text','text':'first'})])
        self.patch(first['revision'],[change('a',{'id':'a','type':'text','text':'second'})])
        self.store.undo(self.owner,self.doc['id'])
        self.assertEqual(self.store.whiteboard(self.owner,self.doc['id'])['elements'][0]['text'],'first')
        self.store.undo(self.owner,self.doc['id'])
        self.assertEqual(self.store.whiteboard(self.owner,self.doc['id'])['elements'],[])

    def test_redone_change_still_blocks_older_same_object_undo(self):
        first=self.patch(1,[change('a',{'id':'a','type':'text','text':'first'})])
        self.patch(first['revision'],[change('a',{'id':'a','type':'text','text':'second'})])
        self.store.undo(self.owner,self.doc['id']);self.store.redo(self.owner,self.doc['id'])
        with self.assertRaises(Conflict):self.store.undo(self.owner,self.doc['id'],transaction_id=first['transaction_id'])
        self.assertEqual(self.store.whiteboard(self.owner,self.doc['id'])['elements'][0]['text'],'second')

    def test_multiple_undo_and_redo_follow_original_order(self):
        first=self.patch(1,[change('a',{'id':'a','type':'text','text':'one'})])
        second=self.patch(first['revision'],[change('a',{'id':'a','type':'text','text':'two'})])
        self.patch(second['revision'],[change('a',{'id':'a','type':'text','text':'three'})])
        for expected in ['two','one',None]:
            self.store.undo(self.owner,self.doc['id'])
            elements=self.store.whiteboard(self.owner,self.doc['id'])['elements']
            self.assertEqual(elements[0]['text'] if elements else None,expected)
        for expected in ['one','two','three']:
            self.store.redo(self.owner,self.doc['id'])
            self.assertEqual(self.store.whiteboard(self.owner,self.doc['id'])['elements'][0]['text'],expected)

    def test_multi_redo_refuses_an_intervening_independent_edit(self):
        first=self.patch(1,[change('a',{'id':'a','type':'text','text':'one'})])
        self.patch(first['revision'],[change('a',{'id':'a','type':'text','text':'two'})])
        self.store.undo(self.owner,self.doc['id']);undone=self.store.undo(self.owner,self.doc['id'])
        self.patch(undone['revision'],[change('b',{'id':'b','type':'text','text':'keep'})])
        with self.assertRaises(Conflict):self.store.redo(self.owner,self.doc['id'])
        self.assertEqual(self.store.whiteboard(self.owner,self.doc['id'])['elements'][0]['text'],'keep')

    def test_ownership_and_invalid_image_are_checked_atomically(self):
        with self.assertRaises(NotFound):
            self.store.whiteboard(self.other, self.doc["id"])
        bad_file = {"kind": "file", "id": "f", "value": {"id": "f", "dataURL": "data:image/png;base64,YWJj"}, "position": 0}
        with self.assertRaises(StudioError):
            self.patch(1, [change("a", {"id": "a"}), bad_file])
        self.assertEqual(self.store.whiteboard(self.owner, self.doc["id"])["elements"], [])
        self.assertEqual(self.store.get_document(self.owner, self.doc["id"])["revision"], 1)


if __name__ == "__main__":
    unittest.main()
