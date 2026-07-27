"use client";

/**
 * Unified Canon Review page (I-4, CF-8) — F2-3 triage workbench.
 *
 * Entry: /forge/review?pack=<pack_id> | ?job=<ingestion_job_id> | ?scope=story
 *
 * Three scopes share one workbench (components/forge/review/ReviewWorkbench)
 * with a shared filter bar, detail/provenance drawer, and selection + bulk
 * verdicts (including server-side "all matching" via the by-filter
 * preview/execute endpoint):
 *  1. Pack proposals — review pack-extracted content before commit.
 *  2. Ingestion jobs — proposals produced by an ingestion job (by-ingest
 *     queue); commit via POST /canon-review/by-ingest/{job_id}/commit.
 *     Deep link: ?job=<id>.
 *  3. Story / scene — the CF-8 story queue, including the story-level
 *     no-scene lane.
 *
 * Scope + filter state is mirrored to the URL query parameters so any
 * triage view is deep-linkable (lib/reviewItem.ts).
 */

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Inbox,
  Loader2,
  Package,
  Shield,
  Zap,
} from "lucide-react";
import { canonApi, ingestApi, storiesApi } from "@/lib/api";
import type { IngestJob } from "@/lib/types";
import type { ReviewFilters, ReviewScope } from "@/lib/reviewItem";
import {
  filtersFromParams,
  reviewParamsToSearch,
  scopeFromParams,
  toReviewItem,
} from "@/lib/reviewItem";
import { FORGE_KEYS } from "@/lib/query-keys";
import { ReviewWorkbench } from "@/components/forge/review/ReviewWorkbench";
import { cn } from "@/lib/utils";

// ─── Constants ───────────────────────────────────────────────

const SCOPE_TABS = [
  { id: "pack", label: "Pack proposals", icon: Package },
  { id: "ingest", label: "Ingestion jobs", icon: Inbox },
  { id: "story", label: "Story / scene", icon: Shield },
] as const;

// ─── Progress Bar ────────────────────────────────────────────

function ReviewProgress({ summary }: { summary: { total: number; pending: number; accepted: number; rejected: number } }) {
  if (summary.total === 0) return null;
  const acceptedPct = (summary.accepted / summary.total) * 100;
  const rejectedPct = (summary.rejected / summary.total) * 100;

  return (
    <div className="space-y-1">
      <div className="flex gap-3 text-[10px]">
        <span className="text-fg-secondary">
          <span className="text-emerald-400 font-bold">{summary.accepted}</span> accepted
        </span>
        <span className="text-fg-secondary">
          <span className="text-red-400 font-bold">{summary.rejected}</span> rejected
        </span>
        <span className="text-fg-secondary">
          <span className="text-amber-400 font-bold">{summary.pending}</span> pending
        </span>
        <span className="text-fg-muted">/ {summary.total}</span>
      </div>
      <div className="flex h-1.5 rounded-full overflow-hidden bg-bg-hover">
        <div className="bg-emerald-500 transition-all" style={{ width: `${acceptedPct}%` }} />
        <div className="bg-red-500 transition-all" style={{ width: `${rejectedPct}%` }} />
      </div>
    </div>
  );
}

// ─── Scope props ─────────────────────────────────────────────

interface ScopeProps {
  filters: ReviewFilters;
  onFiltersChange: (next: ReviewFilters) => void;
}

// ─── Scope: Pack proposals (I-4) ─────────────────────────────

