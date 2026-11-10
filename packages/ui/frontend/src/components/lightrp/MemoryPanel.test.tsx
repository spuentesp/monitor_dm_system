// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryPanel } from "./MemoryPanel";
import { lightRpApi } from "@/lib/lightRpApi";

vi.mock("@/components/NotificationProvider", () => ({
  useNotify: () => ({ notify: vi.fn() }),
}));

const memories = {
  memories: [
    {
      id: "mem-1",
      text: 'Player said: "My favourite flower is the moonpetal lily."',
      importance: 0.6,
      created_at: "2026-11-01T10:00:00Z",
    },
    {
      id: "mem-2",
      text: 'Player said: "I grew up on the coast."',
      importance: 0.5,
      created_at: "2026-11-02T10:00:00Z",
    },
  ],
  total: 2,
};

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryPanel characterId="c-1" characterName="Wisp" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("MemoryPanel — what this character remembers about you", () => {
  it("lists the character's memories of the user", async () => {
    const list = vi.spyOn(lightRpApi, "listMemoriesAboutYou").mockResolvedValue(memories);
    renderPanel();

    expect(await screen.findByText(/moonpetal lily/)).toBeInTheDocument();
    expect(screen.getByText(/grew up on the coast/)).toBeInTheDocument();
    // Cross-component call: the view is scoped to this character.
    expect(list).toHaveBeenCalledWith("c-1", { limit: 50 });
  });

  it("deleting a memory calls the delete endpoint with the character and memory id", async () => {
    vi.spyOn(lightRpApi, "listMemoriesAboutYou").mockResolvedValue(memories);
    const del = vi.spyOn(lightRpApi, "deleteMemory").mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole("button", { name: /forget memory: player said: "my favourite/i }));

    await waitFor(() => expect(del).toHaveBeenCalledWith("c-1", "mem-1"));
    expect(del).toHaveBeenCalledTimes(1);
  });

  it("shows the empty state when nothing is remembered", async () => {
    vi.spyOn(lightRpApi, "listMemoriesAboutYou").mockResolvedValue({ memories: [], total: 0 });
    renderPanel();
    expect(await screen.findByText(/doesn't remember anything about you yet/i)).toBeInTheDocument();
  });
});
