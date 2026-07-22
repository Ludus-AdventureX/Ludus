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
TOKEN_ROOT = REPOSITORY_ROOT / "design" / "tokens"
THEME_TOKEN_PATH = TOKEN_ROOT / "themes.generated.css"
SEMANTIC_TOKEN_PATH = TOKEN_ROOT / "semantic.css"
COMPONENT_TOKEN_PATH = TOKEN_ROOT / "components.css"
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

SEMANTIC_CSS = """/* Generated semantic aliases for the Ludus V7 theme contract. */
@layer tokens {
  :root {
    --surface-canvas: var(--paper-base);
    --surface-sheet: var(--paper-sheet);
    --surface-muted: var(--paper-wash);
    --surface-night: var(--night-base);
    --surface-night-sheet: var(--night-sheet);
    --text-primary: var(--ink);
    --text-secondary: var(--ink-2);
    --text-tertiary: var(--ink-3);
    --border-subtle: var(--paper-rule);
    --border-strong: var(--paper-rule-strong);
    --responsibility-human: var(--human);
    --responsibility-analysis: var(--analysis);
    --responsibility-unknown: var(--unknown);
    --state-danger: var(--danger);
    --focus-ring: color-mix(in srgb, var(--analysis) 72%, white);
    --shadow-soft: 0 18px 60px rgb(var(--shadow-rgb) / 0.12);
  }
}
"""

COMPONENT_CSS = """/* Generated geometry tokens; component CSS consumes these aliases. */
@layer tokens {
  :root {
    --layout-max: 1440px;
    --masthead-height: 72px;
    --spine-height: 76px;
    --stage-gutter: clamp(18px, 3vw, 48px);
    --panel-padding: clamp(20px, 3vw, 40px);
    --drawer-width: min(420px, calc(100vw - 28px));
    --radius-control: 3px;
    --radius-panel: 5px;
    --duration-fast: 140ms;
    --duration-medium: 240ms;
    --font-editorial: "Iowan Old Style", "Songti SC", "Noto Serif CJK SC", serif;
    --font-ui: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
    --font-mono: "SFMono-Regular", Consolas, monospace;
  }
}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Snapshot the immutable Look V7 design input.")
    parser.add_argument("--check", action="store_true", help="Validate the existing manifest and tokens without writing them.")
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
    configured = (
        Path(os.environ["DECISION_LAB_LOOK_PATH"])
        if os.environ.get("DECISION_LAB_LOOK_PATH")
        else DEFAULT_LOOK_ROOT
    )
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


def render_theme_tokens(themes_css: str) -> str:
    pattern = re.compile(
        r'(?P<selector>:root,\s*html\[data-theme="ink"\]|html\[data-theme="(?P<theme>[a-z]+)"\])\s*\{(?P<body>.*?)\}',
        re.DOTALL,
    )
    blocks: dict[str, tuple[str, str]] = {}
    for match in pattern.finditer(themes_css):
        theme = match.group("theme") or "ink"
        if theme in EXPECTED_THEMES:
            selector = match.group("selector").replace("\r\n", "\n").strip()
            body = match.group("body").replace("\r\n", "\n").strip("\n")
            blocks[theme] = (selector, body)

    if set(blocks) != set(EXPECTED_THEMES):
        raise RuntimeError(f"Unable to generate all ten theme blocks; found {sorted(blocks)}")

    rendered = [
        "/* Generated from ../look/themes.css by scripts/snapshot_look.py.",
        "   Do not hand-edit. Responsibility semantics remain Human / Analysis / Unknown. */",
        "@layer tokens {",
    ]
    for theme in EXPECTED_THEMES:
        selector, body = blocks[theme]
        indented_body = "\n".join(f"  {line.rstrip()}" for line in body.splitlines())
        rendered.extend([f"  {selector} {{", indented_body, "  }", ""])
    rendered.append("}")
    return "\n".join(rendered).rstrip() + "\n"


def generated_artifacts(themes_css: str) -> dict[Path, str]:
    return {
        THEME_TOKEN_PATH: render_theme_tokens(themes_css),
        SEMANTIC_TOKEN_PATH: SEMANTIC_CSS,
        COMPONENT_TOKEN_PATH: COMPONENT_CSS,
    }


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_manifest(
    look_root: Path,
    files: dict[str, bytes],
    artifacts: dict[Path, str],
) -> dict[str, Any]:
    version_text = files["VERSION"].decode("utf-8-sig").replace("\r\n", "\n").rstrip("\n")
    themes_css = files["themes.css"].decode("utf-8-sig")
    themes = theme_ids(themes_css)
    if themes != list(EXPECTED_THEMES):
        raise RuntimeError(f"Look theme IDs differ from the frozen V7 set: {themes}")

    return {
        "schemaVersion": "1.1.0",
        "source": "../look",
        "lookVersionText": version_text,
        "importedAt": date.today().isoformat(),
        "files": list(CORE_FILES),
        "fileSha256": {name: hashlib.sha256(files[name]).hexdigest() for name in CORE_FILES},
        "bundleSha256": bundle_hash(files),
        "expectedBundleSha256": EXPECTED_BUNDLE_SHA256,
        "themes": list(EXPECTED_THEMES),
        "defaultTheme": "ink",
        "themeTokenNames": token_names(themes_css),
        "generatedArtifacts": {
            str(path.relative_to(REPOSITORY_ROOT)).replace("\\", "/"): sha256_text(content)
            for path, content in artifacts.items()
        },
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
            "themes.css": "token-source; converted to centralized generated tokens",
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


def check_text_file(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"{label} is missing: {path}")
    actual = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    if actual != expected:
        raise RuntimeError(f"{label} drift detected: {path}")


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
        "generatedArtifacts",
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
    themes_css = files["themes.css"].decode("utf-8-sig")
    artifacts = generated_artifacts(themes_css)
    manifest = build_manifest(look_root, files, artifacts)

    if manifest["bundleSha256"] != EXPECTED_BUNDLE_SHA256:
        raise RuntimeError(
            "Look core bundle differs from the frozen V7 hash; stop automatic import and review the design diff."
        )

    if args.check:
        check_manifest(manifest_path, manifest)
        for path, content in artifacts.items():
            check_text_file(path, content, path.name)
        print("LOOK_V7_SNAPSHOT_OK")
        print("LOOK_V7_TOKENS_OK")
        return 0

    for path, content in artifacts.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8", newline="\n")
    print(f"LOOK_V7_SNAPSHOT_WRITTEN {manifest_path}")
    print(f"LOOK_V7_BUNDLE_SHA256 {manifest['bundleSha256']}")
    print("LOOK_V7_TOKENS_WRITTEN")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"LOOK_V7_SNAPSHOT_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc