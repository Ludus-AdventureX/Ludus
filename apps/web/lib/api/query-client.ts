import { QueryClient } from "@tanstack/react-query";

/**
 * Factory for the TanStack Query client. A factory (rather than a shared module
 * singleton) keeps server and client renders from leaking cache across requests
 * in the Next.js App Router; the browser instance is memoised once in the
 * Providers boundary.
 */
export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: 1,
        refetchOnWindowFocus: false,
      },
    },
  });
}
