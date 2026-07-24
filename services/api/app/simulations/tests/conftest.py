"""Shared pytest wiring for the owner simulation test modules.

The tests directory is deliberately not a package; the r1 owner module defines
the transactional ``session`` fixture, and re-exporting it here makes it visible
to every owner test module in this directory without duplicating the fixture.
"""

from test_simulation_repository_service import session  # noqa: F401
