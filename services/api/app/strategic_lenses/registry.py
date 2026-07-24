"""Explicit five-lens registry assembly.

The only place where concrete lens implementations meet the shared
``LensRegistry``. Registration is explicit and fail-closed: building the
default registry requires the exact canonical five-lens set, so a missing or
duplicated lens breaks assembly instead of surfacing later in a formal run.

Persistence of ``StrategicLensArtifact`` is intentionally NOT wired here:
CCR-20260724-Ways-01 (canonical artifact schema + migration) is pending with
contract_lead, and this module must not invent schema, migrations or enums.
"""

from __future__ import annotations

from app.agents.lenses import LensRegistry

from .adapters import MeadowsLensAdapter, PreMortemLensAdapter
from .lenses.counterparty_response_matrix import CounterpartyResponseMatrixLens
from .lenses.porter_five_forces import PorterFiveForcesLens
from .lenses.scenario_planning import ScenarioPlanningLens


def build_lens_registry() -> LensRegistry:
    """Assemble the canonical five-lens registry and enforce the full set."""

    registry = LensRegistry()
    registry.register(PorterFiveForcesLens())
    registry.register(CounterpartyResponseMatrixLens())
    registry.register(PreMortemLensAdapter())
    registry.register(ScenarioPlanningLens())
    registry.register(MeadowsLensAdapter())
    registry.require_full_set()
    return registry
