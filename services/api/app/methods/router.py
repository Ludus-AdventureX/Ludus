from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .loader import MethodPackLoader
from .models import CynefinGateDecision, LoadedMethodPack, MethodRouteResult


class MethodRouteUnavailableError(RuntimeError):
    """Raised when a matching method is not present in the published catalog."""


class MethodRouter:
    """Route confirmed case inputs against a published method manifest."""

    def __init__(self, loader: MethodPackLoader | str | Path) -> None:
        self.loader = loader if isinstance(loader, MethodPackLoader) else MethodPackLoader(loader)

    def route(self, request: Mapping[str, Any] | Any) -> MethodRouteResult:
        data = self._as_mapping(request)
        level = self._value(
            data,
            "analysis_level",
            "analysisLevel",
            "requested_level",
            "requestedLevel",
            "requested_analysis_level",
            "requestedAnalysisLevel",
            "level",
        )
        if level == "quick":
            return MethodRouteResult(
                route="unsupported",
                reasons=["quick_analysis_stays_in_conversation_and_does_not_invoke_formal_method_router"],
            )
        if level not in {"focused", "full"}:
            return MethodRouteResult(
                route="unsupported",
                reasons=["analysis_level_must_be_focused_or_full"],
            )

        pack = self._load_published_method()
        manifest = pack.manifest
        subject_class = self._nested_value(data, "subject", "class", "subjectClass")
        decision_type = self._nested_value(data, "decision", "type", "decisionType")
        unsupported_reason = self._unsupported_reason(
            subject_class,
            decision_type,
            data,
            manifest,
        )
        if unsupported_reason is not None:
            return MethodRouteResult(route="unsupported", reasons=[unsupported_reason])

        missing = self._missing_required_inputs(data, level, manifest)
        applicability_missing, applicability_reason = self._applicability_gate(data, manifest)
        if applicability_reason is not None:
            return MethodRouteResult(route="unsupported", reasons=[applicability_reason])
        missing.extend(applicability_missing)
        options = self._options(data)
        if options is None:
            missing.append("options")
        elif len(options) < 2:
            return MethodRouteResult(
                route="partial",
                method_id=pack.method_id,
                method_version=pack.version,
                content_hash=pack.content_hash,
                reasons=["fewer_than_two_comparable_options"],
                missing_inputs=["options.minimum_items=2"],
                required_lens_artifacts=self._required_lenses(manifest, level),
            )

        if missing:
            return MethodRouteResult(
                route="partial",
                method_id=pack.method_id,
                method_version=pack.version,
                content_hash=pack.content_hash,
                reasons=["confirmed_inputs_missing"],
                missing_inputs=sorted(set(missing)),
                required_lens_artifacts=self._required_lenses(manifest, level),
            )

        return MethodRouteResult(
            route="exact",
            method_id=pack.method_id,
            method_version=pack.version,
            content_hash=pack.content_hash,
            formal_analysis_allowed=True,
            reasons=["published_method_applicability_and_required_inputs_match"],
            required_lens_artifacts=self._required_lenses(manifest, level),
        )

    def select(self, request: Mapping[str, Any] | Any) -> MethodRouteResult:
        return self.route(request)

    def route_method(self, request: Mapping[str, Any] | Any) -> MethodRouteResult:
        return self.route(request)

    def __call__(self, request: Mapping[str, Any] | Any) -> MethodRouteResult:
        return self.route(request)

    def _load_published_method(self) -> LoadedMethodPack:
        try:
            return self.loader.load_from_catalog("hardtech-market-direction", "1.1.0")
        except Exception as exc:
            raise MethodRouteUnavailableError(
                "hardtech-market-direction@1.1.0 is not available as a verified published method"
            ) from exc

    @staticmethod
    def _as_mapping(request: Mapping[str, Any] | Any) -> Mapping[str, Any]:
        if isinstance(request, Mapping):
            return request
        if hasattr(request, "model_dump"):
            value = request.model_dump()
            if isinstance(value, Mapping):
                return value
        if hasattr(request, "dict"):
            value = request.dict()
            if isinstance(value, Mapping):
                return value
        raise TypeError("method route request must be a mapping or model with model_dump()")

    @staticmethod
    def _value(data: Mapping[str, Any], *names: str) -> Any:
        for name in names:
            if name in data:
                return data[name]
        return None

    @classmethod
    def _nested_value(cls, data: Mapping[str, Any], parent: str, *names: str) -> Any:
        nested = data.get(parent)
        if isinstance(nested, Mapping):
            value = cls._value(nested, *names)
            if value is not None:
                return value
        return cls._value(data, *names)

    @classmethod
    def _options(cls, data: Mapping[str, Any]) -> list[Any] | None:
        value = cls._value(data, "options", "comparable_options")
        if value is None:
            decision = data.get("decision")
            if isinstance(decision, Mapping):
                value = cls._value(decision, "options", "comparable_options")
        return value if isinstance(value, list) else None

    @classmethod
    def _field_present(cls, data: Mapping[str, Any], path: str) -> bool:
        value = cls._field_value(data, path)
        if value is None:
            aliases = cls._aliases(path)
            for container_name in ("evidence_policy", "evidencePolicy", "reproducibility"):
                container = data.get(container_name)
                if isinstance(container, Mapping):
                    value = cls._value(container, *aliases)
                    if value is not None:
                        break
        if value is None:
            return False
        if path in {
            "subject.id",
            "subject.class",
            "subject.stage",
            "subject.owner",
            "decision.question",
            "decision.deadline",
            "goals",
            "constraints",
            "allowed_materials",
            "allowed_connectors",
            "known_facts",
            "unknown_items",
            "workspace_id",
            "case_version",
            "case_snapshot_hash",
            "dossier_snapshot_hash",
        }:
            if isinstance(value, str):
                return bool(value.strip())
            if isinstance(value, (list, tuple, set, Mapping)):
                return bool(value)
        return True

    @classmethod
    def _missing_required_inputs(
        cls,
        data: Mapping[str, Any],
        level: str,
        manifest: Mapping[str, Any],
    ) -> list[str]:
        missing: list[str] = []
        levels = manifest.get("analysis_levels")
        level_data = levels.get(level) if isinstance(levels, Mapping) else None
        if not isinstance(level_data, Mapping):
            return [f"analysis_levels.{level}"]
        for item in manifest.get("required_inputs", []):
            if not isinstance(item, Mapping):
                continue
            required_for = item.get("required_for", [])
            if level not in required_for:
                continue
            for field in item.get("fields", []):
                if field == "options":
                    continue
                if not cls._field_present(data, field):
                    missing.append(str(field))
        if not cls._field_present(data, "constraints"):
            missing.append("cash.runway")
        return missing

    @classmethod
    def _field_value(cls, data: Mapping[str, Any], path: str) -> Any:
        parent, separator, leaf = path.partition(".")
        if separator:
            for parent_name in (parent, cls._camel(parent)):
                nested = data.get(parent_name)
                if isinstance(nested, Mapping):
                    value = cls._value(nested, leaf, cls._camel(leaf))
                    if value is not None:
                        return value
        return cls._value(data, *cls._aliases(path))

    @classmethod
    def _aliases(cls, path: str) -> tuple[str, ...]:
        aliases = [path, cls._camel(path)]
        aliases.extend(
            {
                "subject.id": ["decisionSubjectId"],
                "decision.question": ["decisionQuestion"],
                "decision.deadline": ["decisionDeadline", "deadline"],
                "unknown_items": ["unknowns"],
            }.get(path, [])
        )
        return tuple(dict.fromkeys(aliases))

    @classmethod
    def _applicability_gate(
        cls,
        data: Mapping[str, Any],
        manifest: Mapping[str, Any],
    ) -> tuple[list[str], str | None]:
        missing: list[str] = []
        switching_rule = cls._applicability_rule(manifest, "switching_cost_material")
        switching_cost = cls._field_value(data, str(switching_rule["field"]))
        if switching_cost is None:
            missing.append("switching_cost.material")
        elif switching_cost != switching_rule["value"]:
            return [], "switching_cost_is_not_material"

        confirmation_rule = cls._applicability_rule(manifest, "decision_contract_confirmed")
        confirmed = cls._field_value(data, str(confirmation_rule["field"]))
        if confirmed != confirmation_rule["value"]:
            missing.append("confirmation.route_inputs_confirmed")

        for field in (
            "confirmation.allowed_materials_confirmed",
            "confirmation.unknown_items_confirmed",
        ):
            if cls._field_value(data, field) is not True:
                missing.append(field)

        if cls._value(data, "requires_prohibited_materials", "requiresProhibitedMaterials") is True:
            missing.append("materials.authorization")
        return missing, None

    @staticmethod
    def _applicability_rule(
        manifest: Mapping[str, Any],
        rule_id: str,
    ) -> Mapping[str, Any]:
        applicability = manifest.get("applicability")
        rules = applicability.get("all") if isinstance(applicability, Mapping) else None
        if isinstance(rules, list):
            for rule in rules:
                if isinstance(rule, Mapping) and rule.get("rule_id") == rule_id:
                    return rule
        raise MethodRouteUnavailableError(f"published method applicability rule is missing: {rule_id}")

    @staticmethod
    def _required_lenses(manifest: Mapping[str, Any], level: str) -> list[str]:
        levels = manifest.get("analysis_levels")
        if not isinstance(levels, Mapping):
            return []
        value = levels.get(level)
        if not isinstance(value, Mapping):
            return []
        lenses = value.get("required_lens_artifacts", [])
        return list(lenses) if isinstance(lenses, list) else []

    @classmethod
    def _unsupported_reason(
        cls,
        subject_class: Any,
        decision_type: Any,
        data: Mapping[str, Any],
        manifest: Mapping[str, Any],
    ) -> str | None:
        subject_rule = cls._applicability_rule(manifest, "subject_is_hardtech")
        decision_rule = cls._applicability_rule(manifest, "decision_is_market_direction")
        supported_subject_classes = set(subject_rule["value"])
        supported_decision_types = set(decision_rule["value"])
        if subject_class is not None and subject_class not in supported_subject_classes:
            return "subject_class_is_outside_hardtech_method_scope"
        if decision_type is not None and decision_type not in supported_decision_types:
            if str(decision_type).lower() in {
                "marketing_optimization",
                "campaign_optimization",
                "pure_marketing_optimization",
                "investment_selection",
                "portfolio_selection",
                "engineering_certification",
                "compliance_signoff",
            }:
                return "decision_type_is_explicitly_excluded_by_method"
            return "decision_type_is_outside_hardtech_method_scope"
        return None

    @staticmethod
    def _camel(value: str) -> str:
        parts = value.split("_")
        return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


