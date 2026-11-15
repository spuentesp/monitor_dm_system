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

  it("shows the CF-12 'Campaign so far' collapsible for the selected story", async () => {
    vi.spyOn(storiesApi, "getArcRecap").mockResolvedValue({
      story_id: "story-1",
      universe_id: "u-1",
      recap: "## Major Arcs\n\nThe party fled Ironwatch.",
      detail: "standard",
      scene_count: 3,
      scenes_watermark: "wm-3",
      last_scene_id: "scene-3",
      generated_at: "2026-11-11T10:00:00Z",
      persisted: true,
    });
    const refreshSpy = vi.spyOn(storiesApi, "refreshArcRecap");
    const user = userEvent.setup();
    renderPanel("u-1");

    // Collapsed by default in the prep panel; persisted read only, no POST.
    const toggle = await screen.findByTestId("arc-recap-toggle");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);

    expect(await screen.findByTestId("arc-recap-body")).toHaveTextContent("The party fled Ironwatch.");
    expect(refreshSpy).not.toHaveBeenCalled();
    expect(screen.getByTestId("arc-recap-persisted-badge")).toHaveTextContent("3 scenes");
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

// ---------------------------------------------------------------------------
// World clock (CF-11 Advance World Time)
// ---------------------------------------------------------------------------

const BASE_CLOCK = {
  universe_id: "u-1",
  story_id: "story-1",
  current_at: "1012-03-04T09:00:00+00:00",
  display: "1012-03-04T09:00:00+00:00",
  deadlines: [
    {
      id: "d-ransom",
      title: "The ransom is due",
      due_at: "1012-03-03T00:00:00+00:00",
      notes: "",
      status: "overdue" as const,
    },
    {
      id: "d-festival",
      title: "Midsummer festival",
      due_at: "1012-06-01T00:00:00+00:00",
      notes: "",
      status: "upcoming" as const,
    },
  ],
  advances: [
    {
      from_at: "1012-03-01T09:00:00+00:00",
      to_at: "1012-03-04T09:00:00+00:00",
      delta: "+3 days",
      advanced_at: "2026-11-10T00:00:00+00:00",
    },
  ],
  offscreen_summary: "Mira struck a deal with the guild while the party rested.",
  offscreen_summary_at: "2026-11-10T00:00:00+00:00",
  updated_at: "1012-03-04T09:00:00+00:00",
};

const ADVANCE_RESULT = {
  clock: { ...BASE_CLOCK, current_at: "1012-03-04T11:00:00+00:00", display: "1012-03-04T11:00:00+00:00" },
  changed: true,
  initialized: false,
  crossed: [],
  due: [BASE_CLOCK.deadlines[0]],
  offscreen_summary: "",
  npc_activities: [],
  staged_proposal_ids: [],
  staging_errors: [],
};

describe("World clock (CF-11)", () => {
  it("shows the readout, deadlines and off-screen tick, then advances after confirmation", async () => {
    vi.spyOn(gmTableApi, "getClock").mockResolvedValue({ found: true, clock: BASE_CLOCK });
    const advanceSpy = vi.spyOn(gmTableApi, "advanceClock").mockResolvedValue(ADVANCE_RESULT);
    const user = userEvent.setup();
    renderPanel("u-1");

    // CF-7 briefing content: readout, deadline statuses, off-screen tick.
    expect(await screen.findByTestId("clock-readout")).toHaveTextContent("1012-03-04T09:00:00");
    expect(screen.getByTestId("deadline-overdue")).toHaveTextContent("The ransom is due");
    expect(screen.getByTestId("deadline-overdue")).toHaveTextContent("overdue");
    expect(screen.getByTestId("deadline-upcoming")).toHaveTextContent("Midsummer festival");
    expect(screen.getByTestId("offscreen-summary")).toHaveTextContent("Mira struck a deal with the guild");
    expect(screen.getByText(/last advance: \+3 days/i)).toBeInTheDocument();

    // Two-step confirmation: Advance → Confirm.
    await user.type(screen.getByLabelText("Advance world time"), "+2 hours");
    await user.click(screen.getByRole("button", { name: "Advance" }));
    await user.click(screen.getByTestId("confirm-advance"));

    await waitFor(() =>
      expect(advanceSpy).toHaveBeenCalledWith({
        universe_id: "u-1",
        story_id: "story-1",
        delta: "+2 hours",
      }),
    );
    expect(await screen.findByTestId("clock-info")).toHaveTextContent("World time is now");
  });

  it("surfaces an advance error instead of failing silently", async () => {
    vi.spyOn(gmTableApi, "getClock").mockResolvedValue({ found: false, clock: null });
    vi.spyOn(gmTableApi, "advanceClock").mockRejectedValue(
      new Error("No world clock yet for this story"),
    );
    const user = userEvent.setup();
    renderPanel("u-1");

    expect(await screen.findByText(/no clock yet/i)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Advance world time"), "+3 days");
    await user.click(screen.getByRole("button", { name: "Advance" }));
    await user.click(screen.getByTestId("confirm-advance"));

    expect(await screen.findByTestId("clock-error")).toHaveTextContent(
      "No world clock yet for this story",
    );
  });

  it("sends an absolute first set as target_time", async () => {
    vi.spyOn(gmTableApi, "getClock").mockResolvedValue({ found: false, clock: null });
    const advanceSpy = vi.spyOn(gmTableApi, "advanceClock").mockResolvedValue({
      ...ADVANCE_RESULT,
      initialized: true,
    });
    const user = userEvent.setup();
    renderPanel("u-1");

    expect(await screen.findByText(/no clock yet/i)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Advance world time"), "1012-03-01T09:00");
    await user.click(screen.getByRole("button", { name: "Advance" }));
    await user.click(screen.getByTestId("confirm-advance"));

    await waitFor(() =>
      expect(advanceSpy).toHaveBeenCalledWith({
        universe_id: "u-1",
        story_id: "story-1",
        target_time: "1012-03-01T09:00",
      }),
    );
  });

  it("creates a deadline once the clock exists", async () => {
    vi.spyOn(gmTableApi, "getClock").mockResolvedValue({ found: true, clock: BASE_CLOCK });
    const deadlineSpy = vi.spyOn(gmTableApi, "upsertDeadline").mockResolvedValue(BASE_CLOCK);
    const user = userEvent.setup();
    renderPanel("u-1");

    expect(await screen.findByTestId("clock-readout")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Deadline title"), "The ransom is due");
    await user.type(screen.getByLabelText("Deadline due"), "1012-03-03");
    await user.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() =>
      expect(deadlineSpy).toHaveBeenCalledWith({
        universe_id: "u-1",
        story_id: "story-1",
        title: "The ransom is due",
        due_at: "1012-03-03",
      }),
    );
    expect(await screen.findByText(/deadline saved/i)).toBeInTheDocument();
  });
});
