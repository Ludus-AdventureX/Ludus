# One-shot generator for tests/a2a/fixtures/*.json — reuses the lane tests'
# gate-passing payload builders so the A2A fixtures can never drift from the
# behavior contracts. Run from services/api: .venv/Scripts/python.exe tests/a2a/_gen_fixtures.py
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = API_ROOT.parents[1]
OUT = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(API_ROOT))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    lanes = API_ROOT / "tests" / "lens_lanes"
    porter = _load("gen_porter", lanes / "test_porter_five_forces.py")
    scenario = _load("gen_scenario", lanes / "test_scenario_lens.py")
    meadows = _load("gen_meadows", lanes / "test_meadows_lens.py")

    golden = REPO_ROOT / "fixtures" / "spherical-robot" / "expected" / "strategic-lenses"
    payloads = {
        "porter_five_forces": porter.make_payload(),
        "counterparty_response_matrix": json.loads(
            (golden / "counterparty_response_matrix.json").read_text("utf-8")
        ),
        "pre_mortem": json.loads((golden / "pre_mortem.json").read_text("utf-8")),
        "scenario_planning": scenario._payload(),
        "meadows_leverage_points": meadows.spherical_robot_meadows_payload(),
    }

    # Sanity: every payload must pass its own behavior gate before we save it.
    from app.agents.lenses import StrategicLensStageOutput
    from app.strategic_lenses.registry import build_lens_registry
    from app.types import StrategicLensType

    registry = build_lens_registry()
    for key, payload in payloads.items():
        stage = StrategicLensStageOutput.from_payload(payload)
        report = registry.get(StrategicLensType(key)).validate_behavior(stage)
        assert report.ok, f"{key} fixture fails its gate: {report.findings}"

    OUT.mkdir(parents=True, exist_ok=True)
    for key, payload in payloads.items():
        (OUT / f"{key}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print("wrote", key)


if __name__ == "__main__":
    main()
