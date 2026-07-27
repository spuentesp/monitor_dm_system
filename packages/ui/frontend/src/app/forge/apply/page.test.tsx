// @vitest-environment happy-dom
/**
 * Apply wizard tests (F1-6 / MP-7 / MP-8):
 * - ?pack=<id> preselects the pack: the wizard loads exactly that pack and
 *   shows its name on the target step (the PackLibrary + packs-hub Apply
 *   buttons both deep-link this way).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ingestApi } from "@/lib/api";
import type { KnowledgePack } from "@/lib/types";
import ApplyPackPage from "./page";

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

function renderWizard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ApplyPackPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  nav.params = "";
  nav.push.mockReset();
  nav.back.mockReset();
});

// ─── ?pack= preselection ──────────────────────────────────────

describe("Apply wizard — ?pack= preselection (F1-6)", () => {
  it("loads the pack named in ?pack= and shows it on the target step", async () => {
    nav.params = "pack=p-1";
    const getPack = vi.spyOn(ingestApi, "getPack").mockResolvedValue(pack("p-1", "Ashen Vale Pack"));

    renderWizard();

    expect(await screen.findByText("Ashen Vale Pack")).toBeInTheDocument();
    expect(getPack).toHaveBeenCalledWith("p-1");
    // Target step renders for the preselected pack.
    expect(screen.getByText(/where do you want to apply this pack/i)).toBeInTheDocument();
  });
});
