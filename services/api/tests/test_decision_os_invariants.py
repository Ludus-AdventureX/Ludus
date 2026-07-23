from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import Enum, UniqueConstraint

import app.models  # noqa: F401
from app.analyses.schemas import DeepAnalysisRequest, DeepAnalysisResult
from app.db import Base
from app.decisions.schemas import SignoffPayload, SignoffRequest, SystemRecommendation
from app.evidence.schemas import SourceRecord
from app.simulations.schemas import SimulationRun
from app.tenancy.schemas import User as UserContract
from app.types import (
    AnalysisRunStatus,
    AnalysisStatus,
    CaseOperationalStatus,
    DecisionLifecycleStage,
    DecisionStatus,
    NodeType,
)


def test_repaired_enum_symbols_share_one_canonical_value_set() -> None:
    assert AnalysisStatus is AnalysisRunStatus
    assert DecisionStatus is DecisionLifecycleStage
    assert [item.value for item in AnalysisRunStatus] == [
        "queued",
        "planning",
        "retrieving",
        "analyzing",
        "criticizing",
        "synthesizing",
        "validating",
        "ready",
        "blocked",
        "needs_attention",
        "cancelled",
    ]
    assert [item.value for item in NodeType] == [
        "decision",
        "lever",
        "constraint",
        "external",
        "unknown",
        "intermediate",
        "outcome",
        "indicator",
    ]


def test_case_lifecycle_and_operational_status_are_separate() -> None:
    lifecycle = {item.value for item in DecisionLifecycleStage}
    operational = {item.value for item in CaseOperationalStatus}

    assert lifecycle == {
        "draft",
        "scoped",
        "ready",
        "running",
        "review",
        "pending_signoff",
        "decided",
        "monitoring",
    }
    assert operational == {
        "ok",
        "blocked",
        "needs_attention",
        "cancelled",
        "reopened",
        "archived",
    }
    assert lifecycle.isdisjoint({"blocked", "cancelled", "reopened", "archived"})


def test_decision_case_uses_canonical_database_identifier() -> None:
    columns = Base.metadata.tables["decision_cases"].c
    assert "decision_case_id" in columns
    assert "case_id" not in columns


def test_membership_session_and_candidate_contracts_are_single_source() -> None:
    membership = Base.metadata.tables["workspace_memberships"].c
    session = Base.metadata.tables["user_sessions"].c

    assert {"workspace_id", "user_id", "role", "capabilities", "status"} <= set(membership.keys())
    assert {"id", "user_id", "token_version", "expires_at", "revoked_at"} <= set(session.keys())
    assert "candidate_revisions" in Base.metadata.tables
    assert "candidate_updates" not in Base.metadata.tables
    assert "memory_candidates" not in Base.metadata.tables


def test_tenant_unique_constraints_include_workspace() -> None:
    global_tables = {"users", "workspaces", "user_sessions"}
    for table_name, table in Base.metadata.tables.items():
        if table_name in global_tables:
            continue
        for constraint in table.constraints:
            if isinstance(constraint, UniqueConstraint):
                assert "workspace_id" in {column.name for column in constraint.columns}


def test_database_status_columns_use_enums() -> None:
    status_like_names = {"status", "operational_status", "role", "scope", "formality", "actor"}
    for table in Base.metadata.tables.values():
        for column in table.c:
            if column.name in status_like_names:
                assert isinstance(column.type, Enum), f"{table.name}.{column.name}"

_CANONICAL_TIME = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)


def _source_record_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "source-1",
        "workspaceId": "workspace-1",
        "decisionCaseId": "case-1",
        "sourceScope": "pre_run",
        "kind": "human_input",
        "canonicalUri": "ludus://case/case-1/input/source-1",
        "title": "User-provided constraint",
        "contentHash": "sha256:source-1",
        "sourceVersion": "1",
        "originMode": "live",
        "createdAt": _CANONICAL_TIME,
    }
    payload.update(overrides)
    return payload


