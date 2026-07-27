/**
 * Unit tests for the shared canon-review triage model (F2-3a):
 * - toReviewItem normalization across the three scope shapes
 * - applyReviewFilters: each filter, combined filters, sort orders
 * - URL query-param (de)serialization (deep-linkable scope + filters)
 */

import { describe, it, expect } from "vitest";
import type { ProposalItem } from "./types";
import type { ReviewItem, ReviewItemInput } from "./reviewItem";
import {
  DEFAULT_REVIEW_FILTERS,
  applyReviewFilters,
  filtersFromParams,
  reviewParamsToSearch,
  scopeFromParams,
  toReviewItem,
} from "./reviewItem";

// ─── Fixtures ────────────────────────────────────────────────

function proposal(overrides: Partial<ProposalItem> = {}): ProposalItem {
  return {
    proposal_id: "p1",
    change_type: "fact",
    content: { statement: "The moon is hollow" },
    confidence: 0.95,
    authority: "source",
    proposer: "IngestionPipeline",
    status: "pending",
    evidence: [],
    created_at: "2026-07-10T12:00:00Z",
    ...overrides,
  };
}

function item(overrides: Partial<ReviewItem> = {}): ReviewItem {
  return {
    id: "p1",
    scope: "pack",
    change_type: "fact",
    proposal_type: "create_lore_fact",
    status: "pending",
    pack_id: "pack-1",
    ingestion_job_id: null,
    story_id: null,
    scene_id: null,
    turn_id: null,
    source: "knowledge_pack:pack-1",
    content: { statement: "The moon is hollow" },
    source_ref: null,
    evidence: [],
    confidence: 0.95,
    authority: "source",
    proposer: "IngestionPipeline",
    canon_level: null,
    decision_reason: null,
    decided_by: null,
    decided_at: null,
    created_at: "2026-07-10T12:00:00Z",
    updated_at: null,
    ...overrides,
  };
}

// ─── Adapter ─────────────────────────────────────────────────

describe("toReviewItem", () => {
  it("normalizes a pack proposal with lineage from context", () => {
    const r = toReviewItem(proposal(), "pack", { packId: "pack-9" });
    expect(r.scope).toBe("pack");
    expect(r.pack_id).toBe("pack-9");
    expect(r.ingestion_job_id).toBeNull();
    expect(r.status).toBe("pending");
    expect(r.confidence).toBe(0.95);
  });

  it("derives job lineage from the ingestion_job:<id> source tag", () => {
    const r = toReviewItem(
      proposal({ source: "ingestion_job:job-7", proposal_type: "create_axiom" }),
      "ingest",
    );
    expect(r.ingestion_job_id).toBe("job-7");
    expect(r.pack_id).toBeNull();
    expect(r.proposal_type).toBe("create_axiom");
  });

  it("derives pack lineage from the knowledge_pack:<id> source tag", () => {
    const r = toReviewItem(proposal({ source: "knowledge_pack:pack-3" }), "pack");
    expect(r.pack_id).toBe("pack-3");
  });

  it("maps story/scene queue extras: scene/turn lineage and decision metadata", () => {
    const raw: ReviewItemInput = {
      ...proposal({ status: "accepted" }),
      scene_id: "scene-1",
      turn_id: "turn-2",
      updated_at: "2026-07-11T09:00:00Z",
      decision_metadata: {
        decided_by: "GM",
        decided_at: "2026-07-11T08:30:00Z",
        reason: "Fits canon",
      },
    };
    const r = toReviewItem(raw, "story", { storyId: "story-5" });
    expect(r.story_id).toBe("story-5");
    expect(r.scene_id).toBe("scene-1");
    expect(r.turn_id).toBe("turn-2");
    expect(r.decision_reason).toBe("Fits canon");
    expect(r.decided_by).toBe("GM");
    expect(r.decided_at).toBe("2026-07-11T08:30:00Z");
    expect(r.updated_at).toBe("2026-07-11T09:00:00Z");
  });

  it("pulls source_ref and canon_level out of the content payload", () => {
    const r = toReviewItem(
      proposal({ content: { statement: "s", source_ref: "p. 42, §3", canon_level: "core" } }),
      "ingest",
    );
    expect(r.source_ref).toBe("p. 42, §3");
    expect(r.canon_level).toBe("core");
  });
});

// ─── Filters ─────────────────────────────────────────────────

const ITEMS: ReviewItem[] = [
  item({
    id: "a",
    status: "pending",
    change_type: "entity",
    confidence: 0.95,
    created_at: "2026-07-01T10:00:00Z",
    content: { name: "Ashen Duke", entity_type: "npc" },
  }),
  item({
    id: "b",
    status: "pending",
    change_type: "fact",
    confidence: 0.8,
    created_at: "2026-07-05T10:00:00Z",
    content: { statement: "The moon is hollow" },
  }),
  item({
    id: "c",
    status: "accepted",
    change_type: "state_change",
    confidence: 0.5,
    created_at: "2026-07-10T10:00:00Z",
    content: { name: "Torch", add_tags: ["lit"] },
  }),
  item({
    id: "d",
    status: "rejected",
    change_type: "event",
    confidence: 0.2,
    created_at: "2026-07-20T10:00:00Z",
    content: { name: "Festival of Embers" },
  }),
];