function PackReviewScope({ packId, filters, onFiltersChange }: ScopeProps & { packId: string | null }) {
  const router = useRouter();
  const queryClient = useQueryClient();

  // Fetch pack info
  const { data: pack, isLoading: packLoading } = useQuery({
    queryKey: ["pack", packId],
    queryFn: () => ingestApi.getPack(packId!),
    enabled: !!packId,
    staleTime: 30000,
  });

  // Fetch proposals (page cap: 200 — "all matching" bulk verdicts are
  // resolved server-side via the by-filter endpoint, not this list).
  const proposalsQuery = useQuery({
    queryKey: ["proposals", packId],
    queryFn: () => ingestApi.listProposals(packId!, { per_page: 200 }),
    enabled: !!packId,
    staleTime: 10000,
  });

  const proposals = proposalsQuery.data?.proposals ?? [];
  const summary = proposalsQuery.data?.summary ?? { total: 0, pending: 0, accepted: 0, rejected: 0 };

  const items = useMemo(
    () => proposals.map((p) => toReviewItem(p, "pack", { packId })),
    [proposals, packId],
  );

  // Commit mutation
  const commitMutation = useMutation({
    mutationFn: () => ingestApi.commitAccepted(packId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["proposals", packId] });
      queryClient.invalidateQueries({ queryKey: ["pack", packId] });
      queryClient.invalidateQueries({ queryKey: ["forge-packs"] });
    },
  });

  const allReviewed = summary.pending === 0 && summary.total > 0;
  const hasAccepted = summary.accepted > 0;

  // ─── No pack selected ─────────────────────────────────────
  if (!packId) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 text-fg-muted">
        <Package className="h-12 w-12 opacity-30" />
        <p>Select a pack to review proposals</p>
        <button onClick={() => router.push("/forge/packs")} className="btn-cyber px-4 py-2 text-sm">
          Back to Packs
        </button>
      </div>
    );
  }

  return (
    <>
      {/* Pack header row */}
      <div className="shrink-0 border-b border-border px-6 py-3 space-y-3">
        <div className="flex-1 min-w-0">
          <h2 className="text-sm font-bold text-fg-primary truncate">
            Pack: {pack?.name ?? "…"}
          </h2>
          <p className="text-xs text-fg-muted">
            Review extracted content before committing to canon
          </p>
        </div>
        <ReviewProgress summary={summary} />
      </div>

      <div className="flex-1 min-h-0">
        <ReviewWorkbench
          items={items}
          isLoading={packLoading || proposalsQuery.isLoading}
          loadError={proposalsQuery.isError}
          emptyMessage="No proposals for this pack"
          filters={filters}
          onFiltersChange={onFiltersChange}
          byFilterBase={{ source: `knowledge_pack:${packId}` }}
          onChanged={() =>
            queryClient.invalidateQueries({ queryKey: ["proposals", packId] })
          }
          headerActions={
            allReviewed && hasAccepted ? (
              <button
                onClick={() => commitMutation.mutate()}
                disabled={commitMutation.isPending}
                className="btn-cyber px-4 py-1.5 text-xs flex items-center gap-1.5"
              >
                {commitMutation.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Zap className="h-3 w-3" />
                )}
                Commit {summary.accepted} to Canon
              </button>
            ) : undefined
          }
        />
      </div>

      {/* Commit result */}
      {commitMutation.isSuccess && (
        <div className="shrink-0 border-t border-emerald-500/30 bg-emerald-500/10 px-6 py-3 flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-emerald-400" />
          <span className="text-sm text-emerald-300">
            Committed {commitMutation.data?.committed ?? 0} proposals to canon
          </span>
          {commitMutation.data?.errors?.length > 0 && (
            <span className="text-xs text-amber-400">
              ({commitMutation.data.errors.length} errors)
            </span>
          )}
        </div>
      )}
      {commitMutation.isError && (
        <div className="shrink-0 border-t border-red-500/30 bg-red-500/10 px-6 py-3 flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-red-400" />
          <span className="text-sm text-red-300">
            Commit failed: {(commitMutation.error as Error).message}
          </span>
        </div>
      )}
    </>
  );
}

// ─── Scope: Ingestion jobs (F1-4 by-ingest) ──────────────────

