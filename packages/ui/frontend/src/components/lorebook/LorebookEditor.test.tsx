// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LorebookEditor } from "./LorebookEditor";
import * as api from "@/lib/api";
import type { GraphNode, WorldGraph } from "@/lib/types";

function characterNode(id: string, label: string): GraphNode {
  return {
    id,
    type: "worldNode",
    position: { x: 0, y: 0 },
    data: { label, kind: "character" },
  };
}

function graph(nodes: GraphNode[]): WorldGraph {
  return { nodes, edges: [] };
}

beforeEach(() => {
  vi.restoreAllMocks();
  globalThis.fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify({}), { status: 200, headers: { "Content-Type": "application/json" } })),
  ) as unknown as typeof fetch;
  vi.spyOn(api.lorebookApi, "list").mockResolvedValue([]);
  vi.spyOn(api.lorebookApi, "stats").mockResolvedValue({ total_entries: 0, total_triggers: 0 });
  vi.spyOn(api.graphApi, "getWorldGraph").mockResolvedValue(
    graph([characterNode("c1", "Vesper"), characterNode("c2", "Karn")]),
  );
});

function renderEditor(props: { characterId?: string; universeId?: string; onClose?: () => void }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LorebookEditor {...props} />
    </QueryClientProvider>,
  );
}

describe("LorebookEditor — universe mode (F3-4.4)", () => {
  it("shows a scope selector defaulting to Universe-wide", async () => {
    renderEditor({ universeId: "u1" });

    const scope = await screen.findByLabelText("Lorebook scope");
    expect((scope as HTMLSelectElement).value).toBe("universe:u1");
    expect(screen.getByRole("option", { name: "Universe-wide" })).toBeInTheDocument();
    expect(await screen.findByRole("option", { name: "Vesper" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Karn" })).toBeInTheDocument();

    await waitFor(() =>
      expect(api.lorebookApi.list).toHaveBeenCalledWith("universe:u1"),
    );
  });

  it("fetches the universe's characters via the world graph", async () => {
    renderEditor({ universeId: "u1" });

    await screen.findByRole("option", { name: "Vesper" });
    expect(api.graphApi.getWorldGraph).toHaveBeenCalledWith({
      universe_id: "u1",
      entity_types: ["character"],
    });
  });

  it("switching scope to a character refetches entries for that character", async () => {
    const user = userEvent.setup();
    renderEditor({ universeId: "u1" });

    const scope = await screen.findByLabelText("Lorebook scope");
    await screen.findByRole("option", { name: "Vesper" });
    await user.selectOptions(scope, "c1");

    await waitFor(() => expect(api.lorebookApi.list).toHaveBeenCalledWith("c1"));
  });

  it("hides the close button when onClose is undefined (embedded)", async () => {
    renderEditor({ universeId: "u1" });

    await screen.findByLabelText("Lorebook scope");
    expect(screen.queryByLabelText("Close")).not.toBeInTheDocument();
  });
});

describe("LorebookEditor — character mode (unchanged)", () => {
  it("keeps the character-scoped behavior with no scope selector", async () => {
    renderEditor({ characterId: "c1", onClose: () => {} });

    await waitFor(() => expect(api.lorebookApi.list).toHaveBeenCalledWith("c1"));
    expect(screen.queryByLabelText("Lorebook scope")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Close")).toBeInTheDocument();
    expect(api.graphApi.getWorldGraph).not.toHaveBeenCalled();
  });
});
