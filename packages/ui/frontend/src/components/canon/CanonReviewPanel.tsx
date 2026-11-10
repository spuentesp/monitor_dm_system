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
  onDefer,
  onEdit,
  compact = false,
}: {
  proposal: ProposalItem;
  onAccept?: (id: string, reason: string) => void;
  onReject?: (id: string, reason: string) => void;
  onDefer?: (id: string, reason: string) => void;
  onEdit?: (id: string, contentPatch: Record<string, unknown>, reason: string) => void;
  compact?: boolean;
}) {
  const [reason, setReason] = useState("");
  const [showReason, setShowReason] = useState<"accept" | "reject" | "defer" | null>(null);
  const [showEdit, setShowEdit] = useState(false);
  const initialStatement = String(proposal.content.statement ?? proposal.content.text ?? "");
  const [editText, setEditText] = useState(initialStatement);
  const [editReason, setEditReason] = useState("");
  const typeConfig = CHANGE_TYPE_CONFIG[proposal.change_type] ?? CHANGE_TYPE_CONFIG.fact;
  const statusConfig = STATUS_CONFIG[proposal.status] ?? STATUS_CONFIG.pending;
  const tier = getConfidenceTier(proposal.confidence);
  const TypeIcon = typeConfig.icon;
  const StatusIcon = statusConfig.icon;

  const contentPreview = useMemo(() => {
    const c = proposal.content;
    if (c.name) return String(c.name);
    if (c.label) return String(c.label);
    if (c.statement) return String(c.statement).slice(0, 120);
    if (c.text) return String(c.text).slice(0, 120);
    return JSON.stringify(c).slice(0, 120);
  }, [proposal.content]);

  const evidenceExcerpt = typeof proposal.content.source_excerpt === "string"
    ? proposal.content.source_excerpt
    : null;
  const explanation =
    proposal.decision_metadata?.reason ??
    proposal.defer_reason ??
    proposal.edit_reason ??
    proposal.review_reason ??
    null;

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
            {proposal.deferred && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full border border-sky-500/30 bg-sky-500/10 text-sky-300 font-medium">
                Deferred
              </span>
            )}
            {proposal.needs_review && (
              <span
                data-testid="needs-review-badge"
                title={`Advisory flag: this does not prevent acceptance or commit.${proposal.review_reason ? ` ${proposal.review_reason}` : ""}`}
                className="text-[10px] px-1.5 py-0.5 rounded-full border border-amber-500/40 bg-amber-500/10 text-amber-300 font-medium flex items-center gap-1"
              >
                <AlertTriangle className="w-3 h-3" />
                Needs review
              </span>
            )}
            {proposal.status !== "pending" && (
              <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full border font-medium flex items-center gap-1", statusConfig.bg, statusConfig.color)}>
                <StatusIcon className="w-3 h-3" />
                {statusConfig.label}
              </span>
            )}
          </div>
          <p className="text-sm text-slate-300 mt-1 break-words">{contentPreview}</p>
          {evidenceExcerpt && (
            <div className="mt-1 rounded border border-white/8 bg-white/2 px-2 py-1">
              <p className="text-[9px] uppercase tracking-wider text-slate-500">Evidence</p>
              <p className="text-[11px] text-slate-400 break-words">{evidenceExcerpt}</p>
            </div>
          )}
          {proposal.evidence.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1">
              {proposal.evidence.map((item, i) => (
                <span key={`${item.ref_id}-${i}`} className="text-[9px] px-1.5 py-0.5 rounded border border-white/8 text-slate-500">
                  {item.type}: {item.ref_id.slice(0, 8)}
                </span>
              ))}
            </div>
          )}
          {explanation && (
            <p className="text-[10px] text-slate-400 mt-1">
              <span className="text-slate-500">Explanation:</span> {explanation}
            </p>
          )}
          {proposal.needs_review && (
            <p className="text-[10px] text-amber-300/80 mt-1">Advisory flag: it does not prevent acceptance or commit.</p>
          )}
          {proposal.proposer && (
            <p className="text-[10px] text-slate-500 mt-1">Proposed by: {proposal.proposer}</p>
          )}
        </div>
      </div>

      {proposal.status === "pending" && onAccept && onReject && (
        <div className="space-y-2">
          <AnimatePresence>
            {showReason && !showEdit && (
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
                  placeholder={showReason === "defer" ? "Reason for deferring..." : `Reason for ${showReason}ing...`}
                  className="w-full px-2 py-1.5 text-xs rounded-lg bg-white/5 border border-white/10 text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-cyan-500/40"
                />
              </motion.div>
            )}
            {showEdit && onEdit && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden space-y-1.5"
              >
                <textarea
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  rows={2}
                  className="w-full px-2 py-1.5 text-xs rounded-lg bg-white/5 border border-white/10 text-slate-300 focus:outline-none focus:border-cyan-500/40"
                />
                <input
                  type="text"
                  value={editReason}
                  onChange={(e) => setEditReason(e.target.value)}
                  placeholder="Why is this being edited?"
                  className="w-full px-2 py-1.5 text-xs rounded-lg bg-white/5 border border-white/10 text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-cyan-500/40"
                />
                <button
                  onClick={() => {
                    const statement = editText.trim();
                    if (!statement) return;
                    onEdit(proposal.proposal_id, { statement }, editReason.trim());
                    setShowEdit(false);
                  }}
                  className="px-2.5 py-1 text-xs font-medium rounded-lg bg-cyan-500/15 text-cyan-300 border border-cyan-500/30"
                >
                  Save edit
                </button>
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
            {onEdit && (
              <button
                onClick={() => {
                  setShowReason(null);
                  setEditText(initialStatement);
                  setShowEdit((v) => !v);
                }}
                className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-lg bg-white/5 text-slate-300 border border-white/10 hover:bg-white/10 transition-all"
              >
                Edit
              </button>
            )}
            {onDefer && !proposal.deferred && (
              <button
                onClick={() => {
                  if (showReason === "defer") {
                    onDefer(proposal.proposal_id, reason.trim());
                    setShowReason(null);
                    setReason("");
                  } else {
                    setShowReason("defer");
                  }
                }}
                className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-lg bg-sky-500/10 text-sky-300 border border-sky-500/25 hover:bg-sky-500/20 transition-all"
              >
                Defer
              </button>
            )}
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
  onDefer,
  onEdit,
}: {
  scene: SceneReview;
  onAccept: (proposalId: string, reason: string) => void;
  onReject: (proposalId: string, reason: string) => void;
  onDefer: (proposalId: string, reason: string) => void;
  onEdit: (proposalId: string, contentPatch: Record<string, unknown>, reason: string) => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const [filter, setFilter] = useState<"all" | "pending" | "deferred" | "accepted" | "rejected">("pending");

  const filtered = useMemo(() => {
    const deferred = scene.deferred ?? [];
    const all = [...scene.pending, ...deferred, ...scene.accepted, ...scene.rejected];
    if (filter === "all") return all;
    if (filter === "deferred") return deferred;
    return all.filter((p) => p.status === filter && (filter !== "pending" || !p.deferred));
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
          {(scene.deferred ?? []).length > 0 && (
            <span className="px-1.5 py-0.5 rounded-full bg-sky-500/15 text-sky-300 border border-sky-500/20">
              {(scene.deferred ?? []).length} deferred
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

      {(scene.summary || (scene.participants ?? []).length > 0 || (scene.locations ?? []).length > 0) && (
        <div className="px-4 pb-2 space-y-1">
          {scene.summary && (
            <p className="text-xs text-slate-400">{scene.summary}</p>
          )}
          {((scene.participants ?? []).length > 0 || (scene.locations ?? []).length > 0) && (
            <div className="flex flex-wrap gap-1">
              {(scene.participants ?? []).map((name) => (
                <span key={`participant-${name}`} className="text-[9px] px-1.5 py-0.5 rounded-full border border-emerald-500/20 text-emerald-300">
                  {name}
                </span>
              ))}
              {(scene.locations ?? []).map((name) => (
                <span key={`location-${name}`} className="text-[9px] px-1.5 py-0.5 rounded-full border border-sky-500/20 text-sky-300">
                  {name}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

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
              {(["pending", "deferred", "accepted", "rejected", "all"] as const).map((f) => (
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
                  onDefer={onDefer}
                  onEdit={onEdit}
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

  const deferMutation = useMutation({
    mutationFn: ({ proposalId, reason }: { proposalId: string; reason: string }) =>
      canonApi.deferProposal(proposalId, reason || "Deferred by GM"),
    onSuccess: invalidate,
  });

  const editMutation = useMutation({
    mutationFn: ({
      proposalId,
      contentPatch,
      reason,
    }: {
      proposalId: string;
      contentPatch: Record<string, unknown>;
      reason: string;
    }) => canonApi.editProposal(proposalId, contentPatch, reason || undefined),
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

  const handleDefer = useCallback(
    (proposalId: string, reason: string) => deferMutation.mutate({ proposalId, reason }),
    [deferMutation],
  );

  const handleEdit = useCallback(
    (proposalId: string, contentPatch: Record<string, unknown>, reason: string) =>
      editMutation.mutate({ proposalId, contentPatch, reason }),
    [editMutation],
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
        <SceneCard scene={scene} onAccept={handleAccept} onReject={handleReject} onDefer={handleDefer} onEdit={handleEdit} />
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
              {queue.total_pending} pending{queue.total_deferred ? `, ${queue.total_deferred} deferred` : ""} across {queue.scenes.length} lane{queue.scenes.length !== 1 ? "s" : ""}
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
              onDefer={handleDefer}
              onEdit={handleEdit}
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
