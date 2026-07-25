"""Signoff, append-only DecisionRecord and Review routes."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.decisions.schemas import (
    DecisionRecord as DecisionRecordSchema,
    Review as ReviewSchema,
    ReviewCreateRequest,
    SignoffCreateRequest,
    SignoffRequest as SignoffRequestSchema,
    SignoffSignCommand,
)
from app.models import (
    DecisionCase,
    DecisionLifecycleEvent,
    DecisionRecord,
    DecisionReview,
    SignoffRequest,
)
from app.reports.models import ReportArtifact
from app.security.csrf import require_csrf
from app.security.envelope import ApiFailure, workspace_not_found
from app.tenancy.context import WorkspaceContext, require_capability, require_workspace_context
from app.types import (
    DecisionLifecycleStage,
    DomainEventActor,
    SignoffRequestStatus,
    WorkspaceCapability,
)

router = APIRouter(tags=["decisions"])


def _envelope(data: Any, event_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": True, "data": data}
    if event_id:
        payload["eventId"] = event_id
    return payload


def _not_found() -> ApiFailure:
    return workspace_not_found("CASE_NOT_FOUND", "The requested decision resource was not found.")


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _secret_hash(value: str) -> str:
    return _canonical_hash({"value": value})


def _uuid(value: Any, field: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise ApiFailure(
            "VALIDATION_FAILED",
            f"{field} must be a UUID string.",
            http_status=422,
            details={"field": field},
        ) from exc


def _origin_values(values: Any) -> list[str]:
    return [getattr(value, "value", str(value)) for value in (values or [])]


async def _case_for_workspace(
    db: AsyncSession, context: WorkspaceContext, decision_case_id: UUID
) -> DecisionCase:
    case = await db.scalar(
        select(DecisionCase).where(
            DecisionCase.workspace_id == context.workspace_id,
            DecisionCase.decision_case_id == decision_case_id,
        )
    )
    if case is None:
        raise _not_found()
    return case


async def _signoff_for_workspace(
    db: AsyncSession, context: WorkspaceContext, signoff_request_id: UUID
) -> SignoffRequest:
    request = await db.scalar(
        select(SignoffRequest).where(
            SignoffRequest.workspace_id == context.workspace_id,
            SignoffRequest.id == signoff_request_id,
        )
    )
    if request is None:
        raise _not_found()
    return request


async def _decision_for_workspace(
    db: AsyncSession, context: WorkspaceContext, decision_id: UUID
) -> DecisionRecord:
    record = await db.scalar(
        select(DecisionRecord).where(
            DecisionRecord.workspace_id == context.workspace_id,
            DecisionRecord.id == decision_id,
        )
    )
    if record is None:
        raise _not_found()
    return record


def _signoff_data(request: SignoffRequest) -> dict[str, Any]:
    return SignoffRequestSchema(
        id=str(request.id),
        workspace_id=str(request.workspace_id),
        decision_case_id=str(request.decision_case_id),
        requested_by_user_id=str(request.requested_by_user_id),
        payload=request.payload,
        payload_hash=request.payload_hash,
        status=request.status,
        nonce_hash=request.nonce_hash,
        nonce_issued_at=request.nonce_issued_at,
        expires_at=request.expires_at,
        created_at=request.created_at,
        signed_at=request.signed_at,
    ).model_dump(by_alias=True, mode="json")


def _decision_data(record: DecisionRecord) -> dict[str, Any]:
    return DecisionRecordSchema(
        id=str(record.id),
        workspace_id=str(record.workspace_id),
        decision_case_id=str(record.decision_case_id),
        case_version=record.case_version,
        record_kind=record.record_kind,
        supersedes_decision_record_id=(
            str(record.supersedes_decision_record_id)
            if record.supersedes_decision_record_id
            else None
        ),
        signoff_request_id=str(record.signoff_request_id),
        payload=record.payload,
        payload_hash=record.payload_hash,
        source_analysis_run_id=str(record.source_analysis_run_id),
        source_report_artifact_id=str(record.source_report_artifact_id),
        source_judgment_set_id=str(record.source_judgment_set_id),
        source_dissent_record_id=str(record.source_dissent_record_id),
        source_causal_graph_id=(str(record.source_causal_graph_id) if record.source_causal_graph_id else None),
        source_causal_graph_version_id=(
            str(record.source_causal_graph_version_id)
            if record.source_causal_graph_version_id
            else None
        ),
        source_simulation_run_id=(str(record.source_simulation_run_id) if record.source_simulation_run_id else None),
        origin_modes=_origin_values(record.origin_modes),
        system_recommendation=record.system_recommendation,
        selected_option_id=record.selected_option_id,
        decision_text=record.decision_text,
        conditions=record.conditions,
        thresholds=record.thresholds,
        exit_criteria=record.exit_criteria,
        action_items=record.action_items,
        leading_indicators=record.leading_indicators,
        accepted_unknown_ids=record.accepted_unknown_ids,
        review_date=record.review_date,
        signed_by_user_id=str(record.signed_by_user_id),
        signed_at=record.signed_at,
        signature_statement=record.signature_statement,
        signature_hash=record.signature_hash,
        record_hash=record.record_hash,
    ).model_dump(by_alias=True, mode="json")


def _review_data(review: DecisionReview) -> dict[str, Any]:
    return ReviewSchema(
        id=str(review.id),
        workspace_id=str(review.workspace_id),
        decision_case_id=str(review.decision_case_id),
        decision_record_id=str(review.decision_record_id),
        source_case_version=review.source_case_version,
        source_analysis_run_id=str(review.source_analysis_run_id),
        source_causal_graph_version_id=(
            str(review.source_causal_graph_version_id)
            if review.source_causal_graph_version_id
            else None
        ),
        source_simulation_run_id=(str(review.source_simulation_run_id) if review.source_simulation_run_id else None),
        review_date=review.review_date,
        outcome=review.outcome,
        recommendation_adoption=review.recommendation_adoption,
        execution_assessment=review.execution_assessment,
        decision_process_assessment=review.decision_process_assessment,
        outcome_quality=review.outcome_quality,
        observed_indicator_values=review.observed_indicator_values,
        threshold_breaches=review.threshold_breaches,
        external_changes=review.external_changes,
        actual_outcomes=review.actual_outcomes,
        assumption_results=review.assumption_results,
        lessons=review.lessons,
        next_decision_changes=review.next_decision_changes,
        notes=review.notes,
        next_review_date=review.next_review_date,
        created_by=str(review.created_by),
        created_at=review.created_at,
    ).model_dump(by_alias=True, mode="json")


async def _append_lifecycle_event(
    db: AsyncSession,
    *,
    context: WorkspaceContext,
    decision_case_id: UUID,
    from_stage: DecisionLifecycleStage,
    to_stage: DecisionLifecycleStage,
    command_type: str,
    command_id: UUID,
    payload_hash: str,
) -> None:
    db.add(
        DecisionLifecycleEvent(
            workspace_id=context.workspace_id,
            decision_case_id=decision_case_id,
            from_stage=from_stage,
            to_stage=to_stage,
            actor_type=DomainEventActor.USER,
            actor_id=context.user_id,
            command_type=command_type,
            command_id=command_id,
            payload_hash=payload_hash,
        )
    )


async def _report_for_signoff(
    db: AsyncSession,
    context: WorkspaceContext,
    decision_case_id: UUID,
    payload_doc: dict[str, Any],
) -> ReportArtifact:
    report_id = _uuid(payload_doc["sourceReportArtifactId"], "sourceReportArtifactId")
    report = await db.scalar(
        select(ReportArtifact).where(
            ReportArtifact.workspace_id == context.workspace_id,
            ReportArtifact.decision_case_id == decision_case_id,
            ReportArtifact.id == report_id,
            ReportArtifact.status == "ready",
        )
    )
    if report is None:
        raise ApiFailure(
            "SIGNOFF_REPORT_NOT_READY",
            "A signoff request requires a ready report for the same case.",
            http_status=409,
        )
    expected = {
        "sourceAnalysisRunId": str(report.analysis_run_id),
        "sourceReportArtifactId": str(report.id),
        "sourceJudgmentSetId": str(report.source_judgment_set_id),
        "sourceDissentRecordId": str(report.source_dissent_record_id),
    }
    mismatches = [key for key, value in expected.items() if payload_doc.get(key) != value]
    if mismatches:
        raise ApiFailure(
            "SIGNOFF_PAYLOAD_SOURCE_MISMATCH",
            "The signoff payload source projection does not match the ready report.",
            http_status=409,
            details={"fields": mismatches},
        )
    return report


@router.post(
    "/cases/{decisionCaseId}/signoff-requests",
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def create_signoff_request(
    body: SignoffCreateRequest,
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    context: WorkspaceContext = Depends(require_capability(WorkspaceCapability.REVIEW)),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    case = await _case_for_workspace(db, context, decision_case_id)
    payload_doc = body.payload.model_dump(by_alias=True, mode="json")
    payload_hash = _canonical_hash(payload_doc)
    await _report_for_signoff(db, context, decision_case_id, payload_doc)
    now = datetime.now(timezone.utc)
    nonce = secrets.token_urlsafe(32)
    request = SignoffRequest(
        workspace_id=context.workspace_id,
        decision_case_id=decision_case_id,
        requested_by_user_id=context.user_id,
        payload=payload_doc,
        payload_hash=payload_hash,
        status=SignoffRequestStatus.PENDING,
        nonce_hash=_secret_hash(nonce),
        nonce_issued_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    db.add(request)
    await db.flush()
    from_stage = DecisionLifecycleStage(case.status)
    case.status = DecisionLifecycleStage.PENDING_SIGNOFF
    case.updated_at = now
    await _append_lifecycle_event(
        db,
        context=context,
        decision_case_id=decision_case_id,
        from_stage=from_stage,
        to_stage=DecisionLifecycleStage.PENDING_SIGNOFF,
        command_type="create_signoff_request",
        command_id=request.id,
        payload_hash=payload_hash,
    )
    await db.commit()
    return _envelope({"signoffRequest": _signoff_data(request), "nonce": nonce})


@router.get("/signoff-requests/{signoffRequestId}")
async def read_signoff_request(
    signoff_request_id: UUID = Path(alias="signoffRequestId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    request = await _signoff_for_workspace(db, context, signoff_request_id)
    return _envelope(_signoff_data(request))


@router.post(
    "/signoff-requests/{signoffRequestId}/nonce-rotations",
    dependencies=[Depends(require_csrf)],
)
async def rotate_signoff_nonce(
    signoff_request_id: UUID = Path(alias="signoffRequestId"),
    context: WorkspaceContext = Depends(require_capability(WorkspaceCapability.SIGN)),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    request = await _signoff_for_workspace(db, context, signoff_request_id)
    if request.status != SignoffRequestStatus.PENDING:
        raise ApiFailure("SIGNOFF_REQUEST_NOT_PENDING", "Only pending signoff requests can rotate a nonce.", http_status=409)
    now = datetime.now(timezone.utc)
    nonce = secrets.token_urlsafe(32)
    request.nonce_hash = _secret_hash(nonce)
    request.nonce_issued_at = now
    request.expires_at = now + timedelta(minutes=15)
    await db.commit()
    return _envelope({"signoffRequest": _signoff_data(request), "nonce": nonce})


@router.post("/signoff-requests/{signoffRequestId}/sign", dependencies=[Depends(require_csrf)])
async def sign_signoff_request(
    body: SignoffSignCommand,
    signoff_request_id: UUID = Path(alias="signoffRequestId"),
    context: WorkspaceContext = Depends(require_capability(WorkspaceCapability.SIGN)),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    request = await _signoff_for_workspace(db, context, signoff_request_id)
    now = datetime.now(timezone.utc)
    if request.status != SignoffRequestStatus.PENDING:
        raise ApiFailure("SIGNOFF_REQUEST_NOT_PENDING", "Only pending signoff requests can be signed.", http_status=409)
    if request.expires_at <= now:
        request.status = SignoffRequestStatus.EXPIRED
        await db.commit()
        raise ApiFailure("SIGNOFF_REQUEST_EXPIRED", "The signoff nonce has expired.", http_status=409)
    if body.payload_hash != request.payload_hash or _secret_hash(body.nonce) != request.nonce_hash:
        raise ApiFailure("SIGNOFF_PROOF_INVALID", "The payload hash or nonce is invalid.", http_status=403)

    case = await _case_for_workspace(db, context, request.decision_case_id)
    report = await _report_for_signoff(db, context, request.decision_case_id, request.payload)
    previous_id = case.current_decision_record_id
    record_kind = "revision" if previous_id else "original"
    signed_case_version = case.current_version + 1
    signature_hash = _canonical_hash(
        {
            "payloadHash": request.payload_hash,
            "nonceHash": request.nonce_hash,
            "signatureStatement": body.signature_statement,
            "signedByUserId": str(context.user_id),
            "signedAt": now.isoformat(),
        }
    )
    record_hash = _canonical_hash(
        {
            "workspaceId": str(context.workspace_id),
            "decisionCaseId": str(request.decision_case_id),
            "signoffRequestId": str(request.id),
            "payloadHash": request.payload_hash,
            "signatureHash": signature_hash,
            "recordKind": record_kind,
            "supersedesDecisionRecordId": str(previous_id) if previous_id else None,
        }
    )
    payload = request.payload
    record = DecisionRecord(
        workspace_id=context.workspace_id,
        decision_case_id=request.decision_case_id,
        case_version=signed_case_version,
        record_kind=record_kind,
        supersedes_decision_record_id=previous_id,
        signoff_request_id=request.id,
        payload=payload,
        payload_hash=request.payload_hash,
        source_analysis_run_id=report.analysis_run_id,
        source_report_artifact_id=report.id,
        source_judgment_set_id=report.source_judgment_set_id,
        source_dissent_record_id=report.source_dissent_record_id,
        source_causal_graph_id=_uuid(payload["sourceCausalGraphId"], "sourceCausalGraphId") if payload.get("sourceCausalGraphId") else None,
        source_causal_graph_version_id=_uuid(payload["sourceCausalGraphVersionId"], "sourceCausalGraphVersionId") if payload.get("sourceCausalGraphVersionId") else None,
        source_simulation_run_id=_uuid(payload["sourceSimulationRunId"], "sourceSimulationRunId") if payload.get("sourceSimulationRunId") else None,
        origin_modes=report.origin_modes,
        system_recommendation=payload["systemRecommendation"],
        selected_option_id=payload["selectedOptionId"],
        decision_text=payload["decisionDraft"],
        conditions=payload["conditions"],
        thresholds=payload["thresholds"],
        exit_criteria=payload["exitCriteria"],
        action_items=payload["actionItems"],
        leading_indicators=payload["leadingIndicators"],
        accepted_unknown_ids=payload["acceptedUnknownIds"],
        review_date=payload["reviewDate"],
        signed_by_user_id=context.user_id,
        signed_at=now,
        signature_statement=body.signature_statement,
        signature_hash=signature_hash,
        record_hash=record_hash,
    )
    db.add(record)
    await db.flush()
    request.status = SignoffRequestStatus.SIGNED
    request.signed_at = now
    from_stage = DecisionLifecycleStage(case.status)
    case.status = DecisionLifecycleStage.DECIDED
    case.current_version = signed_case_version
    case.current_decision_record_id = record.id
    case.updated_at = now
    await _append_lifecycle_event(
        db,
        context=context,
        decision_case_id=request.decision_case_id,
        from_stage=from_stage,
        to_stage=DecisionLifecycleStage.DECIDED,
        command_type="sign_signoff_request",
        command_id=request.id,
        payload_hash=request.payload_hash,
    )
    await db.commit()
    return _envelope(_decision_data(record))


@router.get("/cases/{decisionCaseId}/decisions")
async def list_case_decisions(
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    limit: int = Query(default=50, ge=1, le=100),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _case_for_workspace(db, context, decision_case_id)
    records = (
        await db.execute(
            select(DecisionRecord)
            .where(
                DecisionRecord.workspace_id == context.workspace_id,
                DecisionRecord.decision_case_id == decision_case_id,
            )
            .order_by(DecisionRecord.created_at.desc())
            .limit(limit)
        )
    ).scalars()
    return _envelope({"items": [_decision_data(record) for record in records], "nextCursor": None})


@router.get("/decisions/{decisionId}")
async def read_decision(
    decision_id: UUID = Path(alias="decisionId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return _envelope(_decision_data(await _decision_for_workspace(db, context, decision_id)))


@router.get("/decisions/{decisionId}/reviews")
async def list_decision_reviews(
    decision_id: UUID = Path(alias="decisionId"),
    limit: int = Query(default=50, ge=1, le=100),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    record = await _decision_for_workspace(db, context, decision_id)
    reviews = (
        await db.execute(
            select(DecisionReview)
            .where(
                DecisionReview.workspace_id == context.workspace_id,
                DecisionReview.decision_record_id == record.id,
            )
            .order_by(DecisionReview.created_at.desc())
            .limit(limit)
        )
    ).scalars()
    return _envelope({"items": [_review_data(review) for review in reviews], "nextCursor": None})


@router.post(
    "/decisions/{decisionId}/reviews",
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def create_decision_review(
    body: ReviewCreateRequest,
    decision_id: UUID = Path(alias="decisionId"),
    context: WorkspaceContext = Depends(require_capability(WorkspaceCapability.REVIEW)),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    record = await _decision_for_workspace(db, context, decision_id)
    review = DecisionReview(
        workspace_id=context.workspace_id,
        decision_case_id=record.decision_case_id,
        decision_record_id=record.id,
        source_case_version=body.source_case_version,
        source_analysis_run_id=_uuid(body.source_analysis_run_id, "sourceAnalysisRunId"),
        source_causal_graph_version_id=_uuid(body.source_causal_graph_version_id, "sourceCausalGraphVersionId") if body.source_causal_graph_version_id else None,
        source_simulation_run_id=_uuid(body.source_simulation_run_id, "sourceSimulationRunId") if body.source_simulation_run_id else None,
        review_date=body.review_date.isoformat(),
        outcome=body.outcome,
        recommendation_adoption=body.recommendation_adoption,
        execution_assessment=body.execution_assessment,
        decision_process_assessment=body.decision_process_assessment,
        outcome_quality=body.outcome_quality,
        observed_indicator_values=body.observed_indicator_values,
        threshold_breaches=body.threshold_breaches,
        external_changes=body.external_changes,
        actual_outcomes=body.actual_outcomes,
        assumption_results=[item.model_dump(by_alias=True, mode="json") for item in body.assumption_results],
        lessons=body.lessons,
        next_decision_changes=body.next_decision_changes,
        notes=body.notes,
        next_review_date=body.next_review_date.isoformat() if body.next_review_date else None,
        created_by=context.user_id,
    )
    db.add(review)
    await db.commit()
    return _envelope(_review_data(review))


@router.get("/decisions/{decisionId}/reviews/{reviewId}")
async def read_decision_review(
    decision_id: UUID = Path(alias="decisionId"),
    review_id: UUID = Path(alias="reviewId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    record = await _decision_for_workspace(db, context, decision_id)
    review = await db.scalar(
        select(DecisionReview).where(
            DecisionReview.workspace_id == context.workspace_id,
            DecisionReview.decision_record_id == record.id,
            DecisionReview.id == review_id,
        )
    )
    if review is None:
        raise _not_found()
    return _envelope(_review_data(review))
