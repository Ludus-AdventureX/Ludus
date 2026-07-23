from __future__ import annotations

import copy
import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from .models import MethodPackDescriptor
from .source_validator import (
    MethodSourceValidationError,
    _is_link_like,
    _normalized_bytes,
    compute_package_hash,
    validate_method_source,
    validate_runtime_package,
)


class MethodPackInstallError(RuntimeError):
    """Base error for method-pack installation failures."""


class MethodPackConflictError(MethodPackInstallError):
    """Raised when an ID/version already exists with a different content hash."""


def _assert_catalog_boundary(catalog: Path, candidate: Path) -> None:
    try:
        relative = candidate.absolute().relative_to(catalog)
    except ValueError as exc:
        raise MethodPackInstallError(f"method-pack path escapes catalog boundary: {candidate}") from exc
    current = catalog
    for part in relative.parts:
        current /= part
        if _is_link_like(current):
            raise MethodPackInstallError(f"linked catalog path is forbidden: {current}")
    if not candidate.resolve().is_relative_to(catalog):
        raise MethodPackInstallError(f"method-pack path escapes catalog boundary: {candidate}")


class MethodPackInstaller:
    """Validate a ways source and publish an immutable runtime catalog entry."""

    def install(self, source_path: str | Path, catalog_root: str | Path) -> MethodPackDescriptor:
        validated = validate_method_source(source_path)
        catalog = Path(catalog_root).expanduser().resolve()
        source = validated.root
        if catalog == source or catalog.is_relative_to(source):
            raise MethodPackInstallError("runtime catalog cannot be inside the editable source package")
        catalog.mkdir(parents=True, exist_ok=True)
        destination = catalog / validated.method_id / validated.version
        _assert_catalog_boundary(catalog, destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _assert_catalog_boundary(catalog, destination)

        runtime_manifest = self._runtime_manifest(validated.manifest)
        candidate_hash = self._candidate_hash(source, runtime_manifest)
        if destination.exists():
            return self._reuse_or_reject_existing(
                destination,
                validated.method_id,
                validated.version,
                candidate_hash,
            )

        staging = Path(
            tempfile.mkdtemp(prefix=f".{validated.method_id}-{validated.version}-", dir=catalog)
        )
        try:
            self._copy_as_runtime(source, staging, runtime_manifest)
            staged_hash = compute_package_hash(staging, published_manifest=True)
            if staged_hash != candidate_hash:
                raise MethodPackInstallError("candidate hash changed while staging runtime package")
            self._write_runtime_manifest(staging, candidate_hash)
            runtime = validate_runtime_package(staging)
            runtime_hash = compute_package_hash(staging, published_manifest=True)
            if runtime_hash != candidate_hash:
                raise MethodPackInstallError("runtime hash changed during publication")
            try:
                _assert_catalog_boundary(catalog, destination)
                os.replace(staging, destination)
            except FileExistsError:
                self._archive_staging(staging, catalog)
                _assert_catalog_boundary(catalog, destination)
                return self._reuse_or_reject_existing(
                    destination,
                    validated.method_id,
                    validated.version,
                    candidate_hash,
                )
            return MethodPackDescriptor(
                method_id=runtime.method_id,
                version=runtime.version,
                status="published",
                content_hash=candidate_hash,
                root=destination,
                manifest=runtime.manifest,
            )
        except MethodSourceValidationError as exc:
            self._archive_staging(staging, catalog)
            raise MethodPackInstallError(str(exc)) from exc
        except Exception:
            self._archive_staging(staging, catalog)
            raise

    @staticmethod
    def _runtime_manifest(source_manifest: dict[str, Any]) -> dict[str, Any]:
        runtime_manifest = copy.deepcopy(source_manifest)
        runtime_manifest["status"] = "published"
        release = runtime_manifest.setdefault("release", {})
        if not isinstance(release, dict):
            raise MethodPackInstallError("manifest.release must be a mapping")
        release["runtime_status"] = "published"
        release["content_hash"] = None
        return runtime_manifest

    def _candidate_hash(self, source: Path, runtime_manifest: dict[str, Any]) -> str:
        hasher = hashlib.sha256()
        for source_file in sorted(
            (path for path in source.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(source).as_posix(),
        ):
            relative = source_file.relative_to(source).as_posix()
            if relative == "manifest.yaml":
                content = self._yaml_bytes(runtime_manifest)
            else:
                content = _normalized_bytes(source_file)
            relative_bytes = relative.encode("utf-8")
            hasher.update(len(relative_bytes).to_bytes(8, "big"))
            hasher.update(relative_bytes)
            hasher.update(len(content).to_bytes(8, "big"))
            hasher.update(content)
        return hasher.hexdigest()

    def _copy_as_runtime(
        self,
        source: Path,
        staging: Path,
        runtime_manifest: dict[str, Any],
    ) -> None:
        for source_file in sorted(
            (path for path in source.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(source).as_posix(),
        ):
            relative = source_file.relative_to(source)
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if relative.as_posix() == "manifest.yaml":
                continue
            destination.write_bytes(_normalized_bytes(source_file))
        (staging / "manifest.yaml").write_bytes(self._yaml_bytes(runtime_manifest))

    def _write_runtime_manifest(self, staging: Path, content_hash: str) -> None:
        manifest_path = staging / "manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise MethodPackInstallError("runtime manifest is not a mapping")
        release = manifest.get("release")
        if not isinstance(release, dict):
            raise MethodPackInstallError("runtime manifest.release is not a mapping")
        release["content_hash"] = content_hash
        manifest_path.write_bytes(self._yaml_bytes(manifest))

    @staticmethod
    def _yaml_bytes(value: dict[str, Any]) -> bytes:
        text = yaml.safe_dump(value, allow_unicode=True, sort_keys=False)
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        return normalized.encode("utf-8")

    @staticmethod
    def _archive_staging(staging: Path, catalog: Path) -> Path | None:
        if not staging.exists():
            return None
        failed_root = catalog / ".failed"
        _assert_catalog_boundary(catalog, failed_root)
        failed_root.mkdir(parents=True, exist_ok=True)
        target = failed_root / f"{staging.name.lstrip('.')}-{uuid4().hex}"
        _assert_catalog_boundary(catalog, target)
        os.replace(staging, target)
        return target

    def _reuse_or_reject_existing(
        self,
        destination: Path,
        method_id: str,
        version: str,
        candidate_hash: str,
    ) -> MethodPackDescriptor:
        try:
            runtime = validate_runtime_package(destination)
            actual_hash = compute_package_hash(destination, published_manifest=True)
        except Exception as exc:
            raise MethodPackConflictError(
                f"existing method pack is invalid and cannot be replaced: {destination}"
            ) from exc
        expected_hash = runtime.manifest.get("release", {}).get("content_hash")
        if expected_hash != actual_hash:
            raise MethodPackConflictError(f"existing method pack hash mismatch: {destination}")
        if actual_hash != candidate_hash:
            raise MethodPackConflictError(
                f"same method id/version has different content hash: {method_id}@{version}"
            )
        if runtime.method_id != method_id or runtime.version != version:
            raise MethodPackConflictError(f"existing method pack identity mismatch: {destination}")
        return MethodPackDescriptor(
            method_id=runtime.method_id,
            version=runtime.version,
            status="published",
            content_hash=actual_hash,
            root=destination,
            manifest=runtime.manifest,
        )


def install_method_pack(source_path: str | Path, catalog_root: str | Path) -> MethodPackDescriptor:
    """Functional convenience wrapper for the CLI and callers without DI."""

    return MethodPackInstaller().install(source_path, catalog_root)
