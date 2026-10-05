"""Manifest-based allowlist for the Studio React island.

Only files named in ``studio-manifest.json`` (written by the build) can be served from ``/studio-assets/``. The manifest also
carries each file's SHA-256 so a deployment can detect a partially copied or tampered bundle.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

MIME = {".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp",
        ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf", ".txt": "text/plain; charset=utf-8", ".map": "application/json"}
PREFIX = "/studio-assets/"


class StudioAssets:
    def __init__(self, static_dir):
        self.root = Path(static_dir) / "studio-assets"
        self.manifest_path = self.root / "studio-manifest.json"
        self._stamp, self._files = None, {}

    def _load(self):
        try:
            stamp = self.manifest_path.stat().st_mtime_ns
        except OSError:
            self._stamp, self._files = None, {}
            return
        if stamp != self._stamp:
            try:
                manifest = json.loads(self.manifest_path.read_text())
                files = manifest.get("files", {})
                self._files = {name: item for name, item in files.items() if isinstance(name, str) and not name.startswith("/") and ".." not in name.split("/")}
            except (OSError, ValueError, AttributeError):
                self._files = {}
            self._stamp = stamp

    def available(self):
        self._load()
        return bool(self._files)

    def resolve(self, request_path):
        """Return ``(path, mime, immutable)`` for an allowlisted request path, else ``None``."""
        if not request_path.startswith(PREFIX):
            return None
        self._load()
        name = request_path.removeprefix(PREFIX)
        if name == "studio-manifest.json":
            return (self.manifest_path, MIME[".json"], False) if self.manifest_path.is_file() else None
        if name not in self._files:
            return None
        path = (self.root / name).resolve()
        if self.root.resolve() not in path.parents or not path.is_file():
            return None
        return path, MIME.get(path.suffix.lower(), "application/octet-stream"), "-" in path.stem

    def verify(self):
        """Names of manifest files that are missing or whose hash differs. Used by tests and the release check."""
        self._load()
        problems = []
        for name, item in self._files.items():
            path = self.root / name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item.get("sha256"):
                problems.append(name)
        return problems
