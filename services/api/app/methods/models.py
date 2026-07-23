from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class MethodPackDescriptor:
    """Stable identity and publication metadata for an installed method pack."""

    method_id: str
    version: str
    status: str
    content_hash: str
    root: Path
    manifest: Mapping[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def id(self) -> str:
        return self.method_id

    @property
    def method_version(self) -> str:
        return self.version

    @property
    def path(self) -> Path:
        return self.root

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.method_id,
            "version": self.version,
            "status": self.status,
            "content_hash": self.content_hash,
            "path": str(self.root),
        }


@dataclass(frozen=True, slots=True)
class LoadedMethodPack(MethodPackDescriptor):
    """A hash-verified runtime pack available to workers and the router."""

    files: tuple[str, ...] = ()

    def read_text(self, relative_path: str) -> str:
        candidate = self.root / relative_path
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self.root.resolve()):
            raise ValueError(f"method-pack path escapes root: {relative_path}")
        return resolved.read_text(encoding="utf-8")

    def schema(self, schema_name: str) -> dict[str, Any]:
        import json

        path = self.root / "schemas" / schema_name
        return json.loads(self.read_text(path.relative_to(self.root).as_posix()))


@dataclass(frozen=True, slots=True)
class ValidatedMethodSource:
    """Source-package validation receipt used by the installer."""

    root: Path
    method_id: str
    version: str
    manifest: dict[str, Any]
    files: tuple[Path, ...]
    schema_ids: tuple[str, ...]
    prompt_paths: tuple[Path, ...]
    eval_paths: tuple[Path, ...]
    skill_disposition_counts: dict[str, int]


@dataclass(slots=True)
class MethodRouteResult:
    """A safe route decision; formal analysis is allowed only for ``exact``."""

    route: str
    method_id: str | None = None
    method_version: str | None = None
    content_hash: str | None = None
    formal_analysis_allowed: bool = False
    reasons: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    required_lens_artifacts: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return self.route

    @property
    def is_formal(self) -> bool:
        return self.formal_analysis_allowed

    @property
    def method_ref(self) -> str | None:
        if self.method_id is None or self.method_version is None:
            return None
        return f"{self.method_id}@{self.method_version}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "methodId": self.method_id,
            "methodVersion": self.method_version,
            "contentHash": self.content_hash,
            "formalAnalysisAllowed": self.formal_analysis_allowed,
            "reasons": list(self.reasons),
            "missingInputs": list(self.missing_inputs),
            "requiredLensArtifacts": list(self.required_lens_artifacts),
        }
@dataclass(slots=True)
class CynefinGateDecision:
    """Deterministic pre-run classification result before a formal method run."""

    domain: str
    recommended_analysis_level: str
    default_action: str
    formal_analysis_allowed: bool
    override_required: bool
    rationale_codes: list[str] = field(default_factory=list)
    safe_to_fail_probes: list[str] = field(default_factory=list)
    review_triggers: list[str] = field(default_factory=list)
    overridden_by_user_id: str | None = None
    override_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "recommendedAnalysisLevel": self.recommended_analysis_level,
            "defaultAction": self.default_action,
            "formalAnalysisAllowed": self.formal_analysis_allowed,
            "overrideRequired": self.override_required,
            "rationaleCodes": list(self.rationale_codes),
            "safeToFailProbes": list(self.safe_to_fail_probes),
            "reviewTriggers": list(self.review_triggers),
            "overrideUserId": self.overridden_by_user_id,
            "overrideReason": self.override_reason,
        }
