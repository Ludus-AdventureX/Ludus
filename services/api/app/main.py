from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from app.analyses.case_reads import router as case_reads_router
from app.analyses.routes import router as analyses_router
from app.auth.guest import router as guest_alpha_router
from app.auth.routes import router as auth_router
from app.evidence.routes import router as evidence_router
from app.security.envelope import register_error_handlers
from app.tenancy.routes import workspace_router


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


app = FastAPI(
    title="Ludus API",
    version="0.1.0",
    description="API for the Ludus decision operating system.",
)

# Canonical router mounting is owned by the Contract Lead (CCR-20260724-005):
# auth endpoints per docs/product-plan/10 and the tenancy-guarded workspace
# router that Task 4+ resource routers must be included into.
register_error_handlers(app)
app.include_router(auth_router)
app.include_router(workspace_router)
# Deep-research pipeline surface (CCR-20260726-MOUNT-01): the Task 8 evidence
# read router and the Task 9 analysis SSE/resolution/cancel router each ship an
# absolute /api/workspaces/{workspaceId} prefix with a per-route
# require_workspace_context guard, so they mount on the app directly rather than
# under workspace_router (which would double the prefix); see CCR §M7.
app.include_router(evidence_router)
app.include_router(analyses_router)
# Case-scoped read projections (CCR-20260726-READ-01): run anchors + report
# list/read. Same absolute-prefix + per-route guard pattern as the analyses
# router above (§M7 precedent).
app.include_router(case_reads_router)
# PROTOTYPE (guest alpha): hidden from OpenAPI and hard-gated by
# ENABLE_GUEST_ALPHA (uniform 404 when disabled); no product contract.
app.include_router(guest_alpha_router)


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    return HealthResponse()