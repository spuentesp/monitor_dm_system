// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToneTab } from "./ToneTab";
import * as api from "@/lib/api";
import type { TagDefinition, ToneProfile } from "@/lib/types";

function profile(overrides: Partial<ToneProfile> = {}): ToneProfile {
  return {
    profile_id: "p1",
    name: "Grim Noir",
    description: "Grim Noir",
    instruction: "Terse, gritty narration",
    trigger_tags: ["grim", "noir"],
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

function tagDef(overrides: Partial<TagDefinition> = {}): TagDefinition {
  return {
    tag: "grim",
    category: "tone",
    synonyms: [],
    description: "",
    example_tones: [],
    pack_id: null,
    is_builtin: false,
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

  it("sends the selected category and language on create (F3-4.1)", async () => {
    const createSpy = vi.spyOn(api.toneApi, "createProfile").mockResolvedValue(profile());
    const user = userEvent.setup();
    renderTone();

    await user.type(screen.getByPlaceholderText(/profile name/i), "Swashbuckler");
    await user.type(screen.getByPlaceholderText(/narration instruction/i), "Daring and quick");
    await user.selectOptions(screen.getByLabelText(/^category$/i), "genre");
    await user.selectOptions(screen.getByLabelText(/^language$/i), "es");
    await user.click(screen.getByRole("button", { name: /add profile/i }));

    await waitFor(() =>
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({ category: "genre", language: "es" }),
      ),
    );
  });

  it("edits a profile through toneApi.updateProfile (F3-4.1)", async () => {
    vi.spyOn(api.toneApi, "listProfiles").mockResolvedValue({ profiles: [profile()], total: 1 });
    const updateSpy = vi.spyOn(api.toneApi, "updateProfile").mockResolvedValue(profile());
    const user = userEvent.setup();
    renderTone();

    await user.click(await screen.findByRole("button", { name: /^edit$/i }));
    const instructionBox = screen.getByLabelText(/edit instruction/i);
    await user.clear(instructionBox);
    await user.type(instructionBox, "Slow-burn dread");
    await user.selectOptions(screen.getByLabelText(/edit category/i), "mood");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(updateSpy).toHaveBeenCalledWith(
        "p1",
        expect.objectContaining({
          name: "Grim Noir",
          instruction: "Slow-burn dread",
          trigger_tags: ["grim", "noir"],
          category: "mood",
          language: "en",
        }),
      ),
    );
  });

  it("cancel discards an in-progress edit without calling updateProfile", async () => {
    vi.spyOn(api.toneApi, "listProfiles").mockResolvedValue({ profiles: [profile()], total: 1 });
    const updateSpy = vi.spyOn(api.toneApi, "updateProfile").mockResolvedValue(profile());
    const user = userEvent.setup();
    renderTone();

    await user.click(await screen.findByRole("button", { name: /^edit$/i }));
    await user.click(screen.getByRole("button", { name: /^cancel$/i }));

    expect(updateSpy).not.toHaveBeenCalled();
    expect(screen.queryByLabelText(/edit instruction/i)).not.toBeInTheDocument();
  });

  it("hides Edit and Delete for builtin profiles", async () => {
    vi.spyOn(api.toneApi, "listProfiles").mockResolvedValue({
      profiles: [profile({ is_builtin: true })],
      total: 1,
    });
    renderTone();
    await screen.findByText("Grim Noir");
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^delete$/i })).not.toBeInTheDocument();
  });

  it("autocompletes trigger tags from the tag registry (F3-4.3)", async () => {
    const suggestSpy = vi.spyOn(api.toneApi, "suggestTags").mockResolvedValue({
      suggestions: [tagDef({ tag: "grim" }), tagDef({ tag: "grim_noir" })],
      partial: "gr",
      total_found: 2,
    });
    const user = userEvent.setup();
    renderTone();

    const input = screen.getByPlaceholderText(/trigger tags/i);
    await user.type(input, "noir, gr");

    const option = await screen.findByRole("option", { name: /grim_noir/i });
    await user.click(option);

    expect((input as HTMLInputElement).value).toBe("noir, grim_noir");
    expect(suggestSpy).toHaveBeenCalledWith("gr", expect.objectContaining({ limit: 8 }));
  });

  it("does not suggest tags already present in the input (F3-4.3)", async () => {
    vi.spyOn(api.toneApi, "suggestTags").mockResolvedValue({
      suggestions: [tagDef({ tag: "grim" }), tagDef({ tag: "grim_noir" })],
      partial: "gri",
      total_found: 2,
    });
    const user = userEvent.setup();
    renderTone();

    const input = screen.getByPlaceholderText(/trigger tags/i);
    await user.type(input, "grim, gri");

    expect(await screen.findByRole("option", { name: /grim_noir/i })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /^grim$/i })).not.toBeInTheDocument();
  });
});