class CynefinOverrideError(ValueError):
    """Raised when a formal gate override is incomplete or not auditable."""


_CYNEFIN_DEFAULTS: dict[str, tuple[str, str, bool, bool]] = {
    "clear": ("quick", "proceed_quick", False, True),
    "complicated": ("focused", "proceed_focused", True, False),
    "complex": ("full", "proceed_full", True, False),
    "chaotic": ("quick", "stabilize_first", False, True),
    "disorder": ("quick", "clarify_scope", False, True),
}


def evaluate_cynefin_gate(
    domain: str,
    *,
    requested_level: str | None = None,
    override_user_id: str | None = None,
    override_reason: str | None = None,
) -> CynefinGateDecision:
    """Return the manifest-locked default route and apply only an auditable human override."""

    if domain not in _CYNEFIN_DEFAULTS:
        raise ValueError(f"unknown Cynefin domain: {domain}")
    if requested_level is not None and requested_level not in {"quick", "focused", "full"}:
        raise CynefinOverrideError(f"unsupported requested analysis level: {requested_level}")
    if bool(override_user_id) != bool(override_reason):
        raise CynefinOverrideError("Cynefin override requires both a human user id and a reason")
    recommended_level, default_action, formal_allowed, override_required = _CYNEFIN_DEFAULTS[
        domain
    ]
    has_override = bool(override_user_id and override_reason)
    if requested_level in {"focused", "full"} and not formal_allowed and not has_override:
        raise CynefinOverrideError(
            "this Cynefin domain cannot start a formal run without a human override"
        )
    if has_override:
        if requested_level not in {"focused", "full"}:
            raise CynefinOverrideError(
                "Cynefin formal override must explicitly select focused or full analysis"
            )
        recommended_level = requested_level
        default_action = f"proceed_{requested_level}"
        formal_allowed = True
    elif requested_level in {"focused", "full"} and formal_allowed:
        recommended_level = requested_level
        default_action = f"proceed_{requested_level}"

    safe_to_fail_probes = ["define_bounded_safe_to_fail_probe"] if domain == "complex" else []
    review_triggers = (
        ["probe_threshold_reached", "material_assumption_invalidated"]
        if domain == "complex"
        else []
    )
    return CynefinGateDecision(
        domain=domain,
        recommended_analysis_level=recommended_level,
        default_action=default_action,
        formal_analysis_allowed=formal_allowed,
        override_required=override_required,
        rationale_codes=[f"cynefin_domain_{domain}"],
        safe_to_fail_probes=safe_to_fail_probes,
        review_triggers=review_triggers,
        overridden_by_user_id=override_user_id if has_override else None,
        override_reason=override_reason if has_override else None,
    )
