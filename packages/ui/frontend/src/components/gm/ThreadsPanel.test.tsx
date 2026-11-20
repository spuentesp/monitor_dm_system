// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { storiesApi } from "@/lib/api";
import type { StoryThread } from "@/lib/types";
import { ThreadsPanel } from "./ThreadsPanel";

const THREAD: StoryThread = {
  id: "t-1",
  title: "Who stole the sunstone?",
  thread_type: "plot",
  status: "open",
  urgency: "high",
  source: "checkpoint",
};

function renderPanel(universeId: string | null = "u-1") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThreadsPanel universeId={universeId} />
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

describe("ThreadsPanel (CF-3)", () => {
  it("prompts for a universe when none is selected", () => {
    renderPanel(null);
    expect(
      screen.getByText(/select a universe to track unresolved threads/i),
    ).toBeInTheDocument();
  });

  it("lists the story's threads with urgency and resolves one", async () => {
    vi.spyOn(storiesApi, "listThreads").mockResolvedValue([THREAD] as never);
    const update = vi.spyOn(storiesApi, "updateThread").mockResolvedValue({} as never);
    const user = userEvent.setup();
    renderPanel();

    expect(await screen.findByText("Who stole the sunstone?")).toBeInTheDocument();
    expect(screen.getByText("high")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Resolve" }));
    await waitFor(() => expect(update).toHaveBeenCalledWith("story-1", "t-1", "resolve", undefined));
  });

  it("shows an empty state when the story has no open threads", async () => {
    vi.spyOn(storiesApi, "listThreads").mockResolvedValue([] as never);
    renderPanel();
    expect(await screen.findByText(/no open threads in this story/i)).toBeInTheDocument();
  });
});
