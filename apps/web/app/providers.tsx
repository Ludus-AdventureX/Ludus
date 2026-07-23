"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { makeQueryClient } from "@/lib/api";

/**
 * Client-side provider boundary. The QueryClient is created once per browser
 * session via lazy `useState` initialiser so it is never recreated on re-render
 * and never shared across server requests.
 */
export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(makeQueryClient);

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
