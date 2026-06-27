"use client";

import { useQuery } from "@tanstack/react-query";
import { performanceApi } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Performance tab (T-038 — performance monitoring bridge). Live
 * snapshot of slow queries, alerts, and the latest health check.
 * Extracted from app/settings/page.tsx.
 */
export function PerformanceTab() {

  const overviewQ = useQuery({
    queryKey: ["performance", "overview"],
    queryFn: () => performanceApi.overview(),
    refetchInterval: 15_000,
  });
  const slowQ = useQuery({
    queryKey: ["performance", "slow"],
    queryFn: () => performanceApi.slowQueries(15),
    refetchInterval: 30_000,
  });
  const alertsQ = useQuery({
    queryKey: ["performance", "alerts"],
    queryFn: () => performanceApi.alerts({ limit: 15 }),
    refetchInterval: 30_000,
  });

  const o = overviewQ.data;

  return (
    <div className="space-y-8 max-w-5xl">
      <div>
        <h2 className="text-lg font-bold text-slate-100">Performance</h2>
        <p className="text-sm text-slate-500 mt-1">
          Query latency, slow operations and alert history.
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "Requests", value: o?.request_count ?? "—" },
          { label: "Avg latency", value: o ? `${o.avg_latency_ms.toFixed(0)} ms` : "—" },
          { label: "p95", value: o ? `${o.p95_ms.toFixed(0)} ms` : "—" },
          { label: "Slow queries", value: o?.slow_query_count ?? "—" },
        ].map((c) => (
          <div key={c.label} className="bg-zinc-900/60 border border-zinc-800 rounded-lg px-4 py-3">
            <div className="text-[10px] uppercase tracking-wide text-slate-500">{c.label}</div>
            <div className="text-xl font-bold text-slate-100 mt-1">{c.value}</div>
          </div>
        ))}
      </div>

      <div>
        <h3 className="text-sm font-bold text-slate-200 mb-2">Slow queries</h3>
        {(slowQ.data ?? []).length === 0 ? (
          <p className="text-xs text-slate-500">None recorded.</p>
        ) : (
          <div className="space-y-1">
            {(slowQ.data ?? []).map((q) => (
              <div
                key={q.query_id}
                className="flex items-center justify-between gap-4 bg-zinc-900/40 border border-zinc-800 rounded-lg px-4 py-2"
              >
                <span className="text-xs text-slate-400 truncate">{q.query_summary}</span>
                <span className="text-xs font-mono text-amber-400 flex-shrink-0">
                  {q.duration_ms.toFixed(0)} ms
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <h3 className="text-sm font-bold text-slate-200 mb-2">Alerts</h3>
        {(alertsQ.data ?? []).length === 0 ? (
          <p className="text-xs text-slate-500">No alerts.</p>
        ) : (
          <div className="space-y-1">
            {(alertsQ.data ?? []).map((a) => (
              <div
                key={a.alert_id}
                className="flex items-center justify-between gap-4 bg-zinc-900/40 border border-zinc-800 rounded-lg px-4 py-2"
              >
                <span className="text-xs text-slate-400 truncate">{a.message}</span>
                <span
                  className={
                    a.severity === "critical"
                      ? "text-xs text-red-400"
                      : a.severity === "warning"
                        ? "text-xs text-amber-400"
                        : "text-xs text-slate-500"
                  }
                >
                  {a.severity}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
