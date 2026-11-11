// @vitest-environment happy-dom
/**
 * CF-14 — public share page (G07):
 * - renders only what /api/share returns (server has filtered drafts)
 * - character selector re-queries with viewer_character
 * - revoked/unknown token → friendly unavailable state (404)
 * - empty story → "nothing published yet"
 * - expanding an artifact loads its detail + offers the .md export link
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError, shareApi } from "@/lib/api";
import SharePage from "./page";

// ─── next/navigation mock ─────────────────────────────────────

const nav = vi.hoisted(() => ({ token: "tok-abc" }));

vi.mock("next/navigation", () => ({
  useParams: () => ({ token: nav.token }),
}));

// ─── api mock ────────────────────────────────────────────────

vi.mock("@/lib/api", () => ({
  shareApi: {
    view: vi.fn(),
    recap: vi.fn(),
    handout: vi.fn(),
    exportUrl: vi.fn((token: string, id: string) => `/api/share/${token}/export/${id}.md`),
  },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
}));

function viewFixture(over: Record<string, unknown> = {}) {
  return {
    story_id: "story-1",
    character_id: null,
    artifacts: [
      {
        id: "art-1",
        artifact_type: "recap",
        title: "Session 4 recap",
        spoiler_level: "party",
        updated_at: "2026-11-01T00:00:00Z",
      },
    ],
    characters: [],
    ...over,
  };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SharePage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  nav.token = "tok-abc";
});

describe("SharePage (CF-14)", () => {
  it("renders published artifacts from the share view", async () => {
    vi.mocked(shareApi.view).mockResolvedValue(viewFixture() as never);
    renderPage();

    expect(await screen.findByTestId("share-artifact-list")).toBeInTheDocument();
    expect(screen.getByText("Session 4 recap")).toBeInTheDocument();
    expect(shareApi.view).toHaveBeenCalledWith("tok-abc", null);
  });

  it("shows the unavailable state for a revoked or unknown token (404)", async () => {
    vi.mocked(shareApi.view).mockRejectedValue(new ApiError(404, "Not found") as never);
    renderPage();

    const unavailable = await screen.findByTestId("share-unavailable");
    expect(unavailable).toHaveTextContent("no longer available");
    expect(unavailable).toHaveTextContent("revoked or expired");
  });

  it("shows a retry hint when rate-limited (429)", async () => {
    vi.mocked(shareApi.view).mockRejectedValue(new ApiError(429, "Too many") as never);
    renderPage();

    expect(await screen.findByTestId("share-unavailable")).toHaveTextContent(
      "Too many requests",
    );
  });

  it("renders the empty state when nothing is published", async () => {
    vi.mocked(shareApi.view).mockResolvedValue(viewFixture({ artifacts: [] }) as never);
    renderPage();

    expect(await screen.findByTestId("share-empty")).toHaveTextContent(
      "Nothing has been published yet",
    );
  });

  it("offers a character selector and re-queries with viewer_character", async () => {
    vi.mocked(shareApi.view).mockResolvedValue(
      viewFixture({
        characters: [
          { id: "char-1", name: "Mira" },
          { id: "char-2", name: "Torvin" },
        ],
      }) as never,
    );
    renderPage();

    await screen.findByTestId("share-character-picker");
    expect(shareApi.view).toHaveBeenCalledWith("tok-abc", null);

    await userEvent.selectOptions(screen.getByRole("combobox"), "char-1");
    await waitFor(() => expect(shareApi.view).toHaveBeenCalledWith("tok-abc", "char-1"));
  });

  it("expands an artifact, loads its detail, and offers the .md export", async () => {
    vi.mocked(shareApi.view).mockResolvedValue(
      viewFixture({
        artifacts: [
          {
            id: "art-1",
            artifact_type: "handout",
            title: "A letter",
            spoiler_level: "party",
            updated_at: "2026-11-01T00:00:00Z",
          },
        ],
      }) as never,
    );
    vi.mocked(shareApi.handout).mockResolvedValue({
      id: "art-1",
      story_id: "story-1",
      artifact_type: "handout",
      title: "A letter",
      content: "Come at dawn.",
      spoiler_level: "party",
      scope_character_id: null,
      published: true,
      created_at: "2026-11-01T00:00:00Z",
      updated_at: "2026-11-01T00:00:00Z",
    } as never);
    renderPage();

    await userEvent.click(await screen.findByTestId("share-artifact-art-1"));
    expect(await screen.findByTestId("share-artifact-detail")).toHaveTextContent(
      "Come at dawn.",
    );
    expect(shareApi.handout).toHaveBeenCalledWith("tok-abc", "art-1", null);
    expect(screen.getByTestId("share-export-art-1")).toHaveAttribute(
      "href",
      "/api/share/tok-abc/export/art-1.md",
    );
  });
});
