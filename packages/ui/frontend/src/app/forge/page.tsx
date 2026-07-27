"use client";

/**
 * Forge overview dashboard (F1-2).
 *
 * A fast, attention-first authoring front door: selected-world context, KPI
 * tiles, attention strip, jobs attention table, recent worlds/packs, review
 * signal and quick actions. Operational, not analytical — no charts, no
 * coverage scores, no proposal totals (no global endpoint; the review card
 * counts packs with status=review_pending only).
 *
 * Data: universes / packs / jobs / jobs-health are queried in parallel, each
 * card renders its own loading/error state so a single failing endpoint never
 * blanks the page. Jobs poll every 7s, health every 20s (chip-owned).
 *
 * Deep links: ?pack=<id> forwards to /forge/packs?pack=<id>, ?universe=<id>
 * forwards to /forge/worlds?universe=<id> (both sections own those views
 * since F1-1).
 */

import { Suspense, useEffect, useMemo } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  CircleSlash,
  ClipboardCheck,
  Compass,
  Globe2,
  Loader2,
  Package,
  PackageCheck,
  Plus,
  RotateCcw,
  Sparkles,
  Unlock,
  Upload,
} from "lucide-react";
import { ingestApi, jobsHealthApi, universesApi } from "@/lib/api";
import type { IngestJob, KnowledgePack, Universe } from "@/lib/types";
import { cn, formatRelativeTime, truncate } from "@/lib/utils";
import { FORGE_KEYS, UNIVERSE_KEYS } from "@/lib/query-keys";
import { useWorldContext } from "@/lib/world-context";
import { useNotify } from "@/components/NotificationProvider";
import { PipelineHealthChip } from "@/components/forge/PipelineHealthChip";
import { StatusBadge } from "@/components/forge/ingest/StatusBadge";
import { JobIcon } from "@/components/forge/ingest/JobIcon";
import { LIVE_JOB_STATUSES } from "@/components/forge/ingest/ingest-constants";

// Failed/blocked statuses that deserve attention. Broader than
// FAILED_JOB_STATUSES — includes the two statuses the health endpoint drops
// (failed_non_retryable) plus provider blocks.
const ATTENTION_FAILED_STATUSES = new Set([
  "failed",
  "error",
  "killed",
  "failed_non_retryable",
  "blocked_provider",
]);

const UUID_LIKE_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const isUuidLike = (v: string) => UUID_LIKE_RE.test(v);

const MAX_ATTENTION_JOBS = 5;
const MAX_RECENT = 4;

// ─── Small shared pieces ──────────────────────────────────────

function CardError({ label }: { label: string }) {
  return (
    <p className="flex items-center gap-1.5 text-[11px] text-red-300/90" role="alert">
      <AlertTriangle className="w-3 h-3" aria-hidden="true" />
      Couldn’t load {label}.
    </p>
  );
}

function CardLoading({ label }: { label: string }) {
  return (
    <p className="flex items-center gap-1.5 text-[11px] text-slate-500">
      <Loader2 className="w-3 h-3 animate-spin" aria-hidden="true" />
      Loading {label}…
    </p>
  );
}

function KpiTile({
  label,
  value,
  href,
  icon: Icon,
  tone,
  isLoading,
  isError,
}: {
  label: string;
  value: number | null;
  href: string;
  icon: React.ElementType;
  tone: "default" | "cyan" | "red";
  isLoading: boolean;
  isError: boolean;
}) {
  const toneCls =
    tone === "red" && (value ?? 0) > 0
      ? "text-red-300"
      : tone === "cyan" && (value ?? 0) > 0
        ? "text-cyan-300"
        : "text-slate-100";
  return (
    <Link
      href={href}
      data-testid={`kpi-${label.toLowerCase().replace(/\s+/g, "-")}`}
      className="card-glass rounded-xl border border-white/5 p-4 transition-colors hover:border-white/15 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-cyan-400/60"
    >
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-slate-500">
        <Icon className="w-3.5 h-3.5" aria-hidden="true" />
        {label}
      </div>
      {isError ? (
        <div className="mt-2"><CardError label={label.toLowerCase()} /></div>
      ) : isLoading ? (
        <p className="mt-2 text-xl font-bold text-slate-600">…</p>
      ) : (
        <p className={cn("mt-2 text-xl font-bold font-mono", toneCls)}>{value ?? 0}</p>
      )}
    </Link>
  );
}

