// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TagDefinitionsPanel } from "./TagDefinitionsPanel";
import * as api from "@/lib/api";
import type { TagDefinition } from "@/lib/types";

function tagDef(overrides: Partial<TagDefinition> = {}): TagDefinition {
  return {
    tag: "grim",
    category: "tone",
    synonyms: ["dark", "bleak"],
    description: "Grimdark tone",
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
  vi.spyOn(api.toneApi, "listTags").mockResolvedValue({ tags: [], total: 0 });
});

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TagDefinitionsPanel />
    </QueryClientProvider>,
  );
}

describe("TagDefinitionsPanel (F3-4.3)", () => {
  it("lists tags for the active category", async () => {
    const listSpy = vi.spyOn(api.toneApi, "listTags").mockResolvedValue({
      tags: [tagDef()],
      total: 1,
    });
    renderPanel();

    await screen.findByText("grim");
    expect(screen.getByText("Grimdark tone")).toBeInTheDocument();
    expect(listSpy).toHaveBeenCalledWith({ category: "tone" });
  });

  it("switches between the four category tabs", async () => {
    const listSpy = vi.spyOn(api.toneApi, "listTags").mockResolvedValue({ tags: [], total: 0 });
    const user = userEvent.setup();
    renderPanel();

    for (const label of ["Tone", "Theme", "Style", "Concept"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }

    await user.click(screen.getByRole("button", { name: "Theme" }));
    await waitFor(() => expect(listSpy).toHaveBeenCalledWith({ category: "theme" }));

    await user.click(screen.getByRole("button", { name: "Concept" }));
    await waitFor(() => expect(listSpy).toHaveBeenCalledWith({ category: "concept" }));
  });

  it("creates a tag definition in the active category", async () => {
    const createSpy = vi.spyOn(api.toneApi, "createTag").mockResolvedValue(tagDef());
    const user = userEvent.setup();
    renderPanel();

    await user.type(screen.getByLabelText(/new tag name/i), "grim noir");
    await user.type(screen.getByLabelText(/new tag synonyms/i), "dark, bleak");
    await user.type(screen.getByLabelText(/new tag description/i), "Grimdark tone");
    await user.click(screen.getByRole("button", { name: /add tag/i }));

    await waitFor(() =>
      expect(createSpy).toHaveBeenCalledWith({
        tag: "grim_noir",
        category: "tone",
        synonyms: ["dark", "bleak"],
        description: "Grimdark tone",
      }),
    );
  });

  it("edits synonyms and description", async () => {
    vi.spyOn(api.toneApi, "listTags").mockResolvedValue({ tags: [tagDef()], total: 1 });
    const updateSpy = vi.spyOn(api.toneApi, "updateTag").mockResolvedValue(tagDef());
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole("button", { name: /^edit$/i }));
    const synonymsInput = screen.getByLabelText(/edit synonyms/i);
    await user.clear(synonymsInput);
    await user.type(synonymsInput, "gritty");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(updateSpy).toHaveBeenCalledWith("grim", {
        synonyms: ["gritty"],
        description: "Grimdark tone",
      }),
    );
  });

  it("deletes a non-builtin tag", async () => {
    vi.spyOn(api.toneApi, "listTags").mockResolvedValue({ tags: [tagDef()], total: 1 });
    const deleteSpy = vi.spyOn(api.toneApi, "deleteTag").mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole("button", { name: /^delete$/i }));

    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith("grim"));
  });

  it("hides Delete for builtin tags", async () => {
    vi.spyOn(api.toneApi, "listTags").mockResolvedValue({
      tags: [tagDef({ is_builtin: true })],
      total: 1,
    });
    renderPanel();

    await screen.findByText("grim");
    expect(screen.getByText("builtin")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^delete$/i })).not.toBeInTheDocument();
  });
});
