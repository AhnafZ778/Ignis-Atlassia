"""Helpers for publishing traceable source references safely."""

from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit


def public_source_reference(value: str | None) -> str | None:
    """Replace a local file URI with a stable project-relative reference."""
    if not value:
        return value
    parsed = urlsplit(value)
    if parsed.scheme.lower() != "file":
        return value
    path = unquote(parsed.path).replace("\\", "/")
    marker = "/NASA_data/"
    if marker in path:
        relative = "NASA_data/" + path.split(marker, 1)[1]
    else:
        relative = PurePosixPath(path).name or "local-source"
    return f"local-file:{relative}"


def sanitize_public_payload(value):
    """Recursively sanitize file URIs in JSON-compatible data."""
    if isinstance(value, dict):
        return {key: sanitize_public_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_public_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_public_payload(item) for item in value)
    if isinstance(value, str) and value.startswith("file:"):
        return public_source_reference(value)
    return value