function IngestJobsScope({ initialJobId, filters, onFiltersChange }: ScopeProps & { initialJobId: string | null }) {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(initialJobId);

  const jobsQuery = useQuery<IngestJob[]>({
    queryKey: FORGE_KEYS.jobs,
    queryFn: () => ingestApi.listJobs(),
    staleTime: 10000,
  });

  const reviewQuery = useQuery({
    queryKey: ["canon-review", "by-ingest", jobId],
    queryFn: () => canonApi.byIngest(jobId!),
    enabled: !!jobId,
  });

  const review = reviewQuery.data;
  const items = useMemo(
    () =>
      [...(review?.pending ?? []), ...(review?.accepted ?? []), ...(review?.rejected ?? [])].map(
        (p) => toReviewItem(p, "ingest", { jobId }),
      ),
    [review, jobId],
  );

  const commitMutation = useMutation({
    mutationFn: () => canonApi.commitByIngest(jobId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["canon-review", "by-ingest", jobId] });
    },
  });

  const jobs = jobsQuery.data ?? [];
  const pendingCount = review?.pending.length ?? 0;
  const acceptedCount = review?.accepted.length ?? 0;

  return (
    <>
      {/* Job picker */}
      <div className="shrink-0 border-b border-border px-6 py-3 flex items-center gap-3 flex-wrap">
        <label className="text-xs text-fg-muted shrink-0">Ingestion job</label>
        <select
          value={jobId ?? ""}
          onChange={(e) => setJobId(e.target.value || null)}
          aria-label="Ingestion job"
          className="flex-1 min-w-0 max-w-md px-2 py-1.5 text-xs rounded-lg bg-bg-hover border border-border text-fg-primary focus:outline-none focus:border-accent-primary"
        >
          <option value="">Select a job…</option>
          {jobs.map(job => (
            <option key={job.id} value={job.id}>
              {job.source_title} — {job.id.slice(0, 8)} ({job.status})
            </option>
          ))}
        </select>
      </div>

      {!jobId ? (
        <div className="flex-1 flex flex-col items-center justify-center py-16 text-fg-muted">
          <Inbox className="h-8 w-8 mb-2 opacity-30" />
          <p className="text-sm">Select an ingestion job to review its proposals</p>
        </div>
      ) : (
        <div className="flex-1 min-h-0">
          <ReviewWorkbench
            items={items}
            isLoading={reviewQuery.isLoading}
            loadError={!!reviewQuery.error}
            emptyMessage="No proposals for this job"
            filters={filters}
            onFiltersChange={onFiltersChange}
            byFilterBase={{ source: `ingestion_job:${jobId}` }}
            onChanged={() =>
              queryClient.invalidateQueries({ queryKey: ["canon-review", "by-ingest", jobId] })
            }
            headerActions={
              pendingCount === 0 && acceptedCount > 0 ? (
                <button
                  onClick={() => commitMutation.mutate()}
                  disabled={commitMutation.isPending}
                  className="btn-cyber px-4 py-1.5 text-xs flex items-center gap-1.5"
                >
                  {commitMutation.isPending ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Zap className="h-3 w-3" />
                  )}
                  Commit {acceptedCount} to Canon
                </button>
              ) : undefined
            }
          />
        </div>
      )}

      {/* Commit result */}
      {commitMutation.isSuccess && (
        <div className="shrink-0 border-t border-emerald-500/30 bg-emerald-500/10 px-6 py-3 flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-emerald-400" />
          <span className="text-sm text-emerald-300">
            Committed {commitMutation.data?.committed ?? 0} proposals to canon
          </span>
          {commitMutation.data?.errors?.length > 0 && (
            <span className="text-xs text-amber-400">
              ({commitMutation.data.errors.length} errors)
            </span>
          )}
        </div>
      )}
      {commitMutation.isError && (
        <div className="shrink-0 border-t border-red-500/30 bg-red-500/10 px-6 py-3 flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-red-400" />
          <span className="text-sm text-red-300">
            Commit failed: {(commitMutation.error as Error).message}
          </span>
        </div>
      )}
    </>
  );
}

// ─── Scope: Story / scene (CF-8 queue) ───────────────────────

