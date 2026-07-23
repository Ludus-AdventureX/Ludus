from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPOSITORY_ROOT / "services" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.methods.installer import MethodPackInstaller  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and publish a Ludus method source package")
    parser.add_argument("source", type=Path, help="editable ways source package directory")
    parser.add_argument(
        "--catalog-root",
        type=Path,
        default=REPOSITORY_ROOT / "method-packs",
        help="runtime method-pack catalog directory",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = args.source if args.source.is_absolute() else REPOSITORY_ROOT / args.source
    catalog = args.catalog_root if args.catalog_root.is_absolute() else REPOSITORY_ROOT / args.catalog_root
    installed = MethodPackInstaller().install(source, catalog)
    payload = installed.as_dict()
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(f"PUBLISHED {installed.method_id}@{installed.version}")
        print(f"CONTENT_HASH {installed.content_hash}")
        print(f"CATALOG_PATH {installed.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
