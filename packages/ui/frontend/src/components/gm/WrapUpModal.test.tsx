// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WrapUpModal } from "./WrapUpModal";
import { chatApi } from "@/lib/api";

// P1.3 — guided end-of-session wrap-up digest. Mounting the modal fires
// chatApi.wrapUp; the modal owns the progress state (several LLM calls
// server-side) and an error state with retry.

vi.mock("@/lib/api", () => ({
  chatApi: { wrapUp: vi.fn() },
}));

const DIGEST = {
  recap: "The party found the sealed door beneath the chapel; Mira pocketed the key.",
  accepted: 2,
  rejected: 1,
  pending: 1,
  canon_items: [
    {
      proposal_id: "p-1",
      change_type: "fact",
      status: "accepted",
      label: "Mira pocketed the chapel key",
    },
    {
      proposal_id: "p-2",
      change_type: "entity",
      status: "rejected",
      label: "The king greeted the party",
    },
  ],
  open_threads: ["The sealed door", "The missing key"],
  next_prep: {
    recap: "Recent scenes recap",
    open_threads: ["The sealed door"],
    hooks: [
      {
        title: "The cult gathers",
        description: "The dawn meeting gives the party a chance to spy.",
        urgency: "medium",
        suggested_scene_type: "social",
        connected_entities: [],
      },
    ],
    npc_reminders: ["Mira"],
    world_state_changes: [],
  },
};

function renderModal(onClose = () => {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <WrapUpModal sessionId="rec-1" onClose={onClose} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("WrapUpModal (P1.3)", () => {
  it("shows a progress state while the wrap-up runs", async () => {
    vi.mocked(chatApi.wrapUp).mockReturnValue(new Promise(() => {}) as never);
    renderModal();
    expect(await screen.findByTestId("wrap-up-loading")).toBeInTheDocument();
    expect(chatApi.wrapUp).toHaveBeenCalledWith("rec-1");
  });

  it("renders all digest sections after a successful wrap-up", async () => {
    vi.mocked(chatApi.wrapUp).mockResolvedValue(DIGEST as never);
    renderModal();

    expect(await screen.findByTestId("wrap-up-recap")).toHaveTextContent(
      "Mira pocketed the key",
    );
    const canon = screen.getByTestId("wrap-up-canon");
    expect(canon).toHaveTextContent("2 accepted");
    expect(canon).toHaveTextContent("1 rejected");
    expect(canon).toHaveTextContent("1 pending");
    expect(canon).toHaveTextContent("Mira pocketed the chapel key");
    expect(canon).toHaveTextContent("The king greeted the party");

    const threads = screen.getByTestId("wrap-up-threads");
    expect(threads).toHaveTextContent("The sealed door");
    expect(threads).toHaveTextContent("The missing key");

    const nextPrep = screen.getByTestId("wrap-up-next-prep");
    expect(nextPrep).toHaveTextContent("The cult gathers");
    expect(nextPrep).toHaveTextContent("Remember: Mira");
  });

  it("shows an error state with a retry button when the wrap-up fails", async () => {
    vi.mocked(chatApi.wrapUp).mockRejectedValue(new Error("LLM timeout"));
    renderModal();

    const error = await screen.findByTestId("wrap-up-error");
    expect(error).toHaveTextContent("LLM timeout");

    vi.mocked(chatApi.wrapUp).mockResolvedValue(DIGEST as never);
    await userEvent.click(screen.getByRole("button", { name: /Try again/ }));
    expect(await screen.findByTestId("wrap-up-recap")).toBeInTheDocument();
  });

  it("renders empty-state copy when there are no canon items, threads, or hooks", async () => {
    vi.mocked(chatApi.wrapUp).mockResolvedValue({
      ...DIGEST,
      accepted: 0,
      rejected: 0,
      pending: 0,
      canon_items: [],
      open_threads: [],
      next_prep: null,
    } as never);
    renderModal();

    const canon = await screen.findByTestId("wrap-up-canon");
    expect(canon).toHaveTextContent("No canon changes were proposed this session.");
    expect(screen.getByTestId("wrap-up-threads")).toHaveTextContent(
      "No dangling threads on the board.",
    );
    expect(screen.getByTestId("wrap-up-next-prep")).toHaveTextContent(
      "No hooks drafted",
    );
  });
});
