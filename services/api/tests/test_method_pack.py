from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from app.methods.installer import (
    MethodPackConflictError,
    MethodPackInstallError,
    MethodPackInstaller,
)
from app.methods.loader import (
    MethodPackIntegrityError,
    MethodPackLoadError,
    MethodPackLoader,
)
from app.methods.source_validator import (
    MethodSourceValidationError,
    validate_method_source,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = REPOSITORY_ROOT / "ways" / "hardtech-market-direction" / "1.1.0"


def test_hardtech_source_satisfies_publish_contract() -> None:
    validated = validate_method_source(SOURCE_ROOT)

    assert validated.method_id == "hardtech-market-direction"
    assert validated.version == "1.1.0"
    assert validated.manifest["status"] == "release_candidate"
    assert validated.manifest["release"]["runtime_status"] == "unpublished"
    assert len(validated.schema_ids) == 17
    assert len(validated.prompt_paths) == 10
    assert len(validated.eval_paths) == 6
    assert validated.skill_disposition_counts == {
        "P0 直接编译": 13,
        "能力已被其他合同吸收": 7,
        "延后到下一方法包": 8,
        "仅参考": 1,
        "禁用": 2,
    }


def test_hardtech_way_installs_as_immutable_runtime_pack(tmp_path: Path) -> None:
    installer = MethodPackInstaller()
    loader = MethodPackLoader(tmp_path / "method-packs")

    installed = installer.install(SOURCE_ROOT, tmp_path / "method-packs")
    pack = loader.load_from_catalog(installed.method_id, installed.version)

    assert installed.method_id == "hardtech-market-direction"
    assert installed.version == "1.1.0"
    assert installed.status == "published"
    assert installed.content_hash == pack.content_hash
    assert pack.manifest["status"] == "published"
    assert pack.manifest["release"]["runtime_status"] == "published"
    assert pack.manifest["release"]["content_hash"] == installed.content_hash
    assert pack.root == tmp_path / "method-packs" / "hardtech-market-direction" / "1.1.0"


def test_install_is_idempotent_for_same_id_version_and_hash(tmp_path: Path) -> None:
    installer = MethodPackInstaller()
    catalog = tmp_path / "method-packs"

    first = installer.install(SOURCE_ROOT, catalog)
    second = installer.install(SOURCE_ROOT, catalog)

    assert second == first


def test_different_hash_for_same_id_and_version_is_rejected(tmp_path: Path) -> None:
    installer = MethodPackInstaller()
    catalog = tmp_path / "method-packs"
    source_copy = tmp_path / "source-copy"

    shutil.copytree(SOURCE_ROOT, source_copy)
    installer.install(SOURCE_ROOT, catalog)

    readme = source_copy / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")

    with pytest.raises(MethodPackConflictError):
        installer.install(source_copy, catalog)


def test_runtime_tampering_is_rejected_by_hash_verification(tmp_path: Path) -> None:
    installer = MethodPackInstaller()
    catalog = tmp_path / "method-packs"
    installed = installer.install(SOURCE_ROOT, catalog)
    tampered = catalog / installed.method_id / installed.version / "README.md"
    tampered.write_text(tampered.read_text(encoding="utf-8") + "\ntampered\n", encoding="utf-8")

    with pytest.raises(MethodPackIntegrityError):
        MethodPackLoader(catalog).load_from_catalog(installed.method_id, installed.version)


def test_release_candidate_is_not_loadable_from_runtime_catalog(tmp_path: Path) -> None:
    catalog = tmp_path / "method-packs" / "hardtech-market-direction" / "1.1.0"
    shutil.copytree(SOURCE_ROOT, catalog)

    with pytest.raises(MethodPackLoadError):
        MethodPackLoader(tmp_path / "method-packs").load_from_catalog(
            "hardtech-market-direction", "1.1.0"
        )


def test_unknown_worker_is_rejected_before_install(tmp_path: Path) -> None:
    source_copy = tmp_path / "source-copy"
    shutil.copytree(SOURCE_ROOT, source_copy)
    manifest_path = source_copy / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["workers"].append(
        {
            "id": "unknown-worker",
            "prompt": "prompts/research.md",
            "output_schema": "urn:ludus:method:hardtech-market-direction:research-packet:1.1.0",
        }
    )
    manifest_path.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(MethodSourceValidationError, match="worker"):
        validate_method_source(source_copy)


def test_external_schema_refs_are_rejected(tmp_path: Path) -> None:
    source_copy = tmp_path / "source-copy"
    shutil.copytree(SOURCE_ROOT, source_copy)
    schema_path = source_copy / "schemas" / "challenge.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["$ref"] = "https://example.invalid/schema.json"
    schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(MethodSourceValidationError, match="network schema ref"):
        validate_method_source(source_copy)

def test_unknown_tool_in_global_deny_list_is_rejected(tmp_path: Path) -> None:
    source_copy = tmp_path / "source-copy"
    shutil.copytree(SOURCE_ROOT, source_copy)
    manifest_path = source_copy / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["tool_permissions"]["deny_for_all"].append("unknown_tool")
    manifest_path.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(MethodSourceValidationError, match="unknown tool"):
        validate_method_source(source_copy)


@pytest.mark.parametrize("bad_path", ["../README.md", r"..\README.md", r"C:\outside.md"])
def test_manifest_path_traversal_is_rejected(tmp_path: Path, bad_path: str) -> None:
    source_copy = tmp_path / "source-copy"
    shutil.copytree(SOURCE_ROOT, source_copy)
    manifest_path = source_copy / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["documentation"]["overview"] = bad_path
    manifest_path.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(MethodSourceValidationError, match="path"):
        validate_method_source(source_copy)


def _rewrite_text_newlines(root: Path, newline: str) -> None:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        path.write_bytes(normalized.replace("\n", newline).encode("utf-8"))


def test_lf_and_crlf_source_packages_have_same_content_hash(tmp_path: Path) -> None:
    lf_source = tmp_path / "source-lf"
    crlf_source = tmp_path / "source-crlf"
    shutil.copytree(SOURCE_ROOT, lf_source)
    shutil.copytree(SOURCE_ROOT, crlf_source)
    _rewrite_text_newlines(crlf_source, "\r\n")

    installer = MethodPackInstaller()
    lf_pack = installer.install(lf_source, tmp_path / "catalog-lf")
    crlf_pack = installer.install(crlf_source, tmp_path / "catalog-crlf")

    assert lf_pack.content_hash == crlf_pack.content_hash


@pytest.mark.parametrize(
    ("method_id", "version"),
    [
        ("../hardtech-market-direction", "1.1.0"),
        ("hardtech/../hardtech-market-direction", "1.1.0"),
        ("hardtech-market-direction", "../1.1.0"),
        (r"C:\catalog", "1.1.0"),
    ],
)
def test_loader_rejects_path_components(tmp_path: Path, method_id: str, version: str) -> None:
    with pytest.raises(MethodPackLoadError, match="invalid"):
        MethodPackLoader(tmp_path / "method-packs").load_from_catalog(method_id, version)


def test_checked_in_runtime_matches_source_except_publication_fields() -> None:
    runtime_root = REPOSITORY_ROOT / "method-packs" / "hardtech-market-direction" / "1.1.0"
    runtime = MethodPackLoader(REPOSITORY_ROOT / "method-packs").load_from_catalog(
        "hardtech-market-direction", "1.1.0"
    )

    source_files = {
        path.relative_to(SOURCE_ROOT).as_posix()
        for path in SOURCE_ROOT.rglob("*")
        if path.is_file()
    }
    runtime_files = {
        path.relative_to(runtime_root).as_posix()
        for path in runtime_root.rglob("*")
        if path.is_file()
    }
    assert runtime_files == source_files

    for relative in sorted(source_files - {"manifest.yaml"}):
        source_bytes = (SOURCE_ROOT / relative).read_bytes()
        runtime_bytes = (runtime_root / relative).read_bytes()
        assert source_bytes.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n") == runtime_bytes.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")

    source_manifest = yaml.safe_load(
        (SOURCE_ROOT / "manifest.yaml").read_text(encoding="utf-8")
    )
    runtime_manifest = yaml.safe_load(
        (runtime_root / "manifest.yaml").read_text(encoding="utf-8")
    )
    published_hash = runtime_manifest["release"]["content_hash"]
    runtime_manifest["status"] = "release_candidate"
    runtime_manifest["release"]["runtime_status"] = "unpublished"
    runtime_manifest["release"]["content_hash"] = None
    assert runtime_manifest == source_manifest
    assert runtime.content_hash == published_hash

