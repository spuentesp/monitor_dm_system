// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { gmApi, ApiError } from "@/lib/api";
import type { Contradiction } from "@/lib/types";
import { ContradictionsPanel } from "./ContradictionsPanel";

const CONTRADICTION: Contradiction = {
  fact_a: "The king is dead",
  fact_b: "The king greeted the party",
  severity: "high",
  conflict_type: "semantic",
  explanation: "Canon says the king died last winter.",
  suggestion: "Mark as apparent contradiction.",
};

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ContradictionsPanel universeId="u-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("ContradictionsPanel", () => {
  it("starts from an empty state and detects with a cancellable signal", async () => {
    const detect = vi
      .spyOn(gmApi, "detectContradictions")
      .mockResolvedValue({ contradictions: [CONTRADICTION] });
    const user = userEvent.setup();
    renderPanel();

    expect(screen.getByText(/click detect to find contradictions/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /detect/i }));

    await waitFor(() => expect(detect).toHaveBeenCalled());
    expect(detect).toHaveBeenCalledWith(
      "u-1",
      expect.objectContaining({ scope: "universe", signal: expect.any(AbortSignal) }),
    );
    expect(await screen.findByText("The king is dead")).toBeInTheDocument();
    expect(screen.getByText(/high severity/)).toBeInTheDocument();
  });

  it("offers a Cancel action while detecting and drops the pending state", async () => {
    vi.spyOn(gmApi, "detectContradictions").mockReturnValue(new Promise(() => {}));
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: /detect/i }));

    const cancel = await screen.findByRole("button", { name: "Cancel detection" });
    await user.click(cancel);

    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Cancel detection" })).not.toBeInTheDocument(),
    );
    // Cancelled — not an error, and Detect is usable again.
    expect(screen.queryByText(/failed to detect contradictions/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /detect/i })).toBeEnabled();
  });

  it("shows the failure state when detection errors", async () => {
    vi.spyOn(gmApi, "detectContradictions").mockRejectedValue(new Error("boom"));
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: /detect/i }));

    expect(await screen.findByText(/failed to detect contradictions/i)).toBeInTheDocument();
  });

  it("turns a 429 into the daily-limit message (UX-4 §3)", async () => {
    vi.spyOn(gmApi, "detectContradictions").mockRejectedValue(
      new ApiError(429, '{"detail":"over cap"}'),
    );
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: /detect/i }));

    expect(
      await screen.findByText("Daily limit reached - resets 00:00 UTC. Ask your admin to raise it."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/failed to detect contradictions/i)).not.toBeInTheDocument();
  });

  it("prompts for a universe when none is selected", () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ContradictionsPanel universeId={null} />
      </QueryClientProvider>,
    );
    expect(screen.getByText(/select a universe to detect contradictions/i)).toBeInTheDocument();
  });
});
