"use client";

/**
 * Shared canon-review workbench (F2-3 a/c) — one triage list used by all
 * three scopes (pack / ingestion job / story-scene).
 *
 * - Shared filter bar (status / change type / confidence tier / date range /
 *   text search / sort), state owned by the page and mirrored to the URL.
 * - Per-row checkbox selection, "select visible", "clear", and "select all
 *   matching active filters" — the latter resolved SERVER-SIDE via the
 *   by-filter preview/execute endpoint so it is not silently capped at the
 *   loaded page (200/500/1000 rows).
 * - Bulk accept/reject with a shared reason dialog + affected-count
 *   confirmation; per-item failures rendered from the {results, errors}
 *   contract.
 * - Row click opens the detail/provenance drawer.
 */

import { useCallback, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  BookOpen,
  CalendarClock,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Globe2,
  Layers,
  Loader2,
  Scroll,
  Users,
  X,
  XCircle,
} from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { canonApi } from "@/lib/api";
import type { BatchVerdictError, VerdictByFilterRequest, VerdictItem } from "@/lib/types";
import type { ReviewFilters, ReviewItem } from "@/lib/reviewItem";
import { applyReviewFilters, reviewItemTitle } from "@/lib/reviewItem";
import { CONFIDENCE_TIERS, getConfidenceTier } from "@/lib/confidence";
import { ENTITY_TYPE_CONFIG } from "@/lib/forge";
import { cn } from "@/lib/utils";
import { ReviewFilterBar } from "./ReviewFilterBar";
import { ReviewDetailDrawer } from "./ReviewDetailDrawer";

// ─── Types ───────────────────────────────────────────────────

/** Scope constraint sent to the by-filter endpoint (exactly one is set). */
export interface ByFilterBase {
  story_id?: string | null;
  scene_id?: string | null;
  source?: string | null;
}

interface VerdictOutcome {
  decision: "accepted" | "rejected";
  applied: number;
  errors: BatchVerdictError[];
}

interface ReasonDialogState {
  decision: "accepted" | "rejected";
  mode: "selected" | "all-matching";
  /** Affected count: selection size, or preview count for all-matching. */
  count: number;
  /** Preview token (all-matching mode only). */
  previewToken: string | null;
}

// ─── Row ─────────────────────────────────────────────────────

function ChangeTypeIcon({ item }: { item: ReviewItem }) {
  const entityType = (item.content.entity_type as string) || "";
  const cfg = ENTITY_TYPE_CONFIG[entityType] ?? ENTITY_TYPE_CONFIG.concept;
  const Icon =
    item.change_type === "entity" ? cfg.icon
    : item.change_type === "fact" ? Scroll
    : item.change_type === "relationship" ? Globe2
    : item.change_type === "mechanic" ? Layers
    : item.change_type === "event" ? CalendarClock
    : item.change_type === "state_change" ? Activity
    : BookOpen;
  return (
    <Icon
      className={cn(
        "h-4 w-4 mt-0.5 shrink-0",
        item.change_type === "entity" ? cfg.color : "text-fg-secondary",
      )}
    />
  );
}

