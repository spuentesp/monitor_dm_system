"use client";

import { QueryCache, QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { NotificationProvider, useNotify } from "./NotificationProvider";
import { PageSkeleton } from "./PageSkeleton";
import { WorldContextProvider } from "@/lib/world-context";
import { ApiError, authApi } from "@/lib/api";
import { sanitizeNextPath } from "@/lib/auth-errors";

/** Routes that are reachable without a session — never bounced to /login. */
const PUBLIC_PATH_PREFIXES = ["/login", "/forgot-password", "/reset-password"];

export function isPublicAuthPath(pathname: string): boolean {
  return PUBLIC_PATH_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

/** Redirects to /login?next=<current path> when the API says 401 (unless
 *  auth is disabled locally or we are on a public auth page), with a
 *  "session expired" toast when the user was signed in this SPA session. */
function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { notify } = useNotify();
  const publicPage = isPublicAuthPath(pathname);
  const { data, error, isLoading } = useQuery({
    queryKey: ["auth-me"],
    queryFn: authApi.me,
    retry: false,
    staleTime: 60_000,
  });
  const hadSession = !!data;
  const notifiedExpiryRef = useRef(false);

  useEffect(() => {
    if (publicPage) return;
    if (error instanceof ApiError && error.status === 401) {
      if (hadSession && !notifiedExpiryRef.current) {
        notifiedExpiryRef.current = true;
        notify("error", "Your session has expired. Please sign in again.");
      }
      const search = typeof window === "undefined" ? "" : window.location.search;
      const next = sanitizeNextPath(`${pathname}${search}`) ?? pathname;
      router.replace(`/login?next=${encodeURIComponent(next)}`);
      return;
    }
    notifiedExpiryRef.current = false;
  }, [error, publicPage, pathname, router, notify, hadSession]);

  if (publicPage) return <>{children}</>;
  // Skeleton while the session resolves, and while a 401 redirect is in
  // flight — never a blank screen.
  if (isLoading || (error instanceof ApiError && error.status === 401)) {
    return <PageSkeleton rows={5} />;
  }
  // auth_disabled local mode still returns 200 with a user — fine.
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
      error instanceof ApiError
        ? error.status >= 400 && error.status < 500
        : /\b4\d\d\b|not found|Not Found/i.test(String((error as Error)?.message ?? ""));

    return new QueryClient({
      queryCache: new QueryCache({
        onError: (error) => {
          // 401 is AuthGate's story: it redirects and toasts "session
          // expired" itself — don't also surface the raw response body.
          if (error instanceof ApiError && error.status === 401) return;
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
