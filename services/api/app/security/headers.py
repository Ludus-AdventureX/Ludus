"""Security response headers for every API response (alpha gate).

``app.main`` previously mounted routers and error handlers only: no middleware
at all, so no response carried a single security header. AGENTS.md section 12
requires the hosted entry point to be HTTPS with configurable cookie/CORS/origin
policy, and section 14's security gate lists security response headers among the
things that must be covered. This is the smallest honest implementation of that
requirement.

What is set, and why each one matters for a browser-facing JSON + SSE API:

- ``X-Content-Type-Options: nosniff`` — a JSON error body must never be sniffed
  into something executable;
- ``X-Frame-Options: DENY`` and ``frame-ancestors 'none'`` — the API must not be
  framable, which also blocks clickjacking against any HTML it ever returns;
- ``Referrer-Policy: no-referrer`` — workspace and case ids live in URLs and must
  not leak to third parties through the Referer header;
- ``Cross-Origin-Opener-Policy: same-origin`` — isolates any opener;
- ``Cross-Origin-Resource-Policy: same-origin`` — the API is same-origin by
  design (the web app proxies ``/api``), so cross-origin reads are refused;
- ``Permissions-Policy`` — the API needs no device capabilities at all;
- ``Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`` — an
  API response should be able to load nothing;
- ``Strict-Transport-Security`` — only when explicitly enabled, because sending
  HSTS over plain-HTTP local development would poison the developer's browser
  for the whole domain.

Deliberately NOT done here: no CORS middleware. The deployment contract is a
single origin (the web container proxies ``/api`` to FastAPI), so adding
permissive CORS would widen the attack surface rather than close a gap. Cookie
policy stays where it already lives (``AuthSettings.cookie_secure``).

The middleware never rewrites a body, never touches status codes and adds no
per-request state, so streaming responses (SSE) pass through untouched: headers
are applied to the response object before the body is streamed.
"""

from __future__ import annotations

import os

from starlette.types import ASGIApp, Message, Receive, Scope, Send

HSTS_FLAG = "SECURITY_HSTS_ENABLED"
HSTS_VALUE = "max-age=31536000; includeSubDomains"

# Header name -> value. Applied only when the response does not already set the
# header, so a specific route can always be stricter.
BASE_HEADERS: dict[str, str] = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=(), usb=()",
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
}


def hsts_enabled(env: dict[str, str] | None = None) -> bool:
    """HSTS is opt-in: it must never be sent from a plain-HTTP dev server."""

    source = env if env is not None else os.environ
    return source.get(HSTS_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


class SecurityHeadersMiddleware:
    """Pure-ASGI middleware; adds headers without buffering the response body."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                present = {name.decode("latin-1").lower() for name, _ in headers}
                for name, value in BASE_HEADERS.items():
                    if name not in present:
                        headers.append((name.encode("latin-1"), value.encode("latin-1")))
                if hsts_enabled() and "strict-transport-security" not in present:
                    headers.append(
                        (b"strict-transport-security", HSTS_VALUE.encode("latin-1"))
                    )
            await send(message)

        await self._app(scope, receive, send_with_headers)
