from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, create_model


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPOSITORY_ROOT / "services" / "api"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "packages" / "contracts" / "openapi.json"

sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(API_ROOT))

from app.analyses.schemas import (  # noqa: E402
    DeepAnalysisRequest,
    DeepAnalysisResult,
    MethodVersionRef,
    ValidatorFinding,
    ValidatorResult,
)
from app.decisions.schemas import (  # noqa: E402
    AbstainSystemRecommendation,
    ActionItem,
    LeadingIndicator,
    OptionSystemRecommendation,
    Recommendation,
    RecommendationQuality,
    SignoffPayload,
    SignoffRequest,
    SignoffSignCommand,
    SystemRecommendation,
    Threshold,
)
from app.evidence.schemas import (  # noqa: E402
    PreRunSourceRecord,
    PreRunSourceSpan,
    RunFrozenSourceRecord,
    RunFrozenSourceSpan,
    SourceRecord,
    SourceRecordBase,
    SourceSpan,
    SourceSpanBase,
    SourceSpanLocator,
)
from app.simulations.schemas import (  # noqa: E402
    SimulationOptionScore,
    SimulationRun,
    SimulationTopDriver,
)
from app.tenancy.schemas import User, UserSession, WorkspaceMembership  # noqa: E402
from scripts.export_openapi import build_openapi_document, canonical_json  # noqa: E402


CANONICAL_MODELS: tuple[type[BaseModel], ...] = (
    User,
    WorkspaceMembership,
    UserSession,
    SourceRecordBase,
    PreRunSourceRecord,
    RunFrozenSourceRecord,
    SourceRecord,
    SourceSpanLocator,
    SourceSpanBase,
    PreRunSourceSpan,
    RunFrozenSourceSpan,
    SourceSpan,
    MethodVersionRef,
    ValidatorFinding,
    ValidatorResult,
    DeepAnalysisRequest,
    DeepAnalysisResult,
    OptionSystemRecommendation,
    AbstainSystemRecommendation,
    SystemRecommendation,
    Threshold,
    ActionItem,
    LeadingIndicator,
    RecommendationQuality,
    Recommendation,
    SignoffPayload,
    SignoffRequest,
    SignoffSignCommand,
    SimulationOptionScore,
    SimulationTopDriver,
    SimulationRun,
)


def build_catalog_schemas() -> dict[str, Any]:
    fields = {
        f"contract_{index:02d}": (model, ...)
        for index, model in enumerate(CANONICAL_MODELS, start=1)
    }
    catalog_model = create_model("CanonicalContractCatalog", **fields)
    catalog_app = FastAPI(title="Ludus Canonical Contract Catalog")

    @catalog_app.get("/__canonical_contract_catalog", response_model=catalog_model)
    async def contract_catalog() -> Any:  # pragma: no cover - schema-only route
        raise RuntimeError("schema-only route")

    document = catalog_app.openapi()
    schemas = dict(document.get("components", {}).get("schemas", {}))
    schemas.pop("CanonicalContractCatalog", None)
    return schemas


def build_canonical_openapi_document() -> dict[str, Any]:
    document = build_openapi_document()
    target = document.setdefault("components", {}).setdefault("schemas", {})
    for name, schema in build_catalog_schemas().items():
        existing = target.get(name)
        if existing is not None and existing != schema:
            raise RuntimeError(f"OpenAPI component collision for canonical schema '{name}'")
        target[name] = schema
    document["x-decision-lab-contract-models"] = sorted(model.__name__ for model in CANONICAL_MODELS)
    return document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export FastAPI OpenAPI plus the route-independent canonical schema catalog."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        canonical_json(build_canonical_openapi_document()),
        encoding="utf-8",
        newline="\n",
    )
    print(f"CANONICAL_OPENAPI_EXPORTED {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"CANONICAL_OPENAPI_EXPORT_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
