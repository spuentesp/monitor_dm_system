// @vitest-environment happy-dom
/**
 * CoveragePanel tests (F2-1 wave 2):
 * - the 8 coverage dimensions render as cards with icon+text status badges
 * - gaps are listed and clickable → composer prompt suggestion
 * - non-applicable mechanics / random-tables cards render muted, not failed
 * - floor indicator (identity + ≥1 axiom) and overall status
 * - applicability toggles re-fetch coverage with the require_* flags
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { architectApi } from "@/lib/api";
import type { WorldCoverage } from "@/lib/types";
import { CoveragePanel } from "./CoveragePanel";

export function coverageFixture(over: Partial<WorldCoverage> = {}): WorldCoverage {
  return {
    universe_id: "uv-1",
    computed_at: "2026-07-24T00:00:00Z",
    thresholds: {
      min_axioms: 1,
      min_entities: 5,
      min_facts: 1,
      thin_fact_count: 5,
      conflict_magnitude: 5,
      max_isolated_ratio: 0.5,
      min_provenance_ratio: 0.5,
      min_random_tables: 3,
      require_mechanics: false,
      require_random_tables: false,
    },
    identity: {
      status: "ok",
      gaps: [],
      has_name: true,
      has_genre: true,
      has_tone: true,
      has_narrative_frame: true,
      has_default_system: false,
      name: "Aethoria",
      genre: "fantasy",
      tone: "grim",
      default_system_name: null,
    },
    entity_taxonomy: {
      status: "thin",
      gaps: [{ code: "few_entities", message: "Only 2 entities (baseline: 5)." }],
      total: 2,
      by_type: { character: 1, faction: 1 },
      detail_histogram: { character: { stub: 1 }, faction: { full: 1 } },
      stub_count: 1,
    },
    fact_taxonomy: {
      status: "missing",
      gaps: [{ code: "no_facts", message: "No active lore facts recorded." }],
      total_active: 0,
      by_type: {},
      with_entity_refs: 0,
      with_provenance: 0,
      current_conflict: 0,
      historical_founding: 0,
    },
    axioms: { status: "ok", gaps: [], total: 1, domains: ["metaphysics"] },
    relationships: {
      status: "thin",
      gaps: [
        {
          code: "factions_without_members",
          message: "Factions without members: Iron Brotherhood.",
        },
      ],
      total_edges: 1,
      by_category: { membership: 1 },
      isolated_entities: [],
      factions_without_members: ["Iron Brotherhood"],
      npcs_without_affiliations: [],
    },
    mechanics: {
      status: "missing",
      gaps: [{ code: "no_linked_system", message: "No game system is linked to this universe." }],
      applicable: false,
      has_linked_system: false,
      system_name: null,
      has_core_mechanic: false,
      success_method: null,
      attribute_count: 0,
      skill_count: 0,
      resolution_mechanic_count: 0,
      has_combat_rules: false,
      has_social_rules: false,
      condition_count: 0,
      has_advancement: false,
      has_character_creation: false,
    },
    random_tables: {
      status: "missing",
      gaps: [{ code: "no_random_tables", message: "No random tables available." }],
      applicable: false,
      total: 0,
      by_type: {},
      linked_to_universe: 0,
      linked_to_system: 0,
    },
    provenance: {
      status: "ok",
      gaps: [],
      primitives_total: 3,
      with_source_refs: 0,
      with_evidence: 0,
      avg_confidence: 0.9,
      by_canon_level: { canon: 3 },
      pending_review: 0,
      ingested_material: false,
    },
    floor_met: true,
    overall_status: "thin",
    ...over,
  };
}

function renderPanel(onSuggestGap = vi.fn(), universeId: string | null = "uv-1") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <CoveragePanel universeId={universeId} onSuggestGap={onSuggestGap} />
    </QueryClientProvider>,
  );
  return onSuggestGap;
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("CoveragePanel", () => {
  it("renders all 8 dimension cards with icon+text status badges", async () => {
    vi.spyOn(architectApi, "coverage").mockResolvedValue(coverageFixture());
    renderPanel();

    for (const label of [
      "Identity",
      "Entities",
      "Facts",
      "Axioms",
      "Relationships",
      "Game System",
      "Random Tables",
      "Provenance",
    ]) {
      expect(await screen.findByText(label)).toBeInTheDocument();
    }
    // Status is text, not color-only.
    expect(screen.getAllByText("OK").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Thin").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Missing").length).toBeGreaterThanOrEqual(1);
    // Key counts per dimension.
    expect(screen.getByText("Aethoria")).toBeInTheDocument();
    expect(screen.getByText("metaphysics")).toBeInTheDocument();
  });

  it("lists gaps and a gap click suggests a composer prompt", async () => {
    vi.spyOn(architectApi, "coverage").mockResolvedValue(coverageFixture());
    const onSuggestGap = renderPanel();
    const user = userEvent.setup();

    const gap = await screen.findByText("Factions without members: Iron Brotherhood.");
    await user.click(gap);

    expect(onSuggestGap).toHaveBeenCalledWith("Add a faction with members.");
  });

  it("renders non-applicable mechanics/tables muted as 'Not required', not as failures", async () => {
    vi.spyOn(architectApi, "coverage").mockResolvedValue(coverageFixture());
    renderPanel();

    await screen.findByText("Game System");
    const notRequired = screen.getAllByText("Not required");
    expect(notRequired).toHaveLength(2);
    // Their gaps are suppressed — not surfaced as failures.
    expect(
      screen.queryByText("No game system is linked to this universe."),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("No random tables available.")).not.toBeInTheDocument();
  });

  it("renders applicable mechanics as a normal card with its gaps", async () => {
    const fixture = coverageFixture();
    fixture.mechanics = { ...fixture.mechanics, applicable: true };
    vi.spyOn(architectApi, "coverage").mockResolvedValue(fixture);
    const onSuggestGap = renderPanel();
    const user = userEvent.setup();

    const gap = await screen.findByText("No game system is linked to this universe.");
    // Only random tables remains muted; mechanics renders as a normal card.
    expect(screen.getAllByText("Not required")).toHaveLength(1);
    await user.click(gap);
    expect(onSuggestGap).toHaveBeenCalledWith("Link a game system to this universe.");
  });

  it("shows the floor indicator (identity + ≥1 axiom)", async () => {
    vi.spyOn(architectApi, "coverage").mockResolvedValue(coverageFixture());
    renderPanel();
    expect(await screen.findByText("Floor met")).toBeInTheDocument();
  });

  it("shows 'Floor not met' when the identity+axiom floor is missing", async () => {
    vi.spyOn(architectApi, "coverage").mockResolvedValue(
      coverageFixture({ floor_met: false, overall_status: "missing" }),
    );
    renderPanel();
    expect(await screen.findByText("Floor not met")).toBeInTheDocument();
  });

  it("re-fetches with require_mechanics when the toggle is enabled", async () => {
    const spy = vi.spyOn(architectApi, "coverage").mockResolvedValue(coverageFixture());
    renderPanel();
    const user = userEvent.setup();

    await screen.findByText("Identity");
    expect(spy).toHaveBeenLastCalledWith("uv-1", {
      require_mechanics: false,
      require_random_tables: false,
    });

    await user.click(screen.getByLabelText("Coverage settings"));
    await user.click(screen.getByLabelText(/Mechanical play/));

    await screen.findByText("Identity");
    await vi.waitFor(() =>
      expect(spy).toHaveBeenLastCalledWith("uv-1", {
        require_mechanics: true,
        require_random_tables: false,
      }),
    );
  });

  it("prompts to select a universe when none is selected", () => {
    const spy = vi.spyOn(architectApi, "coverage").mockResolvedValue(coverageFixture());
    renderPanel(vi.fn(), null);
    expect(screen.getByText("Select a universe to see coverage")).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });
});