def _signoff_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "caseVersion": 3,
        "sourceAnalysisRunId": "analysis-run-1",
        "sourceReportArtifactId": "report-1",
        "sourceJudgmentSetId": "judgment-set-1",
        "sourceDissentRecordId": "dissent-1",
        "systemRecommendation": {
            "kind": "abstain",
            "reasonCodes": ["fatal-unknown"],
            "rationale": "Evidence does not support a single option.",
        },
        "selectedOptionId": "human-selected-option",
        "decisionDraft": "Proceed only after the fatal unknown is resolved.",
        "conditions": ["Validate the supplier capacity."],
        "thresholds": [
            {
                "metric": "validated-capacity",
                "operator": ">=",
                "value": "1000 units/month",
                "actionIfMissed": "Pause the rollout.",
            }
        ],
        "exitCriteria": ["Capacity remains below threshold for two reviews."],
        "actionItems": [
            {
                "id": "action-1",
                "text": "Run supplier audit.",
                "owner": "Decision owner",
                "dueAt": date(2026, 8, 1),
                "status": "open",
            }
        ],
        "leadingIndicators": [
            {
                "id": "indicator-1",
                "metric": "validated-capacity",
                "expectedDirection": "up",
                "threshold": ">= 1000 units/month",
                "checkCadence": "weekly",
            }
        ],
        "acceptedUnknownIds": ["unknown-1"],
        "reviewDate": date(2026, 8, 15),
    }
    payload.update(overrides)
    return payload


def _simulation_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "simulation-1",
        "workspaceId": "workspace-1",
        "decisionCaseId": "case-1",
        "graphId": "graph-1",
        "graphVersionId": "graph-version-1",
        "strategyVersionId": "strategy-version-1",
        "scenarioVersionId": "scenario-version-1",
        "scoreDefinitionId": "score-definition-1",
        "scoreDefinitionVersion": "1.0.0",
        "decisionMakerProfileId": "profile-1",
        "decisionMakerProfileVersion": 2,
        "riskTolerance": 0.4,
        "engineVersion": "1.0.0",
        "scenarioId": "scenario-1",
        "simulationMode": "formal",
        "epsilon": 0.0001,
        "maxSteps": 50,
        "steps": 12,
        "inputHash": "sha256:simulation-1",
        "nodeResults": {"outcome-1": 0.75},
        "optionScores": [{"optionId": "option-1", "score": 0.65}],
        "topDrivers": [{"nodeId": "driver-1", "scoreDelta": 0.2}],
        "recommendationShift": "No change",
        "convergenceStatus": "converged",
        "originModes": ["fixture"],
        "createdAt": _CANONICAL_TIME,
    }
    payload.update(overrides)
    return payload


def test_source_records_separate_pre_run_and_run_frozen_contracts() -> None:
    pre_run = SourceRecord.model_validate(_source_record_payload())
    assert pre_run.root.source_scope == "pre_run"
    assert "analysisRunId" not in pre_run.model_dump(by_alias=True)

    with pytest.raises(ValidationError):
        SourceRecord.model_validate(
            _source_record_payload(analysisRunId="analysis-run-1")
        )
    with pytest.raises(ValidationError):
        SourceRecord.model_validate(
            _source_record_payload(sourceScope="run_frozen")
        )
    with pytest.raises(ValidationError):
        payload_without_scope = _source_record_payload()
        payload_without_scope.pop("sourceScope")
        SourceRecord.model_validate(payload_without_scope)

    frozen = SourceRecord.model_validate(
        _source_record_payload(
            id="source-2",
            sourceScope="run_frozen",
            analysisRunId="analysis-run-1",
            frozenFromSourceRecordId="source-1",
            frozenAt=_CANONICAL_TIME + timedelta(seconds=1),
        )
    )
    assert frozen.root.source_scope == "run_frozen"
    assert frozen.root.analysis_run_id == "analysis-run-1"



def test_source_contract_rejects_fabricated_raw_artifacts_for_human_inputs() -> None:
    for source_kind in ("human_input", "case_snapshot"):
        with pytest.raises(ValidationError):
            SourceRecord.model_validate(
                _source_record_payload(
                    kind=source_kind,
                    rawArtifactId="fabricated-raw-artifact",
                )
            )

    uploaded = SourceRecord.model_validate(
        _source_record_payload(
            kind="uploaded_file",
            rawArtifactId="real-upload-artifact",
        )
    )
    assert uploaded.root.raw_artifact_id == "real-upload-artifact"


def test_content_hash_rejects_internal_whitespace() -> None:
    with pytest.raises(ValidationError):
        SourceRecord.model_validate(_source_record_payload(contentHash="sha256:not valid"))


