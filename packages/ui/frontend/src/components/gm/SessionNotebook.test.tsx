// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { gmApi } from "@/lib/api";
import { SessionNotebook } from "./SessionNotebook";

function renderNotebook(universeId: string | null = "u-1") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SessionNotebook universeId={universeId} multiverseId="mv-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("SessionNotebook (P2.3 — server-backed scratchpad)", () => {
  it("hydrates from the API and debounced-saves edits back to it", async () => {
    const getSpy = vi.spyOn(gmApi, "getNotes").mockResolvedValue({
      universe_id: "u-1",
      content: "the party crossed the river",
      updated_at: "2026-07-23T10:00:00Z",
    });
    const upsertSpy = vi.spyOn(gmApi, "upsertNotes").mockResolvedValue({
      universe_id: "u-1",
      content: "",
      updated_at: "2026-07-23T10:01:00Z",
    });
    const user = userEvent.setup();
    renderNotebook();

    await waitFor(() => expect(getSpy).toHaveBeenCalledWith("u-1"));
    const textarea = (await screen.findByPlaceholderText(
      /Record events, NPC dialogue/i,
    )) as HTMLTextAreaElement;
    await waitFor(() => expect(textarea.value).toBe("the party crossed the river"));

    await user.click(textarea);
    await user.keyboard(" and found the chapel");
    await waitFor(() => expect(upsertSpy).toHaveBeenCalled(), { timeout: 3000 });
    expect(upsertSpy).toHaveBeenCalledWith(
      "u-1",
      "the party crossed the river and found the chapel",
    );
  });

  it("tells the GM where ingest proposals land (P3.2)", () => {
    vi.spyOn(gmApi, "getNotes").mockResolvedValue({
      universe_id: "u-1",
      content: "",
      updated_at: "2026-11-06T10:00:00Z",
    });
    renderNotebook();
    expect(screen.getByTestId("ingest-hint")).toHaveTextContent(
      "Proposals land in Forge → Review",
    );
  });

  it("keeps localStorage untouched — the notebook is server-backed", async () => {
    vi.spyOn(gmApi, "getNotes").mockResolvedValue({
      universe_id: "u-1",
      content: "x",
      updated_at: "2026-07-23T10:00:00Z",
    });
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    renderNotebook();
    await screen.findByPlaceholderText(/Record events, NPC dialogue/i);
    expect(setItemSpy).not.toHaveBeenCalledWith("gm-notebook-u-1", expect.anything());
  });
});
