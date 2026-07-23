"""Uniform API envelope and non-leaking error semantics.

AGENTS.md section 9 requires every API response to use the shared
success/error envelope with stable error codes, and section 5 requires
cross-workspace access to be answered with an undifferentiated 404 so that
resource existence is never leaked. This module is the single place where
those two contracts are enforced for routers owned by the Case/API/Data
lane; ``register_error_handlers`` must be attached to the FastAPI app by the
Contract Lead when the routers are mounted.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiFailure(Exception):
    """Structured API failure carrying a canonical error code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.retryable = retryable
        self.details = details


def failure_body(failure: ApiFailure) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": failure.code,
        "message": failure.message,
        "retryable": failure.retryable,
    }
    if failure.details is not None:
        error["details"] = failure.details
    return {"ok": False, "error": error}


def workspace_not_found() -> ApiFailure:
    """Uniform 404 for missing, foreign, or inactive workspace-scoped access.

    The message is intentionally identical for every denial reason so that
    neither membership state nor resource existence can be probed.
    """

    return ApiFailure(
        "WORKSPACE_NOT_FOUND",
        "Workspace not found.",
        http_status=404,
    )


def session_rejected() -> ApiFailure:
    """Uniform 401 for missing, invalid, revoked, or expired sessions."""

    return ApiFailure(
        "SESSION_REVOKED_OR_EXPIRED",
        "Session is missing, revoked, or expired. Please sign in again.",
        http_status=401,
    )


def _sanitize_validation_errors(errors: Sequence[Any]) -> list[dict[str, Any]]:
    """Project Pydantic error dicts onto the envelope contract fields.

    On the locked stack ``RequestValidationError.errors()`` accepts no keyword
    arguments, so ``url``/``input`` cannot be suppressed at the source and are
    stripped here instead: ``input`` may echo submitted values (passwords
    included) and ``url`` is documentation noise. Only ``type``/``loc``/``msg``
    and JSON-scalar ``ctx`` entries survive; non-scalar ctx values (for
    example the wrapped exception of ``json_invalid``) are dropped rather than
    stringified because their reprs can embed raw input fragments.
    """

    sanitized: list[dict[str, Any]] = []
    for error in errors:
        if not isinstance(error, dict):
            continue
        entry: dict[str, Any] = {
            "type": str(error.get("type", "value_error")),
            "loc": [
                part if isinstance(part, (str, int)) else str(part)
                for part in error.get("loc", ())
            ],
            "msg": str(error.get("msg", "Invalid value.")),
        }
        ctx = error.get("ctx")
        if isinstance(ctx, dict):
            safe_ctx = {
                key: value
                for key, value in ctx.items()
                if value is None or isinstance(value, (str, int, float, bool))
            }
            if safe_ctx:
                entry["ctx"] = safe_ctx
        sanitized.append(entry)
    return sanitized


def register_error_handlers(app: FastAPI) -> None:
    """Attach envelope-shaped handlers; called from app assembly."""

    @app.exception_handler(ApiFailure)
    async def handle_api_failure(_request: Request, failure: ApiFailure) -> JSONResponse:
        return JSONResponse(status_code=failure.http_status, content=failure_body(failure))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        failure = ApiFailure(
            "VALIDATION_FAILED",
            "Request body or parameters failed validation.",
            http_status=422,
            details={"errors": _sanitize_validation_errors(exc.errors())},
        )
        return JSONResponse(status_code=failure.http_status, content=failure_body(failure))
