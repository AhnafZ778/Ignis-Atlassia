"""Structured Studio failures. Every error carries an HTTP status and a machine-readable code."""
from __future__ import annotations


class StudioError(Exception):
    status = 400
    code = "bad-request"

    def __init__(self, message, *, code=None, details=None, status=None):
        super().__init__(message)
        if code:
            self.code = code
        if status:
            self.status = status
        self.details = details or {}

    def payload(self):
        return {"error": str(self), "code": self.code, **({"details": self.details} if self.details else {})}


class Unauthorized(StudioError):
    status = 401
    code = "no-browser-identity"


class Forbidden(StudioError):
    status = 403
    code = "forbidden"


class NotFound(StudioError):
    status = 404
    code = "not-found"


class Conflict(StudioError):
    status = 409
    code = "revision-conflict"


class LimitExceeded(StudioError):
    status = 413
    code = "limit-exceeded"


class Throttled(StudioError):
    status = 429
    code = "throttled"


class Unavailable(StudioError):
    status = 503
    code = "capability-unavailable"


class StoreVersionError(StudioError):
    status = 500
    code = "store-version"
