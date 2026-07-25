"""HTTP handlers for the SIM-02A simulation run surface (CCR-20260724-SIM-02A).

Exactly two routes: POST run create and GET run replay. The router object is
RELATIVE (`/simulations/{graphId}`); mounting under ``workspace_router`` — which
alone owns ``/api/workspaces/{workspaceId}`` and ``require_workspace_context`` —
plus OpenAPI catalog registration belong to the Contract Lead (§10). This module
performs no membership parsing of its own.

Error discipline (§8): mapping is by exception type / stable ``code`` attribute
only, never by message text; every scope denial collapses into the uniform
``CASE_NOT_FOUND``; the two Addendum A1 lower-snake codes pass through verbatim.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import IdempotencyRecord
from app.security.csrf import require_csrf
from app.security.envelope import ApiFailure, failure_body
from app.tenancy.context import (
    WorkspaceContext,
    require_capability,
    require_workspace_context,
)
from app.types import WorkspaceCapability

from .domain import SimulationAuthorizationError, SimulationError
from .errors import (
    SimulationPersistenceError,
    SimulationRepositoryError,
    simulation_scope_not_found,
)
from .idempotency import (
    IDEMPOTENCY_HEADER,
    RESPONSE_KIND_SUCCESS,
    RUN_CREATE_ROUTE_KEY,
    IdempotencyRaceError,
    build_idempotency_record,
    idempotency_conflict,
    normalized_request_hash,
    validate_idempotency_key,
)
from .repository import SimulationInputRepository
from .run_policy import (
    SimulationRunRateLimiter,
    enforce_formal_overrides,
    enforce_graph_budget,
    simulation_not_converged,
    terminal_run_status,
)
from .schemas_api import SimulationRunCreateRequest, run_data_from_view
from .service import SimulationRunRequest, SimulationRunService, SimulationRunView

router = APIRouter(prefix="/simulations/{graphId}", tags=["simulations"])

# The verbatim Addendum A1 fail-closed codes: deliberate lower-snake exceptions
# to the uppercase API-code convention, frozen across every later SIM CCR.
_VERBATIM_DOMAIN_CODES = frozenset(
    {"strategy_edge_gating_unsupported", "score_constraint_operator_unsupported"}
)


def _map_domain_error(exc: SimulationError) -> ApiFailure:
    """§8 mapping by exception type / stable ``code`` attribute — never message text."""

    if isinstance(exc, SimulationPersistenceError):
        return ApiFailure(
            "SIMULATION_PERSISTENCE_FAILED",
            "Persisting the simulation run failed. Retry the request.",
            http_status=500,
            retryable=True,
        )
    if isinstance(exc, SimulationRepositoryError):
        if exc.code == "graph_scope_mismatch":
            # Same-workspace cross-graph anchors: anti-enumeration precedence.
            return simulation_scope_not_found()
        if exc.code == "formal_authorization_rejected":
            return _graph_not_confirmed()
        if exc.code in _VERBATIM_DOMAIN_CODES:
            return ApiFailure(
                exc.code,
                "The simulation input uses a contract feature the engine does not execute.",
                http_status=422,
            )
        return _simulation_input_invalid(exc.code)
    if isinstance(exc, SimulationAuthorizationError):
        return _graph_not_confirmed()
    # Remaining domain errors (graph invariants, input membership) are same-tenant
    # contract violations surfaced through the engine/assembly layers.
    return _simulation_input_invalid("simulation_input_rejected")


def _graph_not_confirmed() -> ApiFailure:
    return ApiFailure(
        "GRAPH_NOT_CONFIRMED",
        "Formal simulation requires a confirmed graph version.",
        http_status=409,
    )


def _simulation_input_invalid(domain_code: str) -> ApiFailure:
    return ApiFailure(
        "SIMULATION_INPUT_INVALID",
        "The simulation input violates the run contract.",
        http_status=422,
        details={"domainCode": domain_code},
    )


def _success_payload(view: SimulationRunView, *, replay: bool) -> dict:
    data = run_data_from_view(view).model_dump(mode="json", by_alias=True)
    payload: dict = {"ok": True, "data": data}
    if replay:
        # §4.9: meta.idempotencyReplay is present ONLY on replays.
        payload["meta"] = {"idempotencyReplay": True}
    return payload


async def _replay_response(
    service: SimulationRunService,
    context: WorkspaceContext,
    graph_id: UUID,
    record: IdempotencyRecord,
) -> JSONResponse:
    """Replay the committed terminal outcome (§4.7): same status, same body."""

    view = await service.get_run(context, graph_id, record.resource_id)
    if record.response_kind == RESPONSE_KIND_SUCCESS:
        return JSONResponse(
            status_code=record.http_status,
            content=_success_payload(view, replay=True),
        )
    return JSONResponse(
        status_code=record.http_status,
        content=failure_body(simulation_not_converged(view.id, view.convergence_status)),
    )


@router.post("/runs", status_code=201)
async def create_simulation_run(
    payload: SimulationRunCreateRequest,
    request: Request,
    graph_id: UUID = Path(alias="graphId"),
    context: WorkspaceContext = Depends(
        require_capability(WorkspaceCapability.CONTRIBUTE)
    ),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> JSONResponse:
    """POST run (§5): membership + contribute + CSRF + Idempotency-Key required."""

    idempotency_key = validate_idempotency_key(request.headers.get(IDEMPOTENCY_HEADER))

    # Rate limiting is independent of idempotency (§9): metered before any
    # replay lookup or engine work; a 429 never consumes the key.
    await SimulationRunRateLimiter().check_run_attempt(
        db, workspace_id=context.workspace_id, user_id=context.user_id
    )

    request_hash = normalized_request_hash(
        payload.model_dump(mode="json", by_alias=True), graph_id
    )
    repository = SimulationInputRepository(db)
    service = SimulationRunService(db)

    existing = await repository.get_idempotency_record(
        context.workspace_id, RUN_CREATE_ROUTE_KEY, idempotency_key
    )
    if existing is not None:
        if existing.normalized_request_hash != request_hash:
            raise idempotency_conflict()
        return await _replay_response(service, context, graph_id, existing)

    # Path graphId is the tenancy anchor (§5.2): the graph must exist in this
    # workspace and the referenced graph version must belong to exactly it;
    # any mismatch is the uniform 404 before any engine or budget work.
    graph = await repository.get_graph(context.workspace_id, graph_id)
    if graph is None:
        raise simulation_scope_not_found()
    graph_version = await repository.get_graph_version(
        context.workspace_id, graph.decision_case_id, payload.graph_version_id
    )
    if graph_version is None or graph_version.graph_id != graph_id:
        raise simulation_scope_not_found()

    try:
        enforce_formal_overrides(payload.mode, payload.node_overrides)
        await enforce_graph_budget(
            repository, context.workspace_id, payload.graph_version_id
        )

        run_request = SimulationRunRequest(
            decision_case_id=graph.decision_case_id,
            graph_version_id=payload.graph_version_id,
            strategy_version_id=payload.strategy_version_id,
            scenario_version_id=payload.scenario_version_id,
            score_definition_id=payload.score_definition_id,
            simulation_mode=payload.mode,
            decision_maker_profile_id=payload.decision_maker_profile_id,
            decision_maker_profile_version=payload.decision_maker_profile_version,
            epsilon=payload.epsilon,
            max_steps=payload.max_steps,
            node_overrides=dict(payload.node_overrides),
            include_sensitivity=True,  # server-fixed (§5.6)
        )

        def build_record(view: SimulationRunView) -> IdempotencyRecord:
            http_status, response_kind = terminal_run_status(
                payload.mode, view.convergence_status
            )
            return build_idempotency_record(
                workspace_id=context.workspace_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                resource_id=view.id,
                http_status=http_status,
                response_kind=response_kind,
            )

        try:
            view, record = await service.run_and_record_idempotent(
                context, run_request, build_record
            )
        except IdempotencyRaceError:
            committed = await repository.get_idempotency_record(
                context.workspace_id, RUN_CREATE_ROUTE_KEY, idempotency_key
            )
            if committed is None or committed.normalized_request_hash != request_hash:
                raise idempotency_conflict() from None
            return await _replay_response(service, context, graph_id, committed)
    except ApiFailure:
        raise
    except SimulationError as exc:
        raise _map_domain_error(exc) from exc

    if record.response_kind != RESPONSE_KIND_SUCCESS:
        # Formal non-convergence (§7): the run IS persisted for audit; the
        # response is the 409 with tenant-safe details.
        raise simulation_not_converged(view.id, view.convergence_status)
    return JSONResponse(status_code=201, content=_success_payload(view, replay=False))


@router.get("/runs/{simulationRunId}")
async def get_simulation_run(
    graph_id: UUID = Path(alias="graphId"),
    simulation_run_id: UUID = Path(alias="simulationRunId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """GET replay (§6): active membership only; byte-equal frozen inputs + results."""

    view = await SimulationRunService(db).get_run(context, graph_id, simulation_run_id)
    return _success_payload(view, replay=False)