def test_deep_analysis_budget_rejects_non_finite_values() -> None:
    request = {
        "workspaceId": "workspace-1",
        "decisionCaseId": "case-1",
        "analysisRunId": "analysis-run-1",
        "charterId": "charter-1",
        "charterVersion": 1,
        "caseSnapshotHash": "sha256:case",
        "dossierSnapshotHash": "sha256:dossier",
        "materialSnapshotHash": "sha256:materials",
        "analysisDepth": "focused",
        "method": {
            "id": "hardtech-market-direction",
            "version": "1.1.0",
            "contentHash": "sha256:method",
        },
        "allowedTools": ["search_web"],
        "allowedConnectorIds": ["connector-1"],
        "idempotencyKey": "deep-analysis-1",
    }
    for budget in ({"tokens": math.nan}, {"tokens": math.inf}):
        with pytest.raises(ValidationError):
            DeepAnalysisRequest.model_validate({**request, "budget": budget})


def test_system_recommendation_requires_option_or_explicit_abstention() -> None:
    option = SystemRecommendation.model_validate({"kind": "option", "optionId": "option-1"})
    assert option.root.kind == "option"

    abstain = SystemRecommendation.model_validate(
        {
            "kind": "abstain",
            "reasonCodes": ["fatal-unknown"],
            "rationale": "Evidence is insufficient.",
        }
    )
    assert abstain.model_dump(by_alias=True)["kind"] == "abstain"

    with pytest.raises(ValidationError):
        SystemRecommendation.model_validate({"kind": "option", "optionId": "   "})
    with pytest.raises(ValidationError):
        SystemRecommendation.model_validate(
            {
                "kind": "abstain",
                "reasonCodes": ["fatal-unknown"],
                "rationale": "Evidence is insufficient.",
                "optionId": "option-1",
            }
        )
    with pytest.raises(ValidationError):
        SystemRecommendation.model_validate(
            {"kind": "abstain", "reasonCodes": [], "rationale": "No evidence."}
        )


def test_signoff_payload_freezes_all_18_fields_and_preserves_abstain() -> None:
    expected_properties = [
        "caseVersion",
        "sourceAnalysisRunId",
        "sourceReportArtifactId",
        "sourceJudgmentSetId",
        "sourceDissentRecordId",
        "sourceCausalGraphId",
        "sourceCausalGraphVersionId",
        "sourceSimulationRunId",
        "systemRecommendation",
        "selectedOptionId",
        "decisionDraft",
        "conditions",
        "thresholds",
        "exitCriteria",
        "actionItems",
        "leadingIndicators",
        "acceptedUnknownIds",
        "reviewDate",
    ]
    schema = SignoffPayload.model_json_schema(mode="serialization")
    assert list(schema["properties"]) == expected_properties
    assert len(schema["properties"]) == 18

    payload = SignoffPayload.model_validate(_signoff_payload())
    serialized = payload.model_dump(by_alias=True, mode="json")
    assert serialized["systemRecommendation"]["kind"] == "abstain"
    assert serialized["conditions"] == ["Validate the supplier capacity."]
    assert serialized["thresholds"][0]["actionIfMissed"] == "Pause the rollout."
    assert serialized["actionItems"][0]["id"] == "action-1"

    with pytest.raises(ValidationError):
        SignoffPayload.model_validate(
            _signoff_payload(sourceCausalGraphId="graph-1")
        )
    with pytest.raises(ValidationError):
        SignoffPayload.model_validate(
            _signoff_payload(sourceSimulationRunId="simulation-1")
        )

    replayed = SignoffPayload.model_validate(
        _signoff_payload(
            sourceCausalGraphId="graph-1",
            sourceCausalGraphVersionId="graph-version-1",
            sourceSimulationRunId="simulation-1",
        )
    )
    assert replayed.source_simulation_run_id == "simulation-1"


