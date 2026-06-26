"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Loader2,
  RotateCcw,
  Trash2,
  CircleSlash,
  PackageCheck,
  ChevronDown,
  ChevronUp,
  Unlock,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { ingestApi } from "@/lib/api";
import type { IngestJob } from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";
import { StatusBadge } from "./StatusBadge";
import { JobIcon } from "./JobIcon";
import { useRouter } from "next/navigation";
import { FAILED_JOB_STATUSES, LIVE_JOB_STATUSES, mergeJobsSafely } from "./ingest-constants";
import { FORGE_KEYS } from "@/lib/query-keys";
import { useNotify } from "@/components/NotificationProvider";

const UUID_LIKE_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isUuidLike(value: string): boolean {
  return UUID_LIKE_RE.test(value);
}

export function IngestionJobsList() {
  const router = useRouter();
  const queryClient = useQueryClient();
  // id → EventSource (the live stream we own)
  const sseRefs = useRef<Map<string, EventSource>>(new Map());
  // id → retry count for transient errors (cleared on a successful message)
  const retryRefs = useRef<Map<string, number>>(new Map());
  const [expandedJobId, setExpandedId] = useState<string | null>(null);

  const { data: jobs = [], isLoading } = useQuery<IngestJob[]>({
    queryKey: FORGE_KEYS.jobs,
    queryFn: async () => {
      const incoming = await ingestApi.listJobs();
      const prev = queryClient.getQueryData<IngestJob[]>(FORGE_KEYS.jobs);
      return mergeJobsSafely(prev, incoming);
    },
    staleTime: 5000,
    refetchInterval: 5000, // Background fallback
  });

  const activeJobIds = useMemo(
    () => jobs
      .filter((j) => LIVE_JOB_STATUSES.has(j.status) && isUuidLike(j.id))
      .map((j) => j.id)
      .sort()
      .join(","),
    [jobs],
  );

  /**
   * Open (or replace) the SSE for a given job id. Always closes the existing
   * ES first so that status flips (processing → completed → processing on
   * retry) don't leak the previous stream.
   */
  const openStream = useCallback(
    (id: string) => {
      const previous = sseRefs.current.get(id);
      if (previous) {
        previous.close();
        sseRefs.current.delete(id);
      }

      let es: EventSource;
      try {
        es = ingestApi.streamJob(id);
      } catch (err) {
        // Construction failed (network down, etc.) — let the next reconcile
        // or poll pick it up. Don't surface to the user: this is a dashboard,
        // not a blocking surface, and the 5 s poll will retry naturally.
        retryRefs.current.set(id, (retryRefs.current.get(id) ?? 0) + 1);
        // eslint-disable-next-line no-console
        console.warn(`[ingest] EventSource open failed for ${id}`, err);
        return;
      }
      sseRefs.current.set(id, es);
      retryRefs.current.set(id, 0);

      es.onmessage = (evt) => {
        let updated: IngestJob;
        try {
          updated = JSON.parse(evt.data);
        } catch (err) {
          // Don't swallow silently — leave a breadcrumb. A malformed message
          // usually means the server sent something other than an IngestJob.
          // eslint-disable-next-line no-console
          console.warn(`[ingest] malformed SSE payload for ${id}`, err);
          return;
        }
        retryRefs.current.set(id, 0);
        queryClient.setQueryData<IngestJob[]>(FORGE_KEYS.jobs, (prev) => {
          if (!prev) return prev;
          // Only update if the status is actually different or progress increased
          // to avoid jumping backwards due to polling race conditions
          const existing = prev.find(j => j.id === updated.id);
          if (existing && existing.status === updated.status && existing.progress >= updated.progress) {
            return prev;
          }
          return prev.map((j) => (j.id === updated.id ? updated : j));
        });

        if (!LIVE_JOB_STATUSES.has(updated.status)) {
          es.close();
          sseRefs.current.delete(id);
          retryRefs.current.delete(id);
          queryClient.invalidateQueries({ queryKey: FORGE_KEYS.jobs });
          queryClient.invalidateQueries({ queryKey: FORGE_KEYS.sources });
          queryClient.invalidateQueries({ queryKey: FORGE_KEYS.packs });
        }
      };

      es.onerror = () => {
        // Transient error (network blip, server restart). Close the broken
        // socket, then schedule a single retry — but only if the job is
        // still live AND we haven't retried too many times already.
        es.close();
        sseRefs.current.delete(id);
        const attempts = (retryRefs.current.get(id) ?? 0) + 1;
        retryRefs.current.set(id, attempts);
        if (attempts > 3) {
          // Give up — let the 5 s poll pick up state changes.
          retryRefs.current.delete(id);
          return;
        }
        // Reopen with a small backoff so we don't hammer a flapping server.
        const backoffMs = Math.min(1000 * 2 ** (attempts - 1), 8000);
        setTimeout(() => {
          // Re-check the job is still live before reopening.
          const current = queryClient.getQueryData<IngestJob[]>(FORGE_KEYS.jobs);
          const stillLive = current?.some(
            (j) => j.id === id && LIVE_JOB_STATUSES.has(j.status),
          );
          if (stillLive) openStream(id);
        }, backoffMs);
      };
    },
    [queryClient],
  );

  useEffect(() => {
    const activeIds = new Set(activeJobIds ? activeJobIds.split(",") : []);

    // Open new connections (openStream always replaces existing)
    for (const id of activeIds) {
      openStream(id);
    }

    // Close connections for jobs that are no longer active
    for (const [id, es] of Array.from(sseRefs.current.entries())) {
      if (!activeIds.has(id)) {
        es.close();
        sseRefs.current.delete(id);
        retryRefs.current.delete(id);
      }
    }
  }, [activeJobIds, openStream]);

  // Clean up all on unmount
  useEffect(() => {
    return () => {
      for (const es of sseRefs.current.values()) es.close();
      sseRefs.current.clear();
      retryRefs.current.clear();
    };
  }, []);

  const deleteJob = useMutation({
    mutationFn: (jobId: string) => ingestApi.deleteJob(jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: FORGE_KEYS.jobs }),
  });

  const cancelJob = useMutation({
    mutationFn: (jobId: string) => ingestApi.cancelJob(jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: FORGE_KEYS.jobs }),
  });

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

  const unlockQueue = useMutation({
    mutationFn: () => ingestApi.unlockQueue(),
    onSuccess: (r) => {
      notify("info", `Queue unlocked (recovered ${r.recovered_jobs}, cleared ${r.cleared_pending + r.cleared_active}).`);
      queryClient.invalidateQueries({ queryKey: FORGE_KEYS.jobs });
    },
    onError: (e: unknown) =>
      notify("error", e instanceof Error ? e.message : "Unlock failed."),
  });

  const purgeFailedJobs = useMutation({
    mutationFn: () => ingestApi.purgeFailedJobs(),
    onSuccess: (r) => {
      notify("info", `Purged ${r.deleted} failed job${r.deleted === 1 ? "" : "s"}.`);
      queryClient.invalidateQueries({ queryKey: FORGE_KEYS.jobs });
    },
    onError: (e: unknown) =>
      notify("error", e instanceof Error ? e.message : "Purge failed."),
  });

  const sortedJobs = useMemo(() => {
    return [...jobs].sort((a, b) => {
      // Running first
      const aLive = LIVE_JOB_STATUSES.has(a.status);
      const bLive = LIVE_JOB_STATUSES.has(b.status);
      if (aLive && !bLive) return -1;
      if (!aLive && bLive) return 1;
      // Then by start time
      return new Date(b.started_at ?? 0).getTime() - new Date(a.started_at ?? 0).getTime();
    });
  }, [jobs]);

  if (isLoading && jobs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-slate-500 gap-3">
        <Loader2 className="w-6 h-6 animate-spin" />
        <p className="text-xs">Loading activity…</p>
      </div>
    );
  }

  const failedCount = jobs.filter((j) => FAILED_JOB_STATUSES.has(j.status)).length;
  const hasLive = jobs.some((j) => LIVE_JOB_STATUSES.has(j.status));

  const toolbar = (failedCount > 0 || hasLive) && (
    <div className="flex items-center justify-end gap-2 pb-1">
      {failedCount > 0 && (
        <button
          onClick={() => purgeFailedJobs.mutate()}
          disabled={purgeFailedJobs.isPending}
          className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] text-slate-400 border border-white/8 hover:text-red-300 hover:border-red-500/25 transition-colors disabled:opacity-50"
          title="Delete all failed job logs"
        >
          <Trash2 className="w-3 h-3" /> Purge {failedCount} failed
        </button>
      )}
      <button
        onClick={() => unlockQueue.mutate()}
        disabled={unlockQueue.isPending}
        className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] text-slate-400 border border-white/8 hover:text-amber-300 hover:border-amber-500/25 transition-colors disabled:opacity-50"
        title="Clear a stuck queue lock and recover stranded jobs"
      >
        {unlockQueue.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Unlock className="w-3 h-3" />}
        Unlock queue
      </button>
    </div>
  );

  if (jobs.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-white/5 p-12 text-center text-slate-600">
        <p className="text-xs">No recent activity.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {toolbar}
      {sortedJobs.slice(0, 15).map((job) => {
        const isFailed = FAILED_JOB_STATUSES.has(job.status);
        // Failed jobs auto-expand (unless the user explicitly collapsed this one)
        // so the reason is visible without a click — no more buried errors.
        const isExpanded = expandedJobId === job.id || (isFailed && expandedJobId !== `-${job.id}`);
        const isLive = LIVE_JOB_STATUSES.has(job.status);
        const errorText = job.error || job.errors?.[0] || job.last_error || null;

        return (
          <div key={job.id} className={cn(
            "glass rounded-xl border transition-all overflow-hidden",
            isFailed ? "bg-red-500/[0.04] border-red-500/25"
              : isLive ? "bg-cyan-500/[0.03] border-cyan-500/20"
              : "border-white/5 bg-white/[0.01]"
          )}>
            <div className="p-3 flex items-center gap-3">
              <JobIcon status={job.status} className="w-4 h-4" />
              
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-slate-200 truncate">{job.source_title}</span>
                  <StatusBadge status={job.status} />
                </div>
                <div className="flex items-center gap-2 mt-0.5 text-[10px] text-slate-500">
                  <span className="uppercase tracking-tighter opacity-60 font-mono">{job.id.slice(0, 8)}</span>
                  <span>·</span>
                  <span>{formatRelativeTime(job.started_at)}</span>
                  {job.current_stage && (
                    <>
                      <span>·</span>
                      <span className={isFailed ? "text-red-400/80" : "text-cyan-400/80"}>
                        {isFailed ? `failed at ${job.current_stage}` : job.current_stage}
                      </span>
                    </>
                  )}
                </div>
                {/* Error visible on the row itself — not buried in the panel */}
                {isFailed && errorText && (
                  <p className="mt-1 text-[11px] text-red-300/90 leading-snug line-clamp-2">
                    {errorText}
                  </p>
                )}
              </div>

              <div className="flex items-center gap-1 self-start">
                {isFailed && job.source_id && (
                  <button
                    onClick={() => retryJob.mutate(job.source_id)}
                    disabled={retryJob.isPending}
                    className="flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] text-cyan-300 border border-cyan-500/25 hover:bg-cyan-500/10 transition-colors disabled:opacity-50"
                    title="Re-run ingestion for this source"
                  >
                    {retryJob.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <RotateCcw className="w-3 h-3" />}
                    Retry
                  </button>
                )}
                {job.pack_id && (
                  <button
                    onClick={() => router.push(`/forge?pack=${job.pack_id}`)}
                    className="p-1.5 rounded-lg text-slate-500 hover:text-cyan-400 hover:bg-white/5 transition-colors"
                    title="View Result"
                  >
                    <PackageCheck className="w-3.5 h-3.5" />
                  </button>
                )}
                {isLive && (
                  <button
                    onClick={() => cancelJob.mutate(job.id)}
                    disabled={cancelJob.isPending}
                    className="p-1.5 rounded-lg text-slate-500 hover:text-amber-400 hover:bg-white/5 transition-colors"
                    title="Cancel"
                  >
                    <CircleSlash className="w-3.5 h-3.5" />
                  </button>
                )}
                <button
                  onClick={() => deleteJob.mutate(job.id)}
                  disabled={deleteJob.isPending}
                  className="p-1.5 rounded-lg text-slate-600 hover:text-red-400 hover:bg-white/5 transition-colors"
                  title="Delete Log"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => setExpandedId(isExpanded ? `-${job.id}` : job.id)}
                  className="p-1.5 rounded-lg text-slate-500 hover:text-slate-200 transition-colors"
                >
                  {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                </button>
              </div>
            </div>

            {isLive && (
              <div className="px-3 pb-1">
                <div className="h-1 rounded-full bg-white/5 overflow-hidden">
                  <motion.div 
                    className="h-full bg-cyan-500" 
                    initial={{ width: 0 }}
                    animate={{ width: `${job.progress}%` }}
                    transition={{ type: "spring", bounce: 0, duration: 0.5 }}
                  />
                </div>
              </div>
            )}

            <AnimatePresence>
              {isExpanded && (
                <motion.div
                  initial={{ height: 0 }}
                  animate={{ height: "auto" }}
                  exit={{ height: 0 }}
                  className="overflow-hidden bg-black/20 border-t border-white/5"
                >
                  <div className="p-3 space-y-3">
                    <div className="grid grid-cols-4 gap-2 text-center">
                      {[
                        ["Snippets", job.snippet_count, "text-cyan-400"],
                        ["Entities", job.entities_extracted, "text-purple-400"],
                        ["Axioms", job.axioms_extracted, "text-amber-400"],
                        ["Proposals", job.proposals_generated, "text-emerald-400"],
                      ].map(([label, val, color]) => (
                        <div key={label} className="bg-white/2 rounded-lg py-1.5">
                          <p className="text-[9px] text-slate-500 uppercase tracking-tighter">{label}</p>
                          <p className={cn("text-xs font-bold font-mono", color)}>{val}</p>
                        </div>
                      ))}
                    </div>

                    {job.activity_log.length > 0 && (
                      <div className="space-y-1 max-h-32 overflow-y-auto pr-1 custom-scrollbar">
                        {job.activity_log.map((line, idx) => (
                          <div key={idx} className="text-[10px] text-slate-400 flex gap-2">
                            <span className="text-slate-600 flex-shrink-0">•</span>
                            <span className="break-words">{line}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {job.error && (
                      <div className="p-2 rounded bg-red-500/10 border border-red-500/20 text-[10px] text-red-300 font-mono italic">
                        {job.error}
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}
