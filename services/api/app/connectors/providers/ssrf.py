"""SSRF guard for provider outbound URLs (Task 8, case_api_data).

Every remote URL a provider adapter fetches must pass ``validate_outbound_url``
first. Policy (10-api-and-events.md security error ``UNSAFE_REMOTE_URL``):

- protocol whitelist: http/https only;
- no userinfo credentials inside the URL;
- port whitelist: 80 / 443 / 8080 / 8443;
- the hostname and *every* resolved address must be public: loopback,
  private (RFC1918/ULA), link-local (incl. 169.254.169.254 cloud metadata),
  reserved, multicast, and unspecified addresses are rejected;
- well-known metadata hostnames are rejected by name as defense in depth;
- redirects are never followed blindly: adapters re-validate every hop.

The resolver is injectable so tests can prove DNS-rebinding style negatives
without touching the network.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Sequence
from urllib.parse import urlsplit

Resolver = Callable[[str], Sequence[str]]

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_ALLOWED_PORTS = frozenset({80, 443, 8080, 8443})
_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata.goog",
        "instance-data",
    }
)


class UnsafeRemoteUrlError(Exception):
    """Raised when an outbound URL fails the SSRF safety policy."""

    code = "UNSAFE_REMOTE_URL"

    def __init__(self, reason: str) -> None:
        # Reason strings are static policy labels; they never echo the URL
        # body or credentials, so they are safe for logs and envelopes.
        super().__init__(reason)
        self.reason = reason


def _default_resolver(host: str) -> Sequence[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError as exc:  # DNS failure is a fail-closed rejection.
        raise UnsafeRemoteUrlError("dns_resolution_failed") from exc
    return [info[4][0] for info in infos]


def _reject_non_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    if (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise UnsafeRemoteUrlError("non_public_address")


def validate_outbound_url(url: str, *, resolver: Resolver | None = None) -> str:
    """Validate one outbound URL; return it unchanged when safe.

    Raises :class:`UnsafeRemoteUrlError` with a static policy reason on any
    violation. Adapters must call this again for every redirect hop.
    """

    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise UnsafeRemoteUrlError("scheme_not_allowed")
    if parts.username is not None or parts.password is not None:
        raise UnsafeRemoteUrlError("userinfo_not_allowed")
    host = parts.hostname
    if not host:
        raise UnsafeRemoteUrlError("host_missing")
    host = host.lower().rstrip(".")
    if host in _BLOCKED_HOSTNAMES:
        raise UnsafeRemoteUrlError("blocked_hostname")
    try:
        port = parts.port
    except ValueError as exc:
        raise UnsafeRemoteUrlError("port_invalid") from exc
    effective_port = port if port is not None else (80 if scheme == "http" else 443)
    if effective_port not in _ALLOWED_PORTS:
        raise UnsafeRemoteUrlError("port_not_allowed")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        _reject_non_public(literal)
        return url

    resolve = resolver or _default_resolver
    addresses = resolve(host)
    if not addresses:
        raise UnsafeRemoteUrlError("dns_resolution_failed")
    for raw in addresses:
        try:
            _reject_non_public(ipaddress.ip_address(raw))
        except ValueError as exc:
            raise UnsafeRemoteUrlError("dns_resolution_failed") from exc
    return url
