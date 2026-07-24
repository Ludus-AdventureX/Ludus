/**
 * Public entry point for the generated API client layer. Feature code imports
 * from `@/lib/api` only, never from `@decision-lab/contracts` directly, so the
 * generated-only boundary stays enforceable in one place.
 */
export { apiClient, ApiError, API_BASE_URL, CSRF_COOKIE_NAME, CSRF_HEADER_NAME } from "./client";
export { fetchHealth, healthQueryKey, healthQueryOptions } from "./health";
export {
  authSessionQueryKey,
  ensureCsrfToken,
  fetchSessionProbe,
  sessionProbeQueryOptions,
  type SessionProbe,
} from "./auth";
export { makeQueryClient } from "./query-client";
export type * from "./schemas";
