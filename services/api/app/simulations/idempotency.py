"""Idempotency-Key runtime flow for the SIM-02A run route (CCR-20260724-SIM-02A §4).

Persistence schema (``idempotency_records``) landed with the P3 prerequisite; this
module adds the frozen runtime semantics:

- header format gate: required, 1..200 chars, visible ASCII only, otherwise 422
  ``VALIDATION_FAILED`` and the key is NOT consumed;
- normalized request hash: sha256 over canonical JSON (sorted keys, ``,``/``:``
  separators, UTF-8) of the VALIDATED request model plus the path ``graphId``
  anchor, so the same key replayed against a different graph is a conflict;
- same key + same hash ⇒ replay of the committed terminal outcome; same key +
  different hash ⇒ 409 ``IDEMPOTENCY_CONFLICT`` with no hash echo;
- concurrency: the losing transaction of the unique-constraint race surfaces as
  ``IdempotencyRaceError`` so the caller can re-read and replay the winner.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.models import IdempotencyRecord
from app.security.envelope import ApiFailure

IDEMPOTENCY_HEADER = "Idempotency-Key"
RUN_CREATE_ROUTE_KEY = "simulations.runs.create"
RECORD_RETENTION = timedelta(hours=48)

RESPONSE_KIND_SUCCESS = "success"
RESPONSE_KIND_NON_CONVERGED = "non_converged"

_KEY_MIN_LENGTH = 1
_KEY_MAX_LENGTH = 200
_IDEMPOTENCY_UNIQUE_CONSTRAINT = "uq_idempotency_records_workspace_route_key"


class IdempotencyRaceError(Exception):
    """The concurrent-writer race was lost; the committed record must be replayed."""


def idempotency_conflict() -> ApiFailure:
    """Same key, different normalized request: 409 with no details (§4.8)."""

    return ApiFailure(
        "IDEMPOTENCY_CONFLICT",
        "The Idempotency-Key was already used with a different request.",
        http_status=409,
    )


def _header_validation_failed(message: str) -> ApiFailure:
    # Mirrors the sanitized RequestValidationError envelope shape so header and
    # body validation failures are indistinguishable in structure.
    return ApiFailure(
        "VALIDATION_FAILED",
        "Request body or parameters failed validation.",
        http_status=422,
        details={
            "errors": [
                {
                    "type": "idempotency_key_invalid",
                    "loc": ["header", IDEMPOTENCY_HEADER],
                    "msg": message,
                }
            ]
        },
    )


def validate_idempotency_key(raw_value: str | None) -> str:
    """Enforce the frozen header format (§4.3); failures never consume the key."""

    if raw_value is None:
        raise _header_validation_failed("Idempotency-Key header is required.")
    if not (_KEY_MIN_LENGTH <= len(raw_value) <= _KEY_MAX_LENGTH):
        raise _header_validation_failed(
            "Idempotency-Key must be between 1 and 200 characters."
        )
    if any(not (0x21 <= ord(char) <= 0x7E) for char in raw_value):
        raise _header_validation_failed(
            "Idempotency-Key must contain visible ASCII characters only."
        )
    return raw_value


def normalized_request_hash(validated_body: dict, graph_id: UUID) -> str:
    """sha256 over canonical JSON of the validated body plus the graphId anchor (§4.2)."""

    payload = {"graphId": str(graph_id), "request": validated_body}
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_idempotency_record(
    *,
    workspace_id: UUID,
    idempotency_key: str,
    request_hash: str,
    resource_id: UUID,
    http_status: int,
    response_kind: str,
    route_key: str = RUN_CREATE_ROUTE_KEY,
) -> IdempotencyRecord:
    """Stage one replay record; ``expires_at`` enforces the 48h retention window."""

    created_at = datetime.now(timezone.utc)
    return IdempotencyRecord(
        id=uuid4(),
        workspace_id=workspace_id,
        route_key=route_key,
        idempotency_key=idempotency_key,
        normalized_request_hash=request_hash,
        resource_type="simulation_run",
        resource_id=resource_id,
        http_status=http_status,
        response_kind=response_kind,
        created_at=created_at,
        expires_at=created_at + RECORD_RETENTION,
    )


def is_idempotency_unique_violation(exc: IntegrityError) -> bool:
    """Detect the (workspace, route, key) unique-race loss on the DB error.

    asyncpg exposes the violated constraint name on the wrapped driver error;
    the string fallback covers driver variants that only carry it in the text.
    This inspects database driver diagnostics, never domain error messages.
    """

    origin = getattr(exc, "orig", None)
    seen = set()
    while origin is not None and id(origin) not in seen:
        seen.add(id(origin))
        if getattr(origin, "constraint_name", None) == _IDEMPOTENCY_UNIQUE_CONSTRAINT:
            return True
        origin = getattr(origin, "__cause__", None)
    return _IDEMPOTENCY_UNIQUE_CONSTRAINT in str(exc)
