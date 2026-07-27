// @vitest-environment happy-dom
/**
 * Explorer edge context menu tests (F2-2 phase 4):
 * - right-clicking an edge opens the context menu
 * - Edit resolves the edge to its stored relationship and PATCHes
 *   category/tags/properties
 * - Delete asks for confirmation and DELETEs the edge
 * - an unresolvable edge surfaces an error instead of a silent no-op
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { entitiesApi, graphApi, universesApi } from "@/lib/api";
import type { EntityRelationship, Multiverse, Universe } from "@/lib/types";
import ExplorerPage from "./page";

// ─── @xyflow/react mock ───────────────────────────────────────
// ReactFlow doesn't run under happy-dom. The mock renders each edge as a
// button wired to the page's onEdgeContextMenu prop so the test can
// "right-click" an edge, and captures nodes for later assertions.

const rf = vi.hoisted(() => ({
  props: undefined as
    | {
        nodes: { id: string; data?: { label?: string } }[];
        edges: { id: string; source: string; target: string; label?: string }[];
        onEdgeContextMenu?: (event: unknown, edge: unknown) => void;
      }
    | undefined,
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
}));

vi.mock("@xyflow/react", async () => {
  const React = await import("react");
  return {
    ReactFlow: (props: NonNullable<typeof rf.props>) => {
      rf.props = props;
      return React.createElement(
        "div",
        { "data-testid": "react-flow" },
        props.edges.map((e) =>
          React.createElement(
            "button",
            {
              key: e.id,
              "data-testid": `edge-${e.id}`,
              onClick: (event: { preventDefault: () => void; clientX: number; clientY: number }) =>
                props.onEdgeContextMenu?.(
                  { preventDefault: () => {}, clientX: 10, clientY: 20 },
                  e,
                ),
            },
            String(e.label ?? e.id),
          ),
        ),
      );
    },
    Background: () => null,
    BackgroundVariant: { Dots: "dots" },
    Controls: () => null,
    MiniMap: () => null,
    addEdge: (edge: unknown, edges: unknown[]) => [...edges, edge],
    useNodesState: (init: unknown) => {
      const [v, setV] = React.useState(init);
      return [v, setV, () => {}];
    },
    useEdgesState: (init: unknown) => {
      const [v, setV] = React.useState(init);
      return [v, setV, () => {}];
    },
  };
});

// The adapters module pulls in xyflow layout helpers; replace it with a
// deterministic 1:1 mapping.
vi.mock("@/features/graph/adapters", () => ({
  toReactFlowNode: (n: { id: string; data?: { label?: string; kind?: string } }) => ({
    id: n.id,
    data: n.data,
    position: { x: 0, y: 0 },
  }),
  toReactFlowEdge: (e: { id: string; source: string; target: string; label?: string }) => ({
    ...e,
    data: { label: e.label },
  }),
  toReactFlowGraph: (g: { nodes: unknown[]; edges: unknown[] }) => ({
    nodes: g.nodes,
    edges: g.edges,
  }),
}));

// ─── Fixtures ─────────────────────────────────────────────────

const MV: Multiverse = {
  id: "mv-1",
  name: "The Mistlands",
  description: null,
  tags: [],
  universe_count: 1,
  created_at: "2026-07-01T00:00:00Z",
};

const U: Universe = {
  id: "u-1",
  name: "Ashen Vale",
  multiverse_id: "mv-1",
  genre: "Fantasy",
  description: null,
  tags: [],
  is_active: true,
  entity_count: 2,
  session_count: 0,
  created_at: "2026-07-01T00:00:00Z",
};

const REL: EntityRelationship = {
  relationship_id: "42",
  from_entity_id: "e-1",
  to_entity_id: "e-2",
  rel_type: "KNOWS",
  category: "social",
  subcategory: null,
  properties: {},
  tags: [],
  created_at: null,
};

const GRAPH = {
  nodes: [
    { id: "e-1", data: { label: "Mira", kind: "character" } },
    { id: "e-2", data: { label: "Tomm", kind: "character" } },
  ],
  edges: [{ id: "rel-42", source: "e-1", target: "e-2", label: "KNOWS" }],
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ExplorerPage />
    </QueryClientProvider>,
  );
}

async function openEdgeMenu(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByTestId("edge-rel-42");
  await user.click(screen.getByTestId("edge-rel-42"));
  return screen.findByRole("menu", { name: "Edge actions" });
}

beforeEach(() => {
  vi.restoreAllMocks();
  rf.props = undefined;
  window.localStorage.clear();
  vi.spyOn(universesApi, "listMultiverses").mockResolvedValue([MV]);
  vi.spyOn(universesApi, "listUniverses").mockResolvedValue([U]);
  vi.spyOn(graphApi, "getUniverseGraph").mockResolvedValue(GRAPH as never);
  vi.spyOn(graphApi, "getEgoGraph").mockResolvedValue({ nodes: [], edges: [] } as never);
  vi.spyOn(entitiesApi, "listRelationships").mockResolvedValue({
    relationships: [REL],
    total: 1,
  });
});

describe("Explorer — edge context menu", () => {
  it("opens on edge right-click and closes via the backdrop", async () => {
    const user = userEvent.setup();
    renderPage();
    const menu = await openEdgeMenu(user);
    expect(screen.getByRole("menuitem", { name: /edit relationship/i })).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: /delete relationship/i }),
    ).toBeInTheDocument();

    await user.click(screen.getByTestId("edge-menu-backdrop"));
    await waitFor(() => expect(menu).not.toBeInTheDocument());
  });

  it("edits the relationship through the modal", async () => {
    const user = userEvent.setup();
    const updateSpy = vi
      .spyOn(entitiesApi, "updateRelationship")
      .mockResolvedValue({ ...REL, category: "power" });
    renderPage();
    await openEdgeMenu(user);

    await user.click(screen.getByRole("menuitem", { name: /edit relationship/i }));
    // Resolves the synthetic edge to the stored relationship first.
    await waitFor(() =>
      expect(entitiesApi.listRelationships).toHaveBeenCalledWith("e-1"),
    );
    expect(await screen.findByText("Edit relationship")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Relationship category"), "power");
    await user.type(screen.getByLabelText("Relationship tags"), "grim, secret");
    fireEvent.change(screen.getByLabelText("Relationship properties"), {
      target: { value: '{"since":"the war"}' },
    });
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() =>
      expect(updateSpy).toHaveBeenCalledWith("42", {
        category: "power",
        tags: ["grim", "secret"],
        properties: { since: "the war" },
      }),
    );
  });

  it("rejects invalid properties JSON before calling the API", async () => {
    const user = userEvent.setup();
    const updateSpy = vi
      .spyOn(entitiesApi, "updateRelationship")
      .mockResolvedValue(REL);
    renderPage();
    await openEdgeMenu(user);
    await user.click(screen.getByRole("menuitem", { name: /edit relationship/i }));
    await screen.findByText("Edit relationship");

    fireEvent.change(screen.getByLabelText("Relationship properties"), {
      target: { value: "not json" },
    });
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    expect(await screen.findByText(/not valid JSON/i)).toBeInTheDocument();
    expect(updateSpy).not.toHaveBeenCalled();
  });

  it("deletes the relationship after confirmation", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const deleteSpy = vi
      .spyOn(entitiesApi, "deleteRelationship")
      .mockResolvedValue({ deleted: true, relationship_id: "42" });
    renderPage();
    await openEdgeMenu(user);

    await user.click(screen.getByRole("menuitem", { name: /delete relationship/i }));
    await waitFor(() => expect(window.confirm).toHaveBeenCalled());
    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith("42"));
  });

  it("does not delete when the confirm is cancelled", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const deleteSpy = vi
      .spyOn(entitiesApi, "deleteRelationship")
      .mockResolvedValue({ deleted: true, relationship_id: "42" });
    renderPage();
    await openEdgeMenu(user);

    await user.click(screen.getByRole("menuitem", { name: /delete relationship/i }));
    await waitFor(() => expect(window.confirm).toHaveBeenCalled());
    expect(deleteSpy).not.toHaveBeenCalled();
  });

  it("surfaces an error when the edge cannot be resolved", async () => {
    const user = userEvent.setup();
    vi.spyOn(entitiesApi, "listRelationships").mockResolvedValue({
      relationships: [],
      total: 0,
    });
    renderPage();
    await openEdgeMenu(user);

    await user.click(screen.getByRole("menuitem", { name: /delete relationship/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not resolve/i);
  });
});
