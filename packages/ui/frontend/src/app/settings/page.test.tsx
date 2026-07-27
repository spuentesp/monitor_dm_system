// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SettingsPage from "./page";
import * as api from "@/lib/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

beforeEach(() => {
  vi.restoreAllMocks();
  globalThis.fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify({}), { status: 200, headers: { "Content-Type": "application/json" } })),
  ) as unknown as typeof fetch;
  // The page mounts the LLM tab by default; give its queries sane data.
  vi.spyOn(api.llmApi, "listProviders").mockResolvedValue([]);
  vi.spyOn(api.llmApi, "listAssignments").mockResolvedValue([]);
  vi.spyOn(api.dbApi, "allStatus").mockResolvedValue([]);
});

describe("/settings — tone tab (F1-5a)", () => {
  it("links to /forge/style instead of rendering an inline ToneTab", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={qc}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    await user.click(screen.getByRole("button", { name: /^tone$/i }));

    const link = await screen.findByRole("link", { name: /open forge/i });
    expect(link).toHaveAttribute("href", "/forge/style");
    // The inline tone CRUD UI is gone — no profile form on this page.
    expect(screen.queryByPlaceholderText(/profile name/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add profile/i })).not.toBeInTheDocument();
  });
});
