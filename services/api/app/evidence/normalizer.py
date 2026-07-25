"""Source normalization and same-source deduplication (Task 8).

Pure functions only: canonical URI normalization, root-source fingerprinting,
and independent-source grouping. Three articles citing the same underlying
report collapse into one group and therefore count as exactly one independent
source for the quality gateway.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import NAMESPACE_URL, UUID, uuid5

# Query parameters that never change the underlying document identity.
_TRACKING_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gclid",
        "fbclid",
        "ref",
        "ref_src",
    }
)

_DEFAULT_PORTS = {"http": "80", "https": "443"}


def canonicalize_url(url: str) -> str:
    """Normalize a URL for identity comparison, never for fetching.

    Lower-cases scheme/host, strips default ports, fragments, tracking
    parameters and trailing slashes, and sorts the remaining query pairs so
    the same document always yields the same canonical string.
    """

    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    netloc = host
    if port is not None and str(port) != _DEFAULT_PORTS.get(scheme, ""):
        netloc = f"{host}:{port}"
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(sorted(query_pairs))
    return urlunsplit((scheme, netloc, path, query, ""))


def source_domain(url: str) -> str | None:
    """Extract the lower-cased registrable host for display and grading."""

    host = urlsplit(url.strip()).hostname
    return host.lower() if host else None


@dataclass(frozen=True)
class SourceIdentity:
    """Identity inputs of one evidence candidate for dedup purposes.

    ``cited_source_uri`` names the underlying document a page merely cites
    (for example three news articles quoting the same market report); when
    present it, not the page URL, defines the independent source.
    """

    candidate_key: str
    canonical_uri: str | None = None
    cited_source_uri: str | None = None
    content_sha256: str | None = None


def root_source_fingerprint(identity: SourceIdentity) -> str:
    """Return the stable fingerprint of the underlying (root) source."""

    if identity.cited_source_uri:
        return f"cited:{canonicalize_url(identity.cited_source_uri)}"
    if identity.canonical_uri:
        return f"uri:{canonicalize_url(identity.canonical_uri)}"
    if identity.content_sha256:
        return f"sha256:{identity.content_sha256.lower()}"
    # No stable identity at all: the candidate is its own singleton group.
    return f"opaque:{identity.candidate_key}"


def group_id_for_fingerprint(fingerprint: str) -> UUID:
    """Derive a deterministic UUID for one root-source fingerprint."""

    return uuid5(NAMESPACE_URL, f"ludus-independent-source:{fingerprint}")


@dataclass(frozen=True)
class IndependentSourceGrouping:
    """Result of same-source deduplication over one candidate batch."""

    group_by_candidate: dict[str, UUID] = field(default_factory=dict)
    members_by_group: dict[UUID, tuple[str, ...]] = field(default_factory=dict)

    @property
    def independent_source_count(self) -> int:
        return len(self.members_by_group)


def group_independent_sources(
    identities: list[SourceIdentity],
) -> IndependentSourceGrouping:
    """Group candidates by root source; each group is one independent source."""

    group_by_candidate: dict[str, UUID] = {}
    members: dict[UUID, list[str]] = {}
    for identity in identities:
        group = group_id_for_fingerprint(root_source_fingerprint(identity))
        group_by_candidate[identity.candidate_key] = group
        members.setdefault(group, []).append(identity.candidate_key)
    return IndependentSourceGrouping(
        group_by_candidate=group_by_candidate,
        members_by_group={
            group: tuple(keys) for group, keys in members.items()
        },
    )
