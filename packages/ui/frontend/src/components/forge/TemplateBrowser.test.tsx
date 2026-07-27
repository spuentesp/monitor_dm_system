// @vitest-environment happy-dom
/**
 * Tests for TemplateBrowser + TemplateEditorModal (F3-2b):
 * - list renders templates
 * - "New Template" opens the editor modal and submits templatesApi.create
 * - edit icon opens the modal pre-populated and submits templatesApi.update
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as api from "@/lib/api";
import type { EntityTemplate } from "@/lib/types";
import { TemplateBrowser } from "./TemplateBrowser";

const UNIVERSE_ID = "11111111-1111-1111-1111-111111111111";

function makeTemplate(over: Partial<EntityTemplate> = {}): EntityTemplate {
  return {
    template_id: "22222222-2222-2222-2222-222222222222",
    universe_id: UNIVERSE_ID,
    name: "City Guard",
    description: "A rank-and-file watchman.",
    entity_type: "character",
    base_properties: { role: "guard" },
    variable_properties: [],
    naming_pattern: { type: "numbered" },
    stat_generation: { method: "fixed", formulas: {}, constraints: {} },
    default_state_tags: ["on_duty"],
    default_detail_level: "stub",
    default_personality: null,
    parent_template_id: null,
    usage_count: 0,
    created_at: "2026-07-24T00:00:00Z",
    updated_at: null,
    ...over,
  };
}

function renderBrowser(universeId: string | null = UNIVERSE_ID) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TemplateBrowser universeId={universeId} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api.templatesApi, "list").mockResolvedValue({
    templates: [makeTemplate()],
    total: 1,
    limit: 50,
    offset: 0,
  });
});

describe("TemplateBrowser", () => {
  it("renders templates from the list endpoint", async () => {
    renderBrowser();
    expect(await screen.findByText("City Guard")).toBeInTheDocument();
  });

  it("disables New Template without a universe", async () => {
    renderBrowser(null);
    const btn = await screen.findByRole("button", { name: /new template/i });
    expect(btn).toBeDisabled();
  });

  it("creates a template via the editor modal", async () => {
    const createSpy = vi
      .spyOn(api.templatesApi, "create")
      .mockResolvedValue(makeTemplate({ name: "Dock Thug" }));
    const user = userEvent.setup();
    renderBrowser();

    await user.click(await screen.findByRole("button", { name: /new template/i }));
    // Modal opens in create mode
    expect(await screen.findByText("New Template", { selector: "h2" })).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("e.g., City Guard"), "Dock Thug");
    await user.click(screen.getByRole("button", { name: /create template/i }));

    await waitFor(() => expect(createSpy).toHaveBeenCalledOnce());
    const payload = createSpy.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.universe_id).toBe(UNIVERSE_ID);
    expect(payload.name).toBe("Dock Thug");
    expect(payload.entity_type).toBe("character");
    expect(payload.base_properties).toEqual({});
    expect(payload.variable_properties).toEqual([]);
  });

  it("shows a JSON validation error and does not submit", async () => {
    const createSpy = vi.spyOn(api.templatesApi, "create").mockResolvedValue(makeTemplate());
    const user = userEvent.setup();
    renderBrowser();

    await user.click(await screen.findByRole("button", { name: /new template/i }));
    await user.type(screen.getByPlaceholderText("e.g., City Guard"), "X");
    const basePropsField = screen.getByLabelText("Base Properties (JSON object)");
    fireEvent.change(basePropsField, { target: { value: "{not json" } });
    await user.click(screen.getByRole("button", { name: /create template/i }));

    expect(await screen.findByText("Invalid JSON")).toBeInTheDocument();
    expect(createSpy).not.toHaveBeenCalled();
  });

  it("opens the editor pre-populated and submits an update", async () => {
    const tpl = makeTemplate();
    const updateSpy = vi.spyOn(api.templatesApi, "update").mockResolvedValue(tpl);
    const user = userEvent.setup();
    renderBrowser();

    await user.click(await screen.findByRole("button", { name: /edit template/i }));
    expect(
      await screen.findByText(`Edit Template — ${tpl.name}`, { selector: "h2" }),
    ).toBeInTheDocument();

    const nameInput = screen.getByDisplayValue("City Guard");
    await user.clear(nameInput);
    await user.type(nameInput, "City Guard Captain");
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(updateSpy).toHaveBeenCalledOnce());
    const [id, payload] = updateSpy.mock.calls[0];
    expect(id).toBe(tpl.template_id);
    expect((payload as Record<string, unknown>).name).toBe("City Guard Captain");
    // Edit mode must not try to change entity_type (not in the update schema)
    expect((payload as Record<string, unknown>).entity_type).toBeUndefined();
  });
});
