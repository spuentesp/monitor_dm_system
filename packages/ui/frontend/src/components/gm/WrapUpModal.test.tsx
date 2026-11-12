// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WrapUpModal } from "./WrapUpModal";
import { chatApi, gmApi } from "@/lib/api";

// P1.3 — guided end-of-session wrap-up digest. Mounting the modal fires
// chatApi.wrapUp; the modal owns the progress state (several LLM calls
// server-side) and an error state with retry.

vi.mock("@/lib/api", () => ({
  chatApi: { wrapUp: vi.fn() },
  req: vi.fn(),
  gmApi: {
    sharePublish: vi.fn(),
    shareUnpublish: vi.fn(),
  },
}));

import { gmTableApi } from "@/lib/gm-table-api";

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

function renderModal(onClose = () => {}, scope?: { universeId?: string | null; storyId?: string | null }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <WrapUpModal
        sessionId="rec-1"
        universeId={scope?.universeId ?? null}
        storyId={scope?.storyId ?? null}
        onClose={onClose}
      />
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

  // CF-11 — recorder wrap-up gains the world clock readout + advance control.
  it("shows the world clock section and advances after confirmation when ids are given", async () => {
    vi.mocked(chatApi.wrapUp).mockResolvedValue(DIGEST as never);
    const clock = {
      universe_id: "u-1",
      story_id: "story-1",
      current_at: "1012-03-04T09:00:00+00:00",
      display: "1012-03-04T09:00:00+00:00",
      deadlines: [],
      advances: [],
      offscreen_summary: "",
      offscreen_summary_at: null,
      updated_at: "1012-03-04T09:00:00+00:00",
    };
    vi.spyOn(gmTableApi, "getClock").mockResolvedValue({ found: true, clock });
    const advanceSpy = vi.spyOn(gmTableApi, "advanceClock").mockResolvedValue({
      clock: { ...clock, current_at: "1012-03-05T09:00:00+00:00", display: "1012-03-05T09:00:00+00:00" },
      changed: true,
      initialized: false,
      crossed: [],
      due: [],
      offscreen_summary: "A quiet day in town.",
      npc_activities: [],
      staged_proposal_ids: [],
      staging_errors: [],
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <WrapUpModal
          sessionId="rec-1"
          onClose={() => {}}
          universeId="u-1"
          storyId="story-1"
        />
      </QueryClientProvider>,
    );

    expect(await screen.findByTestId("wrap-up-clock")).toBeInTheDocument();
    expect(await screen.findByTestId("clock-readout")).toHaveTextContent("1012-03-04T09:00:00");

    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Advance world time"), "+1 day");
    await user.click(screen.getByRole("button", { name: "Advance" }));
    await user.click(screen.getByTestId("confirm-advance"));

    await waitFor(() =>
      expect(advanceSpy).toHaveBeenCalledWith({
        universe_id: "u-1",
        story_id: "story-1",
        delta: "+1 day",
      }),
    );
    expect(await screen.findByTestId("clock-info")).toHaveTextContent("World time is now");
  });

  it("hides the clock section when the recording has no story attached", async () => {
    vi.mocked(chatApi.wrapUp).mockResolvedValue(DIGEST as never);
    renderModal();

    expect(await screen.findByTestId("wrap-up-recap")).toBeInTheDocument();
    expect(screen.queryByTestId("wrap-up-clock")).not.toBeInTheDocument();
  });
});

describe("WrapUpModal publish (CF-14)", () => {
  it("hides the share section when the session has no story scope", async () => {
    vi.mocked(chatApi.wrapUp).mockResolvedValue(DIGEST as never);
    renderModal();
    await screen.findByTestId("wrap-up-recap");
    expect(screen.queryByTestId("wrap-up-share")).not.toBeInTheDocument();
  });

  it("publishes the recap and shows the share link", async () => {
    vi.mocked(chatApi.wrapUp).mockResolvedValue(DIGEST as never);
    vi.mocked(gmApi.sharePublish).mockResolvedValue({
      artifact_id: "art-9",
      token: "tok-abc",
      share_path: "/share/tok-abc",
      published: true,
    } as never);
    renderModal(undefined, { universeId: "uni-1", storyId: "story-1" });

    await userEvent.click(await screen.findByTestId("wrap-up-publish"));
    expect(gmApi.sharePublish).toHaveBeenCalledWith({
      universe_id: "uni-1",
      story_id: "story-1",
      artifact_type: "recap",
      title: "Session recap",
      content: DIGEST.recap,
      session_id: "rec-1",
    });

    const link = await screen.findByTestId("wrap-up-share-link");
    expect(screen.getByTestId("wrap-up-share-url")).toHaveTextContent(
      "/share/tok-abc",
    );
    expect(link).toBeInTheDocument();
    expect(screen.queryByTestId("wrap-up-publish")).not.toBeInTheDocument();
  });

  it("unpublishing returns to the publish button", async () => {
    vi.mocked(chatApi.wrapUp).mockResolvedValue(DIGEST as never);
    vi.mocked(gmApi.sharePublish).mockResolvedValue({
      artifact_id: "art-9",
      token: "tok-abc",
      share_path: "/share/tok-abc",
      published: true,
    } as never);
    vi.mocked(gmApi.shareUnpublish).mockResolvedValue({
      artifact_id: "art-9",
      published: false,
    } as never);
    renderModal(undefined, { universeId: "uni-1", storyId: "story-1" });

    await userEvent.click(await screen.findByTestId("wrap-up-publish"));
    await screen.findByTestId("wrap-up-share-link");

    await userEvent.click(screen.getByTestId("wrap-up-unpublish"));
    await waitFor(() => expect(screen.getByTestId("wrap-up-publish")).toBeInTheDocument());
    expect(gmApi.shareUnpublish).toHaveBeenCalledWith({
      universe_id: "uni-1",
      artifact_id: "art-9",
    });
  });
});
