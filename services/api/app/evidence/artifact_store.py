"""Minimal filesystem artifact store for evidence raw materials (Task 8).

P0 ArtifactStore is locked to filesystem storage; the database keeps only
workspace-scoped relative pointers (10-api-and-events.md). The root directory
comes from ``LUDUS_ARTIFACT_ROOT`` (tests point it at a tmp dir); writes are
staged then moved so a crash never leaves a half-written artifact behind the
recorded pointer.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

ARTIFACT_ROOT_ENV = "LUDUS_ARTIFACT_ROOT"
_DEFAULT_ROOT = Path("var") / "artifacts"


@dataclass(frozen=True)
class StoredArtifact:
    """Result of one immutable write: pointer + integrity metadata."""

    storage_path: str  # workspace-scoped relative POSIX path
    sha256: str
    byte_size: int


class FilesystemArtifactStore:
    """Append-only body storage under one root; no update or delete surface."""

    def __init__(self, root: Path | None = None) -> None:
        env_root = os.getenv(ARTIFACT_ROOT_ENV, "").strip()
        self._root = root or (Path(env_root) if env_root else _DEFAULT_ROOT)

    @property
    def root(self) -> Path:
        return self._root

    def write(
        self,
        *,
        workspace_id: uuid.UUID,
        content: bytes,
        suffix: str = ".md",
    ) -> StoredArtifact:
        digest = hashlib.sha256(content).hexdigest()
        relative = PurePosixPath(
            f"workspaces/{workspace_id}/uploads/raw/{uuid.uuid4().hex}{suffix}"
        )
        target = self._root / Path(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.with_suffix(target.suffix + ".staging")
        staging.write_bytes(content)
        os.replace(staging, target)
        return StoredArtifact(
            storage_path=str(relative),
            sha256=digest,
            byte_size=len(content),
        )

    def read(self, *, workspace_id: uuid.UUID, storage_path: str) -> bytes:
        """Read one artifact body, refusing any pointer that escapes the tenant."""

        pointer = PurePosixPath(storage_path)
        expected_prefix = ("workspaces", str(workspace_id))
        if pointer.is_absolute() or ".." in pointer.parts:
            raise ValueError("storage_path must be a workspace-scoped relative pointer")
        if pointer.parts[:2] != expected_prefix:
            raise ValueError("storage_path does not belong to this workspace")
        return (self._root / Path(*pointer.parts)).read_bytes()
