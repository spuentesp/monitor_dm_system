// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ImageSuggestionChip } from "./ImageSuggestionChip";
import * as api from "@/lib/api";
import type { ImageSuggestionMeta } from "@/features/chat/types";

vi.mock("@/components/NotificationProvider", () => ({
  useNotify: () => ({ notify: vi.fn() }),
}));

const sceneSuggestion: ImageSuggestionMeta = {
  suggestion_id: "11111111-1111-4111-8111-111111111111",
  asset_type: "location",
  subject_entity_ids: ["22222222-2222-4222-8222-222222222222"],
  reason: "location_change",
  aspect_ratio: "16:9",
  source_turn_id: "turn-9",
};

const portraitSuggestion: ImageSuggestionMeta = {
  suggestion_id: "33333333-3333-4333-8333-333333333333",
  asset_type: "portrait",
  subject_entity_ids: ["44444444-4444-4444-8444-444444444444"],
  reason: "npc_entry",
  aspect_ratio: "1:1",
  source_turn_id: "turn-6",
};

const sceneResponse = {
  image_url: "https://minio.example.com/presigned/scene.png",
  key: "assets/scene/session-s-1/x.png",
  asset_id: "55555555-5555-4555-8555-555555555555",
  approval_status: "pending" as const,
  prompt_warnings: [],
};

const sceneResponseWithFallback = {
  ...sceneResponse,
  prompt_warnings: [
    "text-only fallback: provider does not consume reference images; dropped 2 approved reference(s) at the orchestrator.",
  ],
};

const portraitResponse = {
  avatar_url: "https://minio.example.com/presigned/portrait.png",
  key: "assets/portrait/character-c-1/x.png",
  asset_id: "66666666-6666-4666-8666-666666666666",
  approval_status: "pending" as const,
  prompt_warnings: [],
};

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("ImageSuggestionChip", () => {
  it("renders a chip and never generates until clicked", () => {
    const genScene = vi.spyOn(api.imageApi, "generateScene");
    const genPortrait = vi.spyOn(api.imageApi, "generatePortrait");
    render(<ImageSuggestionChip suggestion={sceneSuggestion} sessionId="s-1" onSettled={vi.fn()} />);

    expect(screen.getByRole("button", { name: /illustrate/i })).toBeInTheDocument();
    expect(genScene).not.toHaveBeenCalled();
    expect(genPortrait).not.toHaveBeenCalled();
  });

  it("click generates a scene image with loop_suggestion trigger + turn provenance, then shows the pending preview", async () => {
    const user = userEvent.setup();
    const genScene = vi.spyOn(api.imageApi, "generateScene").mockResolvedValue(sceneResponse);
    render(<ImageSuggestionChip suggestion={sceneSuggestion} sessionId="s-1" onSettled={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /illustrate/i }));

    expect(genScene).toHaveBeenCalledWith({
      session_id: "s-1",
      trigger: "loop_suggestion",
      source_turn_id: "turn-9",
    });
    // The returned PENDING asset reuses the Task 8 pending-preview flow.
    const img = await screen.findByRole("img");
    expect(img).toHaveAttribute("src", sceneResponse.image_url);
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
  });

  it("portrait suggestions with a character anchor call the portrait endpoint", async () => {
    const user = userEvent.setup();
    const genPortrait = vi.spyOn(api.imageApi, "generatePortrait").mockResolvedValue(portraitResponse);
    const genScene = vi.spyOn(api.imageApi, "generateScene");
    render(
      <ImageSuggestionChip
        suggestion={portraitSuggestion}
        sessionId="s-1"
        characterId="c-1"
        onSettled={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /illustrate/i }));

    expect(genPortrait).toHaveBeenCalledWith("c-1", {
      trigger: "loop_suggestion",
      source_turn_id: "turn-6",
    });
    expect(genScene).not.toHaveBeenCalled();
    expect(await screen.findByRole("img")).toHaveAttribute("src", portraitResponse.avatar_url);
  });

  it("portrait suggestions without a character anchor fall back to the scene endpoint", async () => {
    const user = userEvent.setup();
    const genScene = vi.spyOn(api.imageApi, "generateScene").mockResolvedValue(sceneResponse);
    const genPortrait = vi.spyOn(api.imageApi, "generatePortrait");
    render(<ImageSuggestionChip suggestion={portraitSuggestion} sessionId="s-1" onSettled={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /illustrate/i }));

    expect(genScene).toHaveBeenCalledWith({
      session_id: "s-1",
      trigger: "loop_suggestion",
      source_turn_id: "turn-6",
    });
    expect(genPortrait).not.toHaveBeenCalled();
  });

  it("dismiss settles the chip without generating anything", async () => {
    const user = userEvent.setup();
    const onSettled = vi.fn();
    const genScene = vi.spyOn(api.imageApi, "generateScene");
    render(<ImageSuggestionChip suggestion={sceneSuggestion} sessionId="s-1" onSettled={onSettled} />);

    await user.click(screen.getByRole("button", { name: /dismiss/i }));

    expect(onSettled).toHaveBeenCalledWith(sceneSuggestion.suggestion_id);
    expect(genScene).not.toHaveBeenCalled();
  });

  it("approving the pending preview settles the chip (parent removes it)", async () => {
    const user = userEvent.setup();
    const onSettled = vi.fn();
    vi.spyOn(api.imageApi, "generateScene").mockResolvedValue(sceneResponse);
    vi.spyOn(api.imageApi, "approveAsset").mockResolvedValue(undefined as never);
    render(<ImageSuggestionChip suggestion={sceneSuggestion} sessionId="s-1" onSettled={onSettled} />);

    await user.click(screen.getByRole("button", { name: /illustrate/i }));
    await user.click(await screen.findByRole("button", { name: "Approve" }));

    await waitFor(() => expect(onSettled).toHaveBeenCalledWith(sceneSuggestion.suggestion_id));
  });

  it("a failed generation keeps the chip retryable and does not settle", async () => {
    const user = userEvent.setup();
    const onSettled = vi.fn();
    vi.spyOn(api.imageApi, "generateScene").mockRejectedValue(new Error("provider down"));
    render(<ImageSuggestionChip suggestion={sceneSuggestion} sessionId="s-1" onSettled={onSettled} />);

    await user.click(screen.getByRole("button", { name: /illustrate/i }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /illustrate/i })).toBeEnabled(),
    );
    expect(onSettled).not.toHaveBeenCalled();
  });

  it("forwards prompt_warnings to the pending preview so the text-only fallback badge appears", async () => {
    const user = userEvent.setup();
    vi.spyOn(api.imageApi, "generateScene").mockResolvedValue(sceneResponseWithFallback);
    render(<ImageSuggestionChip suggestion={sceneSuggestion} sessionId="s-1" onSettled={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /illustrate/i }));

    expect(await screen.findByTestId("ref-mode-text-only")).toHaveTextContent(/text-only fallback/i);
  });
});
