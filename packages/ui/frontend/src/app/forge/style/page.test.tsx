// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as api from "@/lib/api";
import ForgeStylePage from "./page";

beforeEach(() => {
  vi.restoreAllMocks();
  globalThis.fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify({}), { status: 200, headers: { "Content-Type": "application/json" } })),
  ) as unknown as typeof fetch;
  vi.spyOn(api.toneApi, "listProfiles").mockResolvedValue({ profiles: [], total: 0 });
  vi.spyOn(api.toneApi, "listLibraries").mockResolvedValue({ libraries: [], total: 0 });
  vi.spyOn(api.toneApi, "listTags").mockResolvedValue({ tags: [], total: 0 });
  vi.spyOn(api.universesApi, "listUniverses").mockResolvedValue([]);
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ForgeStylePage />
    </QueryClientProvider>,
  );
}

describe("/forge/style — page skeleton (F3-4.0)", () => {
  it("mounts with four tabs and defaults to Profiles (the lifted ToneTab)", () => {
    renderPage();
    for (const label of ["Profiles", "Libraries", "Tags", "Lorebook"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
    expect(screen.getByText("Tone Profiles")).toBeInTheDocument();
  });

  it("renders the real Libraries panel (F3-4.2)", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Libraries" }));
    expect(await screen.findByRole("heading", { name: "Tone Libraries" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /new library/i })).toBeInTheDocument();
  });

  it("renders the real Tags panel with category tabs (F3-4.3)", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Tags" }));
    expect(await screen.findByRole("heading", { name: "Tag Definitions" })).toBeInTheDocument();
    for (const label of ["Tone", "Theme", "Style", "Concept"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
  });

  it("renders the real Lorebook panel (F3-4.4)", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Lorebook" }));
    expect(await screen.findByRole("heading", { name: "Lorebook" })).toBeInTheDocument();
    expect(screen.getByLabelText("Universe")).toBeInTheDocument();
    expect(
      await screen.findByText(/create a universe first/i),
    ).toBeInTheDocument();
  });
});
