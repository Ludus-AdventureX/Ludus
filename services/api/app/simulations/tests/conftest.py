"""Shared pytest wiring for the owner simulation test modules.

The tests directory is deliberately not a package; the r1 owner module defines
the transactional ``session`` fixture, and re-exporting it here makes it visible
to every owner test module in this directory without duplicating the fixture.
"""

import os
from collections.abc import Iterator

import pytest

from test_simulation_repository_service import session  # noqa: F401


@pytest.fixture(autouse=True, scope="session")
def _qa_auth_jwt_secret() -> Iterator[None]:
    """AUTH_JWT_SECRET for the suite (AuthSettings fails closed without it)."""
    previous = os.environ.get("AUTH_JWT_SECRET")
    os.environ["AUTH_JWT_SECRET"] = "qa-test-jwt-secret-not-for-production"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("AUTH_JWT_SECRET", None)
        else:
            os.environ["AUTH_JWT_SECRET"] = previous
