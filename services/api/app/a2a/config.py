"""A2A prototype settings (env prefix ``A2A_`` + ``PANDAAI_``).

Follows the guest-alpha precedent: plain ``os.getenv`` reads, no new settings
framework, and the master switch defaults to OFF so the canonical deployment
is unchanged unless the operator opts in explicitly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

A2A_ENABLED_FLAG = "A2A_ENABLED"

# Track rule: total task time must stay below 20 minutes; keep headroom for
# transport + report assembly by defaulting the pipeline budget to 15 minutes.
_DEFAULT_TASK_BUDGET_SECONDS = 900.0
_DEFAULT_LENS_MODEL_CALLS = 24.0

# services/api/app/a2a/config.py -> repo root (decision-lab) is 4 parents up:
# a2a -> app -> services/api -> services -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[4]


def a2a_enabled() -> bool:
    """Master gate; mirrors ``guest_alpha_enabled`` truthy parsing."""

    return os.getenv(A2A_ENABLED_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass(frozen=True, slots=True)
class A2ASettings:
    """Frozen snapshot of every knob the A2A surface reads."""

    public_url: str
    agent_name: str
    agent_version: str
    task_budget_seconds: float
    max_model_calls: float
    method_pack_root: Path
    panda_username: str
    panda_password: str
    panda_base_url: str
    panda_api_key: str
    panda_timeout_seconds: float


def get_a2a_settings() -> A2ASettings:
    """Read settings from the environment on every call (test-friendly)."""

    return A2ASettings(
        public_url=os.getenv("A2A_PUBLIC_URL", "http://localhost:8000").rstrip("/"),
        agent_name=os.getenv("A2A_AGENT_NAME", "Ludus Five-Lens Research Agent"),
        agent_version=os.getenv("A2A_AGENT_VERSION", "1.0.0"),
        task_budget_seconds=_float_env(
            "A2A_TASK_BUDGET_SECONDS", _DEFAULT_TASK_BUDGET_SECONDS
        ),
        max_model_calls=_float_env("A2A_MAX_MODEL_CALLS", _DEFAULT_LENS_MODEL_CALLS),
        method_pack_root=Path(
            os.getenv("A2A_METHOD_PACK_ROOT", str(_REPO_ROOT / "method-packs"))
        ),
        panda_username=os.getenv("PANDAAI_USERNAME", "").strip(),
        panda_password=os.getenv("PANDAAI_PASSWORD", ""),
        panda_base_url=os.getenv("PANDAAI_DATA_BASE_URL", "").rstrip("/"),
        panda_api_key=os.getenv("PANDAAI_DATA_API_KEY", ""),
        panda_timeout_seconds=_float_env("PANDAAI_DATA_TIMEOUT_SECONDS", 30.0),
    )
