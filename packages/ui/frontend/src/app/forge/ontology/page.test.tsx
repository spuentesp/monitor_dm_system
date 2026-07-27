// @vitest-environment happy-dom
/**
 * /forge/ontology page tests (F2-2 phase 6):
 * - tab bar renders all four tabs and switches between them
 * - universe picker defaults to the first universe and re-scopes queries
 * - Facts: list renders, filters are sent to the API, create / edit / delete
 * - Axioms: create flow sends the authoring body
 * - Events: create flow sends the authoring body
 * - Relationships: edit flow patches category/tags/properties, delete flow
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WorldContextProvider } from "@/lib/world-context";
import { entitiesApi, graphApi, universesApi } from "@/lib/api";
import type {
  EntityRelationship,
  OntologyAxiom,
  OntologyEvent,
  OntologyFact,
  Universe,
} from "@/lib/types";
import OntologyPage from "./page";

// ─── Fixtures ─────────────────────────────────────────────────

function universe(id: string, name: string): Universe {
  return {
    id,
    name,
    multiverse_id: "mv-1",
    genre: "Fantasy",
    description: null,
    tags: [],
    is_active: true,
    entity_count: 2,
    session_count: 0,
    created_at: "2026-07-01T00:00:00Z",
  };
}

function fact(overrides: Partial<OntologyFact> = {}): OntologyFact {
  return {
    id: "fact-1",
    universe_id: "u-1",
    statement: "The bridge is broken",
    fact_type: "state",
    magnitude: 3,
    scope: "local",
    time_ref: null,
    duration: null,
    canon_level: "canon",
    knowledge_scope: "world",
    confidence: 0.9,
    authority: "gm",
    status: "active",
    created_at: "2026-07-01T00:00:00Z",
    replaces: null,
    properties: null,
    entity_ids: [],
    source_ids: [],
    ...overrides,
  };
}

function axiom(overrides: Partial<OntologyAxiom> = {}): OntologyAxiom {
  return {
    id: "ax-1",
    universe_id: "u-1",
    statement: "Magic costs memories",
    domain: "metaphysics",
    magnitude: 8,
    scope: "global",
    canon_level: "canon",
    confidence: 1,
    authority: "gm",
    source_ref: null,
    tags: [],
    properties: null,
    created_at: "2026-07-01T00:00:00Z",
    source_ids: [],
    ...overrides,
  };
}

function event(overrides: Partial<OntologyEvent> = {}): OntologyEvent {
  return {
    id: "ev-1",
    universe_id: "u-1",
    scene_id: null,
    title: "The bridge collapses",
    description: null,
    start_time: "2026-07-01T10:00:00Z",
    end_time: null,
    magnitude: 5,
    scope: "local",
    canon_level: "canon",
    knowledge_scope: "world",
    confidence: 1,
    authority: "gm",
    created_at: "2026-07-01T00:00:00Z",
    properties: null,
    entity_ids: [],
    source_ids: [],
    timeline_after: [],
    ...overrides,
  };
}

function relationship(overrides: Partial<EntityRelationship> = {}): EntityRelationship {
  return {
    relationship_id: "42",
    from_entity_id: "e-1",
    to_entity_id: "e-2",
    rel_type: "KNOWS",
    category: "social",
    subcategory: null,
    properties: {},
    tags: ["old-friends"],
    created_at: null,
    ...overrides,
  };
}

// ─── Render helper ────────────────────────────────────────────

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <WorldContextProvider>
        <OntologyPage />
      </WorldContextProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
  vi.spyOn(universesApi, "listUniverses").mockResolvedValue([
    universe("u-1", "Ashen Vale"),
    universe("u-2", "Fogharbor"),
  ]);
  vi.spyOn(entitiesApi, "listFacts").mockResolvedValue({
    facts: [fact()],
    count: 1,
    limit: 100,
    offset: 0,
  });
  vi.spyOn(entitiesApi, "listAxioms").mockResolvedValue({
    axioms: [axiom()],
    count: 1,
    limit: 100,
    offset: 0,
  });
  vi.spyOn(entitiesApi, "listEvents").mockResolvedValue({
    events: [event()],
    count: 1,
    limit: 100,
    offset: 0,
  });
  vi.spyOn(entitiesApi, "listUniverseRelationships").mockResolvedValue({
    relationships: [relationship()],
    total: 1,
    limit: 500,
    offset: 0,
  });
  vi.spyOn(graphApi, "getUniverseGraph").mockResolvedValue({
    nodes: [
      { id: "e-1", type: "worldNode", position: { x: 0, y: 0 }, data: { label: "Mira" } },
      { id: "e-2", type: "worldNode", position: { x: 0, y: 0 }, data: { label: "Tomm" } },
    ],
    edges: [],
  } as never);
});

// ─── Shell ────────────────────────────────────────────────────

describe("Ontology page — shell", () => {
  it("renders all four tabs and defaults to the facts list", async () => {
    renderPage();
    for (const label of ["Facts", "Axioms", "Events", "Relationships"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
    expect(await screen.findByText("The bridge is broken")).toBeInTheDocument();
    expect(entitiesApi.listFacts).toHaveBeenCalledWith(
      "u-1",
      expect.objectContaining({ limit: 100 }),
    );
  });

  it("switches tabs and queries the matching endpoint", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("The bridge is broken");

    await user.click(screen.getByRole("button", { name: "Axioms" }));
    expect(await screen.findByText("Magic costs memories")).toBeInTheDocument();
    expect(entitiesApi.listAxioms).toHaveBeenCalledWith("u-1", expect.anything());

    await user.click(screen.getByRole("button", { name: "Events" }));
    expect(await screen.findByText("The bridge collapses")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Relationships" }));
    expect(await screen.findByText(/edge #42/)).toBeInTheDocument();
  });

  it("re-scopes queries when the universe picker changes", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("The bridge is broken");

    await user.selectOptions(screen.getByLabelText("Universe"), "u-2");
    await waitFor(() =>
      expect(entitiesApi.listFacts).toHaveBeenCalledWith("u-2", expect.anything()),
    );
  });
});

// ─── Facts tab ────────────────────────────────────────────────

describe("Ontology page — facts tab", () => {
  it("sends the selected filters to the API", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("The bridge is broken");

    await user.selectOptions(screen.getByLabelText("Filter by fact type"), "occurrence");
    await waitFor(() =>
      expect(entitiesApi.listFacts).toHaveBeenCalledWith(
        "u-1",
        expect.objectContaining({ fact_type: "occurrence" }),
      ),
    );
  });

  it("creates a fact through the modal", async () => {
    const user = userEvent.setup();
    const createSpy = vi
      .spyOn(entitiesApi, "createFact")
      .mockResolvedValue(fact({ id: "fact-2", statement: "New rumor" }));
    renderPage();
    await screen.findByText("The bridge is broken");

    await user.click(screen.getByRole("button", { name: /new fact/i }));
    await user.type(screen.getByLabelText("Statement"), "New rumor");
    await user.click(screen.getByRole("button", { name: /create fact/i }));

    await waitFor(() =>
      expect(createSpy).toHaveBeenCalledWith(
        "u-1",
        expect.objectContaining({ statement: "New rumor", fact_type: "state" }),
      ),
    );
  });

  it("edits a fact through the modal", async () => {
    const user = userEvent.setup();
    const updateSpy = vi
      .spyOn(entitiesApi, "updateFact")
      .mockResolvedValue(fact({ statement: "The bridge is repaired" }));
    renderPage();
    await screen.findByText("The bridge is broken");

    await user.click(screen.getByLabelText("Edit fact The bridge is broken"));
    const statement = screen.getByLabelText("Statement");
    await user.clear(statement);
    await user.type(statement, "The bridge is repaired");
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() =>
      expect(updateSpy).toHaveBeenCalledWith(
        "fact-1",
        expect.objectContaining({ statement: "The bridge is repaired" }),
      ),
    );
  });

  it("deletes a fact after confirmation", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const deleteSpy = vi
      .spyOn(entitiesApi, "deleteFact")
      .mockResolvedValue({ deleted: true });
    renderPage();
    await screen.findByText("The bridge is broken");

    await user.click(screen.getByLabelText("Delete fact The bridge is broken"));
    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith("fact-1", { force: true }));
  });

  it("does not delete when the confirm is cancelled", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const deleteSpy = vi
      .spyOn(entitiesApi, "deleteFact")
      .mockResolvedValue({ deleted: true });
    renderPage();
    await screen.findByText("The bridge is broken");

    await user.click(screen.getByLabelText("Delete fact The bridge is broken"));
    expect(deleteSpy).not.toHaveBeenCalled();
  });
});

// ─── Axioms tab ───────────────────────────────────────────────

describe("Ontology page — axioms tab", () => {
  it("creates an axiom with its domain", async () => {
    const user = userEvent.setup();
    const createSpy = vi
      .spyOn(entitiesApi, "createAxiom")
      .mockResolvedValue(axiom({ id: "ax-2" }));
    renderPage();
    await screen.findByText("The bridge is broken");
    await user.click(screen.getByRole("button", { name: "Axioms" }));
    await screen.findByText("Magic costs memories");

    await user.click(screen.getByRole("button", { name: /new axiom/i }));
    await user.type(screen.getByLabelText("Statement"), "Iron rejects the drowned");
    const domain = screen.getByLabelText("Domain");
    await user.clear(domain);
    await user.type(domain, "physics");
    await user.click(screen.getByRole("button", { name: /create axiom/i }));

    await waitFor(() =>
      expect(createSpy).toHaveBeenCalledWith(
        "u-1",
        expect.objectContaining({ statement: "Iron rejects the drowned", domain: "physics" }),
      ),
    );
  });

  it("sends domain and canon filters to the API", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: "Axioms" }));
    await screen.findByText("Magic costs memories");

    await user.selectOptions(screen.getByLabelText("Filter by canon level"), "rumor");
    await waitFor(() =>
      expect(entitiesApi.listAxioms).toHaveBeenCalledWith(
        "u-1",
        expect.objectContaining({ canon_level: "rumor" }),
      ),
    );
  });
});

// ─── Events tab ───────────────────────────────────────────────

describe("Ontology page — events tab", () => {
  it("creates an event with title and start time", async () => {
    const user = userEvent.setup();
    const createSpy = vi
      .spyOn(entitiesApi, "createEvent")
      .mockResolvedValue(event({ id: "ev-2" }));
    renderPage();
    await user.click(screen.getByRole("button", { name: "Events" }));
    await screen.findByText("The bridge collapses");

    await user.click(screen.getByRole("button", { name: /new event/i }));
    await user.type(screen.getByLabelText("Title"), "The flood arrives");
    await user.type(screen.getByLabelText("Start time"), "2026-08-01T09:30");
    await user.click(screen.getByRole("button", { name: /create event/i }));

    await waitFor(() =>
      expect(createSpy).toHaveBeenCalledWith(
        "u-1",
        expect.objectContaining({
          title: "The flood arrives",
          start_time: expect.stringContaining("2026-08-01"),
        }),
      ),
    );
  });

  it("deletes an event after confirmation", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const deleteSpy = vi
      .spyOn(entitiesApi, "deleteEvent")
      .mockResolvedValue({ deleted: true });
    renderPage();
    await user.click(screen.getByRole("button", { name: "Events" }));
    await screen.findByText("The bridge collapses");

    await user.click(screen.getByLabelText("Delete event The bridge collapses"));
    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith("ev-1", { force: true }));
  });
});

// ─── Relationships tab ────────────────────────────────────────

describe("Ontology page — relationships tab", () => {
  it("edits category, tags and properties through the modal", async () => {
    const user = userEvent.setup();
    const updateSpy = vi
      .spyOn(entitiesApi, "updateRelationship")
      .mockResolvedValue(relationship({ category: "power" }));
    renderPage();
    await user.click(screen.getByRole("button", { name: "Relationships" }));
    await screen.findByText(/edge #42/);

    await user.click(screen.getByLabelText("Edit relationship 42"));
    await user.selectOptions(screen.getByLabelText("Category"), "power");
    const tags = screen.getByLabelText("Tags");
    await user.clear(tags);
    await user.type(tags, "grim, secret");
    fireEvent.change(screen.getByLabelText("Properties"), {
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

  it("deletes a relationship after confirmation", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const deleteSpy = vi
      .spyOn(entitiesApi, "deleteRelationship")
      .mockResolvedValue({ deleted: true, relationship_id: "42" });
    renderPage();
    await user.click(screen.getByRole("button", { name: "Relationships" }));
    await screen.findByText(/edge #42/);

    await user.click(screen.getByLabelText("Delete relationship 42"));
    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith("42"));
  });
});
