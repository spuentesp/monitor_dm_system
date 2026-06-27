// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToneTab } from "./ToneTab";
import * as api from "@/lib/api";

beforeEach(() => {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify({}), { status: 200, headers: { "Content-Type": "application/json" } })),
  ) as unknown as typeof fetch;
  vi.spyOn(api.toneApi, "listProfiles").mockResolvedValue({ profiles: [], total: 0 });
  vi.spyOn(api.toneApi, "listLibraries").mockResolvedValue({ libraries: [], total: 0 });
});

function renderTone() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToneTab />
    </QueryClientProvider>,
  );
}

describe("ToneTab", () => {
  it("renders the section header", () => {
    renderTone();
    expect(screen.getByText("Tone Profiles")).toBeInTheDocument();
  });

  it("disables Add profile until both name and instruction are filled", () => {
    renderTone();
    const btn = screen.getByRole("button", { name: /add profile/i });
    expect(btn).toBeDisabled();
  });

  it("enables Add profile when name and instruction are filled", async () => {
    const user = userEvent.setup();
    renderTone();
    await user.type(screen.getByPlaceholderText(/profile name/i), "Geralt");
    await user.type(screen.getByPlaceholderText(/narration instruction/i), "Terse, gritty");
    expect(screen.getByRole("button", { name: /add profile/i })).not.toBeDisabled();
  });

  it("renders library list", async () => {
    vi.spyOn(api.toneApi, "listLibraries").mockResolvedValue({
      libraries: [{ library_id: "l1", name: "Default", is_default: true, tone_profile_ids: [] }],
      total: 1,
    });
    renderTone();
    await waitFor(() => expect(screen.getByText("Default")).toBeInTheDocument());
  });
});
