"""Deterministic content hash for frozen decision-maker profiles (CCR-SIM-02A §2).

Pure module: no I/O, no ORM imports. The hash is always computed server-side over
the frozen business payload — canonical JSON with sorted keys, ``,``/``:``
separators, UTF-8 — so identical payloads always produce identical hashes and any
frozen field change changes the hash. Caller-supplied content hashes are never
accepted as authoritative anywhere in this package; the only write path
(repository insert) calls this function itself.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping
from uuid import UUID


def compute_profile_content_hash(
    *,
    workspace_id: UUID,
    profile_id: UUID,
    version: int,
    decision_case_id: UUID | None,
    user_id: UUID,
    display_name: str,
    preference_weights: Mapping[str, Any],
    risk_tolerance: float,
) -> str:
    """sha256 over the canonical JSON of every frozen profile field.

    ``preference_weights`` is deep-normalized through json round-trip semantics
    (sorted keys at every level), never trusting JSONB key order.
    """

    payload = {
        "workspaceId": str(workspace_id),
        "profileId": str(profile_id),
        "version": int(version),
        "decisionCaseId": None if decision_case_id is None else str(decision_case_id),
        "userId": str(user_id),
        "displayName": display_name,
        "preferenceWeights": dict(preference_weights),
        "riskTolerance": float(risk_tolerance),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()