function SectionHeader({ title, viewAllHref }: { title: string; viewAllHref?: string }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">{title}</h2>
      {viewAllHref && (
        <Link href={viewAllHref} className="text-[11px] text-cyan-400/80 hover:text-cyan-300 transition-colors">
          View all →
        </Link>
      )}
    </div>
  );
}

// ─── Jobs attention table (sub-task 4) ────────────────────────

function jobErrorText(job: IngestJob): string | null {
  return job.error || job.errors?.[0] || job.last_error?.message || null;
}

function JobsAttentionTable({
  jobs,
  staleIds,
  isLoading,
  isError,
}: {
  jobs: IngestJob[];
  staleIds: Set<string>;
  isLoading: boolean;
  isError: boolean;
}) {
  const queryClient = useQueryClient();
  const { notify } = useNotify();

  const retryJob = useMutation({
    mutationFn: (sourceId: string) => ingestApi.rescanSource(sourceId),
    onSuccess: () => {
      notify("info", "Re-queued for ingestion.");
      queryClient.invalidateQueries({ queryKey: FORGE_KEYS.jobs });
      queryClient.invalidateQueries({ queryKey: FORGE_KEYS.sources });
    },
    onError: (e: unknown) =>
      notify("error", e instanceof Error ? e.message : "Retry failed."),
  });

  const cancelJob = useMutation({
    mutationFn: (jobId: string) => ingestApi.cancelJob(jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: FORGE_KEYS.jobs }),
    onError: (e: unknown) =>
      notify("error", e instanceof Error ? e.message : "Cancel failed."),
  });

  const unlockQueue = useMutation({
    mutationFn: () => ingestApi.unlockQueue(),
    onSuccess: (r) => {
      notify(
        "info",
        `Queue unlocked (recovered ${r.recovered_jobs}, cleared ${r.cleared_pending + r.cleared_active}).`,
      );
      queryClient.invalidateQueries({ queryKey: FORGE_KEYS.jobs });
    },
    onError: (e: unknown) =>
      notify("error", e instanceof Error ? e.message : "Unlock failed."),
  });

  // Top jobs needing attention: live first, then failed — both newest first.
  const attentionJobs = useMemo(() => {
    const byNewest = (a: IngestJob, b: IngestJob) =>
      new Date(b.started_at ?? 0).getTime() - new Date(a.started_at ?? 0).getTime();
    const live = jobs.filter((j) => LIVE_JOB_STATUSES.has(j.status)).sort(byNewest);
    const failed = jobs.filter((j) => ATTENTION_FAILED_STATUSES.has(j.status)).sort(byNewest);
    return [...live, ...failed].slice(0, MAX_ATTENTION_JOBS);
  }, [jobs]);

  const hasAttention = attentionJobs.length > 0;

  return (
    <section aria-label="Jobs needing attention">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          Jobs needing attention
        </h2>
        <div className="flex items-center gap-3">
          {hasAttention && (
            <button
              onClick={() => unlockQueue.mutate()}
              disabled={unlockQueue.isPending}
              className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] text-slate-400 border border-white/8 hover:text-amber-300 hover:border-amber-500/25 transition-colors disabled:opacity-50"
              title="Clear a stuck queue lock and recover stranded jobs"
            >
              {unlockQueue.isPending ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <Unlock className="w-3 h-3" />
              )}
              Unlock queue
            </button>
          )}
          <Link href="/forge/ingest" className="text-[11px] text-cyan-400/80 hover:text-cyan-300 transition-colors">
            Ingest Studio →
          </Link>
        </div>
      </div>

      {isError ? (
        <div className="card-glass rounded-xl border border-white/5 p-4">
          <CardError label="ingestion jobs" />
        </div>
      ) : isLoading ? (
        <div className="card-glass rounded-xl border border-white/5 p-4">
          <CardLoading label="ingestion jobs" />
        </div>
      ) : !hasAttention ? (
        <div className="rounded-xl border border-dashed border-white/5 p-6 text-center">
          <p className="text-xs text-slate-600">Nothing running or broken right now.</p>
        </div>
      ) : (
        <div className="card-glass rounded-xl border border-white/5 overflow-x-auto">
          <table className="w-full text-left text-xs">
            <caption className="sr-only">
              Active and failed ingestion jobs, newest first
            </caption>
            <thead>
              <tr className="border-b border-white/5 text-[10px] uppercase tracking-wider text-slate-500">
                <th scope="col" className="px-3 py-2 font-medium">Source</th>
                <th scope="col" className="px-3 py-2 font-medium">Status</th>
                <th scope="col" className="px-3 py-2 font-medium">Stage</th>
                <th scope="col" className="px-3 py-2 font-medium w-28">Progress</th>
                <th scope="col" className="px-3 py-2 font-medium">Error</th>
                <th scope="col" className="px-3 py-2 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {attentionJobs.map((job) => {
                const isLive = LIVE_JOB_STATUSES.has(job.status);
                const isFailed = ATTENTION_FAILED_STATUSES.has(job.status);
                const isStale = staleIds.has(job.id);
                const errorText = isFailed ? jobErrorText(job) : null;

                return (
                  <tr
                    key={job.id}
                    data-testid={`attention-job-${job.id}`}
                    className={cn(
                      "border-b border-white/5 last:border-0 align-top",
                      isFailed && "bg-red-500/[0.04]",
                      isLive && !isStale && "bg-cyan-500/[0.03]",
                      isStale && "bg-amber-500/[0.04]",
                    )}
                  >
                    <td className="px-3 py-2.5 max-w-[180px]">
                      <div className="flex items-center gap-2">
                        <JobIcon status={job.status} className="w-3.5 h-3.5 flex-shrink-0" />
                        <span className="font-medium text-slate-200 truncate">
                          {job.source_title || "Untitled source"}
                        </span>
                      </div>
                      <div className="mt-0.5 text-[9px] text-slate-600 font-mono">
                        {isUuidLike(job.id) ? job.id.slice(0, 8) : "local"} ·{" "}
                        {formatRelativeTime(job.started_at)}
                      </div>
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <StatusBadge status={job.status} />
                      {isStale && (
                        <span className="ml-1 tag-dim text-[10px] px-1.5 py-0.5 rounded-full border bg-amber-500/10 border-amber-500/20 text-amber-300">
                          stale
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-slate-400 max-w-[120px] truncate">
                      {job.current_stage ?? "—"}
                    </td>
                    <td className="px-3 py-2.5">
                      {isLive ? (
                        <div
                          className="h-1.5 rounded-full bg-white/5 overflow-hidden"
                          role="progressbar"
                          aria-valuenow={Math.round(job.progress ?? 0)}
                          aria-valuemin={0}
                          aria-valuemax={100}
                          aria-label={`Progress for ${job.source_title || "job"}`}
                        >
                          <div
                            className="h-full bg-cyan-500 transition-all"
                            style={{ width: `${Math.min(100, Math.max(0, job.progress ?? 0))}%` }}
                          />
                        </div>
                      ) : (
                        <span className="text-slate-600">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 max-w-[220px]">
                      {errorText ? (
                        <span className="text-[11px] text-red-300/90 leading-snug line-clamp-2">
                          {truncate(errorText, 140)}
                        </span>
                      ) : (
                        <span className="text-slate-600">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center justify-end gap-1">
                        {isFailed && job.source_id && (
                          <button
                            onClick={() => retryJob.mutate(job.source_id)}
                            disabled={retryJob.isPending}
                            className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] text-cyan-300 border border-cyan-500/25 hover:bg-cyan-500/10 transition-colors disabled:opacity-50"
                            title="Re-run ingestion for this source"
                          >
                            {retryJob.isPending ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                              <RotateCcw className="w-3 h-3" />
                            )}
                            Re-run
                          </button>
                        )}
                        {isLive && isUuidLike(job.id) && (
                          <button
                            onClick={() => cancelJob.mutate(job.id)}
                            disabled={cancelJob.isPending}
                            className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] text-amber-300 border border-amber-500/25 hover:bg-amber-500/10 transition-colors disabled:opacity-50"
                            title="Cancel this job"
                          >
                            <CircleSlash className="w-3 h-3" />
                            Cancel
                          </button>
                        )}
                        {job.pack_id && (
                          <Link
                            href={`/forge/packs?pack=${encodeURIComponent(job.pack_id)}`}
                            className="p-1.5 rounded-lg text-slate-500 hover:text-cyan-400 hover:bg-white/5 transition-colors"
                            title="View result pack"
                          >
                            <PackageCheck className="w-3.5 h-3.5" />
                          </Link>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// ─── Dashboard ────────────────────────────────────────────────

function ForgeDashboard() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const world = useWorldContext();

  // Deep-link preservation (F1-1): ?pack= and ?universe= belong to the
  // canonical sections now — forward immediately.
  const packParam = searchParams.get("pack");
  const universeParam = searchParams.get("universe");
  useEffect(() => {
    if (packParam) {
      router.replace(`/forge/packs?pack=${encodeURIComponent(packParam)}`);
    } else if (universeParam) {
      router.replace(`/forge/worlds?universe=${encodeURIComponent(universeParam)}`);
    }
  }, [packParam, universeParam, router]);

  // Independent queries — each card renders its own loading/error state.
  const universesQuery = useQuery({
    queryKey: UNIVERSE_KEYS.universes(),
    queryFn: () => universesApi.listUniverses(),
    staleTime: 15_000,
  });
  const packsQuery = useQuery({
    queryKey: FORGE_KEYS.packs,
    queryFn: () => ingestApi.listPacks(),
    staleTime: 10_000,
  });
  const jobsQuery = useQuery({
    queryKey: FORGE_KEYS.jobs,
    queryFn: () => ingestApi.listJobs(),
    staleTime: 5_000,
    refetchInterval: 7_000, // spec: poll jobs every 5–10s
  });
  // Health is queried here (not only in the chip) to mark stale jobs in the
  // attention table; the chip owns the user-facing health states.
  const healthQuery = useQuery({
    queryKey: FORGE_KEYS.jobsHealth,
    queryFn: jobsHealthApi.health,
    staleTime: 10_000,
    refetchInterval: 20_000,
  });

  const universes: Universe[] = universesQuery.data ?? [];
  const packs: KnowledgePack[] = packsQuery.data ?? [];
  const jobs: IngestJob[] = jobsQuery.data ?? [];

  const liveCount = jobs.filter((j) => LIVE_JOB_STATUSES.has(j.status)).length;
  const failedCount = jobs.filter((j) => ATTENTION_FAILED_STATUSES.has(j.status)).length;
  const staleIds = useMemo(
    () => new Set((healthQuery.data?.stale ?? []).map((s) => s.job_id)),
    [healthQuery.data],
  );
  const reviewPacks = useMemo(
    () => packs.filter((p) => p.status === "review_pending"),
    [packs],
  );
  const attentionTotal = failedCount + staleIds.size + reviewPacks.length;

  const recentUniverses = useMemo(
    () =>
      [...universes]
        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
        .slice(0, MAX_RECENT),
    [universes],
  );
  const recentPacks = useMemo(
    () =>
      [...packs]
        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
        .slice(0, MAX_RECENT),
    [packs],
  );

  // "Open world" target: the selected world if it still exists, else newest.
  const selectedUniverse = universes.find((u) => u.id === world.universeId) ?? null;
  const openTarget = selectedUniverse ?? recentUniverses[0] ?? null;
  const selectedLabel =
    selectedUniverse?.name ?? world.universeLabel ?? null;

  return (
    <div className="h-full overflow-y-auto custom-scrollbar">
      <div className="max-w-5xl mx-auto px-8 py-8 space-y-8">
        {/* Header */}
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-slate-600">
              <Sparkles className="w-3.5 h-3.5 text-cyan-400" aria-hidden="true" />
              World Forge
            </div>
            <h1 className="text-2xl font-bold text-slate-100">Forge Overview</h1>
            <p className="text-sm text-slate-500 max-w-xl">
              What’s running, what’s broken, and what needs your call.
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <PipelineHealthChip />
            {world.universeId && (
              <div
                className="inline-flex items-center gap-1.5 rounded-full border border-purple-500/25 bg-purple-500/10 px-2.5 py-1 text-[10px] font-medium text-purple-300"
                title="Selected world — stored in this browser only"
                data-testid="selected-world-chip"
              >
                <Globe2 className="w-3 h-3" aria-hidden="true" />
                <span className="text-purple-400/70">Selected world:</span>
                <span>{selectedLabel ?? `${world.universeId.slice(0, 8)}…`}</span>
              </div>
            )}
          </div>
        </div>

        {/* KPI row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiTile
            label="Worlds"
            value={universesQuery.data ? universes.length : null}
            href="/forge/worlds"
            icon={Globe2}
            tone="default"
            isLoading={universesQuery.isLoading}
            isError={universesQuery.isError}
          />
          <KpiTile
            label="Packs"
            value={packsQuery.data ? packs.length : null}
            href="/forge/packs"
            icon={Package}
            tone="default"
            isLoading={packsQuery.isLoading}
            isError={packsQuery.isError}
          />
          <KpiTile
            label="Active jobs"
            value={jobsQuery.data ? liveCount : null}
            href="/forge/ingest"
            icon={Activity}
            tone="cyan"
            isLoading={jobsQuery.isLoading}
            isError={jobsQuery.isError}
          />
          <KpiTile
            label="Needs attention"
            value={jobsQuery.data || packsQuery.data ? attentionTotal : null}
            href="#attention"
            icon={AlertTriangle}
            tone="red"
            isLoading={jobsQuery.isLoading && packsQuery.isLoading}
            isError={false}
          />
        </div>

        {/* Attention strip */}
        {attentionTotal > 0 && (
          <div id="attention" className="flex flex-wrap gap-2" role="alert">
            {failedCount > 0 && (
              <Link
                href="/forge/ingest"
                className="flex items-center gap-1.5 rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-1.5 text-[11px] text-red-300 hover:bg-red-500/15 transition-colors"
              >
                <AlertTriangle className="w-3 h-3" aria-hidden="true" />
                {failedCount} failed ingest job{failedCount === 1 ? "" : "s"}
              </Link>
            )}
            {staleIds.size > 0 && (
              <Link
                href="/forge/ingest"
                className="flex items-center gap-1.5 rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-1.5 text-[11px] text-amber-300 hover:bg-amber-500/15 transition-colors"
              >
                <AlertTriangle className="w-3 h-3" aria-hidden="true" />
                {staleIds.size} stale job{staleIds.size === 1 ? "" : "s"} (no recent progress)
              </Link>
            )}
            {reviewPacks.length > 0 && (
              <Link
                href="/forge/review"
                className="flex items-center gap-1.5 rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-3 py-1.5 text-[11px] text-emerald-300 hover:bg-emerald-500/15 transition-colors"
              >
                <ClipboardCheck className="w-3 h-3" aria-hidden="true" />
                {reviewPacks.length} pack{reviewPacks.length === 1 ? "" : "s"} awaiting review
              </Link>
            )}
          </div>
        )}

        {/* Jobs attention table */}
        <JobsAttentionTable
          jobs={jobs}
          staleIds={staleIds}
          isLoading={jobsQuery.isLoading}
          isError={jobsQuery.isError}
        />

        {/* Recent worlds + packs */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <section aria-label="Recent worlds">
            <SectionHeader title="Recent worlds" viewAllHref="/forge/worlds" />
            {universesQuery.isError ? (
              <CardError label="worlds" />
            ) : universesQuery.isLoading ? (
              <CardLoading label="worlds" />
            ) : recentUniverses.length === 0 ? (
              <p className="text-xs text-slate-600 border border-dashed border-white/5 rounded-xl p-4 text-center">
                No worlds yet — create one from the Worlds section.
              </p>
            ) : (
              <ul className="space-y-2">
                {recentUniverses.map((u) => {
                  const isSelected = world.universeId === u.id;
                  return (
                    <li key={u.id}>
                      <Link
                        href={`/forge/worlds?universe=${encodeURIComponent(u.id)}`}
                        data-testid={`world-card-${u.id}`}
                        aria-current={isSelected ? "true" : undefined}
                        className={cn(
                          "flex items-center gap-3 rounded-xl border p-3 transition-colors card-glass",
                          isSelected
                            ? "border-purple-500/40 ring-1 ring-purple-500/25"
                            : "border-white/5 hover:border-white/15",
                        )}
                      >
                        <Globe2
                          className={cn("w-4 h-4 flex-shrink-0", isSelected ? "text-purple-400" : "text-slate-500")}
                          aria-hidden="true"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-semibold text-slate-200 truncate">{u.name}</span>
                            {isSelected && (
                              <span className="text-[9px] uppercase tracking-wider text-purple-300 bg-purple-500/10 border border-purple-500/25 rounded-full px-1.5 py-px">
                                Selected
                              </span>
                            )}
                          </div>
                          <p className="text-[10px] text-slate-500 mt-0.5">
                            {u.entity_count} entities · {u.genre ?? "no genre"}
                          </p>
                        </div>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section aria-label="Recent packs">
            <SectionHeader title="Recent packs" viewAllHref="/forge/packs" />
            {packsQuery.isError ? (
              <CardError label="packs" />
            ) : packsQuery.isLoading ? (
              <CardLoading label="packs" />
            ) : recentPacks.length === 0 ? (
              <p className="text-xs text-slate-600 border border-dashed border-white/5 rounded-xl p-4 text-center">
                No packs yet — ingest a source to build one.
              </p>
            ) : (
              <ul className="space-y-2">
                {recentPacks.map((p) => (
                  <li key={p.id}>
                    <Link
                      href={`/forge/packs?pack=${encodeURIComponent(p.id)}`}
                      data-testid={`pack-card-${p.id}`}
                      className="flex items-center gap-3 rounded-xl border border-white/5 p-3 transition-colors card-glass hover:border-white/15"
                    >
                      <Package className="w-4 h-4 flex-shrink-0 text-slate-500" aria-hidden="true" />
                      <div className="flex-1 min-w-0">
                        <span className="text-xs font-semibold text-slate-200 truncate block">{p.name}</span>
                        <p className="text-[10px] text-slate-500 mt-0.5">
                          <span
                            className={cn(
                              "inline-block w-1.5 h-1.5 rounded-full mr-1 align-middle",
                              p.status === "review_pending"
                                ? "bg-emerald-400"
                                : p.status === "error"
                                  ? "bg-red-400"
                                  : "bg-slate-500",
                            )}
                            aria-hidden="true"
                          />
                          {p.status} · {p.entity_count + p.axiom_count + p.lore_fact_count} items
                        </p>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        {/* Review + coverage */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <section aria-label="Packs awaiting review">
            <SectionHeader title="Packs awaiting review" viewAllHref="/forge/review" />
            {packsQuery.isError ? (
              <CardError label="review status" />
            ) : packsQuery.isLoading ? (
              <CardLoading label="review status" />
            ) : reviewPacks.length === 0 ? (
              <p className="text-xs text-slate-600 border border-dashed border-white/5 rounded-xl p-4 text-center">
                Nothing waiting on a human decision.
              </p>
            ) : (
              <ul className="space-y-2">
                {reviewPacks.slice(0, 3).map((p) => (
                  <li key={p.id}>
                    <Link
                      href={`/forge/review?pack=${encodeURIComponent(p.id)}`}
                      className="flex items-center gap-3 rounded-xl border border-emerald-500/20 bg-emerald-500/[0.04] p-3 transition-colors hover:border-emerald-500/40"
                    >
                      <ClipboardCheck className="w-4 h-4 flex-shrink-0 text-emerald-400" aria-hidden="true" />
                      <span className="text-xs font-semibold text-slate-200 truncate">{p.name}</span>
                    </Link>
                  </li>
                ))}
                {reviewPacks.length > 3 && (
                  <li className="text-[11px] text-slate-500 pl-1">
                    + {reviewPacks.length - 3} more in{" "}
                    <Link href="/forge/review" className="text-emerald-400/80 hover:text-emerald-300">
                      Canon Review
                    </Link>
                  </li>
                )}
              </ul>
            )}
          </section>

          <section aria-label="Coverage gaps">
            <SectionHeader title="Coverage gaps" />
            <Link
              href="/forge/architect"
              className="flex items-center gap-3 rounded-xl border border-white/5 p-4 transition-colors card-glass hover:border-purple-500/30"
            >
              <Compass className="w-5 h-5 flex-shrink-0 text-purple-400" aria-hidden="true" />
              <div>
                <p className="text-xs font-semibold text-slate-200">Find what’s missing</p>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Coverage and gap tracking live in the Architect workbench.
                </p>
              </div>
            </Link>
          </section>
        </div>

        {/* Quick actions */}
        <section aria-label="Quick actions">
          <SectionHeader title="Quick actions" />
          <div className="flex flex-wrap gap-2">
            <Link
              href="/forge/worlds/new"
              className="btn-cyber text-xs py-2"
              data-testid="action-new-world"
            >
              <Plus className="w-3.5 h-3.5" aria-hidden="true" />
              New world
            </Link>
            <Link href="/forge/ingest" className="btn-cyber text-xs py-2">
              <Upload className="w-3.5 h-3.5" aria-hidden="true" />
              Upload source
            </Link>
            <Link href="/forge/architect" className="btn-cyber text-xs py-2">
              <Compass className="w-3.5 h-3.5" aria-hidden="true" />
              Open Architect
            </Link>
            {openTarget ? (
              <Link
                href={`/forge/worlds?universe=${encodeURIComponent(openTarget.id)}`}
                className="btn-cyber text-xs py-2"
                data-testid="action-open-world"
              >
                <Globe2 className="w-3.5 h-3.5" aria-hidden="true" />
                Open {selectedUniverse ? "selected" : "newest"} world
                {openTarget.name ? `: ${truncate(openTarget.name, 24)}` : ""}
              </Link>
            ) : (
              <span
                className="btn-cyber text-xs py-2 opacity-40 cursor-not-allowed"
                aria-disabled="true"
                data-testid="action-open-world"
              >
                <Globe2 className="w-3.5 h-3.5" aria-hidden="true" />
                Open world
              </span>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

export default function ForgeOverviewPage() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-slate-500">Loading Forge…</div>}>
      <ForgeDashboard />
    </Suspense>
  );
}
