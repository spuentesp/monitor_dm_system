// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { gmApi, storiesApi, ApiError } from "@/lib/api";
import type { Handout } from "@/lib/types";
import { HandoutsPanel } from "./HandoutsPanel";

const HANDOUT: Handout = {
  title: "A sealed letter",
  content: "Come at dawn.",
  handout_type: "letter",
  related_entities: [],
  tone: "mysterious",
  spoiler_level: "safe",
};

function renderPanel(universeId: string | null = "u-1") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <HandoutsPanel universeId={universeId} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(storiesApi, "listStories").mockResolvedValue({
    stories: [
      {
        id: "story-1",
        universe_id: "u-1",
        title: "Main Quest",
        story_type: "campaign",
        status: "active",
        scene_count: 0,
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
    total: 1,
  } as never);
});

describe("HandoutsPanel (CF-6 / CF-14)", () => {
  it("prompts for a universe when none is selected", () => {
    renderPanel(null);
    expect(screen.getByText(/select a universe to generate handouts/i)).toBeInTheDocument();
  });

  it("generates a handout and offers to publish it to the story", async () => {
    const generate = vi.spyOn(gmApi, "generateHandout").mockResolvedValue({ handout: HANDOUT } as never);
    const user = userEvent.setup();
    renderPanel();

    const button = await screen.findByRole("button", { name: /generate/i });
    await user.click(button);

    await waitFor(() => expect(generate).toHaveBeenCalled());
    expect(await screen.findByText("A sealed letter")).toBeInTheDocument();
    expect(screen.getByText("Come at dawn.")).toBeInTheDocument();
    expect(screen.getByTestId("handout-publish")).toBeInTheDocument();
  });

  it("shows the daily-limit copy on 429", async () => {
    vi.spyOn(gmApi, "generateHandout").mockRejectedValue(new ApiError(429, "over cap"));
    const user = userEvent.setup();
    renderPanel();

    const button = await screen.findByRole("button", { name: /generate/i });
    await user.click(button);

    expect(
      await screen.findByText("Daily limit reached - resets 00:00 UTC. Ask your admin to raise it."),
    ).toBeInTheDocument();
  });
});
