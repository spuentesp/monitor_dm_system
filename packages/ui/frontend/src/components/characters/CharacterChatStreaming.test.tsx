// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CharacterChat } from "./CharacterChat";
import * as api from "@/lib/api";
import { lightRpApi, type StreamEvent } from "@/lib/lightRpApi";
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
  memory_count: 0,
  created_at: "2026-11-01T00:00:00Z",
  updated_at: "2026-11-01T00:00:00Z",
} as StandaloneCharacter;

function fakeStream(events: StreamEvent[]): AsyncGenerator<StreamEvent> {
  return (async function* () {
    for (const event of events) yield event;
  })();
}

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
});

describe("CharacterChat — streaming send", () => {
  it("streams the reply through sendStream with the conversation and text, rendering the tokens", async () => {
    const sendStream = vi.spyOn(lightRpApi, "sendStream").mockReturnValue(
      fakeStream([
        { type: "token", text: "The " },
        { type: "token", text: "road " },
        { type: "token", text: "winds " },
        { type: "token", text: "on." },
        {
          type: "done",
          conversation_id: "conv-1",
          text: "The road winds on.",
          emotional_state: "calm",
          relationship_snapshot: { trust: 0.2 },
        },
      ]),
    );
    const user = userEvent.setup();
    render(<CharacterChat character={char} onBack={() => {}} />);
    expect(await screen.findByText("Well met, traveller.")).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText(/message wisp/i), "Which way now?");
    await user.click(screen.getByRole("button", { name: /send/i }));

    // Cross-component call: the streaming endpoint gets the character, the
    // conversation, and exactly what the player typed.
    await waitFor(() =>
      expect(sendStream).toHaveBeenCalledWith("c-1", "conv-1", "Which way now?", {
        include_cross_incarnation: false,
      }),
    );
    expect(await screen.findByText("The road winds on.")).toBeInTheDocument();
    // The done event surfaces the emotional read in the bubble and the panel.
    expect((await screen.findAllByText("calm")).length).toBeGreaterThan(0);
  });

  it("labels each speaker and strips the model's 'Name:' prefix from character replies", async () => {
    vi.spyOn(lightRpApi, "sendStream").mockReturnValue(
      fakeStream([
        { type: "token", text: "Wisp: Hello, traveller." },
        {
          type: "done",
          conversation_id: "conv-1",
          text: "Wisp: Hello, traveller.",
          emotional_state: null,
          relationship_snapshot: {},
        },
      ]),
    );
    const user = userEvent.setup();
    render(<CharacterChat character={char} onBack={() => {}} />);
    expect(await screen.findByText("Well met, traveller.")).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText(/message wisp/i), "Hi Wisp");
    await user.click(screen.getByRole("button", { name: /send/i }));

    // The character bubble shows the reply without the "Wisp:" prefix...
    expect(await screen.findByText("Hello, traveller.")).toBeInTheDocument();
    // ...the player's own line is visible and labelled...
    expect(screen.getByText("Hi Wisp")).toBeInTheDocument();
    expect(screen.getByText("You")).toBeInTheDocument();
    // ...and character messages carry the character's name as a label.
    expect(screen.getAllByText("Wisp").length).toBeGreaterThan(1);
  });

  it("reopening a persisted conversation loads its transcript and does not start a new one", async () => {
    const start = vi.spyOn(api.entitiesApi, "startCharacterConversation");
    vi.spyOn(lightRpApi, "getConversationTurns").mockResolvedValue({
      conversation_id: "conv-old",
      status: "active",
      turns: [
        { turn_index: 0, speaker_role: "npc", entity_name: "Wisp", text: "Well met, traveller.", emotional_state: null, timestamp: null },
        { turn_index: 1, speaker_role: "player", entity_name: "Player", text: "Hi Wisp", emotional_state: null, timestamp: null },
        { turn_index: 2, speaker_role: "npc", entity_name: "Wisp", text: "The road winds on.", emotional_state: "calm", timestamp: null },
      ],
    });
    const sendStream = vi.spyOn(lightRpApi, "sendStream").mockReturnValue(
      fakeStream([
        {
          type: "done",
          conversation_id: "conv-old",
          text: "Glad to see you again.",
          emotional_state: "warm",
          relationship_snapshot: {},
        },
      ]),
    );
    const user = userEvent.setup();
    render(<CharacterChat character={char} onBack={() => {}} resumeConversationId="conv-old" />);

    // History renders, no new conversation is started.
    expect(await screen.findByText("Hi Wisp")).toBeInTheDocument();
    expect(screen.getByText("The road winds on.")).toBeInTheDocument();
    expect(start).not.toHaveBeenCalled();

    // Sending continues the SAME conversation.
    await user.type(screen.getByPlaceholderText(/message wisp/i), "You still there?");
    await user.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() =>
      expect(sendStream).toHaveBeenCalledWith("c-1", "conv-old", "You still there?", {
        include_cross_incarnation: false,
      }),
    );
    expect(await screen.findByText("Glad to see you again.")).toBeInTheDocument();
  });

  it("opening a pre-started conversation does not start another one", async () => {
    const start = vi.spyOn(api.entitiesApi, "startCharacterConversation");
    render(
      <CharacterChat
        character={char}
        onBack={() => {}}
        initialConversation={{
          conversation_id: "conv-9",
          character_id: "card-9",
          entity_id: "ent-9",
          universe_id: "u-1",
          version_id: "v-9",
          opening: "The chapel is quiet today.",
        }}
      />,
    );
    expect(await screen.findByText("The chapel is quiet today.")).toBeInTheDocument();
    expect(start).not.toHaveBeenCalled();
  });
});
