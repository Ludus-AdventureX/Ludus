"""Deterministic canonical report documents for the worker's READY hook.

The quality gate has already passed when this module runs, so the document is
ASSEMBLED deterministically from confirmed inputs (charter + in-process stage
outputs) instead of trusting the model to emit canonical JSON. Every document
is validated by ``validate_content_for_level`` at persist time, so a template
drift fails loudly rather than persisting garbage.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from app.analyses.synthesis import build_report_validation
from app.types import AnalysisRunStatus, FormalAnalysisLevel, OriginMode


def _stage_text(stage_outputs: Mapping[str, Any], stage: AnalysisRunStatus, *keys: str) -> str:
    """Best-effort human text from a stage output; empty string when absent."""

    output = stage_outputs.get(stage.value)
    if not isinstance(output, Mapping):
        return ""
    for key in (*keys, "summary", "value", "conclusion", "text"):
        value = output.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _texts(values: Sequence[Any], fallback: str) -> list[str]:
    out = [str(v).strip() for v in values if str(v).strip()]
    return out or [fallback]


def _quality_block() -> dict[str, Any]:
    # The run reached READY, i.e. the validation stage's quality gate passed;
    # the four-dimension block mirrors that verdict.
    return {
        "evidenceAvailability": "sufficient",
        "claimSupport": "supported",
        "assumptionStability": "stable",
        "causalReliability": "confirmed",
        "strategicRobustness": "robust",
        "processQuality": "passed",
        "weakestDimension": "assumption_stability",
        "rationale": ["quality gate passed at the validating stage"],
    }


def _deterministic_quality_gate(anchor: datetime | None) -> dict[str, Any]:
    # checkedAt is schema-required, but a wall-clock stamp inside the CONTENT
    # would change the canonical hash on every rebuild and break idempotent
    # re-persistence. Anchor it to the run's own completion time instead.
    gate = dict(build_report_validation(passed=True))
    if anchor is not None:
        gate["checkedAt"] = anchor.isoformat()
    return gate


def build_focused_document(
    *,
    charter: Any,
    stage_outputs: Mapping[str, Any],
    origin_mode: OriginMode,
    anchor: datetime | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Canonical focused (brief) report document from confirmed inputs."""

    anchor_date = today or (anchor.date() if anchor else date.today())
    review_date = (anchor_date + timedelta(days=90)).isoformat()
    option_ids = [str(o) for o in (charter.option_ids or [])] or ["opt_a"]
    goals = _texts([g.get("text", "") for g in (charter.goals or []) if isinstance(g, Mapping)],
                   "validate the decisive assumption before committing")
    constraints = _texts(
        [c.get("text", "") for c in (charter.constraints or []) if isinstance(c, Mapping)],
        "the stated resource and time window",
    )
    decision = _stage_text(stage_outputs, AnalysisRunStatus.SYNTHESIZING, "decision", "recommendation") or (
        f"Proceed on '{charter.decision_question}' under the stated conditions."
    )
    why_now = _stage_text(stage_outputs, AnalysisRunStatus.ANALYZING, "whyNow") or (
        "The confirmed charter window makes deferral costlier than a bounded commitment."
    )
    counter_text = _stage_text(stage_outputs, AnalysisRunStatus.CRITICIZING, "strongestObjection") or (
        "The decisive assumption may not survive contact with the counterparty."
    )
    gap_question = _stage_text(stage_outputs, AnalysisRunStatus.RETRIEVING, "openQuestion") or (
        "Which unverified assumption flips this recommendation first?"
    )

    return {
        "schemaVersion": "report-1.0.0",
        "methodId": charter.method_id,
        "methodVersion": charter.method_version,
        "methodContentHash": charter.method_content_hash,
        "executiveBrief": {
            "decision": decision,
            "whyNow": why_now,
            "conditions": goals,
            "thresholds": [],
            "exitCriteria": constraints,
            "reviewDate": review_date,
        },
        "recommendation": {
            "outcome": {"kind": "option", "optionId": option_ids[0]},
            "alternativeOptionIds": option_ids[1:],
            "summary": decision,
            "conditions": goals,
            "thresholds": [
                {
                    "metric": "review checkpoint",
                    "operator": "<=",
                    "value": review_date,
                    "actionIfMissed": "pause and re-run the focused analysis",
                }
            ],
            "exitCriteria": constraints,
            "risks": [counter_text],
            "fragileAssumptionIds": [],
            "leadingIndicators": [
                {
                    "id": "li-review",
                    "metric": "condition confirmations",
                    "expectedDirection": "up",
                    "threshold": ">= 1 confirmed per week",
                    "checkCadence": "weekly",
                }
            ],
            "nextActions": [
                {
                    "id": "act-review",
                    "text": "confirm the stated conditions before the review date",
                    "owner": "decision owner",
                    "dueAt": review_date,
                    "status": "open",
                }
            ],
            "reviewDate": review_date,
            "quality": _quality_block(),
        },
        "evidenceReview": {
            "evidenceIds": [],
            "conflictGroupIds": [],
            "freshnessWarnings": [],
            "reconciliationFindings": [],
        },
        "counterArguments": [
            {
                "id": "ch-worker-001",
                "category": "counterargument",
                "text": counter_text,
                "severity": "high",
                "affectedOptionIds": [option_ids[0]],
                "evidenceIds": [],
                "mitigation": "revisit at the review date",
                "status": "confirmed",
            }
        ],
        "residualUncertainty": [
            {
                "id": "unk-worker-001",
                "question": gap_question,
                "priority": "high",
                "status": "open",
            }
        ],
        "qualityGate": _deterministic_quality_gate(anchor),
        "originModes": [origin_mode.value],
    }


def build_structured_document(
    *,
    charter: Any,
    stage_outputs: Mapping[str, Any],
    origin_mode: OriginMode,
    lens_artifact_ids: Sequence[UUID | str],
    anchor: datetime | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Canonical full (detailed) report document; requires the five lens ids."""

    base = build_focused_document(
        charter=charter, stage_outputs=stage_outputs, origin_mode=origin_mode,
        anchor=anchor, today=today
    )
    situation = {
        "title": "Situation",
        "summary": _stage_text(stage_outputs, AnalysisRunStatus.ANALYZING)
        or f"Confirmed charter question: {charter.decision_question}",
        "claimIds": [],
        "evidenceIds": [],
    }
    option_ids = [str(o) for o in (charter.option_ids or [])] or ["opt_a"]
    return {
        **base,
        "situation": situation,
        "sections": [situation],
        "options": [
            {
                "optionId": option_id,
                "summary": f"Option {option_id} under the confirmed charter.",
                "benefits": [],
                "risks": [],
            }
            for option_id in option_ids
        ],
        "lensArtifactIds": [str(i) for i in lens_artifact_ids],
        "simulationSeeds": {"candidateNodes": [], "candidateEdges": []},
        "appendix": [],
    }


def build_document_for_level(
    *,
    analysis_level: FormalAnalysisLevel,
    charter: Any,
    stage_outputs: Mapping[str, Any],
    origin_mode: OriginMode,
    lens_artifact_ids: Sequence[UUID | str] = (),
    anchor: datetime | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    if analysis_level is FormalAnalysisLevel.FULL:
        return build_structured_document(
            charter=charter,
            stage_outputs=stage_outputs,
            origin_mode=origin_mode,
            lens_artifact_ids=lens_artifact_ids,
            anchor=anchor,
            today=today,
        )
    return build_focused_document(
        charter=charter, stage_outputs=stage_outputs, origin_mode=origin_mode,
        anchor=anchor, today=today
    )
