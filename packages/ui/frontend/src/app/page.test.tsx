// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LobbyPage from "./page";
import * as api from "@/lib/api";
import type { Session, Universe, StorySummary } from "@/lib/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/",
}));

const session: Session = {
  id: "s-1",
  title: "The Ashen Road",
  mode: "autonomous_gm",
  multiverse_id: null,
  universe_id: "u-1",
  universe_label: "Mistlands",
  world_id: null,
  character_id: null,
  created_at: "2026-07-30T10:00:00Z",
  updated_at: "2026-07-31T09:00:00Z",
  message_count: 42,
} as Session;

const universe: Universe = {
  id: "u-1",
  name: "Mistlands",
  multiverse_id: "m-1",
  genre: "dark fantasy",
  description: "A drowned kingdom.",
  tags: [],
  is_active: true,
  entity_count: 120,
  session_count: 3,
  story_count: 2,
  created_at: "2026-07-01T00:00:00Z",
} as Universe;

const story: StorySummary = {
  id: "st-1",
  universe_id: "u-1",
  title: "Salt and Smoke",
  story_type: "campaign",
  status: "active",
  scene_count: 7,
  created_at: "2026-07-20T00:00:00Z",
} as StorySummary;

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LobbyPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api.chatApi, "listSessions").mockResolvedValue([session]);
  vi.spyOn(api.universesApi, "listUniverses").mockResolvedValue([universe]);
  vi.spyOn(api.storiesApi, "listStories").mockResolvedValue({ stories: [story], total: 1 });
});

describe("Lobby — Campaigns tab", () => {
  it("shows the continue-playing rail with a resume link to /play?session=", async () => {
    renderPage();
    expect(await screen.findByText("The Ashen Road")).toBeInTheDocument();
    const cont = screen.getByRole("link", { name: /continue/i });
    expect(cont).toHaveAttribute("href", "/play?session=s-1");
  });

  it("shows a universe card with playable state and latest story", async () => {
    renderPage();
    expect(await screen.findByText("Mistlands")).toBeInTheDocument();
    expect(screen.getByText("ready")).toBeInTheDocument();
    expect(screen.getByText("Salt and Smoke")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^play$/i })).toHaveAttribute("href", "/play?universe=u-1");
    expect(screen.getByRole("link", { name: /stories/i })).toHaveAttribute(
      "href",
      "/forge/worlds?universe=u-1",
    );
  });

  it("has a New campaign call-to-action", async () => {
    renderPage();
    expect(await screen.findByRole("button", { name: /new campaign/i })).toBeInTheDocument();
  });

  it("shows an error notice with retry when universes fail to load", async () => {
    vi.spyOn(api.universesApi, "listUniverses").mockRejectedValue(new Error("backend down"));
    const user = userEvent.setup();
    renderPage();
    expect(
      await screen.findByText(/couldn't load your worlds/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/no universes yet/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(api.universesApi.listUniverses).toHaveBeenCalledTimes(2);
  });

  it("shows an inline error in the rail area when sessions fail to load", async () => {
    vi.spyOn(api.chatApi, "listSessions").mockRejectedValue(new Error("boom"));
    renderPage();
    expect(await screen.findByText(/couldn't load recent sessions/i)).toBeInTheDocument();
    expect(screen.queryByText("The Ashen Road")).not.toBeInTheDocument();
  });

  it("shows 'Stories unavailable' on cards when stories fail to load", async () => {
    vi.spyOn(api.storiesApi, "listStories").mockRejectedValue(new Error("boom"));
    renderPage();
    expect(await screen.findByText("Stories unavailable")).toBeInTheDocument();
    expect(screen.queryByText("No stories yet")).not.toBeInTheDocument();
  });
});
