"""Task 8 owner tests: SSRF guard negatives (no network involved)."""

from __future__ import annotations

import pytest

from app.connectors.providers.ssrf import UnsafeRemoteUrlError, validate_outbound_url


def _resolver(*addresses: str):
    def resolve(host: str):
        return list(addresses)

    return resolve


PUBLIC = _resolver("93.184.216.34")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.test/data",
        "gopher://example.test/1",
        "javascript:alert(1)",
    ],
)
def test_non_http_schemes_rejected(url: str) -> None:
    with pytest.raises(UnsafeRemoteUrlError) as excinfo:
        validate_outbound_url(url, resolver=PUBLIC)
    assert excinfo.value.reason == "scheme_not_allowed"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://127.0.0.53/resolve",
        "https://[::1]/admin",
        "http://10.0.0.5/internal",
        "http://172.16.4.2/internal",
        "http://192.168.1.10/router",
        "http://169.254.169.254/latest/meta-data/",
        "http://0.0.0.0/",
        "https://[fd00:ec2::254]/metadata",
        "https://[fe80::1]/link-local",
    ],
)
def test_internal_loopback_and_metadata_addresses_rejected(url: str) -> None:
    with pytest.raises(UnsafeRemoteUrlError) as excinfo:
        validate_outbound_url(url)
    assert excinfo.value.reason == "non_public_address"


@pytest.mark.parametrize(
    "host", ["localhost", "metadata.google.internal", "metadata.goog", "instance-data"]
)
def test_blocked_hostnames_rejected_by_name(host: str) -> None:
    with pytest.raises(UnsafeRemoteUrlError) as excinfo:
        validate_outbound_url(f"https://{host}/x", resolver=PUBLIC)
    assert excinfo.value.reason == "blocked_hostname"


def test_dns_rebinding_to_private_address_rejected() -> None:
    with pytest.raises(UnsafeRemoteUrlError) as excinfo:
        validate_outbound_url(
            "https://evil.example.test/x", resolver=_resolver("93.184.216.34", "10.0.0.9")
        )
    assert excinfo.value.reason == "non_public_address"


def test_dns_failure_fails_closed() -> None:
    with pytest.raises(UnsafeRemoteUrlError) as excinfo:
        validate_outbound_url("https://nx.example.test/x", resolver=_resolver())
    assert excinfo.value.reason == "dns_resolution_failed"


def test_userinfo_rejected() -> None:
    with pytest.raises(UnsafeRemoteUrlError) as excinfo:
        validate_outbound_url("https://user:pass@example.test/x", resolver=PUBLIC)
    assert excinfo.value.reason == "userinfo_not_allowed"


def test_unusual_port_rejected() -> None:
    with pytest.raises(UnsafeRemoteUrlError) as excinfo:
        validate_outbound_url("https://example.test:6379/x", resolver=PUBLIC)
    assert excinfo.value.reason == "port_not_allowed"


def test_public_https_url_passes() -> None:
    url = "https://example.test/report?id=1"
    assert validate_outbound_url(url, resolver=PUBLIC) == url


def test_reason_labels_never_echo_url_content() -> None:
    secret_url = "https://user:hunter2@example.test/private-path"
    with pytest.raises(UnsafeRemoteUrlError) as excinfo:
        validate_outbound_url(secret_url, resolver=PUBLIC)
    assert "hunter2" not in str(excinfo.value)
    assert "private-path" not in str(excinfo.value)
