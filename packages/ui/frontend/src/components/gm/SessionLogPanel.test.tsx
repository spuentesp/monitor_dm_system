// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { gmTableApi } from "@/lib/gm-table-api";
import { SessionLogPanel } from "./SessionLogPanel";

function renderPanel(universeId: string | null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SessionLogPanel universeId={universeId} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  globalThis.fetch = vi.fn(() =>
    Promise.resolve(new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } })),
  ) as unknown as typeof fetch;
});

describe("SessionLogPanel (CF-5/CF-8)", () => {
  it("prompts for a universe when none is selected", () => {
    renderPanel(null);
    expect(screen.getByText(/select a universe to log/i)).toBeInTheDocument();
  });

  it("proposes canon changes and shows contradiction flags", async () => {
    const spy = vi.spyOn(gmTableApi, "proposeSessionLog").mockResolvedValue({
      batch_id: "b1b1b1b1-0000-0000-0000-000000000000",
      items: [
        {
          statement: "the key is now with Mira",
          participants: ["Mira"],
          locations: [],
          proposal_id: "p-1",
          flags: [
            {
              kind: "direct",
              severity: "medium",
              explanation: "Canon says the key is lost.",
            },
          ],
        },
        {
          statement: "the docks burned",
          participants: [],
          locations: ["Ironwatch"],
          proposal_id: "p-2",
          flags: [],
        },
      ],
      proposal_errors: [],
    });
    const user = userEvent.setup();
    renderPanel("u-1");

    await user.type(
      screen.getByPlaceholderText(/paste or type what happened/i),
      "Mira took back the key. The docks burned.",
    );
    await user.click(screen.getByRole("button", { name: /propose canon changes/i }));

    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith({
        universe_id: "u-1",
        log_text: "Mira took back the key. The docks burned.",
      }),
    );
    // Items render with participants/locations and their flags.
    expect(await screen.findByText("the key is now with Mira")).toBeInTheDocument();
    expect(screen.getByText("the docks burned")).toBeInTheDocument();
    expect(screen.getByText("[direct · medium] Canon says the key is lost.")).toBeInTheDocument();
    expect(screen.getByText("Mira")).toBeInTheDocument();
    expect(screen.getByText("Ironwatch")).toBeInTheDocument();
    // Everything is staged for the CF-8 queue.
    expect(screen.getByText(/staged for review in the Canon Review/i)).toBeInTheDocument();
  });

  it("surfaces analysis failures without staging anything", async () => {
    vi.spyOn(gmTableApi, "proposeSessionLog").mockRejectedValue(new Error("boom"));
    const user = userEvent.setup();
    renderPanel("u-1");

    await user.type(screen.getByPlaceholderText(/paste or type what happened/i), "Something.");
    await user.click(screen.getByRole("button", { name: /propose canon changes/i }));

    expect(await screen.findByText(/analysis failed/i)).toBeInTheDocument();
  });
});
