// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WorldContextProvider } from "@/lib/world-context";
import { entitiesApi, universesApi } from "@/lib/api";
import type { RPGSystem, Universe } from "@/lib/types";
import GMAssistantPage from "./page";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <WorldContextProvider>
        <GMAssistantPage />
      </WorldContextProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
  globalThis.fetch = vi.fn(() =>
    Promise.resolve(new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } })),
  ) as unknown as typeof fetch;
  vi.spyOn(universesApi, "listMultiverses").mockResolvedValue([]);
  vi.spyOn(universesApi, "listUniverses").mockResolvedValue([
    {
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
    } as Universe,
  ]);
  vi.spyOn(universesApi, "getUniverse").mockResolvedValue({
    id: "u-1",
    name: "Alpha World",
    multiverse_id: "mv-1",
    genre: null,
    description: null,
    default_game_system_id: "sys-1",
    tags: [],
    is_active: true,
    entity_count: 0,
    session_count: 0,
    created_at: "2026-01-01T00:00:00Z",
  } as Universe);
  vi.spyOn(entitiesApi, "listSystems").mockResolvedValue([
    {
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
    } as RPGSystem,
  ]);
});

describe("GM Assistant first-run state (UX-5)", () => {
  it("shows the guided guide instead of the empty recorder until a world is picked", async () => {
    const user = userEvent.setup();
    renderPage();

    // No universe → the center shows the guided first-run state (desktop and
    // narrow layouts both mount it under happy-dom).
    expect(screen.getAllByTestId("first-run-guide").length).toBeGreaterThan(0);
    expect(screen.getByTestId("first-use-tour")).toBeInTheDocument();
    expect(screen.queryByText(/select a universe to record a session into it/i)).not.toBeInTheDocument();

    // Picking a world swaps the guide for the recorder.
    const universeSelect = (await screen.findByText("Alpha World")).closest("select")!;
    await user.selectOptions(universeSelect, "u-1");
    await waitFor(() =>
      expect(screen.queryByTestId("first-run-guide")).not.toBeInTheDocument(),
    );
  });
});
