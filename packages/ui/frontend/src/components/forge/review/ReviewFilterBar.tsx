"use client";

/**
 * Shared canon-review filter bar (F2-3a) — one control set for all three
 * scopes (pack / ingestion job / story-scene). State lives in the URL via
 * the page; this component is controlled.
 */

import { Search } from "lucide-react";
import type { ReviewFilters, ReviewSort, ReviewStatus } from "@/lib/reviewItem";
import { CONFIDENCE_TIERS } from "@/lib/confidence";
import { cn } from "@/lib/utils";

const CHANGE_TYPES = [
  { id: "all", label: "All types" },
  { id: "entity", label: "Entities" },
  { id: "fact", label: "Facts" },
  { id: "relationship", label: "Relationships" },
  { id: "mechanic", label: "Mechanics" },
  { id: "state_change", label: "State changes" },
  { id: "event", label: "Events" },
] as const;

const STATUS_OPTIONS: Array<{ id: "all" | ReviewStatus; label: string }> = [
  { id: "all", label: "All statuses" },
  { id: "pending", label: "Pending" },
  { id: "accepted", label: "Accepted" },
  { id: "rejected", label: "Rejected" },
];

const SORT_OPTIONS: Array<{ id: ReviewSort; label: string }> = [
  { id: "newest", label: "Newest first" },
  { id: "oldest", label: "Oldest first" },
  { id: "confidence", label: "Confidence" },
];

const selectClass = cn(
  "px-2 py-1.5 text-xs rounded-lg bg-bg-hover border border-border",
  "text-fg-primary focus:outline-none focus:border-accent-primary",
);

export function ReviewFilterBar({
  filters,
  onChange,
}: {
  filters: ReviewFilters;
  onChange: (next: ReviewFilters) => void;
}) {
  const set = <K extends keyof ReviewFilters>(key: K, value: ReviewFilters[K]) =>
    onChange({ ...filters, [key]: value });

  return (
    <div
      className="flex items-center gap-2 flex-wrap"
      data-testid="review-filter-bar"
    >
      {/* Text search */}
      <div className="relative">
        <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-fg-muted" />
        <input
          type="text"
          value={filters.search}
          onChange={(e) => set("search", e.target.value)}
          placeholder="Search proposals…"
          aria-label="Search proposals"
          className={cn(selectClass, "pl-6 w-44")}
        />
      </div>

      {/* Status */}
      <select
        value={filters.status}
        onChange={(e) => set("status", e.target.value as ReviewFilters["status"])}
        aria-label="Filter by status"
        className={selectClass}
      >
        {STATUS_OPTIONS.map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
      </select>

      {/* Change type */}
      <select
        value={filters.changeType}
        onChange={(e) => set("changeType", e.target.value)}
        aria-label="Filter by change type"
        className={selectClass}
      >
        {CHANGE_TYPES.map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
      </select>

      {/* Confidence tier (shared definition from lib/confidence) */}
      <select
        value={filters.confidenceTier}
        onChange={(e) =>
          set("confidenceTier", e.target.value as ReviewFilters["confidenceTier"])
        }
        aria-label="Filter by confidence tier"
        className={selectClass}
      >
        <option value="all">All confidence</option>
        <option value="high">
          {CONFIDENCE_TIERS.high.label} (≥{CONFIDENCE_TIERS.high.min * 100}%)
        </option>
        <option value="medium">
          {CONFIDENCE_TIERS.medium.label} ({CONFIDENCE_TIERS.medium.min * 100}–
          {CONFIDENCE_TIERS.high.min * 100}%)
        </option>
        <option value="low">
          {CONFIDENCE_TIERS.low.label} (&lt;{CONFIDENCE_TIERS.medium.min * 100}%)
        </option>
      </select>

      {/* Date range */}
      <input
        type="date"
        value={filters.dateFrom}
        onChange={(e) => set("dateFrom", e.target.value)}
        aria-label="Created from"
        className={selectClass}
      />
      <span className="text-[10px] text-fg-muted">–</span>
      <input
        type="date"
        value={filters.dateTo}
        onChange={(e) => set("dateTo", e.target.value)}
        aria-label="Created to"
        className={selectClass}
      />

      {/* Sort */}
      <select
        value={filters.sort}
        onChange={(e) => set("sort", e.target.value as ReviewSort)}
        aria-label="Sort proposals"
        className={selectClass}
      >
        {SORT_OPTIONS.map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}
