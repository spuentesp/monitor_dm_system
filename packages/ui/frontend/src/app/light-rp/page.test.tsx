// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LightRpPage from "./page";
import * as api from "@/lib/api";
import type { StandaloneCharacter } from "@/lib/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

// Keep the real chat out of page tests — it opens conversations on mount.
vi.mock("@/components/characters/CharacterChat", () => ({
  CharacterChat: ({ character, onBack }: { character: StandaloneCharacter; onBack: () => void }) => (
    <div data-testid="character-chat">
      chat:{character.name}
      <button onClick={onBack}>back</button>
    </div>
  ),
}));

vi.mock("@/components/NotificationProvider", () => ({
  useNotify: () => ({ notify: vi.fn() }),
}));

const char: StandaloneCharacter = {
  id: "c-1",
  name: "Wisp",
  description: "A fox-spirit guide.\nLikes riddles.",
  avatar_url: null,
  personality: "playful",
  gm_notes: "",
  first_message: "Hello, traveller.",
  is_ooc_persona: false,
  entity_id: null,
  default_universe_id: null,
  versions: [],
  memory_count: 7,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-30T00:00:00Z",
} as StandaloneCharacter;

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LightRpPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api.entitiesApi, "listStandaloneCharacters").mockResolvedValue([char]);
});

describe("/light-rp", () => {
  it("renders character cards with one-line summary and memory badge", async () => {
    renderPage();
    expect(await screen.findByText("Wisp")).toBeInTheDocument();
    expect(screen.getByText("A fox-spirit guide.")).toBeInTheDocument();
    expect(screen.queryByText("Likes riddles.")).not.toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument(); // memory_count badge
  });

  it("opens the chat on card Chat click and returns on back", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("button", { name: /^chat$/i }));
    expect(screen.getByTestId("character-chat")).toHaveTextContent("chat:Wisp");
    await user.click(screen.getByRole("button", { name: /back/i }));
    expect(await screen.findByText("Wisp")).toBeInTheDocument();
  });

  it("has an Import card button that accepts SillyTavern files", async () => {
    renderPage();
    const input = (await screen.findByLabelText(/import card/i)) as HTMLInputElement;
    expect(input).toHaveAttribute("type", "file");
    expect(input.accept).toContain(".json");
    expect(input.accept).toContain(".png");
  });
});
