/**
 * Shared canon-review triage model (F2-3a).
 *
 * One adapter normalizes the three proposal shapes the review surfaces
 * return — pack proposals (`ingestApi.listProposals`), by-ingest items
 * (`canonApi.byIngest`), and story/scene queue items (`canonApi.storyQueue`
 * / `canonApi.sceneReview`, which serialize full ProposedChangeResponse
 * documents) — into a single `ReviewItem` the workbench renders.
 *
 * Also home to the shared filter model + pure filter/sort helpers and the
 * URL query-parameter (de)serialization that makes scope + filter state
 * deep-linkable.
 */

import type { ProposalItem } from "./types";
import { CONFIDENCE_TIERS } from "./confidence";

// ─── Model ───────────────────────────────────────────────────

export type ReviewScope = "pack" | "ingest" | "story";

export type ReviewStatus = "pending" | "accepted" | "rejected";

export type ReviewSort = "newest" | "oldest" | "confidence";

export interface ReviewItem {
  id: string;
  scope: ReviewScope;
  change_type: string;
  /** Raw extraction subtype (e.g. create_axiom) — the operation subtype. */
  proposal_type: string | null;
  status: ReviewStatus;
  // Lineage
  pack_id: string | null;
  ingestion_job_id: string | null;
  story_id: string | null;
  scene_id: string | null;
  turn_id: string | null;
  source: string | null;
  // Payload
  content: Record<string, unknown>;
  /** Source page/section when the extractor recorded one. */
  source_ref: string | null;
  evidence: Array<{ type: string; ref_id: string }>;
  confidence: number;
  authority: string;
  proposer: string;
  canon_level: string | null;
  // Decision metadata (when decided)
  decision_reason: string | null;
  decided_by: string | null;
  decided_at: string | null;
  // Timestamps
  created_at: string | null;
  updated_at: string | null;
}

/**
 * Input shape accepted by the adapter. `ProposalItem` is the common
 * denominator; story/scene items carry the extra ProposedChangeResponse
 * fields at runtime even though the frontend type doesn't declare them.
 */
export type ReviewItemInput = ProposalItem &
  Partial<{
    scene_id: string | null;
    story_id: string | null;
    turn_id: string | null;
    updated_at: string | null;
    decision_metadata: {
      decided_by: string;
      decided_at: string;
      reason: string;
    } | null;
  }>;

export interface ReviewItemContext {
  packId?: string | null;
  jobId?: string | null;
  storyId?: string | null;
}

function strOrNull(v: unknown): string | null {
  return typeof v === "string" && v.length > 0 ? v : null;
}

/** Normalize any of the three scope shapes into a ReviewItem. */
export function toReviewItem(
  raw: ReviewItemInput,
  scope: ReviewScope,
  ctx: ReviewItemContext = {},
): ReviewItem {
  const content = raw.content ?? {};
  const source = raw.source ?? null;
  // Derive lineage from the source tag when explicit IDs are absent:
  // "knowledge_pack:<uuid>" / "ingestion_job:<uuid>".
  const sourceId = source?.includes(":") ? source.slice(source.indexOf(":") + 1) : null;
  return {
    id: raw.proposal_id,
    scope,
    change_type: raw.change_type,
    proposal_type: raw.proposal_type ?? null,
    status: raw.status,
    pack_id:
      ctx.packId ?? (source?.startsWith("knowledge_pack:") ? sourceId : null),
    ingestion_job_id:
      ctx.jobId ?? (source?.startsWith("ingestion_job:") ? sourceId : null),
    story_id: raw.story_id ?? ctx.storyId ?? null,
    scene_id: raw.scene_id ?? null,
    turn_id: raw.turn_id ?? null,
    source,
    content,
    source_ref: strOrNull(content.source_ref) ?? strOrNull(content.source_hint),
    evidence: raw.evidence ?? [],
    confidence: raw.confidence,
    authority: raw.authority,
    proposer: raw.proposer,
    canon_level: strOrNull(content.canon_level),
    decision_reason: raw.decision_metadata?.reason ?? null,
    decided_by: raw.decision_metadata?.decided_by ?? null,
    decided_at: raw.decision_metadata?.decided_at ?? null,
    created_at: raw.created_at ?? null,
    updated_at: raw.updated_at ?? null,
  };
}

/** Display title shared by the row and the drawer. */
export function reviewItemTitle(item: ReviewItem): string {
  const c = item.content;
  const candidate =
    c.name ?? c.statement ?? c.label ?? c.title ?? c.text ?? c.checkpoint_summary;
  if (typeof candidate === "string" && candidate.length > 0) return candidate;
  return "Untitled proposal";
}

// ─── Filters ─────────────────────────────────────────────────

export interface ReviewFilters {
  status: "all" | ReviewStatus;
  changeType: string; // "all" or a change_type value
  confidenceTier: "all" | keyof typeof CONFIDENCE_TIERS;
  /** Inclusive ISO date (YYYY-MM-DD) bounds on created_at; "" = unbounded. */
  dateFrom: string;
  dateTo: string;
  search: string;
  sort: ReviewSort;
}

export const DEFAULT_REVIEW_FILTERS: ReviewFilters = {
  status: "all",
  changeType: "all",
  confidenceTier: "all",
  dateFrom: "",
  dateTo: "",
  search: "",
  sort: "newest",
};

