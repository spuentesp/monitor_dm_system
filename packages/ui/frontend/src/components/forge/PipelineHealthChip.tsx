"use client";

/**
 * Pipeline health chip (F1-2 sub-task 5).
 *
 * Maps GET /api/jobs/health into a single glanceable status, mounted on the
 * Forge dashboard and the Ingest Studio header. States (in priority order):
 *   unreachable        — the endpoint itself failed (backend down/degraded)
 *   watchdog_disabled  — healthy-looking pipeline, but nothing auto-recovers
 *                        stale jobs; deliberately distinct from "healthy"
 *   watchdog_down      — enabled but not running
 *   stale              — running jobs with no recent progress
 *   attention          — failed and/or provider-blocked jobs present
 *   active             — work in flight, nothing wrong
 *   healthy            — idle and clean
 *
 * The chip only surfaces the 7 statuses the endpoint exposes plus the stale
 * list; it never derives "no jobs" from absent counts (6 statuses are
 * dropped server-side — see JobsHealthResponse).
 */

import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  PowerOff,
  WifiOff,
} from "lucide-react";
import { jobsHealthApi } from "@/lib/api";
import type { JobsHealthResponse } from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";
import { FORGE_KEYS } from "@/lib/query-keys";

export type PipelineHealthState =
  | "loading"
  | "unreachable"
  | "watchdog_disabled"
  | "watchdog_down"
  | "stale"
  | "attention"
  | "active"
  | "healthy";

export interface PipelineHealth {
  state: PipelineHealthState;
  /** Short chip label, e.g. "2 stale jobs". */
  label: string;
  /** Secondary detail line shown in the tooltip/next to the label. */
  detail: string;
}

export function derivePipelineHealth(
  data: JobsHealthResponse | undefined,
  isError: boolean,
  isLoading: boolean,
): PipelineHealth {
  if (isLoading) {
    return { state: "loading", label: "Checking pipeline…", detail: "Fetching /jobs/health" };
  }
  if (isError || !data) {
    return {
      state: "unreachable",
      label: "Health unreachable",
      detail: "The /jobs/health endpoint did not respond",
    };
  }

  const { watchdog, counts, stale } = data;

  if (!watchdog.enabled) {
    return {
      state: "watchdog_disabled",
      label: "Watchdog disabled",
      detail: "Stale jobs are not auto-recovered",
    };
  }
  if (!watchdog.is_running) {
    return {
      state: "watchdog_down",
      label: "Watchdog not running",
      detail: "Enabled, but no watchdog tick has run",
    };
  }
  if (stale.length > 0) {
    const worst = Math.max(...stale.map((s) => s.stale_for_min));
    return {
      state: "stale",
      label: `${stale.length} stale job${stale.length === 1 ? "" : "s"}`,
      detail: `No progress for ~${Math.round(worst)} min`,
    };
  }
  if (counts.failed > 0 || counts.blocked_provider > 0) {
    const parts: string[] = [];
    if (counts.failed > 0) parts.push(`${counts.failed} failed`);
    if (counts.blocked_provider > 0) parts.push(`${counts.blocked_provider} provider-blocked`);
    return {
      state: "attention",
      label: parts.join(" · "),
      detail: "Jobs need attention",
    };
  }
  if (counts.running > 0 || counts.pending > 0) {
    return {
      state: "active",
      label: "Pipeline active",
      detail: `${counts.running} running · ${counts.pending} queued`,
    };
  }
  return { state: "healthy", label: "Pipeline healthy", detail: "No active or failed jobs" };
}

const STATE_STYLE: Record<PipelineHealthState, { classes: string; Icon: React.ElementType; spin?: boolean }> = {
  loading:           { classes: "border-white/10 bg-white/5 text-slate-400",        Icon: Loader2, spin: true },
  unreachable:       { classes: "border-red-500/25 bg-red-500/10 text-red-300",     Icon: WifiOff },
  watchdog_disabled: { classes: "border-amber-500/25 bg-amber-500/10 text-amber-300", Icon: PowerOff },
  watchdog_down:     { classes: "border-amber-500/25 bg-amber-500/10 text-amber-300", Icon: AlertTriangle },
  stale:             { classes: "border-amber-500/25 bg-amber-500/10 text-amber-300", Icon: AlertTriangle },
  attention:         { classes: "border-red-500/25 bg-red-500/10 text-red-300",     Icon: AlertTriangle },
  active:            { classes: "border-cyan-500/25 bg-cyan-500/10 text-cyan-300",  Icon: Activity },
  healthy:           { classes: "border-emerald-500/25 bg-emerald-500/10 text-emerald-300", Icon: CheckCircle2 },
};

export function PipelineHealthChip({ className }: { className?: string }) {
  const { data, isError, isLoading } = useQuery({
    queryKey: FORGE_KEYS.jobsHealth,
    queryFn: jobsHealthApi.health,
    staleTime: 10_000,
    refetchInterval: 20_000, // spec: poll health every 15–30s
  });

  const health = derivePipelineHealth(data, isError, isLoading);
  const { classes, Icon, spin } = STATE_STYLE[health.state];

  return (
    <div
      role="status"
      data-testid="pipeline-health-chip"
      data-state={health.state}
      title={data ? `${health.detail} · checked ${formatRelativeTime(data.generated_at)}` : health.detail}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-medium",
        classes,
        className,
      )}
    >
      <Icon className={cn("w-3 h-3", spin && "animate-spin")} aria-hidden="true" />
      <span>{health.label}</span>
      {data && (
        <span className="opacity-60 font-normal">· {formatRelativeTime(data.generated_at)}</span>
      )}
    </div>
  );
}
