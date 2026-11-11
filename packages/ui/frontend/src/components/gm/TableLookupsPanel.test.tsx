// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { storiesApi } from "@/lib/api";
import { gmTableApi } from "@/lib/gm-table-api";
import { TableLookupsPanel } from "./TableLookupsPanel";

function renderPanel(universeId: string | null, systemId: string | null = null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TableLookupsPanel universeId={universeId} systemId={systemId} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  globalThis.fetch = vi.fn(() =>
    Promise.resolve(new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } })),
  ) as unknown as typeof fetch;
});

describe("TableLookupsPanel (CF-3/Q-2/Q-4/Q-7)", () => {
  it("prompts for a universe when none is selected", () => {
    renderPanel(null);
    expect(screen.getByText(/select a universe to run table lookups/i)).toBeInTheDocument();
  });

  it("looks up an NPC dossier by name", async () => {
    const spy = vi.spyOn(gmTableApi, "lookupNpc").mockResolvedValue({
      found: true,
      entity: {
        id: "e-1",
        name: "Mira",
        entity_type: "character",
        description: "A thief with a debt.",
        state_tags: ["friendly"],
      },
      agendas: [{ id: "a-1", title: "Get the key back", description: "She owes the guild." }],
      relationships: [],
      recent_facts: [{ id: "f-1", statement: "the key is with Mira" }],
      note: "",
    });
    const user = userEvent.setup();
    renderPanel("u-1");

    await user.type(screen.getByPlaceholderText(/npc name/i), "Mira");
    await user.click(screen.getByRole("button", { name: /look up/i }));

    await waitFor(() => expect(spy).toHaveBeenCalledWith("u-1", { name: "Mira" }));
    expect(await screen.findByText("A thief with a debt.")).toBeInTheDocument();
    expect(screen.getByText(/wants|what they want/i)).toBeInTheDocument();
    expect(screen.getByText(/the key is with Mira/)).toBeInTheDocument();
    expect(screen.getByText("Get the key back")).toBeInTheDocument();
  });

  it("answers an improvise request and shows the rationale", async () => {
    const spy = vi.spyOn(gmTableApi, "improvise").mockResolvedValue({
      kind: "complication",
      suggestions: ["The guild master arrives with guards."],
      rationale: "presses the open thread",
    });
    const user = userEvent.setup();
    renderPanel("u-1");

    await user.click(screen.getByRole("button", { name: /complication/i }));
    await user.type(screen.getByPlaceholderText(/what is happening/i), "the party is stalling");
    await user.click(screen.getByRole("button", { name: /complicate things/i }));

    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith({
        universe_id: "u-1",
        kind: "complication",
        context: "the party is stalling",
        count: 3,
      }),
    );
    expect(await screen.findByText("The guild master arrives with guards.")).toBeInTheDocument();
    expect(screen.getByText("presses the open thread")).toBeInTheDocument();
  });

  it("answers a rules question with its source", async () => {
    const spy = vi.spyOn(gmTableApi, "lookupRules").mockResolvedValue({
      answer: "Roll Might against the target.",
      source: "Grappling",
      covered: true,
    });
    const user = userEvent.setup();
    renderPanel("u-1", "sys-1");

    await user.click(screen.getByRole("button", { name: /rules/i }));
    await user.type(screen.getByPlaceholderText(/grappling/i), "How does grappling work?");
    await user.click(screen.getByRole("button", { name: /answer question/i }));

    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith({
        system_id: "sys-1",
        universe_id: null,
        question: "How does grappling work?",
      }),
    );
    expect(await screen.findByText("Roll Might against the target.")).toBeInTheDocument();
    expect(screen.getByText("Source: Grappling")).toBeInTheDocument();
  });

  // CF-2 / CF-11 — the recap lookup carries the world-clock time line.
  it("shows the recap time line from the world clock", async () => {
    vi.spyOn(storiesApi, "listStories").mockResolvedValue({
      stories: [{ id: "story-1", title: "Iron Watch", status: "active" }],
      total: 1,
    } as never);
    const spy = vi.spyOn(gmTableApi, "lookupLastSession").mockResolvedValue({
      found: true,
      session_id: "s-new",
      session_title: "Session 2",
      ledger_entry: {
        entry_id: "e-1",
        sequence: 2,
        summary: "The party returned to Ironwatch.",
        state_changes: [],
        open_questions: [],
        world_moves: [],
        scene_index: 1,
        created_at: "2026-11-08T00:00:00Z",
      },
      transcript: [],
      world_time: "1012-03-04T09:00:00+00:00",
      time_line: [
        {
          from_at: "1012-03-01T09:00:00+00:00",
          to_at: "1012-03-04T09:00:00+00:00",
          delta: "+3 days",
          advanced_at: "2026-11-10T00:00:00+00:00",
        },
      ],
      note: "",
    });
    const user = userEvent.setup();
    renderPanel("u-1");

    await user.click(screen.getByRole("button", { name: "Last session" }));
    await user.click(screen.getByRole("button", { name: "Look up last session" }));

    await waitFor(() => expect(spy).toHaveBeenCalledWith("u-1", "story-1"));
    const timeLine = await screen.findByTestId("recap-time-line");
    expect(timeLine).toHaveTextContent("World time: 1012-03-04T09:00:00+00:00");
    expect(timeLine).toHaveTextContent("+3 days (1012-03-01 → 1012-03-04)");
  });
});
