"use client";

import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { NotificationProvider, useNotify } from "./NotificationProvider";
import { WorldContextProvider } from "@/lib/world-context";

function QueryClientWithNotify({ children }: { children: React.ReactNode }) {
  const { notify } = useNotify();
  
  const [queryClient] = useState(() => {
    // One toast per distinct error message per 30s window — a failing poll
    // must not flood the console/notifications (T-051).
    const recent = new Map<string, number>();
    const shouldNotify = (msg: string) => {
      const now = Date.now();
      const last = recent.get(msg) ?? 0;
      if (now - last < 30_000) return false;
      recent.set(msg, now);
      return true;
    };
    const isClientError = (error: unknown) =>
      /\b4\d\d\b|not found|Not Found/i.test(String((error as Error)?.message ?? ""));

    return new QueryClient({
      queryCache: new QueryCache({
        onError: (error) => {
          const msg = (error as Error).message || "An unexpected error occurred.";
          // 404s are an expected state for fresh/empty resources — panels
          // render their own empty states; don't toast them.
          if (isClientError(error)) return;
          if (shouldNotify(msg)) notify("error", msg);
        },
      }),
      defaultOptions: {
        queries: {
          staleTime: 30_000,
          // Never retry client errors; one retry for transient failures.
          retry: (failureCount, error) =>
            !isClientError(error) && failureCount < 1,
        },
      },
    });
  });

  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <NotificationProvider>
      <QueryClientWithNotify>
        <WorldContextProvider>{children}</WorldContextProvider>
      </QueryClientWithNotify>
    </NotificationProvider>
  );
}
