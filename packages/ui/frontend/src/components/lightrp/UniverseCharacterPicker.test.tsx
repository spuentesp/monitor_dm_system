// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { UniverseCharacterPicker } from "./UniverseCharacterPicker";
import { entitiesApi, universesApi } from "@/lib/api";
import { lightRpApi } from "@/lib/lightRpApi";
import type { StandaloneCharacter } from "@/lib/types";

vi.mock("@/components/NotificationProvider", () => ({
  useNotify: () => ({ notify: vi.fn() }),
}));

const entity = {
  entity_id: "ent-9",
  name: "Sister Veil",
  description: "A keeper of quiet oaths.",
  universe_id: "u-1",
};

const started = {
  conversation_id: "conv-9",
  character_id: "card-9",
  entity_id: "ent-9",
  universe_id: "u-1",
  version_id: "v-9",
  opening: "The chapel is quiet today.",
  preset: "light",
};

const card = { id: "card-9", name: "Sister Veil" } as StandaloneCharacter;

function renderPicker(onStarted = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <UniverseCharacterPicker personaId="p-1" onStarted={onStarted} onClose={() => {}} />
    </QueryClientProvider>,
  );
  return onStarted;
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(universesApi, "listUniverses").mockResolvedValue([{ id: "u-1", name: "Grey Harbour" }] as never);
  vi.spyOn(lightRpApi, "listUniverseCharacters").mockResolvedValue([entity]);
});

describe("UniverseCharacterPicker — one-click start", () => {
  it("one action opens the chat with a first message — no import or mode choice", async () => {
    const start = vi.spyOn(lightRpApi, "startUniverseCharacterChat").mockResolvedValue(started);
    const getCard = vi.spyOn(entitiesApi, "getStandaloneCharacter").mockResolvedValue(card);
    const user = userEvent.setup();
    const onStarted = renderPicker();

    await user.click(await screen.findByRole("button", { name: /sister veil/i }));

    await waitFor(() =>
      expect(start).toHaveBeenCalledWith({ entity_id: "ent-9", persona_character_id: "p-1" }),
    );
    expect(getCard).toHaveBeenCalledWith("card-9");
    await waitFor(() => expect(onStarted).toHaveBeenCalledWith(card, started));
  });
});
