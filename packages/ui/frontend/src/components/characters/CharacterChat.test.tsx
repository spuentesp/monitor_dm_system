// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CharacterChat } from "./CharacterChat";
import * as api from "@/lib/api";
import type { StandaloneCharacter } from "@/lib/types";

vi.mock("@/components/NotificationProvider", () => ({
  useNotify: () => ({ notify: vi.fn() }),
}));

const char = {
  id: "c-1",
  name: "Wisp",
  description: "A fox-spirit guide.",
  avatar_url: null,
  personality: "playful",
  gm_notes: "",
  first_message: "Well met, traveller.",
  is_ooc_persona: false,
  entity_id: "e-1",
  default_universe_id: null,
  versions: [],
  memory_count: 7,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-30T00:00:00Z",
} as StandaloneCharacter;

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api.entitiesApi, "startCharacterConversation").mockResolvedValue({
    conversation_id: "conv-1",
    character_id: "c-1",
    version_id: "v-1",
    entity_id: "e-1",
    universe_id: "u-1",
    opening: "Well met, traveller.",
  });
  vi.spyOn(api.entitiesApi, "endCharacterConversation").mockResolvedValue({ ended: true, proposals: 0 });
  vi.spyOn(api.imageApi, "generateScene").mockResolvedValue({
    image_url: "https://minio.example.com/scene.png",
    key: "scenes/conversation-conv-1/x.png",
  });
});

describe("CharacterChat — scene image", () => {
  it("calls the scene endpoint for the active conversation and shows the image inline", async () => {
    const user = userEvent.setup();
    render(<CharacterChat character={char} onBack={() => {}} />);

    // Wait for the conversation to open
    expect(await screen.findByText("Well met, traveller.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /generate scene image/i }));

    await waitFor(() =>
      expect(api.imageApi.generateScene).toHaveBeenCalledWith({
        conversation_id: "conv-1",
        last_n: 12,
      }),
    );
    const img = await screen.findByAltText("Scene illustration");
    expect(img).toHaveAttribute("src", "https://minio.example.com/scene.png");
  });

  it("disables the scene button until a conversation is open", () => {
    vi.spyOn(api.entitiesApi, "startCharacterConversation").mockReturnValue(new Promise(() => {}));
    render(<CharacterChat character={char} onBack={() => {}} />);
    expect(screen.getByRole("button", { name: /generate scene image/i })).toBeDisabled();
  });
});
