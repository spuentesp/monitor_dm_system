"use client";

import { useQuery } from "@tanstack/react-query";
import { systemApi } from "../lib/api";

type BackendStatus = "checking" | "online" | "degraded" | "offline";

/**
 * Global connection status indicator. Shows a small pill in the sidebar
 * indicating whether the backend API is reachable and databases are healthy.
 *
 * - 🟢 Online: API healthy, all DBs connected
 * - 🟡 Degraded: API up but some DBs disconnected
 * - 🔴 Offline: API unreachable
 * - ⚪ Checking: Initial health check in progress
 */
export function ConnectionStatus() {
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["health"],
    queryFn: () => systemApi.getHealth(),
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  });

  let status: BackendStatus = "checking";
  let degradedDbs: string[] = [];

  if (isLoading) {
    status = "checking";
  } else if (error) {
    status = "offline";
  } else if (data) {
    if (data.status === "ok") {
      status = "online";
    } else {
      const down: string[] = [];
      if (data.components) {
        for (const [name, state] of Object.entries(data.components)) {
          if (state !== "online") down.push(name);
        }
      }
      status = down.length > 0 ? "degraded" : "online";
      degradedDbs = down;
    }
  }

  const config: Record<BackendStatus, { dot: string; label: string; pulse: boolean }> = {
    checking: { dot: "bg-slate-500", label: "Checking…", pulse: true },
    online: { dot: "bg-emerald-400", label: "Online", pulse: false },
    degraded: { dot: "bg-amber-400", label: "Degraded", pulse: true },
    offline: { dot: "bg-red-400", label: "Offline", pulse: true },
  };

  const { dot, label, pulse } = config[status];

  return (
    <button
      onClick={() => refetch()}
      className="flex items-center gap-2 px-2 py-1.5 rounded-lg text-[11px] text-slate-500 hover:bg-white/5 transition-all w-full"
      title={
        degradedDbs.length > 0
          ? `Degraded databases: ${degradedDbs.join(", ")}\nClick to recheck`
          : `Backend ${status}\nClick to recheck`
      }
    >
      <span className="relative flex h-2 w-2 shrink-0">
        {pulse && (
          <span
            className={`absolute inset-0 rounded-full ${dot} opacity-75 animate-ping`}
          />
        )}
        <span className={`relative inline-flex h-2 w-2 rounded-full ${dot}`} />
      </span>
      <span className="truncate">{label}</span>
    </button>
  );
}