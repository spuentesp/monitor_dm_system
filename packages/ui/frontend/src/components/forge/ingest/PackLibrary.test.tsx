// @vitest-environment happy-dom
/**
 * PackLibrary tests (F1-6):
 * - the per-pack "Apply" button router-pushes into the /forge/apply wizard
 *   with the right ?pack= query param (the inline canonizePack flow is gone)
 * - retired API surface: nothing references canonizePack / activateUniverse
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ingestApi } from "@/lib/api";
import type { KnowledgePack } from "@/lib/types";
import { PackLibrary } from "./PackLibrary";

// ─── next/navigation mock ─────────────────────────────────────

const nav = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push }),
}));

// ─── Fixtures ─────────────────────────────────────────────────

function pack(id: string, name: string, status = "ready"): KnowledgePack {
  return {
    id,
    name,
    description: null,
    pack_type: "setting",
    status,
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

function renderLibrary() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PackLibrary />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  nav.push.mockReset();
  vi.spyOn(ingestApi, "listPacks").mockResolvedValue([pack("p-1", "Ashen Vale Pack")]);
});

// ─── Apply deep-link ──────────────────────────────────────────

describe("PackLibrary — apply deep link (F1-6)", () => {
  it("Apply navigates to /forge/apply with the pack preselected", async () => {
    const user = userEvent.setup();
    renderLibrary();

    await user.click(await screen.findByRole("button", { name: /^apply$/i }));

    expect(nav.push).toHaveBeenCalledWith("/forge/apply?pack=p-1");
  });

  it("no longer fires the retired canonizePack wrapper", async () => {
    const user = userEvent.setup();
    renderLibrary();

    await user.click(await screen.findByRole("button", { name: /^apply$/i }));

    expect("canonizePack" in ingestApi).toBe(false);
  });
});

// ─── Retired API surface grep-asserts ─────────────────────────

describe("retired API surface (F1-5c, F1-6)", () => {
  it("lib/api.ts has no activateUniverse or canonizePack", () => {
    const src = readFileSync(join(__dirname, "../../../lib/api.ts"), "utf8");
    expect(src).not.toContain("activateUniverse");
    expect(src).not.toContain("canonizePack");
  });

  it("PackLibrary has no inline canonize flow left", () => {
    const src = readFileSync(join(__dirname, "PackLibrary.tsx"), "utf8");
    expect(src).not.toContain("canonizePack");
    expect(src).not.toContain("confirmCanonize");
    expect(src).not.toContain("setApplyingId");
  });
});