function StoryScope({ filters, onFiltersChange }: ScopeProps) {
  const queryClient = useQueryClient();
  const [storyId, setStoryId] = useState<string | null>(null);

  const storiesQuery = useQuery({
    queryKey: ["stories", "review-picker"],
    queryFn: () => storiesApi.listStories({ limit: 100 }),
    staleTime: 30000,
  });

  // only_pending=false so the status filter can reach accepted/rejected
  // items too; the story-level no-scene lane arrives with scene_id=null.
  const queueQuery = useQuery({
    queryKey: ["canon-review", "story-queue", storyId],
    queryFn: () => canonApi.storyQueue(storyId!, false),
    enabled: !!storyId,
  });

  const items = useMemo(
    () =>
      (queueQuery.data?.scenes ?? []).flatMap((scene) =>
        [...scene.pending, ...scene.accepted, ...scene.rejected].map((p) =>
          toReviewItem(p, "story", { storyId }),
        ),
      ),
    [queueQuery.data, storyId],
  );

  const stories = storiesQuery.data?.stories ?? [];

  return (
    <>
      <div className="shrink-0 border-b border-border px-6 py-3 flex items-center gap-3">
        <label className="text-xs text-fg-muted shrink-0">Story</label>
        <select
          value={storyId ?? ""}
          onChange={(e) => setStoryId(e.target.value || null)}
          aria-label="Story"
          className="flex-1 min-w-0 max-w-md px-2 py-1.5 text-xs rounded-lg bg-bg-hover border border-border text-fg-primary focus:outline-none focus:border-accent-primary"
        >
          <option value="">Select a story…</option>
          {stories.map(story => (
            <option key={story.id} value={story.id}>
              {story.title} ({story.story_type})
            </option>
          ))}
        </select>
      </div>

      {!storyId ? (
        <div className="flex-1 flex flex-col items-center justify-center py-16 text-fg-muted">
          <Shield className="h-8 w-8 mb-2 opacity-30" />
          <p className="text-sm">Select a story to review canon proposals</p>
        </div>
      ) : (
        <div className="flex-1 min-h-0">
          <ReviewWorkbench
            items={items}
            isLoading={queueQuery.isLoading}
            loadError={!!queueQuery.error}
            emptyMessage="No proposals for this story"
            filters={filters}
            onFiltersChange={onFiltersChange}
            byFilterBase={{ story_id: storyId }}
            onChanged={() =>
              queryClient.invalidateQueries({ queryKey: ["canon-review", "story-queue", storyId] })
            }
          />
        </div>
      )}
    </>
  );
}

// ─── Main Page ───────────────────────────────────────────────

function ReviewPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const paramsString = searchParams.toString();
  const packId = searchParams.get("pack");
  const jobId = searchParams.get("job");

  // Local state initialized from the URL (deep links); every change writes
  // back to the URL so triage views are shareable. The effect re-syncs when
  // the URL changes externally (back/forward navigation).
  const [scope, setScope] = useState<ReviewScope>(() => scopeFromParams(searchParams));
  const [filters, setFilters] = useState<ReviewFilters>(() => filtersFromParams(searchParams));

  useEffect(() => {
    const params = new URLSearchParams(paramsString);
    setScope(scopeFromParams(params));
    setFilters(filtersFromParams(params));
  }, [paramsString]);

  const updateUrl = useCallback(
    (nextScope: ReviewScope, nextFilters: ReviewFilters) => {
      const params = reviewParamsToSearch(
        new URLSearchParams(paramsString),
        nextScope,
        nextFilters,
      );
      router.replace(`?${params.toString()}`);
    },
    [paramsString, router],
  );

  const handleScopeChange = useCallback(
    (next: ReviewScope) => {
      setScope(next);
      updateUrl(next, filters);
    },
    [filters, updateUrl],
  );

  const handleFiltersChange = useCallback(
    (next: ReviewFilters) => {
      setFilters(next);
      updateUrl(scope, next);
    },
    [scope, updateUrl],
  );

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="shrink-0 border-b border-border px-6 py-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/forge")}
            className="p-1 rounded hover:bg-bg-hover text-fg-muted hover:text-fg-primary transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-bold text-fg-primary truncate">Canon Review</h1>
            <p className="text-xs text-fg-muted">
              Review proposals from packs, ingestion jobs, and story scenes
            </p>
          </div>
        </div>
      </div>

      {/* Scope switcher */}
      <div className="shrink-0 flex border-b border-border px-6">
        {SCOPE_TABS.map(tab => {
          const TabIcon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => handleScopeChange(tab.id)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium border-b-2 transition-colors",
                scope === tab.id
                  ? "border-accent-primary text-accent-primary"
                  : "border-transparent text-fg-muted hover:text-fg-secondary",
              )}
            >
              <TabIcon className="h-3.5 w-3.5" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {scope === "pack" && (
        <PackReviewScope packId={packId} filters={filters} onFiltersChange={handleFiltersChange} />
      )}
      {scope === "ingest" && (
        <IngestJobsScope initialJobId={jobId} filters={filters} onFiltersChange={handleFiltersChange} />
      )}
      {scope === "story" && <StoryScope filters={filters} onFiltersChange={handleFiltersChange} />}
    </div>
  );
}

export default function ReviewPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center h-full">
          <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
        </div>
      }
    >
      <ReviewPageInner />
    </Suspense>
  );
}