describe("applyReviewFilters", () => {
  it("filters by status", () => {
    const out = applyReviewFilters(ITEMS, { ...DEFAULT_REVIEW_FILTERS, status: "pending" });
    expect(out.map((i) => i.id).sort()).toEqual(["a", "b"]);
  });

  it("filters by change type (including state_change and event)", () => {
    expect(
      applyReviewFilters(ITEMS, { ...DEFAULT_REVIEW_FILTERS, changeType: "state_change" }).map(
        (i) => i.id,
      ),
    ).toEqual(["c"]);
    expect(
      applyReviewFilters(ITEMS, { ...DEFAULT_REVIEW_FILTERS, changeType: "event" }).map(
        (i) => i.id,
      ),
    ).toEqual(["d"]);
  });

  it("filters by confidence tier (high ≥0.9, medium 0.7–0.9, low <0.7)", () => {
    expect(
      applyReviewFilters(ITEMS, { ...DEFAULT_REVIEW_FILTERS, confidenceTier: "high" }).map(
        (i) => i.id,
      ),
    ).toEqual(["a"]);
    expect(
      applyReviewFilters(ITEMS, { ...DEFAULT_REVIEW_FILTERS, confidenceTier: "medium" }).map(
        (i) => i.id,
      ),
    ).toEqual(["b"]);
    expect(
      applyReviewFilters(ITEMS, { ...DEFAULT_REVIEW_FILTERS, confidenceTier: "low" })
        .map((i) => i.id)
        .sort(),
    ).toEqual(["c", "d"]);
  });

  it("filters by inclusive date range on created_at", () => {
    const out = applyReviewFilters(ITEMS, {
      ...DEFAULT_REVIEW_FILTERS,
      dateFrom: "2026-07-05",
      dateTo: "2026-07-10",
    });
    expect(out.map((i) => i.id).sort()).toEqual(["b", "c"]);
  });

  it("filters by text search over title and payload", () => {
    expect(
      applyReviewFilters(ITEMS, { ...DEFAULT_REVIEW_FILTERS, search: "ashen" }).map((i) => i.id),
    ).toEqual(["a"]);
    // search also reaches into the serialized content
    expect(
      applyReviewFilters(ITEMS, { ...DEFAULT_REVIEW_FILTERS, search: "hollow" }).map((i) => i.id),
    ).toEqual(["b"]);
  });

  it("combines filters (status + confidence tier + search)", () => {
    const out = applyReviewFilters(ITEMS, {
      ...DEFAULT_REVIEW_FILTERS,
      status: "pending",
      confidenceTier: "medium",
      search: "moon",
    });
    expect(out.map((i) => i.id)).toEqual(["b"]);
  });

  it("sorts newest, oldest, and by confidence", () => {
    const newest = applyReviewFilters(ITEMS, { ...DEFAULT_REVIEW_FILTERS, sort: "newest" });
    expect(newest.map((i) => i.id)).toEqual(["d", "c", "b", "a"]);
    const oldest = applyReviewFilters(ITEMS, { ...DEFAULT_REVIEW_FILTERS, sort: "oldest" });
    expect(oldest.map((i) => i.id)).toEqual(["a", "b", "c", "d"]);
    const byConf = applyReviewFilters(ITEMS, { ...DEFAULT_REVIEW_FILTERS, sort: "confidence" });
    expect(byConf.map((i) => i.id)).toEqual(["a", "b", "c", "d"]);
  });
});

// ─── URL state ───────────────────────────────────────────────

describe("scopeFromParams", () => {
  it("defaults to pack, honors ?scope= and the ?job= deep link", () => {
    expect(scopeFromParams(new URLSearchParams())).toBe("pack");
    expect(scopeFromParams(new URLSearchParams("scope=story"))).toBe("story");
    expect(scopeFromParams(new URLSearchParams("scope=ingest"))).toBe("ingest");
    expect(scopeFromParams(new URLSearchParams("job=abc"))).toBe("ingest");
    expect(scopeFromParams(new URLSearchParams("scope=bogus"))).toBe("pack");
  });
});

describe("filtersFromParams", () => {
  it("returns defaults for an empty query", () => {
    expect(filtersFromParams(new URLSearchParams())).toEqual(DEFAULT_REVIEW_FILTERS);
  });

  it("parses a full filter set from the query", () => {
    const params = new URLSearchParams(
      "status=pending&type=entity&conf=high&from=2026-07-01&to=2026-07-31&q=moon&sort=confidence",
    );
    expect(filtersFromParams(params)).toEqual({
      status: "pending",
      changeType: "entity",
      confidenceTier: "high",
      dateFrom: "2026-07-01",
      dateTo: "2026-07-31",
      search: "moon",
      sort: "confidence",
    });
  });

  it("falls back to defaults for invalid values", () => {
    const params = new URLSearchParams("status=weird&conf=extreme&sort=random");
    expect(filtersFromParams(params)).toEqual(DEFAULT_REVIEW_FILTERS);
  });
});

describe("reviewParamsToSearch", () => {
  it("omits default-valued filters and preserves deep-link params", () => {
    const base = new URLSearchParams("pack=pack-1");
    const out = reviewParamsToSearch(base, "pack", DEFAULT_REVIEW_FILTERS);
    expect(out.get("pack")).toBe("pack-1");
    expect(out.get("scope")).toBe("pack");
    expect(out.get("status")).toBeNull();
    expect(out.get("q")).toBeNull();
    expect(out.get("sort")).toBeNull();
  });

  it("round-trips a non-default filter set", () => {
    const filters = {
      status: "accepted" as const,
      changeType: "event",
      confidenceTier: "low" as const,
      dateFrom: "2026-07-01",
      dateTo: "2026-07-31",
      search: "festival",
      sort: "oldest" as const,
    };
    const out = reviewParamsToSearch(new URLSearchParams(), "story", filters);
    expect(out.get("scope")).toBe("story");
    expect(filtersFromParams(out)).toEqual(filters);
  });
});