function parseTime(iso: string | null): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
}

export function applyReviewFilters(
  items: ReviewItem[],
  filters: ReviewFilters,
): ReviewItem[] {
  const needle = filters.search.trim().toLowerCase();
  const from = filters.dateFrom ? Date.parse(`${filters.dateFrom}T00:00:00`) : null;
  // Inclusive end-of-day for the "to" bound.
  const to = filters.dateTo ? Date.parse(`${filters.dateTo}T23:59:59.999`) : null;

  const filtered = items.filter((item) => {
    if (filters.status !== "all" && item.status !== filters.status) return false;
    if (filters.changeType !== "all" && item.change_type !== filters.changeType)
      return false;
    if (filters.confidenceTier !== "all") {
      const c = item.confidence;
      if (filters.confidenceTier === "high" && c < CONFIDENCE_TIERS.high.min)
        return false;
      if (
        filters.confidenceTier === "medium" &&
        (c < CONFIDENCE_TIERS.medium.min || c >= CONFIDENCE_TIERS.high.min)
      )
        return false;
      if (filters.confidenceTier === "low" && c >= CONFIDENCE_TIERS.medium.min)
        return false;
    }
    const created = parseTime(item.created_at);
    if (from !== null && (created === null || created < from)) return false;
    if (to !== null && (created === null || created > to)) return false;
    if (needle) {
      const haystack = [
        reviewItemTitle(item),
        item.proposer,
        item.proposal_type ?? "",
        item.change_type,
        JSON.stringify(item.content),
      ]
        .join("\n")
        .toLowerCase();
      if (!haystack.includes(needle)) return false;
    }
    return true;
  });

  const sorted = [...filtered];
  if (filters.sort === "confidence") {
    sorted.sort((a, b) => b.confidence - a.confidence);
  } else {
    sorted.sort((a, b) => {
      const ta = parseTime(a.created_at) ?? 0;
      const tb = parseTime(b.created_at) ?? 0;
      return filters.sort === "newest" ? tb - ta : ta - tb;
    });
  }
  return sorted;
}

// ─── URL state ───────────────────────────────────────────────

const URL_KEYS = {
  scope: "scope",
  status: "status",
  changeType: "type",
  confidenceTier: "conf",
  dateFrom: "from",
  dateTo: "to",
  search: "q",
  sort: "sort",
} as const;

const VALID_SCOPES: ReviewScope[] = ["pack", "ingest", "story"];

/** Minimal read interface — matches Next's ReadonlyURLSearchParams. */
export interface ParamReader {
  get(name: string): string | null;
  toString(): string;
}

/** Read the scope from URL params (?scope=…, falling back to ?job= deep link). */
export function scopeFromParams(params: ParamReader): ReviewScope {
  const scope = params.get(URL_KEYS.scope);
  if (scope && (VALID_SCOPES as string[]).includes(scope)) return scope as ReviewScope;
  if (params.get("job")) return "ingest";
  return "pack";
}

/** Read filters from URL params; missing/invalid values fall back to defaults. */
export function filtersFromParams(params: ParamReader): ReviewFilters {
  const d = DEFAULT_REVIEW_FILTERS;
  const status = params.get(URL_KEYS.status);
  const conf = params.get(URL_KEYS.confidenceTier);
  const sort = params.get(URL_KEYS.sort);
  return {
    status: status === "pending" || status === "accepted" || status === "rejected" ? status : d.status,
    changeType: params.get(URL_KEYS.changeType) ?? d.changeType,
    confidenceTier:
      conf === "high" || conf === "medium" || conf === "low" ? conf : d.confidenceTier,
    dateFrom: params.get(URL_KEYS.dateFrom) ?? d.dateFrom,
    dateTo: params.get(URL_KEYS.dateTo) ?? d.dateTo,
    search: params.get(URL_KEYS.search) ?? d.search,
    sort: sort === "oldest" || sort === "confidence" ? sort : d.sort,
  };
}

/**
 * Merge scope + filters into an existing param set (preserving deep-link
 * params like ?pack=/?job=). Default-valued filters are omitted to keep
 * URLs short.
 */
export function reviewParamsToSearch(
  base: URLSearchParams,
  scope: ReviewScope,
  filters: ReviewFilters,
): URLSearchParams {
  const next = new URLSearchParams(base.toString());
  const d = DEFAULT_REVIEW_FILTERS;
  next.set(URL_KEYS.scope, scope);
  const setOrDelete = (key: string, value: string, fallback: string) => {
    if (value === fallback || value === "") next.delete(key);
    else next.set(key, value);
  };
  setOrDelete(URL_KEYS.status, filters.status, d.status);
  setOrDelete(URL_KEYS.changeType, filters.changeType, d.changeType);
  setOrDelete(URL_KEYS.confidenceTier, filters.confidenceTier, d.confidenceTier);
  setOrDelete(URL_KEYS.dateFrom, filters.dateFrom, d.dateFrom);
  setOrDelete(URL_KEYS.dateTo, filters.dateTo, d.dateTo);
  setOrDelete(URL_KEYS.search, filters.search, d.search);
  setOrDelete(URL_KEYS.sort, filters.sort, d.sort);
  return next;
}
