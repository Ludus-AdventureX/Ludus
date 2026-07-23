from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from .models import LoadedMethodPack
from .source_validator import (
    MethodSourceValidationError,
    _is_link_like,
    compute_package_hash,
    validate_runtime_package,
)

_COMPONENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class MethodPackLoadError(RuntimeError):
    """Raised when a runtime package is unavailable or structurally invalid."""


class MethodPackIntegrityError(MethodPackLoadError):
    """Raised when published package bytes do not match the recorded hash."""


class MethodPackLoader:
    """Load only published, structurally valid and hash-verified method packs."""

    def __init__(self, catalog_root: str | Path) -> None:
        self.catalog_root = Path(catalog_root).expanduser().resolve()

    def load_from_catalog(self, method_id: str, version: str) -> LoadedMethodPack:
        self._validate_component(method_id, "method id")
        self._validate_component(version, "method version")
        package_root = self._catalog_package_root(method_id, version)
        try:
            validated = validate_runtime_package(package_root)
        except MethodSourceValidationError as exc:
            raise MethodPackLoadError(str(exc)) from exc
        expected_hash = validated.manifest.get("release", {}).get("content_hash")
        actual_hash = compute_package_hash(package_root, published_manifest=True)
        if expected_hash != actual_hash:
            raise MethodPackIntegrityError(
                f"published method pack hash mismatch: {method_id}@{version}"
            )
        files = tuple(
            sorted(
                path.relative_to(package_root).as_posix()
                for path in package_root.rglob("*")
                if path.is_file()
            )
        )
        return LoadedMethodPack(
            method_id=validated.method_id,
            version=validated.version,
            status="published",
            content_hash=actual_hash,
            root=package_root,
            manifest=validated.manifest,
            files=files,
        )

    def load(self, method_id: str, version: str) -> LoadedMethodPack:
        return self.load_from_catalog(method_id, version)

    def list_published(self) -> list[LoadedMethodPack]:
        if not self.catalog_root.is_dir():
            return []
        packs: list[LoadedMethodPack] = []
        for method_directory in sorted(self.catalog_root.iterdir(), key=lambda path: path.name):
            if method_directory.name.startswith("."):
                continue
            if _is_link_like(method_directory):
                raise MethodPackLoadError(f"linked method catalog entry is forbidden: {method_directory}")
            if not method_directory.is_dir():
                continue
            for version_directory in sorted(method_directory.iterdir(), key=lambda path: path.name):
                if version_directory.name.startswith("."):
                    continue
                if _is_link_like(version_directory):
                    raise MethodPackLoadError(
                        f"linked method version entry is forbidden: {version_directory}"
                    )
                if not version_directory.is_dir():
                    continue
                manifest_path = version_directory / "manifest.yaml"
                if not manifest_path.is_file():
                    raise MethodPackLoadError(f"runtime package manifest is missing: {version_directory}")
                try:
                    status = self._read_status(manifest_path)
                except Exception as exc:
                    raise MethodPackLoadError(f"runtime package manifest is unreadable: {version_directory}") from exc
                if status != "published":
                    continue
                packs.append(self.load_from_catalog(method_directory.name, version_directory.name))
        return packs

    def _catalog_package_root(self, method_id: str, version: str) -> Path:
        method_root = self.catalog_root / method_id
        package_root = method_root / version
        for candidate in (method_root, package_root):
            if _is_link_like(candidate):
                raise MethodPackLoadError(f"linked catalog path is forbidden: {candidate}")
        if not package_root.is_dir():
            raise MethodPackLoadError(
                f"published method pack is not available: {method_id}@{version}"
            )
        resolved = package_root.resolve()
        if not resolved.is_relative_to(self.catalog_root):
            raise MethodPackLoadError(f"method-pack path escapes catalog boundary: {package_root}")
        return package_root

    @staticmethod
    def _read_status(manifest_path: Path) -> str | None:
        import yaml

        value = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        return value.get("status") if isinstance(value, dict) else None

    @staticmethod
    def _validate_component(value: str, label: str) -> None:
        if not isinstance(value, str) or not _COMPONENT_PATTERN.fullmatch(value):
            raise MethodPackLoadError(f"invalid {label}: {value!r}")
        if PurePosixPath(value).is_absolute() or "/" in value or "\\" in value or value in {".", ".."}:
            raise MethodPackLoadError(f"invalid {label}: {value!r}")
