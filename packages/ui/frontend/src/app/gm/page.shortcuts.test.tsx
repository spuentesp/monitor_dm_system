// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WorldContextProvider } from "@/lib/world-context";
import GMAssistantPage from "./page";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <WorldContextProvider>
        <GMAssistantPage />
      </WorldContextProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
  globalThis.fetch = vi.fn(() =>
    Promise.resolve(new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } })),
  ) as unknown as typeof fetch;
});

describe("GM Assistant table shortcuts (UX-5)", () => {
  it("r focuses the dice roller expression input", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.keyboard("r");

    await waitFor(() =>
      expect(document.activeElement).toHaveAttribute("data-testid", "dice-expr"),
    );
  });

  it("n opens the scratchpad and focuses the note input", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.keyboard("n");

    await waitFor(() =>
      expect(document.activeElement).toHaveAttribute(
        "data-testid",
        "session-notebook-input",
      ),
    );
  });

  it("r inside the dice input types a character instead of re-focusing", async () => {
    const user = userEvent.setup();
    renderPage();

    const input = await screen.findByPlaceholderText("e.g. 2d6+3");
    await user.click(input);
    await user.keyboard("r");
    expect((input as HTMLInputElement).value).toContain("r");
  });
});
