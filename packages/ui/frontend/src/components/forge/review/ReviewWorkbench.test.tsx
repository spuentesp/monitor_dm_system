// @vitest-environment happy-dom
/**
 * Tests for the shared canon-review workbench (F2-3 a/b/c):
 * - filter bar drives the list (status / change type / confidence / search / sort)
 * - row click opens the detail/provenance drawer (create vs state_change payload)
 * - selection: per-row, select visible, clear
 * - bulk selected: reason dialog + batch payload
 * - select all matching: server-side preview token flow (by-filter endpoint)
 * - partial-failure rendering from the {results, errors} contract
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as api from "@/lib/api";
import type { ReviewFilters, ReviewItem } from "@/lib/reviewItem";
import { DEFAULT_REVIEW_FILTERS } from "@/lib/reviewItem";
import { ReviewWorkbench } from "./ReviewWorkbench";

const STORY_ID = "11111111-1111-1111-1111-111111111111";

function item(id: string, overrides: Partial<ReviewItem> = {}): ReviewItem {
  return {
    id,
    scope: "story",
    change_type: "fact",
    proposal_type: "create_lore_fact",
    status: "pending",
    pack_id: null,
    ingestion_job_id: null,
    story_id: STORY_ID,
    scene_id: "scene-1",
    turn_id: null,
    source: null,
    content: { statement: `Statement ${id}` },
    source_ref: null,
    evidence: [],
    confidence: 0.95,
    authority: "gm",
    proposer: "Narrator",
    canon_level: null,
    decision_reason: null,
    decided_by: null,
    decided_at: null,
    created_at: "2026-07-10T12:00:00Z",
    updated_at: null,
    ...overrides,
  };
}

function renderWorkbench(
  items: ReviewItem[],
  filters: ReviewFilters = DEFAULT_REVIEW_FILTERS,
  onFiltersChange: (f: ReviewFilters) => void = vi.fn(),
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onChanged = vi.fn();
  render(
    <QueryClientProvider client={qc}>
      <ReviewWorkbench
        items={items}
        emptyMessage="Nothing here"
        filters={filters}
        onFiltersChange={onFiltersChange}
        byFilterBase={{ story_id: STORY_ID }}
        onChanged={onChanged}
      />
    </QueryClientProvider>,
  );
  return { onChanged, onFiltersChange };
}

beforeEach(() => {
  vi.restoreAllMocks();
});

// ─── Filters ─────────────────────────────────────────────────

describe("ReviewWorkbench — filters (F2-3a)", () => {
  const items = [
    item("a", { status: "pending", change_type: "entity", confidence: 0.95, content: { name: "Ashen Duke", entity_type: "npc" } }),
    item("b", { status: "pending", change_type: "fact", confidence: 0.75 }),
    item("c", { status: "accepted", change_type: "state_change", confidence: 0.4 }),
  ];

  it("applies the status filter to the rendered list", () => {
    renderWorkbench(items, { ...DEFAULT_REVIEW_FILTERS, status: "pending" });
    expect(screen.getByTestId("review-row-a")).toBeInTheDocument();
    expect(screen.getByTestId("review-row-b")).toBeInTheDocument();
    expect(screen.queryByTestId("review-row-c")).not.toBeInTheDocument();
  });

  it("applies the change-type filter (including state_change)", () => {
    renderWorkbench(items, { ...DEFAULT_REVIEW_FILTERS, changeType: "state_change" });
    expect(screen.queryByTestId("review-row-a")).not.toBeInTheDocument();
    expect(screen.getByTestId("review-row-c")).toBeInTheDocument();
  });

  it("applies the confidence-tier filter", () => {
    renderWorkbench(items, { ...DEFAULT_REVIEW_FILTERS, confidenceTier: "high" });
    expect(screen.getByTestId("review-row-a")).toBeInTheDocument();
    expect(screen.queryByTestId("review-row-b")).not.toBeInTheDocument();
    expect(screen.queryByTestId("review-row-c")).not.toBeInTheDocument();
  });

  it("applies text search and combined filters", () => {
    renderWorkbench(items, {
      ...DEFAULT_REVIEW_FILTERS,
      status: "pending",
      search: "ashen",
    });
    expect(screen.getByTestId("review-row-a")).toBeInTheDocument();
    expect(screen.queryByTestId("review-row-b")).not.toBeInTheDocument();
  });

  it("sorts by confidence when selected", () => {
    renderWorkbench(items, { ...DEFAULT_REVIEW_FILTERS, sort: "confidence" });
    const rows = screen.getAllByTestId(/^review-row-/);
    expect(rows[0]).toHaveAttribute("data-testid", "review-row-a");
  });

  it("filter bar edits propagate via onFiltersChange", async () => {
    const onFiltersChange = vi.fn();
    const user = userEvent.setup();
    renderWorkbench(items, DEFAULT_REVIEW_FILTERS, onFiltersChange);

    await user.selectOptions(screen.getByLabelText(/filter by status/i), "pending");
    expect(onFiltersChange).toHaveBeenCalledWith({
      ...DEFAULT_REVIEW_FILTERS,
      status: "pending",
    });

    await user.selectOptions(screen.getByLabelText(/sort proposals/i), "confidence");
    expect(onFiltersChange).toHaveBeenCalledWith({
      ...DEFAULT_REVIEW_FILTERS,
      sort: "confidence",
    });
  });
});

// ─── Detail / provenance drawer ──────────────────────────────

describe("ReviewWorkbench — detail drawer (F2-3b)", () => {
  it("opens the drawer on row click and shows provenance + proposed value", async () => {
    const decided = item("p1", {
      status: "accepted",
      content: { statement: "The moon is hollow", source_ref: "p. 42" },
      source_ref: "p. 42",
      canon_level: "core",
      decision_reason: "Fits canon",
      decided_by: "GM",
      decided_at: "2026-07-11T08:30:00Z",
      evidence: [{ type: "snippet", ref_id: "snip-1" }],
    });
    const user = userEvent.setup();
    renderWorkbench([decided]);

    await user.click(screen.getByTestId("review-row-p1"));

    const drawer = await screen.findByTestId("review-detail-drawer");
    expect(within(drawer).getByText("Proposed value")).toBeInTheDocument();
    // statement appears as the title, in the payload table, and raw payload
    expect(within(drawer).getAllByText("The moon is hollow").length).toBeGreaterThan(0);
    expect(within(drawer).getByText("create_lore_fact")).toBeInTheDocument();
    expect(within(drawer).getAllByText("p. 42").length).toBeGreaterThan(0);
    expect(within(drawer).getByText("core")).toBeInTheDocument();
    expect(within(drawer).getByText("Fits canon")).toBeInTheDocument();
    expect(within(drawer).getByText("snippet:snip-1")).toBeInTheDocument();
    expect(within(drawer).getByText(/story \/ scene/i)).toBeInTheDocument();

    await user.click(within(drawer).getByRole("button", { name: /close detail/i }));
    await waitFor(() =>
      expect(screen.queryByTestId("review-detail-drawer")).not.toBeInTheDocument(),
    );
  });

  it("renders explicit Added/Removed sections for state_change payloads", async () => {
    const sc = item("s1", {
      change_type: "state_change",
      proposal_type: "update_entity_state",
      content: { name: "Torch", add_tags: ["lit"], remove_tags: ["cold"] },
    });
    const user = userEvent.setup();
    renderWorkbench([sc]);

    await user.click(screen.getByTestId("review-row-s1"));

    const drawer = await screen.findByTestId("review-detail-drawer");
    // state_change payloads are labelled "Payload", never "diff"
    expect(within(drawer).getByText("Payload")).toBeInTheDocument();
    expect(within(drawer).queryByText(/diff/i)).not.toBeInTheDocument();
    expect(within(drawer).getByText("Added")).toBeInTheDocument();
    expect(within(drawer).getByText('["lit"]')).toBeInTheDocument();
    expect(within(drawer).getByText("Removed")).toBeInTheDocument();
    expect(within(drawer).getByText('["cold"]')).toBeInTheDocument();
  });
});

// ─── Selection + bulk ergonomics ─────────────────────────────

describe("ReviewWorkbench — selection and bulk verdicts (F2-3c)", () => {
  it("selects visible pending rows and clears the selection", async () => {
    const items = [item("a"), item("b"), item("c", { status: "accepted" })];
    const user = userEvent.setup();
    renderWorkbench(items);

    await user.click(screen.getByRole("button", { name: /select visible \(2\)/i }));
    expect(screen.getByText("2 selected")).toBeInTheDocument();
    // accepted rows have no checkbox and are never selected
    expect(screen.queryByRole("checkbox", { name: /select proposal statement c/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^clear$/i }));
    expect(screen.queryByText(/selected/)).not.toBeInTheDocument();
  });

  it("per-row checkbox toggles selection", async () => {
    const user = userEvent.setup();
    renderWorkbench([item("a"), item("b")]);

    await user.click(screen.getByRole("checkbox", { name: /select proposal statement a/i }));
    expect(screen.getByText("1 selected")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /select proposal statement a/i }));
    expect(screen.queryByText(/selected/)).not.toBeInTheDocument();
  });

  it("accepts selected rows with the shared reason dialog", async () => {
    const verdictSpy = vi.spyOn(api.canonApi, "batchVerdicts")
      .mockResolvedValue({ results: [], errors: [] });
    const { onChanged } = renderWorkbench([item("a"), item("b")]);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /select visible \(2\)/i }));
    await user.click(screen.getByRole("button", { name: /accept selected/i }));

    // Confirmation shows the affected count
    expect(await screen.findByText(/accept 2 proposals\?/i)).toBeInTheDocument();
    const reasonBox = screen.getByLabelText(/decision reason/i);
    await user.clear(reasonBox);
    await user.type(reasonBox, "Triage sweep");
    await user.click(screen.getByRole("button", { name: /confirm accept \(2\)/i }));

    await waitFor(() =>
      expect(verdictSpy).toHaveBeenCalledWith([
        { proposal_id: "a", decision: "accepted", reason: "Triage sweep" },
        { proposal_id: "b", decision: "accepted", reason: "Triage sweep" },
      ]),
    );
    expect(onChanged).toHaveBeenCalled();
  });

  it("rejects selected rows with a reason", async () => {
    const verdictSpy = vi.spyOn(api.canonApi, "batchVerdicts")
      .mockResolvedValue({ results: [], errors: [] });
    renderWorkbench([item("a")]);
    const user = userEvent.setup();

    await user.click(screen.getByRole("checkbox", { name: /select proposal statement a/i }));
    await user.click(screen.getByRole("button", { name: /reject selected/i }));
    await user.click(await screen.findByRole("button", { name: /confirm reject \(1\)/i }));

    await waitFor(() =>
      expect(verdictSpy).toHaveBeenCalledWith([
        { proposal_id: "a", decision: "rejected", reason: "Batch rejected by GM" },
      ]),
    );
  });

  it("renders per-item failures from the {results, errors} contract", async () => {
    vi.spyOn(api.canonApi, "batchVerdicts").mockResolvedValue({
      results: [{
        proposal_id: "a",
        status: "accepted",
        decision_metadata: { decided_by: "GM", decided_at: "", reason: "" },
      }],
      errors: [{ proposal_id: "b", error: "Proposal already decided" }],
    });
    const user = userEvent.setup();
    renderWorkbench([item("a"), item("b")]);

    await user.click(screen.getByRole("button", { name: /select visible \(2\)/i }));
    await user.click(screen.getByRole("button", { name: /accept selected/i }));
    await user.click(await screen.findByRole("button", { name: /confirm accept \(2\)/i }));

    const outcome = await screen.findByTestId("verdict-outcome");
    expect(within(outcome).getByText(/1 accepted, 1 failed/)).toBeInTheDocument();
    expect(within(outcome).getByText(/b: Proposal already decided/)).toBeInTheDocument();
  });

  it("select all matching resolves server-side with a preview token", async () => {
    const byFilterSpy = vi.spyOn(api.canonApi, "verdictsByFilter").mockResolvedValue({
      affected_count: 37,
      preview_token: "tok-1",
      results: [],
      errors: [],
    });
    const filters: ReviewFilters = {
      ...DEFAULT_REVIEW_FILTERS,
      changeType: "fact",
      confidenceTier: "high",
    };
    const user = userEvent.setup();
    renderWorkbench([item("a")], filters);

    await user.click(screen.getByRole("button", { name: /accept all matching/i }));

    // Phase 1: dry-run preview carries the scope + active filters
    await waitFor(() =>
      expect(byFilterSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          decision: "accepted",
          story_id: STORY_ID,
          change_type: "fact",
          confidence_min: 0.9,
          dry_run: true,
        }),
      ),
    );

    // Confirmation shows the SERVER count, not the loaded-row count
    expect(await screen.findByText(/accept 37 proposals\?/i)).toBeInTheDocument();
    expect(screen.getByText(/resolved server-side/i)).toBeInTheDocument();

    byFilterSpy.mockResolvedValue({
      affected_count: 37,
      preview_token: null,
      results: [],
      errors: [],
    });
    await user.click(screen.getByRole("button", { name: /confirm accept \(37\)/i }));

    // Phase 2: execute with the preview token
    await waitFor(() =>
      expect(byFilterSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          dry_run: false,
          preview_token: "tok-1",
          reason: "Batch approved by GM",
        }),
      ),
    );
  });

  it("quick per-row verdict goes through batchVerdicts", async () => {
    const verdictSpy = vi.spyOn(api.canonApi, "batchVerdicts")
      .mockResolvedValue({ results: [], errors: [] });
    const user = userEvent.setup();
    renderWorkbench([item("a")]);

    await user.click(screen.getByTitle("Accept"));

    await waitFor(() =>
      expect(verdictSpy).toHaveBeenCalledWith([
        { proposal_id: "a", decision: "accepted", reason: "Approved in Forge review" },
      ]),
    );
  });
});

// ─── state_change / event rows ───────────────────────────────

describe("ReviewWorkbench — state_change/event rendering (F2-3f)", () => {
  it("renders state_change and event rows with their change-type badges", () => {
    renderWorkbench([
      item("sc", { change_type: "state_change", content: { name: "Torch", add_tags: ["lit"] } }),
      item("ev", { change_type: "event", content: { name: "Festival of Embers" } }),
    ]);
    const scRow = screen.getByTestId("review-row-sc");
    const evRow = screen.getByTestId("review-row-ev");
    expect(within(scRow).getByText("state_change")).toBeInTheDocument();
    expect(within(scRow).getByText("Torch")).toBeInTheDocument();
    expect(within(evRow).getByText("event")).toBeInTheDocument();
    expect(within(evRow).getByText("Festival of Embers")).toBeInTheDocument();
  });
});
