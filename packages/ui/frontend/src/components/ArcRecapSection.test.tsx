// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError, storiesApi } from "@/lib/api";
import type { ArcRecap } from "@/lib/types";
import { ArcRecapSection } from "./ArcRecapSection";

// CF-12 — the story-arc recap panel: GET returns the persisted recap without
// regenerating (404 = none yet → generate), POST refreshes with a length.

const RECAP: ArcRecap = {
  story_id: "story-1",
  universe_id: "u-1",
  recap: "## Major Arcs\n\nThe party fled Ironwatch with the chapel key.",
  detail: "standard",
  scene_count: 4,
  scenes_watermark: "wm-4",
  last_scene_id: "scene-4",
  generated_at: "2026-11-11T10:00:00Z",
  persisted: true,
};

function renderSection(props: Partial<Parameters<typeof ArcRecapSection>[0]> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ArcRecapSection storyId="story-1" {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("ArcRecapSection (CF-12)", () => {
  it("renders the persisted recap without regenerating it", async () => {
    const getSpy = vi.spyOn(storiesApi, "getArcRecap").mockResolvedValue(RECAP);
    const refreshSpy = vi.spyOn(storiesApi, "refreshArcRecap");
    renderSection();

    expect(await screen.findByTestId("arc-recap-body")).toHaveTextContent(
      "The party fled Ironwatch with the chapel key.",
    );
    expect(getSpy).toHaveBeenCalledWith("story-1");
    expect(refreshSpy).not.toHaveBeenCalled();
    const badge = screen.getByTestId("arc-recap-persisted-badge");
    expect(badge).toHaveTextContent("persisted");
    expect(badge).toHaveTextContent("4 scenes");
  });

  it("offers to generate when no recap exists yet (GET 404) and POSTs on generate", async () => {
    vi.spyOn(storiesApi, "getArcRecap").mockRejectedValue(new ApiError(404, "No arc recap generated yet"));
    const refreshSpy = vi
      .spyOn(storiesApi, "refreshArcRecap")
      .mockResolvedValue({ ...RECAP, recap: "## Open Threads\n\nThe sealed door.", persisted: true });
    const user = userEvent.setup();
    renderSection();

    const generate = await screen.findByTestId("arc-recap-generate");
    expect(screen.queryByTestId("arc-recap-body")).not.toBeInTheDocument();
    await user.click(generate);

    await waitFor(() => expect(refreshSpy).toHaveBeenCalledWith("story-1", "standard"));
    expect(await screen.findByTestId("arc-recap-body")).toHaveTextContent("The sealed door.");
  });

  it("refreshes with the selected length", async () => {
    vi.spyOn(storiesApi, "getArcRecap").mockResolvedValue(RECAP);
    const refreshSpy = vi.spyOn(storiesApi, "refreshArcRecap").mockResolvedValue(RECAP);
    const user = userEvent.setup();
    renderSection();

    await screen.findByTestId("arc-recap-body");
    await user.selectOptions(screen.getByTestId("arc-recap-detail"), "detailed");
    await user.click(screen.getByTestId("arc-recap-refresh"));

    await waitFor(() => expect(refreshSpy).toHaveBeenCalledWith("story-1", "detailed"));
  });

  it("keeps the persisted recap visible when a refresh fails", async () => {
    vi.spyOn(storiesApi, "getArcRecap").mockResolvedValue(RECAP);
    vi.spyOn(storiesApi, "refreshArcRecap").mockRejectedValue(new ApiError(500, "boom"));
    const user = userEvent.setup();
    renderSection();

    await screen.findByTestId("arc-recap-body");
    await user.click(screen.getByTestId("arc-recap-refresh"));

    expect(await screen.findByText(/refresh failed/i)).toBeInTheDocument();
    expect(screen.getByTestId("arc-recap-body")).toHaveTextContent("chapel key");
  });

  it("hides the body behind the toggle when collapsible", async () => {
    vi.spyOn(storiesApi, "getArcRecap").mockResolvedValue(RECAP);
    const user = userEvent.setup();
    renderSection({ collapsible: true, defaultOpen: false });

    expect(screen.getByTestId("arc-recap-toggle")).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByTestId("arc-recap-body")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("arc-recap-toggle"));
    expect(await screen.findByTestId("arc-recap-body")).toBeInTheDocument();
  });

  it("renders nothing without a story", () => {
    const { container } = renderSection({ storyId: null });
    expect(container).toBeEmptyDOMElement();
  });
});
