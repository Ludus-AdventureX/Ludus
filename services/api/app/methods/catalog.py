"""Server-side authority for the method binding recorded on a charter.

``methodContentHash`` used to be whatever the caller sent, and the shipped web
client sent ``sha256:`` + 32 random bytes. Every charter and every run therefore
carried a traceability field that was shape-correct and meaning-free: it could
not answer the only question it exists to answer — which method bytes produced
this verdict.

The binding is now resolved from the published package on disk through the same
:class:`~app.methods.loader.MethodPackLoader` the router uses, so a charter's
recorded method and a routing decision cannot disagree, and the loader's
integrity check (manifest-declared hash vs. recomputed bytes) applies to the
charter path too.

The catalog is REQUIRED. When it cannot be resolved the caller fails closed:
refusing to create a charter is recoverable, recording a fabricated provenance
hash is not.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .loader import MethodPackLoader, MethodPackLoadError

CATALOG_ROOT_ENV = "METHOD_CATALOG_ROOT"

# The single published pack. Kept in sync with MethodRouter._load_published_method:
# both sides must name the same default or a charter could record a method the
# router never selected.
DEFAULT_METHOD_ID = "hardtech-market-direction"
DEFAULT_METHOD_VERSION = "1.1.0"

_CATALOG_DIRNAME = "method-packs"


class MethodBindingUnavailable(RuntimeError):
    """The requested method is not resolvable from the published catalog."""


@dataclass(frozen=True)
class MethodBinding:
    """A method identity plus the hash of the bytes that carry it."""

    method_id: str
    method_version: str
    content_hash: str


def method_catalog_root() -> Path:
    """Locate the published method catalog.

    ``METHOD_CATALOG_ROOT`` wins when set (the container sets nothing and relies
    on the image layout). Otherwise two layouts are probed, in order:

    - repository checkout: ``services/api/app/methods`` -> ``<repo>/method-packs``
    - container image: ``/app/app/methods`` -> ``/app/method-packs``

    A missing catalog is NOT papered over here; the resolver raises so the
    failure names the missing path.
    """

    configured = os.getenv(CATALOG_ROOT_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    here = Path(__file__).resolve()
    candidates: list[Path] = []
    for depth in (4, 2):
        if depth < len(here.parents):
            candidates.append(here.parents[depth] / _CATALOG_DIRNAME)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    # Nothing found: return the most likely location so the error message points
    # at a real path instead of an empty string.
    return candidates[0] if candidates else Path(_CATALOG_DIRNAME).resolve()


def resolve_method_binding(
    method_id: str | None = None, method_version: str | None = None
) -> MethodBinding:
    """Resolve (id, version) into an authoritative binding.

    Blank/absent inputs fall back to the single published pack, which is what
    the router would have selected anyway.

    Raises:
        MethodBindingUnavailable: the pack is missing, structurally invalid, or
            its bytes do not match the hash its manifest declares.
    """

    wanted_id = (str(method_id).strip() if method_id is not None else "") or DEFAULT_METHOD_ID
    wanted_version = (
        str(method_version).strip() if method_version is not None else ""
    ) or DEFAULT_METHOD_VERSION
    return _resolve(str(method_catalog_root()), wanted_id, wanted_version)


# Hashing a pack walks and reads every file in it, so the result is memoised per
# (root, id, version). Published packs are immutable by definition; a failed
# resolution is not cached, so a repaired catalog recovers without a restart.
@lru_cache(maxsize=32)
def _resolve(catalog_root: str, method_id: str, version: str) -> MethodBinding:
    try:
        pack = MethodPackLoader(catalog_root).load_from_catalog(method_id, version)
    except MethodPackLoadError as exc:
        raise MethodBindingUnavailable(str(exc)) from exc
    return MethodBinding(
        method_id=pack.method_id,
        method_version=pack.version,
        # `sha256:` prefixed to match every other content hash on the wire
        # (case/dossier snapshots, report digests); the loader returns bare hex.
        content_hash=f"sha256:{pack.content_hash}",
    )


def reset_binding_cache() -> None:
    """Drop the memoised bindings (tests that relocate the catalog)."""

    _resolve.cache_clear()
