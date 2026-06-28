"use client";

/**
 * Proposal Review Page (I-4)
 *
 * Entry: /forge/review?pack=<pack_id>
 *
 * Flow:
 *  1. Load proposals for the pack
 *  2. Display grouped by type (entities, axioms, lore, relationships, mechanics)
 *  3. Accept/reject individual or batch
 *  4. "Commit to Canon" button commits all accepted proposals to Neo4j
 */

import { Suspense, useCallback, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Globe2,
  Layers,
  Loader2,
  Package,
  Scroll,
  Sparkles,
  Users,
  XCircle,
  Zap,
} from "lucide-react";
import { ingestApi } from "@/lib/api";
import { FORGE_KEYS } from "@/lib/query-keys";
import {
  ENTITY_TYPE_CONFIG,
} from "@/lib/forge";
import type { ProposalItem } from "@/lib/types";
import { cn } from "@/lib/utils";

// ─── Constants ───────────────────────────────────────────────

const PROPOSAL_TABS: Array<{
  id: string;
  label: string;
  icon: React.ElementType;
  changeTypes: string[];
}> = [
  { id: "entities", label: "Entities", icon: Users, changeTypes: ["entity"] },
  { id: "axioms", label: "Axioms", icon: Scroll, changeTypes: ["fact"] },
  { id: "lore", label: "Lore", icon: BookOpen, changeTypes: ["fact"] },
  { id: "relationships", label: "Relationships", icon: Globe2, changeTypes: ["relationship"] },
  { id: "mechanics", label: "Mechanics", icon: Layers, changeTypes: ["mechanic"] },
];

const CONFIDENCE_TIERS = {
  high: { min: 0.9, label: "High", color: "text-emerald-400", bg: "bg-emerald-500/20" },
  medium: { min: 0.7, label: "Medium", color: "text-amber-400", bg: "bg-amber-500/20" },
  low: { min: 0, label: "Low", color: "text-red-400", bg: "bg-red-500/20" },
};

function confidenceTier(v: number) {
  if (v >= 0.9) return CONFIDENCE_TIERS.high;
  if (v >= 0.7) return CONFIDENCE_TIERS.medium;
  return CONFIDENCE_TIERS.low;
}

// ─── Proposal Card ───────────────────────────────────────────

function ProposalCard({
  proposal,
  onAccept,
  onReject,
  isProcessing,
}: {
  proposal: ProposalItem;
  onAccept: () => void;
  onReject: () => void;
  isProcessing: boolean;
}) {
  const content = proposal.content;
  const tier = confidenceTier(proposal.confidence);
  const isEntity = proposal.change_type === "entity";
  const isFact = proposal.change_type === "fact";
  const isRelationship = proposal.change_type === "relationship";
  const isMechanic = proposal.change_type === "mechanic";

  // Derive display fields from content
  const name = (content.name as string) || (content.statement as string) || "Untitled";
  const description = (content.description as string) || "";
  const entityType = (content.entity_type as string) || "";
  const domain = (content.domain as string) || "";
  const statement = (content.statement as string) || "";
  const fromEntity = (content.from_entity as string) || "";
  const toEntity = (content.to_entity as string) || "";
  const relType = (content.rel_type as string) || "";

  const cfg = ENTITY_TYPE_CONFIG[entityType] ?? ENTITY_TYPE_CONFIG.concept;
  const Icon = isEntity ? cfg.icon : isFact ? Scroll : isRelationship ? Globe2 : Layers;

  const statusBadge = {
    pending: { label: "Pending", color: "tag-amber", icon: CircleDot },
    accepted: { label: "Accepted", color: "tag-cyan", icon: CheckCircle2 },
    rejected: { label: "Rejected", color: "tag-red", icon: XCircle },
  }[proposal.status];

  const StatusIcon = statusBadge?.icon ?? CircleDot;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -20 }}
      className={cn(
        "group flex gap-3 px-4 py-3 border-b border-border transition-colors",
        proposal.status === "accepted" && "bg-emerald-500/5",
        proposal.status === "rejected" && "bg-red-500/5 opacity-60",
        proposal.status === "pending" && "hover:bg-bg-hover",
      )}
    >
      {/* Icon */}
      <Icon className={cn("h-4 w-4 mt-0.5 shrink-0", isEntity ? cfg.color : "text-fg-secondary")} />

      {/* Content */}
      <div className="flex-1 min-w-0 space-y-1">
        <div className="flex items-center gap-2 flex-wrap">
          {/* Status badge */}
          <span className={cn("text-[10px] px-1.5 py-0.5 rounded border flex items-center gap-1", statusBadge?.color)}>
            <StatusIcon className="h-2.5 w-2.5" />
            {statusBadge?.label}
          </span>

          {/* Type badge */}
          {isEntity && (
            <span className={cn("text-[10px] px-1.5 py-0.5 rounded border", cfg.tag)}>
              {entityType}
            </span>
          )}
          {isFact && domain && (
            <span className="text-[10px] px-1.5 py-0.5 rounded border tag-dim">{domain}</span>
          )}
          {isRelationship && (
            <span className="text-[10px] px-1.5 py-0.5 rounded border tag-dim">{relType}</span>
          )}

          {/* Confidence */}
          <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full", tier.bg, tier.color)}>
            {Math.round(proposal.confidence * 100)}%
          </span>

          {/* Name */}
          <span className="font-semibold text-fg-primary text-sm truncate">{name}</span>
        </div>

        {/* Description / Statement */}
        {isEntity && description && (
          <p className="text-xs text-fg-secondary truncate">{description}</p>
        )}
        {isFact && statement && !isEntity && (
          <p className="text-xs text-fg-secondary line-clamp-2">{statement}</p>
        )}
        {isRelationship && fromEntity && toEntity && (
          <p className="text-xs text-fg-secondary">
            <span className="text-cyan-400">{fromEntity}</span>
            <ChevronRight className="inline h-3 w-3 mx-0.5" />
            <span className="text-purple-400">{relType}</span>
            <ChevronRight className="inline h-3 w-3 mx-0.5" />
            <span className="text-cyan-400">{toEntity}</span>
          </p>
        )}
      </div>

      {/* Actions */}
      {proposal.status === "pending" && (
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={onAccept}
            disabled={isProcessing}
            className={cn(
              "p-1.5 rounded transition-colors",
              "hover:bg-emerald-500/20 text-fg-muted hover:text-emerald-400",
              "disabled:opacity-40",
            )}
            title="Accept"
          >
            {isProcessing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
          </button>
          <button
            onClick={onReject}
            disabled={isProcessing}
            className={cn(
              "p-1.5 rounded transition-colors",
              "hover:bg-red-500/20 text-fg-muted hover:text-red-400",
              "disabled:opacity-40",
            )}
            title="Reject"
          >
            <XCircle className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
    </motion.div>
  );
}

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

// ─── Main Page ───────────────────────────────────────────────

function ReviewPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const packId = searchParams.get("pack");

  const [activeTab, setActiveTab] = useState("entities");
  const [processingId, setProcessingId] = useState<string | null>(null);

  // Fetch pack info
  const { data: pack, isLoading: packLoading } = useQuery({
    queryKey: FORGE_KEYS.pack(packId!),
    queryFn: () => ingestApi.getPack(packId!),
    enabled: !!packId,
    staleTime: 30000,
  });

  // Fetch proposals
  const { data: proposalsData, isLoading: proposalsLoading } = useQuery({
    queryKey: FORGE_KEYS.proposals(packId!),
    queryFn: () => ingestApi.listProposals(packId!, { per_page: 200 }),
    enabled: !!packId,
    staleTime: 10000,
  });

  const proposals = proposalsData?.proposals ?? [];
  const summary = proposalsData?.summary ?? { total: 0, pending: 0, accepted: 0, rejected: 0 };

  // Filter proposals by active tab
  const filteredProposals = useMemo(() => {
    const tab = PROPOSAL_TABS.find(t => t.id === activeTab);
    if (!tab) return proposals;
    // For axioms tab, filter content with domain; for lore, without domain
    if (tab.id === "axioms") {
      return proposals.filter(p => p.change_type === "fact" && (p.content.domain as string));
    }
    if (tab.id === "lore") {
      return proposals.filter(p => p.change_type === "fact" && !(p.content.domain as string));
    }
    return proposals.filter(p => tab.changeTypes.includes(p.change_type));
  }, [proposals, activeTab]);

  // Per-tab counts
  const tabCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const tab of PROPOSAL_TABS) {
      if (tab.id === "axioms") {
        counts[tab.id] = proposals.filter(p => p.change_type === "fact" && (p.content.domain as string)).length;
      } else if (tab.id === "lore") {
        counts[tab.id] = proposals.filter(p => p.change_type === "fact" && !(p.content.domain as string)).length;
      } else {
        counts[tab.id] = proposals.filter(p => tab.changeTypes.includes(p.change_type)).length;
      }
    }
    return counts;
  }, [proposals]);

  // Review mutation
  const reviewMutation = useMutation({
    mutationFn: ({ proposalId, action, reason }: { proposalId: string; action: "accept" | "reject"; reason?: string }) =>
      ingestApi.reviewProposal(proposalId, action, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: FORGE_KEYS.proposals(packId!) });
    },
  });

  // Batch review mutation
  const batchMutation = useMutation({
    mutationFn: (actions: Array<{ proposal_id: string; action: "accept" | "reject"; reason?: string }>) =>
      ingestApi.batchReview(actions),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: FORGE_KEYS.proposals(packId!) });
    },
  });

  // Commit mutation
  const commitMutation = useMutation({
    mutationFn: () => ingestApi.commitAccepted(packId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: FORGE_KEYS.proposals(packId!) });
      queryClient.invalidateQueries({ queryKey: FORGE_KEYS.pack(packId!) });
      queryClient.invalidateQueries({ queryKey: FORGE_KEYS.packs });
    },
  });

  // Handlers
  const handleReview = useCallback(
    (proposalId: string, action: "accept" | "reject") => {
      setProcessingId(proposalId);
      reviewMutation.mutate(
        { proposalId, action },
        { onSettled: () => setProcessingId(null) },
      );
    },
    [reviewMutation],
  );

  const handleBatchAccept = useCallback(() => {
    const pending = proposals.filter(p => p.status === "pending");
    if (pending.length === 0) return;
    batchMutation.mutate(
      pending.map(p => ({ proposal_id: p.proposal_id, action: "accept" as const, reason: "Batch accept" })),
    );
  }, [proposals, batchMutation]);

  const handleBatchReject = useCallback(() => {
    const pending = proposals.filter(p => p.status === "pending");
    if (pending.length === 0) return;
    batchMutation.mutate(
      pending.map(p => ({ proposal_id: p.proposal_id, action: "reject" as const, reason: "Batch reject" })),
    );
  }, [proposals, batchMutation]);

  const handleAcceptHighConfidence = useCallback(() => {
    const highConf = proposals.filter(p => p.status === "pending" && p.confidence >= 0.9);
    if (highConf.length === 0) return;
    batchMutation.mutate(
      highConf.map(p => ({ proposal_id: p.proposal_id, action: "accept" as const, reason: "High confidence auto-accept" })),
    );
  }, [proposals, batchMutation]);

  const handleCommit = useCallback(() => {
    commitMutation.mutate();
  }, [commitMutation]);

  const allReviewed = summary.pending === 0 && summary.total > 0;
  const hasAccepted = summary.accepted > 0;

  // ─── No pack selected ─────────────────────────────────────
  if (!packId) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 text-fg-muted">
        <Package className="h-12 w-12 opacity-30" />
        <p>Select a pack to review proposals</p>
        <button onClick={() => router.push("/forge")} className="btn-cyber px-4 py-2 text-sm">
          Back to Forge
        </button>
      </div>
    );
  }

  // ─── Loading ──────────────────────────────────────────────
  if (packLoading || proposalsLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
      </div>
    );
  }

  // ─── Main View ────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="shrink-0 border-b border-border px-6 py-4 space-y-3">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/forge")}
            className="p-1 rounded hover:bg-bg-hover text-fg-muted hover:text-fg-primary transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-bold text-fg-primary truncate">
              Review: {pack?.name ?? "Pack"}
            </h1>
            <p className="text-xs text-fg-muted">
              Review extracted content before committing to canon
            </p>
          </div>

          {/* Batch actions */}
          <div className="flex items-center gap-2">
            {summary.pending > 0 && (
              <>
                <button
                  onClick={handleAcceptHighConfidence}
                  disabled={batchMutation.isPending}
                  className="btn-ghost px-3 py-1.5 text-xs flex items-center gap-1.5"
                >
                  <Sparkles className="h-3 w-3" />
                  Accept High Conf
                </button>
                <button
                  onClick={handleBatchAccept}
                  disabled={batchMutation.isPending}
                  className="btn-ghost px-3 py-1.5 text-xs flex items-center gap-1.5 text-emerald-400"
                >
                  <Check className="h-3 w-3" />
                  Accept All
                </button>
                <button
                  onClick={handleBatchReject}
                  disabled={batchMutation.isPending}
                  className="btn-ghost px-3 py-1.5 text-xs flex items-center gap-1.5 text-red-400"
                >
                  <XCircle className="h-3 w-3" />
                  Reject All
                </button>
              </>
            )}
            {allReviewed && hasAccepted && (
              <button
                onClick={handleCommit}
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
            )}
          </div>
        </div>

        {/* Progress */}
        <ReviewProgress summary={summary} />
      </div>

      {/* Tabs */}
      <div className="shrink-0 flex border-b border-border px-6">
        {PROPOSAL_TABS.map(tab => {
          const count = tabCounts[tab.id] ?? 0;
          const TabIcon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium border-b-2 transition-colors",
                activeTab === tab.id
                  ? "border-accent-primary text-accent-primary"
                  : "border-transparent text-fg-muted hover:text-fg-secondary",
              )}
            >
              <TabIcon className="h-3.5 w-3.5" />
              {tab.label}
              {count > 0 && (
                <span className={cn(
                  "text-[10px] px-1.5 py-0.5 rounded-full",
                  activeTab === tab.id ? "bg-accent-primary/20" : "bg-bg-hover",
                )}>
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Proposal list */}
      <div className="flex-1 overflow-y-auto">
        {filteredProposals.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-fg-muted">
            <CheckCircle2 className="h-8 w-8 mb-2 opacity-30" />
            <p className="text-sm">No proposals in this category</p>
          </div>
        ) : (
          <AnimatePresence>
            {filteredProposals.map(proposal => (
              <ProposalCard
                key={proposal.proposal_id}
                proposal={proposal}
                onAccept={() => handleReview(proposal.proposal_id, "accept")}
                onReject={() => handleReview(proposal.proposal_id, "reject")}
                isProcessing={processingId === proposal.proposal_id}
              />
            ))}
          </AnimatePresence>
        )}
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
