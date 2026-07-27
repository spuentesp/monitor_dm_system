// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CanonReviewPanel } from "./CanonReviewPanel";
import * as api from "@/lib/api";
import type { CanonQueue, ProposalItem, SceneReview } from "@/lib/types";

const STORY_ID = "11111111-1111-1111-1111-111111111111";
const SCENE_ID = "22222222-2222-2222-2222-222222222222";

function proposal(id: string, status: "pending" | "accepted" | "rejected" = "pending"): ProposalItem {
  return {
    proposal_id: id,
    change_type: "fact",
    content: { text: `Proposal ${id}` },
    confidence: 0.95,
    authority: "gm",
    proposer: "Narrator",
    status,
    evidence: [],
    created_at: null,
  };
}

function queue(scenes: SceneReview[], totalPending: number): CanonQueue {
  return { story_id: STORY_ID, scenes, total_pending: totalPending };
}

function sceneReview(pending: ProposalItem[]): SceneReview {
  return { scene_id: SCENE_ID, pending, accepted: [], rejected: [], by_change_type: { fact: pending.length } };
}

function renderPanel(props: { storyId?: string | null; sceneId?: string | null }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CanonReviewPanel storyId={props.storyId ?? null} sceneId={props.sceneId ?? null} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("CanonReviewPanel — reason capture (F2-3d)", () => {
  it("passes the typed accept reason to the verdict mutation", async () => {
    vi.spyOn(api.canonApi, "storyQueue").mockResolvedValue(
      queue([sceneReview([proposal("p1")])], 1),
    );
    const acceptSpy = vi.spyOn(api.canonApi, "acceptProposal").mockResolvedValue(proposal("p1", "accepted"));
    const user = userEvent.setup();

    renderPanel({ storyId: STORY_ID });

    await user.click(await screen.findByRole("button", { name: /^accept$/i }));
    await user.type(screen.getByPlaceholderText(/reason for accepting/i), "Consistent with lore");
    await user.click(screen.getByRole("button", { name: /^accept$/i }));

    await waitFor(() =>
      expect(acceptSpy).toHaveBeenCalledWith("p1", "Consistent with lore"),
    );
  });

  it("passes the typed reject reason to the verdict mutation", async () => {
    vi.spyOn(api.canonApi, "storyQueue").mockResolvedValue(
      queue([sceneReview([proposal("p1")])], 1),
    );
    const rejectSpy = vi.spyOn(api.canonApi, "rejectProposal").mockResolvedValue(proposal("p1", "rejected"));
    const user = userEvent.setup();

    renderPanel({ storyId: STORY_ID });

    await user.click(await screen.findByRole("button", { name: /^reject$/i }));
    await user.type(screen.getByPlaceholderText(/reason for rejecting/i), "Contradicts chapter 3");
    await user.click(screen.getByRole("button", { name: /^reject$/i }));

    await waitFor(() =>
      expect(rejectSpy).toHaveBeenCalledWith("p1", "Contradicts chapter 3"),
    );
  });
});

describe("CanonReviewPanel — batch actions", () => {
  it("scene-mode Accept All batches exactly the current scene's pending proposals", async () => {
    vi.spyOn(api.canonApi, "sceneReview").mockResolvedValue(
      sceneReview([proposal("p1"), proposal("p2")]),
    );
    const batchSpy = vi.spyOn(api.canonApi, "batchVerdicts")
      .mockResolvedValue({ results: [], errors: [] });
    const acceptSpy = vi.spyOn(api.canonApi, "acceptProposal");
    const user = userEvent.setup();

    renderPanel({ storyId: null, sceneId: SCENE_ID });

    await user.click(await screen.findByRole("button", { name: /accept all \(2\)/i }));

    await waitFor(() => expect(batchSpy).toHaveBeenCalledTimes(1));
    expect(batchSpy).toHaveBeenCalledWith([
      { proposal_id: "p1", decision: "accepted", reason: "Batch approved by GM" },
      { proposal_id: "p2", decision: "accepted", reason: "Batch approved by GM" },
    ]);
    expect(acceptSpy).not.toHaveBeenCalled();
  });

  it("story-mode Reject All batches every pending proposal in the queue", async () => {
    vi.spyOn(api.canonApi, "storyQueue").mockResolvedValue(
      queue([sceneReview([proposal("p1"), proposal("p2")])], 2),
    );
    const batchSpy = vi.spyOn(api.canonApi, "batchVerdicts")
      .mockResolvedValue({ results: [], errors: [] });
    const user = userEvent.setup();

    renderPanel({ storyId: STORY_ID });

    await user.click(await screen.findByRole("button", { name: /reject all/i }));

    await waitFor(() => expect(batchSpy).toHaveBeenCalledTimes(1));
    const items = batchSpy.mock.calls[0][0];
    expect(items.map(i => i.proposal_id).sort()).toEqual(["p1", "p2"]);
    expect(items.every(i => i.decision === "rejected")).toBe(true);
  });

  it("surfaces per-item failures from the batch response instead of blanket success", async () => {
    vi.spyOn(api.canonApi, "storyQueue").mockResolvedValue(
      queue([sceneReview([proposal("p1"), proposal("p2")])], 2),
    );
    vi.spyOn(api.canonApi, "batchVerdicts").mockResolvedValue({
      results: [{
        proposal_id: "p1",
        status: "accepted",
        decision_metadata: { decided_by: "GM", decided_at: "", reason: "" },
      }],
      errors: [{ proposal_id: "p2", error: "Proposal already decided" }],
    });
    const user = userEvent.setup();

    renderPanel({ storyId: STORY_ID });

    await user.click(await screen.findByRole("button", { name: /accept all \(2\)/i }));

    expect(await screen.findByText(/1 applied, 1 failed/i)).toBeInTheDocument();
    expect(screen.getByText(/proposal already decided/i)).toBeInTheDocument();
  });
});

describe("CanonReviewPanel — story-level lane (F2-3d)", () => {
  it("renders proposals with no scene under a story-level lane", async () => {
    vi.spyOn(api.canonApi, "storyQueue").mockResolvedValue(
      queue([{ ...sceneReview([proposal("p-story")]), scene_id: null }], 1),
    );

    renderPanel({ storyId: STORY_ID });

    expect(await screen.findByText("Story-level")).toBeInTheDocument();
    expect(screen.getByText("Proposal p-story")).toBeInTheDocument();
  });
});
