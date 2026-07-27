// @vitest-environment happy-dom
/**
 * World-creation wizard tests (F1-3):
 * - method picker renders all five methods and switches between them
 * - Blank: pick setting → universe form → submit → confirm lands on
 *   /forge/worlds?universe=<id>
 * - From pack: pack rows router-push into the /forge/apply wizard
 * - Quick seed: shared QuickSeedForm submits and its result card links
 *   into the Worlds tree
 * - Demo: forgeApi.demoWorld → confirm with Play + Open links
 * - Fork: ?method=fork&universe=<id> deep link preselects the source
 *   universe (Snapshots page entry point)
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WorldContextProvider } from "@/lib/world-context";
import { forgeApi, ingestApi, universesApi, type QuickWorldResult } from "@/lib/api";
import type { KnowledgePack, Multiverse, Universe } from "@/lib/types";
import NewWorldPage from "./page";

// ─── next/navigation mock ─────────────────────────────────────

const nav = vi.hoisted(() => ({
  params: "",
  push: vi.fn(),
  back: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(nav.params),
  useRouter: () => ({ push: nav.push, back: nav.back }),
}));

// ─── Fixtures ─────────────────────────────────────────────────

function multiverse(id: string, name: string): Multiverse {
  return {
    id,
    name,
    description: null,
    tags: [],
    universe_count: 1,
    created_at: "2026-07-01T00:00:00Z",
  };
}

function universe(id: string, name: string, mv = "mv-1"): Universe {
  return {
    id,
    name,
    multiverse_id: mv,
    genre: "Fantasy",
    description: null,
    tags: [],
    is_active: true,
    entity_count: 3,
    session_count: 0,
    created_at: "2026-07-01T00:00:00Z",
  };
}

function pack(id: string, name: string): KnowledgePack {
  return {
    id,
    name,
    description: null,
    pack_type: "setting",
    status: "ready",
    system_name: null,
    game_system_id: null,
    game_system: null,
    game_system_data: null,
    source_profile_data: null,
    chunk_summaries: [],
    section_summaries: [],
    source_mindscape: null,
    tags: [],
    axiom_count: 1,
    entity_count: 2,
    lore_fact_count: 3,
    axioms: [],
    entity_archetypes: [],
    lore_facts: [],
    entity_relationships: [],
    created_at: "2026-07-02T00:00:00Z",
    updated_at: null,
    applied_to: [],
    parent_pack_ids: [],
    source_document_ids: [],
  };
}

function quickResult(overrides: Partial<QuickWorldResult> = {}): QuickWorldResult {
  return {
    multiverse_id: "mv-new",
    universe_id: "u-new",
    world_name: "Fogharbor",
    world_description: "A rain-soaked harbor city.",
    axiom: "The drowned barter for memories.",
    opening_scene: "You step off the last ferry.",
    pc_concept: "A debt-ridden ferryman",
    entities: [],
    lore_facts: [],
    committed: 6,
    errors: [],
    session_id: null,
    ...overrides,
  };
}

// ─── Render helper ────────────────────────────────────────────

function renderWizard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <WorldContextProvider>
        <NewWorldPage />
      </WorldContextProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  nav.params = "";
  nav.push.mockReset();
  nav.back.mockReset();
  window.localStorage.clear();
  vi.spyOn(universesApi, "listMultiverses").mockResolvedValue([multiverse("mv-1", "The Mistlands")]);
  vi.spyOn(universesApi, "listUniverses").mockResolvedValue([universe("u-1", "Ashen Vale")]);
  vi.spyOn(ingestApi, "listPacks").mockResolvedValue([pack("p-1", "Ashen Vale Pack")]);
});

// ─── Method picker ────────────────────────────────────────────

describe("World wizard — method picker", () => {
  it("renders all five methods and switches into one", async () => {
    const user = userEvent.setup();
    renderWizard();

    for (const m of ["blank", "quick", "pack", "fork", "demo"]) {
      expect(screen.getByTestId(`method-${m}`)).toBeInTheDocument();
    }

    await user.click(screen.getByTestId("method-quick"));
    expect(await screen.findByText("Your seed")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /all methods/i }));
    expect(await screen.findByTestId("method-blank")).toBeInTheDocument();
  });
});

// ─── Blank ────────────────────────────────────────────────────

describe("World wizard — blank method", () => {
  it("creates a universe in a picked setting and lands on the confirm step", async () => {
    const created = universe("u-created", "New Vale");
    const createUniverse = vi.spyOn(universesApi, "createUniverse").mockResolvedValue(created);

    const user = userEvent.setup();
    renderWizard();

    await user.click(screen.getByTestId("method-blank"));
    // Step 2a: pick the existing setting.
    await user.click(await screen.findByRole("button", { name: /the mistlands/i }));

    // Step 2b: the shared CreateUniverseForm appears.
    const nameInput = await screen.findByPlaceholderText(/universe name…/i);
    await user.type(nameInput, "New Vale");
    await user.click(screen.getByRole("button", { name: /create universe/i }));

    await waitFor(() =>
      expect(createUniverse).toHaveBeenCalledWith({
        name: "New Vale",
        multiverse_id: "mv-1",
        genre: undefined,
        description: undefined,
      }),
    );

    // Step 3: confirm + land on /forge/worlds?universe=<id>.
    expect(await screen.findByText(/is ready\./)).toBeInTheDocument();
    expect(screen.getByTestId("confirm-open-world")).toHaveAttribute(
      "href",
      "/forge/worlds?universe=u-created",
    );
  });
});

// ─── From pack ────────────────────────────────────────────────

describe("World wizard — from-pack method", () => {
  it("router-pushes into the apply wizard when a pack is picked", async () => {
    const user = userEvent.setup();
    renderWizard();

    await user.click(screen.getByTestId("method-pack"));
    await user.click(await screen.findByRole("button", { name: /ashen vale pack/i }));

    expect(nav.push).toHaveBeenCalledWith("/forge/apply?pack=p-1");
  });
});

// ─── Quick seed ───────────────────────────────────────────────

describe("World wizard — quick-seed method", () => {
  it("submits the shared QuickSeedForm and links into the Worlds tree", async () => {
    const quickWorld = vi
      .spyOn(forgeApi, "quickWorld")
      .mockResolvedValue(quickResult());

    const user = userEvent.setup();
    renderWizard();

    await user.click(screen.getByTestId("method-quick"));
    await user.type(await screen.findByPlaceholderText(/rain-soaked harbor city/i), "A city of glass and salt");
    await user.click(screen.getByRole("button", { name: /forge world/i }));

    await waitFor(() =>
      expect(quickWorld).toHaveBeenCalledWith(
        expect.objectContaining({ seed: "A city of glass and salt" }),
      ),
    );

    // The result card is the confirm-and-land UI.
    const openInTree = await screen.findByRole("link", { name: /open in tree/i });
    expect(openInTree).toHaveAttribute("href", "/forge/worlds?universe=u-new");
  });
});

// ─── Demo ─────────────────────────────────────────────────────

describe("World wizard — demo method", () => {
  it("creates the demo world and confirms with Play + Open links", async () => {
    const demoWorld = vi
      .spyOn(forgeApi, "demoWorld")
      .mockResolvedValue(quickResult({ world_name: "Millhaven", session_id: "sess-1", reused: false }));

    const user = userEvent.setup();
    renderWizard();

    await user.click(screen.getByTestId("method-demo"));
    await user.click(await screen.findByRole("button", { name: /create demo world/i }));

    await waitFor(() => expect(demoWorld).toHaveBeenCalledWith(true));

    expect(await screen.findByText(/is ready\./)).toBeInTheDocument();
    expect(screen.getByTestId("confirm-open-world")).toHaveAttribute(
      "href",
      "/forge/worlds?universe=u-new",
    );
    expect(screen.getByRole("link", { name: /play now/i })).toHaveAttribute(
      "href",
      "/play?session=sess-1",
    );
  });
});

// ─── Fork (deep link from Snapshots) ──────────────────────────

describe("World wizard — fork method", () => {
  it("preselects the universe from ?method=fork&universe= and forks it", async () => {
    nav.params = "method=fork&universe=u-1";
    const forkUniverse = vi.spyOn(universesApi, "forkUniverse").mockResolvedValue({
      source_universe_id: "u-1",
      new_universe_id: "u-fork",
      name: "Ashen Vale — branch",
      entities_cloned: 3,
      relationships_cloned: 2,
      status: "forked",
    });

    const user = userEvent.setup();
    renderWizard();

    // Straight into step 2 with the source universe preselected.
    const sourceRow = await screen.findByRole("button", { name: /ashen vale/i });
    expect(sourceRow).toHaveClass("bg-purple-500/10");

    await user.type(screen.getByPlaceholderText(/what-if branch/i), "Ashen Vale — branch");
    await user.click(screen.getByRole("button", { name: /fork universe/i }));

    await waitFor(() =>
      expect(forkUniverse).toHaveBeenCalledWith("u-1", { name: "Ashen Vale — branch" }),
    );

    expect(await screen.findByText(/3 entities and 2 relationships cloned\./)).toBeInTheDocument();
    expect(screen.getByTestId("confirm-open-world")).toHaveAttribute(
      "href",
      "/forge/worlds?universe=u-fork",
    );
  });
});
