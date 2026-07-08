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
    """Convert Pydantic v2 error dicts to JSON-safe form.

    Pydantic v2 field_validator errors include the original exception instance
    under ctx["error"], which is not JSON-serializable. This converts any
    exception to its string representation and strips the Pydantic URL.
    """
    safe = []
    for err in errors:
        entry: dict = {k: v for k, v in err.items() if k != "url"}
        if "ctx" in entry and isinstance(entry["ctx"], dict):
            ctx = dict(entry["ctx"])
            if "error" in ctx and isinstance(ctx["error"], Exception):
                ctx["error"] = str(ctx["error"])
            entry["ctx"] = ctx
        safe.append(entry)
    return safe


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": _safe_validation_errors(exc.errors()),
            }
        },
    )


async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception for %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"}},
    )
