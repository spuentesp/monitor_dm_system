"use client";

import { QueryCache, QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { NotificationProvider, useNotify } from "./NotificationProvider";
import { WorldContextProvider } from "@/lib/world-context";
import { ApiError, authApi } from "@/lib/api";

/** Redirects to /login when the API says 401 (unless auth is disabled locally
 *  or we are already on the login page). */
function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const onLoginPage = pathname.startsWith("/login");
  const { data, error, isLoading } = useQuery({
    queryKey: ["auth-me"],
    queryFn: authApi.me,
    retry: false,
    staleTime: 60_000,
  });
  useEffect(() => {
    if (onLoginPage) return;
    if (error instanceof ApiError && error.status === 401) {
      router.push("/login");
    }
  }, [error, onLoginPage, router]);
  if (onLoginPage) return <>{children}</>;
  if (isLoading) return null;
  // auth_disabled local mode still returns 200 with a user — fine.
  if (error instanceof ApiError && error.status === 401) return null;
  return <>{children}</>;
}

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
        <WorldContextProvider>
          <AuthGate>{children}</AuthGate>
        </WorldContextProvider>
      </QueryClientWithNotify>
    </NotificationProvider>
  );
}
