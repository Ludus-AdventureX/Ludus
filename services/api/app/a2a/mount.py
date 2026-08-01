"""Conditional mounting of the A2A surface onto the canonical FastAPI app.

Mirrors the guest-alpha gating philosophy at mount time instead of request
time: when ``A2A_ENABLED`` is off, ``mount_a2a`` returns without touching the
app — zero routes, zero OpenAPI entries, zero probe surface, and the deployed
service behaves exactly as before (the switch-back guarantee).

When on, the official a2a-sdk wires:

* ``GET  /.well-known/agent-card.json`` — public Agent Card discovery;
* ``POST /a2a``                        — A2A JSON-RPC (message/send,
  message/stream via SSE, tasks/get, tasks/cancel), backed by an in-memory
  task store (tasks do not survive restarts; acceptable for review).
"""

from __future__ import annotations

from fastapi import FastAPI

from app.a2a.config import a2a_enabled, get_a2a_settings

A2A_RPC_PATH = "/a2a"
AGENT_CARD_PATH = "/.well-known/agent-card.json"


def mount_a2a(app: FastAPI) -> bool:
    """Mount A2A routes when enabled; report whether mounting happened."""

    if not a2a_enabled():
        return False

    # Imported lazily so a disabled deployment never even loads the SDK.
    from a2a.server.apps import A2AStarletteApplication
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.tasks import InMemoryTaskStore

    from app.a2a.agent_card import build_agent_card
    from app.a2a.executor import FiveLensAgentExecutor

    settings = get_a2a_settings()
    a2a_app = A2AStarletteApplication(
        agent_card=build_agent_card(settings),
        http_handler=DefaultRequestHandler(
            agent_executor=FiveLensAgentExecutor(),
            task_store=InMemoryTaskStore(),
        ),
    )
    a2a_app.add_routes_to_app(
        app,
        agent_card_url=AGENT_CARD_PATH,
        rpc_url=A2A_RPC_PATH,
    )
    return True
