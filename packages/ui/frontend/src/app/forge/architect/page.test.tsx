// @vitest-environment happy-dom
/**
 * Architect page tests (F2-1 wave 2):
 * - clicking a coverage gap injects the suggested prompt into the composer
 * - coverage query is invalidated when an architect turn settles
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { architectApi, chatApi, graphApi, universesApi } from "@/lib/api";
import type { Multiverse, Session, Universe, WorldCoverage } from "@/lib/types";
import ArchitectPage from "./page";

// ─── Module mocks ─────────────────────────────────────────────

// ReactFlow doesn't run under happy-dom; the mini graph is irrelevant here.
vi.mock("@xyflow/react", () => ({
  ReactFlow: () => null,
  Background: () => null,
  BackgroundVariant: { Dots: "dots" },
  Controls: () => null,
  Handle: () => null,
  Position: { Top: "top", Bottom: "bottom", Left: "left", Right: "right" },
  useNodesState: (init: unknown) => [init, () => {}, () => {}],
  useEdgesState: (init: unknown) => [init, () => {}, () => {}],
}));

// Capture the page's turn-settled callback; keep the real Composer so the
// composer-injection path is exercised end to end.
const captured = vi.hoisted(() => ({
  onTurnSettled: undefined as ((sessionId: string) => void) | undefined,
}));

vi.mock("@/features/chat", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/features/chat")>();
  return {
    ...mod,
    useChatSession: (opts: { onTurnSettled?: (sessionId: string) => void }) => {
      captured.onTurnSettled = opts.onTurnSettled;
      return {
        messages: [],
        streamingMsg: null,
        isTyping: false,
        sendFailure: null,
        status: "connected",
        send: vi.fn(),
        retry: vi.fn(),
        dismissFailure: vi.fn(),
      };
    },
    ChatList: () => null,
  };
});

// ─── Fixtures ─────────────────────────────────────────────────

const MV: Multiverse = {
  id: "mv-1",
  name: "Prime",
  description: null,
  tags: [],
  universe_count: 1,
  created_at: "2026-07-24T00:00:00Z",
};

const UV: Universe = {
  id: "uv-1",
  name: "Aethoria",
  multiverse_id: "mv-1",
  genre: "fantasy",
  description: null,
  tags: [],
  is_active: true,
  entity_count: 2,
  session_count: 0,
  created_at: "2026-07-24T00:00:00Z",
};

const SESSION: Session = {
  id: "s-1",
  title: "World Architect session",
  mode: "world_architect",
  multiverse_id: "mv-1",
  universe_id: null,
  world_id: null,
  character_id: null,
  created_at: "2026-07-24T00:00:00Z",
  updated_at: "2026-07-24T00:00:00Z",
  message_count: 0,
};

function coverageFixture(): WorldCoverage {
  const dim = { status: "ok" as const, gaps: [] };
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
      ...dim,
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
    entity_taxonomy: { ...dim, total: 2, by_type: {}, detail_histogram: {}, stub_count: 0 },
    fact_taxonomy: {
      ...dim,
      total_active: 0,
      by_type: {},
      with_entity_refs: 0,
      with_provenance: 0,
      current_conflict: 0,
      historical_founding: 0,
    },
    axioms: { ...dim, total: 1, domains: ["metaphysics"] },
    relationships: {
      status: "thin",
      gaps: [
        {
          code: "factions_without_members",
          message: "Factions without members: Iron Brotherhood.",
        },
      ],
      total_edges: 1,
      by_category: {},
      isolated_entities: [],
      factions_without_members: ["Iron Brotherhood"],
      npcs_without_affiliations: [],
    },
    mechanics: {
      ...dim,
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
      ...dim,
      applicable: false,
      total: 0,
      by_type: {},
      linked_to_universe: 0,
      linked_to_system: 0,
    },
    provenance: {
      ...dim,
      primitives_total: 3,
      with_source_refs: 0,
      with_evidence: 0,
      avg_confidence: null,
      by_canon_level: {},
      pending_review: 0,
      ingested_material: false,
    },
    floor_met: true,
    overall_status: "thin",
  };
}

// ─── Setup ────────────────────────────────────────────────────

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ArchitectPage />
    </QueryClientProvider>,
  );
}

/** Drive the page to the point where the coverage panel is loaded. */
async function settleToCoverage() {
  const user = userEvent.setup();
  renderPage();

  // Multiverse auto-selects; pick the universe to arm the coverage query.
  await screen.findByRole("option", { name: "Aethoria" });
  const universeSelect = screen.getByDisplayValue("All universes");
  await user.selectOptions(universeSelect, "uv-1");

  await screen.findByText("Factions without members: Iron Brotherhood.");
  return user;
}

let coverageSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.restoreAllMocks();
  captured.onTurnSettled = undefined;
  vi.spyOn(universesApi, "listMultiverses").mockResolvedValue([MV]);
  vi.spyOn(universesApi, "listUniverses").mockResolvedValue([UV]);
  vi.spyOn(chatApi, "listSessions").mockResolvedValue([]);
  vi.spyOn(chatApi, "createSession").mockResolvedValue(SESSION);
  vi.spyOn(graphApi, "getWorldGraph").mockResolvedValue({ nodes: [], edges: [] });
  coverageSpy = vi.spyOn(architectApi, "coverage").mockResolvedValue(coverageFixture());
});

// ─── Tests ────────────────────────────────────────────────────

describe("Architect page — gap-driven building (F2-1)", () => {
  it("clicking a coverage gap injects the suggested prompt into the composer", async () => {
    const user = await settleToCoverage();

    await user.click(screen.getByText("Factions without members: Iron Brotherhood."));

    const textarea = screen.getByPlaceholderText(/Describe what to add to the world/);
    expect(textarea).toHaveValue("Add a faction with members.");
  });

  it("invalidates the coverage query when an architect turn settles", async () => {
    await settleToCoverage();

    expect(coverageSpy).toHaveBeenCalledTimes(1);
    expect(captured.onTurnSettled).toBeDefined();

    await act(async () => {
      captured.onTurnSettled!("s-1");
    });

    await waitFor(() => expect(coverageSpy).toHaveBeenCalledTimes(2));
  });
});