function ReviewRow({
  item,
  selected,
  onToggleSelect,
  onOpen,
  onQuickVerdict,
  isProcessing,
}: {
  item: ReviewItem;
  selected: boolean;
  onToggleSelect: () => void;
  onOpen: () => void;
  onQuickVerdict: (decision: "accepted" | "rejected") => void;
  isProcessing: boolean;
}) {
  const tier = getConfidenceTier(item.confidence);
  const content = item.content;
  const isEntity = item.change_type === "entity";
  const isRelationship = item.change_type === "relationship";
  const description = (content.description as string) || "";
  const statement = (content.statement as string) || "";
  const fromEntity = (content.from_entity as string) || "";
  const toEntity = (content.to_entity as string) || "";
  const relType = (content.rel_type as string) || "";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "group flex gap-3 px-4 py-3 border-b border-border transition-colors cursor-pointer",
        item.status === "accepted" && "bg-emerald-500/5",
        item.status === "rejected" && "bg-red-500/5 opacity-60",
        item.status === "pending" && "hover:bg-bg-hover",
        selected && "bg-accent-primary/10",
      )}
      onClick={onOpen}
      data-testid={`review-row-${item.id}`}
    >
      {/* Selection checkbox (pending only) */}
      {item.status === "pending" ? (
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggleSelect}
          onClick={(e) => e.stopPropagation()}
          aria-label={`Select proposal ${reviewItemTitle(item)}`}
          className="mt-1 h-3.5 w-3.5 shrink-0 accent-cyan-500"
        />
      ) : (
        <span className="mt-1 h-3.5 w-3.5 shrink-0" />
      )}

      <ChangeTypeIcon item={item} />

      {/* Content */}
      <div className="flex-1 min-w-0 space-y-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className={cn(
              "text-[10px] px-1.5 py-0.5 rounded border flex items-center gap-1 capitalize",
              item.status === "pending" && "tag-amber",
              item.status === "accepted" && "tag-cyan",
              item.status === "rejected" && "tag-red",
            )}
          >
            <CircleDot className="h-2.5 w-2.5" />
            {item.status}
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded border tag-dim">
            {item.change_type}
          </span>
          <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full", tier.bg, tier.color)}>
            {Math.round(item.confidence * 100)}%
          </span>
          <span className="font-semibold text-fg-primary text-sm truncate">
            {reviewItemTitle(item)}
          </span>
        </div>

        {isEntity && description && (
          <p className="text-xs text-fg-secondary truncate">{description}</p>
        )}
        {item.change_type === "fact" && statement && (
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

      {/* Quick actions */}
      {item.status === "pending" && (
        <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={() => onQuickVerdict("accepted")}
            disabled={isProcessing}
            className={cn(
              "p-1.5 rounded transition-colors",
              "hover:bg-emerald-500/20 text-fg-muted hover:text-emerald-400",
              "disabled:opacity-40",
            )}
            title="Accept"
          >
            {isProcessing ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Check className="h-3.5 w-3.5" />
            )}
          </button>
          <button
            onClick={() => onQuickVerdict("rejected")}
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

// ─── Reason dialog ───────────────────────────────────────────

function ReasonDialog({
  dialog,
  busy,
  onConfirm,
  onCancel,
}: {
  dialog: ReasonDialogState;
  busy: boolean;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}) {
  const [reason, setReason] = useState(
    dialog.decision === "accepted" ? "Batch approved by GM" : "Batch rejected by GM",
  );
  const verb = dialog.decision === "accepted" ? "Accept" : "Reject";
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md rounded-xl border border-border bg-bg-primary p-4 space-y-3 shadow-xl">
        <h3 className="text-sm font-semibold text-fg-primary">
          {verb} {dialog.count} proposal{dialog.count !== 1 ? "s" : ""}?
        </h3>
        <p className="text-xs text-fg-muted">
          {dialog.mode === "all-matching"
            ? "This applies to every proposal matching the active filters — resolved server-side, not just the rows loaded on screen."
            : "This applies to the proposals you selected."}
        </p>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
          aria-label="Decision reason"
          placeholder="Reason (required)…"
          className="w-full px-2 py-1.5 text-xs rounded-lg bg-bg-hover border border-border text-fg-primary placeholder:text-fg-muted focus:outline-none focus:border-accent-primary"
        />
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            disabled={busy}
            className="btn-ghost px-3 py-1.5 text-xs flex items-center gap-1"
          >
            <X className="h-3 w-3" />
            Cancel
          </button>
          <button
            onClick={() => onConfirm(reason.trim())}
            disabled={busy || reason.trim().length === 0}
            className={cn(
              "btn-ghost px-3 py-1.5 text-xs flex items-center gap-1.5 disabled:opacity-40",
              dialog.decision === "accepted" ? "text-emerald-400" : "text-red-400",
            )}
          >
            {busy ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : dialog.decision === "accepted" ? (
              <Check className="h-3 w-3" />
            ) : (
              <XCircle className="h-3 w-3" />
            )}
            Confirm {verb.toLowerCase()} ({dialog.count})
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Workbench ───────────────────────────────────────────────

/** Map the confidence-tier filter onto the by-filter request's min/max. */
function confidenceRange(tier: ReviewFilters["confidenceTier"]): {
  confidence_min?: number;
  confidence_max?: number;
} {
  if (tier === "high") return { confidence_min: CONFIDENCE_TIERS.high.min };
  if (tier === "medium")
    return {
      confidence_min: CONFIDENCE_TIERS.medium.min,
      // Backend bound is inclusive; nudge below the high threshold so the
      // server set matches the client-side tier exactly.
      confidence_max: CONFIDENCE_TIERS.high.min - 0.000001,
    };
  if (tier === "low")
    return { confidence_max: CONFIDENCE_TIERS.medium.min - 0.000001 };
  return {};
}

export function buildByFilterRequest(
  base: ByFilterBase,
  filters: ReviewFilters,
  decision: "accepted" | "rejected",
  reason: string,
  dryRun: boolean,
  previewToken: string | null = null,
): VerdictByFilterRequest {
  return {
    decision,
    reason,
    story_id: base.story_id ?? null,
    scene_id: base.scene_id ?? null,
    source: base.source ?? null,
    // Verdicts only make sense on pending; "all" lets the backend default
    // to pending. An explicit accepted/rejected filter passes through.
    status: filters.status === "all" ? null : filters.status,
    change_type: filters.changeType === "all" ? null : filters.changeType,
    ...confidenceRange(filters.confidenceTier),
    created_after: filters.dateFrom ? `${filters.dateFrom}T00:00:00Z` : null,
    created_before: filters.dateTo ? `${filters.dateTo}T23:59:59.999Z` : null,
    search: filters.search.trim() || null,
    dry_run: dryRun,
    preview_token: previewToken,
  };
}

export function ReviewWorkbench({
  items,
  isLoading = false,
  loadError = false,
  emptyMessage,
  filters,
  onFiltersChange,
  byFilterBase,
  onChanged,
  headerActions,
}: {
  items: ReviewItem[];
  isLoading?: boolean;
  loadError?: boolean;
  emptyMessage: string;
  filters: ReviewFilters;
  onFiltersChange: (next: ReviewFilters) => void;
  byFilterBase: ByFilterBase;
  onChanged: () => void;
  headerActions?: React.ReactNode;
}) {
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [drawerItem, setDrawerItem] = useState<ReviewItem | null>(null);
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [dialog, setDialog] = useState<ReasonDialogState | null>(null);
  const [outcome, setOutcome] = useState<VerdictOutcome | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const filtered = useMemo(() => applyReviewFilters(items, filters), [items, filters]);
  const visiblePending = useMemo(
    () => filtered.filter((i) => i.status === "pending"),
    [filtered],
  );

  const verdictMutation = useMutation({
    mutationFn: (verdicts: VerdictItem[]) => canonApi.batchVerdicts(verdicts),
  });
  const byFilterMutation = useMutation({
    mutationFn: (req: VerdictByFilterRequest) => canonApi.verdictsByFilter(req),
  });

  const busy = verdictMutation.isPending || byFilterMutation.isPending;

  const handleOutcome = useCallback(
    (decision: "accepted" | "rejected", applied: number, errors: BatchVerdictError[]) => {
      setOutcome({ decision, applied, errors });
      setSelected(new Set());
      onChanged();
    },
    [onChanged],
  );

  // ── Quick per-row verdict (default reason, no dialog) ──────
  const handleQuickVerdict = useCallback(
    (item: ReviewItem, decision: "accepted" | "rejected") => {
      setProcessingId(item.id);
      setOutcome(null);
      setNotice(null);
      verdictMutation.mutate(
        [
          {
            proposal_id: item.id,
            decision,
            reason:
              decision === "accepted" ? "Approved in Forge review" : "Rejected in Forge review",
          },
        ],
        {
          onSuccess: (data) =>
            handleOutcome(decision, data.results.length, data.errors),
          onError: (err) =>
            setNotice(`Verdict failed: ${err instanceof Error ? err.message : String(err)}`),
          onSettled: () => setProcessingId(null),
        },
      );
    },
    [verdictMutation, handleOutcome],
  );

  // ── Selection helpers ──────────────────────────────────────
  const toggleSelect = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const selectVisible = useCallback(() => {
    setSelected(new Set(visiblePending.map((i) => i.id)));
  }, [visiblePending]);

  const clearSelection = useCallback(() => setSelected(new Set()), []);

  // ── Bulk: selected ─────────────────────────────────────────
  const openSelectedDialog = useCallback(
    (decision: "accepted" | "rejected") => {
      if (selected.size === 0) return;
      setOutcome(null);
      setDialog({ decision, mode: "selected", count: selected.size, previewToken: null });
    },
    [selected],
  );

  // ── Bulk: all matching active filters (server-side) ────────
  const openAllMatchingDialog = useCallback(
    (decision: "accepted" | "rejected") => {
      setOutcome(null);
      setNotice(null);
      byFilterMutation.mutate(
        buildByFilterRequest(byFilterBase, filters, decision, "preview", true),
        {
          onSuccess: (data) => {
            if (data.affected_count === 0) {
              setNotice("No proposals match the active filters.");
              return;
            }
            setDialog({
              decision,
              mode: "all-matching",
              count: data.affected_count,
              previewToken: data.preview_token,
            });
          },
          onError: (err) =>
            setNotice(`Preview failed: ${err instanceof Error ? err.message : String(err)}`),
        },
      );
    },
    [byFilterMutation, byFilterBase, filters],
  );

  // ── Dialog confirm ─────────────────────────────────────────
  const handleDialogConfirm = useCallback(
    (reason: string) => {
      if (!dialog) return;
      const { decision, mode, previewToken } = dialog;
      setDialog(null);
      if (mode === "selected") {
        const verdicts: VerdictItem[] = [...selected].map((id) => ({
          proposal_id: id,
          decision,
          reason,
        }));
        verdictMutation.mutate(verdicts, {
          onSuccess: (data) => handleOutcome(decision, data.results.length, data.errors),
          onError: (err) =>
            setNotice(`Batch failed: ${err instanceof Error ? err.message : String(err)}`),
        });
      } else {
        byFilterMutation.mutate(
          buildByFilterRequest(byFilterBase, filters, decision, reason, false, previewToken),
          {
            onSuccess: (data) =>
              handleOutcome(decision, data.results.length, data.errors),
            onError: (err) =>
              setNotice(
                `Bulk verdict failed: ${err instanceof Error ? err.message : String(err)}`,
              ),
          },
        );
      }
    },
    [dialog, selected, verdictMutation, byFilterMutation, byFilterBase, filters, handleOutcome],
  );

  // ── Render ─────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Filter bar + bulk toolbar */}
      <div className="shrink-0 border-b border-border px-6 py-2 space-y-2">
        <div className="flex items-center gap-3 flex-wrap">
          <ReviewFilterBar filters={filters} onChange={onFiltersChange} />
          {headerActions && <div className="flex items-center gap-2 ml-auto">{headerActions}</div>}
        </div>
        <div className="flex items-center gap-2 flex-wrap text-xs">
          <button
            onClick={selectVisible}
            disabled={visiblePending.length === 0}
            className="btn-ghost px-2 py-1 text-[11px] disabled:opacity-40"
          >
            Select visible ({visiblePending.length})
          </button>
          <button
            onClick={() => openAllMatchingDialog("accepted")}
            disabled={busy}
            className="btn-ghost px-2 py-1 text-[11px] text-emerald-400 disabled:opacity-40"
          >
            Accept all matching…
          </button>
          <button
            onClick={() => openAllMatchingDialog("rejected")}
            disabled={busy}
            className="btn-ghost px-2 py-1 text-[11px] text-red-400 disabled:opacity-40"
          >
            Reject all matching…
          </button>
          {selected.size > 0 && (
            <>
              <span className="text-fg-muted">{selected.size} selected</span>
              <button
                onClick={() => openSelectedDialog("accepted")}
                disabled={busy}
                className="btn-ghost px-2 py-1 text-[11px] text-emerald-400 disabled:opacity-40"
              >
                Accept selected
              </button>
              <button
                onClick={() => openSelectedDialog("rejected")}
                disabled={busy}
                className="btn-ghost px-2 py-1 text-[11px] text-red-400 disabled:opacity-40"
              >
                Reject selected
              </button>
              <button onClick={clearSelection} className="btn-ghost px-2 py-1 text-[11px]">
                Clear
              </button>
            </>
          )}
        </div>
      </div>

      {/* Notices + outcome */}
      {notice && (
        <div className="shrink-0 border-b border-amber-500/30 bg-amber-500/10 px-6 py-2 flex items-center gap-2">
          <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0" />
          <span className="text-xs text-amber-300">{notice}</span>
        </div>
      )}
      {outcome && (
        <div
          className={cn(
            "shrink-0 border-b px-6 py-2 space-y-1",
            outcome.errors.length > 0
              ? "border-amber-500/30 bg-amber-500/10"
              : "border-emerald-500/30 bg-emerald-500/10",
          )}
          data-testid="verdict-outcome"
        >
          <div className="flex items-center gap-2">
            {outcome.errors.length > 0 ? (
              <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0" />
            ) : (
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
            )}
            <span className="text-xs text-fg-secondary">
              {outcome.applied} {outcome.decision}
              {outcome.errors.length > 0 && `, ${outcome.errors.length} failed`}
            </span>
            <button
              onClick={() => setOutcome(null)}
              aria-label="Dismiss outcome"
              className="ml-auto p-0.5 rounded hover:bg-bg-hover text-fg-muted"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
          {outcome.errors.length > 0 && (
            <ul className="pl-5 space-y-0.5">
              {outcome.errors.map((e) => (
                <li key={e.proposal_id} className="text-[11px] text-amber-300 font-mono">
                  {e.proposal_id.slice(0, 8)}: {e.error}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-cyan-400" />
          </div>
        ) : loadError ? (
          <div className="flex flex-col items-center justify-center py-16 text-fg-muted">
            <AlertTriangle className="h-8 w-8 mb-2 text-amber-400 opacity-60" />
            <p className="text-sm">Failed to load proposals</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-fg-muted">
            <CheckCircle2 className="h-8 w-8 mb-2 opacity-30" />
            <p className="text-sm">{items.length === 0 ? emptyMessage : "No proposals match the active filters"}</p>
          </div>
        ) : (
          filtered.map((item) => (
            <ReviewRow
              key={item.id}
              item={item}
              selected={selected.has(item.id)}
              onToggleSelect={() => toggleSelect(item.id)}
              onOpen={() => setDrawerItem(item)}
              onQuickVerdict={(decision) => handleQuickVerdict(item, decision)}
              isProcessing={processingId === item.id}
            />
          ))
        )}
      </div>

      {/* Drawer + dialog */}
      <ReviewDetailDrawer item={drawerItem} onClose={() => setDrawerItem(null)} />
      {dialog && (
        <ReasonDialog
          dialog={dialog}
          busy={busy}
          onConfirm={handleDialogConfirm}
          onCancel={() => setDialog(null)}
        />
      )}
    </div>
  );
}
