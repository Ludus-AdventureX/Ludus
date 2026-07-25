"""Seeded world types for the Task 8 evidence owner suite (uniquely named).

Split out of ``conftest.py`` because a plain ``import conftest`` is ambiguous
once several owner suites (simulations / evidence / analyses) are collected in
one pytest run; test modules import this module by its collision-free name.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(slots=True)
class EvidenceWorld:
    """Ids of one fully seeded tenant scope for evidence tests."""

    workspace_id: UUID
    user_id: UUID
    subject_id: UUID
    case_id: UUID
    analysis_run_id: UUID
    source_record_id: UUID
    source_span_id: UUID