def test_deep_analysis_io_uses_only_canonical_case_and_run_identifiers() -> None:
    assert [field.alias for field in DeepAnalysisRequest.model_fields.values()] == [
        "workspaceId",
        "decisionCaseId",
        "analysisRunId",
        "charterId",
        "charterVersion",
        "caseSnapshotHash",
        "dossierSnapshotHash",
        "materialSnapshotHash",
        "analysisDepth",
        "method",
        "budget",
        "allowedTools",
        "allowedConnectorIds",
        "idempotencyKey",
    ]
    assert [field.alias for field in DeepAnalysisResult.model_fields.values()] == [
        "analysisRunId",
        "runManifestId",
        "runManifestHash",
        "judgmentSetId",
        "dissentRecordId",
        "draftRecommendationId",
        "unresolvedUnknownIds",
        "validatorResults",
        "qualityGateResultId",
        "provenanceHash",
    ]
    for model in (DeepAnalysisRequest, DeepAnalysisResult):
        aliases = {field.alias for field in model.model_fields.values()}
        assert "caseId" not in aliases
        assert "runId" not in aliases


def test_simulation_run_freezes_replay_inputs_and_rejects_invalid_numbers() -> None:
    simulation = SimulationRun.model_validate(_simulation_payload())
    serialized = simulation.model_dump(by_alias=True, mode="json")
    assert {
        "graphId",
        "graphVersionId",
        "strategyVersionId",
        "scenarioVersionId",
        "scoreDefinitionId",
        "scoreDefinitionVersion",
        "decisionMakerProfileId",
        "decisionMakerProfileVersion",
        "riskTolerance",
        "engineVersion",
        "epsilon",
        "maxSteps",
        "inputHash",
    } <= set(serialized)

    invalid_payloads = [
        _simulation_payload(steps=51),
        _simulation_payload(riskTolerance=-0.01),
        _simulation_payload(riskTolerance=1.01),
        _simulation_payload(epsilon=0),
        _simulation_payload(nodeResults={"outcome-1": math.nan}),
        _simulation_payload(optionScores=[{"optionId": "option-1", "score": math.inf}]),
    ]
    for payload in invalid_payloads:
        with pytest.raises(ValidationError):
            SimulationRun.model_validate(payload)


def test_sensitive_hashes_are_internal_only_in_serialization_contracts() -> None:
    user = UserContract.model_validate(
        {
            "id": "user-1",
            "email": "owner@example.invalid",
            "passwordHash": "not-a-real-password-hash",
            "status": "active",
            "createdAt": _CANONICAL_TIME,
            "updatedAt": _CANONICAL_TIME,
        }
    )
    assert "passwordHash" not in user.model_dump(by_alias=True, mode="json")

    signoff = SignoffRequest.model_validate(
        {
            "id": "signoff-1",
            "workspaceId": "workspace-1",
            "decisionCaseId": "case-1",
            "requestedByUserId": "user-1",
            "payload": _signoff_payload(),
            "payloadHash": "sha256:signoff-payload",
            "status": "pending",
            "nonceHash": "sha256:nonce",
            "nonceIssuedAt": _CANONICAL_TIME,
            "expiresAt": _CANONICAL_TIME + timedelta(hours=1),
            "createdAt": _CANONICAL_TIME,
        }
    )
    assert "nonceHash" not in signoff.model_dump(by_alias=True, mode="json")


def test_generated_openapi_has_required_discriminators_and_hides_sensitive_fields() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    document = json.loads(
        (repository_root / "packages/contracts/openapi.json").read_text(encoding="utf-8")
    )
    schemas = document["components"]["schemas"]

    union_variants = {
        "SourceRecord": (
            "sourceScope",
            ("PreRunSourceRecord", "RunFrozenSourceRecord"),
        ),
        "SourceSpan": (
            "sourceScope",
            ("PreRunSourceSpan", "RunFrozenSourceSpan"),
        ),
        "SystemRecommendation": (
            "kind",
            ("OptionSystemRecommendation", "AbstainSystemRecommendation"),
        ),
    }
    for union_name, (discriminator, variants) in union_variants.items():
        assert schemas[union_name]["discriminator"]["propertyName"] == discriminator
        assert len(schemas[union_name]["oneOf"]) == 2
        for variant in variants:
            assert discriminator in schemas[variant]["required"]

    for source_variant in (
        "PreRunSourceRecord",
        "RunFrozenSourceRecord",
    ):
        assert "kind" in schemas[source_variant]["required"]
    assert "analysisRunId" not in schemas["PreRunSourceRecord"]["properties"]
    assert {
        "analysisRunId",
        "frozenFromSourceRecordId",
        "frozenAt",
    } <= set(schemas["RunFrozenSourceRecord"]["required"])
    assert "passwordHash" not in schemas["User"]["properties"]
    assert "nonceHash" not in schemas["SignoffRequest"]["properties"]
