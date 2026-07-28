"""R3 battery: mentor reviews (capability boundary) + the portfolio wall.

The mentor preset is MEMBER + [review]: they can write structured feedback and
read everything, but cannot contribute dossier facts or manage invites. The
portfolio is a pure projection - cases with no runs show none.
"""

from __future__ import annotations

from functools import lru_cache
from uuid import uuid4

import httpx

from tests.conftest import QA_ORIGIN, build_qa_app, csrf_headers

GUEST_FLAG = "ENABLE_GUEST_ALPHA"


@lru_cache(maxsize=1)
def _app():
    from app.auth.guest import router as guest_router

    app = build_qa_app()
    app.include_router(guest_router)
    return app


def qa_client() -> httpx.AsyncClient:
    address = f"10.81.{uuid4().bytes[0]}.{uuid4().bytes[1]}"
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(), client=(address, 51234)),
        base_url=QA_ORIGIN,
        headers={"Origin": QA_ORIGIN},
    )


async def _guest(client: httpx.AsyncClient) -> dict:
    headers = await csrf_headers(client)
    response = await client.post("/api/auth/guest", headers=headers)
    assert response.status_code in (200, 201), response.text
    return response.json()["data"]


async def _join_as_mentor(owner, invitee, ws: str) -> None:
    headers = await csrf_headers(owner)
    created = await owner.post(
        f"/api/workspaces/{ws}/invites",
        json={"capabilities": ["review"]},  # the mentor preset
        headers=headers,
    )
    assert created.status_code == 201, created.text
    token = created.json()["data"]["token"]
    await _guest(invitee)
    headers = await csrf_headers(invitee)
    redeemed = await invitee.post(
        "/api/auth/invites/redeem", json={"token": token}, headers=headers
    )
    assert redeemed.status_code == 200, redeemed.text


async def test_mentor_writes_review_student_reads_it(monkeypatch) -> None:
    monkeypatch.setenv(GUEST_FLAG, "true")
    async with qa_client() as student, qa_client() as mentor:
        data = await _guest(student)
        ws, case_id = data["workspaceId"], data["decisionCaseId"]
        await _join_as_mentor(student, mentor, ws)

        headers = await csrf_headers(mentor)
        created = await mentor.post(
            f"/api/workspaces/{ws}/cases/{case_id}/mentor-reviews",
            json={"qualityScore": 4, "blindSpots": "未考虑供应商集中度风险",
                  "nextStep": "先做一轮供应商访谈再签"},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        assert created.json()["data"]["qualityScore"] == 4

        listing = await student.get(f"/api/workspaces/{ws}/cases/{case_id}/mentor-reviews")
        assert listing.status_code == 200
        items = listing.json()["data"]["items"]
        assert len(items) == 1
        assert "供应商" in items[0]["blindSpots"]


async def test_mentor_cannot_contribute_and_score_is_bounded(monkeypatch) -> None:
    monkeypatch.setenv(GUEST_FLAG, "true")
    async with qa_client() as student, qa_client() as mentor:
        data = await _guest(student)
        ws, case_id = data["workspaceId"], data["decisionCaseId"]
        await _join_as_mentor(student, mentor, ws)

        headers = await csrf_headers(mentor)
        # review-only mentor cannot create cases (CONTRIBUTE surface).
        blocked = await mentor.post(
            f"/api/workspaces/{ws}/cases",
            json={"decisionQuestion": "mentor should not create cases here"},
            headers=headers,
        )
        assert blocked.status_code == 403, blocked.text
        # score bounds are schema-enforced.
        bad = await mentor.post(
            f"/api/workspaces/{ws}/cases/{case_id}/mentor-reviews",
            json={"qualityScore": 9, "blindSpots": "x", "nextStep": "y"},
            headers=headers,
        )
        assert bad.status_code == 422


async def test_portfolio_projects_cases_honestly(monkeypatch) -> None:
    monkeypatch.setenv(GUEST_FLAG, "true")
    async with qa_client() as owner:
        data = await _guest(owner)
        ws = data["workspaceId"]
        headers = await csrf_headers(owner)
        await owner.post(
            f"/api/workspaces/{ws}/cases",
            json={"decisionQuestion": "portfolio wall probe case"},
            headers=headers,
        )
        wall = await owner.get(f"/api/workspaces/{ws}/portfolio")
        assert wall.status_code == 200, wall.text
        items = wall.json()["data"]["items"]
        assert len(items) >= 2  # demo case + probe case
        probe = [i for i in items if i["latestRunStatus"] is None]
        assert probe, "a case with no runs must show latestRunStatus=None, not a fabrication"
        for item in items:
            assert item["hasSignedDecision"] in (True, False)
            assert item["reviewDue"] in (True, False)
