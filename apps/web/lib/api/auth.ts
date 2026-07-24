import { apiClient, ApiError } from "./client";
import type { AuthSessionData } from "./schemas";

/**
 * Auth session surface over the canonical Task 3 routes. Only routes present
 * in the generated contract are consumed; login/register/logout mutations are
 * intentionally not wired into any UI yet (the login endpoint must stay
 * unexposed until P2-001 Postgres-backed login rate limiting lands).
 */
export const authSessionQueryKey = ["auth", "session"] as const;

export type SessionProbe =
  | { kind: "authenticated"; data: AuthSessionData }
  | { kind: "unauthenticated" };

/**
 * Reads the current session. A 401 is the canonical "reachable but no active
 * session" answer (SESSION_REVOKED_OR_EXPIRED) and is a valid probe result,
 * not an error; every other failure is surfaced as ApiError / network error so
 * TanStack Query can drive the offline state.
 */
export async function fetchSessionProbe(signal?: AbortSignal): Promise<SessionProbe> {
  const { data, response } = await apiClient.GET("/api/auth/session", { signal });
  if (response.status === 401) {
    return { kind: "unauthenticated" };
  }
  if (!response.ok || data === undefined) {
    throw new ApiError(
      `Session probe failed with status ${response.status}`,
      response.status,
      data,
    );
  }
  return { kind: "authenticated", data: data.data };
}

export function sessionProbeQueryOptions() {
  return {
    queryKey: authSessionQueryKey,
    queryFn: ({ signal }: { signal: AbortSignal }) => fetchSessionProbe(signal),
    staleTime: 15_000,
    refetchInterval: 30_000,
    retry: 1,
  } as const;
}

/**
 * Ensures the double-submit CSRF cookie exists before the first mutation.
 * The server sets the readable `decision_lab_csrf` cookie as a side effect;
 * the returned token is not persisted anywhere by the client.
 */
export async function ensureCsrfToken(signal?: AbortSignal): Promise<void> {
  const { data, response } = await apiClient.GET("/api/auth/csrf", { signal });
  if (!response.ok || data === undefined) {
    throw new ApiError(
      `CSRF token request failed with status ${response.status}`,
      response.status,
      data,
    );
  }
}
