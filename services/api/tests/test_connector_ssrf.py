"""SSRF enforcement on BYOK connector surfaces (2026-08-05 audit P2-2).

The connector probe paths and the connector-built model provider must refuse
non-public endpoints BEFORE any request leaves the process. These tests never
touch the network: a rejected URL fails at the guard, and a passing URL is not
exercised here (that is the providers' own behaviour).
"""

from __future__ import annotations

import pytest

from app.agents.model_provider import (
    ModelProviderConfigError,
    build_model_provider_from_connector,
)
from app.connectors.routes import _probe_mcp, _probe_model
from app.types import ConnectorStatus


async def test_probe_model_rejects_loopback_without_any_request() -> None:
    status = await _probe_model("sk-test", {"base_url": "http://127.0.0.1:9999"})
    assert status is ConnectorStatus.PROVIDER_ERROR


async def test_probe_model_rejects_cloud_metadata() -> None:
    status = await _probe_model(
        "sk-test", {"base_url": "http://169.254.169.254/latest/meta-data"}
    )
    assert status is ConnectorStatus.PROVIDER_ERROR


async def test_probe_mcp_rejects_private_target() -> None:
    status = await _probe_mcp({"url": "http://192.168.1.10:8080/mcp"})
    assert status is ConnectorStatus.PROVIDER_ERROR


async def test_probe_mcp_rejects_blocked_hostname() -> None:
    status = await _probe_mcp({"url": "http://localhost:3000/mcp"})
    assert status is ConnectorStatus.PROVIDER_ERROR


async def test_probe_mcp_rejects_non_http_scheme() -> None:
    status = await _probe_mcp({"url": "gopher://example.test/1"})
    assert status is ConnectorStatus.PROVIDER_ERROR


def test_build_provider_from_connector_refuses_private_target() -> None:
    with pytest.raises(ModelProviderConfigError):
        build_model_provider_from_connector(
            base_url="http://10.0.0.5:8000", api_key="k", model_name="m"
        )


def test_build_provider_from_connector_refuses_link_local() -> None:
    with pytest.raises(ModelProviderConfigError):
        build_model_provider_from_connector(
            base_url="http://[fe80::1]:8000", api_key="k", model_name="m"
        )
