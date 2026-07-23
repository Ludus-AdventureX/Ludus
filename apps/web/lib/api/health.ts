import { apiClient, ApiError } from "./client";
import type { HealthResponse } from "./schemas";

/**
 * The `/health` endpoint is the only route currently exposed by the generated
 * contract, so it is the single real end-to-end signal the Web/UX slice can
 * wire today. It backs the session/connectivity bootstrap surface; business
 * queries (auth/session/case/charter/run) are intentionally absent until the
 * corresponding backend routes are frozen into the contract.
 */
export const healthQueryKey = ["system", "health"] as const;

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const { data, response } = await apiClient.GET("/health", { signal });
  if (!response.ok || data === undefined) {
    throw new ApiError(
      `Health check failed with status ${response.status}`,
      response.status,
      data,
    );
  }
  return data;
}

export function healthQueryOptions() {
  return {
    queryKey: healthQueryKey,
    queryFn: ({ signal }: { signal: AbortSignal }) => fetchHealth(signal),
    // Connectivity is cheap to re-check but should not hammer the API.
    staleTime: 15_000,
    refetchInterval: 30_000,
    retry: 1,
  } as const;
}
