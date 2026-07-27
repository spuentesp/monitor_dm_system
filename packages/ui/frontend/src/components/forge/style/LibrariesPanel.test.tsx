// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LibrariesPanel } from "./LibrariesPanel";
import * as api from "@/lib/api";
import type { ToneLibrary, ToneProfile } from "@/lib/types";

function library(overrides: Partial<ToneLibrary> = {}): ToneLibrary {
  return {
    library_id: "l1",
    name: "Cyberpunk 2020",
    description: "Chrome and neon",
    tone_profile_ids: [],
    pack_id: null,
    universe_id: null,
    priority: 150,
    is_default: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: null,
    ...overrides,
  };
}

function profile(overrides: Partial<ToneProfile> = {}): ToneProfile {
  return {
    profile_id: "p1",
    name: "Grim Noir",
    description: "Grim Noir",
    instruction: "Terse, gritty narration",
    trigger_tags: ["grim"],
    category: "custom",
    language: "en",
    pack_id: null,
    is_builtin: false,
    example_output: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
  globalThis.fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify({}), { status: 200, headers: { "Content-Type": "application/json" } })),
  ) as unknown as typeof fetch;
  vi.spyOn(api.toneApi, "listProfiles").mockResolvedValue({ profiles: [], total: 0 });
  vi.spyOn(api.toneApi, "listLibraries").mockResolvedValue({ libraries: [], total: 0 });
});

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LibrariesPanel />
    </QueryClientProvider>,
  );
}

describe("LibrariesPanel (F3-4.2)", () => {
  it("lists libraries with default badge and priority", async () => {
    vi.spyOn(api.toneApi, "listLibraries").mockResolvedValue({
      libraries: [library(), library({ library_id: "l2", name: "Core", is_default: true, priority: 100 })],
      total: 2,
    });
    renderPanel();

    await screen.findByText("Cyberpunk 2020");
    expect(screen.getByText("Core")).toBeInTheDocument();
    expect(screen.getByText("default")).toBeInTheDocument();
    expect(screen.getByText("priority 150")).toBeInTheDocument();
  });

  it("creates a library with selected profiles", async () => {
    vi.spyOn(api.toneApi, "listProfiles").mockResolvedValue({ profiles: [profile()], total: 1 });
    const createSpy = vi.spyOn(api.toneApi, "createLibrary").mockResolvedValue(library());
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: /new library/i }));
    await user.type(screen.getByLabelText(/library name/i), "My Library");
    await user.click(screen.getByLabelText("Grim Noir"));
    await user.click(screen.getByRole("button", { name: /create library/i }));

    await waitFor(() =>
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "My Library",
          tone_profile_ids: ["p1"],
          priority: 100,
          is_default: false,
        }),
      ),
    );
  });

  it("sets a library as default via updateLibrary", async () => {
    vi.spyOn(api.toneApi, "listLibraries").mockResolvedValue({ libraries: [library()], total: 1 });
    const updateSpy = vi.spyOn(api.toneApi, "updateLibrary").mockResolvedValue(library());
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole("button", { name: /set default/i }));

    await waitFor(() =>
      expect(updateSpy).toHaveBeenCalledWith("l1", { is_default: true }),
    );
  });

  it("deletes a non-default library", async () => {
    vi.spyOn(api.toneApi, "listLibraries").mockResolvedValue({ libraries: [library()], total: 1 });
    const deleteSpy = vi.spyOn(api.toneApi, "deleteLibrary").mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole("button", { name: /^delete$/i }));

    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith("l1"));
  });

  it("hides Set default and Delete for the default library", async () => {
    vi.spyOn(api.toneApi, "listLibraries").mockResolvedValue({
      libraries: [library({ is_default: true })],
      total: 1,
    });
    renderPanel();

    await screen.findByText("Cyberpunk 2020");
    expect(screen.queryByRole("button", { name: /set default/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^delete$/i })).not.toBeInTheDocument();
  });

  it("edits a library inline", async () => {
    vi.spyOn(api.toneApi, "listLibraries").mockResolvedValue({
      libraries: [library({ tone_profile_ids: ["p1"] })],
      total: 1,
    });
    const updateSpy = vi.spyOn(api.toneApi, "updateLibrary").mockResolvedValue(library());
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole("button", { name: /^edit$/i }));
    const nameInput = screen.getByLabelText(/edit library name/i);
    await user.clear(nameInput);
    await user.type(nameInput, "Renamed");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(updateSpy).toHaveBeenCalledWith(
        "l1",
        expect.objectContaining({ name: "Renamed", tone_profile_ids: ["p1"], priority: 150 }),
      ),
    );
  });
});
