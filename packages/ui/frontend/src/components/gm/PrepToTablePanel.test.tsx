// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { gmApi, storiesApi } from "@/lib/api";
import { gmTableApi } from "@/lib/gm-table-api";
import { PrepToTablePanel } from "./PrepToTablePanel";

function renderPanel(universeId: string | null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PrepToTablePanel universeId={universeId} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  globalThis.fetch = vi.fn(() =>
    Promise.resolve(new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } })),
  ) as unknown as typeof fetch;
  vi.spyOn(storiesApi, "listStories").mockResolvedValue({
    stories: [{ id: "story-1", title: "Iron Watch", status: "active" }],
    total: 1,
  } as never);
  vi.spyOn(gmApi, "getNotes").mockResolvedValue({
    universe_id: "u-1",
    content: "Mira wants the key back",
    updated_at: "2026-11-10T00:00:00Z",
  });
  vi.spyOn(gmTableApi, "getPrep").mockResolvedValue({ found: false, bundle: null });
});

describe("PrepToTablePanel (CF-7)", () => {
  it("prompts for a universe when none is selected", () => {
    renderPanel(null);
    expect(screen.getByText(/select a universe to prep/i)).toBeInTheDocument();
  });

  it("extracts the notes for review and commits the included items", async () => {
    const extractSpy = vi.spyOn(gmTableApi, "extractPrep").mockResolvedValue({
      npcs: [
        { name: "Mira", description: "A thief", want: "the key back", existing_entity_id: "e-1" },
        { name: "The guild master", description: "", want: "the ledger", existing_entity_id: null },
      ],
      locations: [],
      threads: [{ title: "The sealed door", description: "", urgency: "high", thread_id: null }],
      notes_summary: "A return to Ironwatch.",
    });
    const commitSpy = vi.spyOn(gmTableApi, "commitPrep").mockResolvedValue({
      bundle: {
        universe_id: "u-1",
        story_id: "story-1",
        npcs: [],
        locations: [],
        threads: [{ title: "The sealed door", description: "", urgency: "high", thread_id: "t-1" }],
        source: "prep_bundle:b-1",
        updated_at: "2026-11-10T00:00:00Z",
      },
      committed_thread_ids: ["t-1"],
      staged_proposal_ids: ["p-1"],
      staging_errors: ["p-2: store down"],
    });
    const user = userEvent.setup();
    renderPanel("u-1");

    await user.click(await screen.findByRole("button", { name: /use notebook notes/i }));
    await user.click(screen.getByRole("button", { name: /extract for review/i }));

    await waitFor(() =>
      expect(extractSpy).toHaveBeenCalledWith("u-1", "Mira wants the key back", "story-1"),
    );
    // Review shows extracted items and marks canon matches.
    expect(await screen.findByDisplayValue("The guild master")).toBeInTheDocument();
    expect(screen.getByText("already in canon")).toBeInTheDocument();
    expect(screen.getByText("A return to Ironwatch.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /save as tonight's prep/i }));

    await waitFor(() => expect(commitSpy).toHaveBeenCalled());
    const body = commitSpy.mock.calls[0][0];
    expect(body.universe_id).toBe("u-1");
    expect(body.story_id).toBe("story-1");
    // All extracted items were included by default (review edits are honored).
    expect(body.npcs.map((n) => n.name)).toEqual(["Mira", "The guild master"]);
    expect(body.threads.map((t) => t.title)).toEqual(["The sealed door"]);

    // The saved bundle becomes "tonight's table".
    expect(await screen.findByText("Tonight's table")).toBeInTheDocument();
    expect(await screen.findByText("saved as thread")).toBeInTheDocument();
    // A rejected staging is surfaced, never silent.
    expect(screen.getByText("Not staged: p-2: store down")).toBeInTheDocument();
  });

  it("loads a previously saved bundle for tonight", async () => {
    vi.spyOn(gmTableApi, "getPrep").mockResolvedValue({
      found: true,
      bundle: {
        universe_id: "u-1",
        story_id: "story-1",
        npcs: [{ name: "Mira", description: "", want: "the key back", existing_entity_id: null }],
        locations: [],
        threads: [],
        source: "prep_bundle:b-1",
        updated_at: "2026-11-10T00:00:00Z",
      },
    });
    renderPanel("u-1");

    expect(await screen.findByText("Tonight's table")).toBeInTheDocument();
    expect(await screen.findByText("Mira")).toBeInTheDocument();
  });
});
