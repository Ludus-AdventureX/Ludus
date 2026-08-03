"""MCP tool invocation for the analysis worker's retrieval phase (Wave E).

Grey-goo §3 retrieval discipline applies to MCP results too: they enter the
same evidence funnel (TDD triple filter) as exa/firecrawl results. MCP tools
are workspace-scoped BYOK connectors (provider='mcp', config JSONB carries
command/args/env/timeout).

The MCP Python package is optional - if not installed, this module is a no-op
and logs a debug message. This mirrors hermes-agent's mcp_tool.py pattern.

Security: MCP results are bounded (max 10 results per tool call, max 2000
chars per result text) and MUST pass the evidence funnel before entering the
analysis pipeline. No MCP result bypasses the TDD triple filter.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

logger = logging.getLogger(__name__)

# Bounded MCP result size (security: prevent context flooding)
_MAX_MCP_RESULTS = 10
_MAX_MCP_RESULT_CHARS = 2000
_MCP_DEFAULT_TIMEOUT = 120


async def invoke_mcp_tools(
    config: Mapping[str, Any],
    *,
    query: str,
    tool_name: str | None = None,
) -> list[dict[str, Any]]:
    """Invoke MCP tools and return results in WebSource-compatible format.

    Args:
        config: MCP server config from WorkspaceConnector.config JSONB
            (command, args, env, timeout)
        query: The search query to pass to the MCP tool
        tool_name: Optional specific tool to invoke (default: auto-discover)

    Returns:
        List of dicts with keys: title, url, snippet, tier, source
        (compatible with WebSource format for the evidence funnel)
    """

    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        logger.debug("mcp package not installed; MCP retrieval disabled")
        return []

    command = str(config.get("command") or "")
    args = list(config.get("args") or [])
    env = dict(config.get("env") or {})
    timeout = int(config.get("timeout") or _MCP_DEFAULT_TIMEOUT)

    if not command:
        logger.warning("MCP connector config missing 'command'; skipping")
        return []

    results: list[dict[str, Any]] = []
    try:
        server_params = StdioServerParameters(
            command=command, args=args, env=env or None
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=timeout)
                # List available tools
                tools_response = await asyncio.wait_for(
                    session.list_tools(), timeout=timeout
                )
                available_tools = [
                    tool.name for tool in (tools_response.tools or [])
                ]
                if not available_tools:
                    logger.info("MCP server has no tools; skipping")
                    return []

                # Invoke the first tool (or specified tool) with the query
                target_tool = tool_name or available_tools[0]
                if target_tool not in available_tools:
                    logger.warning(
                        "MCP tool %s not found; available: %s",
                        target_tool, available_tools
                    )
                    return []

                # Call the tool with the query as input
                call_response = await asyncio.wait_for(
                    session.call_tool(
                        target_tool,
                        arguments={"query": query} if query else {},
                    ),
                    timeout=timeout,
                )

                # Parse the tool result
                if call_response.content:
                    for content_item in call_response.content[:_MAX_MCP_RESULTS]:
                        text = str(getattr(content_item, "text", ""))[:_MAX_MCP_RESULT_CHARS]
                        if text.strip():
                            results.append({
                                "title": f"MCP:{target_tool}",
                                "url": "",  # MCP results may not have URLs
                                "snippet": text,
                                "tier": "L6",  # Default to unverified; funnel will grade
                                "source": f"mcp:{target_tool}",
                            })

    except asyncio.TimeoutError:
        logger.warning("MCP tool invocation timed out after %ss", timeout)
    except Exception:
        logger.exception("MCP tool invocation failed")

    return results
