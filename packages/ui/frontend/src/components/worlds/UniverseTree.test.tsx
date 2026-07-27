// @vitest-environment happy-dom
/**
 * UniverseTree tests (F1-5b / M-33):
 * - an empty universe (entity_count === 0) shows the "Seed from tables"
 *   action in the detail panel; clicking it calls universesApi.seedUniverse
 *   and reports the entities created.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError, storiesApi, universesApi } from "@/lib/api";
import type { Multiverse, Universe } from "@/lib/types";
import { WorldContextProvider } from "@/lib/world-context";
import { UniverseTree } from "./UniverseTree";

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

function universe(id: string, name: string, entityCount: number): Universe {
  return {
    id,
    name,
    multiverse_id: "mv-1",
    genre: "Fantasy",
    description: null,
    tags: [],
    is_active: true,
    entity_count: entityCount,
    story_count: 0,
    session_count: 0,
    created_at: "2026-07-01T00:00:00Z",
  };
}

function renderTree(u: Universe) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <UniverseTree multiverses={[multiverse("mv-1", "The Mistlands")]} requestedUniverseId={u.id} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(storiesApi, "listStories").mockResolvedValue({ stories: [], total: 0 });
});

// ─── Seed from tables ─────────────────────────────────────────

describe("UniverseTree — seed from tables (F1-5b)", () => {
  it("renders the seed action on an empty universe and calls the wrapper", async () => {
    const empty = universe("u-1", "Ashen Vale", 0);
    vi.spyOn(universesApi, "listUniverses").mockResolvedValue([empty]);
    vi.spyOn(universesApi, "getUniverse").mockResolvedValue(empty);
    const seed = vi
      .spyOn(universesApi, "seedUniverse")
      .mockResolvedValue({ universe_id: "u-1", entities_created: 7, errors: [] });

    const user = userEvent.setup();
    renderTree(empty);

    await user.click(await screen.findByRole("button", { name: /seed from tables/i }));

    await waitFor(() =>
      expect(seed).toHaveBeenCalledWith("u-1", { entity_count: 10, use_tables: true }),
    );
    expect(await screen.findByText(/seeded 7 entities/i)).toBeInTheDocument();
  });

  it("does not offer seeding on a universe that already has entities", async () => {
    const full = universe("u-1", "Ashen Vale", 12);
    vi.spyOn(universesApi, "listUniverses").mockResolvedValue([full]);
    vi.spyOn(universesApi, "getUniverse").mockResolvedValue(full);

    renderTree(full);

    // Detail panel renders (name heading), but no seed action.
    expect(await screen.findByRole("heading", { name: "Ashen Vale" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /seed from tables/i })).not.toBeInTheDocument();
  });
});

// ─── F3-3: multiverse edit/delete, template filter, WorldContext ───

function renderBareTree(mvs: Multiverse[], opts?: { withWorldContext?: boolean }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = (
    <QueryClientProvider client={qc}>
      <UniverseTree multiverses={mvs} />
    </QueryClientProvider>
  );
  return render(opts?.withWorldContext ? <WorldContextProvider>{tree}</WorldContextProvider> : tree);
}

describe("UniverseTree — multiverse edit (F3-3)", () => {
  it("edits a multiverse via the row action and calls updateMultiverse", async () => {
    vi.spyOn(universesApi, "listUniverses").mockResolvedValue([]);
    const update = vi
      .spyOn(universesApi, "updateMultiverse")
      .mockResolvedValue(multiverse("mv-1", "Renamed"));

    const user = userEvent.setup();
    renderBareTree([multiverse("mv-1", "The Mistlands")]);

    await user.click(screen.getByRole("button", { name: /edit the mistlands/i }));
    const nameInput = screen.getByLabelText(/multiverse name/i);
    expect(nameInput).toHaveValue("The Mistlands");
    await user.clear(nameInput);
    await user.type(nameInput, "Renamed");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith("mv-1", {
        name: "Renamed",
        description: undefined,
        system_name: undefined,
      }),
    );
  });
});

describe("UniverseTree — multiverse delete (F3-3)", () => {
  it("deletes an empty multiverse after confirmation", async () => {
    vi.spyOn(universesApi, "listUniverses").mockResolvedValue([]);
    const del = vi.spyOn(universesApi, "deleteMultiverse").mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    const user = userEvent.setup();
    renderBareTree([multiverse("mv-1", "The Mistlands")]);

    await user.click(screen.getByRole("button", { name: /delete the mistlands/i }));

    await waitFor(() => expect(del).toHaveBeenCalledWith("mv-1"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows a clean message when the backend refuses a non-empty delete (409)", async () => {
    vi.spyOn(universesApi, "listUniverses").mockResolvedValue([]);
    vi.spyOn(universesApi, "deleteMultiverse").mockRejectedValue(new ApiError(409, "conflict"));
    vi.spyOn(window, "confirm").mockReturnValue(true);

    const user = userEvent.setup();
    renderBareTree([multiverse("mv-1", "The Mistlands")]);

    await user.click(screen.getByRole("button", { name: /delete the mistlands/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/still contains universes/i);
  });

  it("clears the persisted WorldContext selection when the selected multiverse is deleted", async () => {
    window.localStorage.setItem(
      "monitor.world-context.v1",
      JSON.stringify({ multiverseId: "mv-1", universeId: "u-1", universeLabel: "Ashen Vale" }),
    );
    vi.spyOn(universesApi, "listUniverses").mockResolvedValue([]);
    vi.spyOn(universesApi, "deleteMultiverse").mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    const user = userEvent.setup();
    renderBareTree([multiverse("mv-1", "The Mistlands")], { withWorldContext: true });

    await user.click(screen.getByRole("button", { name: /delete the mistlands/i }));

    await waitFor(() => {
      const raw = window.localStorage.getItem("monitor.world-context.v1");
      expect(raw).toBeTruthy();
      const sel = JSON.parse(raw!);
      expect(sel.multiverseId).toBeNull();
      expect(sel.universeId).toBeNull();
    });
  });
});

describe("UniverseTree — universe metadata edit (F3-3)", () => {
  it("edits name/genre/tone/description via updateUniverse", async () => {
    const u = universe("u-1", "Ashen Vale", 12);
    vi.spyOn(universesApi, "listUniverses").mockResolvedValue([u]);
    vi.spyOn(universesApi, "getUniverse").mockResolvedValue(u);
    const update = vi.spyOn(universesApi, "updateUniverse").mockResolvedValue(u);

    const user = userEvent.setup();
    renderTree(u);

    await user.click(await screen.findByRole("button", { name: /edit universe/i }));
    const nameInput = screen.getByLabelText(/universe name/i);
    expect(nameInput).toHaveValue("Ashen Vale");
    await user.clear(nameInput);
    await user.type(nameInput, "Ember Vale");
    await user.type(screen.getByLabelText(/tone/i), "dark");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith("u-1", {
        name: "Ember Vale",
        genre: "Fantasy",
        tone: "dark",
        description: undefined,
      }),
    );
  });
});

describe("UniverseTree — template badge & filter (F3-3)", () => {
  it("badges template universes and filters all/playable/templates", async () => {
    const tpl: Universe = { ...universe("u-tpl", "Canon Blueprint", 5), is_template: true };
    const live = universe("u-live", "Ashen Vale", 12);
    vi.spyOn(universesApi, "listUniverses").mockResolvedValue([tpl, live]);
    vi.spyOn(universesApi, "getUniverse").mockResolvedValue(live);

    const user = userEvent.setup();
    renderBareTree([multiverse("mv-1", "The Mistlands")]);

    // All: both rows visible, template one badged
    expect(await screen.findByText("Canon Blueprint")).toBeInTheDocument();
    expect(screen.getByText("Ashen Vale")).toBeInTheDocument();
    expect(screen.getAllByText("Template").length).toBeGreaterThan(0);

    // Playable only: template row hidden
    await user.selectOptions(screen.getByLabelText(/show/i), "playable");
    expect(screen.queryByText("Canon Blueprint")).not.toBeInTheDocument();
    expect(screen.getByText("Ashen Vale")).toBeInTheDocument();

    // Templates only: playable row hidden
    await user.selectOptions(screen.getByLabelText(/show/i), "templates");
    expect(screen.getByText("Canon Blueprint")).toBeInTheDocument();
    expect(screen.queryByText("Ashen Vale")).not.toBeInTheDocument();
  });
});
