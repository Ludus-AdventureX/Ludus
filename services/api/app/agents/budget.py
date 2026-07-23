"""Hard execution budgets for formal analysis runs.

Budgets are loaded from the published method pack (``budgets.<level>``) and are
enforced as *hard* caps: model calls, retrieval tasks, total sources, parallelism,
delegation depth and wall-clock time. Exhaustion raises :class:`BudgetExhausted`;
the run persists partial artifacts and enters ``needs_attention``. Budgets are
never widened by a ``RunResolution`` - scaling up requires a replacement Charter
and a new Run.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field

from .errors import BudgetExhausted

# Budget keys that are *counters* (each charge increments consumption).
_COUNTER_KEYS: frozenset[str] = frozenset(
    {
        "max_model_calls",
        "max_lens_calls",
        "max_total_tool_calls",
        "max_search_calls",
        "max_fetched_documents",
        "max_research_tracks",
        "max_critic_research_requests",
    }
)


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    """Immutable per-run limits parsed from a method-pack ``budgets`` block."""

    limits: Mapping[str, float]

    @classmethod
    def from_manifest(cls, manifest: Mapping[str, object], level: str) -> "BudgetLimits":
        budgets = manifest.get("budgets")
        if not isinstance(budgets, Mapping):
            raise ValueError("method pack manifest has no 'budgets' block")
        level_block = budgets.get(level)
        if not isinstance(level_block, Mapping):
            raise ValueError(f"method pack manifest has no budget for level {level!r}")
        numeric: dict[str, float] = {}
        for key, value in level_block.items():
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                numeric[str(key)] = float(value)
        return cls(limits=numeric)

    def get(self, key: str) -> float | None:
        value = self.limits.get(key)
        return None if value is None else float(value)


@dataclass(slots=True)
class BudgetLedger:
    """Mutable per-run consumption tracker.

    ``charge`` increments a counter and fails closed the moment it would exceed the
    configured limit; ``check_elapsed`` enforces the wall-clock cap.
    """

    limits: BudgetLimits
    consumed: dict[str, float] = field(default_factory=dict)
    _started_monotonic: float = field(default_factory=time.monotonic)

    def charge(self, key: str, amount: float = 1.0) -> None:
        limit = self.limits.get(key)
        current = self.consumed.get(key, 0.0)
        attempted = current + amount
        if limit is not None and attempted > limit:
            raise BudgetExhausted(key, limit, attempted)
        self.consumed[key] = attempted

    def charge_tool_call(self, *, is_search: bool = False, is_fetch: bool = False) -> None:
        """Charge a single tool call against the aggregate and specific counters."""

        self.charge("max_total_tool_calls")
        if is_search:
            self.charge("max_search_calls")
        if is_fetch:
            self.charge("max_fetched_documents")

    def check_elapsed(self) -> None:
        limit = self.limits.get("max_elapsed_seconds")
        if limit is None:
            return
        elapsed = time.monotonic() - self._started_monotonic
        if elapsed > limit:
            raise BudgetExhausted("max_elapsed_seconds", limit, elapsed)

    def snapshot(self) -> dict[str, float]:
        """A copy of consumed counters for the tool trace / event payload."""

        return dict(self.consumed)

    @staticmethod
    def counter_keys() -> frozenset[str]:
        return _COUNTER_KEYS
