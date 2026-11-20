// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { entitiesApi, universesApi } from "@/lib/api";
import type { RPGSystem, Universe } from "@/lib/types";
import { GMSelector } from "./GMSelector";

const UNIVERSE: Universe = {
  id: "u-1",
  name: "Alpha World",
  multiverse_id: "mv-1",
  genre: null,
  description: null,
  default_game_system_id: null,
  tags: [],
  is_active: true,
  entity_count: 0,
  session_count: 0,
  created_at: "2026-01-01T00:00:00Z",
};

const SYSTEM: RPGSystem = {
  id: "sys-1",
  name: "Bound System",
  description: null,
  version: null,
  core_mechanic: null,
  attributes: [],
  skills: [],
  resources: [],
  rules: [],
  is_builtin: false,
  source_document_id: null,
  character_count: 0,
  session_count: 0,
  needs_review: false,
  degenerate_reason: null,
} as RPGSystem;

function renderSelector(
  overrides: Partial<{
    universeId: string | null;
    systemId: string | null;
    onUniverseChange: (id: string | null, label?: string | null) => void;
    onSystemChange: (id: string | null) => void;
  }> = {},
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onUniverseChange = overrides.onUniverseChange ?? (() => {});
  const onSystemChange = overrides.onSystemChange ?? (() => {});
  return {
    onUniverseChange,
    onSystemChange,
    ...render(
      <QueryClientProvider client={qc}>
        <GMSelector
          universeId={overrides.universeId ?? null}
          systemId={overrides.systemId ?? null}
          onUniverseChange={onUniverseChange}
          onSystemChange={onSystemChange}
        />
      </QueryClientProvider>,
    ),
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(universesApi, "listMultiverses").mockResolvedValue([]);
  vi.spyOn(universesApi, "listUniverses").mockResolvedValue([UNIVERSE]);
  vi.spyOn(entitiesApi, "listSystems").mockResolvedValue([SYSTEM]);
});

describe("GMSelector", () => {
  it("reports universe picks with their label", async () => {
    const onUniverseChange = vi.fn();
    renderSelector({ onUniverseChange });
    const user = userEvent.setup();

    const universeSelect = (await screen.findByText("Alpha World")).closest("select")!;
    await user.selectOptions(universeSelect, "u-1");

    expect(onUniverseChange).toHaveBeenCalledWith("u-1", "Alpha World");
  });

  it("emits onSystemChange with the picked system id", async () => {
    const onSystemChange = vi.fn();
    renderSelector({ onSystemChange });
    const user = userEvent.setup();

    const systemSelect = (await screen.findByText("Bound System")).closest("select")!;
    await user.selectOptions(systemSelect, "sys-1");

    expect(onSystemChange).toHaveBeenCalledWith("sys-1");
  });

  it("renders the multiverse filter", async () => {
    renderSelector();
    expect(screen.getByText("All multiverses")).toBeInTheDocument();
    expect(screen.getByText("Select universe…")).toBeInTheDocument();
  });
});
