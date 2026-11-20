// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { gmApi, storiesApi, ApiError } from "@/lib/api";
import type { PlotHook } from "@/lib/types";
import { PlotHooksPanel } from "./PlotHooksPanel";

const HOOK: PlotHook = {
  hook_id: "h-1",
  title: "The missing caravan",
  description: "Merchants vanished on the north road.",
  urgency: "high",
  suggested_scene_type: "investigation",
  connected_entities: ["North Road"],
};

function renderPanel(universeId: string | null = "u-1") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PlotHooksPanel universeId={universeId} />
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

describe("PlotHooksPanel (CF-4)", () => {
  it("prompts for a universe when none is selected", () => {
    renderPanel(null);
    expect(screen.getByText(/select a universe to generate plot hooks/i)).toBeInTheDocument();
  });

  it("generates hooks for the auto-selected story", async () => {
    const suggest = vi.spyOn(gmApi, "suggestHooks").mockResolvedValue({ hooks: [HOOK] });
    const user = userEvent.setup();
    renderPanel();

    const generate = await screen.findByRole("button", { name: /generate/i });
    await waitFor(() => expect(generate).toBeEnabled());
    await user.click(generate);

    await waitFor(() => expect(suggest).toHaveBeenCalledWith("u-1", "story-1"));
    expect(await screen.findByText("The missing caravan")).toBeInTheDocument();
    expect(screen.getByText(/high/)).toBeInTheDocument();
  });

  it("shows the daily-limit copy on 429", async () => {
    vi.spyOn(gmApi, "suggestHooks").mockRejectedValue(new ApiError(429, "over cap"));
    const user = userEvent.setup();
    renderPanel();

    const generate = await screen.findByRole("button", { name: /generate/i });
    await waitFor(() => expect(generate).toBeEnabled());
    await user.click(generate);

    expect(
      await screen.findByText("Daily limit reached - resets 00:00 UTC. Ask your admin to raise it."),
    ).toBeInTheDocument();
  });
});
