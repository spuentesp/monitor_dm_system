// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { gmApi, storiesApi } from "@/lib/api";
import type { SessionPrep } from "@/lib/types";
import { SessionPrepPanel } from "./SessionPrepPanel";

const PREP: SessionPrep = {
  recap: "The party opened the sealed vault.",
  open_threads: ["Who hired the thieves?"],
  hooks: [],
  npc_reminders: ["Mira lies about the key"],
  world_state_changes: ["The vault door stands open"],
};

function renderPanel(universeId: string | null = "u-1") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SessionPrepPanel universeId={universeId} />
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

describe("SessionPrepPanel (CF-7)", () => {
  it("prompts for a universe when none is selected", () => {
    renderPanel(null);
    expect(screen.getByText(/select a universe to generate session prep/i)).toBeInTheDocument();
  });

  it("generates prep for the auto-selected story and renders the recap", async () => {
    const generate = vi
      .spyOn(gmApi, "generateSessionPrep")
      .mockResolvedValue({ prep: PREP });
    const user = userEvent.setup();
    renderPanel();

    const button = await screen.findByRole("button", { name: /generate/i });
    await waitFor(() => expect(button).toBeEnabled());
    await user.click(button);

    await waitFor(() => expect(generate).toHaveBeenCalledWith("u-1", "story-1"));
    expect(await screen.findByText("The party opened the sealed vault.")).toBeInTheDocument();
    expect(screen.getByText(/who hired the thieves/i)).toBeInTheDocument();
    expect(screen.getByText(/mira lies about the key/i)).toBeInTheDocument();
  });
});
