"""HTTP boundary for Research Studio, shared with the existing flat-route server.

Studio keeps its own browser identity cookie (``fireatlas_studio``) so a Studio document never depends on an
assistant workspace, and an assistant workspace never gains access to Studio documents.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import os
import tempfile
import time
import zipfile
from http import HTTPStatus
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from ..provenance import sanitize_public_payload
from .errors import StudioError

COOKIE = "fireatlas_studio"
PREFIX = "/api/studio/"
MAX_BODY = 3_000_000
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
METHODS = {"GET", "POST", "PATCH", "DELETE"}
EVENT_SECONDS = 600


def _origin(handler):
    configured = os.getenv("FIREATLAS_STUDIO_ORIGIN") or os.getenv("FIREATLAS_ASSISTANT_ORIGIN")
    expected = configured or "http://" + handler.headers.get("Host", "")
    if not configured and urlsplit(expected).hostname not in LOCAL_HOSTS:
        raise StudioError("Configure FIREATLAS_STUDIO_ORIGIN for public deployment.", status=403, code="origin-not-configured")
    return expected


def _check_origin(handler):
    if handler.headers.get("Origin") != _origin(handler):
        raise StudioError("Studio updates require a same-origin request.", status=403, code="cross-origin")


def _body(handler):
    size = int(handler.headers.get("Content-Length", "0") or 0)
    if size == 0:
        return {}
    if handler.headers.get("Content-Type", "").split(";")[0] != "application/json" or not 0 < size <= MAX_BODY:
        raise StudioError("Use a JSON request of at most 3 MB.", status=413 if size > MAX_BODY else 400, code="invalid-body")
    try:
        value = json.loads(handler.rfile.read(size))
    except (ValueError, UnicodeDecodeError):
        raise StudioError("The request is not valid JSON.", code="invalid-json") from None
    if not isinstance(value, dict):
        raise StudioError("Request must be an object.", code="invalid-body")
    return value


def _cookie(handler):
    jar = SimpleCookie()
    try:
        jar.load(handler.headers.get("Cookie", ""))
    except Exception:  # noqa: BLE001 - a malformed cookie header is simply no identity
        return ""
    return jar[COOKIE].value if COOKIE in jar else ""


def _send(handler, value, status=HTTPStatus.OK, token=None):
    encoded = json.dumps(sanitize_public_payload(value)).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    if token:
        secure = "; Secure" if (_origin_configured_https()) else ""
        handler.send_header("Set-Cookie", f"{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=31536000{secure}")
    handler.end_headers()
    try:
        handler.wfile.write(encoded)
    except (BrokenPipeError, ConnectionResetError):
        pass


def _origin_configured_https():
    return (os.getenv("FIREATLAS_STUDIO_ORIGIN") or os.getenv("FIREATLAS_ASSISTANT_ORIGIN") or "").startswith("https://")


def _stream_file(handler, path, mime, filename=None):
    """Serve a file with single-range support so video elements can seek."""
    size = path.stat().st_size
    start, end, status = 0, size - 1, HTTPStatus.OK
    header = handler.headers.get("Range", "")
    if header.startswith("bytes=") and "," not in header:
        low, _, high = header[6:].partition("-")
        try:
            if low == "":
                start = max(0, size - int(high))
            else:
                start = int(low)
                end = min(int(high), size - 1) if high else size - 1
        except ValueError:
            start, end = 0, size - 1
        if start > end or start >= size:
            handler.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            handler.send_header("Content-Range", f"bytes */{size}")
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return
        status = HTTPStatus.PARTIAL_CONTENT
    handler.send_response(status)
    handler.send_header("Content-Type", mime)
    handler.send_header("Content-Length", str(end - start + 1))
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    if status == HTTPStatus.PARTIAL_CONTENT:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    if filename:
        handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    handler.end_headers()
    try:
        with path.open("rb") as source:
            source.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                block = source.read(min(1024 * 1024, remaining))
                if not block:
                    break
                handler.wfile.write(block)
                remaining -= len(block)
    except (BrokenPipeError, ConnectionResetError):
        pass


def _story_zip(service, principal, story_id, revision):
    with tempfile.TemporaryDirectory(prefix="fireatlas-studio-export-") as directory:
        root = Path(directory) / "studio"
        service.export_story(principal, story_id, root, revision)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())
        return buffer.getvalue()


def _events(handler, service, principal, render_id):
    """Server-sent progress for one render. The response ends when the render reaches a terminal state."""
    service.renders.get(principal, render_id)
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Accel-Buffering", "no")
    handler.end_headers()
    deadline, last = time.monotonic() + EVENT_SECONDS, None
    try:
        while time.monotonic() < deadline:
            view = service.renders.get(principal, render_id)
            marker = (view["status"], view.get("phase"), view["progress"], view["error"])
            if marker != last:
                handler.wfile.write(b"event: render\ndata: " + json.dumps(sanitize_public_payload(view)).encode() + b"\n\n")
                handler.wfile.flush()
                last = marker
            if view["status"] in ("completed", "failed", "canceled"):
                return
            time.sleep(0.5)
        handler.wfile.write(b"event: timeout\ndata: {}\n\n")
    except (BrokenPipeError, ConnectionResetError):
        pass


def _int(params, name, default=None):
    try:
        return int(params[name][0]) if name in params else default
    except ValueError:
        raise StudioError(f"{name} must be a whole number.", code="invalid-parameter") from None


def handle(handler, service):
    url = urlsplit(handler.path)
    if not url.path.startswith(PREFIX):
        return False
    try:
        _dispatch(handler, service, url)
    except StudioError as error:
        _send(handler, error.payload(), HTTPStatus(error.status))
    except PermissionError:
        _send(handler, {'error': 'This result is unavailable to this identity.', 'code': 'forbidden'}, HTTPStatus.FORBIDDEN)
    except (ValueError, KeyError, TypeError, OverflowError, __import__('zipfile').BadZipFile) as error:
        _send(handler, {"error": str(error) or "The request is not valid.", "code": "invalid-request"}, HTTPStatus.BAD_REQUEST)
    except Exception:  # noqa: BLE001 - never leak internals; scientific pages stay usable
        _send(handler, {"error": "Studio service unavailable. The scientific pages remain usable.", "code": "studio-unavailable"}, HTTPStatus.SERVICE_UNAVAILABLE)
    return True


def _dispatch(handler, service, url):
    route = url.path.removeprefix(PREFIX).strip("/")
    parts = route.split("/") if route else []
    method, params = handler.command, parse_qs(url.query)
    if method not in METHODS:
        raise StudioError("Unsupported method.", status=405, code="method-not-allowed")
    if method == "GET" and route == "capabilities":
        return _send(handler, service.capabilities())
    if method != "GET":
        _check_origin(handler)
    body = _body(handler) if method in ("POST", "PATCH") and route != 'imports' else {}
    key = handler.headers.get("Idempotency-Key")
    store = service.store

    # -- identity -----------------------------------------------------------------
    token = _cookie(handler)
    if route == "principals" and method == "POST":
        principal = store.principal(token, required=False)
        if principal:
            return _send(handler, {"principal": principal[-6:], "created": False})
        store.throttle("principal:" + hashlib.sha256(handler.client_address[0].encode()).hexdigest(), 30, 3600)
        principal, token = store.create_principal()
        return _send(handler, {"principal": principal[-6:], "created": True}, HTTPStatus.CREATED, token=token)
    if route == "recover" and method == "POST":
        principal, token = store.recover(body.get("recovery"))
        return _send(handler, {"principal": principal[-6:], "recovered": True}, token=token)
    principal = store.principal(token)
    if route == 'contexts' and method == 'POST':
        return _send(handler, service.commands.context(principal, body))
    if route == 'commands' and method == 'POST':
        from ..assistant.http import COOKIE as ASSISTANT_COOKIE
        jar = SimpleCookie(); jar.load(handler.headers.get('Cookie', ''))
        owner = jar[ASSISTANT_COOKIE].value if ASSISTANT_COOKIE in jar else None
        return _send(handler, service.commands.submit(principal, body, key, assistant_owner=owner), HTTPStatus.ACCEPTED)
    if parts[:1] == ['commands'] and len(parts) in (2, 3):
        if len(parts) == 2 and method == 'GET':
            return _send(handler, service.commands.get(principal, parts[1]))
        if len(parts) == 3 and method == 'POST':
            return _send(handler, service.commands.action(principal, parts[1], parts[2], body))
    if parts[:1] == ['packages'] and len(parts) == 2 and method == 'GET':
        return _send(handler, service.commands.package(principal, parts[1]))
    if parts[:1] == ['exports'] and len(parts) in (2,3) and method == 'GET':
        if len(parts) == 2: return _send(handler, service.portability.get(principal, parts[1]))
        if parts[2] == 'download':
            path, mime = service.portability.download(principal, parts[1])
            return _stream_file(handler, path, mime, path.name)
    if parts[:1] == ['miro-transfers'] and len(parts) == 2 and method == 'GET':
        return _send(handler, service.miro.get(principal, parts[1]))
    if parts[:1] == ['miro-transfers'] and len(parts) == 3 and parts[2]=='resume' and method=='POST':
        return _send(handler,service.miro.resume(principal,parts[1]),HTTPStatus.ACCEPTED)
    if route == 'imports' and method == 'POST':
        from .portability import COMPRESSED
        size = int(handler.headers.get('Content-Length', '0'))
        if not 0 < size <= COMPRESSED or handler.headers.get('Content-Type','').split(';')[0] not in {'application/zip','application/octet-stream'}:
            raise StudioError('Upload a native ZIP of at most 512 MiB.', status=413, code='archive-limit')
        with tempfile.NamedTemporaryFile(prefix='fireatlas-board-',suffix='.zip') as upload:
            remaining = size
            while remaining:
                chunk = handler.rfile.read(min(1024*1024,remaining))
                if not chunk: raise StudioError('Archive upload was interrupted.')
                upload.write(chunk); remaining -= len(chunk)
            upload.flush()
            return _send(handler, service.portability.restore(principal, Path(upload.name)), HTTPStatus.CREATED)
    if route == 'assistant-contexts' and method == 'POST':
        if not service.jarvis: raise StudioError('The contextual assistant runtime is unavailable.',status=503)
        from ..assistant.http import COOKIE as ASSISTANT_COOKIE
        cookies=SimpleCookie();cookies.load(handler.headers.get('Cookie',''))
        owner=cookies[ASSISTANT_COOKIE].value if ASSISTANT_COOKIE in cookies else ''
        return _send(handler,service.jarvis.attach_surface(principal,owner,body))
    if len(parts)==3 and parts[0]=='contexts' and parts[2]=='commands' and method=='GET':
        from .graph import check_id
        instance=check_id(parts[1])
        with store.connection() as db:
            rows=db.execute('SELECT id,context FROM commands WHERE principal_id=? ORDER BY created DESC LIMIT 100',(principal,)).fetchall()
        identifiers=[r['id'] for r in rows if json.loads(r['context'])['origin_instance_id']==instance]
        return _send(handler,{'commands':[service.commands.get(principal,i) for i in identifiers[:10]]})
    if route == "recovery" and method == "POST":
        return _send(handler, {"recovery": store.issue_recovery(principal),
                               "note": "Keep this token private. It restores access to your boards from another browser and is shown once."})
    if route == "session" and method == "GET":
        return _send(handler, {"principal": principal[-6:], **service.list_documents(principal)})

    # -- documents ----------------------------------------------------------------
    if route == "documents" and method == "GET":
        return _send(handler, service.list_documents(principal))
    if route == "documents" and method == "POST":
        return _send(handler, service.create_document(principal, body, key), HTTPStatus.CREATED)
    if parts[:1] == ["documents"] and len(parts) >= 2:
        document_id = parts[1]
        tail = parts[2:]
        if tail == ['exports'] and method == 'POST':
            return _send(handler, service.portability.submit(principal, document_id, body, key=key), HTTPStatus.ACCEPTED)
        if tail == ['miro-transfers'] and method == 'POST':
            return _send(handler, service.miro.submit(principal, document_id, body, key=key), HTTPStatus.ACCEPTED)
        if not tail and method == "GET":
            return _send(handler, service.get_document(principal, document_id))
        if not tail and method == "PATCH":
            return _send(handler, service.patch_document(principal, document_id, body))
        if tail == ["actions"] and method == "POST":
            return _send(handler, service.presentation_action(principal, document_id, body, key))
        if tail == ["transactions"] and method == "POST":
            return _send(handler, service.transact(principal, document_id, body, key))
        if tail == ["undo"] and method == "POST":
            return _send(handler, service.undo(principal, document_id, key))
        if tail == ["redo"] and method == "POST":
            return _send(handler, service.envelope(store.redo(principal, document_id, key)))
        if len(tail) == 2 and tail[0] == "revisions" and method == "GET":
            state, digest = store.revision_state(principal, document_id, int(tail[1]))
            return _send(handler, {"revision": int(tail[1]), "state": state, "state_sha256": digest})
        if len(tail) == 3 and tail[0] == "snapshots" and tail[2] == "receipt" and method == "GET":
            return _send(handler, service.snapshot_receipt(principal, document_id, tail[1]))
        if len(tail) == 3 and tail[0] == "snapshots" and tail[2] == "preview" and method == "GET":
            return _send(handler, service.snapshot_preview(principal, document_id, tail[1], params.get("type", ["table"])[0], params.get("day", [None])[0], params.get("source", ["joint"])[0],
                params.get("start", [None])[0], params.get("end", [None])[0], params.get("cell", [None])[0]))
        if len(tail) == 2 and tail[0] == "snapshots" and method == "GET":
            return _send(handler, service.snapshot_report(principal, document_id, tail[1]))
        if tail == ["bindings", "resolve"] and method == "POST":
            return _send(handler, service.resolve_binding(principal, document_id, body.get("binding")))
        if tail and tail[0] == "assistant":
            from .errors import Unavailable
            if service.jarvis is None:
                raise Unavailable("The existing JARVIS runtime is unavailable; deterministic Studio actions still work.")
            if tail == ["assistant", "start"] and method == "POST":
                return _send(handler, service.jarvis.start(principal, document_id, body), HTTPStatus.ACCEPTED)
            if len(tail) == 3 and tail[1] == "runs" and method == "GET":
                return _send(handler, service.jarvis.run(principal, document_id, tail[2]))
            if len(tail) == 4 and tail[1] == "runs" and tail[3] == "cancel" and method == "POST":
                return _send(handler, service.jarvis.run(principal, document_id, tail[2], cancel=True))
            if len(tail) == 4 and tail[1] == "proposals" and tail[3] == "apply" and method == "POST":
                return _send(handler, service.jarvis.apply(principal, document_id, tail[2]))
        if tail == ["stories"] and method == "POST":
            return _send(handler, service.create_story(principal, document_id, body, key), HTTPStatus.CREATED)
        if tail == ["projects"] and method == "GET":
            return _send(handler, service.document_projects(principal, document_id))
        if tail == ["assets"] and method == "POST":
            try:
                raw = base64.b64decode(body.get("data", ""), validate=True)
            except (binascii.Error, ValueError):
                raise StudioError("Image data must be base64.", code="asset-type") from None
            return _send(handler, service.add_asset(principal, document_id, raw, body.get("license"), body.get("attribution")), HTTPStatus.CREATED)
        if tail == ["workflow"] and method == "POST":
            return _send(handler, service.save_workflow(principal, document_id, body.get("definition"), body.get("expected_revision")))
        if tail == ["room"] and method == "POST":
            return _send(handler, service.rooms.create(principal, document_id), HTTPStatus.CREATED)

    # -- assets -------------------------------------------------------------------
    if len(parts) == 2 and parts[0] == "assets" and method == "GET":
        path, mime = service.asset_file(principal, parts[1])
        return _stream_file(handler, path, mime)

    # -- stories ------------------------------------------------------------------
    if parts[:1] == ["stories"] and len(parts) >= 2:
        story_id, tail = parts[1], parts[2:]
        revision = _int(params, "revision")
        if not tail and method == "GET":
            return _send(handler, service.get_story(principal, story_id, revision))
        if not tail and method == "PATCH":
            return _send(handler, service.update_story(principal, story_id, body, key))
        if tail == ["resolve"] and method == "POST":
            return _send(handler, service.resolve_story(principal, story_id, revision))
        if tail == ["renders"] and method == "POST":
            return _send(handler, service.start_render(principal, story_id, key, narration_requested=body.get("narration", False)), HTTPStatus.ACCEPTED)
        if tail == ["export"] and method == "GET":
            data = _story_zip(service, principal, story_id, revision)
            handler.send_response(HTTPStatus.OK)
            handler.send_header("Content-Type", "application/zip")
            handler.send_header("Content-Length", str(len(data)))
            handler.send_header("Content-Disposition", 'attachment; filename="fireatlas-studio-story.zip"')
            handler.send_header("Cache-Control", "no-store")
            handler.send_header("X-Content-Type-Options", "nosniff")
            handler.end_headers()
            try:
                handler.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return None

    # -- workflows and runs -------------------------------------------------------
    if route == "workflows/validate" and method == "POST":
        return _send(handler, service.validate_workflow(body.get("definition")))
    if route == "workflows/templates" and method == "GET":
        from .workflow import templates
        return _send(handler, {"templates": templates()})
    if len(parts) == 2 and parts[0] == "workflows" and method == "GET":
        return _send(handler, service.get_workflow(principal, parts[1]))
    if len(parts) == 3 and parts[0] == "workflows" and parts[2] == "run" and method == "POST":
        return _send(handler, service.run_workflow(principal, parts[1]), HTTPStatus.ACCEPTED)
    if len(parts) == 2 and parts[0] == "runs" and method == "GET":
        return _send(handler, service.get_run(principal, parts[1]))
    if len(parts) == 3 and parts[0] == "runs" and parts[2] == "cancel" and method == "POST":
        return _send(handler, service.cancel_run(principal, parts[1]))
    if len(parts) == 3 and parts[0] == "runs" and parts[2] == "apply" and method == "POST":
        return _send(handler, service.apply_workflow_output(principal, parts[1], body.get("node_id"), body.get("expected_revision")))

    # -- renders ------------------------------------------------------------------
    if parts[:1] == ["renders"] and len(parts) >= 2:
        render_id, tail = parts[1], parts[2:]
        if not tail and method == "GET":
            return _send(handler, service.renders.get(principal, render_id))
        if tail == ["cancel"] and method == "POST":
            return _send(handler, service.renders.cancel(principal, render_id))
        if tail == ["artifact"] and method == "GET":
            path, mime = service.renders.artifact(principal, render_id, params.get("name", [""])[0])
            return _stream_file(handler, path, mime, filename=path.name if params.get("download") else None)
        if tail == ["events"] and method == "GET":
            return _events(handler, service, principal, render_id)

    # -- rooms and invites --------------------------------------------------------
    rooms = service.rooms
    if route == "invites/redeem" and method == "POST":
        return _send(handler, rooms.redeem(principal, body.get("token")))
    if len(parts) == 3 and parts[0] == "invites" and parts[2] == "redeem" and method == "POST":
        return _send(handler, rooms.redeem(principal, parts[1]))
    if parts[:1] == ["rooms"] and len(parts) >= 2:
        room_id, tail = parts[1], parts[2:]
        if not tail and method == "GET":
            return _send(handler, rooms.view(principal, room_id))
        if tail == ["invites"] and method == "POST":
            return _send(handler, rooms.invite(principal, room_id, body.get("role"), body.get("ttl_seconds", 7 * 86400)), HTTPStatus.CREATED)
        if tail == ["comments"] and method == "GET":
            return _send(handler, {"comments": rooms.comments(principal, room_id)})
        if tail == ["comments"] and method == "POST":
            return _send(handler, rooms.comment(principal, room_id, body.get("body"), body.get("card_id"), body.get("chapter")), HTTPStatus.CREATED)
        if tail == ["presenter"] and method == "GET":
            return _send(handler, rooms.presenter(principal, room_id, _int(params, "after", 0)))
        if tail == ["presenter"] and method == "POST":
            return _send(handler, rooms.present(principal, room_id, body.get("state"), body.get("expected_epoch")))
        if tail == ["heartbeat"] and method == "POST":
            return _send(handler, rooms.heartbeat(principal, room_id, body.get("cursor")))
        if tail == ["authorize"] and method == "POST":
            return _send(handler, rooms.authorize(principal, room_id))
    raise StudioError("Studio route not found.", status=404, code="route-not-found")
