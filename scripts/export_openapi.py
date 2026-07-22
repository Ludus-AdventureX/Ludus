from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPOSITORY_ROOT / "services" / "api"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "packages" / "contracts" / "openapi.json"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def build_openapi_document() -> dict[str, Any]:
    sys.path.insert(0, str(API_ROOT))
    try:
        from app.main import app
    except ModuleNotFoundError as exc:
        missing = exc.name or "project dependency"
        raise RuntimeError(
            f"Cannot import the FastAPI application because '{missing}' is unavailable. "
            "Install the approved services/api environment before generating contracts."
        ) from exc

    document = app.openapi()
    if not isinstance(document, dict):
        raise RuntimeError("FastAPI returned an invalid OpenAPI document.")
    return document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export the canonical FastAPI OpenAPI document with stable ordering."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output path; defaults to packages/contracts/openapi.json.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare generated content with --output without modifying it.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    rendered = canonical_json(build_openapi_document())

    if args.check:
        if not output.is_file():
            print(f"OPENAPI_DRIFT: missing snapshot at {output}", file=sys.stderr)
            return 1
        current = output.read_text(encoding="utf-8-sig")
        if current != rendered:
            print(f"OPENAPI_DRIFT: snapshot differs at {output}", file=sys.stderr)
            return 1
        print("OPENAPI_SNAPSHOT_OK")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"OPENAPI_EXPORTED {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"OPENAPI_EXPORT_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc