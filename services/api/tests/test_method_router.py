from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.methods.installer import MethodPackInstaller
from app.methods.loader import MethodPackLoader
from app.methods.router import MethodRouteUnavailableError, MethodRouter

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = REPOSITORY_ROOT / "ways" / "hardtech-market-direction" / "1.1.0"


def complete_snapshot(level: str = "full") -> dict[str, object]:
    return {
        "analysis_level": level,
        "workspace_id": "workspace-1",
        "case_version": 3,
        "case_snapshot_hash": "sha256:case",
        "dossier_snapshot_hash": "sha256:dossier",
        "subject": {
            "id": "subject-1",
            "class": "robotics",
            "stage": "seed",
            "owner": "founder",
        },
        "decision": {
            "type": "market_direction",
            "question": "优先进入救援市场还是家庭服务市场？",
            "deadline": "2026-08-01",
        },
        "goals": ["在现金窗口内验证可交付市场"],
        "constraints": ["现金窗口 9 个月", "研发团队 6 人"],
        "options": [
            {"id": "rescue", "label": "救援市场"},
            {"id": "home", "label": "家庭服务市场"},
        ],
        "switching_cost": {"material": True},
        "allowed_materials": ["public_sources"],
        "prohibited_materials": ["secrets"],
        "allowed_connectors": ["search_web", "fetch_url"],
        "known_facts": ["已有原型"],
        "assumptions": ["采购方愿意参与试点"],
        "unknown_items": ["认证周期"],
        "confirmation": {
            "route_inputs_confirmed": True,
            "allowed_materials_confirmed": True,
            "unknown_items_confirmed": True,
        },
    }


def installed_router(tmp_path: Path) -> MethodRouter:
    catalog = tmp_path / "method-packs"
    MethodPackInstaller().install(SOURCE_ROOT, catalog)
    return MethodRouter(MethodPackLoader(catalog))


def test_spherical_robot_routes_exact_to_published_method(tmp_path: Path) -> None:
    result = installed_router(tmp_path).route(complete_snapshot("full"))

    assert result.route == "exact"
    assert result.method_id == "hardtech-market-direction"
    assert result.method_version == "1.1.0"
    assert result.formal_analysis_allowed is True
    assert result.missing_inputs == []
    assert result.content_hash


def test_missing_confirmed_input_routes_partial(tmp_path: Path) -> None:
    request = complete_snapshot("focused")
    decision = dict(request["decision"])  # type: ignore[arg-type]
    decision.pop("question")
    request["decision"] = decision

    result = installed_router(tmp_path).route(request)

    assert result.route == "partial"
    assert result.method_id == "hardtech-market-direction"
    assert result.formal_analysis_allowed is False
    assert "decision.question" in result.missing_inputs


def test_non_matching_marketing_problem_is_unsupported(tmp_path: Path) -> None:
    request = complete_snapshot("focused")
    decision = dict(request["decision"])  # type: ignore[arg-type]
    decision["type"] = "marketing_optimization"
    request["decision"] = decision

    result = installed_router(tmp_path).route(request)

    assert result.route == "unsupported"
    assert result.method_id is None
    assert result.method_version is None
    assert result.formal_analysis_allowed is False


def test_quick_route_does_not_select_formal_method(tmp_path: Path) -> None:
    result = installed_router(tmp_path).route(complete_snapshot("quick"))

    assert result.route == "unsupported"
    assert result.method_id is None
    assert result.formal_analysis_allowed is False


def test_router_never_returns_method_missing_from_catalog(tmp_path: Path) -> None:
    router = MethodRouter(MethodPackLoader(tmp_path / "empty-catalog"))

    with pytest.raises(MethodRouteUnavailableError):
        router.route(complete_snapshot("full"))


def test_focused_route_does_not_require_lens_artifacts(tmp_path: Path) -> None:
    result = installed_router(tmp_path).route(complete_snapshot("focused"))

    assert result.route == "exact"
    assert result.formal_analysis_allowed is True
    assert result.required_lens_artifacts == []

def test_non_material_switching_cost_is_unsupported(tmp_path: Path) -> None:
    request = complete_snapshot("focused")
    request["switching_cost"] = {"material": False}

    result = installed_router(tmp_path).route(request)

    assert result.route == "unsupported"
    assert result.method_id is None
    assert "switching_cost_is_not_material" in result.reasons


def test_missing_route_confirmation_is_partial(tmp_path: Path) -> None:
    request = complete_snapshot("focused")
    request.pop("confirmation")

    result = installed_router(tmp_path).route(request)

    assert result.route == "partial"
    assert result.formal_analysis_allowed is False
    assert "confirmation.route_inputs_confirmed" in result.missing_inputs


def test_canonical_requested_level_alias_routes_exact(tmp_path: Path) -> None:
    request = complete_snapshot()
    request.pop("analysis_level")
    request["requestedLevel"] = "focused"

    result = installed_router(tmp_path).route(request)

    assert result.route == "exact"
    assert result.formal_analysis_allowed is True


@pytest.mark.parametrize(
    "fixture_name",
    [
        "spherical-robot.json",
        "bci-platform-seed.json",
        "bci-platform-angel.json",
        "partial-missing-decision-contract.json",
        "unsupported-marketing-optimization.json",
    ],
)
def test_checked_in_route_eval_contracts_are_executable(
    tmp_path: Path,
    fixture_name: str,
) -> None:
    fixture = json.loads((SOURCE_ROOT / "evals" / fixture_name).read_text(encoding="utf-8"))

    result = installed_router(tmp_path).route(fixture["input"])
    expected = fixture["expectedRoute"]

    assert result.route == expected["matchStatus"]
    assert result.formal_analysis_allowed is expected["formalAnalysisAllowed"]
    assert result.method_id == expected["recommendedMethodId"]
    assert result.method_version == expected["recommendedMethodVersion"]


def test_prohibited_or_unconfirmed_materials_route_partial(tmp_path: Path) -> None:
    request = complete_snapshot("focused")
    request["requires_prohibited_materials"] = True

    result = installed_router(tmp_path).route(request)

    assert result.route == "partial"
    assert result.formal_analysis_allowed is False
    assert result.method_id == "hardtech-market-direction"
    assert "materials.authorization" in result.missing_inputs