def test_manifest_source_skill_version_drift_is_rejected(tmp_path: Path) -> None:
    source_copy = tmp_path / "source-copy"
    shutil.copytree(SOURCE_ROOT, source_copy)
    manifest_path = source_copy / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["source_skills"][0]["version"] = "0.0.0"
    manifest_path.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(MethodSourceValidationError, match="source Skill version drift"):
        validate_method_source(source_copy)


def _make_directory_link(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            check=True,
            capture_output=True,
            text=True,
        )


def test_loader_rejects_catalog_method_directory_link_escape(tmp_path: Path) -> None:
    outside_catalog = tmp_path / "outside-catalog"
    MethodPackInstaller().install(SOURCE_ROOT, outside_catalog)
    catalog = tmp_path / "method-packs"
    catalog.mkdir()
    _make_directory_link(
        catalog / "hardtech-market-direction",
        outside_catalog / "hardtech-market-direction",
    )

    with pytest.raises(MethodPackLoadError, match="link|boundary"):
        MethodPackLoader(catalog).load_from_catalog("hardtech-market-direction", "1.1.0")


def test_installer_rejects_catalog_method_directory_link_escape(tmp_path: Path) -> None:
    outside_catalog = tmp_path / "outside-catalog"
    MethodPackInstaller().install(SOURCE_ROOT, outside_catalog)
    catalog = tmp_path / "method-packs"
    catalog.mkdir()
    _make_directory_link(
        catalog / "hardtech-market-direction",
        outside_catalog / "hardtech-market-direction",
    )

    with pytest.raises(MethodPackInstallError, match="link|boundary"):
        MethodPackInstaller().install(SOURCE_ROOT, catalog)


@pytest.mark.parametrize(
    "mutation",
    [
        ("applicability", "operator", "eq"),
        ("exclusion", "route", "unsupported"),
        ("cynefin", "formal_block_domains", ["disorder"]),
    ],
)
def test_manifest_route_and_cynefin_contract_drift_is_rejected(
    tmp_path: Path,
    mutation: tuple[str, str, object],
) -> None:
    source_copy = tmp_path / "source-copy"
    shutil.copytree(SOURCE_ROOT, source_copy)
    manifest_path = source_copy / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    section, field, value = mutation
    if section == "applicability":
        manifest["applicability"]["all"][0][field] = value
    elif section == "exclusion":
        manifest["exclusions"]["any"][4][field] = value
    else:
        manifest["decision_gate"]["cynefin"][field] = value
    manifest_path.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(MethodSourceValidationError, match="applicability|exclusion|Cynefin"):
        validate_method_source(source_copy)
