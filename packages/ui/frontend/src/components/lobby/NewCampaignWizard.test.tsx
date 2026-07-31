// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NewCampaignWizard } from "./NewCampaignWizard";
import * as api from "@/lib/api";
import type { Session, Universe } from "@/lib/types";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/components/NotificationProvider", () => ({
  useNotify: () => ({ notify: vi.fn() }),
}));

const universe: Universe = {
  id: "u-1",
  name: "Mistlands",
  multiverse_id: "m-1",
  genre: "dark fantasy",
  description: null,
  tags: [],
  is_active: true,
  entity_count: 120,
  session_count: 3,
  story_count: 1,
  created_at: "2026-07-01T00:00:00Z",
} as Universe;

function renderWizard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <NewCampaignWizard universes={[universe]} onClose={() => {}} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  push.mockReset();
  vi.spyOn(api.storiesApi, "listStories").mockResolvedValue({ stories: [], total: 0 });
  vi.spyOn(api.chatApi, "createSession").mockResolvedValue({ id: "s-new" } as Session);
});

describe("NewCampaignWizard", () => {
  it("walks universe → story → details and creates a session", async () => {
    const user = userEvent.setup();
    renderWizard();

    // Step 1: pick the universe
    await user.click(await screen.findByRole("button", { name: /Mistlands/ }));

    // Step 2: start a brand-new story (no existing stories mocked)
    await user.click(await screen.findByRole("button", { name: /new story/i }));

    // Step 3: title + begin
    await user.type(await screen.findByLabelText(/campaign title/i), "The Drowned Court");
    await user.click(screen.getByRole("button", { name: /begin campaign/i }));

    expect(api.chatApi.createSession).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "The Drowned Court",
        mode: "autonomous_gm",
        universe_id: "u-1",
        universe_label: "Mistlands",
      }),
    );
    expect(push).toHaveBeenCalledWith("/play?session=s-new");
  });

  it("offers existing stories in step 2", async () => {
    vi.spyOn(api.storiesApi, "listStories").mockResolvedValue({
      stories: [
        {
          id: "st-1",
          universe_id: "u-1",
          title: "Salt and Smoke",
          story_type: "campaign",
          status: "active",
          scene_count: 3,
          created_at: "2026-07-20T00:00:00Z",
        },
      ],
      total: 1,
    });
    const user = userEvent.setup();
    renderWizard();
    await user.click(await screen.findByRole("button", { name: /Mistlands/ }));
    expect(await screen.findByRole("button", { name: /Salt and Smoke/ })).toBeInTheDocument();
  });
});
