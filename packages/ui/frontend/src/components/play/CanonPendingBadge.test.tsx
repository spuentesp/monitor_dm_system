// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { CanonPendingBadge } from "./CanonPendingBadge";

vi.mock("@/lib/api", () => ({
  canonApi: { storyQueue: vi.fn() },
}));

import { canonApi } from "@/lib/api";

function renderBadge(storyId: string | null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<CanonPendingBadge storyId={storyId} />, { wrapper });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("CanonPendingBadge", () => {
  it("renders nothing when the story has no pending proposals", async () => {
    vi.mocked(canonApi.storyQueue).mockResolvedValue({
      story_id: "st-1",
      scenes: [],
      total_pending: 0,
    } as never);
    const { container } = renderBadge("st-1");
    await vi.waitFor(() => expect(canonApi.storyQueue).toHaveBeenCalled());
    expect(screen.queryByTestId("canon-pending-badge")).not.toBeInTheDocument();
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing without a story binding", () => {
    renderBadge(null);
    expect(canonApi.storyQueue).not.toHaveBeenCalled();
    expect(screen.queryByTestId("canon-pending-badge")).not.toBeInTheDocument();
  });

  it("links to /forge/review with the pending count", async () => {
    vi.mocked(canonApi.storyQueue).mockResolvedValue({
      story_id: "st-1",
      scenes: [],
      total_pending: 3,
    } as never);
    renderBadge("st-1");
    const badge = await screen.findByTestId("canon-pending-badge");
    expect(badge).toHaveAttribute("href", "/forge/review");
    expect(badge).toHaveTextContent("3 canon changes pending review");
  });

  it("uses singular wording for one pending change", async () => {
    vi.mocked(canonApi.storyQueue).mockResolvedValue({
      story_id: "st-1",
      scenes: [],
      total_pending: 1,
    } as never);
    renderBadge("st-1");
    const badge = await screen.findByTestId("canon-pending-badge");
    expect(badge).toHaveTextContent("1 canon change pending review");
  });
});
