"use client";

/**
 * Canon-review detail & provenance drawer (F2-3b).
 *
 * Row click opens the complete structured payload plus provenance:
 * operation subtype, evidence refs, source page/section, scene/turn/job/pack
 * lineage, authority, proposer, timestamps, existing decision reason.
 *
 * Create proposals are labelled "Proposed value". State/update payloads
 * render explicit Added / Removed / Changed sections when the payload
 * carries them. This is deliberately NOT branded a "diff" — the proposal
 * contract has no canonical before/after target yet.
 */

import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import type { ReviewItem } from "@/lib/reviewItem";
import { reviewItemTitle } from "@/lib/reviewItem";
import { getConfidenceTier } from "@/lib/confidence";
import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<string, string> = {
  pending: "tag-amber",
  accepted: "tag-cyan",
  rejected: "tag-red",
};

const SCOPE_LABELS: Record<string, string> = {
  pack: "Knowledge pack",
  ingest: "Ingestion job",
  story: "Story / scene",
};

function shortId(id: string | null): string | null {
  return id ? id.slice(0, 8) : null;
}

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function MetaRow({ label, value, mono }: { label: string; value: string | null; mono?: boolean }) {
  if (!value) return null;
  return (
    <div className="flex items-baseline gap-2">
      <span className="w-24 shrink-0 text-[10px] uppercase tracking-wide text-fg-muted">
        {label}
      </span>
      <span className={cn("text-xs text-fg-secondary break-all", mono && "font-mono")}>
        {value}
      </span>
    </div>
  );
}

