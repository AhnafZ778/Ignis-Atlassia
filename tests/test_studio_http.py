"""Studio HTTP boundary: identity cookie, same-origin checks, route behaviour and static allowlists."""
from __future__ import annotations

import base64
import contextlib
import io
import json
import tempfile
import threading
import unittest
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from fireatlas import core
from fireatlas.demo import BBOX, make_demo
from fireatlas.web import handler_factory

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 20


class Client:
    def __init__(self, base):
        self.base, self.cookie = base, None

    def call(self, method, path, body=None, headers=None, origin=True, raw=False):
        data = json.dumps(body).encode() if body is not None else None
        request = Request(self.base + path, data=data, method=method)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if method != "GET" and origin:
            request.add_header("Origin", self.base)
        if self.cookie:
            request.add_header("Cookie", self.cookie)
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with urlopen(request) as response:
                self._cookie(response)
                payload = response.read()
                return response.status, (payload if raw else (json.loads(payload) if payload else None)), response.headers
        except HTTPError as error:
            payload = error.read()
            return error.code, (payload if raw else json.loads(payload or b"null")), error.headers

    def _cookie(self, response):
        header = response.headers.get("Set-Cookie")
        if header:
            self.cookie = header.split(";")[0]


class StudioHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.database = root / "study.sqlite3"
        with contextlib.redirect_stdout(io.StringIO()):
            make_demo(root / "fixtures", self.database)
        with core.connect(self.database) as db:
            db.execute("UPDATE batches SET demo=0")
        factory = handler_factory(self.database)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), factory)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(lambda: factory.studio.close())
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.alice, self.bob = Client(self.base), Client(self.base)
        for client in (self.alice, self.bob):
            status, _, _ = client.call("POST", "/api/studio/principals", {})
            self.assertEqual(status, 201)

    def board(self, client=None):
        client = client or self.alice
        status, document, _ = client.call("POST", "/api/studio/documents", {"title": "HTTP board", "study": {"context": {"year": 2015, "month": 7, "bbox": list(BBOX)}}})
        self.assertEqual(status, 201, document)
        return document

    def test_capabilities_need_no_identity_and_report_truthful_gates(self):
        status, caps, _ = Client(self.base).call("GET", "/api/studio/capabilities")
        self.assertEqual(status, 200)
        for key in ("canvas", "workflow", "video", "narration", "collaboration"):
            self.assertIn(key, caps)
        self.assertFalse(caps["video"]["available"])
        self.assertTrue(caps["video"]["reason"])

    def test_identity_cookie_is_http_only_strict_and_required(self):
        status, body, headers = Client(self.base).call("POST", "/api/studio/principals", {})
        cookie = headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertEqual(Client(self.base).call("GET", "/api/studio/documents")[0], 401)
        self.assertEqual(self.alice.call("GET", "/api/studio/documents")[0], 200)
        again = self.alice.call("POST", "/api/studio/principals", {})
        self.assertFalse(again[1]["created"])

    def test_mutations_require_a_same_origin_json_request(self):
        status, body, _ = self.alice.call("POST", "/api/studio/documents", {"title": "x"}, origin=False)
        self.assertEqual((status, body["code"]), (403, "cross-origin"))
        status, body, _ = self.alice.call("POST", "/api/studio/documents", {"title": "x"}, headers={"Origin": "http://evil.example"}, origin=False)
        self.assertEqual(status, 403)
        request = Request(self.base + "/api/studio/documents", data=b"title=x", method="POST", headers={"Origin": self.base, "Cookie": self.alice.cookie, "Content-Type": "text/plain"})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 400)

    def test_document_lifecycle_conflicts_and_idempotency_over_http(self):
        document = self.board()
        did = document["id"]
        tx = {"base_revision": document["revision"], "ops": [{"op": "add_card", "card": {"id": "a", "type": "text", "title": "A"}}]}
        status, first, _ = self.alice.call("POST", f"/api/studio/documents/{did}/transactions", tx, headers={"Idempotency-Key": "http-key-0001"})
        self.assertEqual(status, 200, first)
        _, replay, _ = self.alice.call("POST", f"/api/studio/documents/{did}/transactions", tx, headers={"Idempotency-Key": "http-key-0001"})
        self.assertTrue(replay["idempotent_replay"])
        status, conflict, _ = self.alice.call("POST", f"/api/studio/documents/{did}/transactions", {"base_revision": document["revision"], "ops": [{"op": "update_card", "id": "a", "patch": {"title": "z"}}]})
        self.assertEqual((status, conflict["code"]), (409, "revision-conflict"))
        status, patched, _ = self.alice.call("PATCH", f"/api/studio/documents/{did}", {"selection": {"document_revision": first["revision"], "card_id": "a"}})
        self.assertEqual(status, 200)
        self.assertEqual(patched["selection"]["card_id"], "a")
        self.assertEqual(self.alice.call("POST", f"/api/studio/documents/{did}/undo", {})[0], 200)
        self.assertEqual(self.bob.call("GET", f"/api/studio/documents/{did}")[0], 404)
        self.assertEqual(self.bob.call("PATCH", f"/api/studio/documents/{did}", {"title": "x"})[0], 404)

    def test_binding_snapshot_story_export_and_reader_pages(self):
        document = self.board()
        did = document["id"]
        _, added, _ = self.alice.call("POST", f"/api/studio/documents/{did}/transactions", {"base_revision": document["revision"], "ops": [{"op": "add_card", "card": {"id": "c1", "type": "chart", "title": "Overlap"}}]})
        status, resolved, _ = self.alice.call("POST", f"/api/studio/documents/{did}/bindings/resolve", {"binding": {"operation": "research", "context": {}, "arguments": {}}})
        self.assertEqual(status, 200, resolved)
        snapshot = resolved["snapshot"]
        _, bound, _ = self.alice.call("POST", f"/api/studio/documents/{did}/transactions", {"base_revision": added["revision"], "ops": [{"op": "update_card", "id": "c1", "patch": {"snapshot_id": snapshot["id"], "binding": {"operation": "research"}}}]})
        status, report, _ = self.alice.call("GET", f"/api/studio/documents/{did}/snapshots/{snapshot['id']}")
        self.assertTrue(report["verification"]["verified"])
        self.assertEqual(self.bob.call("GET", f"/api/studio/documents/{did}/snapshots/{snapshot['id']}")[0], 404)
        status, story, _ = self.alice.call("POST", f"/api/studio/documents/{did}/stories", {})
        self.assertEqual(status, 201)
        sid = story["id"]
        status, resolved_story, _ = self.alice.call("POST", f"/api/studio/stories/{sid}/resolve", {})
        self.assertEqual(status, 200)
        self.assertEqual(resolved_story["resolved"]["profile"]["duration_seconds"], 120)
        status, archive, headers = self.alice.call("GET", f"/api/studio/stories/{sid}/export", raw=True)
        self.assertEqual((status, headers["Content-Type"]), (200, "application/zip"))
        names = zipfile.ZipFile(io.BytesIO(archive)).namelist()
        self.assertIn("index.json", names)
        self.assertTrue(any(n.endswith("/manifest.json") for n in names))
        self.assertEqual(self.bob.call("GET", f"/api/studio/stories/{sid}")[0], 404)
        status, refused, _ = self.alice.call("POST", f"/api/studio/stories/{sid}/renders", {})
        self.assertEqual((status, refused["code"]), (503, "video-unavailable"))

    def test_assets_upload_validation_and_private_download(self):
        document = self.board()
        did = document["id"]
        payload = {"data": base64.b64encode(PNG).decode(), "license": "CC-BY-4.0", "attribution": "Photographer"}
        status, asset, _ = self.alice.call("POST", f"/api/studio/documents/{did}/assets", payload)
        self.assertEqual(status, 201, asset)
        status, content, headers = self.alice.call("GET", f"/api/studio/assets/{asset['id']}", raw=True)
        self.assertEqual((status, content, headers["Content-Type"]), (200, PNG, "image/png"))
        self.assertEqual(self.bob.call("GET", f"/api/studio/assets/{asset['id']}")[0], 404)
        self.assertEqual(self.alice.call("POST", f"/api/studio/documents/{did}/assets", {**payload, "data": "not base64!"})[0], 400)
        self.assertEqual(self.alice.call("POST", f"/api/studio/documents/{did}/assets", {**payload, "license": ""})[0], 400)

    def test_rooms_are_unavailable_without_an_adapter_and_work_with_loopback(self):
        document = self.board()
        status, body, _ = self.alice.call("POST", f"/api/studio/documents/{document['id']}/room", {})
        self.assertEqual((status, body["code"]), (503, "capability-unavailable"))
        studio = self.server.RequestHandlerClass.studio
        from fireatlas.studio.rooms import LoopbackAdapter, Rooms
        studio.rooms = Rooms(studio.store, LoopbackAdapter())
        status, room, _ = self.alice.call("POST", f"/api/studio/documents/{document['id']}/room", {})
        self.assertEqual(status, 201, room)
        status, invite, _ = self.alice.call("POST", f"/api/studio/rooms/{room['id']}/invites", {"role": "viewer"})
        self.assertEqual(status, 201)
        status, joined, _ = self.bob.call("POST", "/api/studio/invites/redeem", {"token": invite["token"]})
        self.assertEqual((status, joined["role"]), (200, "viewer"))
        self.assertEqual(self.bob.call("POST", "/api/studio/invites/redeem", {"token": invite["token"]})[0], 403)
        self.assertEqual(self.bob.call("GET", f"/api/studio/documents/{document['id']}")[1]["role"], "viewer")
        self.assertEqual(self.bob.call("POST", f"/api/studio/rooms/{room['id']}/comments", {"body": "hi"})[0], 403)

    def test_recovery_restores_the_same_documents_in_a_new_browser(self):
        document = self.board()
        _, recovery, _ = self.alice.call("POST", "/api/studio/recovery", {})
        fresh = Client(self.base)
        status, body, _ = fresh.call("POST", "/api/studio/recover", {"recovery": recovery["recovery"]})
        self.assertEqual(status, 200)
        self.assertEqual(fresh.call("GET", f"/api/studio/documents/{document['id']}")[0], 200)
        self.assertEqual(Client(self.base).call("POST", "/api/studio/recover", {"recovery": "rec_wrong"}, origin=True)[0], 403)

    def test_workflow_routes_validate_and_run(self):
        document = self.board()
        did = document["id"]
        flow = {"nodes": [{"id": "op", "type": "operation", "params": {"operation": "research", "arguments": {}}},
                          {"id": "jac", "type": "pick", "params": {"path": "/overlap/jaccard"}, "inputs": {"source": "op"}}]}
        self.assertEqual(self.alice.call("POST", "/api/studio/workflows/validate", {"definition": flow})[1]["valid"], True)
        status, bad, _ = self.alice.call("POST", "/api/studio/workflows/validate", {"definition": {"nodes": [{"id": "x", "type": "shell"}]}})
        self.assertEqual(status, 400)
        status, saved, _ = self.alice.call("POST", f"/api/studio/documents/{did}/workflow", {"definition": flow})
        self.assertEqual(status, 200, saved)
        status, run, _ = self.alice.call("POST", f"/api/studio/workflows/{saved['id']}/run", {})
        self.assertEqual(status, 202)
        import time
        deadline = time.time() + 30
        while time.time() < deadline and run["status"] == "running":
            time.sleep(0.2)
            run = self.alice.call("GET", f"/api/studio/runs/{run['id']}")[1]
        self.assertEqual(run["status"], "completed", run)
        self.assertEqual(self.bob.call("GET", f"/api/studio/runs/{run['id']}")[0], 404)

    def test_templates_and_deterministic_board_action(self):
        status, templates, _ = self.alice.call("GET", "/api/studio/workflows/templates")
        self.assertEqual(status, 200)
        self.assertEqual({item["id"] for item in templates["templates"]}, {"study-to-board", "findings-to-story"})
        document = self.board()
        status, built, _ = self.alice.call("POST", f"/api/studio/documents/{document['id']}/actions",
                                           {"action": "build_investigation", "base_revision": document["revision"]})
        self.assertEqual(status, 200, built)
        self.assertEqual(len(built["document"]["state"]["order"]), 7)
        self.assertEqual(built["document"]["state"]["cards"]["starter-2"]["binding"]["operation"], "replay")
        status, again, _ = self.alice.call("POST", f"/api/studio/documents/{document['id']}/actions",
                                           {"action": "build_investigation", "base_revision": built["document"]["revision"]})
        self.assertEqual(status, 200)
        self.assertFalse(again["created"])

    def test_unknown_route_and_error_bodies_do_not_leak_internals(self):
        status, body, _ = self.alice.call("GET", "/api/studio/not-a-route")
        self.assertEqual((status, body["code"]), (404, "route-not-found"))
        status, body, _ = self.alice.call("POST", "/api/studio/documents/doc_missing/transactions", {"base_revision": 1, "ops": [{"op": "set_title", "title": "x"}]})
        self.assertEqual(status, 404)
        self.assertNotIn("Traceback", json.dumps(body))
        self.assertNotIn(str(self.database), json.dumps(body))

    def test_existing_assistant_workspace_cannot_reach_studio_documents(self):
        document = self.board()
        cookie_only = Client(self.base)
        cookie_only.cookie = "fireatlas_workspace=" + "x" * 40
        self.assertEqual(cookie_only.call("GET", f"/api/studio/documents/{document['id']}")[0], 401)


class StudioStaticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.database = root / "study.sqlite3"
        with contextlib.redirect_stdout(io.StringIO()):
            make_demo(root / "fixtures", self.database)
        factory = handler_factory(self.database)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), factory)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(lambda: factory.studio.close())
        self.client = Client(f"http://127.0.0.1:{self.server.server_port}")

    def test_only_manifest_files_are_served_from_studio_assets(self):
        from fireatlas.studio.assets import StudioAssets
        from fireatlas.web import STATIC
        assets = StudioAssets(STATIC)
        status, _, _ = self.client.call("GET", "/studio-assets/../web.py")
        self.assertEqual(status, 404)
        status, _, _ = self.client.call("GET", "/studio-assets/not-in-manifest.js")
        self.assertEqual(status, 404)
        if assets.available():
            self.assertEqual(assets.verify(), [])
            name = next(iter(assets._files))
            status, body, headers = self.client.call("GET", "/studio-assets/" + name, raw=True)
            self.assertEqual(status, 200)
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_studio_pages_are_served_and_linked_only_from_investigate_and_research(self):
        for path, marker in (("/studio.html", b"studio"), ("/studio-reader.html", b"reader")):
            status, body, _ = self.client.call("GET", path, raw=True)
            self.assertEqual(status, 200, path)
            self.assertIn(marker, body.lower())
        for path in ("/investigate.html", "/research.html"):
            self.assertIn(b"studio.html", self.client.call("GET", path, raw=True)[1], path)
        landing = self.client.call("GET", "/", raw=True)[1]
        self.assertNotIn(b"studio", landing.lower())
        for path in ("/atlas.html", "/evidence.html", "/replay.html", "/assistant.html"):
            self.assertNotIn(b"studio.html", self.client.call("GET", path, raw=True)[1], path)


if __name__ == "__main__":
    unittest.main()
