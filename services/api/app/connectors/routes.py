"""BYOK connector management routes (AGENTS sections 8 + 12).

Relative router mounted under ``workspace_router``; every route re-checks the
``manage_connectors`` capability. The audited read-only catalog is fixed:
Exa (search), Tavily (search fallback), Firecrawl (fetch).

Security invariants enforced here:
- the plaintext key exists only inside one request handler frame;
- responses carry the display mask only, never the key;
- a missing CONNECTOR_MASTER_KEY answers 503 for writes and keeps reads
  working (catalog + masked list stay visible).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.crypto import (
    ConnectorCryptoError,
    crypto_available,
    decrypt_secret,
    encrypt_secret,
)
from app.connectors.providers.base import ProviderFailure
from app.connectors.providers.ssrf import UnsafeRemoteUrlError, validate_outbound_url
from app.contracts.schemas import CanonicalModel
from app.db import get_session
from app.models import WorkspaceConnector
from app.security.csrf import require_csrf
from app.security.envelope import ApiFailure, workspace_not_found
from app.tenancy.context import WorkspaceContext, require_capability
from app.types import ConnectorStatus, WorkspaceCapability

router = APIRouter(tags=["connectors"])

# The audited catalog is a product decision, not user input.
CATALOG: dict[str, dict[str, str]] = {
    "exa": {"label": "Exa", "kind": "search", "hint": "默认网络检索"},
    "tavily": {"label": "Tavily", "kind": "search", "hint": "检索备用"},
    "firecrawl": {"label": "Firecrawl", "kind": "fetch", "hint": "网页抓取"},
    "model": {"label": "自定义模型", "kind": "model", "hint": "OpenAI-compatible endpoint"},
    "mcp": {"label": "MCP 工具服务器", "kind": "mcp", "hint": "HTTP/SSE MCP Server"},
}


class ConnectorUpsertRequest(CanonicalModel):
    provider: str
    api_key: str = ""  # optional for mcp with auth_type=none
    # model-specific fields
    base_url: str | None = None
    model_name: str | None = None
    # mcp-specific fields
    server_url: str | None = None
    server_name: str | None = None
    auth_type: str | None = None  # "none" | "bearer"


def _crypto_unavailable() -> ApiFailure:
    return ApiFailure(
        "CONNECTOR_CRYPTO_UNAVAILABLE",
        "\u8fde\u63a5\u5668\u52a0\u5bc6\u672a\u914d\u7f6e\uff08CONNECTOR_MASTER_KEY\uff09\uff0c\u6682\u65e0\u6cd5\u4fdd\u5b58 Key\u3002",
        http_status=503,
        retryable=False,
    )


def _unknown_provider() -> ApiFailure:
    return ApiFailure(
        "CONNECTOR_PROVIDER_UNKNOWN",
        "\u4e0d\u5728\u5ba1\u6838\u76ee\u5f55\u4e2d\u7684\u8fde\u63a5\u5668\u7c7b\u578b\u3002",
        http_status=422,
        retryable=False,
    )


def _connector_view(row: WorkspaceConnector) -> dict[str, Any]:
    meta = CATALOG.get(row.provider, {})
    view: dict[str, Any] = {
        "connectorId": str(row.id),
        "provider": row.provider,
        "label": meta.get("label", row.provider),
        "kind": meta.get("kind", ""),
        "mask": row.mask,
        "status": row.status,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
        "lastCheckedAt": row.last_checked_at.isoformat() if row.last_checked_at else None,
    }
    # Expose non-secret config fields for model/mcp
    if row.config:
        view["config"] = row.config
    return view


@router.get("/connectors/catalog")
async def get_catalog(
    context: WorkspaceContext = Depends(require_capability(WorkspaceCapability.MANAGE_CONNECTORS)),
) -> dict[str, Any]:
    """The fixed audited catalog + whether writes are currently possible."""

    return {
        "ok": True,
        "data": {
            "items": [
                {"provider": provider, **meta} for provider, meta in CATALOG.items()
            ],
            "writable": crypto_available(),
        },
    }


@router.get("/connectors")
async def list_connectors(
    context: WorkspaceContext = Depends(require_capability(WorkspaceCapability.MANAGE_CONNECTORS)),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(WorkspaceConnector)
            .where(WorkspaceConnector.workspace_id == context.workspace_id)
            .order_by(WorkspaceConnector.provider)
        )
    ).scalars().all()
    return {"ok": True, "data": {"items": [_connector_view(row) for row in rows]}}


@router.post("/connectors", status_code=201, dependencies=[Depends(require_csrf)])
async def upsert_connector(
    body: ConnectorUpsertRequest,
    context: WorkspaceContext = Depends(require_capability(WorkspaceCapability.MANAGE_CONNECTORS)),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create or replace this workspace's key for one provider."""

    provider = body.provider.strip().lower()
    if provider not in CATALOG:
        raise _unknown_provider()
    if not crypto_available():
        raise _crypto_unavailable()
    
    # Validate provider-specific fields
    config_payload: dict[str, str] | None = None
    if provider == "model":
        if not body.base_url or not body.model_name:
            raise ApiFailure(
                "CONNECTOR_MODEL_FIELDS_REQUIRED",
                "自定义模型需要填写 base_url 和 model_name。",
                http_status=422, retryable=False,
            )
        try:
            # Save-time SSRF gate: refuse non-public endpoints up front instead
            # of discovering them on the first probe/request.
            validate_outbound_url(body.base_url)
        except UnsafeRemoteUrlError:
            raise ApiFailure(
                "CONNECTOR_URL_UNSAFE",
                "base_url 必须是公网 HTTPS/HTTP 地址，不能指向内网、回环或云元数据。",
                http_status=422, retryable=False,
            )
        config_payload = {"base_url": body.base_url.strip(), "model_name": body.model_name.strip()}
    elif provider == "mcp":
        if not body.server_url:
            raise ApiFailure(
                "CONNECTOR_MCP_URL_REQUIRED",
                "MCP 服务器需要填写 server_url。",
                http_status=422, retryable=False,
            )
        try:
            validate_outbound_url(body.server_url)
        except UnsafeRemoteUrlError:
            raise ApiFailure(
                "CONNECTOR_URL_UNSAFE",
                "server_url 必须是公网 HTTPS/HTTP 地址，不能指向内网、回环或云元数据。",
                http_status=422, retryable=False,
            )
        auth = (body.auth_type or "none").strip().lower()
        config_payload = {
            "url": body.server_url.strip(),
            "name": (body.server_name or "MCP Server").strip(),
            "auth_type": auth,
        }
    
    # For mcp with auth_type=none, api_key is optional (use placeholder)
    secret = body.api_key.strip() if body.api_key else ""
    if provider == "mcp" and config_payload and config_payload.get("auth_type") == "none":
        secret = secret or "__no_auth__"
    if not secret or len(secret) > 512:
        raise ApiFailure(
            "CONNECTOR_KEY_INVALID", "Key 为空或超长。", http_status=422, retryable=False
        )
    
    try:
        enc = encrypt_secret(secret, workspace_id=str(context.workspace_id), provider=provider)
    except ConnectorCryptoError:
        raise _crypto_unavailable()
    
    existing = (
        await db.execute(
            select(WorkspaceConnector).where(
                WorkspaceConnector.workspace_id == context.workspace_id,
                WorkspaceConnector.provider == provider,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.ciphertext = enc.ciphertext
        existing.nonce = enc.nonce
        existing.key_version = enc.key_version
        existing.mask = enc.mask
        existing.status = ConnectorStatus.AVAILABLE.value
        existing.last_checked_at = None
        existing.config = config_payload
        row = existing
    else:
        row = WorkspaceConnector(
            workspace_id=context.workspace_id,
            provider=provider,
            ciphertext=enc.ciphertext,
            nonce=enc.nonce,
            key_version=enc.key_version,
            mask=enc.mask,
            config=config_payload,
        )
        db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"ok": True, "data": _connector_view(row)}


@router.delete("/connectors/{connectorId}", dependencies=[Depends(require_csrf)])
async def delete_connector(
    connector_id: UUID = Path(alias="connectorId"),
    context: WorkspaceContext = Depends(require_capability(WorkspaceCapability.MANAGE_CONNECTORS)),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    result = await db.execute(
        delete(WorkspaceConnector).where(
            WorkspaceConnector.workspace_id == context.workspace_id,
            WorkspaceConnector.id == connector_id,
        )
    )
    if result.rowcount == 0:
        raise workspace_not_found()
    await db.commit()
    return {"ok": True, "data": {"deleted": True}}


@router.post("/connectors/{connectorId}/test", dependencies=[Depends(require_csrf)])
async def test_connector(
    connector_id: UUID = Path(alias="connectorId"),
    context: WorkspaceContext = Depends(require_capability(WorkspaceCapability.MANAGE_CONNECTORS)),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Probe the provider with the stored key; update + return the status."""

    row = (
        await db.execute(
            select(WorkspaceConnector).where(
                WorkspaceConnector.workspace_id == context.workspace_id,
                WorkspaceConnector.id == connector_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise workspace_not_found()
    if not crypto_available():
        raise _crypto_unavailable()

    try:
        plaintext = decrypt_secret(
            row.ciphertext, row.nonce, row.key_version,
            workspace_id=str(context.workspace_id), provider=row.provider,
        )
    except ConnectorCryptoError:
        row.status = ConnectorStatus.INVALID_CREDENTIALS.value
        row.last_checked_at = datetime.now(timezone.utc)
        await db.commit()
        return {"ok": True, "data": _connector_view(row)}

    status = await _probe_provider(row.provider, plaintext, config=row.config)
    row.status = status.value
    row.last_checked_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return {"ok": True, "data": _connector_view(row)}


async def _probe_provider(provider: str, api_key: str, config: dict | None = None) -> ConnectorStatus:
    """One cheap real call per provider; failures map to canonical statuses."""

    from app.connectors.providers.exa import ExaSearchProvider
    from app.connectors.providers.firecrawl import FirecrawlFetchProvider
    from app.connectors.providers.tavily import TavilySearchProvider

    try:
        if provider == "exa":
            outcome = await ExaSearchProvider(api_key=api_key).search("ping", limit=1)
        elif provider == "tavily":
            outcome = await TavilySearchProvider(api_key=api_key).search("ping", limit=1)
        elif provider == "firecrawl":
            outcome = await FirecrawlFetchProvider(api_key=api_key).fetch("https://example.com")
        elif provider == "model":
            return await _probe_model(api_key, config or {})
        elif provider == "mcp":
            return await _probe_mcp(config or {})
        else:
            return ConnectorStatus.DISABLED
    except Exception:
        return ConnectorStatus.PROVIDER_ERROR
    if isinstance(outcome, ProviderFailure):
        return outcome.status
    return ConnectorStatus.AVAILABLE


async def _probe_model(api_key: str, config: dict) -> ConnectorStatus:
    """Probe an OpenAI-compatible model endpoint with a minimal models list call."""
    import httpx

    base_url = config.get("base_url", "").rstrip("/")
    if not base_url:
        return ConnectorStatus.INVALID_CREDENTIALS
    try:
        # SSRF guard: base_url is user-supplied; refuse non-public targets
        # (loopback/private/link-local/metadata) before any request is made.
        validate_outbound_url(base_url)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code == 401:
                return ConnectorStatus.INVALID_CREDENTIALS
            if resp.status_code == 429:
                return ConnectorStatus.RATE_LIMITED
            if resp.status_code < 400:
                return ConnectorStatus.AVAILABLE
            return ConnectorStatus.PROVIDER_ERROR
    except Exception:
        # SSRF rejection and network failures share one opaque status: the
        # probe answer never reveals whether a target exists or why it failed.
        return ConnectorStatus.PROVIDER_ERROR


async def _probe_mcp(config: dict) -> ConnectorStatus:
    """Probe an MCP server by fetching its tool list via HTTP."""
    import httpx

    url = config.get("url", "").rstrip("/")
    if not url:
        return ConnectorStatus.INVALID_CREDENTIALS
    try:
        validate_outbound_url(url)
        async with httpx.AsyncClient(timeout=15) as client:
            # Try standard MCP initialize or health check
            resp = await client.get(url, headers={"Accept": "application/json"})
            if resp.status_code < 400:
                return ConnectorStatus.AVAILABLE
            return ConnectorStatus.PROVIDER_ERROR
    except Exception:
        return ConnectorStatus.PROVIDER_ERROR


@router.get("/connectors/{connectorId}/tools")
async def list_connector_tools(
    connector_id: UUID = Path(alias="connectorId"),
    context: WorkspaceContext = Depends(require_capability(WorkspaceCapability.MANAGE_CONNECTORS)),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Discover tools exposed by an MCP connector.

    Connects to the MCP server and fetches the tool list. Only works for
    provider='mcp' connectors.
    """
    import httpx

    row = (
        await db.execute(
            select(WorkspaceConnector).where(
                WorkspaceConnector.workspace_id == context.workspace_id,
                WorkspaceConnector.id == connector_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise workspace_not_found()
    if row.provider != "mcp":
        raise ApiFailure(
            "CONNECTOR_NOT_MCP",
            "\u53ea\u6709 MCP \u8fde\u63a5\u5668\u652f\u6301\u5de5\u5177\u53d1\u73b0\u3002",
            http_status=422,
            retryable=False,
        )
    config = row.config or {}
    url = config.get("url", "").rstrip("/")
    if not url:
        return {"ok": True, "data": {"items": []}}

    auth_type = config.get("auth_type", "none")
    headers: dict[str, str] = {"Accept": "application/json"}
    if auth_type == "bearer" and crypto_available():
        try:
            token = decrypt_secret(
                row.ciphertext, row.nonce, row.key_version,
                workspace_id=str(context.workspace_id), provider="mcp",
            )
            if token and token != "__no_auth__":
                headers["Authorization"] = f"Bearer {token}"
        except Exception:
            pass

    try:
        # SSRF guard: the MCP server URL is user-supplied; refuse non-public
        # targets (loopback/private/link-local/metadata) before any request.
        validate_outbound_url(url)
        async with httpx.AsyncClient(timeout=15) as client:
            # Attempt to list tools from the MCP server via a GET to a tools endpoint
            resp = await client.get(f"{url}/tools", headers=headers)
            if resp.status_code < 400:
                body = resp.json()
                # Normalize: server may return {tools: [...]} or {items: [...]} or [...]
                if isinstance(body, list):
                    tools = body
                elif isinstance(body, dict):
                    tools = body.get("tools") or body.get("items") or []
                else:
                    tools = []
                items = [
                    {
                        "name": t.get("name", ""),
                        "description": t.get("description", ""),
                        "inputSchema": t.get("inputSchema") or t.get("input_schema"),
                    }
                    for t in tools
                    if isinstance(t, dict)
                ]
                return {"ok": True, "data": {"items": items}}
            # Opaque status only: the caller never learns host details, TLS
            # quirks or internal error text from the provider.
            return {"ok": True, "data": {"items": [], "error": f"provider_error_{resp.status_code}"}}
    except Exception:
        return {"ok": True, "data": {"items": [], "error": "provider_unreachable"}}