/** Key/value rendering of the payload, minus keys rendered elsewhere. */
function PayloadTable({
  content,
  skipKeys,
}: {
  content: Record<string, unknown>;
  skipKeys: Set<string>;
}) {
  const entries = Object.entries(content).filter(([k]) => !skipKeys.has(k));
  if (entries.length === 0) return null;
  return (
    <dl className="space-y-1">
      {entries.map(([key, value]) => (
        <div key={key} className="flex items-baseline gap-2">
          <dt className="w-32 shrink-0 text-[10px] font-mono text-fg-muted">{key}</dt>
          <dd className="text-xs text-fg-secondary break-words min-w-0">
            {formatValue(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** Explicit Added / Removed / Changed sections for state/update payloads. */
function StateChangeSections({ content }: { content: Record<string, unknown> }) {
  const sections: Array<{ label: string; keys: string[]; accent: string }> = [
    { label: "Added", keys: ["add_tags", "add", "added"], accent: "text-emerald-400" },
    { label: "Removed", keys: ["remove_tags", "remove", "removed"], accent: "text-red-400" },
    {
      label: "Changed",
      keys: ["resource_changes", "changes", "updated", "set_fields"],
      accent: "text-cyan-400",
    },
  ];
  const rendered = sections
    .map((s) => ({ ...s, key: s.keys.find((k) => content[k] !== undefined) }))
    .filter((s) => s.key !== undefined);
  if (rendered.length === 0) return null;
  return (
    <div className="space-y-2">
      {rendered.map((s) => (
        <div key={s.label}>
          <p className={cn("text-[10px] font-semibold uppercase tracking-wide", s.accent)}>
            {s.label}
          </p>
          <p className="text-xs text-fg-secondary break-words">
            {formatValue(content[s.key!])}
          </p>
        </div>
      ))}
    </div>
  );
}

const STATE_SECTION_KEYS = new Set([
  "add_tags",
  "add",
  "added",
  "remove_tags",
  "remove",
  "removed",
  "resource_changes",
  "changes",
  "updated",
  "set_fields",
]);

export function ReviewDetailDrawer({
  item,
  onClose,
}: {
  item: ReviewItem | null;
  onClose: () => void;
}) {
  return (
    <AnimatePresence>
      {item && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-black/50"
          />
          <motion.aside
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "tween", duration: 0.2 }}
            className="fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col border-l border-border bg-bg-primary"
            data-testid="review-detail-drawer"
          >
            {/* Header */}
            <div className="flex items-start gap-3 border-b border-border px-4 py-3">
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span
                    className={cn(
                      "text-[10px] px-1.5 py-0.5 rounded border capitalize",
                      STATUS_STYLES[item.status] ?? "tag-dim",
                    )}
                  >
                    {item.status}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded border tag-dim">
                    {item.change_type}
                  </span>
                  {(() => {
                    const tier = getConfidenceTier(item.confidence);
                    return (
                      <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full", tier.bg, tier.color)}>
                        {tier.label} {Math.round(item.confidence * 100)}%
                      </span>
                    );
                  })()}
                </div>
                <h2 className="text-sm font-semibold text-fg-primary break-words">
                  {reviewItemTitle(item)}
                </h2>
              </div>
              <button
                onClick={onClose}
                aria-label="Close detail"
                className="p-1 rounded hover:bg-bg-hover text-fg-muted hover:text-fg-primary transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto px-4 py-3 space-y-5">
              {/* Operation */}
              <section className="space-y-1.5">
                <h3 className="text-[10px] font-semibold uppercase tracking-wide text-fg-muted">
                  Operation
                </h3>
                <MetaRow label="Change type" value={item.change_type} mono />
                <MetaRow label="Subtype" value={item.proposal_type} mono />
                <MetaRow label="Canon level" value={item.canon_level} />
              </section>

              {/* Provenance */}
              <section className="space-y-1.5">
                <h3 className="text-[10px] font-semibold uppercase tracking-wide text-fg-muted">
                  Provenance
                </h3>
                <MetaRow label="Scope" value={SCOPE_LABELS[item.scope] ?? item.scope} />
                <MetaRow label="Pack" value={shortId(item.pack_id)} mono />
                <MetaRow label="Job" value={shortId(item.ingestion_job_id)} mono />
                <MetaRow label="Story" value={shortId(item.story_id)} mono />
                <MetaRow label="Scene" value={shortId(item.scene_id)} mono />
                <MetaRow label="Turn" value={shortId(item.turn_id)} mono />
                <MetaRow label="Source" value={item.source} mono />
                <MetaRow label="Source ref" value={item.source_ref} />
                <MetaRow label="Authority" value={item.authority} />
                <MetaRow label="Proposer" value={item.proposer} />
                {item.evidence.length > 0 && (
                  <div className="flex items-baseline gap-2">
                    <span className="w-24 shrink-0 text-[10px] uppercase tracking-wide text-fg-muted">
                      Evidence
                    </span>
                    <ul className="text-xs text-fg-secondary space-y-0.5">
                      {item.evidence.map((e, i) => (
                        <li key={i} className="font-mono break-all">
                          {e.type}:{shortId(e.ref_id)}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </section>

              {/* Payload */}
              <section className="space-y-1.5">
                <h3 className="text-[10px] font-semibold uppercase tracking-wide text-fg-muted">
                  {item.change_type === "state_change" || item.change_type === "event"
                    ? "Payload"
                    : "Proposed value"}
                </h3>
                <StateChangeSections content={item.content} />
                <PayloadTable
                  content={item.content}
                  skipKeys={new Set([...STATE_SECTION_KEYS, "source_ref", "canon_level"])}
                />
              </section>

              {/* Timestamps & decision */}
              <section className="space-y-1.5">
                <h3 className="text-[10px] font-semibold uppercase tracking-wide text-fg-muted">
                  Timeline & decision
                </h3>
                <MetaRow label="Created" value={formatTime(item.created_at)} />
                <MetaRow label="Updated" value={formatTime(item.updated_at)} />
                <MetaRow label="Decided at" value={item.decided_at ? formatTime(item.decided_at) : null} />
                <MetaRow label="Decided by" value={item.decided_by} />
                {item.decision_reason && (
                  <div className="flex items-baseline gap-2">
                    <span className="w-24 shrink-0 text-[10px] uppercase tracking-wide text-fg-muted">
                      Reason
                    </span>
                    <span className="text-xs text-fg-secondary break-words">
                      {item.decision_reason}
                    </span>
                  </div>
                )}
              </section>

              {/* Raw payload */}
              <section className="space-y-1.5">
                <h3 className="text-[10px] font-semibold uppercase tracking-wide text-fg-muted">
                  Raw payload
                </h3>
                <pre className="max-h-64 overflow-auto rounded-lg border border-border bg-bg-hover p-2 text-[10px] font-mono text-fg-secondary">
                  {JSON.stringify(item.content, null, 2)}
                </pre>
              </section>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
