from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOOK_ROOT = REPOSITORY_ROOT.parent / "look"
MANIFEST_PATH = REPOSITORY_ROOT / "design" / "look-source-manifest.json"
CORE_FILES = ("VERSION", "README.md", "index.html", "themes.css", "styles.css", "app.js")
EXPECTED_BUNDLE_SHA256 = "c5d5d65bf62efdd14e4e3e13d1c70b92f9d6b4cdd4dbd2f652107d84d1a55e98"
EXPECTED_THEMES = (
    "ink",
    "ledger",
    "vermilion",
    "red",
    "orange",
    "yellow",
    "green",
    "cyan",
    "blue",
    "purple",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Snapshot the immutable Look V7 design input.")
    parser.add_argument("--check", action="store_true", help="Validate the existing manifest without writing it.")
    parser.add_argument(
        "--look-root",
        type=Path,
        default=None,
        help="Look source directory; defaults to ../look or DECISION_LAB_LOOK_PATH.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=MANIFEST_PATH,
        help="Manifest path; defaults to design/look-source-manifest.json.",
    )
    return parser.parse_args()


def resolve_look_root(argument: Path | None) -> Path:
    if argument is not None:
        return argument.resolve()
    configured = Path(os.environ["DECISION_LAB_LOOK_PATH"]) if os.environ.get("DECISION_LAB_LOOK_PATH") else DEFAULT_LOOK_ROOT
    return configured.resolve()


def load_core_files(look_root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for name in CORE_FILES:
        path = look_root / name
        if not path.is_file():
            raise RuntimeError(f"Look core file is missing: {name}")
        files[name] = path.read_bytes()
    return files


def bundle_hash(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name in CORE_FILES:
        digest.update(name.encode("utf-8"))
        digest.update(b"\n")
        digest.update(files[name])
        digest.update(b"\n")
    return digest.hexdigest()


def theme_ids(themes_css: str) -> list[str]:
    ids = set(re.findall(r'html\[data-theme="([^"]+)"\]', themes_css))
    return sorted(ids, key=EXPECTED_THEMES.index if ids.issubset(set(EXPECTED_THEMES)) else None)


def token_names(themes_css: str) -> list[str]:
    return sorted(set(re.findall(r"--([A-Za-z0-9-]+)\s*:", themes_css)))


def build_manifest(look_root: Path, files: dict[str, bytes]) -> dict[str, Any]:
    version_text = files["VERSION"].decode("utf-8-sig").replace("\r\n", "\n").rstrip("\n")
    themes = theme_ids(files["themes.css"].decode("utf-8-sig"))
    if themes != list(EXPECTED_THEMES):
        raise RuntimeError(f"Look theme IDs differ from the frozen V7 set: {themes}")

    return {
        "schemaVersion": "1.0.0",
        "source": "../look",
        "lookVersionText": version_text,
        "importedAt": date.today().isoformat(),
        "files": list(CORE_FILES),
        "fileSha256": {name: hashlib.sha256(files[name]).hexdigest() for name in CORE_FILES},
        "bundleSha256": bundle_hash(files),
        "expectedBundleSha256": EXPECTED_BUNDLE_SHA256,
        "themes": list(EXPECTED_THEMES),
        "defaultTheme": "ink",
        "themeTokenNames": token_names(files["themes.css"].decode("utf-8-sig")),
        "componentMappings": [
            {"source": "masthead", "target": "Masthead"},
            {"source": "decision-spine", "target": "DecisionSpine"},
            {"source": "workspace", "target": "WorkspaceView"},
            {"source": "analysis", "target": "AnalysisView"},
            {"source": "report", "target": "ReportView"},
            {"source": "sandbox", "target": "SandboxView"},
            {"source": "decision", "target": "DecisionView"},
            {"source": "project-drawer", "target": "ProjectDrawer"},
            {"source": "empty-project", "target": "EmptyProjectView"},
            {"source": "review-dialog", "target": "ReviewDialog"},
            {"source": "theme-drawer", "target": "ThemeDrawer"},
            {"source": "evidence-drawer", "target": "EvidenceDrawer"},
        ],
        "runtimeDependencyPolicy": {
            "index.html": "structure-and-accessibility-reference",
            "themes.css": "token-source; convert to centralized tokens",
            "styles.css": "layout-and-component-source; split before production use",
            "app.js": "behavior-specification-only; never load at runtime",
        },
        "readiness": {
            "lookRootExists": look_root.is_dir(),
            "bundleMatchesFrozenV7": bundle_hash(files) == EXPECTED_BUNDLE_SHA256,
            "headOrLogoStateNotRead": True,
        },
    }


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def check_manifest(manifest_path: Path, expected: dict[str, Any]) -> None:
    if not manifest_path.is_file():
        raise RuntimeError(f"Look source manifest is missing: {manifest_path}")
    actual = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    for key in (
        "schemaVersion",
        "source",
        "files",
        "fileSha256",
        "bundleSha256",
        "expectedBundleSha256",
        "themes",
        "defaultTheme",
    ):
        if actual.get(key) != expected.get(key):
            raise RuntimeError(f"Look manifest drift at key '{key}'.")
    if actual.get("bundleSha256") != EXPECTED_BUNDLE_SHA256:
        raise RuntimeError("Look bundle hash does not match the frozen V7 hash.")


def main() -> int:
    args = parse_args()
    look_root = resolve_look_root(args.look_root)
    manifest_path = args.manifest.resolve()
    files = load_core_files(look_root)
    manifest = build_manifest(look_root, files)

    if manifest["bundleSha256"] != EXPECTED_BUNDLE_SHA256:
        raise RuntimeError(
            "Look core bundle differs from the frozen V7 hash; stop automatic import and review the design diff."
        )

    if args.check:
        check_manifest(manifest_path, manifest)
        print("LOOK_V7_SNAPSHOT_OK")
        return 0

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8", newline="\n")
    print(f"LOOK_V7_SNAPSHOT_WRITTEN {manifest_path}")
    print(f"LOOK_V7_BUNDLE_SHA256 {manifest['bundleSha256']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"LOOK_V7_SNAPSHOT_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc