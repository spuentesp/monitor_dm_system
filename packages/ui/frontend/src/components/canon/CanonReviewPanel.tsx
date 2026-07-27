"use client";

import { useCallback, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Gavel,
  Loader2,
  Package,
  Scroll,
  Shield,
  Sparkles,
  Users,
  XCircle,
  Zap,
} from "lucide-react";
import { canonApi } from "@/lib/api";
import type { ProposalItem, SceneReview, VerdictItem } from "@/lib/types";
import { CANON_KEYS } from "@/lib/query-keys";
import { getConfidenceTier } from "@/lib/confidence";
import { cn } from "@/lib/utils";

// ─── Constants ───────────────────────────────────────────────

const CHANGE_TYPE_CONFIG: Record<string, { label: string; icon: React.ElementType; color: string }> = {
  entity: { label: "Entity", icon: Users, color: "text-blue-400" },
  fact: { label: "Fact", icon: Scroll, color: "text-purple-400" },
  relationship: { label: "Relationship", icon: Sparkles, color: "text-amber-400" },
  mechanic: { label: "Mechanic", icon: Zap, color: "text-emerald-400" },
  state_change: { label: "State Change", icon: Activity, color: "text-cyan-400" },
  event: { label: "Event", icon: CalendarClock, color: "text-rose-400" },
};

const STATUS_CONFIG: Record<string, { label: string; icon: React.ElementType; color: string; bg: string }> = {
  pending: { label: "Pending", icon: Clock, color: "text-amber-400", bg: "bg-amber-500/10 border-amber-500/20" },
  accepted: { label: "Accepted", icon: CheckCircle2, color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/20" },
  rejected: { label: "Rejected", icon: XCircle, color: "text-red-400", bg: "bg-red-500/10 border-red-500/20" },
};

// ─── Sub-components ──────────────────────────────────────────

function ProposalCard({
  proposal,
  onAccept,
  onReject,
  compact = false,
}: {
  proposal: ProposalItem;
  onAccept?: (id: string, reason: string) => void;
  onReject?: (id: string, reason: string) => void;
  compact?: boolean;
}) {
  const [reason, setReason] = useState("");
  const [showReason, setShowReason] = useState<"accept" | "reject" | null>(null);
  const typeConfig = CHANGE_TYPE_CONFIG[proposal.change_type] ?? CHANGE_TYPE_CONFIG.fact;
  const statusConfig = STATUS_CONFIG[proposal.status] ?? STATUS_CONFIG.pending;
  const tier = getConfidenceTier(proposal.confidence);
  const TypeIcon = typeConfig.icon;
  const StatusIcon = statusConfig.icon;

  const contentPreview = useMemo(() => {
    const c = proposal.content;
    if (c.name) return String(c.name);
    if (c.label) return String(c.label);
    if (c.text) return String(c.text).slice(0, 120);
    return JSON.stringify(c).slice(0, 120);
  }, [proposal.content]);

  if (compact && proposal.status !== "pending") return null;

  return (
    <div className={cn(
      "rounded-lg border p-3 space-y-2 transition-all",
      proposal.status === "pending" ? "border-amber-500/20 bg-amber-500/5" :
      proposal.status === "accepted" ? "border-emerald-500/20 bg-emerald-500/5" :
      "border-red-500/20 bg-red-500/5",
    )}>
      <div className="flex items-start gap-2">
        <TypeIcon className={cn("w-4 h-4 mt-0.5 shrink-0", typeConfig.color)} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-medium text-slate-200">{typeConfig.label}</span>
            <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full font-medium", tier.bg, tier.color)}>
              {tier.label} {Math.round(proposal.confidence * 100)}%
            </span>
            {proposal.status !== "pending" && (
              <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full border font-medium flex items-center gap-1", statusConfig.bg, statusConfig.color)}>
                <StatusIcon className="w-3 h-3" />
                {statusConfig.label}
              </span>
            )}
          </div>
          <p className="text-sm text-slate-300 mt-1 break-words">{contentPreview}</p>
          {proposal.proposer && (
            <p className="text-[10px] text-slate-500 mt-1">Proposed by: {proposal.proposer}</p>
          )}
        </div>
      </div>

      {proposal.status === "pending" && onAccept && onReject && (
        <div className="space-y-2">
          <AnimatePresence>
            {showReason && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <input
                  type="text"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder={`Reason for ${showReason}ing...`}
                  className="w-full px-2 py-1.5 text-xs rounded-lg bg-white/5 border border-white/10 text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-cyan-500/40"
                />
              </motion.div>
            )}
          </AnimatePresence>
          <div className="flex gap-2">
            <button
              onClick={() => {
                if (showReason === "accept") {
                  onAccept(proposal.proposal_id, reason.trim());
                  setShowReason(null);
                  setReason("");
                } else {
                  setShowReason("accept");
                }
              }}
              className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-lg bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/25 transition-all"
            >
              <CheckCircle2 className="w-3 h-3" />
              Accept
            </button>
            <button
              onClick={() => {
                if (showReason === "reject") {
                  onReject(proposal.proposal_id, reason.trim());
                  setShowReason(null);
                  setReason("");
                } else {
                  setShowReason("reject");
                }
              }}
              className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-lg bg-red-500/15 text-red-400 border border-red-500/30 hover:bg-red-500/25 transition-all"
            >
              <XCircle className="w-3 h-3" />
              Reject
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function SceneCard({
  scene,
  onAccept,
  onReject,
}: {
  scene: SceneReview;
  onAccept: (proposalId: string, reason: string) => void;
  onReject: (proposalId: string, reason: string) => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const [filter, setFilter] = useState<"all" | "pending" | "accepted" | "rejected">("pending");

  const filtered = useMemo(() => {
    const all = [...scene.pending, ...scene.accepted, ...scene.rejected];
    if (filter === "all") return all;
    return all.filter((p) => p.status === filter);
  }, [scene, filter]);

  // scene_id is null for the story-level lane (proposals with no scene).
  const isStoryLevel = scene.scene_id === null;

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-white/5 transition-colors"
      >
        {expanded ? <ChevronDown className="w-4 h-4 text-slate-500" /> : <ChevronRight className="w-4 h-4 text-slate-500" />}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-cyan-400" />
            <span className="text-sm font-medium text-slate-200">
              {isStoryLevel ? "Story-level" : "Scene"}
            </span>
            {!isStoryLevel && (
              <span className="text-[10px] font-mono text-slate-500">{scene.scene_id!.slice(0, 8)}</span>
            )}
            {isStoryLevel && (
              <span className="text-[10px] text-slate-500">not tied to a scene</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 text-[10px]">
          {scene.pending.length > 0 && (
            <span className="px-1.5 py-0.5 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/20">
              {scene.pending.length} pending
            </span>
          )}
          {scene.accepted.length > 0 && (
            <span className="px-1.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/20">
              {scene.accepted.length} accepted
            </span>
          )}
          {scene.rejected.length > 0 && (
            <span className="px-1.5 py-0.5 rounded-full bg-red-500/15 text-red-400 border border-red-500/20">
              {scene.rejected.length} rejected
            </span>
          )}
        </div>
      </button>

      {/* Body */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: "auto" }}
            exit={{ height: 0 }}
            className="overflow-hidden"
          >
            {/* Change type summary */}
            {Object.keys(scene.by_change_type).length > 0 && (
              <div className="px-4 py-2 border-t border-white/5 flex gap-3 flex-wrap">
                {Object.entries(scene.by_change_type).map(([type, count]) => {
                  const cfg = CHANGE_TYPE_CONFIG[type];
                  if (!cfg) return null;
                  const Icon = cfg.icon;
                  return (
                    <span key={type} className="flex items-center gap-1 text-[10px] text-slate-500">
                      <Icon className={cn("w-3 h-3", cfg.color)} />
                      {count} {cfg.label}
                    </span>
                  );
                })}
              </div>
            )}

            {/* Filter tabs */}
            <div className="px-4 py-2 border-t border-white/5 flex gap-1">
              {(["pending", "accepted", "rejected", "all"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={cn(
                    "px-2 py-1 text-[10px] font-medium rounded-md transition-all capitalize",
                    filter === f
                      ? "bg-cyan-500/15 text-cyan-400 border border-cyan-500/30"
                      : "text-slate-500 hover:text-slate-300 border border-transparent",
                  )}
                >
                  {f}
                </button>
              ))}
            </div>

            {/* Proposals */}
            <div className="px-4 py-2 space-y-2 max-h-96 overflow-y-auto">
              {filtered.length === 0 && (
                <p className="text-xs text-slate-600 text-center py-4">No {filter} proposals</p>
              )}
              {filtered.map((p) => (
                <ProposalCard
                  key={p.proposal_id}
                  proposal={p}
                  onAccept={onAccept}
                  onReject={onReject}
                />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────

interface CanonReviewPanelProps {
  /** Story ID to show the canon queue for. */
  storyId: string | null;
  /** Scene ID to show a single scene review. Takes priority over storyId. */
  sceneId?: string | null;
  /** Called when proposals change (accept/reject). */
  onProposalsChanged?: () => void;
  /** Whether to show in compact mode (for sidebar embedding). */
  compact?: boolean;
}

export function CanonReviewPanel({
  storyId,
  sceneId,
  onProposalsChanged,
  compact = false,
}: CanonReviewPanelProps) {
  const qc = useQueryClient();
  const [batchNotice, setBatchNotice] = useState<string | null>(null);

  // ── Queries ──────────────────────────────────────────────
  const storyQuery = useQuery({
    queryKey: [...CANON_KEYS.queue, storyId],
    queryFn: () => canonApi.storyQueue(storyId!, true),
    enabled: !!storyId && !sceneId,
    refetchInterval: 15_000,
  });

  const sceneQuery = useQuery({
    queryKey: CANON_KEYS.review(sceneId!),
    queryFn: () => canonApi.sceneReview(sceneId!),
    enabled: !!sceneId,
    refetchInterval: 10_000,
  });

  // ── Mutations ────────────────────────────────────────────
  const invalidate = useCallback(() => {
    qc.invalidateQueries({ queryKey: CANON_KEYS.queue });
    qc.invalidateQueries({ queryKey: ["canon-review"] });
    onProposalsChanged?.();
  }, [qc, onProposalsChanged]);

  const acceptMutation = useMutation({
    mutationFn: ({ proposalId, reason }: { proposalId: string; reason: string }) =>
      canonApi.acceptProposal(proposalId, reason || "Approved by GM"),
    onSuccess: invalidate,
  });

  const rejectMutation = useMutation({
    mutationFn: ({ proposalId, reason }: { proposalId: string; reason: string }) =>
      canonApi.rejectProposal(proposalId, reason || "Not suitable for canon"),
    onSuccess: invalidate,
  });

  const batchMutation = useMutation({
    mutationFn: (items: VerdictItem[]) => canonApi.batchVerdicts(items),
    onSuccess: (data) => {
      invalidate();
      // Per-item failures come back in the response — surface them instead
      // of claiming blanket success.
      setBatchNotice(
        data.errors.length > 0
          ? `${data.results.length} applied, ${data.errors.length} failed — ${data.errors[0].error}`
          : null,
      );
    },
    onError: (err) =>
      setBatchNotice(`Batch failed: ${err instanceof Error ? err.message : String(err)}`),
  });

  const handleAccept = useCallback(
    (proposalId: string, reason: string) => acceptMutation.mutate({ proposalId, reason }),
    [acceptMutation],
  );

  const handleReject = useCallback(
    (proposalId: string, reason: string) => rejectMutation.mutate({ proposalId, reason }),
    [rejectMutation],
  );

  // ── Batch actions (current scope only) ────────────────────
  const scopePending = useMemo<ProposalItem[]>(() => {
    if (sceneId) return sceneQuery.data?.pending ?? [];
    return storyQuery.data?.scenes.flatMap((s) => s.pending) ?? [];
  }, [sceneId, sceneQuery.data, storyQuery.data]);

  const applyToAllPending = useCallback(
    (decision: "accepted" | "rejected") => {
      if (scopePending.length === 0) return;
      setBatchNotice(null);
      batchMutation.mutate(
        scopePending.map((p) => ({
          proposal_id: p.proposal_id,
          decision,
          reason: decision === "accepted" ? "Batch approved by GM" : "Batch rejected by GM",
        })),
      );
    },
    [scopePending, batchMutation],
  );

  // ── Render ────────────────────────────────────────────────

  // Single scene mode
  if (sceneId) {
    const scene = sceneQuery.data;
    if (sceneQuery.isLoading) {
      return (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-5 h-5 text-cyan-400 animate-spin" />
        </div>
      );
    }
    if (sceneQuery.error || !scene) {
      return (
        <div className="text-center py-8 text-sm text-slate-500">
          <AlertTriangle className="w-5 h-5 mx-auto mb-2 text-amber-400" />
          Failed to load scene review
        </div>
      );
    }

    return (
      <div className={cn("space-y-3", compact && "text-sm")}>
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <Gavel className="w-4 h-4 text-cyan-400" />
            Canon Review
          </h3>
          {scene.pending.length > 0 && (
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => applyToAllPending("accepted")}
                disabled={batchMutation.isPending}
                className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium rounded-lg bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/25 transition-all disabled:opacity-50"
              >
                {batchMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3" />}
                Accept All ({scene.pending.length})
              </button>
              <button
                onClick={() => applyToAllPending("rejected")}
                disabled={batchMutation.isPending}
                className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium rounded-lg bg-red-500/15 text-red-400 border border-red-500/30 hover:bg-red-500/25 transition-all disabled:opacity-50"
              >
                {batchMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <XCircle className="w-3 h-3" />}
                Reject All
              </button>
            </div>
          )}
        </div>
        {batchNotice && (
          <p className="text-[10px] text-amber-400 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3 shrink-0" />
            {batchNotice}
          </p>
        )}
        <SceneCard scene={scene} onAccept={handleAccept} onReject={handleReject} />
      </div>
    );
  }

  // Story queue mode
  if (storyId) {
    const queue = storyQuery.data;
    if (storyQuery.isLoading) {
      return (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-5 h-5 text-cyan-400 animate-spin" />
        </div>
      );
    }
    if (storyQuery.error || !queue) {
      return (
        <div className="text-center py-8 text-sm text-slate-500">
          <AlertTriangle className="w-5 h-5 mx-auto mb-2 text-amber-400" />
          Failed to load canon queue
        </div>
      );
    }

    if (queue.scenes.length === 0) {
      return (
        <div className="text-center py-8 text-sm text-slate-500">
          <Shield className="w-6 h-6 mx-auto mb-2 text-slate-600" />
          No pending proposals
          <p className="text-[10px] text-slate-600 mt-1">All canon changes have been reviewed</p>
        </div>
      );
    }

    return (
      <div className={cn("space-y-3", compact && "text-sm")}>
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <Gavel className="w-4 h-4 text-cyan-400" />
            Canon Queue
            <span className="text-[10px] font-normal text-slate-500">
              {queue.total_pending} pending across {queue.scenes.length} lane{queue.scenes.length !== 1 ? "s" : ""}
            </span>
          </h3>
          {queue.total_pending > 0 && (
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => applyToAllPending("accepted")}
                disabled={batchMutation.isPending}
                className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium rounded-lg bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/25 transition-all disabled:opacity-50"
              >
                {batchMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3" />}
                Accept All ({queue.total_pending})
              </button>
              <button
                onClick={() => applyToAllPending("rejected")}
                disabled={batchMutation.isPending}
                className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium rounded-lg bg-red-500/15 text-red-400 border border-red-500/30 hover:bg-red-500/25 transition-all disabled:opacity-50"
              >
                {batchMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <XCircle className="w-3 h-3" />}
                Reject All
              </button>
            </div>
          )}
        </div>
        {batchNotice && (
          <p className="text-[10px] text-amber-400 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3 shrink-0" />
            {batchNotice}
          </p>
        )}
        <div className="space-y-2">
          {queue.scenes.map((scene) => (
            <SceneCard
              key={scene.scene_id ?? "story-level"}
              scene={scene}
              onAccept={handleAccept}
              onReject={handleReject}
            />
          ))}
        </div>
      </div>
    );
  }

  // No story or scene selected
  return (
    <div className="text-center py-8 text-sm text-slate-500">
      <Package className="w-6 h-6 mx-auto mb-2 text-slate-600" />
      Select a story to review canon proposals
    </div>
  );
}