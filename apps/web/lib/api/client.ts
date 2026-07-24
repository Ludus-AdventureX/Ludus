import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "@decision-lab/contracts";

/**
 * Single source of truth for the browser -> FastAPI transport.
 *
 * The client is typed exclusively from the generated `@decision-lab/contracts`
 * paths. Web/UX never hand-writes a parallel request/response DTO; when an
 * endpoint is missing from the generated surface it must be raised as a
 * CONTRACT_CHANGE_REQUEST / INTEGRATION_QUESTION rather than typed locally.
 */

/**
 * Base URL for the API. Empty string keeps requests same-origin so a Next.js
 * rewrite / reverse proxy can terminate them; an absolute origin can be
 * injected for split deployments. The value is a public build-time env var and
 * never carries a secret.
 */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

/**
 * Double-submit CSRF wiring, aligned with the canonical Task 3 auth contract
 * (services/api/app/auth/config.py): the server issues the token via
 * `GET /api/auth/csrf` as the readable `decision_lab_csrf` cookie, and every
 * cookie-authenticated mutation must echo it in the `X-CSRF-Token` header.
 */
export const CSRF_COOKIE_NAME = "decision_lab_csrf";
export const CSRF_HEADER_NAME = "X-CSRF-Token";

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const prefix = `${name}=`;
  for (const part of document.cookie.split(";")) {
    const trimmed = part.trim();
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length));
    }
  }
  return null;
}

const csrfMiddleware: Middleware = {
  onRequest({ request }) {
    if (SAFE_METHODS.has(request.method.toUpperCase())) {
      return request;
    }
    const token = readCookie(CSRF_COOKIE_NAME);
    if (token) {
      request.headers.set(CSRF_HEADER_NAME, token);
    }
    return request;
  },
};

/**
 * Shared typed client. `credentials: "include"` carries the revocable session
 * cookie on every request so the server can re-check session + membership +
 * capability at its own boundary.
 */
export const apiClient = createClient<paths>({
  baseUrl: API_BASE_URL,
  credentials: "include",
});

apiClient.use(csrfMiddleware);

/**
 * Transport-level failure raised when a typed request returns a non-2xx status
 * or an empty body. `body` carries the canonical failure envelope
 * `{ ok: false, error: { code, message, retryable, details? } }` when the
 * server produced one; it stays `unknown` because failure responses are not
 * part of the generated success types and must be narrowed at the call site.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}
