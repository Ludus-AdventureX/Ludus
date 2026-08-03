from __future__ import annotations

import math
from typing import Literal

from pydantic import Field, field_validator

from app.contracts.schemas import CanonicalModel, ContentHash, Identifier, NonEmptyText
from app.types import FormalAnalysisLevel


class ChainLinkKind(str):
    """Decision-chain link kinds: the four canonical link types that the
    validator audits against. Premise → Evidence → Inference → Decision.
    """

    PREMISE = "premise"
    EVIDENCE = "evidence"
    INFERENCE = "inference"
    DECISION = "decision"


class ChainLink(CanonicalModel):
    """One decision-chain link. Produced by planning (initial draft) and
    refined by each subsequent stage; the validator audits by link_id.
    """

    link_id: Identifier
    kind: Literal["premise", "evidence", "inference", "decision"]
    text: NonEmptyText
    cites_evidence_ids: list[Identifier] = []
    cites_packet_ids: list[Identifier] = []
    supports_link_ids: list[Identifier] = []
    stage: NonEmptyText  # stage that created/updated this link


class ChainLinkUpdates(CanonicalModel):
    """Per-stage output: which links were added/confirmed/refuted this round."""

    added: list[ChainLink] = []
    confirmed: list[Identifier] = []
    refuted: list[Identifier] = []


class DecisionChain(CanonicalModel):
    """Accumulated decision chain across all stages (validator input)."""

    links: list[ChainLink] = []


class MethodVersionRef(CanonicalModel):
    id: Identifier
    version: NonEmptyText
    content_hash: ContentHash


class ValidatorFinding(CanonicalModel):
    code: Identifier
    message: NonEmptyText
    artifact_ids: list[Identifier]


class ValidatorResult(CanonicalModel):
    validator_id: Literal[
        "V1_scope_charter",
        "V2_source_traceability",
        "V3_evidence_quality",
        "V4_claim_evidence_entailment",
        "V5_contradiction_alignment",
        "V6_unknown_assumption",
        "V7_adversarial_dissent",
        "V8_causal_simulation",
        "V9_publication_authority",
    ]
    validator_version: NonEmptyText
    outcome: Literal["pass", "warn", "block"]
    findings: list[ValidatorFinding]
    repair_target: str | None = None
    execution_mode: Literal["deterministic", "model_assisted", "hybrid"]
    model_invocation_ref: Identifier | None = None


class DeepAnalysisRequest(CanonicalModel):
    workspace_id: Identifier
    decision_case_id: Identifier
    analysis_run_id: Identifier
    charter_id: Identifier
    charter_version: int = Field(gt=0)
    case_snapshot_hash: ContentHash
    dossier_snapshot_hash: ContentHash
    material_snapshot_hash: ContentHash
    analysis_depth: FormalAnalysisLevel
    method: MethodVersionRef
    budget: dict[str, float]
    allowed_tools: list[Identifier]
    allowed_connector_ids: list[Identifier]
    idempotency_key: NonEmptyText

    @field_validator("budget")
    @classmethod
    def budget_values_are_non_negative(cls, budget: dict[str, float]) -> dict[str, float]:
        if any(not math.isfinite(value) or value < 0 for value in budget.values()):
            raise ValueError("analysis budget values must be finite and non-negative")
        return budget

    @field_validator("allowed_tools", "allowed_connector_ids")
    @classmethod
    def identifiers_are_unique(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("allowed identifiers must not contain duplicates")
        return values


class DeepAnalysisResult(CanonicalModel):
    analysis_run_id: Identifier
    run_manifest_id: Identifier
    run_manifest_hash: ContentHash
    judgment_set_id: Identifier
    dissent_record_id: Identifier
    draft_recommendation_id: Identifier
    unresolved_unknown_ids: list[Identifier]
    validator_results: list[ValidatorResult]
    quality_gate_result_id: Identifier
    provenance_hash: ContentHash
