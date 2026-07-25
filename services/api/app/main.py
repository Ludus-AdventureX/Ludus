from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from app.a2a.mount import mount_a2a
from app.auth.guest import router as guest_alpha_router
from app.auth.routes import router as auth_router
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
# PROTOTYPE (guest alpha): hidden from OpenAPI and hard-gated by
# ENABLE_GUEST_ALPHA (uniform 404 when disabled); no product contract.
app.include_router(guest_alpha_router)
# PROTOTYPE (A2A remote agent, PandaAI track): mount-time gated by A2A_ENABLED;
# when the flag is off nothing is mounted and the app is unchanged.
mount_a2a(app)


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    return HealthResponse()