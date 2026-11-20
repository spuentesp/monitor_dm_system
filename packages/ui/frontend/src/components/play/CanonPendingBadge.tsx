"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";

import { canonApi } from "@/lib/api";
import { CANON_KEYS } from "@/lib/query-keys";

/**
 * Inline canon-transparency badge (UX-6): shows when the session's story has
 * GM-proposed canon changes pending review, linking to the review panel at
 * /forge/review. Uses the existing GET /stories/{id}/canon-queue endpoint —
 * the same query CanonReviewPanel uses, so the caches stay shared.
 */
export function CanonPendingBadge({ storyId }: { storyId: string | null }) {
  const { data } = useQuery({
    queryKey: [...CANON_KEYS.queue, storyId],
    queryFn: () => canonApi.storyQueue(storyId!, true),
    enabled: !!storyId,
    refetchInterval: 30_000,
    staleTime: 10_000,
    retry: false,
  });

  const pending = data?.total_pending ?? 0;
  if (!storyId || pending <= 0) return null;

  return (
    <Link
      href="/forge/review"
      data-testid="canon-pending-badge"
      title="GM-proposed canon changes are waiting for review"
      className="flex items-center gap-1.5 whitespace-nowrap rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[10px] font-medium text-emerald-200 transition-colors hover:bg-emerald-500/20"
    >
      <ShieldCheck className="h-3 w-3" />
      {pending} canon change{pending === 1 ? "" : "s"} pending review
    </Link>
  );
}
