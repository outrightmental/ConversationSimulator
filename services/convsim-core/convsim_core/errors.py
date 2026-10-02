# SPDX-License-Identifier: Apache-2.0
import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ConvsimError(Exception):
    """Application-level error with a stable frontend-displayable code."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def convsim_error_handler(request: Request, exc: ConvsimError) -> JSONResponse:
    logger.warning(
        "Application error for %s %s: code=%s status=%d",
        request.method,
        request.url.path,
        exc.code,
        exc.status_code,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


def _safe_validation_errors(errors: list) -> list:
    """Convert Pydantic v2 error dicts to JSON-safe, content-free form.

    Pydantic v2 field_validator errors include the original exception instance
    under ctx["error"], which is not JSON-serializable. This converts any
    exception to its string representation and strips the Pydantic URL.

    The "input" key — the rejected value itself — is dropped. It is the only
    part of a Pydantic error that echoes caller-supplied content back, and a
    422 body ends up in the clipboard via "Copy diagnostics" and from there in
    a public issue report, so a rejected player name or turn must not ride
    along. Everything that identifies the problem ("loc", "msg", "type", "ctx")
    is schema-derived and is kept.
    """
    safe = []
    for err in errors:
        entry: dict = {k: v for k, v in err.items() if k not in ("url", "input")}
        if "ctx" in entry and isinstance(entry["ctx"], dict):
            ctx = dict(entry["ctx"])
            if "error" in ctx and isinstance(ctx["error"], Exception):
                ctx["error"] = str(ctx["error"])
            entry["ctx"] = ctx
        safe.append(entry)
    return safe


# How many field failures the single-line message names before it is truncated.
_MAX_REPORTED_FIELDS = 5

# How long one field's reason may be before it is clipped. Pydantic's own
# messages are a short sentence, but a @field_validator is free to raise
# something long — the approved-voice list, for one — and the whole summary is
# rendered in a compact error card and copied into a bug report.
_MAX_REASON_CHARS = 120


def _clip(reason: str) -> str:
    """Trim one reason to _MAX_REASON_CHARS, marking the cut."""
    if len(reason) <= _MAX_REASON_CHARS:
        return reason
    return reason[: _MAX_REASON_CHARS - 1].rstrip() + "\u2026"


def _field_path(loc) -> str:
    """Dotted field path for one Pydantic error location.

    ``loc`` is a tuple like ("body", "tts_voice_id") or ("query", "context").
    The "body" prefix is dropped because every request model lives there and it
    only adds noise; "query"/"path" are kept because they say where to look.
    A body-wide failure — a missing body, or malformed JSON, whose loc is just
    an offset — has no field to name, so it reads as "body".
    """
    parts = [str(p) for p in (loc or ())]
    if parts[:1] == ["body"]:
        parts = parts[1:]
    if not parts or all(p.isdigit() for p in parts):
        return "body"
    return ".".join(parts)


def _validation_summary(errors: list) -> str:
    """One line naming which fields failed and why.

    Without this the client can only show "Request validation failed", which
    tells a user nothing and tells a maintainer reading a pasted report nothing
    either — exactly the dead end seen in issue #508.

    This line is surfaced in the UI and copied into bug reports, so — like the
    details list, which drops "input" for the same reason — it must carry no
    caller content. Pydantic's built-in ``msg`` is schema-derived ("Input
    should be a valid string"). A ``value_error`` ``msg``, though, is "Value
    error, " plus whatever one of our own ``@field_validator``s raised, so
    those sentences must not interpolate the value they rejected. Length is
    clipped here as a backstop, but it only bounds a leak; it does not prevent
    one.
    """
    named = [
        f"{_field_path(e.get('loc'))}: {_clip(str(e.get('msg', 'invalid value')))}"
        for e in errors
    ]
    if not named:
        return "Request validation failed"
    shown = named[:_MAX_REPORTED_FIELDS]
    suffix = (
        f" (and {len(named) - _MAX_REPORTED_FIELDS} more)"
        if len(named) > _MAX_REPORTED_FIELDS
        else ""
    )
    return f"Request validation failed — {'; '.join(shown)}{suffix}"


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = _safe_validation_errors(exc.errors())
    # Log it: a 422 used to leave no trace at all, so the log excerpt that
    # "Copy diagnostics" collects was silent about the very request that
    # failed. Only the field path and Pydantic's error type are logged — both
    # schema-derived — so no caller content reaches the log file.
    logger.warning(
        "Request validation failed for %s %s: %s",
        request.method,
        request.url.path,
        ", ".join(f"{_field_path(d.get('loc'))}={d.get('type', 'invalid')}" for d in details)
        or "no field details",
    )
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": _validation_summary(details),
                "details": details,
            }
        },
    )


async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception for %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"}},
    )
