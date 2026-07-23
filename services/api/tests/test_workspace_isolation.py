"""Task 3 QA gate: workspace isolation (acceptance matrix rows W-01..W-04).

The DB-level negative tests run on the frozen baseline already (Task 19A
constraints). The HTTP-level tests skip until ``app.tenancy`` routes exist.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.models import WorkspaceMembership
from app.types import WorkspaceCapability, WorkspaceMembershipStatus, WorkspaceRole

from tests.conftest import TenancyFixture


# ---------------------------------------------------------------------------
# DB-level isolation regressions: executable on the frozen baseline today.
# ---------------------------------------------------------------------------


async def test_membership_unique_per_workspace_user(
    db_connection: AsyncConnection, two_tenants: TenancyFixture
) -> None:
    """W-03 support: one membership row per workspace+user is DB-enforced."""

    with pytest.raises(IntegrityError):
        await db_connection.execute(
            insert(WorkspaceMembership).values(
                id=uuid4(),
                workspace_id=two_tenants.workspace_a,
                user_id=two_tenants.user_a,
                role=WorkspaceRole.MEMBER,
                capabilities=[WorkspaceCapability.CONTRIBUTE],
                status=WorkspaceMembershipStatus.ACTIVE,
            )
        )


async def test_capability_projection_is_per_membership(
    db_connection: AsyncConnection, two_tenants: TenancyFixture
) -> None:
    """W-03: capabilities live on the membership row; tenants stay distinct."""

    rows = (
        (
            await db_connection.execute(
                select(
                    WorkspaceMembership.workspace_id,
                    WorkspaceMembership.capabilities,
                ).where(
                    WorkspaceMembership.id.in_(
                        [two_tenants.membership_a, two_tenants.membership_b]
                    )
                )
            )
        )
        .all()
    )
    by_workspace = {row.workspace_id: set(row.capabilities) for row in rows}
    assert WorkspaceCapability.SIGN in by_workspace[two_tenants.workspace_a]
    assert WorkspaceCapability.SIGN not in by_workspace[two_tenants.workspace_b]


async def test_no_cross_tenant_membership_exists(
    db_connection: AsyncConnection, two_tenants: TenancyFixture
) -> None:
    """W-01 support: fixture users have zero membership in the foreign tenant."""

    foreign = (
        await db_connection.execute(
            select(WorkspaceMembership.id).where(
                WorkspaceMembership.workspace_id == two_tenants.workspace_b,
                WorkspaceMembership.user_id == two_tenants.user_a,
            )
        )
    ).first()
    assert foreign is None


# ---------------------------------------------------------------------------
# HTTP-level isolation gates: activate when app.tenancy routes are delivered.
# ---------------------------------------------------------------------------


class TestHttpIsolationGates:
    """Rows W-01, W-02, W-04 against the live API."""

    @pytest.fixture(autouse=True)
    def _require_tenancy_routes(self):
        pytest.importorskip(
            "app.tenancy.routes",
            reason="Task 3 tenancy routes not delivered yet",
        )

    async def test_cross_workspace_read_returns_uniform_404(self) -> None:
        """W-01/W-02: member of A gets 404 for B's resources; body must be
        indistinguishable from a true-missing 404."""

        import httpx

        from app.main import app

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"Origin": "http://testserver"},
        ) as client:
            csrf = await client.get("/api/auth/csrf")
            headers = {
                "X-CSRF-Token": csrf.json().get("data", {}).get("token")
                or csrf.json().get("token")
            }
            email = f"qa-iso-{uuid4().hex[:10]}@example.test"
            await client.post(
                "/api/auth/register",
                json={"email": email, "password": "correct horse battery staple"},
                headers=headers,
            )
            await client.post(
                "/api/auth/login",
                json={"email": email, "password": "correct horse battery staple"},
                headers=headers,
            )

            foreign_workspace = uuid4()
            foreign_subject = uuid4()
            missing = await client.get(f"/api/workspaces/{uuid4()}")
            foreign = await client.get(f"/api/workspaces/{foreign_workspace}")
            nested = await client.get(
                f"/api/workspaces/{foreign_workspace}/subjects/{foreign_subject}"
            )

            assert missing.status_code == 404
            assert foreign.status_code == 404
            assert nested.status_code == 404
            # anti-oracle: identical envelope for foreign vs truly missing
            assert foreign.json() == missing.json()
            for response in (missing, foreign, nested):
                assert response.status_code != 403
                body = response.text.lower()
                assert "forbidden" not in body
                assert "not a member" not in body
