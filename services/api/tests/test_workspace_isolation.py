"""Task 3 QA gate: workspace isolation (acceptance matrix rows W-01..W-04).

The DB-level negative tests run on the frozen baseline already (Task 19A
constraints). The HTTP-level tests skip until ``app.tenancy.routes`` exists
and then run against the QA app assembly with its tenancy probe route.
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
# Capability projection unit tests (activate with app.tenancy.context).
# ---------------------------------------------------------------------------


class TestCapabilityProjection:
    """Row W-03 against the delivered projection logic."""

    @pytest.fixture(autouse=True)
    def _require_context(self):
        pytest.importorskip(
            "app.tenancy.context",
            reason="Task 3 tenancy context not delivered yet",
        )

    def test_owner_projects_full_capability_set(self) -> None:
        from app.tenancy.context import project_capabilities

        projected = project_capabilities(WorkspaceRole.OWNER, [])
        assert projected == frozenset(WorkspaceCapability)

    def test_member_gets_only_stored_grants(self) -> None:
        from app.tenancy.context import project_capabilities

        granted = [WorkspaceCapability.CONTRIBUTE, WorkspaceCapability.REVIEW]
        projected = project_capabilities(WorkspaceRole.MEMBER, granted)
        assert projected == frozenset(granted)
        assert WorkspaceCapability.SIGN not in projected
        assert WorkspaceCapability.MANAGE_CONNECTORS not in projected


# ---------------------------------------------------------------------------
# HTTP-level isolation gates (activate with app.tenancy.routes).
# ---------------------------------------------------------------------------


class TestHttpIsolationGates:
    """Rows W-01, W-02, W-04 against the assembled API."""

    @pytest.fixture(autouse=True)
    def _require_tenancy_routes(self):
        pytest.importorskip(
            "app.tenancy.routes",
            reason="Task 3 tenancy routes not delivered yet",
        )

    async def test_cross_workspace_access_returns_uniform_404(self) -> None:
        """W-01/W-02: a real foreign workspace and a nonexistent one are
        byte-identical uniform 404s; never 403, never an existence oracle."""

        from tests.conftest import qa_client, register_user

        async with qa_client() as attacker, qa_client() as victim:
            _, victim_data = await register_user(victim)
            victim_workspace = victim_data["memberships"][0]["workspaceId"]

            await register_user(attacker)

            foreign = await attacker.get(
                f"/api/workspaces/{victim_workspace}/qa-tenancy-probe"
            )
            nonexistent = await attacker.get(
                f"/api/workspaces/{uuid4()}/qa-tenancy-probe"
            )

            assert foreign.status_code == 404
            assert nonexistent.status_code == 404
            assert foreign.content == nonexistent.content, (
                "foreign vs nonexistent workspace responses must be identical"
            )
            body = foreign.json()
            assert body["error"]["code"] == "WORKSPACE_NOT_FOUND"
            lowered = foreign.text.lower()
            assert "forbidden" not in lowered
            assert "member" not in lowered

    async def test_unauthenticated_workspace_access_is_401(self) -> None:
        """W-01 support: no session yields the uniform session failure."""

        from tests.conftest import qa_client

        async with qa_client() as client:
            response = await client.get(
                f"/api/workspaces/{uuid4()}/qa-tenancy-probe"
            )
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "SESSION_REVOKED_OR_EXPIRED"

    async def test_own_workspace_probe_succeeds(self) -> None:
        """W-04 sanity: the same probe passes for the member's own tenant."""

        from tests.conftest import qa_client, register_user

        async with qa_client() as client:
            _, data = await register_user(client)
            workspace_id = data["memberships"][0]["workspaceId"]
            response = await client.get(
                f"/api/workspaces/{workspace_id}/qa-tenancy-probe"
            )
            assert response.status_code == 200
            assert response.json() == {"reached": True}

    async def test_owner_membership_summary_projects_all_capabilities(self) -> None:
        """W-03: /api/auth/session projects the full owner capability set even
        though stored grants are empty."""

        from tests.conftest import qa_client, register_user

        async with qa_client() as client:
            _, data = await register_user(client)
            membership = data["memberships"][0]
            assert membership["role"] == "owner"
            assert sorted(membership["capabilities"]) == [
                "contribute",
                "manage_connectors",
                "review",
                "sign",
            ]
